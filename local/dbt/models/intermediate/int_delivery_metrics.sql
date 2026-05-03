-- Core business metric model. One row per delivery, with delay and margin calculations.
-- margin_gap_usd > 0 means the delivery cost us more than we collected in freight.
with deliveries as (
    select * from {{ ref('stg_deliveries') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
)

select
    d.order_id,
    d.route_id,
    d.driver_id,
    d.vehicle_type,
    d.stop_number,
    d.destination_lat,
    d.destination_lon,
    d.h3_cell_9,
    d.grid_cell_id,
    d.delivery_status,
    d.traffic_zone,
    d.has_hem_access,
    d.distance_from_prev_km,
    o.destination_district,
    o.total_freight_usd,
    o.payment_method,

    -- delay signal
    datediff('minute', d.estimated_arrival_at, d.actual_arrival_at) as delay_minutes,

    -- cost of delay: HCMC motorbike driver ~$3/hr, van ~$5/hr
    case d.vehicle_type
        when 'van'       then datediff('minute', d.estimated_arrival_at, d.actual_arrival_at) / 60.0 * 5.0
        else                  datediff('minute', d.estimated_arrival_at, d.actual_arrival_at) / 60.0 * 3.0
    end as delay_cost_usd,

    -- margin gap: positive = revenue lost to uncompensated delays
    case d.vehicle_type
        when 'van'       then datediff('minute', d.estimated_arrival_at, d.actual_arrival_at) / 60.0 * 5.0
        else                  datediff('minute', d.estimated_arrival_at, d.actual_arrival_at) / 60.0 * 3.0
    end - coalesce(o.total_freight_usd, 0)  as margin_gap_usd,

    d.estimated_arrival_at,
    d.actual_arrival_at

from deliveries d
left join orders o on d.order_id = o.order_id
