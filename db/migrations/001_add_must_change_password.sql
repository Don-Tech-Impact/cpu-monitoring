-- Migration: Add must_change_password column if it doesn't exist
-- This migration is idempotent and can be run multiple times safely

USE finance_db;

-- Check if column exists and add it if it doesn't
SET @dbname = DATABASE();
SET @tablename = 'users';
SET @columnname = 'must_change_password';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT ''Column already exists, skipping'';',
  'ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE AFTER is_superadmin;'
));

PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;
