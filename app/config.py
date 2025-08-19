"""
Configuration settings for the application
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eraya_ops.db")

# Application Configuration
APP_TITLE = "Eraya Style Order Processor"
APP_VERSION = "2.0.0"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# File Upload Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
UPLOAD_DIR = "uploads"
BASE_DIR = Path(".")

# Shopify Configuration
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN", "")

# Security Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
SESSION_EXPIRY_DAYS = int(os.getenv("SESSION_EXPIRY_DAYS", "7"))
REMEMBER_ME_DAYS = int(os.getenv("REMEMBER_ME_DAYS", "30"))

# Feature Flags
USE_JSON = os.getenv("USE_JSON", "false").lower() == "true"
ENABLE_WEBSOCKETS = os.getenv("ENABLE_WEBSOCKETS", "true").lower() == "true"

# Validate required configuration
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is required")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Either SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY environment variable is required")

print(f"🔧 Configuration loaded:")
print(f"   Supabase URL: {SUPABASE_URL}")
print(f"   Service Key: {SUPABASE_SERVICE_ROLE_KEY[:20] if SUPABASE_SERVICE_ROLE_KEY else 'None'}...")
print(f"   Debug Mode: {DEBUG}")
print(f"   Use JSON: {USE_JSON}")
