"""
Downstream consumer for the ELT pipeline.

Reads exclusively from dbt mart tables — no aggregations, no business logic,
no queries against staging or intermediate models. All numbers are pre-computed
by dbt; this app only selects, filters, and renders.

Local:  reads from db/logistics.duckdb  (mart tables built by `dbt run`)
Cloud:  same SQL works against BigQuery  (mart tables built by Dataform)
        — swap get_con() for a BigQuery client to migrate.
"""
import os
import duckdb
import streamlit as st
import pydeck as pdk

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'logistics.duckdb')

st.set_page_config(
    page_title="Delivery Analytics — HCMC",
    page_icon="🛵",
    layout="wide"
)


@st.cache_resource
def get_con():
    return duckdb.connect(DB_PATH, read_only=True)


def q(sql):
    return get_con().execute(sql).fetchdf()


# ── Mart reads (no aggregation, no business logic) ────────────────────────────

@st.cache_data
def load_kpis():
    return q("SELECT * FROM main.mart_kpis")


@st.cache_data
def load_district():
    return q("SELECT * FROM main.mart_district ORDER BY avg_delay_minutes DESC")


@st.cache_data
def load_map_points():
    return q("""
        SELECT destination_lat   AS lat,
               destination_lon   AS lon,
               delay_minutes,
               destination_district AS district,
               delivery_status
        FROM main.mart_deliveries
    """)


@st.cache_data
def load_hotspots():
    return q("""
        SELECT dominant_district  AS district,
               total_deliveries,
               avg_delay_minutes,
               total_margin_gap_usd,
               failure_rate_pct,
               dominant_traffic_zone,
               hem_access_pct
        FROM main.mart_h3
        WHERE is_hotspot = true
        ORDER BY avg_delay_minutes DESC
        LIMIT 30
    """)


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("🛵 Last-Mile Delivery Analytics")
st.caption("Ho Chi Minh City · Spatial Blindness Detection · Internal BA Dashboard")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Overview",
    "🗺️ Delay Map",
    "🏘️ District Breakdown",
    "🚨 Hotspot Zones",
])


# ── Tab 1: Overview ───────────────────────────────────────────────────────────
with tab1:
    try:
        kpi = load_kpis()
    except Exception as e:
        st.error(f"Mart tables not found. Run `dbt run` first.\n\n{e}")
        st.stop()

    st.subheader("Business Impact Summary")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Deliveries",     f"{int(kpi['total_deliveries'][0]):,}")
    c2.metric("Avg Delay",            f"{kpi['avg_delay_minutes'][0]} min")
    c3.metric("Severely Delayed",     f"{kpi['pct_severely_delayed'][0]}%",
              help="Deliveries >15 min late")
    c4.metric("Delay Cost (at-risk)", f"${int(kpi['at_risk_cost_usd'][0]):,}",
              help="Driver cost of all delays over 15 min")
    c5.metric("Margin Gap",           f"${int(kpi['total_margin_gap_usd'][0]):,}",
              help="Delay cost minus freight collected — revenue lost to spatial blindness")

    st.divider()

    st.markdown("""
    #### What is Spatial Blindness?

    Traditional routing systems calculate shipping fees using **straight-line distance**.
    But in HCMC's dense urban fabric, the *actual* cost of a delivery is determined by
    **where it goes** — not just how far.

    Narrow hẻm (alleyways), congested markets in Quận 5 and Quận 10, and complex building
    access in Gò Vấp inflate driver time far beyond what the distance estimate predicts.
    When the platform offers free shipping (orders > $100), this hidden delay becomes a
    **direct margin loss**.

    #### How this dashboard helps

    Every delivery's GPS coordinate is snapped to an **H3 hexagonal cell** (~100 m × 100 m).
    Cells where the average delay exceeds 15 minutes are flagged as **hotspots** — the
    specific zones causing margin erosion. This enables:

    - **Dynamic surcharges** — add a delivery fee for orders going to hotspot cells
    - **Route planning** — prioritise van (vs motorbike) for high-delay zones
    - **Free-shipping exclusions** — exclude hotspot districts from blanket free-shipping offers
    """)

    st.divider()
    st.subheader("Delays by District — Quick View")
    dist = load_district()
    st.bar_chart(dist.set_index("destination_district")["avg_delay_minutes"], height=300)


# ── Tab 2: Delay Map ──────────────────────────────────────────────────────────
with tab2:
    st.subheader("Delivery Delay Heatmap — HCMC")
    st.caption("Intensity = delay duration. Bright red clusters are spatially blind zones.")

    pts = load_map_points()

    layer = pdk.Layer(
        "HeatmapLayer",
        data=pts,
        get_position=["lon", "lat"],
        get_weight="delay_minutes",
        radius_pixels=35,
        intensity=1.2,
        threshold=0.05,
        color_range=[
            [0, 128, 0, 80],
            [255, 255, 0, 140],
            [255, 140, 0, 180],
            [255, 0, 0, 220],
        ],
    )

    view = pdk.ViewState(latitude=10.785, longitude=106.685, zoom=11, pitch=0)

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    ))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        n_delayed = int((pts["delay_minutes"] > 15).sum())
        st.metric("Deliveries >15 min late", f"{n_delayed:,}",
                  f"{100*n_delayed/len(pts):.1f}% of total")
    with col2:
        n_failed = int((pts["delivery_status"] == "failed").sum())
        st.metric("Failed Deliveries", f"{n_failed:,}",
                  f"{100*n_failed/len(pts):.1f}% failure rate")


# ── Tab 3: District Breakdown ─────────────────────────────────────────────────
with tab3:
    st.subheader("Performance by District")
    dist = load_district()

    st.caption(
        "Districts shaded red have avg delay >20 min — "
        "indicative of structural spatial complexity, not random traffic variation."
    )

    def highlight_delay(val):
        if isinstance(val, (int, float)) and val > 20:
            return "background-color: #ffcccc"
        return ""

    styled = dist.rename(columns={
        "destination_district": "District",
        "total_deliveries":     "Deliveries",
        "avg_delay_minutes":    "Avg Delay (min)",
        "pct_delayed":          "% Delayed >15min",
        "failure_rate_pct":     "Failure Rate (%)",
        "total_delay_cost_usd": "Delay Cost ($)",
        "margin_gap_usd":       "Margin Gap ($)",
    }).style.map(highlight_delay, subset=["Avg Delay (min)"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Avg Delay by District**")
        st.bar_chart(dist.set_index("destination_district")["avg_delay_minutes"], height=280)
    with col_b:
        st.markdown("**Margin Gap by District ($)**")
        st.bar_chart(dist.set_index("destination_district")["margin_gap_usd"], height=280)


# ── Tab 4: Hotspot Zones ──────────────────────────────────────────────────────
with tab4:
    st.subheader("Highest-Risk Delivery Zones")
    st.caption(
        "Each row is one H3 hexagonal cell (~100 m × 100 m). "
        "These are the precise drop-point clusters causing margin erosion."
    )

    hotspots = load_hotspots()

    display = hotspots.rename(columns={
        "district":             "District",
        "total_deliveries":     "Deliveries",
        "avg_delay_minutes":    "Avg Delay (min)",
        "total_margin_gap_usd": "Margin Gap ($)",
        "failure_rate_pct":     "Failure Rate (%)",
        "dominant_traffic_zone":"Traffic Zone",
        "hem_access_pct":       "% Hẻm Access",
    })

    st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()
    total_gap   = hotspots["total_margin_gap_usd"].sum()
    n_zones     = len(hotspots)
    worst_dist  = hotspots.groupby("district")["total_margin_gap_usd"].sum().idxmax()

    c1, c2, c3 = st.columns(3)
    c1.metric("Hotspot Zones Identified", f"{n_zones}")
    c2.metric("Combined Margin Gap",      f"${total_gap:,.0f}")
    c3.metric("Worst District",           worst_dist)

    st.info(
        f"**Recommended action:** Apply a $1.50–$2.50 delivery surcharge for orders "
        f"destined for the {n_zones} flagged zones, particularly in **{worst_dist}**. "
        f"This would recover an estimated **${abs(total_gap):,.0f}** in uncompensated delay cost."
    )
