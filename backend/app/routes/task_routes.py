from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.middleware.auth import get_current_user
from app.services.task_service import TaskService
from app.schemas.task_schemas import (
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskStatusUpdateRequest,
    TaskResponse,
    TaskListResponse
)

router = APIRouter(prefix="/tasks", tags=["Task Management"])

@router.get("", response_model=TaskListResponse)
def get_tasks(
    status: Optional[str] = Query(None, description="Filter by status: To Do, In Progress, Review, Completed"),
    priority: Optional[str] = Query(None, description="Filter by priority: Low, Medium, High, Critical"),
    assigned_member_id: Optional[str] = Query(None, description="Filter by member_id"),
    meeting_id: Optional[str] = Query(None, description="Filter by meeting_id"),
    approval_status: Optional[str] = Query(None, description="Filter by approval_status: Approved, Awaiting Approval, Rejected"),
    search: Optional[str] = Query(None, description="Search in title or description"),
    view_mode: Optional[str] = Query(None, description="'all' or 'my'"),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve tasks for authenticated user's team.
    Supports status, priority, member, and meeting filters.
    """
    team_id = current_user["team_id"]
    return TaskService.list_tasks(
        team_id=team_id,
        current_user=current_user,
        status=status,
        priority=priority,
        assigned_member_id=assigned_member_id,
        meeting_id=meeting_id,
        approval_status=approval_status,
        search=search,
        view_mode=view_mode
    )

def check_not_viewer(user: dict):
    role = str(user.get("role", "")).lower()
    if role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Viewers have read-only access and cannot create, modify, or approve tasks."
        )

@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    req: TaskCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a task awaiting Team Leader approval in MongoDB Atlas.
    """
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    return TaskService.create_task(team_id=team_id, current_user=current_user, req=req)

@router.get("/{task_id}", response_model=TaskResponse)
def get_task_details(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve full task details with team-level and role-based data isolation."""
    team_id = current_user["team_id"]
    return TaskService.get_task(team_id=team_id, task_id=task_id, current_user=current_user)

@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: str,
    req: TaskStatusUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update status for Kanban column transitions.
    Allowed for Administrators and assigned team members.
    """
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    return TaskService.update_task_status(
        team_id=team_id,
        task_id=task_id,
        current_user=current_user,
        new_status=req.status,
        order=req.order,
        trigger_automation=req.trigger_automation,
    )

@router.patch("/{task_id}", response_model=TaskResponse)
def update_task_details(
    task_id: str,
    req: TaskUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Edit permitted task details.
    Admins can reassign members and change all metadata; members can update their own task notes.
    """
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    return TaskService.update_task(
        team_id=team_id,
        task_id=task_id,
        current_user=current_user,
        req=req
    )

@router.post("/{task_id}/approve", response_model=TaskResponse)
def approve_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Team Leader Approval:
    Transitions task from 'Awaiting Approval' to 'Approved',
    updates member assigned_tasks in MongoDB, and triggers Zapier task_approved webhook (ZAP 1).
    """
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    return TaskService.approve_task(team_id=team_id, task_id=task_id, current_user=current_user)

@router.post("/{task_id}/reject", response_model=TaskResponse)
def reject_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejects an AI recommended task."""
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    return TaskService.reject_task(team_id=team_id, task_id=task_id, current_user=current_user)

@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete task from MongoDB Atlas.
    Restricted to authorized Administrators.
    """
    check_not_viewer(current_user)
    team_id = current_user["team_id"]
    TaskService.delete_task(team_id=team_id, task_id=task_id, current_user=current_user)
    return {"success": True, "message": f"Task '{task_id}' deleted successfully."}
