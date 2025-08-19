"""
Jobs router for file processing and job management
"""
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any
from pathlib import Path
import threading

from app.deps import require_manager
from app.services import jobs_service

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.post("/api/process")
async def api_process(
    file: UploadFile = UploadFile(...),
    order_prefix: str = Form("#ER"),
    max_threads: int = Form(8),
    retry_total: int = Form(3),
    backoff_factor: float = Form(0.6),
    timeout_sec: int = Form(15),
    include_per_product_csv: bool = Form(True),
    include_back_messages_csv: bool = Form(True),
    zip_name: str = Form("results"),
):
    """Process uploaded CSV file"""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    # Create job directory
    job_id = jobs_service.create_job(csv_path, options)
    job_dir = Path(".") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded file
    csv_path = job_dir / file.filename
    with open(csv_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Prepare job options
    options = {
        "order_prefix": order_prefix or "#ER",
        "max_threads": max(1, min(int(max_threads), 32)),
        "retry_total": max(0, int(retry_total)),
        "backoff_factor": float(backoff_factor),
        "timeout_sec": max(3, int(timeout_sec)),
        "include_per_product_csv": bool(include_per_product_csv),
        "include_back_messages_csv": bool(include_back_messages_csv),
        "zip_name": zip_name.strip() or "results",
    }

    # Start job in background thread
    t = threading.Thread(
        target=jobs_service.run_job, 
        args=(job_id, csv_path, job_dir, options), 
        daemon=True
    )
    t.start()
    
    return {"job_id": job_id}

@router.get("/api/status/{job_id}")
def api_status(job_id: str):
    """Get job status"""
    job = jobs_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/api/download/{job_id}")
def api_download(job_id: str):
    """Download processed results"""
    job = jobs_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != "completed" or not job["zip_path"]:
        raise HTTPException(status_code=400, detail="Job not finished yet")
    
    zip_path = Path(job["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP file not found")
    
    return FileResponse(
        zip_path, 
        media_type="application/zip", 
        filename=zip_path.name
    )
