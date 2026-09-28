"""
engines.biomass
===============
Solid-biomass steam plant (grate boiler → condensing turbine) for Thai
VSPP / SPP projects, e.g. corn husk + wood chip plants.

  fuel mix (moisture, dry LHV) → as-received LHV
  net MWh = min(gross × (1 − parasitic), contract MW) × 8760 × AF × LF
  fuel t  = net kWh × net heat rate ÷ LHV_mix

Two analysis modes (same engine, same output schema):

  • Greenfield  (brownfield_mode = False)
      CAPEX build-up → 20-yr PPA → IRR / NPV / DSCR / LCOE, like the WTE engine.

  • Brownfield / operating asset  (brownfield_mode = True)
      Starts at `valuation_year` with an operating plant: opening debt balance,
      remaining book value, remaining BOI years, PPA ending in `ppa_end_year`.
      t0 outflow = `entry_value_mb` (price paid for the whole asset; 0 → NPV only,
      i.e. NPV = present value of remaining cash flows = asset / equity value).
      Used for owner-side questions such as "what is +1 % availability worth
      over the remaining PPA?".

Differences vs the WTE engine
  • No tipping fee / MSW chemistry. Fuel is BOUGHT (฿/t) → largest OPEX line.
  • Export capped at contract MW (VSPP), so extra gross capacity only buffers
    wet fuel / degradation — it does not add revenue.
  • Heat rate can be entered directly (e.g. from an IAPWS heat balance) or
    built from boiler × cycle efficiency.
  • T-VER from grid-electricity displacement: tCO2e = net MWh × grid EF.

All default numbers are ASSUMPTIONS for illustration; see presets.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import copy

from .shared import (
    irr_brentq, npv_calc, payback_period, dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm, boi_tax_rate, TaxLossCarryForward,
    capex_breakdown, working_capital_recovery,
    build_result,
)

HOURS_YR = 8760.0

META = {
    "code":        "biomass",
    "label":       "Biomass — Solid fuel steam plant",
    "icon":        "🌾",
    "description": "Buy agri/wood residue, burn in grate boiler. Revenue = FiT (+ T-VER).",
    "color":       "#8BAA3C",
}


# ════════════════════════════════════════════════════════════════════════
# █  INPUTS  █
# ════════════════════════════════════════════════════════════════════════
@dataclass
class BiomassInputs:
    # ── Project meta ─────────────────────────────────────────────
    project_name: str = "Biomass Project"
    cod_year: int = 2027
    project_life: int = 20

    # ── Brownfield / operating-asset mode ────────────────────────
    brownfield_mode: bool = False
    valuation_year: int = 2026          # first modelled calendar year
    ppa_end_year: int = 2046            # last calendar year with PPA revenue
    last_year_fraction: float = 1.0     # share of the final year still under PPA
    entry_value_mb: float = 0.0         # EV paid at valuation (0 = NPV only)
    opening_debt_mb: float = 0.0        # debt balance at start of valuation_year
    remaining_debt_tenor: int = 0       # years left on the loan
    remaining_book_value_mb: float = 0.0
    remaining_dep_years: int = 0

    # ── Plant sizing ─────────────────────────────────────────────
    mw_gross: float = 9.9               # installed, generator terminal
    contract_mw: float = 8.0            # PPA export cap
    parasitic_load_pct: float = 0.10    # aux power, % of gross
    availability: float = 0.90          # AF: hours available / 8760
    load_factor: float = 0.98           # MW exported ÷ contract MW while running
    overhaul_interval_years: int = 4    # counted from COD
    overhaul_extra_outage_days: int = 14

    # ── Efficiency / heat rate ───────────────────────────────────
    use_heat_rate_input: bool = True
    net_heat_rate_kj_kwh: float = 15650.0   # fuel LHV in ÷ net kWh out
    boiler_efficiency: float = 0.83         # used when use_heat_rate_input = False
    cycle_efficiency: float = 0.308         # turbine + generator (gross)
    heat_rate_degradation_pct: float = 0.003  # per year, from model start

    # ── Fuel (two-stream mix, mass shares) ───────────────────────
    fuel1_share: float = 0.80           # e.g. corn husk
    fuel1_moisture: float = 0.25
    fuel1_lhv_dry_mj: float = 16.5
    fuel1_price_thb_t: float = 800.0
    fuel2_share: float = 0.20           # e.g. wood chip
    fuel2_moisture: float = 0.35
    fuel2_lhv_dry_mj: float = 18.5
    fuel2_price_thb_t: float = 1200.0
    fuel_transport_thb_t: float = 0.0
    fuel_price_esc: float = 0.02
    ash_pct_of_fuel: float = 0.05
    ash_disposal_thb_t: float = 300.0

    # ── Revenue ─────────────────────────────────────────────────
    fit_base: float = 4.24
    fit_premium: float = 0.30
    premium_years: int = 8
    cpi_escalation: float = 0.0
    cpi_linked_fraction: float = 0.0
    tariff_base_year: int = 0           # year fit_base refers to (0 = model start year)
    enable_carbon: bool = True
    grid_ef_tco2_mwh: float = 0.50      # verify against current TGO factor
    carbon_price: float = 100.0         # ฿/tCO2e
    carbon_share_to_project: float = 1.0

    # ── CAPEX (greenfield only) ─────────────────────────────────
    epc_cost: float = 650.0             # MB
    owner_cost_pct: float = 0.08
    contingency_pct: float = 0.05
    idc_pct: float = 0.05
    construction_years: int = 2
    use_idc_drawdown: bool = True
    wc_pct_revenue_yr1: float = 0.16
    dsra_months: float = 6.0
    decommissioning_pct: float = 0.02

    # ── OPEX ────────────────────────────────────────────────────
    om_fixed_mb: float = 20.0           # O&M contract fee, MB/yr
    om_escalation: float = 0.03
    maint_var_thb_kwh: float = 0.25     # routine maintenance & spares
    overhaul_cost_mb: float = 15.0      # added in overhaul years
    water_chem_thb_kwh: float = 0.05
    pdf_thb_kwh: float = 0.01           # power development fund – verify rate
    insured_value_mb: float = 1000.0
    insurance_pct: float = 0.004
    sga_my: float = 12.0
    sga_esc: float = 0.03

    # ── Project finance ─────────────────────────────────────────
    debt_pct: float = 0.70
    interest_rate: float = 0.055
    debt_tenor: int = 12
    discount_rate: float = 0.0625
    tax_rate: float = 0.20
    depreciation_years: int = 20
    nol_carryforward_years: int = 5
    boi_full_years: int = 8
    boi_partial_years: int = 5
    boi_partial_rate: float = 0.10

    # ── WACC ────────────────────────────────────────────────────
    rf: float = 0.0205
    beta_unlevered: float = 0.50
    mrp: float = 0.085
    terminal_value: float = 0.0


# ════════════════════════════════════════════════════════════════════════
# █  TECHNICAL  █
# ════════════════════════════════════════════════════════════════════════
def lhv_as_received_mj(lhv_dry_mj: float, moisture: float) -> float:
    """LHV_ar ≈ LHV_dry × (1 − M) − 2.44 × M   (MJ/kg; 2.44 = latent heat of water)."""
    return max(lhv_dry_mj * (1 - moisture) - 2.44 * moisture, 0.0)


def fuel_mix(p: BiomassInputs) -> dict:
    s1, s2 = p.fuel1_share, p.fuel2_share
    tot = s1 + s2 if (s1 + s2) > 0 else 1.0
    s1, s2 = s1 / tot, s2 / tot
    l1 = lhv_as_received_mj(p.fuel1_lhv_dry_mj, p.fuel1_moisture)
    l2 = lhv_as_received_mj(p.fuel2_lhv_dry_mj, p.fuel2_moisture)
    lhv = s1 * l1 + s2 * l2
    price = s1 * p.fuel1_price_thb_t + s2 * p.fuel2_price_thb_t + p.fuel_transport_thb_t
    return {"share1": s1, "share2": s2, "lhv1_mj": l1, "lhv2_mj": l2,
            "lhv_mj_per_kg": lhv, "lhv_kcal_per_kg": lhv / 4.184e-3,
            "price_thb_t": price,
            "moisture_mix": s1 * p.fuel1_moisture + s2 * p.fuel2_moisture}


def base_heat_rate(p: BiomassInputs) -> float:
    """Net heat rate kJ/kWh at model start."""
    if p.use_heat_rate_input and p.net_heat_rate_kj_kwh > 0:
        return p.net_heat_rate_kj_kwh
    eta_net = p.boiler_efficiency * p.cycle_efficiency * (1 - p.parasitic_load_pct)
    return 3600.0 / eta_net if eta_net > 0 else 0.0


def mw_export(p: BiomassInputs) -> float:
    """Exportable MW = min(gross × (1 − parasitic), contract cap)."""
    return min(p.mw_gross * (1 - p.parasitic_load_pct), p.contract_mw)


def _life(p: BiomassInputs) -> int:
    if p.brownfield_mode:
        return max(p.ppa_end_year - p.valuation_year + 1, 1)
    return p.project_life


def _start_year(p: BiomassInputs) -> int:
    return p.valuation_year if p.brownfield_mode else p.cod_year


def _year_fraction(p: BiomassInputs, y: int) -> float:
    return p.last_year_fraction if (y == _life(p) - 1) else 1.0


def _is_overhaul_year(p: BiomassInputs, cal_year: int) -> bool:
    age = cal_year - p.cod_year + 1          # 1 = first operating year
    return (p.overhaul_interval_years > 0 and age > 0
            and age % p.overhaul_interval_years == 0)


def availability_year(p: BiomassInputs, cal_year: int) -> float:
    af = p.availability
    if _is_overhaul_year(p, cal_year):
        af -= p.overhaul_extra_outage_days / 365.0
    return max(af, 0.0)


def net_mwh_year(p: BiomassInputs, y: int) -> float:
    cal = _start_year(p) + y
    return (mw_export(p) * HOURS_YR * availability_year(p, cal)
            * p.load_factor * _year_fraction(p, y))


def heat_rate_year(p: BiomassInputs, y: int) -> float:
    return base_heat_rate(p) * (1 + p.heat_rate_degradation_pct) ** y


def fuel_tons_year(p: BiomassInputs, y: int, mix: dict | None = None) -> float:
    mix = mix or fuel_mix(p)
    lhv_kj_kg = mix["lhv_mj_per_kg"] * 1000
    if lhv_kj_kg <= 0:
        return 0.0
    return net_mwh_year(p, y) * 1000 * heat_rate_year(p, y) / lhv_kj_kg / 1000


def compute_raw_material(p: BiomassInputs) -> dict:
    mix = fuel_mix(p)
    hr = base_heat_rate(p)
    mwh0 = net_mwh_year(p, 0)
    t0 = fuel_tons_year(p, 0, mix)
    op_days = HOURS_YR / 24 * p.availability
    return {
        "mode": "brownfield" if p.brownfield_mode else "greenfield",
        "fuel_mix": mix,
        "lhv_mj_per_kg": mix["lhv_mj_per_kg"],
        "lhv_kcal_per_kg": mix["lhv_kcal_per_kg"],
        "net_heat_rate_kj_kwh": hr,
        "net_efficiency": 3600.0 / hr if hr > 0 else 0.0,
        "sfc_kg_per_kwh": (t0 * 1000) / (mwh0 * 1000) if mwh0 > 0 else 0.0,
        "mw_gross": p.mw_gross,
        "mw_export": mw_export(p),
        "spare_mw_above_contract": max(p.mw_gross * (1 - p.parasitic_load_pct)
                                       - p.contract_mw, 0.0),
        "fuel_ton_per_yr": t0,
        "fuel_ton_per_day": t0 / op_days if op_days > 0 else 0.0,
        "ash_ton_yr": t0 * p.ash_pct_of_fuel,
        "net_mwh_yr1": mwh0,
        "capacity_factor_yr1": mwh0 / (p.contract_mw * HOURS_YR) if p.contract_mw else 0.0,
    }


# ════════════════════════════════════════════════════════════════════════
# █  REVENUE / OPEX  █
# ════════════════════════════════════════════════════════════════════════
def _yearly_revenue(p: BiomassInputs, y: int) -> dict:
    mwh = net_mwh_year(p, y)
    cal = _start_year(p) + y
    ppa_idx = cal - p.cod_year                      # years since COD → premium window
    cpi_idx = cal - (p.tariff_base_year or _start_year(p))
    rate = p.fit_base + (p.fit_premium if 0 <= ppa_idx < p.premium_years else 0.0)
    if p.cpi_escalation and p.cpi_linked_fraction:
        rate = (rate * (1 - p.cpi_linked_fraction)
                + rate * p.cpi_linked_fraction * (1 + p.cpi_escalation) ** max(cpi_idx, 0))
    fit_rev = mwh * 1000 * rate / 1e6
    tco2 = mwh * p.grid_ef_tco2_mwh if p.enable_carbon else 0.0
    carbon = tco2 * p.carbon_price * p.carbon_share_to_project / 1e6
    return {"net_mwh": mwh, "rate": rate, "fit_rev": fit_rev,
            "carbon_rev": carbon, "tco2": tco2, "revenue": fit_rev + carbon}


def _yearly_opex(p: BiomassInputs, y: int, mix: dict) -> dict:
    frac = _year_fraction(p, y)
    mwh = net_mwh_year(p, y)
    kwh = mwh * 1000
    esc = (1 + p.om_escalation) ** y
    fuel_t = fuel_tons_year(p, y, mix)
    fuel = fuel_t * mix["price_thb_t"] * (1 + p.fuel_price_esc) ** y / 1e6
    om_fixed = p.om_fixed_mb * esc * frac
    maint = kwh * p.maint_var_thb_kwh * esc / 1e6
    overhaul = (p.overhaul_cost_mb * esc
                if _is_overhaul_year(p, _start_year(p) + y) else 0.0)
    ash = fuel_t * p.ash_pct_of_fuel * p.ash_disposal_thb_t * esc / 1e6
    water = kwh * p.water_chem_thb_kwh * esc / 1e6
    pdf = kwh * p.pdf_thb_kwh / 1e6
    insurance = p.insured_value_mb * p.insurance_pct * esc * frac
    sga = p.sga_my * (1 + p.sga_esc) ** y * frac
    cash_cogs = fuel + om_fixed + maint + overhaul + ash + water + pdf + insurance
    return {"fuel": fuel, "fuel_t": fuel_t, "om_fixed": om_fixed, "maint": maint,
            "overhaul": overhaul, "ash": ash, "water_chem": water, "pdf": pdf,
            "insurance": insurance, "sga": sga,
            "cash_cogs": cash_cogs, "total": cash_cogs + sga}


# ════════════════════════════════════════════════════════════════════════
# █  MAIN ENTRY POINT  █
# ════════════════════════════════════════════════════════════════════════
def _capex(p: BiomassInputs) -> dict:
    mwx = mw_export(p)
    if p.brownfield_mode:
        ev = max(p.entry_value_mb, 0.0)
        debt = p.opening_debt_mb
        return {"epc": 0.0, "owner_cost": 0.0, "contingency": 0.0, "idc": 0.0,
                "working_capital": 0.0, "dsra": 0.0,
                "total_proj_capex": ev, "total_capex": ev,
                "equity": max(ev - debt, 0.0) if ev > 0 else 0.0,
                "debt": debt, "decom_cost": 0.0,
                "capex_per_mw_installed": ev / p.mw_gross if p.mw_gross and ev else 0.0,
                "capex_per_mw_contracted": ev / mwx if mwx and ev else 0.0}
    mix = fuel_mix(p)
    rev1 = _yearly_revenue(p, 0)["revenue"]
    base = capex_breakdown(p.epc_cost, p.owner_cost_pct, p.contingency_pct,
                           p.idc_pct, p.debt_pct)
    ds1 = base["debt"] * (p.interest_rate + 1 / max(p.debt_tenor, 1))
    return capex_breakdown(
        p.epc_cost, p.owner_cost_pct, p.contingency_pct, p.idc_pct, p.debt_pct,
        p.mw_gross, mwx, interest_rate=p.interest_rate,
        construction_years=p.construction_years,
        use_idc_drawdown=p.use_idc_drawdown,
        wc_pct_revenue_yr1=p.wc_pct_revenue_yr1, revenue_yr1_mb=rev1,
        dsra_months=p.dsra_months, debt_service_yr1_mb=ds1,
        decommissioning_pct=p.decommissioning_pct)


def run_model(p: BiomassInputs) -> dict:
    p = copy.deepcopy(p)
    life = _life(p)
    start = _start_year(p)
    mix = fuel_mix(p)
    raw = compute_raw_material(p)
    cx = _capex(p)

    if p.brownfield_mode:
        ds = debt_schedule_annuity(p.opening_debt_mb, p.interest_rate,
                                   p.remaining_debt_tenor, life)
        dep_years = max(p.remaining_dep_years, 1)
        dep_annual = p.remaining_book_value_mb / dep_years if p.remaining_dep_years else 0.0
        boi_offset = start - p.cod_year
    else:
        ds = debt_schedule_annuity(cx["debt"], p.interest_rate, p.debt_tenor, life)
        dep_years = max(1, min(int(p.depreciation_years), life))
        dep_annual = cx["total_proj_capex"] / dep_years
        boi_offset = 0
    tlcf = TaxLossCarryForward(p.nol_carryforward_years)

    t0_equity = cx["equity"]
    t0_project = cx["total_capex"]
    fcfe, fcff = [-t0_equity], [-t0_project]
    cum_e, cum_p = -t0_equity, -t0_project
    cum_fcfe, cum_fcff, rows, opex_list, mwh_list = [], [], [], [], []

    for y in range(life):
        rev = _yearly_revenue(p, y)
        op = _yearly_opex(p, y, mix)
        revenue, opex = rev["revenue"], op["total"]
        dep = dep_annual if y < dep_years else 0.0
        ebitda = revenue - opex
        ebit = ebitda - dep
        interest, principal, balance = ds[y]
        ebt = ebit - interest
        tax_eff = boi_tax_rate(y + boi_offset, p.boi_full_years, p.boi_partial_years,
                               p.boi_partial_rate, p.tax_rate)
        tax_amt = tlcf.tax(ebt, tax_eff)
        npat = ebt - tax_amt
        ocf = npat + dep
        cfads = npat + dep + interest
        dscr = dscr_year(cfads, interest, principal)
        fcfe_y = ocf - principal
        fcff_y = ebit * (1 - tax_eff) + dep
        fcfe.append(fcfe_y); fcff.append(fcff_y)
        cum_e += fcfe_y; cum_p += fcff_y
        cum_fcfe.append(cum_e); cum_fcff.append(cum_p)
        opex_list.append(opex); mwh_list.append(rev["net_mwh"])
        cal = start + y
        rows.append({
            "year": y + 1, "calendar_year": cal,
            "fit_rev": rev["fit_rev"], "tip_rev": 0.0, "rdf_rev": 0.0,
            "carbon_rev": rev["carbon_rev"], "revenue": revenue,
            "rev_breakdown": {"FiT": rev["fit_rev"], "Carbon": rev["carbon_rev"]},
            "net_mwh": rev["net_mwh"], "tariff": rev["rate"],
            "availability": availability_year(p, cal),
            "heat_rate": heat_rate_year(p, y), "fuel_t": op["fuel_t"],
            "opex_om": op["om_fixed"] + op["maint"] + op["overhaul"],
            "opex_feedstock": op["fuel"], "opex_ash": op["ash"],
            "opex_bottom_ash": op["ash"], "opex_fly_ash": 0.0,
            "opex_flue": 0.0, "opex_aux": op["water_chem"],
            "opex_sga": op["sga"], "opex_insurance": op["insurance"],
            "opex_pdf": op["pdf"], "opex_boiler_tube": 0.0,
            "opex": opex, "opex_breakdown": op,
            "cogs_incl_dep": op["cash_cogs"] + dep,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit,
            "interest": interest, "debt_balance": balance, "ebt": ebt,
            "tax_eff": tax_eff, "tax": tax_amt, "npat": npat, "ocf": ocf,
            "principal_repay": principal, "cfads": cfads, "dscr": dscr,
            "fcfe": fcfe_y, "fcff": fcff_y,
        })

    if not p.brownfield_mode and len(fcfe) > 1:
        rec = working_capital_recovery(cx["working_capital"], cx["dsra"])
        fcfe[-1] += rec - cx["decom_cost"]; fcff[-1] += rec - cx["decom_cost"]
        cum_fcfe[-1] += rec - cx["decom_cost"]; cum_fcff[-1] += rec - cx["decom_cost"]
    if p.terminal_value > 0:
        fcfe[-1] += p.terminal_value; fcff[-1] += p.terminal_value

    wacc = wacc_capm(p.rf, p.mrp, p.beta_unlevered, p.debt_pct, p.tax_rate,
                     p.interest_rate)
    has_entry = (not p.brownfield_mode) or p.entry_value_mb > 0
    eirr = irr_brentq(fcfe) if has_entry else None
    pirr = irr_brentq(fcff) if has_entry else None
    debt_dscr = [r["dscr"] for r in rows
                 if r["principal_repay"] > 0 and r["dscr"] < float("inf")]
    kpis = {
        "project_irr": pirr, "equity_irr": eirr,
        "project_npv": npv_calc(fcff, p.discount_rate),
        "equity_npv": npv_calc(fcfe, wacc["ke"]),
        "payback_project": payback_period(cum_fcff) if has_entry else None,
        "payback_equity": payback_period(cum_fcfe) if has_entry else None,
        "dscr_min": min(debt_dscr) if debt_dscr else None,
        "dscr_avg": sum(debt_dscr) / len(debt_dscr) if debt_dscr else None,
        "lcoe_thb_per_kwh": lcoe_thb_per_kwh(t0_project, opex_list, mwh_list,
                                             p.discount_rate),
        "bcr": bcr_calc([r["revenue"] for r in rows], [r["opex"] for r in rows],
                        p.discount_rate, capex_at_t0=t0_project),
        "wacc": wacc["wacc"], "ke": wacc["ke"],
    }
    if p.brownfield_mode:
        # value of remaining cash flows, excluding any entry price
        kpis["enterprise_value_remaining"] = npv_calc([0.0] + fcff[1:], p.discount_rate)
        kpis["equity_value_remaining"] = npv_calc([0.0] + fcfe[1:], wacc["ke"])

    return build_result(
        engine_type="biomass", inputs=asdict(p), raw_material=raw,
        generation={
            "mwh_yr": rows[0]["net_mwh"] if rows else 0.0,
            "mw_gross": p.mw_gross, "mw_net": mw_export(p),
            "parasitic_pct": p.parasitic_load_pct,
            "boiler_eff": p.boiler_efficiency, "turbine_eff": p.cycle_efficiency,
            "plant_eff": raw["net_efficiency"],
            "net_heat_rate_kj_kwh": raw["net_heat_rate_kj_kwh"],
            "sfc_kg_per_kwh": raw["sfc_kg_per_kwh"],
            "feedstock_ton_yr": raw["fuel_ton_per_yr"],
            "feedstock_ton_day": raw["fuel_ton_per_day"],
            "ash_ton_yr": raw["ash_ton_yr"],
            "lhv_kcal_per_kg": raw["lhv_kcal_per_kg"],
            "lhv_mj_per_kg": raw["lhv_mj_per_kg"],
            "capacity_factor": raw["capacity_factor_yr1"],
        },
        capex=cx, wacc=wacc, rows=rows, kpis=kpis, fcfe=fcfe, fcff=fcff,
        cum_fcfe=cum_fcfe, cum_fcff=cum_fcff,
        carbon={"rev_mb_yr": rows[0]["carbon_rev"] if rows else 0.0,
                "tco2_yr": rows[0]["net_mwh"] * p.grid_ef_tco2_mwh
                if (rows and p.enable_carbon) else 0.0},
        extras={"analysis_mode": raw["mode"], "start_year": start, "life": life},
    )


# ════════════════════════════════════════════════════════════════════════
# █  PRESETS  █
# ════════════════════════════════════════════════════════════════════════
def default_preset() -> BiomassInputs:
    """9.9 MW biomass VSPP as a GREENFIELD base case.

    Representative Thai biomass VSPP: 9.9 MW installed, 8.0 MW contract, net heat
    rate 15,650 kJ/kWh, corn-husk + wood mix, FiT ~4.67 ฿/kWh + a 0.30 ฿/kWh
    biomass VSPP adder for the first 8 years (the incentive a NEW project
    receives), with 1% CPI on 56% of tariff, plus T-VER. Modelled as a brand-new
    project (own CAPEX) so it produces IRR / NPV / DSCR / LCOE comparable to the
    other engines. For the operating-asset (remaining-PPA) valuation of an
    existing plant, use PRESETS["brownfield"] instead.
    """
    return BiomassInputs(
        project_name="Biomass VSPP 9.9 MW",
        cod_year=2027, project_life=20, brownfield_mode=False,
        mw_gross=9.9, contract_mw=8.0, parasitic_load_pct=0.10,
        availability=0.90, load_factor=0.98,
        overhaul_interval_years=4, overhaul_extra_outage_days=14,
        use_heat_rate_input=True, net_heat_rate_kj_kwh=15650.0,
        heat_rate_degradation_pct=0.003,
        fuel1_share=0.80, fuel1_moisture=0.25, fuel1_lhv_dry_mj=16.5, fuel1_price_thb_t=1500.0,
        fuel2_share=0.20, fuel2_moisture=0.35, fuel2_lhv_dry_mj=18.5, fuel2_price_thb_t=2200.0,
        fuel_price_esc=0.01, ash_pct_of_fuel=0.05, ash_disposal_thb_t=300.0,
        fit_base=4.67, fit_premium=0.30, premium_years=8,   # biomass VSPP FiT adder
        cpi_escalation=0.01, cpi_linked_fraction=0.56, tariff_base_year=2027,
        enable_carbon=True, grid_ef_tco2_mwh=0.50, carbon_price=330.0, carbon_share_to_project=1.0,
        epc_cost=650.0, owner_cost_pct=0.08, contingency_pct=0.05, idc_pct=0.05,
        construction_years=2, use_idc_drawdown=True, wc_pct_revenue_yr1=0.16,
        dsra_months=6.0, decommissioning_pct=0.02,
        om_fixed_mb=20.0, om_escalation=0.03, maint_var_thb_kwh=0.25, overhaul_cost_mb=15.0,
        water_chem_thb_kwh=0.05, pdf_thb_kwh=0.01, insured_value_mb=1000.0, insurance_pct=0.004,
        sga_my=20.0, sga_esc=0.03,
        debt_pct=0.70, interest_rate=0.055, debt_tenor=12, discount_rate=0.0625,
        tax_rate=0.20, depreciation_years=20, nol_carryforward_years=5,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
        rf=0.0205, beta_unlevered=0.50, mrp=0.085,
    )


def brownfield_preset() -> BiomassInputs:
    """A 9.9 MW biomass VSPP as an operating asset valued from 2026.

    Example operating plant: 9.9 MW installed, 8.0 MW contract, COD 2019,
    20-yr PPA, effective FiT ~4.67 ฿/kWh, corn husk + wood fuel. Values the
    remaining PPA (2026–2039) — enterprise / equity value, not a new-build IRR.
    """
    return BiomassInputs(
        project_name="Biomass VSPP — operating asset (brownfield 2026–2039)",
        cod_year=2019, brownfield_mode=True,
        valuation_year=2026, ppa_end_year=2039, last_year_fraction=0.6,
        entry_value_mb=0.0, opening_debt_mb=400.0, remaining_debt_tenor=7,
        remaining_book_value_mb=585.0, remaining_dep_years=13,
        mw_gross=9.9, contract_mw=8.0, parasitic_load_pct=0.10,
        availability=0.90, load_factor=0.98,
        overhaul_interval_years=4, overhaul_extra_outage_days=14,
        use_heat_rate_input=True, net_heat_rate_kj_kwh=15650.0,
        heat_rate_degradation_pct=0.003,
        fuel1_share=0.80, fuel1_moisture=0.25, fuel1_lhv_dry_mj=16.5,
        fuel1_price_thb_t=1500.0,
        fuel2_share=0.20, fuel2_moisture=0.35, fuel2_lhv_dry_mj=18.5,
        fuel2_price_thb_t=2200.0,
        fuel_price_esc=0.02,
        fit_base=4.67, fit_premium=0.0, premium_years=0,
        cpi_escalation=0.01, cpi_linked_fraction=0.56, tariff_base_year=2025,
        enable_carbon=True, grid_ef_tco2_mwh=0.50, carbon_price=330.0,
        om_fixed_mb=20.0, maint_var_thb_kwh=0.25, overhaul_cost_mb=15.0,
        water_chem_thb_kwh=0.05, pdf_thb_kwh=0.01,
        insured_value_mb=1000.0, insurance_pct=0.004,
        sga_my=29.4, sga_esc=0.03,
        interest_rate=0.055, discount_rate=0.0625, tax_rate=0.20,
        boi_full_years=8, boi_partial_years=5, boi_partial_rate=0.10,
    )


PRESETS = {"greenfield": default_preset, "brownfield": brownfield_preset}


# ════════════════════════════════════════════════════════════════════════
# █  INPUT SECTIONS (for GUI)  █
# ════════════════════════════════════════════════════════════════════════
INPUT_SECTIONS = [
    ("Plant & Mode", [
        ("project_name",        "Project Name",            "str",   ""),
        ("cod_year",            "COD Year",                "int",   "e.g. 2019"),
        ("project_life",        "Project Life (greenfield)","int",  "yr"),
        ("brownfield_mode",     "Operating-asset mode",    "bool",  "ON = value remaining PPA"),
        ("valuation_year",      "Valuation start year",    "int",   "brownfield"),
        ("ppa_end_year",        "PPA end year",            "int",   "brownfield"),
        ("last_year_fraction",  "Final-year fraction",     "pct",   "% of last year under PPA"),
        ("mw_gross",            "MW Gross (installed)",    "float", "MW"),
        ("contract_mw",         "Contract MW (export cap)","float", "MW"),
        ("parasitic_load_pct",  "Parasitic Load",          "pct",   "% of gross (8-12%)"),
        ("availability",        "Availability (AF)",       "pct",   "%"),
        ("load_factor",         "Load factor when running","pct",   "%"),
        ("overhaul_interval_years","Overhaul cycle",       "int",   "yr from COD"),
        ("overhaul_extra_outage_days","Overhaul extra outage","int","days"),
    ]),
    ("Heat Rate & Efficiency", [
        ("use_heat_rate_input", "Use net heat rate input", "bool",  "OFF = boiler × cycle"),
        ("net_heat_rate_kj_kwh","Net Heat Rate",           "float", "kJ/kWh (14,500-17,000)"),
        ("boiler_efficiency",   "Boiler Efficiency",       "pct",   "% LHV (78-85%)"),
        ("cycle_efficiency",    "Cycle + Gen Efficiency",  "pct",   "% (28-32%)"),
        ("heat_rate_degradation_pct","HR degradation",     "pct",   "%/yr"),
    ]),
    ("Fuel", [
        ("fuel1_share",         "Fuel 1 share (e.g. corn husk)","pct","% mass"),
        ("fuel1_moisture",      "Fuel 1 moisture",         "pct",   "% as received"),
        ("fuel1_lhv_dry_mj",    "Fuel 1 LHV dry",          "float", "MJ/kg"),
        ("fuel1_price_thb_t",   "Fuel 1 price",            "float", "฿/t"),
        ("fuel2_share",         "Fuel 2 share (e.g. wood)","pct",   "% mass"),
        ("fuel2_moisture",      "Fuel 2 moisture",         "pct",   "% as received"),
        ("fuel2_lhv_dry_mj",    "Fuel 2 LHV dry",          "float", "MJ/kg"),
        ("fuel2_price_thb_t",   "Fuel 2 price",            "float", "฿/t"),
        ("fuel_transport_thb_t","Transport adder",         "float", "฿/t"),
        ("fuel_price_esc",      "Fuel price escalation",   "pct",   "%/yr"),
        ("ash_pct_of_fuel",     "Ash",                     "pct",   "% of fuel"),
        ("ash_disposal_thb_t",  "Ash disposal",            "float", "฿/t"),
    ]),
    ("Revenue", [
        ("fit_base",            "FiT / tariff",            "float", "฿/kWh"),
        ("fit_premium",         "FiT premium",             "float", "฿/kWh"),
        ("premium_years",       "Premium years",           "int",   "yr"),
        ("cpi_escalation",      "CPI escalation",          "pct",   "%/yr"),
        ("cpi_linked_fraction", "CPI-linked fraction",     "pct",   "% of tariff"),
        ("tariff_base_year",    "Tariff base year",        "int",   "0 = start year"),
        ("enable_carbon",       "T-VER carbon credit",     "bool",  ""),
        ("grid_ef_tco2_mwh",    "Grid emission factor",    "float", "tCO₂/MWh"),
        ("carbon_price",        "Carbon price",            "float", "฿/tCO₂"),
    ]),
    ("CAPEX (greenfield) / Entry (brownfield)", [
        ("epc_cost",            "EPC Cost",                "float", "MB"),
        ("owner_cost_pct",      "Owner's Cost",            "pct",   "% EPC"),
        ("contingency_pct",     "Contingency",             "pct",   "%"),
        ("construction_years",  "Construction",            "int",   "yr"),
        ("use_idc_drawdown",    "Use IDC drawdown",        "bool",  ""),
        ("wc_pct_revenue_yr1",  "Working capital",         "pct",   "% Y1 revenue"),
        ("dsra_months",         "DSRA",                    "float", "months"),
        ("entry_value_mb",      "Entry value (brownfield)","float", "MB, 0 = NPV only"),
        ("opening_debt_mb",     "Opening debt (brownfield)","float","MB"),
        ("remaining_debt_tenor","Remaining tenor",         "int",   "yr"),
        ("remaining_book_value_mb","Remaining book value", "float", "MB"),
        ("remaining_dep_years", "Remaining dep. years",    "int",   "yr"),
    ]),
    ("OPEX", [
        ("om_fixed_mb",         "O&M contract fee",        "float", "MB/yr"),
        ("om_escalation",       "O&M escalation",          "pct",   "%/yr"),
        ("maint_var_thb_kwh",   "Maintenance (variable)",  "float", "฿/kWh"),
        ("overhaul_cost_mb",    "Overhaul cost",           "float", "MB per event"),
        ("water_chem_thb_kwh",  "Water & chemicals",       "float", "฿/kWh"),
        ("pdf_thb_kwh",         "Power Dev. Fund",         "float", "฿/kWh"),
        ("insured_value_mb",    "Insured value",           "float", "MB"),
        ("insurance_pct",       "Insurance rate",          "pct",   "%/yr"),
        ("sga_my",              "SG&A (Y1)",               "float", "MB/yr"),
        ("sga_esc",             "SG&A escalation",         "pct",   "%/yr"),
    ]),
    ("Project Finance & BOI", [
        ("debt_pct",            "Debt ratio (greenfield)", "pct",   "%"),
        ("interest_rate",       "Interest rate",           "pct",   "% p.a."),
        ("debt_tenor",          "Debt tenor (greenfield)", "int",   "yr"),
        ("discount_rate",       "Discount rate",           "pct",   "%"),
        ("tax_rate",            "Tax rate (CIT)",          "pct",   "%"),
        ("depreciation_years",  "Depreciation life",       "int",   "yr"),
        ("nol_carryforward_years","Loss carry-fwd",        "int",   "yr"),
        ("boi_full_years",      "BOI 0% years (from COD)", "int",   "yr"),
        ("boi_partial_years",   "BOI partial years",       "int",   "yr"),
        ("boi_partial_rate",    "BOI partial rate",        "pct",   "%"),
        ("rf",                  "Risk-free rate",          "pct",   "%"),
        ("beta_unlevered",      "β unlevered",             "float", ""),
        ("mrp",                 "Market risk premium",     "pct",   "%"),
        ("terminal_value",      "Terminal value",          "float", "MB"),
    ]),
]


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    for name, fn in PRESETS.items():
        p = fn(); res = run_model(p); k = res["kpis"]; g = res["generation"]
        print(f"━━━ {p.project_name} ━━━")
        print(f"  Export MW / HR    : {g['mw_net']:.2f} MW / {g['net_heat_rate_kj_kwh']:,.0f} kJ/kWh")
        print(f"  Net MWh (yr1)     : {g['mwh_yr']:,.0f}  CF {g['capacity_factor']*100:.1f}%")
        print(f"  Fuel              : {g['feedstock_ton_yr']:,.0f} t/yr  LHV {g['lhv_mj_per_kg']:.2f} MJ/kg")
        if p.brownfield_mode:
            print(f"  EV remaining      : {k['enterprise_value_remaining']:,.1f} MB")
            print(f"  Equity value rem. : {k['equity_value_remaining']:,.1f} MB")
        else:
            print(f"  Project / Equity IRR: {(k['project_irr'] or 0)*100:.2f}% / {(k['equity_irr'] or 0)*100:.2f}%")
            print(f"  LCOE              : {k['lcoe_thb_per_kwh']:.2f} ฿/kWh")
