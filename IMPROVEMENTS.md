# 🔧 FeasFlow — Engine Improvement Roadmap

Gap analysis for each of the 5 engines vs **real Thai power-plant projects**.
Each item has:
- **Current state** in code
- **Reality gap** — what real projects do differently
- **Impact** rating (🔴 High / 🟡 Medium / 🟢 Low)
- **Suggested fix** with formula + Thai benchmark values

Use this as the **prioritized backlog** when iterating each engine.

---

# 🌐 COMMON IMPROVEMENTS (apply to ALL engines)

These cut across every plant type. Address these FIRST for biggest accuracy gains.

## 🔴 C1. Working Capital

**Current**: Zero working capital modeled.

**Reality**: Real projects need cash buffer for:
- **Accounts Receivable** — PEA/EGAT pays in 60-90 days (creates 2-3 months revenue gap)
- **Inventory** — Spare parts, consumables, fuel reserve
- **DSRA** — Debt Service Reserve Account (banks require 3-6 months of debt service)

**Impact**: 🔴 High — increases project CAPEX by 5-10%, reduces IRR by 0.5-1.5pp

**Fix**: Add to `shared.capex_breakdown`:
```python
working_capital = revenue_yr1 * (60 / 365)        # 2 months AR
dsra            = debt_service_yr1 * 0.5          # 6 months DSRA
total_capex    += working_capital + dsra
# At end of project: + return of working capital + DSRA release
fcfe[-1]       += working_capital + dsra          # recovered
```

**Benchmark**: WC = 5-8% of total CAPEX for Thai WTE/biogas

---

## 🔴 C2. Construction-period drawdown

**Current**: `idc_pct = 5%` flat regardless of construction length.

**Reality**: IDC depends on:
- Construction period (1-3 years)
- Debt drawdown profile (S-curve: 20/50/30%)
- Interest accrued during build

**Impact**: 🔴 High for big projects — undercounts by 50% for 3-yr builds

**Fix**:
```python
def calc_idc(debt_amount, interest_rate, construction_years,
              drawdown_profile=None):
    # Default S-curve drawdown
    if drawdown_profile is None:
        if construction_years == 1: drawdown_profile = [1.0]
        elif construction_years == 2: drawdown_profile = [0.4, 0.6]
        else: drawdown_profile = [0.20, 0.50, 0.30]

    idc = 0
    drawn = 0
    for yr, pct in enumerate(drawdown_profile):
        drawn += debt_amount * pct
        # Interest for remaining (full-yr − yr) periods
        idc += drawn * interest_rate * (construction_years - yr - 0.5)
    return idc
```

**Benchmark**: IDC = 8-12% of EPC for 3-yr construction at MLR-0.5%

---

## 🟡 C3. PPA Escalation

**Current**: FiT/PPA flat (with optional 8-yr premium for WTE).

**Reality**: Real PPAs have:
- **FiTv** (variable component) — escalates with CPI (~2%/yr) — Thai SPP scheme
- **FiTf** (fixed component) — flat
- Some PPAs auto-escalate every 5 years vs CPI

**Impact**: 🟡 Medium — 0.5-1pp IRR over project life

**Fix**: Add to each engine's `_yearly_revenue`:
```python
fit_rate = fit_base + (fit_premium if y < premium_years else 0)
if cpi_linked_pct > 0:
    fit_rate *= (1 + cpi_escalation) ** y
```

**Benchmark**: VSPP usually flat. SPP Hybrid Firm: FiTv portion (~50%) escalates 2%/yr

---

## 🟡 C4. Insurance breakdown

**Current**: `insurance_pct = 0.4%` of CAPEX, single line.

**Reality**: Three policies:
- **Property all-risk (PAR)**: 0.2-0.3% of CAPEX/yr
- **Business interruption (BI)**: 0.15-0.25% of CAPEX/yr (insures revenue loss)
- **Third-party liability (TPL)**: 0.05-0.10% of CAPEX/yr

**Impact**: 🟢 Low (only affects OPEX breakdown view)

**Fix**: Split `insurance_pct` into `insurance_par_pct + insurance_bi_pct + insurance_tpl_pct`

---

## 🟡 C5. Decommissioning cost

**Current**: Zero end-of-life cost.

**Reality**: Project end requires:
- Site restoration
- Equipment dismantling
- Waste disposal
- Final landfill capping (for WTE/RDF/Biogas)

**Impact**: 🟡 Medium — affects late-life NPV

**Fix**: Add `decommissioning_cost_pct` (e.g. 2% of CAPEX) subtracted from FCFE in last year

---

## 🟡 C6. Currency / Import risk

**Current**: All ฿ THB.

**Reality**: Major equipment (turbines, FGT, panels) often imported. Exchange rate moves affect:
- Initial CAPEX (during construction)
- O&M (spare parts)

**Impact**: 🟡 Medium — bigger for solar/biogas/WTE (more imported)

**Fix**: Add `import_pct` field + USD/THB sensitivity

---

## 🔴 C7. Sensitivity / Monte Carlo

**Current**: Not implemented in new architecture (was in legacy `feas_engine.py`).

**Reality**: Bankers ALWAYS require:
- Tornado chart (±20% on key drivers)
- Monte Carlo (1000 runs, P10/P50/P90)

**Impact**: 🔴 High — required by every bank / IFI for credit committee

**Fix**: Port from old code → port `compute_sensitivity()` and `monte_carlo()` to `engines/shared.py` as engine-agnostic functions

---

# 🗑️ ENGINE 1 — RDF (sell to cement)

## Current model recap
- MSW input (tons/d) × yield% → RDF pellets (tons/d)
- LHV = Dulong from composition × moisture
- Revenue = RDF tons × (LHV × ฿/kcal) + tipping fee
- OPEX = transport + labour + electricity + maintenance + disposal + SG&A

## Gaps

### 🔴 R1. RDF yield modeling

**Current**: `rdf_yield_pct = 1.0` (100% mass retained) — UNREALISTIC

**Reality**: Yield depends on MSW composition + processing:
- Organic fraction (food, paper wet) → removed → typically 25-40% mass loss
- Glass/metal/inerts → separated → 8-15% loss
- Drying losses → 15-30% (water in food/organics)
- **Net RDF yield: 25-50% of MSW input** (EU benchmark)

**Impact**: 🔴 Critical — overestimates RDF output by 2-4x

**Fix**: Compute yield from composition:
```python
def calc_rdf_yield(composition, moisture, drying_loss=0.20):
    # Combustibles that survive processing
    keep_components = ['paper', 'plastic', 'cloth', 'rubber',
                       'leather', 'wood']
    keep_pct = sum(composition.get(c, 0) for c in keep_components)
    # Subtract drying water loss
    after_drying = keep_pct * (1 - moisture)  # dry basis
    return after_drying
```

**Benchmark Thailand**: 25-35% yield (high food/moisture MSW), 40-50% for sorted industrial MSW

---

### 🔴 R2. Drying energy cost

**Current**: Only generic `electricity_mb_yr` (8 MB/yr).

**Reality**: Thermal drying is energy-intensive:
- Need to evaporate ~30-40% of input water
- Energy required: 2.5-3 MJ/kg water evaporated
- For 240 t/d MSW @ 50% moisture → ~80 t/d water → ~7.6 TJ/day thermal!
- Often use waste heat from on-site WTE, or natural gas/biomass

**Impact**: 🔴 High — adds 15-30% to OPEX

**Fix**:
```python
water_evap_t_yr = msw_in_t_yr * (moisture_in - moisture_out)
drying_energy_mj_yr = water_evap_t_yr * 1000 * drying_mj_per_kg_water
drying_fuel_cost_mb = drying_energy_mj_yr / fuel_lhv_mj_per_kg / 1000 \
                       * fuel_cost_thb_per_ton / 1e6
```

**Benchmark**: 3-5 MB/yr for 240 t/d plant if using NG, 8-12 if using diesel

---

### 🟡 R3. Quality tiers + chlorine cap

**Current**: Single `rdf_price_thb_per_kcal` regardless of quality.

**Reality**: Cement plants pay by quality:
- LHV ≥ 4,500 kcal/kg → premium price (~0.22-0.25 ฿/kcal)
- LHV 3,500-4,500 → standard (~0.18-0.20 ฿/kcal)
- LHV < 3,500 → rejected or steep discount
- **Chlorine cap** (typical < 0.7%): textile/PVC raises Cl → rejection risk
- **Ash cap** (< 15%): high-ash batches rejected

**Impact**: 🟡 Medium — affects revenue 10-25%

**Fix**: Add quality-tier pricing:
```python
def rdf_price(lhv_kcal, cl_pct, ash_pct):
    if cl_pct > 0.7 or ash_pct > 15:
        return 0  # rejected
    if lhv_kcal >= 4500:
        return 0.24
    elif lhv_kcal >= 3500:
        return 0.20
    elif lhv_kcal >= 2500:
        return 0.15
    return 0  # too low
```

**Benchmark Thailand**: TPI Polene typical 0.18-0.22 ฿/kcal; SCG higher 0.20-0.25

---

### 🟡 R4. Offtake risk / contract minimums

**Current**: Assumes 100% of RDF is sold.

**Reality**: Cement plants:
- Contract minimum/maximum monthly tonnage (take-or-pay caps)
- Right to reject batches (quality / cement plant outage)
- Market price moves with coal price

**Impact**: 🟡 Medium — affects revenue reliability

**Fix**: Add `offtake_utilization_pct` (e.g. 0.85) and reject penalty

---

### 🟢 R5. Storage CAPEX

**Current**: Not separately modeled.

**Reality**: Need 5-15 days of RDF storage → silo or covered yard
- Silo CAPEX: ~10-20 MB for 1,000-ton silo
- Yard storage: 2-5 MB for sheltered concrete pad

**Impact**: 🟢 Low (small CAPEX item) but realistic to include

**Fix**: Add `storage_capex_mb` as separate line, scale with days_of_inventory

---

## RDF priority list

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | R1 — RDF yield from composition | 🔴 | M |
| 2 | R2 — Drying energy cost | 🔴 | M |
| 3 | R3 — Quality tiers + Cl cap | 🟡 | L |
| 4 | R4 — Offtake utilization | 🟡 | L |
| 5 | R5 — Storage CAPEX | 🟢 | L |

---

# 🔥 ENGINE 2 — WTE (MSW → electricity)

## Current model recap
- Dulong → LHV (kcal/kg)
- kWh/kg = LHV × η ÷ 859.845
- Required MSW = target kWh / (kWh/kg × 1000)
- Revenue = MWh × FiT + tipping + carbon

## Gaps

### 🔴 W1. Gross vs Net plant output

**Current**: Uses `mw_net` directly in generation calc — ignores parasitic.

**Reality**: WTE plant has 12-18% parasitic load:
- Induced draft fans (flue gas)
- Forced draft fans (combustion air)
- Boiler feed pumps
- Ash conveyors
- Flue gas treatment (scrubbers, bag filters)
- **Net export = Gross × (1 − parasitic_pct)**

**Impact**: 🔴 High — overestimates net export by 15%

**Fix**:
```python
@dataclass
class WTEInputs:
    mw_gross: float = 9.9        # at generator terminal
    parasitic_load_pct: float = 0.15
    @property
    def mw_net(self):
        return self.mw_gross * (1 - self.parasitic_load_pct)
```

**Benchmark Thailand**: Grate WTE 12-15% parasitic, Fluidized bed 14-18%

---

### 🔴 W2. Boiler efficiency vs thermal-electric efficiency

**Current**: Single `efficiency = 0.25` (lumped).

**Reality**: Two-stage:
- **Boiler thermal eff (η_b)**: 75-85% (heat from combustion to steam)
- **Steam-to-electricity (η_t)**: 25-30% (Rankine cycle)
- **Overall plant: η = η_b × η_t ≈ 19-26%**

**Impact**: 🔴 High for accuracy, allows component optimization

**Fix**: Replace with two parameters:
```python
boiler_efficiency: float = 0.80
turbine_efficiency: float = 0.28
@property
def plant_efficiency(self):
    return self.boiler_efficiency * self.turbine_efficiency
```

**Benchmark Thailand**: Yasothon 1.5 MW → η_b 78%, η_t 25% → 19.5% overall

---

### 🟡 W3. Variable LHV by season

**Current**: Single annual LHV from composition.

**Reality**: Thai MSW LHV varies:
- Dry season (Nov-Apr): 1,800-2,200 kcal/kg (less rain, drier organics)
- Wet season (May-Oct): 1,400-1,800 kcal/kg
- Annual avg may meet 1,670 but **wet season can fail minimum 1,440**

**Impact**: 🟡 Medium — affects availability + plant rating

**Fix**: Add `seasonal_lhv_variation_pct` (default 0.15) for sensitivity

---

### 🟡 W4. Ash composition + fly ash hazardous handling

**Current**: `ash_pct = 0.20` × single `ash_disposal_cost = 800 ฿/ton`.

**Reality**:
- **Bottom ash** ~15% of MSW — non-hazardous, ฿/ton: 500-1,000
- **Fly ash** ~5% of MSW — **HAZARDOUS** (heavy metals concentrated), ฿/ton: **2,500-4,000**
- Some fly ash can be cement-stabilized → cheaper

**Impact**: 🟡 Medium — fly ash disposal is 2-3x more than bottom

**Fix**:
```python
bottom_ash_pct: float = 0.15
bottom_ash_disposal: float = 800     # ฿/ton
fly_ash_pct: float = 0.05
fly_ash_disposal: float = 3000       # ฿/ton (hazardous)
```

**Benchmark**: Bangkok WTE projects: fly ash 2,800-3,500 ฿/ton

---

### 🟡 W5. Flue Gas Treatment (FGT) consumables

**Current**: `flue_gas_cost = 15 MB/yr` flat.

**Reality**: FGT consumes:
- **Lime/Ca(OH)₂** for acid gas (HCl, SO₂) — scales with Cl% in feed
- **Urea/NH₃** for NOₓ (SNCR/SCR)
- **Activated carbon** for dioxins/mercury
- **Bag filter replacement** every 2-3 years

**Impact**: 🟡 Medium — depends on MSW composition

**Fix**:
```python
lime_cost = msw_yr * cl_pct * lime_factor * lime_price_thb_per_ton / 1e6
urea_cost = msw_yr * nox_factor * urea_price / 1e6
ac_cost   = msw_yr * ac_dose_kg_per_ton * ac_price / 1e6
```

**Benchmark**: Total FGT chemicals 8-15 MB/yr for 8 MW plant

---

### 🟡 W6. Major overhaul cycle

**Current**: Constant availability (e.g. 0.85).

**Reality**:
- **Annual minor outage**: 7-14 days/yr (already in availability)
- **Major overhaul**: every 4 years, 21-30 days outage
- **Boiler tube replacement**: every 8-12 years, 2-month outage

**Impact**: 🟡 Medium — overhaul years have ~10pp lower availability

**Fix**: Add `overhaul_year_availability` for years 4, 8, 12, 16, 20

---

### 🟢 W7. Auxiliary fuel during startup

**Current**: `aux_fuel_pct = 3%` of generation hours × `฿800/MWh`.

**Reality**: Diesel/LPG for:
- Cold startup (1-2 days after major outage)
- Low-LHV feed supplementation
- Below-design load operation

**Impact**: 🟢 Low (already in model, just refine values)

**Benchmark**: 2-4% of fuel cost equivalent

---

## WTE priority list

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | W1 — Gross vs Net parasitic | 🔴 | L |
| 2 | W2 — Boiler × Turbine efficiency | 🔴 | L |
| 3 | W4 — Split bottom/fly ash | 🟡 | L |
| 4 | W5 — FGT consumables scaled | 🟡 | M |
| 5 | W6 — Major overhaul cycle | 🟡 | M |
| 6 | W3 — Seasonal LHV variation | 🟡 | L |
| 7 | W7 — Refine aux fuel | 🟢 | L |

---

# 🔄 ENGINE 3 — RDF + WTE Combined

## Current model recap
- MSW split by `rdf_split_pct` (e.g. 30/70)
- Both streams use SAME LHV (raw MSW composition)

## Gaps

### 🔴 RW1. WTE-side feed has different (lower) LHV

**Current**: Both streams use same composition LHV.

**Reality**: After RDF processing:
- **RDF stream**: combustibles (paper, plastic, cloth, wood) — high LHV
- **WTE stream**: rejects + fines + low-grade — **LOWER LHV** (mostly food, glass, hazardous)

**Impact**: 🔴 High — overestimates WTE electricity output

**Fix**: Compute separate LHV for each stream after split:
```python
# RDF stream LHV (after concentration)
rdf_lhv = compute_msw_chemistry(rdf_composition, after_drying_moisture)

# WTE stream LHV (residue after RDF extraction)
wte_composition = {k: max(v - rdf_take[k], 0)
                    for k, v in raw_msw.items()}
wte_lhv = compute_msw_chemistry(wte_composition, raw_moisture)
```

---

### 🔴 RW2. Mass balance reject tracking

**Current**: 100% of split goes to either RDF or WTE.

**Reality**: Sorting line generates rejects (5-15% of input) that:
- Can't be made into RDF (oversized, hazardous)
- Burned in WTE (good — shouldn't be wasted)

**Impact**: 🔴 High — affects both streams' tonnage

**Fix**: Three-way split:
```
msw_in → sorting →
  ├─ RDF stream (e.g. 30%)
  ├─ Direct WTE feed (e.g. 55%)
  └─ Reject (e.g. 5%) → also feed WTE OR landfill
```

---

### 🟡 RW3. Operating flexibility

**Current**: Fixed split ratio.

**Reality**: Operator can adjust ratio based on:
- RDF market price (high → divert more to RDF)
- WTE availability (overhaul → all to RDF stockpile)

**Impact**: 🟡 Medium — adds revenue optimization scenarios

**Fix**: Add `min_rdf_split`, `max_rdf_split` for sensitivity scenarios

---

## RDF+WTE priority list

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | RW2 — Mass balance with reject | 🔴 | M |
| 2 | RW1 — Separate LHV per stream | 🔴 | M |
| 3 | RW3 — Operating flexibility | 🟡 | M |

---

# 🌿 ENGINE 4 — Biogas

## Current model recap
- Single source: COD chain → biogas → kWh/m³
- Required vinasse volume back-calculated from target MW
- TOU revenue + fixed O&M

## Gaps

### 🔴 B1. Multi-source feedstock portfolio

**Current**: Single feedstock (COD, %CH4, cost).

**Reality**: Real projects (e.g. Akarawat) mix sources:
- KSL (low COD ~135k) — low cost but more volume needed
- Mithphol (high COD ~190k) — fewer trucks, lower transport
- Kanchanasingkorn (mid COD ~149k) — different pricing

**Impact**: 🔴 High — affects unit economics and risk diversification

**Fix**: Add `feedstock_sources: list[FeedstockSource]` where each has own COD/%CH4/price; total kWh = sum of all sources

```python
@dataclass
class FeedstockSource:
    name: str
    m3_per_day: float
    cod_mg_per_l: float
    ch4_pct: float
    material_cost: float
    transport_cost: float
```

---

### 🟡 B2. Digester startup ramp (Year 1)

**Current**: Year 1 = full capacity.

**Reality**:
- First 60-90 days: bacterial culture growing → 30-50% capacity
- Year 1 actual yield: ~70-80% of design

**Impact**: 🟡 Medium — Year 1 cash flow lower

**Fix**: Add `year_1_capacity_factor = 0.75` for biogas projects

---

### 🟡 B3. Digestate disposal

**Current**: Not modeled.

**Reality**: After digestion:
- Liquid digestate: 80-90% of input volume — can fertilizer/discharge (cost ~50-100 ฿/m³)
- Solid digestate: 5-15% — composted or landfilled

**Impact**: 🟡 Medium — adds OPEX

**Fix**:
```python
digestate_liquid_t_yr = ww_yr * 0.85
digestate_disposal_mb_yr = digestate_liquid_t_yr * disposal_cost / 1e6
```

---

### 🟡 B4. Flare cost (when grid down)

**Current**: Not modeled.

**Reality**: When grid is unavailable, biogas must be flared (env regulation):
- Wasted fuel
- Maintenance of flare system

**Impact**: 🟡 Low-Medium

**Fix**: Add `grid_downtime_pct = 2%` × wasted biogas

---

### 🟡 B5. REC (Renewable Energy Certificate)

**Current**: Not modeled.

**Reality**: Biogas/biomass eligible for I-REC sales (~150-300 ฿/MWh)

**Impact**: 🟡 Medium — extra revenue 0.5-1pp IRR

**Fix**: Add `rec_revenue_thb_per_mwh` × annual MWh

---

### 🟢 B6. pH/VFA inhibition events

**Current**: Constant operation.

**Reality**: pH crash → 1-3 week downtime (rare but real risk)

**Impact**: 🟢 Low — only matters in stress scenarios

**Fix**: Add to Monte Carlo as occasional 2-week outage event

---

## Biogas priority list

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | B1 — Multi-source portfolio | 🔴 | H |
| 2 | B2 — Year 1 startup ramp | 🟡 | L |
| 3 | B3 — Digestate disposal cost | 🟡 | L |
| 4 | B5 — REC revenue stream | 🟡 | L |
| 5 | B4 — Flare/grid downtime | 🟡 | L |

---

# ☀️ ENGINE 5 — Solar PV

## Current model recap
- PVWatts monthly profile × cooling gain × kWp → annual kWh
- TOU peak/off-peak split
- Annual degradation 0.55%

## Gaps

### 🔴 S1. Inverter replacement (Year 11-12)

**Current**: Not modeled.

**Reality**: Inverters last 10-15 years (modules last 25). At year ~12:
- **Replacement cost: 8-12% of original CAPEX** for new inverters
- **Plant downtime: 1-2 months** during swap

**Impact**: 🔴 High — single big CAPEX hit kills IRR

**Fix**:
```python
inverter_replace_year: int = 12
inverter_replace_pct: float = 0.10
inverter_downtime_days: int = 45
# In year 12: add CAPEX outflow, reduce generation
```

**Benchmark**: Module 25-yr, central inverter 10-12 yr, string inverter 12-15 yr

---

### 🟡 S2. Soiling losses (especially dry season)

**Current**: Not modeled (lumped in cooling gain).

**Reality**: Dust accumulates → 2-5% loss/yr (more in Thailand dry season Mar-May)
- Periodic cleaning recovers some
- FPV self-cleans by rainwater (~1-2% only)

**Impact**: 🟡 Medium — 2-3% annual revenue loss

**Fix**:
```python
soiling_loss_pct: float = 0.03      # 3% annual avg
# ground-mount: 0.04, FPV: 0.015
cleaning_frequency_per_yr: int = 4
cleaning_cost_per_event: float = 200000  # ฿
```

---

### 🟡 S3. Land lease cost (ground-mount)

**Current**: Not modeled.

**Reality**: Ground solar needs 1.5-2 hectares per MW:
- Land lease: 20,000-50,000 ฿/rai/year (1 rai = 0.16 ha)
- 20-25 year lease term
- Some projects own land (capex burden vs opex)

**Impact**: 🟡 Medium for ground · 🟢 None for FPV (on water)

**Fix**:
```python
is_floating: bool = True
land_area_rai_per_mw: float = 7   # ~1.1 ha/MW
land_lease_thb_per_rai_yr: float = 30000
land_lease_mb_yr = land_area * mw * lease_thb / 1e6
```

---

### 🟡 S4. Performance ratio (PR) decomposition

**Current**: PR lumped in `cooling_gain` (1.0-1.05).

**Reality**: PR is product of:
- Module efficiency × Temperature derating (4-7%)
- Inverter efficiency (96-98%)
- DC/AC wiring losses (2-4%)
- Soiling (already separately listed)
- Mismatch (1-2%)
- **Typical PR: 75-83%**

**Impact**: 🟡 Medium for accuracy

**Fix**: Expose PR as `performance_ratio = 0.80` (replaces cooling_gain when desired)

---

### 🟡 S5. Module degradation curve

**Current**: Linear 0.55%/yr from year 2.

**Reality**: Some modules have:
- **Year 1 LID** (light-induced degradation): 1-3% one-time
- **Years 2-25 linear**: 0.5-0.7%/yr
- Some technologies (TOPCon, HJT): degradation 0.3-0.4%/yr

**Impact**: 🟡 Medium for accuracy

**Fix**: Two-tier degradation:
```python
year_1_lid_pct: float = 0.02
annual_degradation: float = 0.0055
def degradation_factor(year):
    if year == 0: return 1.0
    return (1 - year_1_lid_pct) * (1 - annual_degradation) ** (year - 1)
```

---

### 🟢 S6. Curtailment risk

**Current**: 100% generation accepted.

**Reality**: If grid is constrained, PEA may curtail (rare in Thailand currently)

**Impact**: 🟢 Low currently, may rise in future with high solar penetration

**Fix**: Add `curtailment_pct = 0%` (configurable for stress scenarios)

---

## Solar priority list

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | S1 — Inverter replacement at yr 12 | 🔴 | L |
| 2 | S2 — Soiling losses | 🟡 | L |
| 3 | S3 — Land lease (ground only) | 🟡 | L |
| 4 | S4 — PR decomposition | 🟡 | M |
| 5 | S5 — LID + tiered degradation | 🟡 | L |

---

# 📋 OVERALL PRIORITIZATION

## Phase 1 — Highest impact (do first)

| # | Item | Engine | Why now |
|---|---|---|---|
| 1 | C1 — Working capital + DSRA | all | Bank requirement, affects all IRR |
| 2 | C7 — Sensitivity + Monte Carlo | all | Bank requirement |
| 3 | W1 — Gross vs Net parasitic | WTE | 15% generation overstatement |
| 4 | W2 — Two-stage efficiency | WTE | Component-level realism |
| 5 | R1 — Realistic RDF yield | RDF | 2-4x overstatement currently |
| 6 | R2 — Drying energy cost | RDF | 15-30% OPEX understatement |
| 7 | S1 — Inverter replacement | Solar | Single biggest IRR hit |
| 8 | B1 — Multi-source feedstock | Biogas | Real project structure |

## Phase 2 — Medium impact (refine accuracy)

| # | Item | Engine |
|---|---|---|
| 1 | C2 — IDC with drawdown profile | all |
| 2 | W4 — Bottom/fly ash split | WTE |
| 3 | W5 — FGT consumables scaled | WTE |
| 4 | RW1+RW2 — Mass balance + LHV per stream | RDF+WTE |
| 5 | S2+S3 — Soiling + Land lease | Solar |
| 6 | B2+B3+B5 — Startup + digestate + REC | Biogas |

## Phase 3 — Polish + edge cases

- Remaining items in each engine's list
- C4-C6 common items
- Decommissioning cost
- Currency hedging

---

# 🛠️ How to implement

For each improvement:

1. **Read the section** in this doc + the engine's `INPUT_SECTIONS`
2. **Add fields** to engine's `Inputs` dataclass (default to current behavior — backwards compatible)
3. **Update `compute_raw_material()` or `_yearly_*()`** function with the new formula
4. **Add fields to `INPUT_SECTIONS`** so GUI shows them
5. **Update preset** with realistic Thai benchmark value
6. **Test**:
   - `python -m engines.<name>` — CLI smoke test
   - `streamlit run feas_streamlit.py` — verify GUI
   - Validate KPI changes are in expected direction

7. **Commit + push** with descriptive message

---

# 🎯 Recommended workflow for iteration

Pick the engine + improvement number. Tell me:
> "ทำ W1 ใน WTE engine"

I'll then:
1. Read current `engines/wte.py`
2. Add new fields + logic per this spec
3. Update preset values
4. Test
5. Commit + push to GitHub
6. Report KPI change before/after

This way we iterate **one focused improvement at a time** — easy to review and rollback if needed.
