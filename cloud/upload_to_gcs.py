"""
Phase 2a — Upload data lake files to GCS.

Converts JSON arrays to NDJSON (one record per line) since BigQuery's native
load job requires newline-delimited JSON. Also computes H3 and grid_cell_id
at this stage (same role as the Python UDF in load_to_duckdb.py).

Env vars required:
  GCS_BUCKET   — bucket name, e.g. 'logistics-data-lake-hcmc'
  GOOGLE_APPLICATION_CREDENTIALS — path to service account key JSON
                                   (or use: gcloud auth application-default login)
"""
import os
import json
import math
import h3 as h3lib
from dotenv import load_dotenv
from google.cloud import storage

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

BUCKET   = os.environ['GCS_BUCKET']
PROJECT  = os.environ['GCP_PROJECT']
LAKE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data_lake')
client = storage.Client(project=PROJECT)
bucket = client.bucket(BUCKET)


def upload_bytes(data: str, gcs_path: str, content_type='application/octet-stream'):
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data.encode('utf-8'), content_type=content_type)


def upload_file(local_path: str, gcs_path: str):
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    size = os.path.getsize(local_path)
    print(f"  {gcs_path}  ({size/1024:.1f} KB)")


def add_spatial_indices(record: dict) -> dict:
    """Enrich each delivery_telemetry record with H3 and grid_cell_id."""
    lat = record['spatial_data']['destination_lat']
    lon = record['spatial_data']['destination_lon']
    record['h3_cell_9'] = h3lib.latlng_to_cell(lat, lon, 9)
    record['grid_cell_id'] = f"{math.floor(lat / 0.01)}_{math.floor(lon / 0.01)}"
    return record


def json_to_ndjson(local_path: str, gcs_path: str, transform=None):
    with open(local_path, encoding='utf-8') as f:
        records = json.load(f)
    if transform:
        records = [transform(r) for r in records]
    ndjson = '\n'.join(json.dumps(r, default=str, ensure_ascii=False) for r in records)
    upload_bytes(ndjson, gcs_path, content_type='application/json')
    print(f"  {gcs_path}  ({len(records):,} records)")


print("Uploading structured dimensions (CSV)...")
for name in ['customers.csv', 'products.csv', 'sellers.csv']:
    upload_file(os.path.join(LAKE_DIR, 'raw_csv', name), f'raw_csv/{name}')

print("Uploading orders (JSON → NDJSON)...")
json_to_ndjson(
    os.path.join(LAKE_DIR, 'raw_json', 'orders.json'),
    'raw_json/orders.ndjson'
)

print("Uploading delivery telemetry (JSON → NDJSON + H3 + grid_cell_id)...")
json_to_ndjson(
    os.path.join(LAKE_DIR, 'raw_json', 'delivery_telemetry.json'),
    'raw_json/delivery_telemetry.ndjson',
    transform=add_spatial_indices
)

print(f"\nAll files uploaded to gs://{BUCKET}/")
