import os
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

print("Loading delivery telemetry + computing spatial indices...")
# H3 and grid cells are computed at load time so dbt models stay pure SQL.
# Grid resolution: 0.01° ≈ 1.1 km × 1.1 km cells at HCMC latitude.
con.execute(f"""
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
    FROM read_json_auto('{JSON_DIR}/delivery_telemetry.json')
""")

print("\nRow counts:")
for table in ['raw_customers', 'raw_products', 'raw_sellers', 'raw_orders', 'raw_deliveries']:
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<20} {n:>6,} rows")

con.close()
print(f"\nWarehouse ready: {os.path.abspath(DB_PATH)}")
