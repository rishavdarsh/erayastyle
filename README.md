# Lumen Orders — Complete Business Management System

**Latest Update:** 🔐 **Complete Authentication System** - Individual user accounts with email/password login, role-based access control, and comprehensive user management.

## 🚀 Features

### 📦 **Order Processing**
- CSV to Images & Reports processing
- Shopify integration for order management
- Advanced filtering and bulk operations
- Photo downloading and CSV export

### 👥 **User Management System**
- Individual user accounts with email/password authentication
- Role-based access control (Super Admin, Admin, Manager, Employee)
- User permissions management and custom roles
- Activity logging and audit trails
- Password reset and security features

### 📊 **Business Operations**
- Dashboard with real-time analytics
- Employee attendance tracking with overtime calculation
- Advanced team chat system with file sharing
- Packing management and order organization
- Reports and analytics

### 🔐 **Security Features**
- Secure password hashing (PBKDF2 with salt)
- Session management with HTTP-only cookies
- Force password change on first login
- Route protection middleware
- Comprehensive audit logging

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://127.0.0.1:8000

## 🔑 Default Login Credentials

**All users must change their password on first login:**

- **Ritik (Super Admin)**: `ritik@company.com` / `admin123`
- **Sunny (Admin)**: `sunny@company.com` / `sunny123`
- **Rahul (Manager)**: `rahul@company.com` / `rahul123`
- **Sumit (Employee)**: `sumit@company.com` / `sumit123`
- **Vishal (Manager)**: `vishal@company.com` / `vishal123`
- **Nishant (Employee)**: `nishant@company.com` / `nishant123`

⚠️ **Security Note**: All users will be prompted to change their password on first login for security.

## Deploy on Render
1. Create a new Web Service on https://render.com
2. Connect this repo or upload the ZIP.
3. Render uses `render.yaml` to start the app.
4. You’ll get a public URL like `https://your-app.onrender.com`.

## API
- `POST /api/process` (multipart/form-data): fields include `file` (CSV), `order_prefix`, `max_threads`, `retry_total`, `backoff_factor`, `timeout_sec`, `include_per_product_csv`, `include_back_messages_csv`, `zip_name`.
- `GET /api/status/{job_id}`
- `GET /api/download/{job_id}`
