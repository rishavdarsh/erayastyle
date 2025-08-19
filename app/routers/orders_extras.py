"""
Orders extras router for photo and polaroid downloads
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any, List
import os
import zipfile
import tempfile
from pathlib import Path
import requests
from datetime import datetime

from app.deps import require_manager
from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.post("/api/orders/download-photos")
async def download_order_photos(
    request: Request,
    current_user: Dict = Depends(require_manager),
    order_ids: List[str] = Form(...),
    include_main: bool = Form(True),
    include_polaroids: bool = Form(True),
    zip_name: str = Form("order_photos")
):
    """Download photos for specified orders"""
    try:
        # TODO: Implement actual photo download from Supabase/Shopify
        # For now, return placeholder response
        
        if not order_ids:
            raise HTTPException(status_code=400, detail="No order IDs provided")
        
        # Validate order IDs
        valid_orders = []
        for order_id in order_ids:
            # TODO: Check if order exists in Supabase
            # order = supa.get_order(order_id)
            # if not order:
            #     continue
            valid_orders.append(order_id)
        
        if not valid_orders:
            raise HTTPException(status_code=400, detail="No valid order IDs found")
        
        # TODO: Download actual photos from URLs
        # For now, create a placeholder ZIP file
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create ZIP file
            zip_path = temp_path / f"{zip_name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                # Add placeholder files for each order
                for order_id in valid_orders:
                    # Add main photo placeholder
                    if include_main:
                        main_photo_path = temp_path / f"{order_id}_main.txt"
                        main_photo_path.write_text(f"Main photo for order {order_id}")
                        zip_file.write(main_photo_path, f"{order_id}/main_photo.txt")
                    
                    # Add polaroids placeholder
                    if include_polaroids:
                        polaroid_path = temp_path / f"{order_id}_polaroids.txt"
                        polaroid_path.write_text(f"Polaroids for order {order_id}")
                        zip_file.write(polaroid_path, f"{order_id}/polaroids.txt")
            
            # Return ZIP file
            return FileResponse(
                zip_path,
                media_type="application/zip",
                filename=f"{zip_name}.zip"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading order photos: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to download order photos"
        )

@router.post("/api/orders/download-polaroids")
async def download_order_polaroids(
    request: Request,
    current_user: Dict = Depends(require_manager),
    order_ids: List[str] = Form(...),
    zip_name: str = Form("order_polaroids")
):
    """Download polaroids for specified orders"""
    try:
        # TODO: Implement actual polaroid download from Supabase/Shopify
        # For now, return placeholder response
        
        if not order_ids:
            raise HTTPException(status_code=400, detail="No order IDs provided")
        
        # Validate order IDs
        valid_orders = []
        for order_id in order_ids:
            # TODO: Check if order exists in Supabase
            # order = supa.get_order(order_id)
            # if not order:
            #     continue
            valid_orders.append(order_id)
        
        if not valid_orders:
            raise HTTPException(status_code=400, detail="No valid order IDs found")
        
        # TODO: Download actual polaroids from URLs
        # For now, create a placeholder ZIP file
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create ZIP file
            zip_path = temp_path / f"{zip_name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                # Add placeholder files for each order
                for order_id in valid_orders:
                    # Add polaroids placeholder
                    polaroid_path = temp_path / f"{order_id}_polaroids.txt"
                    polaroid_path.write_text(f"Polaroids for order {order_id}")
                    zip_file.write(polaroid_path, f"{order_id}/polaroids.txt")
            
            # Return ZIP file
            return FileResponse(
                zip_path,
                media_type="application/zip",
                filename=f"{zip_name}.zip"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading order polaroids: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to download order polaroids"
        )

@router.get("/api/orders/{order_id}/photos")
async def get_order_photos(
    request: Request,
    order_id: str,
    current_user: Dict = Depends(require_manager)
):
    """Get photo information for a specific order"""
    try:
        # TODO: Implement actual photo retrieval from Supabase/Shopify
        # For now, return placeholder data
        
        # TODO: Check if order exists
        # order = supa.get_order(order_id)
        # if not order:
        #     raise HTTPException(status_code=404, detail="Order not found")
        
        # Placeholder response
        photos = {
            "order_id": order_id,
            "main_photo": {
                "url": f"https://example.com/photos/{order_id}/main.jpg",
                "status": "available",
                "size": "2.5MB"
            },
            "polaroids": [
                {
                    "id": "pol-1",
                    "url": f"https://example.com/photos/{order_id}/polaroid1.jpg",
                    "status": "available",
                    "size": "1.8MB"
                },
                {
                    "id": "pol-2",
                    "url": f"https://example.com/photos/{order_id}/polaroid2.jpg",
                    "status": "available",
                    "size": "1.9MB"
                }
            ],
            "total_count": 3,
            "total_size": "6.2MB"
        }
        
        return JSONResponse(content=photos)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting order photos: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve order photos"
        )

@router.post("/api/orders/{order_id}/photos/refresh")
async def refresh_order_photos(
    request: Request,
    order_id: str,
    current_user: Dict = Depends(require_manager)
):
    """Refresh photos for a specific order"""
    try:
        # TODO: Implement actual photo refresh from Shopify
        # For now, return placeholder response
        
        # TODO: Check if order exists
        # order = supa.get_order(order_id)
        # if not order:
        #     raise HTTPException(status_code=404, detail="Order not found")
        
        # TODO: Fetch latest photos from Shopify
        # result = supa.refresh_order_photos(order_id)
        
        return JSONResponse(content={
            "message": "Order photos refreshed successfully",
            "order_id": order_id,
            "timestamp": datetime.now().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error refreshing order photos: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh order photos"
        )
