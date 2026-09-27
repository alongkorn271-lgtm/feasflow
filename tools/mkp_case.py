"""
tools/mkp_case.py
=================
Mae Krating Power (MKP) case study with the biomass engine.

  1. Historical back-check 2021–2025 (BE 2564–2568) from the public P&L
  2. Calibrate the unknowns on 2025 (fuel price, carbon price, debt)
  3. Forward valuation 2026–2039 (remaining PPA) in brownfield mode
  4. "What is OE work worth?" – ΔEV / ΔEquity for availability, heat rate,
     fuel price, maintenance, moisture; plus BOI-assumption check

Run:   python -m tools.mkp_case            (from repo root)
Out:   prints a summary and writes tools/output/mkp_report.md + mkp_yearly.csv

Every number not in HIST is an ASSUMPTION. Change ASSUMPTIONS and re-run.
"""
from __future__ import annotations

import copy
import csv
import os
import sys
import io
from dataclasses import replace

from engines import biomass as bm

# ─────────────────────────────────────────────────────────────────────
# Public data: MKP income statement, MB (million THB). AD year = BE − 543
# ─────────────────────────────────────────────────────────────────────
HIST = {
    2021: dict(rev_main=282.86, other=0.48,  cogs=214.35, sga=18.99, interest=31.91, net=18.04),
    2022: dict(rev_main=283.25, other=1.79,  cogs=221.93, sga=24.82, interest=36.20, net=2.08),
    2023: dict(rev_main=269.61, other=3.29,  cogs=234.04, sga=32.48, interest=29.67, net=-23.29),
    2024: dict(rev_main=292.91, other=9.87,  cogs=236.10, sga=25.65, interest=28.14, net=12.88),
    2025: dict(rev_main=294.41, other=10.63, cogs=239.41, sga=29.44, interest=24.20, net=11.96),
}
# From SKE Opportunity Day Q3/2025: Q2 16.61 GWh / 77.5 MB, Q3 14.40 GWh / 67.3 MB
EFFECTIVE_TARIFF = 4.67      # ฿/kWh
CONTRACT_MW = 8.0

# ─────────────────────────────────────────────────────────────────────
# Assumptions (edit here)
# ─────────────────────────────────────────────────────────────────────
ASSUMPTIONS = dict(
    depreciation_mb=45.0,            # inside COGS; not disclosed in the P&L we have
    load_factor=0.98,                # MW/contract while running (Q2–Q3/2025: 97–99%)
    forward_availability=0.90,       # 2026+ base case (≈ 5-yr average)
    interest_rate=0.055,
    remaining_debt_tenor=10,         # years; not public
    carbon_all_other_income=True,    # treat "other income" as T-VER revenue
    # forward escalation (2026+)
    tariff_cpi=0.01,                 # core-inflation link on FiT variable part
    tariff_cpi_linked_fraction=0.56, # ≈ FiTv / FiT for >3 MW biomass (2.39 / 4.24)
    fuel_price_esc=0.015,
    om_escalation=0.025,
    sga_esc=0.02,
)

CALIB_YEAR = 2025


def _units_gwh(year: int) -> float:
    return HIST[year]["rev_main"] / EFFECTIVE_TARIFF


def _one_year(p: bm.BiomassInputs, year: int) -> bm.BiomassInputs:
    """Brownfield single-year view of calendar `year` (for calibration)."""
    q = copy.deepcopy(p)
    q.valuation_year = year
    q.ppa_end_year = year
    q.last_year_fraction = 1.0
    q.heat_rate_degradation_pct = 0.0
    q.fuel_price_esc = 0.0
    q.om_escalation = 0.0
    q.sga_esc = 0.0
    return q


def calibrate(dep_mb: float | None = None, verbose: bool = True) -> tuple[bm.BiomassInputs, dict]:
    A = ASSUMPTIONS
    dep = A["depreciation_mb"] if dep_mb is None else dep_mb
    h = HIST[CALIB_YEAR]
    p = bm.mkp_brownfield_preset()
    p.load_factor = A["load_factor"]
    p.interest_rate = A["interest_rate"]
    p.sga_my = h["sga"]

    # 1) availability that reproduces the sold energy
    units_mwh = _units_gwh(CALIB_YEAR) * 1000
    q = _one_year(p, CALIB_YEAR)
    base_mwh_per_af = bm.mw_export(q) * bm.HOURS_YR * q.load_factor
    af = units_mwh / base_mwh_per_af
    if bm._is_overhaul_year(q, CALIB_YEAR):
        af += q.overhaul_extra_outage_days / 365.0
    p.availability = q.availability = af

    # 2) fuel price that closes COGS (COGS = cash COGS + depreciation)
    mix = bm.fuel_mix(q)
    op = bm._yearly_opex(q, 0, mix)
    nonfuel = op["cash_cogs"] - op["fuel"]
    fuel_needed = h["cogs"] - dep - nonfuel
    tons = op["fuel_t"]
    implied_price = fuel_needed * 1e6 / tons
    k = implied_price / mix["price_thb_t"] if mix["price_thb_t"] else 1.0
    p.fuel1_price_thb_t *= k
    p.fuel2_price_thb_t *= k

    # 3) carbon price that reproduces "other income"
    tco2 = units_mwh * p.grid_ef_tco2_mwh
    if A["carbon_all_other_income"] and tco2 > 0:
        p.carbon_price = h["other"] * 1e6 / tco2

    # 4) debt implied by interest (rate cuts also lower interest, so do not
    #    infer repayment from the year-on-year drop; tenor is an assumption)
    avg_debt = h["interest"] / p.interest_rate
    p.remaining_debt_tenor = A["remaining_debt_tenor"]
    annuity = p.interest_rate / (1 - (1 + p.interest_rate) ** -p.remaining_debt_tenor)
    first_principal = avg_debt * (annuity - p.interest_rate)
    p.opening_debt_mb = max(avg_debt - first_principal / 2, 0.0)

    # 5) remaining book value (straight line to PPA end)
    p.remaining_dep_years = p.ppa_end_year - p.valuation_year + 1
    p.remaining_book_value_mb = dep * p.remaining_dep_years
    p.availability = A["forward_availability"]
    p.cpi_escalation = A["tariff_cpi"]
    p.cpi_linked_fraction = A["tariff_cpi_linked_fraction"]
    p.fuel_price_esc = A["fuel_price_esc"]
    p.om_escalation = A["om_escalation"]
    p.sga_esc = A["sga_esc"]

    # reproduce the calibration year
    q2 = _one_year(copy.deepcopy(p), CALIB_YEAR)
    q2.availability = af
    q2.cpi_escalation = 0.0
    op2 = bm._yearly_opex(q2, 0, bm.fuel_mix(q2))
    rev2 = bm._yearly_revenue(q2, 0)
    model_cogs = op2["cash_cogs"] + dep
    model_net = (rev2["revenue"] - op2["total"] - dep - h["interest"])
    info = dict(
        dep=dep, af_calib=af, units_gwh=units_mwh / 1000, fuel_t=tons,
        lhv=mix["lhv_mj_per_kg"], sfc=tons / units_mwh,
        nonfuel_cash_cogs=nonfuel, fuel_cost=fuel_needed,
        fuel_share_cogs=fuel_needed / h["cogs"],
        implied_fuel_price=implied_price,
        fuel1_price=p.fuel1_price_thb_t, fuel2_price=p.fuel2_price_thb_t,
        tco2=tco2, carbon_price=p.carbon_price,
        avg_debt=avg_debt, opening_debt=p.opening_debt_mb,
        tenor=p.remaining_debt_tenor,
        model_rev=rev2["revenue"], actual_rev=h["rev_main"] + h["other"],
        model_cogs=model_cogs, actual_cogs=h["cogs"],
        model_net=model_net, actual_net=h["net"],
        op_breakdown=op2,
    )
    return p, info


def _value(p: bm.BiomassInputs) -> dict:
    r = bm.run_model(p)
    k = r["kpis"]
    return {"ev": k["enterprise_value_remaining"], "eq": k["equity_value_remaining"],
            "ebitda1": r["rows"][0]["ebitda"], "res": r}


def oe_sensitivities(p: bm.BiomassInputs) -> list[dict]:
    base = _value(p)
    cases = []

    def add(label, mutate):
        q = copy.deepcopy(p); mutate(q); v = _value(q)
        cases.append(dict(case=label, d_ev=v["ev"] - base["ev"],
                          d_eq=v["eq"] - base["eq"],
                          d_ebitda1=v["ebitda1"] - base["ebitda1"]))

    add("AF +1 pt",                 lambda q: setattr(q, "availability", q.availability + 0.01))
    add("AF +2 pt",                 lambda q: setattr(q, "availability", q.availability + 0.02))
    add("Forced outage −5 d/yr",    lambda q: setattr(q, "availability", q.availability + 5 / 365))
    add("Heat rate −1 %",           lambda q: setattr(q, "net_heat_rate_kj_kwh", q.net_heat_rate_kj_kwh * 0.99))
    add("Heat rate −3 %",           lambda q: setattr(q, "net_heat_rate_kj_kwh", q.net_heat_rate_kj_kwh * 0.97))
    def fuel(q, f):
        q.fuel1_price_thb_t *= f; q.fuel2_price_thb_t *= f
    add("Fuel price −5 %",          lambda q: fuel(q, 0.95))
    add("Fuel price +10 % (risk)",  lambda q: fuel(q, 1.10))
    def maint(q, f):
        q.maint_var_thb_kwh *= f; q.overhaul_cost_mb *= f
    add("Maintenance −10 %",        lambda q: maint(q, 0.90))
    def wet(q, d):
        q.fuel1_moisture += d; q.fuel2_moisture += d
    add("Fuel moisture +5 pt (risk)", lambda q: wet(q, 0.05))
    add("AF −3 pt (risk)",          lambda q: setattr(q, "availability", q.availability - 0.03))
    add("No BOI partial after 2027 (check)", lambda q: setattr(q, "boi_partial_rate", q.tax_rate))
    return base, cases


# ─────────────────────────────────────────────────────────────────────
def main() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)

    p, c = calibrate()
    dep_table = []
    for d in (35.0, 45.0, 55.0):
        _, ci = calibrate(d, verbose=False)
        dep_table.append((d, ci["implied_fuel_price"], ci["fuel_share_cogs"]))

    base, sens = oe_sensitivities(p)
    res = base["res"]

    L = []
    L.append("# MKP case — FeasFlow biomass engine\n")
    L.append("> Public P&L + assumptions. Not plant data. Edit `ASSUMPTIONS` and re-run.\n")
    L.append("## 1. Historical back-check (units = main revenue ÷ 4.67 ฿/kWh)\n")
    L.append("| Year (BE) | Revenue MB | Units GWh | CF vs 8 MW | COGS MB | COGS ฿/kWh | Net MB |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for y, h in HIST.items():
        g = _units_gwh(y)
        hrs = 8784 if y % 4 == 0 else 8760
        L.append(f"| {y+543} | {h['rev_main']:.1f} | {g:.1f} | {g*1000/(CONTRACT_MW*hrs):.1%} | "
                 f"{h['cogs']:.1f} | {h['cogs']/g:.2f} | {h['net']:.1f} |")
    L.append("")
    L.append(f"## 2. Calibration on {CALIB_YEAR+543}\n")
    L.append("| Item | Value | Note |\n|---|---:|---|")
    L.append(f"| Availability (AF) | {c['af_calib']:.1%} | LF {ASSUMPTIONS['load_factor']:.0%} |")
    L.append(f"| Net heat rate | {p.net_heat_rate_kj_kwh:,.0f} kJ/kWh | heat balance 45 barg case |")
    L.append(f"| Fuel LHV (mix) | {c['lhv']:.2f} MJ/kg | 80 % husk 25 % M / 20 % wood 35 % M |")
    L.append(f"| Fuel burned | {c['fuel_t']:,.0f} t | SFC {c['sfc']:.2f} kg/kWh |")
    L.append(f"| Non-fuel cash COGS | {c['nonfuel_cash_cogs']:.1f} MB | O&M, maint., ash, water, PDF, insurance |")
    L.append(f"| Depreciation (assumed) | {c['dep']:.1f} MB | |")
    L.append(f"| **Fuel cost (residual)** | **{c['fuel_cost']:.1f} MB** | {c['fuel_share_cogs']:.0%} of COGS |")
    L.append(f"| **Implied blended fuel price** | **{c['implied_fuel_price']:,.0f} ฿/t** | husk {c['fuel1_price']:,.0f} / wood {c['fuel2_price']:,.0f} |")
    L.append(f"| T-VER volume | {c['tco2']:,.0f} tCO₂e | TGO: 94,300 t / 3 yr ≈ 31,400 t/yr |")
    L.append(f"| Implied carbon price | {c['carbon_price']:,.0f} ฿/t | if all other income = T-VER |")
    L.append(f"| Avg debt 2025 / opening 2026 | {c['avg_debt']:.0f} / {c['opening_debt']:.0f} MB | interest ÷ {ASSUMPTIONS['interest_rate']:.1%}; tenor ≈ {c['tenor']} yr |")
    L.append(f"| Check: revenue model / actual | {c['model_rev']:.1f} / {c['actual_rev']:.1f} MB | |")
    L.append(f"| Check: COGS model / actual | {c['model_cogs']:.1f} / {c['actual_cogs']:.1f} MB | |")
    L.append(f"| Check: net profit model / actual | {c['model_net']:.1f} / {c['actual_net']:.1f} MB | tax 0 (BOI) |")
    L.append("\nDepreciation is the key unknown — implied fuel price by depreciation assumption:\n")
    L.append("| Depreciation MB | Implied fuel ฿/t | Fuel % of COGS |\n|---:|---:|---:|")
    for d, fp, fs in dep_table:
        L.append(f"| {d:.0f} | {fp:,.0f} | {fs:.0%} |")
    L.append("")
    k = res["kpis"]
    L.append(f"## 3. Forward valuation {p.valuation_year+543}–{p.ppa_end_year+543} (AF {p.availability:.0%})\n")
    L.append(f"- Enterprise value of remaining cash flows @ {p.discount_rate:.2%}: **{k['enterprise_value_remaining']:,.0f} MB**")
    L.append(f"- Equity value of remaining cash flows @ ke {k['ke']:.2%}: **{k['equity_value_remaining']:,.0f} MB**")
    L.append(f"- DSCR min / avg: {k['dscr_min'] or 0:.2f} / {k['dscr_avg'] or 0:.2f}\n")
    L.append("| Year (BE) | GWh | AF | Revenue | Fuel | O&M+maint | EBITDA | Interest | Tax | NPAT | FCFE |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in res["rows"]:
        L.append(f"| {r['calendar_year']+543} | {r['net_mwh']/1000:.1f} | {r['availability']:.1%} | "
                 f"{r['revenue']:.1f} | {r['opex_feedstock']:.1f} | {r['opex_om']:.1f} | "
                 f"{r['ebitda']:.1f} | {r['interest']:.1f} | {r['tax']:.1f} | {r['npat']:.1f} | {r['fcfe']:.1f} |")
    L.append("")
    L.append("## 4. What is OE work worth? (Δ vs base, MB)\n")
    L.append("| Lever | Δ EBITDA yr-1 | Δ EV (remaining PPA) | Δ Equity value |\n|---|---:|---:|---:|")
    for s in sens:
        L.append(f"| {s['case']} | {s['d_ebitda1']:+.1f} | {s['d_ev']:+.1f} | {s['d_eq']:+.1f} |")
    L.append("\n## 5. Assumptions to verify\n")
    for line in [
        "Depreciation inside COGS (drives implied fuel price) — One Report / notes",
        "Net heat rate, fuel mix, moisture, LHV — plant data",
        "O&M contract fee and structure; maintenance and overhaul budget",
        "Debt balance, rate and tenor — One Report / notes",
        "BOI certificate: exemption years and 50 % reduction period",
        "Tariff structure (FiT fixed vs variable, CPI link) and PPA end date",
        "Grid emission factor and T-VER price / share",
        "Power Development Fund rate for biomass VSPP",
    ]:
        L.append(f"- {line}")
    report = "\n".join(L)
    with open(os.path.join(out_dir, "mkp_report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(out_dir, "mkp_yearly.csv"), "w", newline="", encoding="utf-8") as f:
        cols = ["calendar_year", "net_mwh", "availability", "tariff", "heat_rate", "fuel_t",
                "revenue", "fit_rev", "carbon_rev", "opex_feedstock", "opex_om", "opex_sga",
                "opex", "ebitda", "depreciation", "interest", "tax", "npat",
                "principal_repay", "debt_balance", "dscr", "fcfe", "fcff"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in res["rows"]:
            w.writerow({kk: r[kk] for kk in cols})
    print(report)


if __name__ == "__main__":
    main()
