"""
Create Shopify-related tables in Supabase
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def create_shopify_tables():
    """Create Shopify-related tables"""
    
    # 1. Shopify Configuration Table
    print("Creating shopify_config table...")
    try:
        supabase.rpc('execute_sql', {
            'sql': '''
            CREATE TABLE IF NOT EXISTS shopify_config (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                shop_domain TEXT NOT NULL,
                access_token TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id)
            );
            
            -- Row Level Security
            ALTER TABLE shopify_config ENABLE ROW LEVEL SECURITY;
            
            CREATE POLICY "Users can only access their own config" ON shopify_config
                FOR ALL USING (auth.uid() = user_id);
            '''
        }).execute()
        print("✅ shopify_config table created")
    except Exception as e:
        print(f"❌ Error creating shopify_config table: {e}")
    
    # 2. Shopify Orders Table
    print("Creating shopify_orders table...")
    try:
        supabase.rpc('execute_sql', {
            'sql': '''
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
            
            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_shopify_orders_shopify_id ON shopify_orders(shopify_id);
            CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at ON shopify_orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_shopify_orders_financial_status ON shopify_orders(financial_status);
            CREATE INDEX IF NOT EXISTS idx_shopify_orders_fulfillment_status ON shopify_orders(fulfillment_status);
            
            -- Row Level Security
            ALTER TABLE shopify_orders ENABLE ROW LEVEL SECURITY;
            
            CREATE POLICY "All authenticated users can read orders" ON shopify_orders
                FOR SELECT USING (auth.role() = 'authenticated');
            
            CREATE POLICY "Only service role can write orders" ON shopify_orders
                FOR ALL USING (auth.role() = 'service_role');
            '''
        }).execute()
        print("✅ shopify_orders table created")
    except Exception as e:
        print(f"❌ Error creating shopify_orders table: {e}")
    
    # 3. Shopify Sync Status Table
    print("Creating shopify_sync_status table...")
    try:
        supabase.rpc('execute_sql', {
            'sql': '''
            CREATE TABLE IF NOT EXISTS shopify_sync_status (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                last_sync TIMESTAMPTZ,
                orders_synced INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id)
            );
            
            -- Row Level Security
            ALTER TABLE shopify_sync_status ENABLE ROW LEVEL SECURITY;
            
            CREATE POLICY "Users can only access their own sync status" ON shopify_sync_status
                FOR ALL USING (auth.uid() = user_id);
            '''
        }).execute()
        print("✅ shopify_sync_status table created")
    except Exception as e:
        print(f"❌ Error creating shopify_sync_status table: {e}")

    print("\n🎉 All Shopify tables created successfully!")

if __name__ == "__main__":
    create_shopify_tables()
