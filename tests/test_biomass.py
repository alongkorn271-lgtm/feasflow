"""Tests for engines.biomass and tools.biomass_case.
Run:  python -m pytest tests/test_biomass.py -q     (or)  python -m tests.test_biomass
"""
import copy
from engines import biomass as bm


def test_lhv_as_received():
    # 17 MJ/kg dry, 25 % moisture → 17×0.75 − 2.44×0.25 = 12.14
    assert abs(bm.lhv_as_received_mj(17.0, 0.25) - 12.14) < 1e-9


def test_export_capped_at_contract():
    p = bm.default_preset()
    p.parasitic_load_pct = 0.0          # 9.9 MW available
    assert bm.mw_export(p) == p.contract_mw


def test_fuel_equals_energy_over_lhv():
    p = bm.default_preset()
    mix = bm.fuel_mix(p)
    mwh = bm.net_mwh_year(p, 0)
    t = bm.fuel_tons_year(p, 0, mix)
    expect = mwh * 1000 * bm.heat_rate_year(p, 0) / (mix["lhv_mj_per_kg"] * 1000) / 1000
    assert abs(t - expect) < 1e-6


def test_heat_rate_from_efficiencies():
    p = bm.default_preset()
    p.use_heat_rate_input = False
    hr = bm.base_heat_rate(p)
    eta = p.boiler_efficiency * p.cycle_efficiency * (1 - p.parasitic_load_pct)
    assert abs(hr - 3600 / eta) < 1e-6


def test_greenfield_runs_and_schema():
    r = bm.run_model(bm.default_preset())
    assert len(r["rows"]) == 20
    for key in ("project_irr", "equity_irr", "lcoe_thb_per_kwh", "dscr_min"):
        assert key in r["kpis"]
    assert r["rows"][0]["opex_feedstock"] > 0


def test_brownfield_life_and_years():
    p = bm.brownfield_preset()
    r = bm.run_model(p)
    assert len(r["rows"]) == p.ppa_end_year - p.valuation_year + 1
    assert r["rows"][0]["calendar_year"] == p.valuation_year
    assert r["kpis"]["project_irr"] is None          # no entry price
    assert "enterprise_value_remaining" in r["kpis"]


def test_more_availability_more_value():
    p = bm.brownfield_preset()
    v0 = bm.run_model(p)["kpis"]["enterprise_value_remaining"]
    q = copy.deepcopy(p); q.availability += 0.01
    v1 = bm.run_model(q)["kpis"]["enterprise_value_remaining"]
    assert v1 > v0


def test_calibration_reproduces_2025():
    from tools import biomass_case
    _, c = biomass_case.calibrate()
    assert abs(c["model_cogs"] - c["actual_cogs"]) < 0.05
    assert abs(c["model_rev"] - c["actual_rev"]) < 0.05
    assert abs(c["model_net"] - c["actual_net"]) < 0.05


if __name__ == "__main__":
    import sys
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f(); print("PASS", f.__name__)
    print(f"{len(fns)} tests passed")
