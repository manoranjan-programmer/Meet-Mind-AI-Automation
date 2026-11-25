import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from app.database.mongo import get_col
from app.schemas.auth_schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.utils.security import hash_password, verify_password, create_access_token
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse)
def register_user(req: RegisterRequest):
    users_col = get_col("users")
    teams_col = get_col("teams")
    member_col = get_col("member_profiles")

    clean_email = req.email.strip().lower()
    if users_col.find_one({"email": clean_email}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists."
        )

    # 1. Create team
    team_id = f"TEAM-{uuid.uuid4().hex[:8].upper()}"
    user_id = f"USR-{uuid.uuid4().hex[:8].upper()}"

    team_doc = {
        "team_id": team_id,
        "name": req.team_name.strip() if req.team_name else f"{req.name}'s Team",
        "admin_id": user_id,
        "created_at": datetime.utcnow()
    }
    teams_col.insert_one(team_doc)

    # 2. Create user
    user_doc = {
        "user_id": user_id,
        "team_id": team_id,
        "name": req.name.strip(),
        "email": clean_email,
        "hashed_password": hash_password(req.password),
        "role": req.role or "Admin",
        "created_at": datetime.utcnow()
    }
    users_col.insert_one(user_doc)

    # 3. Create initial admin member profile in member_profiles via common service
    from app.services.team_service import TeamMemberService
    TeamMemberService.create_member_profile(
        team_id=team_id,
        name=req.name.strip(),
        email=clean_email,
        role=req.role or "Team Lead / Admin",
        skills=["Management", "Agile", "Strategy"],
        experience="Senior",
        availability="Available",
        maximum_workload=5,
        registration_method="manual",
        account_status="active"
    )

    # 4. Issue JWT
    token_payload = {
        "user_id": user_id,
        "email": clean_email,
        "name": req.name.strip(),
        "team_id": team_id,
        "role": user_doc["role"]
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user_id,
            email=clean_email,
            name=req.name.strip(),
            role=user_doc["role"],
            team_id=team_id,
            team_name=team_doc["name"],
            created_at=user_doc["created_at"]
        )
    )

@router.post("/login", response_model=TokenResponse)
def login_user(req: LoginRequest):
    users_col = get_col("users")
    teams_col = get_col("teams")

    clean_email = req.email.strip().lower()
    user = users_col.find_one({"email": clean_email})
    if not user or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    team = teams_col.find_one({"team_id": user["team_id"]})
    team_name = team.get("name") if team else "My Team"

    token_payload = {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "team_id": user["team_id"],
        "role": user["role"]
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user["user_id"],
            email=user["email"],
            name=user["name"],
            role=user["role"],
            team_id=user["team_id"],
            team_name=team_name,
            created_at=user.get("created_at")
        )
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    teams_col = get_col("teams")
    team = teams_col.find_one({"team_id": current_user["team_id"]})
    team_name = team.get("name") if team else "My Team"

    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user["email"],
        name=current_user["name"],
        role=current_user["role"],
        team_id=current_user["team_id"],
        team_name=team_name,
        created_at=current_user.get("created_at")
    )
