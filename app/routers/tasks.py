"""
Tasks router for comprehensive task management, assignment, and reporting
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import json

from app.deps import require_employee
from app.services.tasks_service import (
    task_service, 
    TaskStatus, 
    TaskPriority, 
    TaskType
)

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Tasks management page"""
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "title": "Task Management",
        "header": "Task Management"
    })

@router.get("/task-board", response_class=HTMLResponse)
async def task_board_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Task board/Kanban view page"""
    return templates.TemplateResponse("task_board.html", {
        "request": request,
        "title": "Task Board",
        "header": "Task Board"
    })

# Task CRUD Operations
@router.post("/api/tasks")
async def create_task(
    request: Request,
    current_user: Dict = Depends(require_employee),
    task_data: Dict = Body(...)
):
    """Create a new task"""
    try:
        # Validate required fields
        required_fields = ["title", "description", "assigned_to", "task_type"]
        for field in required_fields:
            if field not in task_data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field}"
                )
        
        # Validate task type
        try:
            task_type = TaskType(task_data["task_type"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task type: {task_data['task_type']}"
            )
        
        # Validate priority
        priority = TaskPriority.MEDIUM
        if "priority" in task_data:
            try:
                priority = TaskPriority(task_data["priority"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid priority: {task_data['priority']}"
                )
        
        # Parse due date
        due_date = None
        if "due_date" in task_data and task_data["due_date"]:
            try:
                due_date = datetime.fromisoformat(task_data["due_date"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid due date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Create task
        result = task_service.create_task(
            title=task_data["title"],
            description=task_data["description"],
            assigned_to=task_data["assigned_to"],
            task_type=task_type,
            priority=priority,
            due_date=due_date,
            estimated_hours=task_data.get("estimated_hours"),
            order_id=task_data.get("order_id"),
            tags=task_data.get("tags", []),
            created_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task created successfully",
            "task": result["task"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating task: {str(e)}"
        )

@router.get("/api/tasks/{task_id}")
async def get_task(
    request: Request,
    task_id: str,
    current_user: Dict = Depends(require_employee)
):
    """Get a specific task by ID"""
    try:
        task = task_service.get_task(task_id)
        
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        
        return JSONResponse(content=task)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving task: {str(e)}"
        )

@router.get("/api/tasks")
async def get_tasks(
    request: Request,
    current_user: Dict = Depends(require_employee),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user"),
    status: Optional[str] = Query(None, description="Filter by status"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    due_date_min: Optional[str] = Query(None, description="Filter by minimum due date"),
    due_date_max: Optional[str] = Query(None, description="Filter by maximum due date"),
    limit: int = Query(100, description="Number of tasks to return"),
    offset: int = Query(0, description="Number of tasks to skip")
):
    """Get tasks with filtering and pagination"""
    try:
        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = TaskStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}"
                )
        
        # Parse task type filter
        type_filter = None
        if task_type:
            try:
                type_filter = TaskType(task_type)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid task type: {task_type}"
                )
        
        # Parse priority filter
        priority_filter = None
        if priority:
            try:
                priority_filter = TaskPriority(priority)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid priority: {priority}"
                )
        
        # Parse date filters
        due_date_min_filter = None
        due_date_max_filter = None
        
        if due_date_min:
            try:
                due_date_min_filter = datetime.fromisoformat(due_date_min)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid due_date_min format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        if due_date_max:
            try:
                due_date_max_filter = datetime.fromisoformat(due_date_max)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid due_date_max format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Get tasks
        result = task_service.get_tasks(
            assigned_to=assigned_to,
            status=status_filter,
            task_type=type_filter,
            priority=priority_filter,
            order_id=order_id,
            due_date_min=due_date_min_filter,
            due_date_max=due_date_max_filter,
            limit=limit,
            offset=offset
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving tasks: {str(e)}"
        )

@router.patch("/api/tasks/{task_id}")
async def update_task(
    request: Request,
    task_id: str,
    current_user: Dict = Depends(require_employee),
    updates: Dict = Body(...)
):
    """Update an existing task"""
    try:
        # Validate task exists
        existing_task = task_service.get_task(task_id)
        if not existing_task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        
        # Validate status update if provided
        if "status" in updates:
            try:
                TaskStatus(updates["status"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {updates['status']}"
                )
        
        # Validate priority update if provided
        if "priority" in updates:
            try:
                TaskPriority(updates["priority"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid priority: {updates['priority']}"
                )
        
        # Validate task type update if provided
        if "task_type" in updates:
            try:
                TaskType(updates["task_type"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid task type: {updates['task_type']}"
                )
        
        # Parse due date if provided
        if "due_date" in updates and updates["due_date"]:
            try:
                updates["due_date"] = datetime.fromisoformat(updates["due_date"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid due date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Update task
        result = task_service.update_task(
            task_id=task_id,
            updates=updates,
            updated_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task updated successfully",
            "task_id": task_id,
            "updates": result["updates"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating task: {str(e)}"
        )

@router.delete("/api/tasks/{task_id}")
async def delete_task(
    request: Request,
    task_id: str,
    current_user: Dict = Depends(require_employee)
):
    """Delete a task (soft delete)"""
    try:
        # Validate task exists
        existing_task = task_service.get_task(task_id)
        if not existing_task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        
        # Delete task
        result = task_service.delete_task(
            task_id=task_id,
            deleted_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task deleted successfully",
            "task_id": task_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting task: {str(e)}"
        )

# Task Assignment and Status Management
@router.post("/api/tasks/{task_id}/assign")
async def assign_task(
    request: Request,
    task_id: str,
    current_user: Dict = Depends(require_employee),
    assignment_data: Dict = Body(...)
):
    """Assign a task to a user"""
    try:
        if "assigned_to" not in assignment_data:
            raise HTTPException(
                status_code=400,
                detail="assigned_to field is required"
            )
        
        result = task_service.assign_task(
            task_id=task_id,
            assigned_to=assignment_data["assigned_to"],
            assigned_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task assigned successfully",
            "task_id": task_id,
            "assigned_to": assignment_data["assigned_to"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error assigning task: {str(e)}"
        )

@router.post("/api/tasks/{task_id}/status")
async def change_task_status(
    request: Request,
    task_id: str,
    current_user: Dict = Depends(require_employee),
    status_data: Dict = Body(...)
):
    """Change task status"""
    try:
        if "status" not in status_data:
            raise HTTPException(
                status_code=400,
                detail="status field is required"
            )
        
        # Validate status
        try:
            new_status = TaskStatus(status_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status_data['status']}"
            )
        
        result = task_service.change_task_status(
            task_id=task_id,
            new_status=new_status,
            changed_by=current_user.get("id"),
            notes=status_data.get("notes")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task status changed successfully",
            "task_id": task_id,
            "new_status": new_status.value
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error changing task status: {str(e)}"
        )

# Task Templates
@router.post("/api/task-templates")
async def create_task_template(
    request: Request,
    current_user: Dict = Depends(require_employee),
    template_data: Dict = Body(...)
):
    """Create a reusable task template"""
    try:
        # Validate required fields
        required_fields = ["name", "description", "task_type", "estimated_hours"]
        for field in required_fields:
            if field not in template_data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field}"
                )
        
        # Validate task type
        try:
            task_type = TaskType(template_data["task_type"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task type: {template_data['task_type']}"
            )
        
        # Create template
        result = task_service.create_task_template(
            name=template_data["name"],
            description=template_data["description"],
            task_type=task_type,
            estimated_hours=template_data["estimated_hours"],
            tags=template_data.get("tags", []),
            created_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task template created successfully",
            "template": result["template"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating task template: {str(e)}"
        )

@router.post("/api/task-templates/{template_id}/create-task")
async def create_task_from_template(
    request: Request,
    template_id: str,
    current_user: Dict = Depends(require_employee),
    task_data: Dict = Body(...)
):
    """Create a task from a template"""
    try:
        if "assigned_to" not in task_data:
            raise HTTPException(
                status_code=400,
                detail="assigned_to field is required"
            )
        
        # Parse due date if provided
        due_date = None
        if "due_date" in task_data and task_data["due_date"]:
            try:
                due_date = datetime.fromisoformat(task_data["due_date"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid due date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Create task from template
        result = task_service.create_task_from_template(
            template_id=template_id,
            assigned_to=task_data["assigned_to"],
            due_date=due_date,
            order_id=task_data.get("order_id"),
            created_by=current_user.get("id")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content={
            "message": "Task created from template successfully",
            "task": result["task"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating task from template: {str(e)}"
        )

# Analytics and Reporting
@router.get("/api/tasks/statistics")
async def get_task_statistics(
    request: Request,
    current_user: Dict = Depends(require_employee),
    user_id: Optional[str] = Query(None, description="Filter statistics by user"),
    start_date: Optional[str] = Query(None, description="Start date for statistics"),
    end_date: Optional[str] = Query(None, description="End date for statistics")
):
    """Get task statistics and metrics"""
    try:
        # Parse date range if provided
        date_range = None
        if start_date and end_date:
            try:
                start = datetime.fromisoformat(start_date)
                end = datetime.fromisoformat(end_date)
                date_range = (start, end)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Get statistics
        result = task_service.get_task_statistics(
            user_id=user_id,
            date_range=date_range
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        return JSONResponse(content=result["statistics"])
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving task statistics: {str(e)}"
        )

# Task Board/Kanban Data
@router.get("/api/tasks/board")
async def get_task_board_data(
    request: Request,
    current_user: Dict = Depends(require_employee),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user")
):
    """Get task board data organized by status"""
    try:
        # Get all tasks for the board
        result = task_service.get_tasks(
            assigned_to=assigned_to,
            limit=1000  # Get more tasks for board view
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
        
        # Organize tasks by status
        board_data = {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "cancelled": [],
            "on_hold": []
        }
        
        for task in result["tasks"]:
            status = task.get("status", "pending")
            if status in board_data:
                board_data[status].append(task)
        
        return JSONResponse(content={
            "board": board_data,
            "total_tasks": result["total"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving task board data: {str(e)}"
        )

# Health Check
@router.get("/api/tasks/health")
async def tasks_health_check():
    """Health check for tasks service"""
    try:
        # Test basic functionality
        test_result = task_service.get_tasks(limit=1)
        
        return JSONResponse(content={
            "status": "healthy",
            "service": "tasks",
            "basic_functionality": test_result["success"]
        })
        
    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy",
                "service": "tasks",
                "error": str(e)
            },
            status_code=500
        )
