"""
engines.rdf
===========
RDF (Refuse-Derived Fuel) plant — sell pellets to cement industry.

  MSW → sorting → shredding → drying → densification → RDF pellets
                                                          ↓ truck to cement plant

NO ELECTRICITY GENERATION — this is a fuel-production plant.

Revenue:
  RDF sales (฿/ton — priced on heat content kcal/kg × ฿/kcal)
  + Tipping fee from LAOs (paid to receive MSW)
  + Optional carbon credit (avoided landfill)

CAPEX:
  Sorting line + trommel + magnetic separator + dryer + densifier + storage
  Smaller than WTE (no boiler/turbine).

OPEX:
  Drying energy + electricity + transport to cement + labour + maintenance

Raw material: MSW (sorted) → typical yield 23-50% RDF by weight (EU avg).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoh_thb_per_ton,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    compute_msw_chemistry, carbon_credit_tver,
    build_result,
)


META = {
    "code":        "rdf",
    "label":       "RDF — Refuse Derived Fuel",
    "icon":        "🗑️",
    "description": "MSW → RDF pellets, sell to cement plants by ฿/kcal × LHV.",
    "color":       "#A371F7",
}


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT DATACLASS  █
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class RDFInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "RDF Plant"
    cod_year: int = 2026
    project_life: int = 19

    # ── Plant sizing (in TONNAGE not MW) ─────────────────────────
    msw_intake_design_t_d: float = 240.0    # tons MSW input per day
    actual_utilization: float = 1.0         # % of design
    op_days: int = 365
    availability: float = 0.95               # uptime for maintenance
    rdf_yield_pct: float = 1.0               # % RDF mass out / MSW in (after sorting)
    # mw_gross/mw_net not used but kept for CAPEX_per_MW computation
    mw_gross: float = 0.0
    mw_net: float = 0.0

    # ── MSW Raw Material (Dulong for LHV → price) ──────────────────
    use_msw_auto: bool = True
    msw_moisture: float = 0.20              # RDF is dried — lower moisture than raw MSW
    msw_pct_food:      float = 0.10
    msw_pct_paper:     float = 0.15
    msw_pct_plastic:   float = 0.50
    msw_pct_glass:     float = 0.02
    msw_pct_metal:     float = 0.02
    msw_pct_cloth:     float = 0.10
    msw_pct_wood:      float = 0.05
    msw_pct_rubber:    float = 0.02
    msw_pct_leather:   float = 0.02
    msw_pct_hazardous: float = 0.01
    msw_pct_other:     float = 0.01
    # Manual LHV (used if use_msw_auto = False)
    lhv_manual_kcal_per_kg: float = 4200.0  # typical RDF LHV (already dried)

    # ── Revenue ─────────────────────────────────────────────────
    rdf_price_thb_per_kcal: float = 0.20    # ฿/kcal — cement plant negotiation
    rdf_price_esc: float = 0.015            # escalation /yr (tracks coal)
    tipping_fee: float = 260.0              # ฿/ton MSW received from LAO
    tipping_esc: float = 0.01
    carbon_price: float = 80.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 76.2                  # MB — RDF plant is much cheaper than WTE
    owner_cost_pct: float = 0.08
    contingency_pct: float = 0.10
    idc_pct: float = 0.04
    construction_years: int = 1

    # ── OPEX ────────────────────────────────────────────────────
    transport_to_cement_thb_per_ton: float = 260.0  # ฿/ton RDF delivered
    labour_mb_yr: float = 12.0
    electricity_mb_yr: float = 8.0          # plant electricity consumption cost
    maintenance_mb_yr: float = 8.0
    disposal_misc_mb_yr: float = 10.4       # reject material disposal
    om_escalation: float = 0.01
    sga_my: float = 2.0
    sga_esc: float = 0.02
    insurance_pct: float = 0.003

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.50
    interest_rate: float = 0.06375
    debt_tenor: int = 10
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10

    # ── WACC ────────────────────────────────────────────────────
    rf: float = 0.0205
    beta_unlevered: float = 0.55            # slightly higher beta (off-take risk)
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# █  RAW MATERIAL  █
# ════════════════════════════════════════════════════════════════════════════
def _msw_composition(p: RDFInputs) -> dict:
    return {
        "food":      p.msw_pct_food,    "paper":     p.msw_pct_paper,
        "plastic":   p.msw_pct_plastic, "glass":     p.msw_pct_glass,
        "metal":     p.msw_pct_metal,   "cloth":     p.msw_pct_cloth,
        "wood":      p.msw_pct_wood,    "rubber":    p.msw_pct_rubber,
        "leather":   p.msw_pct_leather, "hazardous": p.msw_pct_hazardous,
        "other":     p.msw_pct_other,
    }


def compute_raw_material(p: RDFInputs) -> dict:
    """MSW intake → sorting yield → RDF tonnage + LHV (priced per kcal)."""
    if p.use_msw_auto:
        comp = _msw_composition(p)
        chem = compute_msw_chemistry(comp, p.msw_moisture)
        if chem is None:
            return {"error": "Invalid composition"}
        lhv_kcal = chem["lhv_kcal_per_kg"]
    else:
        chem = None
        lhv_kcal = p.lhv_manual_kcal_per_kg

    msw_in_t_yr = p.msw_intake_design_t_d * p.actual_utilization * p.op_days * p.availability
    rdf_out_t_yr = msw_in_t_yr * p.rdf_yield_pct
    rdf_out_t_d = rdf_out_t_yr / p.op_days if p.op_days else 0

    # RDF price = LHV × ฿/kcal
    rdf_price_thb_per_ton = lhv_kcal * p.rdf_price_thb_per_kcal

    return {
        "mode":                "auto" if p.use_msw_auto else "manual",
        "chemistry":           chem,
        "composition":         _msw_composition(p) if p.use_msw_auto else None,
        "lhv_kcal_per_kg":     lhv_kcal,
        "lhv_mj_per_kg":       lhv_kcal * 4.184e-3,
        "msw_intake_t_yr":     msw_in_t_yr,
        "msw_intake_t_d":      msw_in_t_yr / p.op_days if p.op_days else 0,
        "rdf_yield_pct":       p.rdf_yield_pct,
        "rdf_output_t_yr":     rdf_out_t_yr,
        "rdf_output_t_d":      rdf_out_t_d,
        "rdf_price_thb_per_ton": rdf_price_thb_per_ton,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  REVENUE & OPEX  █
# ════════════════════════════════════════════════════════════════════════════
def _yearly_revenue(p: RDFInputs, year_idx: int, raw: dict, carbon_mb_yr: float) -> dict:
    rdf_t_yr = raw["rdf_output_t_yr"]
    msw_t_yr = raw["msw_intake_t_yr"]

    # RDF sales: tons × price × escalation
    rdf_price = raw["rdf_price_thb_per_ton"] * (1 + p.rdf_price_esc) ** year_idx
    rdf_rev = rdf_t_yr * rdf_price / 1e6

    # Tipping fee from LAOs (per ton MSW received)
    tip_rev = msw_t_yr * p.tipping_fee * (1 + p.tipping_esc) ** year_idx / 1e6

    revenue = rdf_rev + tip_rev + carbon_mb_yr
    return {
        "rdf_rev":     rdf_rev,
        "tip_rev":     tip_rev,
        "carbon_rev":  carbon_mb_yr,
        "revenue":     revenue,
    }


def _yearly_opex(p: RDFInputs, year_idx: int, capex_total: float,
                  rdf_t_yr: float) -> dict:
    transport = rdf_t_yr * p.transport_to_cement_thb_per_ton / 1e6 \
                * (1 + p.om_escalation) ** year_idx
    labour = p.labour_mb_yr * (1 + p.om_escalation) ** year_idx
    electricity = p.electricity_mb_yr * (1 + p.om_escalation) ** year_idx
    maintenance = p.maintenance_mb_yr * (1 + p.om_escalation) ** year_idx
    disposal = p.disposal_misc_mb_yr * (1 + p.om_escalation) ** year_idx
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * p.insurance_pct
    total = transport + labour + electricity + maintenance + disposal + sga + insurance
    return {
        "transport": transport, "labour": labour, "electricity": electricity,
        "maintenance": maintenance, "disposal": disposal,
        "sga": sga, "insurance": insurance,
        "om": labour + electricity + maintenance,  # combined for compat
        "feedstock": 0.0, "ash": 0.0, "flue": 0.0, "aux": 0.0, "pdf": 0.0,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════════
def run_model(p: RDFInputs) -> dict:
    p = copy.deepcopy(p)

    raw = compute_raw_material(p)
    if "error" in raw:
        raise RuntimeError(raw["error"])

    # CAPEX (no MW concept — use raw output tonnage / 1000 as scaling factor)
    # For capex_per_mw, use rdf_output_t_d as proxy ("MW-equivalent")
    rdf_t_d = raw["rdf_output_t_d"]
    cx = capex_breakdown(p.epc_cost, p.owner_cost_pct, p.contingency_pct,
                          p.idc_pct, p.debt_pct,
                          mw_gross=rdf_t_d / 100,   # crude proxy
                          mw_net=rdf_t_d / 100)
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = capex_total / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    # Carbon credit (avoided landfill from MSW received)
    msw_t_yr = raw["msw_intake_t_yr"]
    carbon_mb_yr, be_yr = carbon_credit_tver(msw_t_yr, p.carbon_price,
                                              enabled=p.enable_carbon)

    rows = []
    fcfe = [-equity]
    fcff = [-capex_total]
    cum_fcfe_list = []; cum_fcff_list = []
    cum_e = 0; cum_p = -capex_total
    opex_list = []; rdf_tons_list = []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, raw, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw["rdf_output_t_yr"])
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

        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe_list.append(cum_e); cum_fcff_list.append(cum_p)
        opex_list.append(opex); rdf_tons_list.append(raw["rdf_output_t_yr"])

        rows.append({
            "year":           y + 1,
            "calendar_year":  p.cod_year + y,
            "fit_rev":        0.0,
            "tip_rev":        rev["tip_rev"],
            "rdf_rev":        rev["rdf_rev"],
            "carbon_rev":     rev["carbon_rev"],
            "revenue":        revenue,
            "rev_breakdown":  {"RDF Sales": rev["rdf_rev"],
                                "Tipping": rev["tip_rev"],
                                "Carbon": rev["carbon_rev"]},
            "opex_om":        op["om"],
            "opex_feedstock": 0.0,
            "opex_ash":       0.0,
            "opex_flue":      0.0,
            "opex_aux":       op["transport"],  # transport is the "aux" for RDF
            "opex_sga":       op["sga"],
            "opex_insurance": op["insurance"],
            "opex_pdf":       op["disposal"],   # use pdf slot for misc disposal
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
    # No LCOE — RDF is fuel, not electricity. LCO-Pellet instead.
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
        "lcoe_thb_per_kwh": None,                # N/A for RDF
        "lco_pellet_thb_per_ton": lco_pellet,
        "bcr": bcr,
        "wacc": wacc["wacc"], "ke": wacc["ke"],
    }

    return build_result(
        engine_type="rdf",
        inputs=asdict(p),
        raw_material=raw,
        generation={
            "mwh_yr":            None,             # no electricity
            "msw_intake_t_yr":   raw["msw_intake_t_yr"],
            "msw_intake_t_d":    raw["msw_intake_t_d"],
            "rdf_output_t_yr":   raw["rdf_output_t_yr"],
            "rdf_output_t_d":    raw["rdf_output_t_d"],
            "rdf_price_thb_per_ton": raw["rdf_price_thb_per_ton"],
            "lhv_kcal_per_kg":   raw["lhv_kcal_per_kg"],
            "feedstock_ton_yr":  raw["msw_intake_t_yr"],
            "feedstock_ton_day": raw["msw_intake_t_d"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


# ════════════════════════════════════════════════════════════════════════════
# █  PRESET — Default RDF (cement co-processing)  █
# ════════════════════════════════════════════════════════════════════════════
def default_preset() -> RDFInputs:
    """Reference RDF plant: 240 t/d MSW → ~240 t/d RDF (high plastic mix)."""
    return RDFInputs(
        project_name="RDF Cement Co-processing Plant",
        cod_year=2026, project_life=19,
        msw_intake_design_t_d=240.0, actual_utilization=1.0,
        op_days=365, availability=0.95,
        rdf_yield_pct=1.0,
        use_msw_auto=True,
        msw_moisture=0.20,
        msw_pct_food=0.10, msw_pct_paper=0.15, msw_pct_plastic=0.50,
        msw_pct_glass=0.02, msw_pct_metal=0.02, msw_pct_cloth=0.10,
        msw_pct_wood=0.05, msw_pct_rubber=0.02, msw_pct_leather=0.02,
        msw_pct_hazardous=0.01, msw_pct_other=0.01,
        rdf_price_thb_per_kcal=0.20,
        rdf_price_esc=0.015,
        tipping_fee=260.0, tipping_esc=0.01,
        epc_cost=76.2, owner_cost_pct=0.08, contingency_pct=0.10,
        idc_pct=0.04, construction_years=1,
        transport_to_cement_thb_per_ton=260.0,
        labour_mb_yr=12.0, electricity_mb_yr=8.0,
        maintenance_mb_yr=8.0, disposal_misc_mb_yr=10.4,
        om_escalation=0.01, sga_my=2.0, sga_esc=0.02,
        insurance_pct=0.003,
        debt_pct=0.50, interest_rate=0.06375,
        debt_tenor=10, discount_rate=0.0625,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS  █
# ════════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant", [
        ("project_name",          "Project Name",         "str",   ""),
        ("cod_year",              "COD Year",             "int",   ""),
        ("project_life",          "Project Life",         "int",   "yr"),
        ("msw_intake_design_t_d", "MSW Intake Design",    "float", "t/d"),
        ("actual_utilization",    "Actual Utilization",   "pct",   "%"),
        ("op_days",               "Operating Days",       "int",   "days/yr"),
        ("availability",          "Availability",         "pct",   "%"),
        ("rdf_yield_pct",         "RDF Yield (mass)",     "pct",   "% MSW input"),
    ]),
    ("Raw Material — MSW Composition (for LHV)", [
        ("use_msw_auto",     "Use Dulong Auto",       "bool",  "ON for chemistry-driven"),
        ("msw_moisture",     "Moisture (after drying)","pct",  "% — RDF is dried"),
        ("msw_pct_food",     "Food",                   "pct",  "%"),
        ("msw_pct_paper",    "Paper",                  "pct",  "%"),
        ("msw_pct_plastic",  "Plastic",                "pct",  "%"),
        ("msw_pct_glass",    "Glass",                  "pct",  "%"),
        ("msw_pct_metal",    "Metal",                  "pct",  "%"),
        ("msw_pct_cloth",    "Cloth",                  "pct",  "%"),
        ("msw_pct_wood",     "Wood/Grass",             "pct",  "%"),
        ("msw_pct_rubber",   "Rubber",                 "pct",  "%"),
        ("msw_pct_leather",  "Leather",                "pct",  "%"),
        ("msw_pct_hazardous","Hazardous",              "pct",  "%"),
        ("msw_pct_other",    "Other",                  "pct",  "%"),
        ("lhv_manual_kcal_per_kg","LHV (manual)",      "float","kcal/kg (if auto OFF)"),
    ]),
    ("Revenue", [
        ("rdf_price_thb_per_kcal", "RDF Price",         "float", "฿/kcal"),
        ("rdf_price_esc",          "Price Escalation",  "pct",   "%/yr"),
        ("tipping_fee",            "Tipping Fee from LAO","float","฿/ton MSW"),
        ("tipping_esc",            "Tipping Escalation","pct",   "%/yr"),
        ("carbon_price",           "Carbon Price",      "float", "฿/tCO₂"),
        ("enable_carbon",          "Enable Carbon",     "bool",  ""),
    ]),
    ("CAPEX & OPEX", [
        ("epc_cost",                       "EPC Cost",                  "float", "MB"),
        ("owner_cost_pct",                 "Owner's Cost",              "pct",   "% EPC"),
        ("contingency_pct",                "Contingency",               "pct",   "%"),
        ("idc_pct",                        "IDC",                       "pct",   "% EPC"),
        ("construction_years",             "Construction",              "int",   "yr"),
        ("transport_to_cement_thb_per_ton","Transport to Cement",       "float", "฿/ton RDF"),
        ("labour_mb_yr",                   "Labour",                    "float", "MB/yr"),
        ("electricity_mb_yr",              "Plant Electricity",         "float", "MB/yr"),
        ("maintenance_mb_yr",              "Maintenance",               "float", "MB/yr"),
        ("disposal_misc_mb_yr",            "Disposal/Misc",             "float", "MB/yr"),
        ("om_escalation",                  "OPEX Escalation",           "pct",   "%/yr"),
        ("sga_my",                         "SG&A (Y1)",                 "float", "MB/yr"),
        ("sga_esc",                        "SG&A Escalation",           "pct",   "%/yr"),
        ("insurance_pct",                  "Insurance",                 "pct",   "% CAPEX/yr"),
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
    print(f"  RDF output       : {r['rdf_output_t_d']:>8.1f} t/d")
    print(f"  LHV              : {r['lhv_kcal_per_kg']:>8.0f} kcal/kg")
    print(f"  RDF price        : {r['rdf_price_thb_per_ton']:>8.0f} ฿/ton")
    print(f"  Project IRR      : {(k['project_irr'] or 0)*100:>7.2f}%")
    print(f"  Equity IRR       : {(k['equity_irr']  or 0)*100:>7.2f}%")
    print(f"  DSCR min         : {k['dscr_min']:.2f}")
    print(f"  LCO-Pellet       : {k['lco_pellet_thb_per_ton']:>8.0f} ฿/ton")
