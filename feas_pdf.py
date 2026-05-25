"""
feas_pdf.py — Multi-engine PDF report exporter.

Reads engine-agnostic results and produces a 4-page A4 portrait PDF:
  1. Cover + Executive Summary + KPI grid
  2. Cash Flow Table (year-by-year)
  3. Core Charts (Revenue / Cum CF / DSCR / OPEX)
  4. Assumptions
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch
from matplotlib.gridspec import GridSpec


# Colors (neumorphic)
NAVY    = "#2D3748"
ACCENT  = "#F0A52B"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
ERROR   = "#EF4444"
INFO    = "#3B82F6"
TEXT    = "#2D3748"
SUBTEXT = "#718096"
MUTED   = "#A0AEC0"
BORDER  = "#D5DBE0"
LBLUE   = "#DBEAFE"
ACCENT_SOFT = "#FFEBC9"

A4_W, A4_H = 8.27, 11.69


def _new_page(title=None, subtitle=None):
    fig = plt.figure(figsize=(A4_W, A4_H), facecolor="white")
    if title:
        fig.text(0.06, 0.965, title, fontsize=16, fontweight="bold", color=NAVY)
        if subtitle:
            fig.text(0.06, 0.945, subtitle, fontsize=9, color=SUBTEXT, style="italic")
        fig.add_artist(plt.Rectangle((0.06, 0.935), 0.88, 0.003,
                                       color=ACCENT, transform=fig.transFigure))
    return fig


def _footer(fig, page, total, project):
    fig.text(0.06, 0.025,
              f"{project}  ·  Feasibility Report  ·  "
              f"Generated {datetime.now():%Y-%m-%d %H:%M}",
              fontsize=7, color=MUTED)
    fig.text(0.94, 0.025, f"Page {page} / {total}",
              fontsize=7, color=MUTED, ha="right")


def _style_ax(ax, title=None):
    ax.set_facecolor("white")
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", color=TEXT, pad=6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BORDER)
    ax.spines["bottom"].set_color(BORDER)
    ax.tick_params(colors=SUBTEXT, labelsize=7)
    ax.grid(True, axis="y", color=BORDER, alpha=0.6, linestyle="--", linewidth=0.5)


def _color_irr(v, hurdle=0.12):
    if v is None: return MUTED
    return SUCCESS if v >= hurdle else (WARNING if v >= 0 else ERROR)


def _color_dscr(v):
    if v is None: return MUTED
    return SUCCESS if v >= 1.30 else (WARNING if v >= 1.20 else ERROR)


# ════════════════════════════════════════════════════════════════════════
# Pages
# ════════════════════════════════════════════════════════════════════════
def _page_cover(pdf, results, project_name, page, total):
    fig = plt.figure(figsize=(A4_W, A4_H), facecolor="white")

    # Banner
    ax = fig.add_axes([0, 0.78, 1, 0.17])
    ax.set_facecolor(NAVY)
    ax.text(0.5, 0.65, "⚡  FEASIBILITY  STUDIO",
              fontsize=22, fontweight="bold", color="white",
              ha="center", transform=ax.transAxes)
    ax.text(0.5, 0.35, project_name, fontsize=14, color="white",
              ha="center", transform=ax.transAxes)
    ax.text(0.5, 0.15,
              f"Engine: {results.get('engine_type','?').upper()}  ·  Multi-engine report",
              fontsize=9, color=ACCENT_SOFT,
              ha="center", transform=ax.transAxes, style="italic")
    ax.axis("off")

    fig.text(0.06, 0.745, f"Generated: {datetime.now():%B %d, %Y · %H:%M}",
              fontsize=9, color=SUBTEXT)

    # Verdict
    k = results["kpis"]
    eirr = k.get("equity_irr") or 0
    hurdle = 0.12
    if eirr < 0:
        v_color, v_text = ERROR, "PROJECT NOT VIABLE"
        v_detail = "Negative IRR — project loses money under current assumptions."
    elif eirr < hurdle:
        v_color, v_text = WARNING, "MARGINAL — REQUIRES OPTIMIZATION"
        v_detail = "Equity IRR below 12% hurdle. Consider tuning CAPEX or revenue."
    else:
        v_color, v_text = SUCCESS, "PROJECT IS VIABLE FOR INVESTMENT"
        v_detail = "Equity IRR exceeds hurdle. Recommend proceeding to detailed DD."

    ax_v = fig.add_axes([0.06, 0.605, 0.88, 0.09])
    ax_v.axis("off")
    ax_v.add_patch(FancyBboxPatch((0.005, 0.05), 0.99, 0.9,
                                    boxstyle="round,pad=0.02,rounding_size=0.02",
                                    facecolor=v_color, alpha=0.12,
                                    edgecolor=v_color, linewidth=1.5,
                                    transform=ax_v.transAxes))
    ax_v.text(0.025, 0.68, v_text, fontsize=12, fontweight="bold",
                color=v_color, transform=ax_v.transAxes)
    ax_v.text(0.025, 0.25, v_detail, fontsize=8, color=TEXT,
                transform=ax_v.transAxes)

    # KPI grid 3×3
    fig.text(0.06, 0.575, "KEY FINANCIAL METRICS",
              fontsize=10, fontweight="bold", color=ACCENT)
    fig.add_artist(plt.Rectangle((0.06, 0.568), 0.88, 0.002,
                                   color=ACCENT, transform=fig.transFigure))

    def kpi_box(x, y, label, value, sub, color):
        ax = fig.add_axes([x, y, 0.27, 0.10])
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1,
                                      boxstyle="round,pad=0.02,rounding_size=0.03",
                                      facecolor="white", edgecolor=BORDER,
                                      linewidth=1, transform=ax.transAxes))
        ax.add_patch(plt.Rectangle((0.02, 0.92), 0.96, 0.06,
                                     color=color, transform=ax.transAxes))
        ax.text(0.05, 0.72, label, fontsize=7, color=SUBTEXT,
                  fontweight="bold", transform=ax.transAxes)
        ax.text(0.05, 0.35, value, fontsize=16, fontweight="bold",
                  color=color, transform=ax.transAxes)
        ax.text(0.05, 0.10, sub, fontsize=6, color=MUTED, transform=ax.transAxes)

    fp = lambda v: f"{v*100:.2f}%" if v is not None else "n/a"
    fn = lambda v, d=2: f"{v:.{d}f}" if v is not None else "n/a"
    inputs = results["inputs"]
    et = results.get("engine_type", "")
    cost_label = "LCO-PELLET" if et == "rdf" else "LCOE"
    cost_value = (f"{k.get('lco_pellet_thb_per_ton', 0):.0f}"
                   if et == "rdf"
                   else f"{k.get('lcoe_thb_per_kwh', 0):.2f}")
    cost_sub = "฿/ton" if et == "rdf" else "฿/kWh"

    grid = [
        ("PROJECT IRR",   fp(k["project_irr"]),  "hurdle 12%", _color_irr(k["project_irr"])),
        ("EQUITY IRR",    fp(k["equity_irr"]),   "after debt", _color_irr(k["equity_irr"])),
        ("EQUITY NPV",    f"{k['equity_npv']:.0f} MB",
         f"@ {inputs.get('discount_rate',0.0625)*100:.2f}%",
         SUCCESS if k['equity_npv'] >= 0 else ERROR),
        ("DSCR MIN",      fn(k["dscr_min"]),     "≥ 1.30 bank", _color_dscr(k["dscr_min"])),
        ("DSCR AVG",      fn(k["dscr_avg"]),     "lifetime",    _color_dscr(k["dscr_avg"])),
        (cost_label,      cost_value,            cost_sub,      INFO),
        ("PAYBACK (EQ)",  f"{(k['payback_equity'] or 0):.1f} yr", "from COD",
         SUCCESS if (k.get("payback_equity") or 99) <= 10 else WARNING),
        ("BCR",           f"{k['bcr']:.3f}x",   ">1 viable",
         SUCCESS if k['bcr'] >= 1 else ERROR),
        ("WACC",          fp(k["wacc"]),        "CAPM", NAVY),
    ]
    xs = [0.06, 0.36, 0.66]
    ys = [0.450, 0.335, 0.220]
    for i, kpi in enumerate(grid):
        r, c = divmod(i, 3)
        kpi_box(xs[c], ys[r], *kpi)

    # Project overview
    fig.text(0.06, 0.185, "PROJECT OVERVIEW",
              fontsize=10, fontweight="bold", color=ACCENT)
    fig.add_artist(plt.Rectangle((0.06, 0.178), 0.88, 0.002,
                                   color=ACCENT, transform=fig.transFigure))
    overview = [
        ("Engine",      results.get("engine_type", "?").upper()),
        ("COD Year",    f"{inputs.get('cod_year', 0)}"),
        ("Project Life",f"{inputs.get('project_life', 0)} yr"),
        ("Total CAPEX", f"{results['capex']['total_capex']:,.0f} MB"),
        ("Equity",      f"{results['capex']['equity']:,.0f} MB"),
        ("Debt",        f"{results['capex']['debt']:,.0f} MB"),
        ("Interest",    f"{inputs.get('interest_rate', 0)*100:.3f}%"),
        ("Tenor",       f"{inputs.get('debt_tenor', 0)} yr"),
    ]
    for i, (lbl, val) in enumerate(overview):
        x = 0.06 + (i % 4) * 0.22
        y = 0.15 - (i // 4) * 0.038
        fig.text(x, y, lbl, fontsize=7, color=MUTED)
        fig.text(x, y - 0.018, val, fontsize=8.5, color=TEXT, fontweight="bold")

    _footer(fig, page, total, project_name)
    pdf.savefig(fig)
    plt.close(fig)


def _page_cashflow(pdf, results, project_name, page, total):
    fig = _new_page("CASH FLOW MODEL",
                     f"Year-by-year P&L → CF → DSCR  ·  "
                     f"{results['inputs'].get('project_life',0)}-year horizon  ·  MB THB")
    rows = results["rows"]
    cols = ["Yr", "Revenue", "OPEX", "EBITDA", "Dep", "EBIT",
            "Int", "Tax", "NPAT", "OCF", "DSCR", "FCFE", "Σ FCFE"]
    cum = 0
    data = []
    for r in rows:
        cum += r["fcfe"]
        dscr_s = f"{r['dscr']:.2f}" if r['dscr'] < 1e9 else "inf"
        data.append([
            r["year"],
            f"{r['revenue']:,.1f}", f"{r['opex']:,.1f}",
            f"{r['ebitda']:,.1f}", f"{r['depreciation']:,.1f}",
            f"{r['ebit']:,.1f}", f"{r['interest']:,.1f}",
            f"{r['tax']:,.1f}", f"{r['npat']:,.1f}",
            f"{r['ocf']:,.1f}", dscr_s,
            f"{r['fcfe']:,.1f}", f"{cum:,.1f}",
        ])

    ax = fig.add_axes([0.04, 0.05, 0.92, 0.87])
    ax.axis("off")
    tbl = ax.table(cellText=data, colLabels=cols, loc="upper center",
                     cellLoc="right", colLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.scale(1, 1.4)
    for c in range(len(cols)):
        cell = tbl[0, c]
        cell.set_facecolor(NAVY)
        cell.set_text_props(color="white", fontweight="bold", fontsize=7)
    for r in range(len(data)):
        for c in range(len(cols)):
            cell = tbl[r+1, c]
            cell.set_edgecolor(BORDER)
            cell.set_facecolor("white" if r % 2 == 0 else "#FAFBFC")
            if c == len(cols) - 1:
                try:
                    v = float(data[r][c].replace(",", ""))
                    cell.set_text_props(color=ERROR if v < 0 else SUCCESS,
                                          fontweight="bold")
                except Exception:
                    pass
            if c == 10 and data[r][c] != "inf":
                try:
                    d = float(data[r][c])
                    if d < 1.20 and rows[r]["principal_repay"] > 0:
                        cell.set_facecolor("#FFE0E0")
                        cell.set_text_props(color=ERROR, fontweight="bold")
                except Exception:
                    pass

    _footer(fig, page, total, project_name)
    pdf.savefig(fig)
    plt.close(fig)


def _page_charts(pdf, results, project_name, page, total):
    fig = _new_page("CORE VISUALIZATIONS",
                     "Revenue · Cumulative cash flow · DSCR · OPEX breakdown")
    gs = GridSpec(2, 2, left=0.07, right=0.96, top=0.88, bottom=0.07,
                    hspace=0.38, wspace=0.25, figure=fig)
    rows = results["rows"]
    yrs = [r["calendar_year"] for r in rows]

    # 1. Revenue + NPAT
    ax1 = fig.add_subplot(gs[0, 0])
    fit_r = [r["fit_rev"]    for r in rows]
    tip_r = [r["tip_rev"]    for r in rows]
    rdf_r = [r["rdf_rev"]    for r in rows]
    car_r = [r["carbon_rev"] for r in rows]
    npat  = [r["npat"]       for r in rows]
    bot = [0] * len(yrs)
    if any(fit_r):
        ax1.bar(yrs, fit_r, color=ACCENT, label="FiT/Elec", alpha=0.92)
        bot = list(fit_r)
    if any(tip_r):
        ax1.bar(yrs, tip_r, bottom=bot, color="#26C6DA", label="Tipping", alpha=0.92)
        bot = [b+t for b, t in zip(bot, tip_r)]
    if any(rdf_r):
        ax1.bar(yrs, rdf_r, bottom=bot, color="#A371F7", label="RDF", alpha=0.92)
        bot = [b+r for b, r in zip(bot, rdf_r)]
    if any(c > 0 for c in car_r):
        ax1.bar(yrs, car_r, bottom=bot, color=SUCCESS, label="Carbon", alpha=0.92)
    ax1.plot(yrs, npat, color=ERROR, linewidth=1.8, marker="o", markersize=2.5,
              label="NPAT")
    _style_ax(ax1, "Revenue + NPAT (MB/yr)")
    ax1.legend(fontsize=6, loc="upper left")

    # 2. Cum CF
    ax2 = fig.add_subplot(gs[0, 1])
    cum_e = results["cum_fcfe"]; cum_p = results["cum_fcff"]
    ax2.fill_between(yrs, cum_e, 0, color=SUCCESS, alpha=0.18,
                      where=[v >= 0 for v in cum_e], interpolate=True)
    ax2.fill_between(yrs, cum_e, 0, color=ERROR, alpha=0.12,
                      where=[v < 0 for v in cum_e], interpolate=True)
    ax2.plot(yrs, cum_p, color=INFO, linewidth=1.2, linestyle="--", label="Cum FCFF")
    ax2.plot(yrs, cum_e, color=SUCCESS, linewidth=2, label="Cum FCFE")
    ax2.axhline(0, color=MUTED, linewidth=0.8)
    pb = results["kpis"].get("payback_equity")
    if pb is not None and pb < len(yrs):
        ax2.axvline(yrs[0] + pb - 1, color=ACCENT, linestyle=":",
                     linewidth=1.5, label=f"Payback {pb:.1f}yr")
    _style_ax(ax2, "Cumulative Cash Flow (MB)")
    ax2.legend(fontsize=6, loc="lower right")

    # 3. DSCR
    ax3 = fig.add_subplot(gs[1, 0])
    dscr = [r["dscr"] if r["dscr"] < 1e9 else None for r in rows]
    valid = [(y, d) for y, d in zip(yrs, dscr) if d is not None]
    if valid:
        vy, vd = zip(*valid)
        colors = [SUCCESS if d >= 1.30 else (WARNING if d >= 1.20 else ERROR)
                   for d in vd]
        ax3.bar(vy, vd, color=colors, alpha=0.85, width=0.8)
        ax3.axhline(1.30, color=SUCCESS, linestyle="--", linewidth=1,
                     label="Bank 1.30x")
        ax3.axhline(1.20, color=WARNING, linestyle="--", linewidth=1,
                     label="Min 1.20x")
    _style_ax(ax3, "DSCR Profile")
    ax3.legend(fontsize=6, loc="upper right")

    # 4. OPEX
    ax4 = fig.add_subplot(gs[1, 1])
    keys = [("opex_om", "O&M", NAVY),
            ("opex_feedstock", "Feedstock", "#B15224"),
            ("opex_ash", "Ash", "#9F4A0A"),
            ("opex_flue", "Flue", WARNING),
            ("opex_aux", "Aux/Trans", ACCENT),
            ("opex_sga", "SG&A", SUCCESS),
            ("opex_insurance", "Insur.", INFO),
            ("opex_pdf", "PDF/Misc", "#A371F7")]
    bot = [0] * len(yrs)
    for k_, lbl, col in keys:
        vals = [r.get(k_, 0) for r in rows]
        if not any(vals):
            continue
        ax4.bar(yrs, vals, bottom=bot, color=col, label=lbl, alpha=0.9)
        bot = [b+v for b, v in zip(bot, vals)]
    _style_ax(ax4, "OPEX Breakdown (MB/yr)")
    ax4.legend(fontsize=5, loc="upper left", ncol=2)

    _footer(fig, page, total, project_name)
    pdf.savefig(fig)
    plt.close(fig)


def _page_assumptions(pdf, results, project_name, page, total):
    fig = _new_page("INPUT ASSUMPTIONS",
                     "All parameters used to generate this report")
    inputs = results["inputs"]
    y = 0.90
    col_idx = 0
    for k, v in inputs.items():
        if isinstance(v, float):
            s = f"{v:.4f}".rstrip("0").rstrip(".") if not k.endswith("_pct") else f"{v*100:.2f}%"
        elif isinstance(v, bool):
            s = "✓" if v else "✗"
        else:
            s = str(v)
        x = 0.06 + col_idx * 0.46
        fig.text(x,        y, k, fontsize=7, color=TEXT, family="monospace")
        fig.text(x + 0.30, y, s, fontsize=7, color=ACCENT, fontweight="bold",
                  family="monospace")
        y -= 0.018
        if y < 0.07:
            y = 0.90
            col_idx += 1
            if col_idx > 1:
                break
    _footer(fig, page, total, project_name)
    pdf.savefig(fig)
    plt.close(fig)


# ════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════
def export_feas_pdf(results: dict, output_path: str | Path,
                     engine_code: str = None, **kwargs) -> Path:
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")
    project_name = results["inputs"].get("project_name", "Project")
    total_pages = 4
    with PdfPages(output_path) as pdf:
        d = pdf.infodict()
        d['Title'] = f"{project_name} — Feasibility Report"
        d['Author'] = "Feasibility Studio (multi-engine)"
        d['Subject'] = f"Engine: {results.get('engine_type','?')}"
        d['CreationDate'] = datetime.now()

        _page_cover(pdf, results, project_name, 1, total_pages)
        _page_cashflow(pdf, results, project_name, 2, total_pages)
        _page_charts(pdf, results, project_name, 3, total_pages)
        _page_assumptions(pdf, results, project_name, 4, total_pages)
    return output_path


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    from engines import REGISTRY
    out_dir = Path(__file__).parent
    for code, mod in REGISTRY.items():
        p = mod.default_preset()
        res = mod.run_model(p)
        path = export_feas_pdf(res, out_dir / f"report_{code}.pdf",
                                 engine_code=code)
        print(f"  ✅ {path.name}  ({path.stat().st_size/1024:.1f} KB)")
