# HegmaKart Operations Microservices — Setup Guide

> **Purpose**: Standalone guide for running the Hegma Flask Operations Microservices (`admin_ops`) and Next.js Operations Command Center locally.
> Existing legacy documentation is preserved in `LOCAL_SETUP.md`.

---

## 🏗️ Architecture

```text
Next.js Operations Dashboard (Port 3000)
    │
    ├─► REST API calls ──► Flask Operations API (Port 5000)
    │                             │
    │                             ├─► Saleor Core Django GraphQL (Port 8000)
    │                             │
    │                             └─► PostgreSQL `dev_hegma` (Port 5432)
```

---

## 📋 Prerequisites
- **Python**: 3.9+
- **PostgreSQL**: Running on port `5432` with database `dev_hegma`
- **Saleor Core**: Running on port `8000` (`http://localhost:8000/graphql/`)

---

## 🐍 Step 1: Python Environment & Dependencies

```bash
cd backend

# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate       # On Windows: .\venv\Scripts\Activate.ps1

# 2. Install all dependencies (pinned for stability)
pip install --upgrade pip
pip install -r requirements.txt
```

### Key dependencies in `requirements.txt`:
- `Flask==2.0.2` & `Werkzeug==2.3.8` (Pinned for legacy route compatibility)
- `Flask-SQLAlchemy>=2.5.1` (ORM for operations tables)
- `PyJWT>=2.8.0` (Cryptographically signed review tokens)
- `requests>=2.28.0` (GraphQL client communication with Saleor)
- `setuptools==80.10.2` (Prevents setuptools 82+ deprecation breaks)
- `loguru==0.7.3` (Structured logging to stdout & `logs/flask_app.log`)

---

## ⚙️ Step 2: Environment Configuration

Copy the example environment file:
```bash
cp .env.example .env
```

Ensure your `.env` contains:
```ini
FLASK_ENV=development
SECRET_KEY=hegma_dev_secret_key_123
DEBUG=True
PORT=5000
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL connection
DB_NAME=dev_hegma
DB_USER_NAME=postgres
DB_PASSWORD=your_local_password
DB_HOST=localhost
DB_PORT=5432

# Saleor GraphQL connection
GRAPHQL_API_URL=http://localhost:8000/graphql/
HEGMA_AUTH_TOKEN="Bearer YOUR_SALEOR_APP_TOKEN"
FLASK_SECRET_KEY=hegma-secure-review-signing-key
```

---

## 🗄️ Step 3: Database Tables

The operations microservices use 4 dedicated tables in `dev_hegma` (managed via `admin_ops/database.py`):
1. `product_reviews`: Verified customer ratings and reviews.
2. `audit_logs`: Detailed operational audit trail.
3. `email_logs`: Transactional email delivery history.
4. `courier_slas`: Indian courier transit rules (Bluedart, Delhivery, DTDC, etc.).

These tables are created automatically on first run via SQLAlchemy, or you can verify them in PostgreSQL:
```bash
psql -U postgres -d dev_hegma -c "\dt"
```

---

## 🚀 Step 4: Start the Flask API Server

```bash
python api.py
```
Server runs on **`http://localhost:5000`**.

> [!TIP]
> **Port 5000 Already in Use on macOS?**
> macOS uses port 5000 for AirPlay Receiver by default. To disable:
> Open **System Settings** → **General** → **AirDrop & AirPlay** → Turn **AirPlay Receiver** to **Off**.
> Or run: `kill -9 $(lsof -t -i :5000)`

---

## 💻 Step 5: Start Next.js Operations Dashboard (Optional)

In a separate terminal window:
```bash
cd Dashboard
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🧪 Step 6: Quick Verification

```bash
# 1. Health check & executive metrics
curl -s http://localhost:5000/api/admin/dashboard/metrics

# 2. Test Delivery SLA calculation
curl -s -X POST http://localhost:5000/api/admin/delivery/estimate \
  -H "Content-Type: application/json" \
  -d '{"origin_pincode": "560001", "destination_pincode": "110001", "carrier": "Bluedart"}'

# 3. Test Email logs
curl -s http://localhost:5000/api/admin/emails/logs
```
