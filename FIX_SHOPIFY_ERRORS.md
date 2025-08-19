# 🔧 Fix Shopify Integration Errors

## STEP 1: Set up Database Tables (REQUIRED FIRST)

The main issue is that the database tables don't exist yet. You need to create them in Supabase.

### Go to Supabase Dashboard:
1. Open: https://supabase.com/dashboard
2. Select your project
3. Go to **SQL Editor** (left sidebar)
4. Click **New Query**
5. Copy and paste this SQL code:

```sql
-- Shopify Integration Database Tables
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
```

6. Click **Run** to execute the SQL
7. You should see "Success. No rows returned" message

## STEP 2: Add Encryption Key to .env file

Add this line to your `.env` file (create the file if it doesn't exist):

```
SHOPIFY_ENCRYPTION_KEY=SUAqfNFtRWvcI44O8g6Tj1xTD6lUFb4ko_7TdMrgOjtk=
```

## STEP 3: Restart the Server

After completing the database setup:

1. Stop the current server (Ctrl+C)
2. Restart: `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

## STEP 4: Test the Connection

1. Go to: http://localhost:8000/shopify/settings
2. Enter your store name (e.g., "407f1f-4")
3. Enter your Shopify access token
4. Click "Connect Store"

## What the errors mean:

### ❌ "Could not find the table 'public.shopify_config'"
- **Cause**: Database tables don't exist
- **Fix**: Run the SQL script above in Supabase

### ❌ "Error connecting: Unexpected token 'I', "Internal S"... is not valid JSON"
- **Cause**: The frontend is receiving an HTML error page instead of JSON
- **Fix**: This will be resolved once the database tables are created

## After Setup Success:

✅ **Connection Status** will show green
✅ **Store information** will load automatically
✅ **Sync Now** button will be enabled
✅ **Dashboard** will show real Shopify data
✅ **Orders sync** every 10 minutes automatically

## Need Help?

If you see any other errors after completing these steps, let me know and I'll help debug them!
