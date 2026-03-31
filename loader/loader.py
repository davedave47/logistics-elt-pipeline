import os
import duckdb

DB_DIR = '../db'
DB_PATH = os.path.join(DB_DIR, 'logistics.duckdb')
LAKE_DIR = '../data_lake'

os.makedirs(DB_DIR, exist_ok=True)

def build_data_warehouse():
    print(f"Connecting to DuckDB at: {os.path.abspath(DB_PATH)}")
    conn = duckdb.connect(DB_PATH)

    try:
        print("\nLoading Dimension Tables (CSV)...")
        conn.execute("""
            CREATE OR REPLACE TABLE stg_customers AS 
            SELECT * FROM read_csv_auto('../data_lake/raw_orders/crm_customers.csv');
        """)
        print(" + stg_customers loaded.")

        conn.execute("""
            CREATE OR REPLACE TABLE stg_products AS 
            SELECT * FROM read_csv_auto('../data_lake/raw_orders/ecommerce_products.csv');
        """)
        print(" + stg_products loaded.")

        print("\nLoading Fact Tables (JSON)...")
        conn.execute("""
            CREATE OR REPLACE TABLE stg_sales_orders AS 
            SELECT * FROM read_json_auto('../data_lake/raw_deliveries/sales_orders.json');
        """)
        print(" + stg_sales_orders loaded.")

        conn.execute("""
            CREATE OR REPLACE TABLE stg_delivery_telemetry AS 
            SELECT * FROM read_json_auto('../data_lake/raw_deliveries/delivery_telemetry.json');
        """)
        print(" + stg_delivery_telemetry loaded.")

        print("\n--- Warehouse Status ---")
        tables = conn.execute("SHOW TABLES").fetchall()
        for table in tables:
            table_name = table[0]
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            print(f"Table '{table_name}': {count:,} rows")

    except Exception as e:
        print(f"An error occurred during loading: {e}")
    finally:
        conn.close()
        print("\nConnection closed. Data Warehouse is ready for dbt Transformation.")

if __name__ == "__main__":
    build_data_warehouse()