# Last-Mile Delivery Analytics: Uncovering Spatial Blindness

---

## 1. The Business Problem

E-commerce platforms in Vietnam typically price shipping using **straight-line distance**: the farther the delivery, the higher the fee. This works well in open areas, but breaks down in dense urban environments like Ho Chi Minh City.

HCMC's geography has features that routing algorithms cannot see from a coordinate alone:

- **Hẻm (alleys)**: Narrow residential lanes that require a driver to dismount, navigate on foot, or take a long detour. A delivery 500 m away can take 20 minutes longer than the algorithm expects.
- **Market congestion**: Districts like Quận 5 (Chợ Lớn) and Quận 10 have dense street markets that cause unpredictable traffic.
- **Complex building access**: Some apartment blocks and industrial estates have access rules that add significant time at the door.

The platform collects a fixed shipping fee based on distance. When a delivery takes longer than estimated, the extra driver time and fuel cost is absorbed silently — it never shows up on an invoice. This is **spatial blindness**: the algorithm is blind to the street-level reality of specific drop-point zones.

**The Margin Gap** is the financial consequence. For each delivery:

```
Margin Gap = Delay Cost − Freight Collected
```

When `Margin Gap > 0`, the platform paid more to execute the delivery than it charged the customer. High-volume, high-margin products in complex zones can turn profitable orders into loss-making ones at scale.

The goal of this project is to **identify exactly which geographic zones cause the margin gap** — precisely enough that the pricing team can act on the output (e.g., add a $1.50 surcharge for orders delivered to flagged zones).

---

## 2. Why ELT, Not ETL

Traditional **ETL** (Extract → Transform → Load) transforms data before it enters the warehouse. This means you decide the schema at extraction time. If the business later asks a new question — "can we also see delays by vehicle type?" — you have to go back to the source, re-extract, and re-transform.

**ELT** (Extract → Load → Transform) loads raw data into the warehouse first, then applies transformations in-database using SQL.

### Why ELT is better for this project

| Concern | ETL | ELT (this project) |
|---|---|---|
| Schema flexibility | Fixed at extraction time | New questions = new dbt model, no re-ingestion |
| Raw data preservation | Transformed data only; originals gone | Raw JSON structs preserved in DuckDB as-is |
| Computation location | Separate transform server (expensive egress) | In-warehouse SQL — where the data already lives |
| Auditability | Hard to re-run from raw | Raw tables always available; re-run any model |

### What makes this pipeline ELT specifically

The loader (`local/load_to_duckdb.py`) does exactly one thing: read files and write them to DuckDB tables. It does **not** flatten nested objects, rename fields, or apply business rules.

```python
# The loader: preserve structure, no transformation
con.execute("""
    CREATE OR REPLACE TABLE raw_orders AS
    SELECT * FROM read_json_auto('orders.json')   -- nested JSON loaded as DuckDB STRUCT
""")
```

The `orders.json` file has nested objects (`payment`, `line_items`, `shipping_snapshot`). These are loaded as DuckDB `STRUCT` and `STRUCT[]` types and stored exactly as they arrived. The nested structure is only unpacked later, in the dbt staging layer.

The one exception: H3 cell indices are computed at load time using a Python UDF. This is a technical constraint — dbt runs pure SQL and has no access to the `h3` Python library — but the raw spatial coordinates and all other nested fields remain untouched.

---

## 3. Pipeline Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  EXTRACT / GENERATE                                            │
│  data_generator/generate_data.py                               │
│  Synthetic HCMC orders + driver telemetry (Python + Faker)     │
└───────────────────────────┬────────────────────────────────────┘
                            │  .csv  +  .json
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  DATA LAKE   data_lake/                                        │
│  raw_csv/    customers · products · sellers                    │
│  raw_json/   orders (nested) · delivery_telemetry (nested)     │
└───────────────────────────┬────────────────────────────────────┘
                            │  DuckDB read_csv_auto / read_json_auto
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  LOAD   local/load_to_duckdb.py                                │
│  Raw files → DuckDB tables, no transformation                  │
│  H3 cell index computed here via Python UDF                    │
└───────────────────────────┬────────────────────────────────────┘
                            │  SQL only, in-warehouse
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  TRANSFORM   local/dbt/                                        │
│  staging/        Unpack nested structs, cast types             │
│  intermediate/   Join tables, compute delay + cost metrics     │
│  marts/          Pre-aggregated outputs for downstream use     │
└───────────────────────────┬────────────────────────────────────┘
                            │  SELECT * FROM mart_*
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  DOWNSTREAM   local/spatial_analysis.py                        │
│  Streamlit dashboard — reads only from mart tables             │
└────────────────────────────────────────────────────────────────┘
```

The cloud variant (`cloud/`) replaces DuckDB with GCS + BigQuery and dbt with Cloud Dataform. The SQL logic inside each model is identical except for a small set of BigQuery dialect differences (see §9).

---

## 4. Raw Data Schema

### Structured dimensions → `data_lake/raw_csv/`

These are clean, flat tables loaded with `read_csv_auto`. They change rarely (product catalog, customer list) so CSV is appropriate.

| File | Columns | Role |
|---|---|---|
| `customers.csv` | `customer_id`, `customer_name`, `phone`, `segment`, `district` | Who placed the order |
| `products.csv` | `product_id`, `product_name`, `category`, `price_usd`, `weight_g` | What was ordered |
| `sellers.csv` | `seller_id`, `seller_name`, `district`, `warehouse_lat`, `warehouse_lon` | Where it shipped from |

### Semi-structured facts → `data_lake/raw_json/`

These are event documents with nested structures. JSON is appropriate because the schema varies per event and the nesting reflects how the source API sends data — flattening it before the warehouse would lose information.

**`orders.json`** — one document per order:

```json
{
  "order_id": "uuid",
  "customer_id": "uuid",
  "order_status": "delivered | shipped | processing | cancelled",
  "order_timestamp": "ISO-8601",
  "payment": {
    "method": "credit_card | cod | momo | zalopay",
    "installments": 1,
    "amount_usd": 45.50
  },
  "line_items": [
    { "product_id": "uuid", "seller_id": "uuid",
      "quantity": 2, "unit_price_usd": 15.00, "freight_value_usd": 1.50 }
  ],
  "shipping_snapshot": {
    "destination_district": "Quận 3",
    "destination_lat": 10.7801,
    "destination_lon": 106.6821,
    "address_text": "..."
  }
}
```

The `line_items` array is the critical semi-structured element — one order can contain between 1 and 5 products from different sellers. This cannot be represented in a flat CSV without either repeating the order header or splitting into two tables at source time. In ELT, we load the array as-is and let dbt unpack it.

**`delivery_telemetry.json`** — one document per delivery stop on a driver route:

```json
{
  "order_id": "uuid",
  "route_id": "RT_20240115_DRV_042",
  "driver_id": "DRV_042",
  "stop_number": 3,
  "vehicle_type": "motorbike | van",
  "spatial_data": {
    "destination_lat": 10.7801,
    "destination_lon": 106.6821,
    "distance_from_prev_km": 1.5
  },
  "telemetry": {
    "dispatched_at": "ISO-8601",
    "estimated_arrival_at": "ISO-8601",
    "actual_arrival_at": "ISO-8601",
    "status": "delivered | failed"
  },
  "complexity_factors": {
    "traffic_zone": "high | medium | low",
    "has_hem_access": true,
    "weather_condition": "clear | rainy"
  }
}
```

The `estimated_arrival_at` vs `actual_arrival_at` gap is the source of every delay metric in the pipeline.

---

## 5. dbt: Core Concepts Used in This Project

### What dbt does

dbt (Data Build Tool) turns SQL `SELECT` statements into warehouse objects (views or tables). You write the query; dbt handles the `CREATE OR REPLACE VIEW` boilerplate, builds the dependency graph, and runs models in the correct order.

### Sources

Sources are declarations that tell dbt about tables that were loaded by an external process (the loader). They are defined in `local/dbt/models/staging/sources.yml`:

```yaml
sources:
  - name: logistics_raw
    schema: main
    tables:
      - name: raw_orders
      - name: raw_deliveries
      # ...
```

In a model, you reference a source with `{{ source('logistics_raw', 'raw_orders') }}`. This creates an auditable link between the model and its upstream data, and allows dbt to detect if the source table is missing.

### Models and the `{{ ref() }}` function

Every SQL file in `models/` is a dbt model. Instead of hardcoding table names, models reference each other with `{{ ref('model_name') }}`:

```sql
-- int_delivery_metrics.sql
with deliveries as (
    select * from {{ ref('stg_deliveries') }}   -- depends on stg_deliveries
),
orders as (
    select * from {{ ref('stg_orders') }}        -- depends on stg_orders
)
```

dbt reads all `ref()` calls across every model and builds a **DAG** (Directed Acyclic Graph) — a dependency tree that determines the execution order. You never have to specify "run A before B"; dbt infers it. If `stg_deliveries` fails, `int_delivery_metrics` and all its dependents are automatically skipped.

### Materialization: view vs table

Each model can be materialized as either a **view** or a **table**, configured in `dbt_project.yml`:

```yaml
models:
  Logistics:
    staging:      { +materialized: view  }   # query aliases — no storage cost
    intermediate: { +materialized: view  }   # query aliases — rebuilt on every read
    marts:        { +materialized: table }   # pre-computed — fast reads for dashboards
```

**Views** (staging, intermediate): no data is stored. Every time you query `stg_orders`, DuckDB runs the SQL and reads from `raw_orders` on the fly. This is fine for intermediate steps where the data is only read by other dbt models, not by end users.

**Tables** (marts): the query result is computed once and stored. When the Streamlit dashboard does `SELECT * FROM mart_kpis`, it reads pre-computed rows in microseconds — it does not re-scan `raw_orders` or re-run the delay calculation.

### CTE pattern

Every model in this project uses a `WITH` clause (Common Table Expression) to name intermediate steps. This is a dbt convention that makes SQL readable and testable:

```sql
with base as (
    select * from {{ ref('int_delivery_metrics') }}   -- name the input
)
select
    h3_cell_9,
    avg(delay_minutes) as avg_delay_minutes           -- aggregate
from base
group by h3_cell_9
```

---

## 6. dbt Model Layers

The full DAG, showing how data flows from raw sources to mart tables:

```
raw_customers  → stg_customers  ─────────────────────────────────┐
raw_products   → stg_products   ─────────────────────────────────┤ (available for joins)
raw_sellers    → stg_sellers    ─────────────────────────────────┘

raw_orders     → stg_orders     ──────────────────────┐
               → stg_order_items (unnested line_items) │
                                                       ├──▶ int_delivery_metrics
raw_deliveries → stg_deliveries ──────────────────────┘
                                                              │
                                          ┌───────────────────┼───────────────────────┐
                                          ▼                   ▼                       ▼
                                     mart_kpis          mart_district          mart_deliveries
                                     mart_h3            mart_grid
                                                   mart_spatial_comparison
```

### Staging layer (`staging/`)

**Purpose**: one model per raw source. Each model does exactly three things: rename fields to a consistent convention, cast types (e.g., string timestamps to `TIMESTAMP`), and unpack nested struct fields using dot-notation access.

```sql
-- stg_orders.sql: unpacking nested structs
payment.method          as payment_method,
shipping_snapshot.destination_lat as destination_lat,
len(line_items)         as item_count,
(select sum(item.freight_value_usd) from unnest(line_items) t(item)) as total_freight_usd
```

Staging models are views. They add no computational cost — they are simply clean lenses over the raw tables.

**`stg_orders`** — one row per order. The `line_items` array is aggregated here into order-level totals (`subtotal_usd`, `total_freight_usd`).

**`stg_order_items`** — one row per line item. The `UNNEST(line_items)` call expands each order into multiple rows, one per product. This enables product-level analysis without touching the raw JSON.

**`stg_deliveries`** — one row per delivery stop. The nested `spatial_data`, `telemetry`, and `complexity_factors` structs are all flattened into columns. The pre-computed `h3_cell_9` and `grid_cell_id` columns (added by the loader) pass through unchanged.

### Intermediate layer (`intermediate/`)

**Purpose**: joins and metric derivation. This is where the core business logic lives.

**`int_delivery_metrics`** joins `stg_deliveries` and `stg_orders` on `order_id`, then computes three new columns that do not exist in any raw source:

```sql
-- Delay: actual minus estimated, in minutes
datediff('minute', estimated_arrival_at, actual_arrival_at) as delay_minutes,

-- Delay cost: driver time wasted, priced by vehicle type
case vehicle_type
    when 'van' then delay_minutes / 60.0 * 5.0   -- van driver: ~$5/hr
    else            delay_minutes / 60.0 * 3.0   -- motorbike: ~$3/hr
end as delay_cost_usd,

-- Margin gap: was the delay covered by freight collected?
delay_cost_usd - coalesce(total_freight_usd, 0) as margin_gap_usd
```

This is a view. No downstream model or the dashboard ever queries a staging model directly — they always go through `int_delivery_metrics`.

### Mart layer (`marts/`)

**Purpose**: pre-aggregated outputs. Marts are materialized as tables and are the **only layer the dashboard reads from**. All aggregation and business logic is complete before the dashboard touches the data.

| Model | Rows | What it pre-computes |
|---|---|---|
| `mart_kpis` | 1 | Fleet-wide summary: total deliveries, avg delay, total at-risk cost, margin gap |
| `mart_district` | 11 (one per district) | Delay and failure metrics grouped by HCMC district |
| `mart_deliveries` | 3,000 (one per delivery) | Individual delivery records for map rendering — the mart version of `int_delivery_metrics` |
| `mart_h3` | 373 (one per H3 cell) | Delay, cost, failure rate, and hotspot flag per hexagon |
| `mart_grid` | 72 (one per grid cell) | Same metrics grouped by rectangular lat/lon cell |
| `mart_spatial_comparison` | 2 (one per method) | H3 vs Grid side-by-side comparison metrics |

---

## 7. Metrics Dictionary

Every metric in the pipeline, with its formula and business interpretation.

### Delivery-level metrics (computed in `int_delivery_metrics`)

**`delay_minutes`**
- Formula: `actual_arrival_at − estimated_arrival_at` in minutes
- What it means: How many minutes late was this specific delivery stop versus the routing algorithm's estimate? Positive = late; near-zero = on time; negative = arrived early.
- Why it matters: The routing algorithm's estimate is what the platform *sold* to the customer. Any positive deviation is a cost that wasn't priced in.

**`delay_cost_usd`**
- Formula: `delay_minutes / 60 × driver_rate` where motorbike = $3/hr, van = $5/hr
- What it means: The monetary value of the driver's wasted time on this delivery stop.
- Why it matters: Driver cost is the platform's primary variable cost. A 30-minute delay on a motorbike costs the platform $1.50 that was never recovered.

**`margin_gap_usd`**
- Formula: `delay_cost_usd − total_freight_usd`
- What it means: The uncompensated portion of the delay. Positive = the delay cost exceeded the freight collected (net loss on this delivery). Negative = freight more than covered the delay cost (profitable despite delay).
- Important nuance: Most individual deliveries have a negative margin gap because freight values often exceed small delays. The business problem emerges at the **zone level** — certain H3 cells have consistently positive average margin gaps, meaning *every delivery to that zone* loses money on average.

**`delivery_status`**
- Values: `delivered`, `failed`
- A `failed` delivery absorbs 100% of the driver's time and cost with zero revenue. In complex zones, the failure rate is elevated because drivers cannot locate the address or access the building.

### Zone-level metrics (computed in `mart_h3` and `mart_grid`)

**`avg_delay_minutes`**
- Average `delay_minutes` across all deliveries in the spatial cell.
- What it means: The systematic delay penalty for this zone. A cell with `avg_delay_minutes = 45` means every delivery to it takes 45 minutes longer than the algorithm predicts, regardless of driver or time of day. That is a structural feature of the zone, not random noise.

**`is_hotspot`**
- Formula: `avg_delay_minutes > 15`
- What it means: A binary flag identifying cells with structurally above-average delays. The 15-minute threshold is the minimum delay that materially changes driver economics (15 min × $3/hr = $0.75 extra cost per stop, which compounds across a 15-stop route).
- This is the primary output the pricing team acts on: flagged zones get a delivery surcharge.

**`total_margin_gap_usd`**
- Sum of `margin_gap_usd` across all deliveries in the cell.
- What it means: The total financial exposure from this zone. A hotspot cell with `total_margin_gap_usd = $30` means all deliveries to that hex have collectively cost the platform $30 more than was collected in freight. At scale, this directly compresses gross margin.

**`failure_rate_pct`**
- Formula: `failed deliveries / total deliveries × 100`
- What it means: The proportion of deliveries in this zone that could not be completed. High failure rate is both a direct cost (driver time wasted) and a customer experience problem.

**`hem_access_pct`**
- Formula: `deliveries with has_hem_access = true / total × 100`
- What it means: The share of deliveries in this cell that required navigating a hẻm (alley). This is a proxy for structural complexity. High `hem_access_pct` correlated with high `avg_delay_minutes` validates that hẻm access is a driver of spatial blindness in that zone.

**`dominant_district`**
- The most common district among deliveries in this H3 cell (statistical mode).
- Why needed: An H3 cell at resolution 9 is ~100m × 100m, which can straddle a district boundary. This field gives the dashboard a human-readable label for the zone without requiring a spatial join.

**`unique_drivers`**
- Count of distinct drivers who delivered to this cell.
- What it means: Low `unique_drivers` in a high-delay cell suggests the zone is served by a small pool of drivers who may have local knowledge. Expanding the driver pool for that zone could introduce unfamiliar drivers who suffer even longer delays.

### Comparison metrics (computed in `mart_spatial_comparison`)

These metrics answer the question: *which spatial index method — H3 hexagons or a rectangular lat/lon grid — more accurately identifies the zones causing margin loss?*

**`total_cells`**
- The number of distinct spatial cells each method produces from the same set of deliveries.
- H3 (res=9) produces ~373 cells; the 0.01° grid produces ~72 cells. H3 is more granular because its cells are ~11× smaller in area.

**`hotspot_cells`**
- Number of cells flagged as hotspots (`avg_delay > 15 min`) by each method.

**`hotspot_capture_rate_pct`** *(Recall)*
- Formula: `delayed orders in hotspot cells / all delayed orders × 100`
- What it means: Of all the deliveries that actually experienced significant delay, what percentage are sitting inside a cell that got flagged? High recall = the method finds where the problems are.

**`hotspot_precision_pct`** *(Precision)*
- Formula: `delayed orders in hotspot cells / all orders in hotspot cells × 100`
- What it means: When a cell is flagged as a hotspot, how often is a delivery there actually delayed? Low precision = over-flagging (flagging normal zones). High precision = the flag is reliable.

**`margin_gap_capture_pct`**
- Formula: `total margin gap in hotspot cells / total margin gap across all deliveries × 100`
- What it means: What proportion of the total financial loss is concentrated in the flagged zones? High capture = flagging these zones is financially meaningful.

**`avg_within_cell_delay_stddev`**
- Formula: Average of the standard deviation of `delay_minutes` within each cell.
- What it means: How homogeneous is each cell? Low stddev means deliveries to the same cell experience similar delays — the cell is a coherent unit. High stddev means the cell contains a mix of easy and hard deliveries, which reduces its usefulness as an actionable zone.
- H3 is expected to have lower stddev because its uniform area better matches the physical scale at which spatial complexity actually operates (a single hẻm is ~100m, the same order of magnitude as an H3 res-9 cell).

---

## 8. H3 Hexagons vs Lat/Lon Grid

The core comparison of this project is whether H3 hexagonal indexing or a rectangular lat/lon grid better surfaces spatial blindness.

### The Lat/Lon Grid

The simplest spatial index: divide the map into rectangles by rounding coordinates to the nearest 0.01°. In this project, `grid_cell_id` is computed as:

```sql
CONCAT(FLOOR(lat / 0.01), '_', FLOOR(lon / 0.01))
```

At HCMC's latitude, 0.01° ≈ 1.1 km in both directions, giving cells of roughly 1.1 km × 1.1 km.

**Grid limitations for this use case:**

1. **Cell area is too large**: A 1.1 km² cell covers an entire neighbourhood. A single spatially blind hẻm (perhaps 200m long) is diluted across hundreds of routine deliveries from the rest of the cell, pushing the average delay down and preventing the cell from being flagged.

2. **Edge-straddling**: Grid edges are fixed horizontal and vertical lines. A problematic alley that runs diagonally may split across two or four cells, with each cell receiving only a fraction of the delay signal. Neither cell gets flagged; the problem is invisible.

3. **Variable area**: At higher latitudes, the east-west dimension of a degree of longitude shrinks. This means grid cells are not the same size everywhere — the index distorts comparisons between zones.

### H3 Hexagons

H3 is Uber's open-source hierarchical spatial indexing system. Each GPS coordinate is mapped to a hexagonal cell at a chosen resolution. At **resolution 9**, each cell covers approximately **0.1 km²** (~105m per side).

```python
# Computed in the loader using the h3 Python library
h3.latlng_to_cell(lat, lon, resolution=9)
# Returns a string like "8965b564347ffff"
```

**H3 advantages for this use case:**

1. **Uniform area**: Every resolution-9 cell on Earth covers the same area. Comparing delay intensity between two cells is a fair comparison — they represent the same amount of geographic space.

2. **Scale matching**: A spatially blind hẻm is typically 50–200m long. An H3 res-9 cell is ~105m across — the same order of magnitude. One problematic alley tends to fall mostly within a single cell, concentrating its delay signal rather than diluting it.

3. **Fewer edge artifacts**: A hexagon has 6 equidistant neighbours (vs 4 for a square). A diagonal alley shares its boundary with a maximum of 2 H3 cells instead of up to 4 grid squares. This reduces signal dilution.

4. **Hierarchy**: H3 cells at resolution 9 can be aggregated to resolution 8 (0.7 km²) or resolution 7 (5 km²) without re-computing — useful for rolling up from operational (street-level) to strategic (district-level) decisions.

### What the data shows

`mart_spatial_comparison` produces a two-row table comparing both methods on the same deliveries:

| Metric | H3 | Grid | Better |
|---|---|---|---|
| Cell area | ~0.1 km² (uniform) | ~1.1 km² (variable) | H3 (finer, more precise) |
| Total cells | ~373 | ~72 | — |
| `hotspot_precision_pct` | Higher | Lower | H3 (fewer false flags) |
| `avg_within_cell_delay_stddev` | Lower | Higher | H3 (more homogeneous cells) |

The key business implication: H3 identifies smaller, more actionable zones. Instead of flagging an entire neighbourhood, it can flag a specific cluster of streets. A surcharge rule targeting an H3 cell applies to orders within ~100m, not orders within ~1.1 km — dramatically reducing the risk of over-charging customers in the normal parts of the neighbourhood.

---

## 9. Spatial Blindness Simulation

Since real HCMC delivery data is not available, the generator (`data_generator/generate_data.py`) creates synthetic data with a known ground truth.

**Complex districts** (hard-coded with `complex=True`):

| District | GPS center | Rationale |
|---|---|---|
| Quận 3 | 10.7801, 106.6821 | Dense residential alleys near city centre |
| Quận 5 | 10.7553, 106.6639 | Chợ Lớn market district, chronic congestion |
| Quận 10 | 10.7733, 106.6668 | Mixed market and residential, narrow streets |
| Gò Vấp | 10.8388, 106.6654 | High-density suburb with narrow lane network |

**Delay injection logic:**

```python
if order['is_complex'] and random.random() > 0.35:
    # 65% chance of a significant delay in complex districts
    delay_min = random.randint(15, 60)      # 15–60 minute delay
    traffic_zone = 'high'
    has_hem = True
    status = 'delivered' if random.random() > 0.12 else 'failed'  # 12% failure rate
else:
    # Normal delivery: small random variance only
    act_time += timedelta(minutes=base_mins + random.randint(-2, 8))
    traffic_zone = random.choice(['low', 'medium'])
```

This means the H3 and grid cells covering Quận 3, Quận 5, Quận 10, and Gò Vấp should consistently emerge as hotspots. The spatial comparison analysis (`mart_spatial_comparison`) measures how well each index method recovers this ground truth.

---

## 10. Downstream Consumer

The Streamlit dashboard (`local/spatial_analysis.py`) is a **pure mart consumer**. It contains no aggregations, no business logic, and no SQL more complex than `SELECT` and `WHERE`. All computation was done upstream in dbt.

```python
# Every data function in the app looks like this:
def load_kpis():
    return q("SELECT * FROM main.mart_kpis")          # 1 pre-computed row

def load_district():
    return q("SELECT * FROM main.mart_district ORDER BY avg_delay_minutes DESC")

def load_hotspots():
    return q("""
        SELECT dominant_district, total_deliveries, avg_delay_minutes,
               total_margin_gap_usd, failure_rate_pct, dominant_traffic_zone
        FROM main.mart_h3
        WHERE is_hotspot = true
        ORDER BY avg_delay_minutes DESC
        LIMIT 30
    """)
```

This separation is intentional. If the hotspot threshold changes from 15 minutes to 20 minutes, you change one line in `mart_h3.sql`, re-run `dbt run`, and the dashboard reflects the update automatically — without touching any Python code.

---

## 11. Cloud Scale-Out

The local pipeline (DuckDB + dbt) is architecturally identical to the cloud pipeline (GCS + BigQuery + Dataform). Swapping between them requires no changes to business logic.

| Component | Local | Cloud |
|---|---|---|
| Data Lake | `data_lake/` folder | GCS bucket |
| Load | `local/load_to_duckdb.py` | `cloud/upload_to_gcs.py` → `cloud/load_to_bigquery.py` |
| Transform | `local/dbt/` (dbt-duckdb) | `cloud/dataform/` (Cloud Dataform) |
| Warehouse | `db/logistics.duckdb` | BigQuery dataset |
| Dashboard | Reads from DuckDB | Reads from BigQuery (swap `get_con()`) |

**Cloud SQL differences** (documented in each `.sqlx` file):

| DuckDB | BigQuery | Why different |
|---|---|---|
| `datediff('minute', a, b)` | `TIMESTAMP_DIFF(b, a, MINUTE)` | Dialect |
| `COUNT(*) FILTER (WHERE x)` | `COUNTIF(x)` | BQ doesn't support FILTER clause |
| `SUM(x) FILTER (WHERE y)` | `SUM(IF(y, x, 0))` | Same reason |
| `MODE() WITHIN GROUP (ORDER BY x)` | `APPROX_TOP_COUNT(x, 1)[OFFSET(0)].value` | BQ has no MODE aggregate |
| `x / y` (zero division = NULL) | `SAFE_DIVIDE(x, y)` | BQ returns error on divide-by-zero |

The H3 Python UDF used in `load_to_duckdb.py` becomes a Python function in `upload_to_gcs.py` that enriches each JSON record before upload — BigQuery has no native H3 SQL function, so the index is computed at ingestion time rather than at load time.

---

## 12. Setup & Execution

```bash
# Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# One-time dbt profile setup
cp local/profiles_template.yml ~/.dbt/profiles.yml
# Edit the path inside to point to your absolute path of db/logistics.duckdb

# Phase 1 — generate the data lake
cd data_generator && python generate_data.py

# Phase 2 — load into DuckDB
cd ../local && python load_to_duckdb.py

# Phase 3 — run all dbt models
cd dbt && dbt run

# Run a single model and its upstream dependencies
dbt run --select +mart_h3

# Phase 4 — launch dashboard
cd .. && streamlit run spatial_analysis.py
```
