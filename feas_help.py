# ════════════════════════════════════════════════════════════════════════
#  feas_help.py — per-parameter guidance shown as a hover tooltip
#
#  Used by feas_main.py: hover the parameter name to see what it means,
#  its typical range for Thai power projects, and how it moves the results.
#  key matches the field name in each engine (shared across engines).
#
#  Format:  key -> (desc, typical_range, impact)
#     desc   = what it is / what it does
#     range  = typical value range for Thai power projects
#     impact = how changing it moves IRR / NPV / DSCR
#  Keys not in this dict fall back to the field's inline hint.
# ════════════════════════════════════════════════════════════════════════
from __future__ import annotations
from typing import Optional

_G: dict[str, tuple[str, str, str]] = {}


def _add(keys, desc, rng="", impact=""):
    for k in (keys if isinstance(keys, (list, tuple)) else [keys]):
        _G[k] = (desc, rng, impact)


# ─────────────────────────────────────────────────────────────
# Project / time (shared by all engines)
# ─────────────────────────────────────────────────────────────
_add("project_name", "Project name, shown on report headers and exported files.",
     "", "No effect on the calculation.")
_add("cod_year", "COD = Commercial Operation Date — the first year the project earns revenue.",
     "2026–2030", "Shifting COD shifts all cash flows; small NPV effect via discounting.")
_add("project_life", "Project life in years used for the cash-flow model.",
     "RDF/WTE 20–25 yr · Solar 25 yr · Biogas 15–20 yr",
     "Longer → more cumulative revenue → higher IRR/NPV (but budget for major overhauls).")
_add("op_days", "Operating days per year.", "300–365 days",
     "More days → proportionally more output and revenue.")
_add(["availability", "performance_warranty"],
     "Availability = share of time the plant is available to run (net of outages/breakdowns).",
     "90–96%", "Higher → directly more energy/revenue; strong IRR driver.")
_add("actual_utilization", "Actual throughput vs the design capacity.",
     "80–100%", "Low → less feedstock/output than designed → lower revenue.")

# ─────────────────────────────────────────────────────────────
# CAPEX build-up (shared)
# ─────────────────────────────────────────────────────────────
_add("epc_cost", "EPC (Engineering-Procurement-Construction) — the main construction cost "
     "in million baht (MB); the largest CAPEX item.",
     "≈ 100–200 MB/MW (tech/size dependent)",
     "Higher → more capital → lowers IRR/NPV the most (highly sensitive).")
_add("owner_cost_pct", "Owner's costs (consultants / land / permits) as a % of EPC.",
     "5–12%", "Adds to CAPEX → lowers IRR.")
_add("contingency_pct", "Contingency reserve as a % of EPC.", "5–15%", "Adds to CAPEX → lowers IRR.")
_add(["idc_pct", "use_idc_drawdown"],
     "IDC = Interest During Construction — loan interest before revenue starts, capitalised into CAPEX.",
     "3–6% of debt", "Longer build / higher rate → more IDC → higher CAPEX.")
_add("construction_years", "Construction period (years) before COD.", "1–3 yr",
     "Longer → more IDC and delayed revenue.")
_add("wc_pct_revenue_yr1", "Working capital as a % of Year-1 revenue, to fund operations before cash is collected.",
     "10–15%", "Adds up-front capital but is recovered at project end.")
_add("dsra_months", "DSRA = Debt Service Reserve Account — cash reserve (in months of debt service) "
     "usually required by lenders.",
     "6 months", "Adds up-front capital; recovered once debt is fully repaid.")
_add("decommissioning_pct", "End-of-life decommissioning cost as a % of CAPEX.",
     "1–3%", "Negative cash flow in the final year; small NPV effect.")

# ─────────────────────────────────────────────────────────────
# Capital structure + WACC (CAPM)
# ─────────────────────────────────────────────────────────────
_add("debt_pct", "Debt ratio — share of total investment funded by loans; the rest is owner equity.",
     "50–70%", "More debt → less equity → higher Equity IRR (leverage) but lower DSCR, higher risk.")
_add("interest_rate", "Loan interest rate per year.", "5–8%",
     "Higher → more interest burden → lower DSCR and Equity IRR.")
_add("debt_tenor", "Loan repayment period (years).", "8–15 yr",
     "Longer → smaller payments → better DSCR, but more total interest.")
_add("discount_rate", "Discount rate used for present value (NPV) — usually set equal to WACC.",
     "6–9%", "Higher → future cash worth less today → lower NPV.")
_add("rf", "Risk-Free Rate — government-bond yield, the base of WACC (CAPM).",
     "2–3.5%", "A component of the Cost of Equity.")
_add("beta_unlevered", "Unlevered beta (β) — business risk vs the market, before debt effects; used in CAPM.",
     "0.5–0.9 (infrastructure)", "Higher → higher Cost of Equity → higher WACC → lower NPV.")
_add("mrp", "Market Risk Premium — equity return over bonds; used in CAPM.",
     "6–9%", "Higher → higher Cost of Equity → higher WACC.")

# ─────────────────────────────────────────────────────────────
# Tax + BOI
# ─────────────────────────────────────────────────────────────
_add("tax_rate", "Corporate Income Tax (CIT) rate after BOI incentives end.",
     "20% (Thailand)", "Higher → lower after-tax profit → lower IRR.")
_add("depreciation_years", "Tax depreciation life — years over which project CAPEX is written off "
     "straight-line (capped at project life). Shorter than project life in reality.",
     "machinery 5–10 yr · buildings 20 yr", "Shorter → bigger early tax shield → higher IRR (earlier).")
_add("nol_carryforward_years", "Tax-loss carry-forward — years a year's loss can offset future taxable "
     "profit (NOL). Thai Revenue Code allows 5 years.",
     "5 yr (Thailand)", "Longer → early losses shelter later profit → fairer, higher IRR.")
_add("boi_full_years", "Years of 100% tax exemption from BOI (counted from COD).",
     "3–8 yr", "Longer → big early tax savings → materially higher IRR (early cash is worth most).")
_add("boi_partial_years", "Years of partial tax reduction after the full-exemption period.",
     "0–5 yr", "Continues to reduce tax.")
_add("boi_partial_rate", "Reduced tax rate during BOI partial period (e.g. 10% = half of 20%).",
     "10%", "Lower → more tax savings.")

# ─────────────────────────────────────────────────────────────
# OPEX / escalation / insurance (shared)
# ─────────────────────────────────────────────────────────────
_add(["om_escalation", "cpi_escalation"], "Annual escalation (inflation) of operating costs (OPEX/CPI).",
     "1–3%/yr", "Higher → OPEX grows faster → lower profit in later years.")
_add("cpi_linked_fraction", "Share of the FiT tariff that is CPI-linked (FiTv, inflation-adjusted); "
     "the rest is fixed (FiTf).",
     "0–30% (per PPA)", "Higher → electricity revenue grows with inflation.")
_add(["sga_my", "sga_esc"], "SG&A — Selling, General & Administrative overhead in Year 1 + annual escalation.",
     "1–5 MB/yr", "Adds fixed OPEX.")
_add(["om_my_fixed", "om_pct_capex", "maintenance_mb_yr", "labour_mb_yr", "electricity_mb_yr"],
     "Operations & Maintenance (O&M) — either a fixed amount (MB/yr) or a % of CAPEX.",
     "O&M ≈ 2–4% of CAPEX/yr", "Higher → lower profit every year; ongoing IRR effect.")
_add(["insurance_par_pct", "insurance_bi_pct", "insurance_tpl_pct"],
     "Insurance premiums: PAR (property all-risk) / BI (business interruption) / TPL (third-party "
     "liability), each a % of CAPEX per year.",
     "≈ 0.3–0.5%/yr total", "Adds small but recurring OPEX.")
_add("terminal_value", "Terminal / salvage value at the end of the project, in million baht.",
     "0 or land value", "Adds cash flow in the final year → small NPV improvement.")
_add(["pdf_pct", "disposal_misc_mb_yr"], "Miscellaneous / provision costs (PDF/Misc).", "", "Adds OPEX.")

# ─────────────────────────────────────────────────────────────
# MSW / Dulong (RDF, WTE, RDF+WTE)
# ─────────────────────────────────────────────────────────────
_add("msw_intake_design_t_d", "Designed municipal solid waste (MSW) intake per day, in tonnes/day (t/d).",
     "100–1,000 t/d", "More → more feedstock/output → higher revenue and a larger plant.")
_add("use_msw_auto", "On = auto-calculate heating value (LHV) from the waste mix via Dulong's formula · "
     "Off = enter LHV manually.",
     "Recommended: On", "Chemistry-driven mode is more realistic.")
_add("msw_moisture", "Moisture of incoming waste (% wet weight) — Thai MSW is wet due to food waste.",
     "45–60%", "Wetter → lower LHV → less power / lower RDF quality.")
_add("msw_moisture_after_drying", "Moisture after drying (%).", "10–20%",
     "Drier → higher LHV → better RDF quality.")
_add("drying_loss_pct", "Extra mass lost during drying/sorting (beyond water).",
     "10–25%", "Higher → lower RDF yield.")
_add(["msw_pct_food", "msw_pct_paper", "msw_pct_plastic", "msw_pct_glass", "msw_pct_metal",
      "msw_pct_cloth", "msw_pct_wood", "msw_pct_rubber", "msw_pct_leather",
      "msw_pct_hazardous", "msw_pct_other"],
     "Waste composition (% wet weight) — all fields should sum to ~100%; used to derive C/H/O/N/S "
     "via Dulong's formula.",
     "food 30–50 · plastic 15–30 · paper 10–20 (Thailand)",
     "Plastic/paper/wood are the combustible, energy-rich fractions · glass/metal/moisture drag LHV down.")

# ─────────────────────────────────────────────────────────────
# RDF (sell RDF to cement plants)
# ─────────────────────────────────────────────────────────────
_add(["use_yield_from_composition", "rdf_yield_pct_manual"],
     "RDF Yield = share of waste converted into RDF fuel · Auto = computed from the mix · Off = entered manually.",
     "25–45%", "Higher → more sellable RDF → more revenue.")
_add("use_quality_tier_pricing", "On = RDF price varies by quality (LHV) in tiers · Off = single flat price.",
     "Recommended: On", "Reflects the real market (higher-LHV RDF sells for more).")
_add(["rdf_price_thb_per_kcal_high", "rdf_price_thb_per_kcal_std", "rdf_price_thb_per_kcal_low",
      "rdf_price_thb_per_kcal"],
     "RDF selling price per unit of heating value (baht/kcal), split by LHV quality tier.",
     "0.15–0.25 baht/kcal", "Higher → directly more core revenue (a highly sensitive RDF driver).")
_add(["chlorine_cap_pct", "ash_cap_pct"],
     "Chlorine/ash caps the cement plant will accept — above the cap the RDF is rejected "
     "(high chlorine corrodes the kiln).",
     "Cl ≤ 0.7% · Ash ≤ 18%", "Tighter caps → some RDF becomes unsellable.")
_add(["rdf_price_esc", "tipping_esc"], "Annual escalation of price / fee.", "1–2%/yr",
     "Helps revenue grow over time.")
_add("offtake_utilization", "Share the cement plant actually buys (offtake) out of what is produced.",
     "75–95%", "Low → unsold output → lower revenue.")
_add(["storage_days_capacity", "storage_capex_thb_per_ton_capacity"],
     "RDF storage capacity (days) + build cost per tonne of capacity.",
     "7–14 days", "Adds a small amount of CAPEX.")
_add("tipping_fee", "Gate/tipping fee received per tonne of waste accepted — an important side revenue.",
     "200–500 baht/tonne", "Higher → much more revenue (often make-or-break for RDF/WTE).")
_add(["transport_to_cement_thb_per_ton", "transport_rdf_thb_per_ton"],
     "RDF transport cost to the cement plant, per tonne.",
     "200–400 baht/tonne", "Higher → lower net RDF margin.")
_add(["drying_mj_per_kg_water", "drying_fuel_lhv_mj_per_kg", "drying_fuel_thb_per_ton", "drying_fuel_source"],
     "Energy/fuel used to dry off moisture (MJ per kg of water + fuel type/price).",
     "≈ 2.5–3.5 MJ/kg water", "High moisture → costly drying fuel → lower profit.")
_add("lhv_manual_kcal_per_kg", "Manually entered LHV (used when Dulong auto is Off).",
     "3,000–5,000 kcal/kg", "Higher → better output/price.")

# ─────────────────────────────────────────────────────────────
# WTE / RDF+WTE (combustion to power)
# ─────────────────────────────────────────────────────────────
_add(["mw_gross", "mw_net"], "Electrical capacity — Gross (at the generator) and Net (after in-plant use).",
     "WTE 1–10 MW", "Larger → more electricity revenue (but higher CAPEX).")
_add("parasitic_load_pct", "Plant's own power use (parasitic/auxiliary load) — subtract from Gross to get Net.",
     "8–15% (WTE)", "Higher → less net electricity sold → lower revenue.")
_add(["boiler_efficiency", "turbine_efficiency"],
     "Boiler efficiency (η_boiler) × turbine (η_turbine) = overall heat→electricity conversion efficiency.",
     "η_b 80–88% · η_t 25–35%", "Higher → more power per tonne of waste → more revenue.")
_add(["fit_base", "fit_premium", "premium_years"],
     "FiT (Feed-in Tariff) purchase price: base + premium (baht/kWh) and the number of premium years.",
     "WTE ≈ 3.66 + early-year premium", "Higher tariff → directly more core revenue (highly sensitive).")
_add("seasonal_lhv_variation_pct", "Seasonal LHV variation (wetter waste in the rainy season).",
     "±5–15%", "Captures uncertainty in power output.")
_add(["bottom_ash_pct", "fly_ash_pct", "bottom_ash_disposal_thb_per_ton", "fly_ash_disposal_thb_per_ton"],
     "Bottom-ash / fly-ash fractions + disposal cost per tonne (fly ash is hazardous and costs more).",
     "bottom 15–25% · fly 3–5%", "More ash / costlier disposal → higher OPEX.")
_add(["use_fgt_scaling", "lime_kg_per_ton_msw", "urea_kg_per_ton_msw", "ac_kg_per_ton_msw",
      "lime_price_thb_per_ton"],
     "FGT = Flue Gas Treatment: lime scrubs acids · urea cuts NOx · activated carbon (AC) captures "
     "dioxins/mercury.",
     "lime 10–20 · urea 2–5 kg/tonne", "More reagents → higher OPEX (required by emission regulations).")
_add(["overhaul_interval_years", "overhaul_outage_days", "boiler_tube_replace_year",
      "boiler_tube_replace_cost_mb", "bag_filter_replace_yrs", "bag_filter_replace_cost_mb"],
     "Major-overhaul schedule + boiler-tube / bag-filter replacement cycles — each with an outage.",
     "overhaul yearly ≈ 10–20 days", "Overhaul years → lower availability + lump costs → weaker cash flow that year.")
_add(["aux_fuel_pct", "aux_fuel_thb_per_mwh", "flue_gas_cost"],
     "Auxiliary fuel to start/support combustion when LHV is low.",
     "0–5% of energy", "More use → higher OPEX.")
_add(["rdf_split_pct", "rdf_split_min", "rdf_split_max", "reject_pct",
      "rdf_yield_within_split", "rdf_moisture_after_drying"],
     "Three-way waste split in the RDF+WTE plant: make RDF to sell / burn for WTE power / reject.",
     "RDF 20–40% · reject ≈ 5%", "More RDF split → more RDF sales revenue but less electricity (trade-off).")

# ─────────────────────────────────────────────────────────────
# Biogas
# ─────────────────────────────────────────────────────────────
_add("cod_mg_per_l", "COD (Chemical Oxygen Demand) — organic strength of the wastewater (mg/L), a proxy "
     "for chemical energy.",
     "ethanol wastewater 80,000–200,000 mg/L", "Higher → more gas/power per m³ of feed.")
_add("cod_removal_pct", "Efficiency of COD breakdown in the anaerobic system (% COD removal).",
     "UASB 70–85% · lagoon 50–70%", "Higher → more CH₄ produced.")
_add("ch4_yield_m3_per_kg", "Methane produced per unit of COD removed (m³-CH₄/kg-COD) — theoretical max 0.35.",
     "0.25–0.35", "Higher → more gas/power.")
_add(["ch4_pct", "biogas_lhv_mj_per_m3"],
     "Methane fraction of the biogas (%CH₄) + heating value (LHV) of the gas.",
     "CH₄ 55–65% · LHV 18–24 MJ/m³", "Higher CH₄ → richer gas → more power per m³.")
_add("gas_engine_efficiency", "Gas-engine efficiency converting heat energy → electricity.",
     "38–45%", "Higher → more power per unit of gas → more revenue.")
_add("year1_capacity_factor", "Year-1 capacity factor (ramp-up) — biological systems take time to stabilise.",
     "70–85%", "Low → lower first-year revenue than normal.")
_add(["grid_downtime_pct", "flare_om_mb_yr"],
     "Share of time power cannot reach the grid (must be flared) + flare system O&M.",
     "3–8%", "More downtime → less electricity sold.")
_add(["on_peak_price", "off_peak_price", "on_peak_ratio", "off_peak_rate", "peak_rate", "offpeak_rate"],
     "Time-of-use tariff: On-Peak (weekday daytime, higher) / Off-Peak (night/weekend, lower) + peak share.",
     "TOU tariff", "Higher On-Peak share → higher average revenue per kWh.")
_add(["use_multi_source", "source_a_name", "source_a_cod_mg_per_l", "source_a_ch4_pct",
      "source_a_m3_per_day", "source_a_cost_thb_per_m3",
      "source_b_name", "source_b_cod_mg_per_l", "source_b_ch4_pct", "source_b_m3_per_day",
      "source_b_cost_thb_per_m3", "source_c_name", "source_c_cod_mg_per_l", "source_c_ch4_pct",
      "source_c_m3_per_day", "source_c_cost_thb_per_m3"],
     "Multi-source mode (A/B/C) — each wastewater source has its own COD, %CH₄, m³/day and purchase cost.",
     "", "Combines energy from all sources → total capacity and revenue.")
_add(["digestate_disposal_thb_per_m3", "digestate_liquid_fraction"],
     "Handling of post-digestion sludge/effluent (digestate) + disposal cost per m³.", "", "Adds OPEX.")
_add(["enable_rec", "rec_price_thb_per_mwh"],
     "REC = Renewable Energy Certificate — green-energy credits sold as side revenue.",
     "REC ≈ 50–200 baht/MWh", "On → small extra revenue.")
_add(["material_cost_thb_per_m3", "transport_cost_thb_per_m3", "additional_cost_thb_per_m3", "feedstock_name"],
     "Feedstock / transport / other cost per m³ of wastewater.", "", "Higher → lower profit.")

# ─────────────────────────────────────────────────────────────
# Solar PV
# ─────────────────────────────────────────────────────────────
_add(["pvwatts_location", "cooling_gain_factor"],
     "Reference solar profile (PVWatts) by location + cooling gain of floating panels (FPV runs slightly "
     "cooler and yields a bit more).",
     "cooling gain +3–8% (FPV)", "Better sun / cooler → more generation.")
_add("dc_ac_ratio", "DC panel power to AC inverter ratio (DC/AC ratio, or ILR).",
     "1.1–1.3", "Higher → better morning/evening output but clipping at midday.")
_add(["inverter_efficiency", "temperature_derate_pct", "soiling_loss_pct",
      "dc_wiring_losses_pct", "mismatch_losses_pct", "use_pr_breakdown"],
     "Loss factors that combine into the Performance Ratio: inverter · temperature · soiling (dust) · "
     "DC wiring · mismatch.",
     "total PR ≈ 75–82%", "More losses → actual generation drops below the theoretical value.")
_add(["cleaning_frequency_per_yr", "cleaning_cost_per_event_mb"],
     "Panel cleaning frequency per year + cost per cleaning — cleaning more often means less dust but "
     "more cost.",
     "2–6 times/yr", "Balance between soiling loss and cleaning cost.")
_add(["year1_lid_pct", "annual_degradation"],
     "Panel degradation: LID (Light-Induced Degradation) in Year 1 + cumulative annual degradation.",
     "LID ≈ 1–2% · degradation ≈ 0.5%/yr", "Accumulates over time → generation falls in later years.")
_add("curtailment_pct", "Share of generation curtailed (ordered down) when the grid is full.",
     "0–5%", "Higher → less electricity sold.")
_add(["is_floating", "land_area_rai_per_mw", "land_lease_thb_per_rai_yr", "land_lease_escalation"],
     "Floating (FPV) or ground-mounted + land used (rai/MW) and land lease rate (FPV usually has no land "
     "lease).",
     "≈ 6–10 rai/MW (ground)", "High lease rate → higher OPEX (FPV saves this).")
_add(["inverter_replace_year", "inverter_replace_pct_of_capex", "inverter_replace_downtime_days"],
     "Mid-life inverter replacement (life ≈ 10–12 yr) + cost + downtime.",
     "year 10–13 · ≈ 5–10% of CAPEX", "Replacement year → a one-off dip in cash flow.")
_add(["peak_start_hour", "peak_end_hour", "weekdays_per_year", "weekend_days_per_year"],
     "On-Peak window (start-end hour) + weekdays/weekend days per year, used to split TOU revenue.",
     "peak ≈ 09:00–22:00 Mon–Fri", "Sets the Peak/Off-Peak revenue mix.")

# ─────────────────────────────────────────────────────────────
# Carbon credit (T-VER)
# ─────────────────────────────────────────────────────────────
_add(["enable_carbon", "carbon_price"],
     "Enable carbon-credit (T-VER) sales from greenhouse-gas reductions + price per tonne CO₂eq.",
     "Thai price ≈ 100–300 baht/tonne", "On → extra revenue (still volatile with the carbon market).")

# ─────────────────────────────────────────────────────────────
# Biomass (solid-fuel steam plant)
# ─────────────────────────────────────────────────────────────
_add("contract_mw", "PPA export cap (MW) — the meter can't sell above this even if the "
     "generator is bigger. Net export = min(gross − parasitic, contract).",
     "VSPP ≤ 8 MW · SPP larger", "Below installed MW → the spare capacity earns nothing.")
_add("load_factor", "Load factor while running — average export as a share of the contract MW "
     "when the plant is online (separate from availability).",
     "95–99%", "Higher → more energy per available hour.")
_add(["use_heat_rate_input", "net_heat_rate_kj_kwh"],
     "Net heat rate — fuel energy (LHV) in per net kWh out; the inverse of overall efficiency. "
     "Toggle off to derive it from boiler × cycle efficiency instead.",
     "14,500–17,000 kJ/kWh (biomass grate)", "Lower → less fuel per kWh → lower fuel cost → higher IRR.")
_add("cycle_efficiency", "Steam cycle + generator efficiency (turbine gross).",
     "28–32% (biomass Rankine)", "Higher → more power per unit of steam.")
_add("heat_rate_degradation_pct", "Yearly worsening of heat rate (fouling, wear) from model start.",
     "0.2–0.5%/yr", "Fuel creeps up over the project life.")
_add(["fuel1_share", "fuel2_share"],
     "Mass share of each fuel stream in the blend (e.g. corn husk + wood chip); shares are "
     "normalised to 100%.",
     "husk 70–85% · wood 15–30%", "Sets the blended LHV and fuel price.")
_add(["fuel1_moisture", "fuel2_moisture"],
     "As-received moisture of the fuel — wet fuel carries less usable energy: "
     "LHV_ar = LHV_dry·(1−M) − 2.44·M.",
     "husk 20–30% · wood 30–40%", "Wetter → lower as-received LHV → more tonnes burned → higher cost.")
_add(["fuel1_lhv_dry_mj", "fuel2_lhv_dry_mj"],
     "Dry (bone-dry) lower heating value of the fuel.",
     "corn husk 15–17 · wood 18–19 MJ/kg", "Higher → more energy per tonne.")
_add(["fuel1_price_thb_t", "fuel2_price_thb_t", "fuel_transport_thb_t", "fuel_price_esc"],
     "Delivered fuel price per tonne (+ optional transport adder, + annual escalation). "
     "Fuel is the single largest operating cost of a biomass plant.",
     "≈ 1,300–2,300 ฿/t delivered", "The #1 driver — a few % on fuel price swings IRR sharply.")
_add(["ash_pct_of_fuel", "ash_disposal_thb_t"],
     "Ash produced as a share of fuel burned + its disposal cost per tonne.",
     "5–10% of fuel", "Adds OPEX; minor next to fuel.")
_add("grid_ef_tco2_mwh", "Grid emission factor — tonnes CO₂ avoided per MWh, used for the T-VER credit.",
     "≈ 0.5 tCO₂/MWh (Thai grid)", "Higher → more carbon credits.")
_add(["om_fixed_mb", "maint_var_thb_kwh", "overhaul_cost_mb"],
     "O&M contract fee (fixed MB/yr) + variable maintenance (฿/kWh) + a lump overhaul cost "
     "added in each major-overhaul year.",
     "fee ~15–25 MB · maint 0.2–0.3 ฿/kWh", "Second-largest cost block after fuel.")
_add(["water_chem_thb_kwh", "pdf_thb_kwh"],
     "Water & chemicals (฿/kWh) and the Power Development Fund levy (฿/kWh) on generation.",
     "PDF ~0.01 ฿/kWh (verify)", "Small recurring OPEX.")
_add(["insured_value_mb", "insurance_pct"],
     "Insured asset value and the annual premium as a % of it.",
     "≈ 0.4%/yr", "Adds fixed OPEX.")
# Brownfield (operating-asset valuation) fields
_add(["brownfield_mode", "valuation_year", "ppa_end_year", "last_year_fraction", "entry_value_mb",
      "opening_debt_mb", "remaining_debt_tenor", "remaining_book_value_mb", "remaining_dep_years"],
     "Brownfield mode values an already-running plant over its REMAINING PPA (from valuation year "
     "to PPA end) using the opening debt, remaining tenor and remaining book value. Entry value 0 "
     "means the output is the enterprise / equity value of what's left (IRR is then undefined).",
     "e.g. 2026→2039, ~7 yr debt left", "Answers 'what is the remaining contract worth', not new-project IRR.")


# ════════════════════════════════════════════════════════════════════════
#  KPI guidance — hover text for the KPI cards (desktop + web).
#  Full definitions, formulas and worked notes: METRICS.md.
#
#  Format:  kpi_key -> (what, formula, read)
#     what    = what the number is
#     formula = how the engine computes it
#     read    = how to judge it (the colour thresholds the cards use)
#  Keys follow results["kpis"]; "discount_rate" is the brownfield hero card.
# ════════════════════════════════════════════════════════════════════════
_K: dict[str, tuple[str, str, str]] = {}


def _kpi(keys, what, formula="", read=""):
    for k in (keys if isinstance(keys, (list, tuple)) else [keys]):
        _K[k] = (what, formula, read)


_kpi("project_irr",
     "Project IRR — return on the whole investment before financing (unlevered).",
     "Rate r where NPV(FCFF) = 0. Year 0 = −total CAPEX; each year "
     "FCFF = EBIT × (1 − tax) + depreciation; last year adds WC/DSRA "
     "recovery − decommissioning.",
     "Green ≥ 12% hurdle · amber 0–12% · red < 0. Compare with WACC: "
     "IRR > WACC creates value. "
     "If IRR is undefined (cash flow never changes sign) the card shows MIRR "
     "(financed and reinvested at WACC).")
_kpi("equity_irr",
     "Equity IRR — return to the shareholders after debt service (levered).",
     "Rate r where NPV(FCFE) = 0. Year 0 = −equity; each year "
     "FCFE = NPAT + depreciation − principal repaid.",
     "Green ≥ 12% hurdle · amber 0–12% · red < 0; the status banner is judged "
     "on this number. Compare "
     "with Ke (cost of equity). Falls back to MIRR at Ke when IRR is undefined.")
_kpi("equity_npv",
     "Equity NPV — present value of the shareholders' cash flows, in MB.",
     "Σ FCFE(t) / (1 + Ke)^t for t = 0 … N, discounted at Ke "
     "(CAPM cost of equity), not at the Discount Rate input.",
     "> 0 → equity earns more than its required return Ke.")
_kpi("project_npv",
     "Project NPV — present value of the unlevered project cash flows, in MB.",
     "Σ FCFF(t) / (1 + r)^t for t = 0 … N, r = Discount Rate input.",
     "> 0 → the project beats the discount rate before financing.")
_kpi("dscr_min",
     "DSCR min — the weakest year's debt cover (loan-repayment years only).",
     "DSCR = CFADS ÷ (interest + principal), where "
     "CFADS = NPAT + depreciation + interest (= EBITDA − tax).",
     "Green ≥ 1.30 (bankable) · amber 1.20–1.30 (tight) · red < 1.20 "
     "(lenders will not accept). Lenders size debt on this number.")
_kpi("dscr_avg",
     "DSCR avg — average debt cover over the loan tenor.",
     "Mean of yearly DSCR = CFADS ÷ (interest + principal), over the years "
     "with principal repayment.",
     "Same 1.30 / 1.20 bands as DSCR min. A high average with a low minimum "
     "means one or two tight years — check the DSCR chart.")
_kpi("lcoe_thb_per_kwh",
     "LCOE — levelised cost of electricity, ฿/kWh.",
     "[CAPEX + Σ OPEX(t) / (1 + r)^t] × 1000 ÷ Σ MWh(t) / (1 + r)^t, "
     "r = Discount Rate. OPEX includes fuel / feedstock; tax and financing "
     "are excluded.",
     "Compare with the tariff (FiT / PPA): tariff > LCOE → margin per kWh.")
_kpi("lco_pellet_thb_per_ton",
     "LCO-Pellet — levelised cost of producing one ton of RDF, ฿/ton (RDF engine).",
     "[CAPEX + Σ OPEX(t) / (1 + r)^t] × 10⁶ ÷ Σ tons(t) / (1 + r)^t, "
     "r = Discount Rate.",
     "Compare with the RDF selling price: price > LCO → margin per ton.")
_kpi("bcr",
     "BCR — benefit-cost ratio (UNIDO style).",
     "PV(revenue) ÷ [CAPEX + PV(OPEX)], discounted at the Discount Rate. "
     "Depreciation is not a cost here (CAPEX is already counted).",
     "Green > 1: discounted revenue covers every cost; red < 1: it does not. "
     "Ignores tax and financing.")
_kpi(["payback_equity", "payback"],
     "Payback — years from COD until the shareholders get their equity back.",
     "First year where −equity + Σ FCFE ≥ 0, interpolated linearly inside "
     "that year. Undiscounted.",
     "Green ≤ 10 yr, amber > 10 yr. '—' = not paid back within project life.")
_kpi("payback_project",
     "Project payback — years from COD until cumulative FCFF recovers total CAPEX.",
     "First year where −CAPEX + Σ FCFF ≥ 0, interpolated linearly. Undiscounted.",
     "Shorter = less exposure to late-life risk.")
_kpi("wacc",
     "WACC — weighted average cost of capital, from CAPM.",
     "E/V × Ke + D/V × Kd × (1 − tax), with Ke = Rf + βL × MRP and "
     "βL = βU × [1 + (1 − tax) × D/E].",
     "Benchmark for Project IRR. Project NPV, LCOE and BCR use the Discount "
     "Rate input, not this value — set them equal for a consistent view.")
_kpi("ke",
     "Ke — cost of equity (CAPM), the return shareholders require.",
     "Ke = Rf + βL × MRP, βL = βU × [1 + (1 − tax) × D/E].",
     "Discount rate for Equity NPV; benchmark for Equity IRR.")
_kpi(["project_mirr", "equity_mirr"],
     "MIRR — modified IRR, shown when the ordinary IRR is undefined.",
     "[FV of positive flows at the reinvest rate ÷ PV of negative flows at the "
     "finance rate]^(1/N) − 1. Project: WACC / WACC; equity: Ke / Ke.",
     "Always single-valued, so it still ranks a loss-making case.")
_kpi("enterprise_value_remaining",
     "Enterprise Value — what the plant's remaining cash flows are worth today "
     "(brownfield, to debt + equity).",
     "Σ FCFF(t) / (1 + r)^t for t ≥ 1, r = Discount Rate; the entry price "
     "(year 0) is excluded.",
     "Compare with an asking price for the operating asset.")
_kpi("equity_value_remaining",
     "Equity Value — what the shareholders' remaining cash flows are worth today "
     "(brownfield).",
     "Σ FCFE(t) / (1 + Ke)^t for t ≥ 1, after servicing the opening debt.",
     "Roughly Enterprise Value minus the remaining debt.")
_kpi("discount_rate",
     "Discount Rate — the input rate used for Enterprise Value, LCOE and BCR "
     "(usually set equal to WACC). Equity Value is discounted at Ke instead.",
     "",
     "No IRR in brownfield mode: with entry value 0 there is no up-front "
     "investment, so IRR is undefined.")


def kpi_guide(key: str, sep: str = "\n") -> Optional[str]:
    """Return the hover text for one KPI card (None = no guidance).

    `sep` joins the lines — "\\n" for Tk labels, "\\n\\n" for Streamlit
    (markdown needs a blank line to break)."""
    entry = _K.get(key)
    if entry is None:
        return None
    what, formula, read = entry
    lines = [what]
    if formula:
        lines.append(f"Formula:  {formula}")
    if read:
        lines.append(f"Read:  {read}")
    return sep.join(lines)


# ════════════════════════════════════════════════════════════════════════
def guide_for(key: str, label: str = "", hint: str = "") -> Optional[str]:
    """Return the tooltip text for one parameter (None = no guidance)."""
    entry = _G.get(key)
    if entry is None:
        h = (hint or "").strip()
        return f"{label}\n{h}" if (label and h) else (h or None)
    desc, rng, impact = entry
    lines = [label.strip()] if label else []
    lines.append(desc)
    if rng:
        lines.append(f"Typical:  {rng}")
    if impact:
        lines.append(f"Impact:  {impact}")
    return "\n".join(l for l in lines if l)


def coverage() -> int:
    """Number of parameters with detailed guidance (used in tests)."""
    return len(_G)
