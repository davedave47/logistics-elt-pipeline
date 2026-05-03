-- One row per line item (unnested from orders.line_items array).
-- Join to stg_products for enrichment in downstream models.
with source as (
    select * from {{ source('logistics_raw', 'raw_orders') }}
)

select
    o.order_id,
    o.order_timestamp::timestamp    as order_timestamp,
    item.product_id,
    item.seller_id,
    item.quantity,
    item.unit_price_usd,
    item.freight_value_usd,
    item.quantity * item.unit_price_usd as line_total_usd
from source o,
unnest(o.line_items) t(item)
