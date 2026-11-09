import re
import datetime
from flask import Blueprint, request, jsonify
from admin_ops.database import db, CourierSLA
from logger import get_logger

log = get_logger()
delivery_bp = Blueprint('delivery', __name__)

# Indian Gazetted & Major National Holidays (month, day)
INDIAN_HOLIDAYS = {
    (1, 1),    # New Year's Day
    (1, 26),   # Republic Day
    (5, 1),    # May Day
    (8, 15),   # Independence Day
    (10, 2),   # Mahatma Gandhi Jayanti
    (11, 1),   # Kannada Rajyotsava (Regional HQ)
    (12, 25),  # Christmas
}

DEFAULT_RULES = [
    {
        "courier_name": "Bluedart Air Express",
        "zone_name": "Bengaluru Metro",
        "pincode_prefixes": "560, 561, 562",
        "transit_days": 1,
        "base_price": 70.0,
        "per_kg_price": 25.0,
        "cutoff_hour": 14,
        "is_active": True
    },
    {
        "courier_name": "Delhivery Express Surface",
        "zone_name": "Bengaluru Metro",
        "pincode_prefixes": "560, 561, 562",
        "transit_days": 2,
        "base_price": 45.0,
        "per_kg_price": 18.0,
        "cutoff_hour": 15,
        "is_active": True
    },
    {
        "courier_name": "Bluedart Air Express",
        "zone_name": "South India Tier-1 & Tier-2",
        "pincode_prefixes": "57, 58, 59, 50, 51, 52, 53, 60, 61, 62, 63, 64, 67, 68, 69",
        "transit_days": 2,
        "base_price": 110.0,
        "per_kg_price": 35.0,
        "cutoff_hour": 13,
        "is_active": True
    },
    {
        "courier_name": "DTDC Standard Surface",
        "zone_name": "South India Tier-1 & Tier-2",
        "pincode_prefixes": "57, 58, 59, 50, 51, 52, 53, 60, 61, 62, 63, 64, 67, 68, 69",
        "transit_days": 3,
        "base_price": 65.0,
        "per_kg_price": 22.0,
        "cutoff_hour": 14,
        "is_active": True
    },
    {
        "courier_name": "Bluedart Air Express",
        "zone_name": "Pan-India National Metro",
        "pincode_prefixes": "11, 12, 40, 41, 70, 38",
        "transit_days": 2,
        "base_price": 140.0,
        "per_kg_price": 45.0,
        "cutoff_hour": 13,
        "is_active": True
    },
    {
        "courier_name": "Delhivery Standard Surface",
        "zone_name": "Rest of India (General)",
        "pincode_prefixes": "*",
        "transit_days": 4,
        "base_price": 85.0,
        "per_kg_price": 28.0,
        "cutoff_hour": 14,
        "is_active": True
    },
    {
        "courier_name": "DTDC Economy Surface",
        "zone_name": "Rest of India (Economy)",
        "pincode_prefixes": "*",
        "transit_days": 6,
        "base_price": 55.0,
        "per_kg_price": 20.0,
        "cutoff_hour": 14,
        "is_active": True
    }
]

def ensure_default_slas():
    """Seeds default courier SLAs if the table is currently empty."""
    try:
        count = CourierSLA.query.count()
        if count == 0:
            for rule in DEFAULT_RULES:
                sla = CourierSLA(
                    courier_name=rule["courier_name"],
                    zone_name=rule["zone_name"],
                    pincode_prefixes=rule["pincode_prefixes"],
                    transit_days=rule["transit_days"],
                    base_price=rule["base_price"],
                    per_kg_price=rule["per_kg_price"],
                    cutoff_hour=rule["cutoff_hour"],
                    is_active=rule["is_active"]
                )
                db.session.add(sla)
            db.session.commit()
            log.info("Seeded default courier SLAs.")
    except Exception as e:
        log.error(f"Error ensuring default SLAs: {e}")

def is_working_day(date_obj):
    """Checks if a given date is a working day (skips Sundays and gazetted holidays)."""
    # 6 is Sunday in Python's weekday() (0=Monday, ..., 6=Sunday)
    if date_obj.weekday() == 6:
        return False
    if (date_obj.month, date_obj.day) in INDIAN_HOLIDAYS:
        return False
    return True

def calculate_transit_and_edd(transit_business_days, cutoff_hour=14, order_time=None):
    """
    Calculates dispatch date and estimated delivery date (EDD)
    by advancing across working days and skipping weekends & holidays.
    """
    if order_time is None:
        order_time = datetime.datetime.now()

    # Determine initial dispatch day
    current_date = order_time.date()
    is_cutoff_passed = order_time.hour >= cutoff_hour

    # If order is placed after cutoff or on non-working day, advance dispatch date
    if is_cutoff_passed or not is_working_day(current_date):
        current_date += datetime.timedelta(days=1)
        while not is_working_day(current_date):
            current_date += datetime.timedelta(days=1)

    dispatch_date = current_date

    # Advance business transit days
    days_counted = 0
    delivery_date = dispatch_date

    while days_counted < transit_business_days:
        delivery_date += datetime.timedelta(days=1)
        if is_working_day(delivery_date):
            days_counted += 1

    # Format user-friendly dates
    formatted_edd = delivery_date.strftime("%A, %b %d, %Y")
    short_window = f"Delivered by {delivery_date.strftime('%a, %b %d')}"

    return {
        "dispatch_date": dispatch_date.isoformat(),
        "delivery_date": delivery_date.isoformat(),
        "delivery_date_formatted": formatted_edd,
        "delivery_window": short_window,
        "is_cutoff_passed": is_cutoff_passed,
        "cutoff_time": f"{cutoff_hour % 12 or 12}:00 {'PM' if cutoff_hour >= 12 else 'AM'}"
    }

def find_matching_slas(pincode):
    """Finds active courier SLAs matching the given pincode, prioritizing specific prefixes."""
    ensure_default_slas()
    clean_pincode = str(pincode).strip().replace(" ", "")
    all_active = CourierSLA.query.filter_by(is_active=True).all()

    prefix_matches = []
    wildcard_matches = []

    for sla in all_active:
        prefixes_str = sla.pincode_prefixes or ""
        prefixes = [p.strip() for p in prefixes_str.split(",") if p.strip()]

        if "*" in prefixes:
            wildcard_matches.append(sla)
        else:
            for p in prefixes:
                if clean_pincode.startswith(p):
                    prefix_matches.append(sla)
                    break

    # If specific prefix rules match, prioritize them; otherwise use wildcard pan-India fallbacks
    return prefix_matches if prefix_matches else wildcard_matches


# --- SALEOR SYNCHRONOUS WEBHOOK ---

@delivery_bp.route('/webhooks/shipping-methods', methods=['POST'])
def webhook_shipping_methods():
    """
    Saleor Synchronous Webhook: SHIPPING_LIST_METHODS_FOR_CHECKOUT
    Receives cart weight & destination pincode from Saleor checkout.
    Queries local courier_slas, executes weekend/holiday transit math,
    and returns available shipping methods with estimated delivery dates to Saleor.
    """
    payload = request.json or {}
    log.info("Received SHIPPING_LIST_METHODS_FOR_CHECKOUT webhook from Saleor")

    # Extract destination pincode
    checkout = payload.get("checkout") or payload
    shipping_addr = checkout.get("shippingAddress") or {}
    pincode = shipping_addr.get("postalCode") or payload.get("pincode") or "560001"

    # Extract total weight in kg (default 0.5 kg if empty)
    total_weight = 0.5
    lines = checkout.get("lines") or []
    if lines:
        w_sum = 0.0
        for l in lines:
            v_weight = (l.get("variant") or {}).get("weight", {})
            val = v_weight.get("value", 0.0) if isinstance(v_weight, dict) else (v_weight or 0.0)
            qty = l.get("quantity", 1)
            w_sum += float(val) * qty
        if w_sum > 0:
            total_weight = w_sum
    elif payload.get("weight"):
        try:
            total_weight = float(payload["weight"])
        except Exception:
            total_weight = 0.5

    # Match courier SLAs
    matching_slas = find_matching_slas(pincode)
    shipping_methods = []

    for sla in matching_slas:
        # Calculate shipping cost: base_price + extra weight * per_kg_price
        extra_kg = max(0.0, total_weight - 1.0)
        cost = round(sla.base_price + (extra_kg * sla.per_kg_price), 2)

        # Transit & EDD math
        math_res = calculate_transit_and_edd(sla.transit_days, sla.cutoff_hour)

        method_id = f"sla-{sla.id[:8]}-{sla.courier_name.lower().replace(' ', '-')}"
        method_name = f"{sla.courier_name} ({math_res['delivery_window']})"

        shipping_methods.append({
            "id": method_id,
            "name": method_name,
            "amount": cost,
            "currency": "INR",
            "maximum_delivery_days": sla.transit_days + 1,
            "minimum_delivery_days": max(1, sla.transit_days - 1),
            "description": f"Shipped via {sla.zone_name}. Order before {math_res['cutoff_time']} for same-day dispatch."
        })

    return jsonify(shipping_methods)


# --- ESTIMATOR & ADMIN CRUD ENDPOINTS ---

@delivery_bp.route('/delivery/estimate', methods=['GET', 'POST'])
@delivery_bp.route('/admin/delivery/estimate', methods=['GET', 'POST'])
def estimate_delivery():
    """
    Estimator sandbox API: Calculate delivery rates, transit days, and exact EDD
    for any pincode and package weight.
    """
    if request.method == 'POST':
        data = request.json or {}
        pincode = str(data.get("pincode", "")).strip()
        weight = float(data.get("weight", 0.5))
    else:
        pincode = str(request.args.get("pincode", "")).strip()
        weight = float(request.args.get("weight", 0.5))

    if not pincode:
        return jsonify({"success": False, "message": "Pincode is required."}), 400

    matching_slas = find_matching_slas(pincode)
    results = []

    for sla in matching_slas:
        extra_kg = max(0.0, weight - 1.0)
        cost = round(sla.base_price + (extra_kg * sla.per_kg_price), 2)
        transit_info = calculate_transit_and_edd(sla.transit_days, sla.cutoff_hour)

        results.append({
            "sla_id": sla.id,
            "courier_name": sla.courier_name,
            "zone_name": sla.zone_name,
            "transit_days": sla.transit_days,
            "cost": cost,
            "currency": "INR",
            "dispatch_date": transit_info["dispatch_date"],
            "delivery_date": transit_info["delivery_date"],
            "delivery_date_formatted": transit_info["delivery_date_formatted"],
            "delivery_window": transit_info["delivery_window"],
            "is_cutoff_passed": transit_info["is_cutoff_passed"],
            "cutoff_time": transit_info["cutoff_time"],
            "weight_calculated": weight
        })

    # Sort fastest delivery first
    results.sort(key=lambda x: x["transit_days"])

    return jsonify({
        "success": True,
        "pincode": pincode,
        "weight_kg": weight,
        "options_count": len(results),
        "options": results
    })


@delivery_bp.route('/delivery/slas', methods=['GET'])
@delivery_bp.route('/admin/delivery/slas', methods=['GET'])
def list_slas():
    """List all configured Courier SLAs."""
    ensure_default_slas()
    slas = CourierSLA.query.order_by(CourierSLA.zone_name.asc(), CourierSLA.transit_days.asc()).all()
    return jsonify({
        "success": True,
        "count": len(slas),
        "slas": [s.to_dict() for s in slas]
    })


@delivery_bp.route('/delivery/slas', methods=['POST'])
@delivery_bp.route('/admin/delivery/slas', methods=['POST'])
def create_sla():
    """Create a new Courier SLA rule."""
    data = request.json or {}
    courier_name = data.get("courier_name", "").strip()
    zone_name = data.get("zone_name", "").strip()

    if not courier_name or not zone_name:
        return jsonify({"success": False, "message": "courier_name and zone_name are required."}), 400

    sla = CourierSLA(
        courier_name=courier_name,
        zone_name=zone_name,
        pincode_prefixes=data.get("pincode_prefixes", "*").strip(),
        transit_days=int(data.get("transit_days", 2)),
        base_price=float(data.get("base_price", 70.0)),
        per_kg_price=float(data.get("per_kg_price", 25.0)),
        cutoff_hour=int(data.get("cutoff_hour", 14)),
        is_active=bool(data.get("is_active", True))
    )

    db.session.add(sla)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Courier SLA created successfully.",
        "sla": sla.to_dict()
    })


@delivery_bp.route('/delivery/slas/<sla_id>', methods=['PUT', 'POST'])
@delivery_bp.route('/admin/delivery/slas/<sla_id>', methods=['PUT', 'POST'])
def update_sla(sla_id):
    """Update an existing Courier SLA rule."""
    sla = CourierSLA.query.get(sla_id)
    if not sla:
        return jsonify({"success": False, "message": "SLA rule not found."}), 404

    data = request.json or {}
    if "courier_name" in data: sla.courier_name = data["courier_name"].strip()
    if "zone_name" in data: sla.zone_name = data["zone_name"].strip()
    if "pincode_prefixes" in data: sla.pincode_prefixes = data["pincode_prefixes"].strip()
    if "transit_days" in data: sla.transit_days = int(data["transit_days"])
    if "base_price" in data: sla.base_price = float(data["base_price"])
    if "per_kg_price" in data: sla.per_kg_price = float(data["per_kg_price"])
    if "cutoff_hour" in data: sla.cutoff_hour = int(data["cutoff_hour"])
    if "is_active" in data: sla.is_active = bool(data["is_active"])

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Courier SLA updated successfully.",
        "sla": sla.to_dict()
    })


@delivery_bp.route('/delivery/slas/<sla_id>', methods=['DELETE'])
@delivery_bp.route('/admin/delivery/slas/<sla_id>', methods=['DELETE'])
def delete_sla(sla_id):
    """Delete an SLA rule."""
    sla = CourierSLA.query.get(sla_id)
    if not sla:
        return jsonify({"success": False, "message": "SLA rule not found."}), 404

    db.session.delete(sla)
    db.session.commit()

    return jsonify({"success": True, "message": "Courier SLA rule deleted."})


@delivery_bp.route('/delivery/slas/seed-defaults', methods=['POST'])
@delivery_bp.route('/admin/delivery/slas/seed-defaults', methods=['POST'])
def seed_slas():
    """Reset to default SLA rules."""
    CourierSLA.query.delete()
    for rule in DEFAULT_RULES:
        sla = CourierSLA(
            courier_name=rule["courier_name"],
            zone_name=rule["zone_name"],
            pincode_prefixes=rule["pincode_prefixes"],
            transit_days=rule["transit_days"],
            base_price=rule["base_price"],
            per_kg_price=rule["per_kg_price"],
            cutoff_hour=rule["cutoff_hour"],
            is_active=rule["is_active"]
        )
        db.session.add(sla)
    db.session.commit()

    return jsonify({"success": True, "message": f"Seeded {len(DEFAULT_RULES)} default courier SLA rules."})
