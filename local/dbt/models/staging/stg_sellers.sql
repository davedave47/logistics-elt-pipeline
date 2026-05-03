with source as (
    select * from {{ source('logistics_raw', 'raw_sellers') }}
)

select
    seller_id,
    seller_name,
    district,
    warehouse_lat,
    warehouse_lon
from source
