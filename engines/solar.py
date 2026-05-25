"""
engines.solar
=============
Solar PV (ground-mount or floating) feasibility engine.

  Sunlight → PV panels → inverter → grid

Uses solar_generation_engine for PVWatts monthly profile + hourly bell curve
TOU split, then wraps the standard financial cascade.

No feedstock — the raw material is sunlight (free).
Revenue: TOU electricity (peak × peak_rate + offpeak × offpeak_rate).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy
import os, sys

# Ensure parent path is available for solar_generation_engine
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    build_result,
)

try:
    from solar_generation_engine import (
        SolarInputs as _SolarInputs,
        run_engine as _solar_run_engine,
        PVWATTS_NAKHON_SI_THAMMARAT,
        PVWATTS_REFERENCE_KW,
        DEFAULT_SOLAR_SHAPE,
    )
    _HAS_SOLAR_ENGINE = True
except ImportError:
    _HAS_SOLAR_ENGINE = False


META = {
    "code":        "solar",
    "label":       "Solar PV",
    "icon":        "☀️",
    "description": "Solar PV (ground or floating) with PVWatts profile + TOU.",
    "color":       "#F0A52B",
}


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT DATACLASS  █
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class SolarPVInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "Solar PV Project"
    cod_year: int = 2026
    project_life: int = 25

    # ── Plant sizing ────────────────────────────────────────────
    mw_gross: float = 2.0
    mw_net:   float = 2.0          # MW (= capacity_kwp × 0.001)

    # ── Raw Material — Solar resource (PVWatts) ──────────────────
    pvwatts_location: str = "Nakhon Si Thammarat"
    cooling_gain_factor: float = 1.05      # 1.0 ground · 1.05 FPV
    annual_degradation: float = 0.0055

    # ── TOU pricing ────────────────────────────────────────────
    peak_rate: float = 4.40                # ฿/kWh
    offpeak_rate: float = 2.80
    peak_start_hour: int = 9
    peak_end_hour: int = 22
    weekdays_per_year: int = 261
    weekend_days_per_year: int = 104

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 55.0
    owner_cost_pct: float = 0.08
    contingency_pct: float = 0.05
    idc_pct: float = 0.04
    construction_years: int = 1

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.015            # 1.5%/yr typical
    om_my_fixed: float = 0.0
    om_escalation: float = 0.025
    sga_my: float = 1.5
    sga_esc: float = 0.02
    insurance_pct: float = 0.003
    pdf_pct: float = 0.02

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.06
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10

    # ── WACC ────────────────────────────────────────────────────
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL = SOLAR RESOURCE  █
# ════════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: SolarPVInputs) -> dict:
    """Compute PVWatts-based monthly generation + TOU split."""
    if not _HAS_SOLAR_ENGINE:
        return {"error": "solar_generation_engine not available"}

    capacity_kwp = p.mw_net * 1000.0
    si = _SolarInputs(
        capacity_kwp=capacity_kwp,
        pvwatts_monthly_kwh=list(PVWATTS_NAKHON_SI_THAMMARAT),
        pvwatts_reference_kw=PVWATTS_REFERENCE_KW,
        cooling_gain_factor=p.cooling_gain_factor,
        solar_shape=list(DEFAULT_SOLAR_SHAPE),
        peak_start_hour=p.peak_start_hour,
        peak_end_hour=p.peak_end_hour,
        weekdays_per_year=p.weekdays_per_year,
        weekend_days_per_year=p.weekend_days_per_year,
        peak_rate=p.peak_rate if p.peak_rate > 0 else None,
        offpeak_rate=p.offpeak_rate if p.offpeak_rate > 0 else None,
        annual_degradation=p.annual_degradation,
    )
    res = _solar_run_engine(si)

    annual_kwh = res.annual_generation_kwh
    cf = annual_kwh / (capacity_kwp * 8760.0) if capacity_kwp > 0 else 0
    peak_ratio = (res.annual_peak_kwh / annual_kwh) if annual_kwh > 0 else 0

    monthly = []
    for m in res.monthly:
        monthly.append({
            "name":             m.name,
            "days":             m.days,
            "daily_yield":      m.daily_yield,
            "generation_kwh":   m.generation_kwh,
            "peak_kwh":         m.peak_generation_kwh,
            "offpeak_kwh":      m.offpeak_generation_kwh,
            "peak_value":       m.peak_value,
            "offpeak_value":    m.offpeak_value,
            "total_value":      m.total_value,
            "peak_share":       (m.peak_generation_kwh / m.generation_kwh)
                                if m.generation_kwh > 0 else 0,
        })

    return {
        "location":              p.pvwatts_location,
        "capacity_kwp":          capacity_kwp,
        "specific_yield":        res.specific_yield_pvwatts,
        "effective_yield":       res.effective_yield,
        "cooling_gain":          p.cooling_gain_factor,
        "annual_generation_kwh": annual_kwh,
        "annual_peak_kwh":       res.annual_peak_kwh,
        "annual_offpeak_kwh":    res.annual_offpeak_kwh,
        "annual_value_thb":      res.annual_value,
        "monthly":               monthly,
        "capacity_factor":       cf,
        "peak_ratio":            peak_ratio,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════════
def run_model(p: SolarPVInputs) -> dict:
    p = copy.deepcopy(p)

    raw = compute_raw_material(p)
    if "error" in raw:
        raise RuntimeError(raw["error"])

    annual_kwh = raw["annual_generation_kwh"]
    annual_value_thb = raw["annual_value_thb"] or 0
    peak_kwh = raw["annual_peak_kwh"]
    offpeak_kwh = raw["annual_offpeak_kwh"]

    # CAPEX
    cx = capex_breakdown(p.epc_cost, p.owner_cost_pct, p.contingency_pct,
                          p.idc_pct, p.debt_pct, p.mw_gross, p.mw_net)
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = capex_total / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    # Year-by-year (with annual degradation)
    rows = []
    fcfe = [-equity]
    fcff = [-capex_total]
    cum_fcfe_list = []
    cum_fcff_list = []
    cum_e = 0; cum_p = -capex_total
    opex_list = []; mwh_list = []

    base_revenue_mb = annual_value_thb / 1e6

    for y in range(p.project_life):
        deg_factor = (1 - p.annual_degradation) ** y
        revenue = base_revenue_mb * deg_factor
        net_mwh = (annual_kwh / 1000) * deg_factor

        rev_on = (peak_kwh / 1000) * deg_factor * p.peak_rate * 1000 / 1e6
        rev_off = (offpeak_kwh / 1000) * deg_factor * p.offpeak_rate * 1000 / 1e6

        # OPEX
        if p.om_my_fixed > 0:
            om = p.om_my_fixed * (1 + p.om_escalation) ** y
        else:
            om = capex_total * p.om_pct_capex * (1 + p.om_escalation) ** y
        sga = p.sga_my * (1 + p.sga_esc) ** y
        insurance = capex_total * p.insurance_pct
        pdf = revenue * p.pdf_pct
        opex = om + sga + insurance + pdf

        ebitda = revenue - opex
        ebit = ebitda - dep
        interest, principal_repay, _ = ds[y]
        ebt = ebit - interest
        tax_eff = boi_tax_rate(y, p.boi_full_years, p.boi_partial_years,
                                p.boi_partial_rate, p.tax_rate)
        tax_amt = max(ebt, 0) * tax_eff
        npat = ebt - tax_amt
        ocf = npat + dep
        cfads = npat + dep + interest
        dscr = dscr_year(cfads, interest, principal_repay)
        fcfe_y = ocf - interest - principal_repay
        fcff_y = ebit * (1 - tax_eff) + dep

        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe_list.append(cum_e); cum_fcff_list.append(cum_p)
        opex_list.append(opex); mwh_list.append(net_mwh)

        rows.append({
            "year":           y + 1,
            "calendar_year":  p.cod_year + y,
            "fit_rev":        revenue,
            "tip_rev":        0.0,
            "rdf_rev":        0.0,
            "carbon_rev":     0.0,
            "revenue":        revenue,
            "rev_breakdown":  {"Peak": rev_on, "Off-Peak": rev_off},
            "opex_om":        om,
            "opex_feedstock": 0.0,
            "opex_ash":       0.0,
            "opex_flue":      0.0,
            "opex_aux":       0.0,
            "opex_sga":       sga,
            "opex_insurance": insurance,
            "opex_pdf":       pdf,
            "opex":           opex,
            "opex_breakdown": {"O&M": om, "SG&A": sga, "Insurance": insurance, "PDF": pdf},
            "ebitda":         ebitda,
            "depreciation":   dep,
            "ebit":           ebit,
            "interest":       interest,
            "ebt":            ebt,
            "tax_eff":        tax_eff,
            "tax":            tax_amt,
            "npat":           npat,
            "ocf":            ocf,
            "principal_repay": principal_repay,
            "cfads":          cfads,
            "dscr":           dscr,
            "fcfe":           fcfe_y,
            "fcff":           fcff_y,
            "degradation":    deg_factor,
        })

    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value
        fcff[-1] += p.terminal_value

    wacc = wacc_capm(p.rf, p.mrp, p.beta_unlevered,
                      p.debt_pct, p.tax_rate, p.interest_rate)
    eirr = irr_brentq(fcfe)
    pirr = irr_brentq(fcff)
    enpv = npv_calc(fcfe, p.discount_rate)
    pnpv = npv_calc(fcff, p.discount_rate)
    pb_e = payback_period(cum_fcfe_list)
    pb_p = payback_period(cum_fcff_list)
    bcr = bcr_calc([r["revenue"] for r in rows],
                    [r["opex"] + dep for r in rows], p.discount_rate)
    lcoe = lcoe_thb_per_kwh(capex_total, opex_list, mwh_list, p.discount_rate)
    debt_dscr = [r["dscr"] for r in rows
                  if r["principal_repay"] > 0 and r["dscr"] < float('inf')]
    dscr_min = min(debt_dscr) if debt_dscr else None
    dscr_avg = sum(debt_dscr) / len(debt_dscr) if debt_dscr else None

    kpis = {
        "project_irr": pirr, "equity_irr": eirr,
        "project_npv": pnpv, "equity_npv": enpv,
        "payback_project": pb_p, "payback_equity": pb_e,
        "dscr_min": dscr_min, "dscr_avg": dscr_avg,
        "lcoe_thb_per_kwh": lcoe, "bcr": bcr,
        "wacc": wacc["wacc"], "ke": wacc["ke"],
    }

    return build_result(
        engine_type="solar",
        inputs=asdict(p),
        raw_material=raw,
        generation={
            "mwh_yr":         annual_kwh / 1000,
            "annual_kwh":     annual_kwh,
            "peak_kwh":       peak_kwh,
            "offpeak_kwh":    offpeak_kwh,
            "capacity_factor": raw["capacity_factor"],
            "peak_ratio":     raw["peak_ratio"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": 0.0, "tco2_yr": 0.0},
    )


# ════════════════════════════════════════════════════════════════════════════
# █  PRESET — Floating Solar PV 2 MW  █
# ════════════════════════════════════════════════════════════════════════════
def default_preset() -> SolarPVInputs:
    return SolarPVInputs(
        project_name="Floating Solar PV 2 MW",
        cod_year=2026, project_life=25,
        mw_gross=2.0, mw_net=2.0,
        pvwatts_location="Nakhon Si Thammarat",
        cooling_gain_factor=1.05, annual_degradation=0.0055,
        peak_rate=4.40, offpeak_rate=2.80,
        peak_start_hour=9, peak_end_hour=22,
        weekdays_per_year=261, weekend_days_per_year=104,
        epc_cost=55.0, owner_cost_pct=0.08, contingency_pct=0.05,
        idc_pct=0.04, construction_years=1,
        om_pct_capex=0.015, om_escalation=0.025,
        sga_my=1.5, sga_esc=0.02,
        insurance_pct=0.003, pdf_pct=0.02,
        debt_pct=0.70, interest_rate=0.06,
        debt_tenor=12, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS  █
# ════════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant", [
        ("project_name",          "Project Name",          "str",    ""),
        ("cod_year",              "COD Year",              "int",    ""),
        ("project_life",          "Project Life",          "int",    "yr"),
        ("mw_gross",              "MW Gross",              "float",  "MW"),
        ("mw_net",                "MW Net",                "float",  "MW"),
    ]),
    ("Solar Resource — PVWatts", [
        ("pvwatts_location",      "PVWatts Location",     "str",   ""),
        ("cooling_gain_factor",   "Cooling Gain",         "float", "× (1.0 ground · 1.05 FPV)"),
        ("annual_degradation",    "Annual Degradation",   "pct",   "%/yr"),
    ]),
    ("Revenue (TOU)", [
        ("peak_rate",             "Peak Rate",            "float", "฿/kWh"),
        ("offpeak_rate",          "Off-Peak Rate",        "float", "฿/kWh"),
        ("peak_start_hour",       "Peak Start Hour",      "int",   "0-23"),
        ("peak_end_hour",         "Peak End Hour",        "int",   "0-24"),
        ("weekdays_per_year",     "Weekdays / yr",        "int",   ""),
        ("weekend_days_per_year", "Weekend days / yr",    "int",   ""),
    ]),
    ("CAPEX & OPEX", [
        ("epc_cost",            "EPC Cost",         "float", "MB"),
        ("owner_cost_pct",      "Owner's Cost",     "pct",   "% EPC"),
        ("contingency_pct",     "Contingency",      "pct",   "%"),
        ("idc_pct",             "IDC",              "pct",   "% EPC"),
        ("construction_years",  "Construction",     "int",   "yr"),
        ("om_pct_capex",        "O&M",              "pct",   "% CAPEX/yr"),
        ("om_my_fixed",         "O&M Fixed",        "float", "MB/yr"),
        ("om_escalation",       "O&M Escalation",   "pct",   "%/yr"),
        ("sga_my",              "SG&A (Y1)",        "float", "MB/yr"),
        ("sga_esc",             "SG&A Escalation",  "pct",   "%/yr"),
        ("insurance_pct",       "Insurance",        "pct",   "% CAPEX/yr"),
        ("pdf_pct",             "PDF",              "pct",   "% of rev"),
    ]),
    ("Project Finance & BOI", [
        ("debt_pct",            "Debt Ratio",       "pct",   "%"),
        ("interest_rate",       "Interest Rate",    "pct",   "% p.a."),
        ("debt_tenor",          "Debt Tenor",       "int",   "yr"),
        ("discount_rate",       "Discount Rate",    "pct",   "%"),
        ("tax_rate",            "Tax Rate (CIT)",   "pct",   "%"),
        ("boi_full_years",      "BOI 0% Years",     "int",   "yr"),
        ("boi_partial_years",   "BOI 50% Years",    "int",   "yr"),
        ("boi_partial_rate",    "BOI Partial Rate", "pct",   "%"),
        ("rf",                  "Risk-Free Rate",   "pct",   "%"),
        ("beta_unlevered",      "β Unlevered",      "float", ""),
        ("mrp",                 "Market Risk Premium","pct", "%"),
        ("terminal_value",      "Terminal Value",   "float", "MB"),
    ]),
]


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = default_preset()
    res = run_model(p)
    k = res["kpis"]; r = res["raw_material"]
    print(f"━━━ {p.project_name} ━━━")
    print(f"  Specific yield   : {r['specific_yield']:>8,.1f} kWh/kWp/yr")
    print(f"  Effective yield  : {r['effective_yield']:>8,.1f} kWh/kWp/yr")
    print(f"  Annual gen       : {r['annual_generation_kwh']/1000:>8,.0f} MWh")
    print(f"  Capacity factor  : {r['capacity_factor']*100:>6.2f} %")
    print(f"  Annual revenue   : {(r['annual_value_thb'] or 0)/1e6:>6.2f} MB/yr")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>6.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>6.2f}%")
    print(f"  DSCR min         : {k['dscr_min']:.2f}")
