import csv
import io
import time
import json
import threading
from flask import Blueprint, request, jsonify
from admin_ops.services.graphql_client import execute_graphql
from logger import get_logger

log = get_logger()
catalog_bp = Blueprint('catalog', __name__)

GET_VARIANT_BY_SKU = """
query GetVariantBySKU($sku: String!, $channel: String!) {
  productVariants(first: 1, filter: {sku: $sku}) {
    edges {
      node {
        id
        name
        product {
          id
          name
          taxClass { name }
          channelListings {
            channel { slug }
            isPublished
          }
        }
        pricing {
          price { gross { amount } }
        }
        quantityAvailable
      }
    }
  }
}
"""

GET_CHANNELS_WAREHOUSES = """
query {
  channels { id slug }
  warehouses(first: 1) { edges { node { id } } }
}
"""

# Fetchers for Creation
GET_PRODUCT_TYPE = """
query GetProductType($slug: String!) {
  productTypes(first: 1, filter: {search: $slug}) {
    edges { node { id } }
  }
}
"""

GET_CATEGORY = """
query GetCategory($slug: String!) {
  categories(first: 1, filter: {search: $slug}) {
    edges { node { id } }
  }
}
"""

CREATE_PRODUCT = """
mutation CreateProduct($input: ProductCreateInput!) {
  productCreate(input: $input) {
    product { id }
    errors { field message }
  }
}
"""

CREATE_VARIANT = """
mutation CreateVariant($input: ProductVariantCreateInput!) {
  productVariantCreate(input: $input) {
    productVariant { id }
    errors { field message }
  }
}
"""

UPDATE_PRODUCT = """
mutation UpdateProduct($id: ID!, $input: ProductInput!) {
  productUpdate(id: $id, input: $input) { errors { field message } }
}
"""

UPDATE_VARIANT = """
mutation UpdateVariant($id: ID!, $input: ProductVariantInput!) {
  productVariantUpdate(id: $id, input: $input) { errors { field message } }
}
"""

UPDATE_CHANNEL_LISTING = """
mutation UpdateChannelListing($id: ID!, $channelId: ID!, $price: PositiveDecimal, $isPublished: Boolean) {
  productVariantChannelListingUpdate(id: $id, input: { channelId: $channelId, price: $price }) { errors { field message } }
  productChannelListingUpdate(id: $id, input: { updateChannels: [{ channelId: $channelId, isPublished: $isPublished }] }) { errors { field message } }
}
"""

UPDATE_STOCK = """
mutation UpdateStock($variantId: ID!, $warehouseId: ID!, $quantity: Int!) {
  productVariantStocksUpdate(variantId: $variantId, stocks: [{ warehouse: $warehouseId, quantity: $quantity }]) { errors { field message } }
}
"""

UPDATE_METADATA = """
mutation UpdateMetadata($id: ID!, $input: [MetadataInput!]!) {
  updateMetadata(id: $id, input: $input) { errors { field message } }
}
"""

CREATE_MEDIA = """
mutation CreateMedia($product: ID!, $mediaUrl: String!) {
  productMediaCreate(product: $product, input: { alt: "Image", mediaUrl: $mediaUrl }) { errors { field message } }
}
"""

active_jobs = {}

def process_catalog_batch(app, job_id, rows, channel_id, channel_slug, warehouse_id):
    success_count = 0
    skipped_count = 0
    error_count = 0
    errors = []
    
    active_jobs[job_id]["status"] = "processing"
    
    for row in rows:
        sku = row.get("SKU", "").strip()
        if not sku: continue
        
        log.info(f"[Job {job_id}] Processing SKU: {sku}")
        
        # 1. Fetch Current State
        variant_res = execute_graphql(GET_VARIANT_BY_SKU, {"sku": sku, "channel": channel_slug})
        edges = variant_res.get("data", {}).get("productVariants", {}).get("edges", [])
        
        row_errors = []
        mutations_fired = 0
        product_id = None
        variant_id = None
        
        is_new_product = False
        
        if not edges:
            # --- CREATION FORK ---
            is_new_product = True
            log.info(f"[Job {job_id}] SKU {sku} not found. Attempting CREATE.")
            
            p_type_slug = row.get("ProductType", "").strip()
            cat_slug = row.get("Category", "").strip()
            
            if not p_type_slug or not cat_slug:
                error_count += 1
                errors.append(f"SKU {sku}: Cannot create without ProductType and Category")
                continue
                
            pt_res = execute_graphql(GET_PRODUCT_TYPE, {"slug": p_type_slug})
            pt_edges = pt_res.get("data", {}).get("productTypes", {}).get("edges", [])
            if not pt_edges:
                error_count += 1
                errors.append(f"SKU {sku}: ProductType '{p_type_slug}' not found")
                continue
            product_type_id = pt_edges[0]["node"]["id"]
            
            cat_res = execute_graphql(GET_CATEGORY, {"slug": cat_slug})
            cat_edges = cat_res.get("data", {}).get("categories", {}).get("edges", [])
            if not cat_edges:
                error_count += 1
                errors.append(f"SKU {sku}: Category '{cat_slug}' not found")
                continue
            category_id = cat_edges[0]["node"]["id"]
            
            # Extract Attributes
            attributes = []
            for k, v in row.items():
                if k.startswith("Attribute:") and v.strip():
                    attr_slug = k.split("Attribute:")[1].strip()
                    # A proper PIM sync maps values to IDs here, but for simplicity we rely on string matching if Saleor supports it,
                    # or skip for now if it requires rigid IDs. Saleor requires IDs for attribute values. 
                    # We will push them via bulk string matching if allowed, else skip.
                    
            # Create Product
            prod_input = {
                "productType": product_type_id,
                "category": category_id,
                "name": row.get("ProductName", sku).strip()
            }
            if row.get("TaxClass"): prod_input["taxClass"] = row.get("TaxClass").strip()
            
            c_prod = execute_graphql(CREATE_PRODUCT, {"input": prod_input})
            if c_prod.get("error") or c_prod["data"]["productCreate"]["errors"]:
                error_count += 1
                errors.append(f"SKU {sku}: productCreate failed")
                continue
            product_id = c_prod["data"]["productCreate"]["product"]["id"]
            mutations_fired += 1
            
            # Create Variant
            var_input = {
                "product": product_id,
                "sku": sku,
                "name": row.get("VariantName", sku).strip()
            }
            c_var = execute_graphql(CREATE_VARIANT, {"input": var_input})
            if c_var.get("error") or c_var["data"]["productVariantCreate"]["errors"]:
                error_count += 1
                errors.append(f"SKU {sku}: productVariantCreate failed")
                continue
            variant_id = c_var["data"]["productVariantCreate"]["productVariant"]["id"]
            mutations_fired += 1
            
        else:
            # --- UPDATE FORK ---
            variant_node = edges[0]["node"]
            product_node = variant_node["product"]
            variant_id = variant_node["id"]
            product_id = product_node["id"]
            
            curr_var_name = variant_node.get("name", "")
            curr_prod_name = product_node.get("name", "")
            curr_tax = product_node.get("taxClass", {}).get("name", "") if product_node.get("taxClass") else ""
            
            prod_input = {}
            row_prod_name = row.get("ProductName", "").strip()
            if row_prod_name and row_prod_name != curr_prod_name: prod_input["name"] = row_prod_name
            row_tax = row.get("TaxClass", "").strip()
            if row_tax and row_tax != curr_tax: prod_input["taxClass"] = row_tax
                
            if prod_input:
                p_res = execute_graphql(UPDATE_PRODUCT, {"id": product_id, "input": prod_input})
                if p_res.get("error") or p_res["data"]["productUpdate"]["errors"]: row_errors.append("Product update failed")
                mutations_fired += 1
                
            var_input = {}
            row_var_name = row.get("VariantName", "").strip()
            if row_var_name and row_var_name != curr_var_name: var_input["name"] = row_var_name
            if var_input:
                v_res = execute_graphql(UPDATE_VARIANT, {"id": variant_id, "input": var_input})
                if v_res.get("error") or v_res["data"]["productVariantUpdate"]["errors"]: row_errors.append("Variant update failed")
                mutations_fired += 1
                
        # --- COMMON UPDATES (PRICE, STOCK, MEDIA, METADATA) ---
        
        # Channel Listing
        price_str = row.get("Price", "").strip()
        new_price = float(price_str) if price_str else None
        
        pub_str = row.get("IsPublished", "").strip().lower()
        new_published = True if pub_str in ['true', '1', 'yes'] else False if pub_str in ['false', '0', 'no'] else None
        
        curr_price, curr_published = None, True
        if not is_new_product:
            if variant_node.get("pricing") and variant_node["pricing"].get("price"):
                curr_price = variant_node["pricing"]["price"]["gross"]["amount"]
            for listing in product_node.get("channelListings", []):
                if listing["channel"]["slug"] == channel_slug:
                    curr_published = listing["isPublished"]
                    break
        
        price_changed = (new_price is not None and new_price != curr_price)
        pub_changed = (new_published is not None and new_published != curr_published)
        
        if channel_id and (is_new_product or price_changed or pub_changed):
            pr_res = execute_graphql(UPDATE_CHANNEL_LISTING, {
                "id": variant_id, 
                "channelId": channel_id, 
                "price": new_price if price_changed or is_new_product else curr_price,
                "isPublished": new_published if pub_changed or is_new_product else curr_published
            })
            if pr_res.get("error"): row_errors.append("Channel listing failed")
            mutations_fired += 1
            
        # Stock
        stock_str = row.get("Stock", "").strip()
        if stock_str and warehouse_id:
            try:
                stock_val = int(stock_str)
                curr_stock = 0 if is_new_product else variant_node.get("quantityAvailable", 0)
                if stock_val != curr_stock:
                    st_res = execute_graphql(UPDATE_STOCK, {"variantId": variant_id, "warehouseId": warehouse_id, "quantity": stock_val})
                    if st_res.get("error"): row_errors.append("Stock update failed")
                    mutations_fired += 1
            except ValueError:
                row_errors.append("Invalid stock")

        # Media
        media_url = row.get("ImageURL", "").strip()
        if media_url:
            # We blindly add the media URL. In a true diff, we'd check if it already exists.
            m_res = execute_graphql(CREATE_MEDIA, {"product": product_id, "mediaUrl": media_url})
            if m_res.get("error") or m_res["data"]["productMediaCreate"]["errors"]:
                row_errors.append("Media create failed")
            mutations_fired += 1

        # Metadata
        meta_items = []
        if row.get("Brand", "").strip(): meta_items.append({"key": "brand", "value": row.get("Brand").strip()})
        if row.get("WeightedOfferPrice", "").strip(): meta_items.append({"key": "weighted_offer_price", "value": row.get("WeightedOfferPrice").strip()})
        if row.get("Discount", "").strip(): meta_items.append({"key": "discount", "value": row.get("Discount").strip()})
        if row.get("RelatedSKUs", "").strip(): meta_items.append({"key": "related_skus", "value": row.get("RelatedSKUs").strip()})
            
        meta_str = row.get("Metadata", "").strip()
        if meta_str:
            try:
                meta_dict = json.loads(meta_str)
                for k, v in meta_dict.items(): meta_items.append({"key": str(k), "value": str(v)})
            except: row_errors.append("Invalid JSON Metadata")
                
        if meta_items:
            # In a true diff, we'd check existing metadata.
            md_res = execute_graphql(UPDATE_METADATA, {"id": product_id, "input": meta_items})
            if md_res.get("error") or md_res["data"]["updateMetadata"]["errors"]: row_errors.append("Metadata failed")
            mutations_fired += 1
        
        if mutations_fired == 0:
            skipped_count += 1
        elif row_errors:
            error_count += 1
            errors.append(f"SKU {sku} errors: {', '.join(row_errors)}")
        else:
            success_count += 1
            
        time.sleep(0.1)

    active_jobs[job_id].update({"status": "completed", "success_count": success_count, "skipped_count": skipped_count, "error_count": error_count, "errors": errors})
    
    # Save Audit Log
    try:
        from flask import current_app
        from admin_ops.database import db, AuditLog
        with app.app_context():
            audit = AuditLog(
                action_type="PIM_CATALOG_SYNC",
                status="COMPLETED_WITH_ERRORS" if error_count > 0 else "SUCCESS",
                records_processed=success_count + skipped_count,
                records_failed=error_count,
                error_details=json.dumps(errors) if errors else None
            )
            db.session.add(audit)
            db.session.commit()
    except Exception as e:
        log.error(f"Failed to save audit log: {e}")


@catalog_bp.route('/catalog/sync', methods=['POST'])
def sync_catalog():
    from flask import current_app
    app = current_app._get_current_object()
    
    if 'file' not in request.files: return jsonify({"success": False, "message": "No file part"}), 400
    file = request.files['file']
    if not file or not file.filename.endswith('.csv'): return jsonify({"success": False, "message": "Invalid CSV file"}), 400

    env_res = execute_graphql(GET_CHANNELS_WAREHOUSES, {})
    channels = env_res.get("data", {}).get("channels", [])
    channel_id = channels[0]["id"] if channels else None
    channel_slug = channels[0]["slug"] if channels else "default-channel"
    wh_edges = env_res.get("data", {}).get("warehouses", {}).get("edges", [])
    warehouse_id = wh_edges[0]["node"]["id"] if wh_edges else None
    
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    rows = list(csv.DictReader(stream))
    if not rows: return jsonify({"success": False, "message": "CSV is empty"}), 400

    job_id = str(int(time.time()))
    active_jobs[job_id] = {"status": "starting", "total": len(rows), "success_count": 0, "skipped_count": 0, "error_count": 0, "errors": []}
    
    thread = threading.Thread(target=process_catalog_batch, args=(app, job_id, rows, channel_id, channel_slug, warehouse_id))
    thread.start()

    return jsonify({"success": True, "message": "Batch PIM Sync queued", "job_id": job_id})

@catalog_bp.route('/catalog/sync/status/<job_id>', methods=['GET'])
def sync_status(job_id):
    job = active_jobs.get(job_id)
    return jsonify({"success": True, "data": job}) if job else (jsonify({"success": False, "message": "Job not found"}), 404)
