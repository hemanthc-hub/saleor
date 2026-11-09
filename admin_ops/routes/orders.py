import csv
import io
import datetime
from flask import Blueprint, request, jsonify, send_file
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger

log = get_logger()
orders_bp = Blueprint('orders', __name__)

# --- GRAPHQL QUERIES ---

FETCH_FILTERED_ORDERS_QUERY = """
query GetFilteredOrders($filter: OrderFilterInput!) {
  orders(first: 100, filter: $filter) {
    edges {
      node {
        id
        number
        status
        created
        paymentStatus
        total { gross { amount currency } }
        shippingMethodName
        userEmail
        billingAddress { firstName lastName streetAddress1 city postalCode country { code } phone }
        shippingAddress { firstName lastName streetAddress1 city postalCode country { code } phone }
        lines { productName productSku quantity }
        invoices { url }
        fulfillments { trackingNumber }
        metadata { key value }
      }
    }
  }
}
"""

FETCH_TRACKING_QUERY = """
query GetTrackingExport($updatedGte: DateTime!) {
  orders(first: 100, filter: {updatedAt: {gte: $updatedGte}}) {
    edges {
      node {
        number
        userEmail
        channel { slug }
        fulfillments {
          id
          created
          status
          trackingNumber
        }
      }
    }
  }
}
"""


UPDATE_ORDER_METADATA_MUTATION = '''
mutation UpdateOrderMetadata($id: ID!, $input: [MetadataInput!]!) {
  updateMetadata(id: $id, input: $input) {
    errors { field message }
    item {
      ... on Order {
        id
        metadata { key value }
      }
    }
  }
}
'''

ORDER_FULFILL_MUTATION = """
mutation FulfillOrder($order: ID!, $trackingNumber: String!) {
  orderFulfill(
    order: $order
    input: { lines: [] notifyCustomer: true }
  ) {
    errors { field message code }
    fulfillments { id status }
  }
}
"""

UPDATE_TRACKING_MUTATION = """
mutation UpdateTracking($id: ID!, $tracking: String!) {
  fulfillmentUpdateTracking(id: $id, input: {trackingNumber: $tracking, notifyCustomer: true}) {
    errors { field message }
    fulfillment { trackingNumber }
  }
}
"""

def format_address(addr):
    if not addr: return ""
    parts = [
        f"{addr.get('firstName', '')} {addr.get('lastName', '')}".strip(),
        addr.get("streetAddress1", ""),
        addr.get("city", ""),
        addr.get("postalCode", ""),
        addr.get("country", {}).get("code", "") if addr.get("country") else ""
    ]
    return ", ".join([p for p in parts if p])





def _fetch_and_filter_orders(filter_type, start_date=None, end_date=None):
    filter_input = {}
    if filter_type == "PENDING":
        filter_input["status"] = "UNFULFILLED"
    elif filter_type == "MISSING_TRACKING":
        filter_input["status"] = "FULFILLED"
    elif filter_type == "PARTIAL":
        filter_input["status"] = "PARTIALLY_FULFILLED" 
    elif filter_type == "CANCELLED":
        filter_input["status"] = "CANCELED"
    elif filter_type == "RETURNED":
        filter_input["status"] = "RETURNED"
    elif filter_type == "COMPLETED":
        filter_input["status"] = "FULFILLED"
        
    if start_date or end_date:
        created_filter = {}
        if start_date:
            created_filter["gte"] = start_date
        if end_date:
            created_filter["lte"] = end_date
        filter_input["created"] = created_filter
    
    variables = {"filter": filter_input}
    res = execute_graphql(FETCH_FILTERED_ORDERS_QUERY, variables)
    if res.get("error"):
        raise Exception(str(res["error"]))
        
    edges = res.get("data", {}).get("orders", {}).get("edges", [])
    orders = [e["node"] for e in edges]
    
    # Python-side filtering
    filtered = []
    custom_statuses = ["ABANDONED", "READY_TO_SHIP", "SHIPPED", "IN_TRANSIT", "DELIVERED"]
    
    for order in orders:
        metadata = order.get("metadata", [])
        hegma_status = next((m.get("value") for m in metadata if m.get("key") == "hegma_status"), None)
        
        if filter_type in custom_statuses:
            if hegma_status != filter_type: continue
        else:
            if hegma_status in custom_statuses: continue
            
            if filter_type == "MISSING_INVOICES":
                if len(order.get("invoices", [])) > 0:
                    continue
            elif filter_type == "MISSING_TRACKING":
                fulfillments = order.get("fulfillments", [])
                has_tracking = any(f.get("trackingNumber") for f in fulfillments)
                if has_tracking:
                    continue
            elif filter_type == "PARTIAL":
                if order.get("status") not in ["PARTIALLY_FULFILLED", "PARTIALLY_RETURNED"]:
                    continue
        
        filtered.append(order)
        
    return filtered

@orders_bp.route('/orders/list', methods=['GET'])
def list_orders():
    filter_type = request.args.get("filter", "ALL")
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")
    try:
        orders = _fetch_and_filter_orders(filter_type, start_date, end_date)
        return jsonify({"success": True, "orders": orders})
    except Exception as e:
        log.error(f"Failed to list orders: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@orders_bp.route('/orders/export', methods=['GET'])
def export_orders():
    log.info("Starting order export process...")
    filter_type = request.args.get("filter", "ALL")
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")
    order_ids = request.args.get("ids", "")
    
    try:
        orders = _fetch_and_filter_orders(filter_type, start_date, end_date)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
        
    if order_ids:
        ids_list = order_ids.split(",")
        orders = [o for o in orders if o["id"] in ids_list]

    if not orders:
        return jsonify({"success": False, "message": "No orders found to export."}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Order ID", "Date", "Customer Name", "Customer Email", "Phone",
        "Shipping Address", "Billing Address", "Products", "Payment Status", "Total Amount", "Currency",
        "Tracking Numbers", "Invoice URLs"
    ])

    for order in orders:
        created_date = datetime.datetime.fromisoformat(order["created"].replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
        email = order.get("userEmail") or ""
        
        ship_addr = order.get("shippingAddress") or {}
        bill_addr = order.get("billingAddress") or {}
        name = f"{ship_addr.get('firstName', '')} {ship_addr.get('lastName', '')}".strip()
        phone = ship_addr.get("phone", "")
        
        def _fmt(addr):
            if not addr: return ""
            parts = filter(None, [addr.get('streetAddress1'), addr.get('city'), addr.get('postalCode'), addr.get('country', {}).get('code')])
            return ", ".join(parts)
            
        shipping_address = _fmt(ship_addr)
        billing_address = _fmt(bill_addr)
        
        lines = order.get("lines", [])
        products_str = " | ".join([f"{l['quantity']}x {l['productName']} ({l['productSku']})" for l in lines])
        
        total = order.get("total", {}).get("gross", {})
        amount = total.get("amount", 0)
        currency = total.get("currency", "")
        payment_status = order.get("paymentStatus", "")
        
        tracking_numbers = ", ".join([f.get("trackingNumber") for f in order.get("fulfillments", []) if f.get("trackingNumber")])
        invoice_urls = ", ".join([i.get("url") for i in order.get("invoices", []) if i.get("url")])

        writer.writerow([
            order["number"], created_date, name, email, phone,
            shipping_address, billing_address, products_str, payment_status, amount, currency,
            tracking_numbers, invoice_urls
        ])

    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(
        mem,
        mimetype='text/csv',
        download_name=f"orders_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        as_attachment=True
    )


@orders_bp.route('/tracking/export/today', methods=['GET'])
def tracking_export_today():
    log.info("Starting tracking export for today...")
    
    # Get start of today in UTC
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    variables = {"updatedGte": today_start.isoformat()}
    result = execute_graphql(FETCH_TRACKING_QUERY, variables)
    
    if result["error"]: return jsonify({"success": False, "message": "Failed to connect to Saleor API"}), 500
    
    orders = result["data"].get("orders", {}).get("edges", [])
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "OrderNumber", "Channel", "CustomerEmail", "FulfillmentID", 
        "FulfillmentStatus", "TrackingNumber", "DateCreated"
    ])
    
    exported_count = 0
    for edge in orders:
        node = edge["node"]
        order_number = node["number"]
        email = node.get("userEmail", "")
        channel = node.get("channel", {}).get("slug", "")
        
        for fulfillment in node.get("fulfillments", []):
            # Check if fulfillment has tracking and was created today
            created_str = fulfillment.get("created")
            tracking = fulfillment.get("trackingNumber")
            
            if created_str:
                created_dt = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created_dt >= today_start and tracking:
                    cw.writerow([
                        order_number,
                        channel,
                        email,
                        fulfillment["id"],
                        fulfillment["status"],
                        tracking,
                        created_str
                    ])
                    exported_count += 1
    
    log.info(f"Exported {exported_count} tracking records.")
    
    response = send_file(io.BytesIO(si.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f"tracking_summary_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
    return response


@orders_bp.route('/orders/import', methods=['POST'])
def import_tracking():
    if 'file' not in request.files: return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']
    if not file or not file.filename.endswith('.csv'): return jsonify({"success": False, "error": "Invalid file format. Please upload a CSV."}), 400

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    csv_input = csv.DictReader(stream)
    
    required_cols = {"SaleorOrderID", "TrackingNumberToFill"}
    if not required_cols.issubset(set(csv_input.fieldnames or [])): return jsonify({"success": False, "error": "CSV is missing required columns: SaleorOrderID, TrackingNumberToFill"}), 400
    
    success_count = 0
    error_count = 0
    errors = []
    
    for row in csv_input:
        order_id = row.get("SaleorOrderID", "").strip()
        tracking = row.get("TrackingNumberToFill", "").strip()
        
        if not order_id or not tracking: continue
            
        result = execute_graphql(ORDER_FULFILL_MUTATION, {"order": order_id, "trackingNumber": tracking})
        
        if result["error"] or (result["data"]["orderFulfill"]["errors"]):
            error_count += 1
            errors.append(f"Order {order_id}: {result.get('error') or result['data']['orderFulfill']['errors']}")
        else:
            success_count += 1
            
    return jsonify({"success": True, "message": f"Successfully updated {success_count} tracking numbers. {error_count} failed."})



@orders_bp.route('/orders/status', methods=['POST'])
def update_orders_status():
    data = request.json
    order_ids = data.get("orderIds", [])
    status = data.get("status")
    meta_key = data.get("key", "hegma_status")
    
    if not order_ids or not status:
        return jsonify({"success": False, "message": "Missing orderIds or status"}), 400
        
    success_count = 0
    errors = []
    
    for oid in order_ids:
        variables = {
            "id": oid,
            "input": [{"key": meta_key, "value": status}]
        }
        res = execute_graphql(UPDATE_ORDER_METADATA_MUTATION, variables)
        if res.get("error") or res.get("data", {}).get("updateMetadata", {}).get("errors"):
            errors.append(f"{oid} failed")
        else:
            success_count += 1
            
    return jsonify({
        "success": True, 
        "message": f"Updated {success_count} orders to {status}.", 
        "errors": errors
    })

