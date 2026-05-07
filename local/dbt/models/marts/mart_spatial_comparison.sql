-- Side-by-side comparison of H3 vs Grid spatial indexing methods.
-- Each row is one method; metrics measure how well each surfaces spatial blindness.
--
-- Business metrics:
--   hotspot_capture_rate_pct  — recall: % of all delayed orders inside hotspot cells
--   hotspot_precision_pct     — precision: % of deliveries in hotspot cells that are delayed
--   margin_gap_in_hotspots    — total USD loss concentrated in flagged cells
--   margin_gap_capture_pct    — % of total margin gap captured by hotspot cells
--   avg_within_cell_delay_stddev — within-cell delay homogeneity (lower = tighter grouping)
--
-- Formal spatial metrics:
--   mdqe_km  — Mean Distance Quantization Error: avg Haversine distance (km) from
--              each delivery GPS to its assigned cell centroid. Lower = less
--              information loss from snapping a continuous coordinate to a discrete cell.
--   sdc_km   — Spatial Distortion Coefficient: σ of center-to-neighbor distances.
--              H3 = 0.000 (equidistant by construction); Grid ≈ 0.228 km at HCMC
--              because orthogonal neighbors are ~1.11 km while diagonals are ~1.56 km.
--              Lower = more uniform coverage, unbiased proximity queries.
--   cl_us_per_row — Computational Latency: µs per row measured at load time
--              (Python UDF for H3 vs pure-SQL FLOOR for Grid). Stored in raw_cl_benchmarks.

with base as (
    select * from {{ ref('int_delivery_metrics') }}
),

totals as (
    select
        count(*)                                            as total_deliveries,
        count(*) filter (where delay_minutes > 15)          as total_delayed,
        sum(margin_gap_usd)                                 as total_margin_gap
    from base
),

-- ── MDQE: approximate cell centroids ─────────────────────────────────────────

-- H3 centroid: avg lat/lon of all deliveries in the cell (proxy for true geometric
-- centroid — accurate for dense distributions, avoids requiring the H3 C library)
h3_centroids as (
    select
        h3_cell_9,
        avg(destination_lat)                                as centroid_lat,
        avg(destination_lon)                                as centroid_lon
    from base
    where h3_cell_9 is not null
    group by h3_cell_9
),

-- Grid centroid: exact midpoint — cell spans [floor*0.01, (floor+1)*0.01]
grid_centroids as (
    select distinct
        grid_cell_id,
        floor(destination_lat / 0.01) * 0.01 + 0.005       as centroid_lat,
        floor(destination_lon / 0.01) * 0.01 + 0.005       as centroid_lon
    from base
    where grid_cell_id is not null
),

-- Per-delivery Haversine distance to H3 cell centroid
h3_distances as (
    select
        {{ haversine_km('b.destination_lat', 'b.destination_lon',
                        'c.centroid_lat',   'c.centroid_lon') }}
                                                            as dist_km
    from base b
    join h3_centroids c using (h3_cell_9)
),

-- Per-delivery Haversine distance to grid cell centroid
grid_distances as (
    select
        {{ haversine_km('b.destination_lat', 'b.destination_lon',
                        'c.centroid_lat',   'c.centroid_lon') }}
                                                            as dist_km
    from base b
    join grid_centroids c using (grid_cell_id)
),

-- ── Cell-level aggregates ────────────────────────────────────────────────────

h3_cells as (
    select
        h3_cell_9                                           as cell_id,
        count(*)                                            as deliveries,
        avg(delay_minutes)                                  as avg_delay,
        stddev(delay_minutes)                               as stddev_delay,
        sum(margin_gap_usd)                                 as cell_margin_gap,
        count(*) filter (where delay_minutes > 15)          as delayed_count,
        avg(delay_minutes) > 15                             as is_hotspot
    from base
    where h3_cell_9 is not null
    group by h3_cell_9
),

grid_cells as (
    select
        grid_cell_id                                        as cell_id,
        count(*)                                            as deliveries,
        avg(delay_minutes)                                  as avg_delay,
        stddev(delay_minutes)                               as stddev_delay,
        sum(margin_gap_usd)                                 as cell_margin_gap,
        count(*) filter (where delay_minutes > 15)          as delayed_count,
        avg(delay_minutes) > 15                             as is_hotspot
    from base
    where grid_cell_id is not null
    group by grid_cell_id
),

-- ── CL: benchmarks written by loader at ingest time ─────────────────────────

cl as (
    select method, microseconds_per_row
    from {{ source('logistics_raw', 'raw_cl_benchmarks') }}
),

-- ── Final summaries ──────────────────────────────────────────────────────────

h3_summary as (
    select
        'H3 (res=9, ~0.1 km²)'                             as method,
        count(*)                                            as total_cells,
        count(*) filter (where is_hotspot)                  as hotspot_cells,
        round(100.0 * sum(delayed_count) filter (where is_hotspot)
              / nullif((select total_delayed from totals), 0), 1)
                                                            as hotspot_capture_rate_pct,
        round(100.0 * sum(delayed_count) filter (where is_hotspot)
              / nullif(sum(deliveries) filter (where is_hotspot), 0), 1)
                                                            as hotspot_precision_pct,
        round(sum(cell_margin_gap) filter (where is_hotspot), 2)
                                                            as margin_gap_in_hotspots_usd,
        round(100.0 * sum(cell_margin_gap) filter (where is_hotspot)
              / nullif((select total_margin_gap from totals), 0), 1)
                                                            as margin_gap_capture_pct,
        round(avg(stddev_delay), 2)                         as avg_within_cell_delay_stddev,
        round((select avg(dist_km) from h3_distances), 4)  as mdqe_km,
        0.000                                               as sdc_km,
        round((select microseconds_per_row from cl where method = 'H3'), 4)
                                                            as cl_us_per_row
    from h3_cells
),

grid_summary as (
    select
        'Grid (0.01°, ~1.1 km²)'                           as method,
        count(*)                                            as total_cells,
        count(*) filter (where is_hotspot)                  as hotspot_cells,
        round(100.0 * sum(delayed_count) filter (where is_hotspot)
              / nullif((select total_delayed from totals), 0), 1)
                                                            as hotspot_capture_rate_pct,
        round(100.0 * sum(delayed_count) filter (where is_hotspot)
              / nullif(sum(deliveries) filter (where is_hotspot), 0), 1)
                                                            as hotspot_precision_pct,
        round(sum(cell_margin_gap) filter (where is_hotspot), 2)
                                                            as margin_gap_in_hotspots_usd,
        round(100.0 * sum(cell_margin_gap) filter (where is_hotspot)
              / nullif((select total_margin_gap from totals), 0), 1)
                                                            as margin_gap_capture_pct,
        round(avg(stddev_delay), 2)                         as avg_within_cell_delay_stddev,
        round((select avg(dist_km) from grid_distances), 4) as mdqe_km,
        0.228                                               as sdc_km,
        round((select microseconds_per_row from cl where method = 'Grid'), 4)
                                                            as cl_us_per_row
    from grid_cells
)

select * from h3_summary
union all
select * from grid_summary
