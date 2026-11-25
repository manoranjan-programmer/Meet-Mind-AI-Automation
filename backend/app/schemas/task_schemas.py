from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class TaskBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = ""
    assigned_member_id: Optional[str] = None
    priority: str = Field("Medium", description="Low, Medium, High, or Critical")
    deadline: Optional[str] = None
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = "Ad-hoc / Manual Task"
    required_skills: List[str] = Field(default_factory=list)

class TaskCreateRequest(TaskBase):
    task_id: Optional[str] = None
    approval_status: Optional[str] = "Awaiting Approval"

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_member_id: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None
    approval_status: Optional[str] = None
    meeting_title: Optional[str] = None
    required_skills: Optional[List[str]] = None

class TaskStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="To Do, In Progress, Review, or Completed")
    order: Optional[int] = Field(None, description="Optional column sort order for drag-and-drop reordering")
    trigger_automation: bool = Field(True, description="Whether explicit completion should dispatch Zapier webhook")

class TaskResponse(BaseModel):
    id: Optional[str] = None
    task_id: str
    team_id: str
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = "General"
    title: str
    description: Optional[str] = ""
    created_by: Optional[str] = None
    created_by_id: Optional[str] = None
    assigned_by_id: Optional[str] = None
    assigned_member_id: Optional[str] = None
    assigned_member_name: Optional[str] = "Unassigned"
    assigned_member_role: Optional[str] = "Unassigned"
    assigned_member_email: Optional[str] = ""
    priority: str = "Medium"
    deadline: Optional[str] = None
    status: str = "To Do"  # To Do, In Progress, Review, Completed
    approval_status: str = "Awaiting Approval"
    order: Optional[int] = 0
    required_skills: List[str] = Field(default_factory=list)
    confidence_score: Optional[float] = 1.0
    assignment_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class TaskCountsResponse(BaseModel):
    todo: int = 0
    in_progress: int = 0
    review: int = 0
    completed: int = 0
    awaiting_approval: int = 0
    total: int = 0

class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    counts: TaskCountsResponse
    meetings: List[str] = Field(default_factory=list)
