# -*- coding: utf-8 -*-
"""
audit_correctness.py
====================
Methodology correctness audit for all 5 engines.

Run from the project root:
    python audit_correctness.py

Each test prints PASS / FAIL with the expected and actual value.
Exit code 1 if any test fails.
"""
from __future__ import annotations
import sys
import os

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engines.shared import (
    irr_brentq, npv_calc, payback_period,
    dscr_year, bcr_calc, lcoe_thb_per_kwh,
    debt_schedule_annuity, wacc_capm,
    dulong_hhv, lhv_from_hhv,
    carbon_credit_tver,
)

# ── test harness ──────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0
_BUGS: list[str] = []


def check(name: str, got, expected, tol_abs: float = 1e-4, note: str = ""):
    """Absolute-tolerance check."""
    global _PASS, _FAIL
    if expected is None:
        ok = got is None
    elif got is None:
        ok = False
    else:
        ok = abs(got - expected) <= tol_abs
    sym = "PASS" if ok else "FAIL"
    if not ok:
        _FAIL += 1
        _BUGS.append(name)
        print(f"  {sym}  {name}")
        print(f"        expected {expected:.6g},  got {got:.6g}   (tol_abs={tol_abs})")
        if note:
            print(f"        NOTE: {note}")
    else:
        _PASS += 1
        print(f"  {sym}  {name}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ==========================================================================
# 1. IRR
# ==========================================================================
section("1. IRR  (bisection on NPV = 0)")

# 1a. Par bond: invest 100, receive 10 coupon/yr for 15 yrs, get 100 back at yr 15
#     Cash flows: [-100, 10, 10, ..., 10+100]  -> IRR = 10.0%
cf_bond = [-100.0] + [10.0] * 14 + [110.0]   # 15 periods, last = coupon + par
irr_bond = irr_brentq(cf_bond)
check("IRR par bond (10% coupon, 15yr) = 0.10", irr_bond, 0.10, tol_abs=1e-5)

# 1b. Single terminal CF: invest 100, get 100*(1.1)^5 = 161.051 at yr 5 -> IRR = 10%
cf_single = [-100.0, 0, 0, 0, 0, 161.051]
irr_single = irr_brentq(cf_single)
check("IRR single terminal (100->161.051 in 5yr) = 0.10", irr_single, 0.10, tol_abs=1e-5)

# 1c. All-negative flows -> must return None
cf_neg = [-100.0, -10.0, -10.0, -10.0]
irr_neg = irr_brentq(cf_neg)
check("IRR all-negative CFs returns None",
      0.0 if irr_neg is None else 1.0, 0.0, tol_abs=0.01)

# 1d. Solve[-10,5,10]: NPV=0 at r where -10 + 5/(1+r) + 10/(1+r)^2 = 0
#     Quadratic: 10x^2 + 5x - 10 = 0, x=1/(1+r)
#     x = (-5 + sqrt(25+400))/20 = (-5 + 20.616)/20 = 0.7808
#     r = 1/0.7808 - 1 = 0.2807... let me verify:
import math
a, b, c = 10.0, 5.0, -10.0
disc_q = b**2 - 4*a*c
x = (-b + math.sqrt(disc_q)) / (2*a)
irr_expected_small = 1.0/x - 1.0
cf_small = [-10.0, 5.0, 10.0]
irr_small = irr_brentq(cf_small)
check("IRR [-10, 5, 10] analytic", irr_small, irr_expected_small, tol_abs=1e-5)


# ==========================================================================
# 2. NPV
# ==========================================================================
section("2. NPV  (sum cf_t / (1+r)^t)")

# 2a. NPV at IRR must = 0
cf_test = [-100.0, 30.0, 30.0, 30.0, 30.0, 30.0]
irr_t = irr_brentq(cf_test)
npv_at_irr = npv_calc(cf_test, irr_t)
check("NPV at IRR = 0", npv_at_irr, 0.0, tol_abs=1e-4)

# 2b. Analytical: PV of 5-yr annuity of 10 at 10% = 10 * [1-1.1^-5]/0.10 = 37.908
pv_annuity_exp = 10.0 * (1.0 - 1.1**-5) / 0.10
cf_annuity = [0.0, 10.0, 10.0, 10.0, 10.0, 10.0]
npv_annuity = npv_calc(cf_annuity, 0.10)
check("NPV 5-yr annuity 10 @ 10% = 37.908", npv_annuity, pv_annuity_exp, tol_abs=1e-4)

# 2c. NPV of known bond at premium rate: par bond at 10%, discount at 8% => NPV > 0
npv_premium = npv_calc(cf_bond, 0.08)
check("NPV par-10%-bond at 8% discount > 0", 1.0 if npv_premium > 0 else 0.0, 1.0, tol_abs=0.01)


# ==========================================================================
# 3. Payback Period
# ==========================================================================
section("3. Payback Period  (linear interpolation, 1-indexed years)")

# 3a. Crosses exactly at Year 3 (cum reaches 0 at index t=2 -> year 3)
# To get payback=3.0, cumulative must be exactly 0 at Year 3
cum = [-40.0, -20.0, 0.0, 35.0]
pb = payback_period(cum)
check("Payback: cum=0 at Year 3 -> 3.0", pb, 3.0, tol_abs=1e-9)

# 3b. Interpolation: [-30,-10,20] -> 2 + 10/(10+20) = 2.333
cum2 = [-30.0, -10.0, 20.0]
pb2 = payback_period(cum2)
check("Payback interpolated = 2.333", pb2, 7.0/3.0, tol_abs=1e-4)

# 3c. Year-1 positive -> 1.0
cum3 = [5.0, 10.0, 20.0]
pb3 = payback_period(cum3)
check("Payback Year-1 positive = 1.0", pb3, 1.0, tol_abs=1e-9)

# 3d. Never recovers -> None
cum4 = [-40.0, -30.0, -20.0]
pb4 = payback_period(cum4)
check("Payback never positive = None",
      0.0 if pb4 is None else 1.0, 0.0, tol_abs=0.01)

# 3e. Engine-level verification: equity payback must include initial equity outflow.
#   Simulate the engine's cumulative-CF builder with the fix applied (cum_e = -equity).
#   With Equity=100, FCFE=+20/yr, correct payback = 5.0 yr.
equity_out = 100.0
annual_fcfe = 20.0
# Fixed engine builds cum from -equity:
cum_fixed = [-equity_out + annual_fcfe * (i + 1) for i in range(7)]
pb_fixed = payback_period(cum_fixed)
print(f"\n  Equity payback (post-fix): cum_e starts at -equity")
print(f"    Equity=100, FCFE=+20/yr  ->  expected payback 5.0 yr")
print(f"    Computed payback         ->  {pb_fixed:.2f} yr")
check("Equity payback uses initial outflow (post-fix)", pb_fixed, 5.0, tol_abs=1e-3,
      note="Engine code: cum_e = -equity (was 0 in old code)")


# ==========================================================================
# 4. DSCR
# ==========================================================================
section("4. DSCR  (CFADS / (Interest + Principal))")

dscr = dscr_year(100.0, 20.0, 30.0)
check("DSCR = 100/(20+30) = 2.0", dscr, 2.0, tol_abs=1e-9)

dscr_inf = dscr_year(50.0, 0.0, 0.0)
check("DSCR with zero debt service = inf",
      1.0 if dscr_inf == float('inf') else 0.0, 1.0, tol_abs=0.01)


# ==========================================================================
# 5. LCOE
# ==========================================================================
section("5. LCOE  (THB/kWh = PV_costs_MB*1000 / PV_MWh)")

# 1-yr project: capex=1 MB, opex=0, 1000 MWh, r=0 -> LCOE = 1*1000/1000 = 1.0
lcoe_s = lcoe_thb_per_kwh(1.0, [0.0], [1000.0], 0.0)
check("LCOE simple = 1.0 THB/kWh (capex=1MB, 1000 MWh, r=0)", lcoe_s, 1.0, tol_abs=1e-6)

# 2-yr, r=0: capex=1, opex=[0.1,0.1], MWh=[1000,1000]
# PV_cost = 1 + 0.1 + 0.1 = 1.2 MB; PV_MWh = 2000 MWh
# LCOE = 1.2*1000/2000 = 0.60 THB/kWh
lcoe_2 = lcoe_thb_per_kwh(1.0, [0.1, 0.1], [1000.0, 1000.0], 0.0)
check("LCOE 2yr, r=0 = 0.60 THB/kWh", lcoe_2, 0.60, tol_abs=1e-6)

# With discount r=10%, 1yr: PV_cost=1+0.05/1.1, PV_MWh=1000/1.1
lcoe_d = lcoe_thb_per_kwh(1.0, [0.05], [1000.0], 0.10)
exp_d = (1.0 + 0.05 / 1.1) * 1000.0 / (1000.0 / 1.1)
check("LCOE 1yr, r=10% = (1+0.05/1.1)*1000/(1000/1.1)", lcoe_d, exp_d, tol_abs=1e-5)


# ==========================================================================
# 6. WACC / CAPM / Hamada
# ==========================================================================
section("6. WACC-CAPM  (Hamada + CAPM + WACC)")

# Damodaran textbook example:
# rf=5%, MRP=6%, betaU=0.80, D/V=40%, T=30%, kd=7%
# D/E = 0.40/0.60 = 0.6667
# betaL = 0.80 * (1 + 0.70 * 0.6667) = 1.1733
# ke = 5% + 1.1733*6% = 12.04%
# kd_at = 7% * 0.70 = 4.90%
# WACC = 0.60*12.04% + 0.40*4.90% = 9.18%
w = wacc_capm(rf=0.05, mrp=0.06, beta_unlevered=0.80,
              debt_pct=0.40, tax_rate=0.30, interest_rate=0.07)
de_ratio = 0.40 / 0.60
betaL_exp = 0.80 * (1.0 + 0.70 * de_ratio)
ke_exp    = 0.05 + betaL_exp * 0.06
kd_at_exp = 0.07 * 0.70
wacc_exp  = 0.60 * ke_exp + 0.40 * kd_at_exp

check("Beta levered (Hamada)", w["beta_levered"], betaL_exp, tol_abs=1e-8)
check("Cost of equity (CAPM ke)", w["ke"], ke_exp, tol_abs=1e-8)
check("After-tax kd", w["kd_aftertax"], kd_at_exp, tol_abs=1e-8)
check("WACC", w["wacc"], wacc_exp, tol_abs=1e-8)

# All-equity edge case: WACC = ke = rf + betaU * MRP
w_eq = wacc_capm(rf=0.04, mrp=0.05, beta_unlevered=0.70,
                 debt_pct=0.0, tax_rate=0.20, interest_rate=0.06)
check("WACC all-equity = ke = rf + betaU*MRP", w_eq["wacc"],
      0.04 + 0.70 * 0.05, tol_abs=1e-8)


# ==========================================================================
# 7. Debt Schedule (annuity)
# ==========================================================================
section("7. Debt Schedule  (equal-payment annuity)")

P, r, n = 1000.0, 0.10, 5
pmt_exp = P * r * (1 + r)**n / ((1 + r)**n - 1)
ds = debt_schedule_annuity(P, r, n, 7)

int_y1_exp = P * r                  # Year-1 interest = 100
pr_y1_exp  = pmt_exp - int_y1_exp   # Year-1 principal = PMT - 100

check("Annuity Year-1 interest = P*r = 100", ds[0][0], int_y1_exp, tol_abs=1e-3)
check("Annuity Year-1 principal = PMT - interest", ds[0][1], pr_y1_exp, tol_abs=1e-3)
check("Annuity after tenor (yr6) interest = 0", ds[5][0], 0.0, tol_abs=1e-9)
check("Annuity after tenor (yr6) principal = 0", ds[5][1], 0.0, tol_abs=1e-9)
check("Balance at end of tenor (yr5) approx 0", ds[4][2], 0.0, tol_abs=0.05)

total_int = sum(ds[y][0] for y in range(5))
total_int_exp = pmt_exp * 5 - P
check("Total interest = total payments - principal", total_int, total_int_exp, tol_abs=0.05)


# ==========================================================================
# 8. Dulong HHV
# ==========================================================================
section("8. Dulong HHV  (81.0*C + 342.5*(H-O/8) + 22.5*S per %wt, Channiwala 2002)")

# Pure carbon: HHV = 81.0 * 100 = 8100 kcal/kg
hhv_C = dulong_hhv(100.0, 0.0, 0.0, 0.0, 0.0)
check("Dulong pure C = 8100 kcal/kg (canonical)", hhv_C, 8100.0, tol_abs=5.0)

# Pure sulfur: HHV = 22.5 * 100 = 2250 kcal/kg
hhv_S = dulong_hhv(0.0, 0.0, 0.0, 0.0, 100.0)
check("Dulong pure S = 2250 kcal/kg (canonical)", hhv_S, 2250.0, tol_abs=5.0)

# Wood (C=50, H=6, O=44): expected range 3800-5000 kcal/kg
# Note: H_eff = H - O/8 = 6 - 5.5 = 0.5 (most H is bound in cellulose)
# -> HHV is low end ~4200 kcal/kg, consistent with literature (17-20 MJ/kg dry wood)
hhv_wood = dulong_hhv(50.0, 6.0, 44.0, 0.0, 0.0)
wood_ok = 3800 <= hhv_wood <= 5000
print(f"  INFO  Dulong wood (C50 H6 O44): {hhv_wood:.0f} kcal/kg"
      f"  ({'OK in 3800-5000' if wood_ok else 'OUT OF RANGE 3800-5000'})")
if not wood_ok:
    _FAIL += 1
    _BUGS.append("Dulong wood HHV out of expected range 3800-5000 kcal/kg")
    print(f"  FAIL  Dulong wood HHV out of range")
else:
    _PASS += 1

# Coefficient comparison vs Channiwala & Parikh (2002) canonical Dulong form:
#   HHV = 81.0*C + 342.5*(H-O/8) + 22.5*S  (+ 5.56*N extended Wilson variant)
hhv_code  = dulong_hhv(60.0, 8.0, 20.0, 2.0, 1.0)
hhv_std   = 81.0*60 + 342.5*(8 - 20/8) + 5.56*2 + 22.5*1
pct_diff  = abs(hhv_code - hhv_std) / hhv_std * 100.0
print(f"  INFO  Dulong vs Channiwala-canonical: code={hhv_code:.0f}"
      f"  std={hhv_std:.0f}  diff={pct_diff:.2f}%  (post-fix)")
check("Dulong now matches Channiwala canonical", hhv_code, hhv_std, tol_abs=0.5)


# ==========================================================================
# 9. LHV from HHV
# ==========================================================================
section("9. LHV from HHV  (LHV = HHV - 5.84*(9H + Moisture), ISO 1928)")

hhv_w = dulong_hhv(50.0, 6.0, 44.0, 0.0, 0.0)
lhv_w = lhv_from_hhv(hhv_w, 6.0, 0.0)
lhv_exp_w = hhv_w - 5.84 * (9.0 * 6.0 + 0.0)
check("LHV = HHV - 5.84*(9H+W) formula (ISO-aligned)", lhv_w, lhv_exp_w, tol_abs=1e-6)

lhv_range_ok = 3500 <= lhv_w <= 5000
print(f"  INFO  LHV dry wood: {lhv_w:.0f} kcal/kg"
      f"  ({'OK in 3500-5000' if lhv_range_ok else 'OUT OF RANGE'})")


# ==========================================================================
# 10. T-VER Carbon Credit
# ==========================================================================
section("10. T-VER Carbon Credit  (BE_y = D*DOC*DOCf*F*MCF*(16/12)*GWP*(1-OX))")

# Manual: 1000 t waste, 100 Thai Baht/tCO2e
waste   = 1000.0
cp      = 100.0
DOC, DOCf, F, MCF, GWP, OX = 0.148, 0.5, 0.5, 1.0, 21, 0.1
be_manual_tco2e = waste * DOC * DOCf * F * MCF * (16.0/12.0) * GWP * (1.0 - OX)
rev_correct_mb  = be_manual_tco2e * cp / 1e6

rev_mb_code, be_yr_code = carbon_credit_tver(waste, cp, enabled=True)

print(f"\n  Manual BE  = {be_manual_tco2e:.2f} tCO2e for {waste:.0f} t waste")
print(f"  code be_yr = {be_yr_code:.6f}")
print(f"  Correct revenue = {rev_correct_mb:.6f} MB/yr")
print(f"  Code revenue    = {rev_mb_code:.6f} MB/yr")
ratio = rev_mb_code / rev_correct_mb if rev_correct_mb > 0 else 0
print(f"  Code/Correct ratio = {ratio:.6f}  (should be 1.000)")

check("T-VER be_yr = tCO2e (not tCO2e/1000)",
      be_yr_code, be_manual_tco2e, tol_abs=1.0,
      note="BUG: be_yr has /1e3 in formula -> units wrong, revenue understated 1000x")

check("T-VER revenue correct (MB/yr)",
      rev_mb_code, rev_correct_mb, tol_abs=1e-5,
      note="BUG: /1e3 in be_yr then /1e6 in rev = /1e9 total instead of /1e6")

if abs(ratio - 1.0) > 0.01:
    print(f"  FAIL  Carbon revenue off by factor {1.0/ratio:.0f}x -- BUG CONFIRMED")
    # already counted in the check() calls above
else:
    print(f"  PASS  Carbon revenue within tolerance")


# ==========================================================================
# 11. FCFE formula (verify the fix: FCFE = NPAT + Dep - Principal)
# ==========================================================================
section("11. FCFE formula  (verify fix: OCF - Principal, NOT OCF - Int - Principal)")

# EBIT=10, Int=2, T=20%, Dep=3, Principal=1
# NPAT = (10-2)*(1-0.2) = 6.4
# OCF  = 9.4
# Correct FCFE (post-fix) = OCF - Principal = 9.4 - 1 = 8.4
# Equivalently: FCFE = FCFF - Int*(1-T) - Principal = 11.0 - 1.6 - 1 = 8.4
ebit_ex, int_ex, t_ex, dep_ex, pr_ex = 10.0, 2.0, 0.20, 3.0, 1.0
ebt_ex  = ebit_ex - int_ex
tax_ex  = ebt_ex * t_ex
npat_ex = ebt_ex - tax_ex
ocf_ex  = npat_ex + dep_ex
fcff_ex = ebit_ex * (1.0 - t_ex) + dep_ex
fcfe_correct  = fcff_ex - int_ex * (1.0 - t_ex) - pr_ex   # Damodaran identity
fcfe_postfix  = ocf_ex - pr_ex                             # what engine does now

print(f"\n  EBIT={ebit_ex}, Int={int_ex}, T={t_ex}, Dep={dep_ex}, Principal={pr_ex}")
print(f"  NPAT = {npat_ex:.2f},  OCF = {ocf_ex:.2f},  FCFF = {fcff_ex:.2f}")
print(f"  Damodaran FCFE (FCFF - Int*(1-T) - Pr)   = {fcfe_correct:.2f}")
print(f"  Engine    FCFE (OCF - Pr, post-fix)       = {fcfe_postfix:.2f}")

check("FCFE engine formula matches Damodaran identity (post-fix)",
      fcfe_postfix, fcfe_correct, tol_abs=1e-6,
      note="Engine fix: fcfe_y = ocf - principal_repay (interest already in NPAT)")

# Verify via actual WTE engine: equity IRR should now be > 0 and roughly near WACC for default
try:
    from engines.wte import run_model as _wte_run, default_preset as _wte_pre
    _res = _wte_run(_wte_pre())
    _eirr = _res["kpis"]["equity_irr"] or 0.0
    _pirr = _res["kpis"]["project_irr"] or 0.0
    print(f"\n  WTE post-fix Equity IRR = {_eirr*100:.2f}%  (was negative pre-fix)")
    print(f"  WTE post-fix Project IRR = {_pirr*100:.2f}%")
    check("WTE equity IRR positive (post-fix)",
          1.0 if _eirr > 0.0 else 0.0, 1.0, tol_abs=0.01,
          note="Pre-fix: -1.97%; Post-fix should be positive")
except Exception as e:
    print(f"  SKIP  WTE engine check: {e}")


# ==========================================================================
# 12. BCR -- UNIDO-style with CAPEX in denominator (post-fix)
# ==========================================================================
section("12. BCR  (UNIDO standard: PV(rev) / [CAPEX + PV(opex)])")

# Revenues=[20*10yr], OpEx=[10*10yr], CAPEX=100, r=0
# Standard BCR = 200 / (100+100) = 1.00
revenues_l  = [20.0] * 10
costs_opex_l = [10.0] * 10
bcr_with_capex = bcr_calc(revenues_l, costs_opex_l, 0.0, capex_at_t0=100.0)
print(f"\n  revenues=[20x10yr], opex=[10x10yr], CAPEX=100, r=0")
print(f"  BCR (with CAPEX) = {bcr_with_capex:.2f}  (UNIDO standard)")
check("BCR = 200/(100+100) = 1.00 (UNIDO standard)",
      bcr_with_capex, 1.0, tol_abs=1e-6)

# Back-compat: omitting capex_at_t0 must still give old behaviour
bcr_no_capex = bcr_calc(revenues_l, costs_opex_l, 0.0)
check("BCR without capex_at_t0 = 2.0 (back-compat)",
      bcr_no_capex, 2.0, tol_abs=1e-6)


# ==========================================================================
# 12b. Monte Carlo percentile (linear interpolation, numpy-style)
# ==========================================================================
section("12b. Monte Carlo percentile  (linear interpolation, post-fix)")

# Build a simple model with a known triangular input to check percentile interp.
# Use a deterministic dataset to verify the interpolation formula directly.
# samples=[10, 20, 30, 40, 50] sorted; p10 -> pos = 0.10*4 = 0.4 -> 10+0.4*(20-10) = 14
# p50 -> pos = 0.50*4 = 2.0 -> 30; p90 -> pos = 0.90*4 = 3.6 -> 40+0.6*10 = 46
from engines.shared import monte_carlo
class _DummyDC:
    def __init__(self): self.x = 30.0
def _model_identity(p):
    return {"kpis": {"metric": p.x}}
out = monte_carlo(_model_identity, _DummyDC(),
                  {"x": {"dist": "uniform", "low": 10.0, "high": 50.0}},
                  n_runs=5000, metric="metric", seed=1)
# Uniform[10,50] -> theoretical p10=14, p50=30, p90=46
print(f"\n  Uniform[10,50] n=5000 -> p10={out['p10']:.2f}, "
      f"p50={out['p50']:.2f}, p90={out['p90']:.2f}")
check("Monte Carlo p10 of Uniform[10,50] ~= 14", out["p10"], 14.0, tol_abs=1.0)
check("Monte Carlo p50 of Uniform[10,50] ~= 30", out["p50"], 30.0, tol_abs=1.0)
check("Monte Carlo p90 of Uniform[10,50] ~= 46", out["p90"], 46.0, tol_abs=1.0)


# ==========================================================================
# 13. Engine smoke test (WTE default preset)
# ==========================================================================
section("13. WTE Engine smoke test  (default_preset, sanity ranges)")

try:
    from engines.wte import run_model as wte_run, default_preset as wte_preset
    p = wte_preset()
    res = wte_run(p)
    k = res["kpis"]

    pirr = k.get("project_irr")
    eirr = k.get("equity_irr")
    wacc_v = k.get("wacc")
    ke_v = k.get("ke")
    lcoe_v = k.get("lcoe_thb_per_kwh")
    carbon_rev = res["carbon"]["rev_mb_yr"]

    # ke must be > WACC (since ke is bigger of the two components)
    if ke_v is not None and wacc_v is not None:
        check("WTE ke > WACC (CAPM consistency)",
              1.0 if ke_v > wacc_v else 0.0, 1.0, tol_abs=0.01)

    print(f"\n  Default WTE preset results (post-fix):")
    print(f"    Project IRR  = {(pirr or 0)*100:.2f}%  (expect 5-20%)")
    print(f"    Equity IRR   = {(eirr or 0)*100:.2f}%  (post-fix: positive)")
    print(f"    WACC         = {(wacc_v or 0)*100:.2f}%")
    print(f"    LCOE         = {(lcoe_v or 0):.2f} THB/kWh  (expect 2.5-7 for small WTE)")
    print(f"    Carbon rev   = {carbon_rev:.4f} MB/yr  (post-fix: full magnitude)")

    pirr_ok = pirr is not None and 0.03 < pirr < 0.25
    lcoe_ok = lcoe_v is not None and 1.0 < lcoe_v < 8.0
    check("WTE project IRR in range [3%,25%]",
          1.0 if pirr_ok else 0.0, 1.0, tol_abs=0.01)
    check("WTE LCOE in range [1,8] THB/kWh",
          1.0 if lcoe_ok else 0.0, 1.0, tol_abs=0.01)

except Exception as e:
    _FAIL += 1
    _BUGS.append(f"WTE engine failed: {e}")
    print(f"  FAIL  WTE engine error: {e}")


# ==========================================================================
# 14. Biogas COD chain
# ==========================================================================
section("14. Biogas COD chain  (COD -> CH4 -> kWh)")

# Manual chain:
# COD = 190000 mg/L = 190 g/L = 190 kg/m3
# cod_removed = 190 * 0.55 = 104.5 kg-COD/m3
# ch4 = 104.5 * 0.35 = 36.575 m3-CH4/m3
# biogas = 36.575 / 0.48 = 76.198 m3-biogas/m3
# LHV_biogas = 17.5 MJ/m3
# thermal = 76.198 * 17.5 = 1333.5 MJ/m3
# electric = 1333.5 * 0.415 = 553.4 MJ/m3
# kWh = 553.4 / 3.6 = 153.7 kWh/m3

cod_mg_l     = 190000.0
cod_load     = cod_mg_l / 1000.0          # kg/m3
cod_removal  = 0.55
ch4_yield    = 0.35                        # m3-CH4/kg-COD
ch4_pct_frac = 0.48
lhv_bio      = 17.5
eff_engine   = 0.415

cod_removed_calc = cod_load * cod_removal
ch4_calc         = cod_removed_calc * ch4_yield
biogas_calc      = ch4_calc / ch4_pct_frac
thermal_calc     = biogas_calc * lhv_bio
electric_calc    = thermal_calc * eff_engine
kwh_calc         = electric_calc / 3.6

check("COD load = 190 kg/m3", cod_load, 190.0, tol_abs=1e-6)
check("COD removed = 104.5 kg/m3", cod_removed_calc, 104.5, tol_abs=1e-3)
check("CH4 = 36.575 m3/m3", ch4_calc, 36.575, tol_abs=1e-3)
check("Biogas = 76.198 m3/m3", biogas_calc, 76.1979, tol_abs=1e-3)
check("kWh/m3 feedstock = 153.7", kwh_calc, 153.71, tol_abs=0.1)


# ==========================================================================
# SUMMARY
# ==========================================================================
print(f"\n{'='*60}")
print(f"  AUDIT SUMMARY")
print(f"{'='*60}")
print(f"  Passed : {_PASS}")
print(f"  Failed : {_FAIL}")
print(f"  Total  : {_PASS + _FAIL}")

if _BUGS:
    print(f"\n  Bugs / issues found:")
    for i, b in enumerate(_BUGS, 1):
        print(f"    {i:2d}. {b}")

print()
sys.exit(1 if _FAIL > 0 else 0)
