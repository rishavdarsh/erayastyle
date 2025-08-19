-- Shopify Integration Database Tables
-- Run this SQL in your Supabase SQL Editor

-- 1. Shopify Configuration Table
CREATE TABLE IF NOT EXISTS shopify_config (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    shop_domain TEXT NOT NULL,
    access_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- 2. Shopify Orders Table
CREATE TABLE IF NOT EXISTS shopify_orders (
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

-- 3. Shopify Sync Status Table
CREATE TABLE IF NOT EXISTS shopify_sync_status (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    last_sync TIMESTAMPTZ,
    orders_synced INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_shopify_orders_shopify_id ON shopify_orders(shopify_id);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_financial_status ON shopify_orders(financial_status);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_fulfillment_status ON shopify_orders(fulfillment_status);

-- Row Level Security (RLS)
ALTER TABLE shopify_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE shopify_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE shopify_sync_status ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can manage their own Shopify config" ON shopify_config
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "All authenticated users can read orders" ON shopify_orders
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Service role can manage orders" ON shopify_orders
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users can manage their own sync status" ON shopify_sync_status
    FOR ALL USING (auth.uid() = user_id);
