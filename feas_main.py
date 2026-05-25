"""
feas_main.py — Multi-engine feasibility dashboard.

Modern fintech-style layout:
  ┌──────┬─────────────────────────────────────────────────────────┐
  │      │  Welcome bar (greeting · subtitle · search · bell · user)│
  │ Side ├─────────────────────────────────────────────────────────┤
  │ bar  │ ┌── KPI cards (3 hero + 6 secondary) ────────────────┐  │
  │ (5   │ └────────────────────────────────────────────────────┘  │
  │ icons)│ ┌─Inputs (scroll)─┐ ┌─Charts + Cashflow Table ─────┐  │
  │      │ │                  │ │                                │  │
  │      │ └──────────────────┘ └────────────────────────────────┘  │
  └──────┴─────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import json, os, sys
from dataclasses import fields, asdict
from pathlib import Path
from typing import Optional, Any

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from engines import REGISTRY
from feas_theme import (
    apply_theme, make_card, make_kpi_card, make_pill_badge,
    make_sidebar_button, draw_sparkline, mpl_style_ax,
    status_color_irr, status_color_dscr, status_color_npv,
    kind_for_irr, kind_for_dscr, kind_for_npv,
    BG, CARD, CARD_SOFT, BORDER, DIVIDER,
    ACCENT, ACCENT_LT, ACCENT_SOFT, ACCENT_DK, LIME, LIME_LT,
    SIDEBAR_BG, SIDEBAR_ACTIVE_BG, SIDEBAR_ACTIVE_FG,
    SIDEBAR_TEXT, SIDEBAR_TEXT_DIM,
    TEXT, TEXT_SUB, TEXT_MUTED,
    SUCCESS, WARNING, ERROR, INFO,
    BADGE_POS_BG, BADGE_POS_FG, BADGE_NEG_BG, BADGE_NEG_FG,
    PASS, MARGINAL, FAIL, NEUTRAL,
    FF, F_DISPLAY, F_H1, F_H2, F_H3, F_BODY, F_BODY_B, F_SMALL, F_TINY,
    F_MONO, F_MONO_B, F_KPI,
    SIDEBAR_WIDTH, SIDEBAR_ITEM_HEIGHT, TOPBAR_HEIGHT,
)

DEBOUNCE_MS = 500
ENGINE_ORDER = ["rdf", "wte", "rdf_wte", "biogas", "solar"]

# Display names for sidebar items
ENGINE_LABELS = {
    "rdf":     "RDF",
    "wte":     "WTE",
    "rdf_wte": "RDF + WTE",
    "biogas":  "Biogas",
    "solar":   "Solar PV",
}


# ════════════════════════════════════════════════════════════════════════
class ScrollableFrame(tk.Frame):
    """Scrollable container with a modern CTkScrollbar (or ttk fallback)."""
    def __init__(self, master, bg=BG, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)

        # Use CTkScrollbar for modern rounded thumb when customtkinter available
        try:
            import customtkinter as _ctk
            self.vsb = _ctk.CTkScrollbar(
                self,
                orientation="vertical",
                command=self.canvas.yview,
                width=18,
                corner_radius=8,
                fg_color="#E2E8F0",          # track — light gray, always visible
                button_color="#7C8898",      # thumb — mid-dark gray
                button_hover_color="#5C6779",
            )
        except Exception:
            self.vsb = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)

        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                                 anchor="nw")
        # Pack scrollbar FIRST (right side) so it always reserves space
        self.vsb.pack(side="right", fill="y", padx=(2, 0))
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner.bind("<Configure>",
                          lambda _: self.canvas.configure(
                              scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                          lambda e: self.canvas.itemconfig(self._win, width=e.width))

        def on_mw(e):
            w = self.winfo_containing(e.x_root, e.y_root)
            if w and str(w).startswith(str(self.canvas)):
                self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", on_mw)


# ════════════════════════════════════════════════════════════════════════
class FeasApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Feasibility Studio")
        self.root.geometry("1820x1040")
        self.root.minsize(1440, 820)

        apply_theme(root)

        # State
        self.current_engine_code: str = "wte"
        self.current_engine = REGISTRY[self.current_engine_code]
        self.params: Any = self.current_engine.default_preset()
        self.results: Optional[dict] = None
        self.entries: dict[str, tk.Variable] = {}
        self._recalc_after: Optional[str] = None
        self._loading_params = False
        self._sparkline_history: dict[str, list[float]] = {}

        # Build UI
        self._build_layout()
        self._build_sidebar()
        self._build_topbar()
        self._build_content()

        self._load_engine(self.current_engine_code)

    # ───────────────────────────────────────────────────────────────
    def _build_layout(self):
        # Sidebar (white) | Right area (BG)
        self.sidebar_frame = tk.Frame(self.root, bg=SIDEBAR_BG,
                                        width=SIDEBAR_WIDTH,
                                        highlightbackground=BORDER,
                                        highlightthickness=0)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        # Thin divider between sidebar and main
        tk.Frame(self.root, bg=BORDER, width=1).pack(side="left", fill="y")

        right = tk.Frame(self.root, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self.topbar_frame = tk.Frame(right, bg=BG, height=TOPBAR_HEIGHT)
        self.topbar_frame.pack(side="top", fill="x")
        self.topbar_frame.pack_propagate(False)

        self.content_frame = tk.Frame(right, bg=BG)
        self.content_frame.pack(side="top", fill="both", expand=True)

    # ───────────────────────────────────────────────────────────────
    # Sidebar (white, pill active)
    # ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        # Brand area
        brand = tk.Frame(self.sidebar_frame, bg=SIDEBAR_BG, height=92)
        brand.pack(fill="x", pady=(0, 16))
        brand.pack_propagate(False)
        brand_inner = tk.Frame(brand, bg=SIDEBAR_BG)
        brand_inner.pack(expand=True)
        tk.Label(brand_inner, text="◢", font=(FF, 26, "bold"),
                  bg=SIDEBAR_BG, fg=ACCENT).pack(side="left", padx=(0, 10))
        tk.Label(brand_inner, text="FeasFlow", font=(FF, 18, "bold"),
                  bg=SIDEBAR_BG, fg=TEXT).pack(side="left")

        # Section label (uppercase tracker)
        tk.Label(self.sidebar_frame, text="MAIN  MENU", font=(FF, 9, "bold"),
                  bg=SIDEBAR_BG, fg=TEXT_MUTED, anchor="w"
                  ).pack(fill="x", padx=22, pady=(0, 8))

        # Engine items
        self.sidebar_items: dict = {}
        for code in ENGINE_ORDER:
            mod = REGISTRY[code]
            meta = mod.META
            btn = make_sidebar_button(
                self.sidebar_frame,
                icon=meta["icon"],
                label=ENGINE_LABELS.get(code, code.upper()),
                color=meta["color"],
                is_active=(code == self.current_engine_code),
                command=lambda c=code: self._load_engine(c),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.sidebar_items[code] = btn

        # Spacer to push version to bottom
        tk.Frame(self.sidebar_frame, bg=SIDEBAR_BG).pack(fill="both", expand=True)

        # Version footer
        tk.Label(self.sidebar_frame, text="v2.1  ·  multi-engine",
                  font=F_TINY, bg=SIDEBAR_BG, fg=TEXT_MUTED
                  ).pack(side="bottom", pady=16)

    def _refresh_sidebar(self):
        for w in self.sidebar_frame.winfo_children():
            w.destroy()
        self._build_sidebar()

    # ───────────────────────────────────────────────────────────────
    # Top bar — welcome + actions
    # ───────────────────────────────────────────────────────────────
    def _build_topbar(self):
        # Left: greeting block
        left = tk.Frame(self.topbar_frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=14)

        self.welcome_label = tk.Label(left, text="", font=F_DISPLAY,
                                        bg=BG, fg=TEXT, anchor="w",
                                        justify="left")
        self.welcome_label.pack(anchor="w", fill="x")
        self.welcome_sub = tk.Label(left, text="", font=F_SMALL,
                                      bg=BG, fg=TEXT_SUB, anchor="w",
                                      justify="left", wraplength=1100)
        self.welcome_sub.pack(anchor="w", fill="x", pady=(4, 0))

        # Right: actions
        right = tk.Frame(self.topbar_frame, bg=BG)
        right.pack(side="right", fill="y", padx=24, pady=20)

        def icon_btn(parent, glyph, command):
            b = tk.Button(parent, text=glyph, command=command,
                           bg=BG, fg=TEXT, font=(FF, 14),
                           relief="flat", bd=0, padx=10, pady=6,
                           activebackground=ACCENT_SOFT,
                           activeforeground=ACCENT_DK, cursor="hand2",
                           highlightthickness=0)
            return b

        def text_btn(parent, text, command, primary=False):
            bg = ACCENT if primary else CARD
            fg = "white" if primary else TEXT
            active_bg = ACCENT_DK if primary else BG
            b = tk.Button(parent, text=text, command=command,
                           bg=bg, fg=fg, font=F_BODY_B,
                           relief="flat", bd=0, padx=16, pady=8,
                           activebackground=active_bg,
                           activeforeground="white" if primary else ACCENT_DK,
                           cursor="hand2",
                           highlightbackground=BORDER, highlightthickness=1)
            return b

        text_btn(right, "📊 Export Excel", self._export_excel,
                  primary=True).pack(side="right", padx=(6, 0))
        text_btn(right, "PDF", self._export_pdf).pack(side="right", padx=4)
        text_btn(right, "Save", self._save_scenario).pack(side="right", padx=4)
        text_btn(right, "Load", self._load_scenario).pack(side="right", padx=4)
        text_btn(right, "↺ Reset", self._reset_to_preset).pack(side="right", padx=4)

        # Divider line
        tk.Frame(self.topbar_frame, bg=BORDER, height=1).pack(side="bottom", fill="x")

    def _update_topbar(self):
        meta = self.current_engine.META
        label = ENGINE_LABELS.get(self.current_engine_code, "")
        self.welcome_label.configure(text=f"{meta['icon']}  {label} feasibility")
        # Subtitle on two lines: description + project
        self.welcome_sub.configure(
            text=(f"{meta['description']}\n"
                   f"Project: {self.params.project_name}")
        )

    # ───────────────────────────────────────────────────────────────
    # Content area
    # ───────────────────────────────────────────────────────────────
    def _build_content(self):
        # Single scrollable outer — KPI hero on top, then 2-col below
        self.outer_scroll = ScrollableFrame(self.content_frame, bg=BG)
        self.outer_scroll.pack(fill="both", expand=True)

        outer = self.outer_scroll.inner

        # Status alert
        self.alert_holder = tk.Frame(outer, bg=BG)
        self.alert_holder.pack(fill="x", padx=24, pady=(12, 4))

        # Hero KPI row (3 large cards)
        self.hero_kpi_row = tk.Frame(outer, bg=BG)
        self.hero_kpi_row.pack(fill="x", padx=24, pady=(8, 8))

        # Secondary KPI row (6 smaller cards)
        self.sec_kpi_row = tk.Frame(outer, bg=BG)
        self.sec_kpi_row.pack(fill="x", padx=24, pady=(0, 12))

        # Two-column area: inputs (left) + everything else (right)
        cols = tk.Frame(outer, bg=BG)
        cols.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        self.input_col = tk.Frame(cols, bg=BG, width=440)
        self.input_col.pack(side="left", fill="y", padx=(0, 12))
        self.input_col.pack_propagate(False)
        self.input_scroll = ScrollableFrame(self.input_col, bg=BG)
        self.input_scroll.pack(fill="both", expand=True)

        self.output_col = tk.Frame(cols, bg=BG)
        self.output_col.pack(side="right", fill="both", expand=True)

    # ───────────────────────────────────────────────────────────────
    # Engine loader
    # ───────────────────────────────────────────────────────────────
    def _load_engine(self, code: str):
        if code not in REGISTRY:
            return
        self.current_engine_code = code
        self.current_engine = REGISTRY[code]
        self.params = self.current_engine.default_preset()
        # Reset sparkline history when switching engines
        self._sparkline_history.clear()
        self._refresh_sidebar()
        self._update_topbar()
        self._build_input_panel()
        self._populate_inputs()
        self._recalc(immediate=True)

    def _reset_to_preset(self):
        self.params = self.current_engine.default_preset()
        self._sparkline_history.clear()
        self._populate_inputs()
        self._recalc(immediate=True)

    # ───────────────────────────────────────────────────────────────
    # Input panel
    # ───────────────────────────────────────────────────────────────
    def _build_input_panel(self):
        for w in self.input_scroll.inner.winfo_children():
            w.destroy()
        self.entries.clear()
        for title, fld_list in self.current_engine.INPUT_SECTIONS:
            self._make_section(self.input_scroll.inner, title, fld_list)
        tk.Frame(self.input_scroll.inner, bg=BG, height=20).pack()

    def _make_section(self, parent, title, field_list):
        card = make_card(parent, title=title, padx=18, pady=14)
        card.pack(fill="x", padx=4, pady=6)
        for spec in field_list:
            self._make_field(card.body, *spec)

    def _make_field(self, parent, key, label, ftype, hint):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="Card.TLabel", width=22, anchor="w"
                  ).pack(side="left")
        if ftype == "bool":
            var = tk.BooleanVar()
            self.entries[key] = var
            cb = tk.Checkbutton(row, variable=var,
                                 bg=CARD, activebackground=CARD,
                                 highlightthickness=0, bd=0, fg=ACCENT,
                                 selectcolor=CARD,
                                 command=lambda k=key: self._on_input_change(k))
            cb.pack(side="left", padx=4)
        else:
            var = tk.StringVar()
            self.entries[key] = var
            if ftype.startswith("choice:"):
                options = ftype.split(":", 1)[1].split("|")
                w = ttk.Combobox(row, textvariable=var, values=options,
                                  state="readonly", width=16)
            else:
                w = ttk.Entry(row, textvariable=var, width=16)
            w.pack(side="left", padx=4)
            var.trace_add("write", lambda *a, k=key: self._on_input_change(k))
        if hint:
            ttk.Label(row, text=hint, style="CardSub.TLabel"
                      ).pack(side="left", padx=(4, 0))

    # ───────────────────────────────────────────────────────────────
    # Inputs ↔ params
    # ───────────────────────────────────────────────────────────────
    def _field_spec(self, key):
        for _t, lst in self.current_engine.INPUT_SECTIONS:
            for spec in lst:
                if spec[0] == key: return spec
        return None

    def _populate_inputs(self):
        self._loading_params = True
        try:
            for fld in fields(self.params):
                key = fld.name
                if key not in self.entries: continue
                val = getattr(self.params, key)
                spec = self._field_spec(key)
                if spec is None: continue
                _, _, ftype, _ = spec
                if ftype == "bool":
                    self.entries[key].set(bool(val)); continue
                if ftype == "pct":
                    s = f"{val * 100:.2f}"
                elif ftype == "float":
                    s = f"{val:.4f}".rstrip("0").rstrip(".")
                    if not s or s == "-": s = "0"
                elif ftype == "int":
                    s = f"{int(val)}"
                else:
                    s = str(val)
                self.entries[key].set(s)
        finally:
            self._loading_params = False

    def _read_inputs(self) -> bool:
        new_vals = {}
        for fld in fields(self.params):
            key = fld.name
            if key not in self.entries: continue
            spec = self._field_spec(key)
            if spec is None: continue
            _, _, ftype, _ = spec
            try:
                if ftype == "bool":
                    new_vals[key] = bool(self.entries[key].get()); continue
                raw = self.entries[key].get().strip()
                if ftype == "pct":
                    new_vals[key] = float(raw) / 100.0 if raw else 0.0
                elif ftype == "float":
                    new_vals[key] = float(raw) if raw else 0.0
                elif ftype == "int":
                    new_vals[key] = int(float(raw)) if raw else 0
                else:
                    new_vals[key] = raw
            except (ValueError, TypeError):
                return False
        for k, v in new_vals.items():
            setattr(self.params, k, v)
        return True

    # ───────────────────────────────────────────────────────────────
    # Recalc
    # ───────────────────────────────────────────────────────────────
    def _on_input_change(self, key):
        if self._loading_params: return
        self._schedule_recalc()

    def _schedule_recalc(self):
        if self._recalc_after is not None:
            try: self.root.after_cancel(self._recalc_after)
            except Exception: pass
        self._recalc_after = self.root.after(DEBOUNCE_MS, self._recalc)

    def _recalc(self, immediate=False):
        self._recalc_after = None
        if not self._read_inputs():
            return
        try:
            self.results = self.current_engine.run_model(self.params)
        except Exception as e:
            print(f"Engine error: {e}")
            return
        # Track sparkline history per metric
        self._track_sparklines()
        self._update_topbar()
        self._render_all()

    def _track_sparklines(self):
        """Maintain a rolling history (last 12 recalcs) per KPI for sparklines."""
        if not self.results: return
        k = self.results["kpis"]
        metrics = {
            "project_irr": (k.get("project_irr") or 0) * 100,
            "equity_irr":  (k.get("equity_irr")  or 0) * 100,
            "equity_npv":  k.get("equity_npv") or 0,
            "dscr_min":    k.get("dscr_min") or 0,
            "dscr_avg":    k.get("dscr_avg") or 0,
            "lcoe":        k.get("lcoe_thb_per_kwh") or k.get("lco_pellet_thb_per_ton") or 0,
            "bcr":         k.get("bcr") or 0,
            "payback":     k.get("payback_equity") or 0,
            "wacc":        (k.get("wacc") or 0) * 100,
        }
        for key, val in metrics.items():
            hist = self._sparkline_history.setdefault(key, [])
            hist.append(val)
            if len(hist) > 12:
                hist.pop(0)

    # ───────────────────────────────────────────────────────────────
    # Rendering
    # ───────────────────────────────────────────────────────────────
    def _render_all(self):
        for w in self.alert_holder.winfo_children():
            w.destroy()
        for w in self.hero_kpi_row.winfo_children():
            w.destroy()
        for w in self.sec_kpi_row.winfo_children():
            w.destroy()
        for w in self.output_col.winfo_children():
            w.destroy()

        self._render_alert()
        self._render_hero_kpis()
        self._render_secondary_kpis()
        self._render_generation()
        self._render_engine_specific()
        self._render_cashflow_table()
        self._render_core_charts()
        self._render_wacc_capex_carbon()

    def _render_alert(self):
        k = self.results["kpis"]
        eirr = k.get("equity_irr") or 0
        dscr = k.get("dscr_min")
        hurdle = 0.12
        if eirr < 0:
            msg = f"  Equity IRR {eirr*100:.2f}% — Project loses money under current assumptions"
            bg_bn = BADGE_NEG_BG; fg_bn = BADGE_NEG_FG; icon = "⚠"
        elif eirr < hurdle:
            msg = f"  Equity IRR {eirr*100:.2f}% below 12% hurdle — Marginal, consider tuning"
            bg_bn = "#FEF3C7"; fg_bn = "#92400E"; icon = "⚠"
        elif dscr is not None and dscr < 1.20:
            msg = f"  DSCR min {dscr:.2f} below 1.20 — Not bankable yet"
            bg_bn = "#FEF3C7"; fg_bn = "#92400E"; icon = "⚠"
        else:
            dscr_s = f"{dscr:.2f}" if dscr else "n/a"
            msg = f"  Equity IRR {eirr*100:.2f}% · DSCR min {dscr_s} — Project is viable"
            bg_bn = BADGE_POS_BG; fg_bn = BADGE_POS_FG; icon = "✓"
        pill = tk.Frame(self.alert_holder, bg=bg_bn,
                         highlightbackground=BORDER, highlightthickness=0)
        pill.pack(fill="x")
        inner = tk.Frame(pill, bg=bg_bn)
        inner.pack(fill="x", padx=18, pady=10)
        tk.Label(inner, text=icon, font=(FF, 13, "bold"),
                  bg=bg_bn, fg=fg_bn).pack(side="left")
        tk.Label(inner, text=msg, font=F_BODY_B,
                  bg=bg_bn, fg=fg_bn, anchor="w").pack(side="left")

    # ── Hero KPI cards (3 large) ─────────────────────────────────
    def _render_hero_kpis(self):
        k = self.results["kpis"]
        eirr = k.get("equity_irr") or 0
        pirr = k.get("project_irr") or 0
        npv = k.get("equity_npv") or 0

        def pct_badge(v, hurdle=0.12):
            if v is None or v == 0: return ("0%", "neutral")
            sign = "+" if v >= 0 else ""
            kind = "pos" if v >= hurdle else ("warn" if v >= 0 else "neg")
            return (f"{sign}{v*100:.2f}%", kind)

        hero = [
            ("Project IRR",  f"{pirr*100:.2f}%",  pct_badge(pirr - 0.12),
              "vs 12% hurdle",  "project_irr"),
            ("Equity IRR",   f"{eirr*100:.2f}%",  pct_badge(eirr - 0.12),
              "after debt service",  "equity_irr"),
            ("Equity NPV",   f"{npv:,.0f} MB",
             (f"{'+' if npv >= 0 else ''}{npv:.1f} MB",
              "pos" if npv >= 0 else "neg"),
             f"@ {asdict(self.params).get('discount_rate', 0.0625)*100:.2f}%",
             "equity_npv"),
        ]
        for i, (lbl, val, (badge_txt, badge_kind), sub, key) in enumerate(hero):
            card = make_kpi_card(
                self.hero_kpi_row,
                label=lbl, value=val,
                sparkline_values=self._sparkline_history.get(key, []),
                badge_text=badge_txt, badge_kind=badge_kind,
                sub=sub,
            )
            card.grid(row=0, column=i, sticky="nsew", padx=6)
        for i in range(3):
            self.hero_kpi_row.columnconfigure(i, weight=1, uniform="hero")

    # ── Secondary KPI cards (6 smaller) ──────────────────────────
    def _render_secondary_kpis(self):
        k = self.results["kpis"]
        engine_type = self.results.get("engine_type", "")
        is_rdf = engine_type == "rdf"

        cost_lbl = "LCO-Pellet" if is_rdf else "LCOE"
        cost_val = (f"{k.get('lco_pellet_thb_per_ton', 0):.0f}"
                     if is_rdf
                     else f"{k.get('lcoe_thb_per_kwh', 0):.2f}")
        cost_sub = "฿/ton RDF" if is_rdf else "฿/kWh"

        def dscr_kind(v):
            if v is None: return "neutral"
            return "pos" if v >= 1.30 else ("warn" if v >= 1.20 else "neg")

        cards = [
            ("DSCR min",    f"{(k.get('dscr_min') or 0):.2f}",
             ("≥1.30 = bank", dscr_kind(k.get("dscr_min"))),
             "≥ 1.30 bankable", "dscr_min"),
            ("DSCR avg",    f"{(k.get('dscr_avg') or 0):.2f}",
             ("lifetime", dscr_kind(k.get("dscr_avg"))),
             "average", "dscr_avg"),
            (cost_lbl, cost_val, ("", "neutral"), cost_sub, "lcoe"),
            ("BCR", f"{(k.get('bcr') or 0):.2f}x",
             ("> 1", "pos" if (k.get("bcr") or 0) >= 1 else "neg"),
             "PV ratio", "bcr"),
            ("Payback", f"{(k.get('payback_equity') or 0):.1f} yr",
             ("equity", "pos" if (k.get("payback_equity") or 99) <= 10 else "warn"),
             "from COD", "payback"),
            ("WACC",     f"{(k.get('wacc') or 0)*100:.2f}%",
             ("CAPM", "neutral"), "discount rate", "wacc"),
        ]
        for i, (lbl, val, (badge_txt, badge_kind), sub, key) in enumerate(cards):
            card = make_kpi_card(
                self.sec_kpi_row,
                label=lbl, value=val,
                sparkline_values=self._sparkline_history.get(key, []),
                badge_text=badge_txt, badge_kind=badge_kind,
                sub=sub,
            )
            card.grid(row=0, column=i, sticky="nsew", padx=6)
        for i in range(len(cards)):
            self.sec_kpi_row.columnconfigure(i, weight=1, uniform="sec")

    def _render_generation(self):
        gen = self.results["generation"]
        cx = self.results["capex"]
        card = make_card(self.output_col, title="Generation · Feedstock · CAPEX")
        card.pack(fill="x", padx=4, pady=4)
        rows = self._build_generation_summary_rows(gen, cx)
        for i, (lbl, val) in enumerate(rows):
            r, c = divmod(i, 3)
            cell = tk.Frame(card.body, bg=CARD)
            cell.grid(row=r, column=c, sticky="w", padx=14, pady=6)
            tk.Label(cell, text=lbl, font=F_TINY, bg=CARD, fg=TEXT_MUTED,
                      anchor="w").pack(anchor="w")
            tk.Label(cell, text=val, font=F_BODY_B, bg=CARD, fg=TEXT,
                      anchor="w").pack(anchor="w")
        for i in range(3):
            card.body.columnconfigure(i, weight=1)

    def _build_generation_summary_rows(self, gen, cx):
        et = self.current_engine_code
        rows = []
        if et in ("wte", "rdf_wte", "biogas", "solar"):
            if gen.get("mwh_yr") is not None:
                rows.append(("Net Generation", f"{gen['mwh_yr']:,.0f} MWh/yr"))
        if et == "wte":
            rows += [
                ("Feedstock Required", f"{gen.get('msw_ton_per_yr', 0):,.0f} t/yr "
                                         f"({gen.get('msw_ton_per_day', 0):,.0f} t/d)"),
                ("Ash Output", f"{gen.get('ash_ton_yr', 0):,.0f} t/yr"),
                ("LHV", f"{gen.get('lhv_kcal_per_kg', 0):,.0f} kcal/kg "
                          f"({gen.get('lhv_mj_per_kg', 0):.2f} MJ/kg)"),
            ]
        elif et == "rdf":
            rows += [
                ("MSW Intake", f"{gen.get('msw_intake_t_yr', 0):,.0f} t/yr "
                                f"({gen.get('msw_intake_t_d', 0):,.0f} t/d)"),
                ("RDF Output", f"{gen.get('rdf_output_t_yr', 0):,.0f} t/yr "
                                f"({gen.get('rdf_output_t_d', 0):,.0f} t/d)"),
                ("RDF Price", f"{gen.get('rdf_price_thb_per_ton', 0):,.0f} ฿/ton"),
                ("LHV", f"{gen.get('lhv_kcal_per_kg', 0):,.0f} kcal/kg"),
            ]
        elif et == "rdf_wte":
            rows += [
                ("MSW Intake", f"{gen.get('msw_intake_t_yr', 0):,.0f} t/yr"),
                ("RDF Output", f"{gen.get('rdf_output_t_yr', 0):,.0f} t/yr"),
                ("Split (RDF/WTE)", f"{gen.get('rdf_split_pct', 0)*100:.0f}% / "
                                       f"{(1-gen.get('rdf_split_pct', 0))*100:.0f}%"),
                ("LHV", f"{gen.get('lhv_kcal_per_kg', 0):,.0f} kcal/kg"),
            ]
        elif et == "biogas":
            rows += [
                ("Feedstock Volume", f"{gen.get('feedstock_m3_yr', 0):,.0f} m³/yr"),
                ("Biogas Total", f"{gen.get('biogas_m3_yr', 0):,.0f} m³/yr"),
                ("kWh / m³ feed", f"{gen.get('kwh_per_m3', 0):.2f}"),
            ]
        elif et == "solar":
            rows += [
                ("Annual kWh", f"{gen.get('annual_kwh', 0):,.0f}"),
                ("Capacity Factor", f"{gen.get('capacity_factor', 0)*100:.2f} %"),
                ("Peak Ratio", f"{gen.get('peak_ratio', 0)*100:.1f} %"),
            ]
        rows += [
            ("CAPEX Total", f"{cx['total_capex']:,.1f} MB"
                              + (f"  ·  {cx['capex_per_mw_installed']:.0f} MB/MW"
                                 if cx['capex_per_mw_installed'] > 0 else "")),
            ("Equity / Debt", f"{cx['equity']:,.1f} / {cx['debt']:,.1f} MB"),
        ]
        return rows

    def _render_engine_specific(self):
        raw = self.results["raw_material"]
        et = self.current_engine_code
        if et in ("wte", "rdf", "rdf_wte") and raw.get("chemistry"):
            self._render_msw_chemistry_card(raw)
        elif et == "biogas":
            self._render_biogas_chain_card(raw)
        elif et == "solar":
            self._render_solar_card(raw)

    def _render_msw_chemistry_card(self, raw):
        chem = raw["chemistry"]
        card = make_card(self.output_col, title="MSW Chemistry — Dulong's Formula")
        card.pack(fill="x", padx=4, pady=4)
        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x", pady=(0, 8))

        viab_kind = ("pos" if chem.get("viable_target") else
                       ("warn" if chem.get("viable_min") else "neg"))
        viab_text = ("VIABLE" if chem.get("viable_target") else
                      "Marginal" if chem.get("viable_min") else "NOT VIABLE")

        tk.Label(head,
                  text=f"LHV  {chem['lhv_kcal_per_kg']:,.0f} kcal/kg",
                  font=F_H1, bg=CARD, fg=TEXT).pack(side="left")
        tk.Label(head,
                  text=f"   ({chem['lhv_mj_per_kg']:.2f} MJ/kg)",
                  font=F_BODY, bg=CARD, fg=TEXT_SUB).pack(side="left")
        make_pill_badge(head, viab_text, kind=viab_kind
                          ).pack(side="left", padx=(8, 0))

        body = tk.Frame(card.body, bg=CARD)
        body.pack(fill="x")

        c1 = tk.Frame(body, bg=CARD); c1.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        tk.Label(c1, text="Elements (% wet weight)",
                  font=F_BODY_B, bg=CARD, fg=TEXT_SUB).pack(anchor="w", pady=(0, 4))
        for elem in ("C", "H", "O", "N", "S", "Ash"):
            r = tk.Frame(c1, bg=CARD); r.pack(fill="x", pady=2)
            tk.Label(r, text=elem, font=F_BODY, bg=CARD, fg=TEXT_SUB,
                      width=8, anchor="w").pack(side="left")
            tk.Label(r, text=f"{chem['totals'][elem]:>8.3f}  %", font=F_MONO,
                      bg=CARD, fg=TEXT).pack(side="left")

        c2 = tk.Frame(body, bg=CARD); c2.grid(row=0, column=1, sticky="nw")
        tk.Label(c2, text="Component HHV Contribution",
                  font=F_BODY_B, bg=CARD, fg=TEXT_SUB).pack(anchor="w", pady=(0, 4))
        h = tk.Frame(c2, bg=CARD); h.pack(fill="x")
        for hdr, w in [("Component", 14), ("Wet %", 8), ("HHV", 13)]:
            tk.Label(h, text=hdr, font=F_SMALL, bg=CARD, fg=TEXT_MUTED,
                      width=w, anchor="w" if hdr == "Component" else "e"
                      ).pack(side="left")
        for cname, cdata in chem["per_component"].items():
            if cdata["wet_pct"] <= 0: continue
            r = tk.Frame(c2, bg=CARD); r.pack(fill="x")
            tk.Label(r, text=cname.capitalize(), font=F_BODY,
                      bg=CARD, fg=TEXT, width=14, anchor="w").pack(side="left")
            tk.Label(r, text=f"{cdata['wet_pct']:.1f}%", font=F_MONO,
                      bg=CARD, fg=TEXT_SUB, width=8, anchor="e").pack(side="left")
            tk.Label(r, text=f"{cdata['hhv_contrib']:>8,.1f}", font=F_MONO,
                      bg=CARD, fg=TEXT, width=13, anchor="e").pack(side="left")
        # Total
        rt = tk.Frame(c2, bg=ACCENT_SOFT); rt.pack(fill="x", pady=(4, 0))
        tk.Label(rt, text="TOTAL HHV", font=F_BODY_B,
                  bg=ACCENT_SOFT, fg=ACCENT_DK, width=14, anchor="w"
                  ).pack(side="left", padx=2, pady=4)
        tk.Label(rt, text=f"{chem['hhv_kcal_per_kg']:>8,.1f}",
                  font=F_MONO_B, bg=ACCENT_SOFT, fg=ACCENT_DK,
                  width=20, anchor="e").pack(side="left", padx=2, pady=4)

        for c in range(2):
            body.columnconfigure(c, weight=1, uniform="msw")

    def _render_biogas_chain_card(self, raw):
        card = make_card(self.output_col,
                          title="Biogas Chemistry Chain (COD → kWh)")
        card.pack(fill="x", padx=4, pady=4)
        head = tk.Frame(card.body, bg=CARD); head.pack(fill="x", pady=(0, 8))
        tk.Label(head,
                  text=f"{raw['biogas_m3_per_m3']:.2f} m³-biogas/m³ feed   →   "
                       f"{raw['kwh_per_m3']:.2f} kWh/m³",
                  font=F_H1, bg=CARD, fg=TEXT).pack(side="left")

        body = tk.Frame(card.body, bg=CARD); body.pack(fill="x")
        cols_data = [
            ("Chemistry (per 1 m³ feed)", [
                ("COD Load",       f"{raw['cod_load_kg_per_m3']:.2f} kg-COD"),
                ("COD Removed",    f"{raw['cod_removed_kg_per_m3']:.2f} kg"),
                ("CH₄ Produced",   f"{raw['ch4_m3_per_m3']:.2f} m³-CH₄"),
                ("Biogas",         f"{raw['biogas_m3_per_m3']:.2f} m³-biogas"),
                ("LHV",            f"{raw['lhv_mj_per_m3']:.2f} MJ/m³-bg"),
                ("Thermal",        f"{raw['energy_thermal_mj_per_m3']:.1f} MJ"),
                ("kWh / m³ feed",  f"{raw['kwh_per_m3']:.2f} kWh"),
            ]),
            ("Required Volume", [
                ("Target gen",  f"{raw['target_mwh_yr']:,.0f} MWh/yr"),
                ("m³ / day",    f"{raw['m3_per_day']:,.0f}"),
                ("m³ / yr",     f"{raw['m3_per_yr']:,.0f}"),
            ]),
            ("Cost", [
                ("Total ฿/m³ feed",  f"{raw['total_cost_thb_per_m3']:.2f}"),
                ("฿ / m³ biogas",    f"{raw['cost_per_m3_biogas']:.3f}"),
                ("฿ / kWh feed",     f"{raw['cost_per_kwh_feedstock']:.4f}"),
                ("Annual feed cost", f"{raw['feedstock_cost_mb_yr']:.2f} MB/yr"),
            ]),
        ]
        for ci, (title_col, items) in enumerate(cols_data):
            c = tk.Frame(body, bg=CARD)
            c.grid(row=0, column=ci, sticky="nw",
                    padx=(0 if ci == 0 else 12, 12 if ci < 2 else 0))
            tk.Label(c, text=title_col, font=F_BODY_B,
                      bg=CARD, fg=TEXT_SUB).pack(anchor="w", pady=(0, 4))
            for lbl, val in items:
                r = tk.Frame(c, bg=CARD); r.pack(fill="x", pady=2)
                tk.Label(r, text=lbl, font=F_BODY, bg=CARD, fg=TEXT_SUB,
                          width=18, anchor="w").pack(side="left")
                tk.Label(r, text=val, font=F_MONO_B, bg=CARD, fg=TEXT
                          ).pack(side="left")
        for c in range(3):
            body.columnconfigure(c, weight=1, uniform="bio")

    def _render_solar_card(self, raw):
        card = make_card(self.output_col, title="Solar Generation — PVWatts + TOU")
        card.pack(fill="x", padx=4, pady=4)
        head = tk.Frame(card.body, bg=CARD); head.pack(fill="x", pady=(0, 8))
        tk.Label(head,
                  text=f"{raw['annual_generation_kwh']/1000:,.0f} MWh/yr",
                  font=F_H1, bg=CARD, fg=TEXT).pack(side="left")
        tk.Label(head,
                  text=f"   ·  CF {raw['capacity_factor']*100:.1f}%  ·  "
                       f"Yield {raw['effective_yield']:,.0f} kWh/kWp/yr",
                  font=F_BODY, bg=CARD, fg=TEXT_SUB).pack(side="left")

        body = tk.Frame(card.body, bg=CARD); body.pack(fill="x")
        c1 = tk.Frame(body, bg=CARD); c1.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        tk.Label(c1, text="Resource", font=F_BODY_B,
                  bg=CARD, fg=TEXT_SUB).pack(anchor="w", pady=(0, 4))
        for lbl, val in [
            ("Location",         raw['location']),
            ("Capacity",         f"{raw['capacity_kwp']:,.0f} kWp"),
            ("PVWatts yield",    f"{raw['specific_yield']:,.1f}"),
            ("Cooling gain",     f"{raw['cooling_gain']:.2f} ×"),
            ("Effective yield",  f"{raw['effective_yield']:,.1f}"),
            ("Capacity factor",  f"{raw['capacity_factor']*100:.2f} %"),
            ("Peak share",       f"{raw['peak_ratio']*100:.1f} %"),
            ("Annual revenue",   f"{(raw['annual_value_thb'] or 0)/1e6:.2f} MB/yr"),
        ]:
            r = tk.Frame(c1, bg=CARD); r.pack(fill="x", pady=2)
            tk.Label(r, text=lbl, font=F_BODY, bg=CARD, fg=TEXT_SUB,
                      width=18, anchor="w").pack(side="left")
            tk.Label(r, text=str(val), font=F_MONO, bg=CARD, fg=TEXT
                      ).pack(side="left")

        c2 = tk.Frame(body, bg=CARD); c2.grid(row=0, column=1, sticky="nw")
        tk.Label(c2, text="Monthly Generation", font=F_BODY_B,
                  bg=CARD, fg=TEXT_SUB).pack(anchor="w", pady=(0, 4))
        h = tk.Frame(c2, bg=CARD); h.pack(fill="x")
        for hdr, w in [("Mo", 5), ("kWh/kWp/d", 10), ("MWh", 9), ("Peak%", 7)]:
            tk.Label(h, text=hdr, font=F_SMALL, bg=CARD, fg=TEXT_MUTED,
                      width=w, anchor="e").pack(side="left")
        for m in raw['monthly']:
            r = tk.Frame(c2, bg=CARD); r.pack(fill="x")
            tk.Label(r, text=m['name'], font=F_BODY,
                      bg=CARD, fg=TEXT, width=5, anchor="e").pack(side="left")
            tk.Label(r, text=f"{m['daily_yield']:.2f}", font=F_MONO,
                      bg=CARD, fg=TEXT_SUB, width=10, anchor="e").pack(side="left")
            tk.Label(r, text=f"{m['generation_kwh']/1000:,.1f}", font=F_MONO,
                      bg=CARD, fg=TEXT, width=9, anchor="e").pack(side="left")
            tk.Label(r, text=f"{m['peak_share']*100:.1f}%", font=F_MONO,
                      bg=CARD, fg=TEXT_SUB, width=7, anchor="e").pack(side="left")
        for c in range(2):
            body.columnconfigure(c, weight=1, uniform="sol")

    def _render_cashflow_table(self):
        card = make_card(self.output_col,
                          title="Cashflow Table (year-by-year, MB THB)",
                          padx=14, pady=10)
        card.pack(fill="x", padx=4, pady=4)
        cols = ("yr", "rev", "opex", "ebitda", "dep", "ebit", "int", "tax",
                "npat", "ocf", "dscr", "fcfe", "cumfcfe")
        headings = ("Yr", "Revenue", "OPEX", "EBITDA", "Dep", "EBIT",
                    "Interest", "Tax", "NPAT", "OCF", "DSCR", "FCFE", "Σ FCFE")
        tv = ttk.Treeview(card.body, columns=cols, show="headings", height=14)
        widths = (38, 82, 76, 76, 60, 68, 72, 60, 68, 68, 60, 70, 82)
        for c, h, w in zip(cols, headings, widths):
            tv.heading(c, text=h, anchor="e")
            tv.column(c, width=w, anchor="e")
        tv.column("yr", anchor="center")
        tv.pack(fill="x")
        tv.tag_configure("neg", foreground=ERROR)
        tv.tag_configure("pos", foreground=SUCCESS)
        tv.tag_configure("dscr_low", background="#FEF2F2")
        cum = 0
        for r in self.results["rows"]:
            cum += r["fcfe"]
            tags = ["neg" if cum < 0 else "pos"]
            if r["dscr"] < 1.20 and r["principal_repay"] > 0:
                tags.append("dscr_low")
            dscr_v = f"{r['dscr']:.2f}" if r['dscr'] < 1e9 else "inf"
            tv.insert("", "end", values=(
                r["year"], f"{r['revenue']:,.1f}", f"{r['opex']:,.1f}",
                f"{r['ebitda']:,.1f}", f"{r['depreciation']:,.1f}",
                f"{r['ebit']:,.1f}", f"{r['interest']:,.1f}",
                f"{r['tax']:,.1f}", f"{r['npat']:,.1f}",
                f"{r['ocf']:,.1f}", dscr_v,
                f"{r['fcfe']:,.1f}", f"{cum:,.1f}",
            ), tags=tuple(tags))

    def _render_core_charts(self):
        card = make_card(self.output_col, title="Visualizations")
        card.pack(fill="x", padx=4, pady=4)
        # Bigger figure with more vertical space — 2x2 grid stretched out
        fig = Figure(figsize=(14, 11), dpi=92, facecolor=CARD)
        # Fix the rendered height so charts don't get squished
        canvas = FigureCanvasTkAgg(fig, master=card.body)
        widget = canvas.get_tk_widget()
        widget.configure(height=820)
        widget.pack(fill="x", expand=False)

        rows = self.results["rows"]
        yrs = [r["calendar_year"] for r in rows]

        ax1 = fig.add_subplot(2, 2, 1)
        ax2 = fig.add_subplot(2, 2, 2)
        ax3 = fig.add_subplot(2, 2, 3)
        ax4 = fig.add_subplot(2, 2, 4)

        # 1. Revenue stack + NPAT
        fit_r = [r["fit_rev"]    for r in rows]
        tip_r = [r["tip_rev"]    for r in rows]
        rdf_r = [r["rdf_rev"]    for r in rows]
        car_r = [r["carbon_rev"] for r in rows]
        npat  = [r["npat"]       for r in rows]
        bot = [0] * len(yrs)
        if any(fit_r):
            ax1.bar(yrs, fit_r, color=ACCENT_DK, label="Electricity / FiT", alpha=0.95)
            bot = list(fit_r)
        if any(tip_r):
            ax1.bar(yrs, tip_r, bottom=bot, color=LIME, label="Tipping", alpha=0.95)
            bot = [b + t for b, t in zip(bot, tip_r)]
        if any(rdf_r):
            ax1.bar(yrs, rdf_r, bottom=bot, color=LIME_LT, label="RDF Sales", alpha=0.95)
            bot = [b + r for b, r in zip(bot, rdf_r)]
        if any(c > 0 for c in car_r):
            ax1.bar(yrs, car_r, bottom=bot, color=ACCENT_LT, label="Carbon", alpha=0.95)
        ax1.plot(yrs, npat, color=TEXT, linewidth=1.8, marker="o", markersize=3,
                  label="NPAT")
        mpl_style_ax(ax1, "Revenue Composition + NPAT (MB/yr)")
        ax1.legend(fontsize=8, loc="upper left", framealpha=0.95)

        # 2. Cumulative FCFE
        cum_e = self.results["cum_fcfe"]
        cum_p = self.results["cum_fcff"]
        ax2.fill_between(yrs, cum_e, 0, color=ACCENT, alpha=0.16,
                          where=[v >= 0 for v in cum_e], interpolate=True)
        ax2.fill_between(yrs, cum_e, 0, color=ERROR, alpha=0.10,
                          where=[v < 0 for v in cum_e], interpolate=True)
        ax2.plot(yrs, cum_p, color=TEXT_MUTED, linewidth=1.4, linestyle="--",
                  label="Cum FCFF")
        ax2.plot(yrs, cum_e, color=ACCENT_DK, linewidth=2.4, label="Cum FCFE")
        ax2.axhline(0, color=TEXT_MUTED, linewidth=1, alpha=0.6)
        pb = self.results["kpis"].get("payback_equity")
        if pb is not None and pb < len(yrs):
            ax2.axvline(yrs[0] + pb - 1, color=WARNING, linestyle=":",
                         linewidth=1.5, label=f"Payback ~{pb:.1f}yr")
        mpl_style_ax(ax2, "Cumulative Cash Flow (MB)")
        ax2.legend(fontsize=8, loc="lower right")

        # 3. DSCR profile
        dscr = [r["dscr"] if r["dscr"] < 1e9 else None for r in rows]
        valid = [(y, d) for y, d in zip(yrs, dscr) if d is not None]
        if valid:
            vy, vd = zip(*valid)
            colors = [ACCENT if d >= 1.30 else (WARNING if d >= 1.20 else ERROR)
                       for d in vd]
            ax3.bar(vy, vd, color=colors, alpha=0.9, width=0.7)
            ax3.axhline(1.30, color=ACCENT_DK, linestyle="--", linewidth=1,
                         label="Bank 1.30x")
            ax3.axhline(1.20, color=WARNING, linestyle="--", linewidth=1,
                         label="Min 1.20x")
        mpl_style_ax(ax3, "DSCR Profile")
        ax3.legend(fontsize=8, loc="upper right")

        # 4. OPEX breakdown
        keys = [
            ("opex_om",        "O&M",       ACCENT_DK),
            ("opex_feedstock", "Feedstock", "#65A30D"),
            ("opex_ash",       "Ash",       "#A16207"),
            ("opex_flue",      "Flue Gas",  "#CA8A04"),
            ("opex_aux",       "Aux/Transport", LIME),
            ("opex_sga",       "SG&A",      LIME_LT),
            ("opex_insurance", "Insurance", "#06B6D4"),
            ("opex_pdf",       "PDF/Misc",  "#8B5CF6"),
        ]
        bot = [0] * len(yrs)
        for k_, lbl, col in keys:
            vals = [r.get(k_, 0) for r in rows]
            if not any(vals): continue
            ax4.bar(yrs, vals, bottom=bot, color=col, label=lbl, alpha=0.95)
            bot = [b + v for b, v in zip(bot, vals)]
        mpl_style_ax(ax4, "OPEX Breakdown (MB/yr)")
        ax4.legend(fontsize=7, loc="upper left", ncol=2)

        # More breathing room between subplots to avoid title/legend overlap
        fig.subplots_adjust(left=0.07, right=0.97, top=0.94, bottom=0.07,
                             hspace=0.42, wspace=0.22)
        canvas.draw()

    def _render_wacc_capex_carbon(self):
        card = make_card(self.output_col,
                          title="WACC (CAPM) · CAPEX · Carbon")
        card.pack(fill="x", padx=4, pady=(4, 14))
        w = self.results["wacc"]
        cx = self.results["capex"]
        carbon = self.results.get("carbon", {})
        items = [
            ("Rf",          f"{w['rf']*100:.2f}%"),
            ("MRP",         f"{w['mrp']*100:.2f}%"),
            ("β unlevered", f"{w['beta_unlevered']:.3f}"),
            ("β levered",   f"{w['beta_levered']:.3f}"),
            ("Ke",          f"{w['ke']*100:.2f}%"),
            ("Kd",          f"{w['kd']*100:.2f}%"),
            ("Kd after-tax",f"{w['kd_aftertax']*100:.2f}%"),
            ("D/E",         f"{w['de_ratio']:.3f}"),
            ("WACC",        f"{w['wacc']*100:.2f}%"),
            ("─────",       "─────"),
            ("EPC",         f"{cx['epc']:,.1f} MB"),
            ("Owner",       f"{cx['owner_cost']:,.1f} MB"),
            ("Contingency", f"{cx['contingency']:,.1f} MB"),
            ("IDC",         f"{cx['idc']:,.1f} MB"),
            ("TOTAL CAPEX", f"{cx['total_capex']:,.1f} MB"),
            ("Equity",      f"{cx['equity']:,.1f} MB"),
            ("Debt",        f"{cx['debt']:,.1f} MB"),
            ("─────",       "─────"),
            ("Carbon credit", f"{carbon.get('rev_mb_yr', 0):.2f} MB/yr"),
            ("Avoided CO₂",   f"{carbon.get('tco2_yr', 0):,.0f} t/yr"),
        ]
        for i, (lbl, val) in enumerate(items):
            r, c = divmod(i, 4)
            cell = tk.Frame(card.body, bg=CARD)
            cell.grid(row=r, column=c, sticky="w", padx=14, pady=4)
            tk.Label(cell, text=lbl, font=F_TINY, bg=CARD, fg=TEXT_MUTED,
                      anchor="w").pack(anchor="w")
            tk.Label(cell, text=val, font=F_BODY_B, bg=CARD, fg=TEXT,
                      anchor="w").pack(anchor="w")
        for c in range(4):
            card.body.columnconfigure(c, weight=1)

    # ───────────────────────────────────────────────────────────────
    # Save / Load / Export
    # ───────────────────────────────────────────────────────────────
    def _save_scenario(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON scenario", "*.json"), ("All", "*.*")],
            initialdir=_DIR,
            initialfile=f"{self.current_engine_code}_"
                         f"{self.params.project_name.replace(' ', '_')}.json",
        )
        if not path: return
        if not self._read_inputs():
            messagebox.showerror("Save", "Invalid input.")
            return
        try:
            data = {"engine": self.current_engine_code, "params": asdict(self.params)}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Save", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save", str(e))

    def _load_scenario(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON scenario", "*.json"), ("All", "*.*")],
            initialdir=_DIR,
        )
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            engine_code = data.get("engine", self.current_engine_code)
            if engine_code in REGISTRY:
                self.current_engine_code = engine_code
                self.current_engine = REGISTRY[engine_code]
            InputsCls = type(self.current_engine.default_preset())
            self.params = InputsCls(**data.get("params", data))
            self._refresh_sidebar()
            self._update_topbar()
            self._build_input_panel()
            self._populate_inputs()
            self._recalc(immediate=True)
        except Exception as e:
            messagebox.showerror("Load", str(e))

    def _export_excel(self):
        if not self._read_inputs(): return
        try:
            self.results = self.current_engine.run_model(self.params)
        except Exception as e:
            messagebox.showerror("Export", str(e)); return
        safe = self.params.project_name.replace(" ", "_").replace("/", "-")
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("All", "*.*")],
            initialdir=_DIR,
            initialfile=f"{self.current_engine_code}_{safe}.xlsx",
        )
        if not path: return
        try:
            from feas_excel import export_feas_report
            saved = export_feas_report(self.results, path,
                                        engine_code=self.current_engine_code)
            if messagebox.askyesno("Export", f"Saved: {saved}\n\nOpen now?"):
                try: os.startfile(str(saved))
                except AttributeError:
                    import subprocess
                    subprocess.run(["open" if sys.platform == "darwin"
                                     else "xdg-open", str(saved)])
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _export_pdf(self):
        if not self._read_inputs(): return
        try:
            self.results = self.current_engine.run_model(self.params)
        except Exception as e:
            messagebox.showerror("Export PDF", str(e)); return
        safe = self.params.project_name.replace(" ", "_").replace("/", "-")
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("All", "*.*")],
            initialdir=_DIR,
            initialfile=f"{self.current_engine_code}_{safe}.pdf",
        )
        if not path: return
        try:
            from feas_pdf import export_feas_pdf
            saved = export_feas_pdf(self.results, path,
                                      engine_code=self.current_engine_code)
            if messagebox.askyesno("Export PDF", f"Saved: {saved}\n\nOpen now?"):
                try: os.startfile(str(saved))
                except AttributeError:
                    import subprocess
                    subprocess.run(["open" if sys.platform == "darwin"
                                     else "xdg-open", str(saved)])
        except Exception as e:
            messagebox.showerror("Export PDF", str(e))


# ════════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    try: root.tk.call("tk", "scaling", 1.15)
    except tk.TclError: pass
    app = FeasApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
