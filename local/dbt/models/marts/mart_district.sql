{{ config(materialized='table') }}

select
    destination_district,
    count(*)                                                                        as total_deliveries,
    round(avg(delay_minutes), 1)                                                    as avg_delay_minutes,
    round(100.0 * count(*) filter (where delay_minutes > 15) / count(*), 1)        as pct_delayed,
    round(100.0 * count(*) filter (where delivery_status = 'failed') / count(*), 1) as failure_rate_pct,
    round(sum(delay_cost_usd), 2)                                                   as total_delay_cost_usd,
    round(sum(case when delay_minutes > 15 then margin_gap_usd else 0 end), 0)     as margin_gap_usd

from {{ ref('int_delivery_metrics') }}
where destination_district is not null
group by destination_district
