import os
import csv
import json
import random
import uuid
from datetime import datetime, timedelta
from faker import Faker

fake = Faker('vi_VN')

LAKE_DIR = '../data_lake'
CSV_DIR = os.path.join(LAKE_DIR, 'raw_csv')
JSON_DIR = os.path.join(LAKE_DIR, 'raw_json')
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

def generate_customers(num_customers):
    customers = []
    filepath = os.path.join(CSV_DIR, 'crm_customers.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['customer_id', 'customer_name', 'phone', 'segment'])
        segments = ['Consumer', 'Corporate', 'Home Office']
        
        for i in range(1, num_customers + 1):
            record = [i, fake.name(), fake.phone_number(), random.choice(segments)]
            writer.writerow(record)
            customers.append(i)
    return customers

def generate_products(num_products):
    products = []
    filepath = os.path.join(CSV_DIR, 'ecommerce_products.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['product_id', 'product_name', 'category', 'price'])
        categories = ['Electronics', 'Home Goods', 'Apparel', 'Office Supplies']
        
        for i in range(1, num_products + 1):
            price = round(random.uniform(10.0, 500.0), 2)
            record = [i, f"Product {i}", random.choice(categories), price]
            writer.writerow(record)
            products.append(i)
    return products

def generate_sales_orders(num_orders, customers, products):
    filepath = os.path.join(JSON_DIR, 'sales_orders.json')
    orders_data = []
    routing_data = [] 
    
    for _ in range(num_orders):
        order_id = str(uuid.uuid4())
        customer_id = random.choice(customers)
        order_timestamp = datetime.now() - timedelta(days=random.randint(1, 30))
        
        line_items = []
        subtotal = 0
        for _ in range(random.randint(1, 5)):
            qty = random.randint(1, 3)
            unit_price = round(random.uniform(10.0, 100.0), 2) 
            line_items.append({
                "product_id": random.choice(products),
                "quantity": qty,
                "unit_price": unit_price
            })
            subtotal += (unit_price * qty)

        dest_lat = round(random.uniform(10.7000, 10.8500), 6)
        dest_lon = round(random.uniform(106.6000, 106.8000), 6)
        
        shipping_fee_paid = 0.00 if subtotal > 100 else 2.00
        
        order_record = {
            "order_id": order_id,
            "customer_id": customer_id,
            "order_timestamp": order_timestamp.isoformat(),
            "financials": {
                "subtotal_usd": round(subtotal, 2),
                "shipping_fee_paid_usd": shipping_fee_paid,
                "total_paid_usd": round(subtotal + shipping_fee_paid, 2)
            },
            "shipping_snapshot": {
                "recipient_name": fake.name(),
                "recipient_phone": fake.phone_number(),
                "destination_lat": dest_lat,
                "destination_lon": dest_lon,
                "address_text": fake.address()
            },
            "line_items": line_items
        }
        orders_data.append(order_record)
        
        routing_data.append({
            "order_id": order_id, 
            "customer_id": customer_id,
            "lat": dest_lat, 
            "lon": dest_lon,
            "ordered_at": order_timestamp
        })

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(orders_data, f, indent=4, ensure_ascii=False)
        
    return routing_data

def generate_route_telemetry(orders_list):
    filepath = os.path.join(JSON_DIR, 'delivery_telemetry.json')
    deliveries = []
    
    random.shuffle(orders_list)
    
    while orders_list:
        batch_size = random.randint(5, 15)
        route_orders = orders_list[:batch_size]
        orders_list = orders_list[batch_size:]
        
        if not route_orders:
            break
            
        driver_id = f"DRV_{random.randint(100, 999)}"
        vehicle_type = random.choice(['motorbike', 'van'])
        
        # Dispatch route a few hours after the latest order in the batch
        latest_order_time = max(o['ordered_at'] for o in route_orders)
        route_dispatched_at = latest_order_time + timedelta(hours=random.randint(2, 12))
        
        current_est_time = route_dispatched_at
        current_act_time = route_dispatched_at
        
        for stop_number, order in enumerate(route_orders):
            lat = order['lat']
            lon = order['lon']
            
            distance_miles = round(random.uniform(0.5, 3.0), 2)
            transit_mins = int(distance_miles * 6) + 3 
            
            current_est_time += timedelta(minutes=transit_mins)
            
            is_complex_zone = (10.7600 < lat < 10.7900) and (106.6700 < lon < 106.6900)
            
            if is_complex_zone and random.random() > 0.4:
                delay = random.randint(20, 50) 
                current_act_time += timedelta(minutes=(transit_mins + delay))
                status = 'Delivered' if random.random() > 0.1 else 'Failed'
            else:
                current_act_time += timedelta(minutes=(transit_mins + random.randint(-2, 5)))
                status = 'Delivered'
                
            record = {
                "order_id": order['order_id'],
                "customer_id": order['customer_id'],
                "spatial_data": {
                    "lat": lat,
                    "lon": lon
                },
                "telemetry": {
                    "ordered_at": order['ordered_at'].isoformat(),
                    "dispatched_at": route_dispatched_at.isoformat(),
                    "estimated_delivery_at": current_est_time.isoformat(),
                    "actual_delivery_at": current_act_time.isoformat(),
                    "status": status
                },
                "logistics_meta": {
                    "route_id": f"RT_{route_dispatched_at.strftime('%Y%m%d')}_{driver_id}",
                    "stop_number": stop_number + 1,
                    "distance_from_last_stop": distance_miles,
                    "vehicle_type": vehicle_type,
                    "driver_id": driver_id
                }
            }
            deliveries.append(record)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(deliveries, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    TOTAL_CUSTOMERS = 1000
    TOTAL_PRODUCTS = 50
    TOTAL_ORDERS = 5000

    print("Generating Dimensions...")
    customer_ids = generate_customers(TOTAL_CUSTOMERS)
    product_ids = generate_products(TOTAL_PRODUCTS)
    
    print("Generating Sales Orders...")
    generated_orders = generate_sales_orders(TOTAL_ORDERS, customer_ids, product_ids)
    
    print("Generating Route Telemetry...")
    generate_route_telemetry(generated_orders)
    
    print(f"Success! Data Lake populated in: {os.path.abspath(LAKE_DIR)}")