-- Side-by-side comparison of H3 vs Grid spatial indexing methods.
-- Each row is one method; metrics measure how well it surfaces spatial blindness.
--
-- Key metrics:
--   hotspot_cells         — number of cells flagged as delay hotspots
--   hotspot_capture_rate  — % of all delayed orders inside hotspot cells (recall)
--   hotspot_precision     — % of deliveries in hotspot cells that are actually delayed (precision)
--   margin_gap_in_hotspots — total USD loss concentrated in flagged cells
--   margin_gap_capture_pct — % of total margin gap that sits in hotspot cells
--   avg_delay_variance    — avg within-cell delay std dev (lower = more homogeneous grouping)

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
        round(avg(stddev_delay), 2)                         as avg_within_cell_delay_stddev
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
        round(avg(stddev_delay), 2)                         as avg_within_cell_delay_stddev
    from grid_cells
)

select * from h3_summary
union all
select * from grid_summary
