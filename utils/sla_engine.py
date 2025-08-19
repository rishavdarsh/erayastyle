from datetime import datetime, timedelta
from typing import Optional
from .status_engine import OrderStatus

def compute_sla_due_at(order: dict, current_status: str) -> Optional[datetime]:
    """
    Compute SLA due date based on order status and properties
    """
    created_at = datetime.fromisoformat(order["created_at"].rstrip('Z'))
    
    # No SLA for completed/cancelled orders
    if current_status in [
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
        OrderStatus.RETURNED
    ]:
        return None
    
    # Base SLAs by status
    SLA_HOURS = {
        OrderStatus.PENDING: 24,  # 24 hours to confirm
        OrderStatus.CONFIRMED: 48,  # 48 hours to process
        OrderStatus.PROCESSING: 72,  # 72 hours to pack
        OrderStatus.READY_TO_PACK: 24,  # 24 hours to pack
        OrderStatus.PACKED: 24,  # 24 hours to ship
        OrderStatus.SHIPPED: 168,  # 7 days to deliver
    }
    
    # Get base SLA hours
    base_hours = SLA_HOURS.get(current_status)
    if not base_hours:
        return None
        
    # Adjust for order properties
    if any(item.get("properties", {}).get("_requires_engraving") for item in order.get("line_items", [])):
        base_hours += 24  # Add 24 hours for engraving
    
    # Adjust for weekends
    # TODO: Add proper business days calculation
    
    return created_at + timedelta(hours=base_hours)

def is_sla_breached(order: dict, current_status: str) -> bool:
    """
    Check if order has breached its SLA
    """
    sla_due_at = compute_sla_due_at(order, current_status)
    if not sla_due_at:
        return False
        
    return datetime.utcnow() > sla_due_at
