# Comprehensive Master Plan: Flask Standalone Operations for Saleor

## The "Decoupled" Philosophy
We are using a **Standalone Flask Application** (Backend-for-Frontend) inside your existing `/Hegma/backend` repository. By keeping Flask completely separate from the Saleor Django backend, you guarantee **Zero Upgrade Hurdles**. 

---

## Execution Runbook (Git Safety & Scaffolding)
Before writing code, run these commands to secure your existing work and scaffold the isolated `admin_ops` module:

```bash
# 1. Save existing changes and branch out
git add .
git commit -m "chore: save local changes before adding saleor ops"
git checkout -b feature/saleor-ops-microservices

# 2. Scaffold the isolated Flask Blueprint
mkdir -p admin_ops/routes admin_ops/services admin_ops/templates
touch admin_ops/__init__.py admin_ops/routes/__init__.py admin_ops/services/__init__.py
```

---

## 9 Custom Features & Executable Prompts
You can choose and pick which of these features you want to build. Copy the "Executable Prompt" for a feature and paste it to the AI to execute it.

### 1. Order Management & Multiple Couriers
**Goal:** Export unfulfilled orders, generate courier-specific CSVs, and import tracking numbers to fulfill orders in Saleor.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/orders.py`. Write a Flask Blueprint that exposes `GET /api/orders/export` and `POST /api/orders/import`. Write the GraphQL client logic in `services/graphql_client.py` to fetch `UNFULFILLED` orders and execute `orderFulfill` mutations. Register this blueprint in the main `api.py`."

### 2. Executive Dashboard
**Goal:** A secure HTML/Jinja2 view of daily revenue and KPIs.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/dashboard.py`. Write a Flask route `GET /dashboard` that queries Saleor for today's orders and revenue. Create `admin_ops/templates/dashboard.html` using Tailwind CSS and Chart.js to display the metrics."

### 3. Catalog Sync
**Goal:** Upload a master CSV template to update prices and stock.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/catalog.py`. Write a Flask route `POST /api/catalog/sync` that accepts a CSV upload. Parse the CSV and execute Saleor `productUpdate` GraphQL mutations for each row."

### 4. Tracking Export
**Goal:** Generate a CSV file with tracking URLs for orders shipped today.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/tracking.py`. Write a Flask route `GET /api/tracking/export/today` that queries Saleor for fulfillments created today, converts it to CSV in-memory, and returns it as a downloadable file."

### 5. Verified Product Reviews
**Goal:** Flask DB saves reviews after GraphQL verification of delivery.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/reviews.py`. Write a Flask route `POST /api/reviews/submit` that accepts an order_id. Verify via Saleor GraphQL that the order is `FULFILLED`, extract the delivery date, and save the review to a SQLAlchemy `product_reviews` table."

### 6. Related Products
**Goal:** Next.js reads `Metadata: related_skus` to fetch cross-sells.
> **Executable Prompt:**
> "No backend code needed. The catalogue team adds a `Metadata: related_skus` column in the CSV (Feature 3). Instruct the Next.js frontend team to fetch this metadata and run a GraphQL query to display related products."

### 7. Dynamic Delivery Estimator
**Goal:** Synchronous Saleor Webhooks ping Flask for courier SLAs.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/delivery.py`. Write an endpoint `POST /api/webhooks/shipping-methods`. Receive the cart weight/pincode payload from Saleor. Query a local `courier_slas` table, calculate transit dates using weekend/holiday math, and return the JSON shipping options to Saleor."

### 8. Transactional Emails
**Goal:** Flask listens for `ORDER_CREATED` webhooks to send HTML emails.
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/emails.py`. Write a webhook endpoint `POST /api/webhooks/order-created`. Parse the Saleor payload, generate an HTML receipt using Jinja2, and send it via `Flask-Mail`."

### 9. Advanced Payment Fallback
**Goal:** Synchronous Webhooks route logic (Razorpay -> Secondary -> COD).
> **Executable Prompt:**
> "Create `/Hegma/backend/admin_ops/routes/payments.py`. Write an endpoint `POST /api/webhooks/payment-gateways`. Implement a ping to check if Razorpay is alive. If not, fallback to Secondary. If both down, check cart value/pincode preconditions and return `['Cash On Delivery']` or an empty list."
