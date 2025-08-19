#!/usr/bin/env python3
"""
Integrate Supabase into app.py by replacing JSON-based functions with Supabase calls
"""

import re

def integrate_supabase_into_app():
    """Update app.py to use Supabase instead of JSON files"""
    print("🔧 INTEGRATING SUPABASE INTO APP.PY")
    print("=" * 50)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Step 1: Add Supabase imports after existing imports
        print("📦 Adding Supabase imports...")
        
        # Find the line with fastapi imports
        fastapi_import_line = "from fastapi import FastAPI"
        if fastapi_import_line in content:
            # Add Supabase imports after the existing imports but before Navigation items
            nav_items_line = "# Navigation items for the sidebar"
            if nav_items_line in content:
                supabase_imports = """
# Supabase integration
from dotenv import load_dotenv
from supabase_client import supabase, SupabaseUserManager

# Load environment variables
load_dotenv()
"""
                content = content.replace(nav_items_line, supabase_imports + "\n" + nav_items_line)
                print("✅ Added Supabase imports")
            else:
                print("⚠️ Could not find navigation items section")
        
        # Step 2: Replace get_current_user_from_session function
        print("🔧 Replacing get_current_user_from_session function...")
        
        old_function_pattern = r'def get_current_user_from_session\(session_id: str = None\) -> Optional\[Dict\]:.*?(?=\ndef |\nclass |\n@|\nif __name__|$)'
        
        new_function = '''def get_current_user_from_session(session_id: str = None) -> Optional[Dict]:
    """Get current user from session using Supabase"""
    # Dev auto-login bypass
    if DEV_AUTOLOGIN_USER and DEV_AUTOLOGIN_USER in USERS_DATABASE:
        return USERS_DATABASE[DEV_AUTOLOGIN_USER]
    
    if not session_id:
        return None
    
    try:
        user = SupabaseUserManager.get_user_by_session(session_id)
        return user
    except Exception as e:
        print(f"Error getting user from session: {e}")
        return None'''
        
        content = re.sub(old_function_pattern, new_function, content, flags=re.DOTALL)
        print("✅ Updated get_current_user_from_session function")
        
        # Step 3: Replace authenticate_user function (if it exists)
        print("🔧 Looking for authenticate_user function...")
        
        if 'def authenticate_user(' in content:
            auth_function_pattern = r'def authenticate_user\([^)]*\):.*?(?=\ndef |\nclass |\n@|\nif __name__|$)'
            
            new_auth_function = '''def authenticate_user(employee_id: str, password: str):
    """Authenticate user using Supabase"""
    try:
        user = SupabaseUserManager.get_user_by_id(employee_id)
        if user and verify_password(password, user.get('password_hash', '')):
            return user
        return None
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None'''
        
            content = re.sub(auth_function_pattern, new_auth_function, content, flags=re.DOTALL)
            print("✅ Updated authenticate_user function")
        
        # Step 4: Update login route to use Supabase for session creation
        print("🔧 Updating login route...")
        
        # Look for the login route and update session creation
        if '@app.post("/login")' in content:
            print("✅ Found login route - it will use the updated authenticate_user function")
        
        # Step 5: Add helper function for session creation
        print("🔧 Adding session creation helper...")
        
        session_helper = '''
def create_user_session_supabase(user_id: str):
    """Create user session using Supabase"""
    try:
        import secrets
        session_id = secrets.token_urlsafe(32)
        
        # Get current login count
        user = SupabaseUserManager.get_user_by_id(user_id)
        current_count = user.get('login_count', 0) if user else 0
        
        # Update user with session_id
        SupabaseUserManager.update_user(user_id, {
            'session_id': session_id,
            'last_login': datetime.now().isoformat(),
            'login_count': current_count + 1
        })
        
        return session_id
    except Exception as e:
        print(f"Error creating session: {e}")
        return None
'''
        
        # Add this function before the app routes
        app_routes_start = '@app.middleware("http")'
        if app_routes_start in content:
            content = content.replace(app_routes_start, session_helper + "\n" + app_routes_start)
            print("✅ Added session creation helper")
        
        # Step 6: Update user API endpoints
        print("🔧 Updating user API endpoints...")
        
        # Replace get_users API
        if '@app.get("/api/users")' in content:
            # This will need manual updating as it's complex
            print("⚠️ Found /api/users endpoint - needs manual update to use SupabaseUserManager.get_all_users()")
        
        # Write the updated content
        with open('app_with_supabase.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Created app_with_supabase.py with Supabase integration")
        print()
        print("📋 NEXT STEPS:")
        print("1. Review app_with_supabase.py")
        print("2. Test the integration")
        print("3. Replace app.py with app_with_supabase.py when ready")
        print("4. Update any remaining JSON-based user operations manually")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    integrate_supabase_into_app()
