"""
engines.shared
==============
Common math used by every plant-type engine — keep it stateless.

Sections:
  1.  Constants & market benchmarks (Thailand)
  2.  Financial math (IRR, NPV, BCR, payback, LCOE, DSCR)
  3.  Project finance (debt schedule, WACC CAPM, BOI tax cascade)
  4.  CAPEX build-up (with IDC drawdown profile + working capital + DSRA)
  5.  Combustion math (Dulong formula + LHV)
  6.  MSW chemistry database (Thai Energy Ministry standard)
  7.  Carbon credit (T-VER)
  8.  PPA escalation helper
  9.  Sensitivity analysis (tornado)
  10. Monte Carlo simulation
  11. Standard result builder
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Optional


# ════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS
# ════════════════════════════════════════════════════════════════════════
KCAL_PER_KWH = 859.845
KCAL_TO_MJ   = 4.184e-3
MJ_PER_KWH   = 3.6
HOURS_PER_YEAR = 8760

# LHV viability thresholds (kcal/kg) — Thai Energy Ministry
LHV_MIN_VIABLE = 1440
LHV_TARGET_AVG = 1670

# Thai market reference (2026)
THAI_MARKET = {
    "fit_industrial_waste":  6.08,
    "fit_community_waste":   5.78,
    "fit_hybrid_firm":       3.66,
    "fit_biogas":            2.0724,
    "fit_premium_8yr":       0.70,
    "mlr":                   0.06875,
    "rf_thai_35yr_bond":     0.0205,
    "mrp_set":               0.085,
    "beta_unlevered_re":     0.50,
    "boi_full_years":        8,
    "boi_partial_years":     5,
    "boi_partial_rate":      0.10,
    "cit_standard":          0.20,
    "carbon_price":          100.0,
    "cpi_avg":               0.02,     # Thai CPI ~2%/yr average
    "rec_price_min":         150.0,    # ฿/MWh — Thailand I-REC market low
    "rec_price_max":         300.0,    # ฿/MWh — high
}


# ════════════════════════════════════════════════════════════════════════
# 2. FINANCIAL MATH
# ════════════════════════════════════════════════════════════════════════
def irr_brentq(cash_flows: list[float]) -> Optional[float]:
    """IRR via bisection on NPV(r) in range [-99%, 2000%]."""
    def npv(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(cash_flows))
    lo, hi = -0.99, 20.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0: lo = mid
        else:            hi = mid
        if abs(hi - lo) < 1e-8: return mid
    return (lo + hi) / 2


def npv_calc(cash_flows: list[float], disc: float) -> float:
    return sum(cf / (1 + disc) ** t for t, cf in enumerate(cash_flows))


def payback_period(cum_cf: list[float]) -> Optional[float]:
    """Year (1-indexed, linearly interpolated) when cumulative CF first turns ≥ 0."""
    for t, v in enumerate(cum_cf):
        if v >= 0:
            if t == 0: return 1.0
            prev = cum_cf[t-1]
            frac = -prev / (v - prev) if (v - prev) != 0 else 0
            return t + frac
    return None


def dscr_year(cfads: float, interest: float, principal: float) -> float:
    ds = interest + principal
    if ds <= 0: return float('inf')
    return cfads / ds


def bcr_calc(benefits: list[float], costs: list[float], disc: float,
              capex_at_t0: float = 0.0) -> float:
    """UNIDO-style BCR = PV(benefits) / [CAPEX + PV(operating costs)].

    Pass `capex_at_t0` (undiscounted, Year-0 cash outflow) so the denominator
    is true total cost basis. `costs` should be operating cash costs (NOT
    include depreciation, which is non-cash and already represented by CAPEX).
    """
    pv_b = sum(b / (1 + disc) ** (t + 1) for t, b in enumerate(benefits))
    pv_c = capex_at_t0 + sum(c / (1 + disc) ** (t + 1) for t, c in enumerate(costs))
    return pv_b / pv_c if pv_c > 0 else 0.0


def lcoe_thb_per_kwh(capex_mb: float, opex_list_mb: list[float],
                      mwh_list: list[float], disc: float) -> float:
    pv_cost = capex_mb + sum(o / (1 + disc) ** (t + 1)
                              for t, o in enumerate(opex_list_mb))
    pv_mwh  = sum(m / (1 + disc) ** (t + 1) for t, m in enumerate(mwh_list))
    if pv_mwh <= 0: return 0.0
    return (pv_cost * 1000) / pv_mwh


def lcoh_thb_per_ton(capex_mb: float, opex_list_mb: list[float],
                      tons_list: list[float], disc: float) -> float:
    pv_cost = capex_mb + sum(o / (1 + disc) ** (t + 1)
                              for t, o in enumerate(opex_list_mb))
    pv_tons = sum(t_ / (1 + disc) ** (t + 1) for t, t_ in enumerate(tons_list))
    if pv_tons <= 0: return 0.0
    return (pv_cost * 1e6) / pv_tons


# ════════════════════════════════════════════════════════════════════════
# 3. PROJECT FINANCE
# ════════════════════════════════════════════════════════════════════════
def debt_schedule_annuity(principal: float, rate: float, tenor: int,
                           total_years: int) -> list[tuple[float, float, float]]:
    """Equal-payment annuity. Returns (interest, principal_repay, end_balance)."""
    if principal <= 0 or rate <= 0 or tenor <= 0:
        return [(0.0, 0.0, 0.0)] * total_years
    pmt = principal * rate * (1 + rate) ** tenor / ((1 + rate) ** tenor - 1)
    bal = principal
    out = []
    for y in range(total_years):
        if y < tenor and bal > 1e-6:
            interest = bal * rate
            repay = min(pmt - interest, bal)
            bal = max(bal - repay, 0)
        else:
            interest = repay = 0.0
        out.append((interest, repay, bal))
    return out


def wacc_capm(rf: float, mrp: float, beta_unlevered: float,
               debt_pct: float, tax_rate: float, interest_rate: float) -> dict:
    if debt_pct >= 1.0:   de_ratio = 1e6
    elif debt_pct <= 0:   de_ratio = 0.0
    else:                 de_ratio = debt_pct / (1 - debt_pct)
    beta_levered = beta_unlevered * (1 + (1 - tax_rate) * de_ratio)
    ke = rf + beta_levered * mrp
    kd_aftertax = interest_rate * (1 - tax_rate)
    e_v = 1 - debt_pct
    d_v = debt_pct
    wacc = e_v * ke + d_v * kd_aftertax
    return {
        "rf": rf, "mrp": mrp,
        "beta_unlevered": beta_unlevered, "beta_levered": beta_levered,
        "ke": ke, "kd": interest_rate, "kd_aftertax": kd_aftertax,
        "de_ratio": de_ratio, "wacc": wacc,
    }


def boi_tax_rate(year_idx: int, boi_full_years: int,
                  boi_partial_years: int, boi_partial_rate: float,
                  standard_rate: float) -> float:
    """Effective CIT cascade: 0% (BOI full) → partial rate → standard."""
    if year_idx < boi_full_years:                                  return 0.0
    if year_idx < boi_full_years + boi_partial_years:              return boi_partial_rate
    return standard_rate


# ════════════════════════════════════════════════════════════════════════
# 4. CAPEX BUILD-UP (with IDC drawdown, working capital, DSRA, decom)
# ════════════════════════════════════════════════════════════════════════
def calc_idc(debt_amount: float, interest_rate: float,
              construction_years: int,
              drawdown_profile: Optional[list[float]] = None) -> float:
    """Interest During Construction with realistic drawdown profile.

    Default S-curve (Phase 1 + 2 + 3 = 100%):
      1-year build: [1.0]
      2-year build: [0.40, 0.60]
      3-year build: [0.20, 0.50, 0.30]
      4-year build: [0.15, 0.30, 0.35, 0.20]
    """
    if drawdown_profile is None:
        defaults = {1: [1.0], 2: [0.4, 0.6],
                    3: [0.20, 0.50, 0.30],
                    4: [0.15, 0.30, 0.35, 0.20]}
        drawdown_profile = defaults.get(construction_years,
                                         [1.0/construction_years]*construction_years)
    idc = 0.0
    drawn = 0.0
    for yr, pct in enumerate(drawdown_profile):
        drawn += debt_amount * pct
        # Interest on drawn amount for remaining build years
        years_remaining = construction_years - yr - 0.5  # mid-year approx
        idc += drawn * interest_rate * max(years_remaining, 0)
    return idc


def capex_breakdown(epc: float, owner_pct: float, contingency_pct: float,
                     idc_pct: float, debt_pct: float,
                     mw_gross: float = 0, mw_net: float = 0,
                     *,
                     interest_rate: Optional[float] = None,
                     construction_years: int = 2,
                     use_idc_drawdown: bool = False,
                     wc_pct_revenue_yr1: float = 0.0,
                     revenue_yr1_mb: float = 0.0,
                     dsra_months: float = 0.0,
                     debt_service_yr1_mb: float = 0.0,
                     decommissioning_pct: float = 0.0) -> dict:
    """Build full CAPEX from EPC base. Returns dict.

    NEW (C1, C2, C5):
      • use_idc_drawdown=True → compute IDC via drawdown profile
        (requires interest_rate + construction_years)
      • wc_pct_revenue_yr1   → working capital as % of Year-1 revenue
      • dsra_months          → DSRA reserve in months of Year-1 debt service
      • decommissioning_pct  → end-of-life cost (% CAPEX), recovered at year N
    """
    owner = epc * owner_pct
    base = epc + owner
    contingency = base * contingency_pct

    # Pre-WC pre-DSRA CAPEX for IDC base
    pre_idc_capex = base + contingency
    debt_amount = pre_idc_capex * debt_pct

    if use_idc_drawdown and interest_rate is not None:
        idc = calc_idc(debt_amount, interest_rate, construction_years)
    else:
        idc = epc * idc_pct

    total_proj = base + contingency + idc

    # Working capital (return at end of project life)
    wc = revenue_yr1_mb * (wc_pct_revenue_yr1 if wc_pct_revenue_yr1
                            else 0.0)
    # DSRA reserve
    dsra = debt_service_yr1_mb * (dsra_months / 12.0)

    total = total_proj + wc + dsra

    equity = total * (1 - debt_pct)
    debt = total * debt_pct

    decom_cost = total_proj * decommissioning_pct  # end-of-life outflow

    return {
        "epc":             epc,
        "owner_cost":      owner,
        "contingency":     contingency,
        "idc":             idc,
        "working_capital": wc,
        "dsra":            dsra,
        "total_proj_capex": total_proj,    # excludes WC/DSRA
        "total_capex":     total,
        "equity":          equity,
        "debt":            debt,
        "decom_cost":      decom_cost,
        "capex_per_mw_installed":  total / mw_gross if mw_gross > 0 else 0,
        "capex_per_mw_contracted": total / mw_net   if mw_net   > 0 else 0,
    }


def working_capital_recovery(working_capital_mb: float,
                              dsra_mb: float) -> float:
    """Returned at end of project (added to last-year FCFE)."""
    return working_capital_mb + dsra_mb


# ════════════════════════════════════════════════════════════════════════
# 5. COMBUSTION MATH
# ════════════════════════════════════════════════════════════════════════
def dulong_hhv(C: float, H: float, O: float, N: float, S: float) -> float:
    """Dulong HHV (kcal/kg). All inputs are % by weight.

    Coefficients per Channiwala & Parikh (2002) review of Dulong-form
    correlations for solid fuels:
        HHV = 81.0·C + 342.5·(H − O/8) + 22.5·S   (canonical Dulong)
    The N term (5.56) is from the extended Wilson variant — small but
    relevant for high-N waste (food/cloth/leather).
    """
    return 81.0 * C + 342.5 * (H - O / 8.00) + 5.56 * N + 22.5 * S


def lhv_from_hhv(hhv_kcal: float, H_pct: float, moisture_pct: float) -> float:
    """LHV = HHV − 5.84 × (9H + Moisture).

    Factor 5.84 corresponds to the ISO 1928 latent heat of vapourisation
    at 25 °C (h_fg ≈ 583.9 kcal/kg of water) divided by 100 to match
    %-weight inputs of H and Moisture.
    """
    return hhv_kcal - 5.84 * (9.00 * H_pct + moisture_pct)


# ════════════════════════════════════════════════════════════════════════
# 6. MSW CHEMISTRY (Thai Energy Ministry, % dry weight)
# ════════════════════════════════════════════════════════════════════════
MSW_COMPONENT_CHEMISTRY = {
    "food":      {"C": 48.00, "H": 6.40,  "O": 32.60, "N": 2.60, "S": 0.40, "Ash": 10.00},
    "paper":     {"C": 43.50, "H": 6.00,  "O": 44.00, "N": 0.30, "S": 0.30, "Ash":  6.00},
    "cardboard": {"C": 44.00, "H": 5.90,  "O": 44.60, "N": 0.30, "S": 0.30, "Ash":  5.00},
    "plastic":   {"C": 60.00, "H": 7.20,  "O": 22.80, "N": 0.00, "S": 0.00, "Ash": 10.00},
    "cloth":     {"C": 55.00, "H": 6.60,  "O": 31.20, "N": 4.60, "S": 0.10, "Ash":  2.50},
    "rubber":    {"C": 78.00, "H": 10.00, "O":  0.00, "N": 2.00, "S": 0.00, "Ash": 10.00},
    "leather":   {"C": 60.00, "H": 8.00,  "O": 11.60, "N":10.00, "S": 0.40, "Ash": 10.00},
    "wood":      {"C": 48.65, "H": 6.00,  "O": 40.35, "N": 1.80, "S": 0.20, "Ash":  3.00},
    "glass":     {"C":  0.50, "H": 0.10,  "O":  0.40, "N": 0.10, "S": 0.00, "Ash": 98.90},
    "metal":     {"C":  4.80, "H": 0.60,  "O":  4.50, "N": 0.10, "S": 0.00, "Ash": 90.00},
    "hazardous": {"C": 26.30, "H": 3.00,  "O":  2.00, "N": 0.50, "S": 0.20, "Ash": 68.00},
    "other":     {"C": 26.30, "H": 3.00,  "O":  2.00, "N": 0.50, "S": 0.20, "Ash": 68.00},
}

# Chlorine content (% dry weight) — Thai reference for RDF quality
MSW_COMPONENT_CHLORINE = {
    "food":      0.40, "paper":     0.20, "cardboard": 0.20,
    "plastic":   0.80, "cloth":     0.30, "rubber":    0.10,
    "leather":   0.10, "wood":      0.05, "glass":     0.00,
    "metal":     0.00, "hazardous": 1.50, "other":     0.50,
}


def compute_msw_chemistry(composition_pct: dict, moisture: float) -> dict:
    """Aggregate MSW chemistry → HHV → LHV from weighted composition."""
    total_pct = sum(composition_pct.values())
    if total_pct <= 0:
        return None
    norm = {k: v / total_pct for k, v in composition_pct.items()}
    dry_factor = 1.0 - moisture

    totals = {"C": 0.0, "H": 0.0, "O": 0.0, "N": 0.0, "S": 0.0, "Ash": 0.0}
    cl_total = 0.0
    per_component = {}
    component_hhv = {}

    for comp_name, wet_frac in norm.items():
        if wet_frac <= 0 or comp_name not in MSW_COMPONENT_CHEMISTRY:
            continue
        chem = MSW_COMPONENT_CHEMISTRY[comp_name]
        weighted = {}
        for elem, val_dry in chem.items():
            w_pct = wet_frac * dry_factor * val_dry
            weighted[elem] = w_pct
            totals[elem] += w_pct
        # Chlorine
        cl_total += wet_frac * dry_factor * MSW_COMPONENT_CHLORINE.get(comp_name, 0)

        c, h, o, n, s = (weighted["C"], weighted["H"], weighted["O"],
                          weighted["N"], weighted["S"])
        hhv_c = dulong_hhv(c, h, o, n, s)
        component_hhv[comp_name] = hhv_c
        per_component[comp_name] = {
            "wet_pct":     wet_frac * 100,
            "dry_pct":     wet_frac * dry_factor * 100,
            "weighted":    weighted,
            "hhv_contrib": hhv_c,
        }

    hhv_total = sum(component_hhv.values())
    lhv_total = lhv_from_hhv(hhv_total, totals["H"], moisture * 100)

    return {
        "totals":          totals,
        "chlorine_pct":    cl_total,
        "per_component":   per_component,
        "moisture_pct":    moisture * 100,
        "hhv_kcal_per_kg": hhv_total,
        "lhv_kcal_per_kg": lhv_total,
        "lhv_mj_per_kg":   lhv_total * KCAL_TO_MJ,
        "viable_min":      lhv_total >= LHV_MIN_VIABLE,
        "viable_target":   lhv_total >= LHV_TARGET_AVG,
    }


# ════════════════════════════════════════════════════════════════════════
# 7. CARBON CREDIT (T-VER methodology)
# ════════════════════════════════════════════════════════════════════════
def carbon_credit_tver(waste_tons_yr: float, carbon_price: float,
                        enabled: bool = True) -> tuple[float, float]:
    """T-VER-METHWM-02 — avoided methane from MSW landfill.

    BE_y = D × DOC × DOCf × F × MCF × (16/12) × GWP × (1 − OX)
    Default Thai MSW: DOC ≈ 0.148 tC/t.
    """
    if not enabled or waste_tons_yr <= 0:
        return 0.0, 0.0
    DOC, DOCf, F, MCF, GWP, OX = 0.148, 0.5, 0.5, 1.0, 21, 0.1
    # be_yr in tCO2e/yr; revenue in MB/yr (= tCO2e × THB/tCO2e ÷ 1e6 THB/MB)
    be_yr = waste_tons_yr * DOC * DOCf * F * MCF * (16/12) * GWP * (1 - OX)
    rev_mb = be_yr * carbon_price / 1e6
    return rev_mb, be_yr


# ════════════════════════════════════════════════════════════════════════
# 8. PPA ESCALATION (C3)
# ════════════════════════════════════════════════════════════════════════
def ppa_escalated_rate(base_rate: float, premium: float, year_idx: int,
                        premium_years: int,
                        cpi_escalation: float = 0.0,
                        cpi_linked_fraction: float = 0.0) -> float:
    """FiT/PPA rate for a given year.

      Total rate = base + (premium if y < premium_years)
      If cpi_linked_fraction > 0, that portion escalates by CPI each year.
      Thai SPP Hybrid: FiTv ~ 50% × (1+CPI)^y; FiTf flat.
    """
    rate = base_rate + (premium if year_idx < premium_years else 0.0)
    if cpi_escalation > 0 and cpi_linked_fraction > 0:
        flat_part   = rate * (1 - cpi_linked_fraction)
        linked_part = rate * cpi_linked_fraction * (1 + cpi_escalation) ** year_idx
        rate = flat_part + linked_part
    return rate


# ════════════════════════════════════════════════════════════════════════
# 9. SENSITIVITY ANALYSIS (C7)
# ════════════════════════════════════════════════════════════════════════
def compute_sensitivity(run_model_fn: Callable,
                         base_params,
                         dimensions: list[tuple[str, float, float]],
                         metric: str = "equity_irr") -> dict:
    """Tornado-style sensitivity.

    Args:
      run_model_fn:  engine's run_model function
      base_params:   dataclass instance (will be deepcopied for each variant)
      dimensions:    [(param_name, down_pct, up_pct), ...]
                      e.g. ('epc_cost', -0.20, +0.20)
      metric:        kpi key to track (default equity_irr)

    Returns:
      {
        "base":  base metric value,
        "items": [{name, down_pct, up_pct, down_value, up_value,
                    down_delta, up_delta}, ...]  — sorted by |max_delta| desc
      }
    """
    base_res = run_model_fn(copy.deepcopy(base_params))
    base_val = base_res["kpis"].get(metric) or 0

    items = []
    for name, dn, up in dimensions:
        try:
            p_dn = copy.deepcopy(base_params)
            orig = getattr(p_dn, name, None)
            if orig is None: continue
            setattr(p_dn, name, orig * (1 + dn))
            res_dn = run_model_fn(p_dn)
            val_dn = res_dn["kpis"].get(metric) or 0

            p_up = copy.deepcopy(base_params)
            setattr(p_up, name, orig * (1 + up))
            res_up = run_model_fn(p_up)
            val_up = res_up["kpis"].get(metric) or 0

            items.append({
                "name": name,
                "down_pct":   dn,
                "up_pct":     up,
                "down_value": val_dn,
                "up_value":   val_up,
                "down_delta": val_dn - base_val,
                "up_delta":   val_up - base_val,
                "max_abs_delta": max(abs(val_dn - base_val),
                                      abs(val_up - base_val)),
            })
        except Exception:
            continue

    items.sort(key=lambda x: x["max_abs_delta"], reverse=True)
    return {"base": base_val, "metric": metric, "items": items}


# ════════════════════════════════════════════════════════════════════════
# 10. MONTE CARLO SIMULATION (C7)
# ════════════════════════════════════════════════════════════════════════
def monte_carlo(run_model_fn: Callable,
                 base_params,
                 distributions: dict[str, dict],
                 n_runs: int = 1000,
                 metric: str = "equity_irr",
                 seed: Optional[int] = 42) -> dict:
    """Run Monte Carlo simulation.

    Args:
      distributions: {param_name: {"dist": "triangular"|"normal"|"uniform",
                                    "low": ..., "mid": ..., "high": ...}}
                      (mid is mean for normal)

    Returns:
      {
        "samples": list of metric values,
        "p10": 10th percentile,
        "p50": median,
        "p90": 90th percentile,
        "mean": mean,
        "std": stdev,
        "n_runs": int,
      }
    """
    rng = random.Random(seed)

    def sample(spec):
        d = spec.get("dist", "triangular")
        if d == "triangular":
            return rng.triangular(spec["low"], spec["high"], spec["mid"])
        if d == "normal":
            return rng.gauss(spec["mid"], spec.get("std", 0.1 * spec["mid"]))
        if d == "uniform":
            return rng.uniform(spec["low"], spec["high"])
        return spec["mid"]

    samples = []
    for _ in range(n_runs):
        p = copy.deepcopy(base_params)
        for name, spec in distributions.items():
            if hasattr(p, name):
                setattr(p, name, sample(spec))
        try:
            res = run_model_fn(p)
            v = res["kpis"].get(metric)
            if v is not None:
                samples.append(v)
        except Exception:
            continue

    samples.sort()
    n = len(samples)
    if n == 0:
        return {"samples": [], "n_runs": 0}

    def pct(p):
        # Linear interpolation between order statistics (numpy default).
        if n == 1:
            return samples[0]
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        frac = pos - lo
        return samples[lo] + frac * (samples[hi] - samples[lo])

    mean = sum(samples) / n
    var = sum((x - mean) ** 2 for x in samples) / n
    std = var ** 0.5

    return {
        "samples": samples,
        "p10":     pct(0.10),
        "p50":     pct(0.50),
        "p90":     pct(0.90),
        "min":     samples[0],
        "max":     samples[-1],
        "mean":    mean,
        "std":     std,
        "n_runs":  n,
        "metric":  metric,
    }


# ════════════════════════════════════════════════════════════════════════
# 11. SHARED DATACLASSES (composed into engines)
# ════════════════════════════════════════════════════════════════════════
@dataclass
class ProjectFinance:
    debt_pct: float = 0.70
    interest_rate: float = 0.06375
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10


@dataclass
class WaccInputs:
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085


# ════════════════════════════════════════════════════════════════════════
# 12. RESULT BUILDER
# ════════════════════════════════════════════════════════════════════════
def build_result(*, engine_type: str, inputs: dict,
                  raw_material: dict, generation: dict,
                  capex: dict, wacc: dict, rows: list,
                  kpis: dict, fcfe: list, fcff: list,
                  cum_fcfe: list, cum_fcff: list,
                  carbon: dict = None, extras: dict = None) -> dict:
    out = {
        "engine_type":   engine_type,
        "inputs":        inputs,
        "raw_material":  raw_material,
        "generation":    generation,
        "capex":         capex,
        "wacc":          wacc,
        "rows":          rows,
        "fcfe":          fcfe,
        "fcff":          fcff,
        "cum_fcfe":      cum_fcfe,
        "cum_fcff":      cum_fcff,
        "kpis":          kpis,
        "carbon":        carbon or {"rev_mb_yr": 0.0, "tco2_yr": 0.0},
    }
    if extras:
        out["extras"] = extras
    return out
