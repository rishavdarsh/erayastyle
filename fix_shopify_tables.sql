-- Fix Shopify tables to work without auth system
-- Run this in Supabase SQL Editor

-- Drop existing tables if they exist
DROP TABLE IF EXISTS shopify_sync_status;
DROP TABLE IF EXISTS shopify_orders;
DROP TABLE IF EXISTS shopify_config;

-- 1. Shopify Configuration Table (NO AUTH DEPENDENCY)
CREATE TABLE shopify_config (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    shop_domain TEXT NOT NULL,
    access_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- 2. Shopify Orders Table
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

-- 3. Shopify Sync Status Table (NO AUTH DEPENDENCY)
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_shopify_orders_shopify_id ON shopify_orders(shopify_id);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_financial_status ON shopify_orders(financial_status);
CREATE INDEX IF NOT EXISTS idx_shopify_orders_fulfillment_status ON shopify_orders(fulfillment_status);

-- Row Level Security (DISABLED for simplicity)
-- We're not using RLS since there's no auth system
