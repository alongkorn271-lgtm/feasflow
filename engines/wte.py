"""
engines.wte
===========
Pure Waste-to-Energy engine.

  MSW → boiler combustion → steam → turbine → electricity

Revenue:
  Electricity sales (FiT or PPA) + Tipping fee + Optional carbon credit
CAPEX:
  Incinerator + boiler + turbine + flue gas treatment
OPEX:
  O&M + ash disposal + flue gas treatment + auxiliary fuel + SG&A + insurance + PDF

Raw material: MSW (or pre-processed RDF feed).
Chemistry: Dulong's Formula → HHV → LHV → required tons/day.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional
import copy

from .shared import (
    THAI_MARKET, HOURS_PER_YEAR, KCAL_PER_KWH,
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    compute_msw_chemistry, carbon_credit_tver,
    build_result,
)


META = {
    "code":        "wte",
    "label":       "WTE — Waste to Energy",
    "icon":        "🔥",
    "description": "Burn MSW to generate electricity. Revenue = FiT + tipping.",
    "color":       "#F0883E",
}


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT DATACLASS  █
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class WTEInputs:
    """All parameters for a WTE feasibility model."""
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "WTE Project"
    cod_year: int = 2027
    project_life: int = 20

    # ── Plant sizing ────────────────────────────────────────────
    mw_gross: float = 9.9
    mw_net:   float = 8.0
    availability: float = 0.85
    op_days: int = 330
    performance_warranty: float = 0.90
    efficiency: float = 0.25            # thermal-to-electric

    # ── MSW Raw Material (Dulong Auto-Compute) ──────────────────
    use_msw_auto: bool = True
    msw_moisture: float = 0.40
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
    # Manual NCV (used if use_msw_auto = False)
    ncv_mj_per_kg_manual: float = 10.0

    # Waste intake (computed when use_msw_auto=True)
    waste_intake_design: float = 650.0      # tons/day (placeholder, may be overridden)
    actual_utilization: float = 0.80

    # ── Revenue ─────────────────────────────────────────────────
    fit_base: float = 5.78                  # community waste VSPP (THB/kWh)
    fit_premium: float = 0.70
    premium_years: int = 8
    tipping_fee: float = 400.0
    tipping_esc: float = 0.02
    carbon_price: float = 100.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 2000.0                # MB
    owner_cost_pct: float = 0.10
    contingency_pct: float = 0.10
    idc_pct: float = 0.05
    construction_years: int = 3

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.05
    om_my_fixed: float = 0.0
    om_escalation: float = 0.03
    ash_disposal_cost: float = 800.0        # THB/ton ash
    ash_pct: float = 0.20                   # of input MSW
    flue_gas_cost: float = 15.0             # MB/yr
    aux_fuel_thb_per_mwh: float = 800.0
    aux_fuel_pct: float = 0.03              # of generation hours
    sga_my: float = 12.0
    sga_esc: float = 0.03
    insurance_pct: float = 0.004
    pdf_pct: float = 0.02                   # Power Development Fund

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.06375
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10

    # ── WACC (CAPM) ─────────────────────────────────────────────
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085
    parent_share: float = 1.0
    parent_tax_rate: float = 0.20
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL CALCS  █
# ════════════════════════════════════════════════════════════════════════════
def _msw_composition_dict(p: WTEInputs) -> dict:
    return {
        "food":      p.msw_pct_food,
        "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic,
        "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,
        "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,
        "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather,
        "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def compute_raw_material(p: WTEInputs) -> dict:
    """Compute MSW chemistry → LHV → required MSW tons/day."""
    if p.use_msw_auto:
        comp = _msw_composition_dict(p)
        chem = compute_msw_chemistry(comp, p.msw_moisture)
        if chem is None:
            return {"mode": "auto", "error": "Invalid composition", "lhv_kcal_per_kg": 0}
        lhv_kcal = chem["lhv_kcal_per_kg"]
    else:
        chem = None
        # Manual NCV in MJ/kg → convert to kcal/kg
        lhv_kcal = p.ncv_mj_per_kg_manual / 4.184e-3

    # kWh per kg MSW = LHV(kcal) × η ÷ 859.845
    kwh_per_kg = lhv_kcal * p.efficiency / KCAL_PER_KWH

    # Target generation
    hours_yr = p.op_days * 24 * p.availability * p.performance_warranty
    target_mwh_yr = p.mw_net * hours_yr
    target_kwh_yr = target_mwh_yr * 1000

    # Required MSW
    if kwh_per_kg > 0:
        msw_kg_yr = target_kwh_yr / kwh_per_kg
        msw_ton_yr = msw_kg_yr / 1000
        msw_ton_d  = msw_ton_yr / p.op_days
    else:
        msw_ton_yr = msw_ton_d = 0

    return {
        "mode":             "auto" if p.use_msw_auto else "manual",
        "chemistry":        chem,
        "composition":      _msw_composition_dict(p) if p.use_msw_auto else None,
        "lhv_kcal_per_kg":  lhv_kcal,
        "lhv_mj_per_kg":    lhv_kcal * 4.184e-3,
        "kwh_per_kg_msw":   kwh_per_kg,
        "kwh_per_ton_msw":  kwh_per_kg * 1000,
        "target_mwh_yr":    target_mwh_yr,
        "msw_ton_per_yr":   msw_ton_yr,
        "msw_ton_per_day":  msw_ton_d,
        "ash_ton_yr":       msw_ton_yr * p.ash_pct,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX / P&L  █
# ════════════════════════════════════════════════════════════════════════════
def _fit_rate(p: WTEInputs, year_idx: int) -> float:
    return p.fit_base + (p.fit_premium if year_idx < p.premium_years else 0.0)


def _net_generation_mwh(p: WTEInputs) -> float:
    hours = p.op_days * 24
    return p.mw_net * hours * p.availability * p.performance_warranty


def _yearly_revenue(p: WTEInputs, year_idx: int, msw_ton_yr: float,
                     carbon_mb_yr: float) -> dict:
    net_mwh = _net_generation_mwh(p)
    rate = _fit_rate(p, year_idx)
    fit_rev = net_mwh * 1000 * rate / 1e6
    tip_rev = msw_ton_yr * p.tipping_fee * (1 + p.tipping_esc) ** year_idx / 1e6
    revenue = fit_rev + tip_rev + carbon_mb_yr
    return {
        "fit_rev":    fit_rev,
        "tip_rev":    tip_rev,
        "carbon_rev": carbon_mb_yr,
        "revenue":    revenue,
        "net_mwh":    net_mwh,
    }


def _yearly_opex(p: WTEInputs, year_idx: int, capex_total: float,
                  fit_rev_mb: float, msw_ton_yr: float) -> dict:
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * (1 + p.om_escalation) ** year_idx
    else:
        om = capex_total * p.om_pct_capex * (1 + p.om_escalation) ** year_idx

    ash = msw_ton_yr * p.ash_pct * p.ash_disposal_cost / 1e6 * (1 + p.om_escalation) ** year_idx
    flue = p.flue_gas_cost * (1 + p.om_escalation) ** year_idx
    aux = (_net_generation_mwh(p) * p.aux_fuel_pct * p.aux_fuel_thb_per_mwh / 1e6
            * (1 + p.om_escalation) ** year_idx)
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * p.insurance_pct
    pdf = fit_rev_mb * p.pdf_pct
    total = om + ash + flue + aux + sga + insurance + pdf

    return {
        "om": om, "ash": ash, "flue": flue, "aux": aux,
        "sga": sga, "insurance": insurance, "pdf": pdf,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════════
def run_model(p: WTEInputs) -> dict:
    """Run full 20-year WTE feasibility model. Returns standard result dict."""
    p = copy.deepcopy(p)

    # ── Raw material ─────────────────────────────────────────────
    raw = compute_raw_material(p)
    msw_ton_yr = raw["msw_ton_per_yr"]

    # ── CAPEX ────────────────────────────────────────────────────
    cx = capex_breakdown(
        p.epc_cost, p.owner_cost_pct, p.contingency_pct, p.idc_pct,
        p.debt_pct, p.mw_gross, p.mw_net,
    )
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = capex_total / p.project_life

    # ── Debt schedule ───────────────────────────────────────────
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    # ── Carbon credit ───────────────────────────────────────────
    carbon_mb_yr, be_yr = carbon_credit_tver(msw_ton_yr, p.carbon_price,
                                              enabled=p.enable_carbon)

    # ── Year-by-year P&L ─────────────────────────────────────────
    rows = []
    fcfe = [-equity]
    fcff = [-capex_total]
    cum_fcfe_list = []
    cum_fcff_list = []
    cum_e = 0
    cum_p = -capex_total
    opex_list = []
    mwh_list = []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, msw_ton_yr, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, rev["fit_rev"], msw_ton_yr)
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
        fcfe_y = ocf - interest - principal_repay
        fcff_y = ebit * (1 - tax_eff) + dep

        fcfe.append(fcfe_y)
        fcff.append(fcff_y)
        cum_e += fcfe_y
        cum_p += fcff_y
        cum_fcfe_list.append(cum_e)
        cum_fcff_list.append(cum_p)
        opex_list.append(opex)
        mwh_list.append(rev["net_mwh"])

        rows.append({
            "year":           y + 1,
            "calendar_year":  p.cod_year + y,
            "fit_rev":        rev["fit_rev"],
            "tip_rev":        rev["tip_rev"],
            "rdf_rev":        0.0,
            "carbon_rev":     rev["carbon_rev"],
            "revenue":        revenue,
            "rev_breakdown":  {"FiT": rev["fit_rev"], "Tipping": rev["tip_rev"],
                                "Carbon": rev["carbon_rev"]},
            "opex_om":        op["om"],
            "opex_feedstock": 0.0,
            "opex_ash":       op["ash"],
            "opex_flue":      op["flue"],
            "opex_aux":       op["aux"],
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

    # Terminal value
    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value
        fcff[-1] += p.terminal_value

    # ── KPIs ─────────────────────────────────────────────────────
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
        "project_irr":       pirr,
        "equity_irr":        eirr,
        "project_npv":       pnpv,
        "equity_npv":        enpv,
        "payback_project":   pb_p,
        "payback_equity":    pb_e,
        "dscr_min":          dscr_min,
        "dscr_avg":          dscr_avg,
        "lcoe_thb_per_kwh":  lcoe,
        "bcr":               bcr,
        "wacc":              wacc["wacc"],
        "ke":                wacc["ke"],
    }

    return build_result(
        engine_type="wte",
        inputs=asdict(p),
        raw_material=raw,
        generation={
            "mwh_yr":            _net_generation_mwh(p),
            "msw_ton_per_day":   raw["msw_ton_per_day"],
            "msw_ton_per_yr":    msw_ton_yr,
            "feedstock_ton_yr":  msw_ton_yr,
            "feedstock_ton_day": raw["msw_ton_per_day"],
            "ash_ton_yr":        raw["ash_ton_yr"],
            "lhv_kcal_per_kg":   raw["lhv_kcal_per_kg"],
            "lhv_mj_per_kg":     raw["lhv_mj_per_kg"],
        },
        capex=cx,
        wacc=wacc,
        rows=rows,
        kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


# ════════════════════════════════════════════════════════════════════════════
# █  PRESET  █
# ════════════════════════════════════════════════════════════════════════════
def default_preset() -> WTEInputs:
    """Municipal WTE 1.5 MW — small-scale reference case."""
    return WTEInputs(
        project_name="Municipal WTE 1.5 MW",
        cod_year=2025, project_life=20,
        mw_gross=1.8, mw_net=1.5,
        availability=0.85, op_days=330,
        performance_warranty=0.90, efficiency=0.25,
        use_msw_auto=True,
        msw_moisture=0.50,
        msw_pct_food=0.37, msw_pct_paper=0.07, msw_pct_plastic=0.32,
        msw_pct_glass=0.09, msw_pct_metal=0.05, msw_pct_cloth=0.06,
        msw_pct_wood=0.01, msw_pct_hazardous=0.02, msw_pct_other=0.01,
        fit_base=5.78, fit_premium=0.70, premium_years=8,
        tipping_fee=400.0, tipping_esc=0.02,
        epc_cost=240.0, owner_cost_pct=0.08, contingency_pct=0.05,
        idc_pct=0.05, construction_years=2,
        om_pct_capex=0.05, om_escalation=0.03,
        ash_disposal_cost=800.0, flue_gas_cost=4.0,
        aux_fuel_pct=0.03, sga_my=2.5, sga_esc=0.03,
        insurance_pct=0.005, pdf_pct=0.02,
        debt_pct=0.70, interest_rate=0.06375,
        debt_tenor=12, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS  — for GUI sidebar engine view  █
# ════════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant", [
        ("project_name",          "Project Name",          "str",    ""),
        ("cod_year",              "COD Year",              "int",    ""),
        ("project_life",          "Project Life",          "int",    "yr"),
        ("mw_gross",              "MW Gross (installed)",  "float",  "MW"),
        ("mw_net",                "MW Net (contracted)",   "float",  "MW"),
        ("availability",          "Availability",          "pct",    "%"),
        ("op_days",               "Operating Days",        "int",    "days/yr"),
        ("performance_warranty",  "Performance Warranty",  "pct",    "%"),
        ("efficiency",            "Thermal Efficiency",    "pct",    "%"),
    ]),
    ("Raw Material — MSW", [
        ("use_msw_auto",     "Use Dulong Auto-Compute", "bool", "ON for chemistry-driven"),
        ("msw_moisture",     "Moisture",                "pct",  "%"),
        ("msw_pct_food",     "Food",                    "pct",  "%"),
        ("msw_pct_paper",    "Paper",                   "pct",  "%"),
        ("msw_pct_plastic",  "Plastic",                 "pct",  "%"),
        ("msw_pct_glass",    "Glass",                   "pct",  "%"),
        ("msw_pct_metal",    "Metal",                   "pct",  "%"),
        ("msw_pct_cloth",    "Cloth",                   "pct",  "%"),
        ("msw_pct_wood",     "Wood/Grass",              "pct",  "%"),
        ("msw_pct_rubber",   "Rubber",                  "pct",  "%"),
        ("msw_pct_leather",  "Leather",                 "pct",  "%"),
        ("msw_pct_hazardous","Hazardous",               "pct",  "%"),
        ("msw_pct_other",    "Other",                   "pct",  "%"),
        ("ncv_mj_per_kg_manual","NCV (manual)",         "float","MJ/kg (if auto OFF)"),
        ("ash_pct",          "Ash %",                   "pct",  "%"),
    ]),
    ("Revenue", [
        ("fit_base",       "FiT Base",         "float", "฿/kWh"),
        ("fit_premium",    "FiT Premium",      "float", "฿/kWh"),
        ("premium_years",  "Premium Years",    "int",   "yr"),
        ("tipping_fee",    "Tipping Fee",      "float", "฿/ton"),
        ("tipping_esc",    "Tipping Escalation","pct",  "%/yr"),
        ("carbon_price",   "Carbon Price",     "float", "฿/tCO₂"),
        ("enable_carbon",  "Enable Carbon Credit", "bool", ""),
    ]),
    ("CAPEX & OPEX", [
        ("epc_cost",            "EPC Cost",         "float", "MB"),
        ("owner_cost_pct",      "Owner's Cost",     "pct",   "% EPC"),
        ("contingency_pct",     "Contingency",      "pct",   "%"),
        ("idc_pct",             "IDC",              "pct",   "% EPC"),
        ("construction_years",  "Construction",     "int",   "yr"),
        ("om_pct_capex",        "O&M",              "pct",   "% CAPEX/yr"),
        ("om_my_fixed",         "O&M Fixed",        "float", "MB/yr (0=use %)"),
        ("om_escalation",       "O&M Escalation",   "pct",   "%/yr"),
        ("ash_disposal_cost",   "Ash Disposal",     "float", "฿/ton"),
        ("flue_gas_cost",       "Flue Gas",         "float", "MB/yr"),
        ("aux_fuel_pct",        "Aux Fuel % gen",   "pct",   "%"),
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
    k = res["kpis"]
    print(f"━━━ {p.project_name} ━━━")
    print(f"  LHV               : {res['raw_material']['lhv_kcal_per_kg']:>8,.0f} kcal/kg")
    print(f"  Required MSW      : {res['generation']['msw_ton_per_day']:>8.1f} ton/day")
    print(f"  Project IRR       : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR        : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min / avg    : {k['dscr_min']:.2f} / {k['dscr_avg']:.2f}")
    print(f"  LCOE              : {k['lcoe_thb_per_kwh']:>8.2f} THB/kWh")
