import datetime
from flask import Blueprint, request, jsonify
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger
import re

log = get_logger()
dashboard_bp = Blueprint('dashboard', __name__)

FETCH_METRICS_QUERY = """
query GetMetrics($filter: OrderFilterInput!) {
  orders(first: 100, filter: $filter) {
    edges {
      node {
        id
        status
        created
        total {
          gross {
            amount
            currency
          }
        }
      }
    }
  }
}
"""

@dashboard_bp.route('/dashboard/metrics', methods=['GET'])
def get_dashboard_metrics():
    """
    Returns JSON metrics for the dashboard.
    Supports query param 'time_range' (e.g. 1h, 5h, 12h, 1d, 2d, 3d, 7d, 1m, 1y).
    Defaults to 1d.
    """
    time_range = request.args.get("time_range", "1d")
    
    match = re.match(r"^(\d+)([hdmy])$", time_range)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit == 'h':
            delta = datetime.timedelta(hours=value)
        elif unit == 'd':
            delta = datetime.timedelta(days=value)
        elif unit == 'm':
            delta = datetime.timedelta(days=value * 30)
        elif unit == 'y':
            delta = datetime.timedelta(days=value * 365)
        else:
            delta = datetime.timedelta(days=1)
    else:
        # Fallback to 1 day if invalid
        delta = datetime.timedelta(days=1)

    past_time = datetime.datetime.now(datetime.timezone.utc) - delta
    
    # Saleor v3 'created' filter expects a Date (YYYY-MM-DD), not ISO datetime
    filter_input = {
        "created": {"gte": past_time.strftime("%Y-%m-%d")}
    }
    
    variables = {"filter": filter_input}
    result = execute_graphql(FETCH_METRICS_QUERY, variables)
    
    if result["error"]:
        log.error(f"Failed to fetch metrics: {result['error']}")
        return jsonify({"success": False, "message": "Failed to connect to Saleor API"}), 500
        
    orders = result["data"].get("orders", {}).get("edges", [])
    
    metrics = {
        "total_revenue": 0.0,
        "currency": "INR", # Assuming INR or getting from first order
        "total_orders": 0,
        "pending": 0,
        "shipped": 0,
        "returned": 0,
        "other": 0,
        "time_series": {}
    }
    
    # Pre-determine grouping strategy based on time range
    # e.g., '1h' -> group by minute? Let's just do hour for anything > 1d, otherwise by day
    # To keep it simple: 
    # 'h' -> by hour (e.g. "12:00")
    # 'd' -> by hour if value==1 else by day
    # 'm' -> by day
    # 'y' -> by month
    
    for edge in orders:
        node = edge["node"]
        
        # Exact time filter: drop orders that are on the correct date but older than our exact 'past_time' hour
        order_time = datetime.datetime.fromisoformat(node["created"].replace("Z", "+00:00"))
        if order_time < past_time:
            continue
            
        metrics["total_orders"] += 1
        status = node["status"]
        amount = node["total"]["gross"]["amount"]
        currency = node["total"]["gross"]["currency"]
        
        metrics["currency"] = currency
        metrics["total_revenue"] += amount
        
        if status == "UNFULFILLED":
            metrics["pending"] += 1
        elif status == "FULFILLED":
            metrics["shipped"] += 1
        elif status == "RETURNED":
            metrics["returned"] += 1
        else:
            metrics["other"] += 1
            
        # Grouping logic
        if match:
            unit = match.group(2)
            val = int(match.group(1))
            if unit == 'h' or (unit == 'd' and val == 1):
                group_key = order_time.strftime("%H:00")
            elif unit == 'd' or unit == 'm':
                group_key = order_time.strftime("%b %d")
            elif unit == 'y':
                group_key = order_time.strftime("%b %Y")
            else:
                group_key = order_time.strftime("%b %d")
        else:
            group_key = order_time.strftime("%H:00")

        if group_key not in metrics["time_series"]:
            metrics["time_series"][group_key] = {"revenue": 0, "orders": 0}
            
        metrics["time_series"][group_key]["revenue"] += amount
        metrics["time_series"][group_key]["orders"] += 1

    # Round revenue
    metrics["total_revenue"] = round(metrics["total_revenue"], 2)

    return jsonify({
        "success": True,
        "data": metrics
    })
