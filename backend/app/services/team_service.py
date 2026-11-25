import re
import uuid
import io
import csv
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException, status
import pandas as pd
from bson import ObjectId

from app.database.mongo import get_col
from app.config import settings
from app.utils.security import hash_password, generate_invitation_token, hash_token
from app.services.zapier_service import ZapierService, dispatch_webhook_in_background
from app.schemas.team_schemas import (
    MemberCreateRequest,
    MemberUpdateRequest,
    BulkImportRowResult,
    BulkImportSummaryResponse,
    AcceptInvitationRequest
)

logger = logging.getLogger("meetmind.team")

class TeamMemberService:
    @staticmethod
    def _generate_member_id(team_id: str) -> str:
        """Generate a clean sequential or unique member ID like MEM001, MEM002."""
        col = get_col("member_profiles")
        count = col.count_documents({"team_id": team_id}) + 1
        return f"MEM{count:03d}"

    @staticmethod
    def _clean_skills(skills_input: Any) -> List[str]:
        """Normalize skills input from list or comma-separated string."""
        if not skills_input:
            return []
        if isinstance(skills_input, list):
            cleaned = []
            for s in skills_input:
                if isinstance(s, str):
                    for sub in s.split(","):
                        sub_trimmed = sub.strip()
                        if sub_trimmed and sub_trimmed not in cleaned:
                            cleaned.append(sub_trimmed)
            return cleaned
        if isinstance(skills_input, str):
            items = [s.strip() for s in skills_input.split(",") if s.strip()]
            # deduplicate preserving order
            return list(dict.fromkeys(items))
        return []

    @staticmethod
    def _validate_email(email: str) -> bool:
        regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        return bool(re.match(regex, email.strip()))

    @staticmethod
    def create_member_profile(
        team_id: str,
        name: str,
        email: str,
        role: str,
        skills: Any,
        experience: str = "Intermediate",
        availability: str = "Available",
        maximum_workload: int = 5,
        registration_method: str = "manual",
        account_status: str = "active",
        profile_image: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Common validation and persistence service for all 3 registration methods.
        All members are saved into meetmind_ai.member_profiles with standard structure.
        """
        col = get_col("member_profiles")
        clean_email = email.strip().lower()
        
        # 1. Validate fields
        if not name or len(name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
        if not clean_email or not TeamMemberService._validate_email(clean_email):
            raise HTTPException(status_code=400, detail=f"Invalid email address: {email}")
        if not role or len(role.strip()) < 2:
            raise HTTPException(status_code=400, detail="Role is required.")
            
        # 2. Check duplicate within team
        existing = col.find_one({"team_id": team_id, "email": clean_email})
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A member with email '{clean_email}' already exists in this team."
            )

        # 3. Generate member ID
        member_id = TeamMemberService._generate_member_id(team_id)
        
        # Ensure member_id is unique in team
        while col.find_one({"team_id": team_id, "member_id": member_id}):
            random_suffix = str(uuid.uuid4())[:4].upper()
            member_id = f"MEM-{random_suffix}"

        # 4. Standard document structure
        doc = {
            "member_id": member_id,
            "team_id": team_id,
            "name": name.strip(),
            "email": clean_email,
            "role": role.strip(),
            "skills": TeamMemberService._clean_skills(skills),
            "experience": experience.strip() if experience else "Intermediate",
            "availability": availability.strip() if availability else "Available",
            "maximum_workload": int(maximum_workload) if maximum_workload else 5,
            "assigned_tasks": [],
            "registration_method": registration_method,
            "account_status": account_status,
            "profile_image": profile_image,
            "created_at": datetime.utcnow()
        }

        result = col.insert_one(doc)
        doc["_id"] = result.inserted_id

        # Trigger Zapier Team Member Added Webhook in background
        dispatch_webhook_in_background(
            ZapierService.send_team_member_added_webhook(doc)
        )

        return doc

    @staticmethod
    def list_members(
        team_id: str,
        search: Optional[str] = None,
        availability: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List team members with search, filters, and computed active workload."""
        col = get_col("member_profiles")
        query: Dict[str, Any] = {"team_id": team_id}

        if status and status.lower() != "all":
            query["account_status"] = status.lower()

        if availability and availability.lower() != "all":
            query["availability"] = availability

        if role and role.lower() != "all":
            query["role"] = {"$regex": role, "$options": "i"}

        if search and search.strip():
            term = search.strip()
            query["$or"] = [
                {"name": {"$regex": term, "$options": "i"}},
                {"email": {"$regex": term, "$options": "i"}},
                {"role": {"$regex": term, "$options": "i"}},
                {"skills": {"$in": [re.compile(term, re.IGNORECASE)]}}
            ]

        cursor = col.find(query).sort("created_at", -1)
        members = []
        for doc in cursor:
            # Format doc
            doc["id"] = str(doc["_id"])
            assigned = doc.get("assigned_tasks", [])
            max_w = doc.get("maximum_workload", 5) or 5
            active_count = len(assigned)
            doc["active_tasks_count"] = active_count
            doc["workload_percentage"] = min(100.0, round((active_count / max_w) * 100, 1))
            members.append(doc)

        return members

    @staticmethod
    def get_member(team_id: str, member_id: str) -> Dict[str, Any]:
        col = get_col("member_profiles")
        doc = col.find_one({"team_id": team_id, "member_id": member_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Member profile not found.")
        doc["id"] = str(doc["_id"])
        assigned = doc.get("assigned_tasks", [])
        max_w = doc.get("maximum_workload", 5) or 5
        doc["active_tasks_count"] = len(assigned)
        doc["workload_percentage"] = min(100.0, round((len(assigned) / max_w) * 100, 1))
        return doc

    @staticmethod
    def update_member(team_id: str, member_id: str, update_data: MemberUpdateRequest) -> Dict[str, Any]:
        col = get_col("member_profiles")
        doc = col.find_one({"team_id": team_id, "member_id": member_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Member profile not found.")

        updates: Dict[str, Any] = {}
        if update_data.name is not None:
            updates["name"] = update_data.name.strip()
        if update_data.role is not None:
            updates["role"] = update_data.role.strip()
        if update_data.skills is not None:
            updates["skills"] = TeamMemberService._clean_skills(update_data.skills)
        if update_data.experience is not None:
            updates["experience"] = update_data.experience.strip()
        if update_data.availability is not None:
            updates["availability"] = update_data.availability.strip()
        if update_data.maximum_workload is not None:
            updates["maximum_workload"] = update_data.maximum_workload
        if update_data.profile_image is not None:
            updates["profile_image"] = update_data.profile_image

        if updates:
            updates["updated_at"] = datetime.utcnow()
            col.update_one({"_id": doc["_id"]}, {"$set": updates})

        return TeamMemberService.get_member(team_id, member_id)

    @staticmethod
    def delete_member(team_id: str, member_id: str) -> bool:
        col = get_col("member_profiles")
        res = col.delete_one({"team_id": team_id, "member_id": member_id})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Member profile not found.")
        return True

    # ------------------ METHOD 2: CSV / EXCEL BULK IMPORT ------------------ #
    @staticmethod
    def parse_and_validate_bulk_file(
        team_id: str,
        file_bytes: bytes,
        filename: str,
        commit: bool = True
    ) -> BulkImportSummaryResponse:
        """
        Parses CSV or Excel, validates every row, detects duplicates,
        separates valid and invalid rows, and saves valid members into MongoDB
        with registration_method: "csv_import".
        """
        col = get_col("member_profiles")
        filename_lower = filename.lower()

        # Read into Pandas DataFrame
        try:
            if filename_lower.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8")
            elif filename_lower.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(file_bytes))
            else:
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a .csv or .xlsx file.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse spreadsheet: {str(e)}")

        # Normalize column headers
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        required_cols = ["name", "email", "role"]
        for col_name in required_cols:
            if col_name not in df.columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required column '{col_name}'. Required columns: name, email, role, skills, experience, availability, maximum_workload"
                )

        # Get existing emails in this team to detect duplicates
        existing_members = col.find({"team_id": team_id}, {"email": 1})
        existing_emails = {m["email"].lower() for m in existing_members}

        seen_file_emails = set()
        duplicate_emails = []
        valid_rows: List[BulkImportRowResult] = []
        invalid_rows: List[BulkImportRowResult] = []
        members_to_insert = []

        for idx, row in df.iterrows():
            row_num = int(idx) + 2  # 1-based, accounting for header row
            name = str(row.get("name", "")).strip() if pd.notna(row.get("name")) else ""
            raw_email = str(row.get("email", "")).strip() if pd.notna(row.get("email")) else ""
            clean_email = raw_email.lower()
            role = str(row.get("role", "")).strip() if pd.notna(row.get("role")) else ""
            skills_raw = row.get("skills", "")
            skills = TeamMemberService._clean_skills(skills_raw if pd.notna(skills_raw) else [])
            experience = str(row.get("experience", "Intermediate")).strip() if pd.notna(row.get("experience")) else "Intermediate"
            availability = str(row.get("availability", "Available")).strip() if pd.notna(row.get("availability")) else "Available"
            
            # Workload validation
            max_w_raw = row.get("maximum_workload", 5)
            try:
                max_w = int(max_w_raw) if pd.notna(max_w_raw) else 5
                if max_w < 1 or max_w > 20:
                    max_w = 5
            except Exception:
                max_w = 5

            error_msg = None
            if not name or len(name) < 2:
                error_msg = "Name is required and must be at least 2 characters."
            elif not clean_email or not TeamMemberService._validate_email(clean_email):
                error_msg = f"Invalid email format: '{raw_email}'."
            elif not role or len(role) < 2:
                error_msg = "Role is required."
            elif clean_email in existing_emails:
                error_msg = f"Email '{clean_email}' already exists in your team."
                if clean_email not in duplicate_emails:
                    duplicate_emails.append(clean_email)
            elif clean_email in seen_file_emails:
                error_msg = f"Duplicate email '{clean_email}' found multiple times in this file."
                if clean_email not in duplicate_emails:
                    duplicate_emails.append(clean_email)

            if error_msg:
                invalid_rows.append(BulkImportRowResult(
                    row_number=row_num,
                    name=name,
                    email=raw_email,
                    role=role,
                    skills=skills,
                    experience=experience,
                    availability=availability,
                    maximum_workload=max_w,
                    is_valid=False,
                    error=error_msg
                ))
            else:
                seen_file_emails.add(clean_email)
                row_res = BulkImportRowResult(
                    row_number=row_num,
                    name=name,
                    email=clean_email,
                    role=role,
                    skills=skills,
                    experience=experience,
                    availability=availability,
                    maximum_workload=max_w,
                    is_valid=True,
                    error=None
                )
                valid_rows.append(row_res)
                members_to_insert.append({
                    "name": name,
                    "email": clean_email,
                    "role": role,
                    "skills": skills,
                    "experience": experience,
                    "availability": availability,
                    "maximum_workload": max_w
                })

        # If commit is True, generate pending invitations for valid rows (Section 8: does not directly create active members)
        imported_count = 0
        if commit and members_to_insert:
            for item in members_to_insert:
                try:
                    # Map role to Editor or Viewer, preserving specific role title in message
                    target_role = "Viewer" if "viewer" in item["role"].lower() else "Editor"
                    TeamMemberService.create_invitation(
                        team_id=team_id,
                        current_user={"email": "CSV Bulk Import", "name": "Team Leader"},
                        email=item["email"],
                        role=target_role,
                        message=f"Bulk imported as {item['role']}"
                    )
                    imported_count += 1
                except Exception as insert_err:
                    # If already active or pending, skip gracefully
                    pass

        return BulkImportSummaryResponse(
            total_rows=len(df),
            valid_count=len(valid_rows),
            invalid_count=len(invalid_rows),
            imported_count=imported_count if commit else 0,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            duplicate_emails=duplicate_emails
        )

    @staticmethod
    def get_csv_template() -> str:
        """Returns CSV template content for download."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["name", "email", "role", "skills", "experience", "availability", "maximum_workload"])
        writer.writerow(["Jai", "jai@example.com", "Frontend Developer", "React,JavaScript,CSS", "Intermediate", "Available", "5"])
        writer.writerow(["Arun", "arun@example.com", "Backend Developer", "Python,Node.js,MongoDB", "Advanced", "Available", "5"])
        writer.writerow(["Priya", "priya@example.com", "UI/UX Designer", "Figma,UI Design", "Intermediate", "Busy", "3"])
        writer.writerow(["Karthik", "karthik@example.com", "Tester", "Selenium,Testing", "Intermediate", "Available", "5"])
        return output.getvalue()

    # ------------------ METHOD 3: INVITATION & SELF-REGISTRATION ------------------ #
    @staticmethod
    def create_invitation(
        team_id: str,
        current_user: dict,
        email: str,
        role: str = "Editor",
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a secure time-limited invitation conforming to Section 3:
        Fields:
          - invitation_id
          - team_id
          - invited_email
          - invited_by
          - assigned_role (Editor / Viewer)
          - token_hash (cryptographically secure random token hashed)
          - invitation_status (pending, accepted, expired, revoked)
          - created_at
          - expires_at (72 hours expiry)
          - accepted_at
          - revoked_at
        """
        clean_email = email.strip().lower()
        if not TeamMemberService._validate_email(clean_email):
            raise HTTPException(status_code=400, detail="Invalid email format.")

        # Normalize access level / role (Editor or Viewer)
        norm_role = role.strip()
        if norm_role.lower() in ["viewer", "read-only", "read_only"]:
            assigned_role = "Viewer"
        else:
            assigned_role = "Editor"

        # Check if already an active member in team
        member_col = get_col("member_profiles")
        existing_member = member_col.find_one({"team_id": team_id, "email": clean_email, "account_status": "active"})
        if existing_member:
            raise HTTPException(
                status_code=409,
                detail=f"User with email '{clean_email}' is already an active member of this team."
            )

        inv_col = get_col("team_invitations")
        # Check if active pending invitation already exists for this email
        active_pending = inv_col.find_one({
            "team_id": team_id,
            "invited_email": clean_email,
            "invitation_status": "pending",
            "expires_at": {"$gt": datetime.utcnow()}
        })
        if active_pending:
            raise HTTPException(
                status_code=409,
                detail=f"A pending invitation already exists for '{clean_email}'. You can resend or revoke it."
            )

        raw_token, token_hash = generate_invitation_token()
        invitation_id = f"INV-{uuid.uuid4().hex[:10].upper()}"
        correlation_id = f"INV-CORR-{uuid.uuid4().hex[:8].upper()}"
        # Expiry period: 72 hours (as specified in Section 3)
        expires_at = datetime.utcnow() + timedelta(hours=72)

        teams_col = get_col("teams")
        team = teams_col.find_one({"team_id": team_id})
        team_name = team.get("name", "MeetMind Team") if team else "MeetMind Team"

        invitation_url = f"{settings.FRONTEND_URL}/accept-invitation/{raw_token}"

        invitation_doc = {
            "invitation_id": invitation_id,
            "correlation_id": correlation_id,
            "team_id": team_id,
            "team_name": team_name,
            "invited_email": clean_email,
            "email": clean_email,  # backward compatibility
            "invited_by": current_user.get("name") or current_user.get("email"),
            "assigned_role": assigned_role,
            "role": assigned_role,  # backward compatibility
            "message": message.strip() if message else None,
            "token_hash": token_hash,
            "invitation_status": "pending",
            "status": "pending",  # backward compatibility
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "accepted_at": None,
            "revoked_at": None,
            "invitation_url": invitation_url
        }

        inv_col.insert_one(invitation_doc)

        logger.info(
            f"[{correlation_id}] Generated team invitation: "
            f"invitation_id={invitation_id}, team_id={team_id}, "
            f"intended_recipient={clean_email}, assigned_role={assigned_role}, "
            f"mongo_save_result=SUCCESS"
        )

        # Trigger Zapier Team Invitation Created Webhook in background
        dispatch_webhook_in_background(
            ZapierService.send_team_invitation_created_webhook(
                invitation_doc,
                is_resend=False,
                correlation_id=correlation_id
            )
        )

        invitation_doc["raw_token"] = raw_token  # returned only upon creation so admin can copy if needed
        return invitation_doc

    @staticmethod
    def list_invitations(team_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        inv_col = get_col("team_invitations")
        query: Dict[str, Any] = {"team_id": team_id}
        
        cursor = inv_col.find(query).sort("created_at", -1)
        invitations = []
        now = datetime.utcnow()
        for doc in cursor:
            # Check expiry dynamically
            st = doc.get("invitation_status") or doc.get("status")
            if st == "pending" and doc.get("expires_at") and doc.get("expires_at") < now:
                st = "expired"
                inv_col.update_one({"_id": doc["_id"]}, {"$set": {"invitation_status": "expired", "status": "expired"}})

            if status_filter and status_filter.lower() != "all":
                if st.lower() != status_filter.lower():
                    continue

            inv_id = doc.get("invitation_id")
            invited_email = doc.get("invited_email") or doc.get("email")
            role_val = doc.get("assigned_role") or doc.get("role") or "Editor"
            invitations.append({
                "invitation_id": inv_id,
                "team_id": doc["team_id"],
                "team_name": doc.get("team_name"),
                "email": invited_email,
                "invited_email": invited_email,
                "role": role_val,
                "assigned_role": role_val,
                "invited_by": doc.get("invited_by"),
                "status": st,
                "invitation_status": st,
                "expires_at": doc["expires_at"],
                "created_at": doc["created_at"],
                "accepted_at": doc.get("accepted_at"),
                "revoked_at": doc.get("revoked_at"),
                "invitation_url": doc.get("invitation_url")
            })
        return invitations

    @staticmethod
    def revoke_invitation(team_id: str, invitation_id: str) -> bool:
        inv_col = get_col("team_invitations")
        res = inv_col.update_one(
            {"team_id": team_id, "invitation_id": invitation_id, "$or": [{"invitation_status": "pending"}, {"status": "pending"}]},
            {"$set": {"invitation_status": "revoked", "status": "revoked", "revoked_at": datetime.utcnow()}}
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Pending invitation not found or already processed.")
        return True

    @staticmethod
    def resend_invitation(team_id: str, invitation_id: str, current_user: dict) -> Dict[str, Any]:
        """Resends an invitation with a refreshed token and extended 72h expiry."""
        inv_col = get_col("team_invitations")
        inv = inv_col.find_one({"team_id": team_id, "invitation_id": invitation_id})
        if not inv:
            raise HTTPException(status_code=404, detail="Invitation not found.")

        raw_token, token_hash = generate_invitation_token()
        expires_at = datetime.utcnow() + timedelta(hours=72)
        invitation_url = f"{settings.FRONTEND_URL}/accept-invitation/{raw_token}"
        correlation_id = f"INV-RESEND-CORR-{uuid.uuid4().hex[:8].upper()}"

        updates = {
            "token_hash": token_hash,
            "invitation_status": "pending",
            "status": "pending",
            "expires_at": expires_at,
            "invitation_url": invitation_url,
            "correlation_id": correlation_id,
            "updated_at": datetime.utcnow()
        }
        inv_col.update_one({"_id": inv["_id"]}, {"$set": updates})
        inv.update(updates)
        inv["raw_token"] = raw_token

        logger.info(
            f"[{correlation_id}] Resending team invitation: "
            f"invitation_id={invitation_id}, team_id={team_id}, "
            f"intended_recipient={inv.get('invited_email')}, "
            f"mongo_save_result=UPDATED"
        )

        # Trigger Zapier invitation webhook again with is_resend=True
        dispatch_webhook_in_background(
            ZapierService.send_team_invitation_created_webhook(
                inv,
                is_resend=True,
                correlation_id=correlation_id
            )
        )
        return inv

    @staticmethod
    def verify_invitation_token(raw_token: str) -> Dict[str, Any]:
        """Verify token hash without revealing database internals."""
        token_hash = hash_token(raw_token)
        inv_col = get_col("team_invitations")
        inv = inv_col.find_one({"token_hash": token_hash})
        if not inv:
            raise HTTPException(status_code=404, detail="Invalid invitation token.")
        
        st = inv.get("invitation_status") or inv.get("status")
        if st != "pending":
            raise HTTPException(status_code=400, detail=f"This invitation has already been {st}.")

        if inv.get("expires_at") and inv.get("expires_at") < datetime.utcnow():
            inv_col.update_one({"_id": inv["_id"]}, {"$set": {"invitation_status": "expired", "status": "expired"}})
            raise HTTPException(status_code=400, detail="This invitation has expired.")

        return inv

    @staticmethod
    def accept_invitation(req: AcceptInvitationRequest, authenticated_user: Optional[dict] = None) -> Dict[str, Any]:
        """
        Acceptance flow:
        - Verifies invitation token
        - Checks email match if user is already authenticated
        - Creates user account in `users` with hashed password if not present
        - Saves member profile in `member_profiles` with registration_method="invitation"
        - Marks invitation as accepted with accepted_at
        """
        inv = TeamMemberService.verify_invitation_token(req.token)
        team_id = inv["team_id"]
        invited_email = (inv.get("invited_email") or inv.get("email")).strip().lower()
        assigned_role = inv.get("assigned_role") or inv.get("role") or "Editor"

        # Security check: If authenticated, verify email matches invited email
        if authenticated_user:
            auth_email = authenticated_user.get("email", "").strip().lower()
            if auth_email != invited_email:
                raise HTTPException(
                    status_code=403,
                    detail=f"Authenticated account ({auth_email}) does not match the invited email ({invited_email})."
                )

        users_col = get_col("users")
        inv_col = get_col("team_invitations")

        # 1. Create user account if doesn't exist
        existing_user = users_col.find_one({"email": invited_email})
        if existing_user:
            user_id = existing_user["user_id"]
            # Update user's team_id and role
            users_col.update_one(
                {"_id": existing_user["_id"]},
                {"$set": {"team_id": team_id, "role": assigned_role}}
            )
        else:
            if not req.password or len(req.password) < 6:
                raise HTTPException(status_code=400, detail="Password of at least 6 characters is required for new accounts.")
            user_id = f"USR-{uuid.uuid4().hex[:10].upper()}"
            new_user = {
                "user_id": user_id,
                "team_id": team_id,
                "name": req.name.strip(),
                "email": invited_email,
                "hashed_password": hash_password(req.password),
                "role": assigned_role,
                "created_at": datetime.utcnow()
            }
            users_col.insert_one(new_user)

        # 2. Persist member profile into common member_profiles collection
        member_doc = TeamMemberService.create_member_profile(
            team_id=team_id,
            name=req.name.strip(),
            email=invited_email,
            role=assigned_role,
            skills=req.skills,
            experience=req.experience,
            availability=req.availability,
            maximum_workload=req.maximum_workload or 5,
            registration_method="invitation",
            account_status="active"
        )

        # 3. Mark invitation as accepted (single-use enforcement)
        inv_col.update_one(
            {"_id": inv["_id"]},
            {"$set": {"invitation_status": "accepted", "status": "accepted", "accepted_at": datetime.utcnow()}}
        )

        member_doc["id"] = str(member_doc["_id"])
        return member_doc

    @staticmethod
    def reject_invitation(raw_token: str) -> Dict[str, Any]:
        """
        Rejection flow:
        - Verifies pending invitation token
        - Marks invitation as rejected with rejected_at timestamp
        - Does NOT create user/member or dispatch acceptance webhook
        """
        inv = TeamMemberService.verify_invitation_token(raw_token)
        inv_col = get_col("team_invitations")
        now = datetime.utcnow()
        inv_col.update_one(
            {"_id": inv["_id"]},
            {"$set": {"invitation_status": "rejected", "status": "rejected", "rejected_at": now}}
        )
        logger.info(
            f"Invitation rejected: invitation_id={inv.get('invitation_id')} "
            f"team_id={inv.get('team_id')} email={inv.get('invited_email') or inv.get('email')}"
        )
        return {
            "status": "rejected",
            "invitation_id": inv.get("invitation_id"),
            "team_id": inv.get("team_id"),
            "invited_email": inv.get("invited_email") or inv.get("email"),
            "rejected_at": now.isoformat() + "Z",
        }
