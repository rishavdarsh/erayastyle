#!/usr/bin/env python3
"""
Create Supabase tables and migrate existing data
"""

import json
from supabase_client import supabase
from datetime import datetime

def create_users_table():
    """Create users table in Supabase"""
    print("Creating users table in Supabase...")
    
    # SQL to create users table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        email VARCHAR UNIQUE NOT NULL,
        password_hash VARCHAR NOT NULL,
        role VARCHAR NOT NULL DEFAULT 'employee',
        status VARCHAR NOT NULL DEFAULT 'active',
        phone VARCHAR,
        joining_date DATE,
        shift VARCHAR,
        manager_id VARCHAR,
        address TEXT,
        city VARCHAR,
        state VARCHAR,
        zip VARCHAR,
        emergency_contact_name VARCHAR,
        emergency_contact_relation VARCHAR,
        emergency_contact_phone VARCHAR,
        emergency_contact_email VARCHAR,
        photo_url VARCHAR,
        icon VARCHAR DEFAULT '👤',
        icon_color VARCHAR DEFAULT '#6b7280',
        last_login TIMESTAMP,
        login_count INTEGER DEFAULT 0,
        session_id VARCHAR,
        permissions TEXT[], -- Array of permission strings
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    -- Create RLS policies
    ALTER TABLE users ENABLE ROW LEVEL SECURITY;
    
    -- Policy for authenticated users to read all users
    CREATE POLICY "Users can read all users" ON users
        FOR SELECT USING (auth.role() = 'authenticated');
    
    -- Policy for service role to do everything
    CREATE POLICY "Service role can do everything" ON users
        FOR ALL USING (auth.role() = 'service_role');
    
    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
    CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
    """
    
    try:
        # Execute SQL using Supabase
        response = supabase.rpc('execute_sql', {'sql': create_table_sql}).execute()
        print("✅ Users table created successfully")
        return True
    except Exception as e:
        print(f"⚠️ Error creating table: {e}")
        print("💡 You may need to create the table manually in Supabase dashboard")
        return False

def migrate_existing_users():
    """Migrate users from JSON files to Supabase"""
    print("Migrating existing users to Supabase...")
    
    try:
        # Read existing user data
        with open('data/users_database.json', 'r') as f:
            users_data = json.load(f)
        
        with open('data/users_auth.json', 'r') as f:
            auth_data = json.load(f)
        
        migrated_count = 0
        
        for user_id, user_info in users_data.items():
            # Get auth info for this user
            auth_info = auth_data.get(user_id, {})
            
            # Prepare user data for Supabase
            supabase_user = {
                'id': user_id,
                'name': user_info.get('name', ''),
                'email': user_info.get('email', f"{user_id}@company.com"),
                'password_hash': auth_info.get('password_hash', ''),
                'role': user_info.get('role', 'employee'),
                'status': 'active' if user_info.get('status') == 'active' else 'inactive',
                'phone': user_info.get('phone', ''),
                'joining_date': user_info.get('joining_date'),
                'shift': user_info.get('shift'),
                'manager_id': user_info.get('manager'),
                'address': user_info.get('address', ''),
                'city': user_info.get('city', ''),
                'state': user_info.get('state', ''),
                'zip': user_info.get('zip', ''),
                'emergency_contact_name': user_info.get('emergency_contact_name', ''),
                'emergency_contact_relation': user_info.get('emergency_contact_relation', ''),
                'emergency_contact_phone': user_info.get('emergency_contact_phone', ''),
                'emergency_contact_email': user_info.get('emergency_contact_email', ''),
                'photo_url': user_info.get('photo', ''),
                'icon': user_info.get('icon', '👤'),
                'icon_color': user_info.get('icon_color', '#6b7280'),
                'last_login': user_info.get('last_login'),
                'login_count': user_info.get('login_count', 0),
                'session_id': auth_info.get('session_id'),
                'permissions': user_info.get('permissions', [])
            }
            
            # Remove None values
            supabase_user = {k: v for k, v in supabase_user.items() if v is not None}
            
            try:
                # Insert user into Supabase
                response = supabase.table('users').insert(supabase_user).execute()
                print(f"✅ Migrated user: {user_info.get('name', user_id)}")
                migrated_count += 1
            except Exception as e:
                print(f"⚠️ Error migrating user {user_id}: {e}")
        
        print(f"✅ Migration completed: {migrated_count} users migrated")
        return True
        
    except FileNotFoundError:
        print("⚠️ No existing user files found - starting fresh")
        return True
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False

def test_supabase_operations():
    """Test basic Supabase operations"""
    print("Testing Supabase operations...")
    
    try:
        # Test reading users
        response = supabase.table('users').select('id, name, email').limit(5).execute()
        users = response.data
        
        print(f"✅ Found {len(users)} users in database")
        for user in users:
            print(f"  - {user.get('name', 'Unknown')} ({user.get('email', 'No email')})")
        
        return True
    except Exception as e:
        print(f"❌ Error testing operations: {e}")
        return False

def main():
    """Run the complete setup"""
    print("🚀 SUPABASE DATABASE SETUP")
    print("=" * 50)
    
    # Note: Table creation might need to be done in Supabase dashboard
    print("📋 MANUAL STEP REQUIRED:")
    print("1. Go to your Supabase dashboard")
    print("2. Navigate to SQL Editor")
    print("3. Run the SQL below to create the users table:")
    print()
    print("CREATE TABLE IF NOT EXISTS users (")
    print("    id VARCHAR PRIMARY KEY,")
    print("    name VARCHAR NOT NULL,")
    print("    email VARCHAR UNIQUE NOT NULL,")
    print("    password_hash VARCHAR NOT NULL,")
    print("    role VARCHAR NOT NULL DEFAULT 'employee',")
    print("    status VARCHAR NOT NULL DEFAULT 'active',")
    print("    phone VARCHAR,")
    print("    joining_date DATE,")
    print("    shift VARCHAR,")
    print("    manager_id VARCHAR,")
    print("    address TEXT,")
    print("    city VARCHAR,")
    print("    state VARCHAR,")
    print("    zip VARCHAR,")
    print("    emergency_contact_name VARCHAR,")
    print("    emergency_contact_relation VARCHAR,")
    print("    emergency_contact_phone VARCHAR,")
    print("    emergency_contact_email VARCHAR,")
    print("    photo_url VARCHAR,")
    print("    icon VARCHAR DEFAULT '👤',")
    print("    icon_color VARCHAR DEFAULT '#6b7280',")
    print("    last_login TIMESTAMP,")
    print("    login_count INTEGER DEFAULT 0,")
    print("    session_id VARCHAR,")
    print("    permissions TEXT[],")
    print("    created_at TIMESTAMP DEFAULT NOW(),")
    print("    updated_at TIMESTAMP DEFAULT NOW()")
    print(");")
    print()
    print("After creating the table, run this script again to migrate data.")
    
    # Try to test if table exists
    try:
        response = supabase.table('users').select('id').limit(1).execute()
        print("✅ Users table already exists!")
        
        # Migrate existing data
        migrate_existing_users()
        
        # Test operations
        test_supabase_operations()
        
    except Exception as e:
        print(f"⚠️ Table doesn't exist yet. Please create it manually first.")

if __name__ == "__main__":
    main()
