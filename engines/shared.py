"""
engines.shared
==============
Common financial + technical math used by every plant-type engine.

Functions are stateless and operate on raw numbers / dicts so each engine
module can import only what it needs.

Sections:
  1. Constants
  2. Financial math   — IRR · NPV · BCR · payback · LCOE · DSCR
  3. Project finance  — debt schedule · WACC (CAPM) · BOI tax cascade
  4. Combustion math  — Dulong's formula · LHV from moisture
  5. MSW chemistry    — Thai Energy Ministry component database
  6. Carbon credit    — T-VER methodology (avoided methane from MSW)
  7. Common dataclass — ProjectFinance + WaccInputs (composed into engines)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS
# ════════════════════════════════════════════════════════════════════════════
KCAL_PER_KWH = 859.845                # 1 kWh = 859.845 kcal
KCAL_TO_MJ   = 4.184e-3
MJ_PER_KWH   = 3.6
HOURS_PER_YEAR = 8760

# LHV viability thresholds (kcal/kg) — Thai Energy Ministry
LHV_MIN_VIABLE  = 1440
LHV_TARGET_AVG  = 1670

# Default Thai market reference (2026)
THAI_MARKET = {
    "fit_industrial_waste": 6.08,
    "fit_community_waste":  5.78,
    "fit_hybrid_firm":      3.66,
    "fit_biogas":           2.0724,
    "fit_premium_8yr":      0.70,
    "mlr":                  0.06875,
    "rf_thai_35yr_bond":    0.0205,
    "mrp_set":              0.085,
    "beta_unlevered_re":    0.50,
    "boi_full_years":       8,
    "boi_partial_years":    5,
    "boi_partial_rate":     0.10,
    "cit_standard":         0.20,
    "carbon_price":         100.0,
}


# ════════════════════════════════════════════════════════════════════════════
# 2. FINANCIAL MATH
# ════════════════════════════════════════════════════════════════════════════
def irr_brentq(cash_flows: list[float]) -> Optional[float]:
    """IRR via bisection. Returns None if no real root in [-0.99, 20.0]."""
    def npv(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(cash_flows))
    lo, hi = -0.99, 20.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
        if abs(hi - lo) < 1e-8:
            return mid
    return (lo + hi) / 2


def npv_calc(cash_flows: list[float], disc: float) -> float:
    return sum(cf / (1 + disc) ** t for t, cf in enumerate(cash_flows))


def payback_period(cum_cf: list[float]) -> Optional[float]:
    """Year (1-indexed, linearly interpolated) when cumulative CF turns ≥ 0."""
    for t, v in enumerate(cum_cf):
        if v >= 0:
            if t == 0:
                return 1.0
            prev = cum_cf[t-1]
            frac = -prev / (v - prev) if (v - prev) != 0 else 0
            return t + frac
    return None


def dscr_year(cfads: float, interest: float, principal: float) -> float:
    """DSCR = CFADS / Debt Service.  Infinity when no debt service."""
    ds = interest + principal
    if ds <= 0:
        return float('inf')
    return cfads / ds


def bcr_calc(benefits: list[float], costs: list[float], disc: float) -> float:
    """PV(Benefits) / PV(Costs).  Indexed from year 1."""
    pv_b = sum(b / (1 + disc) ** (t + 1) for t, b in enumerate(benefits))
    pv_c = sum(c / (1 + disc) ** (t + 1) for t, c in enumerate(costs))
    return pv_b / pv_c if pv_c > 0 else 0.0


def lcoe_thb_per_kwh(capex_mb: float, opex_list_mb: list[float],
                      mwh_list: list[float], disc: float) -> float:
    """Levelized cost of electricity. ฿/kWh.

    LCOE = (CAPEX_MB + PV(OPEX_MB)) × 1000 / PV(MWh)
         = ฿/kWh (since MB×1000 = THB×1000 and ÷MWh gives THB×1000/MWh = ฿/kWh)
    """
    pv_cost = capex_mb + sum(o / (1 + disc) ** (t + 1)
                              for t, o in enumerate(opex_list_mb))
    pv_mwh = sum(m / (1 + disc) ** (t + 1)
                  for t, m in enumerate(mwh_list))
    if pv_mwh <= 0:
        return 0.0
    return (pv_cost * 1000) / pv_mwh


def lcoh_thb_per_ton(capex_mb: float, opex_list_mb: list[float],
                      tons_list: list[float], disc: float) -> float:
    """Levelized cost per ton of product (e.g. RDF pellets). ฿/ton."""
    pv_cost = capex_mb + sum(o / (1 + disc) ** (t + 1)
                              for t, o in enumerate(opex_list_mb))
    pv_tons = sum(t_ / (1 + disc) ** (t + 1)
                   for t, t_ in enumerate(tons_list))
    if pv_tons <= 0:
        return 0.0
    return (pv_cost * 1e6) / pv_tons


# ════════════════════════════════════════════════════════════════════════════
# 3. PROJECT FINANCE
# ════════════════════════════════════════════════════════════════════════════
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
    """CAPM-based WACC.

      βL = βu × [1 + (1 − t) × D/E]
      Ke = Rf + βL × MRP
      Kd_aftertax = Kd × (1 − t)
      WACC = E/V × Ke + D/V × Kd × (1 − t)
    """
    if debt_pct >= 1.0:
        de_ratio = 1e6
    elif debt_pct <= 0:
        de_ratio = 0.0
    else:
        de_ratio = debt_pct / (1 - debt_pct)
    beta_levered = beta_unlevered * (1 + (1 - tax_rate) * de_ratio)
    ke = rf + beta_levered * mrp
    kd_aftertax = interest_rate * (1 - tax_rate)
    e_v = 1 - debt_pct
    d_v = debt_pct
    wacc = e_v * ke + d_v * kd_aftertax
    return {
        "rf":             rf,
        "mrp":            mrp,
        "beta_unlevered": beta_unlevered,
        "beta_levered":   beta_levered,
        "ke":             ke,
        "kd":             interest_rate,
        "kd_aftertax":    kd_aftertax,
        "de_ratio":       de_ratio,
        "wacc":           wacc,
    }


def boi_tax_rate(year_idx: int, boi_full_years: int,
                  boi_partial_years: int, boi_partial_rate: float,
                  standard_rate: float) -> float:
    """Effective CIT for a given year.

      Years 0..boi_full−1                  : 0%
      Years boi_full..boi_full+partial−1   : boi_partial_rate (e.g. 10%)
      Years thereafter                     : standard_rate (20%)
    """
    if year_idx < boi_full_years:
        return 0.0
    if year_idx < boi_full_years + boi_partial_years:
        return boi_partial_rate
    return standard_rate


def capex_breakdown(epc: float, owner_pct: float, contingency_pct: float,
                     idc_pct: float, debt_pct: float,
                     mw_gross: float = 0, mw_net: float = 0) -> dict:
    """Build full CAPEX from EPC base.

      EPC + Owner (10% EPC) + Contingency (10% of EPC+Owner) + IDC (5% EPC).
    """
    owner = epc * owner_pct
    base = epc + owner
    contingency = base * contingency_pct
    idc = epc * idc_pct
    total = base + contingency + idc
    equity = total * (1 - debt_pct)
    debt = total * debt_pct
    return {
        "epc": epc,
        "owner_cost": owner,
        "contingency": contingency,
        "idc": idc,
        "total_capex": total,
        "equity": equity,
        "debt": debt,
        "capex_per_mw_installed":  total / mw_gross if mw_gross > 0 else 0,
        "capex_per_mw_contracted": total / mw_net if mw_net > 0 else 0,
    }


# ════════════════════════════════════════════════════════════════════════════
# 4. COMBUSTION MATH (Dulong's Formula)
# ════════════════════════════════════════════════════════════════════════════
def dulong_hhv(C: float, H: float, O: float, N: float, S: float) -> float:
    """Dulong HHV (kcal/kg). Inputs are % by weight (e.g. C=20.7 means 20.7%)."""
    return 80.60 * C + 339.10 * (H - O / 8.00) + 5.56 * N + 22.20 * S


def lhv_from_hhv(hhv_kcal: float, H_pct: float, moisture_pct: float) -> float:
    """LHV (kcal/kg) — subtract latent heat of moisture + H₂O from hydrogen.

      LHV = HHV − 5.72 × (9·H + M)
    """
    return hhv_kcal - 5.72 * (9.00 * H_pct + moisture_pct)


# ════════════════════════════════════════════════════════════════════════════
# 5. MSW CHEMISTRY (Thai Energy Ministry standard, % by dry weight)
# ════════════════════════════════════════════════════════════════════════════
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


def compute_msw_chemistry(composition_pct: dict, moisture: float) -> dict:
    """Aggregate MSW chemistry → HHV → LHV from composition.

      composition_pct: {component_name: wet_weight_fraction} (auto-normalised)
      moisture:        0-1 fraction (e.g. 0.50)
    """
    total_pct = sum(composition_pct.values())
    if total_pct <= 0:
        return None
    norm = {k: v / total_pct for k, v in composition_pct.items()}
    dry_factor = 1.0 - moisture

    totals = {"C": 0.0, "H": 0.0, "O": 0.0, "N": 0.0, "S": 0.0, "Ash": 0.0}
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
        "per_component":   per_component,
        "moisture_pct":    moisture * 100,
        "hhv_kcal_per_kg": hhv_total,
        "lhv_kcal_per_kg": lhv_total,
        "lhv_mj_per_kg":   lhv_total * KCAL_TO_MJ,
        "viable_min":      lhv_total >= LHV_MIN_VIABLE,
        "viable_target":   lhv_total >= LHV_TARGET_AVG,
    }


# ════════════════════════════════════════════════════════════════════════════
# 6. CARBON CREDIT (T-VER methodology — avoided methane from MSW landfill)
# ════════════════════════════════════════════════════════════════════════════
def carbon_credit_tver(waste_tons_yr: float, carbon_price: float,
                        enabled: bool = True) -> tuple[float, float]:
    """T-VER-METHWM-02 baseline emission methodology.

    BE_y = D × DOC × DOCf × F × MCF × (16/12) × GWP × (1 − OX)

    Returns (rev_mb_yr, be_tco2_yr).
    Default Thai MSW: DOC ≈ 0.148 tC/t.
    """
    if not enabled or waste_tons_yr <= 0:
        return 0.0, 0.0
    DOC, DOCf, F, MCF, GWP, OX = 0.148, 0.5, 0.5, 1.0, 21, 0.1
    be_yr = waste_tons_yr * DOC * DOCf * F * MCF * (16/12) * GWP * (1 - OX) / 1e3
    rev_mb = be_yr * carbon_price / 1e6
    return rev_mb, be_yr


# ════════════════════════════════════════════════════════════════════════════
# 7. COMMON DATACLASS — composed into each engine's input dataclass
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class ProjectFinance:
    """Financial structure — debt / interest / tax / BOI / discount rate."""
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
    """CAPM inputs."""
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085


@dataclass
class CapexStructure:
    """CAPEX build-up parameters."""
    epc_cost: float = 0.0                  # MB THB (turnkey)
    owner_cost_pct: float = 0.10
    contingency_pct: float = 0.10
    idc_pct: float = 0.05
    construction_years: int = 2


@dataclass
class CommonOpex:
    """OPEX components common to most plant types."""
    om_pct_capex: float = 0.04
    om_my_fixed: float = 0.0               # overrides om_pct_capex when > 0
    om_escalation: float = 0.03
    sga_my: float = 1.5
    sga_esc: float = 0.02
    insurance_pct: float = 0.004           # of CAPEX/yr


# ════════════════════════════════════════════════════════════════════════════
# 8. RESULT BUILDER — standard output schema all engines return
# ════════════════════════════════════════════════════════════════════════════
def build_result(*, engine_type: str, inputs: dict,
                  raw_material: dict, generation: dict,
                  capex: dict, wacc: dict, rows: list,
                  kpis: dict, fcfe: list, fcff: list,
                  cum_fcfe: list, cum_fcff: list,
                  carbon: dict = None,
                  extras: dict = None) -> dict:
    """Build the standard result dict so the GUI/Excel/PDF can render any engine."""
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
