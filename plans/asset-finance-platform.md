# SmallBiz Asset & Finance Manager — Product Plan

> **Vision:** Transform the existing Finance Monitoring System into a multi-tenant SaaS platform that helps small businesses (clinics, hospitals, schools, retail shops) track their physical assets, manage basic cash flow, and generate actionable reports — all without needing an accountant or IT team.

---

## 🎯 Target Market

| Segment | Pain Point | Willingness to Pay |
|---|---|---|
| Private clinics / dental offices | Equipment worth $100k+ tracked on paper | High |
| Private schools / colleges | Furniture, laptops, lab equipment untracked | Medium-High |
| Small retail / pharmacies | Stock + equipment mixed up, no cash flow view | Medium |
| NGOs / nonprofits | Donor-funded assets must be audited | High |
| Small construction firms | Tools and machinery go missing | High |

**Sweet spot:** 5–100 employee organizations that cannot afford SAP/Oracle but need more than a spreadsheet.

---

## 💡 The Two Core Products (One Platform)

### Product A — Asset Management Module
Track every physical asset from purchase to disposal.

### Product B — Finance Tracker Module
Simple cash flow, income/expense ledger, and basic reporting — not full accounting, but enough for a business owner to know where their money is.

---

## 🏗️ System Architecture

```
Browser / Mobile
      |
   Nginx (Reverse Proxy + SSL)
      |
   Flask REST API  ←→  MySQL Database
      |                    |
  Auth Service         Multi-tenant schemas
      |                    |
  Prometheus          Redis (session cache)
      |
  Grafana (internal ops dashboard)
```

### How the Existing Codebase Maps to the New Product

| Existing File | Reuse / Extend |
|---|---|
| `app/app.py` | Extend with new route blueprints for assets and finance |
| `db/init.sql` | Replace `servers` table with new multi-tenant schema |
| `docker-compose.yml` | Add Redis service; keep Nginx, MySQL, Prometheus, Grafana |
| `terraform/main.tf` | Already provisions VPC + RDS + EC2 — reuse as-is for prod |
| `ansible/deploy.yml` | Reuse for EC2 provisioning and Docker deployment |
| `.github/workflows/devsecops.yml` | Keep full DevSecOps pipeline unchanged |
| `config/prometheus.yml` | Add scrape targets for new services |
| `nginx/nginx.conf` | Add SSL termination and route rules |
| `key.py` | Use for generating tenant API keys and secure passwords |

---

## 🗄️ Database Schema Design

### Multi-Tenancy Strategy
Each organization (tenant) gets its own `org_id` foreign key. All tables are scoped by `org_id`. This is the simplest approach for an MVP — single database, row-level isolation.

```sql
-- Organizations (tenants)
CREATE TABLE organizations (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(50) UNIQUE NOT NULL,   -- used in URLs
    plan        ENUM('free','pro','enterprise') DEFAULT 'free',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users
CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    org_id      INT NOT NULL,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role        ENUM('admin','manager','viewer') DEFAULT 'viewer',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- =====================
-- ASSET MANAGEMENT
-- =====================

CREATE TABLE asset_categories (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,   -- e.g. Medical Equipment, Furniture, IT
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE assets (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    org_id          INT NOT NULL,
    category_id     INT,
    asset_tag       VARCHAR(50) NOT NULL,       -- e.g. ASSET-2024-001
    name            VARCHAR(150) NOT NULL,
    description     TEXT,
    location        VARCHAR(100),               -- Room 3B, Ward 2, etc.
    assigned_to     VARCHAR(100),               -- person or department
    status          ENUM('active','maintenance','disposed','lost') DEFAULT 'active',
    purchase_date   DATE,
    purchase_price  DECIMAL(12,2),
    current_value   DECIMAL(12,2),              -- after depreciation
    depreciation_rate DECIMAL(5,2) DEFAULT 0,  -- % per year
    warranty_expiry DATE,
    serial_number   VARCHAR(100),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (category_id) REFERENCES asset_categories(id)
);

CREATE TABLE asset_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    asset_id    INT NOT NULL,
    changed_by  INT NOT NULL,               -- user_id
    change_type ENUM('created','updated','assigned','maintenance','disposed'),
    old_value   JSON,
    new_value   JSON,
    notes       TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (changed_by) REFERENCES users(id)
);

CREATE TABLE maintenance_records (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    asset_id        INT NOT NULL,
    org_id          INT NOT NULL,
    maintenance_date DATE NOT NULL,
    cost            DECIMAL(10,2),
    performed_by    VARCHAR(100),
    description     TEXT,
    next_due_date   DATE,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

-- =====================
-- FINANCE TRACKER
-- =====================

CREATE TABLE accounts (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,   -- Cash, Bank, Mobile Money
    type    ENUM('cash','bank','mobile_money','other') DEFAULT 'cash',
    balance DECIMAL(12,2) DEFAULT 0,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE finance_categories (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,   -- Salaries, Rent, Medical Supplies, School Fees
    type    ENUM('income','expense') NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE transactions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    org_id          INT NOT NULL,
    account_id      INT NOT NULL,
    category_id     INT,
    type            ENUM('income','expense','transfer') NOT NULL,
    amount          DECIMAL(12,2) NOT NULL,
    description     VARCHAR(255),
    reference       VARCHAR(100),               -- invoice/receipt number
    transaction_date DATE NOT NULL,
    recorded_by     INT NOT NULL,               -- user_id
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (category_id) REFERENCES finance_categories(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id)
);
```

---

## 🔌 API Endpoints Design

### Authentication
```
POST /api/auth/register     -- Create org + admin user
POST /api/auth/login        -- Returns JWT token
POST /api/auth/logout
GET  /api/auth/me
```

### Asset Management
```
GET    /api/assets                  -- List all assets (filterable)
POST   /api/assets                  -- Add new asset
GET    /api/assets/<id>             -- Get single asset detail
PUT    /api/assets/<id>             -- Update asset
DELETE /api/assets/<id>             -- Soft delete (mark disposed)
GET    /api/assets/<id>/history     -- Full audit trail
POST   /api/assets/<id>/maintenance -- Log maintenance record
GET    /api/assets/report           -- Summary report (by category, status, value)
GET    /api/assets/export           -- Export to CSV/PDF
```

### Finance Tracker
```
GET    /api/finance/transactions         -- List transactions (date range filter)
POST   /api/finance/transactions         -- Record income or expense
GET    /api/finance/transactions/<id>
PUT    /api/finance/transactions/<id>
DELETE /api/finance/transactions/<id>
GET    /api/finance/summary              -- Total income, expense, net for period
GET    /api/finance/cashflow             -- Monthly cashflow chart data
GET    /api/finance/report               -- Full financial report
GET    /api/finance/export               -- Export to CSV/PDF
```

### Admin / Multi-tenant
```
GET  /api/admin/users           -- List org users
POST /api/admin/users           -- Invite user
PUT  /api/admin/users/<id>      -- Change role
GET  /api/admin/org             -- Org settings
PUT  /api/admin/org             -- Update org settings
```

---

## 🖥️ Frontend Plan

Build a simple **React + Tailwind CSS** single-page app (or use a lightweight template):

### Pages
1. **Login / Register** — Org signup with name, email, password
2. **Dashboard** — Summary cards: total assets, total asset value, monthly income, monthly expenses, net cash
3. **Assets List** — Table with search, filter by category/status/location, bulk actions
4. **Asset Detail** — Full asset card + maintenance history + audit log
5. **Add/Edit Asset** — Form with all fields
6. **Finance Ledger** — Transaction list with date range picker
7. **Add Transaction** — Quick income/expense form
8. **Reports** — Charts: asset value by category (pie), cashflow over time (line), expense breakdown (bar)
9. **Settings** — Users, categories, accounts management

---

## 📊 Reports to Generate

### Asset Reports
- **Asset Register** — Full list with current values (for insurance/audit)
- **Depreciation Report** — Assets losing value over time
- **Maintenance Due** — Assets with upcoming or overdue maintenance
- **Assets by Location** — What is in each room/department
- **Disposed Assets** — Historical record

### Finance Reports
- **Monthly P&L** — Income vs Expenses
- **Cash Flow Statement** — Money in vs money out by week/month
- **Expense Breakdown** — Which categories cost the most
- **Account Balances** — Current balance per account

---

## 🚀 MVP Scope (Phase 1 — What to Build First)

Focus on the minimum that a clinic or school would pay for on Day 1:

- [ ] User registration and login with JWT auth
- [ ] Add / list / edit / delete assets with basic fields
- [ ] Asset status tracking (active, maintenance, disposed)
- [ ] Record income and expense transactions
- [ ] Dashboard summary (asset count, total value, monthly net)
- [ ] CSV export for assets and transactions
- [ ] Multi-tenant isolation (org_id on all records)
- [ ] Basic role system (admin vs viewer)

---

## 📅 Phased Roadmap

### Phase 1 — MVP (Core Value)
- Asset CRUD + status tracking
- Basic income/expense ledger
- Dashboard with summary cards
- CSV export
- Single-tenant (one org per deployment) → simplest to start

### Phase 2 — Growth Features
- Multi-tenant SaaS (multiple orgs, one deployment)
- Maintenance scheduling + email reminders
- Depreciation auto-calculation
- PDF report generation
- Role-based access (admin, manager, viewer)
- Mobile-responsive UI

### Phase 3 — Premium / Enterprise
- QR code / barcode labels for assets (scan to view/update)
- Bulk import via CSV/Excel
- Grafana dashboards for ops teams (already in stack)
- API key access for integrations
- Audit log export for compliance
- WhatsApp/SMS alerts for maintenance due dates

---

## 💰 Pricing Model

| Plan | Price | Features |
|---|---|---|
| Free | $0/month | 1 user, 50 assets, 100 transactions/month |
| Starter | $19/month | 5 users, 500 assets, unlimited transactions |
| Pro | $49/month | 20 users, unlimited assets, PDF reports, maintenance alerts |
| Enterprise | $149/month | Unlimited users, API access, custom branding, priority support |

**Target:** 50 paying Starter/Pro customers = $1,000–$2,500 MRR within 6 months.

---

## 🔧 Technical Changes to Existing Codebase

### Files to Modify
| File | Change |
|---|---|
| `app/app.py` | Refactor into Flask Blueprints: `auth`, `assets`, `finance`, `admin` |
| `db/init.sql` | Replace `servers` table with full schema above |
| `app/requirements.txt` | Add: `flask-jwt-extended`, `flask-bcrypt`, `reportlab` (PDF), `redis` |
| `docker-compose.yml` | Add Redis service for session/cache |
| `nginx/nginx.conf` | Add SSL + route `/api/*` to Flask, `/` to React frontend |
| `config/prometheus.yml` | Add scrape for new service endpoints |

### Files to Add
| File | Purpose |
|---|---|
| `app/blueprints/auth.py` | Login, register, JWT |
| `app/blueprints/assets.py` | Asset CRUD routes |
| `app/blueprints/finance.py` | Transaction routes |
| `app/blueprints/reports.py` | Report generation |
| `app/models/` | DB model helpers |
| `frontend/` | React app (or simple HTML/JS dashboard) |

### Files to Keep Unchanged
- `Jenkinsfile` — CI/CD pipeline stays the same
- `.github/workflows/devsecops.yml` — DevSecOps pipeline stays the same
- `terraform/main.tf` — AWS infrastructure stays the same
- `ansible/deploy.yml` — Server provisioning stays the same
- `key.py` — Reuse for API key generation

---

## 🔒 Security Considerations

- Passwords hashed with bcrypt (never stored plain)
- JWT tokens with expiry (15min access + 7day refresh)
- All routes require `org_id` validation — users cannot access other orgs' data
- Rate limiting on auth endpoints (prevent brute force)
- Input validation on all POST/PUT endpoints
- Existing Bandit + Safety + Trivy pipeline catches new vulnerabilities automatically

---

## 🎯 Go-to-Market Strategy

1. **Pilot with 1 clinic or school for free** — get real feedback, fix pain points
2. **Build a simple landing page** explaining the product
3. **Offer free data migration** from their current spreadsheet (manual import)
4. **Charge after 30-day trial** — most small businesses will pay if it saves them time
5. **Referral program** — existing customers refer others for 1 month free

---

## Summary

This platform solves a real, universal problem: **small organizations lose money and assets because they have no system**. The existing codebase already has the infrastructure (Flask + MySQL + Docker + AWS + CI/CD) — the work is extending the application layer with new domain models and a simple frontend. The result is a product that can be sold to any clinic, school, or small business in any country.
