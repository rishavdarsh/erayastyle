# Eraya Style Web App

## Admin → Users

### Overview
The User Management system provides a comprehensive interface for managing system users with full CRUD operations, search, filtering, pagination, and role-based access control.

### Environment Variables Required
```bash
# Supabase Configuration
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key  # Falls back to SUPABASE_ANON_KEY if not set
SECRET_KEY=your_app_secret_key
ENVIRONMENT=development
```

### Available Routes
- **UI**: `/admin/users` - User management interface (admin/owner only)
- **API**: 
  - `GET /api/users` - List users with pagination and filtering
  - `POST /api/users` - Create new user
  - `PATCH /api/users/{id}` - Update existing user
  - `DELETE /api/users/{id}` - Delete user
  - `GET /api/users/{id}` - Get single user details

### Creating First Admin User
You can create your first admin user either via SQL in Supabase or through the form once you have owner access:

**Via Supabase SQL Editor:**
```sql
INSERT INTO public.users (
    id, name, email, password_hash, role, status, 
    login_count, created_at, updated_at
) VALUES (
    'admin001',
    'System Administrator', 
    'admin@company.com',
    '$argon2id$v=19$m=65536,t=3,p=4$hash_here',  -- Use argon2 hash
    'admin',
    'active',
    0,
    NOW(),
    NOW()
);
```

### Security Features
- **Password Hashing**: Uses Argon2 for secure password storage
- **Email Uniqueness**: Enforced at database and application level
- **CSRF Protection**: Per-request tokens for POST/PATCH/DELETE operations
- **Input Validation**: Server-side validation for all user inputs
- **Role Validation**: Strict role checking (owner, admin, manager, employee, packer)
- **Self-Protection**: Users cannot delete their own accounts

### User Roles & Permissions
- **Owner**: Full system access, can manage all users
- **Admin**: Can manage users, access most features
- **Manager**: Limited user management, departmental access
- **Employee**: Standard user access
- **Packer**: Specialized role for warehouse operations

### Features
- **Search**: Filter by name, email, phone, city, state
- **Role Filter**: Filter by user role
- **Status Filter**: Filter by active/inactive/suspended
- **Sorting**: By created_date (default), name, email, role, status, last_login
- **Pagination**: Configurable page sizes (10, 25, 50, 100)
- **Modal Forms**: Add/Edit users with client-side validation
- **Password Management**: Optional password updates (leave blank to keep current)
- **Status Management**: Active/Inactive/Suspended user states
- **Responsive Design**: Works on desktop and mobile devices

### Data Validation
- **Name**: 1-120 characters, required
- **Email**: RFC compliant format, unique across system
- **Password**: Minimum 6 characters (creation), optional (updates)
- **Role**: Must be valid system role
- **Status**: Must be valid status value
- **Phone/Address**: Optional fields with basic formatting

### Usage Notes
- Never exposes password_hash in API responses or templates
- All API responses include `{ok: boolean, data?: any, error?: string}` format
- Debounced search (300ms delay) for better performance
- Real-time validation feedback in forms
- Toast notifications for all user actions
- Automatic table refresh after modifications
- **Users page uses optimistic deletion and background reconciliation** - rows disappear immediately on delete, with background re-fetch to ensure data consistency
- **Users CRUD (Supabase-backed)** - Full Create, Read, Update, Delete operations connected directly to Supabase with no local JSON files or stale caching

## Global Sidebar & Navigation

The app uses a consistent global sidebar across all pages. The sidebar is implemented as a shared partial in `templates/partials/sidebar.html` and is automatically included in all pages through the base layout template.

### Creating New Pages

To create a new page with the correct layout and routing:

```bash
python scripts/new_page.py --name orders --route /orders
```

This will:
1. Create a new template at `templates/orders.html` that extends the base layout
2. Add a route in `app.py` for the new page
3. Set up the basic page structure with a title and content area

### Template Consistency Check

To verify all page templates correctly extend the base layout:

```bash
python scripts/check_templates.py
```

This check is recommended before committing changes to ensure consistent navigation and styling across the app.

### Project Structure

- `templates/`: Page templates and partials
  - `layout_base.html`: Base template with navigation and layout
  - `partials/`: Reusable template components
    - `sidebar.html`: Global navigation sidebar
- `static/`: Static assets
  - `css/app.css`: Global styles
  - `js/nav.js`: Navigation behavior
- `scripts/`: Development utilities
  - `new_page.py`: Page template generator
  - `check_templates.py`: Template consistency checker

### Navigation

The app uses a persistent left sidebar for navigation. To add a new item to the navigation:

1. Add the route to `protected_paths` in `app.py` if it requires authentication
2. Add an entry to `NAV_ITEMS` in `app.py` with:
   - id: Unique identifier
   - name: Display name
   - icon: Emoji or icon
   - url: Route path
   - active: Boolean for feature flag
   - required_roles: List of roles that can access (optional)
   - badge: Optional "Soon" badge for upcoming features