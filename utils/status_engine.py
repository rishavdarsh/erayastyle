from datetime import datetime, timedelta
from typing import Dict, Optional

class OrderStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY_TO_PACK = "ready_to_pack"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"
    ON_HOLD = "on_hold"
    DISPUTED = "disputed"
    ERROR = "error"

def compute_current_status(order: Dict) -> str:
    """
    Compute internal status based on Shopify order state
    """
    # Handle cancelled state
    if order.get("cancelled_at"):
        if order.get("refunds") and any(r["status"] == "success" for r in order["refunds"]):
            return OrderStatus.REFUNDED
        return OrderStatus.CANCELLED
        
    # Handle closed state
    if order.get("closed_at"):
        if order.get("refunds"):
            return OrderStatus.REFUNDED
        return OrderStatus.DELIVERED
    
    # Check fulfillment status
    fulfillment_status = order.get("fulfillment_status")
    if fulfillment_status == "fulfilled":
        latest_fulfillment = order["fulfillments"][-1]
        if latest_fulfillment.get("tracking_info", {}).get("status") == "delivered":
            return OrderStatus.DELIVERED
        return OrderStatus.SHIPPED
        
    if fulfillment_status == "partial":
        return OrderStatus.PROCESSING
    
    # Check financial status
    financial_status = order.get("financial_status")
    if financial_status == "pending":
        return OrderStatus.PENDING
    
    if financial_status in ["paid", "partially_paid"]:
        # Check for customization/engraving
        if any(item.get("properties", {}).get("_requires_engraving") for item in order.get("line_items", [])):
            return OrderStatus.PROCESSING
        return OrderStatus.READY_TO_PACK
    
    # Check for disputes/errors
    if order.get("disputes"):
        return OrderStatus.DISPUTED
        
    if financial_status == "voided":
        return OrderStatus.ERROR
        
    return OrderStatus.PENDING

def get_status_display(status: str) -> Dict[str, str]:
    """
    Get display properties for a status
    """
    STATUS_DISPLAY = {
        OrderStatus.PENDING: {
            "label": "Pending",
            "color": "gray",
            "icon": "⏳"
        },
        OrderStatus.CONFIRMED: {
            "label": "Confirmed",
            "color": "blue",
            "icon": "✅"
        },
        OrderStatus.PROCESSING: {
            "label": "Processing",
            "color": "purple",
            "icon": "⚙️"
        },
        OrderStatus.READY_TO_PACK: {
            "label": "Ready to Pack",
            "color": "yellow",
            "icon": "📦"
        },
        OrderStatus.PACKED: {
            "label": "Packed",
            "color": "green",
            "icon": "✨"
        },
        OrderStatus.SHIPPED: {
            "label": "Shipped",
            "color": "blue",
            "icon": "🚚"
        },
        OrderStatus.DELIVERED: {
            "label": "Delivered",
            "color": "green",
            "icon": "🎉"
        },
        OrderStatus.CANCELLED: {
            "label": "Cancelled",
            "color": "red",
            "icon": "❌"
        },
        OrderStatus.RETURNED: {
            "label": "Returned",
            "color": "orange",
            "icon": "↩️"
        },
        OrderStatus.REFUNDED: {
            "label": "Refunded",
            "color": "red",
            "icon": "💰"
        },
        OrderStatus.ON_HOLD: {
            "label": "On Hold",
            "color": "orange",
            "icon": "⏸️"
        },
        OrderStatus.DISPUTED: {
            "label": "Disputed",
            "color": "red",
            "icon": "⚠️"
        },
        OrderStatus.ERROR: {
            "label": "Error",
            "color": "red",
            "icon": "❗"
        }
    }
    return STATUS_DISPLAY.get(status, {
        "label": status.title(),
        "color": "gray",
        "icon": "❔"
    })
