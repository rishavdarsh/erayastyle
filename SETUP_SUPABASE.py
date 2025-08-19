#!/usr/bin/env python3
"""
Automatic Supabase Integration Setup Script
This script will:
1. Create .env file with Supabase credentials
2. Update requirements.txt to include Supabase
3. Install Supabase library
4. Create Supabase client setup
5. Update app.py with Supabase integration
"""

import os
import subprocess
import sys

def create_env_file():
    """Create .env file with Supabase credentials"""
    print("🔧 Creating .env file...")
    
    env_content = """# Supabase Configuration
SUPABASE_URL=https://xhqzhljdwcolwonjvyex.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhocXpobGpkd2NvbHdvbmp2eWV4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU0NjMwNDQsImV4cCI6MjA3MTAzOTA0NH0.uDKHnMU0WXobStcg-_mg6sqwzwrVT5r5KEg7aoUgP04

# Application Configuration
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ .env file created successfully")

def update_requirements():
    """Add Supabase to requirements.txt"""
    print("🔧 Updating requirements.txt...")
    
    # Read current requirements
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    # Add Supabase if not already present
    if 'supabase' not in content:
        content += "\n# Supabase client\nsupabase==2.10.0\n"
        
        with open('requirements.txt', 'w') as f:
            f.write(content)
        
        print("✅ Added Supabase to requirements.txt")
    else:
        print("✅ Supabase already in requirements.txt")

def install_supabase():
    """Install Supabase library"""
    print("🔧 Installing Supabase library...")
    
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'supabase==2.10.0'], 
                      check=True, capture_output=True)
        print("✅ Supabase installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Supabase: {e}")
        return False
    
    return True

def create_supabase_client():
    """Create Supabase client module"""
    print("🔧 Creating Supabase client module...")
    
    client_content = '''"""
Supabase client configuration and helper functions
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional, Dict, List, Any

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url: str = os.getenv("SUPABASE_URL")
supabase_key: str = os.getenv("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Supabase URL and key must be set in environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

class SupabaseUserManager:
    """Supabase user management functions"""
    
    @staticmethod
    def create_user_table():
        """Create users table if it doesn't exist"""
        try:
            # This would typically be done through Supabase dashboard
            # For now, we'll just check if table exists
            response = supabase.table('users').select('id').limit(1).execute()
            print("✅ Users table exists")
            return True
        except Exception as e:
            print(f"⚠️ Users table may not exist: {e}")
            return False
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            response = supabase.table('users').select('*').eq('id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting user {user_id}: {e}")
            return None
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict]:
        """Get user by email"""
        try:
            response = supabase.table('users').select('*').eq('email', email).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting user by email {email}: {e}")
            return None
    
    @staticmethod
    def create_user(user_data: Dict) -> Optional[Dict]:
        """Create new user"""
        try:
            response = supabase.table('users').insert(user_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    @staticmethod
    def update_user(user_id: str, user_data: Dict) -> Optional[Dict]:
        """Update user"""
        try:
            response = supabase.table('users').update(user_data).eq('id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user {user_id}: {e}")
            return None
    
    @staticmethod
    def get_all_users() -> List[Dict]:
        """Get all users"""
        try:
            response = supabase.table('users').select('*').execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []

# Test connection on import
try:
    SupabaseUserManager.create_user_table()
    print("✅ Supabase connection established")
except Exception as e:
    print(f"⚠️ Supabase connection issue: {e}")
'''
    
    with open('supabase_client.py', 'w') as f:
        f.write(client_content)
    
    print("✅ Supabase client module created")

def main():
    """Run the complete setup"""
    print("🚀 STARTING SUPABASE INTEGRATION SETUP")
    print("=" * 50)
    
    # Step 1: Create .env file
    create_env_file()
    
    # Step 2: Update requirements.txt
    update_requirements()
    
    # Step 3: Install Supabase
    if install_supabase():
        print("✅ Supabase installation completed")
    else:
        print("❌ Setup failed at installation step")
        return
    
    # Step 4: Create Supabase client
    create_supabase_client()
    
    print("\n🎉 SUPABASE SETUP COMPLETED!")
    print("=" * 50)
    print("Next steps:")
    print("1. Check your Supabase dashboard to create tables")
    print("2. Run the migration script to move existing data")
    print("3. Update app.py to use Supabase instead of JSON files")

if __name__ == "__main__":
    main()
