from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from models import get_db
from models.orders import Order, OrderEvent
from utils.status_engine import get_status_display

router = APIRouter(tags=["orders"])

templates = Jinja2Templates(directory="templates")

# Import NAV_ITEMS from app.py and make it available to templates
from app import NAV_ITEMS
templates.env.globals["NAV_ITEMS"] = NAV_ITEMS

@router.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request):
    """Render the orders dashboard page"""
    return templates.TemplateResponse("orders/index.html", {
        "request": request,
        "title": "Orders Dashboard"
    })

@router.get("/api/orders")
def list_orders(
    status: Optional[List[str]] = Query(None),
    q: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    payment_method: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    tag: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List orders with filters and cursor pagination"""
    query = db.query(Order)
    
    # Apply filters
    if status:
        query = query.filter(Order.current_status.in_(status))
    
    if q:
        query = query.filter(or_(
            Order.order_number.ilike(f"%{q}%"),
            Order.customer_name.ilike(f"%{q}%"),
            Order.email.ilike(f"%{q}%"),
            Order.phone.ilike(f"%{q}%")
        ))
    
    if start_date:
        query = query.filter(Order.created_at >= start_date)
    
    if end_date:
        query = query.filter(Order.created_at <= end_date)
    
    if payment_method:
        query = query.filter(Order.payment_method == payment_method)
    
    if city:
        query = query.filter(Order.shipping_city.ilike(f"%{city}%"))
    
    if state:
        query = query.filter(Order.shipping_state.ilike(f"%{state}%"))
    
    if tag:
        query = query.filter(Order.tags.contains([tag]))
    
    # Handle cursor pagination
    if cursor:
        last_id = int(cursor)
        query = query.filter(Order.id < last_id)
    
    # Always sort by id descending for cursor pagination
    query = query.order_by(Order.id.desc())
    
    # Get one extra record to check if there are more results
    orders = query.limit(limit + 1).all()
    
    has_more = len(orders) > limit
    if has_more:
        orders = orders[:-1]
        next_cursor = str(orders[-1].id)
    else:
        next_cursor = None
    
    # Format orders for response
    results = []
    for order in orders:
        status_display = get_status_display(order.current_status)
        results.append({
            "id": order.id,
            "shopify_id": order.shopify_id,
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "email": order.email,
            "phone": order.phone,
            "total_price": order.total_price,
            "payment_method": order.payment_method,
            "current_status": order.current_status,
            "status_display": status_display,
            "created_at": order.created_at.isoformat(),
            "sla_due_at": order.sla_due_at.isoformat() if order.sla_due_at else None,
            "sla_breached": order.sla_breached,
            "tags": order.tags
        })
    
    return {
        "orders": results,
        "next_cursor": next_cursor
    }

@router.get("/api/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    """Get detailed order information"""
    order = db.query(Order).filter(
        or_(Order.id == order_id, Order.shopify_id == order_id)
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    status_display = get_status_display(order.current_status)
    
    return {
        "id": order.id,
        "shopify_id": order.shopify_id,
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "email": order.email,
        "phone": order.phone,
        "shipping_address": {
            "name": order.shipping_name,
            "address1": order.shipping_address1,
            "address2": order.shipping_address2,
            "city": order.shipping_city,
            "state": order.shipping_state,
            "pincode": order.shipping_pincode,
            "country": order.shipping_country
        },
        "total_price": order.total_price,
        "subtotal_price": order.subtotal_price,
        "total_tax": order.total_tax,
        "total_shipping": order.total_shipping,
        "total_discounts": order.total_discounts,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "current_status": order.current_status,
        "status_display": status_display,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "sla_due_at": order.sla_due_at.isoformat() if order.sla_due_at else None,
        "sla_breached": order.sla_breached,
        "tags": order.tags,
        "note": order.note,
        "line_items": [{
            "id": item.id,
            "product_id": item.product_id,
            "variant_id": item.variant_id,
            "sku": item.sku,
            "title": item.title,
            "variant_title": item.variant_title,
            "quantity": item.quantity,
            "price": item.price,
            "requires_engraving": item.requires_engraving,
            "engraving_text": item.engraving_text,
            "customization_fields": item.customization_fields
        } for item in order.line_items],
        "fulfillments": [{
            "id": f.id,
            "status": f.status,
            "tracking_number": f.tracking_number,
            "tracking_url": f.tracking_url,
            "tracking_company": f.tracking_company,
            "created_at": f.created_at.isoformat()
        } for f in order.fulfillments],
        "events": [{
            "id": e.id,
            "event_type": e.event_type,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "actor_name": e.actor_name,
            "created_at": e.created_at.isoformat()
        } for e in order.events]
    }

@router.post("/api/orders/{order_id}/status")
def update_order_status(
    order_id: str,
    status: str,
    note: Optional[str] = None,
    actor_id: str = None,
    actor_name: str = None,
    db: Session = Depends(get_db)
):
    """Update order status"""
    order = db.query(Order).filter(
        or_(Order.id == order_id, Order.shopify_id == order_id)
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    old_status = order.current_status
    order.current_status = status
    
    # Add event
    db.add(OrderEvent(
        order=order,
        event_type="status_change",
        old_value={"status": old_status},
        new_value={"status": status, "note": note},
        actor_id=actor_id,
        actor_name=actor_name
    ))
    
    db.commit()
    return {"success": True}

@router.get("/api/orders/metrics")
def get_order_metrics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Get order metrics and statistics"""
    query = db.query(Order)
    
    if start_date:
        query = query.filter(Order.created_at >= start_date)
    if end_date:
        query = query.filter(Order.created_at <= end_date)
    
    # Total orders
    total_orders = query.count()
    
    # Orders by status
    status_counts = {}
    for status in ["pending", "confirmed", "processing", "ready_to_pack", "packed", "shipped", "delivered", "cancelled"]:
        count = query.filter(Order.current_status == status).count()
        status_counts[status] = count
    
    # Orders shipped today
    today = datetime.utcnow().date()
    shipped_today = query.filter(
        and_(
            Order.current_status == "shipped",
            Order.updated_at >= datetime.combine(today, datetime.min.time())
        )
    ).count()
    
    # Orders delivered today
    delivered_today = query.filter(
        and_(
            Order.current_status == "delivered",
            Order.updated_at >= datetime.combine(today, datetime.min.time())
        )
    ).count()
    
    # RTO orders
    rto_orders = query.filter(Order.tags.contains(["RTO"])).count()
    
    # Disputed orders
    disputed_orders = query.filter(Order.current_status == "disputed").count()
    
    # SLA breached orders
    sla_breached = query.filter(Order.sla_breached == True).count()
    
    return {
        "total_orders": total_orders,
        "status_counts": status_counts,
        "shipped_today": shipped_today,
        "delivered_today": delivered_today,
        "rto_orders": rto_orders,
        "disputed_orders": disputed_orders,
        "sla_breached": sla_breached
    }
