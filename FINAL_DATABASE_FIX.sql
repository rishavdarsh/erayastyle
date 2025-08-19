-- 🚨 FINAL DATABASE FIX - This will completely solve the UUID error
-- Copy this ENTIRE script and run it in Supabase SQL Editor

-- Step 1: Drop all existing tables (this removes the UUID constraint)
DROP TABLE IF EXISTS shopify_sync_status CASCADE;
DROP TABLE IF EXISTS shopify_orders CASCADE; 
DROP TABLE IF EXISTS shopify_config CASCADE;

-- Step 2: Create new tables with TEXT user_id (not UUID)
CREATE TABLE shopify_config (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    shop_domain TEXT NOT NULL,
    access_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE TABLE shopify_orders (
    id SERIAL PRIMARY KEY,
    shopify_id TEXT UNIQUE NOT NULL,
    order_number TEXT,
    email TEXT,
    total_price DECIMAL(10,2),
    currency TEXT DEFAULT 'USD',
    financial_status TEXT,
    fulfillment_status TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    customer_data JSONB,
    line_items JSONB,
    shipping_address JSONB,
    billing_address JSONB,
    tags TEXT,
    note TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shopify_sync_status (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    last_sync TIMESTAMPTZ,
    orders_synced INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Step 3: Create indexes for performance
CREATE INDEX idx_shopify_orders_shopify_id ON shopify_orders(shopify_id);
CREATE INDEX idx_shopify_orders_created_at ON shopify_orders(created_at);
CREATE INDEX idx_shopify_config_user_id ON shopify_config(user_id);
CREATE INDEX idx_shopify_sync_status_user_id ON shopify_sync_status(user_id);

-- Step 4: Insert a default sync status record
INSERT INTO shopify_sync_status (user_id, status) 
VALUES ('default_user', 'pending') 
ON CONFLICT (user_id) DO NOTHING;

-- Verification: Check the tables were created correctly
SELECT 'shopify_config' as table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'shopify_config' AND column_name = 'user_id'
UNION ALL
SELECT 'shopify_sync_status' as table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'shopify_sync_status' AND column_name = 'user_id';
