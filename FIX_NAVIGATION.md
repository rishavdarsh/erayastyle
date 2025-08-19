# NAVIGATION UNIFICATION FIX

This document contains all the changes needed to fix the navigation inconsistencies in your app.

## PROBLEM
Some pages use the modern template system (with unified sidebar) while others use inline HTML (with custom sidebars).

## SOLUTION
Convert all pages to use the modern template system.

## STEP 1: UPDATE EXISTING ROUTES

### 1. Fix /orders route (app.py line ~2421)

CHANGE FROM:
```python
@app.get("/orders")
def eraya_orders_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      # ... massive inline HTML ...
    """
    return _eraya_style_page("Order Management", body)
```

CHANGE TO:
```python
@app.get("/orders")
def eraya_orders_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("orders/index.html", {
        "request": request,
        "current_user": current_user
    })
```

### 2. Fix /packing route (app.py line ~4896)

CHANGE FROM:
```python
@app.get("/packing")
def eraya_packing_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    body = """
    # ... inline HTML ...
    """
    return _eraya_style_page("Packing", body)
```

CHANGE TO:
```python
@app.get("/packing")
def eraya_packing_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    return templates.TemplateResponse("packing.html", {
        "request": request,
        "current_user": current_user
    })
```

### 3. Fix /shopify/settings route (app.py line ~5334)

CHANGE FROM:
```python
@app.get("/shopify/settings")
def eraya_shopify_settings_page(...):
    body = """..."""
    return _eraya_style_page("Shopify Settings", body)
```

CHANGE TO:
```python
@app.get("/shopify/settings")
def eraya_shopify_settings_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("shopify_settings.html", {
        "request": request,
        "current_user": current_user
    })
```

### 4. Fix /admin/users route (app.py line ~7225)

CHANGE FROM:
```python
@app.get("/admin/users")
def eraya_users_page(...):
    body = """..."""
    return _eraya_style_page("User Management", body)
```

CHANGE TO:
```python
@app.get("/admin/users")
def eraya_users_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "current_user": current_user
    })
```

### 5. Fix /pending route (app.py line ~7228)

CHANGE FROM:
```python
@app.get("/pending")
def eraya_pending_page(...):
    body = """..."""
    return _eraya_style_page("Pending Orders", body)
```

CHANGE TO:
```python
@app.get("/pending")
def eraya_pending_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("pending.html", {
        "request": request,
        "current_user": current_user
    })
```

### 6. Fix /attendance route (app.py line ~7239)

CHANGE FROM:
```python
@app.get("/attendance")
def eraya_attendance_page(...):
    body = """..."""
    return _eraya_style_page("Attendance", body)
```

CHANGE TO:
```python
@app.get("/attendance")
def eraya_attendance_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("attendance.html", {
        "request": request,
        "current_user": current_user
    })
```

### 7. Fix /attendance/report_page route (app.py line ~7507)

CHANGE FROM:
```python
@app.get("/attendance/report_page")
def eraya_attendance_reports_page(...):
    body = """..."""
    return _eraya_style_page("Attendance Reports", body)
```

CHANGE TO:
```python
@app.get("/attendance/report_page")
def eraya_attendance_reports_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("attendance_reports.html", {
        "request": request,
        "current_user": current_user
    })
```

### 8. Fix /chat route (app.py line ~7658)

This one might already be using templates. Check if it returns _eraya_style_page or templates.TemplateResponse.

## STEP 2: DELETE OLD FUNCTION

After all routes are converted, you can delete the entire `_eraya_style_page` function from app.py (around line 1225).

## STEP 3: CLEAN UP

Remove all the massive inline HTML strings from the route functions in app.py. This will make your app.py file much cleaner and more maintainable.

## RESULT

After these changes:
- Every page will have the exact same sidebar
- All pages will be consistent
- app.py will be much cleaner
- Adding new menu items is as simple as editing NAV_ITEMS
- No more duplicate or inconsistent navigation
