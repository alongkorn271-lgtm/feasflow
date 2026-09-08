"""
feas_theme.py — Modern fintech-style theme for the Feasibility Studio.

Palette: emerald + lime green, white surfaces, soft slate text.
Inspired by current AI-finance SaaS dashboards.
"""
from __future__ import annotations

import platform
import tkinter as tk
from tkinter import ttk

# customtkinter provides true rounded-corner widgets (Bao-style)
try:
    import customtkinter as ctk
    _HAS_CTK = True
    ctk.set_appearance_mode("light")
except ImportError:
    _HAS_CTK = False


# ════════════════════════════════════════════════════════════════════════
# COLOR PALETTE — modern fintech (emerald / lime / slate)
# ════════════════════════════════════════════════════════════════════════
# Surfaces
BG          = "#F4F6F8"     # soft page bg (almost white)
CARD        = "#FFFFFF"     # card surface (pure white)
CARD_SOFT   = "#FAFBFC"     # nested cards / table rows
BORDER      = "#E8ECF1"     # very subtle borders
DIVIDER     = "#F1F3F6"
SIDEBAR_BG  = "#FFFFFF"     # white sidebar
SIDEBAR_ITEM_HOVER = "#F4F6F8"

# Accent — emerald + lime (matches reference)
ACCENT      = "#10B981"     # emerald 500
ACCENT_LT   = "#A7F3D0"     # emerald 200 (light pill)
ACCENT_SOFT = "#D1FAE5"     # emerald 100 (active pill bg)
ACCENT_DK   = "#047857"     # emerald 700 (text on light)
LIME        = "#84CC16"     # lime 500 — secondary accent
LIME_LT     = "#D9F99D"     # lime 200

# Sidebar active state
SIDEBAR_ACTIVE_BG = ACCENT_SOFT
SIDEBAR_ACTIVE_FG = ACCENT_DK
SIDEBAR_TEXT      = "#475569"   # slate 600 inactive
SIDEBAR_TEXT_DIM  = "#94A3B8"   # slate 400

# Text
TEXT        = "#0F172A"     # near-black (slate 900)
TEXT_SUB    = "#475569"     # slate 600
TEXT_MUTED  = "#94A3B8"     # slate 400
TEXT_ON_ACCENT = "#FFFFFF"

# Semantic
SUCCESS     = "#10B981"     # emerald
WARNING     = "#F59E0B"     # amber
ERROR       = "#EF4444"     # red
INFO        = "#3B82F6"     # blue

# Status badge backgrounds (soft tints for pill labels)
BADGE_POS_BG = "#D1FAE5"
BADGE_POS_FG = "#047857"
BADGE_NEG_BG = "#FEE2E2"
BADGE_NEG_FG = "#B91C1C"
BADGE_WARN_BG = "#FEF3C7"
BADGE_WARN_FG = "#92400E"
BADGE_INFO_BG = "#DBEAFE"
BADGE_INFO_FG = "#1D4ED8"

# Status helpers (pass/marginal/fail)
PASS        = SUCCESS
MARGINAL    = WARNING
FAIL        = ERROR
NEUTRAL     = INFO

# Sparkline colors per metric type
SPARK_POS   = ACCENT
SPARK_NEG   = ERROR
SPARK_NEU   = INFO

# Treeview / table
TABLE_BG       = CARD
TABLE_FG       = TEXT
TABLE_HDR_BG   = CARD_SOFT
TABLE_HDR_FG   = TEXT_SUB
TABLE_ROW_ALT  = CARD_SOFT
TABLE_SELECT_BG = ACCENT_SOFT


# ════════════════════════════════════════════════════════════════════════
# FONTS
# ════════════════════════════════════════════════════════════════════════
_sys = platform.system()
FF = ("Segoe UI" if _sys == "Windows"
      else "SF Pro Display" if _sys == "Darwin"
      else "Ubuntu")
FF_MONO = "Consolas" if _sys == "Windows" else "Menlo"

F_DISPLAY = (FF, 28, "bold")    # welcome / hero
F_H1      = (FF, 16, "bold")    # card title
F_H2      = (FF, 13, "bold")
F_H3      = (FF, 11, "bold")
F_BODY    = (FF, 10)
F_BODY_B  = (FF, 10, "bold")
F_SMALL   = (FF,  9)
F_TINY    = (FF,  8)
F_MONO    = (FF_MONO, 9)
F_MONO_B  = (FF_MONO, 9, "bold")
F_KPI     = (FF, 22, "bold")
F_BADGE   = (FF,  8, "bold")


# ════════════════════════════════════════════════════════════════════════
# LAYOUT CONSTANTS
# ════════════════════════════════════════════════════════════════════════
SIDEBAR_WIDTH       = 240
SIDEBAR_ITEM_HEIGHT = 56
SIDEBAR_PAD_X       = 12
TOPBAR_HEIGHT       = 110          # taller — description fits two lines
CARD_RADIUS         = 16           # rounded card radius
PILL_RADIUS         = 999          # full pill (status badges, buttons)
INPUT_RADIUS        = 10           # input fields
CARD_PAD_X          = 18
CARD_PAD_Y          = 16
SECTION_GAP         = 12


# ════════════════════════════════════════════════════════════════════════
# TTK THEME
# ════════════════════════════════════════════════════════════════════════
def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(bg=BG)
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass

    # Frame
    s.configure("TFrame",        background=BG)
    s.configure("Card.TFrame",   background=CARD)
    s.configure("Soft.TFrame",   background=CARD_SOFT)
    s.configure("Sidebar.TFrame",background=SIDEBAR_BG)

    # Label
    s.configure("TLabel",        background=BG,   foreground=TEXT,    font=F_BODY)
    s.configure("H1.TLabel",     background=BG,   foreground=TEXT,    font=F_H1)
    s.configure("H2.TLabel",     background=BG,   foreground=TEXT,    font=F_H2)
    s.configure("Welcome.TLabel",background=BG,   foreground=TEXT,    font=F_DISPLAY)
    s.configure("Sub.TLabel",    background=BG,   foreground=TEXT_SUB,font=F_SMALL)
    s.configure("Muted.TLabel",  background=BG,   foreground=TEXT_MUTED,font=F_TINY)
    s.configure("Card.TLabel",   background=CARD, foreground=TEXT,    font=F_BODY)
    s.configure("CardH2.TLabel", background=CARD, foreground=TEXT,    font=F_H2)
    s.configure("CardSub.TLabel",background=CARD, foreground=TEXT_SUB,font=F_SMALL)
    s.configure("Mono.TLabel",   background=CARD, foreground=TEXT,    font=F_MONO)

    # Buttons — primary (green pill)
    s.configure("P.TButton", background=ACCENT, foreground="white",
                font=F_BODY_B, borderwidth=0, focusthickness=0, padding=(18, 9))
    s.map("P.TButton",
          background=[("active", ACCENT_DK), ("pressed", ACCENT_DK),
                       ("disabled", BORDER)],
          foreground=[("disabled", TEXT_SUB)])

    # Secondary — light pill
    s.configure("S.TButton", background=CARD, foreground=TEXT,
                font=F_BODY_B, borderwidth=1, focusthickness=0, padding=(14, 7))
    s.map("S.TButton",
          background=[("active", BG)],
          foreground=[("active", ACCENT_DK)])

    # Topbar — ghost icon button
    s.configure("Ghost.TButton", background=BG, foreground=TEXT,
                font=F_BODY_B, borderwidth=0, relief="flat",
                focusthickness=0, padding=(10, 6))
    s.map("Ghost.TButton",
          background=[("active", ACCENT_SOFT)],
          foreground=[("active", ACCENT_DK)])

    # Entry
    s.configure("TEntry",
                fieldbackground=CARD, foreground=TEXT, font=F_BODY,
                padding=(8, 6), relief="flat",
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                insertcolor=TEXT)
    s.map("TEntry",
          bordercolor=[("focus", ACCENT)],
          lightcolor=[("focus", ACCENT)],
          darkcolor=[("focus", ACCENT)])

    # Combobox
    s.configure("TCombobox",
                fieldbackground=CARD, foreground=TEXT, font=F_BODY,
                background=CARD, padding=(8, 6), relief="flat",
                bordercolor=BORDER, arrowcolor=TEXT_SUB)
    s.map("TCombobox",
          fieldbackground=[("readonly", CARD)],
          bordercolor=[("focus", ACCENT)])

    # Checkbutton
    s.configure("TCheckbutton", background=BG, foreground=TEXT,
                font=F_BODY, focusthickness=0)
    s.map("TCheckbutton",
          background=[("active", BG)],
          indicatorcolor=[("selected", ACCENT), ("!selected", BORDER)])
    s.configure("Card.TCheckbutton", background=CARD, foreground=TEXT,
                font=F_BODY, focusthickness=0)
    s.map("Card.TCheckbutton",
          background=[("active", CARD)],
          indicatorcolor=[("selected", ACCENT), ("!selected", BORDER)])

    # Scrollbar — wider modern (no arrows, prominent thumb + visible trough)
    s.configure("TScrollbar",
                background="#7C8898",     # slate-500-ish — visible thumb
                troughcolor="#D8DEE6",    # darker track (always visible)
                borderwidth=0,
                arrowsize=0,              # hide arrows
                gripcount=0,
                relief="flat",
                width=18)                 # wider — easy to see/grab
    s.map("TScrollbar",
          background=[("active", "#5C6779"), ("pressed", "#3F4856")],
          troughcolor=[("active", "#D8DEE6")])
    # Remove arrows from layout — keep just trough + thumb
    s.layout("Vertical.TScrollbar",
             [("Vertical.Scrollbar.trough",
                {"children": [("Vertical.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"})],
                  "sticky": "ns"})])
    s.layout("Horizontal.TScrollbar",
             [("Horizontal.Scrollbar.trough",
                {"children": [("Horizontal.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"})],
                  "sticky": "ew"})])

    # Progressbar
    s.configure("TProgressbar",
                troughcolor=BORDER, background=ACCENT,
                borderwidth=0, thickness=8)

    # Treeview
    s.configure("Treeview",
                background=TABLE_BG, fieldbackground=TABLE_BG,
                foreground=TABLE_FG, font=F_MONO, rowheight=24, borderwidth=0)
    s.configure("Treeview.Heading",
                background=TABLE_HDR_BG, foreground=TABLE_HDR_FG,
                font=F_MONO_B, relief="flat", padding=(6, 8))
    s.map("Treeview", background=[("selected", TABLE_SELECT_BG)],
                       foreground=[("selected", TEXT)])

    return s


# ════════════════════════════════════════════════════════════════════════
# ROUNDED RECTANGLE on Canvas — for true rounded cards
# ════════════════════════════════════════════════════════════════════════
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r=CARD_RADIUS,
                fill="", outline="", width=1):
    """Draw a rounded rectangle on a Canvas."""
    points = [
        x1+r, y1,  x1+r, y1,  x2-r, y1,  x2-r, y1,
        x2,   y1,  x2,   y1+r,  x2, y1+r,  x2, y2-r,
        x2,   y2-r, x2,   y2,  x2-r, y2,   x2-r, y2,
        x1+r, y2,  x1+r, y2,  x1,   y2,   x1,   y2-r,
        x1,   y2-r, x1,   y1+r, x1,  y1+r, x1,   y1,
    ]
    return canvas.create_polygon(points, smooth=True, fill=fill,
                                   outline=outline, width=width)


# ════════════════════════════════════════════════════════════════════════
# CARD HELPERS — true rounded corners via CustomTkinter
# ════════════════════════════════════════════════════════════════════════
def make_card(parent, title: str | None = None, padx: int = CARD_PAD_X,
               pady: int = CARD_PAD_Y, soft: bool = False):
    """Rounded card with subtle border + optional title bar.

    Uses CTkFrame (true rounded corners) when available, falls back to
    tk.Frame with thin border otherwise.

    Returns the OUTER frame; access body via .body attribute.
    """
    bg = CARD_SOFT if soft else CARD

    if _HAS_CTK:
        outer = ctk.CTkFrame(parent, fg_color=bg, corner_radius=CARD_RADIUS,
                              border_width=1, border_color=BORDER)
    else:
        outer = tk.Frame(parent, bg=bg,
                          highlightbackground=BORDER, highlightthickness=1)

    if title:
        hdr = tk.Frame(outer, bg=bg)
        hdr.pack(fill="x", padx=padx, pady=(pady, 6))
        tk.Label(hdr, text=title, font=F_H2, bg=bg, fg=TEXT,
                  anchor="w").pack(side="left")

    body = tk.Frame(outer, bg=bg)
    body.pack(fill="both", expand=True, padx=padx,
               pady=(0 if title else pady, pady))
    outer.body = body
    return outer


def make_pill_badge(parent, text: str, *, kind: str = "pos"):
    """Rounded pill badge — uses CTkLabel for full rounding, tk.Label as fallback."""
    palette = {
        "pos":     (BADGE_POS_BG,  BADGE_POS_FG),
        "neg":     (BADGE_NEG_BG,  BADGE_NEG_FG),
        "warn":    (BADGE_WARN_BG, BADGE_WARN_FG),
        "info":    (BADGE_INFO_BG, BADGE_INFO_FG),
        "neutral": (DIVIDER,       TEXT_SUB),
    }
    bg, fg = palette.get(kind, (DIVIDER, TEXT_SUB))

    if _HAS_CTK:
        lbl = ctk.CTkLabel(parent, text=text, font=F_BADGE,
                            fg_color=bg, text_color=fg,
                            corner_radius=PILL_RADIUS,
                            padx=10, pady=2,
                            ) if False else None
        # CTkLabel doesn't accept padx/pady — use frame wrapper
        wrap = ctk.CTkFrame(parent, fg_color=bg, corner_radius=PILL_RADIUS,
                             border_width=0)
        inner = tk.Label(wrap, text=text, font=F_BADGE, bg=bg, fg=fg,
                          padx=10, pady=2)
        inner.pack()
        return wrap
    else:
        return tk.Label(parent, text=text, font=F_BADGE, bg=bg, fg=fg,
                         padx=10, pady=3)


# ════════════════════════════════════════════════════════════════════════
# SPARKLINE — small line/area chart on tk.Canvas
# ════════════════════════════════════════════════════════════════════════
def draw_sparkline(parent, values: list[float], width: int = 120,
                    height: int = 40, line_color: str = ACCENT,
                    fill_color: str | None = ACCENT_SOFT,
                    bg: str = CARD, baseline: float | None = None) -> tk.Canvas:
    """Tiny line chart with optional area fill and a dashed reference line.

    `baseline` draws a faint dashed horizontal marker (e.g. 0 for cumulative
    cash flow → where the project turns from loss to profit; 1.30 for a DSCR
    profile → the bankable threshold). The value range is expanded to always
    include the baseline so the marker is meaningful.
    """
    canvas = tk.Canvas(parent, width=width, height=height,
                        bg=bg, highlightthickness=0)
    if not values or len(values) < 2:
        return canvas

    pad = 4
    min_v = min(values)
    max_v = max(values)
    if baseline is not None:                 # keep the reference line on-chart
        min_v = min(min_v, baseline)
        max_v = max(max_v, baseline)
    span  = max_v - min_v if max_v != min_v else 1.0
    n = len(values) - 1

    def y(v):
        return pad + (height - 2 * pad) * (1 - (v - min_v) / span)

    def x(i):
        return pad + (width - 2 * pad) * i / n

    pts = []
    for i, v in enumerate(values):
        pts.extend([x(i), y(v)])

    # Area fill
    if fill_color:
        area = pts + [width - pad, height - pad, pad, height - pad]
        canvas.create_polygon(area, fill=fill_color, outline="",
                                smooth=True)
    # Dashed reference line (drawn under the data line)
    if baseline is not None and min_v <= baseline <= max_v:
        yb = y(baseline)
        canvas.create_line(pad, yb, width - pad, yb,
                            fill=TEXT_MUTED, width=1, dash=(2, 2))
    # Line
    canvas.create_line(*pts, fill=line_color, width=2, smooth=True,
                        capstyle="round")
    return canvas


# ════════════════════════════════════════════════════════════════════════
# KPI CARD with sparkline + pill badge — rounded via CTkFrame
# ════════════════════════════════════════════════════════════════════════
def make_kpi_card(parent, *, label: str, value: str, sparkline_values=None,
                    badge_text: str = "", badge_kind: str = "pos",
                    accent_color: str = ACCENT, sub: str = "",
                    sparkline_baseline: float | None = None):
    """Fintech-style KPI tile with rounded corners."""
    if _HAS_CTK:
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=CARD_RADIUS,
                             border_width=1, border_color=BORDER)
    else:
        card = tk.Frame(parent, bg=CARD,
                         highlightbackground=BORDER, highlightthickness=1)

    # Header row: label + badge
    head = tk.Frame(card, bg=CARD)
    head.pack(fill="x", padx=18, pady=(16, 4))
    tk.Label(head, text=label, font=F_H3, bg=CARD, fg=TEXT_SUB,
              anchor="w").pack(side="left")
    if badge_text:
        make_pill_badge(head, badge_text, kind=badge_kind
                          ).pack(side="left", padx=(8, 0))

    # Body: big value + sparkline
    body = tk.Frame(card, bg=CARD)
    body.pack(fill="x", padx=18, pady=(0, 14))

    tk.Label(body, text=value, font=F_KPI, bg=CARD, fg=TEXT,
              anchor="w").pack(side="left")

    if sparkline_values and len(sparkline_values) >= 2:
        line = (SPARK_POS if badge_kind == "pos"
                 else SPARK_NEG if badge_kind == "neg"
                 else SPARK_NEU)
        soft = (ACCENT_SOFT if badge_kind == "pos"
                 else BADGE_NEG_BG if badge_kind == "neg"
                 else BADGE_INFO_BG)
        spark = draw_sparkline(body, sparkline_values, width=110, height=44,
                                line_color=line, fill_color=soft, bg=CARD,
                                baseline=sparkline_baseline)
        spark.pack(side="right")

    if sub:
        tk.Label(card, text=sub, font=F_TINY, bg=CARD, fg=TEXT_MUTED,
                  anchor="w").pack(fill="x", padx=18, pady=(0, 12))
    return card


# ════════════════════════════════════════════════════════════════════════
# SIDEBAR ITEM
# ════════════════════════════════════════════════════════════════════════
def make_sidebar_button(parent, *, icon: str, label: str, color: str,
                         is_active: bool = False, command=None):
    """Sidebar nav item — rounded active pill (Bao-style).

    Engine items are MAIN navigation.
    Icon 20pt · label 14pt bold — IDENTICAL for active/inactive (only color changes).
    Icon uses Label with `width=2` chars — keeps labels aligned without clipping emoji.
    """
    bg = SIDEBAR_ACTIVE_BG if is_active else SIDEBAR_BG
    fg = SIDEBAR_ACTIVE_FG if is_active else SIDEBAR_TEXT
    icon_fg = SIDEBAR_ACTIVE_FG if is_active else color

    if _HAS_CTK:
        item = ctk.CTkFrame(parent, fg_color=bg,
                             corner_radius=CARD_RADIUS - 2,  # 14
                             border_width=0,
                             height=SIDEBAR_ITEM_HEIGHT)
    else:
        item = tk.Frame(parent, bg=bg, height=SIDEBAR_ITEM_HEIGHT)
    item.pack_propagate(False)
    item.configure(cursor="hand2")

    inner = tk.Frame(item, bg=bg)
    inner.pack(fill="both", expand=True, padx=18)

    # Icon — visible emoji, NOT constrained inside a fixed-size frame
    # `width=2` reserves ~2 char-widths so labels align across all rows
    icon_lbl = tk.Label(inner, text=icon, font=(FF, 20),
                         bg=bg, fg=icon_fg, width=2, anchor="center")
    icon_lbl.pack(side="left", padx=(0, 12))

    # Label — 14pt bold uniformly (active uses fg color = ACCENT_DK)
    lbl_w = tk.Label(inner, text=label, font=(FF, 14, "bold"),
                      bg=bg, fg=fg, anchor="w")
    lbl_w.pack(side="left", fill="x", expand=True)

    if command:
        for w in (item, inner, icon_lbl, lbl_w):
            try: w.bind("<Button-1>", lambda e: command())
            except: pass

    return item


# ════════════════════════════════════════════════════════════════════════
# STATUS HELPERS
# ════════════════════════════════════════════════════════════════════════
def status_color_irr(irr, hurdle=0.12):
    if irr is None: return TEXT_MUTED
    return PASS if irr >= hurdle else (MARGINAL if irr >= 0 else FAIL)


def status_color_dscr(dscr):
    if dscr is None: return TEXT_MUTED
    return PASS if dscr >= 1.30 else (MARGINAL if dscr >= 1.20 else FAIL)


def status_color_npv(npv):
    if npv is None: return TEXT_MUTED
    return PASS if npv >= 0 else FAIL


def kind_for_irr(irr, hurdle=0.12):
    if irr is None: return "neutral"
    return "pos" if irr >= hurdle else ("warn" if irr >= 0 else "neg")


def kind_for_dscr(dscr):
    if dscr is None: return "neutral"
    return "pos" if dscr >= 1.30 else ("warn" if dscr >= 1.20 else "neg")


def kind_for_npv(npv):
    if npv is None: return "neutral"
    return "pos" if npv >= 0 else "neg"


# ════════════════════════════════════════════════════════════════════════
# MATPLOTLIB
# ════════════════════════════════════════════════════════════════════════
def mpl_style_ax(ax, title=None):
    ax.set_facecolor(CARD)
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold",
                      color=TEXT, pad=10, loc="left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BORDER)
    ax.spines["bottom"].set_color(BORDER)
    ax.tick_params(colors=TEXT_SUB, labelsize=8)
    ax.grid(True, axis="y", color=DIVIDER, alpha=1.0, linestyle="-", linewidth=0.8)
    # x-axis is calendar years → whole-number ticks/labels (e.g. 2025, not 2025.0)
    from matplotlib.ticker import MaxNLocator, FuncFormatter
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{int(round(v))}"))
