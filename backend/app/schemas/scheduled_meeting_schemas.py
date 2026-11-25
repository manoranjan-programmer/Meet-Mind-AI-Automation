from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ParseScheduleCommandRequest(BaseModel):
    command: str = Field(..., min_length=3, description="Natural language scheduling command")
    timezone: str = Field("Asia/Kolkata", description="Target timezone, defaults to Asia/Kolkata")

class ExtractedMeetingDetails(BaseModel):
    meeting_title: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM (24-hour)
    timezone: str = "Asia/Kolkata"
    duration_minutes: int = 30
    agenda: Optional[str] = "Team discussion and sync"
    participants: List[str] = Field(default_factory=list)
    is_ambiguous: bool = False
    clarification_question: Optional[str] = None

class MeetingPreviewResponse(BaseModel):
    status: str
    extracted: ExtractedMeetingDetails
    matched_participants: List[Dict[str, Any]]
    scheduled_start_utc: str
    scheduled_end_utc: str
    formatted_local_time: str

class ConfirmScheduleRequest(BaseModel):
    meeting_title: str
    description: Optional[str] = None
    agenda: Optional[str] = "Team discussion and sync"
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    timezone: str = "Asia/Kolkata"
    duration_minutes: int = 30
    selected_participant_ids: List[str] = Field(default_factory=list)

class UpdateScheduleRequest(BaseModel):
    meeting_title: Optional[str] = None
    description: Optional[str] = None
    agenda: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    timezone: Optional[str] = None
    duration_minutes: Optional[int] = None
    selected_participant_ids: Optional[List[str]] = None

class ScheduledMeetingResponse(BaseModel):
    meeting_id: str
    room_id: str
    team_id: str
    created_by: str
    host_id: Optional[str] = None
    host_name: Optional[str] = None
    host_email: Optional[str] = None
    host_role: Optional[str] = None
    meeting_link: Optional[str] = None
    invitation_event_id: Optional[str] = None
    invitation_dispatch_status: Optional[str] = None
    invitation_dispatch_error: Optional[str] = None
    meeting_title: str
    description: Optional[str] = None
    agenda: Optional[str] = None
    scheduled_start_at: str
    scheduled_end_at: str
    timezone: str
    duration_minutes: Optional[int] = 30
    duration: Optional[str] = None
    selected_participant_ids: List[str]
    participants: List[Dict[str, Any]]
    meeting_status: str  # scheduled, starting, active, completed, cancelled, missed
    is_joinable: bool = False
    time_until_start_seconds: int = 0
    actual_started_at: Optional[str] = None
    actual_completed_at: Optional[str] = None
    created_at: str

class UpcomingMeetingsListResponse(BaseModel):
    team_id: str
    total: int
    upcoming_meetings: List[ScheduledMeetingResponse]
    today_meetings: List[ScheduledMeetingResponse]
    active_meetings: List[ScheduledMeetingResponse]
    completed_meetings: List[ScheduledMeetingResponse]
    cancelled_meetings: List[ScheduledMeetingResponse]
