"""
engines.biogas
==============
Anaerobic-digestion biogas plant engine.

  Wastewater/vinasse → anaerobic digester → biogas → gas engine → electricity

Raw material chain (standard anaerobic-digestion methodology):
  COD load (kg/m³ feed)
    × %COD removal     → COD removed (kg/m³)
    × CH4 yield        → CH4 produced (m³-CH4/m³ feed)
    ÷ %CH4 in biogas   → biogas (m³-biogas/m³ feed)
    × LHV (≈ %CH4 × 35.8)
    × gas engine efficiency
    ÷ 3.6              → kWh per m³ feed

Revenue: TOU electricity sales (peak/off-peak) + optional carbon
OPEX:    Feedstock cost + O&M + transport + PDF + SG&A
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    HOURS_PER_YEAR,
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, capex_breakdown,
    build_result,
)


META = {
    "code":        "biogas",
    "label":       "Biogas",
    "icon":        "🌿",
    "description": "Anaerobic digestion of wastewater → biogas → electricity (TOU).",
    "color":       "#3FB950",
}


# Pure CH4 LHV (Nm³ basis)
LHV_CH4_MJ_PER_NM3 = 35.8


# ════════════════════════════════════════════════════════════════════════════
# █  INPUT DATACLASS  █
# ════════════════════════════════════════════════════════════════════════════
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

    # ── Raw Material — Feedstock chemistry (COD chain) ──────────
    feedstock_name: str = "Vinasse"
    cod_mg_per_l: float = 190000.0
    ch4_pct: float = 0.48
    cod_removal_pct: float = 0.55
    ch4_yield_m3_per_kg: float = 0.35
    biogas_lhv_mj_per_m3: float = 17.5      # 0 = auto from %CH4 × 35.8
    gas_engine_efficiency: float = 0.415

    # Feedstock cost (THB/m³ ≈ THB/ton for water-based)
    material_cost_thb_per_m3: float = 50.0
    transport_cost_thb_per_m3: float = 0.0
    additional_cost_thb_per_m3: float = 25.0

    # ── Revenue (TOU pricing) ───────────────────────────────────
    on_peak_price: float = 4.2243
    off_peak_price: float = 2.3567
    on_peak_ratio: float = 0.398            # 132.5 / 333 days (PEA TOU calendar)
    carbon_price: float = 80.0
    enable_carbon: bool = True

    # ── CAPEX ───────────────────────────────────────────────────
    epc_cost: float = 320.0
    owner_cost_pct: float = 0.05
    contingency_pct: float = 0.05
    idc_pct: float = 0.05
    construction_years: int = 2

    # ── OPEX ────────────────────────────────────────────────────
    om_pct_capex: float = 0.0
    om_my_fixed: float = 34.49              # 3.046 MB/month × 12 (typical reference)
    om_escalation: float = 0.002
    sga_my: float = 1.2
    sga_esc: float = 0.02
    insurance_pct: float = 0.0
    pdf_pct: float = 0.02

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.675
    interest_rate: float = 0.0528           # MLR-0.5% (2020)
    debt_tenor: int = 8
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
# █  RAW MATERIAL CHAIN  █
# ════════════════════════════════════════════════════════════════════════════
def biogas_lhv_auto(ch4_pct: float) -> float:
    """LHV of biogas from CH4 content (Nm³ basis)."""
    return ch4_pct * LHV_CH4_MJ_PER_NM3


def compute_raw_material(p: BiogasInputs) -> dict:
    """COD chain: per 1 m³ feedstock + required volume to meet target MW."""
    cod_load = p.cod_mg_per_l / 1000.0                  # kg-COD/m³
    cod_removed = cod_load * p.cod_removal_pct
    ch4 = cod_removed * p.ch4_yield_m3_per_kg
    biogas = ch4 / p.ch4_pct if p.ch4_pct > 0 else 0
    lhv = p.biogas_lhv_mj_per_m3 if p.biogas_lhv_mj_per_m3 > 0 else biogas_lhv_auto(p.ch4_pct)
    energy_thermal = biogas * lhv
    energy_electric = energy_thermal * p.gas_engine_efficiency
    kwh_per_m3 = energy_electric / 3.6

    # Cost
    total_cost_m3 = (p.material_cost_thb_per_m3
                      + p.transport_cost_thb_per_m3
                      + p.additional_cost_thb_per_m3)
    cost_per_m3_biogas = total_cost_m3 / biogas if biogas > 0 else 0
    cost_per_kwh = total_cost_m3 / kwh_per_m3 if kwh_per_m3 > 0 else 0

    # Required volume to meet target MW
    hours_yr = p.op_days * 24 * p.availability * p.performance_warranty
    target_mwh = p.mw_net * hours_yr
    target_kwh = target_mwh * 1000
    m3_per_yr = target_kwh / kwh_per_m3 if kwh_per_m3 > 0 else 0
    m3_per_day = m3_per_yr / p.op_days if p.op_days > 0 else 0

    feedstock_cost_mb_yr = m3_per_yr * total_cost_m3 / 1e6

    return {
        # Chemistry per 1 m³
        "cod_load_kg_per_m3":     cod_load,
        "cod_removed_kg_per_m3":  cod_removed,
        "ch4_m3_per_m3":          ch4,
        "biogas_m3_per_m3":       biogas,
        "lhv_mj_per_m3":          lhv,
        "energy_thermal_mj_per_m3": energy_thermal,
        "energy_electric_mj_per_m3": energy_electric,
        "kwh_per_m3":             kwh_per_m3,
        # Cost
        "total_cost_thb_per_m3":  total_cost_m3,
        "cost_per_m3_biogas":     cost_per_m3_biogas,
        "cost_per_kwh_feedstock": cost_per_kwh,
        # Required volume
        "target_mwh_yr":          target_mwh,
        "m3_per_yr":              m3_per_yr,
        "m3_per_day":             m3_per_day,
        "feedstock_cost_mb_yr":   feedstock_cost_mb_yr,
        # Total biogas
        "biogas_total_m3_yr":     m3_per_yr * biogas,
        "biogas_total_m3_day":    m3_per_day * biogas,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════════
def _net_generation_mwh(p: BiogasInputs) -> float:
    hours = p.op_days * 24
    return p.mw_net * hours * p.availability * p.performance_warranty


def _yearly_revenue(p: BiogasInputs, year_idx: int, carbon_mb_yr: float) -> dict:
    net_mwh = _net_generation_mwh(p)
    mwh_on = net_mwh * p.on_peak_ratio
    mwh_off = net_mwh * (1 - p.on_peak_ratio)
    rev_on = mwh_on * 1000 * p.on_peak_price / 1e6
    rev_off = mwh_off * 1000 * p.off_peak_price / 1e6
    elec_rev = rev_on + rev_off
    revenue = elec_rev + carbon_mb_yr
    return {
        "rev_on":       rev_on,
        "rev_off":      rev_off,
        "elec_rev":     elec_rev,
        "carbon_rev":   carbon_mb_yr,
        "revenue":      revenue,
        "net_mwh":      net_mwh,
    }


def _yearly_opex(p: BiogasInputs, year_idx: int, capex_total: float,
                  feedstock_cost_mb_yr: float, elec_rev_mb: float) -> dict:
    if p.om_my_fixed > 0:
        om = p.om_my_fixed * (1 + p.om_escalation) ** year_idx
    else:
        om = capex_total * p.om_pct_capex * (1 + p.om_escalation) ** year_idx
    sga = p.sga_my * (1 + p.sga_esc) ** year_idx
    insurance = capex_total * p.insurance_pct
    pdf = elec_rev_mb * p.pdf_pct
    feedstock = feedstock_cost_mb_yr
    total = om + sga + insurance + pdf + feedstock
    return {
        "om": om, "feedstock": feedstock, "sga": sga,
        "insurance": insurance, "pdf": pdf,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════════
def run_model(p: BiogasInputs) -> dict:
    p = copy.deepcopy(p)

    # Raw material
    raw = compute_raw_material(p)

    # CAPEX
    cx = capex_breakdown(p.epc_cost, p.owner_cost_pct, p.contingency_pct,
                          p.idc_pct, p.debt_pct, p.mw_gross, p.mw_net)
    capex_total = cx["total_capex"]
    equity = cx["equity"]
    debt = cx["debt"]
    dep = capex_total / p.project_life
    ds = debt_schedule_annuity(debt, p.interest_rate, p.debt_tenor, p.project_life)

    # Carbon (biogas avoided methane from WW = waste_m3/yr × 0.05 reference factor)
    from .shared import carbon_credit_tver
    waste_proxy_tons = raw["m3_per_yr"] * 0.05  # proxy: WW-equivalent waste mass
    carbon_mb_yr, be_yr = carbon_credit_tver(waste_proxy_tons, p.carbon_price,
                                              enabled=p.enable_carbon)

    # Year-by-year
    rows = []
    fcfe = [-equity]
    fcff = [-capex_total]
    cum_fcfe_list = []
    cum_fcff_list = []
    cum_e = 0; cum_p = -capex_total
    opex_list = []; mwh_list = []

    for y in range(p.project_life):
        rev = _yearly_revenue(p, y, carbon_mb_yr)
        op = _yearly_opex(p, y, capex_total, raw["feedstock_cost_mb_yr"], rev["elec_rev"])
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
        opex_list.append(opex); mwh_list.append(rev["net_mwh"])

        rows.append({
            "year":           y + 1,
            "calendar_year":  p.cod_year + y,
            "fit_rev":        rev["elec_rev"],
            "tip_rev":        0.0,
            "rdf_rev":        0.0,
            "carbon_rev":     rev["carbon_rev"],
            "revenue":        revenue,
            "rev_breakdown":  {"On-Peak": rev["rev_on"], "Off-Peak": rev["rev_off"],
                                "Carbon": rev["carbon_rev"]},
            "opex_om":        op["om"],
            "opex_feedstock": op["feedstock"],
            "opex_ash":       0.0,
            "opex_flue":      0.0,
            "opex_aux":       0.0,
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
        engine_type="biogas",
        inputs=asdict(p),
        raw_material=raw,
        generation={
            "mwh_yr":            _net_generation_mwh(p),
            "feedstock_m3_yr":   raw["m3_per_yr"],
            "feedstock_m3_day":  raw["m3_per_day"],
            "biogas_m3_yr":      raw["biogas_total_m3_yr"],
            "biogas_m3_day":     raw["biogas_total_m3_day"],
            "kwh_per_m3":        raw["kwh_per_m3"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis,
        fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe_list, cum_fcff=cum_fcff_list,
        carbon={"rev_mb_yr": carbon_mb_yr, "tco2_yr": be_yr},
    )


# ════════════════════════════════════════════════════════════════════════════
# █  PRESET — Biogas 4.9 MW vinasse reference  █
# ════════════════════════════════════════════════════════════════════════════
def default_preset() -> BiogasInputs:
    """Biogas 4.9 MW — vinasse feedstock reference case."""
    return BiogasInputs(
        project_name="Biogas Plant 4.9 MW",
        cod_year=2010, project_life=25,
        mw_gross=4.9, mw_net=4.9,
        availability=1.0, op_days=333, performance_warranty=0.85,
        feedstock_name="Vinasse",
        cod_mg_per_l=190000, ch4_pct=0.48,
        cod_removal_pct=0.55, ch4_yield_m3_per_kg=0.35,
        biogas_lhv_mj_per_m3=17.5, gas_engine_efficiency=0.415,
        material_cost_thb_per_m3=50.0,
        transport_cost_thb_per_m3=0.0,
        additional_cost_thb_per_m3=25.0,
        on_peak_price=4.2243, off_peak_price=2.3567, on_peak_ratio=0.398,
        epc_cost=320.0, owner_cost_pct=0.05, contingency_pct=0.05,
        idc_pct=0.05, construction_years=2,
        om_pct_capex=0.0, om_my_fixed=34.49, om_escalation=0.002,
        sga_my=1.2, sga_esc=0.02, insurance_pct=0.0, pdf_pct=0.02,
        debt_pct=0.675, interest_rate=0.0528,
        debt_tenor=8, discount_rate=0.0625,
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
        ("availability",          "Availability",          "pct",    "%"),
        ("op_days",               "Operating Days",        "int",    "days/yr"),
        ("performance_warranty",  "Performance Warranty",  "pct",    "%"),
    ]),
    ("Raw Material — Feedstock Chemistry (COD chain)", [
        ("feedstock_name",         "Feedstock Name",     "str",   ""),
        ("cod_mg_per_l",           "COD",                "float", "mg/L"),
        ("ch4_pct",                "% CH₄ in biogas",    "pct",   "%"),
        ("cod_removal_pct",        "% COD Removal",      "pct",   "anaerobic"),
        ("ch4_yield_m3_per_kg",    "CH₄ Yield",          "float", "m³-CH4/kg-COD"),
        ("biogas_lhv_mj_per_m3",   "Biogas LHV",         "float", "MJ/m³ (0=auto)"),
        ("gas_engine_efficiency",  "Gas Engine Eff",     "pct",   "% electric"),
        ("material_cost_thb_per_m3","Material Cost",     "float", "฿/m³"),
        ("transport_cost_thb_per_m3","Transport Cost",   "float", "฿/m³"),
        ("additional_cost_thb_per_m3","Additional Cost", "float", "฿/m³"),
    ]),
    ("Revenue (TOU)", [
        ("on_peak_price",   "On-Peak Price",    "float", "฿/kWh"),
        ("off_peak_price",  "Off-Peak Price",   "float", "฿/kWh"),
        ("on_peak_ratio",   "On-Peak Ratio",    "pct",   "%"),
        ("carbon_price",    "Carbon Price",     "float", "฿/tCO₂"),
        ("enable_carbon",   "Enable Carbon",    "bool",  ""),
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
        ("pdf_pct",             "PDF",              "pct",   "% of elec rev"),
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
    print(f"  Biogas/m³ vinasse : {r['biogas_m3_per_m3']:>7.2f} m³")
    print(f"  kWh/m³ vinasse    : {r['kwh_per_m3']:>7.2f}")
    print(f"  Required vinasse  : {r['m3_per_day']:>7.0f} m³/day")
    print(f"  Project IRR       : {(k['project_irr'] or 0)*100:>6.2f}%")
    print(f"  Equity IRR        : {(k['equity_irr']  or 0)*100:>6.2f}%")
    print(f"  DSCR min          : {k['dscr_min']:.2f}")
