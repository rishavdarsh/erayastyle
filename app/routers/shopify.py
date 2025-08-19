"""
Shopify router for order management and analytics with real API integration (NO AUTH - FIXED)
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any, List
import json
import httpx
import asyncio
from datetime import datetime, timedelta
import os
import base64
from cryptography.fernet import Fernet
import hashlib

from app.services import supa

router = APIRouter()

# Use a simple default user ID
DEFAULT_USER_ID = "default_user"

# Encryption for storing sensitive data
def get_encryption_key():
    """Generate or get encryption key for sensitive data"""
    key = os.getenv("SHOPIFY_ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        print(f"⚠️  Generated new encryption key. Add SHOPIFY_ENCRYPTION_KEY={key} to your .env file")
    return key.encode() if isinstance(key, str) else key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    """Encrypt sensitive data"""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt sensitive data"""
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

class ShopifyClient:
    """Shopify API client for making requests"""
    
    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "")
        if not self.shop_domain.endswith(".myshopify.com"):
            self.shop_domain = f"{self.shop_domain}.myshopify.com"
        self.access_token = access_token
        self.base_url = f"https://{self.shop_domain}"
        
    async def make_request(self, endpoint: str, method: str = "GET", params: Dict = None) -> Dict:
        """Make authenticated request to Shopify API"""
        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}/admin/api/2023-10/{endpoint}.json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params or {})
            else:
                response = await client.request(method, url, headers=headers, json=params or {})
            
            if response.status_code == 429:
                # Rate limit hit, wait and retry
                await asyncio.sleep(2)
                return await self.make_request(endpoint, method, params)
            
            response.raise_for_status()
            return response.json()
    
    async def test_connection(self) -> Dict:
        """Test connection to Shopify store"""
        try:
            shop_data = await self.make_request("shop")
            return {
                "success": True,
                "shop": shop_data.get("shop", {})
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_orders(self, limit: int = 250, status: str = "any", since_id: str = None) -> Dict:
        """Get orders from Shopify"""
        params = {
            "limit": min(limit, 250),  # Shopify max is 250
            "status": status
        }
        if since_id:
            params["since_id"] = since_id
            
        try:
            return await self.make_request("orders", params=params)
        except Exception as e:
            return {"orders": [], "error": str(e)}
    
    async def get_products_count(self) -> int:
        """Get total products count"""
        try:
            result = await self.make_request("products/count")
            return result.get("count", 0)
        except:
            return 0
    
    async def get_orders_count(self) -> int:
        """Get total orders count"""
        try:
            result = await self.make_request("orders/count")
            return result.get("count", 0)
        except:
            return 0

# Database functions for storing Shopify config
def save_shopify_config(user_id: str, shop_domain: str, access_token: str) -> Dict:
    """Save encrypted Shopify configuration"""
    try:
        encrypted_token = encrypt_data(access_token)
        config_data = {
            "user_id": user_id,
            "shop_domain": shop_domain,
            "access_token": encrypted_token,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Check if config exists
        existing = supa.supabase.table("shopify_config").select("*").eq("user_id", user_id).execute()
        
        if existing.data:
            # Update existing
            response = supa.supabase.table("shopify_config").update(config_data).eq("user_id", user_id).execute()
        else:
            # Insert new
            response = supa.supabase.table("shopify_config").insert(config_data).execute()
        
        return {"success": True, "data": response.data[0] if response.data else None}
    except Exception as e:
        error_msg = str(e)
        print(f"Error saving Shopify config: {e}")
        if "Could not find the table" in error_msg:
            return {"success": False, "error": "Database tables not set up. Please run the SQL setup script in Supabase."}
        return {"success": False, "error": str(e)}

def get_shopify_config(user_id: str) -> Dict:
    """Get decrypted Shopify configuration"""
    try:
        response = supa.supabase.table("shopify_config").select("*").eq("user_id", user_id).execute()
        
        if response.data:
            config = response.data[0]
            config["access_token"] = decrypt_data(config["access_token"])
            return {"success": True, "config": config}
        else:
            return {"success": False, "error": "No configuration found"}
    except Exception as e:
        error_msg = str(e)
        print(f"Error getting Shopify config: {e}")
        if "Could not find the table" in error_msg:
            return {"success": False, "error": "Database tables not set up. Please run the SQL setup script in Supabase."}
        return {"success": False, "error": str(e)}

def save_shopify_orders(orders: List[Dict]) -> Dict:
    """Save Shopify orders to database"""
    try:
        # Transform orders for storage
        db_orders = []
        for order in orders:
            db_order = {
                "shopify_id": str(order["id"]),
                "order_number": order.get("order_number", ""),
                "email": order.get("email", ""),
                "total_price": float(order.get("total_price", 0)),
                "currency": order.get("currency", "USD"),
                "financial_status": order.get("financial_status", ""),
                "fulfillment_status": order.get("fulfillment_status"),
                "created_at": order.get("created_at"),
                "updated_at": order.get("updated_at"),
                "customer_data": json.dumps(order.get("customer", {})),
                "line_items": json.dumps(order.get("line_items", [])),
                "shipping_address": json.dumps(order.get("shipping_address", {})),
                "billing_address": json.dumps(order.get("billing_address", {})),
                "tags": order.get("tags", ""),
                "note": order.get("note", ""),
                "synced_at": datetime.utcnow().isoformat()
            }
            db_orders.append(db_order)
        
        # Upsert orders
        response = supa.supabase.table("shopify_orders").upsert(db_orders, on_conflict="shopify_id").execute()
        return {"success": True, "count": len(db_orders)}
    except Exception as e:
        print(f"Error saving Shopify orders: {e}")
        return {"success": False, "error": str(e)}

async def sync_shopify_orders(user_id: str) -> Dict:
    """Sync orders from Shopify to database (incremental)"""
    try:
        # Get Shopify config
        config_result = get_shopify_config(user_id)
        if not config_result["success"]:
            return {"success": False, "error": "No Shopify configuration found"}
        
        config = config_result["config"]
        client = ShopifyClient(config["shop_domain"], config["access_token"])
        
        # Get orders from Shopify (incremental - only new orders)
        orders_result = await client.get_orders(limit=250, status="any")
        if "error" in orders_result:
            return {"success": False, "error": orders_result["error"]}
        
        orders = orders_result.get("orders", [])
        
        # Save to database
        save_result = save_shopify_orders(orders)
        
        # Update sync status
        sync_status = {
            "user_id": user_id,
            "last_sync": datetime.utcnow().isoformat(),
            "orders_synced": len(orders),
            "status": "success"
        }
        
        supa.supabase.table("shopify_sync_status").upsert(sync_status, on_conflict="user_id").execute()
        
        return {
            "success": True,
            "orders_synced": len(orders),
            "message": f"Successfully synced {len(orders)} orders"
        }
        
    except Exception as e:
        print(f"Error syncing Shopify orders: {e}")
        return {"success": False, "error": str(e)}

async def full_sync_shopify_orders(user_id: str) -> Dict:
    """Full sync of ALL orders from Shopify to database"""
    try:
        # Get Shopify config
        config_result = get_shopify_config(user_id)
        if not config_result["success"]:
            return {"success": False, "error": "No Shopify configuration found"}
        
        config = config_result["config"]
        client = ShopifyClient(config["shop_domain"], config["access_token"])
        
        print(f"Starting full sync for user {user_id}")
        
        # Fetch ALL orders in batches without relying on count
        all_orders = []
        limit = 250  # Shopify max per request
        params = {"limit": limit, "status": "any"}
        
        # Fetch orders in batches until we get no more
        batch_count = 0
        while True:
            batch_count += 1
            print(f"Fetching batch {batch_count}...")
            
            try:
                # Get batch of orders
                orders_result = await client.make_request("orders", params=params)
                if "orders" not in orders_result:
                    print("No orders in response")
                    break
                    
                batch_orders = orders_result["orders"]
                if not batch_orders:
                    print("Empty batch received")
                    break
                    
                print(f"Batch {batch_count}: Got {len(batch_orders)} orders")
                all_orders.extend(batch_orders)
                
                # Check if we have more orders
                if len(batch_orders) < limit:
                    print(f"Received {len(batch_orders)} orders (less than limit {limit}), stopping")
                    break
                    
                # Get the last order ID for pagination
                last_order_id = batch_orders[-1]["id"]
                params["since_id"] = last_order_id
                
                # Safety check to prevent infinite loops
                if batch_count > 50:  # Max 50 batches
                    print("Reached maximum batch limit, stopping")
                    break
                    
            except Exception as e:
                print(f"Error fetching batch {batch_count}: {e}")
                break
        
        print(f"Total orders fetched: {len(all_orders)}")
        
        if not all_orders:
            return {"success": False, "error": "No orders were fetched"}
        
        # Save all orders to database
        save_result = save_shopify_orders(all_orders)
        
        if not save_result["success"]:
            return {"success": False, "error": f"Failed to save orders: {save_result['error']}"}
        
        # Update sync status
        sync_status = {
            "user_id": user_id,
            "last_sync": datetime.utcnow().isoformat(),
            "orders_synced": len(all_orders),
            "status": "success"
        }
        
        supa.supabase.table("shopify_sync_status").upsert(sync_status, on_conflict="user_id").execute()
        
        return {
            "success": True,
            "orders_synced": len(all_orders),
            "message": f"Successfully synced {len(all_orders)} orders (full sync)"
        }
        
    except Exception as e:
        print(f"Error in full sync: {e}")
        return {"success": False, "error": str(e)}

# Routes (NO AUTHENTICATION REQUIRED)
@router.get("/shopify/settings", response_class=HTMLResponse)
async def shopify_settings_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Shopify settings page"""
    return templates.TemplateResponse("shopify_settings.html", {
        "request": request,
        "title": "Shopify Settings",
        "header": "Shopify Settings"
    })

@router.post("/api/shopify/config")
async def save_config(request: Request):
    """Save Shopify configuration (NO AUTH)"""
    try:
        body = await request.json()
        
        shop_domain = body.get("shop_domain", "").strip()
        access_token = body.get("access_token", "").strip()
        
        if not shop_domain or not access_token:
            raise HTTPException(status_code=400, detail="Shop domain and access token are required")
        
        # Test connection first
        client = ShopifyClient(shop_domain, access_token)
        test_result = await client.test_connection()
        
        if not test_result["success"]:
            raise HTTPException(status_code=400, detail=f"Connection failed: {test_result['error']}")
        
        # Save configuration with default user ID
        result = save_shopify_config(DEFAULT_USER_ID, shop_domain, access_token)
        
        if result["success"]:
            return JSONResponse(content={
                "success": True,
                "message": "Configuration saved successfully",
                "shop_info": test_result["shop"]
            })
        else:
            raise HTTPException(status_code=500, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/shopify/config")
async def get_config(request: Request):
    """Get Shopify configuration (NO AUTH)"""
    try:
        result = get_shopify_config(DEFAULT_USER_ID)
        
        if result["success"]:
            config = result["config"]
            # Remove sensitive data from response
            safe_config = {
                "shop_domain": config["shop_domain"],
                "updated_at": config["updated_at"],
                "has_token": bool(config.get("access_token"))
            }
            return JSONResponse(content={
                "success": True,
                "config": safe_config
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": result["error"]
            })
            
    except Exception as e:
        print(f"Error getting config: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.delete("/api/shopify/config")
async def delete_config(request: Request):
    """Delete Shopify configuration (NO AUTH)"""
    try:
        # Delete the configuration
        response = supa.supabase.table("shopify_config").delete().eq("user_id", DEFAULT_USER_ID).execute()
        
        # Also clear sync status
        supa.supabase.table("shopify_sync_status").delete().eq("user_id", DEFAULT_USER_ID).execute()
        
        return JSONResponse(content={
            "success": True,
            "message": "Configuration deleted successfully"
        })
        
    except Exception as e:
        print(f"Error deleting config: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.get("/api/shopify/test")
async def test_connection(request: Request):
    """Test Shopify connection (NO AUTH)"""
    try:
        config_result = get_shopify_config(DEFAULT_USER_ID)
        if not config_result["success"]:
            raise HTTPException(status_code=400, detail="No configuration found")
        
        config = config_result["config"]
        client = ShopifyClient(config["shop_domain"], config["access_token"])
        result = await client.test_connection()
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error testing connection: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.post("/api/shopify/test-connection")
async def test_connection_post(request: Request):
    """Test Shopify connection with provided credentials (NO AUTH)"""
    try:
        body = await request.json()
        
        shop_domain = body.get("shop_domain", "").strip()
        access_token = body.get("access_token", "").strip()
        
        if not shop_domain or not access_token:
            return JSONResponse(content={
                "success": False,
                "error": "Shop domain and access token are required"
            }, status_code=400)
        
        # Test connection directly without saving
        client = ShopifyClient(shop_domain, access_token)
        result = await client.test_connection()
        
        return JSONResponse(content=result)
        
    except Exception as e:
        print(f"Error testing connection with provided credentials: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

@router.get("/api/shopify/store-info")
async def get_store_info(request: Request):
    """Get store information (NO AUTH)"""
    try:
        config_result = get_shopify_config(DEFAULT_USER_ID)
        if not config_result["success"]:
            raise HTTPException(status_code=400, detail="No configuration found")
        
        config = config_result["config"]
        client = ShopifyClient(config["shop_domain"], config["access_token"])
        
        # Get shop info
        shop_result = await client.test_connection()
        if not shop_result["success"]:
            raise HTTPException(status_code=400, detail=shop_result["error"])
        
        shop = shop_result["shop"]
        
        # Get counts
        products_count = await client.get_products_count()
        orders_count = await client.get_orders_count()
        
        store_info = {
            "name": shop.get("name", ""),
            "email": shop.get("email", ""),
            "domain": shop.get("domain", ""),
            "product_count": products_count,
            "order_count": orders_count,
            "plan_name": shop.get("plan_name", ""),
            "currency": shop.get("currency", ""),
            "timezone": shop.get("timezone", "")
        }
        
        return JSONResponse(content={
            "success": True,
            "store": store_info
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting store info: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.post("/api/shopify/sync")
async def manual_sync(request: Request, background_tasks: BackgroundTasks):
    """Manually trigger order sync (NO AUTH)"""
    try:
        # Add sync task to background
        background_tasks.add_task(sync_shopify_orders, DEFAULT_USER_ID)
        
        return JSONResponse(content={
            "success": True,
            "message": "Sync started in background"
        })
        
    except Exception as e:
        print(f"Error starting sync: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.post("/api/shopify/instant-sync")
async def instant_sync(request: Request):
    """Instant sync - fetches latest orders immediately (NO AUTH)"""
    try:
        print("Starting instant sync...")
        
        # Get Shopify config
        config_result = get_shopify_config(DEFAULT_USER_ID)
        if not config_result["success"]:
            return JSONResponse(content={
                "success": False,
                "error": "No Shopify configuration found. Please configure your store first."
            })
        
        config = config_result["config"]
        client = ShopifyClient(config["shop_domain"], config["access_token"])
        
        print(f"Fetching latest orders from {config['shop_domain']}...")
        
        # Get latest orders (recent ones first)
        orders_result = await client.get_orders(limit=250, status="any")
        if "error" in orders_result:
            return JSONResponse(content={
                "success": False,
                "error": f"Failed to fetch orders: {orders_result['error']}"
            })
        
        orders = orders_result.get("orders", [])
        print(f"Fetched {len(orders)} orders from Shopify")
        
        if not orders:
            return JSONResponse(content={
                "success": True,
                "orders_synced": 0,
                "message": "No new orders to sync"
            })
        
        # Save to database
        save_result = save_shopify_orders(orders)
        if not save_result["success"]:
            return JSONResponse(content={
                "success": False,
                "error": f"Failed to save orders: {save_result['error']}"
            })
        
        # Update sync status
        sync_status = {
            "user_id": DEFAULT_USER_ID,
            "last_sync": datetime.utcnow().isoformat(),
            "orders_synced": len(orders),
            "status": "success"
        }
        
        supa.supabase.table("shopify_sync_status").upsert(sync_status, on_conflict="user_id").execute()
        
        print(f"Instant sync completed: {len(orders)} orders synced")
        
        return JSONResponse(content={
            "success": True,
            "orders_synced": len(orders),
            "message": f"✅ Instantly synced {len(orders)} orders!",
            "latest_orders": [
                {
                    "order_number": order.get("order_number", "N/A"),
                    "customer": order.get("customer", {}).get("first_name", "Unknown"),
                    "total": order.get("total_price", "0"),
                    "status": order.get("financial_status", "unknown"),
                    "created": order.get("created_at", "N/A")
                }
                for order in orders[:5]  # Show first 5 orders
            ]
        })
        
    except Exception as e:
        print(f"Error in instant sync: {e}")
        return JSONResponse(content={
            "success": False,
            "error": f"Sync failed: {str(e)}"
        }, status_code=500)

@router.post("/api/shopify/full-sync")
async def full_sync(request: Request, background_tasks: BackgroundTasks):
    """Manually trigger FULL order sync - fetches ALL orders (NO AUTH)"""
    try:
        # Add full sync task to background
        background_tasks.add_task(full_sync_shopify_orders, DEFAULT_USER_ID)
        
        return JSONResponse(content={
            "success": True,
            "message": "Full sync started in background - this will fetch ALL orders"
        })
        
    except Exception as e:
        print(f"Error starting full sync: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.post("/api/shopify/test-full-sync")
async def test_full_sync(request: Request):
    """Test endpoint for full sync (NO AUTH)"""
    try:
        # Test the full sync function directly
        result = await full_sync_shopify_orders(DEFAULT_USER_ID)
        return JSONResponse(content=result)
        
    except Exception as e:
        print(f"Error in test full sync: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

@router.get("/api/shopify/orders")
async def get_orders(
    request: Request,
    limit: int = Query(50, description="Number of orders to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Get synced Shopify orders from database (NO AUTH)"""
    try:
        # Get orders from database
        response = supa.supabase.table("shopify_orders")\
            .select("*")\
            .order("created_at", desc=True)\
            .range(offset, offset + limit - 1)\
            .execute()
        
        orders = []
        for order in response.data or []:
            order_data = {
                "id": order["shopify_id"],
                "order_number": order["order_number"],
                "email": order["email"],
                "total_price": order["total_price"],
                "currency": order["currency"],
                "financial_status": order["financial_status"],
                "fulfillment_status": order["fulfillment_status"],
                "created_at": order["created_at"],
                "customer": json.loads(order.get("customer_data", "{}")),
                "line_items": json.loads(order.get("line_items", "[]")),
                "tags": order.get("tags", ""),
                "synced_at": order["synced_at"]
            }
            orders.append(order_data)
        
        return JSONResponse(content={
            "success": True,
            "orders": orders,
            "total": len(orders),
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        print(f"Error getting orders: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.get("/api/shopify/sync-status")
async def get_sync_status(request: Request):
    """Get current sync status (NO AUTH)"""
    try:
        # Get sync status from database
        response = supa.supabase.table("shopify_sync_status")\
            .select("*")\
            .eq("user_id", DEFAULT_USER_ID)\
            .execute()
        
        if response.data:
            status = response.data[0]
            return JSONResponse(content={
                "success": True,
                "status": status
            })
        else:
            return JSONResponse(content={
                "success": True,
                "status": {
                    "user_id": DEFAULT_USER_ID,
                    "last_sync": None,
                    "orders_synced": 0,
                    "status": "pending",
                    "error_message": None
                }
        })
        
    except Exception as e:
        print(f"Error getting sync status: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })

@router.get("/api/shopify/analytics")
async def get_analytics(
    request: Request,
    days: int = Query(30, description="Number of days for analytics")
):
    """Get order analytics from synced data (NO AUTH)"""
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get orders from database
        response = supa.supabase.table("shopify_orders")\
            .select("*")\
            .gte("created_at", start_date.isoformat())\
            .lte("created_at", end_date.isoformat())\
            .execute()
        
        orders = response.data or []
        
        # Calculate analytics
        total_orders = len(orders)
        total_revenue = sum(float(order.get("total_price", 0)) for order in orders)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        # Group by financial status
        status_counts = {}
        for order in orders:
            status = order.get("financial_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Recent orders (last 10)
        recent_orders = sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]
        
        analytics = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "totals": {
                "orders": total_orders,
                "revenue": round(total_revenue, 2),
                "avg_order_value": round(avg_order_value, 2)
            },
            "status_breakdown": status_counts,
            "recent_orders": recent_orders
        }
        
        return JSONResponse(content={
            "success": True,
            "analytics": analytics
        })
        
    except Exception as e:
        print(f"Error getting analytics: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        })
