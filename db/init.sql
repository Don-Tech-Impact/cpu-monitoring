CREATE DATABASE IF NOT EXISTS finance_db;
USE finance_db;

-- Organizations (tenants)
CREATE TABLE IF NOT EXISTS organizations (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(50) UNIQUE NOT NULL,
    plan        ENUM('free','pro','enterprise') DEFAULT 'free',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    org_id        INT NOT NULL,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('admin','manager','viewer') DEFAULT 'viewer',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Asset Categories
CREATE TABLE IF NOT EXISTS asset_categories (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Assets
CREATE TABLE IF NOT EXISTS assets (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    org_id            INT NOT NULL,
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
    depreciation_rate DECIMAL(5,2) DEFAULT 0,
    warranty_expiry   DATE,
    serial_number     VARCHAR(100),
    notes             TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (category_id) REFERENCES asset_categories(id)
);

-- Asset History (audit trail)
CREATE TABLE IF NOT EXISTS asset_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    asset_id    INT NOT NULL,
    changed_by  INT NOT NULL,
    change_type ENUM('created','updated','assigned','maintenance','disposed'),
    old_value   JSON,
    new_value   JSON,
    notes       TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (changed_by) REFERENCES users(id)
);

-- Maintenance Records
CREATE TABLE IF NOT EXISTS maintenance_records (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    asset_id         INT NOT NULL,
    org_id           INT NOT NULL,
    maintenance_date DATE NOT NULL,
    cost             DECIMAL(10,2),
    performed_by     VARCHAR(100),
    description      TEXT,
    next_due_date    DATE,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

-- Finance Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,
    type    ENUM('cash','bank','mobile_money','other') DEFAULT 'cash',
    balance DECIMAL(12,2) DEFAULT 0,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Finance Categories
CREATE TABLE IF NOT EXISTS finance_categories (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    org_id  INT NOT NULL,
    name    VARCHAR(100) NOT NULL,
    type    ENUM('income','expense') NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    org_id           INT NOT NULL,
    account_id       INT NOT NULL,
    category_id      INT,
    type             ENUM('income','expense','transfer') NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    description      VARCHAR(255),
    reference        VARCHAR(100),
    transaction_date DATE NOT NULL,
    recorded_by      INT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (category_id) REFERENCES finance_categories(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id)
);

-- Seed demo organization
INSERT INTO organizations (name, slug, plan) VALUES ('Demo Clinic', 'demo-clinic', 'pro');
INSERT INTO users (org_id, name, email, password_hash, role) VALUES (1, 'Admin User', 'admin@demo.com', '$2b$12$zv.joA0OR.gyx82ZkJ3k8e7Tei1TpXRGccgGYThVAh59hRwNg2hSe', 'admin');
-- password above is: admin123

INSERT INTO asset_categories (org_id, name) VALUES (1, 'Medical Equipment'), (1, 'Furniture'), (1, 'IT Equipment'), (1, 'Vehicles');
INSERT INTO assets (org_id, category_id, asset_tag, name, location, status, purchase_date, purchase_price, current_value) VALUES
(1, 1, 'ASSET-001', 'X-Ray Machine', 'Radiology Room', 'active', '2022-01-15', 15000.00, 12000.00),
(1, 1, 'ASSET-002', 'ECG Monitor', 'Ward A', 'active', '2023-03-10', 3500.00, 3000.00),
(1, 2, 'ASSET-003', 'Reception Desk', 'Reception', 'active', '2021-06-01', 800.00, 600.00),
(1, 3, 'ASSET-004', 'Dell Laptop', 'Admin Office', 'active', '2023-08-20', 1200.00, 1000.00);

INSERT INTO accounts (org_id, name, type, balance) VALUES
(1, 'Cash on Hand', 'cash', 5000.00),
(1, 'Bank Account', 'bank', 45000.00);

INSERT INTO finance_categories (org_id, name, type) VALUES
(1, 'Consultation Fees', 'income'),
(1, 'Lab Tests', 'income'),
(1, 'Salaries', 'expense'),
(1, 'Medical Supplies', 'expense'),
(1, 'Utilities', 'expense'),
(1, 'Rent', 'expense');

INSERT INTO transactions (org_id, account_id, category_id, type, amount, description, transaction_date, recorded_by) VALUES
(1, 2, 1, 'income', 2500.00, 'Weekly consultation fees', '2026-02-17', 1),
(1, 2, 2, 'income', 1200.00, 'Lab test revenue', '2026-02-18', 1),
(1, 1, 4, 'expense', 800.00, 'Medical supplies restock', '2026-02-19', 1),
(1, 2, 3, 'expense', 8000.00, 'Monthly salaries', '2026-02-20', 1),
(1, 2, 6, 'expense', 2000.00, 'Monthly rent', '2026-02-21', 1);

GRANT ALL PRIVILEGES ON finance_db.* TO 'finance_user'@'%';
FLUSH PRIVILEGES;
