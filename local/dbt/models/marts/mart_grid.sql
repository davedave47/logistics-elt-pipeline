-- Aggregates delivery metrics by rectangular lat/lon grid cell (0.01° × 0.01°).
-- At HCMC latitude, each cell is approximately 1.1 km × 1.1 km —
-- but unlike H3, cell area varies slightly with latitude and edges do not align
-- with natural geographic boundaries.
with base as (
    select * from {{ ref('int_delivery_metrics') }}
),

-- reconstruct lat/lon from the grid_cell_id for centroid calculation
parsed as (
    select
        *,
        split_part(grid_cell_id, '_', 1)::integer * 0.01 as cell_lat_min,
        split_part(grid_cell_id, '_', 2)::integer * 0.01 as cell_lon_min
    from base
    where grid_cell_id is not null
)

select
    grid_cell_id,
    round(cell_lat_min + 0.005, 4)                              as cell_lat_center,
    round(cell_lon_min + 0.005, 4)                              as cell_lon_center,
    count(*)                                                    as total_deliveries,
    round(avg(delay_minutes), 1)                                as avg_delay_minutes,
    round(sum(delay_cost_usd), 2)                               as total_delay_cost_usd,
    round(sum(margin_gap_usd), 2)                               as total_margin_gap_usd,
    round(avg(margin_gap_usd), 2)                               as avg_margin_gap_usd,
    round(
        100.0 * count(*) filter (where delivery_status = 'failed') / count(*), 1
    )                                                           as failure_rate_pct,
    round(
        100.0 * count(*) filter (where has_hem_access = true) / count(*), 1
    )                                                           as hem_access_pct,
    count(distinct driver_id)                                   as unique_drivers,
    avg(delay_minutes) > 15                                     as is_hotspot,
    mode() within group (order by traffic_zone)                 as dominant_traffic_zone

from parsed
group by grid_cell_id, cell_lat_min, cell_lon_min
