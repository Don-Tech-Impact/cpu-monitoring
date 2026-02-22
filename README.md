# SmallBiz Asset & Finance Manager

A production-ready multi-tenant SaaS platform for small businesses — clinics, schools, pharmacies, and NGOs — to track physical assets and manage basic cash flow.

## Architecture

```
Client → Nginx (Reverse Proxy) → Flask REST API → MySQL 8.0
                                        ↓
                              Prometheus + Grafana (Monitoring)
                              Redis (Session Cache)
```

## Features

### Asset Management
- Track physical assets (equipment, furniture, IT, vehicles) from purchase to disposal
- Asset categories, location tracking, assignment to staff/departments
- Maintenance scheduling and history
- Full audit trail for every change
- Depreciation tracking
- CSV export

### Finance Tracker
- Record income and expense transactions
- Multiple accounts (cash, bank, mobile money)
- Income/expense categories
- Monthly cash flow summary
- 6-month trend charts
- CSV export

### Platform
- Multi-tenant: each organization has isolated data
- Role-based access: admin, manager, viewer
- JWT authentication
- Professional dashboard UI
- Prometheus metrics + Grafana dashboards
- Full DevSecOps CI/CD pipeline

## Quick Start

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/finance-monitoring-system.git
cd finance-monitoring-system

# Create .env file
cp config/.env.example .env
# Edit .env with your credentials

# Start all services
make up

# View logs
make logs
```

## Access

| Service | URL | Credentials |
|---|---|---|
| Dashboard UI | http://localhost/ui | Register or use demo: admin@demo.com / admin123 |
| API | http://localhost/api | JWT Bearer token |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / (see .env) |

## API Endpoints

### Authentication
- `POST /api/auth/register` — Create organization + admin user
- `POST /api/auth/login` — Login, returns JWT token
- `GET  /api/auth/me` — Current user info

### Assets
- `GET    /api/assets` — List assets (filter: `?status=active&category_id=1`)
- `POST   /api/assets` — Add asset
- `GET    /api/assets/<id>` — Asset detail
- `PUT    /api/assets/<id>` — Update asset
- `DELETE /api/assets/<id>` — Soft delete (mark disposed)
- `GET    /api/assets/<id>/history` — Audit trail
- `POST   /api/assets/<id>/maintenance` — Log maintenance
- `GET    /api/assets/export/csv` — Export to CSV
- `GET    /api/asset-categories` — List categories
- `POST   /api/asset-categories` — Create category

### Finance
- `GET    /api/finance/transactions` — List transactions (filter: `?type=income&from=2026-01-01&to=2026-01-31`)
- `POST   /api/finance/transactions` — Record transaction
- `DELETE /api/finance/transactions/<id>` — Delete transaction
- `GET    /api/finance/accounts` — List accounts
- `POST   /api/finance/accounts` — Create account
- `GET    /api/finance/categories` — Finance categories
- `POST   /api/finance/categories` — Create category
- `GET    /api/finance/summary` — Monthly summary
- `GET    /api/finance/cashflow` — 6-month trend data
- `GET    /api/finance/export/csv` — Export to CSV

### Dashboard
- `GET /api/dashboard` — Aggregated stats for dashboard

## Environment Variables

See `config/.env.example` for all options.

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL host (default: `db`) |
| `DB_USER` | MySQL username |
| `DB_PASSWORD` | MySQL password |
| `DB_NAME` | Database name (default: `finance_db`) |
| `JWT_SECRET_KEY` | Secret key for JWT signing |
| `REDIS_URL` | Redis connection URL |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password |

## Project Structure

```
.
├── app/
│   ├── blueprints/
│   │   ├── auth.py          # Authentication routes
│   │   ├── assets.py        # Asset management routes
│   │   ├── finance.py       # Finance tracker routes
│   │   └── dashboard.py     # Dashboard aggregate route
│   ├── templates/
│   │   └── index.html       # Single-page dashboard UI
│   ├── app.py               # Flask app factory
│   ├── Dockerfile
│   └── requirements.txt
├── db/
│   └── init.sql             # Multi-tenant schema + seed data
├── nginx/
│   └── nginx.conf           # Reverse proxy config
├── config/
│   ├── .env.example
│   └── prometheus.yml
├── terraform/               # AWS infrastructure (VPC, EC2, RDS)
├── ansible/                 # EC2 provisioning playbook
├── .github/workflows/       # DevSecOps CI/CD pipeline
├── docker-compose.yml
├── Makefile
└── README.md
```

## Available Commands

```bash
make up                 # Start all services
make down               # Stop and remove containers
make logs               # View real-time logs
make shell              # SSH into web container
make verify             # Verify database initialization
make test-connection    # Test MySQL connection
```

## Demo Credentials

After `make up`, the demo organization is pre-loaded:
- **Email:** admin@demo.com
- **Password:** admin123
- **Organization:** Demo Clinic

## Deployment

The project includes a full DevSecOps pipeline:
- **GitHub Actions** (`.github/workflows/devsecops.yml`): SAST → Lint → Docker Build → Trivy scan → Terraform validate → Deploy to EC2
- **Jenkins** (`Jenkinsfile`): Same pipeline for Jenkins environments
- **Terraform** (`terraform/`): AWS VPC + EC2 + RDS infrastructure
- **Ansible** (`ansible/`): EC2 server provisioning and hardening

## Target Markets

| Segment | Use Case |
|---|---|
| Private clinics | Track medical equipment, manage daily cash flow |
| Schools / colleges | Manage IT assets, furniture, lab equipment |
| Pharmacies | Track shop equipment + daily revenue/expenses |
| NGOs | Donor-funded asset tracking for audit compliance |
| Construction firms | Tool and machinery management |

## Author

Abdulai Tamba Lebbie
