import hmac
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from sqlalchemy.orm import Session
from models.orders import Order, OrderLineItem, OrderFulfillment, OrderEvent
from .status_engine import compute_current_status
from .sla_engine import compute_sla_due_at, is_sla_breached

class ShopifySync:
    def __init__(self, shop_url: str, access_token: str, webhook_secret: str):
        self.shop_url = shop_url
        self.access_token = access_token
        self.webhook_secret = webhook_secret
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to Shopify API with rate limiting"""
        url = f"{self.shop_url}/admin/api/2024-01{endpoint}"
        
        while True:
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('Retry-After', 5))
                time.sleep(retry_after)
                continue
                
            response.raise_for_status()
            return response.json()
    
    def verify_webhook(self, data: bytes, hmac_header: str) -> bool:
        """Verify Shopify webhook HMAC"""
        calculated_hmac = hmac.new(
            self.webhook_secret.encode('utf-8'),
            data,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(calculated_hmac, hmac_header)
    
    def sync_order(self, shopify_order: Dict, db: Session) -> Order:
        """Sync a single order from Shopify to database"""
        # Find or create order
        order = db.query(Order).filter_by(shopify_id=str(shopify_order["id"])).first()
        if not order:
            order = Order(shopify_id=str(shopify_order["id"]))
            db.add(order)
        
        # Update basic details
        order.order_number = shopify_order["order_number"]
        order.email = shopify_order["email"]
        order.phone = shopify_order.get("phone")
        
        # Customer details
        shipping_address = shopify_order.get("shipping_address", {})
        order.customer_name = shopify_order.get("customer", {}).get("name")
        order.shipping_name = shipping_address.get("name")
        order.shipping_address1 = shipping_address.get("address1")
        order.shipping_address2 = shipping_address.get("address2")
        order.shipping_city = shipping_address.get("city")
        order.shipping_state = shipping_address.get("province")
        order.shipping_pincode = shipping_address.get("zip")
        order.shipping_country = shipping_address.get("country_code")
        
        # Order details
        order.currency = shopify_order["currency"]
        order.total_price = float(shopify_order["total_price"])
        order.subtotal_price = float(shopify_order["subtotal_price"])
        order.total_tax = float(shopify_order["total_tax"])
        order.total_shipping = float(shopify_order.get("total_shipping_price_set", {}).get("shop_money", {}).get("amount", 0))
        order.total_discounts = float(shopify_order["total_discounts"])
        
        # Payment details
        financial_status = shopify_order["financial_status"]
        order.payment_method = "cod" if shopify_order.get("payment_gateway_names", []) == ["cash_on_delivery"] else "prepaid"
        order.payment_status = financial_status
        
        # Fulfillment
        order.fulfillment_status = shopify_order["fulfillment_status"] or "unfulfilled"
        
        # Timestamps
        order.created_at = datetime.fromisoformat(shopify_order["created_at"].rstrip('Z'))
        order.updated_at = datetime.fromisoformat(shopify_order["updated_at"].rstrip('Z'))
        order.cancelled_at = datetime.fromisoformat(shopify_order["cancelled_at"].rstrip('Z')) if shopify_order.get("cancelled_at") else None
        order.closed_at = datetime.fromisoformat(shopify_order["closed_at"].rstrip('Z')) if shopify_order.get("closed_at") else None
        
        # Compute status and SLA
        current_status = compute_current_status(shopify_order)
        if current_status != order.current_status:
            db.add(OrderEvent(
                order=order,
                event_type="status_change",
                old_value={"status": order.current_status},
                new_value={"status": current_status},
                actor_id="system",
                actor_name="Shopify Sync"
            ))
        order.current_status = current_status
        
        # Update SLA
        order.sla_due_at = compute_sla_due_at(shopify_order, current_status)
        order.sla_breached = is_sla_breached(shopify_order, current_status)
        
        # Metadata
        order.tags = shopify_order.get("tags", "").split(", ") if shopify_order.get("tags") else []
        order.note = shopify_order.get("note")
        
        # Sync line items
        existing_items = {item.shopify_id: item for item in order.line_items}
        for shopify_item in shopify_order["line_items"]:
            item_id = str(shopify_item["id"])
            if item_id in existing_items:
                item = existing_items[item_id]
            else:
                item = OrderLineItem(shopify_id=item_id)
                order.line_items.append(item)
            
            item.product_id = str(shopify_item["product_id"])
            item.variant_id = str(shopify_item["variant_id"])
            item.sku = shopify_item.get("sku")
            item.title = shopify_item["title"]
            item.variant_title = shopify_item.get("variant_title")
            item.quantity = shopify_item["quantity"]
            item.price = float(shopify_item["price"])
            
            # Handle customization
            properties = {p["name"]: p["value"] for p in shopify_item.get("properties", [])}
            item.customization_fields = properties
            item.requires_engraving = properties.get("_requires_engraving") == "true"
            item.engraving_text = properties.get("engraving_text")
        
        # Sync fulfillments
        existing_fulfillments = {f.shopify_id: f for f in order.fulfillments}
        for shopify_fulfillment in shopify_order.get("fulfillments", []):
            fulfillment_id = str(shopify_fulfillment["id"])
            if fulfillment_id in existing_fulfillments:
                fulfillment = existing_fulfillments[fulfillment_id]
            else:
                fulfillment = OrderFulfillment(shopify_id=fulfillment_id)
                order.fulfillments.append(fulfillment)
            
            fulfillment.status = shopify_fulfillment["status"]
            fulfillment.tracking_number = shopify_fulfillment.get("tracking_number")
            fulfillment.tracking_url = shopify_fulfillment.get("tracking_url")
            fulfillment.tracking_company = shopify_fulfillment.get("tracking_company")
            fulfillment.created_at = datetime.fromisoformat(shopify_fulfillment["created_at"].rstrip('Z'))
            fulfillment.updated_at = datetime.fromisoformat(shopify_fulfillment["updated_at"].rstrip('Z'))
        
        db.commit()
        return order
    
    def backfill_orders(self, db: Session, start_date: Optional[datetime] = None):
        """Backfill all orders from Shopify"""
        params = {
            'limit': 250,
            'status': 'any'
        }
        
        if start_date:
            params['created_at_min'] = start_date.isoformat()
        
        while True:
            response = self._get("/orders.json", params)
            orders = response.get("orders", [])
            
            if not orders:
                break
            
            for shopify_order in orders:
                self.sync_order(shopify_order, db)
            
            # Handle pagination
            next_link = response.get("next_link")
            if not next_link:
                break
                
            params['page_info'] = next_link.split("page_info=")[1]
            
            # Rate limiting
            time.sleep(0.5)  # 2 requests per second
    
    def sync_recent_orders(self, db: Session):
        """Sync orders from last 48 hours"""
        start_date = datetime.utcnow() - timedelta(hours=48)
        self.backfill_orders(db, start_date)
