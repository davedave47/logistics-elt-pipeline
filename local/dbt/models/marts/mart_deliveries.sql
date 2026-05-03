-- Individual-record mart for map visualisation and point-level analysis.
-- Downstream consumers (dashboards, notebooks) read from here instead of
-- querying int_delivery_metrics directly.
{{ config(materialized='table') }}

select
    order_id,
    destination_lat,
    destination_lon,
    destination_district,
    h3_cell_9,
    grid_cell_id,
    delay_minutes,
    delay_cost_usd,
    margin_gap_usd,
    delivery_status,
    vehicle_type,
    traffic_zone,
    has_hem_access,
    distance_from_prev_km

from {{ ref('int_delivery_metrics') }}
