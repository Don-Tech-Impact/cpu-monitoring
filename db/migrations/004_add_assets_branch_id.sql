-- Migration: Add branch_id column to assets table
-- This migration is idempotent and can be run multiple times safely

USE finance_db;

-- Check if column exists and add it if it doesn't
SET @dbname = DATABASE();
SET @tablename = 'assets';
SET @columnname = 'branch_id';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT ''Column already exists, skipping'';',
  'ALTER TABLE assets ADD COLUMN branch_id INT NULL AFTER org_id, ADD FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL;'
));

PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;
