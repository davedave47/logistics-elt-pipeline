import os
import time
import duckdb
import h3

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'logistics.duckdb')
LAKE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data_lake')
CSV_DIR = os.path.join(LAKE_DIR, 'raw_csv')
JSON_DIR = os.path.join(LAKE_DIR, 'raw_json')

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

con = duckdb.connect(DB_PATH)

# Python UDF so H3 computation stays in Python and doesn't require the
# DuckDB community extension, which may not be available in all environments.
con.create_function(
    'py_h3_cell',
    lambda lat, lon, res: h3.latlng_to_cell(lat, lon, res),
    [float, float, int],
    str
)

print("Loading structured dimensions (CSV → DuckDB)...")
con.execute(f"""
    CREATE OR REPLACE TABLE raw_customers AS
    SELECT * FROM read_csv_auto('{CSV_DIR}/customers.csv', header=true)
""")
con.execute(f"""
    CREATE OR REPLACE TABLE raw_products AS
    SELECT * FROM read_csv_auto('{CSV_DIR}/products.csv', header=true)
""")
con.execute(f"""
    CREATE OR REPLACE TABLE raw_sellers AS
    SELECT * FROM read_csv_auto('{CSV_DIR}/sellers.csv', header=true)
""")

print("Loading semi-structured orders (JSON → DuckDB STRUCT)...")
con.execute(f"""
    CREATE OR REPLACE TABLE raw_orders AS
    SELECT * FROM read_json_auto('{JSON_DIR}/orders.json')
""")

# Load raw delivery telemetry without spatial indices first so we can
# benchmark H3 and Grid independently on the same dataset.
print("Loading delivery telemetry...")
con.execute(f"""
    CREATE OR REPLACE TABLE _raw_del_base AS
    SELECT * FROM read_json_auto('{JSON_DIR}/delivery_telemetry.json')
""")
n_rows = con.execute("SELECT COUNT(*) FROM _raw_del_base").fetchone()[0]

# CL benchmark — H3 via Python UDF (cross-language call per row)
print("Benchmarking spatial index computation...")
t0 = time.perf_counter()
con.execute("""
    SELECT py_h3_cell(
        spatial_data.destination_lat,
        spatial_data.destination_lon,
        9
    ) FROM _raw_del_base
""")
h3_elapsed = time.perf_counter() - t0

# CL benchmark — Grid via pure-SQL FLOOR (in-engine integer arithmetic)
t0 = time.perf_counter()
con.execute("""
    SELECT CONCAT(
        CAST(FLOOR(spatial_data.destination_lat / 0.01) AS INTEGER), '_',
        CAST(FLOOR(spatial_data.destination_lon / 0.01) AS INTEGER)
    ) FROM _raw_del_base
""")
grid_elapsed = time.perf_counter() - t0

h3_us   = h3_elapsed   / n_rows * 1e6
grid_us = grid_elapsed / n_rows * 1e6
print(f"  H3   CL: {h3_us:.2f} µs/row  ({n_rows:,} rows, {h3_elapsed:.3f}s total)")
print(f"  Grid CL: {grid_us:.4f} µs/row ({n_rows:,} rows, {grid_elapsed:.4f}s total)")

con.execute("""
    CREATE OR REPLACE TABLE raw_cl_benchmarks (
        method               VARCHAR,
        n_rows               INTEGER,
        total_seconds        DOUBLE,
        microseconds_per_row DOUBLE
    )
""")
con.execute(f"""
    INSERT INTO raw_cl_benchmarks VALUES
    ('H3',   {n_rows}, {h3_elapsed:.6f},   {h3_us:.4f}),
    ('Grid', {n_rows}, {grid_elapsed:.6f}, {grid_us:.6f})
""")

# Build final raw_deliveries with both spatial indices
print("Computing spatial indices (H3 + grid)...")
con.execute("""
    CREATE OR REPLACE TABLE raw_deliveries AS
    SELECT
        *,
        py_h3_cell(
            spatial_data.destination_lat,
            spatial_data.destination_lon,
            9
        ) AS h3_cell_9,
        CONCAT(
            CAST(FLOOR(spatial_data.destination_lat / 0.01) AS INTEGER), '_',
            CAST(FLOOR(spatial_data.destination_lon / 0.01) AS INTEGER)
        ) AS grid_cell_id
    FROM _raw_del_base
""")
con.execute("DROP TABLE IF EXISTS _raw_del_base")

print("\nRow counts:")
for table in ['raw_customers', 'raw_products', 'raw_sellers', 'raw_orders', 'raw_deliveries']:
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<20} {n:>6,} rows")

con.close()
print(f"\nWarehouse ready: {os.path.abspath(DB_PATH)}")
