"""
engines.solar
=============
Solar PV plant (ground or floating).

Improvements (S1-S6):
  S1 — Inverter replacement at year ~12 (8-12% CAPEX hit + downtime)
  S2 — Soiling losses (dust accumulation, especially dry season)
  S3 — Land lease (ground-mount only; FPV pays nothing)
  S4 — Performance ratio (PR) decomposition
  S5 — LID (year-1) + tiered degradation
  S6 — Curtailment risk
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy
import os, sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, TaxLossCarryForward,
    capex_breakdown,
    ppa_escalated_rate, working_capital_recovery,
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


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class SolarPVInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "Solar PV Project"
    cod_year: int = 2026
    project_life: int = 25

    # ── Plant sizing ────────────────────────────────────────────
    mw_gross: float = 2.0
    mw_net:   float = 2.0
    dc_ac_ratio: float = 1.20         # S4: DC oversize vs AC inverter

    # ── Mount type (S3 land lease only for ground) ───────────────
    is_floating: bool = True

    # ── Resource ────────────────────────────────────────────────
    pvwatts_location: str = "Nakhon Si Thammarat"
    cooling_gain_factor: float = 1.05    # FPV bonus

    # ── S4: PR decomposition (overrides cooling_gain if use_pr_breakdown) ──
    use_pr_breakdown: bool = False
    temperature_derate_pct: float = 0.06     # 4-7% loss from heat
    inverter_efficiency: float = 0.97        # 96-98%
    dc_wiring_losses_pct: float = 0.03       # 2-4%
    mismatch_losses_pct: float = 0.015       # 1-2%

    # ── S2: Soiling ──────────────────────────────────────────────
    soiling_loss_pct: float = 0.03           # 3% (ground); 1.5% FPV
    cleaning_frequency_per_yr: int = 4
    cleaning_cost_per_event_mb: float = 0.2  # 200,000 ฿ × 4 = 0.8 MB/yr

    # ── S5: Degradation ──────────────────────────────────────────
    year1_lid_pct: float = 0.02              # one-time LID 2%
    annual_degradation: float = 0.0055       # 0.55%/yr after Year 1

    # ── S6: Curtailment ──────────────────────────────────────────
    curtailment_pct: float = 0.0             # 0% baseline; configurable

    # ── S1: Inverter replacement ─────────────────────────────────
    inverter_replace_year: int = 12
    inverter_replace_pct_of_capex: float = 0.10
    inverter_replace_downtime_days: int = 45

    # ── S3: Land lease (ground only) ─────────────────────────────
    land_area_rai_per_mw: float = 7.0        # ~1.1 ha/MW (no land for FPV)
    land_lease_thb_per_rai_yr: float = 30000.0
    land_lease_escalation: float = 0.02

    # ── TOU pricing ─────────────────────────────────────────────
    peak_rate: float = 4.40
    offpeak_rate: float = 2.80
    peak_start_hour: int = 9
    peak_end_hour: int = 22
    weekdays_per_year: int = 261
    weekend_days_per_year: int = 104
    cpi_escalation: float = 0.0
    cpi_linked_fraction: float = 0.0

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 55.0
    owner_cost_pct: float = 0.08
    contingency_pct: float = 0.05
    idc_pct: float = 0.04
    construction_years: int = 1
    use_idc_drawdown: bool = True
    wc_pct_revenue_yr1: float = 0.14
    dsra_months: float = 6.0
    decommissioning_pct: float = 0.02

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.015
    om_my_fixed: float = 0.0
    om_escalation: float = 0.025
    sga_my: float = 1.5
    sga_esc: float = 0.02
    insurance_par_pct: float = 0.002
    insurance_bi_pct: float = 0.001
    insurance_tpl_pct: float = 0.0005
    pdf_pct: float = 0.02

    # ── Finance ─────────────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.06
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    depreciation_years: int = 10       # tax depreciation life (≤ project life)
    nol_carryforward_years: int = 5    # tax-loss carry-forward (Thai: 5 yr)
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════
# █  HELPERS  █
# ════════════════════════════════════════════════════════════════════════
def _performance_ratio(p: SolarPVInputs) -> float:
    """S4: Decompose PR into components when use_pr_breakdown is on."""
    if not p.use_pr_breakdown:
        return p.cooling_gain_factor  # legacy multiplier (1.0 ground, 1.05 FPV)
    pr = (1 - p.temperature_derate_pct) * p.inverter_efficiency \
          * (1 - p.dc_wiring_losses_pct) * (1 - p.mismatch_losses_pct)
    return pr


# ════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL  █
# ════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: SolarPVInputs) -> dict:
    if not _HAS_SOLAR_ENGINE:
        return {"error": "solar_generation_engine not available"}

    capacity_kwp = p.mw_net * 1000.0
    pr = _performance_ratio(p)

    # When use_pr_breakdown, treat pr as the new gain (PVWatts already includes typical losses,
    # but we re-apply explicit PR multiplier on top of PVWatts as a fine-tuner)
    cooling_gain = pr if p.use_pr_breakdown else p.cooling_gain_factor

    si = _SolarInputs(
        capacity_kwp=capacity_kwp,
        pvwatts_monthly_kwh=list(PVWATTS_NAKHON_SI_THAMMARAT),
        pvwatts_reference_kw=PVWATTS_REFERENCE_KW,
        cooling_gain_factor=cooling_gain,
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

    # S2: Apply soiling on top of PVWatts (PVWatts doesn't include this)
    soiling_factor = 1 - p.soiling_loss_pct
    # S6: Curtailment
    curtail_factor = 1 - p.curtailment_pct
    effective_factor = soiling_factor * curtail_factor

    annual_kwh = res.annual_generation_kwh * effective_factor
    peak_kwh = res.annual_peak_kwh * effective_factor
    offpeak_kwh = res.annual_offpeak_kwh * effective_factor

    cf = annual_kwh / (capacity_kwp * 8760.0) if capacity_kwp > 0 else 0
    peak_ratio = (peak_kwh / annual_kwh) if annual_kwh > 0 else 0

    monthly = []
    for m in res.monthly:
        monthly.append({
            "name":           m.name,
            "days":           m.days,
            "daily_yield":    m.daily_yield * effective_factor,
            "generation_kwh": m.generation_kwh * effective_factor,
            "peak_kwh":       m.peak_generation_kwh * effective_factor,
            "offpeak_kwh":    m.offpeak_generation_kwh * effective_factor,
            "peak_value":     (m.peak_value or 0) * effective_factor,
            "offpeak_value":  (m.offpeak_value or 0) * effective_factor,
            "total_value":    (m.total_value or 0) * effective_factor,
            "peak_share":     (m.peak_generation_kwh / m.generation_kwh)
                              if m.generation_kwh > 0 else 0,
        })

    annual_value = (res.annual_value or 0) * effective_factor

    return {
        "location":              p.pvwatts_location,
        "capacity_kwp":          capacity_kwp,
        "is_floating":           p.is_floating,
        "specific_yield":        res.specific_yield_pvwatts,
        "effective_yield":       res.effective_yield * effective_factor,
        "cooling_gain":          cooling_gain,
        "performance_ratio":     pr,
        "soiling_loss_pct":      p.soiling_loss_pct,
        "curtailment_pct":       p.curtailment_pct,
        "annual_generation_kwh": annual_kwh,
        "annual_peak_kwh":       peak_kwh,
        "annual_offpeak_kwh":    offpeak_kwh,
        "annual_value_thb":      annual_value,
        "monthly":               monthly,
        "capacity_factor":       cf,
        "peak_ratio":            peak_ratio,
    }


# ════════════════════════════════════════════════════════════════════════
# █  DEGRADATION FACTOR (S5)  █
# ════════════════════════════════════════════════════════════════════════
def _degradation_factor(p: SolarPVInputs, year_idx: int) -> float:
    """S5: Year-1 LID + linear degradation after."""
    if year_idx == 0:
        return 1.0
    if year_idx == 1:
        return 1.0 - p.year1_lid_pct
    # Years 2+: LID applied, then linear from year 2
    return (1.0 - p.year1_lid_pct) * (1.0 - p.annual_degradation) ** (year_idx - 1)


def _inverter_downtime_factor(p: SolarPVInputs, year_idx: int) -> float:
    """S1: in inverter-replacement year, lose downtime_days from generation."""
    if (year_idx + 1) == p.inverter_replace_year:
        return 1 - (p.inverter_replace_downtime_days / 365.0)
    return 1.0


# ════════════════════════════════════════════════════════════════════════
# █  MAIN  █
# ════════════════════════════════════════════════════════════════════════
def run_model(p: SolarPVInputs) -> dict:
    p = copy.deepcopy(p)
    raw = compute_raw_material(p)
    if "error" in raw:
        raise RuntimeError(raw["error"])

    annual_kwh_yr1 = raw["annual_generation_kwh"]
    annual_value_yr1 = raw["annual_value_thb"] or 0
    peak_kwh_yr1 = raw["annual_peak_kwh"]
    offpeak_kwh_yr1 = raw["annual_offpeak_kwh"]

    # Year-1 estimates
    rev_yr1_mb_est = annual_value_yr1 / 1e6
    debt_pre = capex_breakdown(p.epc_cost, p.owner_cost_pct,
                                p.contingency_pct, p.idc_pct,
                                p.debt_pct)["debt"]
    debt_svc_yr1 = debt_pre * (p.interest_rate + 1 / p.debt_tenor)

    cx = capex_breakdown(
        p.epc_cost, p.owner_cost_pct, p.contingency_pct, p.idc_pct,
        p.debt_pct, p.mw_gross, p.mw_net,
        interest_rate=p.interest_rate,
        construction_years=p.construction_years,
        use_idc_drawdown=p.use_idc_drawdown,
        wc_pct_revenue_yr1=p.wc_pct_revenue_yr1,
        revenue_yr1_mb=rev_yr1_mb_est,
        dsra_months=p.dsra_months,
        debt_service_yr1_mb=debt_svc_yr1,
        decommissioning_pct=p.decommissioning_pct,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]; debt = cx["debt"]
    _dep_years = max(1, min(int(p.depreciation_years), p.project_life))
    _dep_annual = cx["total_proj_capex"] / _dep_years
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)
    _tlcf = TaxLossCarryForward(p.nol_carryforward_years)

    rows = []; fcfe = [-equity]; fcff = [-capex_total]
    cum_fcfe_list, cum_fcff_list = [], []
    cum_e = -equity; cum_p = -capex_total
    opex_list, mwh_list = [], []

    for y in range(p.project_life):
        # S5: degradation + S1: inverter downtime
        deg = _degradation_factor(p, y)
        downtime_factor = _inverter_downtime_factor(p, y)
        effective = deg * downtime_factor

        net_mwh = (annual_kwh_yr1 / 1000) * effective
        peak_rate = ppa_escalated_rate(p.peak_rate, 0, y, 0,
                                          p.cpi_escalation, p.cpi_linked_fraction)
        off_rate = ppa_escalated_rate(p.offpeak_rate, 0, y, 0,
                                         p.cpi_escalation, p.cpi_linked_fraction)
        rev_on = (peak_kwh_yr1 / 1000) * effective * peak_rate * 1000 / 1e6
        rev_off = (offpeak_kwh_yr1 / 1000) * effective * off_rate * 1000 / 1e6
        revenue = rev_on + rev_off

        # OPEX
        esc = (1 + p.om_escalation) ** y
        if p.om_my_fixed > 0:
            om = p.om_my_fixed * esc
        else:
            om = capex_total * p.om_pct_capex * esc

        sga = p.sga_my * (1 + p.sga_esc) ** y
        insurance = capex_total * (p.insurance_par_pct + p.insurance_bi_pct
                                     + p.insurance_tpl_pct)
        pdf = revenue * p.pdf_pct
        # S2: Soiling cleaning cost
        cleaning_cost = p.cleaning_cost_per_event_mb * p.cleaning_frequency_per_yr * esc

        # S3: Land lease (ground only)
        if not p.is_floating:
            land_area_rai = p.mw_net * p.land_area_rai_per_mw
            land_cost = land_area_rai * p.land_lease_thb_per_rai_yr / 1e6 \
                         * (1 + p.land_lease_escalation) ** y
        else:
            land_cost = 0

        # S1: Inverter replacement CAPEX hit in year 12
        inverter_replace_cost = (capex_total * p.inverter_replace_pct_of_capex
                                  if (y + 1) == p.inverter_replace_year else 0)

        opex = om + sga + insurance + pdf + cleaning_cost + land_cost + inverter_replace_cost

        dep = _dep_annual if y < _dep_years else 0.0
        ebitda = revenue - opex
        ebit = ebitda - dep
        interest, principal_repay, _ = ds[y]
        ebt = ebit - interest
        tax_eff = boi_tax_rate(y, p.boi_full_years, p.boi_partial_years,
                                p.boi_partial_rate, p.tax_rate)
        tax_amt = _tlcf.tax(ebt, tax_eff)   # with loss carry-forward
        npat = ebt - tax_amt
        ocf = npat + dep
        cfads = npat + dep + interest
        dscr = dscr_year(cfads, interest, principal_repay)
        fcfe_y = ocf - principal_repay   # interest already deducted in NPAT
        fcff_y = ebit * (1 - tax_eff) + dep

        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe_list.append(cum_e); cum_fcff_list.append(cum_p)
        opex_list.append(opex); mwh_list.append(net_mwh)

        rows.append({
            "year": y + 1, "calendar_year": p.cod_year + y,
            "fit_rev": revenue, "tip_rev": 0.0,
            "rdf_rev": 0.0, "carbon_rev": 0.0,
            "revenue": revenue,
            "rev_breakdown": {"Peak": rev_on, "Off-Peak": rev_off},
            "opex_om": om, "opex_feedstock": 0.0,
            "opex_ash": 0.0, "opex_flue": cleaning_cost,  # soiling cleaning visualised
            "opex_aux": land_cost,                          # land lease in aux slot
            "opex_sga": sga, "opex_insurance": insurance,
            "opex_pdf": pdf,
            "opex_inverter": inverter_replace_cost,
            "opex": opex,
            "opex_breakdown": {"O&M": om, "SG&A": sga, "Insurance": insurance,
                                "PDF": pdf, "Cleaning": cleaning_cost,
                                "Land lease": land_cost,
                                "Inverter replace": inverter_replace_cost},
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit,
            "interest": interest, "ebt": ebt,
            "tax_eff": tax_eff, "tax": tax_amt, "npat": npat, "ocf": ocf,
            "principal_repay": principal_repay,
            "cfads": cfads, "dscr": dscr,
            "fcfe": fcfe_y, "fcff": fcff_y,
            "degradation_factor": deg,
        })

    if len(fcfe) > 1:
        recovery = working_capital_recovery(cx["working_capital"], cx["dsra"])
        fcfe[-1] += recovery - cx["decom_cost"]
        fcff[-1] += recovery - cx["decom_cost"]
        if cum_fcfe_list:
            cum_fcfe_list[-1] += recovery - cx["decom_cost"]
            cum_fcff_list[-1] += recovery - cx["decom_cost"]

    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value; fcff[-1] += p.terminal_value

    wacc = wacc_capm(p.rf, p.mrp, p.beta_unlevered,
                      p.debt_pct, p.tax_rate, p.interest_rate)
    eirr = irr_brentq(fcfe); pirr = irr_brentq(fcff)
    enpv = npv_calc(fcfe, wacc["ke"])
    pnpv = npv_calc(fcff, p.discount_rate)
    pb_e = payback_period(cum_fcfe_list)
    pb_p = payback_period(cum_fcff_list)
    bcr = bcr_calc([r["revenue"] for r in rows],
                    [r["opex"] for r in rows], p.discount_rate,
                    capex_at_t0=capex_total)
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
        engine_type="solar", inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr":         annual_kwh_yr1 / 1000,
            "annual_kwh":     annual_kwh_yr1,
            "peak_kwh":       peak_kwh_yr1,
            "offpeak_kwh":    offpeak_kwh_yr1,
            "capacity_factor": raw["capacity_factor"],
            "peak_ratio":     raw["peak_ratio"],
            "performance_ratio": raw["performance_ratio"],
            "is_floating":    raw["is_floating"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": 0.0, "tco2_yr": 0.0},
    )


def default_preset() -> SolarPVInputs:
    return SolarPVInputs(
        project_name="Floating Solar PV 2 MW",
        cod_year=2026, project_life=25,
        mw_gross=2.0, mw_net=2.0,
        dc_ac_ratio=1.20,
        is_floating=True,
        pvwatts_location="Nakhon Si Thammarat",
        cooling_gain_factor=1.05,
        use_pr_breakdown=False,
        temperature_derate_pct=0.06,
        inverter_efficiency=0.97,
        dc_wiring_losses_pct=0.03,
        mismatch_losses_pct=0.015,
        soiling_loss_pct=0.015,     # FPV — 1.5% (self-cleans)
        cleaning_frequency_per_yr=2,
        cleaning_cost_per_event_mb=0.1,
        year1_lid_pct=0.02,
        annual_degradation=0.0055,
        curtailment_pct=0.0,
        inverter_replace_year=12,
        inverter_replace_pct_of_capex=0.10,
        inverter_replace_downtime_days=45,
        land_area_rai_per_mw=0.0,    # FPV: no land
        land_lease_thb_per_rai_yr=0.0,
        peak_rate=4.40, offpeak_rate=2.80,
        peak_start_hour=9, peak_end_hour=22,
        weekdays_per_year=261, weekend_days_per_year=104,
        cpi_escalation=0.0,
        epc_cost=55.0, owner_cost_pct=0.08, contingency_pct=0.05,
        idc_pct=0.04, construction_years=1,
        use_idc_drawdown=True,
        wc_pct_revenue_yr1=0.14,
        dsra_months=6.0,
        decommissioning_pct=0.02,
        om_pct_capex=0.015, om_escalation=0.025,
        sga_my=1.5, sga_esc=0.02,
        insurance_par_pct=0.002, insurance_bi_pct=0.001, insurance_tpl_pct=0.0005,
        pdf_pct=0.02,
        debt_pct=0.70, interest_rate=0.06,
        debt_tenor=12, discount_rate=0.0625,
        depreciation_years=10, nol_carryforward_years=5,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


INPUT_SECTIONS = [
    ("Plant", [
        ("project_name", "Project Name", "str", ""),
        ("cod_year", "COD Year", "int", "e.g. 2026"),
        ("project_life", "Project Life", "int", "yr"),
        ("mw_gross", "MW Gross", "float", "MW"),
        ("mw_net",   "MW Net",   "float", "MW"),
        ("dc_ac_ratio", "DC/AC ratio", "float", "× (1.2 typical)"),
        ("is_floating", "Floating (FPV)", "bool", "vs ground-mount"),
    ]),
    ("Resource — PVWatts", [
        ("pvwatts_location", "PVWatts Location", "str", ""),
        ("cooling_gain_factor", "Cooling Gain", "float", "× (1.0 ground 1.05 FPV)"),
    ]),
    ("Performance Ratio (S4 — optional override)", [
        ("use_pr_breakdown",      "Use PR Breakdown",  "bool",  "ON to use detail"),
        ("temperature_derate_pct","Temperature derate","pct",   "% (4-7%)"),
        ("inverter_efficiency",   "Inverter Eff",      "pct",   "% (96-98)"),
        ("dc_wiring_losses_pct",  "DC wiring loss",    "pct",   "% (2-4)"),
        ("mismatch_losses_pct",   "Mismatch loss",     "pct",   "% (1-2)"),
    ]),
    ("Losses & Degradation (S2 + S5 + S6)", [
        ("soiling_loss_pct",       "Soiling loss",     "pct",   "%/yr (1.5 FPV / 3-4 ground)"),
        ("cleaning_frequency_per_yr","Cleaning freq",  "int",   "times/yr"),
        ("cleaning_cost_per_event_mb","Cleaning cost", "float", "MB per event"),
        ("year1_lid_pct",          "Year-1 LID",       "pct",   "% one-time"),
        ("annual_degradation",     "Annual degradation","pct",  "%/yr after Y1"),
        ("curtailment_pct",        "Curtailment",      "pct",   "% (0 baseline)"),
    ]),
    ("Inverter Replacement (S1)", [
        ("inverter_replace_year", "Replace year",        "int",   "ปีที่ (จากเริ่ม)"),
        ("inverter_replace_pct_of_capex","Replace cost", "pct",   "% of CAPEX"),
        ("inverter_replace_downtime_days","Downtime",    "int",   "days"),
    ]),
    ("Land Lease (S3 — ground only)", [
        ("land_area_rai_per_mw",   "Land area",        "float", "rai/MW"),
        ("land_lease_thb_per_rai_yr","Lease rate",     "float", "฿/rai/yr"),
        ("land_lease_escalation",  "Lease escalation", "pct",   "%/yr"),
    ]),
    ("Revenue (TOU)", [
        ("peak_rate", "Peak Rate", "float", "฿/kWh"),
        ("offpeak_rate", "Off-Peak Rate", "float", "฿/kWh"),
        ("peak_start_hour", "Peak Start Hour", "int", "0-23"),
        ("peak_end_hour", "Peak End Hour", "int", "0-24"),
        ("weekdays_per_year", "Weekdays/yr", "int", "days/yr"),
        ("weekend_days_per_year", "Weekend/yr", "int", "days/yr"),
        ("cpi_escalation", "CPI Escalation", "pct", "%/yr"),
        ("cpi_linked_fraction", "CPI-linked", "pct", "%"),
    ]),
    ("CAPEX + Working Capital", [
        ("epc_cost", "EPC Cost", "float", "MB"),
        ("owner_cost_pct", "Owner's Cost", "pct", "% EPC"),
        ("contingency_pct", "Contingency", "pct", "%"),
        ("idc_pct", "IDC (fallback)", "pct", "% EPC"),
        ("use_idc_drawdown", "Use IDC Drawdown", "bool", ""),
        ("construction_years", "Construction", "int", "yr"),
        ("wc_pct_revenue_yr1", "Working Capital", "pct", "% Yr-1"),
        ("dsra_months", "DSRA", "float", "months"),
        ("decommissioning_pct", "Decommissioning", "pct", "% CAPEX"),
    ]),
    ("OPEX", [
        ("om_pct_capex", "O&M", "pct", "% CAPEX/yr"),
        ("om_my_fixed", "O&M Fixed", "float", "MB/yr"),
        ("om_escalation", "O&M Escalation", "pct", "%/yr"),
        ("sga_my", "SG&A (Y1)", "float", "MB/yr"),
        ("sga_esc", "SG&A Escalation", "pct", "%/yr"),
        ("insurance_par_pct", "Property all-risk", "pct", "%"),
        ("insurance_bi_pct", "Business interr.", "pct", "%"),
        ("insurance_tpl_pct", "3rd-party liab.", "pct", "%"),
        ("pdf_pct", "PDF", "pct", "%"),
    ]),
    ("Project Finance & BOI", [
        ("debt_pct", "Debt Ratio", "pct", "%"),
        ("interest_rate", "Interest Rate", "pct", "%"),
        ("debt_tenor", "Debt Tenor", "int", "yr"),
        ("discount_rate", "Discount Rate", "pct", "%"),
        ("tax_rate", "Tax Rate", "pct", "%"),
        ("depreciation_years", "Depreciation life", "int", "yr"),
        ("nol_carryforward_years", "Loss carry-fwd", "int", "yr"),
        ("boi_full_years", "BOI 0%", "int", "yr"),
        ("boi_partial_years", "BOI 50%", "int", "yr"),
        ("boi_partial_rate", "BOI Partial", "pct", "%"),
        ("rf", "Risk-Free Rate", "pct", "%"),
        ("beta_unlevered", "β Unlevered", "float", "0.5–0.9"),
        ("mrp", "MRP", "pct", "%"),
        ("terminal_value", "Terminal Value", "float", "MB"),
    ]),
]


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = default_preset()
    res = run_model(p)
    k = res["kpis"]; r = res["raw_material"]; g = res["generation"]
    print(f"━━━ {p.project_name} (improved) ━━━")
    print(f"  Mount            : {'FPV' if r['is_floating'] else 'Ground'}")
    print(f"  Specific yield   : {r['specific_yield']:>8,.1f} kWh/kWp/yr")
    print(f"  Effective yield  : {r['effective_yield']:>8,.1f} kWh/kWp/yr (post soiling)")
    print(f"  PR               : {r['performance_ratio']:>6.3f}")
    print(f"  Soiling          : {r['soiling_loss_pct']*100:>6.1f}%")
    print(f"  Annual gen Y1    : {r['annual_generation_kwh']/1000:>8,.0f} MWh")
    print(f"  Capacity factor  : {r['capacity_factor']*100:>6.2f} %")
    print(f"  Annual revenue Y1: {(r['annual_value_thb'] or 0)/1e6:>6.2f} MB")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>6.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>6.2f}%")
    print(f"  DSCR min         : {k['dscr_min']:.2f}")
