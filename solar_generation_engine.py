"""
solar_generation_engine.py
==========================
Monthly solar-generation engine for power-plant feasibility calculators.

This is a PURE-LOGIC module: no UI, no file I/O. Feed it a ``SolarInputs``
object, get back an ``EngineResult``. Drop it into any Python calculator
front-end (Tkinter, Streamlit, Flask, PySide, a notebook, ...).

It implements the standard two-stage floating-solar generation model:

    HourlyModel    ->  the 24-hour generation SHAPE of one typical day
    MonthlyEngine  ->  that shape reused across all 12 months, each month
                       scaled by the PVWatts monthly energy profile, so
                       real seasonal variation is captured.

Concept
-------
Sunlight over a day always has the same *shape*: a bell curve that rises
at dawn, peaks near noon, fades at dusk. What changes month to month is
the *size* of that bell -- a sunny March day produces far more than an
overcast December day. So the engine separates the two:

    hour_fraction[h]            <- HourlyModel:  shape normalised to sum 1.0
    daily_yield[month]          <- MonthlyEngine: kWh/kWp/day for that month
    generation[h][month] = capacity_kwp * daily_yield[month] * hour_fraction[h]

Summing the grid gives monthly and annual generation. Classifying each
hour against the TOU peak window gives the Peak / Off-peak split that a
feasibility model needs to value the energy.

Identity worth knowing: regardless of the hourly shape, the annual total
always equals  capacity_kwp * effective_yield  -- the shape only moves
energy *within* a day, the PVWatts profile distributes it *across* months.

Scope
-----
Solar generation only. No battery, no load allocation, no offtaker split.
Rate escalation and multi-year discounting belong to the calculator layer;
this module gives Year-1 physical generation plus an optional Year-1 value,
and a degradation helper for projecting later years.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# DEFAULTS  -- override any of these through SolarInputs
# ---------------------------------------------------------------------------

# PVWatts monthly AC energy (kWh) for a 400 kW reference system.
# Source: PVWatts report, Nakhon Si Thammarat, Thailand (NSRDB 8.45N, 99.98E
# NSRDB 8.45N 99.98E — fixed open-rack array.
PVWATTS_NAKHON_SI_THAMMARAT: list[float] = [
    51803, 57439, 63738, 51062, 45848, 42320,
    43852, 46612, 46856, 43563, 35552, 36971,
]
PVWATTS_REFERENCE_KW: float = 400.0          # system size the profile above is for

DAYS_IN_MONTH: list[int] = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_NAMES: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Typical-day generation shape, indexed by clock hour 0..23. Unitless weights
# -- only their relative size matters; the engine normalises them. This is a
# generic bell curve; replace it with site-measured hourly data if available.
DEFAULT_SOLAR_SHAPE: list[float] = [
    0, 0, 0, 0, 0, 0,            # 00:00 - 05:00  night
    0.5, 2, 5, 8, 11, 13,        # 06:00 - 11:00  morning ramp
    14, 13, 11, 8.5, 5.5, 2.5,   # 12:00 - 17:00  afternoon decline
    0.5, 0, 0, 0, 0, 0,          # 18:00 - 23:00  night
]


# ---------------------------------------------------------------------------
# INPUT SCHEMA
# ---------------------------------------------------------------------------

@dataclass
class SolarInputs:
    """All assumptions the engine needs. Only ``capacity_kwp`` is mandatory."""

    # --- solar system -----------------------------------------------------
    capacity_kwp: float                       # DC capacity of the solar plant

    # --- generation resource ---------------------------------------------
    # 12 monthly AC-energy values for a reference system, plus that system's
    # size. The engine derives the specific yield and the month-by-month
    # shares from these -- so swapping in a different site means editing
    # just these two fields.
    pvwatts_monthly_kwh: Sequence[float] = field(
        default_factory=lambda: list(PVWATTS_NAKHON_SI_THAMMARAT))
    pvwatts_reference_kw: float = PVWATTS_REFERENCE_KW

    # FPV cooling-gain factor: PVWatts assumes a fixed open-rack array.
    # Floating solar runs cooler over water and yields slightly more.
    # 1.00 = use PVWatts as-is (conservative); 1.03-1.08 = typical FPV gain.
    cooling_gain_factor: float = 1.00

    # --- hourly shape -----------------------------------------------------
    solar_shape: Sequence[float] = field(
        default_factory=lambda: list(DEFAULT_SOLAR_SHAPE))

    # --- calendar ---------------------------------------------------------
    days_in_month: Sequence[int] = field(
        default_factory=lambda: list(DAYS_IN_MONTH))
    weekdays_per_year: int = 261              # days the TOU peak window applies
    weekend_days_per_year: int = 104          # weekends + holidays (all off-peak)

    # --- time-of-use window ----------------------------------------------
    peak_start_hour: int = 9                  # peak applies for [start, end)
    peak_end_hour: int = 22                   # PEA large-service: Mon-Fri 09-22

    # --- optional valuation ----------------------------------------------
    # If both rates are given, the engine also returns the THB value of the
    # generated energy. Leave as None to get generation (kWh) only.
    peak_rate: float | None = None            # THB/kWh
    offpeak_rate: float | None = None         # THB/kWh

    # --- degradation ------------------------------------------------------
    # Used only by project_generation(); the base result is Year 1.
    annual_degradation: float = 0.0055        # fraction lost per year, yr 2+

    def validate(self) -> None:
        """Raise ValueError on malformed input. Called by run_engine()."""
        if self.capacity_kwp <= 0:
            raise ValueError("capacity_kwp must be positive")
        if len(self.pvwatts_monthly_kwh) != 12:
            raise ValueError("pvwatts_monthly_kwh must have 12 values")
        if len(self.days_in_month) != 12:
            raise ValueError("days_in_month must have 12 values")
        if len(self.solar_shape) != 24:
            raise ValueError("solar_shape must have 24 hourly values")
        if self.pvwatts_reference_kw <= 0:
            raise ValueError("pvwatts_reference_kw must be positive")
        if sum(self.solar_shape) <= 0:
            raise ValueError("solar_shape weights must sum to a positive value")
        if not (0 <= self.peak_start_hour < self.peak_end_hour <= 24):
            raise ValueError("require 0 <= peak_start_hour < peak_end_hour <= 24")
        rates = (self.peak_rate, self.offpeak_rate)
        if (rates[0] is None) != (rates[1] is None):
            raise ValueError("give both peak_rate and offpeak_rate, or neither")


# ---------------------------------------------------------------------------
# OUTPUT SCHEMA
# ---------------------------------------------------------------------------

@dataclass
class MonthlyResult:
    """One month's generation, mirroring a column of the MonthlyEngine sheet."""
    index: int                       # 0 = January
    name: str                        # 'Jan', ...
    days: int
    daily_yield: float               # kWh/kWp/day for this month
    generation_kwh: float            # total generation for the whole month
    peak_generation_kwh: float       # part falling in the TOU peak window
    offpeak_generation_kwh: float    # remainder (incl. all weekend generation)
    peak_value: float | None         # THB, None if no rates supplied
    offpeak_value: float | None
    total_value: float | None


@dataclass
class EngineResult:
    """Everything the engine produces for a Year-1 run."""
    inputs: SolarInputs

    # resource summary
    specific_yield_pvwatts: float    # kWh/kWp/yr implied by the PVWatts profile
    effective_yield: float           # after the FPV cooling-gain factor

    # HourlyModel outputs
    hour_fractions: list[float]      # 24 values, sum = 1.0
    tou_class: list[str]             # 24 values, 'Peak' or 'Off-peak'

    # MonthlyEngine outputs
    monthly: list[MonthlyResult]     # 12 entries, Jan..Dec
    # hourly_generation_by_month[m][h] = kWh generated in hour h on a typical
    # day of month m. This is the 24x12 grid of the MonthlyEngine sheet,
    # transposed to [month][hour] for natural Python iteration.
    hourly_generation_by_month: list[list[float]]

    # annual roll-up
    annual_generation_kwh: float
    annual_peak_kwh: float
    annual_offpeak_kwh: float
    annual_value: float | None       # THB, None if no rates supplied


# ---------------------------------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------------------------------

def compute_hour_fractions(solar_shape: Sequence[float]) -> list[float]:
    """HourlyModel: normalise the 24 shape weights so they sum to 1.0.

    Each returned value is the fraction of a day's generation that falls in
    that clock hour. Independent of plant size and of the month.
    """
    total = sum(solar_shape)
    return [w / total for w in solar_shape]


def classify_tou(peak_start_hour: int, peak_end_hour: int) -> list[str]:
    """HourlyModel: label each of the 24 clock hours 'Peak' or 'Off-peak'.

    An hour h is Peak when  peak_start_hour <= h < peak_end_hour.
    """
    return [
        "Peak" if peak_start_hour <= h < peak_end_hour else "Off-peak"
        for h in range(24)
    ]


def run_engine(inputs: SolarInputs) -> EngineResult:
    """Run the full HourlyModel + MonthlyEngine calculation for Year 1.

    Steps
    -----
    1. HourlyModel    -- normalise the shape, classify hours by TOU.
    2. Resource       -- specific yield from the PVWatts profile, then apply
                         the FPV cooling-gain factor.
    3. MonthlyEngine  -- per month: daily yield from the PVWatts share, then
                         the 24-hour generation grid, then the Peak/Off-peak
                         split using the weekday / weekend day counts.
    4. Roll up to annual totals (and value, if rates were supplied).
    """
    inputs.validate()

    # -- 1. HourlyModel ----------------------------------------------------
    hour_fractions = compute_hour_fractions(inputs.solar_shape)
    tou_class = classify_tou(inputs.peak_start_hour, inputs.peak_end_hour)
    peak_hours = [h for h in range(24) if tou_class[h] == "Peak"]
    offpeak_hours = [h for h in range(24) if tou_class[h] == "Off-peak"]

    # -- 2. Resource -------------------------------------------------------
    pvwatts_annual = sum(inputs.pvwatts_monthly_kwh)
    specific_yield_pvwatts = pvwatts_annual / inputs.pvwatts_reference_kw
    effective_yield = specific_yield_pvwatts * inputs.cooling_gain_factor

    has_rates = inputs.peak_rate is not None and inputs.offpeak_rate is not None

    # -- 3. MonthlyEngine --------------------------------------------------
    monthly: list[MonthlyResult] = []
    grid: list[list[float]] = []

    for m in range(12):
        days = inputs.days_in_month[m]

        # Share of the annual energy that this month contributes, then the
        # daily yield (kWh/kWp/day) implied for the month. Spreading the
        # annual yield by these shares and re-multiplying by days makes the
        # twelve months sum back to capacity * effective_yield exactly.
        month_share = inputs.pvwatts_monthly_kwh[m] / pvwatts_annual
        daily_yield = effective_yield * month_share / days

        # 24-hour generation for one typical day of this month (kWh/hour).
        hourly = [
            inputs.capacity_kwp * daily_yield * hour_fractions[h]
            for h in range(24)
        ]
        grid.append(hourly)

        daily_total = sum(hourly)                      # = capacity * daily_yield
        generation_kwh = daily_total * days

        # Weekday / weekend split, pro-rated like the Excel MonthlyEngine.
        weekday_days = days * inputs.weekdays_per_year / 365.0
        weekend_days = days * inputs.weekend_days_per_year / 365.0

        # On weekdays the peak window applies; on weekends every hour is
        # off-peak, so all weekend generation is off-peak energy.
        peak_per_day = sum(hourly[h] for h in peak_hours)
        offpeak_per_day = sum(hourly[h] for h in offpeak_hours)

        peak_generation = peak_per_day * weekday_days
        offpeak_generation = (offpeak_per_day * weekday_days
                              + daily_total * weekend_days)

        if has_rates:
            peak_value = peak_generation * inputs.peak_rate
            offpeak_value = offpeak_generation * inputs.offpeak_rate
            total_value = peak_value + offpeak_value
        else:
            peak_value = offpeak_value = total_value = None

        monthly.append(MonthlyResult(
            index=m,
            name=MONTH_NAMES[m],
            days=days,
            daily_yield=daily_yield,
            generation_kwh=generation_kwh,
            peak_generation_kwh=peak_generation,
            offpeak_generation_kwh=offpeak_generation,
            peak_value=peak_value,
            offpeak_value=offpeak_value,
            total_value=total_value,
        ))

    # -- 4. Annual roll-up -------------------------------------------------
    annual_generation = sum(r.generation_kwh for r in monthly)
    annual_peak = sum(r.peak_generation_kwh for r in monthly)
    annual_offpeak = sum(r.offpeak_generation_kwh for r in monthly)
    annual_value = (sum(r.total_value for r in monthly)  # type: ignore[misc]
                    if has_rates else None)

    return EngineResult(
        inputs=inputs,
        specific_yield_pvwatts=specific_yield_pvwatts,
        effective_yield=effective_yield,
        hour_fractions=hour_fractions,
        tou_class=tou_class,
        monthly=monthly,
        hourly_generation_by_month=grid,
        annual_generation_kwh=annual_generation,
        annual_peak_kwh=annual_peak,
        annual_offpeak_kwh=annual_offpeak,
        annual_value=annual_value,
    )


# ---------------------------------------------------------------------------
# PROJECTION HELPER  -- for the calculator's multi-year view
# ---------------------------------------------------------------------------

def degradation_factor(year: int, annual_degradation: float) -> float:
    """Performance factor for a given operating year (Year 1 = 1.0).

    Year 1 is full output; from Year 2 the plant loses ``annual_degradation``
    of its capacity each year, compounding.
    """
    if year < 1:
        raise ValueError("year is 1-indexed; the first operating year is 1")
    return (1.0 - annual_degradation) ** (year - 1)


def project_generation(result: EngineResult,
                        years: int,
                        annual_degradation: float | None = None) -> list[float]:
    """Annual generation (kWh) for each operating year 1..years.

    Applies compounding degradation to the Year-1 figure from ``result``.
    Rate escalation and discounting are intentionally left to the calculator
    layer -- this returns physical energy only.
    """
    deg = (result.inputs.annual_degradation
           if annual_degradation is None else annual_degradation)
    base = result.annual_generation_kwh
    return [base * degradation_factor(y, deg) for y in range(1, years + 1)]


# ---------------------------------------------------------------------------
# DEMO  -- runs only when this file is executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 2 MW floating-solar plant, PVWatts profile, PEA TOU rates.
    demo = SolarInputs(
        capacity_kwp=2000,
        peak_rate=4.40,
        offpeak_rate=2.80,
    )
    res = run_engine(demo)

    print("Solar generation engine -- demo run")
    print("=" * 60)
    print(f"  PVWatts specific yield : {res.specific_yield_pvwatts:,.0f} "
          f"kWh/kWp/yr")
    print(f"  Effective yield        : {res.effective_yield:,.0f} kWh/kWp/yr "
          f"(cooling gain {demo.cooling_gain_factor:.2f}x)")
    print(f"  Annual generation      : {res.annual_generation_kwh:,.0f} kWh")
    print(f"  Annual value           : {res.annual_value:,.0f} THB")
    print()
    print(f"  {'Month':5s} {'Daily yield':>12s} {'Generation':>14s} "
          f"{'Peak share':>11s}")
    for r in res.monthly:
        peak_share = r.peak_generation_kwh / r.generation_kwh
        print(f"  {r.name:5s} {r.daily_yield:9.2f}    "
              f"{r.generation_kwh:12,.0f}  {peak_share:10.1%}")
    print()

    # Sanity check: the hourly shape must not change the annual total.
    identity = demo.capacity_kwp * res.effective_yield
    print(f"  Check: capacity x effective_yield = {identity:,.0f} kWh "
          f"-> matches annual = {abs(identity - res.annual_generation_kwh) < 1}")

    # 25-year projection with degradation.
    proj = project_generation(res, years=25)
    print(f"  Year 1 generation      : {proj[0]:,.0f} kWh")
    print(f"  Year 25 generation     : {proj[-1]:,.0f} kWh "
          f"({proj[-1] / proj[0] - 1:+.1%} vs Year 1)")
