"""
Jobs service for file processing and job management
"""
import os
import uuid
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# TODO: Replace with proper database storage
JOBS: Dict[str, Dict[str, Any]] = {}

def create_job(file_path: Path, options: Dict[str, Any]) -> str:
    """Create a new job"""
    job_id = uuid.uuid4().hex[:12]
    
    JOBS[job_id] = {
        "id": job_id,
        "status": "pending",
        "progress": 0.0,
        "message": "Job created",
        "file_path": str(file_path),
        "options": options,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "zip_path": None,
        "error": None
    }
    
    return job_id

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job by ID"""
    return JOBS.get(job_id)

def update_job_status(job_id: str, status: str, progress: float = None, message: str = None, error: str = None):
    """Update job status"""
    if job_id in JOBS:
        JOBS[job_id]["status"] = status
        if progress is not None:
            JOBS[job_id]["progress"] = progress
        if message is not None:
            JOBS[job_id]["message"] = message
        if error is not None:
            JOBS[job_id]["error"] = error
            
        if status == "started":
            JOBS[job_id]["started_at"] = datetime.now().isoformat()
        elif status in ["completed", "error"]:
            JOBS[job_id]["completed_at"] = datetime.now().isoformat()

def run_job(job_id: str, csv_path: Path, job_dir: Path, options: Dict[str, Any]):
    """Run the actual job processing"""
    try:
        update_job_status(job_id, "started", 0.0, "Processing started")
        
        # TODO: Implement actual CSV processing logic
        # This is a placeholder that simulates processing
        
        # Simulate processing steps
        steps = [
            ("Reading CSV", 0.1),
            ("Processing orders", 0.3),
            ("Generating reports", 0.6),
            ("Creating ZIP", 0.9),
            ("Finalizing", 1.0)
        ]
        
        for step_name, progress in steps:
            time.sleep(1)  # Simulate work
            update_job_status(job_id, "processing", progress, f"Step: {step_name}")
        
        # Create a dummy ZIP file
        zip_path = job_dir / f"{options.get('zip_name', 'results')}.zip"
        zip_path.touch()  # Create empty file for now
        
        # Update job as completed
        JOBS[job_id]["zip_path"] = str(zip_path)
        update_job_status(job_id, "completed", 1.0, "Job completed successfully")
        
    except Exception as e:
        update_job_status(job_id, "error", 0.0, f"Error: {str(e)}", str(e))
        print(f"Job {job_id} failed: {e}")

def cleanup_old_jobs(max_age_hours: int = 24):
    """Clean up old completed jobs"""
    current_time = datetime.now()
    jobs_to_remove = []
    
    for job_id, job in JOBS.items():
        if job["status"] in ["completed", "error"]:
            if job["completed_at"]:
                completed_time = datetime.fromisoformat(job["completed_at"])
                age_hours = (current_time - completed_time).total_seconds() / 3600
                if age_hours > max_age_hours:
                    jobs_to_remove.append(job_id)
    
    for job_id in jobs_to_remove:
        # TODO: Clean up actual files
        del JOBS[job_id]
