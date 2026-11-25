from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Any
from datetime import datetime

class MemberBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    role: str = Field(..., min_length=2, max_length=100)
    skills: List[str] = Field(default_factory=list)
    experience: str = Field("Intermediate", description="Junior, Intermediate, Senior, or Advanced")
    availability: str = Field("Available", description="Available, Busy, or On Leave")
    maximum_workload: int = Field(5, ge=1, le=20)
    profile_image: Optional[str] = None

class MemberCreateRequest(MemberBase):
    pass

class MemberUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[str] = None
    availability: Optional[str] = None
    maximum_workload: Optional[int] = Field(None, ge=1, le=20)
    profile_image: Optional[str] = None

class MemberResponse(MemberBase):
    id: Optional[str] = None
    member_id: str
    team_id: str
    assigned_tasks: List[str] = Field(default_factory=list)
    active_tasks_count: int = 0
    workload_percentage: float = 0.0
    registration_method: str  # "manual", "csv_import", "invitation"
    account_status: str       # "active", "invited", "inactive"
    created_at: datetime

class MemberListResponse(BaseModel):
    members: List[MemberResponse]
    total: int
    available_count: int
    busy_count: int

# CSV / Excel Bulk Import
class BulkImportRowResult(BaseModel):
    row_number: int
    name: str
    email: str
    role: str
    skills: List[str]
    experience: str
    availability: str
    maximum_workload: int
    is_valid: bool
    error: Optional[str] = None

class BulkImportSummaryResponse(BaseModel):
    total_rows: int
    valid_count: int
    invalid_count: int
    imported_count: int
    valid_rows: List[BulkImportRowResult]
    invalid_rows: List[BulkImportRowResult]
    duplicate_emails: List[str] = Field(default_factory=list)

# Invitation Models
class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = Field(..., description="Editor or Viewer")
    message: Optional[str] = None

class InvitationResponse(BaseModel):
    invitation_id: str
    team_id: str
    team_name: Optional[str] = None
    email: str
    invited_email: str
    role: str
    assigned_role: str
    invited_by: Optional[str] = None
    status: str  # "pending", "accepted", "revoked", "expired"
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    invitation_url: Optional[str] = None
    raw_token: Optional[str] = None

class InvitationInfoResponse(BaseModel):
    email: str
    invited_email: str
    team_id: str
    team_name: str
    role: str
    assigned_role: str
    invited_by: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_valid: bool
    error: Optional[str] = None

class AcceptInvitationRequest(BaseModel):
    token: str
    name: str = Field(..., min_length=2, max_length=100)
    password: Optional[str] = None  # optional if user is already authenticated
    skills: List[str] = Field(default_factory=list)
    experience: str = Field("Intermediate")
    availability: str = Field("Available")
    maximum_workload: Optional[int] = Field(5, ge=1, le=20)
