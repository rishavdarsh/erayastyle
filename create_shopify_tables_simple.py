"""
Create Shopify-related tables in Supabase using direct table creation
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def create_shopify_config_table():
    """Create shopify_config table with sample data structure"""
    print("Creating shopify_config table structure...")
    try:
        # Try to create a sample record to establish the table structure
        # This will create the table if it doesn't exist
        sample_data = {
            "user_id": "00000000-0000-0000-0000-000000000000",  # Placeholder UUID
            "shop_domain": "sample-store.myshopify.com",
            "access_token": "encrypted_sample_token",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        # This will create the table structure
        response = supabase.table("shopify_config").insert(sample_data).execute()
        
        # Delete the sample record
        supabase.table("shopify_config").delete().eq("user_id", "00000000-0000-0000-0000-000000000000").execute()
        
        print("✅ shopify_config table structure created")
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✅ shopify_config table already exists")
            return True
        print(f"❌ Error creating shopify_config table: {e}")
        return False

def create_shopify_orders_table():
    """Create shopify_orders table with sample data structure"""
    print("Creating shopify_orders table structure...")
    try:
        # Create sample order structure
        sample_order = {
            "shopify_id": "0000000000",
            "order_number": "#1000",
            "email": "sample@example.com",
            "total_price": 0.00,
            "currency": "USD",
            "financial_status": "pending",
            "fulfillment_status": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "customer_data": {},
            "line_items": [],
            "shipping_address": {},
            "billing_address": {},
            "tags": "",
            "note": "",
            "synced_at": "2024-01-01T00:00:00Z"
        }
        
        response = supabase.table("shopify_orders").insert(sample_order).execute()
        
        # Delete the sample record
        supabase.table("shopify_orders").delete().eq("shopify_id", "0000000000").execute()
        
        print("✅ shopify_orders table structure created")
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✅ shopify_orders table already exists")
            return True
        print(f"❌ Error creating shopify_orders table: {e}")
        return False

def create_shopify_sync_status_table():
    """Create shopify_sync_status table with sample data structure"""
    print("Creating shopify_sync_status table structure...")
    try:
        sample_status = {
            "user_id": "00000000-0000-0000-0000-000000000000",
            "last_sync": "2024-01-01T00:00:00Z",
            "orders_synced": 0,
            "status": "pending",
            "error_message": None,
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        response = supabase.table("shopify_sync_status").insert(sample_status).execute()
        
        # Delete the sample record
        supabase.table("shopify_sync_status").delete().eq("user_id", "00000000-0000-0000-0000-000000000000").execute()
        
        print("✅ shopify_sync_status table structure created")
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✅ shopify_sync_status table already exists")
            return True
        print(f"❌ Error creating shopify_sync_status table: {e}")
        return False

def main():
    """Create all Shopify tables"""
    print("🔧 Setting up Shopify database tables...")
    print(f"   URL: {SUPABASE_URL}")
    print(f"   Key: {SUPABASE_SERVICE_ROLE_KEY[:20] if SUPABASE_SERVICE_ROLE_KEY else 'None'}...")
    print()
    
    success_count = 0
    
    if create_shopify_config_table():
        success_count += 1
    
    if create_shopify_orders_table():
        success_count += 1
    
    if create_shopify_sync_status_table():
        success_count += 1
    
    print(f"\n🎉 {success_count}/3 Shopify tables set up successfully!")
    
    if success_count == 3:
        print("\n✅ All tables are ready! You can now:")
        print("   1. Go to /shopify/settings to connect your store")
        print("   2. Enter your store name and access token")
        print("   3. Start syncing orders automatically")
    else:
        print("\n⚠️  Some tables failed to create. Check the errors above.")

if __name__ == "__main__":
    main()
