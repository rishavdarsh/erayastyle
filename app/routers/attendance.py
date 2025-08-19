"""
Attendance router for employee check-in/out and reporting
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any
from datetime import datetime, date
import json

from app.deps import require_employee
from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/attendance", response_class=HTMLResponse)
async def attendance_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Attendance management page"""
    return templates.TemplateResponse("attendance.html", {
        "request": request,
        "title": "Employee Attendance",
        "header": "Employee Attendance"
    })

@router.post("/api/attendance/check_in")
async def check_in(
    request: Request,
    current_user: Dict = Depends(require_employee)
):
    """Check in employee"""
    try:
        user_id = current_user["id"]
        current_time = datetime.now()
        
        # TODO: Implement actual attendance tracking in Supabase
        # For now, we'll use a placeholder approach
        
        # Check if already checked in today
        # attendance_record = supa.get_today_attendance(user_id)
        # if attendance_record and not attendance_record.get("check_out"):
        #     raise HTTPException(status_code=400, detail="Already checked in today")
        
        # Create check-in record
        # record_data = {
        #     "user_id": user_id,
        #     "check_in": current_time.isoformat(),
        #     "date": current_time.date().isoformat(),
        #     "status": "present"
        # }
        # result = supa.create_attendance_record(record_data)
        
        # Placeholder response for now
        return JSONResponse(content={
            "message": "Check-in successful",
            "user_id": user_id,
            "check_in_time": current_time.isoformat(),
            "date": current_time.date().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Check-in error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Check-in failed. Please try again."
        )

@router.post("/api/attendance/check_out")
async def check_out(
    request: Request,
    current_user: Dict = Depends(require_employee)
):
    """Check out employee"""
    try:
        user_id = current_user["id"]
        current_time = datetime.now()
        
        # TODO: Implement actual attendance tracking in Supabase
        # For now, we'll use a placeholder approach
        
        # Check if checked in today
        # attendance_record = supa.get_today_attendance(user_id)
        # if not attendance_record or attendance_record.get("check_out"):
        #     raise HTTPException(status_code=400, detail="No active check-in found")
        
        # Update check-out record
        # result = supa.update_attendance_record(attendance_record["id"], {
        #     "check_out": current_time.isoformat(),
        #     "total_hours": calculate_hours(attendance_record["check_in"], current_time)
        # })
        
        # Placeholder response for now
        return JSONResponse(content={
            "message": "Check-out successful",
            "user_id": user_id,
            "check_out_time": current_time.isoformat(),
            "date": current_time.date().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Check-out error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Check-out failed. Please try again."
        )

@router.get("/api/attendance/records")
async def get_attendance_records(
    request: Request,
    current_user: Dict = Depends(require_employee),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None
):
    """Get attendance records"""
    try:
        # TODO: Implement actual attendance records from Supabase
        # For now, return placeholder data
        
        # Only allow users to see their own records unless they're admin/manager
        if user_id and user_id != current_user["id"]:
            if current_user["role"].lower() not in ["owner", "admin", "manager"]:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Placeholder response
        records = [
            {
                "id": "1",
                "user_id": current_user["id"],
                "user_name": current_user["name"],
                "date": "2024-01-15",
                "check_in": "09:00:00",
                "check_out": "17:00:00",
                "total_hours": 8.0,
                "status": "present"
            }
        ]
        
        return JSONResponse(content={
            "records": records,
            "total": len(records)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting attendance records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve attendance records"
        )

@router.get("/api/attendance/report")
async def get_attendance_report(
    request: Request,
    current_user: Dict = Depends(require_employee),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None
):
    """Get attendance report"""
    try:
        # TODO: Implement actual attendance reporting from Supabase
        # For now, return placeholder data
        
        # Only allow users to see their own reports unless they're admin/manager
        if user_id and user_id != current_user["id"]:
            if current_user["role"].lower() not in ["owner", "admin", "manager"]:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Placeholder response
        report = {
            "period": {
                "start": start_date or "2024-01-01",
                "end": end_date or "2024-01-31"
            },
            "summary": {
                "total_days": 31,
                "present_days": 28,
                "absent_days": 2,
                "late_days": 1,
                "total_hours": 224.0
            },
            "details": [
                {
                    "date": "2024-01-15",
                    "status": "present",
                    "check_in": "09:00:00",
                    "check_out": "17:00:00",
                    "hours": 8.0
                }
            ]
        }
        
        return JSONResponse(content=report)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting attendance report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate attendance report"
        )

@router.get("/attendance/report_page", response_class=HTMLResponse)
async def attendance_report_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Attendance report page"""
    return templates.TemplateResponse("attendance_report.html", {
        "request": request,
        "title": "Attendance Report",
        "header": "Attendance Report"
    })
