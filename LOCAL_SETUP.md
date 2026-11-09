# HegmaKart — Local Development Setup Guide

> **Goal**: This guide will help you run the entire HegmaKart stack (PostgreSQL, Redis, Saleor Django GraphQL, Flask REST API, and React frontend) on your local laptop for development.
> All services run on `localhost` without interacting with production services.

---

## 🏗️ Architecture Overview

```text
Browser (localhost:3000)
    │
    ├─► GraphQL queries  ──► Saleor Django  (localhost:8000)  ← /Hegma/web_api/web_api
    │                             │
    │                             └─► PostgreSQL (localhost:5432)
    │
    └─► REST /api/v1/…  ──► Flask REST API (localhost:5000)  ← /Hegma/backend
                                  │
                                  └─► PostgreSQL (localhost:5432)  [same DB]
```

---

## 📋 Prerequisites Check

Run these commands in your terminal to confirm your environment is ready:

```bash
python3 --version    # Recommended: Python 3.9.x for Saleor and Flask
node --version       # Recommended: Node.js >= 16 (e.g., v25)
npm --version        # Recommended: npm >= 8
psql --version       # Recommended: PostgreSQL 14+
brew --version       # (macOS only) Homebrew
```

---

## 🛠️ Step 1: PostgreSQL Database Setup

PostgreSQL acts as the single data store for both the Saleor backend and the Flask REST API.

### 1.1 Start PostgreSQL

#### 💻 macOS (via Homebrew):
```bash
brew services start postgresql
```

#### 🪟 Windows:
* Open the **Services** app (`services.msc`).
* Find `postgresql-x64-...`, right-click, and select **Start**.

---

### 1.2 Create the Local Database & User

Open your terminal or command prompt and run:
```bash
psql -U postgres
```

Inside the PostgreSQL prompt (`psql`), run the following SQL queries:
```sql
CREATE USER hegma WITH PASSWORD 'hegmalocal@123';
CREATE DATABASE dev_hegma OWNER hegma;
GRANT ALL PRIVILEGES ON DATABASE dev_hegma TO hegma;
\q
```

---

## 🐍 Step 2: Flask REST API (Port 5000)

**Repository Path**: `/Users/nagarajbhat/Hegma/backend`

### 2.1 Virtual Environment Setup

#### 💻 macOS:
```bash
cd /Users/nagarajbhat/Hegma/backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

#### 🪟 Windows (PowerShell):
```powershell
cd C:\path\to\Hegma\backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

---

### 2.2 Install Dependencies

With your virtual environment activated, run:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> [!NOTE]
> All critical version pins (such as `Werkzeug==2.3.8` to prevent Flask import issues and `setuptools==80.10.2` to ensure `razorpay` compatibility) are built directly into `requirements.txt`.

---

### 2.3 Configure environment variables (`.env`)

Create a new file named `.env` in the root of the `/backend` folder. Paste the following configuration:

```ini
# ── Flask ──────────────────────────────────────────────────
SECRET_KEY=dmfEzto5fraqDa-k_nf-A4MGcTGhQokYhLXCBiCUq5I
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# ── Local PostgreSQL (dev_hegma) ───────────────────────────
DB_NAME=dev_hegma
DB_USER_NAME=hegma          # Matches user created in Step 1.2 (or your local pg user)
DB_PASSWORD=hegmalocal@123  # Password set in Step 1.2
DB_HOST=localhost
DB_PORT=5432

# ── GraphQL backend (Saleor running locally) ───────────────
GRAPHQL_API_URL=http://localhost:8000/graphql/
SALEOR_ACCOUNT_REDIRECT_URL=http://localhost:3000
SALEOR_CHANNEL=

# ── HegmaKart Authentication Secrets (Local Dev / OTP bypass) ──
HEGMA_AUTH_TOKEN="Bearer ZIHpWmIQW6PooDwzvvd8mpcysaNLT8"
HEGMA_PASSWORD="hegmaDefault@123"
HEGMA_ENC_PASSWORD="pbkdf2_sha256$260000$NqSTWKPJDVhlVdbfOd7I8p$58QIeXL4iFLzsvaFyxsgAg7D3zy3iUhQQdh1WJSJ5XE="

# ── Razorpay TEST keys (safe for local dev) ────────────────
RAZORPAY_URL=https://api.razorpay.com/v1/orders
RAZORPAY_KEY_ID=rzp_test_hlhXqp1i8nse2U
RAZORPAY_KEY_SECRET=QXdUblS2Z3SXD7etn0c2yHdx
RAZORPAY_AUTH_TOKEN="Basic cnpwX3Rlc3RfaGxoWHFwMWk4bnNlMlU6UVhkVWJsUzJaM1NYRDdldG4wYzJ5SGR4"

# ── MSG91 SMS Gateway & TRAI DLT Template IDs ──────────────
MSG91_AUTH_KEY="375114AdHbKQLu762441736P1"
MSG91_OTP_DLE_ID="1307165234397419583"
MSG91_ORDER_DLE_ID="1307165234361126499"
MSG91_ORDER_COD_DLE_ID="1307165951829477290"
MSG91_CANCEL_DLE_ID="1307171169100455845"
```

---

### 2.4 Run the Backend Server

To start the server, make sure your virtual environment is active and run:
```bash
python api.py
```

It will print output indicating that it is serving on `http://127.0.0.1:5000`.

> [!WARNING]
> **macOS AirPlay Port Conflict**: If you get an `Address already in use` error on port 5000, go to **System Settings** -> **General** -> **AirPlay & Handoff** and turn off **AirPlay Receiver**.

---

### 2.5 🧪 How to Test Endpoints using Thunder Client or EchoAPI

Follow these beginner-friendly instructions to test the running API:

#### Test 1: GET Home Page (Health Check)
1. Open **Thunder Client** or **EchoAPI**.
2. Select **GET** as the request method.
3. Enter the URL: `http://localhost:5000/`
4. Click **Send**.
5. **Expected Response**: Status `200 OK` returning:
   ```html
   <h1>Distant Reading Archive</h1>
   <p>A prototype API for distant reading of science fiction novels.</p>
   ```

#### Test 2: POST Newsletter Subscription (Database test)
1. Select **POST** as the request method.
2. Enter the URL: `http://localhost:5000/api/v1/newsletterSubscription`
3. Click the **Body** tab, select the **JSON** sub-tab.
4. Input the following JSON payload:
   ```json
   {
     "email_id": "intern_test@example.com"
   }
   ```
5. Click **Send**.
6. **Expected Response**: Status `200 OK` returning `"success"`.
7. *Verification*: Run `SELECT * FROM email_emailsubscription;` in your PostgreSQL command line to confirm the email was inserted.

---

## ⚡ Step 3: Saleor GraphQL Backend (Port 8000)

**Repository Path**: `/Users/nagarajbhat/Hegma/web_api/web_api`

Saleor requires Python 3.9 (pinned in `runtime.txt`).

### 3.1 Install Python 3.9.18 and dependencies

#### 💻 macOS:
```bash
cd /Users/nagarajbhat/Hegma/web_api/web_api
python3 -m venv venv_saleor
source venv_saleor/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

#### 🪟 Windows (PowerShell):
```powershell
cd C:\path\to\Hegma\web_api\web_api
python -m venv venv_saleor
.\venv_saleor\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt
```

---

### 3.2 Configure `.env` for Saleor

Create a `.env` file in the root of `/web_api/web_api` with:
```ini
DEBUG=True
SECRET_KEY=local-dev-saleor-secret-key-change-in-prod
DATABASE_URL=postgres://hegma:hegmalocal@123@localhost:5432/dev_hegma
REDIS_URL=redis://localhost:6379/0
CACHE_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/2
ALLOWED_HOSTS=localhost,127.0.0.1
PLAYGROUND_ENABLED=True
DEFAULT_COUNTRY=IN
```

---

### 3.3 Setup Redis (Required for Saleor)

#### 💻 macOS:
```bash
brew install redis
brew services start redis
```

#### 🪟 Windows:
* Run Redis using WSL (`sudo apt install redis-server && sudo service redis-server start`) or use the native Windows port.

---

### 3.4 Run Migrations and Start Saleor

With `venv_saleor` activated, run:
```bash
python manage.py migrate
python manage.py createsuperuser   # Setup your admin dashboard account
python manage.py runserver 0.0.0.0:8000
```

* **GraphQL Playground**: `http://localhost:8000/graphql/`
* **Django Admin Panel**: `http://localhost:8000/dashboard/`

---

## ⚛️ Step 4: React Frontend (Port 3000)

**Repository Path**: `/Users/nagarajbhat/Hegma/Web/hegmakart-web-app-beta_api_url`

### 4.1 Install Node packages
```bash
cd /Users/nagarajbhat/Hegma/Web/hegmakart-web-app-beta_api_url

# --legacy-peer-deps handles old React library dependencies conflicts
npm install --legacy-peer-deps
```

### 4.2 Start Dev Server
```bash
npm start
```
The browser will automatically open to `http://localhost:3000`.

---

## 🛠️ Step 5: Common Troubleshooting

| Error / Issue | Root Cause | Solution |
|---|---|---|
| `ImportError: cannot import name 'url_quote' from 'werkzeug.urls'` | Incompatible `Werkzeug` package | Ensure you are using `Werkzeug<3.0.0` (pinned as `2.3.8` in `requirements.txt`). |
| `ModuleNotFoundError: No module named 'pkg_resources'` | `setuptools` version too high (>=82.0.0) | Ensure you are using `setuptools<=80.10.2` (pinned in `requirements.txt`). |
| `Address already in use (5000)` | macOS AirPlay Receiver listening on port 5000 | Disable AirPlay Receiver in system preferences or run Flask on port 5001. |
| `psycopg2` fails to install | Postgres compiler dependencies missing | Install binary wheel: `pip install psycopg2-binary`. |
| `AttributeError: 'SQLAlchemy' object has no attribute '...'` | Name collision between legacy `db.py` and Flask-SQLAlchemy `db` | Import SQLAlchemy db as an alias (e.g. `from admin_ops.database import db as admin_db`). |
