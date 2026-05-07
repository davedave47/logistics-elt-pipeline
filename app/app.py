"""
HCMC Delivery Operations Dashboard.

Usage:
    streamlit run app/app.py -- --source local
    streamlit run app/app.py -- --source cloud
"""
import os
import argparse
import duckdb
import pandas as pd
import streamlit as st
import pydeck as pdk
import altair as alt
import h3
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'logistics.duckdb')

st.set_page_config(
    page_title="HCMC Delivery Ops",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stApp"] {
    font-family: 'Inter', sans-serif !important;
    background: #f0f4f8 !important;
}
#MainMenu, footer, header,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stHeader"], [data-testid="collapsedControl"] {
    display: none !important;
}

.block-container {
    padding: 0 3rem 2rem !important; 
    max-width: 100% !important;
}

/* --- Navigation Bar Redesign --- */
/* Make the tab container full width */
div[data-baseweb="tab-list"] {
    display: flex !important;
    width: 100% !important;
    background: #ffffff !important;
    border-bottom: 1px solid #e2e8f0 !important;
    padding: 0 !important;
    margin-bottom: 0 !important;
}

/* Distribute tabs evenly */
button[data-baseweb="tab"] {
    flex: 1 !important;
    display: flex !important;
    justify-content: center !important;
    margin: 0 !important;
    border-radius: 0 !important;
    padding: 1rem 0 !important;
    background: transparent !important;
}

button[data-baseweb="tab"] p {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
}

/* Match the highlight bar to the header blue */
div[data-baseweb="tab-highlight"] {
    height: 3px !important;
    background-color: #1d4ed8 !important;
}

/* Prevent Vega-Lite SVG from clipping long Y-axis labels */
[data-testid="stArrowVegaLiteChart"] svg,
[data-testid="stVegaLiteChart"] svg {
    overflow: visible !important;
}
</style>
""", unsafe_allow_html=True)


# ── CLI source ────────────────────────────────────────────────────────────────

def _parse_source():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--source", choices=["local", "cloud"], default=None)
    return p.parse_known_args()[0].source


CLI_SOURCE = _parse_source()


# ── Connections ───────────────────────────────────────────────────────────────

@st.cache_resource
def _duck():
    return duckdb.connect(DB_PATH, read_only=True)


@st.cache_resource
def _bq(proj):
    from google.cloud import bigquery
    return bigquery.Client(project=proj)


def run(sql, eng, proj=""):
    if eng == "duckdb":
        return _duck().execute(sql).fetchdf()
    return _bq(proj).query(sql).to_dataframe()


def T(name, ds, eng, proj):
    return f"{ds}.{name}" if eng == "duckdb" else f"`{proj}.{ds}.{name}`"


# ── Loaders ───────────────────────────────────────────────────────────────────

@st.cache_data
def load_kpis(ds, eng, proj=""):
    return run(f"SELECT * FROM {T('mart_kpis', ds, eng, proj)}", eng, proj)


@st.cache_data
def load_district(ds, eng, proj=""):
    return run(f"SELECT * FROM {T('mart_district', ds, eng, proj)} ORDER BY avg_delay_minutes DESC", eng, proj)


@st.cache_data
def load_h3_zones(ds, eng, proj=""):
    return run(
        f"SELECT h3_cell_9, avg_delay_minutes, total_deliveries, total_margin_gap_usd,"
        f" is_hotspot, dominant_district, failure_rate_pct"
        f" FROM {T('mart_h3', ds, eng, proj)}",
        eng, proj,
    )


@st.cache_data
def load_hotspots(ds, eng, proj=""):
    return run(
        f"SELECT h3_cell_9, dominant_district district, total_deliveries, avg_delay_minutes,"
        f" total_margin_gap_usd, failure_rate_pct, dominant_traffic_zone, hem_access_pct"
        f" FROM {T('mart_h3', ds, eng, proj)} WHERE is_hotspot = true"
        f" ORDER BY avg_delay_minutes DESC LIMIT 50",
        eng, proj,
    )


@st.cache_data
def _hcmc_base_cells():
    poly = h3.LatLngPoly([
        (10.63, 106.56), (10.63, 106.81),
        (10.91, 106.81), (10.91, 106.56),
    ])
    return pd.DataFrame({"h3_cell_9": list(h3.geo_to_cells(poly, 9))})


# ── Top bar ───────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="background:#1d4ed8;padding:.65rem 1.5rem;display:flex;align-items:center;justify-content:space-between;">'
    '<div>'
    '<span style="font-size:.58rem;font-family:\'JetBrains Mono\',monospace;letter-spacing:.16em;text-transform:uppercase;color:#93c5fd;">Last-Mile Analytics</span>'
    '<span style="font-size:1.05rem;font-weight:700;color:#ffffff;margin-left:1rem;letter-spacing:-.01em;">HCMC Delivery Operations</span>'
    '</div>'
    '<span style="font-size:.7rem;color:#bfdbfe;font-family:\'JetBrains Mono\',monospace;">Ho Chi Minh City · 2024</span>'
    '</div>',
    unsafe_allow_html=True,
)


# ── Source Logic ──────────────────────────────────────────────────────────────

if CLI_SOURCE == "cloud":
    GCP_PROJECT = st.secrets.get("gcp_project", "") or os.environ.get("GCP_PROJECT", "")
    BQ_DATASET  = st.secrets.get("bq_dataset", "") or os.environ.get("BQ_DATASET_MARTS", "logistics_marts")
    if not GCP_PROJECT:
        st.error("Set `GCP_PROJECT` env var or `gcp_project` in `.streamlit/secrets.toml`"); st.stop()
    DS, ENG, PROJ = BQ_DATASET, "bigquery", GCP_PROJECT
else:
    DS, ENG, PROJ = "main", "duckdb", ""


# ── Bootstrap ─────────────────────────────────────────────────────────────────

try:
    kpi_df  = load_kpis(DS, ENG, PROJ)
    dist_df = load_district(DS, ENG, PROJ)
except Exception as e:
    st.error(f"Could not reach mart tables. {e}")
    cmd = "`cd local/dbt && dbt run`" if ENG == "duckdb" else "`cd cloud/dataform && dataform run`"
    st.info(f"Run {cmd} first."); st.stop()


# ── Design tokens ─────────────────────────────────────────────────────────────

_RED    = "#ef4444"
_ORANGE = "#f97316"
_GREEN  = "#10b981"
_BLUE   = "#3b82f6"
_CARD   = "#ffffff"
_BORDER = "#e2e8f0"
_GRID   = "#f8fafc"
_LBL    = "#64748b"
_TEXT   = "#334155"

_DIST_ABBR = {
    'Quận 1': 'Q1', 'Quận 3': 'Q3', 'Quận 4': 'Q4', 'Quận 5': 'Q5',
    'Quận 7': 'Q7', 'Quận 10': 'Q10', 'Bình Thạnh': 'BTh', 'Gò Vấp': 'GV',
    'Tân Bình': 'TB', 'Thủ Đức': 'TĐ', 'Bình Chánh': 'BC',
}


def _zlabel(cell_id, district):
    abbr = _DIST_ABBR.get(district, district[:3] if district else "—")
    return f"{abbr}·{cell_id[-4:]}"


# ── Component helpers ─────────────────────────────────────────────────────────

def kpi(col, label, value, sub="", accent=None):
    c = accent or _BLUE
    sub_span = f'<span style="display:block;font-size:.68rem;color:{_LBL};margin-top:.2rem;">{sub}</span>' if sub else ""
    mono = "font-family:'JetBrains Mono',monospace;"
    with col:
        st.markdown(
            f'<div style="background:{_CARD};border:1px solid {_BORDER};border-radius:8px;padding:1rem 1.1rem;border-left:4px solid {c};box-shadow:0 1px 3px rgba(0,0,0,.05);">'
            f'<span style="display:block;font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:{_LBL};font-weight:500;margin-bottom:.3rem;">{label}</span>'
            f'<span style="display:block;font-size:1.6rem;font-weight:700;color:#0f172a;{mono}line-height:1;">{value}</span>'
            f'{sub_span}</div>',
            unsafe_allow_html=True,
        )


def section(text):
    st.markdown(
        f'<p style="font-size:.6rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#94a3b8;margin:.25rem 0 .5rem;padding-bottom:.35rem;border-bottom:1px solid {_BORDER};">{text}</p>',
        unsafe_allow_html=True,
    )



def _cfg(chart):
    return (
        chart
        .configure_view(strokeWidth=1, stroke=_BORDER, fill=_CARD)
        .configure_axis(
            domainColor=_BORDER, gridColor=_GRID,
            labelColor=_LBL, titleColor=_LBL,
            labelFont="Inter", titleFont="Inter",
            labelFontSize=11, titleFontSize=11,
        )
        .configure_legend(
            labelColor=_LBL, titleColor=_LBL,
            labelFont="Inter", titleFont="Inter", labelFontSize=11,
        )
    )


def hbar(df, x, y, x_title, color=None, h=300):
    enc = dict(
        x=alt.X(f"{x}:Q", title=x_title,
                axis=alt.Axis(grid=True, gridColor=_GRID, labelColor=_LBL, titleColor=_LBL)),
        y=alt.Y(f"{y}:N", sort="-x", title=None,
                axis=alt.Axis(labelColor=_TEXT, labelLimit=320, minExtent=80)),
        tooltip=[alt.Tooltip(f"{y}:N"), alt.Tooltip(f"{x}:Q", format=",.1f")],
    )
    if color is not None:
        enc["color"] = color
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(**enc).properties(height=h)


# ── Navigation ────────────────────────────────────────────────────────────────

tab_ov, tab_map, tab_hs = st.tabs(["Overview", "Problem Zones", "High-Risk Zones"])

# ── Page: Overview ────────────────────────────────────────────────────────────

with tab_ov:
    st.write("")

    k   = kpi_df.iloc[0]
    pct = float(k["pct_severely_delayed"])
    gap = float(k["total_margin_gap_usd"])
    n_h3 = int(k["unique_h3_cells"])

    c1, c2, c3, c4, c5 = st.columns(5)
    kpi(c1, "Total Deliveries",    f"{int(k['total_deliveries']):,}")
    kpi(c2, "Avg Delay",           f"{k['avg_delay_minutes']} min",             accent=_ORANGE)
    kpi(c3, "Severely Delayed",    f"{pct:.1f}%",  ">15 min late",              accent=_RED if pct > 50 else _ORANGE)
    kpi(c4, "Driver Cost at Risk", f"${int(k['at_risk_cost_usd']):,}", "uncompensated", accent=_ORANGE)
    kpi(c5, "Margin Gap",          f"${int(gap):,}", "delay minus freight",     accent=_RED if gap > 0 else _GREEN)

    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)

    chart_tab_delay, chart_tab_gap = st.tabs(["Avg Delay by District", "Margin Gap by District"])

    with chart_tab_delay:
        section("Avg delay by district (min)")
        st.altair_chart(
            _cfg(hbar(dist_df, "avg_delay_minutes", "destination_district", "Avg Delay (min)",
                      color=alt.Color("avg_delay_minutes:Q",
                                      scale=alt.Scale(scheme="orangered"), legend=None))),
            use_container_width=True,
        )

    with chart_tab_gap:
        section("Margin gap by district (USD)")
        dist_mg = dist_df.copy()
        dist_mg["type"] = dist_mg["margin_gap_usd"].map(lambda v: "Loss" if v > 0 else "Profit")
        mg = (
            alt.Chart(dist_mg).mark_bar(cornerRadiusEnd=4).encode(
                x=alt.X("margin_gap_usd:Q", title="Margin Gap ($)",
                         axis=alt.Axis(grid=True, gridColor=_GRID, labelColor=_LBL, titleColor=_LBL)),
                y=alt.Y("destination_district:N", sort="-x", title=None,
                         axis=alt.Axis(labelColor=_TEXT, labelLimit=320, minExtent=80)),
                color=alt.Color("type:N",
                                scale=alt.Scale(domain=["Loss", "Profit"], range=[_RED, _GREEN]),
                                legend=alt.Legend(title=None, orient="bottom",
                                                  labelColor=_LBL, labelFont="Inter")),
                tooltip=[alt.Tooltip("destination_district:N"),
                         alt.Tooltip("margin_gap_usd:Q", format=",.0f")],
            ).properties(height=300)
        )
        zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
            color="#cbd5e1", strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart(_cfg(mg + zero), use_container_width=True)



# ── Continuous green → yellow → red colour for delay severity ─────────────────

def _zone_color(row):
    if not row.get("has_data", False) or row["total_deliveries"] == 0:
        return [180, 200, 220, 18]
    delay = float(row["avg_delay_minutes"])
    # Normalise against actual data range: 0 min → green, 35+ min → red
    t = min(delay / 35.0, 1.0)
    # Green (#10b981 16,185,129) → Yellow (#eab308 234,179,8) → Red (#ef4444 239,68,68)
    if t < 0.5:
        s = t * 2
        r, g, b = int(16 + 218 * s), int(185 - 6 * s), int(129 - 121 * s)
    else:
        s = (t - 0.5) * 2
        r, g, b = int(234 + 5 * s), int(179 - 111 * s), int(8 + 60 * s)
    alpha = int(80 + 110 * t)
    return [r, g, b, alpha]


# ── Page: Problem Zones ───────────────────────────────────────────────────────

with tab_map:
    raw_zones = load_h3_zones(DS, ENG, PROJ)

    # Merge data cells onto the full HCMC hex grid so every cell is rendered
    base = _hcmc_base_cells()
    zones = base.merge(raw_zones, on="h3_cell_9", how="left")
    zones["has_data"] = zones["total_deliveries"].notna()
    zones["avg_delay_minutes"]    = zones["avg_delay_minutes"].fillna(0)
    zones["total_deliveries"]     = zones["total_deliveries"].fillna(0).astype(int)
    zones["total_margin_gap_usd"] = zones["total_margin_gap_usd"].fillna(0)
    zones["is_hotspot"]           = zones["is_hotspot"].fillna(False)
    zones["dominant_district"]    = zones["dominant_district"].fillna("—")
    zones["failure_rate_pct"]     = zones["failure_rate_pct"].fillna(0)

    # Compute cell centres so users can locate any zone in Google Maps
    _centers = zones["h3_cell_9"].apply(h3.cell_to_latlng)
    zones["center_lat"] = _centers.apply(lambda c: round(c[0], 5))
    zones["center_lng"] = _centers.apply(lambda c: round(c[1], 5))
    zones["maps_coords"] = zones["center_lat"].astype(str) + ", " + zones["center_lng"].astype(str)

    zones["fill_color"]  = zones.apply(_zone_color, axis=1)
    zones["delay_label"] = zones["avg_delay_minutes"].round(1).astype(str) + " min avg"
    zones["gap_label"]   = zones["total_margin_gap_usd"].round(0).apply(
        lambda v: f"+${v:,.0f} loss" if v > 0 else (f"-${abs(v):,.0f} ok" if v < 0 else "—"))
    zones["status"]       = zones["is_hotspot"].map({True: "HIGH RISK", False: "Normal"})
    zones["status_color"] = zones["is_hotspot"].map({True: "#ef4444",   False: "#10b981"})

    n_hot   = int(zones["is_hotspot"].sum())
    hot_gap = float(zones.loc[zones["is_hotspot"], "total_margin_gap_usd"].sum())
    hot_del = float(zones.loc[zones["is_hotspot"] & zones["has_data"], "avg_delay_minutes"].mean()) if n_hot else 0.0

    c1, c2, c3 = st.columns(3)
    kpi(c1, "High-Risk Zones",   f"{n_hot}",           "H3 cells · avg delay > 15 min", accent=_RED)
    kpi(c2, "Margin Loss in Zones", f"${hot_gap:,.0f}", "across flagged cells",          accent=_RED if hot_gap > 0 else _GREEN)
    kpi(c3, "Avg Delay in Risk Zones", f"{hot_del:.1f} min", "fleet avg ~4 min",         accent=_ORANGE)

    st.write("")

    deck = pdk.Deck(
        layers=[pdk.Layer(
            "H3HexagonLayer",
            id="hex-layer",
            data=zones,
            get_hexagon="h3_cell_9",
            get_fill_color="fill_color",
            stroked=True,
            get_line_color=[80, 80, 80, 160],
            line_width_min_pixels=1,
            filled=True,
            extruded=False,
            pickable=True,
            auto_highlight=True,
        )],
        initial_view_state=pdk.ViewState(latitude=10.775, longitude=106.685, zoom=11.5),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": (
                "<div style='font-family:Inter,sans-serif;font-size:12px;line-height:1.6;'>"
                "<span style='font-family:JetBrains Mono,monospace;font-size:11px;"
                "color:#1d4ed8;font-weight:600;'>{h3_cell_9}</span>"
                "<span style='float:right;font-size:10px;font-weight:700;"
                "color:{status_color};margin-left:8px;'>{status}</span><br>"
                "<span style='color:#64748b;font-size:11px;'>District: {dominant_district}</span>"
                "<hr style='margin:4px 0;border:none;border-top:1px solid #e2e8f0;'>"
                "<span style='color:#64748b;'>Avg delay</span> <b>{delay_label}</b><br>"
                "<span style='color:#64748b;'>Margin gap</span> <b>{gap_label}</b><br>"
                "<span style='color:#64748b;'>Deliveries</span> <b>{total_deliveries}</b><br>"
                "<span style='color:#94a3b8;font-size:10px;'>{maps_coords}</span>"
                "</div>"
            ),
            "style": {
                "backgroundColor": "white",
                "border": "1px solid #e2e8f0",
                "borderRadius": "8px",
                "padding": "10px 14px",
                "boxShadow": "0 2px 8px rgba(0,0,0,.12)",
                "maxWidth": "240px",
            },
        },
    )

    selection = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", height=520)

    # ── Selected cell panel ───────────────────────────────────────────────────
    picked = []
    if selection and hasattr(selection, "selection") and selection.selection:
        picked = selection.selection.objects.get("hex-layer", [])

    if picked:
        row = picked[0]
        cell_id = row.get("h3_cell_9", "—")
        district = row.get("dominant_district", "—")
        delay    = row.get("avg_delay_minutes", 0) or 0
        gap      = row.get("total_margin_gap_usd", 0) or 0
        dels     = int(row.get("total_deliveries", 0) or 0)
        fail_pct = row.get("failure_rate_pct", 0) or 0
        status   = row.get("status", "Normal")

        st.markdown(
            f'<div style="background:#f8fafc;border:1px solid {_BORDER};border-left:4px solid '
            f'{"#ef4444" if status=="HIGH RISK" else "#10b981"};border-radius:8px;'
            f'padding:.75rem 1rem;margin-top:.5rem;">'
            f'<span style="font-size:.58rem;text-transform:uppercase;letter-spacing:.1em;'
            f'color:#64748b;font-weight:600;">Selected Zone</span>'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:.78rem;'
            f'color:#1d4ed8;font-weight:600;margin-left:.75rem;">{cell_id}</span>'
            f'<span style="float:right;font-size:.68rem;font-weight:700;'
            f'color:{"#ef4444" if status=="HIGH RISK" else "#10b981"};">{status}</span>'
            f'<br><span style="font-size:.72rem;color:#64748b;">District: {district}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        mc1, mc2, mc3, mc4 = st.columns(4)
        kpi(mc1, "Avg Delay",     f"{delay:.1f} min",  accent=_ORANGE if delay > 15 else _GREEN)
        kpi(mc2, "Margin Gap",    f"${gap:,.0f}",       accent=_RED if gap > 0 else _GREEN)
        kpi(mc3, "Deliveries",    f"{dels:,}")
        kpi(mc4, "Failure Rate",  f"{fail_pct:.1f}%",  accent=_RED if fail_pct > 10 else _GREEN)
    else:
        st.markdown(
            '<p style="font-size:.72rem;color:#94a3b8;margin-top:.4rem;">'
            'Green = on-time · Yellow = moderate · Orange/red = high delay. '
            'Click any zone to see its metrics.'
            '</p>',
            unsafe_allow_html=True,
        )


# ── Page: High-Risk Zones ─────────────────────────────────────────────────────

with tab_hs:
    st.write("")

    hs = load_hotspots(DS, ENG, PROJ)

    n_zones   = len(hs)
    total_gap = float(hs["total_margin_gap_usd"].sum())
    worst_row = hs.loc[hs["avg_delay_minutes"].idxmax()] if n_zones > 0 else None
    worst_cell = worst_row["h3_cell_9"][:12] + "…" if worst_row is not None else "—"

    c1, c2, c3 = st.columns(3)
    kpi(c1, "Hotspot Zones",       f"{n_zones}",         accent=_ORANGE)
    kpi(c2, "Combined Margin Gap", f"${total_gap:,.0f}", accent=_RED if total_gap > 0 else _GREEN)
    kpi(c3, "Worst Zone (delay)",   worst_cell,           accent=_RED)

    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)

    def _hs_delay(v):
        return "color:#ef4444;font-weight:600" if isinstance(v, (int, float)) and v > 60 else ""

    st.dataframe(
        hs.rename(columns={
            "h3_cell_9":            "H3 Cell",          "district":             "District",
            "total_deliveries":     "Deliveries",        "avg_delay_minutes":    "Avg Delay (min)",
            "total_margin_gap_usd": "Margin Gap ($)",    "failure_rate_pct":     "Failure Rate (%)",
            "dominant_traffic_zone": "Traffic Zone",     "hem_access_pct":       "% Hem Access",
        }).style
            .format({
                "Avg Delay (min)":  "{:.1f}",
                "Margin Gap ($)":   "{:,.0f}",
                "Failure Rate (%)": "{:.1f}",
                "% Hem Access":     "{:.1f}",
            })
            .map(_hs_delay, subset=["Avg Delay (min)"]),
        use_container_width=True, hide_index=True,
    )

    rec = abs(total_gap)
    worst_district = worst_row["district"] if worst_row is not None else "—"
    st.markdown(
        f'<div style="background:#fffbeb;border:1px solid #fde68a;border-left:4px solid {_ORANGE};border-radius:8px;padding:.9rem 1.1rem;margin-top:1rem;font-size:.82rem;color:#92400e;line-height:1.65;">'
        f'<span style="display:block;font-size:.58rem;text-transform:uppercase;letter-spacing:.1em;color:{_ORANGE};font-weight:600;margin-bottom:.25rem;">Pricing Recommendation</span>'
        f'Apply a <strong>$1.50–$2.50 surcharge</strong> for orders routed to the <strong>{n_zones} flagged H3 zones</strong> '
        f'(highest concentration in <strong>{worst_district}</strong>). '
        f'Estimated recovery: <strong>${rec:,.0f}</strong> in currently uncompensated delay cost.'
        f'</div>',
        unsafe_allow_html=True,
    )

