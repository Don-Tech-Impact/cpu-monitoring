CREATE DATABASE IF NOT EXISTS finance_db;
USE finance_db;

CREATE TABLE IF NOT EXISTS servers (
    id  INT AUTO_INCREMENT PRIMARY KEY,
    server_name VARCHAR(50) NOT NULL,
    ip_address VARCHAR(10) NOT NULL,
    server_status VARCHAR(10) NOT NULL,
    cpu_usage DECIMAL(5,2) NOT NULL,
    memory_usage DECIMAL(5,2) NOT NULL,
    disk_usage DECIMAL(5,2) NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO servers (server_name, ip_address, server_status, cpu_usage, memory_usage, disk_usage) VALUES
('web-01', '10.0.1.10', 'active', 45.5, 68.2, 75.1),
('db-01', '10.0.1.20', 'active', 55.3, 72.4, 80.5),
('cache-01', '10.0.1.30', 'inactive', 0.0, 0.0, 0.0),
('web-02', '10.0.1.40', 'active', 35.2, 60.1, 70.3);


GRANT ALL PRIVILEGES ON finance_db.* TO 'user'@'%';
FLUSH PRIVILEGES;