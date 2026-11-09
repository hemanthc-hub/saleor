import datetime
import jwt
import os
from flask import Blueprint, request, jsonify, current_app
from admin_ops.database import db, ProductReview
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger

log = get_logger()
reviews_bp = Blueprint('reviews', __name__)

# Replace with your actual secret key or load from env
JWT_SECRET = os.environ.get("FLASK_SECRET_KEY", "super-secure-hegma-key-1234")

# Saleor GraphQL query to check if order is fulfilled and contains the product
CHECK_ORDER_QUERY = """
query CheckOrder($id: ID!) {
  order(id: $id) {
    status
    lines {
      productSku
      variant { product { id } }
    }
    fulfillments {
      created
    }
  }
}
"""

@reviews_bp.route('/reviews/<product_id>', methods=['GET'])
def get_public_reviews(product_id):
    """Public endpoint to fetch approved reviews for a product."""
    reviews = ProductReview.query.filter_by(product_id=product_id, is_approved=True).order_by(ProductReview.created_at.desc()).all()
    
    avg_rating = 0
    if reviews:
        avg_rating = sum(r.rating for r in reviews) / len(reviews)
        
    return jsonify({
        "success": True,
        "count": len(reviews),
        "average_rating": round(avg_rating, 1),
        "reviews": [r.to_dict() for r in reviews]
    })


@reviews_bp.route('/reviews/submit', methods=['POST'])
def submit_review():
    """Public endpoint where a user submits a review using a secure JWT token."""
    data = request.json
    token = data.get("token")
    rating = data.get("rating")
    comment = data.get("comment", "")
    display_name = data.get("display_name", "Anonymous")
    
    if not token or not rating:
        return jsonify({"success": False, "message": "Token and rating are required."}), 400
        
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return jsonify({"success": False, "message": "Rating must be between 1 and 5."}), 400
    except ValueError:
        return jsonify({"success": False, "message": "Invalid rating."}), 400

    # 1. Decode JWT Token
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        order_id = payload["order_id"]
        product_id = payload["product_id"]
    except jwt.ExpiredSignatureError:
        return jsonify({"success": False, "message": "This review link has expired."}), 400
    except jwt.InvalidTokenError:
        return jsonify({"success": False, "message": "Invalid review link."}), 400
        
    # Check if review already exists
    existing = ProductReview.query.filter_by(order_id=order_id, product_id=product_id).first()
    if existing:
        return jsonify({"success": False, "message": "You have already reviewed this product for this order."}), 400

    # 2. Verify with Saleor (Order Status must be FULFILLED)
    variables = {"id": order_id}
    res = execute_graphql(CHECK_ORDER_QUERY, variables)
    
    if res.get("error") or not res.get("data", {}).get("order"):
        return jsonify({"success": False, "message": "Failed to verify order with the store."}), 500
        
    order_data = res["data"]["order"]
    
    if order_data["status"] not in ["FULFILLED", "PARTIALLY_FULFILLED"]:
        return jsonify({"success": False, "message": f"You can only review delivered products. Order is currently {order_data['status']}."}), 400
        
    # Verify product is actually in the order
    found_product = False
    for line in order_data.get("lines", []):
        variant = line.get("variant")
        if variant and variant.get("product") and variant["product"]["id"] == product_id:
            found_product = True
            break
            
    if not found_product:
        return jsonify({"success": False, "message": "This product was not found in your order."}), 400
        
    # Get delivery date (earliest fulfillment date)
    delivery_date = None
    if order_data.get("fulfillments"):
        try:
            date_str = order_data["fulfillments"][0]["created"]
            delivery_date = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception as e:
            log.warning(f"Could not parse delivery date: {e}")
            
    # 3. Save to DB
    new_review = ProductReview(
        product_id=product_id,
        order_id=order_id,
        rating=rating,
        comment=comment,
        display_name=display_name,
        delivery_date=delivery_date
    )
    
    db.session.add(new_review)
    db.session.commit()
    
    log.info(f"Verified review saved for Product {product_id} from Order {order_id}.")
    
    return jsonify({
        "success": True, 
        "message": "Review submitted successfully!",
        "review": new_review.to_dict()
    })


# --- ADMIN ONLY ROUTES ---

@reviews_bp.route('/admin/reviews', methods=['GET'])
def admin_get_reviews():
    """Admin endpoint to view all reviews."""
    # In a real app, check admin JWT here.
    reviews = ProductReview.query.order_by(ProductReview.created_at.desc()).all()
    return jsonify({
        "success": True,
        "count": len(reviews),
        "reviews": [r.to_dict() for r in reviews]
    })


@reviews_bp.route('/admin/reviews/<review_id>/toggle', methods=['POST'])
def admin_toggle_review(review_id):
    """Admin endpoint to approve/hide a review."""
    review = ProductReview.query.get(review_id)
    if not review:
        return jsonify({"success": False, "message": "Review not found."}), 404
        
    review.is_approved = not review.is_approved
    db.session.commit()
    
    return jsonify({"success": True, "is_approved": review.is_approved})


@reviews_bp.route('/admin/reviews/generate-link', methods=['POST'])
def admin_generate_link():
    """Admin endpoint to manually generate a secure review link for a user."""
    data = request.json
    order_id = data.get("order_id")
    product_id = data.get("product_id")
    
    if not order_id or not product_id:
        return jsonify({"success": False, "message": "order_id and product_id required"}), 400
        
    # Create token valid for 30 days
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    payload = {
        "order_id": order_id,
        "product_id": product_id,
        "exp": exp
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    link = f"https://hegmakart.com/write-review?token={token}"
    
    return jsonify({
        "success": True,
        "token": token,
        "link": link
    })
