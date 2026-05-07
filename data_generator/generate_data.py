import os
import csv
import json
import random
import uuid
import hashlib
from datetime import datetime, timedelta
from faker import Faker

fake = Faker('vi_VN')
random.seed(42)

LAKE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data_lake')
CSV_DIR = os.path.join(LAKE_DIR, 'raw_csv')
JSON_DIR = os.path.join(LAKE_DIR, 'raw_json')
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

# HCMC districts with GPS centers. complex=True marks spatially blind zones
# (narrow hẻm, busy markets) that cause systematic delivery delays.
DISTRICTS = [
    {'name': 'Quận 1',     'lat': 10.7769, 'lon': 106.7009, 'complex': False},
    {'name': 'Quận 3',     'lat': 10.7801, 'lon': 106.6821, 'complex': True},
    {'name': 'Quận 4',     'lat': 10.7572, 'lon': 106.7043, 'complex': False},
    {'name': 'Quận 5',     'lat': 10.7553, 'lon': 106.6639, 'complex': True},
    {'name': 'Quận 7',     'lat': 10.7294, 'lon': 106.7172, 'complex': False},
    {'name': 'Quận 10',    'lat': 10.7733, 'lon': 106.6668, 'complex': True},
    {'name': 'Bình Thạnh', 'lat': 10.8124, 'lon': 106.7120, 'complex': False},
    {'name': 'Gò Vấp',     'lat': 10.8388, 'lon': 106.6654, 'complex': True},
    {'name': 'Tân Bình',   'lat': 10.8031, 'lon': 106.6524, 'complex': False},
    {'name': 'Thủ Đức',    'lat': 10.8544, 'lon': 106.7538, 'complex': False},
    {'name': 'Bình Chánh', 'lat': 10.6883, 'lon': 106.6142, 'complex': False},
]

CATEGORIES = ['Electronics', 'Home Goods', 'Apparel', 'Food & Grocery', 'Office Supplies', 'Beauty']
PAYMENT_METHODS = ['credit_card', 'cod', 'momo', 'zalopay']


def jitter(center, radius=0.04):
    return round(center + random.uniform(-radius, radius), 6)


def cell_delay_prob(lat, lon, is_complex):
    """Per-cell delay probability with micro-zone variation.
    Complex districts average ~60% but range 35-85% per cell.
    Normal districts average ~11% but range 0-22% per cell.
    This breaks up the uniform district blobs into a realistic scatter.
    """
    noise = int(hashlib.md5(f"{int(lat*100)}_{int(lon*100)}".encode()).hexdigest()[:2], 16) / 255.0
    return (0.35 + noise * 0.50) if is_complex else (noise * 0.22)


def generate_customers(n=500):
    path = os.path.join(CSV_DIR, 'customers.csv')
    ids = []
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['customer_id', 'customer_name', 'phone', 'segment', 'district'])
        for _ in range(n):
            cid = str(uuid.uuid4())
            w.writerow([
                cid, fake.name(), fake.phone_number(),
                random.choice(['Consumer', 'Corporate', 'Home Office']),
                random.choice(DISTRICTS)['name']
            ])
            ids.append(cid)
    return ids


def generate_products(n=50):
    path = os.path.join(CSV_DIR, 'products.csv')
    ids = []
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['product_id', 'product_name', 'category', 'price_usd', 'weight_g'])
        for i in range(n):
            pid = str(uuid.uuid4())
            cat = random.choice(CATEGORIES)
            w.writerow([pid, f'{cat} Item {i+1}', cat,
                        round(random.uniform(5.0, 300.0), 2),
                        random.randint(100, 5000)])
            ids.append(pid)
    return ids


def generate_sellers(n=30):
    path = os.path.join(CSV_DIR, 'sellers.csv')
    ids = []
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['seller_id', 'seller_name', 'district', 'warehouse_lat', 'warehouse_lon'])
        for _ in range(n):
            sid = str(uuid.uuid4())
            d = random.choice(DISTRICTS)
            w.writerow([sid, fake.company(), d['name'],
                        jitter(d['lat'], 0.003), jitter(d['lon'], 0.003)])
            ids.append(sid)
    return ids


def generate_orders(n, customer_ids, product_ids, seller_ids):
    """
    Semi-structured: each order document nests payment, line_items array,
    and shipping_snapshot — reflecting how orders arrive from the e-commerce API.
    """
    orders = []
    routing = []

    for _ in range(n):
        oid = str(uuid.uuid4())
        ts = datetime.now() - timedelta(days=random.randint(1, 90))
        district = random.choice(DISTRICTS)
        lat = jitter(district['lat'])
        lon = jitter(district['lon'])

        line_items = []
        for _ in range(random.randint(1, 5)):
            qty = random.randint(1, 3)
            price = round(random.uniform(5.0, 200.0), 2)
            freight = round(random.uniform(0.5, 3.5), 2)
            line_items.append({
                'product_id': random.choice(product_ids),
                'seller_id': random.choice(seller_ids),
                'quantity': qty,
                'unit_price_usd': price,
                'freight_value_usd': freight
            })

        subtotal = sum(i['quantity'] * i['unit_price_usd'] for i in line_items)
        freight_total = sum(i['freight_value_usd'] for i in line_items)

        orders.append({
            'order_id': oid,
            'customer_id': random.choice(customer_ids),
            'order_status': random.choices(
                ['delivered', 'shipped', 'processing', 'cancelled'],
                weights=[70, 15, 10, 5]
            )[0],
            'order_timestamp': ts.isoformat(),
            'payment': {
                'method': random.choice(PAYMENT_METHODS),
                'installments': random.choice([1, 1, 1, 3, 6]),
                'amount_usd': round(subtotal + freight_total, 2)
            },
            'line_items': line_items,
            'shipping_snapshot': {
                'recipient_name': fake.name(),
                'destination_district': district['name'],
                'destination_lat': lat,
                'destination_lon': lon,
                'address_text': fake.address()
            }
        })
        routing.append({
            'order_id': oid,
            'lat': lat,
            'lon': lon,
            'is_complex': district['complex'],
            'ordered_at': ts
        })

    with open(os.path.join(JSON_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
        json.dump(orders, f, indent=2, ensure_ascii=False, default=str)

    return routing


def generate_delivery_telemetry(routing, driver_ids):
    """
    Semi-structured: each delivery stop nests spatial_data, telemetry timestamps,
    and complexity_factors — the raw signal for spatial blindness detection.
    """
    deliveries = []
    random.shuffle(routing)

    while routing:
        batch_size = random.randint(5, 15)
        batch, routing = routing[:batch_size], routing[batch_size:]

        driver_id = random.choice(driver_ids)
        vehicle = random.choice(['motorbike', 'van'])
        dispatched_at = max(o['ordered_at'] for o in batch) + timedelta(hours=random.randint(2, 8))
        route_id = f"RT_{dispatched_at.strftime('%Y%m%d')}_{driver_id}"

        est_time = dispatched_at

        for stop_num, order in enumerate(batch, 1):
            dist_km = round(random.uniform(0.3, 4.0), 2)
            base_mins = int(dist_km * 8) + 2
            est_time += timedelta(minutes=base_mins)

            # Per-stop delay uses a per-cell probability so cells within the same
            # district get different rates, breaking up uniform district blobs.
            prob = cell_delay_prob(order['lat'], order['lon'], order['is_complex'])
            if random.random() < prob:
                stop_delay = random.randint(15, 60)
                traffic_zone = 'high'
                has_hem = True
                status = 'delivered' if random.random() > 0.12 else 'failed'
            else:
                stop_delay = random.randint(-2, 8)
                traffic_zone = random.choice(['low', 'medium'])
                has_hem = random.random() > 0.8
                status = 'delivered'

            act_time = est_time + timedelta(minutes=stop_delay)

            deliveries.append({
                'order_id': order['order_id'],
                'route_id': route_id,
                'driver_id': driver_id,
                'stop_number': stop_num,
                'vehicle_type': vehicle,
                'spatial_data': {
                    'destination_lat': order['lat'],
                    'destination_lon': order['lon'],
                    'distance_from_prev_km': dist_km
                },
                'telemetry': {
                    'dispatched_at': dispatched_at.isoformat(),
                    'estimated_arrival_at': est_time.isoformat(),
                    'actual_arrival_at': act_time.isoformat(),
                    'status': status
                },
                'complexity_factors': {
                    'traffic_zone': traffic_zone,
                    'has_hem_access': has_hem,
                    'weather_condition': random.choice(['clear', 'clear', 'rainy'])
                }
            })

    with open(os.path.join(JSON_DIR, 'delivery_telemetry.json'), 'w', encoding='utf-8') as f:
        json.dump(deliveries, f, indent=2, ensure_ascii=False, default=str)


if __name__ == '__main__':
    print("Generating dimensions (CSV)...")
    customer_ids = generate_customers(500)
    product_ids = generate_products(50)
    seller_ids = generate_sellers(30)

    print("Generating orders (JSON)...")
    routing = generate_orders(100000, customer_ids, product_ids, seller_ids)

    print("Generating delivery telemetry (JSON)...")
    driver_ids = [f'DRV_{i:03d}' for i in range(1, 51)]
    generate_delivery_telemetry(routing, driver_ids)

    print(f"\nDone. Data Lake populated at: {os.path.abspath(LAKE_DIR)}")
    print(f"  raw_csv/ : customers.csv, products.csv, sellers.csv")
    print(f"  raw_json/: orders.json, delivery_telemetry.json")
