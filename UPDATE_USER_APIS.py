#!/usr/bin/env python3
"""
Update user API endpoints in app.py to use Supabase
"""

def update_user_api_endpoints():
    """Update all user-related API endpoints to use Supabase"""
    print("🔧 UPDATING USER API ENDPOINTS FOR SUPABASE")
    print("=" * 60)
    
    try:
        with open('app_with_supabase.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace the get_users API endpoint
        print("📊 Updating /api/users endpoint...")
        
        old_users_api = '''@app.get("/api/users")
def get_users(
    search: str = "",
    role: str = "",
    status: str = "",
    sort_by: str = "name",
    sort_dir: str = "asc",
    current_user: Dict = Depends(require_roles("owner", "admin"))
):
    """Get users with filtering and sorting"""
    try:
        users_list = []
        for user_id, user_data in USERS_DATABASE.items():
            # Apply filters
            if search and search.lower() not in user_data.get("name", "").lower() and search.lower() not in user_data.get("email", "").lower():
                continue
            if role and user_data.get("role", "") != role:
                continue
            if status and user_data.get("status", "") != status:
                continue
            
            # Add user to list
            user_copy = user_data.copy()
            user_copy["id"] = user_id
            users_list.append(user_copy)
        
        # Sort users
        reverse = sort_dir == "desc"
        if sort_by == "name":
            users_list.sort(key=lambda x: x.get("name", "").lower(), reverse=reverse)
        elif sort_by == "role":
            users_list.sort(key=lambda x: x.get("role", "").lower(), reverse=reverse)
        elif sort_by == "status":
            users_list.sort(key=lambda x: x.get("status", "").lower(), reverse=reverse)
        elif sort_by == "last_login":
            users_list.sort(key=lambda x: x.get("last_login", ""), reverse=reverse)
        
        # Get unique roles for filter
        roles = list(set([user.get("role", "employee") for user in users_list]))
        
        return JSONResponse(content={
            "success": True,
            "users": users_list,
            "roles": roles
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)'''
        
        new_users_api = '''@app.get("/api/users")
def get_users(
    search: str = "",
    role: str = "",
    status: str = "",
    sort_by: str = "name",
    sort_dir: str = "asc",
    current_user: Dict = Depends(require_roles("owner", "admin"))
):
    """Get users with filtering and sorting using Supabase"""
    try:
        # Get all users from Supabase
        all_users = SupabaseUserManager.get_all_users()
        users_list = []
        
        for user_data in all_users:
            # Apply filters
            if search and search.lower() not in user_data.get("name", "").lower() and search.lower() not in user_data.get("email", "").lower():
                continue
            if role and user_data.get("role", "") != role:
                continue
            if status and user_data.get("status", "") != status:
                continue
            
            users_list.append(user_data)
        
        # Sort users
        reverse = sort_dir == "desc"
        if sort_by == "name":
            users_list.sort(key=lambda x: x.get("name", "").lower(), reverse=reverse)
        elif sort_by == "role":
            users_list.sort(key=lambda x: x.get("role", "").lower(), reverse=reverse)
        elif sort_by == "status":
            users_list.sort(key=lambda x: x.get("status", "").lower(), reverse=reverse)
        elif sort_by == "last_login":
            users_list.sort(key=lambda x: x.get("last_login", ""), reverse=reverse)
        
        # Get unique roles for filter
        roles = list(set([user.get("role", "employee") for user in users_list]))
        
        return JSONResponse(content={
            "success": True,
            "users": users_list,
            "roles": roles
        })
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)'''
        
        content = content.replace(old_users_api, new_users_api)
        print("✅ Updated /api/users endpoint")
        
        # Update get_users_stats endpoint
        print("📈 Updating /api/users/stats endpoint...")
        
        old_stats_pattern = '''def get_users_stats(current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Get user statistics"""
    return JSONResponse(content=get_user_stats())'''
        
        new_stats = '''def get_users_stats(current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Get user statistics from Supabase"""
    try:
        all_users = SupabaseUserManager.get_all_users()
        
        total_users = len(all_users)
        active_users = len([u for u in all_users if u.get('status') == 'active'])
        inactive_users = total_users - active_users
        admin_count = len([u for u in all_users if u.get('role') in ['owner', 'admin']])
        
        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": inactive_users,
            "admin_count": admin_count
        }
        
        return JSONResponse(content=stats)
    except Exception as e:
        return JSONResponse(content={
            "total_users": 0,
            "active_users": 0,
            "inactive_users": 0,
            "admin_count": 0,
            "error": str(e)
        }, status_code=500)'''
        
        content = content.replace(old_stats_pattern, new_stats)
        print("✅ Updated /api/users/stats endpoint")
        
        # Update toggle user status endpoint
        print("🔄 Looking for toggle user status endpoint...")
        
        if "/toggle-status" in content:
            old_toggle_pattern = r'@app\.post\("/api/users/\{user_id\}/toggle-status"\).*?(?=@app\.|\ndef |\nclass |\nif __name__|$)'
            
            new_toggle = '''@app.post("/api/users/{user_id}/toggle-status")
def toggle_user_status(user_id: str, current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Toggle user status using Supabase"""
    try:
        result = SupabaseUserManager.toggle_user_status(user_id)
        if result:
            return JSONResponse(content={"success": True, "message": "User status updated"})
        else:
            return JSONResponse(content={"success": False, "message": "User not found"}, status_code=404)
    except Exception as e:
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)'''
            
            import re
            content = re.sub(old_toggle_pattern, new_toggle, content, flags=re.DOTALL)
            print("✅ Updated toggle user status endpoint")
        
        # Update the login route to use Supabase session creation
        print("🔐 Updating login route...")
        
        # Find and replace the session creation in login
        if 'session_id = secrets.token_urlsafe(32)' in content:
            # Replace the manual session creation with Supabase version
            old_session_creation = '''session_id = secrets.token_urlsafe(32)
            USERS[employee_id]["session_id"] = session_id
            save_users_auth()'''
            
            new_session_creation = '''session_id = create_user_session_supabase(employee_id)
            if not session_id:
                return JSONResponse(
                    content={"success": False, "message": "Failed to create session"},
                    status_code=500
                )'''
            
            content = content.replace(old_session_creation, new_session_creation)
            print("✅ Updated login session creation")
        
        # Write the updated content
        with open('app_supabase_complete.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Created app_supabase_complete.py with all API endpoints updated")
        print()
        print("📋 INTEGRATION COMPLETE!")
        print("🎯 Next step: Test the integration by replacing app.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    update_user_api_endpoints()
