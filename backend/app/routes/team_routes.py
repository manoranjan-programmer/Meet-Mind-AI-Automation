from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Response
from app.middleware.auth import get_current_user
from app.services.team_service import TeamMemberService
from app.schemas.team_schemas import (
    MemberCreateRequest,
    MemberUpdateRequest,
    MemberResponse,
    MemberListResponse,
    BulkImportSummaryResponse,
    InviteMemberRequest,
    InvitationResponse,
    InvitationInfoResponse,
    AcceptInvitationRequest
)

router = APIRouter(prefix="/team", tags=["Team Management"])
teams_router = APIRouter(prefix="/teams", tags=["Teams"])

# ----------------- METHOD 1: MANUAL MEMBER CRUD ----------------- #

@router.post("/members", response_model=MemberResponse, status_code=201)
def add_team_member(
    req: MemberCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    METHOD 1: Admin manual registration.
    Saves member profile into meetmind_ai.member_profiles with registration_method="manual".
    """
    team_id = current_user["team_id"]
    doc = TeamMemberService.create_member_profile(
        team_id=team_id,
        name=req.name,
        email=req.email,
        role=req.role,
        skills=req.skills,
        experience=req.experience,
        availability=req.availability,
        maximum_workload=req.maximum_workload,
        registration_method="manual",
        account_status="active",
        profile_image=req.profile_image
    )
    doc["id"] = str(doc["_id"])
    doc["active_tasks_count"] = 0
    doc["workload_percentage"] = 0.0
    return doc

@router.get("/members", response_model=MemberListResponse)
def list_team_members(
    search: Optional[str] = Query(None, description="Search by name, email, role, or skill"),
    availability: Optional[str] = Query(None, description="Filter: Available, Busy, On Leave"),
    role: Optional[str] = Query(None, description="Filter by role"),
    status: Optional[str] = Query(None, description="Filter by account status: active, inactive"),
    current_user: dict = Depends(get_current_user)
):
    """List team members with optional search and filters."""
    team_id = current_user["team_id"]
    members = TeamMemberService.list_members(
        team_id=team_id,
        search=search,
        availability=availability,
        role=role,
        status=status
    )
    available = sum(1 for m in members if m.get("availability") == "Available")
    busy = sum(1 for m in members if m.get("availability") == "Busy")

    return MemberListResponse(
        members=members,
        total=len(members),
        available_count=available,
        busy_count=busy
    )

@teams_router.get("/{team_id}/members", response_model=MemberListResponse)
def list_team_members_by_team_id(
    team_id: str,
    status: Optional[str] = Query(None, description="Filter: active, inactive"),
    search: Optional[str] = Query(None),
    availability: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """List members for a specific team, enforcing team isolation."""
    user_team_id = current_user.get("team_id")
    if user_team_id != team_id and current_user.get("role") not in ["Admin", "Team Lead"]:
        raise HTTPException(status_code=403, detail="Access denied: Cannot access members from another team.")

    members = TeamMemberService.list_members(
        team_id=team_id,
        search=search,
        availability=availability,
        role=role,
        status=status
    )
    available = sum(1 for m in members if m.get("availability") == "Available")
    busy = sum(1 for m in members if m.get("availability") == "Busy")

    return MemberListResponse(
        members=members,
        total=len(members),
        available_count=available,
        busy_count=busy
    )

@router.get("/members/template")
def download_csv_template():
    """Download a pre-formatted sample CSV template."""
    csv_content = TeamMemberService.get_csv_template()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=meetmind_team_template.csv"}
    )

@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member_profile(
    member_id: str,
    current_user: dict = Depends(get_current_user)
):
    team_id = current_user["team_id"]
    return TeamMemberService.get_member(team_id, member_id)

@router.put("/members/{member_id}", response_model=MemberResponse)
def update_member_profile(
    member_id: str,
    req: MemberUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    team_id = current_user["team_id"]
    return TeamMemberService.update_member(team_id, member_id, req)

@router.delete("/members/{member_id}")
def delete_team_member(
    member_id: str,
    current_user: dict = Depends(get_current_user)
):
    team_id = current_user["team_id"]
    TeamMemberService.delete_member(team_id, member_id)
    return {"success": True, "message": f"Member {member_id} removed successfully."}

# ----------------- METHOD 2: CSV / EXCEL BULK IMPORT ----------------- #

@router.post("/members/import", response_model=BulkImportSummaryResponse)
async def import_team_members(
    file: UploadFile = File(...),
    preview: bool = Query(False, description="If True, validates without committing to DB"),
    current_user: dict = Depends(get_current_user)
):
    """
    METHOD 2: CSV / Excel bulk upload.
    Parses, validates, detects duplicates, and saves into meetmind_ai.member_profiles
    with registration_method="csv_import".
    """
    team_id = current_user["team_id"]
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    summary = TeamMemberService.parse_and_validate_bulk_file(
        team_id=team_id,
        file_bytes=content,
        filename=file.filename or "upload.csv",
        commit=(not preview)
    )
    return summary

# ----------------- INVITATIONS & ACCESS MANAGEMENT ----------------- #

def require_team_lead(user: dict):
    role = str(user.get("role", "")).lower()
    if not any(leader_kw in role for leader_kw in ["lead", "admin", "owner", "manager", "team leader"]):
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Only Team Leaders or Administrators can perform this action."
        )

@router.post("/invitations", response_model=InvitationResponse, status_code=201)
@router.post("/invite", response_model=InvitationResponse, status_code=201)
def invite_team_member(
    req: InviteMemberRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Team Leader invites team member by email and access level (Editor / Viewer).
    Generates secure single-use token and triggers Zapier invitation webhook.
    """
    require_team_lead(current_user)
    team_id = current_user["team_id"]
    invitation = TeamMemberService.create_invitation(
        team_id=team_id,
        current_user=current_user,
        email=req.email,
        role=req.role,
        message=req.message
    )
    return invitation

@router.get("/invitations", response_model=List[InvitationResponse])
def get_team_invitations(
    status: Optional[str] = Query(None, description="pending, accepted, expired, revoked, or all"),
    current_user: dict = Depends(get_current_user)
):
    """List team invitations for team leader dashboard."""
    team_id = current_user["team_id"]
    return TeamMemberService.list_invitations(team_id, status_filter=status)

@router.post("/invitations/{invitation_id}/resend", response_model=InvitationResponse)
def resend_team_invitation(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Resend a team invitation with a refreshed token and extended 72h expiry."""
    require_team_lead(current_user)
    team_id = current_user["team_id"]
    return TeamMemberService.resend_invitation(team_id, invitation_id, current_user)

@router.delete("/invitations/{invitation_id}")
def revoke_team_invitation(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Revoke a pending team invitation."""
    require_team_lead(current_user)
    team_id = current_user["team_id"]
    TeamMemberService.revoke_invitation(team_id, invitation_id)
    return {"success": True, "message": "Invitation revoked successfully."}

# Public endpoints for invited members to accept & register:

@router.get("/invitation-info", response_model=InvitationInfoResponse)
def get_invitation_info(token: str = Query(..., description="Raw invitation token")):
    """Public endpoint to check if an invitation token is valid before showing registration form."""
    try:
        inv = TeamMemberService.verify_invitation_token(token)
        invited_email = inv.get("invited_email") or inv.get("email")
        role_val = inv.get("assigned_role") or inv.get("role") or "Editor"
        return InvitationInfoResponse(
            email=invited_email,
            invited_email=invited_email,
            team_id=inv["team_id"],
            team_name=inv.get("team_name", "MeetMind Team"),
            role=role_val,
            assigned_role=role_val,
            invited_by=inv.get("invited_by"),
            expires_at=inv.get("expires_at"),
            is_valid=True
        )
    except HTTPException as e:
        return InvitationInfoResponse(
            email="",
            invited_email="",
            team_id="",
            team_name="",
            role="",
            assigned_role="",
            is_valid=False,
            error=e.detail
        )

@router.post("/accept-invitation", response_model=MemberResponse, status_code=201)
def accept_invitation_and_register(
    req: AcceptInvitationRequest,
    current_user: Optional[dict] = Depends(lambda: None)
):
    """
    Public self-registration for invited members.
    Validates token, saves member profile into meetmind_ai.member_profiles
    with registration_method="invitation".
    """
    member_doc = TeamMemberService.accept_invitation(req, authenticated_user=current_user)
    return member_doc
