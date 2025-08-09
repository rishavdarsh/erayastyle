import os
import uuid
import threading
from pathlib import Path
import re
import urllib.request
import urllib.parse
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from processor import process_csv_file, extract_color

import io
import pandas as pd
import datetime
import requests
from typing import Dict, List, Any
import json

app = FastAPI(title="Lumen Order Processor")

# Shopify configuration from environment variables
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "")  # e.g., "mystore.myshopify.com"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN", "")  # Admin API token

def _shopify_get(path: str, params: dict = None) -> dict:
    """Helper function to make Shopify API calls with pagination support."""
    # Try environment variables first, then fall back to SHOPIFY_CONFIG
    shop = SHOPIFY_SHOP or SHOPIFY_CONFIG.get("store_name")
    token = SHOPIFY_TOKEN or SHOPIFY_CONFIG.get("access_token")
    
    if not shop or not token:
        raise HTTPException(status_code=400, detail="Shopify configuration missing. Set SHOPIFY_SHOP and SHOPIFY_TOKEN environment variables or configure via /shopify/settings.")
    
    # Ensure shop has the right format
    if shop and not shop.endswith('.myshopify.com'):
        shop = f"{shop}.myshopify.com"
    
    url = f"https://{shop}/admin/api/2024-07{path}"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        
        # Parse pagination info from Link header
        next_page_info = None
        prev_page_info = None
        
        if "Link" in response.headers:
            link_header = response.headers["Link"]
            # Parse next page info
            if 'rel="next"' in link_header:
                next_match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header)
                if next_match:
                    next_page_info = next_match.group(1)
            
            # Parse previous page info
            if 'rel="previous"' in link_header:
                prev_match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="previous"', link_header)
                if prev_match:
                    prev_page_info = prev_match.group(1)
        
        data = response.json()
        data["_pagination"] = {
            "next_page_info": next_page_info,
            "prev_page_info": prev_page_info
        }
        return data
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Shopify API error: {str(e)}")

# In-memory store for attendance records
ATTENDANCE_RECORDS = {}

# In-memory store for employee data (name to ID mapping)
EMPLOYEES = {
    "Ritik": "EMP001",
    "Sunny": "EMP002",
    "Rahul": "EMP003",
    "Sumit": "EMP004",
    "Vishal": "EMP005",
    "Nishant": "EMP006",
}

# User roles and permissions - ALL USERS GET FULL ACCESS
USER_ROLES = {
    "EMP001": {"name": "Ritik", "role": "admin", "permissions": ["all"]},
    "EMP002": {"name": "Sunny", "role": "admin", "permissions": ["all"]},
    "EMP003": {"name": "Rahul", "role": "admin", "permissions": ["all"]},
    "EMP004": {"name": "Sumit", "role": "admin", "permissions": ["all"]},
    "EMP005": {"name": "Vishal", "role": "admin", "permissions": ["all"]},
    "EMP006": {"name": "Nishant", "role": "admin", "permissions": ["all"]},
}

# Navigation menu structure - EVERYONE GETS FULL ACCESS
UNIFIED_NAVIGATION_MENU = [
    {"id": "dashboard", "name": "Dashboard", "icon": "📊", "url": "/hub", "active": True},
    {"id": "orders", "name": "Order Organizer", "icon": "🧭", "url": "/orders", "active": True},
    {"id": "packing", "name": "Packing Management", "icon": "📦", "url": "/packing", "active": True},
    {"id": "attendance", "name": "Employee Attendance", "icon": "🗓️", "url": "/attendance", "active": True},
    {"id": "chat", "name": "Team Chat", "icon": "💬", "url": "/chat", "active": True},
    {"id": "reports", "name": "Reports & Analytics", "icon": "📊", "url": "/attendance/report_page", "active": True},
    {"id": "separator", "type": "separator", "name": "Additional Features"},
    {"id": "team", "name": "Team Management", "icon": "👥", "url": "/team", "active": False, "badge": "Soon"},
    {"id": "shopify", "name": "Shopify Settings", "icon": "🛒", "url": "/shopify/settings", "active": True},
    {"id": "settings", "name": "System Settings", "icon": "⚙️", "url": "/admin/settings", "active": False, "badge": "Soon"},
    {"id": "users", "name": "User Management", "icon": "👨‍💼", "url": "/admin/users", "active": False, "badge": "Soon"},
    {"id": "security", "name": "Security Settings", "icon": "🔐", "url": "/admin/security", "active": False, "badge": "Soon"},
    {"id": "analytics", "name": "System Analytics", "icon": "📈", "url": "/admin/analytics", "active": False, "badge": "Soon"},
]

# In-memory store for team chat messages
CHAT_MESSAGES = []

# In-memory store for chat channels and DMs
CHAT_CHANNELS = {
    "general": {"name": "General", "messages": []},
    "packing": {"name": "Packing Team", "messages": []},
    "management": {"name": "Management", "messages": []},
    "announcements": {"name": "Announcements", "messages": []}
}

# In-memory store for direct messages (DMs)
DIRECT_MESSAGES = {}  # Format: {"EMP001_EMP002": [messages]}

# In-memory store for user online status
USER_STATUS = {}  # Format: {"EMP001": {"status": "online", "last_seen": timestamp}}

# In-memory store for message reactions
MESSAGE_REACTIONS = {}

# -------------------- SHOPIFY INTEGRATION --------------------
# Shopify store configuration - In production, use environment variables or database
SHOPIFY_CONFIG = {
    "store_name": "",  # Will be set via settings page
    "access_token": "",  # Will be set via settings page
    "api_version": "2024-01"  # Latest stable API version
}

# In-memory store for cached Shopify data
SHOPIFY_CACHE = {
    "orders": [],
    "analytics": {},
    "last_updated": None
}

def get_timestamp():
    """Returns current UTC timestamp in ISO format."""
    return datetime.datetime.utcnow().isoformat()

# -------------------- SHOPIFY API HELPERS --------------------
def make_shopify_request(endpoint: str, params: Dict = None) -> Dict:
    """Make a request to Shopify Admin API."""
    if not SHOPIFY_CONFIG["store_name"] or not SHOPIFY_CONFIG["access_token"]:
        raise HTTPException(status_code=400, detail="Shopify store not configured. Please add your store details in settings.")
    
    url = f"https://{SHOPIFY_CONFIG['store_name']}.myshopify.com/admin/api/{SHOPIFY_CONFIG['api_version']}/{endpoint}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_CONFIG["access_token"],
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Shopify API error: {str(e)}")

def fetch_shopify_orders(limit: int = 50, status: str = "any") -> List[Dict]:
    """Fetch orders from Shopify."""
    params = {
        "limit": limit,
        "status": status,
        "fields": "id,name,email,created_at,updated_at,total_price,currency,financial_status,fulfillment_status,line_items,customer,shipping_address"
    }
    
    try:
        data = make_shopify_request("orders.json", params)
        return data.get("orders", [])
    except Exception as e:
        print(f"Error fetching Shopify orders: {e}")
        return []

def fetch_shopify_analytics() -> Dict:
    """Fetch analytics data from Shopify."""
    try:
        # Get order count for today
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Fetch recent orders for analytics
        recent_orders = fetch_shopify_orders(limit=250)
        
        # Calculate analytics
        total_orders = len(recent_orders)
        today_orders = [o for o in recent_orders if o["created_at"].startswith(today)]
        yesterday_orders = [o for o in recent_orders if o["created_at"].startswith(yesterday)]
        
        total_revenue = sum(float(o.get("total_price", 0)) for o in recent_orders)
        today_revenue = sum(float(o.get("total_price", 0)) for o in today_orders)
        
        pending_orders = [o for o in recent_orders if o.get("financial_status") == "pending"]
        fulfilled_orders = [o for o in recent_orders if o.get("fulfillment_status") == "fulfilled"]
        
        return {
            "total_orders": total_orders,
            "today_orders": len(today_orders),
            "yesterday_orders": len(yesterday_orders),
            "total_revenue": round(total_revenue, 2),
            "today_revenue": round(today_revenue, 2),
            "pending_orders": len(pending_orders),
            "fulfilled_orders": len(fulfilled_orders),
            "currency": recent_orders[0].get("currency", "USD") if recent_orders else "USD",
            "last_updated": get_timestamp()
        }
    except Exception as e:
        print(f"Error fetching Shopify analytics: {e}")
        return {
            "error": str(e),
            "last_updated": get_timestamp()
        }

def calculate_duration(start_time_str: str, end_time_str: str) -> float:
    """Calculates duration in hours between two ISO formatted timestamps."""
    start_time = datetime.datetime.fromisoformat(start_time_str)
    end_time = datetime.datetime.fromisoformat(end_time_str)
    duration = end_time - start_time
    return duration.total_seconds() / 3600 # duration in hours

def extract_links_from_message(message: str) -> list:
    """Extract URLs from message text."""
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    return url_pattern.findall(message)

def get_link_preview(url: str) -> dict:
    """Get basic link preview information."""
    try:
        # Simple link preview - in production you'd use a proper service
        parsed = urllib.parse.urlparse(url)
        return {
            "url": url,
            "title": parsed.netloc,
            "description": f"Link to {parsed.netloc}",
            "image": None
        }
    except:
        return {
            "url": url,
            "title": "Link",
            "description": "External link",
            "image": None
        }

def get_file_type(filename: str) -> str:
    """Determine file type from filename."""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov', 'wmv']:
        return 'video'
    elif ext in ['mp3', 'wav', 'ogg']:
        return 'audio'
    elif ext in ['pdf']:
        return 'pdf'
    elif ext in ['doc', 'docx', 'txt']:
        return 'document'
    else:
        return 'file'

# Serve static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Simple CORS for local dev or static hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jobs memory store (in-memory; for production you'd use Redis/DB)
JOBS = {}
BASE_DIR = Path(os.getenv("DATA_DIR", "jobs"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Chat uploads directory
UPLOADS_DIR = Path("uploads/chat")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


def run_job(job_id: str, csv_path: Path, out_dir: Path, options: dict):
    JOBS[job_id] = {"status": "processing", "message": "Starting...", "zip_path": None, "progress": 0}

    def status_cb(step: str, progress: float = None):
        if job_id in JOBS:
            JOBS[job_id]["message"] = step
            if progress is not None:
                JOBS[job_id]["progress"] = float(progress)

    try:
        zip_path = process_csv_file(csv_path, out_dir, status_cb, options=options)
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["zip_path"] = str(zip_path)
        JOBS[job_id]["message"] = "Completed"
        JOBS[job_id]["progress"] = 100.0
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = f"Error: {e}"
        JOBS[job_id]["progress"] = 0.0


@app.get("/", response_class=HTMLResponse)
def root():
    # Redirect to the hub (dashboard) page instead of showing raw static HTML
    return RedirectResponse(url="/hub")


@app.post("/api/process")
async def api_process(
    file: UploadFile = File(...),
    order_prefix: str = Form("#ER"),
    max_threads: int = Form(8),
    retry_total: int = Form(3),
    backoff_factor: float = Form(0.6),
    timeout_sec: int = Form(15),
    include_per_product_csv: bool = Form(True),
    include_back_messages_csv: bool = Form(True),
    zip_name: str = Form("results"),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    csv_path = job_dir / file.filename

    with open(csv_path, "wb") as f:
        f.write(await file.read())

    options = {
        "order_prefix": order_prefix or "#ER",
        "max_threads": max(1, min(int(max_threads), 32)),
        "retry_total": max(0, int(retry_total)),
        "backoff_factor": float(backoff_factor),
        "timeout_sec": max(3, int(timeout_sec)),
        "include_per_product_csv": bool(include_per_product_csv),
        "include_back_messages_csv": bool(include_back_messages_csv),
        "zip_name": zip_name.strip() or "results",
    }

    t = threading.Thread(target=run_job, args=(job_id, csv_path, job_dir, options), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def api_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


@app.get("/api/download/{job_id}")
def api_download(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job["status"] != "done" or not job["zip_path"]:
        raise HTTPException(status_code=400, detail="Job not finished yet")
    path = Path(job["zip_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP not found")
    return FileResponse(path, media_type="application/zip", filename=Path(path).name)


# -------------------- ERAYA HUB ADD-ON (UI shell) --------------------
def _eraya_lumen_page(title: str, body_html: str) -> HTMLResponse:
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — Eraya Ops</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {{ --brand:#a78bfa; --brand-strong:#8b5cf6; --accent:#f0abfc; }}
    .glass{{backdrop-filter:blur(10px);background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.12);border-radius:1.25rem;}}
    .btn{{display:inline-flex;align-items:center;justify-content:center;border-radius:1rem;padding:.6rem 1rem;font-weight:600;box-shadow:0 6px 20px rgba(168,139,250,.25), inset 0 1px 0 rgba(255,255,255,.08);}}
    .btn-primary{{background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416}}
    .btn-secondary{{background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.2)}}
    *{{scrollbar-width:thin;scrollbar-color:var(--brand) #0f172a}}
    *::-webkit-scrollbar{{height:8px;width:8px}}
    *::-webkit-scrollbar-thumb{{background:var(--brand);border-radius:8px}}

    /* Sidebar Styles */
    .sidebar {{
      width: 280px;
      transition: width 0.3s ease;
    }}
    .sidebar.collapsed {{
      width: 80px;
    }}
    .sidebar-item {{
      display: flex;
      align-items: center;
      padding: 12px 16px;
      margin: 4px 8px;
      border-radius: 12px;
      transition: all 0.2s ease;
      cursor: pointer;
      text-decoration: none;
      color: rgba(255,255,255,0.7);
    }}
    .sidebar-item:hover {{
      background: rgba(255,255,255,0.08);
      color: white;
      transform: translateX(4px);
    }}
    .sidebar-item.active {{
      background: linear-gradient(135deg,var(--brand-strong),var(--accent));
      color: #0b0416;
      font-weight: 600;
    }}
    .sidebar-item.disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}
    .sidebar-icon {{
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      margin-right: 12px;
    }}
    .sidebar-text {{
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }}
    .sidebar.collapsed .sidebar-text {{
      display: none;
    }}
    .sidebar-badge {{
      background: rgba(239, 68, 68, 0.9);
      color: white;
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 10px;
      font-weight: 600;
    }}
    .sidebar.collapsed .sidebar-badge {{
      display: none;
    }}
    .sidebar-separator {{
      margin: 16px 12px 8px 12px;
      padding: 8px 4px;
      font-size: 11px;
      font-weight: 600;
      color: rgba(255,255,255,0.4);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-top: 1px solid rgba(255,255,255,0.1);
    }}
    .sidebar.collapsed .sidebar-separator {{
      display: none;
    }}
    .main-content {{
      margin-left: 280px;
      transition: margin-left 0.3s ease;
    }}
    .main-content.expanded {{
      margin-left: 80px;
    }}
    .role-badge {{
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .role-badge.manager {{
      background: linear-gradient(135deg, #f59e0b, #d97706);
    }}
    .role-badge.admin {{
      background: linear-gradient(135deg, #dc2626, #b91c1c);
    }}
    
    @media (max-width: 768px) {{
      .sidebar {{
        transform: translateX(-100%);
        z-index: 50;
      }}
      .sidebar.mobile-open {{
        transform: translateX(0);
      }}
      .main-content {{
        margin-left: 0;
      }}
    }}
  </style>
</head>
<body class="min-h-screen text-white bg-gradient-to-br from-slate-950 via-indigo-950 to-fuchsia-900">
  
  <!-- Side Navigation -->
  <div id="sidebar" class="sidebar fixed left-0 top-0 h-full glass border-r border-white/10 z-30 flex flex-col">
    <!-- Logo & User Section -->
    <div class="p-4 border-b border-white/10">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl flex-shrink-0" style="background:linear-gradient(135deg,var(--brand),var(--accent))"></div>
        <div class="flex-1 min-w-0">
          <div class="text-lg font-semibold tracking-wide">Eraya Ops</div>
                <div id="userInfo" class="flex items-center gap-2 mt-1">
        <span class="text-xs text-white/60">Admin Access</span>
        <span class="role-badge admin">Full Access</span>
      </div>
    </div>
    <button id="sidebarToggle" class="p-2 hover:bg-white/10 rounded-lg">
      <span class="text-lg">⟨</span>
    </button>
  </div>
    </div>

    <!-- Navigation Menu -->
    <div class="flex-1 overflow-y-auto py-4" id="navigationMenu">
      <!-- Navigation will be loaded here by JavaScript -->
    </div>

    <!-- Quick Actions -->
    <div class="p-4 border-t border-white/10">
      <div class="sidebar-item" onclick="window.location.href='/hub'">
        <div class="sidebar-icon">🏠</div>
        <div class="sidebar-text">Home</div>
      </div>
    </div>
  </div>

  <!-- Main Content Area -->
  <div id="mainContent" class="main-content min-h-screen">
    <!-- Top Header (Mobile) -->
    <header class="sticky top-0 z-20 backdrop-blur bg-slate-900/40 border-b border-white/10 md:hidden">
      <div class="px-4 py-4 flex items-center justify-between">
        <button id="mobileMenuToggle" class="p-2 hover:bg-white/10 rounded-lg">
          <span class="text-lg">☰</span>
        </button>
        <div class="text-lg font-semibold">Eraya Ops</div>
        <div class="w-8"></div>
    </div>
  </header>

    <main class="px-4 py-10 md:px-8 lg:px-12">
    {body_html}
  </main>

  <footer class="border-t border-white/10 py-8 text-center text-white/70">
    Built with ❤️ for Eraya — {title}
  </footer>
  </div>

  <script>
    // Global state
    let sidebarCollapsed = false;

    // DOM elements
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const navigationMenu = document.getElementById('navigationMenu');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');

    // Toggle sidebar
    function toggleSidebar() {{
        sidebarCollapsed = !sidebarCollapsed;
        if (sidebarCollapsed) {{
            sidebar.classList.add('collapsed');
            mainContent.classList.add('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
        }} else {{
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟨</span>';
        }}
        // Save state
        localStorage.setItem('sidebarCollapsed', sidebarCollapsed.toString());
    }}

    // Mobile menu toggle
    function toggleMobileMenu() {{
        sidebar.classList.toggle('mobile-open');
    }}

    // Load navigation menu directly
    async function loadNavigation() {{
        try {{
            const response = await fetch('/api/navigation/admin');
            if (!response.ok) {{
                throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
            }}
            const data = await response.json();
            
            // Render navigation menu
            renderNavigationMenu(data.menu);
            
        }} catch (error) {{
            console.error('Error loading navigation:', error);
            navigationMenu.innerHTML = '<div class="text-center text-red-400 text-sm p-4">Error loading navigation</div>';
        }}
    }}

    // Render navigation menu
    function renderNavigationMenu(menuItems) {{
        let html = '';
        
        menuItems.forEach(item => {{
            if (item.type === 'separator') {{
                html += `<div class="sidebar-separator">${{item.name}}</div>`;
            }} else {{
                const activeClass = window.location.pathname === item.url ? 'active' : '';
                const disabledClass = !item.active ? 'disabled' : '';
                const badge = item.badge ? `<span class="sidebar-badge">${{item.badge}}</span>` : '';
                
                html += `
                    <a href="${{item.active ? item.url : '#'}}" class="sidebar-item ${{activeClass}} ${{disabledClass}}" ${{!item.active ? 'onclick="return false;"' : ''}}>
                        <div class="sidebar-icon">${{item.icon}}</div>
                        <div class="sidebar-text">${{item.name}}</div>
                        ${{badge}}
                    </a>
                `;
            }}
        }});
        
        navigationMenu.innerHTML = html;
    }}

    // Event listeners
    sidebarToggle.addEventListener('click', toggleSidebar);
    mobileMenuToggle?.addEventListener('click', toggleMobileMenu);

    // Initialize sidebar - ENSURE THIS RUNS AFTER DOM IS READY
    function initializeSidebar() {{
        // Restore sidebar collapsed state
        const savedCollapsed = localStorage.getItem('sidebarCollapsed');
        if (savedCollapsed === 'true') {{
            sidebarCollapsed = true;
            sidebar.classList.add('collapsed');
            mainContent.classList.add('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
        }}
        
        // Load navigation menu directly
        loadNavigation();
    }}
    
    // Initialize after a short delay to ensure DOM is ready
    setTimeout(initializeSidebar, 100);
    
    // Also initialize when DOM is fully loaded (backup)
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initializeSidebar);
    }} else {{
        // DOM is already loaded, initialize immediately as backup
        initializeSidebar();
    }}

    // Handle responsive behavior
    function handleResize() {{
        if (window.innerWidth < 768) {{
            mainContent.style.marginLeft = '0';
        }} else {{
            sidebar.classList.remove('mobile-open');
            mainContent.style.marginLeft = sidebarCollapsed ? '80px' : '280px';
        }}
    }}

    window.addEventListener('resize', handleResize);
    handleResize(); // Initial call

    // Close mobile menu when clicking outside
    document.addEventListener('click', function(e) {{
        if (window.innerWidth < 768 && !sidebar.contains(e.target) && !mobileMenuToggle?.contains(e.target)) {{
            sidebar.classList.remove('mobile-open');
        }}
    }});
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


# -------------------- DASHBOARD --------------------
@app.get("/hub")
def eraya_hub_home():
    body = """
    <!-- Header Section -->
    <section class="text-center">
      <h1 class="text-4xl md:text-5xl font-bold">Eraya Ops Hub</h1>
      <p class="mt-3 text-white/80">Fast, reliable tools for fulfillment — all in one place.</p>
    </section>

    <!-- Dashboard Overview Section -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Dashboard Overview</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5" id="statsCards">
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-blue-400" id="ordersToday">-</div>
          <p class="text-white/70 text-sm">Orders Today</p>
          <div id="shopifyStatus" class="mt-1 text-xs text-white/50">📊 Shopify</div>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-green-400" id="activeEmployees">-</div>
          <p class="text-white/70 text-sm">Active Employees</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-yellow-400" id="pendingOrders">-</div>
          <p class="text-white/70 text-sm">Pending Orders</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-purple-400" id="ordersWeek">-</div>
          <p class="text-white/70 text-sm">Orders This Week</p>
        </div>
      </div>
      
      <!-- Revenue Cards (Shopify Integration) -->
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-6" id="revenueCards">
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-emerald-400" id="todayRevenue">-</div>
          <p class="text-white/70 text-sm">Today's Revenue</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-teal-400" id="totalRevenue">-</div>
          <p class="text-white/70 text-sm">Total Revenue</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-cyan-400" id="fulfilledOrders">-</div>
          <p class="text-white/70 text-sm">Fulfilled Orders</p>
        </div>
      </div>
    </section>

    <!-- Quick Tools Section -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Quick Tools</h2>
      <div class="glass p-6">
        <div class="grid sm:grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Employee Lookup -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Employee Lookup</h3>
            <div class="flex gap-2">
              <input type="text" id="employeeSearch" placeholder="Search employee..." class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <button id="searchEmployeeBtn" class="btn btn-primary">Search</button>
            </div>
            <div id="employeeResults" class="mt-2 text-sm"></div>
          </div>
          
          <!-- Order Search -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Search Orders</h3>
            <div class="flex gap-2">
              <input type="text" id="orderSearch" placeholder="Order ID..." class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <button id="searchOrderBtn" class="btn btn-primary">Search</button>
            </div>
            <div id="orderResults" class="mt-2 text-sm text-white/70">Feature coming soon...</div>
          </div>
          
          <!-- Quick Export -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Quick Export</h3>
            <div class="flex gap-2">
              <select id="exportType" class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
                <option value="attendance">Attendance Data</option>
                <option value="orders" disabled>Orders Data (Soon)</option>
              </select>
              <button id="quickExportBtn" class="btn btn-secondary">Export</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Core Operations -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Core Operations</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <a href="/orders" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
               style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🧭</div>
          <h3 class="text-xl font-semibold">Order Organizer</h3>
        </div>
        <p class="text-white/70 mt-3">Clean CSVs, download photos/polaroids, generate back messages & exports.</p>
          <div class="mt-2 text-xs text-blue-400">Ready to process</div>
      </a>

      <a href="/packing" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
               style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📦</div>
          <h3 class="text-xl font-semibold">Packing Management</h3>
        </div>
        <p class="text-white/70 mt-3">Visual picker table with thumbnails & engraving details.</p>
          <div class="mt-2 text-xs text-green-400">Items ready to pack</div>
      </a>

        <a href="/attendance" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🗓️</div>
            <h3 class="text-xl font-semibold">Employee Attendance</h3>
        </div>
          <p class="text-white/70 mt-3">Track employee check-ins, hours, and generate reports.</p>
          <div class="mt-2 text-xs text-yellow-400" id="attendanceStatus">Loading...</div>
      </a>

        <a href="/attendance/report_page" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📊</div>
            <h3 class="text-xl font-semibold">Reports & Analytics</h3>
        </div>
          <p class="text-white/70 mt-3">Comprehensive attendance reports with filtering options.</p>
          <div class="mt-2 text-xs text-purple-400">View detailed reports</div>
        </a>

        <a href="/chat" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">💬</div>
            <h3 class="text-xl font-semibold">Team Chat</h3>
          </div>
          <p class="text-white/70 mt-3">Advanced team communication with channels, DMs, and reactions.</p>
          <div class="mt-2 text-xs text-blue-400">Real-time messaging</div>
        </a>
      </div>
    </section>

    <!-- Additional Modules -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Additional Modules</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📝</div>
            <h3 class="text-xl font-semibold">Content</h3>
          </div>
          <p class="text-white/70 mt-3">Manage product descriptions, images, and marketing content.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📢</div>
            <h3 class="text-xl font-semibold">Marketing</h3>
          </div>
          <p class="text-white/70 mt-3">Campaign management, social media, and promotional tools.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🚚</div>
            <h3 class="text-xl font-semibold">Orders & Fulfillment</h3>
          </div>
          <p class="text-white/70 mt-3">Advanced order management and shipping coordination.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🎧</div>
            <h3 class="text-xl font-semibold">Customer Service</h3>
          </div>
          <p class="text-white/70 mt-3">Support tickets, customer communications, and issue tracking.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📦</div>
            <h3 class="text-xl font-semibold">Inventory & Supplies</h3>
          </div>
          <p class="text-white/70 mt-3">Stock management, supplier relations, and procurement.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">👥</div>
            <h3 class="text-xl font-semibold">Team & Admin</h3>
          </div>
          <p class="text-white/70 mt-3">User management, permissions, and system administration.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">✅</div>
            <h3 class="text-xl font-semibold">Daily Tasks</h3>
          </div>
          <p class="text-white/70 mt-3">Task management, checklists, and workflow automation.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <a href="/pending" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">⏳</div>
            <h3 class="text-xl font-semibold">Pending Orders</h3>
          </div>
          <p class="text-white/70 mt-3">Flag missing photo/variant/back-message.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </a>
      </div>
    </section>

    <!-- Team Chat Widget -->
    <div id="chatWidget" class="fixed bottom-4 right-4 z-50">
      <div id="chatToggle" class="glass p-3 rounded-full cursor-pointer shadow-lg hover:scale-105 transition-transform">
        <div class="flex items-center gap-2">
          <span class="text-xl">💬</span>
          <span class="text-sm font-semibold">Team Chat</span>
          <div id="chatNotification" class="w-2 h-2 bg-red-500 rounded-full hidden"></div>
        </div>
      </div>
      
      <div id="chatPanel" class="hidden mt-2 glass rounded-lg shadow-xl" style="width: 300px; height: 400px;">
        <div class="p-3 border-b border-white/10">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold">Team Chat</h3>
            <button id="chatClose" class="text-white/60 hover:text-white">✕</button>
          </div>
        </div>
        
        <div id="chatMessages" class="flex-1 p-3 overflow-y-auto" style="height: 280px;">
          <div class="text-center text-white/60 text-sm">Loading messages...</div>
        </div>
        
        <div class="p-3 border-t border-white/10">
          <div class="flex items-center gap-2">
            <select id="chatEmployeeSelect" class="flex-1 rounded bg-slate-900/60 border border-white/10 px-2 py-1 text-xs">
              <option value="">Select your name</option>
            </select>
          </div>
          <div class="flex items-center gap-2 mt-2">
            <input type="text" id="chatMessage" placeholder="Type message..." class="flex-1 rounded bg-slate-900/60 border border-white/10 px-2 py-1 text-sm" maxlength="200">
            <button id="chatSend" class="btn btn-primary text-xs px-3 py-1">Send</button>
          </div>
        </div>
      </div>
    </div>

    <script>
      // Fetch and display dashboard stats
      async function loadDashboardStats() {
        try {
          const response = await fetch('/api/dashboard/stats');
          const stats = await response.json();
          
          document.getElementById('ordersToday').textContent = stats.total_orders_today;
          document.getElementById('activeEmployees').textContent = stats.active_employees;
          document.getElementById('pendingOrders').textContent = stats.pending_orders;
          document.getElementById('ordersWeek').textContent = stats.total_orders_week;
          
          // Update Shopify revenue data
          const currency = stats.currency || 'USD';
          document.getElementById('todayRevenue').textContent = `${currency} ${stats.today_revenue || 0}`;
          document.getElementById('totalRevenue').textContent = `${currency} ${stats.total_revenue || 0}`;
          document.getElementById('fulfilledOrders').textContent = stats.fulfilled_orders || 0;
          
          // Update Shopify connection status
          const shopifyStatusEl = document.getElementById('shopifyStatus');
          if (stats.shopify_configured) {
            shopifyStatusEl.textContent = '🛒 Connected';
            shopifyStatusEl.className = 'mt-1 text-xs text-green-400';
          } else {
            shopifyStatusEl.innerHTML = '⚠️ <a href="/shopify/settings" class="text-yellow-400 hover:text-yellow-300">Setup Required</a>';
            shopifyStatusEl.className = 'mt-1 text-xs text-yellow-400';
          }
          
          // Update attendance status
          const attendanceStatusEl = document.getElementById('attendanceStatus');
          if (stats.active_employees > 0) {
            attendanceStatusEl.textContent = `${stats.active_employees} employees working`;
            attendanceStatusEl.className = 'mt-2 text-xs text-green-400';
          } else {
            attendanceStatusEl.textContent = 'No one checked in';
            attendanceStatusEl.className = 'mt-2 text-xs text-red-400';
          }
          
        } catch (error) {
          console.error('Error loading dashboard stats:', error);
        }
      }

      // Employee search functionality
      document.getElementById('searchEmployeeBtn').addEventListener('click', async function() {
        const query = document.getElementById('employeeSearch').value;
        const resultsEl = document.getElementById('employeeResults');
        
        if (!query.trim()) {
          resultsEl.innerHTML = '<p class="text-red-400">Please enter a search term.</p>';
          return;
        }
        
        try {
          const response = await fetch(`/api/search/employee?query=${encodeURIComponent(query)}`);
          const data = await response.json();
          
          if (data.results.length === 0) {
            resultsEl.innerHTML = '<p class="text-yellow-400">No employees found.</p>';
          } else {
            let html = '<div class="space-y-1">';
            data.results.forEach(emp => {
              const statusColor = emp.status === 'Checked In' ? 'text-green-400' : 'text-red-400';
              html += `<div class="flex justify-between items-center p-2 bg-slate-800/50 rounded">
                <span><strong>${emp.name}</strong> (${emp.employee_id})</span>
                <span class="${statusColor}">${emp.status}</span>
              </div>`;
            });
            html += '</div>';
            resultsEl.innerHTML = html;
          }
        } catch (error) {
          resultsEl.innerHTML = '<p class="text-red-400">Error searching employees.</p>';
        }
      });

      // Quick export functionality
      document.getElementById('quickExportBtn').addEventListener('click', async function() {
        const exportType = document.getElementById('exportType').value;
        
        if (exportType === 'attendance') {
          try {
            const response = await fetch('/api/attendance/export');
            if (!response.ok) {
              alert('No attendance data to export.');
              return;
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'attendance_export.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
          } catch (error) {
            alert('Error exporting data.');
          }
        }
      });

      // Enter key support for searches
      document.getElementById('employeeSearch').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          document.getElementById('searchEmployeeBtn').click();
        }
      });

      // Load dashboard stats on page load
      loadDashboardStats();
      
      // Refresh stats every 30 seconds
      setInterval(loadDashboardStats, 30000);

      // ==================== TEAM CHAT FUNCTIONALITY ====================
      const chatToggle = document.getElementById('chatToggle');
      const chatPanel = document.getElementById('chatPanel');
      const chatClose = document.getElementById('chatClose');
      const chatEmployeeSelect = document.getElementById('chatEmployeeSelect');
      const chatMessage = document.getElementById('chatMessage');
      const chatSend = document.getElementById('chatSend');
      const chatMessages = document.getElementById('chatMessages');
      const chatNotification = document.getElementById('chatNotification');

      let lastMessageCount = 0;
      let isChatOpen = false;

      // Populate chat employee dropdown
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };

      for (const name in employees) {
          const option = document.createElement('option');
          option.value = employees[name];
          option.textContent = name;
          chatEmployeeSelect.appendChild(option);
      }

      // Toggle chat panel
      chatToggle.addEventListener('click', function() {
          isChatOpen = !isChatOpen;
          if (isChatOpen) {
              chatPanel.classList.remove('hidden');
              chatNotification.classList.add('hidden');
              loadChatMessages();
          } else {
              chatPanel.classList.add('hidden');
          }
      });

      chatClose.addEventListener('click', function() {
          isChatOpen = false;
          chatPanel.classList.add('hidden');
      });

      // Load chat messages
      async function loadChatMessages() {
          try {
              const response = await fetch('/api/chat/messages?limit=20');
              const data = await response.json();
              
              displayChatMessages(data.messages);
              
              // Show notification if new messages and chat is closed
              if (!isChatOpen && data.messages.length > lastMessageCount) {
                  chatNotification.classList.remove('hidden');
              }
              lastMessageCount = data.messages.length;
              
          } catch (error) {
              console.error('Error loading chat messages:', error);
              chatMessages.innerHTML = '<div class="text-center text-red-400 text-sm">Error loading messages</div>';
          }
      }

      // Display chat messages
      function displayChatMessages(messages) {
          if (messages.length === 0) {
              chatMessages.innerHTML = '<div class="text-center text-white/60 text-sm">No messages yet. Start the conversation!</div>';
              return;
          }

          let html = '';
          messages.forEach(msg => {
              const time = new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
              html += `
                  <div class="mb-3">
                      <div class="flex items-center gap-2 mb-1">
                          <span class="font-semibold text-sm text-blue-400">${msg.employee_name}</span>
                          <span class="text-xs text-white/50">${time}</span>
                      </div>
                      <div class="text-sm bg-slate-800/50 rounded-lg p-2">${msg.message}</div>
                  </div>
              `;
          });
          
          chatMessages.innerHTML = html;
          // Scroll to bottom
          chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      // Send message
      async function sendChatMessage() {
          const employeeId = chatEmployeeSelect.value;
          const message = chatMessage.value.trim();
          
          if (!employeeId) {
              alert('Please select your name first.');
              return;
          }
          
          if (!message) {
              alert('Please enter a message.');
              return;
          }
          
          try {
              const formData = new FormData();
              formData.append('employee_id', employeeId);
              formData.append('message', message);
              
              const response = await fetch('/api/chat/send', {
                  method: 'POST',
                  body: formData
              });
              
              if (response.ok) {
                  chatMessage.value = '';
                  loadChatMessages();
              } else {
                  alert('Error sending message.');
              }
              
          } catch (error) {
              console.error('Error sending message:', error);
              alert('Error sending message.');
          }
      }

      // Event listeners for sending messages
      chatSend.addEventListener('click', sendChatMessage);
      
      chatMessage.addEventListener('keypress', function(e) {
          if (e.key === 'Enter') {
              sendChatMessage();
          }
      });

      // Load messages initially and refresh every 10 seconds
      loadChatMessages();
      setInterval(loadChatMessages, 10000);
    </script>
    """
    return _eraya_lumen_page("Home", body)

@app.get("/orders")
def eraya_orders_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Management</h1>
      <p class="text-white/80 mt-2">Fetch and manage orders directly from your Shopify store.</p>
      
      <!-- Shopify Setup Notice -->
      <div id="shopifyNotice" class="bg-blue-500/20 border border-blue-500/30 rounded-xl p-4 mt-4" style="display: none;">
        <div class="flex items-center gap-3">
          <div class="text-2xl">ℹ️</div>
          <div>
            <div class="font-semibold text-blue-200">Shopify Setup Required</div>
            <div class="text-blue-300/80">Set environment variables: SHOPIFY_SHOP and SHOPIFY_TOKEN</div>
            <div class="text-xs text-blue-400 mt-1">
              Example: <code>set SHOPIFY_SHOP=your-store.myshopify.com</code> and <code>set SHOPIFY_TOKEN=your-token</code>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <div class="flex flex-wrap items-center gap-3">
            <button type="button" id="fetchOrders" class="btn btn-primary">Fetch from Shopify</button>
            <button type="button" id="exportOrders" class="btn btn-secondary">Export CSV (filtered)</button>
            <button type="button" id="exportSelected" class="btn btn-accent" disabled>Export Selected (<span id="selectedCount">0</span>)</button>
            <button type="button" id="downloadPhotos" class="btn btn-accent" disabled>Download Photos (<span id="selectedPhotos">0</span>)</button>
            <div id="status" class="text-white/70">🔄 Auto-fetching ALL orders...</div>
          </div>
          <div class="flex flex-wrap items-center gap-3 mt-2">
            <button type="button" id="selectAll" class="btn btn-sm btn-secondary">Select All</button>
            <button type="button" id="selectNone" class="btn btn-sm btn-secondary">Select None</button>
            <button type="button" id="selectFiltered" class="btn btn-sm btn-secondary">Select Filtered</button>
            <div class="text-white/60 text-sm" id="selectionInfo">No items selected</div>
          </div>
          <div class="flex flex-wrap gap-3 mt-3">
            <input id="qOrder" placeholder="Search Order #" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qProd" placeholder="Search Product" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qVar" placeholder="Search Variant" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <select id="qStatus" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="any">All Orders</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select id="pageSize" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
          </div>
        </div>

        <div class="glass p-0 overflow-auto" style="max-height:70vh">
          <table class="min-w-full text-sm" id="tbl">
            <thead class="sticky top-0 bg-slate-900/80 backdrop-blur" id="head"></thead>
            <tbody id="body"></tbody>
          </table>
        </div>
        
        <div class="flex items-center gap-3">
          <button id="prev" class="btn btn-secondary">Prev</button>
          <div id="pageinfo" class="text-white/70 text-sm"></div>
          <button id="next" class="btn btn-secondary">Next</button>
          <button id="loadMore" class="btn btn-primary" style="display: none;">Load More</button>
        </div>
      </div>

      <!-- Simple lightbox -->
      <div id="lb" class="fixed inset-0 hidden items-center justify-center bg-black/70 p-6">
        <div class="bg-slate-900/90 border border-white/10 rounded-2xl p-4 max-w-5xl w-full">
          <div class="flex justify-between items-center mb-3">
            <div class="text-lg font-semibold">Polaroids</div>
            <button id="lbClose" class="btn btn-secondary">Close</button>
          </div>
          <div id="lbBody" class="grid grid-cols-2 md:grid-cols-4 gap-3"></div>
        </div>
      </div>
    </section>

    <style>
      #body tr:nth-child(even){ background: rgba(255,255,255,0.03); }
      .badge-miss{ background:#ef4444; color:white; padding:2px 6px; border-radius:6px; font-size:12px; }
      #tbl tbody tr:hover { background-color: rgba(255,255,255,0.05); }
      #tbl th, #tbl td { padding: 0.75rem 0.5rem; text-align: left; vertical-align: top; }
      #tbl thead th { background-color: #0f172a; }
      
      /* Column Widths - adjusted for checkbox */
      #tbl th:nth-child(1), #tbl td:nth-child(1) { width: 4%; /* Checkbox */ }
      #tbl th:nth-child(2), #tbl td:nth-child(2) { width: 10%; /* Order Number */ }
      #tbl th:nth-child(3), #tbl td:nth-child(3) { width: 15%; /* Product Name */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(4), #tbl td:nth-child(4) { width: 10%; /* Variant */ }
      #tbl th:nth-child(5), #tbl td:nth-child(5) { width: 5%; /* Color */ }
      #tbl th:nth-child(6), #tbl td:nth-child(6) { width: 10%; /* Main Photo */ }
      #tbl th:nth-child(7), #tbl td:nth-child(7) { width: 10%; /* Polaroids */ }
      #tbl th:nth-child(8), #tbl td:nth-child(8) { width: 10%; /* Back Engraving Type */ }
      #tbl th:nth-child(9), #tbl td:nth-child(9) { width: 15%; /* Back Engraving Value */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(10), #tbl td:nth-child(10) { width: 6%; /* Main Photo Status */ }
      #tbl th:nth-child(11), #tbl td:nth-child(11) { width: 5%; /* Polaroid Count */ }
      
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .table-img { max-height: 80px; width: auto; }
      .btn-accent { background: linear-gradient(135deg, #8b5cf6, #a855f7); color: white; }
      .btn-accent:hover { background: linear-gradient(135deg, #7c3aed, #9333ea); }
      .btn-accent:disabled { opacity: 0.5; cursor: not-allowed; background: #6b7280; }
      .btn-sm { padding: 0.375rem 0.75rem; font-size: 0.875rem; }
      tr.selected { background-color: rgba(139, 92, 246, 0.2) !important; }
      .row-checkbox { transform: scale(1.2); }
    </style>

    <script>
      // elements
      var fetchBtn=document.getElementById('fetchOrders'), exportBtn=document.getElementById('exportOrders'), status=document.getElementById('status');
      var exportSelectedBtn=document.getElementById('exportSelected'), downloadPhotosBtn=document.getElementById('downloadPhotos');
      var selectAllBtn=document.getElementById('selectAll'), selectNoneBtn=document.getElementById('selectNone'), selectFilteredBtn=document.getElementById('selectFiltered');
      var qOrder=document.getElementById('qOrder'), qProd=document.getElementById('qProd'), qVar=document.getElementById('qVar');
      var head=document.getElementById('head'), body=document.getElementById('body'), pageSizeEl=document.getElementById('pageSize');
      var prev=document.getElementById('prev'), next=document.getElementById('next'), pageinfo=document.getElementById('pageinfo');
      var loadMoreBtn=document.getElementById('loadMore');
      var lb=document.getElementById('lb'), lbBody=document.getElementById('lbBody'), lbClose=document.getElementById('lbClose');
      var qStatus=document.getElementById('qStatus');

      // state
      var rows=[], filt=[], page=1, sortBy=null, sortDir=1, nextPageInfo=null;
      var selectedRows = new Set(); // Track selected row indices

      function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m];});}
      function td(h){return '<td class="border-t border-white/10 align-top">'+h+'</td>';}

      function imgFallback(el){el.onerror=null; el.src='https://via.placeholder.com/80?text=No+Img';}

      function openLB(urls){
        lbBody.innerHTML='';
        for(var i=0;i<urls.length;i++){
          var im=document.createElement('img'); im.loading='lazy'; im.src=urls[i];
          im.className='w-full h-40 object-cover rounded-xl border border-white/10';
          im.onerror=function(){ this.src='https://via.placeholder.com/160x160?text=No+Img'; };
          lbBody.appendChild(im);
        }
        lb.classList.remove('hidden'); lb.classList.add('flex');
      }
      lbClose.onclick=function(){lb.classList.add('hidden'); lb.classList.remove('flex');};
      lb.onclick=function(e){ if(e.target===lb) lbClose.onclick(); };

      function convertShopifyOrdersToRows(orders) {
        var converted = [];
        for(var i=0; i<orders.length; i++) {
          var order = orders[i];
          var lineItems = order.line_items || [];
          
          for(var j=0; j<lineItems.length; j++) {
            var item = lineItems[j];
            var properties = {};
            
            // Parse line item properties
            if(item.properties && Array.isArray(item.properties)) {
              for(var k=0; k<item.properties.length; k++) {
                var prop = item.properties[k];
                if(prop.name && prop.value) {
                  properties[prop.name.toLowerCase()] = prop.value;
                }
              }
            }
            
            // Extract data according to mapping rules
            var mainPhoto = properties['photo'] || properties['photo link'] || '';
            var polaroidStr = properties['polaroid'] || properties['your polaroid image'] || '';
            var polaroids = polaroidStr ? polaroidStr.split(/[,\\s]+/).map(function(s){return s.trim();}).filter(function(s){return s;}) : [];
            var backValue = properties['back message'] || properties['back engraving'] || '';
            
            var row = {
              'Order Number': order.name || ('#' + (order.order_number || order.id)),
              'Product Name': item.name || '',
              'Variant': item.variant_title || '',
              'Color': '', // Leave empty as requested
              'Main Photo': mainPhoto,
              'Polaroids': polaroids,
              'Back Engraving Type': backValue ? 'Back Message' : '',
              'Back Engraving Value': backValue,
              'Main Photo Status': mainPhoto ? 'Success' : '',
              'Polaroid Count': polaroids.length.toString()
            };
            
            converted.push(row);
          }
        }
        return converted;
      }

      function buildHead(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count'];
        var h='<tr>';
        
        // Add checkbox column header
        h+='<th class="text-left p-2 border-b border-white/10"><input type="checkbox" id="selectAllCheckbox" class="row-checkbox" title="Select All Visible"></th>';
        
        for(var i=0;i<cols.length;i++){
          var c=cols[i]; var arrow=(sortBy===c?(sortDir>0?' ▲':' ▼'):'');
          h+='<th class="text-left p-2 border-b border-white/10 cursor-pointer" data-col="'+esc(c)+'">'+esc(c)+arrow+'</th>';
        }
        h+='</tr>';
        head.innerHTML=h;
        
        // Add event listeners for sorting
        var ths=head.querySelectorAll('th[data-col]');
        for(var k=0;k<ths.length;k++){
          ths[k].onclick=function(){
            var c=this.getAttribute('data-col');
            if(sortBy===c) sortDir=-sortDir; else {sortBy=c; sortDir=1;}
            applyFilters();
          };
        }
        
        // Add event listener for select all checkbox
        document.getElementById('selectAllCheckbox').onchange = function() {
          if (this.checked) {
            selectAllVisible();
          } else {
            selectNoneVisible();
          }
        };
      }

      function applyFilters(){
        var o=qOrder.value.trim().toLowerCase(), p=qProd.value.trim().toLowerCase(), v=qVar.value.trim().toLowerCase();
        filt=rows.filter(function(r){
          var ok=true;
          if(o) ok = ok && String(r['Order Number']||'').toLowerCase().indexOf(o)>=0;
          if(p) ok = ok && String(r['Product Name']||'').toLowerCase().indexOf(p)>=0;
          if(v) ok = ok && String(r['Variant']||'').toLowerCase().indexOf(v)>=0;
          return ok;
        });
        if(sortBy){
          filt.sort(function(a,b){
            var av=String(a[sortBy]||'').toLowerCase(), bv=String(b[sortBy]||'').toLowerCase();
            if(av<bv) return -1*sortDir; if(av>bv) return 1*sortDir; return 0;
          });
        }
        page=1; render();
      }

      function render(){
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        var out='';
        for(var i=start;i<end;i++){
          var r=filt[i];
          var globalIdx = rows.indexOf(r); // Get global index for selection tracking
          var isSelected = selectedRows.has(globalIdx);
          
          var main=r['Main Photo'] ? '<img loading="lazy" src="'+esc(r['Main Photo'])+'" class="w-20 h-20 object-cover rounded-lg border border-white/10 table-img" onerror="imgFallback(this)">' : '<span class="badge-miss">Missing photo</span>';
          var polys=r['Polaroids']||[]; var thumbs='';
          for(var t=0; t<Math.min(3,polys.length); t++){
            thumbs+='<img loading="lazy" src="'+esc(polys[t])+'" class="w-14 h-14 object-cover rounded-md border border-white/10 table-img" onerror="imgFallback(this)" style="margin-right:4px">';
          }
          var more=polys.length>3?('<div class="text-xs text-white/60">+'+(polys.length-3)+' more</div>'):'';
          var gallery='<a href="#" class="gal" data-idx="'+i+'"><div class="flex gap-2 flex-wrap">'+thumbs+more+'</div></a>';
          var engr=String(r['Back Engraving Value']||'').trim()?('<div class="truncate" style="white-space:pre-wrap">'+esc(r['Back Engraving Value'])+'</div>'):'<span class="badge-miss">Missing</span>';

          out+='<tr class="'+(isSelected?'selected':'')+'" data-global-idx="'+globalIdx+'">'+
            td('<input type="checkbox" class="row-checkbox" data-idx="'+globalIdx+'" '+(isSelected?'checked':'')+'>')+
            td(esc(r['Order Number']))+td(esc(r['Product Name']))+td(esc(r['Variant']))+td(esc(r['Color']))+
            td(main)+td(gallery)+td(esc(r['Back Engraving Type']))+td(engr)+td(esc(r['Main Photo Status']))+td(esc(r['Polaroid Count']))+
          '</tr>';
        }
        body.innerHTML=out;

        // Add event listeners for gallery links
        var links=body.querySelectorAll('a.gal');
        for(var g=0; g<links.length; g++){
          links[g].onclick=function(e){
            e.preventDefault();
            var idx=parseInt(this.getAttribute('data-idx')||'-1',10);
            if(idx>=0 && idx<filt.length){
              var urls=filt[idx]['Polaroids']||[];
              if(urls.length) openLB(urls);
            }
          };
        }
        
        // Add event listeners for checkboxes
        var checkboxes = body.querySelectorAll('.row-checkbox');
        for(var c=0; c<checkboxes.length; c++){
          checkboxes[c].onchange = function(){
            var idx = parseInt(this.getAttribute('data-idx'));
            var row = this.closest('tr');
            if(this.checked) {
              selectedRows.add(idx);
              row.classList.add('selected');
            } else {
              selectedRows.delete(idx);
              row.classList.remove('selected');
            }
            updateSelectionUI();
          };
        }

        var total=filt.length, pages=Math.max(1, Math.ceil(total/per));
        pageinfo.textContent='Page '+page+' / '+pages+' — '+total+' rows';
        prev.disabled=page<=1; next.disabled=page>=pages;
        
        // Hide load more button since we auto-load everything
        loadMoreBtn.style.display = 'none';
        
        // Update selection UI
        updateSelectionUI();
      }

      prev.onclick=function(){ if(page>1){ page--; render(); } };
      next.onclick=function(){ var per=parseInt(pageSizeEl.value,10)||25; var pages=Math.max(1,Math.ceil(filt.length/per)); if(page<pages){ page++; render(); } };
      pageSizeEl.onchange=applyFilters;
      qOrder.oninput=qProd.oninput=qVar.oninput=applyFilters;

      window.imgFallback = imgFallback; // make global for onerror attr
      
      // Selection functions
      function updateSelectionUI() {
        var selectedCount = selectedRows.size;
        var selectedWithPhotos = 0;
        
        selectedRows.forEach(function(idx) {
          if (rows[idx] && rows[idx]['Main Photo']) {
            selectedWithPhotos++;
          }
        });
        
        document.getElementById('selectedCount').textContent = selectedCount;
        document.getElementById('selectedPhotos').textContent = selectedWithPhotos;
        
        exportSelectedBtn.disabled = selectedCount === 0;
        downloadPhotosBtn.disabled = selectedWithPhotos === 0;
        
        document.getElementById('selectionInfo').textContent = 
          selectedCount === 0 ? 'No items selected' : 
          selectedCount + ' items selected (' + selectedWithPhotos + ' with photos)';
      }
      
      function selectAllVisible() {
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        for(var i=start; i<end; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.add(globalIdx);
        }
        render();
      }
      
      function selectNoneVisible() {
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        for(var i=start; i<end; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.delete(globalIdx);
        }
        render();
      }
      
      function selectAll() {
        selectedRows.clear();
        for(var i=0; i<rows.length; i++) {
          selectedRows.add(i);
        }
        render();
      }
      
      function selectNone() {
        selectedRows.clear();
        render();
      }
      
      function selectFiltered() {
        selectedRows.clear();
        for(var i=0; i<filt.length; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.add(globalIdx);
        }
        render();
      }

      function fetchOrdersFromShopify() {
        status.textContent='🔄 Fetching ALL orders from Shopify...'; 
        head.innerHTML=''; 
        body.innerHTML='';
        fetchBtn.disabled = true;
        fetchBtn.textContent = '🔄 Fetching All Orders...';
        rows = []; // Reset rows
        
        // Fetch all orders recursively
        fetchAllOrdersRecursively(null, 0);
      }
      
      function fetchAllOrdersRecursively(pageInfo, totalFetched) {
        var selectedStatus = qStatus.value;
        var url = '/api/shopify/orders?status='+encodeURIComponent(selectedStatus)+'&limit=250'; // Max limit
        if (pageInfo) {
          url += '&page_info='+encodeURIComponent(pageInfo);
        }
        
        fetch(url)
          .then(function(res){ 
            return res.text().then(function(t){ 
              return {ok:res.ok, status:res.status, text:t};
            }); 
          })
          .then(function(x){
            if(!x.ok){ 
              var errorMsg = 'Error: ';
              try {
                var errorData = JSON.parse(x.text);
                errorMsg += errorData.detail || x.text;
                
                // Show setup notice if it's a configuration error
                if (errorData.detail && (errorData.detail.includes('Shopify configuration missing') || errorData.detail.includes('configure via /shopify/settings'))) {
                  var notice = document.getElementById('shopifyNotice');
                  notice.style.display = 'block';
                  // Add link to Shopify settings
                  notice.innerHTML = notice.innerHTML.replace('</div></div>', 
                    '<div class="text-xs text-blue-400 mt-2">' +
                    '<a href="/shopify/settings" class="text-blue-300 hover:text-blue-200 underline">Or configure via Shopify Settings page →</a>' +
                    '</div></div></div>');
                }
              } catch(e) {
                errorMsg += x.text || ('HTTP ' + x.status);
              }
              status.textContent = errorMsg;
              fetchBtn.disabled = false;
              fetchBtn.textContent = 'Fetch from Shopify';
              return; 
            }
            
            // Hide setup notice on successful fetch
            document.getElementById('shopifyNotice').style.display = 'none';
            var data; 
            try{ 
              data=JSON.parse(x.text); 
            } catch(e){ 
              status.textContent='Bad JSON from server';
              fetchBtn.disabled = false;
              fetchBtn.textContent = 'Fetch from Shopify';
              return; 
            }
            
            var orders = data.orders || [];
            var newRows = convertShopifyOrdersToRows(orders);
            rows = rows.concat(newRows);
            totalFetched += orders.length;
            
            // Update status with progress
            status.textContent='🔄 Fetched '+totalFetched+' orders ('+rows.length+' line items)' + (data.next_page_info ? ' - Loading more...' : ' - Complete!');
            
            // Update display with current data
            if (rows.length > 0) {
              buildHead(); 
              applyFilters();
            }
            
            // Continue fetching if there are more pages
            if (data.next_page_info) {
              nextPageInfo = data.next_page_info;
              // Small delay to prevent overwhelming the API
              setTimeout(function() {
                fetchAllOrdersRecursively(data.next_page_info, totalFetched);
              }, 200);
            } else {
              // All done!
              nextPageInfo = null;
              status.textContent='✅ Loaded ALL '+totalFetched+' orders ('+rows.length+' line items)';
              fetchBtn.disabled = false;
              fetchBtn.textContent = 'Fetch from Shopify';
            }
          })
          .catch(function(err){ 
            console.error('Fetch error:', err); 
            status.textContent='❌ Network error: ' + err.message;
            fetchBtn.disabled = false;
            fetchBtn.textContent = 'Fetch from Shopify';
          });
      }

      fetchBtn.onclick = fetchOrdersFromShopify;
      
      loadMoreBtn.onclick=function(){
        if(!nextPageInfo) return;
        status.textContent='Loading more...';
        var selectedStatus = qStatus.value;
        fetch('/api/shopify/orders?status='+encodeURIComponent(selectedStatus)+'&limit=100&page_info='+encodeURIComponent(nextPageInfo))
          .then(function(res){ return res.text().then(function(t){ return {ok:res.ok, text:t};}); })
          .then(function(x){
            if(!x.ok){ status.textContent='Error: '+x.text; return; }
            var data; try{ data=JSON.parse(x.text); }catch(e){ status.textContent='Bad JSON from server'; return; }
            var orders = data.orders || [];
            nextPageInfo = data.next_page_info;
            var newRows = convertShopifyOrdersToRows(orders);
            rows = rows.concat(newRows);
            status.textContent='Loaded '+rows.length+' total line items';
            applyFilters(); // Refresh display with new data
          })
          .catch(function(err){ console.error(err); status.textContent='Unexpected error loading more'; });
      };

      exportBtn.onclick=function(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<filt.length;i++){
          var r=filt[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+('\\n');
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='shopify_orders_filtered.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
      
      // Export selected orders
      exportSelectedBtn.onclick=function(){
        var selectedData = [];
        selectedRows.forEach(function(idx) {
          if (rows[idx]) {
            selectedData.push(rows[idx]);
          }
        });
        
        if (selectedData.length === 0) {
          alert('No orders selected for export');
          return;
        }
        
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<selectedData.length;i++){
          var r=selectedData[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+('\\n');
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='shopify_orders_selected.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
      
      // Download photos in bulk
      downloadPhotosBtn.onclick=function(){
        var photosToDownload = [];
        selectedRows.forEach(function(idx) {
          if (rows[idx] && rows[idx]['Main Photo']) {
            photosToDownload.push({
              url: rows[idx]['Main Photo'],
              filename: 'photo_' + (rows[idx]['Order Number'] || idx).replace(/[^a-zA-Z0-9]/g, '_') + '.jpg'
            });
          }
        });
        
        if (photosToDownload.length === 0) {
          alert('No photos available in selected orders');
          return;
        }
        
        // Download each photo
        photosToDownload.forEach(function(photo, index) {
          setTimeout(function() {
            var a = document.createElement('a');
            a.href = photo.url;
            a.download = photo.filename;
            a.target = '_blank';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }, index * 100); // Small delay between downloads
        });
        
        status.textContent = '📸 Downloading ' + photosToDownload.length + ' photos...';
      };
      
      // Selection button event listeners
      selectAllBtn.onclick = selectAll;
      selectNoneBtn.onclick = selectNone;
      selectFilteredBtn.onclick = selectFiltered;
      
      // Auto-fetch orders when page loads
      document.addEventListener('DOMContentLoaded', function() {
        console.log('Page loaded, auto-fetching orders...');
        setTimeout(function() {
          fetchOrdersFromShopify();
        }, 500); // Small delay to ensure everything is initialized
      });
      
      // Also auto-fetch if DOM is already loaded
      if (document.readyState === 'loading') {
        // DOMContentLoaded listener above will handle this
      } else {
        // DOM is already loaded
        console.log('DOM already loaded, auto-fetching orders...');
        setTimeout(function() {
          fetchOrdersFromShopify();
        }, 100);
      }
    </script>
    """
    return _eraya_lumen_page("Order Management", body)

# -------------------- DASHBOARD STATS API --------------------
@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    # Count active employees (currently checked in)
    active_employees = 0
    total_employees = 0
    employee_names = []
    
    for emp_id, records in ATTENDANCE_RECORDS.items():
        total_employees += 1
        # Get employee name
        emp_name = None
        for name, id_val in EMPLOYEES.items():
            if id_val == emp_id:
                emp_name = name
                break
        
        # Check if currently checked in (last record has no check_out_time)
        if records and "check_out_time" not in records[-1]:
            active_employees += 1
            employee_names.append(emp_name or emp_id)
    
    # Get Shopify data if configured
    shopify_data = {}
    if SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]:
        try:
            shopify_analytics = fetch_shopify_analytics()
            shopify_data = {
                "total_orders_today": shopify_analytics.get("today_orders", 0),
                "total_orders_week": shopify_analytics.get("total_orders", 0),
                "pending_orders": shopify_analytics.get("pending_orders", 0),
                "total_revenue": shopify_analytics.get("total_revenue", 0),
                "today_revenue": shopify_analytics.get("today_revenue", 0),
                "currency": shopify_analytics.get("currency", "USD"),
                "fulfilled_orders": shopify_analytics.get("fulfilled_orders", 0)
            }
        except Exception as e:
            print(f"Error fetching Shopify data for dashboard: {e}")
            shopify_data = {
                "total_orders_today": 0,
                "total_orders_week": 0,
                "pending_orders": 0,
                "total_revenue": 0,
                "today_revenue": 0,
                "currency": "USD",
                "fulfilled_orders": 0
            }
    else:
        # Placeholder data when Shopify not configured
        shopify_data = {
            "total_orders_today": 12,  # Placeholder
            "total_orders_week": 156,  # Placeholder
            "pending_orders": 23,  # Placeholder
            "total_revenue": 45678.90,  # Placeholder
            "today_revenue": 1234.56,  # Placeholder
            "currency": "USD",
            "fulfilled_orders": 133
        }

    stats = {
        **shopify_data,
        "active_employees": active_employees,
        "total_employees": len(EMPLOYEES),
        "active_employee_names": employee_names,
        "shopify_configured": bool(SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]),
        "recent_activity": []  # Can be enhanced later
    }
    
    return JSONResponse(content=stats)

@app.get("/api/search/employee")
def search_employee(query: str):
    results = []
    query_lower = query.lower()
    for name, emp_id in EMPLOYEES.items():
        if query_lower in name.lower() or query_lower in emp_id.lower():
            # Get current status
            status = "Unknown"
            if emp_id in ATTENDANCE_RECORDS and ATTENDANCE_RECORDS[emp_id]:
                last_record = ATTENDANCE_RECORDS[emp_id][-1]
                status = "Checked In" if "check_out_time" not in last_record else "Checked Out"
            
            results.append({
                "name": name,
                "employee_id": emp_id,
                "status": status
            })
    
    return JSONResponse(content={"results": results})

# -------------------- TEAM CHAT API --------------------
@app.post("/api/chat/send")
def send_message(employee_id: str = Form(...), message: str = Form(...)):
    if not employee_id or not message.strip():
        raise HTTPException(status_code=400, detail="Employee ID and message are required.")
    
    # Get employee name
    employee_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == employee_id:
            employee_name = name
            break
    
    if not employee_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Create message object
    chat_message = {
        "id": len(CHAT_MESSAGES) + 1,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "message": message.strip(),
        "timestamp": get_timestamp()
    }
    
    CHAT_MESSAGES.append(chat_message)
    
    # Keep only last 100 messages to prevent memory issues
    if len(CHAT_MESSAGES) > 100:
        CHAT_MESSAGES.pop(0)
    
    return JSONResponse(content={"status": "success", "message": "Message sent successfully."})

@app.get("/api/chat/messages")
def get_messages(limit: int = 20):
    # Return the most recent messages
    recent_messages = CHAT_MESSAGES[-limit:] if len(CHAT_MESSAGES) > limit else CHAT_MESSAGES
    return JSONResponse(content={"messages": recent_messages})

# -------------------- ADVANCED CHAT API --------------------
@app.post("/api/chat/channel/send")
def send_channel_message(channel: str = Form(...), employee_id: str = Form(...), message: str = Form(...), file_info: str = Form(None)):
    if channel not in CHAT_CHANNELS:
        raise HTTPException(status_code=400, detail="Invalid channel.")
    
    if not employee_id or (not message.strip() and not file_info):
        raise HTTPException(status_code=400, detail="Employee ID and message or file are required.")
    
    # Get employee name
    employee_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == employee_id:
            employee_name = name
            break
    
    if not employee_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Process links in message
    links = []
    if message.strip():
        found_links = extract_links_from_message(message)
        links = [get_link_preview(link) for link in found_links]
    
    # Parse file info if provided
    file_attachment = None
    if file_info:
        try:
            import json
            file_attachment = json.loads(file_info)
        except:
            pass
    
    # Create message object
    message_id = f"{channel}_{len(CHAT_CHANNELS[channel]['messages']) + 1}_{get_timestamp()}"
    chat_message = {
        "id": message_id,
        "channel": channel,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "message": message.strip(),
        "timestamp": get_timestamp(),
        "edited": False,
        "edited_at": None,
        "file_attachment": file_attachment,
        "links": links
    }
    
    CHAT_CHANNELS[channel]["messages"].append(chat_message)
    
    # Keep only last 200 messages per channel
    if len(CHAT_CHANNELS[channel]["messages"]) > 200:
        CHAT_CHANNELS[channel]["messages"].pop(0)
    
    return JSONResponse(content={"status": "success", "message": "Message sent successfully.", "message_id": message_id})

@app.get("/api/chat/channel/{channel_name}")
def get_channel_messages(channel_name: str, limit: int = 50):
    if channel_name not in CHAT_CHANNELS:
        raise HTTPException(status_code=404, detail="Channel not found.")
    
    messages = CHAT_CHANNELS[channel_name]["messages"]
    recent_messages = messages[-limit:] if len(messages) > limit else messages
    
    # Add reactions to messages
    for msg in recent_messages:
        msg["reactions"] = MESSAGE_REACTIONS.get(msg["id"], {})
    
    return JSONResponse(content={
        "channel": channel_name,
        "channel_name": CHAT_CHANNELS[channel_name]["name"],
        "messages": recent_messages
    })

@app.get("/api/chat/channels")
def get_channels():
    channels_info = []
    for channel_id, channel_data in CHAT_CHANNELS.items():
        unread_count = len(channel_data["messages"])  # Simplified - in real app, track per user
        channels_info.append({
            "id": channel_id,
            "name": channel_data["name"],
            "unread_count": min(unread_count, 99),  # Cap at 99
            "last_message": channel_data["messages"][-1] if channel_data["messages"] else None
        })
    
    return JSONResponse(content={"channels": channels_info})

@app.post("/api/chat/dm/send")
def send_direct_message(to_employee_id: str = Form(...), from_employee_id: str = Form(...), message: str = Form(...), file_info: str = Form(None)):
    if not to_employee_id or not from_employee_id or (not message.strip() and not file_info):
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    # Validate employee IDs
    from_name = None
    to_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == from_employee_id:
            from_name = name
        if emp_id == to_employee_id:
            to_name = name
    
    if not from_name or not to_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Create DM key (consistent ordering)
    dm_key = "_".join(sorted([from_employee_id, to_employee_id]))
    
    if dm_key not in DIRECT_MESSAGES:
        DIRECT_MESSAGES[dm_key] = []
    
    # Process links in message
    links = []
    if message.strip():
        found_links = extract_links_from_message(message)
        links = [get_link_preview(link) for link in found_links]
    
    # Parse file info if provided
    file_attachment = None
    if file_info:
        try:
            import json
            file_attachment = json.loads(file_info)
        except:
            pass
    
    # Create message object
    message_id = f"dm_{dm_key}_{len(DIRECT_MESSAGES[dm_key]) + 1}_{get_timestamp()}"
    dm_message = {
        "id": message_id,
        "from_employee_id": from_employee_id,
        "from_employee_name": from_name,
        "to_employee_id": to_employee_id,
        "to_employee_name": to_name,
        "message": message.strip(),
        "timestamp": get_timestamp(),
        "edited": False,
        "edited_at": None,
        "file_attachment": file_attachment,
        "links": links
    }
    
    DIRECT_MESSAGES[dm_key].append(dm_message)
    
    # Keep only last 500 DM messages
    if len(DIRECT_MESSAGES[dm_key]) > 500:
        DIRECT_MESSAGES[dm_key].pop(0)
    
    return JSONResponse(content={"status": "success", "message": "DM sent successfully.", "message_id": message_id})

# -------------------- SHOPIFY API ENDPOINTS --------------------

@app.get("/api/shopify/analytics")
def get_shopify_analytics():
    """Get analytics data from Shopify store."""
    try:
        analytics = fetch_shopify_analytics()
        
        # Cache the analytics
        SHOPIFY_CACHE["analytics"] = analytics
        SHOPIFY_CACHE["last_updated"] = get_timestamp()
        
        return JSONResponse(content=analytics)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching analytics: {str(e)}")

@app.post("/api/shopify/config")
def configure_shopify(store_name: str = Form(...), access_token: str = Form(...)):
    """Configure Shopify store connection."""
    try:
        # Test the connection
        old_config = SHOPIFY_CONFIG.copy()
        SHOPIFY_CONFIG["store_name"] = store_name.strip()
        SHOPIFY_CONFIG["access_token"] = access_token.strip()
        
        # Test API call
        test_data = make_shopify_request("shop.json")
        shop_info = test_data.get("shop", {})
        
        return JSONResponse(content={
            "success": True,
            "message": "Shopify store connected successfully!",
            "shop_name": shop_info.get("name", store_name),
            "shop_domain": shop_info.get("domain", f"{store_name}.myshopify.com"),
            "currency": shop_info.get("currency", "USD")
        })
    except Exception as e:
        # Restore old config on error
        SHOPIFY_CONFIG.update(old_config)
        raise HTTPException(status_code=400, detail=f"Failed to connect to Shopify: {str(e)}")

@app.get("/api/shopify/config")
def get_shopify_config():
    """Get current Shopify configuration status."""
    return JSONResponse(content={
        "configured": bool(SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]),
        "store_name": SHOPIFY_CONFIG["store_name"],
        "api_version": SHOPIFY_CONFIG["api_version"],
        "last_updated": SHOPIFY_CACHE.get("last_updated")
    })

@app.get("/api/shopify/orders")
def api_shopify_orders(
    status: str = "any",
    limit: int = 250,  # Default to maximum for efficiency
    page_info: str = None,
    created_at_min: str = None,
    created_at_max: str = None
):
    """Fetch orders from Shopify with pagination support."""
    try:
        params = {
            "limit": min(limit, 250),  # Shopify max is 250
            "status": status,
            "fields": "id,name,order_number,created_at,financial_status,fulfillment_status,customer,email,order_status_url,line_items"
        }
        
        # Add optional parameters
        if page_info:
            params["page_info"] = page_info
        if created_at_min:
            params["created_at_min"] = created_at_min
        if created_at_max:
            params["created_at_max"] = created_at_max
            
        # Call Shopify API
        data = _shopify_get("/orders.json", params)
        
        return JSONResponse(content={
            "orders": data.get("orders", []),
            "next_page_info": data["_pagination"]["next_page_info"],
            "prev_page_info": data["_pagination"]["prev_page_info"]
        })
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Shopify orders: {str(e)}")

# -------------------- USER ROLES & NAVIGATION API --------------------
@app.get("/api/user/{employee_id}/role")
def get_user_role(employee_id: str):
    if employee_id not in USER_ROLES:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user_info = USER_ROLES[employee_id]
    return JSONResponse(content={
        "employee_id": employee_id,
        "name": user_info["name"],
        "role": user_info["role"],
        "permissions": user_info["permissions"]
    })

@app.get("/api/navigation/{role}")
def get_navigation_menu(role: str):
    # Everyone gets the same unified menu now
    return JSONResponse(content={"role": role, "menu": UNIFIED_NAVIGATION_MENU})

@app.get("/api/user/{employee_id}/navigation")
def get_user_navigation(employee_id: str):
    if employee_id not in USER_ROLES:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user_role = USER_ROLES[employee_id]["role"]
    # Everyone gets the same unified menu now
    
    return JSONResponse(content={
        "employee_id": employee_id,
        "role": user_role,
        "menu": UNIFIED_NAVIGATION_MENU
    })

@app.get("/api/chat/dm/{other_employee_id}")
def get_direct_messages(other_employee_id: str, current_employee_id: str, limit: int = 50):
    # Create DM key
    dm_key = "_".join(sorted([current_employee_id, other_employee_id]))
    
    if dm_key not in DIRECT_MESSAGES:
        return JSONResponse(content={"messages": []})
    
    messages = DIRECT_MESSAGES[dm_key]
    recent_messages = messages[-limit:] if len(messages) > limit else messages
    
    # Add reactions to messages
    for msg in recent_messages:
        msg["reactions"] = MESSAGE_REACTIONS.get(msg["id"], {})
    
    return JSONResponse(content={"messages": recent_messages})

@app.post("/api/chat/reaction/add")
def add_reaction(message_id: str = Form(...), employee_id: str = Form(...), emoji: str = Form(...)):
    if not message_id or not employee_id or not emoji:
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    if message_id not in MESSAGE_REACTIONS:
        MESSAGE_REACTIONS[message_id] = {}
    
    if emoji not in MESSAGE_REACTIONS[message_id]:
        MESSAGE_REACTIONS[message_id][emoji] = []
    
    if employee_id not in MESSAGE_REACTIONS[message_id][emoji]:
        MESSAGE_REACTIONS[message_id][emoji].append(employee_id)
    
    return JSONResponse(content={"status": "success", "message": "Reaction added."})

@app.post("/api/chat/reaction/remove")
def remove_reaction(message_id: str = Form(...), employee_id: str = Form(...), emoji: str = Form(...)):
    if not message_id or not employee_id or not emoji:
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    if message_id in MESSAGE_REACTIONS and emoji in MESSAGE_REACTIONS[message_id]:
        if employee_id in MESSAGE_REACTIONS[message_id][emoji]:
            MESSAGE_REACTIONS[message_id][emoji].remove(employee_id)
            
            # Clean up empty reactions
            if not MESSAGE_REACTIONS[message_id][emoji]:
                del MESSAGE_REACTIONS[message_id][emoji]
            if not MESSAGE_REACTIONS[message_id]:
                del MESSAGE_REACTIONS[message_id]
    
    return JSONResponse(content={"status": "success", "message": "Reaction removed."})

@app.post("/api/chat/status/update")
def update_user_status(employee_id: str = Form(...), status: str = Form("online")):
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")
    
    USER_STATUS[employee_id] = {
        "status": status,
        "last_seen": get_timestamp()
    }
    
    return JSONResponse(content={"status": "success", "message": "Status updated."})

@app.get("/api/chat/users/online")
def get_online_users():
    online_users = []
    current_time = datetime.datetime.utcnow()
    
    for emp_id, status_info in USER_STATUS.items():
        last_seen = datetime.datetime.fromisoformat(status_info["last_seen"])
        # Consider user online if they were active in the last 5 minutes
        if (current_time - last_seen).total_seconds() < 300:
            # Get employee name
            emp_name = None
            for name, id_val in EMPLOYEES.items():
                if id_val == emp_id:
                    emp_name = name
                    break
            
            online_users.append({
                "employee_id": emp_id,
                "employee_name": emp_name or emp_id,
                "status": status_info["status"],
                "last_seen": status_info["last_seen"]
            })
    
    return JSONResponse(content={"online_users": online_users})

@app.post("/api/chat/upload")
async def upload_chat_file(file: UploadFile = File(...), employee_id: str = Form(...)):
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")
    
    # Validate file size (max 10MB)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max size is 10MB.")
    
    # Generate unique filename
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = UPLOADS_DIR / unique_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Get file info
        file_type = get_file_type(file.filename)
        file_size = len(content)
        
        # Create file info object
        file_info = {
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "unique_filename": unique_filename,
            "file_type": file_type,
            "file_size": file_size,
            "uploaded_by": employee_id,
            "upload_time": get_timestamp(),
            "url": f"/uploads/chat/{unique_filename}"
        }
        
        return JSONResponse(content={"status": "success", "file": file_info})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


# -------------------- ATTENDANCE --------------------
@app.post("/api/attendance/check_in")
def check_in(employee_id: str = Form(...)):
    if employee_id not in ATTENDANCE_RECORDS:
        ATTENDANCE_RECORDS[employee_id] = []
    
    # Check if already checked in
    if ATTENDANCE_RECORDS[employee_id] and "check_out_time" not in ATTENDANCE_RECORDS[employee_id][-1]:
        raise HTTPException(status_code=400, detail="Already checked in.")

    ATTENDANCE_RECORDS[employee_id].append({"check_in_time": get_timestamp()})
    return JSONResponse(content={"status": "success", "message": "Checked in successfully."})

@app.post("/api/attendance/check_out")
def check_out(employee_id: str = Form(...)):
    if employee_id not in ATTENDANCE_RECORDS or not ATTENDANCE_RECORDS[employee_id]:
        raise HTTPException(status_code=400, detail="Not checked in yet.")
    
    last_record = ATTENDANCE_RECORDS[employee_id][-1]
    if "check_out_time" in last_record:
        raise HTTPException(status_code=400, detail="Already checked out.")

    last_record["check_out_time"] = get_timestamp()
    return JSONResponse(content={"status": "success", "message": "Checked out successfully."})

@app.get("/api/attendance/records")
def get_attendance_records(employee_id: str | None = None, date: str | None = None):
    filtered_records = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        
        emp_filtered_records = []
        for record in records:
            if date:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).strftime("%Y-%m-%d")
                if record_date != date:
                    continue
            emp_filtered_records.append(record)
        
        if emp_filtered_records:
            filtered_records[emp_id] = emp_filtered_records
            
    return JSONResponse(content=filtered_records)

@app.get("/api/attendance/report")
def get_attendance_report(employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    report = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        
        total_hours = 0.0
        for record in records:
            if "check_in_time" in record and "check_out_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
                total_hours += calculate_duration(record["check_in_time"], record["check_out_time"])
        if total_hours > 0 or not records: # Include employee even if 0 hours, but not if no records
             report[emp_id] = {"total_hours": round(total_hours, 2)}
    return JSONResponse(content=report)

@app.get("/api/attendance/overtime")
def get_overtime_report(threshold_hours: float = 8.0, employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    overtime_report = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue

        total_hours = 0.0
        for record in records:
            if "check_in_time" in record and "check_out_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
                total_hours += calculate_duration(record["check_in_time"], record["check_out_time"])
        
        if total_hours > 0 or not records:
            overtime = max(0.0, total_hours - threshold_hours)
            overtime_report[emp_id] = {"total_hours": round(total_hours, 2), "overtime_hours": round(overtime, 2)}
    return JSONResponse(content=overtime_report)

@app.get("/api/attendance/export")
def export_attendance_data(employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    data_for_df = []
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        for record in records:
            if "check_in_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
            row = {"employee_id": emp_id}
            row.update(record)
            data_for_df.append(row)

    if not data_for_df:
        raise HTTPException(status_code=404, detail="No attendance data to export.")

    df = pd.DataFrame(data_for_df)
    
    # Convert timestamps to datetime objects for better formatting in CSV
    for col in ["check_in_time", "check_out_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    headers = {
        "Content-Disposition": "attachment; filename=\"attendance_data.csv\"".encode('latin-1').decode('utf-8'),
        "Content-Type": "text/csv",
    }
    return FileResponse(path=io.BytesIO(csv_buffer.getvalue().encode('utf-8')), media_type="text/csv", filename="attendance_data.csv", headers=headers)


# -------------------- PACKING MANAGEMENT — API --------------------
@app.post("/api/packing/preview")
async def packing_preview(file: UploadFile = File(...)):
    """Accept Organized Orders CSV/XLSX and return normalized rows for the table."""
    try:
        data = await file.read()
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        elif file.filename.lower().endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
        else:
            return JSONResponse({"error": "Unsupported file type"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=400)

    cols = {c.strip(): c for c in df.columns}

    def col(name: str):
        return cols.get(name)

    rows = []
    for _, r in df.iterrows():
        order = r.get(col("Order Number") or "Order Number", r.get("Order Name", ""))
        product = (r.get(col("Product Name") or "Product Name", r.get("Lineitem Name", "")) or "").strip()
        variant = (r.get(col("Variant") or "Variant", r.get("Lineitem Variant Title", "")) or "").strip()
        main_link = (r.get(col("Main Photo Link") or "Main Photo Link", "") or "").strip()
        polaroid_raw = r.get(col("Polaroid Link(s)") or "Polaroid Link(s)", "")
        polaroids = [p.strip() for p in str(polaroid_raw).split(",") if p.strip()]
        back_type = r.get(col("Back Engraving Type") or "Back Engraving Type", "")
        back_value = r.get(col("Back Engraving Value") or "Back Engraving Value", "")
        status = r.get(col("Main Photo Status") or "Main Photo Status", "")
        polaroid_count = r.get(col("Polaroid Count") or "Polaroid Count", "")

        rows.append({
            "Order Number": order,
            "Product Name": product,
            "Variant": variant,

            "Main Photo": main_link,
            "Polaroids": polaroids,
            "Back Engraving Type": back_type,
            "Back Engraving Value": back_value,
        })

    return {
        "columns": [
            "Order Number", "Product Name", "Variant", "Color",
            "Main Photo", "Polaroids", "Back Engraving Type", "Back Engraving Value",
            "Main Photo Status", "Polaroid Count",
        ],
        "rows": rows,
    }


# -------------------- PACKING MANAGEMENT — PAGE --------------------
@app.get("/packing")
def eraya_packing_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Packing Management</h1>
      <p class="text-white/80 mt-2">Upload Organized Orders CSV/XLSX and preview as a table.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <div class="flex flex-wrap items-center gap-3">
            <input type="file" id="f" accept=".csv,.xlsx"
                   class="rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" />
            <button type="button" id="go" class="btn btn-primary">Preview</button>
            <button type="button" id="export" class="btn btn-secondary">Export CSV (filtered)</button>
            <div id="status" class="text-white/70">Waiting for file…</div>
          </div>
          <div class="flex flex-wrap gap-3 mt-3">
            <input id="qOrder" placeholder="Search Order #" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qProd"  placeholder="Search Product" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qVar"   placeholder="Search Variant" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <select id="qStatus" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">All Statuses</option>
              <option value="Packed">Packed</option>
              <option value="Dispute">Dispute</option>
              <option value="Bad photo">Bad photo</option>
              <option value="Missing photo">Missing photo</option>
            </select>
            <select id="pageSize" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
          </div>
        </div>

        <div class="glass p-0 overflow-auto" style="max-height:70vh">
          <table class="min-w-full text-sm" id="tbl">
            <thead class="sticky top-0 bg-slate-900/80 backdrop-blur" id="head"></thead>
            <tbody id="body"></tbody>
          </table>
        </div>
        <div class="flex items-center gap-3">
          <button id="prev" class="btn btn-secondary">Prev</button>
          <div id="pageinfo" class="text-white/70 text-sm"></div>
          <button id="next" class="btn btn-secondary">Next</button>
        </div>
      </div>

      <!-- Simple lightbox -->
      <div id="lb" class="fixed inset-0 hidden items-center justify-center bg-black/70 p-6">
        <div class="bg-slate-900/90 border border-white/10 rounded-2xl p-4 max-w-5xl w-full">
          <div class="flex justify-between items-center mb-3">
            <div class="text-lg font-semibold">Polaroids</div>
            <button id="lbClose" class="btn btn-secondary">Close</button>
          </div>
          <div id="lbBody" class="grid grid-cols-2 md:grid-cols-4 gap-3"></div>
        </div>
      </div>
    </section>

    <style>
      #body tr:nth-child(even){ background: rgba(255,255,255,0.03); }
      .badge-miss{ background:#ef4444; color:white; padding:2px 6px; border-radius:6px; font-size:12px; }
      .packed{ opacity:.6; text-decoration: line-through; }
      #tbl tbody tr:hover { background-color: rgba(255,255,255,0.05); }
      #tbl th, #tbl td { padding: 0.75rem 0.5rem; text-align: left; vertical-align: top; }
      #tbl thead th { background-color: #0f172a; }
      .status-select { background: rgba(255,255,255,0.08); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 0.5rem; padding: 0.25rem 0.5rem; }

      /* Column Widths */
      #tbl th:nth-child(1), #tbl td:nth-child(1) { width: 5%; /* Packed Checkbox */ }
      #tbl th:nth-child(2), #tbl td:nth-child(2) { width: 10%; /* Order Number */ }
      #tbl th:nth-child(3), #tbl td:nth-child(3) { width: 15%; /* Product Name */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(4), #tbl td:nth-child(4) { width: 10%; /* Variant */ }
      #tbl th:nth-child(5), #tbl td:nth-child(5) { width: 5%;  /* Color */ }
      #tbl th:nth-child(6), #tbl td:nth-child(6) { width: 10%; /* Main Photo */ }
      #tbl th:nth-child(7), #tbl td:nth-child(7) { width: 10%; /* Polaroids */ }
      #tbl th:nth-child(8), #tbl td:nth-child(8) { width: 10%; /* Back Engraving Type */ }
      #tbl th:nth-child(9), #tbl td:nth-child(9) { width: 15%; /* Back Engraving Value */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(10), #tbl td:nth-child(10) { width: 5%; /* Main Photo Status */ }
      #tbl th:nth-child(11), #tbl td:nth-child(11) { width: 5%; /* Polaroid Count */ }
      #tbl th:nth-child(12), #tbl td:nth-child(12) { width: 10%; /* Status */ }
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .table-img { max-height: 80px; width: auto; }
      .status-badge { display: inline-block; padding: 2px 6px; border-radius: 6px; font-size: 12px; font-weight: 600; text-transform: capitalize; }
      .status-badge-Packed { background: #10b981; color: white; }
      .status-badge-Dispute { background: #f59e0b; color: white; }
      .status-badge-Badphoto { background: #ef4444; color: white; }
      .status-badge-Missingphoto { background: #ef4444; color: white; }
    </style>

    <script>
      // elements
      var f=document.getElementById('f'), go=document.getElementById('go'), status=document.getElementById('status');
      var qOrder=document.getElementById('qOrder'), qProd=document.getElementById('qProd'), qVar=document.getElementById('qVar');
      var head=document.getElementById('head'), body=document.getElementById('body'), pageSizeEl=document.getElementById('pageSize');
      var prev=document.getElementById('prev'), next=document.getElementById('next'), pageinfo=document.getElementById('pageinfo');
      var exportBtn=document.getElementById('export');
      var lb=document.getElementById('lb'), lbBody=document.getElementById('lbBody'), lbClose=document.getElementById('lbClose');
      var qStatus=document.getElementById('qStatus');

      // state
      var rows=[], filt=[], page=1, sortBy=null, sortDir=1, packed=JSON.parse(localStorage.getItem('packedMap')||'{}'), statuses=JSON.parse(localStorage.getItem('statusMap')||'{}');

      function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m];});}
      function td(h){return '<td class="border-t border-white/10 align-top">'+h+'</td>';}
      function savePacked(){localStorage.setItem('packedMap', JSON.stringify(packed)); localStorage.setItem('statusMap', JSON.stringify(statuses));}

      function imgFallback(el){el.onerror=null; el.src='https://via.placeholder.com/80?text=No+Img';}

      function openLB(urls){
        lbBody.innerHTML='';
        for(var i=0;i<urls.length;i++){
          var im=document.createElement('img'); im.loading='lazy'; im.src=urls[i];
          im.className='w-full h-40 object-cover rounded-xl border border-white/10';
          im.onerror=function(){ this.src='https://via.placeholder.com/160x160?text=No+Img'; };
          lbBody.appendChild(im);
        }
        lb.classList.remove('hidden'); lb.classList.add('flex');
      }
      lbClose.onclick=function(){lb.classList.add('hidden'); lb.classList.remove('flex');};
      lb.onclick=function(e){ if(e.target===lb) lbClose.onclick(); };

      function buildHead(){
        var cols=['Packed','Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count', 'Status'];
        var h='<tr>';
        for(var i=0;i<cols.length;i++){
          var c=cols[i]; var arrow=(sortBy===c?(sortDir>0?' ▲':' ▼'):'');
          h+='<th class="text-left p-2 border-b border-white/10 cursor-pointer" data-col="'+esc(c)+'">'+esc(c)+arrow+'</th>';
        }
        h+='</tr>';
        head.innerHTML=h;
        var ths=head.querySelectorAll('th[data-col]');
        for(var k=0;k<ths.length;k++){
          ths[k].onclick=function(){
            var c=this.getAttribute('data-col');
            if(c==='Packed') return;
            if(sortBy===c) sortDir=-sortDir; else {sortBy=c; sortDir=1;}
            applyFilters();
          };
        }
      }

      function applyFilters(){
        var o=qOrder.value.trim().toLowerCase(), p=qProd.value.trim().toLowerCase(), v=qVar.value.trim().toLowerCase();
        var s=qStatus.value; // Get the selected status
        filt=rows.filter(function(r){
          var ok=true;
          if(o) ok = ok && String(r['Order Number']||'').toLowerCase().indexOf(o)>=0;
          if(p) ok = ok && String(r['Product Name']||'').toLowerCase().indexOf(p)>=0;
          if(v) ok = ok && String(r['Variant']||'').toLowerCase().indexOf(v)>=0;
          if(s) ok = ok && statuses[String(r['Order Number']||'')] === s; // Filter by status
          return ok;
        });
        if(sortBy){
          filt.sort(function(a,b){
            var av=String(a[sortBy]||'').toLowerCase(), bv=String(b[sortBy]||'').toLowerCase();
            if(av<bv) return -1*sortDir; if(av>bv) return 1*sortDir; return 0;
          });
        }
        page=1; render();
      }

      function render(){
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        var out='';
        for(var i=start;i<end;i++){
          var r=filt[i], ord=r['Order Number'], isPacked=!!packed[ord];
          var main=r['Main Photo'] ? '<img loading="lazy" src="'+esc(r['Main Photo'])+'" class="w-20 h-20 object-cover rounded-lg border border-white/10 table-img" onerror="imgFallback(this)">' : '<span class="badge-miss">Missing photo</span>';
          var polys=r['Polaroids']||[]; var thumbs='';
          for(var t=0; t<Math.min(3,polys.length); t++){
            thumbs+='<img loading="lazy" src="'+esc(polys[t])+'" class="w-14 h-14 object-cover rounded-md border border-white/10 table-img" onerror="imgFallback(this)" style="margin-right:4px">';
          }
          var more=polys.length>3?('<div class="text-xs text-white/60">+'+(polys.length-3)+' more</div>'):'';
          var gallery='<a href="#" class="gal" data-idx="'+i+'"><div class="flex gap-2 flex-wrap">'+thumbs+more+'</div></a>';
          var engr=String(r['Back Engraving Value']||'').trim()?('<div class="truncate" style="white-space:pre-wrap">'+esc(r['Back Engraving Value'])+'</div>'):'<span class="badge-miss">Missing</span>';
          var currentStatus = statuses[ord] || '';

          out+='<tr class="'+(isPacked?'packed':'')+'">'+
            td('<input type="checkbox" class="chk" data-ord="'+esc(ord)+'" '+(isPacked?'checked':'')+'>')+
            td(esc(ord))+td(esc(r['Product Name']))+td(esc(r['Variant']))+td(esc(r['Color']))+
            td(main)+td(gallery)+td(esc(r['Back Engraving Type']))+td(engr)+td(esc(r['Main Photo Status']))+td(esc(r['Polaroid Count']))+
            td('<select class="status-select status-badge status-badge-'+esc(currentStatus)+'" data-ord="'+esc(ord)+'">' +
              ['', 'Packed', 'Dispute', 'Bad photo', 'Missing photo'].map(function(opt) {
                return '<option value="'+opt+'" '+(currentStatus===opt?'selected':'')+'>'+(opt||'—')+'</option>';
              }).join('') +
            '</select>') +
          '</tr>';
        }
        body.innerHTML=out;


        // ADD THIS RIGHT AFTER: body.innerHTML=out;
(function addStatusColumn(){
  // 1) Add headers once
  if (!document.getElementById('extra-status-head')) {
    var hr = head.querySelector('tr');
    var th1 = document.createElement('th');
    th1.id = 'extra-status-head';
    th1.className = 'text-left p-2 border-b border-white/10';
    th1.textContent = 'Status';
    hr.appendChild(th1);
  }

  // 2) Add cells to each rendered row (skip if already added)
  var rowsEls = body.querySelectorAll('tr');
  rowsEls.forEach(function(tr){
    if (tr.querySelector('td.__extra_status')) return; // already enhanced

    // Status dropdown
    var tdS = document.createElement('td');
    tdS.className = 'border-t border-white/10 p-2 align-top __extra_status';
    var sel = tr.querySelector('.status-select'); // Select the existing dropdown
    tdS.appendChild(sel);
    tr.appendChild(tdS);
  });
})();


        var chks=body.querySelectorAll('.chk');
        for(var c=0;c<chks.length;c++){
          chks[c].onchange=function(){
            var ord=this.getAttribute('data-ord');
            if(this.checked) packed[ord]=true; else delete packed[ord];
            savePacked();
            this.closest('tr').classList.toggle('packed', this.checked);
          };
        }

        var statusSelects = body.querySelectorAll('.status-select');
        for(var s=0; s<statusSelects.length; s++){
          statusSelects[s].onchange = function(){
            var ord = this.getAttribute('data-ord');
            statuses[ord] = this.value;
            savePacked();
            this.className = 'status-select status-badge status-badge-' + this.value.replace(/ /g, '');
          };
        }
        var links=body.querySelectorAll('a.gal');
        for(var g=0; g<links.length; g++){
          links[g].onclick=function(e){
            e.preventDefault();
            var idx=parseInt(this.getAttribute('data-idx')||'-1',10);
            if(idx>=0 && idx<filt.length){
              var urls=filt[idx]['Polaroids']||[];
              if(urls.length) openLB(urls);
            }
          };
        }

        var total=filt.length, pages=Math.max(1, Math.ceil(total/per));
        pageinfo.textContent='Page '+page+' / '+pages+' — '+total+' rows';
        prev.disabled=page<=1; next.disabled=page>=pages;
      }

      prev.onclick=function(){ if(page>1){ page--; render(); } };
      next.onclick=function(){ var per=parseInt(pageSizeEl.value,10)||25; var pages=Math.max(1,Math.ceil(filt.length/per)); if(page<pages){ page++; render(); } };
      pageSizeEl.onchange=applyFilters;
      qOrder.oninput=qProd.oninput=qVar.oninput=applyFilters;
      qStatus.onchange=applyFilters;

      window.imgFallback = imgFallback; // make global for onerror attr

      go.onclick=function(){
        if(!f.files.length){ alert('Select a CSV/XLSX first.'); return; }
        status.textContent='Uploading…'; head.innerHTML=''; body.innerHTML='';
        var fd=new FormData(); fd.append('file', f.files[0]);
        fetch('/api/packing/preview', {method:'POST', body:fd})
          .then(function(res){ return res.text().then(function(t){ return {ok:res.ok, text:t};}); })
          .then(function(x){
            if(!x.ok){ status.textContent='Error: '+x.text; return; }
            var data; try{ data=JSON.parse(x.text); }catch(e){ status.textContent='Bad JSON from server'; return; }
            rows=data.rows||[]; status.textContent='Loaded '+rows.length+' orders';
            buildHead(); applyFilters();
          })
          .catch(function(err){ console.error(err); status.textContent='Unexpected error'; });
      };

      exportBtn.onclick=function(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count', 'Status'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<filt.length;i++){
          var r=filt[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(cols[c] === 'Status') v = statuses[r['Order Number']] || '';
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+'\\n';
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='packing_filtered.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
    </script>
    """
    return _eraya_lumen_page("Packing", body)

# -------------------- SHOPIFY SETTINGS PAGE --------------------
@app.get("/shopify/settings")
def shopify_settings_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold mb-2">🛒 Shopify Integration Settings</h1>
      <p class="text-white/80 mb-6">Connect your Shopify store to automatically sync orders and analytics with your dashboard.</p>
      
      <!-- Connection Status -->
      <div id="connectionStatus" class="mb-6">
        <!-- Will be populated by JavaScript -->
      </div>
      
      <!-- Configuration Form -->
      <div class="glass p-6 mb-6">
        <h3 class="text-xl font-semibold mb-4">Store Configuration</h3>
        <form id="shopifyForm" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-white/90 mb-2">Store Name</label>
            <input type="text" id="storeName" name="store_name" 
                   placeholder="your-store-name (without .myshopify.com)"
                   class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500">
            <p class="text-xs text-white/60 mt-1">Enter just the store name part (e.g., "my-store" for my-store.myshopify.com)</p>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-white/90 mb-2">Private App Access Token</label>
            <input type="password" id="accessToken" name="access_token" 
                   placeholder="shppa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                   class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500">
            <p class="text-xs text-white/60 mt-1">Get this from your Shopify Admin → Apps → Private Apps</p>
          </div>
          
          <div class="flex gap-3">
            <button type="submit" class="btn btn-primary">
              🔗 Connect Store
            </button>
            <button type="button" id="testConnection" class="btn btn-secondary">
              🧪 Test Connection
            </button>
          </div>
        </form>
      </div>
      
      <!-- How to Get Access Token -->
      <div class="glass p-6 mb-6">
        <h3 class="text-xl font-semibold mb-4">📋 How to Get Your Access Token</h3>
        <div class="space-y-3 text-sm text-white/80">
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">1</span>
            <div>
              <strong>Go to your Shopify Admin</strong><br>
              <span class="text-white/60">Navigate to Settings → Apps and sales channels</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">2</span>
            <div>
              <strong>Create a Private App</strong><br>
              <span class="text-white/60">Click "Develop apps" → "Create an app" → Give it a name</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">3</span>
            <div>
              <strong>Configure API Scopes</strong><br>
              <span class="text-white/60">Enable: read_orders, read_products, read_customers, read_analytics</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">4</span>
            <div>
              <strong>Install & Copy Token</strong><br>
              <span class="text-white/60">Install the app and copy the "Admin API access token"</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Current Data Preview -->
      <div id="dataPreview" class="glass p-6" style="display: none;">
        <h3 class="text-xl font-semibold mb-4">📊 Live Data Preview</h3>
        <div id="previewContent">
          <!-- Will be populated by JavaScript -->
        </div>
      </div>
    </section>
    
    <script>
      const form = document.getElementById('shopifyForm');
      const testBtn = document.getElementById('testConnection');
      const statusDiv = document.getElementById('connectionStatus');
      const previewDiv = document.getElementById('dataPreview');
      const previewContent = document.getElementById('previewContent');
      
      // Load current configuration
      async function loadCurrentConfig() {
        try {
          const response = await fetch('/api/shopify/config');
          const data = await response.json();
          
          if (data.configured) {
            document.getElementById('storeName').value = data.store_name;
            showStatus('success', `✅ Connected to ${data.store_name}.myshopify.com`, data);
            loadDataPreview();
          } else {
            showStatus('warning', '⚠️ Shopify store not configured yet');
          }
        } catch (error) {
          showStatus('error', '❌ Error loading configuration');
        }
      }
      
      function showStatus(type, message, data = null) {
        const colors = {
          success: 'bg-green-500/20 border-green-500/30 text-green-200',
          warning: 'bg-yellow-500/20 border-yellow-500/30 text-yellow-200',
          error: 'bg-red-500/20 border-red-500/30 text-red-200'
        };
        
        let extraInfo = '';
        if (data && data.last_updated) {
          extraInfo = `<div class="text-xs mt-1 opacity-75">Last updated: ${new Date(data.last_updated).toLocaleString()}</div>`;
        }
        
        statusDiv.innerHTML = `
          <div class="border rounded-xl p-4 ${colors[type]}">
            <div class="font-medium">${message}</div>
            ${extraInfo}
          </div>
        `;
      }
      
      // Test connection
      testBtn.addEventListener('click', async () => {
        const storeName = document.getElementById('storeName').value.trim();
        const accessToken = document.getElementById('accessToken').value.trim();
        
        if (!storeName || !accessToken) {
          alert('Please fill in both store name and access token');
          return;
        }
        
        testBtn.disabled = true;
        testBtn.textContent = '🔄 Testing...';
        
        try {
          const formData = new FormData();
          formData.append('store_name', storeName);
          formData.append('access_token', accessToken);
          
          const response = await fetch('/api/shopify/config', {
            method: 'POST',
            body: formData
          });
          
          const result = await response.json();
          
          if (response.ok) {
            showStatus('success', `✅ ${result.message}`, result);
            loadDataPreview();
          } else {
            showStatus('error', `❌ ${result.detail}`);
          }
        } catch (error) {
          showStatus('error', '❌ Connection failed: ' + error.message);
        } finally {
          testBtn.disabled = false;
          testBtn.textContent = '🧪 Test Connection';
        }
      });
      
      // Form submission
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        testBtn.click(); // Reuse test connection logic
      });
      
      // Load data preview
      async function loadDataPreview() {
        try {
          const [ordersRes, analyticsRes] = await Promise.all([
            fetch('/api/shopify/orders?limit=5'),
            fetch('/api/shopify/analytics')
          ]);
          
          const orders = await ordersRes.json();
          const analytics = await analyticsRes.json();
          
          previewContent.innerHTML = `
            <div class="grid md:grid-cols-2 gap-6">
              <div>
                <h4 class="font-semibold mb-3">📈 Analytics Summary</h4>
                <div class="space-y-2 text-sm">
                  <div>Total Orders: <span class="font-mono">${analytics.total_orders || 0}</span></div>
                  <div>Today's Orders: <span class="font-mono">${analytics.today_orders || 0}</span></div>
                  <div>Total Revenue: <span class="font-mono">${analytics.currency} ${analytics.total_revenue || 0}</span></div>
                  <div>Today's Revenue: <span class="font-mono">${analytics.currency} ${analytics.today_revenue || 0}</span></div>
                  <div>Pending Orders: <span class="font-mono">${analytics.pending_orders || 0}</span></div>
                </div>
              </div>
              <div>
                <h4 class="font-semibold mb-3">🛍️ Recent Orders</h4>
                <div class="space-y-2 text-sm">
                  ${orders.orders ? orders.orders.slice(0, 3).map(order => `
                    <div class="bg-white/5 rounded p-2">
                      <div class="font-mono">#${order.name}</div>
                      <div class="text-white/60">${order.currency} ${order.total_price}</div>
                    </div>
                  `).join('') : '<div class="text-white/60">No orders found</div>'}
                </div>
              </div>
            </div>
          `;
          
          previewDiv.style.display = 'block';
        } catch (error) {
          console.error('Error loading preview:', error);
        }
      }
      
      // Load configuration on page load
      loadCurrentConfig();
    </script>
    """
    return _eraya_lumen_page("Shopify Settings", body)

# -------------------- Pending & Attendance placeholders --------------------
@app.get("/pending")
def eraya_pending_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Pending Orders</h1>
      <p class="text-white/80 mt-2">Coming next.</p>
    </section>
    """
    return _eraya_lumen_page("Pending Orders", body)


@app.get("/attendance")
def eraya_attendance_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Employee Attendance</h1>
      <p class="text-white/80 mt-2">Simple check-in/out and attendance records.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Check-in/Check-out</h2>
          <div class="flex items-center gap-3">
            <select id="employeeSelect" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">Select Employee</option>
            </select>
            <button type="button" id="checkInBtn" class="btn btn-primary">Check In</button>
            <button type="button" id="checkOutBtn" class="btn btn-secondary">Check Out</button>
            <div id="attendanceStatus" class="text-white/70"></div>
          </div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Real-time Employee Status</h2>
          <div id="realtimeStatus" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Attendance Records</h2>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <input type="text" id="filterEmployeeId" placeholder="Filter by Employee ID" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="filterDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="applyFilterBtn" class="btn btn-primary">Apply Filter</button>
            <button type="button" id="clearFilterBtn" class="btn btn-secondary">Clear Filter</button>
          </div>
          <table class="min-w-full text-sm" id="attendanceTable">
            <thead>
              <tr>
                <th class="text-left p-2 border-b border-white/10">Employee ID</th>
                <th class="text-left p-2 border-b border-white/10">Check In Time</th>
                <th class="text-left p-2 border-b border-white/10">Check Out Time</th>
                <th class="text-left p-2 border-b border-white/10">Duration (hours)</th>
              </tr>
            </thead>
            <tbody id="attendanceTableBody">
            </tbody>
          </table>
        </div>

        <div class="glass p-5 text-center">
          <h2 class="text-2xl font-semibold mb-3">View Comprehensive Reports</h2>
          <p class="text-white/70 mb-4">Access detailed total hours and overtime reports with advanced filtering options.</p>
          <a href="/attendance/report_page" class="btn btn-primary">Go to Reports Page</a>
        </div>

      </div>
    </section>

    <script>
      const employeeIdInput = document.getElementById('employeeId');
      const checkInBtn = document.getElementById('checkInBtn');
      const checkOutBtn = document.getElementById('checkOutBtn');
      const attendanceStatus = document.getElementById('attendanceStatus');
      const attendanceTableBody = document.getElementById('attendanceTableBody');
      const filterEmployeeIdInput = document.getElementById('filterEmployeeId');
      const filterDateInput = document.getElementById('filterDate');
      const applyFilterBtn = document.getElementById('applyFilterBtn');
      const clearFilterBtn = document.getElementById('clearFilterBtn');
      const realtimeStatusDiv = document.getElementById('realtimeStatus');
      const employeeSelect = document.getElementById('employeeSelect');

      // Populate employee dropdown
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };
      const employeeIdToName = {};
      for (const name in employees) {
          const id = employees[name];
          employeeIdToName[id] = name;

          const option = document.createElement('option');
          option.value = id;
          option.textContent = name;
          employeeSelect.appendChild(option);
      }

      async function fetchAttendanceRecords() {
        const employee_id_filter = filterEmployeeIdInput.value;
        const date_filter = filterDateInput.value;
        
        let url = '/api/attendance/records';
        const params = new URLSearchParams();
        if (employee_id_filter) {
            params.append('employee_id', employee_id_filter);
        }
        if (date_filter) {
            params.append('date', date_filter);
        }
        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        const response = await fetch(url);
        const records = await response.json();
        attendanceTableBody.innerHTML = '';
        
        const realtimeStatus = {};

        for (const employee_id in records) {
          records[employee_id].forEach(record => {
            const row = document.createElement('tr');
            const checkInTime = record.check_in_time ? new Date(record.check_in_time).toLocaleString() : 'N/A';
            const checkOutTime = record.check_out_time ? new Date(record.check_out_time).toLocaleString() : 'N/A';
            let duration = 'N/A';
            if (record.check_in_time && record.check_out_time) {
                const start = new Date(record.check_in_time);
                const end = new Date(record.check_out_time);
                duration = ((end - start) / (1000 * 60 * 60)).toFixed(2);
            } else if (record.check_in_time && !record.check_out_time) {
                const start = new Date(record.check_in_time);
                const now = new Date();
                duration = ((now - start) / (1000 * 60 * 60)).toFixed(2) + ' (current)';
                realtimeStatus[employee_id] = {status: 'Checked In', duration: duration};
            }
            
            if (!realtimeStatus[employee_id]) {
                // If not currently checked in, show status from the last record
                const lastRecord = records[employee_id][records[employee_id].length - 1];
                if (lastRecord && lastRecord.check_out_time) {
                     const start = new Date(lastRecord.check_in_time);
                     const end = new Date(lastRecord.check_out_time);
                     const last_duration = ((end - start) / (1000 * 60 * 60)).toFixed(2);
                    realtimeStatus[employee_id] = {status: 'Checked Out', duration: `${last_duration} (last)`};
                } else {
                    realtimeStatus[employee_id] = {status: 'Unknown', duration: 'N/A'};
                }
            }

            row.innerHTML = `
              <td class="border-t border-white/10 p-2">${employee_id}</td>
              <td class="border-t border-white/10 p-2">${checkInTime}</td>
              <td class="border-t border-white/10 p-2">${checkOutTime}</td>
              <td class="border-t border-white/10 p-2">${duration}</td>
            `;
            attendanceTableBody.appendChild(row);
          });
        }
        
        // Display real-time status
        realtimeStatusDiv.innerHTML = '';
        if (Object.keys(realtimeStatus).length === 0) {
            realtimeStatusDiv.innerHTML = '<p class="text-white/70">No employee status to display.</p>';
        } else {
            for (const emp_id in realtimeStatus) {
                const statusCard = document.createElement('div');
                statusCard.className = "glass p-4 rounded-lg";
                const employeeName = employeeIdToName[emp_id] || emp_id; // Get name or fallback to ID
                statusCard.innerHTML = `
                    <h3 class="font-semibold text-lg">${employeeName} (${emp_id})</h3>
                    <p>Status: <span class="font-bold ${realtimeStatus[emp_id].status === 'Checked In' ? 'text-green-400' : 'text-red-400'}">${realtimeStatus[emp_id].status}</span></p>
                    <p>Duration: ${realtimeStatus[emp_id].duration}</p>
                `;
                realtimeStatusDiv.appendChild(statusCard);
            }
        }

      }

      async function handleCheckIn() {
        const employee_id = employeeSelect.value;
        if (!employee_id) {
          attendanceStatus.textContent = 'Please select an Employee.';
          return;
        }
        const formData = new FormData();
        formData.append('employee_id', employee_id);
        const response = await fetch('/api/attendance/check_in', {
          method: 'POST',
          body: formData,
        });
        const result = await response.json();
        attendanceStatus.textContent = result.message;
        fetchAttendanceRecords();
      }

      async function handleCheckOut() {
        const employee_id = employeeSelect.value;
        if (!employee_id) {
          attendanceStatus.textContent = 'Please select an Employee.';
          return;
        }
        const formData = new FormData();
        formData.append('employee_id', employee_id);
        const response = await fetch('/api/attendance/check_out', {
          method: 'POST',
          body: formData,
        });
        const result = await response.json();
        attendanceStatus.textContent = result.message;
        fetchAttendanceRecords();
      }

      checkInBtn.addEventListener('click', handleCheckIn);
      checkOutBtn.addEventListener('click', handleCheckOut);
      applyFilterBtn.addEventListener('click', fetchAttendanceRecords);
      clearFilterBtn.addEventListener('click', () => {
          filterEmployeeIdInput.value = '';
          filterDateInput.value = '';
          fetchAttendanceRecords();
      });

      // Initial fetch and set up real-time refresh
      fetchAttendanceRecords();
      setInterval(fetchAttendanceRecords, 30000); // Refresh every 30 seconds

    </script>
    """
    return _eraya_lumen_page("Attendance", body)

@app.get("/attendance/report_page")
def eraya_attendance_report_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Attendance Reports</h1>
      <p class="text-white/80 mt-2">View total hours and overtime reports with filters.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Filter Reports</h2>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <input type="text" id="reportEmployeeId" placeholder="Filter by Employee ID" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="reportStartDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="reportEndDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="applyReportFilterBtn" class="btn btn-primary">Apply Filter</button>
            <button type="button" id="clearReportFilterBtn" class="btn btn-secondary">Clear Filter</button>
          </div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Basic Reporting</h2>
          <button type="button" id="exportReportDataBtn" class="btn btn-secondary">Export All Data (CSV)</button>
          <div class="mt-3" id="reportingData"></div>
        </div>

        <div class="glass p-5">
            <h2 class="text-2xl font-semibold mb-3">Overtime Report</h2>
            <label for="reportOvertimeThreshold" class="text-white/70 mr-2">Overtime Threshold (hours):</label>
            <input type="number" id="reportOvertimeThreshold" value="8" step="0.5" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="generateReportOvertimeBtn" class="btn btn-primary">Generate Overtime Report</button>
            <div class="mt-3" id="overtimeData"></div>
        </div>

      </div>
    </section>

    <script>
      const reportEmployeeIdInput = document.getElementById('reportEmployeeId');
      const reportStartDateInput = document.getElementById('reportStartDate');
      const reportEndDateInput = document.getElementById('reportEndDate');
      const applyReportFilterBtn = document.getElementById('applyReportFilterBtn');
      const clearReportFilterBtn = document.getElementById('clearReportFilterBtn');
      const exportReportDataBtn = document.getElementById('exportReportDataBtn');
      const reportingData = document.getElementById('reportingData');
      const reportOvertimeThresholdInput = document.getElementById('reportOvertimeThreshold');
      const generateReportOvertimeBtn = document.getElementById('generateReportOvertimeBtn');
      const overtimeData = document.getElementById('overtimeData');

      async function fetchReports() {
        const employee_id_filter = reportEmployeeIdInput.value;
        const start_date = reportStartDateInput.value;
        const end_date = reportEndDateInput.value;

        // Fetch Total Hours Report
        let reportUrl = '/api/attendance/report';
        let reportParams = new URLSearchParams();
        if (employee_id_filter) reportParams.append('employee_id', employee_id_filter);
        if (start_date) reportParams.append('start_date', start_date);
        if (end_date) reportParams.append('end_date', end_date);
        if (reportParams.toString()) reportUrl += `?${reportParams.toString()}`;

        const totalHoursResponse = await fetch(reportUrl);
        const totalHoursReport = await totalHoursResponse.json();
        let totalHoursHtml = '<h3>Total Hours Report</h3>';
        if (Object.keys(totalHoursReport).length === 0) {
            totalHoursHtml += '<p>No total hours data available.</p>';
        } else {
            totalHoursHtml += '<ul class="list-disc pl-5 mt-2">';
            for (const employee_id in totalHoursReport) {
                totalHoursHtml += `<li><strong>${employee_id}:</strong> Total Hours: ${totalHoursReport[employee_id].total_hours}</li>`;
            }
            totalHoursHtml += '</ul>';
        }
        reportingData.innerHTML = totalHoursHtml;

        // Fetch Overtime Report
        let overtimeUrl = '/api/attendance/overtime';
        let overtimeParams = new URLSearchParams();
        if (employee_id_filter) overtimeParams.append('employee_id', employee_id_filter);
        if (start_date) overtimeParams.append('start_date', start_date);
        if (end_date) overtimeParams.append('end_date', end_date);
        const threshold = reportOvertimeThresholdInput.value;
        if (threshold) overtimeParams.append('threshold_hours', threshold);
        if (overtimeParams.toString()) overtimeUrl += `?${overtimeParams.toString()}`;

        const overtimeResponse = await fetch(overtimeUrl);
        const overtimeReport = await overtimeResponse.json();
        let overtimeHtml = '<h3>Overtime Report</h3>';
        if (Object.keys(overtimeReport).length === 0) {
            overtimeHtml += '<p>No overtime data available.</p>';
        } else {
            overtimeHtml += '<ul class="list-disc pl-5 mt-2">';
            for (const employee_id in overtimeReport) {
                overtimeHtml += `<li><strong>${employee_id}:</strong> Total Hours: ${overtimeReport[employee_id].total_hours}, Overtime Hours: ${overtimeReport[employee_id].overtime_hours}</li>`;
            }
            overtimeHtml += '</ul>';
        }
        overtimeData.innerHTML = overtimeHtml;
      }

      async function handleExportReportData() {
          const employee_id_filter = reportEmployeeIdInput.value;
          const start_date = reportStartDateInput.value;
          const end_date = reportEndDateInput.value;

          let url = '/api/attendance/export';
          const params = new URLSearchParams();
          if (employee_id_filter) params.append('employee_id', employee_id_filter);
          if (start_date) params.append('start_date', start_date);
          if (end_date) params.append('end_date', end_date);
          if (params.toString()) url += `?${params.toString()}`;

          try {
              const response = await fetch(url);
              if (!response.ok) {
                  const errorText = await response.text();
                  alert(`Error exporting data: ${errorText}`);
                  return;
              }
              const blob = await response.blob();
              const urlBlob = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = urlBlob;
              a.download = 'attendance_report.csv';
              document.body.appendChild(a);
              a.click();
              a.remove();
              window.URL.revokeObjectURL(urlBlob);
          } catch (error) {
              console.error('Export failed:', error);
              alert('Failed to export data.');
          }
      }

      applyReportFilterBtn.addEventListener('click', fetchReports);
      clearReportFilterBtn.addEventListener('click', () => {
          reportEmployeeIdInput.value = '';
          reportStartDateInput.value = '';
          reportEndDateInput.value = '';
          fetchReports();
      });
      exportReportDataBtn.addEventListener('click', handleExportReportData);
      generateReportOvertimeBtn.addEventListener('click', fetchReports);

      // Initial fetch
      fetchReports();

    </script>
    """
    return _eraya_lumen_page("Attendance Reports", body)

@app.get("/chat")
def eraya_chat_page():
    body = """
    <div class="flex h-screen bg-slate-900">
      <!-- Sidebar -->
      <div class="w-80 glass border-r border-white/10 flex flex-col">
        <!-- User Info -->
        <div class="p-4 border-b border-white/10">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center">
              <span class="text-white font-semibold" id="userInitials">?</span>
            </div>
            <div class="flex-1">
              <select id="currentUser" class="bg-slate-800 border border-white/10 rounded px-2 py-1 text-sm w-full">
                <option value="">Select your name</option>
              </select>
            </div>
            <div id="onlineIndicator" class="w-3 h-3 bg-gray-400 rounded-full"></div>
          </div>
        </div>

        <!-- Channels Section -->
        <div class="flex-1 overflow-y-auto">
          <div class="p-3">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Channels</h3>
            <div id="channelsList" class="space-y-1">
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="general">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">general</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="packing">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">packing</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="management">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">management</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="announcements">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">📢</span>
                  <span class="text-sm">announcements</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
            </div>
          </div>

          <!-- Direct Messages Section -->
          <div class="p-3 border-t border-white/10">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Direct Messages</h3>
            <div id="dmsList" class="space-y-1">
              <!-- DMs will be populated here -->
            </div>
          </div>

          <!-- Online Users -->
          <div class="p-3 border-t border-white/10">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Online Now</h3>
            <div id="onlineUsersList" class="space-y-1">
              <div class="text-xs text-white/40">Loading...</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col">
        <!-- Chat Header -->
        <div class="p-4 border-b border-white/10 glass">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <span id="chatTitle" class="text-xl font-semibold"># general</span>
              <span id="chatDescription" class="text-sm text-white/60">General team discussion</span>
            </div>
            <div class="flex items-center gap-2">
              <a href="/chat" class="btn btn-primary text-sm">💬 Full Chat</a>
              <button id="backToHub" class="btn btn-secondary text-sm">← Back to Hub</button>
            </div>
          </div>
        </div>

        <!-- Messages Area -->
        <div id="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-4">
          <div class="text-center text-white/60">Loading messages...</div>
        </div>

        <!-- Message Input -->
        <div class="p-4 border-t border-white/10 glass">
          <div class="flex items-end gap-3">
            <div class="flex-1">
              <textarea id="messageInput" 
                       placeholder="Type your message..." 
                       class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm resize-none"
                       rows="1" maxlength="500"></textarea>
            </div>
            <div class="flex gap-2">
              <input type="file" id="fileInput" class="hidden" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt">
              <button id="fileBtn" class="p-2 text-white/60 hover:text-white rounded" title="Upload file">📎</button>
              <button id="emojiBtn" class="p-2 text-white/60 hover:text-white rounded" title="Add emoji">😊</button>
              <button id="sendMessage" class="btn btn-primary">Send</button>
            </div>
          </div>
          <div id="filePreview" class="hidden mt-2 p-3 bg-slate-800 rounded-lg border border-white/10">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div id="fileIcon" class="text-2xl">📎</div>
                <div>
                  <div id="fileName" class="text-sm font-medium"></div>
                  <div id="fileSize" class="text-xs text-white/60"></div>
                </div>
              </div>
              <button id="removeFile" class="text-red-400 hover:text-red-300">✕</button>
            </div>
          </div>
          <div id="emojiPicker" class="hidden mt-2 p-3 bg-slate-800 rounded-lg border border-white/10">
            <div class="grid grid-cols-8 gap-2 text-lg">
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">👍</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">❤️</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😂</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😮</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😢</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😡</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">🎉</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">🔥</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">💯</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">✅</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">❌</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">⚠️</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <style>
      .channel-item.active {
        background-color: rgba(59, 130, 246, 0.2);
        border-left: 3px solid #3b82f6;
      }
      .message-bubble {
        max-width: 70%;
        word-wrap: break-word;
      }
      .message-reactions {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 4px;
      }
      .reaction-btn {
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 12px;
        padding: 2px 6px;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .reaction-btn:hover {
        background: rgba(255, 255, 255, 0.2);
      }
      .reaction-btn.active {
        background: rgba(59, 130, 246, 0.3);
        border-color: #3b82f6;
      }
      .dm-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px;
        border-radius: 6px;
        cursor: pointer;
        transition: background-color 0.2s;
      }
      .dm-item:hover {
        background-color: rgba(255, 255, 255, 0.05);
      }
      .dm-item.active {
        background-color: rgba(59, 130, 246, 0.2);
        border-left: 3px solid #3b82f6;
      }
      .online-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
      }
      .offline-dot {
        width: 8px;
        height: 8px;
        background-color: #6b7280;
        border-radius: 50%;
        display: inline-block;
      }
      .file-attachment {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 12px;
        margin-top: 8px;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: background-color 0.2s;
      }
      .file-attachment:hover {
        background: rgba(255, 255, 255, 0.08);
      }
      .file-icon {
        font-size: 24px;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(59, 130, 246, 0.2);
        border-radius: 8px;
      }
      .link-preview {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 12px;
        margin-top: 8px;
        transition: background-color 0.2s;
      }
      .link-preview:hover {
        background: rgba(255, 255, 255, 0.08);
      }
      .image-preview {
        max-width: 300px;
        max-height: 200px;
        border-radius: 8px;
        margin-top: 8px;
        cursor: pointer;
      }
    </style>

    <script>
      // Chat application state
      let currentUser = '';
      let currentChannel = 'general';
      let currentDM = null;
      let isTyping = false;
      let selectedFile = null;

      // DOM elements
      const currentUserSelect = document.getElementById('currentUser');
      const userInitials = document.getElementById('userInitials');
      const onlineIndicator = document.getElementById('onlineIndicator');
      const channelsList = document.getElementById('channelsList');
      const dmsList = document.getElementById('dmsList');
      const onlineUsersList = document.getElementById('onlineUsersList');
      const chatTitle = document.getElementById('chatTitle');
      const chatDescription = document.getElementById('chatDescription');
      const messagesContainer = document.getElementById('messagesContainer');
      const messageInput = document.getElementById('messageInput');
      const sendMessage = document.getElementById('sendMessage');
      const emojiBtn = document.getElementById('emojiBtn');
      const emojiPicker = document.getElementById('emojiPicker');
      const backToHub = document.getElementById('backToHub');
      const fileBtn = document.getElementById('fileBtn');
      const fileInput = document.getElementById('fileInput');
      const filePreview = document.getElementById('filePreview');
      const fileName = document.getElementById('fileName');
      const fileSize = document.getElementById('fileSize');
      const fileIcon = document.getElementById('fileIcon');
      const removeFile = document.getElementById('removeFile');

      // Employee data
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };

      // Initialize
      function init() {
          // Populate user dropdown
          for (const name in employees) {
              const option = document.createElement('option');
              option.value = employees[name];
              option.textContent = name;
              currentUserSelect.appendChild(option);
          }

          // Event listeners
          currentUserSelect.addEventListener('change', handleUserChange);
          sendMessage.addEventListener('click', handleSendMessage);
          messageInput.addEventListener('keypress', handleKeyPress);
          emojiBtn.addEventListener('click', toggleEmojiPicker);
          backToHub.addEventListener('click', () => window.location.href = '/hub');
          fileBtn.addEventListener('click', () => fileInput.click());
          fileInput.addEventListener('change', handleFileSelect);
          removeFile.addEventListener('click', handleRemoveFile);

          // Channel clicks
          document.querySelectorAll('.channel-item').forEach(item => {
              item.addEventListener('click', () => {
                  const channel = item.dataset.channel;
                  switchToChannel(channel);
              });
          });

          // Emoji picker
          document.querySelectorAll('.emoji').forEach(emoji => {
              emoji.addEventListener('click', () => {
                  messageInput.value += emoji.textContent;
                  emojiPicker.classList.add('hidden');
                  messageInput.focus();
              });
          });

          // Auto-resize textarea
          messageInput.addEventListener('input', function() {
              this.style.height = 'auto';
              this.style.height = Math.min(this.scrollHeight, 120) + 'px';
          });

          // Load initial data
          loadOnlineUsers();
          loadChannelMessages();
          
          // Set up periodic updates
          setInterval(loadOnlineUsers, 10000);
          setInterval(loadChannelMessages, 5000);
      }

      function handleUserChange() {
          currentUser = currentUserSelect.value;
          if (currentUser) {
              const userName = Object.keys(employees).find(key => employees[key] === currentUser);
              userInitials.textContent = userName ? userName.charAt(0).toUpperCase() : '?';
              onlineIndicator.className = 'w-3 h-3 bg-green-400 rounded-full';
              
              // Update user status
              updateUserStatus('online');
              
              // Load DMs
              loadDirectMessages();
          }
      }

      function switchToChannel(channel) {
          currentChannel = channel;
          currentDM = null;
          
          // Update UI
          document.querySelectorAll('.channel-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelector(`[data-channel="${channel}"]`).classList.add('active');
          
          document.querySelectorAll('.dm-item').forEach(item => {
              item.classList.remove('active');
          });

          // Update header
          const channelNames = {
              'general': 'General',
              'packing': 'Packing Team',
              'management': 'Management',
              'announcements': 'Announcements'
          };
          
          chatTitle.textContent = `# ${channel}`;
          chatDescription.textContent = `${channelNames[channel]} discussion`;
          
          loadChannelMessages();
      }

      function switchToDM(employeeId) {
          currentDM = employeeId;
          currentChannel = null;
          
          // Update UI
          document.querySelectorAll('.channel-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelectorAll('.dm-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelector(`[data-dm="${employeeId}"]`).classList.add('active');

          // Update header
          const employeeName = Object.keys(employees).find(key => employees[key] === employeeId);
          chatTitle.textContent = `@ ${employeeName}`;
          chatDescription.textContent = 'Direct message';
          
          loadDMMessages(employeeId);
      }

      async function loadChannelMessages() {
          if (!currentChannel) return;
          
          try {
              const response = await fetch(`/api/chat/channel/${currentChannel}`);
              const data = await response.json();
              displayMessages(data.messages);
          } catch (error) {
              console.error('Error loading channel messages:', error);
          }
      }

      async function loadDMMessages(employeeId) {
          if (!currentUser || !employeeId) return;
          
          try {
              const response = await fetch(`/api/chat/dm/${employeeId}?current_employee_id=${currentUser}`);
              const data = await response.json();
              displayMessages(data.messages, true);
          } catch (error) {
              console.error('Error loading DM messages:', error);
          }
      }

      function displayMessages(messages, isDM = false) {
          if (!messages || messages.length === 0) {
              messagesContainer.innerHTML = '<div class="text-center text-white/60">No messages yet. Start the conversation!</div>';
              return;
          }

          let html = '';
          messages.forEach(msg => {
              const time = new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
              const isOwnMessage = isDM ? msg.from_employee_id === currentUser : msg.employee_id === currentUser;
              
              const senderName = isDM ? msg.from_employee_name : msg.employee_name;
              
              html += `
                  <div class="message-item">
                      <div class="flex items-start gap-3">
                          <div class="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center flex-shrink-0">
                              <span class="text-white text-sm font-semibold">${senderName.charAt(0).toUpperCase()}</span>
                          </div>
                          <div class="flex-1 min-w-0">
                              <div class="flex items-center gap-2 mb-1">
                                  <span class="font-semibold text-sm ${isOwnMessage ? 'text-blue-400' : 'text-white'}">${senderName}</span>
                                  <span class="text-xs text-white/50">${time}</span>
                              </div>
                              <div class="text-sm bg-slate-800/50 rounded-lg p-3 message-bubble">
                                  ${msg.message}
                              </div>
                              ${renderFileAttachment(msg.file_attachment)}
                              ${renderLinkPreviews(msg.links)}
                              <div class="message-reactions" data-message-id="${msg.id}">
                                  ${renderReactions(msg.reactions || {}, msg.id)}
                              </div>
                          </div>
                      </div>
                  </div>
              `;
          });
          
          messagesContainer.innerHTML = html;
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
          
          // Add reaction click handlers
          document.querySelectorAll('.reaction-btn').forEach(btn => {
              btn.addEventListener('click', handleReactionClick);
          });
      }

      function renderReactions(reactions, messageId) {
          let html = '';
          for (const emoji in reactions) {
              const users = reactions[emoji];
              if (users.length > 0) {
                  const isActive = users.includes(currentUser);
                  html += `
                      <span class="reaction-btn ${isActive ? 'active' : ''}" 
                            data-message-id="${messageId}" 
                            data-emoji="${emoji}">
                          ${emoji} ${users.length}
                      </span>
                  `;
              }
          }
          return html;
      }

      function renderFileAttachment(fileAttachment) {
          if (!fileAttachment) return '';
          
          const fileTypeIcons = {
              'image': '🖼️',
              'video': '🎥',
              'audio': '🎵',
              'pdf': '📄',
              'document': '📝',
              'file': '📎'
          };
          
          const icon = fileTypeIcons[fileAttachment.file_type] || '📎';
          
          if (fileAttachment.file_type === 'image') {
              return `
                  <div class="file-attachment">
                      <img src="${fileAttachment.url}" alt="${fileAttachment.filename}" class="image-preview" onclick="window.open('${fileAttachment.url}', '_blank')">
                  </div>
              `;
          } else {
              return `
                  <div class="file-attachment" onclick="window.open('${fileAttachment.url}', '_blank')">
                      <div class="file-icon">${icon}</div>
                      <div class="flex-1">
                          <div class="font-medium text-sm">${fileAttachment.filename}</div>
                          <div class="text-xs text-white/60">${formatFileSize(fileAttachment.file_size)}</div>
                      </div>
                      <div class="text-blue-400 text-sm">Download</div>
                  </div>
              `;
          }
      }

      function renderLinkPreviews(links) {
          if (!links || links.length === 0) return '';
          
          let html = '';
          links.forEach(link => {
              html += `
                  <div class="link-preview" onclick="window.open('${link.url}', '_blank')">
                      <div class="font-medium text-sm text-blue-400">${link.title}</div>
                      <div class="text-xs text-white/60 mt-1">${link.description}</div>
                      <div class="text-xs text-white/40 mt-1">${link.url}</div>
                  </div>
              `;
          });
          
          return html;
      }

      async function handleReactionClick(e) {
          if (!currentUser) return;
          
          const messageId = e.target.dataset.messageId;
          const emoji = e.target.dataset.emoji;
          const isActive = e.target.classList.contains('active');
          
          try {
              const formData = new FormData();
              formData.append('message_id', messageId);
              formData.append('employee_id', currentUser);
              formData.append('emoji', emoji);
              
              const endpoint = isActive ? '/api/chat/reaction/remove' : '/api/chat/reaction/add';
              await fetch(endpoint, { method: 'POST', body: formData });
              
              // Reload messages to show updated reactions
              if (currentChannel) {
                  loadChannelMessages();
              } else if (currentDM) {
                  loadDMMessages(currentDM);
              }
          } catch (error) {
              console.error('Error handling reaction:', error);
          }
      }

      async function handleSendMessage() {
          if (!currentUser) {
              alert('Please select your name first.');
              return;
          }
          
          const message = messageInput.value.trim();
          if (!message && !selectedFile) return;
          
          try {
              let fileInfo = null;
              
              // Upload file if selected
              if (selectedFile) {
                  fileInfo = await uploadFile(selectedFile, currentUser);
                  if (!fileInfo) return; // Upload failed
              }
              
              const formData = new FormData();
              formData.append('employee_id', currentUser);
              formData.append('message', message);
              
              if (fileInfo) {
                  formData.append('file_info', JSON.stringify(fileInfo));
              }
              
              if (currentChannel) {
                  formData.append('channel', currentChannel);
                  await fetch('/api/chat/channel/send', { method: 'POST', body: formData });
                  loadChannelMessages();
              } else if (currentDM) {
                  formData.append('from_employee_id', currentUser);
                  formData.append('to_employee_id', currentDM);
                  await fetch('/api/chat/dm/send', { method: 'POST', body: formData });
                  loadDMMessages(currentDM);
              }
              
              messageInput.value = '';
              messageInput.style.height = 'auto';
              handleRemoveFile(); // Clear file selection
              
          } catch (error) {
              console.error('Error sending message:', error);
          }
      }

      function handleKeyPress(e) {
          if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
          }
      }

      function toggleEmojiPicker() {
          emojiPicker.classList.toggle('hidden');
      }

      function handleFileSelect(e) {
          const file = e.target.files[0];
          if (!file) return;
          
          // Check file size (10MB limit)
          if (file.size > 10 * 1024 * 1024) {
              alert('File too large. Maximum size is 10MB.');
              return;
          }
          
          selectedFile = file;
          showFilePreview(file);
      }

      function showFilePreview(file) {
          fileName.textContent = file.name;
          fileSize.textContent = formatFileSize(file.size);
          
          // Set appropriate icon based on file type
          const ext = file.name.split('.').pop().toLowerCase();
          if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
              fileIcon.textContent = '🖼️';
          } else if (['mp4', 'avi', 'mov', 'wmv'].includes(ext)) {
              fileIcon.textContent = '🎥';
          } else if (['mp3', 'wav', 'ogg'].includes(ext)) {
              fileIcon.textContent = '🎵';
          } else if (ext === 'pdf') {
              fileIcon.textContent = '📄';
          } else if (['doc', 'docx', 'txt'].includes(ext)) {
              fileIcon.textContent = '📝';
          } else {
              fileIcon.textContent = '📎';
          }
          
          filePreview.classList.remove('hidden');
      }

      function handleRemoveFile() {
          selectedFile = null;
          fileInput.value = '';
          filePreview.classList.add('hidden');
      }

      function formatFileSize(bytes) {
          if (bytes === 0) return '0 Bytes';
          const k = 1024;
          const sizes = ['Bytes', 'KB', 'MB', 'GB'];
          const i = Math.floor(Math.log(bytes) / Math.log(k));
          return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
      }

      async function uploadFile(file, employeeId) {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('employee_id', employeeId);
          
          try {
              const response = await fetch('/api/chat/upload', {
                  method: 'POST',
                  body: formData
              });
              
              if (response.ok) {
                  const result = await response.json();
                  return result.file;
              } else {
                  throw new Error('Upload failed');
              }
          } catch (error) {
              console.error('File upload error:', error);
              alert('Failed to upload file.');
              return null;
          }
      }

      async function loadOnlineUsers() {
          try {
              const response = await fetch('/api/chat/users/online');
              const data = await response.json();
              
              let html = '';
              if (data.online_users.length === 0) {
                  html = '<div class="text-xs text-white/40">No one online</div>';
              } else {
                  data.online_users.forEach(user => {
                      html += `
                          <div class="flex items-center gap-2 p-1 cursor-pointer hover:bg-white/5 rounded text-sm"
                               onclick="switchToDM('${user.employee_id}')">
                              <div class="online-dot"></div>
                              <span>${user.employee_name}</span>
                          </div>
                      `;
                  });
              }
              
              onlineUsersList.innerHTML = html;
          } catch (error) {
              console.error('Error loading online users:', error);
          }
      }

      async function loadDirectMessages() {
          if (!currentUser) return;
          
          let html = '';
          for (const [name, empId] of Object.entries(employees)) {
              if (empId !== currentUser) {
                  html += `
                      <div class="dm-item" data-dm="${empId}" onclick="switchToDM('${empId}')">
                          <div class="w-6 h-6 rounded-full bg-gradient-to-r from-green-500 to-blue-500 flex items-center justify-center">
                              <span class="text-white text-xs font-semibold">${name.charAt(0).toUpperCase()}</span>
                          </div>
                          <span class="text-sm">${name}</span>
                      </div>
                  `;
              }
          }
          
          dmsList.innerHTML = html;
      }

      async function updateUserStatus(status) {
          if (!currentUser) return;
          
          try {
              const formData = new FormData();
              formData.append('employee_id', currentUser);
              formData.append('status', status);
              await fetch('/api/chat/status/update', { method: 'POST', body: formData });
          } catch (error) {
              console.error('Error updating status:', error);
          }
      }

      // Initialize the app
      init();
    </script>
    """
    return _eraya_lumen_page("Team Chat", body)
