{{ config(materialized='table') }}

select
    count(*)                                                                    as total_deliveries,
    round(avg(delay_minutes), 1)                                                as avg_delay_minutes,
    round(100.0 * count(*) filter (where delay_minutes > 15) / count(*), 1)    as pct_severely_delayed,
    round(sum(case when delay_minutes > 15 then delay_cost_usd else 0 end), 0) as at_risk_cost_usd,
    round(sum(case when delay_minutes > 15 then margin_gap_usd else 0 end), 0) as total_margin_gap_usd,
    count(distinct h3_cell_9)                                                   as unique_h3_cells,
    count(distinct grid_cell_id)                                                as unique_grid_cells

from {{ ref('int_delivery_metrics') }}
