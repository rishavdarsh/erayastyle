"""
Packing management router for order processing
"""
import os
import tempfile
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from app.utils.csv_utils import parse_file_content, detect_columns, get_status_heuristics

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/packing", response_class=HTMLResponse)
async def packing_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Packing management page"""
    return templates.TemplateResponse("packing.html", {
        "request": request,
        "title": "Packing Management",
        "header": "Packing Management"
    })

@router.post("/api/packing/preview")
async def packing_preview(file: UploadFile = File(...)):
    """
    Preview CSV/XLSX file content for packing management
    """
    try:
        print(f"🔧 Processing file: {file.filename}, size: {file.size}")
        
        # Read file content
        file_content = await file.read()
        print(f"📁 File content read, length: {len(file_content)} bytes")
        
        # Parse file content
        result = parse_file_content(file_content, file.filename)
        if not result:
            raise ValueError("Failed to parse file")
        
        columns, rows, detected = result
        
        print(f"✅ File parsed successfully: {len(columns)} columns, {len(rows)} rows")
        
        # Detect image link columns
        image_link_columns = detect_image_link_columns(columns, rows)
        print(f"🖼️ Detected image link columns: {image_link_columns}")
        
        # Apply status heuristics to rows
        if rows:
            for row in rows:
                status_info = get_status_heuristics(row, detected)
                row.update(status_info)
        
        response_data = {
            "success": True,
            "data": {
                "columns": columns,
                "rows": rows,
                "detected_columns": detected,
                "image_link_columns": image_link_columns,
                "total_rows": len(rows),
                "preview_limit": 2000
            }
        }
        
        print(f"📤 Sending response: {len(rows)} rows, {len(columns)} columns")
        print(f"🔍 Detected columns: {detected}")
        print(f"🖼️ Image link columns: {image_link_columns}")
        
        return JSONResponse(content=response_data)
        
    except ValueError as e:
        print(f"❌ ValueError in packing preview: {e}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )
    except Exception as e:
        print(f"❌ Unexpected error in packing preview: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

def detect_image_link_columns(columns: List[str], rows: List[Dict[str, Any]]) -> List[str]:
    """
    Detect columns that contain image links based on:
    1. Known column names
    2. URL pattern analysis of column values
    """
    image_link_columns = []
    
    # Known image link column names (case and space insensitive)
    known_image_names = [
        "main photo link", "photo link", "image link", "image url", 
        "main photo url", "photo url", "polaroid link(s)", 
        "polaroid links", "polaroid link"
    ]
    
    for col in columns:
        col_lower = col.lower().replace(" ", "")
        
        # Check if column name matches known patterns
        is_known_image_column = any(
            known_name.replace(" ", "") in col_lower 
            for known_name in known_image_names
        )
        
        if is_known_image_column:
            image_link_columns.append(col)
            continue
        
        # Analyze column values for URL patterns
        if len(rows) > 0:
            url_count = 0
            non_empty_count = 0
            
            for row in rows:
                value = str(row.get(col, "")).strip()
                if value and value.lower() not in ['na', 'n/a', 'null', 'none', '']:
                    non_empty_count += 1
                    
                    # Check if value contains URLs
                    urls = extract_urls_from_text(value)
                    if urls:
                        url_count += 1
            
            # If ≥60% of non-empty values contain URLs, treat as image column
            if non_empty_count > 0 and (url_count / non_empty_count) >= 0.6:
                image_link_columns.append(col)
                print(f"🔍 Column '{col}' detected as image link column: {url_count}/{non_empty_count} values contain URLs")
    
    return image_link_columns

def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract URLs from text that may contain multiple URLs separated by various delimiters
    """
    import re
    
    # Split on common delimiters: comma, semicolon, newline, space
    parts = re.split(r'[,;\n\r\s]+', text)
    
    urls = []
    for part in parts:
        part = part.strip()
        if part:
            # Check if it looks like a URL
            if is_likely_url(part):
                urls.append(part)
    
    return urls

def is_likely_url(text: str) -> bool:
    """
    Check if text looks like a URL
    """
    # Must start with http or https
    if not (text.startswith('http://') or text.startswith('https://')):
        return False
    
    # Common image extensions (optional - many signed URLs don't have extensions)
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
    
    # If it has an extension, it should be an image extension
    if '.' in text:
        extension = text.lower().split('.')[-1]
        if extension in ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff']:
            return True
    
    # If no extension but starts with http(s), still consider it a URL
    # (many CDN/signed URLs don't have extensions)
    return True

@router.get("/api/packing/export")
async def packing_export(
    fmt: str = Query("csv", description="Export format"),
    filter_order: Optional[str] = Query(None, description="Filter by order number"),
    filter_product: Optional[str] = Query(None, description="Filter by product name"),
    filter_variant: Optional[str] = Query(None, description="Filter by variant"),
    filter_status: Optional[str] = Query(None, description="Filter by status"),
    filter_sku: Optional[str] = Query(None, description="Filter by SKU"),
    filter_packer: Optional[str] = Query(None, description="Filter by packer")
):
    """Export filtered packing data to CSV"""
    try:
        # For now, return a placeholder response
        # In a real implementation, you would:
        # 1. Get the current data from the client's stored rows
        # 2. Apply filters
        # 3. Generate CSV
        
        if fmt.lower() != "csv":
            return JSONResponse(
                content={"success": False, "error": "Only CSV export is supported"},
                status_code=400
            )
        
        # Placeholder CSV content
        csv_content = "Order Number,Product Name,Variant,Status\n"
        csv_content += "ER1059904,Couple Per...,Gold,OK\n"
        csv_content += "ER1059905,Personalize...,Gold,Missing photo\n"
        
        # Create streaming response
        def generate_csv():
            yield csv_content
        
        response = StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=\"packing_filtered.csv\"",
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
        return response
        
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": f"Export failed: {str(e)}"},
            status_code=500
        )
