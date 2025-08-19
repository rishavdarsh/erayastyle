"""
Hub router for dashboard and main navigation
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional
from datetime import datetime, timedelta
import json

from app.deps import require_manager
from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

def get_shopify_stats() -> Dict:
    """Get real-time Shopify statistics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        
        # Get today's orders
        today_orders = supa.supabase.table("shopify_orders")\
            .select("*")\
            .gte("created_at", today_start.isoformat())\
            .execute()
        
        # Get this week's orders
        week_orders = supa.supabase.table("shopify_orders")\
            .select("*")\
            .gte("created_at", week_start.isoformat())\
            .execute()
        
        # Get all orders for totals
        all_orders = supa.supabase.table("shopify_orders")\
            .select("*")\
            .execute()
        
        today_data = today_orders.data or []
        week_data = week_orders.data or []
        all_data = all_orders.data or []
        
        # Calculate stats
        todays_revenue = sum(float(order.get("total_price", 0)) for order in today_data)
        weeks_revenue = sum(float(order.get("total_price", 0)) for order in week_data)
        total_revenue = sum(float(order.get("total_price", 0)) for order in all_data)
        
        # Count by status
        pending_orders = len([o for o in all_data if o.get("financial_status") in ["pending", "authorized"]])
        fulfilled_orders = len([o for o in all_data if o.get("fulfillment_status") == "fulfilled"])
        
        # Get recent orders (last 5)
        recent_orders = sorted(all_data, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
        
        return {
            "orders_today": len(today_data),
            "orders_this_week": len(week_data),
            "pending_orders": pending_orders,
            "fulfilled_orders": fulfilled_orders,
            "todays_revenue": f"{todays_revenue:,.2f}",
            "weeks_revenue": f"{weeks_revenue:,.2f}",
            "total_revenue": f"{total_revenue:,.2f}",
            "total_orders": len(all_data),
            "recent_orders": recent_orders,
            "last_sync": get_last_sync_time()
        }
        
    except Exception as e:
        print(f"Error getting Shopify stats: {e}")
        # Return fallback stats
        return {
            "orders_today": 0,
            "orders_this_week": 0,
            "pending_orders": 0,
            "fulfilled_orders": 0,
            "todays_revenue": "0.00",
            "weeks_revenue": "0.00",
            "total_revenue": "0.00",
            "total_orders": 0,
            "recent_orders": [],
            "last_sync": "Never",
            "error": "Unable to fetch Shopify data"
        }

def get_last_sync_time() -> str:
    """Get the last sync time"""
    try:
        response = supa.supabase.table("shopify_sync_status")\
            .select("last_sync")\
            .order("last_sync", desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            last_sync = response.data[0].get("last_sync")
            if last_sync:
                sync_time = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                now = datetime.utcnow().replace(tzinfo=sync_time.tzinfo)
                diff = now - sync_time
                
                if diff.total_seconds() < 60:
                    return "Just now"
                elif diff.total_seconds() < 3600:
                    return f"{int(diff.total_seconds() // 60)} minutes ago"
                else:
                    return f"{int(diff.total_seconds() // 3600)} hours ago"
        
        return "Never"
    except Exception as e:
        print(f"Error getting last sync time: {e}")
        return "Unknown"

@router.get("/hub", response_class=HTMLResponse)
async def hub_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Main dashboard/hub page with real Shopify data"""
    
    # Get current time for greeting
    now = datetime.now()
    hour = now.hour
    
    if 5 <= hour < 12:
        time_greeting = "Good morning"
    elif 12 <= hour < 17:
        time_greeting = "Good afternoon"
    else:
        time_greeting = "Good evening"
    
    # Get day message
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_message = f"Happy {day_names[now.weekday()]}! Today is {now.strftime('%B %d, %Y')}"
    
    # Get real Shopify stats
    stats = get_shopify_stats()
    
    # Add some additional mock stats for features not yet implemented
    stats.update({
        "active_employees": 8,  # This would come from attendance system
        "tasks_pending": 3,     # This would come from task system
        "packing_queue": 7      # This would come from packing system
    })
    
    return templates.TemplateResponse("hub.html", {
        "request": request,
        "title": "Dashboard",
        "header": "Dashboard",
        "time_greeting": time_greeting,
        "first_name": "User",  # This would come from the authenticated user
        "day_message": day_message,
        "stats": stats
    })

@router.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    """Redirect root to hub"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/hub", status_code=302)
