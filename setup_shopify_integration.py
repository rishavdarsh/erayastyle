"""
Setup script for Shopify integration
Run this to complete the Shopify integration setup
"""
import os
from pathlib import Path

def create_env_template():
    """Create .env template if it doesn't exist"""
    env_path = Path(".env")
    
    if not env_path.exists():
        env_content = """# Supabase Configuration
SUPABASE_URL=https://xhqzhljdwcolwonjvyex.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhocXpobGpkd2NvbHdvbmp2eWV4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczNzA2ODU3MywiZXhwIjoyMDUyNjQ0NTczfQ.FGQ02lCGIEqtxYUNaNHvlDGwu8iZyG2wjQHq7-tn-vE
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhocXpobGpkd2NvbHdvbmp2eWV4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzcwNjg1NzMsImV4cCI6MjA1MjY0NDU3M30.6uHfYZJqYr-sDW_3YvWkqLQLpxcAMVQ7_wG4Lz3FTEk

# Application Configuration  
DEBUG=false
SECRET_KEY=your-secret-key-change-this-in-production
SESSION_EXPIRY_DAYS=7
REMEMBER_ME_DAYS=30

# Shopify Integration
SHOPIFY_ENCRYPTION_KEY=ng8S2FUS3ctgZ77gVC9H64jy0YdB0-e-P-gSx6uFbJ3I=

# Optional Features
USE_JSON=false
ENABLE_WEBSOCKETS=true"""
        
        try:
            with open(env_path, 'w') as f:
                f.write(env_content)
            print(f"✅ Created .env file with Shopify encryption key")
            return True
        except Exception as e:
            print(f"❌ Error creating .env file: {e}")
            return False
    else:
        # Check if encryption key exists
        with open(env_path, 'r') as f:
            content = f.read()
        
        if "SHOPIFY_ENCRYPTION_KEY" not in content:
            print("⚠️  Please add this line to your .env file:")
            print("SHOPIFY_ENCRYPTION_KEY=ng8S2FUS3ctgZ77gVC9H64jy0YdB0-e-P-gSx6uFbJ3I=")
            return False
        else:
            print("✅ .env file already configured with Shopify encryption key")
            return True

def print_setup_instructions():
    """Print setup instructions"""
    print("""
🚀 SHOPIFY INTEGRATION SETUP COMPLETE!

📋 NEXT STEPS:

1. 📊 DATABASE SETUP (REQUIRED):
   - Go to your Supabase Dashboard: https://supabase.com/dashboard
   - Navigate to SQL Editor
   - Copy and paste the content from 'shopify_tables.sql'
   - Run the SQL to create tables

2. 🛒 SHOPIFY SETUP:
   - In your Shopify Admin, go to: Apps → Develop apps
   - Create a new private app
   - Enable Admin API access
   - Copy the Access Token

3. 🔗 CONNECT YOUR STORE:
   - Start the server: python -m uvicorn main:app --reload
   - Go to: http://localhost:8000/shopify/settings
   - Enter your store name (e.g., "407f1f-4")
   - Enter your access token
   - Click "Connect Store"

4. 🔄 AUTOMATIC FEATURES:
   ✅ Orders sync every 10 minutes automatically
   ✅ Dashboard shows real Shopify data
   ✅ Secure credential storage
   ✅ Manual sync option available
   ✅ Background sync service

5. 📈 VIEW REAL DATA:
   - Dashboard: Real order statistics and revenue
   - Orders page: Live Shopify orders
   - Automatic updates without webhooks

🎉 Your Shopify integration is ready to use!
""")

def main():
    """Main setup function"""
    print("🔧 Setting up Shopify Integration...")
    
    # Create/check .env file
    env_ok = create_env_template()
    
    # Print instructions
    print_setup_instructions()
    
    if not env_ok:
        print("\n⚠️  Please complete the .env setup before starting the server.")
    else:
        print("\n✅ Setup complete! You can now start the server and connect your Shopify store.")

if __name__ == "__main__":
    main()
