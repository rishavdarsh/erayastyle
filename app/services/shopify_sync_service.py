"""
Background service for syncing Shopify orders automatically (NO AUTH - FIXED)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import json

from app.services import supa

logger = logging.getLogger(__name__)

# Use the same default user ID as the router
DEFAULT_USER_ID = "default_user"

class ShopifySyncService:
    """Background service for automatic Shopify order synchronization"""
    
    def __init__(self, sync_interval_minutes: int = 10):
        self.sync_interval = sync_interval_minutes * 60  # Convert to seconds
        self.is_running = False
        self.sync_task = None
    
    async def start_background_sync(self):
        """Start the background sync service"""
        if self.is_running:
            logger.info("Sync service is already running")
            return
        
        self.is_running = True
        self.sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"🔄 Shopify sync service started (interval: {self.sync_interval/60} minutes)")
    
    async def stop_background_sync(self):
        """Stop the background sync service"""
        self.is_running = False
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Shopify sync service stopped")
    
    async def _sync_loop(self):
        """Main sync loop that runs in background"""
        while self.is_running:
            try:
                await self._sync_all_users()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _sync_all_users(self):
        """Sync orders for the default user"""
        try:
            # Just try to sync the default user
            await self._sync_user_orders(DEFAULT_USER_ID)
                
        except Exception as e:
            error_msg = str(e)
            if "Could not find the table" in error_msg:
                logger.warning("⚠️ Shopify tables not found. Please run the SQL setup script in Supabase.")
            else:
                # Only log actual errors, not "no config found" messages
                if "No configuration found" not in error_msg:
                    logger.error(f"Error in sync: {e}")
    
    async def _sync_user_orders(self, user_id: str) -> Dict:
        """Sync orders for a specific user"""
        try:
            # Import here to avoid circular imports
            from app.routers.shopify import get_shopify_config, ShopifyClient, save_shopify_orders
            
            # Get user's Shopify config
            config_result = get_shopify_config(user_id)
            if not config_result["success"]:
                # Don't log this as an error - it's normal when no config exists yet
                return {"success": False, "error": "No configuration found"}
            
            config = config_result["config"]
            client = ShopifyClient(config["shop_domain"], config["access_token"])
            
            # Get the last synced order ID to only fetch new orders
            try:
                last_order_response = supa.supabase.table("shopify_orders")\
                    .select("shopify_id")\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()
                
                since_id = None
                if last_order_response.data:
                    since_id = last_order_response.data[0]["shopify_id"]
            except:
                since_id = None
            
            # Get orders from Shopify
            orders_result = await client.get_orders(limit=250, status="any", since_id=since_id)
            
            if "error" in orders_result:
                logger.error(f"Shopify API error for user {user_id}: {orders_result['error']}")
                self._update_sync_status(user_id, "error", 0, orders_result["error"])
                return {"success": False, "error": orders_result["error"]}
            
            orders = orders_result.get("orders", [])
            
            if not orders:
                logger.info(f"No new orders found for user {user_id}")
                self._update_sync_status(user_id, "success", 0)
                return {"success": True, "orders_synced": 0}
            
            # Save orders to database
            save_result = save_shopify_orders(orders)
            
            if save_result["success"]:
                logger.info(f"✅ Synced {len(orders)} orders for user {user_id}")
                self._update_sync_status(user_id, "success", len(orders))
                return {"success": True, "orders_synced": len(orders)}
            else:
                logger.error(f"Error saving orders for user {user_id}: {save_result['error']}")
                self._update_sync_status(user_id, "error", 0, save_result["error"])
                return {"success": False, "error": save_result["error"]}
                
        except Exception as e:
            error_msg = str(e)
            # Don't log "No configuration found" as an error
            if "No configuration found" not in error_msg:
                logger.error(f"Error syncing orders for user {user_id}: {error_msg}")
                self._update_sync_status(user_id, "error", 0, error_msg)
            return {"success": False, "error": error_msg}
    
    def _update_sync_status(self, user_id: str, status: str, orders_synced: int = 0, error_message: str = None):
        """Update sync status in database"""
        try:
            sync_data = {
                "user_id": user_id,
                "last_sync": datetime.utcnow().isoformat(),
                "orders_synced": orders_synced,
                "status": status,
                "error_message": error_message
            }
            
            supa.supabase.table("shopify_sync_status").upsert(sync_data, on_conflict="user_id").execute()
            
        except Exception as e:
            logger.error(f"Error updating sync status for user {user_id}: {e}")
    
    async def manual_sync(self, user_id: str) -> Dict:
        """Manually trigger sync for a specific user"""
        logger.info(f"🔄 Manual sync triggered for user {user_id}")
        return await self._sync_user_orders(user_id)

# Global sync service instance
sync_service = ShopifySyncService(sync_interval_minutes=10)  # Sync every 10 minutes

async def start_shopify_sync():
    """Start the Shopify sync service"""
    await sync_service.start_background_sync()

async def stop_shopify_sync():
    """Stop the Shopify sync service"""
    await sync_service.stop_background_sync()

async def manual_sync_user(user_id: str) -> Dict:
    """Manually sync orders for a specific user"""
    return await sync_service.manual_sync(user_id)