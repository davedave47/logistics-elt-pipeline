-- Aggregates delivery metrics by H3 hexagon cell (resolution 9, ~0.1 km² uniform area).
-- Hotspot threshold: avg delay > 15 minutes flags a cell as a spatial blindness zone.
with base as (
    select * from {{ ref('int_delivery_metrics') }}
)

select
    h3_cell_9,
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
    mode() within group (order by traffic_zone)                 as dominant_traffic_zone,
    mode() within group (order by destination_district)         as dominant_district

from base
where h3_cell_9 is not null
group by h3_cell_9
