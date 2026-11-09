import re
from flask import Blueprint, request, jsonify
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger

log = get_logger()
related_bp = Blueprint('related', __name__)

DEFAULT_CHANNEL = "default-channel"

# --- GRAPHQL QUERIES & MUTATIONS ---

SEARCH_PRODUCTS_QUERY = """
query SearchProducts($search: String!, $channel: String!) {
  products(first: 20, channel: $channel, filter: { search: $search }) {
    edges {
      node {
        id
        name
        thumbnail { url }
        metadata { key value }
        variants {
          id
          sku
          name
        }
      }
    }
  }
}
"""

LIST_PRODUCTS_QUERY = """
query ListProducts($channel: String!) {
  products(first: 20, channel: $channel) {
    edges {
      node {
        id
        name
        thumbnail { url }
        metadata { key value }
        variants {
          id
          sku
          name
        }
      }
    }
  }
}
"""

GET_PRODUCT_BY_ID_QUERY = """
query GetProductDetails($id: ID!, $channel: String!) {
  product(id: $id, channel: $channel) {
    id
    name
    thumbnail { url }
    metadata { key value }
    variants {
      id
      sku
      name
    }
  }
}
"""

RESOLVE_VARIANTS_BY_SKUS = """
query ResolveVariants($skus: [String!], $channel: String!) {
  productVariants(first: 50, filter: { sku: $skus }, channel: $channel) {
    edges {
      node {
        id
        sku
        name
        pricing {
          price { gross { amount currency } }
        }
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

UPDATE_PRODUCT_METADATA_MUTATION = """
mutation UpdateProductMetadata($id: ID!, $input: [MetadataInput!]!) {
  updateMetadata(id: $id, input: $input) {
    errors { field message }
    item {
      ... on Product {
        id
        metadata { key value }
      }
    }
  }
}
"""

def extract_related_skus(metadata):
    """Extracts related SKUs list from product metadata."""
    if not metadata:
        return []
    for item in metadata:
        if item.get("key") == "related_skus":
            val = item.get("value", "")
            if not val:
                return []
            raw_skus = re.split(r'[,;\n]+', val)
            return [s.strip() for s in raw_skus if s.strip()]
    return []

def resolve_skus_to_items(skus, channel=DEFAULT_CHANNEL):
    """Resolves a list of SKU strings to rich product variant data."""
    if not skus:
        return []
    res = execute_graphql(RESOLVE_VARIANTS_BY_SKUS, {"skus": skus, "channel": channel})
    if res.get("error"):
        log.warning(f"Error resolving SKUs {skus}: {res['error']}")
        return [{"sku": s, "product_name": s, "variant_name": "", "thumbnail": None, "price": None, "currency": "INR"} for s in skus]
    
    edges = res.get("data", {}).get("productVariants", {}).get("edges", [])
    resolved = []
    found_skus = set()
    for edge in edges:
        node = edge.get("node", {})
        sku = node.get("sku", "")
        found_skus.add(sku)
        product = node.get("product") or {}
        price_obj = node.get("pricing", {}).get("price", {}).get("gross", {}) if node.get("pricing") else {}
        resolved.append({
            "variant_id": node.get("id"),
            "sku": sku,
            "variant_name": node.get("name"),
            "product_id": product.get("id"),
            "product_name": product.get("name"),
            "thumbnail": product.get("thumbnail", {}).get("url") if product.get("thumbnail") else None,
            "price": price_obj.get("amount"),
            "currency": price_obj.get("currency", "INR")
        })
    
    for s in skus:
        if s not in found_skus:
            resolved.append({
                "variant_id": None,
                "sku": s,
                "variant_name": "",
                "product_id": None,
                "product_name": f"Unmatched SKU: {s}",
                "thumbnail": None,
                "price": None,
                "currency": "INR"
            })
            
    return resolved


@related_bp.route('/related/search', methods=['GET'])
def search_products():
    """Search products by name or SKU to view or manage their cross-sells."""
    search_term = request.args.get("q", "").strip()
    channel = request.args.get("channel", DEFAULT_CHANNEL)
    
    if search_term:
        res = execute_graphql(SEARCH_PRODUCTS_QUERY, {"search": search_term, "channel": channel})
    else:
        res = execute_graphql(LIST_PRODUCTS_QUERY, {"channel": channel})
        
    if res.get("error"):
        return jsonify({"success": False, "message": str(res["error"])}), 500
        
    edges = res.get("data", {}).get("products", {}).get("edges", [])
    products = []
    for edge in edges:
        node = edge.get("node", {})
        metadata = node.get("metadata", [])
        skus_list = [v["sku"] for v in node.get("variants", []) if v.get("sku")]
        related_skus = extract_related_skus(metadata)
        products.append({
            "id": node.get("id"),
            "name": node.get("name"),
            "thumbnail": node.get("thumbnail", {}).get("url") if node.get("thumbnail") else None,
            "skus": skus_list,
            "primary_sku": skus_list[0] if skus_list else "",
            "related_skus": related_skus,
            "related_count": len(related_skus)
        })
        
    return jsonify({"success": True, "products": products})


@related_bp.route('/related/details/<product_id>', methods=['GET'])
def get_product_related_details(product_id):
    """Fetch product details and its resolved related products."""
    channel = request.args.get("channel", DEFAULT_CHANNEL)
    res = execute_graphql(GET_PRODUCT_BY_ID_QUERY, {"id": product_id, "channel": channel})
    
    if res.get("error"):
        return jsonify({"success": False, "message": str(res["error"])}), 500
        
    product = res.get("data", {}).get("product")
    if not product:
        return jsonify({"success": False, "message": "Product not found"}), 404
        
    metadata = product.get("metadata", [])
    related_skus = extract_related_skus(metadata)
    skus_list = [v["sku"] for v in product.get("variants", []) if v.get("sku")]
    
    resolved_items = resolve_skus_to_items(related_skus, channel=channel)
    
    return jsonify({
        "success": True,
        "product": {
            "id": product.get("id"),
            "name": product.get("name"),
            "thumbnail": product.get("thumbnail", {}).get("url") if product.get("thumbnail") else None,
            "skus": skus_list,
            "primary_sku": skus_list[0] if skus_list else "",
            "related_skus": related_skus,
            "related_items": resolved_items
        }
    })


@related_bp.route('/related/update', methods=['POST'])
def update_related_products():
    """Update related SKUs for a product."""
    data = request.json or {}
    product_id = data.get("product_id")
    raw_related = data.get("related_skus", [])
    
    if not product_id:
        return jsonify({"success": False, "message": "product_id is required"}), 400
        
    if isinstance(raw_related, str):
        cleaned_skus = [s.strip() for s in re.split(r'[,;\n]+', raw_related) if s.strip()]
    elif isinstance(raw_related, list):
        cleaned_skus = [str(s).strip() for s in raw_related if str(s).strip()]
    else:
        cleaned_skus = []
        
    skus_string = ", ".join(cleaned_skus)
    
    variables = {
        "id": product_id,
        "input": [{"key": "related_skus", "value": skus_string}]
    }
    
    res = execute_graphql(UPDATE_PRODUCT_METADATA_MUTATION, variables)
    if res.get("error") or res.get("data", {}).get("updateMetadata", {}).get("errors"):
        err = res.get("error") or res.get("data", {}).get("updateMetadata", {}).get("errors")
        return jsonify({"success": False, "message": f"Saleor error: {err}"}), 500
        
    return jsonify({
        "success": True,
        "message": f"Successfully updated related products for product {product_id}.",
        "related_skus": cleaned_skus
    })


@related_bp.route('/related/public/<product_id>', methods=['GET'])
def get_public_related_products(product_id):
    """
    Public storefront endpoint to fetch resolved related items for display
    on the product details page carousel.
    """
    channel = request.args.get("channel", DEFAULT_CHANNEL)
    res = execute_graphql(GET_PRODUCT_BY_ID_QUERY, {"id": product_id, "channel": channel})
    
    if res.get("error") or not res.get("data", {}).get("product"):
        return jsonify({"success": False, "items": []}), 404
        
    product = res["data"]["product"]
    related_skus = extract_related_skus(product.get("metadata", []))
    items = resolve_skus_to_items(related_skus, channel=channel)
    
    return jsonify({
        "success": True,
        "product_id": product_id,
        "count": len(items),
        "related_items": items
    })
