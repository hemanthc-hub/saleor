import os
import datetime
import jwt
from flask import Blueprint, request, jsonify, render_template_string, current_app
from flask_mail import Message
from admin_ops.database import db, EmailLog
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger

log = get_logger()
emails_bp = Blueprint('emails', __name__)

JWT_SECRET = os.environ.get("FLASK_SECRET_KEY", "super-secure-hegma-key-1234")
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# --- GRAPHQL QUERIES ---

FETCH_ORDER_FOR_EMAIL_QUERY = """
query GetOrderForEmail($id: ID!) {
  order(id: $id) {
    id
    number
    created
    status
    paymentStatus
    shippingMethodName
    userEmail
    total {
      gross {
        amount
        currency
      }
    }
    shippingPrice {
      gross {
        amount
      }
    }
    shippingAddress {
      firstName
      lastName
      streetAddress1
      city
      postalCode
      phone
      country { code }
    }
    billingAddress {
      firstName
      lastName
      streetAddress1
      city
      postalCode
      phone
    }
    lines {
      productName
      productSku
      quantity
      unitPrice {
        gross {
          amount
        }
      }
      totalPrice {
        gross {
          amount
        }
      }
      variant {
        product {
          id
          name
          thumbnail { url }
        }
      }
    }
  }
}
"""

FIND_ORDER_BY_NUMBER_QUERY = """
query FindOrderByNumber($search: String!) {
  orders(first: 1, filter: { search: $search }) {
    edges {
      node {
        id
        number
      }
    }
  }
}
"""

def load_template(filename):
    """Loads a Jinja2 template file from admin_ops/templates."""
    path = os.path.join(TEMPLATES_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    # Fallback to local scratch if not found
    scratch_path = os.path.join("/Users/nagarajbhat/.gemini/antigravity-ide/brain/bd564d2d-a171-447f-b6df-17757fd71971/scratch", filename)
    if os.path.exists(scratch_path):
        with open(scratch_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def format_address(addr):
    if not addr:
        return ""
    parts = filter(None, [
        addr.get("streetAddress1"),
        addr.get("city"),
        addr.get("postalCode"),
        addr.get("country", {}).get("code") if isinstance(addr.get("country"), dict) else addr.get("country")
    ])
    return ", ".join(parts)

def fetch_order_data(order_id_or_number):
    """Fetches full order details from Saleor GraphQL."""
    order_id = str(order_id_or_number).strip()
    
    # If a short order number was passed (e.g. "1415"), resolve to GraphQL ID
    if not order_id.startswith("T3JkZXI") and not order_id.startswith("Order:"):
        res_num = execute_graphql(FIND_ORDER_BY_NUMBER_QUERY, {"search": order_id})
        if res_num and res_num.get("data"):
            edges = res_num["data"].get("orders", {}).get("edges", [])
            if edges:
                order_id = edges[0]["node"]["id"]
            
    res = execute_graphql(FETCH_ORDER_FOR_EMAIL_QUERY, {"id": order_id})
    if not res or res.get("error") or not res.get("data") or not res["data"].get("order"):
        return None
        
    order = res["data"]["order"]
    
    # Format lines
    formatted_lines = []
    for l in order.get("lines", []):
        unit_p = l.get("unitPrice", {}).get("gross", {}).get("amount", 0)
        tot_p = l.get("totalPrice", {}).get("gross", {}).get("amount", unit_p * l.get("quantity", 1))
        product_node = (l.get("variant") or {}).get("product") or {}
        thumb = (product_node.get("thumbnail") or {}).get("url")
        formatted_lines.append({
            "product_name": l.get("productName", ""),
            "sku": l.get("productSku", ""),
            "quantity": l.get("quantity", 1),
            "unit_price": unit_p,
            "total_price": tot_p,
            "product_id": product_node.get("id"),
            "thumbnail": thumb
        })
        
    ship_addr = order.get("shippingAddress") or {}
    cust_name = f"{ship_addr.get('firstName', '')} {ship_addr.get('lastName', '')}".strip()
    if not cust_name:
        cust_name = order.get("userEmail", "Customer")
        
    created_str = order.get("created", "")
    try:
        dt = datetime.datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        created_formatted = dt.strftime("%b %d, %Y, %I:%M %p")
    except Exception:
        created_formatted = created_str
        
    total_gross = order.get("total", {}).get("gross", {})
    ship_price = order.get("shippingPrice", {}).get("gross", {}).get("amount", 0)
    
    return {
        "id": order.get("id"),
        "number": order.get("number"),
        "user_email": order.get("userEmail") or "",
        "customer_name": cust_name,
        "customer_phone": ship_addr.get("phone", ""),
        "created_date": created_formatted,
        "payment_status": order.get("paymentStatus", "NOT_CHARGED").replace('_', ' ').title(),
        "shipping_method": order.get("shippingMethodName", "Standard Delivery"),
        "shipping_address": format_address(ship_addr),
        "lines": formatted_lines,
        "shipping_amount": ship_price,
        "total_amount": total_gross.get("amount", 0),
        "currency": total_gross.get("currency", "INR")
    }

def dispatch_email(recipient, subject, html_content, order_id=None, order_number=None, email_type="ORDER_RECEIPT"):
    """Dispatches email via Flask-Mail and records entry into EmailLog."""
    status = "SENT"
    err_msg = None
    
    try:
        mail = current_app.extensions.get('mail')
        msg = Message(
            subject=subject,
            sender='no-reply@hegmakart.com',
            recipients=[recipient]
        )
        msg.html = html_content
        
        if mail:
            mail.send(msg)
            log.info(f"Dispatched {email_type} to {recipient} for order #{order_number}")
        else:
            log.warning("Flask-Mail extension not found on current_app. Simulating send.")
    except Exception as e:
        status = "FAILED"
        err_msg = str(e)
        log.error(f"Failed to send {email_type} to {recipient}: {e}")
        
    # Save log to database
    try:
        email_record = EmailLog(
            order_id=order_id,
            order_number=str(order_number) if order_number else None,
            recipient_email=recipient,
            email_type=email_type,
            subject=subject,
            status=status,
            error_message=err_msg
        )
        db.session.add(email_record)
        db.session.commit()
    except Exception as db_err:
        log.error(f"Failed to save EmailLog: {db_err}")
        
    return status == "SENT", err_msg


# --- WEBHOOK ENDPOINTS ---

@emails_bp.route('/webhooks/order-created', methods=['POST'])
def webhook_order_created():
    """
    Saleor Webhook: ORDER_CREATED
    Parses payload, renders branded order receipt HTML, and sends to customer.
    """
    payload = request.json or {}
    log.info("Received ORDER_CREATED webhook")
    
    # Extract order ID or number
    order_id = payload.get("id") or (payload.get("order") or {}).get("id")
    order_number = payload.get("number") or (payload.get("order") or {}).get("number")
    
    order_data = None
    if order_id:
        order_data = fetch_order_data(order_id)
    elif order_number:
        order_data = fetch_order_data(order_number)
        
    if not order_data:
        # Fallback: parse raw payload fields directly
        email = payload.get("userEmail") or payload.get("email") or "customer@example.com"
        order_data = {
            "id": order_id or "N/A",
            "number": order_number or "N/A",
            "user_email": email,
            "customer_name": payload.get("customer_name", "Customer"),
            "customer_phone": payload.get("phone", ""),
            "created_date": datetime.datetime.now().strftime("%b %d, %Y"),
            "payment_status": "Confirmed",
            "shipping_method": "Standard Delivery",
            "shipping_address": payload.get("shipping_address", ""),
            "lines": payload.get("lines", []),
            "total_amount": payload.get("total_amount", 0),
            "currency": "INR"
        }
        
    recipient = order_data["user_email"]
    if not recipient:
        return jsonify({"success": False, "message": "No customer email found in order."}), 400
        
    # Render receipt template
    tmpl = load_template("order_receipt.html")
    html_content = render_template_string(
        tmpl,
        order=order_data,
        customer_name=order_data["customer_name"],
        customer_phone=order_data["customer_phone"],
        current_year=datetime.datetime.now().year
    )
    
    subject = f"Order Confirmation #{order_data['number']} - HegmaKart"
    sent, err = dispatch_email(
        recipient=recipient,
        subject=subject,
        html_content=html_content,
        order_id=order_data["id"],
        order_number=order_data["number"],
        email_type="ORDER_RECEIPT"
    )
    
    if sent:
        return jsonify({"success": True, "message": f"Order receipt sent to {recipient}", "order_number": order_data["number"]})
    return jsonify({"success": False, "message": f"Failed to send email: {err}"}), 500


@emails_bp.route('/webhooks/order-fulfilled', methods=['POST'])
def webhook_order_fulfilled():
    """
    Saleor Webhook: ORDER_FULFILLED / DELIVERED
    Extracts products and sends automated verified review request email with signed JWT.
    """
    payload = request.json or {}
    log.info("Received ORDER_FULFILLED webhook")
    
    order_id = payload.get("id") or (payload.get("order") or {}).get("id")
    order_number = payload.get("number") or (payload.get("order") or {}).get("number")
    
    order_data = fetch_order_data(order_id or order_number)
    if not order_data:
        return jsonify({"success": False, "message": "Order not found"}), 404
        
    recipient = order_data["user_email"]
    if not recipient:
        return jsonify({"success": False, "message": "Customer email missing"}), 400
        
    # Pick first available product or product line
    lines = order_data.get("lines", [])
    if not lines:
        return jsonify({"success": False, "message": "No product lines in order"}), 400
        
    target_product = lines[0]
    product_id = target_product.get("product_id") or "UNKNOWN_PRODUCT"
    product_name = target_product.get("product_name", "your purchased product")
    product_thumbnail = target_product.get("thumbnail")
    
    # Generate 30-day cryptographically signed JWT review token
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    token_payload = {
        "order_id": order_data["id"],
        "product_id": product_id,
        "exp": exp
    }
    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    review_url = f"https://hegmakart.com/write-review?token={token}"
    
    # Render review request template
    tmpl = load_template("review_request.html")
    html_content = render_template_string(
        tmpl,
        order_number=order_data["number"],
        product_name=product_name,
        product_thumbnail=product_thumbnail,
        review_url=review_url,
        current_year=datetime.datetime.now().year
    )
    
    subject = f"How was your purchase of {product_name}? - HegmaKart"
    sent, err = dispatch_email(
        recipient=recipient,
        subject=subject,
        html_content=html_content,
        order_id=order_data["id"],
        order_number=order_data["number"],
        email_type="REVIEW_REQUEST"
    )
    
    if sent:
        return jsonify({
            "success": True, 
            "message": f"Review invitation sent to {recipient}",
            "review_url": review_url
        })
    return jsonify({"success": False, "message": f"Failed: {err}"}), 500


# --- ADMIN RESEND & MANAGEMENT ENDPOINTS ---

@emails_bp.route('/emails/resend', methods=['POST'])
@emails_bp.route('/admin/emails/resend', methods=['POST'])
def admin_resend_email():
    """
    Admin Endpoint: Resend any transactional email with optional email override.
    Displays and confirms recipient email ID.
    Body:
    {
      "order_id": "T3JkZXI...",
      "email_type": "ORDER_RECEIPT" | "REVIEW_REQUEST",
      "recipient_email": "override@email.com" (Optional)
    }
    """
    data = request.json or {}
    order_id = data.get("order_id")
    email_type = data.get("email_type", "ORDER_RECEIPT")
    custom_recipient = data.get("recipient_email", "").strip()
    
    if not order_id:
        return jsonify({"success": False, "message": "order_id is required"}), 400
        
    order_data = fetch_order_data(order_id)
    if not order_data:
        return jsonify({"success": False, "message": f"Order {order_id} not found in Saleor"}), 404
        
    # Use override email if provided, else order's original customer email
    target_email = custom_recipient or order_data.get("user_email")
    if not target_email:
        return jsonify({"success": False, "message": "No recipient email available for this order. Please specify recipient_email."}), 400
        
    if email_type == "REVIEW_REQUEST":
        lines = order_data.get("lines", [])
        target_product = lines[0] if lines else {}
        product_id = target_product.get("product_id") or "UNKNOWN_PRODUCT"
        product_name = target_product.get("product_name", "purchased product")
        product_thumbnail = target_product.get("thumbnail")
        
        exp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        token_payload = {
            "order_id": order_data["id"],
            "product_id": product_id,
            "exp": exp
        }
        token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
        review_url = f"https://hegmakart.com/write-review?token={token}"
        
        tmpl = load_template("review_request.html")
        html_content = render_template_string(
            tmpl,
            order_number=order_data["number"],
            product_name=product_name,
            product_thumbnail=product_thumbnail,
            review_url=review_url,
            current_year=datetime.datetime.now().year
        )
        subject = f"[Resent] How was your purchase of {product_name}? - HegmaKart"
    else:
        # ORDER_RECEIPT
        tmpl = load_template("order_receipt.html")
        html_content = render_template_string(
            tmpl,
            order=order_data,
            customer_name=order_data["customer_name"],
            customer_phone=order_data["customer_phone"],
            current_year=datetime.datetime.now().year
        )
        subject = f"[Receipt Resent] Order Confirmation #{order_data['number']} - HegmaKart"
        
    sent, err = dispatch_email(
        recipient=target_email,
        subject=subject,
        html_content=html_content,
        order_id=order_data["id"],
        order_number=order_data["number"],
        email_type=email_type
    )
    
    if sent:
        return jsonify({
            "success": True,
            "message": f"Successfully resent {email_type.replace('_', ' ')} to {target_email}",
            "recipient_email": target_email,
            "order_number": order_data["number"],
            "email_type": email_type
        })
    return jsonify({"success": False, "message": f"Resend failed: {err}"}), 500


@emails_bp.route('/emails/logs', methods=['GET'])
@emails_bp.route('/admin/emails/logs', methods=['GET'])
def get_email_logs():
    """Fetches recent transactional email logs."""
    limit = int(request.args.get("limit", 50))
    logs = EmailLog.query.order_by(EmailLog.created_at.desc()).limit(limit).all()
    return jsonify({
        "success": True,
        "count": len(logs),
        "logs": [l.to_dict() for l in logs]
    })


@emails_bp.route('/emails/test', methods=['POST'])
@emails_bp.route('/admin/emails/test', methods=['POST'])
def send_test_email():
    """Sends a sample test email to verify SMTP."""
    data = request.json or {}
    email = data.get("email", "").strip()
    email_type = data.get("email_type", "ORDER_RECEIPT")
    
    if not email:
        return jsonify({"success": False, "message": "Email address is required"}), 400
        
    mock_order = {
        "id": "MOCK_ORDER_TEST",
        "number": "TEST-1001",
        "user_email": email,
        "customer_name": "Test Healthcare Clinic",
        "customer_phone": "+91 9999999999",
        "created_date": datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        "payment_status": "Paid (Test Mode)",
        "shipping_method": "Express Dental Courier",
        "shipping_address": "Suite 404, Medical Hub, Bengaluru, KA 560001",
        "lines": [
            {
                "product_name": "3M ESPE Filtek Z250 XT Syringe",
                "sku": "D-3MESP-RSTR-012-001",
                "quantity": 2,
                "unit_price": 1450.0,
                "total_price": 2900.0
            }
        ],
        "shipping_amount": 100.0,
        "total_amount": 3000.0,
        "currency": "INR"
    }
    
    if email_type == "REVIEW_REQUEST":
        tmpl = load_template("review_request.html")
        html_content = render_template_string(
            tmpl,
            order_number=mock_order["number"],
            product_name="3M ESPE Filtek Z250 XT Syringe",
            product_thumbnail="https://hegmadental.s3.amazonaws.com/__sized__/allimagesinone/3MESPEFiltekZ250XTSyringe001-thumbnail-255x255-70.jpg",
            review_url="https://hegmakart.com/write-review?token=SAMPLE_TEST_TOKEN",
            current_year=datetime.datetime.now().year
        )
        subject = "[Test Mode] Review Request - HegmaKart"
    else:
        tmpl = load_template("order_receipt.html")
        html_content = render_template_string(
            tmpl,
            order=mock_order,
            customer_name=mock_order["customer_name"],
            customer_phone=mock_order["customer_phone"],
            current_year=datetime.datetime.now().year
        )
        subject = f"[Test Mode] Order Confirmation #{mock_order['number']} - HegmaKart"
        
    sent, err = dispatch_email(
        recipient=email,
        subject=subject,
        html_content=html_content,
        order_id="TEST",
        order_number="TEST-1001",
        email_type="TEST_EMAIL"
    )
    
    if sent:
        return jsonify({"success": True, "message": f"Test email successfully sent to {email}"})
    return jsonify({"success": False, "message": f"Test send failed: {err}"}), 500


@emails_bp.route('/emails/preview', methods=['GET'])
@emails_bp.route('/admin/emails/preview', methods=['GET'])
def preview_email_template():
    """Returns rendered HTML preview of template with sample data."""
    t_type = request.args.get("type", "receipt")
    
    mock_order = {
        "id": "MOCK_ORDER",
        "number": "1415",
        "user_email": "customer@example.com",
        "customer_name": "Dr. Sarah Jenkins",
        "customer_phone": "+91 9876543210",
        "created_date": datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        "payment_status": "Paid",
        "shipping_method": "Bluedart Priority",
        "shipping_address": "Dental Care Center, MG Road, Bengaluru, KA 560001",
        "lines": [
            {
                "product_name": "Koden Cera Lock Brackets",
                "sku": "D-KODEN-BRKT-002-002",
                "quantity": 1,
                "unit_price": 9900.0,
                "total_price": 9900.0
            }
        ],
        "shipping_amount": 0.0,
        "total_amount": 9900.0,
        "currency": "INR"
    }
    
    if t_type == "review":
        tmpl = load_template("review_request.html")
        return render_template_string(
            tmpl,
            order_number=mock_order["number"],
            product_name="Koden Cera Lock Brackets",
            product_thumbnail="https://hegmadental.s3.amazonaws.com/__sized__/products/Koden_Cera_Lock_Brackets_001_3e5998ee-thumbnail-255x255-70.jpg",
            review_url="https://hegmakart.com/write-review?token=SAMPLE_PREVIEW_TOKEN",
            current_year=datetime.datetime.now().year
        )
    else:
        tmpl = load_template("order_receipt.html")
        return render_template_string(
            tmpl,
            order=mock_order,
            customer_name=mock_order["customer_name"],
            customer_phone=mock_order["customer_phone"],
            current_year=datetime.datetime.now().year
        )
