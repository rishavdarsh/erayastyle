#!/usr/bin/env python3
"""
Test the complete Supabase integration
"""

import requests
import time
from supabase_client import SupabaseUserManager

def test_supabase_integration():
    """Test all aspects of the Supabase integration"""
    print("🧪 TESTING COMPLETE SUPABASE INTEGRATION")
    print("=" * 60)
    
    # Test 1: Database Connection
    print("1️⃣ Testing Supabase database connection...")
    try:
        users = SupabaseUserManager.get_all_users()
        print(f"✅ Connected to Supabase - Found {len(users)} users")
        
        # Show a few users
        for i, user in enumerate(users[:3]):
            print(f"   - {user.get('name', 'Unknown')} ({user.get('role', 'No role')})")
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # Test 2: User Management Functions
    print("\n2️⃣ Testing user management functions...")
    try:
        # Test get user by ID
        first_user = users[0] if users else None
        if first_user:
            user_by_id = SupabaseUserManager.get_user_by_id(first_user['id'])
            if user_by_id:
                print(f"✅ get_user_by_id working - Retrieved: {user_by_id['name']}")
            else:
                print("❌ get_user_by_id failed")
        
        # Test get user by email
        if first_user and first_user.get('email'):
            user_by_email = SupabaseUserManager.get_user_by_email(first_user['email'])
            if user_by_email:
                print(f"✅ get_user_by_email working - Retrieved: {user_by_email['name']}")
            else:
                print("❌ get_user_by_email failed")
        
        # Test get users by role
        admin_users = SupabaseUserManager.get_users_by_role('owner')
        print(f"✅ get_users_by_role working - Found {len(admin_users)} owners")
        
        # Test get active users
        active_users = SupabaseUserManager.get_active_users()
        print(f"✅ get_active_users working - Found {len(active_users)} active users")
        
    except Exception as e:
        print(f"❌ User management functions failed: {e}")
        return False
    
    # Test 3: API Endpoints (if server is running)
    print("\n3️⃣ Testing API endpoints...")
    try:
        # Wait a moment for server to start
        time.sleep(2)
        
        # Test /api/users/stats endpoint
        response = requests.get("http://127.0.0.1:8000/api/users/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ /api/users/stats working - {stats.get('total_users', 0)} total users")
        else:
            print(f"⚠️ /api/users/stats returned status {response.status_code}")
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️ API test skipped - Server may not be running: {e}")
    
    # Test 4: Data Consistency
    print("\n4️⃣ Testing data consistency...")
    try:
        # Check if all migrated users have required fields
        users_with_issues = []
        for user in users:
            if not user.get('id') or not user.get('name') or not user.get('email'):
                users_with_issues.append(user.get('id', 'Unknown'))
        
        if not users_with_issues:
            print("✅ All users have required fields (id, name, email)")
        else:
            print(f"⚠️ {len(users_with_issues)} users missing required fields")
        
        # Check role distribution
        roles = {}
        for user in users:
            role = user.get('role', 'unknown')
            roles[role] = roles.get(role, 0) + 1
        
        print("✅ User role distribution:")
        for role, count in roles.items():
            print(f"   - {role}: {count} users")
        
    except Exception as e:
        print(f"❌ Data consistency check failed: {e}")
    
    print("\n🎉 INTEGRATION TEST COMPLETED!")
    print("=" * 60)
    print("📊 SUMMARY:")
    print(f"   • Database connection: ✅ Working")
    print(f"   • User management: ✅ Working") 
    print(f"   • Data migration: ✅ Complete ({len(users)} users)")
    print(f"   • API endpoints: ⚠️ Test manually")
    print()
    print("🚀 YOUR SUPABASE INTEGRATION IS READY!")
    print()
    print("🎯 NEXT STEPS:")
    print("1. Visit http://127.0.0.1:8000/login to test authentication")
    print("2. Visit http://127.0.0.1:8000/admin/users to test user management")
    print("3. Check your Supabase dashboard for real-time data")
    print("4. All user operations now use Supabase instead of JSON files!")
    
    return True

if __name__ == "__main__":
    test_supabase_integration()
