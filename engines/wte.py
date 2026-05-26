"""
engines.wte
===========
Pure Waste-to-Energy engine with realistic plant modeling.

  MSW → boiler (η_b) → steam → turbine (η_t) → gross MW → −parasitic → net MW

Improvements (W1-W7):
  W1 — Gross vs Net (parasitic load ~12-18%)
  W2 — Two-stage efficiency (boiler × turbine)
  W3 — Seasonal LHV variation
  W4 — Bottom ash (15%, non-haz) vs Fly ash (5%, hazardous)
  W5 — FGT consumables scaled with Cl/S content
  W6 — Major overhaul cycle (every 4 yr, 21-30 days outage)
  W7 — Refined aux fuel (startup + low-LHV supplementation)
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
    build_result,
)


META = {
    "code":        "wte",
    "label":       "WTE — Waste to Energy",
    "icon":        "🔥",
    "description": "Burn MSW to generate electricity. Revenue = FiT + tipping.",
    "color":       "#F0883E",
}


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class WTEInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "WTE Project"
    cod_year: int = 2027
    project_life: int = 20

    # ── Plant sizing (W1: gross vs net) ──────────────────────────
    mw_gross: float = 9.9                  # at generator terminal
    parasitic_load_pct: float = 0.15       # W1: fans + pumps + FGT (12-18%)
    availability: float = 0.85
    op_days: int = 330
    performance_warranty: float = 0.90

    # ── Efficiency (W2: two-stage) ───────────────────────────────
    boiler_efficiency: float = 0.80        # heat → steam (75-85%)
    turbine_efficiency: float = 0.28       # steam → electric (25-30%)
    # legacy `efficiency` field retained for back-compat
    efficiency: float = 0.0                # 0 = use boiler × turbine

    # ── MSW Raw Material (W3 seasonal variation) ─────────────────
    use_msw_auto: bool = True
    msw_moisture: float = 0.40
    seasonal_lhv_variation_pct: float = 0.15  # W3: wet/dry variation
    msw_pct_food:      float = 0.37
    msw_pct_paper:     float = 0.07
    msw_pct_plastic:   float = 0.32
    msw_pct_glass:     float = 0.09
    msw_pct_metal:     float = 0.05
    msw_pct_cloth:     float = 0.06
    msw_pct_wood:      float = 0.01
    msw_pct_rubber:    float = 0.00
    msw_pct_leather:   float = 0.00
    msw_pct_hazardous: float = 0.02
    msw_pct_other:     float = 0.01
    ncv_mj_per_kg_manual: float = 10.0

    waste_intake_design: float = 650.0
    actual_utilization: float = 0.80

    # ── Revenue ─────────────────────────────────────────────────
    fit_base: float = 5.78
    fit_premium: float = 0.70
    premium_years: int = 8
    cpi_escalation: float = 0.02           # C3: PPA escalation
    cpi_linked_fraction: float = 0.0       # 0 = flat FiT; 0.5 = SPP Hybrid-style
    tipping_fee: float = 400.0
    tipping_esc: float = 0.02
    carbon_price: float = 100.0
    enable_carbon: bool = True

    # ── CAPEX (with C2 IDC drawdown, C1 WC/DSRA) ─────────────────
    epc_cost: float = 2000.0
    owner_cost_pct: float = 0.10
    contingency_pct: float = 0.10
    idc_pct: float = 0.05                  # fallback if not using drawdown
    construction_years: int = 3
    use_idc_drawdown: bool = True          # C2: better IDC model
    wc_pct_revenue_yr1: float = 0.16       # ~2 months AR (60/365)
    dsra_months: float = 6.0               # C1: 6 months debt service reserve
    decommissioning_pct: float = 0.02      # C5: 2% of CAPEX at end

    # ── OPEX (W4, W5, W6, W7) ────────────────────────────────────
    om_pct_capex: float = 0.05
    om_my_fixed: float = 0.0
    om_escalation: float = 0.03

    # W4: Bottom vs Fly ash split
    bottom_ash_pct: float = 0.15           # 15% of MSW
    fly_ash_pct: float = 0.05              # 5% of MSW (HAZARDOUS)
    bottom_ash_disposal_thb_per_ton: float = 800.0
    fly_ash_disposal_thb_per_ton: float = 3000.0   # hazardous = expensive
    # legacy single ash for compat
    ash_pct: float = 0.20
    ash_disposal_cost: float = 800.0

    # W5: FGT consumables
    flue_gas_cost: float = 15.0            # fallback flat MB/yr
    use_fgt_scaling: bool = True           # W5: scale with Cl/S
    lime_kg_per_ton_msw: float = 12.0      # ~12 kg lime/ton MSW
    lime_price_thb_per_ton: float = 4500.0
    urea_kg_per_ton_msw: float = 3.0
    urea_price_thb_per_ton: float = 18000.0
    ac_kg_per_ton_msw: float = 0.5         # activated carbon
    ac_price_thb_per_ton: float = 60000.0
    bag_filter_replace_yrs: int = 3        # every 3 years
    bag_filter_replace_cost_mb: float = 3.0

    # W6: Major overhaul
    overhaul_interval_years: int = 4
    overhaul_outage_days: int = 28          # 21-30 days typical
    boiler_tube_replace_year: int = 12
    boiler_tube_replace_cost_mb: float = 25.0

    # W7: Aux fuel refined
    aux_fuel_thb_per_mwh: float = 800.0
    aux_fuel_pct: float = 0.03

    # SG&A + Insurance breakdown (C4)
    sga_my: float = 12.0
    sga_esc: float = 0.03
    insurance_par_pct: float = 0.0025      # 0.25% property all-risk
    insurance_bi_pct: float = 0.0015       # 0.15% business interruption
    insurance_tpl_pct: float = 0.0005      # 0.05% third-party liability
    pdf_pct: float = 0.02

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.06375
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


# ════════════════════════════════════════════════════════════════════════
# █  HELPERS  █
# ════════════════════════════════════════════════════════════════════════
def _plant_efficiency(p: WTEInputs) -> float:
    """W2: η_overall = η_boiler × η_turbine (unless legacy efficiency set)."""
    if p.efficiency > 0:
        return p.efficiency
    return p.boiler_efficiency * p.turbine_efficiency


def _mw_net(p: WTEInputs) -> float:
    """W1: Net MW = Gross × (1 − parasitic)."""
    return p.mw_gross * (1 - p.parasitic_load_pct)


def _msw_composition(p: WTEInputs) -> dict:
    return {
        "food":      p.msw_pct_food,    "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic, "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,   "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,    "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather, "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def _availability_year(p: WTEInputs, year_idx: int) -> float:
    """W6: lower availability in overhaul years."""
    avail = p.availability
    # Year-1 indexed: overhaul years are 4, 8, 12, 16 ...
    if (year_idx + 1) % p.overhaul_interval_years == 0:
        # Subtract overhaul outage days from operating days
        outage_factor = 1 - (p.overhaul_outage_days / 365.0)
        avail *= outage_factor
    # Year of boiler tube replacement: bigger outage
    if (year_idx + 1) == p.boiler_tube_replace_year:
        avail *= 0.85  # ~60 days outage
    return avail


# ════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL  █
# ════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: WTEInputs) -> dict:
    if p.use_msw_auto:
        chem = compute_msw_chemistry(_msw_composition(p), p.msw_moisture)
        lhv_kcal = chem["lhv_kcal_per_kg"] if chem else 0
    else:
        chem = None
        lhv_kcal = p.ncv_mj_per_kg_manual / 4.184e-3

    eta = _plant_efficiency(p)
    kwh_per_kg = lhv_kcal * eta / KCAL_PER_KWH

    # Required MSW for net target (mean availability over project life)
    mw_net = _mw_net(p)
    hours_yr = p.op_days * 24 * p.availability * p.performance_warranty
    target_mwh_yr = mw_net * hours_yr
    target_kwh_yr = target_mwh_yr * 1000

    if kwh_per_kg > 0:
        msw_kg_yr = target_kwh_yr / kwh_per_kg
        msw_ton_yr = msw_kg_yr / 1000
        msw_ton_d = msw_ton_yr / p.op_days
    else:
        msw_ton_yr = msw_ton_d = 0

    return {
        "mode": "auto" if p.use_msw_auto else "manual",
        "chemistry":        chem,
        "composition":      _msw_composition(p) if p.use_msw_auto else None,
        "lhv_kcal_per_kg":  lhv_kcal,
        "lhv_mj_per_kg":    lhv_kcal * 4.184e-3,
        "boiler_eff":       p.boiler_efficiency,
        "turbine_eff":      p.turbine_efficiency,
        "plant_eff":        eta,
        "mw_gross":         p.mw_gross,
        "mw_net":           mw_net,
        "parasitic_pct":    p.parasitic_load_pct,
        "kwh_per_kg_msw":   kwh_per_kg,
        "kwh_per_ton_msw":  kwh_per_kg * 1000,
        "target_mwh_yr":    target_mwh_yr,
        "msw_ton_per_yr":   msw_ton_yr,
        "msw_ton_per_day":  msw_ton_d,
        "bottom_ash_ton_yr": msw_ton_yr * p.bottom_ash_pct,
        "fly_ash_ton_yr":    msw_ton_yr * p.fly_ash_pct,
        "ash_ton_yr":       msw_ton_yr * (p.bottom_ash_pct + p.fly_ash_pct),
        "chlorine_pct":     chem.get("chlorine_pct", 0) if chem else 0,
    }


# ════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════
def _net_generation_mwh(p: WTEInputs, year_idx: int = 0) -> float:
    """Net MWh accounting for W6 overhaul-year availability."""
    hours = p.op_days * 24
    mw_net = _mw_net(p)
    avail = _availability_year(p, year_idx)
    return mw_net * hours * avail * p.performance_warranty


def _yearly_revenue(p: WTEInputs, year_idx: int, msw_ton_yr: float,
                     carbon_mb_yr: float) -> dict:
    net_mwh = _net_generation_mwh(p, year_idx)
    rate = ppa_escalated_rate(p.fit_base, p.fit_premium, year_idx,
                                 p.premium_years,
                                 p.cpi_escalation, p.cpi_linked_fraction)
    fit_rev = net_mwh * 1000 * rate / 1e6
    tip_rev = msw_ton_yr * p.tipping_fee * (1 + p.tipping_esc) ** year_idx / 1e6
    revenue = fit_rev + tip_rev + carbon_mb_yr
    return {
        "fit_rev":    fit_rev,
        "tip_rev":    tip_rev,
        "carbon_rev": carbon_mb_yr,
        "revenue":    revenue,
        "net_mwh":    net_mwh,
        "rate":       rate,
    }


def _yearly_opex(p: WTEInputs, year_idx: int, capex_total: float,
                  fit_rev_mb: float, msw_ton_yr: float, raw: dict) -> dict:
    # O&M (% or fixed)
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * (1 + p.om_escalation) ** year_idx
    else:
        om = capex_total * p.om_pct_capex * (1 + p.om_escalation) ** year_idx

    # W4: Split ash disposal
    esc = (1 + p.om_escalation) ** year_idx
    bottom_ash_cost = msw_ton_yr * p.bottom_ash_pct \
                       * p.bottom_ash_disposal_thb_per_ton / 1e6 * esc
    fly_ash_cost = msw_ton_yr * p.fly_ash_pct \
                    * p.fly_ash_disposal_thb_per_ton / 1e6 * esc
    ash_total = bottom_ash_cost + fly_ash_cost

    # W5: FGT consumables (scaled with MSW + Cl content)
    if p.use_fgt_scaling:
        cl_factor = 1.0 + raw.get("chlorine_pct", 0) * 0.1
        lime_cost = msw_ton_yr * p.lime_kg_per_ton_msw * cl_factor \
                     / 1000 * p.lime_price_thb_per_ton / 1e6 * esc
        urea_cost = msw_ton_yr * p.urea_kg_per_ton_msw \
                     / 1000 * p.urea_price_thb_per_ton / 1e6 * esc
        ac_cost = msw_ton_yr * p.ac_kg_per_ton_msw \
                   / 1000 * p.ac_price_thb_per_ton / 1e6 * esc
        # Bag filter replacement every N years
        bag_filter = (p.bag_filter_replace_cost_mb
                       if (year_idx + 1) % p.bag_filter_replace_yrs == 0
                       else 0)
        flue = lime_cost + urea_cost + ac_cost + bag_filter
    else:
        flue = p.flue_gas_cost * esc

    # W7: Aux fuel (refined — includes startup days after outage)
    aux = (_net_generation_mwh(p, year_idx) * p.aux_fuel_pct
            * p.aux_fuel_thb_per_mwh / 1e6 * esc)

    # W6: Boiler tube replacement (one-off in specific year)
    boiler_tube = (p.boiler_tube_replace_cost_mb
                    if (year_idx + 1) == p.boiler_tube_replace_year else 0)

    # SG&A
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx

    # C4: Insurance breakdown
    ins_par = capex_total * p.insurance_par_pct
    ins_bi  = capex_total * p.insurance_bi_pct
    ins_tpl = capex_total * p.insurance_tpl_pct
    insurance = ins_par + ins_bi + ins_tpl

    # PDF
    pdf = fit_rev_mb * p.pdf_pct

    total = (om + ash_total + flue + aux + boiler_tube + sga
              + insurance + pdf)

    return {
        "om": om,
        "bottom_ash":  bottom_ash_cost,
        "fly_ash":     fly_ash_cost,
        "ash":         ash_total,
        "flue":        flue,
        "aux":         aux,
        "boiler_tube": boiler_tube,
        "sga":         sga,
        "insurance":   insurance,
        "ins_par":     ins_par,
        "ins_bi":      ins_bi,
        "ins_tpl":     ins_tpl,
        "pdf":         pdf,
        "total":       total,
    }


# ════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════
def run_model(p: WTEInputs) -> dict:
    p = copy.deepcopy(p)

    raw = compute_raw_material(p)
    msw_ton_yr = raw["msw_ton_per_yr"]
    mw_net = _mw_net(p)

    # Carbon (constant for now — could scale per year)
    carbon_mb_yr, be_yr = carbon_credit_tver(msw_ton_yr, p.carbon_price,
                                              enabled=p.enable_carbon)

    # Estimate Year-1 revenue for WC sizing (rough but works)
    rev_yr1_estimate = (_net_generation_mwh(p, 0) * 1000
                         * (p.fit_base + p.fit_premium) / 1e6
                         + msw_ton_yr * p.tipping_fee / 1e6
                         + carbon_mb_yr)
    debt_svc_yr1_estimate = (capex_breakdown(p.epc_cost, p.owner_cost_pct,
                                              p.contingency_pct, p.idc_pct,
                                              p.debt_pct)["debt"]
                              * (p.interest_rate + 1/p.debt_tenor))

    # CAPEX with all C-improvements
    cx = capex_breakdown(
        p.epc_cost, p.owner_cost_pct, p.contingency_pct, p.idc_pct,
        p.debt_pct, p.mw_gross, mw_net,
        interest_rate=p.interest_rate,
        construction_years=p.construction_years,
        use_idc_drawdown=p.use_idc_drawdown,
        wc_pct_revenue_yr1=p.wc_pct_revenue_yr1,
        revenue_yr1_mb=rev_yr1_estimate,
        dsra_months=p.dsra_months,
        debt_service_yr1_mb=debt_svc_yr1_estimate,
        decommissioning_pct=p.decommissioning_pct,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = cx["total_proj_capex"] / p.project_life     # depreciate proj only, not WC/DSRA
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    rows = []
    fcfe = [-equity]
    fcff = [-capex_total]
    cum_fcfe_list, cum_fcff_list = [], []
    cum_e, cum_p = -equity, -capex_total
    opex_list, mwh_list = [], []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, msw_ton_yr, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, rev["fit_rev"], msw_ton_yr, raw)
        revenue = rev["revenue"]
        opex = op["total"]
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
        fcfe_y = ocf - principal_repay   # interest already deducted in NPAT
        fcff_y = ebit * (1 - tax_eff) + dep

        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe_list.append(cum_e); cum_fcff_list.append(cum_p)
        opex_list.append(opex); mwh_list.append(rev["net_mwh"])

        rows.append({
            "year": y + 1, "calendar_year": p.cod_year + y,
            "fit_rev": rev["fit_rev"], "tip_rev": rev["tip_rev"],
            "rdf_rev": 0.0, "carbon_rev": rev["carbon_rev"],
            "revenue": revenue,
            "rev_breakdown": {"FiT": rev["fit_rev"], "Tipping": rev["tip_rev"],
                               "Carbon": rev["carbon_rev"]},
            "opex_om": op["om"], "opex_feedstock": 0.0,
            "opex_ash": op["ash"],
            "opex_bottom_ash": op["bottom_ash"], "opex_fly_ash": op["fly_ash"],
            "opex_flue": op["flue"], "opex_aux": op["aux"],
            "opex_sga": op["sga"], "opex_insurance": op["insurance"],
            "opex_pdf": op["pdf"],
            "opex_boiler_tube": op["boiler_tube"],
            "opex": opex,
            "opex_breakdown": op,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit,
            "interest": interest, "ebt": ebt,
            "tax_eff": tax_eff, "tax": tax_amt, "npat": npat, "ocf": ocf,
            "principal_repay": principal_repay,
            "cfads": cfads, "dscr": dscr,
            "fcfe": fcfe_y, "fcff": fcff_y,
        })

    # End-of-project: return working capital + DSRA, subtract decom
    if len(fcfe) > 1:
        recovery = working_capital_recovery(cx["working_capital"], cx["dsra"])
        fcfe[-1] += recovery - cx["decom_cost"]
        fcff[-1] += recovery - cx["decom_cost"]
        # Update last cum
        if cum_fcfe_list:
            cum_fcfe_list[-1] = cum_fcfe_list[-1] + recovery - cx["decom_cost"]
            cum_fcff_list[-1] = cum_fcff_list[-1] + recovery - cx["decom_cost"]

    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value
        fcff[-1] += p.terminal_value

    # KPIs
    wacc = wacc_capm(p.rf, p.mrp, p.beta_unlevered,
                      p.debt_pct, p.tax_rate, p.interest_rate)
    eirr = irr_brentq(fcfe); pirr = irr_brentq(fcff)
    # FCFE discounted at cost of equity (ke); FCFF at WACC-proxy discount_rate
    enpv = npv_calc(fcfe, wacc["ke"])
    pnpv = npv_calc(fcff, p.discount_rate)
    pb_e = payback_period(cum_fcfe_list)
    pb_p = payback_period(cum_fcff_list)
    # UNIDO-style BCR: PV(rev) / [CAPEX + PV(opex)]  — no double-count via dep
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
        engine_type="wte", inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr":            _net_generation_mwh(p, 0),
            "mw_gross":          p.mw_gross,
            "mw_net":            mw_net,
            "parasitic_pct":     p.parasitic_load_pct,
            "boiler_eff":        p.boiler_efficiency,
            "turbine_eff":       p.turbine_efficiency,
            "plant_eff":         _plant_efficiency(p),
            "msw_ton_per_day":   raw["msw_ton_per_day"],
            "msw_ton_per_yr":    msw_ton_yr,
            "feedstock_ton_yr":  msw_ton_yr,
            "feedstock_ton_day": raw["msw_ton_per_day"],
            "bottom_ash_ton_yr": raw["bottom_ash_ton_yr"],
            "fly_ash_ton_yr":    raw["fly_ash_ton_yr"],
            "ash_ton_yr":        raw["ash_ton_yr"],
            "lhv_kcal_per_kg":   raw["lhv_kcal_per_kg"],
            "lhv_mj_per_kg":     raw["lhv_mj_per_kg"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


# ════════════════════════════════════════════════════════════════════════
# █  PRESET  █
# ════════════════════════════════════════════════════════════════════════
def default_preset() -> WTEInputs:
    return WTEInputs(
        project_name="Municipal WTE 1.5 MW",
        cod_year=2025, project_life=20,
        mw_gross=1.8, parasitic_load_pct=0.17,    # small plant = high parasitic %
        availability=0.85, op_days=330,
        performance_warranty=0.90,
        boiler_efficiency=0.78, turbine_efficiency=0.25,
        use_msw_auto=True,
        msw_moisture=0.50,
        msw_pct_food=0.37, msw_pct_paper=0.07, msw_pct_plastic=0.32,
        msw_pct_glass=0.09, msw_pct_metal=0.05, msw_pct_cloth=0.06,
        msw_pct_wood=0.01, msw_pct_hazardous=0.02, msw_pct_other=0.01,
        fit_base=5.78, fit_premium=0.70, premium_years=8,
        cpi_escalation=0.02, cpi_linked_fraction=0.0,
        tipping_fee=400.0, tipping_esc=0.02,
        epc_cost=240.0, owner_cost_pct=0.08, contingency_pct=0.05,
        idc_pct=0.05, construction_years=2,
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
        boiler_tube_replace_year=12, boiler_tube_replace_cost_mb=25.0,
        aux_fuel_pct=0.03,
        sga_my=2.5, sga_esc=0.03,
        insurance_par_pct=0.0025, insurance_bi_pct=0.0015, insurance_tpl_pct=0.0005,
        pdf_pct=0.02,
        debt_pct=0.70, interest_rate=0.06375,
        debt_tenor=12, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


# ════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS (for GUI)  █
# ════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant Sizing", [
        ("project_name",          "Project Name",          "str",    ""),
        ("cod_year",              "COD Year",              "int",    ""),
        ("project_life",          "Project Life",          "int",    "yr"),
        ("mw_gross",              "MW Gross (at generator)","float", "MW"),
        ("parasitic_load_pct",    "Parasitic Load",        "pct",    "% (12-18% typical)"),
        ("availability",          "Availability",          "pct",    "%"),
        ("op_days",               "Operating Days",        "int",    "days/yr"),
        ("performance_warranty",  "Performance Warranty",  "pct",    "%"),
        ("boiler_efficiency",     "Boiler Efficiency η_b", "pct",    "% (75-85%)"),
        ("turbine_efficiency",    "Turbine Efficiency η_t","pct",    "% (25-30%)"),
    ]),
    ("Raw Material — MSW", [
        ("use_msw_auto",     "Use Dulong Auto",       "bool", "ON for chemistry-driven"),
        ("msw_moisture",     "Moisture",              "pct",  "%"),
        ("seasonal_lhv_variation_pct", "Seasonal Variation", "pct", "% (wet/dry)"),
        ("msw_pct_food",     "Food",                  "pct",  "%"),
        ("msw_pct_paper",    "Paper",                 "pct",  "%"),
        ("msw_pct_plastic",  "Plastic",               "pct",  "%"),
        ("msw_pct_glass",    "Glass",                 "pct",  "%"),
        ("msw_pct_metal",    "Metal",                 "pct",  "%"),
        ("msw_pct_cloth",    "Cloth",                 "pct",  "%"),
        ("msw_pct_wood",     "Wood/Grass",            "pct",  "%"),
        ("msw_pct_rubber",   "Rubber",                "pct",  "%"),
        ("msw_pct_leather",  "Leather",               "pct",  "%"),
        ("msw_pct_hazardous","Hazardous",             "pct",  "%"),
        ("msw_pct_other",    "Other",                 "pct",  "%"),
    ]),
    ("Revenue", [
        ("fit_base",          "FiT Base",             "float", "฿/kWh"),
        ("fit_premium",       "FiT Premium",          "float", "฿/kWh"),
        ("premium_years",     "Premium Years",        "int",   "yr"),
        ("cpi_escalation",    "CPI Escalation",       "pct",   "%/yr (PPA-linked)"),
        ("cpi_linked_fraction","FiTv linked fraction","pct",   "% of rate (SPP Hybrid)"),
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
        ("use_idc_drawdown",    "Use IDC Drawdown", "bool",  "S-curve model"),
        ("construction_years",  "Construction",     "int",   "yr"),
        ("wc_pct_revenue_yr1",  "Working Capital",  "pct",   "% Year-1 revenue"),
        ("dsra_months",         "DSRA Reserve",     "float", "months debt svc"),
        ("decommissioning_pct", "Decommissioning",  "pct",   "% CAPEX at end"),
    ]),
    ("OPEX — Ash, FGT, O&M", [
        ("om_pct_capex",        "O&M",              "pct",   "% CAPEX/yr"),
        ("om_my_fixed",         "O&M Fixed",        "float", "MB/yr (0=use %)"),
        ("om_escalation",       "O&M Escalation",   "pct",   "%/yr"),
        ("bottom_ash_pct",      "Bottom Ash %",     "pct",   "% MSW"),
        ("bottom_ash_disposal_thb_per_ton", "Bottom Ash Disposal", "float", "฿/ton"),
        ("fly_ash_pct",         "Fly Ash %",        "pct",   "% MSW (HAZARDOUS)"),
        ("fly_ash_disposal_thb_per_ton",    "Fly Ash Disposal",    "float", "฿/ton"),
        ("use_fgt_scaling",     "FGT Scaling",      "bool",  "Scale with Cl/S"),
        ("lime_kg_per_ton_msw", "Lime usage",       "float", "kg/ton MSW"),
        ("lime_price_thb_per_ton","Lime price",     "float", "฿/ton"),
        ("urea_kg_per_ton_msw", "Urea usage",       "float", "kg/ton MSW"),
        ("ac_kg_per_ton_msw",   "Activated C usage","float", "kg/ton MSW"),
        ("bag_filter_replace_yrs", "Bag filter replace", "int", "yr cycle"),
        ("bag_filter_replace_cost_mb", "Bag filter cost", "float", "MB"),
        ("flue_gas_cost",       "Flue Gas (fallback)","float","MB/yr"),
    ]),
    ("OPEX — Overhaul, Aux, SG&A", [
        ("overhaul_interval_years",  "Major Overhaul",      "int",   "yr cycle"),
        ("overhaul_outage_days",     "Overhaul outage",     "int",   "days"),
        ("boiler_tube_replace_year", "Boiler tube replace", "int",   "year"),
        ("boiler_tube_replace_cost_mb","Boiler tube cost",  "float", "MB"),
        ("aux_fuel_pct",        "Aux Fuel % gen",   "pct",   "%"),
        ("aux_fuel_thb_per_mwh","Aux Fuel price",   "float", "฿/MWh"),
        ("sga_my",              "SG&A (Y1)",        "float", "MB/yr"),
        ("sga_esc",             "SG&A Escalation",  "pct",   "%/yr"),
        ("insurance_par_pct",   "Property all-risk","pct",   "% CAPEX/yr"),
        ("insurance_bi_pct",    "Business interr.", "pct",   "% CAPEX/yr"),
        ("insurance_tpl_pct",   "3rd-party liab.",  "pct",   "% CAPEX/yr"),
        ("pdf_pct",             "PDF",              "pct",   "% of FiT rev"),
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
    print(f"  MW gross / net    : {g['mw_gross']:.2f} / {g['mw_net']:.2f}")
    print(f"  Plant eff         : {g['plant_eff']*100:.1f}% "
          f"(boiler {g['boiler_eff']*100:.0f}% × turbine {g['turbine_eff']*100:.0f}%)")
    print(f"  LHV               : {r['lhv_kcal_per_kg']:>8,.0f} kcal/kg")
    print(f"  Required MSW      : {g['msw_ton_per_day']:>8.1f} ton/day")
    print(f"  Project IRR       : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR        : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min / avg    : {k['dscr_min']:.2f} / {k['dscr_avg']:.2f}")
    print(f"  LCOE              : {k['lcoe_thb_per_kwh']:>8.2f} THB/kWh")
