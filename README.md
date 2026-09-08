# FeasFlow — Power-Plant Feasibility Studio

**Multi-engine feasibility model for Thai waste-to-energy & renewable projects.**
Model five plant types — **RDF · WTE · RDF+WTE · Biogas · Solar PV** — from raw
material and plant chemistry all the way to a bankable financial verdict
(IRR, NPV, DSCR, LCOE, payback), with a clean desktop GUI and a web version.

> โปรแกรมศึกษาความเป็นไปได้โรงไฟฟ้า (RDF / WTE / RDF+WTE / Biogas / Solar)
> กรอกค่า → กด Calculate → ได้ IRR / NPV / DSCR / กระแสเงินสด พร้อมกราฟและ export Excel/PDF

*by **Alongkorn Chanta** · © 2026*

---

![FeasFlow — WTE feasibility overview](docs/gui-overview.png)

---

## What it does

Each plant type is a **self-contained engine** that starts from its own raw
material (not a one-size formula) and builds up to the same financial output
schema, so results are comparable across technologies:

| Engine | Starts from | Revenue drivers |
|--------|-------------|-----------------|
| **RDF** | MSW mix → dried refuse-derived fuel | RDF sales (฿/kcal by quality tier) + tipping fee |
| **WTE** | MSW combustion → steam → power | FiT electricity + tipping fee |
| **RDF + WTE** | 3-way split: sell RDF / burn / reject | RDF sales + FiT electricity + tipping |
| **Biogas** | wastewater COD → CH₄ → power | TOU electricity + REC (optional) |
| **Solar PV** | PVWatts irradiance → AC energy | TOU electricity (ground or floating FPV) |

Every engine runs a **two-stage pipeline** — first the **technical / engineering**
model (what the plant physically produces), then the **financial** model (whether
the project makes money). Type the parameters, press **Calculate**, and every KPI,
cash-flow table and chart updates. Hover any parameter for a tooltip with its
meaning, typical range, and impact.

## How it works — technical **and** financial

Two layers, both verified formula-by-formula against textbook standards
(see [`CORRECTNESS_AUDIT.md`](CORRECTNESS_AUDIT.md); `python audit_correctness.py`
→ 59 checks pass). Full per-engine **technical + financial process diagrams** are
in [`FLOWCHARTS.md`](FLOWCHARTS.md); refinement notes in [`IMPROVEMENTS.md`](IMPROVEMENTS.md).

### ① Technical model (engineering) — *what the plant produces*
Turns raw material into net electricity / fuel output:
- **Combustion (RDF / WTE)** — MSW composition → C/H/O/N/S; Dulong HHV
  (Channiwala coefficients); LHV from moisture (ISO 1928); boiler × turbine
  efficiency, parasitic load, availability and overhaul outages → net MWh.
- **Biogas** — COD → CH₄ (0.35 m³/kg-COD theoretical) → biogas → kWh chain;
  gas-engine efficiency, multi-source feedstock, year-1 ramp-up.
- **Solar PV** — PVWatts irradiance × Performance-Ratio breakdown (temperature,
  soiling, inverter, DC wiring, mismatch); LID + annual degradation; TOU split.
- **Mass / energy balance** — RDF yield & drying loss, the 3-way RDF+WTE split,
  bottom/fly-ash split, biogas feedstock volumes.

### ② Financial model — *whether it makes money*
Turns that output into a bankable verdict:
- **CAPEX build-up** — EPC + owner + contingency + IDC (drawdown) + working
  capital + DSRA + decommissioning.
- **Funding & cost of capital** — debt/equity split, annuity debt schedule,
  WACC via CAPM (levered β).
- **Tax** — BOI holiday cascade (0% → partial → full CIT), separate tax
  depreciation life, and tax-loss carry-forward (NOL, 5 yr).
- **Returns & bankability** — year-by-year cash flow → Project / Equity IRR
  (with **MIRR fallback**), NPV, DSCR, BCR, payback, LCOE / LCO-pellet, plus
  optional carbon-credit (T-VER) revenue.

> Parameters are starting assumptions for a *base case* — tune them to your own
> project. The point is a **correct method**, not a fixed answer.

## Screenshots

**Financial visualizations** — revenue composition + NPAT, cumulative cash flow
(with the payback marker), DSCR profile against the 1.30 bank line, and the
year-by-year OPEX breakdown:

![Visualizations](docs/gui-charts.png)

**Biogas engine** — the transparent COD → CH₄ → biogas → kWh chemistry chain
that drives generation, feedstock and CAPEX:

![Biogas chemistry chain](docs/gui-biogas.png)

KPI cards also carry meaningful sparklines: return / NPV / payback show
**cumulative cash flow** (crossing the dashed 0-line = paid back); DSCR shows the
**year-by-year profile** against the dashed 1.30 bank threshold.

## Run it

### A) Web (no install) — Streamlit
Deployed from this repo; open the public URL in any browser. To run locally:
```bash
pip install -r requirements.txt
streamlit run feas_streamlit.py
```

### B) Desktop from source (Python 3.11+)
```bash
pip install -r requirements.txt
python feas_main.py
```

### C) Windows — one-click installer / portable
No Python needed. Build the artifacts yourself with:
```bat
build_installer.bat
```
→ produces `Output\FeasFlow_Setup.exe` (installer, no admin rights required) and
a portable `dist\FeasFlow\` folder.

> The `.exe`/installer is **not code-signed**, so Windows SmartScreen may warn
> ("More info → Run anyway"), and a managed corporate antivirus may block
> unknown executables — in that case use the **web version** or ask IT to
> allow-list it.

## Project layout

```
engines/            self-contained calculation engines (+ shared.py math library)
  shared.py         IRR/NPV/DSCR/LCOE, WACC-CAPM, debt schedule, CAPEX,
                    Dulong/LHV, carbon, NOL, MIRR, sensitivity, Monte Carlo
  rdf / wte / rdf_wte / biogas / solar .py
feas_main.py        desktop GUI (Tkinter)
feas_streamlit.py   web GUI (Streamlit)
feas_help.py        per-parameter guidance shown as tooltips
feas_theme.py       theme, cards, sparklines, chart styling
feas_excel.py       Excel report export      feas_pdf.py  PDF report export
audit_correctness.py / CORRECTNESS_AUDIT.md  methodology verification
FeasFlow.spec / *_installer.iss / build_*.bat  packaging
```

## Notes

- Outputs are estimates for feasibility screening — validate assumptions against
  your real project before any investment decision.
- Not investment advice.

---

© 2026 **Alongkorn Chanta**. All rights reserved.
