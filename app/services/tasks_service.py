"""
Tasks service for managing task creation, assignment, tracking, and management
"""
import os
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import uuid

from app.services import supa

class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"

class TaskPriority(str, Enum):
    """Task priority enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskType(str, Enum):
    """Task type enumeration"""
    ORDER_PROCESSING = "order_processing"
    PHOTO_EDITING = "photo_editing"
    QUALITY_CHECK = "quality_check"
    PACKING = "packing"
    SHIPPING = "shipping"
    CUSTOMER_SERVICE = "customer_service"
    MAINTENANCE = "maintenance"
    OTHER = "other"

class TaskService:
    """Service for managing tasks and task-related operations"""
    
    def __init__(self):
        self.supabase = supa.supabase
    
    def create_task(
        self,
        title: str,
        description: str,
        assigned_to: str,
        task_type: TaskType,
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_date: Optional[datetime] = None,
        estimated_hours: Optional[float] = None,
        order_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        created_by: str = None
    ) -> Dict[str, Any]:
        """Create a new task"""
        try:
            task_data = {
                "id": str(uuid.uuid4()),
                "title": title,
                "description": description,
                "assigned_to": assigned_to,
                "task_type": task_type.value,
                "priority": priority.value,
                "status": TaskStatus.PENDING.value,
                "due_date": due_date.isoformat() if due_date else None,
                "estimated_hours": estimated_hours,
                "order_id": order_id,
                "tags": tags or [],
                "created_by": created_by,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # TODO: Store in Supabase tasks table
            # For now, return the task data
            return {
                "success": True,
                "task": task_data,
                "message": "Task created successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to create task"
            }
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific task by ID"""
        try:
            # TODO: Retrieve from Supabase
            # For now, return placeholder data
            return {
                "id": task_id,
                "title": "Sample Task",
                "description": "This is a sample task description",
                "assigned_to": "user123",
                "task_type": TaskType.ORDER_PROCESSING.value,
                "priority": TaskPriority.MEDIUM.value,
                "status": TaskStatus.PENDING.value,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            print(f"Error retrieving task {task_id}: {e}")
            return None
    
    def get_tasks(
        self,
        assigned_to: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        priority: Optional[TaskPriority] = None,
        order_id: Optional[str] = None,
        due_date_min: Optional[datetime] = None,
        due_date_max: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get tasks with filtering and pagination"""
        try:
            # TODO: Implement Supabase query with filters
            # For now, return placeholder data
            
            filters = {
                "assigned_to": assigned_to,
                "status": status.value if status else None,
                "task_type": task_type.value if task_type else None,
                "priority": priority.value if priority else None,
                "order_id": order_id,
                "due_date_min": due_date_min.isoformat() if due_date_min else None,
                "due_date_max": due_date_max.isoformat() if due_date_max else None
            }
            
            # Filter out None values
            filters = {k: v for k, v in filters.items() if v is not None}
            
            # Placeholder tasks
            tasks = [
                {
                    "id": "task-1",
                    "title": "Process Order #12345",
                    "description": "Review and process customer order",
                    "assigned_to": "user123",
                    "task_type": TaskType.ORDER_PROCESSING.value,
                    "priority": TaskPriority.HIGH.value,
                    "status": TaskStatus.IN_PROGRESS.value,
                    "due_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
                    "estimated_hours": 2.0,
                    "order_id": "order-12345",
                    "tags": ["urgent", "customer-facing"],
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                },
                {
                    "id": "task-2",
                    "title": "Quality Check Photos",
                    "description": "Review photo quality for order #12346",
                    "assigned_to": "user456",
                    "task_type": TaskType.QUALITY_CHECK.value,
                    "priority": TaskPriority.MEDIUM.value,
                    "status": TaskStatus.PENDING.value,
                    "due_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                    "estimated_hours": 1.5,
                    "order_id": "order-12346",
                    "tags": ["quality", "photos"],
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            ]
            
            return {
                "success": True,
                "tasks": tasks,
                "total": len(tasks),
                "filters": filters,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": False
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tasks": [],
                "total": 0
            }
    
    def update_task(
        self,
        task_id: str,
        updates: Dict[str, Any],
        updated_by: str = None
    ) -> Dict[str, Any]:
        """Update an existing task"""
        try:
            # Validate updates
            allowed_fields = {
                "title", "description", "assigned_to", "task_type", 
                "priority", "status", "due_date", "estimated_hours",
                "order_id", "tags", "notes", "completed_at"
            }
            
            invalid_fields = set(updates.keys()) - allowed_fields
            if invalid_fields:
                return {
                    "success": False,
                    "error": f"Invalid fields: {', '.join(invalid_fields)}",
                    "message": "Update failed"
                }
            
            # Add metadata
            updates["updated_at"] = datetime.utcnow().isoformat()
            if updated_by:
                updates["updated_by"] = updated_by
            
            # Handle special cases
            if "status" in updates and updates["status"] == TaskStatus.COMPLETED.value:
                updates["completed_at"] = datetime.utcnow().isoformat()
            
            # TODO: Update in Supabase
            # For now, return success
            
            return {
                "success": True,
                "task_id": task_id,
                "updates": updates,
                "message": "Task updated successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update task"
            }
    
    def delete_task(self, task_id: str, deleted_by: str = None) -> Dict[str, Any]:
        """Delete a task (soft delete)"""
        try:
            # TODO: Implement soft delete in Supabase
            # For now, return success
            
            return {
                "success": True,
                "task_id": task_id,
                "message": "Task deleted successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to delete task"
            }
    
    def assign_task(self, task_id: str, assigned_to: str, assigned_by: str = None) -> Dict[str, Any]:
        """Assign a task to a user"""
        try:
            updates = {
                "assigned_to": assigned_to,
                "assigned_at": datetime.utcnow().isoformat()
            }
            
            if assigned_by:
                updates["assigned_by"] = assigned_by
            
            return self.update_task(task_id, updates, assigned_by)
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to assign task"
            }
    
    def change_task_status(
        self, 
        task_id: str, 
        new_status: TaskStatus, 
        changed_by: str = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Change task status"""
        try:
            updates = {
                "status": new_status.value,
                "status_changed_at": datetime.utcnow().isoformat()
            }
            
            if changed_by:
                updates["status_changed_by"] = changed_by
            
            if notes:
                updates["notes"] = notes
            
            # Handle completion
            if new_status == TaskStatus.COMPLETED:
                updates["completed_at"] = datetime.utcnow().isoformat()
            
            return self.update_task(task_id, updates, changed_by)
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to change task status"
            }
    
    def get_task_statistics(
        self,
        user_id: Optional[str] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None
    ) -> Dict[str, Any]:
        """Get task statistics and metrics"""
        try:
            # TODO: Implement actual statistics from Supabase
            # For now, return placeholder data
            
            stats = {
                "total_tasks": 150,
                "pending_tasks": 45,
                "in_progress_tasks": 30,
                "completed_tasks": 70,
                "cancelled_tasks": 5,
                "overdue_tasks": 8,
                "completion_rate": 0.47,  # 70/150
                "average_completion_time": 2.5,  # days
                "tasks_by_priority": {
                    "low": 20,
                    "medium": 80,
                    "high": 35,
                    "urgent": 15
                },
                "tasks_by_type": {
                    "order_processing": 60,
                    "photo_editing": 30,
                    "quality_check": 25,
                    "packing": 20,
                    "shipping": 10,
                    "other": 5
                }
            }
            
            if user_id:
                # Filter by user
                stats["user_specific"] = {
                    "assigned_tasks": 25,
                    "completed_tasks": 15,
                    "pending_tasks": 10
                }
            
            if date_range:
                start_date, end_date = date_range
                stats["date_range"] = {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "tasks_in_range": 45
                }
            
            return {
                "success": True,
                "statistics": stats
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "statistics": {}
            }
    
    def create_task_template(
        self,
        name: str,
        description: str,
        task_type: TaskType,
        estimated_hours: float,
        tags: Optional[List[str]] = None,
        created_by: str = None
    ) -> Dict[str, Any]:
        """Create a reusable task template"""
        try:
            template_data = {
                "id": str(uuid.uuid4()),
                "name": name,
                "description": description,
                "task_type": task_type.value,
                "estimated_hours": estimated_hours,
                "tags": tags or [],
                "created_by": created_by,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            }
            
            # TODO: Store in Supabase task_templates table
            
            return {
                "success": True,
                "template": template_data,
                "message": "Task template created successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to create task template"
            }
    
    def create_task_from_template(
        self,
        template_id: str,
        assigned_to: str,
        due_date: Optional[datetime] = None,
        order_id: Optional[str] = None,
        created_by: str = None
    ) -> Dict[str, Any]:
        """Create a task from a template"""
        try:
            # TODO: Retrieve template from Supabase
            # For now, use placeholder template
            
            template = {
                "name": "Sample Template",
                "description": "Sample task description",
                "task_type": TaskType.ORDER_PROCESSING.value,
                "estimated_hours": 2.0
            }
            
            # Create task from template
            task_data = {
                "title": template["name"],
                "description": template["description"],
                "assigned_to": assigned_to,
                "task_type": template["task_type"],
                "priority": TaskPriority.MEDIUM.value,
                "estimated_hours": template["estimated_hours"],
                "due_date": due_date.isoformat() if due_date else None,
                "order_id": order_id,
                "template_id": template_id,
                "created_by": created_by
            }
            
            return self.create_task(**task_data)
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to create task from template"
            }

# Global service instance
task_service = TaskService()
