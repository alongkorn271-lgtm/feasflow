"""
Feasibility Engines Package
============================
Each plant type has its own self-contained engine module:

    engines.rdf        — Refuse-Derived Fuel (sell pellets to cement)
    engines.wte        — Waste-to-Energy (MSW → electricity)
    engines.rdf_wte    — Combined RDF + WTE
    engines.biogas     — Anaerobic digestion + gas engine
    engines.solar      — Solar PV (ground or floating)

Each module exports:

    InputsClass      — dataclass with plant-specific fields
    run_model(p)     — return dict with common output schema
    default_preset() — reference/example parameters
    INPUT_SECTIONS   — GUI input layout spec (for sidebar nav)
    META             — display metadata (label, icon, description)

The common shared math (IRR, NPV, WACC, debt, BOI, Dulong) lives in
engines.shared so each engine stays focused on plant-specific calcs.
"""

from . import shared
from . import rdf
from . import wte
from . import rdf_wte
from . import biogas
from . import solar

# Engine registry — keyed by short code used in the sidebar
REGISTRY = {
    "rdf":     rdf,
    "wte":     wte,
    "rdf_wte": rdf_wte,
    "biogas":  biogas,
    "solar":   solar,
}

__all__ = ["shared", "rdf", "wte", "rdf_wte", "biogas", "solar", "REGISTRY"]
