# Handoff → Claude Code: add Biomass engine + MKP case to FeasFlow

> สรุปภาษาไทย: แพ็กนี้เพิ่มโมเดลโรงไฟฟ้าชีวมวล (`engines/biomass.py`) ที่ทำได้ทั้งโครงการใหม่ (greenfield) และโรงที่เดินอยู่แล้ว (brownfield) พร้อมสคริปต์กรณีศึกษาโรงไฟฟ้าแม่กระทิง (`tools/mkp_case.py`) และชุดทดสอบ งานที่ Claude Code ต้องทำต่อคือเชื่อมเข้ากับ GUI / Excel / PDF / audit ตามรายการด้านล่าง โดยห้ามเขียนทับโค้ดเดิมที่ใหม่กว่า

## 0. Context

- Repo: FeasFlow (Python, Tkinter desktop `feas_main.py` + Streamlit `feas_streamlit.py`), engines in `engines/`.
- These files were written against the **GitHub commit of 2026-09-08** ("Clarify README: technical + financial two-layer model").
  **The local folder may be newer. Diff first, merge carefully, never overwrite existing files wholesale.**
- New files only (nothing existing was modified):

| File | Purpose |
|---|---|
| `engines/biomass.py` | New engine. Same interface as other engines: `BiomassInputs`, `run_model(p)`, `default_preset()`, `INPUT_SECTIONS`, `META`. Extra: `mkp_brownfield_preset()`, `PRESETS` dict. |
| `tools/__init__.py`, `tools/mkp_case.py` | MKP case: historical back-check, calibration on 2025 P&L, forward valuation 2026–2039, "value of OE levers" table. Writes `tools/output/mkp_report.md` and `mkp_yearly.csv`. |
| `tests/__init__.py`, `tests/test_biomass.py` | 8 tests (plain asserts; pytest-compatible). |

Verify first:
```bash
python -m engines.biomass          # prints generic greenfield + MKP brownfield
python -m tests.test_biomass       # 8 tests passed
python -m tools.mkp_case           # report; calibration must reproduce 2025 COGS/revenue/net
python audit_correctness.py        # existing 59 checks must still pass
```

## 1. Engine design (read before wiring)

- **Physics:** fuel mix (2 streams, mass share, moisture, dry LHV) → `LHV_ar = LHV_dry(1−M) − 2.44·M`.
  Net MWh = `min(gross×(1−parasitic), contract_MW) × 8760 × AF × LF`; overhaul years (every N yr from COD) lose extra outage days.
  Fuel t = net kWh × net heat rate ÷ LHV. Heat rate is an input (from IAPWS heat balance) or `3600 / (η_boiler × η_cycle × (1−parasitic))`.
- **Revenue:** FiT base (+ premium for `premium_years` since COD); CPI-linked fraction escalates from `tariff_base_year`. T-VER = net MWh × grid EF × carbon price.
- **Opex:** fuel (largest), O&M fee, variable maintenance ฿/kWh, overhaul cost in overhaul years, ash, water/chem, PDF ฿/kWh, insurance, SG&A.
- **Modes:**
  - `brownfield_mode=False` → greenfield, CAPEX via `shared.capex_breakdown`, same KPIs as WTE.
  - `brownfield_mode=True` → starts at `valuation_year`, ends `ppa_end_year` (`last_year_fraction` for partial final year), opening debt + remaining tenor, remaining book value depreciation, BOI indexed from COD. t0 outflow = `entry_value_mb` (0 ⇒ IRR/payback = `None`, and KPIs `enterprise_value_remaining`, `equity_value_remaining` are the answer).
- Output rows reuse the common schema keys (`opex_feedstock`, `opex_om`, `fit_rev`, `carbon_rev`, …) plus extra keys: `net_mwh`, `tariff`, `availability`, `heat_rate`, `fuel_t`, `cogs_incl_dep`, `debt_balance`.
- `build_result(..., extras={"analysis_mode", "start_year", "life"})`.

## 2. Integration tasks

1. **Registry** – `engines/__init__.py`: `from . import biomass`, add `"biomass": biomass` to `REGISTRY`, update docstring and `__all__`.
2. **Desktop GUI** – `feas_main.py`:
   - add `"biomass"` to `ENGINE_ORDER`, label `"Biomass"` in `ENGINE_LABELS`.
   - `_build_generation_summary_rows`: add `et == "biomass"` block → Net generation, Fuel t/yr (t/d), LHV MJ/kg, Net heat rate kJ/kWh, SFC kg/kWh, Capacity factor, Ash t/yr.
   - `_render_engine_specific`: optional "Fuel & Heat Rate" card (mix shares, as-received LHV per stream, blended price ฿/t, spare MW above contract).
   - Everywhere KPIs are formatted: handle `None` IRR/payback (brownfield) → show "—", and when `extras.analysis_mode == "brownfield"` show `enterprise_value_remaining` / `equity_value_remaining` instead of IRR.
   - Preset picker: add a way to load `biomass.PRESETS["mkp_brownfield"]` (button or dropdown) — engines currently only expose `default_preset()`.
3. **Streamlit** – `feas_streamlit.py`: same ENGINE_ORDER/LABELS (`"🌾  Biomass"`), same None-safe KPI display, preset selector.
4. **Excel / PDF export** – `feas_excel.py` `_build_highlights` & generation sections, `feas_pdf.py`: add biomass branches (FiT, net capacity, fuel price, heat rate). Brownfield: label "Remaining-PPA valuation".
5. **Help / tooltips** – `feas_help.py`: entries for every new field in `INPUT_SECTIONS` (meaning, typical range, impact). Key ranges: parasitic 8–12 %, boiler η 78–85 % LHV, cycle η 28–32 %, net HR 14,500–17,000 kJ/kWh, corn husk dry LHV ~15–17 MJ/kg, wood ~18–19 MJ/kg.
6. **Audit** – `audit_correctness.py`: add biomass checks (LHV_ar formula, export cap, fuel = energy/LHV, HR from efficiencies, brownfield life, MKP calibration closes to 2025 P&L). Keep the existing 59 checks green.
7. **Sensitivity / Monte Carlo** – ensure `shared.compute_sensitivity` / `monte_carlo` work with biomass fields (`availability`, `net_heat_rate_kj_kwh`, `fuel1_price_thb_t`, `fuel1_moisture`, `om_fixed_mb`). For brownfield use metric `enterprise_value_remaining`.
8. **Docs** – README engine table (6 engines), FLOWCHARTS.md biomass flow, IMPROVEMENTS.md entry.
9. **Build** – run `build_exe.bat` / `build_installer.bat`; check `FeasFlow.spec` picks up `engines/biomass.py` (hidden imports) and does **not** need `tools/` or `tests/`.

## 3. Acceptance criteria

- All 8 biomass tests + existing 59 audit checks pass.
- Desktop and Streamlit: switch to Biomass, Calculate with default preset → KPIs, cash-flow table, charts, Excel & PDF export work.
- Load MKP preset → brownfield run shows remaining EV/equity value, no crashes on `None` IRR.
- No behaviour change for RDF / WTE / RDF+WTE / Biogas / Solar (compare KPIs before/after on their default presets).

## 4. MKP data & assumptions (for reviewers)

Public: 9.9 MW installed, 8.0 MW VSPP contract (PEA), COD 8 Aug 2019, 20-yr PPA, FiT ~4.62 ฿/kWh (effective ≈ 4.67 from Q2–Q3/2025: 16.61 GWh/77.5 MB, 14.40 GWh/67.3 MB), fuel corn husk + wood, P&L 2021–2025 (in `tools/mkp_case.py: HIST`), T-VER ≈ 94,300 tCO₂e over 3 yrs.

Assumed (edit `ASSUMPTIONS` in `tools/mkp_case.py` / preset): depreciation 45 MB/yr inside COGS, heat rate 15,650 kJ/kWh (IAPWS heat balance, 45 barg/450 °C case), fuel mix 80/20 at 25 %/35 % moisture, O&M fee 20 MB + 0.25 ฿/kWh + 15 MB overhaul every 4 yr, interest 5.5 %, remaining tenor 10 yr, BOI 8 yr + 5 yr at 10 %, CPI 1 % on 56 % of tariff, fuel escalation 1.5 %/yr, grid EF 0.50 t/MWh, PDF 0.01 ฿/kWh.
Calibrated on 2025: AF ≈ 91.8 %, implied fuel ≈ 1,770 ฿/t (≈ 62 % of COGS), implied carbon ≈ 337 ฿/t, opening debt ≈ 420 MB.
