-- ============================================================
-- Finance & Asset Tracking SaaS — Database Initialisation
-- Multi-tenant schema with full audit trail and branch support
-- ============================================================

CREATE DATABASE IF NOT EXISTS finance_db;
USE finance_db;

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Organizations (tenants)
CREATE TABLE IF NOT EXISTS organizations (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(50) UNIQUE NOT NULL,
    logo_path   VARCHAR(255),
    plan        ENUM('free','starter','pro','enterprise') DEFAULT 'free',
    is_active   BOOLEAN DEFAULT TRUE,
    max_users   INT DEFAULT 5,
    max_assets  INT DEFAULT 100,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    org_id              INT NOT NULL,
    branch_id           INT NULL,
    name                VARCHAR(100) NOT NULL,
    email               VARCHAR(150) UNIQUE NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    role                ENUM('admin','manager','accountant','viewer') DEFAULT 'viewer',
    is_active           BOOLEAN DEFAULT TRUE,
    is_superadmin       BOOLEAN DEFAULT FALSE,
    must_change_password BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
    -- branch_id FK added after branches table is created
);

-- Organization Settings (key-value store per org)
CREATE TABLE IF NOT EXISTS organization_settings (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    org_id          INT NOT NULL,
    setting_key     VARCHAR(100) NOT NULL,
    setting_value   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    UNIQUE KEY unique_org_setting (org_id, setting_key)
);

-- Bank Accounts
CREATE TABLE IF NOT EXISTS bank_accounts (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    org_id          INT NOT NULL,
    account_name    VARCHAR(100) NOT NULL,
    bank_name       VARCHAR(100),
    account_number  VARCHAR(50),
    routing_number  VARCHAR(50),
    account_type    ENUM('checking','savings','business') DEFAULT 'checking',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- User Invitations
CREATE TABLE IF NOT EXISTS user_invitations (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    org_id          INT NOT NULL,
    email           VARCHAR(150) NOT NULL,
    role            ENUM('admin','manager','accountant','viewer') DEFAULT 'viewer',
    invited_by      INT NOT NULL,
    token           VARCHAR(255) NOT NULL,
    status          ENUM('pending','accepted','expired') DEFAULT 'pending',
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (invited_by) REFERENCES users(id),
    UNIQUE KEY unique_email_org (email, org_id)
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT,
    org_id          INT,
    action          VARCHAR(100) NOT NULL,
    details         TEXT,
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE SET NULL
);

-- ============================================================
-- BRANCHES (Hospital multi-branch support)
-- ============================================================
CREATE TABLE IF NOT EXISTS branches (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    org_id      INT NOT NULL,
    name        VARCHAR(100) NOT NULL,
    code        VARCHAR(20),
    address     TEXT,
    phone       VARCHAR(30),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- Now add branch_id FK to users
ALTER TABLE users ADD CONSTRAINT fk_users_branch
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL;

-- ============================================================
-- ASSET TABLES
-- ============================================================

-- Asset Categories
CREATE TABLE IF NOT EXISTS asset_categories (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    org_id              INT NOT NULL,
    name                VARCHAR(100) NOT NULL,
    depreciation_method ENUM('straight_line','declining_balance','units_of_production') DEFAULT 'straight_line',
    default_lifespan    INT DEFAULT 5,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Assets
CREATE TABLE IF NOT EXISTS assets (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    org_id            INT NOT NULL,
    branch_id         INT NULL,
    category_id       INT,
    asset_tag         VARCHAR(50) NOT NULL,
    name              VARCHAR(150) NOT NULL,
    description       TEXT,
    location          VARCHAR(100),
    assigned_to       VARCHAR(100),
    status            ENUM('active','maintenance','disposed','lost') DEFAULT 'active',
    purchase_date     DATE,
    purchase_price    DECIMAL(12,2),
    current_value     DECIMAL(12,2),
    salvage_value     DECIMAL(12,2) DEFAULT 0,
    useful_life_years INT DEFAULT 5,
    depreciation_rate DECIMAL(5,2) DEFAULT 0,
    warranty_expiry   DATE,
    serial_number     VARCHAR(100),
    notes             TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES asset_categories(id)
);

-- Asset History / Audit Trail
CREATE TABLE IF NOT EXISTS asset_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    asset_id    INT NOT NULL,
    changed_by  INT,
    change_type VARCHAR(50) NOT NULL,
    old_value   JSON,
    new_value   JSON,
    notes       TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Maintenance Records
CREATE TABLE IF NOT EXISTS maintenance_records (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    asset_id         INT NOT NULL,
    org_id           INT NOT NULL,
    maintenance_date DATE NOT NULL,
    cost             DECIMAL(12,2),
    performed_by     VARCHAR(100),
    description      TEXT,
    next_due_date    DATE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- Asset Maintenance (legacy alias — kept for backward compatibility)
CREATE TABLE IF NOT EXISTS asset_maintenance (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    asset_id        INT NOT NULL,
    maintenance_date DATE NOT NULL,
    description     TEXT,
    cost            DECIMAL(12,2),
    performed_by    VARCHAR(100),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- ============================================================
-- FINANCE TABLES
-- ============================================================

-- Finance Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    org_id      INT NOT NULL,
    name        VARCHAR(100) NOT NULL,
    type        ENUM('cash','bank','mobile_money','other') DEFAULT 'cash',
    balance     DECIMAL(15,2) DEFAULT 0,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Finance Categories
CREATE TABLE IF NOT EXISTS finance_categories (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    org_id      INT NOT NULL,
    name        VARCHAR(100) NOT NULL,
    type        ENUM('income','expense') NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    org_id           INT NOT NULL,
    branch_id        INT NULL,
    account_id       INT NOT NULL,
    bank_account_id  INT,
    category_id      INT,
    type             ENUM('income','expense','transfer') NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    description      VARCHAR(255),
    reference        VARCHAR(100),
    transaction_date DATE NOT NULL,
    recorded_by      INT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id),
    FOREIGN KEY (category_id) REFERENCES finance_categories(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id)
);

-- Transaction Templates
CREATE TABLE IF NOT EXISTS transaction_templates (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    org_id              INT NOT NULL,
    name                VARCHAR(100) NOT NULL,
    description         TEXT,
    transaction_type    ENUM('income','expense','transfer') NOT NULL,
    category_id         INT,
    amount              DECIMAL(15,2),
    account_id          INT,
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE SET NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

-- Recurring Transactions
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    org_id              INT NOT NULL,
    transaction_type    ENUM('income','expense','transfer') NOT NULL,
    category_id         INT,
    account_id          INT,
    amount              DECIMAL(15,2) NOT NULL,
    frequency           ENUM('daily','weekly','monthly','quarterly','yearly') NOT NULL,
    start_date          DATE NOT NULL,
    end_date            DATE,
    description         VARCHAR(255),
    is_active           BOOLEAN DEFAULT TRUE,
    last_run_date       DATE,
    next_run_date       DATE NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE SET NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

-- ============================================================
-- INDEXES for performance and multi-tenant isolation
-- ============================================================

-- Users
CREATE INDEX IF NOT EXISTS idx_users_org_id        ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email         ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_org_active    ON users(org_id, is_active);

-- Assets
CREATE INDEX IF NOT EXISTS idx_assets_org_id       ON assets(org_id);
CREATE INDEX IF NOT EXISTS idx_assets_branch_id    ON assets(branch_id);
CREATE INDEX IF NOT EXISTS idx_assets_org_status   ON assets(org_id, status);
CREATE INDEX IF NOT EXISTS idx_assets_org_category ON assets(org_id, category_id);

-- Transactions
CREATE INDEX IF NOT EXISTS idx_txn_org_id          ON transactions(org_id);
CREATE INDEX IF NOT EXISTS idx_txn_branch_id       ON transactions(branch_id);
CREATE INDEX IF NOT EXISTS idx_txn_org_date        ON transactions(org_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_txn_account_id      ON transactions(account_id);

-- Asset History
CREATE INDEX IF NOT EXISTS idx_asset_history_asset ON asset_history(asset_id);

-- Audit Logs
CREATE INDEX IF NOT EXISTS idx_audit_logs_org      ON audit_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user     ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action   ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_date     ON audit_logs(created_at);

-- Branches
CREATE INDEX IF NOT EXISTS idx_branches_org_id     ON branches(org_id);

-- Org settings
CREATE INDEX IF NOT EXISTS idx_org_settings_org    ON organization_settings(org_id);

-- ============================================================
-- SEED DATA
-- ============================================================

-- Super Admin organisation & user
-- Default password is: Admin@2026! (bcrypt hash below)
-- IMPORTANT: Change this password immediately after first login
INSERT INTO organizations (name, slug, plan, is_active, max_users, max_assets)
    VALUES ('System Admin', 'system', 'enterprise', TRUE, 999, 999999);

INSERT INTO users (org_id, name, email, password_hash, role, is_superadmin, must_change_password)
    VALUES (1, 'Super Admin', 'admin@system.com',
            '$2b$12$0N6DZvJyTXbNqqMnCvdcP.pS.tDD6UvQE/18KzuQ6MO0amWEOAuBG',
            'admin', TRUE, FALSE);
-- Note: hash above corresponds to password 'Admin@2026!'
-- Generate a new hash with: python -c "from flask_bcrypt import Bcrypt; b=Bcrypt(); print(b.generate_password_hash('YourNewPassword', rounds=12).decode())"

-- Demo Clinic organisation
INSERT INTO organizations (name, slug, plan, is_active, max_users, max_assets)
    VALUES ('Demo Clinic', 'demo-clinic', 'pro', TRUE, 10, 500);

-- Demo Clinic admin user — must_change_password = TRUE (force change on first login)
INSERT INTO users (org_id, name, email, password_hash, role, must_change_password)
    VALUES (2, 'Admin User', 'admin@demo.com',
            '$2b$12$0N6DZvJyTXbNqqMnCvdcP.pS.tDD6UvQE/18KzuQ6MO0amWEOAuBG',
            'admin', TRUE);
-- Temporary password: Admin@2026! — user will be forced to change on first login

-- Sample branches for Demo Clinic
INSERT INTO branches (org_id, name, code, address, phone) VALUES
    (2, 'Main Hospital',   'MAIN', '123 Health Avenue, Nairobi', '+254 20 000 0001'),
    (2, 'Westlands Branch','WEST', '45 Westlands Road, Nairobi',  '+254 20 000 0002'),
    (2, 'Karen Branch',    'KRN',  '78 Karen Road, Nairobi',      '+254 20 000 0003');

-- Asset categories for Demo Clinic
INSERT INTO asset_categories (org_id, name, depreciation_method, default_lifespan) VALUES
    (2, 'Medical Equipment', 'straight_line',    10),
    (2, 'Furniture',         'straight_line',     7),
    (2, 'IT Equipment',      'declining_balance', 5),
    (2, 'Vehicles',          'declining_balance', 8);

-- Sample assets (with branch and depreciation fields)
INSERT INTO assets (org_id, branch_id, category_id, asset_tag, name, location,
                   status, purchase_date, purchase_price, current_value,
                   salvage_value, useful_life_years, depreciation_rate) VALUES
    (2, 1, 1, 'ASSET-001', 'X-Ray Machine',    'Radiology Room', 'active',     '2022-01-15', 15000.00, 10500.00, 1500.00, 10, 10),
    (2, 1, 1, 'ASSET-002', 'ECG Monitor',      'Ward A',         'active',     '2023-03-10',  3500.00,  2800.00,  350.00, 10, 10),
    (2, 2, 2, 'ASSET-003', 'Reception Desk',   'Reception',      'active',     '2021-06-01',   800.00,   457.14,    0.00,  7,  0),
    (2, 3, 3, 'ASSET-004', 'Dell Laptop',      'Admin Office',   'active',     '2023-08-20',  1200.00,   864.00,    0.00,  5, 20),
    (2, 1, 4, 'ASSET-005', 'Ambulance',        'Parking Bay',    'active',     '2020-05-10', 45000.00, 19131.88,    0.00,  8, 25);

-- Finance accounts
INSERT INTO accounts (org_id, name, type, balance, is_active) VALUES
    (2, 'Cash on Hand', 'cash',  5000.00, TRUE),
    (2, 'Bank Account', 'bank', 45000.00, TRUE);

-- Finance categories
INSERT INTO finance_categories (org_id, name, type) VALUES
    (2, 'Consultation Fees', 'income'),
    (2, 'Lab Tests',         'income'),
    (2, 'Sales',             'income'),
    (2, 'Salaries',          'expense'),
    (2, 'Medical Supplies',  'expense'),
    (2, 'Utilities',         'expense'),
    (2, 'Rent',              'expense'),
    (2, 'Equipment',         'expense'),
    (2, 'Marketing',         'expense');

-- Sample transactions
INSERT INTO transactions (org_id, branch_id, account_id, category_id, type, amount,
                          description, transaction_date, recorded_by) VALUES
    (2, 1, 2, 1, 'income',  2500.00, 'Weekly consultation fees',  '2026-02-17', 2),
    (2, 1, 2, 2, 'income',  1200.00, 'Lab test revenue',           '2026-02-18', 2),
    (2, 2, 1, 5, 'expense',  800.00, 'Medical supplies restock',   '2026-02-19', 2),
    (2, 1, 2, 4, 'expense', 8000.00, 'Monthly salaries',           '2026-02-20', 2),
    (2, 1, 2, 7, 'expense', 2000.00, 'Monthly rent',               '2026-02-21', 2);

-- Default organisation settings
INSERT INTO organization_settings (org_id, setting_key, setting_value) VALUES
    (2, 'currency',          'USD'),
    (2, 'currency_symbol',   '$'),
    (2, 'date_format',       'YYYY-MM-DD'),
    (2, 'fiscal_year_start', '01'),
    (2, 'tax_rate',          '10'),
    (2, 'business_address',  ''),
    (2, 'business_phone',    ''),
    (2, 'business_email',    ''),
    (2, 'tax_id',            '');
