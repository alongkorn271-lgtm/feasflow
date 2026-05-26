"""
engines.biogas
==============
Biogas plant — anaerobic digestion of wastewater.

Improvements (B1-B6):
  B1 — Multi-source feedstock portfolio (mix sources with different COD/price)
  B2 — Year-1 startup ramp (bacterial culture growing)
  B3 — Digestate disposal cost
  B4 — Flare cost when grid down
  B5 — REC (Renewable Energy Certificate) revenue
  B6 — pH/VFA inhibition risk (Monte Carlo input)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import copy

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    carbon_credit_tver, ppa_escalated_rate, working_capital_recovery,
    build_result,
)


META = {
    "code":        "biogas",
    "label":       "Biogas",
    "icon":        "🌿",
    "description": "Anaerobic digestion of wastewater → biogas → electricity (TOU).",
    "color":       "#3FB950",
}

LHV_CH4_MJ_PER_NM3 = 35.8


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS — including multi-source portfolio  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class BiogasInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "Biogas Project"
    cod_year: int = 2027
    project_life: int = 25

    # ── Plant sizing ────────────────────────────────────────────
    mw_gross: float = 4.9
    mw_net:   float = 4.9
    availability: float = 1.0
    op_days: int = 333
    performance_warranty: float = 0.85

    # ── B1: Multi-source toggle ──────────────────────────────────
    use_multi_source: bool = False        # ON to use 3-source mix
    # Source A
    source_a_name: str = "Source A"
    source_a_m3_per_day: float = 800.0
    source_a_cod_mg_per_l: float = 190000
    source_a_ch4_pct: float = 0.48
    source_a_cost_thb_per_m3: float = 75.0
    # Source B
    source_b_name: str = "Source B"
    source_b_m3_per_day: float = 0.0
    source_b_cod_mg_per_l: float = 145000
    source_b_ch4_pct: float = 0.48
    source_b_cost_thb_per_m3: float = 134.0
    # Source C
    source_c_name: str = "Source C"
    source_c_m3_per_day: float = 0.0
    source_c_cod_mg_per_l: float = 149000
    source_c_ch4_pct: float = 0.48
    source_c_cost_thb_per_m3: float = 187.0

    # ── Single-source legacy ─────────────────────────────────────
    feedstock_name: str = "Vinasse"
    cod_mg_per_l: float = 190000.0
    ch4_pct: float = 0.48
    cod_removal_pct: float = 0.55
    ch4_yield_m3_per_kg: float = 0.35
    biogas_lhv_mj_per_m3: float = 17.5
    gas_engine_efficiency: float = 0.415
    material_cost_thb_per_m3: float = 50.0
    transport_cost_thb_per_m3: float = 0.0
    additional_cost_thb_per_m3: float = 25.0

    # ── B2: Year-1 startup ──────────────────────────────────────
    year1_capacity_factor: float = 0.75    # 70-80% during ramp

    # ── B3: Digestate disposal ──────────────────────────────────
    digestate_liquid_fraction: float = 0.85
    digestate_disposal_thb_per_m3: float = 50.0  # 50-100 ฿/m³

    # ── B4: Flare cost ──────────────────────────────────────────
    grid_downtime_pct: float = 0.02         # 2% of time flared
    flare_om_mb_yr: float = 0.5             # flare system O&M

    # ── B5: REC revenue ─────────────────────────────────────────
    enable_rec: bool = True
    rec_price_thb_per_mwh: float = 200.0    # 150-300 typical

    # ── Revenue (TOU) ───────────────────────────────────────────
    on_peak_price: float = 4.2243
    off_peak_price: float = 2.3567
    on_peak_ratio: float = 0.398
    cpi_escalation: float = 0.0
    cpi_linked_fraction: float = 0.0
    carbon_price: float = 80.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 320.0
    owner_cost_pct: float = 0.05
    contingency_pct: float = 0.05
    idc_pct: float = 0.05
    construction_years: int = 2
    use_idc_drawdown: bool = True
    wc_pct_revenue_yr1: float = 0.14
    dsra_months: float = 6.0
    decommissioning_pct: float = 0.02

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.0
    om_my_fixed: float = 34.49
    om_escalation: float = 0.002
    sga_my: float = 1.2
    sga_esc: float = 0.02
    insurance_par_pct: float = 0.002
    insurance_bi_pct: float = 0.001
    insurance_tpl_pct: float = 0.0005
    pdf_pct: float = 0.02

    # ── Finance ─────────────────────────────────────────────────
    debt_pct: float = 0.675
    interest_rate: float = 0.0528
    debt_tenor: int = 8
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
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
def biogas_lhv_auto(ch4_pct: float) -> float:
    return ch4_pct * LHV_CH4_MJ_PER_NM3


def _compute_source(p: BiogasInputs, m3_per_day: float, cod_mg_l: float,
                     ch4_pct: float, cost_thb_per_m3: float) -> dict:
    """Per-m³ chemistry for one feedstock source."""
    cod_load = cod_mg_l / 1000.0
    cod_removed = cod_load * p.cod_removal_pct
    ch4 = cod_removed * p.ch4_yield_m3_per_kg
    biogas = ch4 / ch4_pct if ch4_pct > 0 else 0
    lhv = p.biogas_lhv_mj_per_m3 if p.biogas_lhv_mj_per_m3 > 0 \
            else biogas_lhv_auto(ch4_pct)
    thermal = biogas * lhv
    electric = thermal * p.gas_engine_efficiency
    kwh_per_m3 = electric / 3.6

    annual_kwh = m3_per_day * p.op_days * kwh_per_m3
    annual_mwh = annual_kwh / 1000
    annual_cost_mb = m3_per_day * p.op_days * cost_thb_per_m3 / 1e6

    return {
        "m3_per_day":  m3_per_day,
        "m3_per_yr":   m3_per_day * p.op_days,
        "cod_load":    cod_load,
        "biogas_m3_per_m3": biogas,
        "kwh_per_m3":  kwh_per_m3,
        "lhv":         lhv,
        "annual_mwh":  annual_mwh,
        "annual_cost_mb": annual_cost_mb,
        "cost_thb_per_m3": cost_thb_per_m3,
    }


# ════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL (multi-source or single)  █
# ════════════════════════════════════════════════════════════════════════
def compute_raw_material(p: BiogasInputs) -> dict:
    if p.use_multi_source:
        sources_data = []
        # Source A
        if p.source_a_m3_per_day > 0:
            sources_data.append(
                {"name": p.source_a_name, **_compute_source(p,
                  p.source_a_m3_per_day, p.source_a_cod_mg_per_l,
                  p.source_a_ch4_pct, p.source_a_cost_thb_per_m3)})
        # B
        if p.source_b_m3_per_day > 0:
            sources_data.append(
                {"name": p.source_b_name, **_compute_source(p,
                  p.source_b_m3_per_day, p.source_b_cod_mg_per_l,
                  p.source_b_ch4_pct, p.source_b_cost_thb_per_m3)})
        # C
        if p.source_c_m3_per_day > 0:
            sources_data.append(
                {"name": p.source_c_name, **_compute_source(p,
                  p.source_c_m3_per_day, p.source_c_cod_mg_per_l,
                  p.source_c_ch4_pct, p.source_c_cost_thb_per_m3)})

        total_m3_day = sum(s["m3_per_day"] for s in sources_data)
        total_m3_yr  = sum(s["m3_per_yr"]  for s in sources_data)
        total_mwh    = sum(s["annual_mwh"] for s in sources_data)
        total_cost_mb = sum(s["annual_cost_mb"] for s in sources_data)
        # Weighted average for display
        if total_m3_yr > 0:
            avg_cod = sum(s["cod_load"] * s["m3_per_yr"] for s in sources_data) \
                       * 1000 / total_m3_yr
            avg_biogas_per_m3 = sum(s["biogas_m3_per_m3"] * s["m3_per_yr"]
                                      for s in sources_data) / total_m3_yr
            avg_kwh_per_m3 = sum(s["kwh_per_m3"] * s["m3_per_yr"]
                                   for s in sources_data) / total_m3_yr
        else:
            avg_cod = avg_biogas_per_m3 = avg_kwh_per_m3 = 0

        return {
            "mode":          "multi",
            "sources":       sources_data,
            "m3_per_day":    total_m3_day,
            "m3_per_yr":     total_m3_yr,
            "total_mwh_yr":  total_mwh,
            "total_cost_mb_yr": total_cost_mb,
            "weighted_cod_mg_l": avg_cod,
            "biogas_m3_per_m3": avg_biogas_per_m3,
            "kwh_per_m3":    avg_kwh_per_m3,
            "lhv_mj_per_m3": p.biogas_lhv_mj_per_m3 or biogas_lhv_auto(p.ch4_pct),
            "feedstock_cost_mb_yr": total_cost_mb,
            "target_mwh_yr": total_mwh,
            "biogas_total_m3_yr": total_m3_yr * avg_biogas_per_m3,
            "biogas_total_m3_day": total_m3_day * avg_biogas_per_m3,
        }

    # Single source (legacy)
    cod_load = p.cod_mg_per_l / 1000.0
    cod_removed = cod_load * p.cod_removal_pct
    ch4 = cod_removed * p.ch4_yield_m3_per_kg
    biogas = ch4 / p.ch4_pct if p.ch4_pct > 0 else 0
    lhv = p.biogas_lhv_mj_per_m3 if p.biogas_lhv_mj_per_m3 > 0 \
            else biogas_lhv_auto(p.ch4_pct)
    energy_thermal = biogas * lhv
    energy_electric = energy_thermal * p.gas_engine_efficiency
    kwh_per_m3 = energy_electric / 3.6

    total_cost_m3 = (p.material_cost_thb_per_m3
                      + p.transport_cost_thb_per_m3
                      + p.additional_cost_thb_per_m3)
    cost_per_m3_biogas = total_cost_m3 / biogas if biogas > 0 else 0
    cost_per_kwh = total_cost_m3 / kwh_per_m3 if kwh_per_m3 > 0 else 0

    hours_yr = p.op_days * 24 * p.availability * p.performance_warranty
    target_mwh = p.mw_net * hours_yr
    target_kwh = target_mwh * 1000
    m3_per_yr = target_kwh / kwh_per_m3 if kwh_per_m3 > 0 else 0
    m3_per_day = m3_per_yr / p.op_days if p.op_days > 0 else 0

    feedstock_cost_mb_yr = m3_per_yr * total_cost_m3 / 1e6

    return {
        "mode":                "single",
        "cod_load_kg_per_m3":     cod_load,
        "cod_removed_kg_per_m3":  cod_removed,
        "ch4_m3_per_m3":          ch4,
        "biogas_m3_per_m3":       biogas,
        "lhv_mj_per_m3":          lhv,
        "energy_thermal_mj_per_m3": energy_thermal,
        "energy_electric_mj_per_m3": energy_electric,
        "kwh_per_m3":             kwh_per_m3,
        "total_cost_thb_per_m3":  total_cost_m3,
        "cost_per_m3_biogas":     cost_per_m3_biogas,
        "cost_per_kwh_feedstock": cost_per_kwh,
        "target_mwh_yr":          target_mwh,
        "m3_per_yr":              m3_per_yr,
        "m3_per_day":             m3_per_day,
        "feedstock_cost_mb_yr":   feedstock_cost_mb_yr,
        "biogas_total_m3_yr":     m3_per_yr * biogas,
        "biogas_total_m3_day":    m3_per_day * biogas,
        "total_mwh_yr":           target_mwh,
    }


# ════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════
def _generation_mwh_year(p: BiogasInputs, raw: dict, year_idx: int) -> float:
    """B2: apply year-1 startup ramp + B4 flare loss."""
    if raw["mode"] == "multi":
        base_mwh = raw["total_mwh_yr"]
    else:
        base_mwh = raw["target_mwh_yr"]

    # B4: subtract flare losses (grid downtime)
    base_mwh *= (1 - p.grid_downtime_pct)

    # B2: Year 1 ramp
    if year_idx == 0:
        return base_mwh * p.year1_capacity_factor
    return base_mwh


def _yearly_revenue(p: BiogasInputs, year_idx: int, raw: dict,
                     carbon_mb_yr: float) -> dict:
    net_mwh = _generation_mwh_year(p, raw, year_idx)
    mwh_on = net_mwh * p.on_peak_ratio
    mwh_off = net_mwh * (1 - p.on_peak_ratio)

    # PPA escalation
    peak_rate = ppa_escalated_rate(p.on_peak_price, 0, year_idx, 0,
                                       p.cpi_escalation, p.cpi_linked_fraction)
    off_rate = ppa_escalated_rate(p.off_peak_price, 0, year_idx, 0,
                                      p.cpi_escalation, p.cpi_linked_fraction)
    rev_on = mwh_on * 1000 * peak_rate / 1e6
    rev_off = mwh_off * 1000 * off_rate / 1e6
    elec_rev = rev_on + rev_off

    # B5: REC revenue
    rec_rev = (net_mwh * p.rec_price_thb_per_mwh / 1e6) if p.enable_rec else 0

    revenue = elec_rev + rec_rev + carbon_mb_yr
    return {
        "rev_on":       rev_on,
        "rev_off":      rev_off,
        "elec_rev":     elec_rev,
        "rec_rev":      rec_rev,
        "carbon_rev":   carbon_mb_yr,
        "revenue":      revenue,
        "net_mwh":      net_mwh,
    }


def _yearly_opex(p: BiogasInputs, year_idx: int, capex_total: float,
                  raw: dict, elec_rev_mb: float) -> dict:
    esc = (1 + p.om_escalation) ** year_idx
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * esc
    else:
        om = capex_total * p.om_pct_capex * esc

    feedstock = raw["feedstock_cost_mb_yr"]
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * (p.insurance_par_pct
                                 + p.insurance_bi_pct
                                 + p.insurance_tpl_pct)
    pdf = elec_rev_mb * p.pdf_pct

    # B3: digestate disposal
    if raw["mode"] == "multi":
        ww_m3_yr = raw["m3_per_yr"]
    else:
        ww_m3_yr = raw["m3_per_yr"]
    digestate_cost_mb = (ww_m3_yr * p.digestate_liquid_fraction
                          * p.digestate_disposal_thb_per_m3 / 1e6 * esc)

    # B4: flare O&M
    flare_cost = p.flare_om_mb_yr * esc

    total = om + sga + insurance + pdf + feedstock + digestate_cost_mb + flare_cost
    return {
        "om": om, "feedstock": feedstock, "sga": sga,
        "insurance": insurance, "pdf": pdf,
        "digestate": digestate_cost_mb,
        "flare": flare_cost,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════
def run_model(p: BiogasInputs) -> dict:
    p = copy.deepcopy(p)
    raw = compute_raw_material(p)

    # Year-1 estimates
    rev_yr1_est = ((raw.get("total_mwh_yr", raw.get("target_mwh_yr", 0)) * 1000
                     * (p.on_peak_price * p.on_peak_ratio
                         + p.off_peak_price * (1 - p.on_peak_ratio)) / 1e6)
                    * p.year1_capacity_factor)
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
        revenue_yr1_mb=rev_yr1_est,
        dsra_months=p.dsra_months,
        debt_service_yr1_mb=debt_svc_yr1,
        decommissioning_pct=p.decommissioning_pct,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]; debt = cx["debt"]
    dep = cx["total_proj_capex"] / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    if raw["mode"] == "multi":
        ww_proxy_tons = raw["m3_per_yr"] * 0.05
    else:
        ww_proxy_tons = raw["m3_per_yr"] * 0.05
    carbon_mb_yr, be_yr = carbon_credit_tver(ww_proxy_tons, p.carbon_price,
                                              enabled=p.enable_carbon)

    rows = []; fcfe = [-equity]; fcff = [-capex_total]
    cum_fcfe_list, cum_fcff_list = [], []
    cum_e = -equity; cum_p = -capex_total
    opex_list, mwh_list = [], []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, raw, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw, rev["elec_rev"])
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
        opex_list.append(opex); mwh_list.append(rev["net_mwh"])

        rows.append({
            "year": y + 1, "calendar_year": p.cod_year + y,
            "fit_rev": rev["elec_rev"], "tip_rev": 0.0,
            "rdf_rev": 0.0, "carbon_rev": rev["carbon_rev"],
            "revenue": revenue,
            "rev_breakdown": {"On-Peak": rev["rev_on"],
                               "Off-Peak": rev["rev_off"],
                               "REC": rev["rec_rev"],
                               "Carbon": rev["carbon_rev"]},
            "opex_om": op["om"], "opex_feedstock": op["feedstock"],
            "opex_ash": 0.0, "opex_flue": op["digestate"],  # digestate visualised here
            "opex_aux": op["flare"],  # flare in aux slot
            "opex_sga": op["sga"], "opex_insurance": op["insurance"],
            "opex_pdf": op["pdf"],
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
        engine_type="biogas", inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr":            raw.get("total_mwh_yr", raw.get("target_mwh_yr", 0)),
            "feedstock_m3_yr":   raw["m3_per_yr"],
            "feedstock_m3_day":  raw["m3_per_day"] if "m3_per_day" in raw else raw["m3_per_day"],
            "biogas_m3_yr":      raw.get("biogas_total_m3_yr", 0),
            "biogas_m3_day":     raw.get("biogas_total_m3_day", 0),
            "kwh_per_m3":        raw.get("kwh_per_m3", 0),
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


def default_preset() -> BiogasInputs:
    return BiogasInputs(
        project_name="Biogas Plant 4.9 MW",
        cod_year=2010, project_life=25,
        mw_gross=4.9, mw_net=4.9,
        availability=1.0, op_days=333, performance_warranty=0.85,
        use_multi_source=False,        # single-source by default
        feedstock_name="Vinasse",
        cod_mg_per_l=190000, ch4_pct=0.48,
        cod_removal_pct=0.55, ch4_yield_m3_per_kg=0.35,
        biogas_lhv_mj_per_m3=17.5, gas_engine_efficiency=0.415,
        material_cost_thb_per_m3=50.0,
        transport_cost_thb_per_m3=0.0,
        additional_cost_thb_per_m3=25.0,
        year1_capacity_factor=0.75,
        digestate_liquid_fraction=0.85,
        digestate_disposal_thb_per_m3=50.0,
        grid_downtime_pct=0.02,
        flare_om_mb_yr=0.5,
        enable_rec=True,
        rec_price_thb_per_mwh=200.0,
        on_peak_price=4.2243, off_peak_price=2.3567, on_peak_ratio=0.398,
        cpi_escalation=0.0,
        epc_cost=320.0, owner_cost_pct=0.05, contingency_pct=0.05,
        idc_pct=0.05, construction_years=2,
        use_idc_drawdown=True,
        wc_pct_revenue_yr1=0.14,
        dsra_months=6.0,
        decommissioning_pct=0.02,
        om_pct_capex=0.0, om_my_fixed=34.49, om_escalation=0.002,
        sga_my=1.2, sga_esc=0.02,
        insurance_par_pct=0.002, insurance_bi_pct=0.001, insurance_tpl_pct=0.0005,
        pdf_pct=0.02,
        debt_pct=0.675, interest_rate=0.0528,
        debt_tenor=8, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


INPUT_SECTIONS = [
    ("Plant", [
        ("project_name", "Project Name", "str", ""),
        ("cod_year", "COD Year", "int", ""),
        ("project_life", "Project Life", "int", "yr"),
        ("mw_gross", "MW Gross", "float", "MW"),
        ("mw_net",   "MW Net",   "float", "MW"),
        ("availability", "Availability", "pct", "%"),
        ("op_days", "Operating Days", "int", "days/yr"),
        ("performance_warranty", "Performance Warranty", "pct", "%"),
    ]),
    ("Feedstock — Single Source (legacy)", [
        ("use_multi_source", "Use Multi-Source", "bool",
          "ON for portfolio mix below"),
        ("feedstock_name", "Feedstock Name", "str", ""),
        ("cod_mg_per_l", "COD", "float", "mg/L"),
        ("ch4_pct", "% CH₄", "pct", "%"),
        ("cod_removal_pct", "% COD Removal", "pct", ""),
        ("ch4_yield_m3_per_kg", "CH₄ Yield", "float", "m³/kg-COD"),
        ("biogas_lhv_mj_per_m3", "Biogas LHV", "float", "MJ/m³"),
        ("gas_engine_efficiency", "Gas Engine Eff", "pct", "%"),
        ("material_cost_thb_per_m3", "Material Cost", "float", "฿/m³"),
        ("transport_cost_thb_per_m3", "Transport Cost", "float", "฿/m³"),
        ("additional_cost_thb_per_m3", "Additional Cost", "float", "฿/m³"),
    ]),
    ("Multi-Source Portfolio (B1)", [
        ("source_a_name",         "Source A Name",      "str",   ""),
        ("source_a_m3_per_day",   "Source A m³/day",    "float", "m³"),
        ("source_a_cod_mg_per_l", "Source A COD",       "float", "mg/L"),
        ("source_a_ch4_pct",      "Source A %CH₄",      "pct",   "%"),
        ("source_a_cost_thb_per_m3","Source A Cost",    "float", "฿/m³"),
        ("source_b_name",         "Source B Name",      "str",   ""),
        ("source_b_m3_per_day",   "Source B m³/day",    "float", "(0 = unused)"),
        ("source_b_cod_mg_per_l", "Source B COD",       "float", "mg/L"),
        ("source_b_ch4_pct",      "Source B %CH₄",      "pct",   "%"),
        ("source_b_cost_thb_per_m3","Source B Cost",    "float", "฿/m³"),
        ("source_c_name",         "Source C Name",      "str",   ""),
        ("source_c_m3_per_day",   "Source C m³/day",    "float", "(0 = unused)"),
        ("source_c_cod_mg_per_l", "Source C COD",       "float", "mg/L"),
        ("source_c_ch4_pct",      "Source C %CH₄",      "pct",   "%"),
        ("source_c_cost_thb_per_m3","Source C Cost",    "float", "฿/m³"),
    ]),
    ("Operating risk & startup (B2, B4)", [
        ("year1_capacity_factor",  "Year-1 ramp",      "pct",   "% (75% typical)"),
        ("grid_downtime_pct",      "Grid downtime",    "pct",   "% (flared)"),
        ("flare_om_mb_yr",         "Flare O&M",        "float", "MB/yr"),
    ]),
    ("Digestate disposal (B3)", [
        ("digestate_liquid_fraction",  "Liquid fraction",  "pct", "%"),
        ("digestate_disposal_thb_per_m3","Disposal cost",  "float","฿/m³"),
    ]),
    ("REC Revenue (B5)", [
        ("enable_rec",                "Enable REC sales", "bool", ""),
        ("rec_price_thb_per_mwh",     "REC price",        "float","฿/MWh"),
    ]),
    ("Revenue (TOU)", [
        ("on_peak_price", "On-Peak Price", "float", "฿/kWh"),
        ("off_peak_price","Off-Peak Price","float", "฿/kWh"),
        ("on_peak_ratio", "On-Peak Ratio", "pct",   "%"),
        ("cpi_escalation","CPI Escalation","pct",   "%/yr"),
        ("cpi_linked_fraction","CPI-linked","pct",  "%"),
        ("carbon_price", "Carbon Price", "float", "฿/tCO₂"),
        ("enable_carbon", "Enable Carbon", "bool", ""),
    ]),
    ("CAPEX + Working Capital", [
        ("epc_cost", "EPC Cost", "float", "MB"),
        ("owner_cost_pct", "Owner's Cost", "pct", "%"),
        ("contingency_pct", "Contingency", "pct", "%"),
        ("idc_pct", "IDC (fallback)", "pct", "%"),
        ("use_idc_drawdown", "Use IDC Drawdown", "bool", ""),
        ("construction_years", "Construction", "int", "yr"),
        ("wc_pct_revenue_yr1", "Working Capital", "pct", "% Yr-1 rev"),
        ("dsra_months", "DSRA", "float", "months"),
        ("decommissioning_pct", "Decommissioning", "pct", "% CAPEX"),
    ]),
    ("OPEX", [
        ("om_pct_capex", "O&M", "pct", "%"),
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
        ("boi_full_years", "BOI 0%", "int", "yr"),
        ("boi_partial_years", "BOI 50%", "int", "yr"),
        ("boi_partial_rate", "BOI Partial", "pct", "%"),
        ("rf", "Risk-Free Rate", "pct", "%"),
        ("beta_unlevered", "β Unlevered", "float", ""),
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
    print(f"  Mode             : {r['mode']}")
    print(f"  Biogas/m³ feed   : {r.get('biogas_m3_per_m3', 0):>7.2f} m³")
    print(f"  kWh/m³ feed      : {r.get('kwh_per_m3', 0):>7.2f}")
    print(f"  Required feed    : {r.get('m3_per_day', 0):>7.0f} m³/day")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>6.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>6.2f}%")
    print(f"  DSCR min         : {k['dscr_min']:.2f}")
