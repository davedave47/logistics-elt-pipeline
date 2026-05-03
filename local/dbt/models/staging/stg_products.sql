with source as (
    select * from {{ source('logistics_raw', 'raw_products') }}
)

select
    product_id,
    product_name,
    category,
    price_usd,
    weight_g
from source
