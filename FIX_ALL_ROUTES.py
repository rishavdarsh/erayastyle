#!/usr/bin/env python3
"""
COMPLETE ROUTE CONVERSION SCRIPT

This script shows you exactly what to change in app.py to fix all styling inconsistencies.
Copy and paste these exact replacements into your app.py file.
"""

def show_all_fixes():
    print("🔧 COMPLETE ROUTE CONVERSION - EXACT CHANGES NEEDED")
    print("=" * 80)
    print()
    
    fixes = [
        {
            "route": "/packing",
            "line": "~4880-5316",
            "find": '''@app.get("/packing")
def eraya_packing_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Packing Management</h1>
      # ... (MASSIVE HTML STRING) ...
    """
    return _eraya_style_page("Packing", body)''',
            "replace": '''@app.get("/packing")
def eraya_packing_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    return templates.TemplateResponse("packing.html", {
        "request": request,
        "current_user": current_user
    })'''
        },
        {
            "route": "/orders",
            "line": "~3491",
            "find": '''@app.get("/orders")
def eraya_orders_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Management</h1>
      # ... (MASSIVE HTML STRING) ...
    """
    return _eraya_style_page("Order Management", body)''',
            "replace": '''@app.get("/orders")
def eraya_orders_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("orders/index.html", {
        "request": request,
        "current_user": current_user
    })'''
        },
        {
            "route": "/shopify/settings",
            "line": "~5542",
            "find": '''@app.get("/shopify/settings")
def eraya_shopify_settings_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Shopify Settings</h1>
      # ... (MASSIVE HTML STRING) ...
    """
    return _eraya_style_page("Shopify Settings", body)''',
            "replace": '''@app.get("/shopify/settings")
def eraya_shopify_settings_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("shopify_settings.html", {
        "request": request,
        "current_user": current_user
    })'''
        },
        {
            "route": "/admin/users",
            "line": "~7209", 
            "find": '''@app.get("/admin/users")  # or similar
def eraya_users_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">User Management</h1>
      # ... (MASSIVE HTML STRING) ...
    """
    return _eraya_style_page("User Management", body)''',
            "replace": '''@app.get("/admin/users")
def eraya_users_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "current_user": current_user
    })'''
        },
        {
            "route": "/attendance",
            "line": "~7490",
            "find": '''@app.get("/attendance")
def eraya_attendance_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Employee Attendance</h1>
      # ... (MASSIVE HTML STRING) ...
    """
    return _eraya_style_page("Attendance", body)''',
            "replace": '''@app.get("/attendance")
def eraya_attendance_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("attendance.html", {
        "request": request,
        "current_user": current_user
    })'''
        }
    ]
    
    for i, fix in enumerate(fixes, 1):
        print(f"🔧 FIX #{i}: {fix['route']} route (around line {fix['line']})")
        print("-" * 60)
        print("FIND AND REPLACE THIS ENTIRE FUNCTION:")
        print()
        print("OLD CODE:")
        print(fix['find'])
        print()
        print("NEW CODE:")
        print(fix['replace'])
        print()
        print("=" * 80)
        print()
    
    print("📋 SUMMARY OF CHANGES:")
    print("-" * 40)
    print("1. Add 'request: Request' parameter to each function")
    print("2. Replace '_eraya_style_page' with 'templates.TemplateResponse'")  
    print("3. Delete the massive 'body = \"\"\"...\"\"\"' HTML strings")
    print("4. Use the template files I created for you")
    print()
    print("✅ RESULT: All pages will have identical styling and navigation!")
    print()

if __name__ == "__main__":
    show_all_fixes()
