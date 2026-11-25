from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from app.services.team_service import TeamMemberService
from app.schemas.team_schemas import (
    InvitationInfoResponse,
    AcceptInvitationRequest,
    MemberResponse
)
from app.middleware.auth import security_bearer
from app.utils.security import decode_access_token
from app.database.mongo import get_col

router = APIRouter(prefix="/invitations", tags=["Public Invitations"])

def get_optional_user(credentials = Depends(security_bearer)) -> Optional[dict]:
    if not credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        if not payload or not payload.get("user_id"):
            return None
        users_col = get_col("users")
        return users_col.find_one({"user_id": payload.get("user_id")})
    except Exception:
        return None

@router.get("/validate/{token}", response_model=InvitationInfoResponse)
def validate_invitation(token: str):
    """
    Validates token, returning team name, inviter, assigned role, and expiry info.
    """
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

@router.post("/accept", response_model=MemberResponse, status_code=201)
def accept_invitation(
    req: AcceptInvitationRequest,
    authenticated_user: Optional[dict] = Depends(get_optional_user)
):
    """
    Accepts invitation, binds membership, hashes password if creating account,
    and single-use marks invitation as accepted.
    """
    return TeamMemberService.accept_invitation(req, authenticated_user=authenticated_user)


class RejectInvitationRequest(BaseModel):
    token: str


@router.post("/reject")
def reject_invitation(req: RejectInvitationRequest):
    """
    Rejects a pending invitation using its single-use token.
    """
    return TeamMemberService.reject_invitation(req.token)
