# CLAUDE.md — FeasFlow project guide for Claude Code

Context for anyone (and any Claude) working on this repo. Read before making changes.

## What this is
FeasFlow — a multi-engine power-plant **feasibility studio**. Six plant types
(**RDF · WTE · RDF+WTE · Biogas · Solar PV · Biomass**) modelled from raw
material → technical output → financial verdict (IRR, NPV, DSCR, LCOE, payback).
Desktop (Tkinter) + web (Streamlit), same calculation engines.

Author: Alongkorn Chanta · © 2026.

## Run / verify
```bash
pip install -r requirements.txt
python feas_main.py                 # desktop GUI (Tkinter)
streamlit run feas_streamlit.py     # web GUI
python audit_correctness.py         # formula audit — must stay 59/59 PASS
python -m tests.test_biomass        # biomass unit tests — 8/8
python -m tools.biomass_case        # operating-asset case study report
```
Windows packaging: `build_installer.bat` → `Output\FeasFlow_Setup.exe`
(PyInstaller `FeasFlow.spec` onedir + Inno Setup `FeasFlow_installer.iss`).

## Architecture
```
engines/                one self-contained engine per plant type
  shared.py             common math: IRR/NPV/MIRR, DSCR, BCR, LCOE, WACC-CAPM,
                        debt schedule, BOI tax cascade, TaxLossCarryForward (NOL),
                        CAPEX build-up, Dulong/LHV, carbon, sensitivity, Monte Carlo,
                        build_result()
  rdf / wte / rdf_wte / biogas / solar / biomass .py
  __init__.py           REGISTRY = {code: module}
feas_main.py            desktop GUI (Tkinter)          feas_theme.py  theme/cards/charts
feas_streamlit.py       web GUI (Streamlit)            feas_help.py   parameter + KPI-card tooltips
feas_excel.py / feas_pdf.py   report export
audit_correctness.py + CORRECTNESS_AUDIT.md   methodology verification
METRICS.md              every KPI: formula, discount rate, colour bands, where shown
tests/  tools/          unit tests · operating-asset case study
docs/                   README screenshots
```

## Engine contract (every engine module exports)
- `XxxInputs` — a `@dataclass` of all parameters (with defaults)
- `run_model(p) -> dict` — returns the **common output schema**:
  `engine_type, inputs, raw_material, generation, capex, wacc, rows[],
   fcfe[], fcff[], cum_fcfe[], cum_fcff[], kpis{}, carbon{}` (+ optional `extras`)
- `default_preset() -> XxxInputs` — the base case shown on load
- `INPUT_SECTIONS` — `[(section_title, [(key, label, ftype, hint), ...]), ...]`;
  the GUIs build the input panel from this, so **new fields appear automatically**
- `META` — `{code, label, icon, description, color}`
- optional `PRESETS = {name: fn}` — extra presets (biomass: greenfield / brownfield);
  the preset dropdown appears only when an engine has >1 preset

`ftype` ∈ `bool | int | float | pct | str | choice:a|b|c`. `pct` values are stored
as fractions (0.20 = 20%); the GUI shows ×100.

## Key methodology (see CORRECTNESS_AUDIT.md)
- **DSCR** = CFADS ÷ (interest + principal), where CFADS = NPAT + Dep + Interest
  (= EBITDA − tax); `dscr_min`/`dscr_avg` over debt-service years only.
- **WACC** via CAPM (levered β); **IRR** by bisection with **MIRR** fallback when
  IRR is undefined. **Tax**: BOI holiday cascade + separate depreciation life +
  5-yr loss carry-forward (NOL).
- **Biomass** brownfield mode: no IRR — outputs `enterprise_value_remaining` /
  `equity_value_remaining` (remaining-PPA valuation).

## Conventions / gotchas
- **Never break the common output schema** — the GUIs, Excel/PDF export and audit
  all read the same keys. Add keys, don't rename. A new KPI also needs a
  `_kpi(...)` entry in `feas_help.py` (card tooltip) and a section in `METRICS.md`.
- Project NPV / LCOE / BCR use the `discount_rate` input; Equity NPV uses **Ke**;
  WACC is computed but not wired into the discount rate (see METRICS.md §2).
- After any engine/finance change: run `audit_correctness.py` (keep 59/59) and
  `tests/`. Don't regress the other engines' base-case KPIs.
- GUI is **DPI-aware**; fixed-pixel widths are scaled by `self.ui_scale`.
- Money in **MB** (million THB); energy conversions in `shared.py` constants.
- Do **not** commit build artifacts (`dist/`, `build/`, `Output/`, `tools/output/`
  are gitignored). Keep secrets out of the repo.
- Parameters are starting assumptions — the goal is a **correct method**, not a
  fixed answer.

## Do / don't for changes
- DO add a new engine by copying an existing module, keeping the contract, and
  registering it in `engines/__init__.py` + `ENGINE_ORDER`/`ENGINE_LABELS` in both
  GUIs + a `feas_help.py` guide entry.
- DO commit only when asked; branch off `main`; end commit messages with the
  Co-Authored-By trailer the environment specifies.
- DON'T push to GitHub unless asked.
