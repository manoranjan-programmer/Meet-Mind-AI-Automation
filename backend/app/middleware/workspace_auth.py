import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from app.middleware.auth import get_current_user
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.workspace_auth")

ROLE_HIERARCHY = {
    "Team Leader": 3,
    "Team Lead": 3,
    "Team Lead / Admin": 3,
    "Team Leader / Admin": 3,
    "Admin": 3,
    "Editor": 2,
    "Viewer": 1
}
LEADER_ROLE_ALIASES = {
    "admin",
    "manager",
    "team lead",
    "team leader",
    "team_leader",
    "team lead / admin",
    "team leader / admin",
}

def verify_workspace_access(
    team_id: str,
    current_user: dict,
    allowed_roles: Optional[List[str]] = None
) -> dict:
    """
    Verifies that the authenticated user is an active member of the specified team_id workspace
    and possesses the required role permission.
    Never trusts team_id or role blindly from client input.
    """
    user_id = current_user.get("user_id")
    user_email = current_user.get("email")
    user_team_id = current_user.get("team_id")

    # 1. Check direct team association
    if user_team_id != team_id:
        # Check if member profile exists for this team_id with active status
        member_col = get_col("member_profiles")
        member = member_col.find_one({
            "team_id": team_id,
            "email": {"$regex": f"^{user_email}$", "$options": "i"},
            "account_status": "active"
        })
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You are not an active member of workspace '{team_id}'."
            )
        role = member.get("role", "Viewer")
    else:
        # Check if user has active member profile or is active user
        member_col = get_col("member_profiles")
        member = member_col.find_one({
            "team_id": team_id,
            "email": {"$regex": f"^{user_email}$", "$options": "i"}
        })
        if member:
            status_val = member.get("account_status", "active")
            if status_val in ["removed", "revoked", "suspended", "inactive", "pending"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Your account status in workspace '{team_id}' is '{status_val}'."
                )
            role = member.get("role", current_user.get("role", "Editor"))
        else:
            role = current_user.get("role", "Team Leader")

    # 2. Check role authorization
    normalized_role = "Team Leader" if str(role).strip().lower() in LEADER_ROLE_ALIASES else role
    if allowed_roles:
        normalized_allowed = [
            "Team Leader" if str(r).strip().lower() in LEADER_ROLE_ALIASES else r
            for r in allowed_roles
        ]
        if normalized_role not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Action requires one of {allowed_roles}, but current role is '{role}'."
            )

    return {
        **current_user,
        "effective_role": normalized_role,
        "team_id": team_id
    }

def require_workspace_member(team_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: Any active member (Team Leader, Editor, Viewer)."""
    return verify_workspace_access(team_id, current_user, allowed_roles=["Team Leader", "Editor", "Viewer"])

def require_workspace_editor_or_leader(team_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: Active Editor or Team Leader."""
    return verify_workspace_access(team_id, current_user, allowed_roles=["Team Leader", "Editor"])

def require_workspace_leader(team_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: Active Team Leader only."""
    return verify_workspace_access(team_id, current_user, allowed_roles=["Team Leader"])
