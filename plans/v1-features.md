# Asset & Finance Manager - V1.0 Feature Expansion Plan

## Executive Summary

This document outlines the comprehensive feature expansion for Version 1.0 of the Asset & Finance Manager. The expansion addresses the core requirements for a multi-tenant business management system with superadmin capabilities, enhanced security, and fault tolerance.

---

## 1. Current System Analysis

### Existing Components
- ✅ Flask backend with Blueprints (auth, assets, finance, dashboard)
- ✅ MySQL database with multi-tenant design
- ✅ JWT authentication
- ✅ Professional dashboard UI with Tailwind CSS
- ✅ Docker orchestration (MySQL, Redis, Flask, Nginx)
- ✅ Prometheus & Grafana monitoring

### Identified Issues to Fix
- Dashboard analytics loading issue
- Transaction creation flow needs improvement
- Missing configuration/settings section
- No superadmin functionality

---

## 2. Feature Requirements Breakdown

### 2.1 Transaction Management Enhancement
**Priority: HIGH**

#### Current State
- Basic transaction CRUD exists
- Limited bank details support

#### Requirements
- **Bank Account Integration**
  - Add multiple bank accounts per organization
  - Store bank name, account number, routing number (encrypted)
  - Link transactions to specific bank accounts
  - Bank statement import capability (future)

- **Transaction Categories**
  - Income types: Sales, Services, Investments, Other Income
  - Expense types: Operations, Salaries, Utilities, Supplies, Other Expenses
  - Transfer types: Between accounts

- **Transaction Features**
  - Recurring transactions (daily, weekly, monthly)
  - Transaction templates
  - Bulk import via CSV
  - Receipt attachment support
  - Transaction notes and tags
  - Search and filter by date, category, account, amount

### 2.2 Configuration & Settings Section
**Priority: HIGH**

#### Requirements
- **Organization Settings**
  - Business name
  - Business logo upload
  - Business address and contact info
  - Tax identification number
  - Fiscal year start

- **Asset Configuration**
  - Asset categories (Medical Equipment, Furniture, IT Equipment, Vehicles, etc.)
  - Asset depreciation methods (Straight-line, Declining balance, Units of production)
  - Default asset lifespan by category
  - Asset tag prefix customization

- **Finance Configuration**
  - Currency selection (USD, EUR, GBP, KES, NGN, etc.)
  - Currency symbol and formatting
  - Decimal precision
  - Tax rates configuration
  - Invoice numbering format

- **User Management**
  - Invite team members
  - Role-based permissions (Admin, Manager, Accountant, Viewer)
  - User activity tracking

### 2.3 Multi-Business Management (Superadmin)
**Priority: HIGH**

#### Requirements
- **Superadmin Account**
  - Create and manage multiple organizations
  - System-wide settings
  - User management across organizations
  - Activity logging and audit trail

- **Organization Management**
  - Create new organizations
  - Set organization plan (Free, Starter, Pro, Enterprise)
  - Allocate user licenses
  - Suspend/activate organizations

- **Business Onboarding**
  - Register new business
  - Generate initial admin credentials
  - Send welcome email with login details
  - Setup wizard for initial configuration

### 2.4 Dashboard Analytics Enhancement
**Priority: MEDIUM**

#### Requirements
- **Real-time Metrics**
  - Total assets value
  - Monthly income/expense
  - Net profit/loss
  - Cash flow trend

- **Charts & Visualizations**
  - Asset distribution by category (pie chart)
  - Income vs Expense trend (line chart)
  - Monthly comparison (bar chart)
  - Top expense categories (horizontal bar)

- **Key Performance Indicators**
  - Asset utilization rate
  - Monthly burn rate
  - Revenue growth
  - Expense breakdown

### 2.5 Team Collaboration
**Priority: MEDIUM**

#### Requirements
- **Member Management**
  - Invite via email
  - Role assignment
  - Remove/deactivate members
  - View member activity

- **Permissions Matrix**
  - View transactions
  - Create transactions
  - Edit transactions
  - Delete transactions
  - Manage assets
  - Manage settings
  - Manage users

---

## 3. Database Schema Changes

### 3.1 New Tables

```sql
-- Organization settings
CREATE TABLE organization_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    org_id INT NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    UNIQUE KEY unique_org_setting (org_id, setting_key)
);

-- Bank accounts
CREATE TABLE bank_accounts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    org_id INT NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    bank_name VARCHAR(100),
    account_number VARCHAR(50),
    routing_number VARCHAR(50),
    account_type ENUM('checking', 'savings', 'business') DEFAULT 'checking',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- User invitations
CREATE TABLE user_invitations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    org_id INT NOT NULL,
    email VARCHAR(150) NOT NULL,
    role ENUM('admin', 'manager', 'accountant', 'viewer') DEFAULT 'viewer',
    invited_by INT NOT NULL,
    token VARCHAR(255) NOT NULL,
    status ENUM('pending', 'accepted', 'expired') DEFAULT 'pending',
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    UNIQUE KEY unique_email_org (email, org_id)
);

-- Superadmin audit log
CREATE TABLE audit_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    org_id INT,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE SET NULL
);

-- Transaction templates
CREATE TABLE transaction_templates (
    id INT PRIMARY KEY AUTO_INCREMENT,
    org_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    transaction_type ENUM('income', 'expense', 'transfer') NOT NULL,
    category_id INT,
    amount DECIMAL(15,2),
    account_id INT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE SET NULL,
    FOREIGN KEY (account_id) REFERENCES finance_accounts(id) ON DELETE SET NULL
);

-- Recurring transactions
CREATE TABLE recurring_transactions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    org_id INT NOT NULL,
    transaction_type ENUM('income', 'expense', 'transfer') NOT NULL,
    category_id INT,
    account_id INT,
    amount DECIMAL(15,2) NOT NULL,
    frequency ENUM('daily', 'weekly', 'monthly', 'quarterly', 'yearly') NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    description VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_run_date DATE,
    next_run_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);
```

### 3.2 Modified Tables

```sql
-- Add superadmin flag to users
ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE AFTER role;

-- Add bank_account_id to transactions
ALTER TABLE transactions ADD COLUMN bank_account_id INT AFTER account_id;
ALTER TABLE transactions ADD FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id) ON DELETE SET NULL;

-- Add logo_path to organizations
ALTER TABLE organizations ADD COLUMN logo_path VARCHAR(255) AFTER name;
ALTER TABLE organizations ADD COLUMN plan ENUM('free', 'starter', 'pro', 'enterprise') DEFAULT 'free' AFTER plan;
```

---

## 4. Security Architecture

### 4.1 Authentication & Authorization

#### JWT Improvements
- Short-lived access tokens (15 minutes)
- Long-lived refresh tokens (7 days)
- Token rotation on refresh
- Secure token storage

#### Role-Based Access Control (RBAC)
```
Superadmin
├── System Administration
├── Organization Management
├── User Management (all orgs)
└── Audit Logs View

Organization Admin
├── Organization Settings
├── User Management (own org)
├── Asset Management
├── Finance Management
└── Reports

Manager
├── Asset Management
├── Finance Management
└── Reports

Accountant
├── Create/Edit Transactions
├── View Assets
└── Reports

Viewer
├── View Only
└── Reports (read)
```

### 4.2 Data Security

#### Encryption
- **At Rest**: MySQL TDE (Transparent Data Encryption)
- **In Transit**: TLS 1.3 for all connections
- **Application Level**: 
  - Encrypt sensitive fields (bank account numbers, routing numbers)
  - UseFernet encryption from cryptography library

#### Input Validation
- All user inputs sanitized
- SQL injection prevention (parameterized queries)
- XSS prevention (output encoding)
- CSRF protection (Flask-WTF tokens)

### 4.3 API Security

#### Rate Limiting
- Login attempts: 5 per minute
- API requests: 100 per minute
- File uploads: 10 per minute

#### Headers Security
- CORS configuration
- Content Security Policy
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Strict-Transport-Security (HSTS)

### 4.4 Audit & Compliance

#### Logging
- All authentication events
- Data modification events
- Administrative actions
- Failed access attempts

#### Audit Trail
- User activity tracking
- Configuration changes
- Data exports
- Login history

---

## 5. High Availability & Fault Tolerance

### 5.1 Architecture

```
                    ┌─────────────┐
                    │   CDN/WAF   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Nginx LB  │
                    │ (HAProxy)   │
                    └──────┬──────┘
                           │
            ┌───────────────┼───────────────┐
            │               │               │
     ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
     │  Web App 1  │ │  Web App 2  │ │  Web App 3  │
     │  (Flask)   │ │  (Flask)   │ │  (Flask)   │
     └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
       ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
       │   MySQL     │ │   MySQL     │ │   MySQL     │
       │  Primary    │ │ Replica 1   │ │ Replica 2   │
       └─────────────┘ └─────────────┘ └─────────────┘
              │
       ┌──────▼──────┐
       │ Redis Cache │
       └─────────────┘
```

### 5.2 Components

#### Load Balancer
- Nginx with upstream configuration
- Health checks every 10 seconds
- Automatic failover
- SSL termination

#### Application Layer
- 3+ Flask instances (auto-scaling)
- Stateless design
- Session storage in Redis
- Health check endpoint

#### Database Layer
- MySQL 8.0 with Group Replication
- Automatic failover
- Read replicas for reporting queries
- Daily backups (offsite storage)

#### Caching Layer
- Redis cluster for sessions
- Query caching
- Rate limiting data
- Pub/Sub for notifications

### 5.3 Monitoring & Alerts

#### Prometheus Metrics
- Application performance
- Database performance
- Cache hit rates
- Request latency
- Error rates

#### Grafana Dashboards
- System health
- Business metrics
- Security events
- Capacity planning

#### Alerting
- Email notifications
- Slack integration
- PagerDuty integration
- Critical issues: Immediate
- Warnings: Within 15 minutes

### 5.4 Backup & Recovery

#### Backup Strategy
- Full backup: Daily at 2 AM UTC
- Incremental: Every 6 hours
- Transaction logs: Every 15 minutes
- Offsite replication: Every hour

#### Recovery Procedures
- RTO (Recovery Time Objective): 1 hour
- RPO (Recovery Point Objective): 15 minutes
- Regular disaster recovery drills

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Fix dashboard analytics loading issue
- [ ] Enhance transaction management
- [ ] Add bank accounts support
- [ ] Implement organization settings

### Phase 2: Configuration (Week 3-4)
- [ ] Asset categories management
- [ ] Depreciation settings
- [ ] Currency configuration
- [ ] Tax rate setup

### Phase 3: Superadmin (Week 5-6)
- [ ] Superadmin role implementation
- [ ] Organization management
- [ ] User invitation system
- [ ] Audit logging

### Phase 4: Security & HA (Week 7-8)
- [ ] Enhanced JWT security
- [ ] Rate limiting
- [ ] Security headers
- [ ] High availability setup

### Phase 5: Testing & Polish (Week 9-10)
- [ ] Integration testing
- [ ] Security audit
- [ ] Performance testing
- [ ] Documentation

---

## 7. API Endpoints

### 7.1 New Endpoints

```
# Settings
GET    /api/settings                  # Get all settings
PUT    /api/settings                  # Update settings
GET    /api/settings/logo             # Get organization logo
POST   /api/settings/logo             # Upload logo

# Bank Accounts
GET    /api/bank-accounts             # List bank accounts
POST   /api/bank-accounts             # Create bank account
GET    /api/bank-accounts/<id>        # Get bank account
PUT    /api/bank-accounts/<id>        # Update bank account
DELETE /api/bank-accounts/<id>        # Delete bank account

# Transactions (Enhanced)
GET    /api/transactions              # List with filters
POST   /api/transactions              # Create transaction
GET    /api/transactions/<id>         # Get transaction
PUT    /api/transactions/<id>         # Update transaction
DELETE /api/transactions/<id>         # Delete transaction
POST   /api/transactions/import       # Bulk import

# Transaction Templates
GET    /api/transaction-templates     # List templates
POST   /api/transaction-templates     # Create template
DELETE /api/transaction-templates/<id> # Delete template

# Recurring Transactions
GET    /api/recurring                 # List recurring
POST   /api/recurring                 # Create recurring
PUT    /api/recurring/<id>           # Update recurring
DELETE /api/recurring/<id>           # Delete recurring

# Team Management
GET    /api/team                     # List team members
POST   /api/team/invite              # Invite member
DELETE /api/team/<id>                # Remove member

# Superadmin
GET    /api/admin/organizations      # List organizations
POST   /api/admin/organizations      # Create organization
GET    /api/admin/organizations/<id> # Get organization
PUT    /api/admin/organizations/<id> # Update organization
DELETE /api/admin/organizations/<id> # Delete organization
GET    /api/admin/audit-logs         # View audit logs
```

---

## 8. Frontend Pages

### 8.1 New Pages Required

1. **Settings Dashboard**
   - Organization profile
   - Logo upload
   - Business details

2. **Asset Settings**
   - Categories management
   - Depreciation configuration

3. **Finance Settings**
   - Currency configuration
   - Tax rates
   - Invoice settings

4. **Bank Accounts**
   - Account listing
   - Add/Edit account
   - Account details

5. **Team Management**
   - Member list
   - Invite modal
   - Role management

6. **Superadmin Panel**
   - Organization list
   - Create organization
   - System settings
   - Audit logs

---

## 9. Acceptance Criteria

### Must Have (MVP)
- [ ] Dashboard analytics working
- [ ] Transaction creation with bank accounts
- [ ] Organization settings with logo
- [ ] Asset categories management
- [ ] Currency configuration
- [ ] Superadmin account functional
- [ ] User invitation system
- [ ] Role-based permissions

### Should Have
- [ ] Transaction templates
- [ ] Recurring transactions
- [ ] Bulk import
- [ ] Audit logging
- [ ] Rate limiting
- [ ] Security headers

### Nice to Have
- [ ] Mobile app (future)
- [ ] API for integrations
- [ ] Multi-language support
- [ ] Advanced reporting

---

## 10. Success Metrics

### User Adoption
- 10+ organizations within 3 months
- 50+ users within 6 months

### Performance
- 99.9% uptime
- < 200ms average response time
- < 1s page load time

### Security
- Zero critical vulnerabilities
- 100% encrypted sensitive data
- Full audit trail

---

## Next Steps

1. **Approve this plan** 
2. **Prioritize features** for Phase 1
3. **Begin implementation** of foundational features
4. **Weekly progress reviews**

---

*Document Version: 1.0*
*Last Updated: 2026-02-22*
*Author: Technical Architecture Team*
