#!/usr/bin/env python3
"""
This file shows the key changes needed to integrate Supabase into app.py
Copy these changes into your main app.py file after creating the users table
"""

# Add these imports at the top of app.py:
"""
from dotenv import load_dotenv
from supabase_client import supabase, SupabaseUserManager

# Load environment variables
load_dotenv()
"""

# Replace the JSON file-based user functions with these Supabase versions:

def get_current_user_from_session(session_id: str):
    """Get current user from session using Supabase"""
    if not session_id:
        return None
    
    try:
        user = SupabaseUserManager.get_user_by_session(session_id)
        return user
    except Exception as e:
        print(f"Error getting user from session: {e}")
        return None

def authenticate_user(email: str, password: str):
    """Authenticate user using Supabase"""
    try:
        user = SupabaseUserManager.get_user_by_email(email)
        if user and verify_password(password, user.get('password_hash', '')):
            return user
        return None
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None

def create_user_session(user_id: str):
    """Create user session using Supabase"""
    try:
        session_id = secrets.token_urlsafe(32)
        
        # Update user with session_id
        SupabaseUserManager.update_user(user_id, {
            'session_id': session_id,
            'last_login': datetime.now().isoformat(),
            'login_count': supabase.table('users').select('login_count').eq('id', user_id).execute().data[0]['login_count'] + 1
        })
        
        return session_id
    except Exception as e:
        print(f"Error creating session: {e}")
        return None

def get_user_stats():
    """Get user statistics from Supabase"""
    try:
        all_users = SupabaseUserManager.get_all_users()
        
        total_users = len(all_users)
        active_users = len([u for u in all_users if u.get('status') == 'active'])
        inactive_users = total_users - active_users
        admin_count = len([u for u in all_users if u.get('role') in ['owner', 'admin']])
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": inactive_users,
            "admin_count": admin_count
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return {"total_users": 0, "active_users": 0, "inactive_users": 0, "admin_count": 0}

# Update the user API endpoints to use Supabase:

def get_users_api():
    """API endpoint to get users from Supabase"""
    try:
        users = SupabaseUserManager.get_all_users()
        roles = list(set([user.get('role', 'employee') for user in users]))
        
        return JSONResponse(content={
            "success": True,
            "users": users,
            "roles": roles
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

# Additional helper functions for Supabase integration:

def migrate_json_to_supabase():
    """One-time migration from JSON files to Supabase"""
    try:
        import json
        
        # Read existing JSON data
        with open('data/users_database.json', 'r') as f:
            users_data = json.load(f)
        
        with open('data/users_auth.json', 'r') as f:
            auth_data = json.load(f)
        
        # Migrate each user
        for user_id, user_info in users_data.items():
            auth_info = auth_data.get(user_id, {})
            
            supabase_user = {
                'id': user_id,
                'name': user_info.get('name', ''),
                'email': user_info.get('email', f"{user_id}@company.com"),
                'password_hash': auth_info.get('password_hash', ''),
                'role': user_info.get('role', 'employee'),
                'status': 'active' if user_info.get('status') == 'active' else 'inactive',
                'phone': user_info.get('phone', ''),
                'photo_url': user_info.get('photo', ''),
                'icon': user_info.get('icon', '👤'),
                'icon_color': user_info.get('icon_color', '#6b7280'),
                'permissions': user_info.get('permissions', [])
            }
            
            # Remove None values
            supabase_user = {k: v for k, v in supabase_user.items() if v is not None}
            
            # Insert into Supabase
            SupabaseUserManager.create_user(supabase_user)
        
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Migration error: {e}")
        return False

print("""
🔧 SUPABASE INTEGRATION READY!

To complete the integration:

1. Go to your Supabase dashboard: https://supabase.com/dashboard
2. Navigate to SQL Editor
3. Run the CREATE TABLE statement from create_supabase_tables.py
4. Copy the functions from app_supabase_integration.py into your main app.py
5. Replace JSON file operations with Supabase calls
6. Run the migration script to move existing data

The key changes are:
- Import supabase_client at the top
- Replace get_current_user_from_session() function
- Replace authenticate_user() function  
- Replace create_user_session() function
- Update all user CRUD operations to use SupabaseUserManager

Ready to proceed with the integration!
""")
