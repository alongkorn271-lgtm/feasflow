"""
engines.rdf
===========
RDF (Refuse-Derived Fuel) plant — sell pellets to cement industry.

Improvements (R1-R5):
  R1 — Realistic yield from MSW composition (25-50%, not 100%)
  R2 — Drying energy cost (water evaporation)
  R3 — Quality tiers + Cl/Ash caps for cement acceptance
  R4 — Offtake utilization (contract minimum, cement plant outage)
  R5 — Storage CAPEX (silo / covered yard)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoh_thb_per_ton,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    compute_msw_chemistry, carbon_credit_tver,
    working_capital_recovery,
    build_result,
)


META = {
    "code":        "rdf",
    "label":       "RDF — Refuse Derived Fuel",
    "icon":        "🗑️",
    "description": "MSW → RDF pellets, sell to cement plants by ฿/kcal × LHV.",
    "color":       "#A371F7",
}


# Components that survive RDF processing (combustibles)
RDF_KEEP_COMPONENTS = {"paper", "cardboard", "plastic", "cloth",
                       "rubber", "leather", "wood"}


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class RDFInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "RDF Plant"
    cod_year: int = 2026
    project_life: int = 19

    # ── Plant sizing (in tonnage) ────────────────────────────────
    msw_intake_design_t_d: float = 240.0
    actual_utilization: float = 1.0
    op_days: int = 365
    availability: float = 0.95
    mw_gross: float = 0.0      # not used (no electricity)
    mw_net: float = 0.0

    # R1: yield mode
    use_yield_from_composition: bool = True
    rdf_yield_pct_manual: float = 0.35      # 35% override if auto OFF
    drying_loss_pct: float = 0.20           # 20% mass loss in drying

    # ── MSW Raw Material ─────────────────────────────────────────
    use_msw_auto: bool = True
    msw_moisture: float = 0.50              # input MSW moisture
    msw_moisture_after_drying: float = 0.15 # R2: after drying (15-20%)
    msw_pct_food:      float = 0.30
    msw_pct_paper:     float = 0.15
    msw_pct_plastic:   float = 0.30
    msw_pct_glass:     float = 0.04
    msw_pct_metal:     float = 0.04
    msw_pct_cloth:     float = 0.08
    msw_pct_wood:      float = 0.05
    msw_pct_rubber:    float = 0.02
    msw_pct_leather:   float = 0.01
    msw_pct_hazardous: float = 0.005
    msw_pct_other:     float = 0.005
    lhv_manual_kcal_per_kg: float = 4200.0

    # ── R2: Drying energy ────────────────────────────────────────
    drying_mj_per_kg_water: float = 3.0     # 2.5-3.5 MJ/kg water (incl. losses)
    drying_fuel_lhv_mj_per_kg: float = 38.0 # natural gas / heavy oil
    drying_fuel_thb_per_ton: float = 25000.0
    drying_fuel_source: str = "natural_gas" # NG / diesel / biomass

    # ── R3: Quality tiers & caps ─────────────────────────────────
    use_quality_tier_pricing: bool = True
    rdf_price_thb_per_kcal_high: float = 0.24   # LHV ≥ 4500
    rdf_price_thb_per_kcal_std:  float = 0.20   # LHV 3500-4500
    rdf_price_thb_per_kcal_low:  float = 0.15   # LHV 2500-3500
    chlorine_cap_pct: float = 0.7
    ash_cap_pct: float = 18.0
    rdf_price_thb_per_kcal: float = 0.20        # fallback flat price
    rdf_price_esc: float = 0.015

    # ── R4: Offtake utilization ──────────────────────────────────
    offtake_utilization: float = 0.85       # 85% of produced RDF sold
    # (cement plant rejection + outage + market downturn)
    offtake_price_index_link: float = 0.5   # 0-1: fraction of price linked to coal

    # ── R5: Storage CAPEX ────────────────────────────────────────
    storage_days_capacity: int = 10
    storage_capex_thb_per_ton_capacity: float = 8000.0  # ~8000 ฿/ton silo

    # ── Tipping fee ──────────────────────────────────────────────
    tipping_fee: float = 260.0
    tipping_esc: float = 0.01
    carbon_price: float = 80.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 76.2
    owner_cost_pct: float = 0.08
    contingency_pct: float = 0.10
    idc_pct: float = 0.04
    construction_years: int = 1
    use_idc_drawdown: bool = True
    wc_pct_revenue_yr1: float = 0.14
    dsra_months: float = 6.0
    decommissioning_pct: float = 0.02

    # ── OPEX ────────────────────────────────────────────────────
    transport_to_cement_thb_per_ton: float = 260.0
    labour_mb_yr: float = 12.0
    electricity_mb_yr: float = 8.0
    maintenance_mb_yr: float = 8.0
    disposal_misc_mb_yr: float = 10.4
    om_escalation: float = 0.01
    sga_my: float = 2.0
    sga_esc: float = 0.02
    insurance_par_pct: float = 0.002
    insurance_bi_pct: float = 0.001
    insurance_tpl_pct: float = 0.0005

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.50
    interest_rate: float = 0.06375
    debt_tenor: int = 10
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
def _msw_composition(p: RDFInputs) -> dict:
    return {
        "food":      p.msw_pct_food,    "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic, "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,   "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,    "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather, "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def _rdf_composition_after_processing(p: RDFInputs) -> dict:
    """R1: After sorting, only combustibles remain (renormalised)."""
    raw = _msw_composition(p)
    kept = {k: v for k, v in raw.items() if k in RDF_KEEP_COMPONENTS}
    total = sum(kept.values())
    if total <= 0:
        return raw
    # Renormalize to 1.0 — RDF feed is dominated by combustibles
    return {k: v / total for k, v in kept.items()}


def _calc_rdf_yield(p: RDFInputs) -> float:
    """R1: Yield = combustibles fraction × (1 − drying mass loss)."""
    if not p.use_yield_from_composition:
        return p.rdf_yield_pct_manual
    raw = _msw_composition(p)
    keep_mass_pct = sum(raw.get(c, 0) for c in RDF_KEEP_COMPONENTS)
    # Drying removes water — but drying_loss_pct already includes that on top of moisture
    # Simpler: yield = combustible_mass × (1 - moisture) × (1 - other losses)
    yield_dry_basis = keep_mass_pct * (1 - p.msw_moisture) \
                       * (1 - p.drying_loss_pct)
    # Add back the moisture remaining (15-20%)
    return yield_dry_basis / max(1 - p.msw_moisture_after_drying, 0.01)


def _rdf_price(p: RDFInputs, lhv_kcal: float,
                 cl_pct: float, ash_pct: float) -> float:
    """R3: Quality-tier pricing with Cl/Ash caps."""
    if not p.use_quality_tier_pricing:
        return lhv_kcal * p.rdf_price_thb_per_kcal
    # Reject if exceeds caps
    if cl_pct > p.chlorine_cap_pct or ash_pct > p.ash_cap_pct:
        return 0.0
    # Tier
    if lhv_kcal >= 4500:
        return lhv_kcal * p.rdf_price_thb_per_kcal_high
    elif lhv_kcal >= 3500:
        return lhv_kcal * p.rdf_price_thb_per_kcal_std
    elif lhv_kcal >= 2500:
        return lhv_kcal * p.rdf_price_thb_per_kcal_low
    return 0.0   # too low


def _drying_energy_cost_mb_yr(p: RDFInputs, msw_t_yr: float) -> float:
    """R2: Cost to evaporate water during drying."""
    water_evap_t_yr = msw_t_yr * max(p.msw_moisture - p.msw_moisture_after_drying, 0)
    energy_mj_yr = water_evap_t_yr * 1000 * p.drying_mj_per_kg_water
    fuel_kg_yr = energy_mj_yr / p.drying_fuel_lhv_mj_per_kg
    fuel_ton_yr = fuel_kg_yr / 1000
    cost_thb_yr = fuel_ton_yr * p.drying_fuel_thb_per_ton
    return cost_thb_yr / 1e6


# ════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL  █
# ════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: RDFInputs) -> dict:
    if p.use_msw_auto:
        # Compute RDF chemistry (after sorting + drying = lower moisture, combustibles only)
        rdf_comp = _rdf_composition_after_processing(p)
        chem = compute_msw_chemistry(rdf_comp, p.msw_moisture_after_drying)
        if chem is None:
            return {"error": "Invalid composition"}
        lhv_kcal = chem["lhv_kcal_per_kg"]
    else:
        chem = None
        lhv_kcal = p.lhv_manual_kcal_per_kg

    # R1: realistic yield
    yield_pct = _calc_rdf_yield(p)

    # MSW intake (wet)
    msw_in_t_yr = p.msw_intake_design_t_d * p.actual_utilization \
                   * p.op_days * p.availability
    rdf_out_t_yr = msw_in_t_yr * yield_pct
    rdf_out_t_d = rdf_out_t_yr / p.op_days if p.op_days else 0

    # R4: offtake utilization (actual sold)
    rdf_sold_t_yr = rdf_out_t_yr * p.offtake_utilization
    rdf_rejected_t_yr = rdf_out_t_yr - rdf_sold_t_yr

    # R3: price with quality tier
    cl_pct = chem.get("chlorine_pct", 0) if chem else 0
    ash_pct = chem.get("totals", {}).get("Ash", 0) if chem else 10
    rdf_price = _rdf_price(p, lhv_kcal, cl_pct, ash_pct)

    return {
        "mode":              "auto" if p.use_msw_auto else "manual",
        "chemistry":         chem,
        "composition":       _msw_composition(p) if p.use_msw_auto else None,
        "rdf_composition":   _rdf_composition_after_processing(p),
        "lhv_kcal_per_kg":   lhv_kcal,
        "lhv_mj_per_kg":     lhv_kcal * 4.184e-3,
        "msw_intake_t_yr":   msw_in_t_yr,
        "msw_intake_t_d":    msw_in_t_yr / p.op_days if p.op_days else 0,
        "rdf_yield_pct":     yield_pct,
        "rdf_output_t_yr":   rdf_out_t_yr,
        "rdf_output_t_d":    rdf_out_t_d,
        "rdf_sold_t_yr":     rdf_sold_t_yr,
        "rdf_rejected_t_yr": rdf_rejected_t_yr,
        "rdf_price_thb_per_ton": rdf_price,
        "chlorine_pct":      cl_pct,
        "ash_pct":           ash_pct,
        "drying_energy_mb_yr": _drying_energy_cost_mb_yr(p, msw_in_t_yr),
    }


# ════════════════════════════════════════════════════════════════════════
# █  REVENUE & OPEX  █
# ════════════════════════════════════════════════════════════════════════
def _yearly_revenue(p: RDFInputs, year_idx: int, raw: dict,
                     carbon_mb_yr: float) -> dict:
    rdf_t_yr = raw["rdf_sold_t_yr"]    # R4: only sold amount
    msw_t_yr = raw["msw_intake_t_yr"]

    rdf_price = raw["rdf_price_thb_per_ton"] * (1 + p.rdf_price_esc) ** year_idx
    rdf_rev = rdf_t_yr * rdf_price / 1e6
    tip_rev = msw_t_yr * p.tipping_fee * (1 + p.tipping_esc) ** year_idx / 1e6
    revenue = rdf_rev + tip_rev + carbon_mb_yr
    return {
        "rdf_rev":     rdf_rev,
        "tip_rev":     tip_rev,
        "carbon_rev":  carbon_mb_yr,
        "revenue":     revenue,
    }


def _yearly_opex(p: RDFInputs, year_idx: int, capex_total: float,
                  raw: dict) -> dict:
    rdf_t_yr = raw["rdf_sold_t_yr"]
    esc = (1 + p.om_escalation) ** year_idx
    transport = rdf_t_yr * p.transport_to_cement_thb_per_ton / 1e6 * esc
    labour = p.labour_mb_yr * esc
    electricity = p.electricity_mb_yr * esc
    maintenance = p.maintenance_mb_yr * esc
    disposal = p.disposal_misc_mb_yr * esc
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx

    # R2: drying energy cost
    drying = raw["drying_energy_mb_yr"] * esc

    # C4: insurance breakdown
    ins_par = capex_total * p.insurance_par_pct
    ins_bi  = capex_total * p.insurance_bi_pct
    ins_tpl = capex_total * p.insurance_tpl_pct
    insurance = ins_par + ins_bi + ins_tpl

    total = (transport + labour + electricity + maintenance + disposal
              + sga + insurance + drying)
    return {
        "transport": transport, "labour": labour, "electricity": electricity,
        "maintenance": maintenance, "disposal": disposal,
        "drying": drying,
        "sga": sga, "insurance": insurance,
        "om": labour + electricity + maintenance,
        "feedstock": 0.0, "ash": 0.0, "flue": 0.0,
        "aux": transport,    # transport sits in aux slot for cross-engine compat
        "pdf": 0.0,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════
def run_model(p: RDFInputs) -> dict:
    p = copy.deepcopy(p)

    raw = compute_raw_material(p)
    if "error" in raw:
        raise RuntimeError(raw["error"])

    rdf_t_d = raw["rdf_output_t_d"]
    rdf_sold_t_yr = raw["rdf_sold_t_yr"]
    msw_t_yr = raw["msw_intake_t_yr"]

    # R5: storage CAPEX — included into EPC base
    storage_capex = (rdf_t_d * p.storage_days_capacity
                     * p.storage_capex_thb_per_ton_capacity / 1e6)
    effective_epc = p.epc_cost + storage_capex

    # Revenue Year-1 estimate
    rev_yr1_est = (rdf_sold_t_yr * raw["rdf_price_thb_per_ton"] / 1e6
                    + msw_t_yr * p.tipping_fee / 1e6)
    debt_pre = capex_breakdown(effective_epc, p.owner_cost_pct,
                                p.contingency_pct, p.idc_pct,
                                p.debt_pct)["debt"]
    debt_svc_yr1_est = debt_pre * (p.interest_rate + 1 / p.debt_tenor)

    cx = capex_breakdown(
        effective_epc, p.owner_cost_pct, p.contingency_pct, p.idc_pct,
        p.debt_pct, mw_gross=rdf_t_d / 100, mw_net=rdf_t_d / 100,
        interest_rate=p.interest_rate,
        construction_years=p.construction_years,
        use_idc_drawdown=p.use_idc_drawdown,
        wc_pct_revenue_yr1=p.wc_pct_revenue_yr1,
        revenue_yr1_mb=rev_yr1_est,
        dsra_months=p.dsra_months,
        debt_service_yr1_mb=debt_svc_yr1_est,
        decommissioning_pct=p.decommissioning_pct,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = cx["total_proj_capex"] / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    carbon_mb_yr, be_yr = carbon_credit_tver(msw_t_yr, p.carbon_price,
                                              enabled=p.enable_carbon)

    rows, fcfe, fcff = [], [-equity], [-capex_total]
    cum_fcfe_list, cum_fcff_list = [], []
    cum_e, cum_p = -equity, -capex_total
    opex_list, rdf_tons_list = [], []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, raw, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw)
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
        opex_list.append(opex); rdf_tons_list.append(rdf_sold_t_yr)

        rows.append({
            "year": y + 1, "calendar_year": p.cod_year + y,
            "fit_rev": 0.0, "tip_rev": rev["tip_rev"],
            "rdf_rev": rev["rdf_rev"], "carbon_rev": rev["carbon_rev"],
            "revenue": revenue,
            "rev_breakdown": {"RDF Sales": rev["rdf_rev"],
                               "Tipping":   rev["tip_rev"],
                               "Carbon":    rev["carbon_rev"]},
            "opex_om": op["om"], "opex_feedstock": 0.0, "opex_ash": 0.0,
            "opex_flue": op["drying"],     # drying in flue slot for visualization
            "opex_aux": op["transport"],
            "opex_sga": op["sga"], "opex_insurance": op["insurance"],
            "opex_pdf": op["disposal"],
            "opex": opex, "opex_breakdown": op,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit,
            "interest": interest, "ebt": ebt,
            "tax_eff": tax_eff, "tax": tax_amt, "npat": npat, "ocf": ocf,
            "principal_repay": principal_repay,
            "cfads": cfads, "dscr": dscr,
            "fcfe": fcfe_y, "fcff": fcff_y,
        })

    # End-of-project recovery
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
    lco_pellet = lcoh_thb_per_ton(capex_total, opex_list, rdf_tons_list, p.discount_rate)
    debt_dscr = [r["dscr"] for r in rows
                  if r["principal_repay"] > 0 and r["dscr"] < float('inf')]
    dscr_min = min(debt_dscr) if debt_dscr else None
    dscr_avg = sum(debt_dscr) / len(debt_dscr) if debt_dscr else None

    kpis = {
        "project_irr": pirr, "equity_irr": eirr,
        "project_npv": pnpv, "equity_npv": enpv,
        "payback_project": pb_p, "payback_equity": pb_e,
        "dscr_min": dscr_min, "dscr_avg": dscr_avg,
        "lcoe_thb_per_kwh": None,
        "lco_pellet_thb_per_ton": lco_pellet,
        "bcr": bcr,
        "wacc": wacc["wacc"], "ke": wacc["ke"],
    }

    return build_result(
        engine_type="rdf",
        inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr": None,
            "msw_intake_t_yr":   raw["msw_intake_t_yr"],
            "msw_intake_t_d":    raw["msw_intake_t_d"],
            "rdf_output_t_yr":   raw["rdf_output_t_yr"],
            "rdf_output_t_d":    raw["rdf_output_t_d"],
            "rdf_sold_t_yr":     raw["rdf_sold_t_yr"],
            "rdf_rejected_t_yr": raw["rdf_rejected_t_yr"],
            "rdf_yield_pct":     raw["rdf_yield_pct"],
            "rdf_price_thb_per_ton": raw["rdf_price_thb_per_ton"],
            "lhv_kcal_per_kg":   raw["lhv_kcal_per_kg"],
            "feedstock_ton_yr":  raw["msw_intake_t_yr"],
            "feedstock_ton_day": raw["msw_intake_t_d"],
            "chlorine_pct":      raw["chlorine_pct"],
            "ash_pct":           raw["ash_pct"],
            "drying_energy_mb_yr": raw["drying_energy_mb_yr"],
            "storage_capex_mb":  storage_capex,
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


# ════════════════════════════════════════════════════════════════════════
# █  PRESET  █
# ════════════════════════════════════════════════════════════════════════
def default_preset() -> RDFInputs:
    return RDFInputs(
        project_name="RDF Cement Co-processing Plant",
        cod_year=2026, project_life=19,
        msw_intake_design_t_d=240.0, actual_utilization=1.0,
        op_days=365, availability=0.95,
        use_yield_from_composition=True,
        drying_loss_pct=0.20,
        use_msw_auto=True,
        msw_moisture=0.50,            # input MSW moisture (real Thai)
        msw_moisture_after_drying=0.15,
        msw_pct_food=0.30, msw_pct_paper=0.15, msw_pct_plastic=0.30,
        msw_pct_glass=0.04, msw_pct_metal=0.04, msw_pct_cloth=0.08,
        msw_pct_wood=0.05, msw_pct_rubber=0.02, msw_pct_leather=0.01,
        msw_pct_hazardous=0.005, msw_pct_other=0.005,
        drying_mj_per_kg_water=3.0,
        drying_fuel_lhv_mj_per_kg=38.0,
        drying_fuel_thb_per_ton=25000.0,
        use_quality_tier_pricing=True,
        rdf_price_thb_per_kcal_high=0.24,
        rdf_price_thb_per_kcal_std=0.20,
        rdf_price_thb_per_kcal_low=0.15,
        chlorine_cap_pct=0.7, ash_cap_pct=18.0,
        rdf_price_esc=0.015,
        offtake_utilization=0.85,
        storage_days_capacity=10,
        storage_capex_thb_per_ton_capacity=8000.0,
        tipping_fee=260.0, tipping_esc=0.01,
        epc_cost=76.2, owner_cost_pct=0.08, contingency_pct=0.10,
        idc_pct=0.04, construction_years=1,
        use_idc_drawdown=True,
        wc_pct_revenue_yr1=0.14,
        dsra_months=6.0,
        decommissioning_pct=0.02,
        transport_to_cement_thb_per_ton=260.0,
        labour_mb_yr=12.0, electricity_mb_yr=8.0,
        maintenance_mb_yr=8.0, disposal_misc_mb_yr=10.4,
        om_escalation=0.01, sga_my=2.0, sga_esc=0.02,
        insurance_par_pct=0.002, insurance_bi_pct=0.001, insurance_tpl_pct=0.0005,
        debt_pct=0.50, interest_rate=0.06375,
        debt_tenor=10, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


# ════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS  █
# ════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant Sizing", [
        ("project_name",          "Project Name",          "str",   ""),
        ("cod_year",              "COD Year",              "int",   ""),
        ("project_life",          "Project Life",          "int",   "yr"),
        ("msw_intake_design_t_d", "MSW Intake Design",     "float", "t/d"),
        ("actual_utilization",    "Actual Utilization",    "pct",   "%"),
        ("op_days",               "Operating Days",        "int",   "days/yr"),
        ("availability",          "Availability",          "pct",   "%"),
        ("use_yield_from_composition", "Use Composition Yield", "bool",
          "auto-calc yield from MSW mix"),
        ("rdf_yield_pct_manual",  "RDF Yield (manual)",    "pct",   "% if auto OFF"),
        ("drying_loss_pct",       "Drying Loss",           "pct",   "% extra"),
    ]),
    ("Raw Material — MSW Composition", [
        ("use_msw_auto",     "Use Dulong Auto",        "bool",  "ON for chemistry-driven"),
        ("msw_moisture",     "Moisture (input MSW)",   "pct",   "% (50% Thai typical)"),
        ("msw_moisture_after_drying", "Moisture after drying", "pct",
          "% (15-20% typical RDF)"),
        ("msw_pct_food",     "Food",                   "pct",   "%"),
        ("msw_pct_paper",    "Paper",                  "pct",   "%"),
        ("msw_pct_plastic",  "Plastic",                "pct",   "%"),
        ("msw_pct_glass",    "Glass",                  "pct",   "%"),
        ("msw_pct_metal",    "Metal",                  "pct",   "%"),
        ("msw_pct_cloth",    "Cloth",                  "pct",   "%"),
        ("msw_pct_wood",     "Wood",                   "pct",   "%"),
        ("msw_pct_rubber",   "Rubber",                 "pct",   "%"),
        ("msw_pct_leather",  "Leather",                "pct",   "%"),
        ("msw_pct_hazardous","Hazardous",              "pct",   "%"),
        ("msw_pct_other",    "Other",                  "pct",   "%"),
        ("lhv_manual_kcal_per_kg","LHV (manual)",      "float", "kcal/kg if auto OFF"),
    ]),
    ("Drying Energy (R2)", [
        ("drying_mj_per_kg_water", "Drying energy",    "float", "MJ/kg water"),
        ("drying_fuel_lhv_mj_per_kg", "Fuel LHV",      "float", "MJ/kg (NG=38)"),
        ("drying_fuel_thb_per_ton","Fuel price",       "float", "฿/ton"),
        ("drying_fuel_source",     "Fuel source",      "choice:natural_gas|diesel|biomass|waste_heat",  ""),
    ]),
    ("RDF Pricing — Quality Tiers (R3)", [
        ("use_quality_tier_pricing", "Quality Tier Pricing", "bool",
          "vs flat ฿/kcal"),
        ("rdf_price_thb_per_kcal_high","Price LHV≥4500","float", "฿/kcal"),
        ("rdf_price_thb_per_kcal_std", "Price LHV≥3500","float", "฿/kcal"),
        ("rdf_price_thb_per_kcal_low", "Price LHV≥2500","float", "฿/kcal"),
        ("chlorine_cap_pct",       "Chlorine cap",     "float", "% (cement reject above)"),
        ("ash_cap_pct",            "Ash cap",          "float", "% (cement reject above)"),
        ("rdf_price_thb_per_kcal", "Flat price (fallback)", "float", "฿/kcal"),
        ("rdf_price_esc",          "Price Escalation", "pct",   "%/yr"),
    ]),
    ("Offtake & Storage (R4 + R5)", [
        ("offtake_utilization",    "Offtake utilization","pct",  "% (cement actually buys)"),
        ("storage_days_capacity",  "Storage days",     "int",   "days RDF stockpile"),
        ("storage_capex_thb_per_ton_capacity", "Storage CAPEX", "float",
          "฿/ton capacity (silo ~8000)"),
        ("tipping_fee",            "Tipping Fee",      "float", "฿/ton MSW"),
        ("tipping_esc",            "Tipping Escalation","pct",  "%/yr"),
        ("carbon_price",           "Carbon Price",     "float", "฿/tCO₂"),
        ("enable_carbon",          "Enable Carbon",    "bool",  ""),
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
    ("OPEX", [
        ("transport_to_cement_thb_per_ton", "Transport",  "float", "฿/ton RDF"),
        ("labour_mb_yr",           "Labour",                "float", "MB/yr"),
        ("electricity_mb_yr",      "Plant Electricity",     "float", "MB/yr"),
        ("maintenance_mb_yr",      "Maintenance",           "float", "MB/yr"),
        ("disposal_misc_mb_yr",    "Disposal/Misc",         "float", "MB/yr"),
        ("om_escalation",          "OPEX Escalation",       "pct",   "%/yr"),
        ("sga_my",                 "SG&A (Y1)",             "float", "MB/yr"),
        ("sga_esc",                "SG&A Escalation",       "pct",   "%/yr"),
        ("insurance_par_pct",      "Property all-risk",     "pct",   "% CAPEX/yr"),
        ("insurance_bi_pct",       "Business interr.",      "pct",   "% CAPEX/yr"),
        ("insurance_tpl_pct",      "3rd-party liab.",       "pct",   "% CAPEX/yr"),
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
    print(f"  RDF yield        : {g['rdf_yield_pct']*100:>7.1f}% (realistic)")
    print(f"  RDF output       : {g['rdf_output_t_d']:>8.1f} t/d")
    print(f"  RDF sold         : {g['rdf_sold_t_yr']/p.op_days:>8.1f} t/d ({p.offtake_utilization*100:.0f}% offtake)")
    print(f"  LHV              : {r['lhv_kcal_per_kg']:>8.0f} kcal/kg")
    print(f"  Cl / Ash         : {r['chlorine_pct']:.2f}% / {r['ash_pct']:.1f}%")
    print(f"  RDF price        : {g['rdf_price_thb_per_ton']:>8.0f} ฿/ton")
    print(f"  Drying energy    : {g['drying_energy_mb_yr']:>8.2f} MB/yr")
    print(f"  Storage CAPEX    : {g['storage_capex_mb']:>8.2f} MB")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min / avg   : {k['dscr_min']:.2f} / {k['dscr_avg']:.2f}")
    print(f"  LCO-Pellet       : {k['lco_pellet_thb_per_ton']:>8.0f} ฿/ton")
