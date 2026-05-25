"""
feas_streamlit.py — Web version of the multi-engine Feasibility Studio.

Run locally:
    streamlit run feas_streamlit.py

Deploy to Streamlit Cloud:
    1. Push to GitHub
    2. Sign in at share.streamlit.io with GitHub
    3. New app → pick repo → main file = feas_streamlit.py
    4. Get public URL like https://feasflow.streamlit.app

Reuses the engines/ package + solar_generation_engine.py as-is.
"""
from __future__ import annotations

import json
import io
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engines import REGISTRY


# ════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="FeasFlow — Feasibility Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ════════════════════════════════════════════════════════════════════════
# COLOR TOKENS (match desktop theme)
# ════════════════════════════════════════════════════════════════════════
ACCENT      = "#1FBC59"
ACCENT_DK   = "#0F9B47"
ACCENT_SOFT = "#E0F7E8"
BG          = "#F1F4F8"
CARD        = "#FFFFFF"
BORDER      = "#E2E8F0"
TEXT        = "#0F172A"
TEXT_SUB    = "#475569"
TEXT_MUTED  = "#94A3B8"
SUCCESS     = "#10B981"
ERROR       = "#EF4444"
WARNING     = "#F59E0B"
INFO        = "#3B82F6"
NAVY        = "#2D3748"


# ════════════════════════════════════════════════════════════════════════
# CUSTOM CSS — neumorphic look, rounded cards, accent colors
# ════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}}

.stApp {{
    background: {BG};
}}

/* Sidebar */
section[data-testid="stSidebar"] {{
    background: {CARD};
    border-right: 1px solid {BORDER};
}}

section[data-testid="stSidebar"] .stRadio > label {{
    font-weight: 600;
    color: {TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 11px;
}}

/* Cards */
.feas-card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 12px;
}}

.feas-title {{
    font-size: 28px;
    font-weight: 700;
    color: {TEXT};
    margin-bottom: 4px;
}}

.feas-subtitle {{
    color: {TEXT_SUB};
    font-size: 13px;
    margin-bottom: 16px;
}}

/* Status banner */
.status-pass {{
    background: {ACCENT_SOFT};
    color: {ACCENT_DK};
    border-left: 4px solid {ACCENT};
    padding: 12px 18px;
    border-radius: 12px;
    font-weight: 600;
    margin: 10px 0 18px;
}}
.status-warn {{
    background: #FFF7E0;
    color: #B7791F;
    border-left: 4px solid {WARNING};
    padding: 12px 18px;
    border-radius: 12px;
    font-weight: 600;
    margin: 10px 0 18px;
}}
.status-fail {{
    background: #FEE2E2;
    color: #B91C1C;
    border-left: 4px solid {ERROR};
    padding: 12px 18px;
    border-radius: 12px;
    font-weight: 600;
    margin: 10px 0 18px;
}}

/* KPI cards (st.metric override) */
[data-testid="stMetricValue"] {{
    font-size: 32px;
    font-weight: 700;
    color: {TEXT};
}}
[data-testid="stMetricLabel"] {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_SUB};
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
[data-testid="stMetricDelta"] {{
    font-size: 12px;
    font-weight: 600;
}}

/* Input fields */
.stNumberInput input, .stTextInput input {{
    border-radius: 10px !important;
    border: 1px solid {BORDER} !important;
}}

/* Expanders (input sections) */
.streamlit-expanderHeader {{
    background: {CARD};
    border-radius: 12px;
    font-weight: 600;
    color: {ACCENT_DK};
}}

/* Buttons */
.stButton > button {{
    border-radius: 10px;
    border: 1px solid {BORDER};
    background: {CARD};
    color: {TEXT};
    font-weight: 600;
    padding: 8px 16px;
}}
.stButton > button:hover {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT};
    color: {ACCENT_DK};
}}

.stDownloadButton > button {{
    background: {ACCENT} !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}}
.stDownloadButton > button:hover {{
    background: {ACCENT_DK} !important;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: 8px;
}}
.stTabs [data-baseweb="tab"] {{
    background: {CARD};
    border-radius: 10px;
    padding: 10px 16px;
    font-weight: 600;
    color: {TEXT_SUB};
}}
.stTabs [aria-selected="true"] {{
    background: {ACCENT_SOFT} !important;
    color: {ACCENT_DK} !important;
}}

/* Dataframe */
.stDataFrame {{
    border-radius: 12px;
    overflow: hidden;
}}

/* Hide Streamlit default footer */
footer {{ visibility: hidden; }}
#MainMenu {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ════════════════════════════════════════════════════════════════════════
ENGINE_ORDER = ["rdf", "wte", "rdf_wte", "biogas", "solar"]
ENGINE_LABELS = {
    "rdf":     "🗑️  RDF",
    "wte":     "🔥  WTE",
    "rdf_wte": "🔄  RDF + WTE",
    "biogas":  "🌿  Biogas",
    "solar":   "☀️  Solar PV",
}

if "engine_code" not in st.session_state:
    st.session_state.engine_code = "wte"
if "params" not in st.session_state:
    st.session_state.params = REGISTRY[st.session_state.engine_code].default_preset()
if "uploaded_scenario" not in st.session_state:
    st.session_state.uploaded_scenario = None


def reset_engine(new_code: str):
    """Switch engine — clear all input widget state for new engine."""
    st.session_state.engine_code = new_code
    st.session_state.params = REGISTRY[new_code].default_preset()
    # Drop any old widget keys
    for k in list(st.session_state.keys()):
        if k.startswith("inp__"):
            del st.session_state[k]


# ════════════════════════════════════════════════════════════════════════
# SIDEBAR — Engine picker
# ════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:12px; padding:12px 0 18px;">
      <div style="font-size:32px; color:{ACCENT};">◢</div>
      <div style="font-size:22px; font-weight:700; color:{TEXT};">FeasFlow</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div style="color:{TEXT_MUTED}; font-size:11px; font-weight:700; '
                 f'letter-spacing:0.1em; margin-bottom:8px;">MAIN MENU</div>',
                 unsafe_allow_html=True)

    selected = st.radio(
        "Plant Type",
        options=ENGINE_ORDER,
        format_func=lambda c: ENGINE_LABELS[c],
        index=ENGINE_ORDER.index(st.session_state.engine_code),
        label_visibility="collapsed",
    )
    if selected != st.session_state.engine_code:
        reset_engine(selected)
        st.rerun()

    st.divider()

    if st.button("↺ Reset to preset", use_container_width=True):
        reset_engine(st.session_state.engine_code)
        st.rerun()

    # Save scenario
    params_dict = asdict(st.session_state.params)
    scenario_json = json.dumps(
        {"engine": st.session_state.engine_code, "params": params_dict},
        indent=2, ensure_ascii=False,
    )
    st.download_button(
        "💾  Save scenario (.json)",
        data=scenario_json,
        file_name=f"{st.session_state.engine_code}_"
                   f"{params_dict.get('project_name','project').replace(' ','_')}.json",
        mime="application/json",
        use_container_width=True,
    )

    # Load scenario
    uploaded = st.file_uploader("📂  Load scenario (.json)", type="json",
                                  label_visibility="collapsed")
    if uploaded is not None and uploaded != st.session_state.uploaded_scenario:
        try:
            data = json.loads(uploaded.read().decode("utf-8"))
            engine = data.get("engine", st.session_state.engine_code)
            if engine in REGISTRY:
                st.session_state.engine_code = engine
                InputsCls = type(REGISTRY[engine].default_preset())
                st.session_state.params = InputsCls(**data.get("params", data))
                st.session_state.uploaded_scenario = uploaded
                # Clear widget state
                for k in list(st.session_state.keys()):
                    if k.startswith("inp__"):
                        del st.session_state[k]
                st.success("Loaded!")
                st.rerun()
        except Exception as e:
            st.error(f"Load failed: {e}")

    st.markdown(f"<div style='position:absolute; bottom:16px; color:{TEXT_MUTED}; "
                 f"font-size:10px;'>v2.1  ·  multi-engine</div>",
                 unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ════════════════════════════════════════════════════════════════════════
mod = REGISTRY[st.session_state.engine_code]
meta = mod.META
params = st.session_state.params

# Header
st.markdown(f"""
<div style="margin-bottom:8px;">
  <div class="feas-title">{meta['icon']}  {ENGINE_LABELS[st.session_state.engine_code].strip().split(maxsplit=1)[1]} feasibility</div>
  <div class="feas-subtitle">{meta['description']}<br>
    Project: {params.project_name}</div>
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# INPUT WIDGETS — read values, build new params
# ════════════════════════════════════════════════════════════════════════
def render_input(key: str, label: str, ftype: str, hint: str, current):
    """Render appropriate Streamlit widget; return new value."""
    widget_key = f"inp__{st.session_state.engine_code}__{key}"
    help_text = hint if hint else None

    if ftype == "bool":
        return st.checkbox(label, value=bool(current),
                            help=help_text, key=widget_key)

    if ftype.startswith("choice:"):
        options = ftype.split(":", 1)[1].split("|")
        try:
            idx = options.index(str(current))
        except ValueError:
            idx = 0
        return st.selectbox(label, options, index=idx,
                              help=help_text, key=widget_key)

    if ftype == "pct":
        val = float(current) * 100
        return st.number_input(label, value=val, step=0.1,
                                 format="%.2f", help=help_text,
                                 key=widget_key) / 100.0

    if ftype == "int":
        return int(st.number_input(label, value=int(current), step=1,
                                       help=help_text, key=widget_key))

    if ftype == "float":
        return st.number_input(label, value=float(current),
                                 format="%.4f", help=help_text, key=widget_key)

    # default str
    return st.text_input(label, value=str(current),
                           help=help_text, key=widget_key)


# Layout: inputs (left) + results (right)
left_col, right_col = st.columns([1, 2.2], gap="medium")

with left_col:
    st.markdown(f'<div style="font-weight:700; color:{TEXT}; '
                 f'margin-bottom:8px; font-size:15px;">📋 Inputs</div>',
                 unsafe_allow_html=True)

    new_values = {}
    for section_title, field_list in mod.INPUT_SECTIONS:
        with st.expander(section_title, expanded=False):
            for spec in field_list:
                key, label, ftype, hint = spec
                current = getattr(params, key)
                new_values[key] = render_input(key, label, ftype, hint, current)

    # Apply new values to params
    for k, v in new_values.items():
        setattr(params, k, v)


# ════════════════════════════════════════════════════════════════════════
# COMPUTE
# ════════════════════════════════════════════════════════════════════════
try:
    results = mod.run_model(params)
except Exception as e:
    st.error(f"Engine error: {e}")
    st.stop()

k = results["kpis"]
gen = results["generation"]
cx = results["capex"]
wacc = results["wacc"]
rows = results["rows"]


# ════════════════════════════════════════════════════════════════════════
# OUTPUT (right column + below)
# ════════════════════════════════════════════════════════════════════════
with right_col:
    # ── Status banner ────────────────────────────────────────────────
    eirr = k.get("equity_irr") or 0
    dscr = k.get("dscr_min")
    hurdle = 0.12
    if eirr < 0:
        st.markdown(f'<div class="status-fail">🔴  Equity IRR {eirr*100:.2f}% '
                     f'— Project loses money</div>',
                     unsafe_allow_html=True)
    elif eirr < hurdle:
        st.markdown(f'<div class="status-warn">⚠️  Equity IRR {eirr*100:.2f}% '
                     f'below 12% hurdle — Marginal, consider tuning</div>',
                     unsafe_allow_html=True)
    elif dscr is not None and dscr < 1.20:
        st.markdown(f'<div class="status-warn">⚠️  DSCR min {dscr:.2f} '
                     f'below 1.20 — Not bankable</div>',
                     unsafe_allow_html=True)
    else:
        dscr_s = f"{dscr:.2f}" if dscr else "n/a"
        st.markdown(f'<div class="status-pass">✅  Equity IRR {eirr*100:.2f}% · '
                     f'DSCR min {dscr_s} — Project is viable</div>',
                     unsafe_allow_html=True)

    # ── KPI cards (3 columns × 3 rows) ───────────────────────────────
    def pct(v):
        return f"{v*100:.2f}%" if v is not None else "n/a"
    def num(v, d=2):
        return f"{v:.{d}f}" if v is not None else "n/a"

    is_rdf = st.session_state.engine_code == "rdf"
    cost_label = "LCO-Pellet" if is_rdf else "LCOE"
    cost_value = (f"{k.get('lco_pellet_thb_per_ton', 0):.0f}"
                   if is_rdf
                   else f"{k.get('lcoe_thb_per_kwh', 0):.2f}")
    cost_unit = "฿/ton" if is_rdf else "฿/kWh"

    def delta_for_irr(v, target=0.12):
        if v is None: return None
        diff = (v - target) * 100
        return f"{diff:+.2f}pp vs hurdle"

    def delta_for_dscr(v, target=1.30):
        if v is None: return None
        diff = v - target
        return f"{diff:+.2f} vs 1.30"

    r1c1, r1c2, r1c3 = st.columns(3)
    r1c1.metric("Project IRR", pct(k["project_irr"]),
                 delta=delta_for_irr(k["project_irr"]))
    r1c2.metric("Equity IRR", pct(k["equity_irr"]),
                 delta=delta_for_irr(k["equity_irr"]))
    r1c3.metric("Equity NPV", f"{k['equity_npv']:.0f} MB",
                 delta=f"@ {params.discount_rate*100:.2f}%",
                 delta_color="off")

    r2c1, r2c2, r2c3 = st.columns(3)
    r2c1.metric("DSCR min", num(k["dscr_min"]),
                 delta=delta_for_dscr(k["dscr_min"]))
    r2c2.metric("DSCR avg", num(k["dscr_avg"]),
                 delta=delta_for_dscr(k["dscr_avg"]))
    r2c3.metric(cost_label, cost_value, delta=cost_unit, delta_color="off")

    r3c1, r3c2, r3c3 = st.columns(3)
    r3c1.metric("BCR", f"{k['bcr']:.3f}x",
                 delta="> 1 viable" if k['bcr'] >= 1 else "< 1 marginal",
                 delta_color="normal" if k['bcr'] >= 1 else "inverse")
    r3c2.metric("Payback (Eq.)",
                 f"{(k['payback_equity'] or 0):.1f} yr",
                 delta="from COD", delta_color="off")
    r3c3.metric("WACC", pct(k["wacc"]), delta="CAPM-derived",
                 delta_color="off")


# ════════════════════════════════════════════════════════════════════════
# TABS BELOW: Cashflow · Charts · Raw Material · WACC · Export
# ════════════════════════════════════════════════════════════════════════
st.markdown("&nbsp;")
tab_cf, tab_charts, tab_raw, tab_wacc, tab_exp = st.tabs(
    ["📊 Cashflow", "📈 Charts", "🔬 Raw Material", "💰 WACC · CAPEX", "⬇️ Export"]
)


# ── TAB: Cashflow ───────────────────────────────────────────────────
with tab_cf:
    df_cf = pd.DataFrame(rows)
    cum = []
    s = 0
    for r in rows:
        s += r["fcfe"]
        cum.append(s)
    df_cf["cum_fcfe"] = cum

    show_cols = {
        "year":           "Yr",
        "calendar_year":  "Calendar",
        "revenue":        "Revenue",
        "opex":           "OPEX",
        "ebitda":         "EBITDA",
        "depreciation":   "Dep",
        "ebit":           "EBIT",
        "interest":       "Interest",
        "tax":            "Tax",
        "npat":           "NPAT",
        "ocf":            "OCF",
        "dscr":           "DSCR",
        "fcfe":           "FCFE",
        "cum_fcfe":       "Σ FCFE",
    }
    df_show = df_cf[list(show_cols.keys())].rename(columns=show_cols)
    # Format DSCR — replace inf
    df_show["DSCR"] = df_show["DSCR"].apply(
        lambda v: "inf" if v >= 1e9 else f"{v:.2f}")
    st.dataframe(df_show.style.format({
        "Revenue":   "{:,.1f}", "OPEX": "{:,.1f}", "EBITDA": "{:,.1f}",
        "Dep":       "{:,.1f}", "EBIT": "{:,.1f}", "Interest": "{:,.1f}",
        "Tax":       "{:,.1f}", "NPAT": "{:,.1f}", "OCF": "{:,.1f}",
        "FCFE":      "{:,.1f}", "Σ FCFE": "{:,.1f}",
    }), use_container_width=True, height=400, hide_index=True)


# ── TAB: Charts ────────────────────────────────────────────────────
with tab_charts:
    yrs = [r["calendar_year"] for r in rows]

    # Chart 1: Revenue + NPAT
    fit_r = [r["fit_rev"]    for r in rows]
    tip_r = [r["tip_rev"]    for r in rows]
    rdf_r = [r["rdf_rev"]    for r in rows]
    car_r = [r["carbon_rev"] for r in rows]
    npat  = [r["npat"]       for r in rows]

    fig1 = go.Figure()
    if any(fit_r):
        fig1.add_trace(go.Bar(x=yrs, y=fit_r, name="FiT/Electricity",
                                marker_color=ACCENT))
    if any(tip_r):
        fig1.add_trace(go.Bar(x=yrs, y=tip_r, name="Tipping",
                                marker_color="#26C6DA"))
    if any(rdf_r):
        fig1.add_trace(go.Bar(x=yrs, y=rdf_r, name="RDF Sales",
                                marker_color="#A371F7"))
    if any(c > 0 for c in car_r):
        fig1.add_trace(go.Bar(x=yrs, y=car_r, name="Carbon",
                                marker_color=SUCCESS))
    fig1.add_trace(go.Scatter(x=yrs, y=npat, name="NPAT", mode="lines+markers",
                                 line=dict(color=ERROR, width=2.5),
                                 marker=dict(size=6)))
    fig1.update_layout(
        title="Revenue Composition + NPAT (MB/yr)",
        barmode="stack",
        plot_bgcolor=CARD,
        paper_bgcolor=CARD,
        font=dict(color=TEXT, size=11),
        height=380,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", y=1.05, x=0),
    )

    # Chart 2: Cumulative CF
    cum_e = results["cum_fcfe"]
    cum_p = results["cum_fcff"]
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=yrs, y=cum_e, name="Cum FCFE (equity)",
                                 mode="lines", fill="tozeroy",
                                 line=dict(color=SUCCESS, width=2.5),
                                 fillcolor="rgba(31,188,89,0.15)"))
    fig2.add_trace(go.Scatter(x=yrs, y=cum_p, name="Cum FCFF (project)",
                                 mode="lines",
                                 line=dict(color=INFO, width=1.5, dash="dash")))
    fig2.add_hline(y=0, line_dash="dot", line_color=TEXT_MUTED)
    pb = k.get("payback_equity")
    if pb is not None and pb < len(yrs):
        fig2.add_vline(x=yrs[0] + pb - 1, line_dash="dash",
                        line_color=WARNING,
                        annotation_text=f"Payback {pb:.1f}yr")
    fig2.update_layout(
        title="Cumulative Cash Flow (MB)",
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(color=TEXT, size=11),
        height=380, margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", y=1.05, x=0),
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig1, use_container_width=True)
    with c2:
        st.plotly_chart(fig2, use_container_width=True)

    # Chart 3: DSCR
    dscr_vals = [r["dscr"] if r["dscr"] < 1e9 else None for r in rows]
    valid = [(y, d) for y, d in zip(yrs, dscr_vals) if d is not None]
    if valid:
        vy, vd = zip(*valid)
        colors = [SUCCESS if d >= 1.30 else (WARNING if d >= 1.20 else ERROR)
                   for d in vd]
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(x=vy, y=vd, marker_color=colors,
                                name="DSCR"))
        fig3.add_hline(y=1.30, line_dash="dash", line_color=SUCCESS,
                        annotation_text="Bank 1.30x")
        fig3.add_hline(y=1.20, line_dash="dash", line_color=WARNING,
                        annotation_text="Min 1.20x")
        fig3.update_layout(
            title="DSCR Profile",
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            height=380, margin=dict(l=40, r=20, t=50, b=40),
            showlegend=False,
        )
    else:
        fig3 = None

    # Chart 4: OPEX breakdown stack
    opex_keys = [
        ("opex_om",        "O&M",          NAVY),
        ("opex_feedstock", "Feedstock",    "#B15224"),
        ("opex_ash",       "Ash",          "#9F4A0A"),
        ("opex_flue",      "Flue Gas",     WARNING),
        ("opex_aux",       "Aux/Transport",ACCENT),
        ("opex_sga",       "SG&A",         SUCCESS),
        ("opex_insurance", "Insurance",    INFO),
        ("opex_pdf",       "PDF/Misc",     "#A371F7"),
    ]
    fig4 = go.Figure()
    for k_, lbl, col in opex_keys:
        vals = [r.get(k_, 0) for r in rows]
        if not any(vals):
            continue
        fig4.add_trace(go.Bar(x=yrs, y=vals, name=lbl, marker_color=col))
    fig4.update_layout(
        title="OPEX Breakdown (MB/yr)",
        barmode="stack",
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(color=TEXT, size=11),
        height=380, margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", y=1.05, x=0),
    )

    c3, c4 = st.columns(2)
    with c3:
        if fig3:
            st.plotly_chart(fig3, use_container_width=True)
    with c4:
        st.plotly_chart(fig4, use_container_width=True)


# ── TAB: Raw Material ──────────────────────────────────────────────
with tab_raw:
    raw = results["raw_material"]
    engine = st.session_state.engine_code

    if engine in ("wte", "rdf", "rdf_wte") and raw.get("chemistry"):
        chem = raw["chemistry"]
        viab = ("✅ VIABLE" if chem.get("viable_target")
                 else "⚠️ Marginal" if chem.get("viable_min")
                 else "❌ NOT VIABLE")
        st.markdown(f"### 🔥 MSW Chemistry — Dulong's Formula")
        st.markdown(f"**LHV** = {chem['lhv_kcal_per_kg']:,.0f} kcal/kg "
                     f"({chem['lhv_mj_per_kg']:.2f} MJ/kg) · "
                     f"**HHV** = {chem['hhv_kcal_per_kg']:,.0f} kcal/kg · "
                     f"{viab}")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Elements (% wet weight)**")
            elem_df = pd.DataFrame([
                {"Element": e, "%": chem["totals"][e]}
                for e in ("C", "H", "O", "N", "S", "Ash")
            ])
            st.dataframe(elem_df.style.format({"%": "{:.3f}"}),
                          hide_index=True, use_container_width=True)
        with col_b:
            st.markdown("**Component HHV contribution**")
            comp_rows = []
            for cname, cdata in chem["per_component"].items():
                if cdata["wet_pct"] <= 0:
                    continue
                comp_rows.append({
                    "Component": cname.capitalize(),
                    "Wet %": cdata["wet_pct"],
                    "HHV (kcal/kg)": cdata["hhv_contrib"],
                })
            comp_df = pd.DataFrame(comp_rows)
            st.dataframe(comp_df.style.format({"Wet %": "{:.1f}",
                                                   "HHV (kcal/kg)": "{:,.1f}"}),
                          hide_index=True, use_container_width=True)

    elif engine == "biogas":
        st.markdown("### 🌿 Biogas Chemistry Chain (COD → kWh)")
        st.markdown(f"**{raw['biogas_m3_per_m3']:.2f}** m³-biogas/m³ feed → "
                     f"**{raw['kwh_per_m3']:.2f}** kWh/m³")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Per 1 m³ feed**")
            chain_df = pd.DataFrame([
                ("COD Load",       f"{raw['cod_load_kg_per_m3']:.2f} kg-COD"),
                ("COD Removed",    f"{raw['cod_removed_kg_per_m3']:.2f} kg"),
                ("CH₄ Produced",   f"{raw['ch4_m3_per_m3']:.2f} m³-CH₄"),
                ("Biogas",         f"{raw['biogas_m3_per_m3']:.2f} m³-bg"),
                ("LHV",            f"{raw['lhv_mj_per_m3']:.2f} MJ/m³-bg"),
                ("Energy thermal", f"{raw['energy_thermal_mj_per_m3']:.1f} MJ"),
                ("kWh / m³ feed",  f"{raw['kwh_per_m3']:.2f} kWh"),
            ], columns=["Metric", "Value"])
            st.dataframe(chain_df, hide_index=True, use_container_width=True)
        with col_b:
            st.markdown("**Required volume**")
            req_df = pd.DataFrame([
                ("Target gen",     f"{raw['target_mwh_yr']:,.0f} MWh/yr"),
                ("m³ / day",       f"{raw['m3_per_day']:,.0f}"),
                ("m³ / yr",        f"{raw['m3_per_yr']:,.0f}"),
            ], columns=["Metric", "Value"])
            st.dataframe(req_df, hide_index=True, use_container_width=True)
        with col_c:
            st.markdown("**Cost analysis**")
            cost_df = pd.DataFrame([
                ("Total ฿/m³ feed",   f"{raw['total_cost_thb_per_m3']:.2f}"),
                ("฿ / m³ biogas",      f"{raw['cost_per_m3_biogas']:.3f}"),
                ("💰 ฿ / kWh feed",   f"{raw['cost_per_kwh_feedstock']:.4f}"),
                ("Annual feed cost",   f"{raw['feedstock_cost_mb_yr']:.2f} MB/yr"),
            ], columns=["Metric", "Value"])
            st.dataframe(cost_df, hide_index=True, use_container_width=True)

    elif engine == "solar":
        st.markdown(f"### ☀️ Solar Generation — PVWatts + TOU")
        st.markdown(f"**{raw['annual_generation_kwh']/1000:,.0f}** MWh/yr · "
                     f"CF **{raw['capacity_factor']*100:.1f}%** · "
                     f"Effective yield **{raw['effective_yield']:,.0f}** kWh/kWp/yr")

        col_a, col_b = st.columns([1, 1.5])
        with col_a:
            st.markdown("**Resource**")
            res_df = pd.DataFrame([
                ("Location",         raw['location']),
                ("Capacity",         f"{raw['capacity_kwp']:,.0f} kWp"),
                ("PVWatts yield",    f"{raw['specific_yield']:,.1f} kWh/kWp/yr"),
                ("Cooling gain",     f"{raw['cooling_gain']:.2f} ×"),
                ("Effective yield",  f"{raw['effective_yield']:,.1f}"),
                ("Capacity factor",  f"{raw['capacity_factor']*100:.2f} %"),
                ("Peak share",       f"{raw['peak_ratio']*100:.1f} %"),
                ("Annual revenue",   f"{(raw['annual_value_thb'] or 0)/1e6:.2f} MB/yr"),
            ], columns=["Metric", "Value"])
            st.dataframe(res_df, hide_index=True, use_container_width=True)
        with col_b:
            st.markdown("**Monthly generation**")
            mo_df = pd.DataFrame([
                {
                    "Month": m['name'],
                    "kWh/kWp/d": m['daily_yield'],
                    "MWh": m['generation_kwh']/1000,
                    "Peak%": m['peak_share']*100,
                }
                for m in raw['monthly']
            ])
            st.dataframe(mo_df.style.format({
                "kWh/kWp/d": "{:.2f}",
                "MWh":       "{:,.1f}",
                "Peak%":     "{:.1f}",
            }), hide_index=True, use_container_width=True)


# ── TAB: WACC & CAPEX ─────────────────────────────────────────────
with tab_wacc:
    col_w, col_c = st.columns(2)
    with col_w:
        st.markdown("### 💼 WACC (CAPM)")
        wacc_df = pd.DataFrame([
            ("Risk-Free Rate (Rf)",      f"{wacc['rf']*100:.2f}%"),
            ("Market Risk Premium",      f"{wacc['mrp']*100:.2f}%"),
            ("β unlevered",              f"{wacc['beta_unlevered']:.3f}"),
            ("β levered",                f"{wacc['beta_levered']:.3f}"),
            ("Ke (cost of equity)",      f"{wacc['ke']*100:.2f}%"),
            ("Kd (interest)",            f"{wacc['kd']*100:.2f}%"),
            ("Kd × (1 − t)",             f"{wacc['kd_aftertax']*100:.2f}%"),
            ("D/E ratio",                f"{wacc['de_ratio']:.3f}"),
            ("**WACC**",                 f"**{wacc['wacc']*100:.2f}%**"),
        ], columns=["Component", "Value"])
        st.dataframe(wacc_df, hide_index=True, use_container_width=True)

    with col_c:
        st.markdown("### 🏗️ CAPEX Breakdown")
        capex_df = pd.DataFrame([
            ("EPC",                f"{cx['epc']:,.1f} MB"),
            ("Owner's Cost",       f"{cx['owner_cost']:,.1f} MB"),
            ("Contingency",        f"{cx['contingency']:,.1f} MB"),
            ("IDC",                f"{cx['idc']:,.1f} MB"),
            ("**Total CAPEX**",    f"**{cx['total_capex']:,.1f} MB**"),
            ("Equity",             f"{cx['equity']:,.1f} MB"),
            ("Debt",               f"{cx['debt']:,.1f} MB"),
            ("CAPEX per MW",
              f"{cx['capex_per_mw_installed']:.0f} MB/MW"
              if cx['capex_per_mw_installed'] > 0 else "—"),
        ], columns=["Item", "Value"])
        st.dataframe(capex_df, hide_index=True, use_container_width=True)

        carbon = results.get("carbon", {})
        if carbon.get("rev_mb_yr", 0) > 0 or carbon.get("tco2_yr", 0) > 0:
            st.markdown("### 🌱 Carbon Credit")
            st.metric("Annual revenue",
                       f"{carbon.get('rev_mb_yr', 0):.2f} MB/yr",
                       delta=f"{carbon.get('tco2_yr', 0):,.0f} tCO₂eq avoided/yr",
                       delta_color="off")


# ── TAB: Export ───────────────────────────────────────────────────
with tab_exp:
    st.markdown("### 📥 Download reports")

    col_x, col_p = st.columns(2)

    safe_name = params.project_name.replace(" ", "_").replace("/", "-")

    # Excel export
    with col_x:
        st.markdown("**Excel report** — Summary, Cashflow, Loan Table, WACC, "
                      "Revenue/OPEX details (7 sheets)")
        try:
            from feas_excel import export_feas_report
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                xlsx_path = export_feas_report(
                    results, tmp.name,
                    engine_code=st.session_state.engine_code,
                )
            with open(xlsx_path, "rb") as f:
                xlsx_bytes = f.read()
            st.download_button(
                "📊  Download Excel (.xlsx)",
                data=xlsx_bytes,
                file_name=f"{st.session_state.engine_code}_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")

    # PDF export
    with col_p:
        st.markdown("**PDF report** — Cover + KPI grid, Cashflow, Charts, "
                      "Assumptions (4 A4 pages)")
        try:
            from feas_pdf import export_feas_pdf
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                pdf_path = export_feas_pdf(
                    results, tmp.name,
                    engine_code=st.session_state.engine_code,
                )
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            st.download_button(
                "📄  Download PDF (.pdf)",
                data=pdf_bytes,
                file_name=f"{st.session_state.engine_code}_{safe_name}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF export failed: {e}")

    st.divider()
    st.markdown(f"<div style='color:{TEXT_MUTED}; font-size:11px;'>"
                 f"Generated {datetime.now():%Y-%m-%d %H:%M}  ·  "
                 f"Engine: {st.session_state.engine_code}  ·  "
                 f"FeasFlow v2.1</div>",
                 unsafe_allow_html=True)
