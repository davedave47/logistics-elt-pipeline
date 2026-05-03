-- One row per delivery stop. Flattens all nested structs from delivery_telemetry.
-- h3_cell_9 and grid_cell_id are pre-computed by the loader (Python h3 library).
with source as (
    select * from {{ source('logistics_raw', 'raw_deliveries') }}
)

select
    order_id,
    route_id,
    driver_id,
    stop_number,
    vehicle_type,

    -- spatial (nested struct)
    spatial_data.destination_lat            as destination_lat,
    spatial_data.destination_lon            as destination_lon,
    spatial_data.distance_from_prev_km      as distance_from_prev_km,

    -- pre-computed spatial indices
    h3_cell_9,
    grid_cell_id,

    -- timestamps (nested struct)
    telemetry.dispatched_at::timestamp      as dispatched_at,
    telemetry.estimated_arrival_at::timestamp as estimated_arrival_at,
    telemetry.actual_arrival_at::timestamp  as actual_arrival_at,
    telemetry.status                        as delivery_status,

    -- complexity signals (nested struct)
    complexity_factors.traffic_zone         as traffic_zone,
    complexity_factors.has_hem_access       as has_hem_access,
    complexity_factors.weather_condition    as weather_condition

from source
