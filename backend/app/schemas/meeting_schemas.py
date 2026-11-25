from pydantic import BaseModel, Field
from typing import List, Optional, Any, Union, Dict
from datetime import datetime

class ParticipantDetail(BaseModel):
    member_id: str
    name: str
    email: Optional[str] = ""
    role: Optional[str] = "Member"

class MeetingStartRequest(BaseModel):
    meeting_title: str = Field(..., min_length=2, max_length=200)
    selected_participant_ids: List[str] = Field(default_factory=list)
    participants: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class MeetingCompleteRequest(BaseModel):
    meeting_id: Optional[str] = None
    meeting_title: str = Field(..., min_length=2, max_length=200)
    duration: Optional[str] = "00:00"
    participants: Optional[Union[List[Any], str]] = Field(default_factory=list)
    selected_participant_ids: Optional[List[str]] = Field(default_factory=list)
    meeting_summary: Optional[str] = None
    key_decisions: Optional[Union[List[str], str]] = Field(default_factory=list)
    action_items: Optional[Union[List[Any], str]] = Field(default_factory=list)
    status: Optional[str] = "Completed"  # "Completed" or "failed"
    error_message: Optional[str] = None

class MeetingResponse(BaseModel):
    id: Optional[str] = None
    meeting_id: str
    team_id: str
    meeting_title: str
    title: str
    host_id: Optional[str] = None
    host_name: Optional[str] = None
    host_email: Optional[str] = None
    host_role: Optional[str] = None
    duration: Optional[str] = "00:00"
    selected_participant_ids: Optional[List[str]] = Field(default_factory=list)
    participants: Any = Field(default_factory=list)
    meeting_summary: Optional[str] = None
    summary: Optional[str] = None
    discussion_topics: Optional[List[str]] = Field(default_factory=list)
    key_decisions: Any = Field(default_factory=list)
    unresolved_questions: Optional[List[str]] = Field(default_factory=list)
    action_items: Any = Field(default_factory=list)
    speaker_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    agent_executions: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    team_lead_email: Optional[str] = ""
    status: str = "Completed"
    created_at: datetime
    completed_at: Optional[datetime] = None

class MeetingListResponse(BaseModel):
    meetings: List[MeetingResponse]
    total: int

class TaskApproveMeetingRequest(BaseModel):
    task_id: str
    assigned_member_id: Optional[str] = None
    assigned_member_name: Optional[str] = None
    assigned_member_email: Optional[str] = None
    assigned_member_role: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None

class TaskEditMeetingRequest(BaseModel):
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    assigned_member_id: Optional[str] = None
    assigned_member_name: Optional[str] = None
    assigned_member_email: Optional[str] = None
    assigned_member_role: Optional[str] = None
