with source as (
    select * from {{ source('logistics_raw', 'raw_customers') }}
)

select
    customer_id,
    customer_name,
    phone,
    segment,
    district
from source
