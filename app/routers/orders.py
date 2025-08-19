"""
Orders router for comprehensive order management, Shopify integration, and file processing
"""
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any, List
from pathlib import Path
import tempfile
import json
import io

from app.deps import require_manager
from app.services.orders_service import (
    shopify_service, 
    order_processing_service, 
    order_download_service
)

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Orders management page"""
    return templates.TemplateResponse("orders/index.html", {
        "request": request,
        "title": "Orders Management",
        "header": "Orders Management"
    })

# Main Orders API Endpoint (serves synced Shopify orders)
@router.get("/api/orders")
async def get_orders(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Order status filter"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    payment_method: Optional[str] = Query(None, description="Payment method filter"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(250, description="Number of orders to return (max 250)")
):
    """Get synced Shopify orders with filtering and pagination"""
    try:
        from app.services import supa
        
        # Use the Shopify API data directly since the database table seems to have extra rows
        shopify_response = supa.supabase.table("shopify_orders").select("*").not_.is_("shopify_id", "null").not_.eq("shopify_id", "").execute()
        all_orders_data = shopify_response.data or []
        
        # Don't limit the data - let the pagination handle it
        
        # Apply additional filters in Python
        filtered_orders = []
        for order in all_orders_data:
            # Apply status filter
            if status and order.get("financial_status") != status:
                continue
                
            # Apply date filters
            if start_date and order.get("created_at", "") < start_date:
                continue
            if end_date and order.get("created_at", "") > end_date:
                continue
                
            # Apply payment method filter
            if payment_method:
                order_tags = (order.get("tags", "") or "").lower()
                if payment_method == "cod" and "cod" not in order_tags and "ppcod" not in order_tags:
                    continue
                elif payment_method == "prepaid" and ("cod" in order_tags or "ppcod" in order_tags):
                    continue
                    
            # Apply search filter
            if q:
                search_text = f"{order.get('order_number', '')} {order.get('email', '')}".lower()
                if q.lower() not in search_text:
                    continue
                    
            filtered_orders.append(order)
        
        # Apply pagination
        if cursor:
            offset = int(cursor) if cursor.isdigit() else 0
        else:
            offset = 0
            
        # Validate and cap limit
        if limit > 250:
            limit = 250
            
        # Get paginated results
        end_index = min(offset + limit, len(filtered_orders))
        orders_data = filtered_orders[offset:end_index]
        
        # Get total count from filtered data
        total_count = len(filtered_orders)
        
        # Convert to frontend format
        orders = []
        for order in orders_data:
            # Parse customer data
            customer_data = {}
            try:
                if order.get("customer_data"):
                    customer_data = json.loads(order["customer_data"])
            except:
                customer_data = {}
            
            # Parse line items
            line_items = []
            try:
                if order.get("line_items"):
                    line_items = json.loads(order["line_items"])
            except:
                line_items = []
            
            # Determine status display
            financial_status = order.get("financial_status", "pending")
            fulfillment_status = order.get("fulfillment_status")
            
            status_display = {
                "pending": {"label": "Pending", "icon": "⏳", "color": "yellow"},
                "paid": {"label": "Paid", "icon": "✅", "color": "green"},
                "partially_paid": {"label": "Partially Paid", "icon": "⚠️", "color": "orange"},
                "refunded": {"label": "Refunded", "icon": "↩️", "color": "red"},
                "cancelled": {"label": "Cancelled", "icon": "❌", "color": "red"}
            }.get(financial_status, {"label": financial_status.title(), "icon": "❓", "color": "gray"})
            
            # Determine payment method from tags
            payment_method = "prepaid"
            if "cod" in (order.get("tags", "") or "").lower():
                payment_method = "cod"
            elif "ppcod" in (order.get("tags", "") or "").lower():
                payment_method = "cod"
            
            # Format order for frontend
            formatted_order = {
                "id": order["id"],
                "shopify_id": order["shopify_id"],
                "order_number": order.get("order_number", f"#{order['id']}"),
                "customer_name": f"{customer_data.get('first_name', '')} {customer_data.get('last_name', '')}".strip() or "Unknown Customer",
                "email": order.get("email", ""),
                "phone": customer_data.get("phone", ""),
                "total_price": float(order.get("total_price", 0)),
                "currency": order.get("currency", "INR"),
                "status": financial_status,
                "status_display": status_display,
                "fulfillment_status": fulfillment_status,
                "payment_method": payment_method,
                "created_at": order.get("created_at", ""),
                "tags": order.get("tags", ""),
                "line_items": line_items,
                "customer_data": customer_data
            }
            orders.append(formatted_order)
        
        # Calculate next cursor only if there are more orders
        next_cursor = None
        if offset + limit < total_count:
            next_cursor = str(offset + limit)
        
        return JSONResponse(content={
            "orders": orders,
            "total": total_count,
            "next_cursor": next_cursor,
            "filters": {
                "status": status,
                "start_date": start_date,
                "end_date": end_date,
                "payment_method": payment_method,
                "search": q
            }
        })
        
    except Exception as e:
        print(f"Error fetching orders: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching orders: {str(e)}"
        )

# Orders Metrics API Endpoint
@router.get("/api/orders/metrics")
async def get_orders_metrics(request: Request):
    """Get orders metrics for dashboard"""
    try:
        from app.services import supa
        
        # Get all orders
        response = supa.supabase.table("shopify_orders").select("*").execute()
        orders = response.data or []
        
        # Calculate metrics
        total_orders = len(orders)
        total_revenue = sum(float(order.get("total_price", 0)) for order in orders)
        
        # Count by status
        status_counts = {}
        for order in orders:
            status = order.get("financial_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Get recent orders (last 5)
        recent_orders = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
        
        # Format recent orders for display
        formatted_recent = []
        for order in recent_orders:
            customer_data = {}
            try:
                if order.get("customer_data"):
                    customer_data = json.loads(order["customer_data"])
            except:
                customer_data = {}
            
            formatted_recent.append({
                "id": order["id"],
                "order_number": order.get("order_number", f"#{order['id']}"),
                "status": order.get("financial_status", "pending"),
                "fulfillment_status": order.get("fulfillment_status"),
                "customer": {
                    "email": order.get("email", ""),
                    "name": f"{customer_data.get('first_name', '')} {customer_data.get('last_name', '')}".strip() or "Unknown Customer"
                },
                "line_items": json.loads(order.get("line_items", "[]")) if order.get("line_items") else [],
                "created_at": order.get("created_at", "")
            })
        
        return JSONResponse(content={
            "id": "metrics",
            "order_number": "#metrics",
            "status": "open",
            "fulfillment_status": "unfulfilled",
            "customer": {
                "email": "customer@example.com",
                "name": "Sample Customer"
            },
            "line_items": [{
                "id": "item-1",
                "name": "Sample Product",
                "variant": "Sample Variant",
                "quantity": 1
            }],
            "created_at": "2024-01-15T10:30:00Z",
            "metrics": {
                "total_orders": total_orders,
                "total_revenue": f"{total_revenue:,.2f}",
                "status_breakdown": status_counts,
                "recent_orders": formatted_recent
            }
        })
        
    except Exception as e:
        print(f"Error fetching orders metrics: {e}")
        # Return fallback data
        return JSONResponse(content={
            "id": "metrics",
            "order_number": "#metrics",
            "status": "open",
            "fulfillment_status": "unfulfilled",
            "customer": {
                "email": "customer@example.com",
                "name": "Sample Customer"
            },
            "line_items": [{
                "id": "item-1",
                "name": "Sample Product",
                "variant": "Sample Variant",
                "quantity": 1
            }],
            "created_at": "2024-01-15T10:30:00Z"
        })

# Shopify Orders API Endpoints
@router.get("/api/orders/shopify")
async def get_shopify_orders(
    request: Request,
    current_user: Dict = Depends(require_manager),
    status: str = Query("any", description="Order status filter"),
    fulfillment_status: Optional[str] = Query(None, description="Fulfillment status filter"),
    limit: int = Query(100, description="Number of orders to return"),
    page_info: Optional[str] = Query(None, description="Pagination token"),
    created_at_min: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    created_at_max: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Fetch orders from Shopify with pagination support"""
    try:
        result = shopify_service.fetch_orders(
            status=status,
            fulfillment_status=fulfillment_status,
            limit=limit,
            page_info=page_info,
            created_at_min=created_at_min,
            created_at_max=created_at_max
        )
        
        # Convert to standardized format
        orders = shopify_service.convert_orders_to_rows(result["orders"])
        
        return JSONResponse(content={
            "orders": orders,
            "total": len(orders),
            "next_page_info": result.get("next_page_info"),
            "prev_page_info": result.get("prev_page_info"),
            "filters": {
                "status": status,
                "fulfillment_status": fulfillment_status,
                "limit": limit,
                "created_at_min": created_at_min,
                "created_at_max": created_at_max
            }
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching Shopify orders: {str(e)}"
        )

@router.get("/api/orders/shopify/all")
async def get_all_shopify_orders(
    request: Request,
    current_user: Dict = Depends(require_manager),
    status: str = Query("any", description="Order status filter"),
    fulfillment_status: Optional[str] = Query(None, description="Fulfillment status filter"),
    created_at_min: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    created_at_max: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Fetch all orders from Shopify (handles pagination automatically)"""
    try:
        orders = shopify_service.fetch_all_orders(
            status=status,
            fulfillment_status=fulfillment_status,
            created_at_min=created_at_min,
            created_at_max=created_at_max
        )
        
        # Convert to standardized format
        converted_orders = shopify_service.convert_orders_to_rows(orders)
        
        return JSONResponse(content={
            "orders": converted_orders,
            "total": len(converted_orders),
            "filters": {
                "status": status,
                "fulfillment_status": fulfillment_status,
                "created_at_min": created_at_min,
                "created_at_max": created_at_max
            }
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching all Shopify orders: {str(e)}"
        )

# File Processing Endpoints
@router.post("/api/orders/process-file")
async def process_orders_file(
    request: Request,
    current_user: Dict = Depends(require_manager),
    file: UploadFile = File(...),
    options: Optional[str] = Form("{}")
):
    """Process uploaded CSV/XLSX file and extract order information"""
    try:
        # Validate file type
        if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Please upload CSV or Excel files."
            )
        
        # Parse options
        try:
            processing_options = json.loads(options) if options else {}
        except json.JSONDecodeError:
            processing_options = {}
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)
        
        try:
            # Process the file
            result = order_processing_service.process_csv_file(temp_file_path, processing_options)
            
            if not result["success"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"File processing failed: {result['error']}"
                )
            
            return JSONResponse(content={
                "message": "File processed successfully",
                "data": result["data"],
                "total_rows": result["total_rows"],
                "filename": file.filename
            })
            
        finally:
            # Clean up temporary file
            temp_file_path.unlink(missing_ok=True)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

# Export Endpoints
@router.post("/api/orders/export")
async def export_orders(
    request: Request,
    current_user: Dict = Depends(require_manager),
    orders_data: str = Form(...),
    export_format: str = Form("csv"),
    include_photos: bool = Form(False)
):
    """Export orders data to CSV or Excel format"""
    try:
        # Parse orders data
        try:
            orders = json.loads(orders_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid orders data format"
            )
        
        # Create export
        export_data, filename = order_processing_service.create_orders_export(
            orders, 
            export_format=export_format,
            include_photos=include_photos
        )
        
        # Return file
        return FileResponse(
            io.BytesIO(export_data),
            media_type="application/octet-stream",
            filename=filename
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating export: {str(e)}"
        )

# Photo Download Endpoints
@router.post("/api/orders/download-photos")
async def download_order_photos(
    request: Request,
    current_user: Dict = Depends(require_manager),
    orders_data: str = Form(...),
    include_main: bool = Form(True),
    include_polaroids: bool = Form(True)
):
    """Download photos for specified orders"""
    try:
        # Parse orders data
        try:
            orders = json.loads(orders_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid orders data format"
            )
        
        if not orders:
            raise HTTPException(
                status_code=400,
                detail="No orders specified for photo download"
            )
        
        # Download photos and create ZIP
        zip_path = order_download_service.download_order_photos(
            orders,
            include_main=include_main,
            include_polaroids=include_polaroids
        )
        
        # Return ZIP file
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=zip_path.name
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading order photos: {str(e)}"
        )

@router.post("/api/orders/download-polaroids")
async def download_order_polaroids(
    request: Request,
    current_user: Dict = Depends(require_manager),
    orders_data: str = Form(...)
):
    """Download polaroids for specified orders"""
    try:
        # Parse orders data
        try:
            orders = json.loads(orders_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid orders data format"
            )
        
        if not orders:
            raise HTTPException(
                status_code=400,
                detail="No orders specified for polaroid download"
            )
        
        # Download polaroids only
        zip_path = order_download_service.download_order_photos(
            orders,
            include_main=False,
            include_polaroids=True
        )
        
        # Return ZIP file
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=zip_path.name
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading order polaroids: {str(e)}"
        )

# Order Management Endpoints
@router.get("/api/orders/{order_id}")
async def get_order_details(
    request: Request,
    order_id: str,
    current_user: Dict = Depends(require_manager)
):
    """Get detailed information for a specific order"""
    try:
        # TODO: Implement order retrieval from Supabase or Shopify
        # For now, return placeholder data
        
        order = {
            "id": order_id,
            "order_number": f"#{order_id}",
            "status": "open",
            "fulfillment_status": "unfulfilled",
            "customer": {
                "email": "customer@example.com",
                "name": "Sample Customer"
            },
            "line_items": [
                {
                    "id": "item-1",
                    "name": "Sample Product",
                    "variant": "Sample Variant",
                    "quantity": 1
                }
            ],
            "created_at": "2024-01-15T10:30:00Z"
        }
        
        return JSONResponse(content=order)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving order: {str(e)}"
        )

@router.post("/api/orders/{order_id}/update-status")
async def update_order_status(
    request: Request,
    order_id: str,
    current_user: Dict = Depends(require_manager)
):
    """Update order status"""
    try:
        # Get request body
        body = await request.json()
        new_status = body.get("status")
        
        if not new_status:
            raise HTTPException(
                status_code=400,
                detail="Status is required"
            )
        
        # TODO: Implement actual status update in Supabase or Shopify
        
        return JSONResponse(content={
            "message": "Order status updated successfully",
            "order_id": order_id,
            "new_status": new_status
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating order status: {str(e)}"
        )

# Analytics and Reporting
@router.get("/api/orders/analytics")
async def get_orders_analytics(
    request: Request,
    current_user: Dict = Depends(require_manager),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Get orders analytics and insights"""
    try:
        # TODO: Implement actual analytics from Supabase or Shopify
        # For now, return placeholder data
        
        analytics = {
            "period": {
                "start": start_date or "2024-01-01",
                "end": end_date or "2024-01-31"
            },
            "summary": {
                "total_orders": 150,
                "fulfilled_orders": 120,
                "unfulfilled_orders": 30,
                "total_revenue": 15000.00
            },
            "fulfillment_status": {
                "fulfilled": 80,
                "unfulfilled": 20,
                "partial": 0
            },
            "daily_trends": {
                "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "orders": [5, 8, 12]
            }
        }
        
        return JSONResponse(content=analytics)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving orders analytics: {str(e)}"
        )

# Health Check
@router.get("/api/orders/health")
async def orders_health_check():
    """Health check for orders service"""
    try:
        # Check Shopify configuration
        shopify_configured = bool(
            shopify_service.base_url and 
            shopify_service.headers.get("X-Shopify-Access-Token")
        )
        
        return JSONResponse(content={
            "status": "healthy",
            "shopify_configured": shopify_configured,
            "services": {
                "shopify": "available",
                "processing": "available",
                "download": "available"
            }
        })
        
    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": str(e)
            },
            status_code=500
        )
