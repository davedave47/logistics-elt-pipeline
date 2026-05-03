"""
Phase 2b — Load from GCS into BigQuery raw tables.

Uses BigQuery native load jobs (no Airbyte/Fivetran needed).
CSV files use auto-detect schema. NDJSON files use auto-detect for
nested STRUCT/ARRAY types.

Env vars required:
  GCP_PROJECT      — GCP project ID
  GCS_BUCKET       — bucket name (same as upload_to_gcs.py)
  BQ_DATASET_RAW   — BigQuery dataset for raw tables (default: logistics_raw)
"""
import os
from google.cloud import bigquery

PROJECT = os.environ['GCP_PROJECT']
BUCKET  = os.environ['GCS_BUCKET']
DATASET = os.environ.get('BQ_DATASET_RAW', 'logistics_raw')

client = bigquery.Client(project=PROJECT)

# Create dataset if it doesn't exist
ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
ds.location = "US"
client.create_dataset(ds, exists_ok=True)
print(f"Dataset ready: {PROJECT}.{DATASET}")


def load_csv(table: str, gcs_uri: str):
    ref = f"{PROJECT}.{DATASET}.{table}"
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_uri(gcs_uri, ref, job_config=cfg)
    job.result()
    n = client.get_table(ref).num_rows
    print(f"  {table:<20} {n:>6,} rows  ←  {gcs_uri}")


def load_ndjson(table: str, gcs_uri: str):
    ref = f"{PROJECT}.{DATASET}.{table}"
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_uri(gcs_uri, ref, job_config=cfg)
    job.result()
    n = client.get_table(ref).num_rows
    print(f"  {table:<20} {n:>6,} rows  ←  {gcs_uri}")


print("\nLoading structured dimensions (CSV → BigQuery)...")
load_csv('raw_customers', f'gs://{BUCKET}/raw_csv/customers.csv')
load_csv('raw_products',  f'gs://{BUCKET}/raw_csv/products.csv')
load_csv('raw_sellers',   f'gs://{BUCKET}/raw_csv/sellers.csv')

print("\nLoading semi-structured facts (NDJSON → BigQuery)...")
load_ndjson('raw_orders',     f'gs://{BUCKET}/raw_json/orders.ndjson')
load_ndjson('raw_deliveries', f'gs://{BUCKET}/raw_json/delivery_telemetry.ndjson')

print(f"\nBigQuery raw dataset ready: {PROJECT}.{DATASET}")
