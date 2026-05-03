-- One row per order. Flattens the nested payment and shipping_snapshot structs.
-- line_items array is aggregated here; see stg_order_items for the unnested version.
with source as (
    select * from {{ source('logistics_raw', 'raw_orders') }}
)

select
    order_id,
    customer_id,
    order_status,
    order_timestamp::timestamp                          as order_timestamp,

    -- payment (nested struct)
    payment.method                                      as payment_method,
    payment.installments                                as payment_installments,
    payment.amount_usd                                  as payment_amount_usd,

    -- shipping destination (nested struct)
    shipping_snapshot.destination_district              as destination_district,
    shipping_snapshot.destination_lat                   as destination_lat,
    shipping_snapshot.destination_lon                   as destination_lon,
    shipping_snapshot.address_text                      as address_text,

    -- line_items array → aggregated order-level financials
    len(line_items)                                     as item_count,
    (
        select sum(item.quantity * item.unit_price_usd)
        from unnest(line_items) t(item)
    )                                                   as subtotal_usd,
    (
        select sum(item.freight_value_usd)
        from unnest(line_items) t(item)
    )                                                   as total_freight_usd

from source
