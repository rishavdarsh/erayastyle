"""
Complete Supabase client with all necessary methods
"""

import os
import datetime
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
    """Complete Supabase user management functions"""
    
    @staticmethod
    def create_user_table():
        """Create users table if it doesn't exist"""
        try:
            response = supabase.table('users').select('id').limit(1).execute()
            print("Users table exists")
            return True
        except Exception as e:
            print(f"Users table may not exist: {e}")
            return False
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            response = supabase.table('users').select('*').eq('id', user_id).execute()
            user = response.data[0] if response.data else None
            # Map id to employee_id for compatibility
            if user:
                user['employee_id'] = user['id']
            return user
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
    def get_user_by_session(session_id: str) -> Optional[Dict]:
        """Get user by session ID"""
        try:
            response = supabase.table('users').select('*').eq('session_id', session_id).execute()
            user = response.data[0] if response.data else None
            # Map id to employee_id for compatibility
            if user:
                user['employee_id'] = user['id']
            return user
        except Exception as e:
            print(f"Error getting user by session {session_id}: {e}")
            return None
    
    @staticmethod
    def create_session(user_id: str, session_token: str, remember_me: bool = False) -> bool:
        """Create/update user session"""
        try:
            response = supabase.table('users').update({
                'session_id': session_token,
                'last_login': datetime.datetime.now().isoformat()
            }).eq('id', user_id).execute()
            return True
        except Exception as e:
            print(f"Error creating session for user {user_id}: {e}")
            return False
    
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
    def delete_user(user_id: str) -> bool:
        """Delete user"""
        try:
            response = supabase.table('users').delete().eq('id', user_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting user {user_id}: {e}")
            return False
    
    @staticmethod
    def get_all_users() -> List[Dict]:
        """Get all users"""
        try:
            response = supabase.table('users').select('*').execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []
    
    @staticmethod
    def get_users_by_role(role: str) -> List[Dict]:
        """Get users by role"""
        try:
            response = supabase.table('users').select('*').eq('role', role).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting users by role {role}: {e}")
            return []
    
    @staticmethod
    def get_active_users() -> List[Dict]:
        """Get active users"""
        try:
            response = supabase.table('users').select('*').eq('status', 'active').execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error getting active users: {e}")
            return []
    
    @staticmethod
    def toggle_user_status(user_id: str) -> Optional[Dict]:
        """Toggle user active/inactive status"""
        try:
            # First get current status
            user = SupabaseUserManager.get_user_by_id(user_id)
            if not user:
                return None
            
            new_status = 'inactive' if user.get('status') == 'active' else 'active'
            return SupabaseUserManager.update_user(user_id, {'status': new_status})
        except Exception as e:
            print(f"Error toggling user status {user_id}: {e}")
            return None
    
    @staticmethod
    def update_user_role(user_id: str, new_role: str) -> Optional[Dict]:
        """Update user role"""
        try:
            return SupabaseUserManager.update_user(user_id, {'role': new_role})
        except Exception as e:
            print(f"Error updating user role {user_id}: {e}")
            return None
    
    @staticmethod
    def update_user_password(user_id: str, password_hash: str) -> Optional[Dict]:
        """Update user password"""
        try:
            return SupabaseUserManager.update_user(user_id, {'password_hash': password_hash})
        except Exception as e:
            print(f"Error updating user password {user_id}: {e}")
            return None
    
    @staticmethod
    def clear_user_session(user_id: str) -> Optional[Dict]:
        """Clear user session"""
        try:
            return SupabaseUserManager.update_user(user_id, {'session_id': None})
        except Exception as e:
            print(f"Error clearing user session {user_id}: {e}")
            return None
    
    @staticmethod
    def bulk_update_users(user_ids: List[str], update_data: Dict) -> bool:
        """Bulk update multiple users"""
        try:
            for user_id in user_ids:
                SupabaseUserManager.update_user(user_id, update_data)
            return True
        except Exception as e:
            print(f"Error bulk updating users: {e}")
            return False

# Test connection on import
try:
    SupabaseUserManager.create_user_table()
    print("Supabase connection established")
except Exception as e:
    print(f"Supabase connection issue: {e}")
