"""
engines.rdf_wte
================
Combined RDF + WTE plant.

  MSW → sorting line → splits into:
                       ├─ RDF stream (sold to cement)
                       └─ WTE feed   (burned for electricity on-site)

Operator can tune the rdf_split (% MSW going to RDF vs WTE).
This captures the strategic choice many Thai projects face:
  • Sell premium RDF to cement (high ฿/ton) AND
  • Burn residual for electricity (FiT + own consumption)

Revenue:
  RDF sales         (฿/kcal × LHV × tons)
  + Electricity     (FiT × MWh + tipping fee)
  + Optional carbon
CAPEX: RDF line + incinerator + boiler + turbine
OPEX: combined
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    KCAL_PER_KWH,
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    compute_msw_chemistry, carbon_credit_tver,
    build_result,
)


META = {
    "code":        "rdf_wte",
    "label":       "RDF + WTE",
    "icon":        "🔄",
    "description": "Combined: split MSW into RDF (sell) + WTE feed (electricity).",
    "color":       "#26C6DA",
}


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT DATACLASS  █
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class RDFWTEInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "RDF + WTE Plant"
    cod_year: int = 2027
    project_life: int = 20

    # ── Plant sizing (electricity side) ──────────────────────────
    mw_gross: float = 9.9
    mw_net:   float = 8.0
    availability: float = 0.85
    op_days: int = 330
    performance_warranty: float = 0.90
    efficiency: float = 0.25

    # ── MSW Raw Material ─────────────────────────────────────────
    msw_intake_design_t_d: float = 500.0    # tons MSW input per day
    actual_utilization: float = 0.85

    # Split: % of MSW going to RDF sales (rest goes to WTE combustion)
    rdf_split_pct: float = 0.30             # 30% RDF / 70% WTE
    rdf_yield_pct: float = 1.0              # mass retention in RDF processing

    use_msw_auto: bool = True
    msw_moisture: float = 0.40
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
    ash_pct: float = 0.20

    # ── RDF revenue side ─────────────────────────────────────────
    rdf_price_thb_per_kcal: float = 0.20
    rdf_price_esc: float = 0.015
    transport_rdf_thb_per_ton: float = 260.0

    # ── WTE revenue side ─────────────────────────────────────────
    fit_base: float = 5.78
    fit_premium: float = 0.70
    premium_years: int = 8
    tipping_fee: float = 400.0
    tipping_esc: float = 0.02
    carbon_price: float = 100.0
    enable_carbon: bool = True

    # ── CAPEX (combined RDF line + WTE) ──────────────────────────
    epc_cost: float = 2100.0
    owner_cost_pct: float = 0.10
    contingency_pct: float = 0.10
    idc_pct: float = 0.05
    construction_years: int = 3

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.05
    om_my_fixed: float = 0.0
    om_escalation: float = 0.03
    ash_disposal_cost: float = 800.0
    flue_gas_cost: float = 15.0
    aux_fuel_thb_per_mwh: float = 800.0
    aux_fuel_pct: float = 0.03
    sga_my: float = 14.0
    sga_esc: float = 0.03
    insurance_pct: float = 0.004
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

    rf: float = 0.0205
    beta_unlevered: float = 0.55
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL  █
# ════════════════════════════════════════════════════════════════════════════
def _msw_composition(p: RDFWTEInputs) -> dict:
    return {
        "food":      p.msw_pct_food,    "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic, "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,   "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,    "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather, "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def compute_raw_material(p: RDFWTEInputs) -> dict:
    """Compute composition → LHV → split between RDF and WTE."""
    if p.use_msw_auto:
        chem = compute_msw_chemistry(_msw_composition(p), p.msw_moisture)
        lhv_kcal = chem["lhv_kcal_per_kg"] if chem else 0
    else:
        chem = None
        lhv_kcal = p.ncv_mj_per_kg_manual / 4.184e-3

    # MSW intake
    msw_t_yr = p.msw_intake_design_t_d * p.actual_utilization * p.op_days * p.availability
    msw_t_d  = msw_t_yr / p.op_days if p.op_days else 0

    # Split
    rdf_msw_t_yr = msw_t_yr * p.rdf_split_pct
    wte_msw_t_yr = msw_t_yr * (1 - p.rdf_split_pct)
    rdf_output_t_yr = rdf_msw_t_yr * p.rdf_yield_pct
    rdf_output_t_d  = rdf_output_t_yr / p.op_days if p.op_days else 0

    # WTE electricity from WTE-side MSW
    # kWh/kg = LHV(kcal) × η ÷ 859.845
    kwh_per_kg = lhv_kcal * p.efficiency / KCAL_PER_KWH
    wte_kwh_yr = wte_msw_t_yr * 1000 * kwh_per_kg
    wte_mwh_yr = wte_kwh_yr / 1000

    # RDF price
    rdf_price_thb_per_ton = lhv_kcal * p.rdf_price_thb_per_kcal

    return {
        "mode":                 "auto" if p.use_msw_auto else "manual",
        "chemistry":            chem,
        "composition":          _msw_composition(p) if p.use_msw_auto else None,
        "lhv_kcal_per_kg":      lhv_kcal,
        "lhv_mj_per_kg":        lhv_kcal * 4.184e-3,
        "msw_intake_t_yr":      msw_t_yr,
        "msw_intake_t_d":       msw_t_d,
        "rdf_msw_t_yr":         rdf_msw_t_yr,
        "wte_msw_t_yr":         wte_msw_t_yr,
        "rdf_output_t_yr":      rdf_output_t_yr,
        "rdf_output_t_d":       rdf_output_t_d,
        "rdf_price_thb_per_ton": rdf_price_thb_per_ton,
        "wte_mwh_yr":           wte_mwh_yr,
        "wte_kwh_per_kg":       kwh_per_kg,
        "ash_t_yr":             wte_msw_t_yr * p.ash_pct,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════════
def _fit_rate(p: RDFWTEInputs, year_idx: int) -> float:
    return p.fit_base + (p.fit_premium if year_idx < p.premium_years else 0)


def _yearly_revenue(p: RDFWTEInputs, year_idx: int, raw: dict,
                     carbon_mb_yr: float) -> dict:
    # RDF stream
    rdf_price = raw["rdf_price_thb_per_ton"] * (1 + p.rdf_price_esc) ** year_idx
    rdf_rev = raw["rdf_output_t_yr"] * rdf_price / 1e6

    # WTE stream
    fit_rev = raw["wte_mwh_yr"] * 1000 * _fit_rate(p, year_idx) / 1e6
    tip_rev = raw["msw_intake_t_yr"] * p.tipping_fee \
              * (1 + p.tipping_esc) ** year_idx / 1e6

    revenue = rdf_rev + fit_rev + tip_rev + carbon_mb_yr
    return {
        "rdf_rev":     rdf_rev,
        "fit_rev":     fit_rev,
        "tip_rev":     tip_rev,
        "carbon_rev":  carbon_mb_yr,
        "revenue":     revenue,
        "wte_mwh":     raw["wte_mwh_yr"],
    }


def _yearly_opex(p: RDFWTEInputs, year_idx: int, capex_total: float,
                  raw: dict, fit_rev_mb: float) -> dict:
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * (1 + p.om_escalation) ** year_idx
    else:
        om = capex_total * p.om_pct_capex * (1 + p.om_escalation) ** year_idx

    ash = raw["ash_t_yr"] * p.ash_disposal_cost / 1e6 \
          * (1 + p.om_escalation) ** year_idx
    flue = p.flue_gas_cost * (1 + p.om_escalation) ** year_idx
    aux = (raw["wte_mwh_yr"] * p.aux_fuel_pct * p.aux_fuel_thb_per_mwh / 1e6
            * (1 + p.om_escalation) ** year_idx)
    rdf_transport = raw["rdf_output_t_yr"] * p.transport_rdf_thb_per_ton / 1e6 \
                    * (1 + p.om_escalation) ** year_idx
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * p.insurance_pct
    pdf = fit_rev_mb * p.pdf_pct
    total = om + ash + flue + aux + rdf_transport + sga + insurance + pdf
    return {
        "om": om, "ash": ash, "flue": flue, "aux": aux,
        "rdf_transport": rdf_transport,
        "sga": sga, "insurance": insurance, "pdf": pdf,
        "feedstock": 0.0,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════════
def run_model(p: RDFWTEInputs) -> dict:
    p = copy.deepcopy(p)

    raw = compute_raw_material(p)
    msw_t_yr = raw["msw_intake_t_yr"]

    cx = capex_breakdown(p.epc_cost, p.owner_cost_pct, p.contingency_pct,
                          p.idc_pct, p.debt_pct, p.mw_gross, p.mw_net)
    capex_total = cx["total_capex"]
    equity = cx["equity"]; debt = cx["debt"]
    dep = capex_total / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    carbon_mb_yr, be_yr = carbon_credit_tver(msw_t_yr, p.carbon_price,
                                              enabled=p.enable_carbon)

    rows = []
    fcfe = [-equity]; fcff = [-capex_total]
    cum_fcfe_list = []; cum_fcff_list = []
    cum_e = 0; cum_p = -capex_total
    opex_list = []; mwh_list = []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, raw, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw, rev["fit_rev"])
        revenue = rev["revenue"]; opex = op["total"]
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
        opex_list.append(opex); mwh_list.append(rev["wte_mwh"])

        rows.append({
            "year":           y + 1,
            "calendar_year":  p.cod_year + y,
            "fit_rev":        rev["fit_rev"],
            "tip_rev":        rev["tip_rev"],
            "rdf_rev":        rev["rdf_rev"],
            "carbon_rev":     rev["carbon_rev"],
            "revenue":        revenue,
            "rev_breakdown":  {"RDF Sales": rev["rdf_rev"],
                                "FiT":      rev["fit_rev"],
                                "Tipping":  rev["tip_rev"],
                                "Carbon":   rev["carbon_rev"]},
            "opex_om":        op["om"],
            "opex_feedstock": 0.0,
            "opex_ash":       op["ash"],
            "opex_flue":      op["flue"],
            "opex_aux":       op["aux"] + op["rdf_transport"],
            "opex_sga":       op["sga"],
            "opex_insurance": op["insurance"],
            "opex_pdf":       op["pdf"],
            "opex":           opex,
            "opex_breakdown": op,
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
        })

    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value; fcff[-1] += p.terminal_value

    wacc = wacc_capm(p.rf, p.mrp, p.beta_unlevered,
                      p.debt_pct, p.tax_rate, p.interest_rate)
    eirr = irr_brentq(fcfe); pirr = irr_brentq(fcff)
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
        engine_type="rdf_wte",
        inputs=asdict(p),
        raw_material=raw,
        generation={
            "mwh_yr":           raw["wte_mwh_yr"],
            "msw_intake_t_yr":  raw["msw_intake_t_yr"],
            "msw_intake_t_d":   raw["msw_intake_t_d"],
            "rdf_output_t_yr":  raw["rdf_output_t_yr"],
            "rdf_output_t_d":   raw["rdf_output_t_d"],
            "wte_mwh_yr":       raw["wte_mwh_yr"],
            "ash_ton_yr":       raw["ash_t_yr"],
            "feedstock_ton_yr": raw["msw_intake_t_yr"],
            "feedstock_ton_day":raw["msw_intake_t_d"],
            "lhv_kcal_per_kg":  raw["lhv_kcal_per_kg"],
            "rdf_split_pct":    p.rdf_split_pct,
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


def default_preset() -> RDFWTEInputs:
    return RDFWTEInputs(
        project_name="Combined RDF + WTE 8 MW (30/70 split)",
        cod_year=2027, project_life=20,
        mw_gross=9.9, mw_net=8.0,
        availability=0.85, op_days=330,
        performance_warranty=0.90, efficiency=0.25,
        msw_intake_design_t_d=500.0, actual_utilization=0.85,
        rdf_split_pct=0.30, rdf_yield_pct=1.0,
        use_msw_auto=True, msw_moisture=0.40,
        msw_pct_food=0.30, msw_pct_paper=0.10, msw_pct_plastic=0.35,
        msw_pct_glass=0.08, msw_pct_metal=0.04, msw_pct_cloth=0.05,
        msw_pct_wood=0.05, msw_pct_rubber=0.01,
        msw_pct_hazardous=0.01, msw_pct_other=0.01,
        rdf_price_thb_per_kcal=0.20, rdf_price_esc=0.015,
        transport_rdf_thb_per_ton=260.0,
        fit_base=5.78, fit_premium=0.70, premium_years=8,
        tipping_fee=400.0, tipping_esc=0.02,
        epc_cost=2100.0, owner_cost_pct=0.10, contingency_pct=0.10,
        idc_pct=0.05, construction_years=3,
        om_pct_capex=0.05, om_escalation=0.03,
        ash_disposal_cost=800.0, flue_gas_cost=15.0,
        aux_fuel_pct=0.03, sga_my=14.0, sga_esc=0.03,
        insurance_pct=0.004, pdf_pct=0.02,
        debt_pct=0.70, interest_rate=0.06375,
        debt_tenor=12, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


INPUT_SECTIONS = [
    ("Plant", [
        ("project_name",          "Project Name",          "str",    ""),
        ("cod_year",              "COD Year",              "int",    ""),
        ("project_life",          "Project Life",          "int",    "yr"),
        ("mw_gross",              "WTE MW Gross",          "float",  "MW"),
        ("mw_net",                "WTE MW Net",            "float",  "MW"),
        ("availability",          "Availability",          "pct",    "%"),
        ("op_days",               "Operating Days",        "int",    "days/yr"),
        ("performance_warranty",  "Performance Warranty",  "pct",    "%"),
        ("efficiency",            "WTE Efficiency",        "pct",    "% thermal"),
    ]),
    ("Raw Material — MSW & Split", [
        ("msw_intake_design_t_d",  "MSW Intake Design",   "float", "t/d"),
        ("actual_utilization",     "Actual Utilization",  "pct",   "%"),
        ("rdf_split_pct",          "RDF Split",           "pct",   "% MSW → RDF"),
        ("rdf_yield_pct",          "RDF Yield",           "pct",   "% mass retained"),
        ("use_msw_auto",           "Use Dulong Auto",     "bool",  "ON for chemistry-driven"),
        ("msw_moisture",           "Moisture",            "pct",   "%"),
        ("msw_pct_food",           "Food",                "pct",   "%"),
        ("msw_pct_paper",          "Paper",               "pct",   "%"),
        ("msw_pct_plastic",        "Plastic",             "pct",   "%"),
        ("msw_pct_glass",          "Glass",               "pct",   "%"),
        ("msw_pct_metal",          "Metal",               "pct",   "%"),
        ("msw_pct_cloth",          "Cloth",               "pct",   "%"),
        ("msw_pct_wood",           "Wood/Grass",          "pct",   "%"),
        ("msw_pct_rubber",         "Rubber",              "pct",   "%"),
        ("msw_pct_leather",        "Leather",             "pct",   "%"),
        ("msw_pct_hazardous",      "Hazardous",           "pct",   "%"),
        ("msw_pct_other",          "Other",               "pct",   "%"),
        ("ash_pct",                "Ash %",               "pct",   "% input"),
    ]),
    ("Revenue", [
        ("rdf_price_thb_per_kcal", "RDF Price",        "float", "฿/kcal"),
        ("rdf_price_esc",          "RDF Escalation",   "pct",   "%/yr"),
        ("fit_base",               "WTE FiT Base",     "float", "฿/kWh"),
        ("fit_premium",            "FiT Premium",      "float", "฿/kWh"),
        ("premium_years",          "Premium Years",    "int",   "yr"),
        ("tipping_fee",            "Tipping Fee",      "float", "฿/ton MSW"),
        ("tipping_esc",            "Tipping Escalation","pct",  "%/yr"),
        ("carbon_price",           "Carbon Price",     "float", "฿/tCO₂"),
        ("enable_carbon",          "Enable Carbon",    "bool",  ""),
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
        ("ash_disposal_cost",   "Ash Disposal",     "float", "฿/ton"),
        ("flue_gas_cost",       "Flue Gas",         "float", "MB/yr"),
        ("aux_fuel_pct",        "Aux Fuel % gen",   "pct",   "%"),
        ("transport_rdf_thb_per_ton","Transport RDF","float","฿/ton RDF"),
        ("sga_my",              "SG&A (Y1)",        "float", "MB/yr"),
        ("sga_esc",             "SG&A Escalation",  "pct",   "%/yr"),
        ("insurance_pct",       "Insurance",        "pct",   "% CAPEX/yr"),
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
    k = res["kpis"]; r = res["raw_material"]
    print(f"━━━ {p.project_name} ━━━")
    print(f"  MSW intake       : {r['msw_intake_t_d']:>8.1f} t/d")
    print(f"  RDF output       : {r['rdf_output_t_d']:>8.1f} t/d  ({p.rdf_split_pct*100:.0f}% split)")
    print(f"  WTE generation   : {r['wte_mwh_yr']:>8.0f} MWh/yr")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min         : {k['dscr_min']:.2f}")
