# 🛠️ STEP-BY-STEP ROUTE FIXES

## Problem: Different CSS/Styling Between Pages
Some pages still use `_eraya_style_page` (old method) which creates different HTML/CSS than the unified template system.

## Solution: Convert All Routes to Use Templates

---

## 🔧 FIX #1: `/packing` route (around line 4880-5316)

**FIND THIS ENTIRE FUNCTION:**
```python
@app.get("/packing")
def eraya_packing_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Packing Management</h1>
      <p class="text-white/80 mt-2">Efficient order packing and tracking system.</p>
      
      <div class="mt-6 grid gap-6">
        <!-- MASSIVE HTML CONTENT HERE -->
      </div>
    </section>
    
    <style>
      /* CSS STYLES HERE */
    </style>
    
    <script>
      /* JAVASCRIPT HERE */
    </script>
    """
    return _eraya_style_page("Packing", body)
```

**REPLACE WITH:**
```python
@app.get("/packing")
def eraya_packing_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    return templates.TemplateResponse("packing.html", {
        "request": request,
        "current_user": current_user
    })
```

---

## 🔧 FIX #2: `/orders` route (around line 3491)

**FIND THIS ENTIRE FUNCTION:**
```python
@app.get("/orders")
def eraya_orders_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Management</h1>
      <p class="text-white/80 mt-2">Fetch and manage orders directly from your Shopify store.</p>
      
      <!-- SHOPIFY SETUP NOTICE -->
      <div id="shopifyNotice" class="bg-blue-500/20 border border-blue-500/30 rounded-xl p-4 mt-4" style="display: none;">
        <!-- MASSIVE HTML CONTENT HERE -->
      </div>
      
      <!-- MORE MASSIVE HTML CONTENT -->
    </section>
    
    <style>
      /* CSS STYLES HERE */
    </style>
    
    <script>
      /* MASSIVE JAVASCRIPT HERE */
    </script>
    """
    return _eraya_style_page("Order Management", body)
```

**REPLACE WITH:**
```python
@app.get("/orders")
def eraya_orders_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("orders/index.html", {
        "request": request,
        "current_user": current_user
    })
```

---

## 🔧 FIX #3: `/shopify/settings` route (around line 5542)

**FIND THIS ENTIRE FUNCTION:**
```python
@app.get("/shopify/settings")
def eraya_shopify_settings_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Shopify Settings</h1>
      <!-- MASSIVE HTML CONTENT HERE -->
    </section>
    
    <style>
      /* CSS STYLES HERE */
    </style>
    
    <script>
      /* JAVASCRIPT HERE */
    </script>
    """
    return _eraya_style_page("Shopify Settings", body)
```

**REPLACE WITH:**
```python
@app.get("/shopify/settings")
def eraya_shopify_settings_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("shopify_settings.html", {
        "request": request,
        "current_user": current_user
    })
```

---

## 🔧 FIX #4: `/admin/users` route (around line 7209)

**FIND THIS ENTIRE FUNCTION:**
```python
@app.get("/admin/users")  # or similar route
def eraya_users_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">User Management</h1>
      <!-- MASSIVE HTML CONTENT HERE -->
    </section>
    
    <style>
      /* CSS STYLES HERE */
    </style>
    
    <script>
      /* JAVASCRIPT HERE */
    </script>
    """
    return _eraya_style_page("User Management", body)
```

**REPLACE WITH:**
```python
@app.get("/admin/users")
def eraya_users_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "current_user": current_user
    })
```

---

## 🔧 FIX #5: `/attendance` route (around line 7490)

**FIND THIS ENTIRE FUNCTION:**
```python
@app.get("/attendance")
def eraya_attendance_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Employee Attendance</h1>
      <!-- MASSIVE HTML CONTENT HERE -->
    </section>
    
    <style>
      /* CSS STYLES HERE */
    </style>
    
    <script>
      /* JAVASCRIPT HERE */
    </script>
    """
    return _eraya_style_page("Attendance", body)
```

**REPLACE WITH:**
```python
@app.get("/attendance")
def eraya_attendance_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    return templates.TemplateResponse("attendance.html", {
        "request": request,
        "current_user": current_user
    })
```

---

## ✅ THE PATTERN

For each route that uses `_eraya_style_page`:

1. **Add `request: Request`** to function parameters
2. **Delete the entire `body = """..."""` string** (can be hundreds of lines!)
3. **Replace the return statement** with `templates.TemplateResponse`
4. **Use the template file** I created for you

## 🎯 RESULT

After these changes:
- ✅ All pages will have **identical styling** 
- ✅ All pages will use the **same CSS framework**
- ✅ All pages will have the **same navigation design**
- ✅ Your `app.py` will be **much cleaner** (no more massive HTML strings!)

---

**Note:** There may be additional routes to convert. Search for any remaining `_eraya_style_page` calls and follow the same pattern.
