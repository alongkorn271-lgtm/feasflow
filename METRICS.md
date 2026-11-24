# METRICS.md — FeasFlow KPI reference

What every KPI in `results["kpis"]` means, exactly how the engines compute it,
how to read it, and where it appears. Applies to all six engines
(RDF · WTE · RDF+WTE · Biogas · Solar PV · Biomass). They share the same
formulas from `engines/shared.py`.

- **Hover text on the KPI cards** (desktop + web) comes from
  `feas_help.py → kpi_guide(key)`. Keep it in sync with this file.
- Method verification is in `CORRECTNESS_AUDIT.md` (`audit_correctness.py`, 59/59).
- Money is in **MB** (million THB). Percentages are stored as fractions (0.12 = 12%).

---

## 1. Timeline and cash-flow building blocks

```
Year 0        investment: FCFF = −total CAPEX,  FCFE = −equity
Years 1 … N   operation (N = project_life), Year 1 = the COD year
Discounting   end-of-year: a year-t flow is divided by (1 + r)^t (no mid-year convention)
```

`total CAPEX` = EPC + owner's cost + contingency + IDC + working capital + DSRA.
`equity` = total CAPEX × (1 − debt %); `debt` = total CAPEX × debt %.

Each operating year the engine builds:

| Item | Formula |
|---|---|
| EBITDA | revenue − OPEX (OPEX includes fuel / feedstock, O&M, ash, insurance, SG&A, PDF levy …) |
| EBIT | EBITDA − depreciation (straight-line on project CAPEX over `depreciation_years`) |
| EBT | EBIT − interest |
| Tax | EBT × effective CIT (BOI cascade: 0% → partial → standard), after 5-yr loss carry-forward (NOL) |
| NPAT | EBT − tax |
| **CFADS** | NPAT + depreciation + interest (= EBITDA − tax) |
| **FCFF** (project) | EBIT × (1 − effective CIT) + depreciation. Unlevered, ignores financing and NOL |
| **FCFE** (equity) | NPAT + depreciation − principal repaid. Interest is already inside NPAT |

Last year: working capital + DSRA are recovered and decommissioning cost is
paid (both FCFF and FCFE). Terminal value is added if set. Debt is an equal-payment
annuity over `debt_tenor`.

## 2. Which discount rate each KPI uses

| Rate | Where it comes from | Used by |
|---|---|---|
| **Discount Rate** (`discount_rate` input, default 6.25%) | user input, a WACC proxy | Project NPV, LCOE, LCO-Pellet, BCR, Enterprise Value (brownfield) |
| **Ke** (cost of equity, CAPM) | computed | Equity NPV, Equity Value (brownfield), equity MIRR |
| **WACC** (CAPM) | computed | project MIRR; benchmark for Project IRR |

> ⚠ **Discount Rate is not linked to WACC.** The WACC card is computed by CAPM, but
> Project NPV / LCOE / BCR use the separate Discount Rate input. For a consistent
> view, set Discount Rate ≈ WACC. Equity NPV always uses Ke (typically 10–16% for
> the base cases, much higher than the 6.25% default Discount Rate).

---

## 3. KPI reference

### Returns

#### `project_irr` — Project IRR · card: hero
Return on the whole investment **before financing** (unlevered).
```
Project IRR = r such that Σ FCFF(t) / (1 + r)^t = 0,   t = 0 … N
```
- Solved by bisection on [−99%, 2000%]. It is `None` (undefined) when NPV has
  the same sign at both ends, i.e. the cash flow never changes sign.
- **Read:** green ≥ 12% hurdle · amber 0–12% · red < 0. Value is created when
  Project IRR > WACC.
- If undefined, the card falls back to **MIRR** (see below) and says so.

#### `equity_irr` — Equity IRR · card: hero
Return to the **shareholders after debt service** (levered).
```
Equity IRR = r such that Σ FCFE(t) / (1 + r)^t = 0,   FCFE(0) = −equity
```
- **Read:** green ≥ 12% · amber 0–12% · red < 0. Compare with **Ke**.
  The status banner is judged on this KPI.
- Leverage normally pushes Equity IRR above Project IRR when Project IRR > Kd × (1 − tax).

#### `project_mirr`, `equity_mirr` — Modified IRR · shown only as a fallback
```
MIRR = [ FV(positive flows, at reinvest rate) ÷ −PV(negative flows, at finance rate) ]^(1/N) − 1
```
- Project: finance = reinvest = WACC. Equity: finance = reinvest = Ke.
- Always single-valued, so it still ranks a loss-making case whose IRR is undefined.
  Added in `build_result()` for every engine.

### Value

#### `equity_npv` — Equity NPV · card: hero (MB)
```
Equity NPV = Σ FCFE(t) / (1 + Ke)^t,   t = 0 … N
```
- **Read:** > 0 means equity earns more than its required return Ke (green), < 0 red.
- The card sub-label shows the rate actually used (`@ Ke x.xx%`).

#### `project_npv` — Project NPV · not on a card (available in `results["kpis"]`)
```
Project NPV = Σ FCFF(t) / (1 + Discount Rate)^t,   t = 0 … N
```
- **Read:** > 0 means the project beats the Discount Rate before financing.

### Bankability

#### `dscr_min` — DSCR min · card: secondary
```
DSCR(t) = CFADS(t) ÷ (interest(t) + principal(t))
DSCR min = min DSCR(t) over years with principal repayment > 0
```
- **Read:** green ≥ 1.30 (bankable) · amber 1.20–1.30 (tight) · red < 1.20
  (lenders will not accept). Lenders size the loan on this number.
- Years with no debt service (DSCR = ∞) are excluded. `None` if there is no debt.

#### `dscr_avg` — DSCR avg · card: secondary
```
DSCR avg = simple mean of DSCR(t) over the same debt-service years
```
- Same 1.30 / 1.20 bands. A high average with a low minimum means one or two
  tight years. Check the DSCR sparkline / chart.

### Unit cost

#### `lcoe_thb_per_kwh` — LCOE · card: secondary (all engines except RDF) · ฿/kWh
```
LCOE = [ total CAPEX + Σ OPEX(t) / (1 + r)^t ] × 1000  ÷  Σ MWh(t) / (1 + r)^t,
       t = 1 … N,  r = Discount Rate
```
- Pre-tax and pre-financing. OPEX includes fuel / feedstock. The ×1000 converts
  MB / MWh → ฿/kWh.
- **Read:** compare with the tariff (FiT / PPA). Tariff > LCOE means a margin per kWh.
- Conservative detail: WC + DSRA sit in CAPEX but their end-of-life recovery is
  not credited.
- RDF (no power sale) sets it to `None`.

#### `lco_pellet_thb_per_ton` — LCO-Pellet · card: secondary (RDF only) · ฿/ton
```
LCO-Pellet = [ total CAPEX + Σ OPEX(t) / (1 + r)^t ] × 10⁶  ÷  Σ RDF tons(t) / (1 + r)^t
```
- **Read:** compare with the RDF selling price. Price > LCO means a margin per ton.

### Efficiency

#### `bcr` — Benefit-Cost Ratio · card: secondary
UNIDO style:
```
BCR = Σ revenue(t) / (1 + r)^t  ÷  [ total CAPEX + Σ OPEX(t) / (1 + r)^t ],
      t = 1 … N,  r = Discount Rate
```
- Revenue = all streams (FiT/PPA, tipping fee, RDF sales, carbon).
  Depreciation is **not** a cost here (CAPEX already counts the outlay).
- **Read:** green ≥ 1 (discounted revenue covers every cost), red < 1.
  Ignores tax and financing.

### Payback

#### `payback_equity` — Payback · card: secondary · years from COD
```
Cum(t) = −equity + Σ_{k=1..t} FCFE(k)
Payback = first t with Cum(t) ≥ 0, linearly interpolated inside that year
```
- Undiscounted. Returns 1.0 if equity is already recovered within Year 1.
  `None` means it is never recovered within project life (shown as "—").
- **Read:** green ≤ 10 yr, amber > 10 yr.

#### `payback_project` — Project payback · not on a card
Same, with `Cum(t) = −total CAPEX + Σ FCFF(k)`.

### Cost of capital

#### `wacc` — WACC · card: secondary
```
βL   = βU × [1 + (1 − tax) × D/E]            (D/E = debt % ÷ (1 − debt %))
Ke   = Rf + βL × MRP
WACC = E/V × Ke + D/V × Kd × (1 − tax)        (Kd = loan interest rate, tax = standard CIT)
```
- Defaults: Rf 2.05% (Thai 35-yr bond), MRP 8.5% (SET), βU 0.50
  (0.55 for RDF and RDF+WTE).
- **Read:** benchmark for Project IRR. It is **not** the rate used for Project NPV
  (see section 2).

#### `ke` — Cost of equity · not on its own card
Ke from the CAPM line above. Discount rate for Equity NPV, benchmark for Equity IRR.
Shown in the Equity NPV sub-label and on the WACC tab.

### Brownfield (operating-asset valuation) — Biomass `brownfield_mode`

In brownfield mode the hero row switches to value cards, because with
`entry_value_mb = 0` there is no up-front investment and IRR is undefined.
(With an entry value > 0 the IRRs are computed again.)

#### `enterprise_value_remaining` — Enterprise Value · card: hero (MB)
```
EV = Σ FCFF(t) / (1 + Discount Rate)^t,   t = 1 … remaining PPA   (Year-0 entry excluded)
```
What the remaining cash flows are worth to debt + equity. Compare with an asking price.

#### `equity_value_remaining` — Equity Value · card: hero (MB)
```
Equity Value = Σ FCFE(t) / (1 + Ke)^t,   t = 1 … remaining PPA
```
After servicing the opening debt. Roughly EV minus the remaining debt.

#### Discount Rate card (brownfield hero)
Shows the Discount Rate input used for EV / LCOE / BCR. Equity Value uses Ke.

---

## 4. Colour bands and the status banner

| KPI | Green | Amber | Red |
|---|---|---|---|
| Project / Equity IRR (or MIRR) | ≥ 12% | 0 – 12% | < 0 |
| Equity NPV | ≥ 0 | — | < 0 |
| DSCR min / avg | ≥ 1.30 | 1.20 – 1.30 | < 1.20 |
| BCR | ≥ 1 | — | < 1 |
| Payback (equity) | ≤ 10 yr | > 10 yr | — |

Excel colours IRR and DSCR green / amber only (amber below 12% / 1.30, no red
band). The web app shows IRR / DSCR as a ± delta against 12% / 1.30 instead of a
colour band.

**Status banner** (top of the results). The first rule that matches wins:

1. Brownfield mode → info: EV · Equity Value · DSCR min
2. Equity IRR < 0 → "Project loses money under current assumptions"
3. Equity IRR < 12% → "below 12% hurdle — Marginal"
4. DSCR min < 1.20 → "Not bankable yet"
5. otherwise → "Project is viable"

The 12% hurdle and the 1.30 / 1.20 DSCR lines are fixed in code (not inputs).

## 5. Where each KPI appears

| KPI key | Desktop card | Web card | Excel summary | PDF KPI grid |
|---|:-:|:-:|:-:|:-:|
| `project_irr` / `equity_irr` | ✓ | ✓ | ✓ | ✓ |
| `project_mirr` / `equity_mirr` | fallback | fallback | — | — |
| `equity_npv` | ✓ | ✓ | ✓ | ✓ |
| `project_npv` | — | — | — | — |
| `dscr_min` / `dscr_avg` | ✓ | ✓ | ✓ | ✓ |
| `lcoe_thb_per_kwh` / `lco_pellet_thb_per_ton` | ✓ (one of) | ✓ | ✓ | ✓ |
| `bcr` | ✓ | ✓ | ✓ | ✓ |
| `payback_equity` | ✓ | ✓ | ✓ | ✓ |
| `payback_project` | — | — | — | — |
| `wacc` | ✓ | ✓ | ✓ | ✓ |
| `ke` | sub-label | sub-label | sub-label | sub-label |
| `enterprise_value_remaining` / `equity_value_remaining` | brownfield | brownfield | — | — |

Every key can also be the `metric` of `shared.sensitivity()` (tornado) and
`shared.monte_carlo()`. Both default to `equity_irr`.

## 6. Known caveats

- **Discount Rate vs WACC** are independent inputs/outputs (section 2).
- **Multiple IRRs:** if a cash flow changes sign more than once (e.g. a big
  mid-life overhaul), bisection returns one root. Cross-check with NPV / MIRR.
- **Payback when never recovered** shows "—" everywhere (cards, Excel, PDF).
  It is undiscounted, so read it together with Equity NPV.
- **Undefined Equity IRR in the banner:** the desktop treats it as 0% ("Marginal"),
  while the web app uses MIRR. The cards themselves both show MIRR.
- **LCOE / BCR** include WC + DSRA in CAPEX without crediting their recovery
  (slightly conservative). Both are pre-tax and pre-financing.

## 7. Adding a KPI

1. Add the key to the engine's `kpis` dict. **Add, never rename.** GUIs, Excel/PDF
   and the audit all read these keys.
2. Add a `_kpi("new_key", what, formula, read)` entry in `feas_help.py`
   so the card gets hover text.
3. Document it here (section 3 + the table in section 5).
4. Run `python audit_correctness.py` (59/59) and `python -m tests.test_biomass`.
