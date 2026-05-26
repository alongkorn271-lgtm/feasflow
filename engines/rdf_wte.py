"""
engines.rdf_wte
================
Combined RDF + WTE plant with 3-way mass balance.

Improvements (RW1-RW3):
  RW1 — Separate LHV per stream (RDF-side high LHV, WTE-side rejects low LHV)
  RW2 — 3-way mass balance with reject (RDF → cement / WTE feed / reject)
  RW3 — Operating flexibility (min/max RDF split for scenarios)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    KCAL_PER_KWH,
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    compute_msw_chemistry, carbon_credit_tver,
    ppa_escalated_rate, working_capital_recovery,
    MSW_COMPONENT_CHEMISTRY,
    build_result,
)


META = {
    "code":        "rdf_wte",
    "label":       "RDF + WTE",
    "icon":        "🔄",
    "description": "Combined: split MSW into RDF (sell) + WTE feed (electricity).",
    "color":       "#26C6DA",
}


# Components that survive RDF processing (combustibles)
RDF_KEEP_COMPONENTS = {"paper", "cardboard", "plastic", "cloth",
                       "rubber", "leather", "wood"}


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class RDFWTEInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "RDF + WTE Plant"
    cod_year: int = 2027
    project_life: int = 20

    # ── Plant sizing (WTE side) ──────────────────────────────────
    mw_gross: float = 9.9
    parasitic_load_pct: float = 0.15
    mw_net: float = 8.0       # legacy compat — actual = mw_gross × (1-parasitic)
    availability: float = 0.85
    op_days: int = 330
    performance_warranty: float = 0.90
    boiler_efficiency: float = 0.78
    turbine_efficiency: float = 0.28
    efficiency: float = 0.0   # 0 = use boiler×turbine

    # ── MSW intake + 3-way split (RW2) ───────────────────────────
    msw_intake_design_t_d: float = 500.0
    actual_utilization: float = 0.85
    rdf_split_pct: float = 0.30
    rdf_yield_within_split: float = 0.65   # RW2: of MSW going to RDF line,
                                              # only 65% becomes sellable RDF
    reject_pct: float = 0.05                # RW2: 5% rejected (to landfill or WTE)
    # Operating bounds for scenarios
    rdf_split_min: float = 0.10
    rdf_split_max: float = 0.50

    # MSW composition
    use_msw_auto: bool = True
    msw_moisture: float = 0.40
    rdf_moisture_after_drying: float = 0.15
    msw_pct_food:      float = 0.30
    msw_pct_paper:     float = 0.10
    msw_pct_plastic:   float = 0.35
    msw_pct_glass:     float = 0.08
    msw_pct_metal:     float = 0.04
    msw_pct_cloth:     float = 0.05
    msw_pct_wood:      float = 0.05
    msw_pct_rubber:    float = 0.01
    msw_pct_leather:   float = 0.00
    msw_pct_hazardous: float = 0.01
    msw_pct_other:     float = 0.01
    ncv_mj_per_kg_manual: float = 10.0

    # ── Ash (W4 split) ───────────────────────────────────────────
    bottom_ash_pct: float = 0.15
    fly_ash_pct: float = 0.05
    bottom_ash_disposal_thb_per_ton: float = 800.0
    fly_ash_disposal_thb_per_ton: float = 3000.0
    ash_pct: float = 0.20      # legacy
    ash_disposal_cost: float = 800.0

    # ── RDF revenue ──────────────────────────────────────────────
    use_quality_tier_pricing: bool = True
    rdf_price_thb_per_kcal_high: float = 0.24
    rdf_price_thb_per_kcal_std:  float = 0.20
    rdf_price_thb_per_kcal_low:  float = 0.15
    rdf_price_thb_per_kcal: float = 0.20    # fallback flat
    rdf_price_esc: float = 0.015
    transport_rdf_thb_per_ton: float = 260.0
    offtake_utilization: float = 0.85

    # ── WTE revenue ──────────────────────────────────────────────
    fit_base: float = 5.78
    fit_premium: float = 0.70
    premium_years: int = 8
    cpi_escalation: float = 0.02
    cpi_linked_fraction: float = 0.0
    tipping_fee: float = 400.0
    tipping_esc: float = 0.02
    carbon_price: float = 100.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 2100.0
    owner_cost_pct: float = 0.10
    contingency_pct: float = 0.10
    idc_pct: float = 0.05
    construction_years: int = 3
    use_idc_drawdown: bool = True
    wc_pct_revenue_yr1: float = 0.16
    dsra_months: float = 6.0
    decommissioning_pct: float = 0.02

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.05
    om_my_fixed: float = 0.0
    om_escalation: float = 0.03

    flue_gas_cost: float = 15.0
    use_fgt_scaling: bool = True
    lime_kg_per_ton_msw: float = 12.0
    lime_price_thb_per_ton: float = 4500.0
    urea_kg_per_ton_msw: float = 3.0
    urea_price_thb_per_ton: float = 18000.0
    ac_kg_per_ton_msw: float = 0.5
    ac_price_thb_per_ton: float = 60000.0
    bag_filter_replace_yrs: int = 3
    bag_filter_replace_cost_mb: float = 4.0

    overhaul_interval_years: int = 4
    overhaul_outage_days: int = 28
    boiler_tube_replace_year: int = 12
    boiler_tube_replace_cost_mb: float = 30.0

    aux_fuel_thb_per_mwh: float = 800.0
    aux_fuel_pct: float = 0.03
    sga_my: float = 14.0
    sga_esc: float = 0.03
    insurance_par_pct: float = 0.0025
    insurance_bi_pct: float = 0.0015
    insurance_tpl_pct: float = 0.0005
    pdf_pct: float = 0.02

    # Drying for RDF stream
    drying_mj_per_kg_water: float = 3.0
    drying_fuel_lhv_mj_per_kg: float = 38.0
    drying_fuel_thb_per_ton: float = 25000.0

    # ── Finance ─────────────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.06375
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10
    rf: float = 0.0205
    beta_unlevered: float = 0.55
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════
# █  HELPERS  █
# ════════════════════════════════════════════════════════════════════════
def _msw_composition(p: RDFWTEInputs) -> dict:
    return {
        "food":      p.msw_pct_food,    "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic, "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,   "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,    "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather, "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def _split_composition(p: RDFWTEInputs) -> tuple[dict, dict]:
    """RW1 + RW2: Split raw MSW into RDF stream (combustibles) vs WTE stream (rest).

    Returns (rdf_composition_normalised, wte_composition_normalised)
    """
    raw = _msw_composition(p)
    # RDF stream — only combustibles, normalised to sum 1.0
    rdf_raw = {k: raw[k] for k in RDF_KEEP_COMPONENTS if k in raw}
    rdf_total = sum(rdf_raw.values())
    if rdf_total > 0:
        rdf_comp = {k: v / rdf_total for k, v in rdf_raw.items()}
    else:
        rdf_comp = raw.copy()

    # WTE stream — what's left (non-combustibles + low-grade)
    wte_raw = {k: raw[k] for k in raw if k not in RDF_KEEP_COMPONENTS}
    wte_total = sum(wte_raw.values())
    if wte_total > 0:
        wte_comp = {k: v / wte_total for k, v in wte_raw.items()}
    else:
        wte_comp = raw.copy()

    return rdf_comp, wte_comp


def _plant_efficiency(p: RDFWTEInputs) -> float:
    if p.efficiency > 0: return p.efficiency
    return p.boiler_efficiency * p.turbine_efficiency


def _mw_net(p: RDFWTEInputs) -> float:
    return p.mw_gross * (1 - p.parasitic_load_pct)


def _availability_year(p: RDFWTEInputs, year_idx: int) -> float:
    avail = p.availability
    if (year_idx + 1) % p.overhaul_interval_years == 0:
        avail *= 1 - (p.overhaul_outage_days / 365.0)
    if (year_idx + 1) == p.boiler_tube_replace_year:
        avail *= 0.85
    return avail


# ════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL (3-way mass balance + separate LHV)  █
# ════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: RDFWTEInputs) -> dict:
    rdf_comp, wte_comp = _split_composition(p)

    # RW1: Compute LHV per stream
    if p.use_msw_auto:
        rdf_chem = compute_msw_chemistry(rdf_comp, p.rdf_moisture_after_drying)
        wte_chem = compute_msw_chemistry(wte_comp, p.msw_moisture)
        rdf_lhv = rdf_chem["lhv_kcal_per_kg"] if rdf_chem else 0
        wte_lhv = wte_chem["lhv_kcal_per_kg"] if wte_chem else 0
        # WTE-side gets MIXED feed (some rejects from RDF line + raw WTE-stream)
        # Use weighted average → done below in mass balance
    else:
        rdf_chem = wte_chem = None
        rdf_lhv = p.ncv_mj_per_kg_manual / 4.184e-3 * 1.5  # RDF side higher LHV
        wte_lhv = p.ncv_mj_per_kg_manual / 4.184e-3 * 0.6  # WTE side lower

    # RW2: 3-way mass balance
    msw_t_yr = p.msw_intake_design_t_d * p.actual_utilization \
                * p.op_days * p.availability
    msw_t_d  = msw_t_yr / p.op_days if p.op_days else 0

    # Sorting line splits by user-set rdf_split_pct
    msw_to_rdf_line_t_yr = msw_t_yr * p.rdf_split_pct
    msw_to_wte_direct_t_yr = msw_t_yr * (1 - p.rdf_split_pct - p.reject_pct)
    reject_t_yr = msw_t_yr * p.reject_pct

    # RDF line: only fraction becomes sellable RDF
    rdf_output_t_yr = msw_to_rdf_line_t_yr * p.rdf_yield_within_split
    rdf_line_residue_t_yr = msw_to_rdf_line_t_yr - rdf_output_t_yr
    # RDF residue → also burned in WTE
    wte_total_feed_t_yr = msw_to_wte_direct_t_yr + rdf_line_residue_t_yr
    wte_total_feed_t_d  = wte_total_feed_t_yr / p.op_days if p.op_days else 0

    # WTE-side blended LHV (raw waste + RDF residue which has higher LHV)
    if (msw_to_wte_direct_t_yr + rdf_line_residue_t_yr) > 0:
        # Approximate residue LHV ≈ raw MSW (rejects + ash before RDF processing)
        # blended ≈ weighted average
        blended_lhv = ((wte_lhv * msw_to_wte_direct_t_yr
                         + rdf_lhv * 0.7 * rdf_line_residue_t_yr)  # residue 70% of RDF LHV
                        / (msw_to_wte_direct_t_yr + rdf_line_residue_t_yr))
    else:
        blended_lhv = wte_lhv

    # WTE electricity from blended feed
    eta = _plant_efficiency(p)
    kwh_per_kg_wte = blended_lhv * eta / KCAL_PER_KWH
    wte_kwh_yr = wte_total_feed_t_yr * 1000 * kwh_per_kg_wte
    wte_mwh_yr = wte_kwh_yr / 1000

    # RDF price (RW3: quality tier)
    rdf_cl = rdf_chem.get("chlorine_pct", 0) if rdf_chem else 0
    rdf_ash = rdf_chem.get("totals", {}).get("Ash", 5) if rdf_chem else 5
    if p.use_quality_tier_pricing:
        if rdf_cl > 0.7 or rdf_ash > 18:
            rdf_price = 0
        elif rdf_lhv >= 4500:
            rdf_price = rdf_lhv * p.rdf_price_thb_per_kcal_high
        elif rdf_lhv >= 3500:
            rdf_price = rdf_lhv * p.rdf_price_thb_per_kcal_std
        elif rdf_lhv >= 2500:
            rdf_price = rdf_lhv * p.rdf_price_thb_per_kcal_low
        else:
            rdf_price = 0
    else:
        rdf_price = rdf_lhv * p.rdf_price_thb_per_kcal

    rdf_sold_t_yr = rdf_output_t_yr * p.offtake_utilization

    # Drying energy (RDF line)
    rdf_drying_water_t_yr = (msw_to_rdf_line_t_yr
                              * max(p.msw_moisture - p.rdf_moisture_after_drying, 0))
    rdf_drying_energy_mb_yr = (rdf_drying_water_t_yr * 1000 * p.drying_mj_per_kg_water
                                 / p.drying_fuel_lhv_mj_per_kg / 1000
                                 * p.drying_fuel_thb_per_ton / 1e6)

    return {
        "mode":              "auto" if p.use_msw_auto else "manual",
        "rdf_chemistry":     rdf_chem,
        "wte_chemistry":     wte_chem,
        "rdf_composition":   rdf_comp,
        "wte_composition":   wte_comp,
        "rdf_lhv_kcal_per_kg":  rdf_lhv,
        "wte_lhv_kcal_per_kg":  wte_lhv,
        "blended_wte_lhv":   blended_lhv,
        "lhv_kcal_per_kg":   rdf_lhv,           # main LHV shown = RDF side
        "lhv_mj_per_kg":     rdf_lhv * 4.184e-3,
        "msw_intake_t_yr":   msw_t_yr,
        "msw_intake_t_d":    msw_t_d,
        "msw_to_rdf_line_t_yr": msw_to_rdf_line_t_yr,
        "msw_to_wte_direct_t_yr": msw_to_wte_direct_t_yr,
        "reject_t_yr":       reject_t_yr,
        "rdf_line_residue_t_yr": rdf_line_residue_t_yr,
        "wte_total_feed_t_yr": wte_total_feed_t_yr,
        "wte_total_feed_t_d": wte_total_feed_t_d,
        "rdf_output_t_yr":   rdf_output_t_yr,
        "rdf_output_t_d":    rdf_output_t_yr / p.op_days if p.op_days else 0,
        "rdf_sold_t_yr":     rdf_sold_t_yr,
        "rdf_price_thb_per_ton": rdf_price,
        "wte_mwh_yr":        wte_mwh_yr,
        "wte_kwh_per_kg":    kwh_per_kg_wte,
        "ash_t_yr":          wte_total_feed_t_yr * (p.bottom_ash_pct + p.fly_ash_pct),
        "bottom_ash_t_yr":   wte_total_feed_t_yr * p.bottom_ash_pct,
        "fly_ash_t_yr":      wte_total_feed_t_yr * p.fly_ash_pct,
        "rdf_chlorine_pct":  rdf_cl,
        "rdf_ash_pct":       rdf_ash,
        "rdf_drying_energy_mb_yr": rdf_drying_energy_mb_yr,
    }


# ════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════
def _wte_mwh_for_year(p: RDFWTEInputs, raw: dict, year_idx: int) -> float:
    """Scale baseline MWh by year-specific availability."""
    base_mwh = raw["wte_mwh_yr"]
    avail_factor = _availability_year(p, year_idx) / p.availability
    return base_mwh * avail_factor


def _yearly_revenue(p: RDFWTEInputs, year_idx: int, raw: dict,
                     carbon_mb_yr: float) -> dict:
    rdf_price = raw["rdf_price_thb_per_ton"] * (1 + p.rdf_price_esc) ** year_idx
    rdf_rev = raw["rdf_sold_t_yr"] * rdf_price / 1e6

    wte_mwh = _wte_mwh_for_year(p, raw, year_idx)
    fit_rate = ppa_escalated_rate(p.fit_base, p.fit_premium, year_idx,
                                     p.premium_years,
                                     p.cpi_escalation, p.cpi_linked_fraction)
    fit_rev = wte_mwh * 1000 * fit_rate / 1e6

    tip_rev = raw["msw_intake_t_yr"] * p.tipping_fee \
              * (1 + p.tipping_esc) ** year_idx / 1e6

    revenue = rdf_rev + fit_rev + tip_rev + carbon_mb_yr
    return {
        "rdf_rev":    rdf_rev,
        "fit_rev":    fit_rev,
        "tip_rev":    tip_rev,
        "carbon_rev": carbon_mb_yr,
        "revenue":    revenue,
        "wte_mwh":    wte_mwh,
    }


def _yearly_opex(p: RDFWTEInputs, year_idx: int, capex_total: float,
                  raw: dict, fit_rev_mb: float) -> dict:
    esc = (1 + p.om_escalation) ** year_idx
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * esc
    else:
        om = capex_total * p.om_pct_capex * esc

    bottom_ash = raw["bottom_ash_t_yr"] * p.bottom_ash_disposal_thb_per_ton / 1e6 * esc
    fly_ash = raw["fly_ash_t_yr"] * p.fly_ash_disposal_thb_per_ton / 1e6 * esc
    ash_total = bottom_ash + fly_ash

    # FGT — scaled with WTE feed
    if p.use_fgt_scaling:
        wte_t = raw["wte_total_feed_t_yr"]
        lime  = wte_t * p.lime_kg_per_ton_msw / 1000 \
                 * p.lime_price_thb_per_ton / 1e6 * esc
        urea  = wte_t * p.urea_kg_per_ton_msw / 1000 \
                 * p.urea_price_thb_per_ton / 1e6 * esc
        ac    = wte_t * p.ac_kg_per_ton_msw / 1000 \
                 * p.ac_price_thb_per_ton / 1e6 * esc
        bag_filter = (p.bag_filter_replace_cost_mb
                       if (year_idx + 1) % p.bag_filter_replace_yrs == 0 else 0)
        flue = lime + urea + ac + bag_filter
    else:
        flue = p.flue_gas_cost * esc

    aux = (raw["wte_mwh_yr"] * p.aux_fuel_pct * p.aux_fuel_thb_per_mwh / 1e6 * esc)
    boiler_tube = (p.boiler_tube_replace_cost_mb
                    if (year_idx + 1) == p.boiler_tube_replace_year else 0)
    rdf_transport = raw["rdf_sold_t_yr"] * p.transport_rdf_thb_per_ton / 1e6 * esc
    rdf_drying = raw["rdf_drying_energy_mb_yr"] * esc

    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * (p.insurance_par_pct + p.insurance_bi_pct
                                 + p.insurance_tpl_pct)
    pdf = fit_rev_mb * p.pdf_pct

    total = (om + ash_total + flue + aux + boiler_tube + rdf_transport
              + rdf_drying + sga + insurance + pdf)

    return {
        "om": om,
        "bottom_ash": bottom_ash, "fly_ash": fly_ash, "ash": ash_total,
        "flue": flue, "aux": aux,
        "boiler_tube": boiler_tube,
        "rdf_transport": rdf_transport, "rdf_drying": rdf_drying,
        "sga": sga, "insurance": insurance, "pdf": pdf,
        "feedstock": 0.0,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════
# █  MAIN  █
# ════════════════════════════════════════════════════════════════════════
def run_model(p: RDFWTEInputs) -> dict:
    p = copy.deepcopy(p)
    raw = compute_raw_material(p)

    # Year-1 estimates for WC / DSRA sizing
    rev_yr1_est = ((raw["rdf_sold_t_yr"] * raw["rdf_price_thb_per_ton"]
                     + raw["wte_mwh_yr"] * 1000 * (p.fit_base + p.fit_premium)
                     + raw["msw_intake_t_yr"] * p.tipping_fee) / 1e6)
    debt_pre = capex_breakdown(p.epc_cost, p.owner_cost_pct,
                                p.contingency_pct, p.idc_pct,
                                p.debt_pct)["debt"]
    debt_svc_yr1 = debt_pre * (p.interest_rate + 1 / p.debt_tenor)

    cx = capex_breakdown(
        p.epc_cost, p.owner_cost_pct, p.contingency_pct, p.idc_pct,
        p.debt_pct, p.mw_gross, _mw_net(p),
        interest_rate=p.interest_rate,
        construction_years=p.construction_years,
        use_idc_drawdown=p.use_idc_drawdown,
        wc_pct_revenue_yr1=p.wc_pct_revenue_yr1,
        revenue_yr1_mb=rev_yr1_est,
        dsra_months=p.dsra_months,
        debt_service_yr1_mb=debt_svc_yr1,
        decommissioning_pct=p.decommissioning_pct,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]; debt = cx["debt"]
    dep = cx["total_proj_capex"] / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    carbon_mb_yr, be_yr = carbon_credit_tver(raw["msw_intake_t_yr"], p.carbon_price,
                                              enabled=p.enable_carbon)

    rows = []; fcfe = [-equity]; fcff = [-capex_total]
    cum_fcfe_list, cum_fcff_list = [], []
    cum_e = -equity; cum_p = -capex_total
    opex_list, mwh_list = [], []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, raw, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw, rev["fit_rev"])
        revenue = rev["revenue"]; opex = op["total"]
        ebitda = revenue - opex; ebit = ebitda - dep
        interest, principal_repay, _ = ds[y]
        ebt = ebit - interest
        tax_eff = boi_tax_rate(y, p.boi_full_years, p.boi_partial_years,
                                p.boi_partial_rate, p.tax_rate)
        tax_amt = max(ebt, 0) * tax_eff
        npat = ebt - tax_amt; ocf = npat + dep
        cfads = npat + dep + interest
        dscr = dscr_year(cfads, interest, principal_repay)
        fcfe_y = ocf - principal_repay   # interest already deducted in NPAT
        fcff_y = ebit * (1 - tax_eff) + dep

        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe_list.append(cum_e); cum_fcff_list.append(cum_p)
        opex_list.append(opex); mwh_list.append(rev["wte_mwh"])

        rows.append({
            "year": y + 1, "calendar_year": p.cod_year + y,
            "fit_rev": rev["fit_rev"], "tip_rev": rev["tip_rev"],
            "rdf_rev": rev["rdf_rev"], "carbon_rev": rev["carbon_rev"],
            "revenue": revenue,
            "rev_breakdown": {"RDF Sales": rev["rdf_rev"],
                               "FiT":      rev["fit_rev"],
                               "Tipping":  rev["tip_rev"],
                               "Carbon":   rev["carbon_rev"]},
            "opex_om": op["om"], "opex_feedstock": 0.0,
            "opex_ash": op["ash"],
            "opex_bottom_ash": op["bottom_ash"], "opex_fly_ash": op["fly_ash"],
            "opex_flue": op["flue"],
            "opex_aux": op["aux"] + op["rdf_transport"] + op["rdf_drying"],
            "opex_sga": op["sga"], "opex_insurance": op["insurance"],
            "opex_pdf": op["pdf"],
            "opex_boiler_tube": op["boiler_tube"],
            "opex": opex, "opex_breakdown": op,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit,
            "interest": interest, "ebt": ebt,
            "tax_eff": tax_eff, "tax": tax_amt, "npat": npat, "ocf": ocf,
            "principal_repay": principal_repay,
            "cfads": cfads, "dscr": dscr,
            "fcfe": fcfe_y, "fcff": fcff_y,
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
        engine_type="rdf_wte", inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr":           raw["wte_mwh_yr"],
            "mw_gross":         p.mw_gross,
            "mw_net":           _mw_net(p),
            "msw_intake_t_yr":  raw["msw_intake_t_yr"],
            "msw_intake_t_d":   raw["msw_intake_t_d"],
            "rdf_output_t_yr":  raw["rdf_output_t_yr"],
            "rdf_output_t_d":   raw["rdf_output_t_d"],
            "rdf_sold_t_yr":    raw["rdf_sold_t_yr"],
            "wte_feed_t_yr":    raw["wte_total_feed_t_yr"],
            "reject_t_yr":      raw["reject_t_yr"],
            "wte_mwh_yr":       raw["wte_mwh_yr"],
            "ash_ton_yr":       raw["ash_t_yr"],
            "feedstock_ton_yr": raw["msw_intake_t_yr"],
            "feedstock_ton_day":raw["msw_intake_t_d"],
            "lhv_kcal_per_kg":  raw["lhv_kcal_per_kg"],
            "rdf_lhv_kcal":     raw["rdf_lhv_kcal_per_kg"],
            "wte_lhv_kcal":     raw["wte_lhv_kcal_per_kg"],
            "rdf_split_pct":    p.rdf_split_pct,
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


def default_preset() -> RDFWTEInputs:
    return RDFWTEInputs(
        project_name="Combined RDF + WTE 8 MW (30/65/5 split)",
        cod_year=2027, project_life=20,
        mw_gross=9.9, parasitic_load_pct=0.15,
        availability=0.85, op_days=330, performance_warranty=0.90,
        boiler_efficiency=0.80, turbine_efficiency=0.28,
        msw_intake_design_t_d=500.0, actual_utilization=0.85,
        rdf_split_pct=0.30, rdf_yield_within_split=0.65, reject_pct=0.05,
        use_msw_auto=True, msw_moisture=0.40,
        rdf_moisture_after_drying=0.15,
        msw_pct_food=0.30, msw_pct_paper=0.10, msw_pct_plastic=0.35,
        msw_pct_glass=0.08, msw_pct_metal=0.04, msw_pct_cloth=0.05,
        msw_pct_wood=0.05, msw_pct_rubber=0.01,
        msw_pct_hazardous=0.01, msw_pct_other=0.01,
        use_quality_tier_pricing=True,
        rdf_price_thb_per_kcal_high=0.24,
        rdf_price_thb_per_kcal_std=0.20,
        rdf_price_thb_per_kcal_low=0.15,
        rdf_price_esc=0.015,
        transport_rdf_thb_per_ton=260.0,
        offtake_utilization=0.85,
        fit_base=5.78, fit_premium=0.70, premium_years=8,
        cpi_escalation=0.02, cpi_linked_fraction=0.0,
        tipping_fee=400.0, tipping_esc=0.02,
        epc_cost=2100.0, owner_cost_pct=0.10, contingency_pct=0.10,
        idc_pct=0.05, construction_years=3,
        use_idc_drawdown=True,
        wc_pct_revenue_yr1=0.16,
        dsra_months=6.0,
        decommissioning_pct=0.02,
        om_pct_capex=0.05, om_escalation=0.03,
        bottom_ash_pct=0.15, fly_ash_pct=0.05,
        bottom_ash_disposal_thb_per_ton=800.0,
        fly_ash_disposal_thb_per_ton=3000.0,
        use_fgt_scaling=True,
        overhaul_interval_years=4, overhaul_outage_days=28,
        boiler_tube_replace_year=12, boiler_tube_replace_cost_mb=30.0,
        aux_fuel_pct=0.03, sga_my=14.0, sga_esc=0.03,
        insurance_par_pct=0.0025, insurance_bi_pct=0.0015, insurance_tpl_pct=0.0005,
        pdf_pct=0.02,
        drying_mj_per_kg_water=3.0,
        drying_fuel_lhv_mj_per_kg=38.0,
        drying_fuel_thb_per_ton=25000.0,
        debt_pct=0.70, interest_rate=0.06375,
        debt_tenor=12, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


INPUT_SECTIONS = [
    ("Plant Sizing", [
        ("project_name",          "Project Name",          "str",   ""),
        ("cod_year",              "COD Year",              "int",   ""),
        ("project_life",          "Project Life",          "int",   "yr"),
        ("mw_gross",              "WTE MW Gross",          "float", "MW"),
        ("parasitic_load_pct",    "Parasitic Load",        "pct",   "%"),
        ("availability",          "Availability",          "pct",   "%"),
        ("op_days",               "Operating Days",        "int",   "days/yr"),
        ("performance_warranty",  "Performance Warranty",  "pct",   "%"),
        ("boiler_efficiency",     "Boiler Efficiency η_b", "pct",   "%"),
        ("turbine_efficiency",    "Turbine Efficiency η_t","pct",   "%"),
    ]),
    ("MSW Intake & 3-way Split (RW2)", [
        ("msw_intake_design_t_d", "MSW Intake Design",     "float", "t/d"),
        ("actual_utilization",    "Actual Utilization",    "pct",   "%"),
        ("rdf_split_pct",         "RDF Split",             "pct",   "% MSW to RDF line"),
        ("rdf_yield_within_split","RDF Yield in stream",   "pct",   "% (65% typical)"),
        ("reject_pct",            "Reject %",              "pct",   "% to landfill"),
        ("rdf_split_min",         "RDF split min",         "pct",   "% (scenario)"),
        ("rdf_split_max",         "RDF split max",         "pct",   "% (scenario)"),
    ]),
    ("Raw Material — MSW Composition", [
        ("use_msw_auto",     "Use Dulong Auto",           "bool",  "ON"),
        ("msw_moisture",     "Moisture (raw MSW)",        "pct",   "%"),
        ("rdf_moisture_after_drying", "RDF moisture",     "pct",   "% (15% typical)"),
        ("msw_pct_food",     "Food",                      "pct",   "%"),
        ("msw_pct_paper",    "Paper",                     "pct",   "%"),
        ("msw_pct_plastic",  "Plastic",                   "pct",   "%"),
        ("msw_pct_glass",    "Glass",                     "pct",   "%"),
        ("msw_pct_metal",    "Metal",                     "pct",   "%"),
        ("msw_pct_cloth",    "Cloth",                     "pct",   "%"),
        ("msw_pct_wood",     "Wood",                      "pct",   "%"),
        ("msw_pct_rubber",   "Rubber",                    "pct",   "%"),
        ("msw_pct_leather",  "Leather",                   "pct",   "%"),
        ("msw_pct_hazardous","Hazardous",                 "pct",   "%"),
        ("msw_pct_other",    "Other",                     "pct",   "%"),
    ]),
    ("RDF Revenue (R3 quality tiers)", [
        ("use_quality_tier_pricing", "Quality Tier Pricing", "bool", ""),
        ("rdf_price_thb_per_kcal_high","Price LHV≥4500","float", "฿/kcal"),
        ("rdf_price_thb_per_kcal_std", "Price LHV≥3500","float", "฿/kcal"),
        ("rdf_price_thb_per_kcal_low", "Price LHV≥2500","float", "฿/kcal"),
        ("rdf_price_esc",          "Price Escalation", "pct",   "%/yr"),
        ("transport_rdf_thb_per_ton","Transport RDF","float", "฿/ton"),
        ("offtake_utilization",    "Offtake util",     "pct",   "%"),
    ]),
    ("WTE Revenue", [
        ("fit_base",          "FiT Base",             "float", "฿/kWh"),
        ("fit_premium",       "FiT Premium",          "float", "฿/kWh"),
        ("premium_years",     "Premium Years",        "int",   "yr"),
        ("cpi_escalation",    "CPI Escalation",       "pct",   "%/yr"),
        ("cpi_linked_fraction","CPI-linked fraction", "pct",   "%"),
        ("tipping_fee",       "Tipping Fee",          "float", "฿/ton"),
        ("tipping_esc",       "Tipping Escalation",   "pct",   "%/yr"),
        ("carbon_price",      "Carbon Price",         "float", "฿/tCO₂"),
        ("enable_carbon",     "Enable Carbon Credit", "bool",  ""),
    ]),
    ("CAPEX + Working Capital", [
        ("epc_cost",            "EPC Cost",         "float", "MB"),
        ("owner_cost_pct",      "Owner's Cost",     "pct",   "% EPC"),
        ("contingency_pct",     "Contingency",      "pct",   "%"),
        ("idc_pct",             "IDC (fallback)",   "pct",   "% EPC"),
        ("use_idc_drawdown",    "Use IDC Drawdown", "bool",  ""),
        ("construction_years",  "Construction",     "int",   "yr"),
        ("wc_pct_revenue_yr1",  "Working Capital",  "pct",   "% Year-1 rev"),
        ("dsra_months",         "DSRA Reserve",     "float", "months"),
        ("decommissioning_pct", "Decommissioning",  "pct",   "% CAPEX"),
    ]),
    ("OPEX — Ash, FGT, O&M", [
        ("om_pct_capex",        "O&M",              "pct",   "% CAPEX/yr"),
        ("om_my_fixed",         "O&M Fixed",        "float", "MB/yr"),
        ("om_escalation",       "O&M Escalation",   "pct",   "%/yr"),
        ("bottom_ash_pct",      "Bottom Ash",       "pct",   "% WTE feed"),
        ("bottom_ash_disposal_thb_per_ton","Bottom Ash $","float","฿/ton"),
        ("fly_ash_pct",         "Fly Ash",          "pct",   "% WTE feed"),
        ("fly_ash_disposal_thb_per_ton",   "Fly Ash $",   "float","฿/ton"),
        ("use_fgt_scaling",     "FGT Scaling",      "bool",  ""),
        ("lime_kg_per_ton_msw", "Lime usage",       "float", "kg/ton"),
        ("urea_kg_per_ton_msw", "Urea usage",       "float", "kg/ton"),
        ("ac_kg_per_ton_msw",   "Activated C",      "float", "kg/ton"),
        ("bag_filter_replace_yrs","Bag filter cycle","int",  "yr"),
        ("bag_filter_replace_cost_mb","Bag filter cost","float","MB"),
        ("flue_gas_cost",       "Flue Gas (fallback)","float","MB/yr"),
    ]),
    ("OPEX — Overhaul + Aux + SG&A", [
        ("overhaul_interval_years",  "Major Overhaul",  "int", "yr"),
        ("overhaul_outage_days",     "Outage days",     "int", ""),
        ("boiler_tube_replace_year", "Boiler tube yr",  "int", ""),
        ("boiler_tube_replace_cost_mb","Boiler tube $", "float","MB"),
        ("aux_fuel_pct",          "Aux Fuel % gen",  "pct", "%"),
        ("aux_fuel_thb_per_mwh",  "Aux Fuel price",  "float","฿/MWh"),
        ("sga_my",                "SG&A (Y1)",       "float","MB/yr"),
        ("sga_esc",               "SG&A Escalation", "pct", "%/yr"),
        ("insurance_par_pct",     "Property all-risk","pct","% CAPEX/yr"),
        ("insurance_bi_pct",      "Business interr.","pct","% CAPEX/yr"),
        ("insurance_tpl_pct",     "3rd-party liab.", "pct","% CAPEX/yr"),
        ("pdf_pct",               "PDF",             "pct","% of FiT rev"),
        ("drying_mj_per_kg_water","Drying energy",   "float","MJ/kg water"),
        ("drying_fuel_thb_per_ton","Drying fuel price","float","฿/ton"),
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
    k = res["kpis"]; r = res["raw_material"]; g = res["generation"]
    print(f"━━━ {p.project_name} (improved) ━━━")
    print(f"  MSW intake       : {g['msw_intake_t_d']:>8.1f} t/d")
    print(f"  RDF output       : {g['rdf_output_t_d']:>8.1f} t/d (sold {g['rdf_sold_t_yr']/p.op_days:.1f})")
    print(f"  WTE feed         : {r['wte_total_feed_t_d']:>8.1f} t/d (incl. RDF residue)")
    print(f"  RDF LHV / WTE LHV: {r['rdf_lhv_kcal_per_kg']:>5.0f} / {r['wte_lhv_kcal_per_kg']:.0f} kcal/kg")
    print(f"  Blended WTE LHV  : {r['blended_wte_lhv']:>5.0f} kcal/kg")
    print(f"  WTE MWh/yr       : {g['wte_mwh_yr']:>8.0f}")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min / avg   : {k['dscr_min']:.2f} / {k['dscr_avg']:.2f}")
