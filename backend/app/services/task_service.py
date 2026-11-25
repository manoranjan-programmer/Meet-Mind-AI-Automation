import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException, status
from bson import ObjectId

from app.database.mongo import get_col
from app.schemas.task_schemas import TaskCreateRequest, TaskUpdateRequest, TaskStatusUpdateRequest
from app.services.automation_service import AutomationService
from app.services.zapier_service import ZapierService, dispatch_webhook_in_background

VALID_STATUSES = ["To Do", "In Progress", "Review", "Completed"]
VALID_PRIORITIES = ["Low", "Medium", "High", "Critical"]
LEADER_ROLES = {"admin", "team lead", "team leader", "team_leader", "manager", "team lead / admin", "team leader / admin"}

class TaskService:
    @staticmethod
    def require_team_leader(team_id: str, current_user: dict) -> dict:
        """Resolve the requester's trusted workspace role before leader-only actions."""
        from app.middleware.workspace_auth import verify_workspace_access

        return verify_workspace_access(
            team_id=team_id,
            current_user=current_user,
            allowed_roles=["Team Leader"]
        )

    @staticmethod
    def resolve_user_access(team_id: str, current_user: dict) -> Dict[str, Any]:
        """Resolves authenticated user's workspace role, member_id, and assignee MongoDB filter."""
        member_col = get_col("member_profiles")
        user_email = (current_user.get("email") or "").strip().lower()
        current_member = (
            member_col.find_one({"team_id": team_id, "email": {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}})
            if user_email else None
        )
        current_member_id = current_member.get("member_id") if current_member else None
        effective_role = (current_member.get("role") if current_member else None) or current_user.get("role", "Member")
        is_leader = str(effective_role).strip().lower() in LEADER_ROLES

        assignee_clauses: List[Dict[str, Any]] = []
        if current_member_id:
            assignee_clauses.append({"assigned_member_id": current_member_id})
        if user_email:
            assignee_clauses.append({"assigned_member_email": {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}})

        assignee_filter: Dict[str, Any] = (
            {"$or": assignee_clauses} if len(assignee_clauses) > 1
            else (assignee_clauses[0] if assignee_clauses else {"_id": None})
        )
        return {
            "is_leader": is_leader,
            "current_member_id": current_member_id,
            "user_email": user_email,
            "assignee_filter": assignee_filter,
        }
    @staticmethod
    def _generate_task_id(team_id: str) -> str:
        col = get_col("tasks")
        count = col.count_documents({}) + 1
        task_id = f"TSK-{count:03d}"
        while col.find_one({"task_id": task_id}):
            count += 1
            task_id = f"TSK-{count:03d}"
        return task_id

    @staticmethod
    def _find_member_details(team_id: str, member_id: Optional[str]) -> Tuple[str, str, str]:
        """Returns (name, role, email) for member_id if found, else Unassigned defaults."""
        if not member_id:
            return "Unassigned", "Unassigned", ""
        
        member_col = get_col("member_profiles")
        m = member_col.find_one({"team_id": team_id, "member_id": member_id})
        if m:
            return m.get("name", "Unassigned"), m.get("role", "Member"), m.get("email", "")
        
        # Check by email or id
        m_email = member_col.find_one({"team_id": team_id, "email": member_id.lower()})
        if m_email:
            return m_email.get("name", "Unassigned"), m_email.get("role", "Member"), m_email.get("email", "")

        return "Unassigned", "Unassigned", ""

    @staticmethod
    def create_task(team_id: str, current_user: dict, req: TaskCreateRequest) -> Dict[str, Any]:
        """
        Creates a task awaiting Team Leader approval in MongoDB Atlas.
        Enforces idempotency: if task_id already exists for team, does not duplicate.
        """
        tasks_col = get_col("tasks")
        member_col = get_col("member_profiles")

        # 1. Check idempotency if task_id was supplied
        if req.task_id:
            existing = tasks_col.find_one({"team_id": team_id, "task_id": req.task_id})
            if existing:
                existing["id"] = str(existing["_id"])
                return existing

        task_id = req.task_id or TaskService._generate_task_id(team_id)
        # Ensure task_id unique in team
        while tasks_col.find_one({"team_id": team_id, "task_id": task_id}):
            random_suffix = uuid.uuid4().hex[:4].upper()
            task_id = f"TSK-{random_suffix}"

        # 2. Resolve & validate selected assignee within the same workspace
        resolved_member_id = None
        m_name, m_role, m_email = "Unassigned", "Unassigned", ""
        if req.assigned_member_id and str(req.assigned_member_id).strip():
            target_mid = str(req.assigned_member_id).strip()
            target_member = member_col.find_one({"team_id": team_id, "member_id": target_mid})
            if not target_member:
                raise HTTPException(
                    status_code=400,
                    detail=f"Selected team member '{target_mid}' does not belong to this workspace."
                )
            resolved_member_id = target_member.get("member_id")
            m_name = target_member.get("name", "Unassigned")
            m_role = target_member.get("role", "Member")
            m_email = target_member.get("email", "")

        creator_id = current_user.get("user_id")
        task_doc = {
            "task_id": task_id,
            "team_id": team_id,
            "meeting_id": req.meeting_id or f"MTG-MANUAL-{uuid.uuid4().hex[:6].upper()}",
            "meeting_title": req.meeting_title.strip() if req.meeting_title else "Manual Task",
            "title": req.title.strip(),
            "description": req.description.strip() if req.description else "",
            "created_by": creator_id,
            "created_by_id": creator_id,
            "assigned_by_id": creator_id if resolved_member_id else None,
            "assigned_member_id": resolved_member_id,
            "assigned_member_name": m_name,
            "assigned_member_role": m_role,
            "assigned_member_email": m_email,
            "priority": req.priority if req.priority in VALID_PRIORITIES else "Medium",
            "deadline": req.deadline.strip() if req.deadline else None,
            "status": "To Do",
            "approval_status": "Awaiting Approval",
            "required_skills": req.required_skills or [],
            "confidence_score": 1.0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        res = tasks_col.insert_one(task_doc)
        task_doc["_id"] = res.inserted_id
        task_doc["id"] = str(res.inserted_id)

        # 3. Add to member assigned_tasks
        if resolved_member_id:
            member_col.update_one(
                {"team_id": team_id, "member_id": resolved_member_id},
                {"$addToSet": {"assigned_tasks": task_id}}
            )

        return task_doc

    @staticmethod
    def list_tasks(
        team_id: str,
        current_user: dict,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_member_id: Optional[str] = None,
        meeting_id: Optional[str] = None,
        approval_status: Optional[str] = None,
        search: Optional[str] = None,
        view_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lists tasks for team with status counts and meeting distinct list.
        Enforces strict role-based visibility:
        - Team Leaders see all tasks in their team (or filter by view_mode='my' / assigned_member_id).
        - Team Members see ONLY tasks assigned to them.
        """
        tasks_col = get_col("tasks")
        access = TaskService.resolve_user_access(team_id, current_user)
        is_leader = access["is_leader"]
        assignee_filter = access["assignee_filter"]

        and_clauses: List[Dict[str, Any]] = [{"team_id": team_id}]

        if not is_leader:
            and_clauses.append(assignee_filter)
        elif view_mode == "my":
            and_clauses.append(assignee_filter)

        if status and status.lower() != "all":
            and_clauses.append({"status": status})

        if priority and priority.lower() != "all":
            and_clauses.append({"priority": priority})

        if is_leader and assigned_member_id and assigned_member_id.lower() != "all":
            and_clauses.append({"assigned_member_id": assigned_member_id})

        if meeting_id and meeting_id.lower() != "all":
            and_clauses.append({"meeting_id": meeting_id})

        if approval_status and approval_status.lower() != "all":
            and_clauses.append({"approval_status": approval_status})

        if search and search.strip():
            term = search.strip()
            and_clauses.append({
                "$or": [
                    {"title": {"$regex": term, "$options": "i"}},
                    {"description": {"$regex": term, "$options": "i"}},
                    {"task_id": {"$regex": term, "$options": "i"}},
                    {"assigned_member_name": {"$regex": term, "$options": "i"}},
                    {"meeting_title": {"$regex": term, "$options": "i"}}
                ]
            })

        query: Dict[str, Any] = {"$and": and_clauses} if len(and_clauses) > 1 else and_clauses[0]

        cursor = tasks_col.find(query).sort([("order", 1), ("created_at", -1)])
        tasks = []
        meetings_set = set()

        for doc in cursor:
            doc["id"] = str(doc["_id"])
            m_title = doc.get("meeting_title")
            if m_title:
                meetings_set.add(m_title)
            tasks.append(doc)

        # Counts scoped strictly to accessible tasks for this user's role
        base_clauses: List[Dict[str, Any]] = [{"team_id": team_id}]
        if not is_leader or view_mode == "my":
            base_clauses.append(assignee_filter)
        team_base_query: Dict[str, Any] = {"$and": base_clauses} if len(base_clauses) > 1 else base_clauses[0]

        todo_count = tasks_col.count_documents({"$and": [team_base_query, {"status": "To Do"}]})
        in_prog_count = tasks_col.count_documents({"$and": [team_base_query, {"status": "In Progress"}]})
        review_count = tasks_col.count_documents({"$and": [team_base_query, {"status": "Review"}]})
        comp_count = tasks_col.count_documents({"$and": [team_base_query, {"status": "Completed"}]})
        awaiting_approval_count = tasks_col.count_documents({"$and": [team_base_query, {"approval_status": "Awaiting Approval"}]})
        total_count = tasks_col.count_documents(team_base_query)

        return {
            "tasks": tasks,
            "counts": {
                "todo": todo_count,
                "in_progress": in_prog_count,
                "review": review_count,
                "completed": comp_count,
                "awaiting_approval": awaiting_approval_count,
                "total": total_count
            },
            "meetings": sorted(list(meetings_set))
        }

    @staticmethod
    def get_task(team_id: str, task_id: str, current_user: Optional[dict] = None) -> Dict[str, Any]:
        tasks_col = get_col("tasks")
        doc = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

        if current_user is not None:
            access = TaskService.resolve_user_access(team_id, current_user)
            if not access["is_leader"]:
                doc_member_id = doc.get("assigned_member_id")
                doc_email = (doc.get("assigned_member_email") or "").strip().lower()
                is_owner = (
                    (access["current_member_id"] and doc_member_id == access["current_member_id"])
                    or (access["user_email"] and doc_email == access["user_email"])
                )
                if not is_owner:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied: You are only authorized to view tasks assigned to you."
                    )

        doc["id"] = str(doc["_id"])
        return doc

    @staticmethod
    def update_task_status(
        team_id: str,
        task_id: str,
        current_user: dict,
        new_status: str,
        order: Optional[int] = None,
        trigger_automation: bool = True,
    ) -> Dict[str, Any]:
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{new_status}'. Allowed: {', '.join(VALID_STATUSES)}"
            )

        tasks_col = get_col("tasks")
        task = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")

        # Permission check: Team Leader or assigned team member can update status
        access = TaskService.resolve_user_access(team_id, current_user)
        is_admin = access["is_leader"]
        is_assignee = (
            (access["current_member_id"] and task.get("assigned_member_id") == access["current_member_id"])
            or (access["user_email"] and (task.get("assigned_member_email") or "").strip().lower() == access["user_email"])
        )
        if not is_admin and not is_assignee:
            raise HTTPException(
                status_code=403,
                detail="You are only authorized to update the status of tasks assigned to you."
            )

        if new_status != "To Do" and str(task.get("approval_status") or "").lower() != "approved":
            raise HTTPException(
                status_code=400,
                detail=f"Task must be approved by the Team Leader before moving to '{new_status}'."
            )

        if new_status == "Completed" and not is_assignee:
            raise HTTPException(
                status_code=403,
                detail="Only the assigned team member can complete this task."
            )

        old_status = task.get("status")
        if new_status == old_status and order is None:
            return TaskService.get_task(team_id, task_id, current_user=current_user)

        now = datetime.utcnow()
        update_fields: Dict[str, Any] = {"status": new_status, "updated_at": now}
        if order is not None:
            update_fields["order"] = int(order)
        completed_by_info = {
            "member_id": access.get("current_member_id") or current_user.get("user_id", ""),
            "name": current_user.get("name") or task.get("assigned_member_name") or "Team Member",
            "email": (current_user.get("email") or task.get("assigned_member_email") or "").strip().lower(),
        }
        if new_status == "Completed" and old_status != "Completed":
            update_fields["completed_at"] = now
            update_fields["completed_by_id"] = completed_by_info["member_id"]
            update_fields["completed_by_name"] = completed_by_info["name"]
            update_fields["completed_by_email"] = completed_by_info["email"]

        if new_status == "Completed":
            owner_clauses = []
            if access.get("current_member_id"):
                owner_clauses.append({"assigned_member_id": access["current_member_id"]})
            if access.get("user_email"):
                owner_clauses.append({
                    "assigned_member_email": {
                        "$regex": f"^{re.escape(access['user_email'])}$",
                        "$options": "i"
                    }
                })
            update_result = tasks_col.update_one(
                {
                    "_id": task["_id"],
                    "status": {"$ne": "Completed"},
                    "approval_status": {"$in": ["Approved", "approved"]},
                    "$or": owner_clauses
                },
                {"$set": update_fields}
            )
            if update_result.matched_count == 0:
                latest = tasks_col.find_one({"_id": task["_id"]})
                if latest and latest.get("status") == "Completed":
                    return TaskService.get_task(team_id, task_id, current_user=current_user)
                raise HTTPException(
                    status_code=409,
                    detail="Task assignment or status changed. Refresh and try again."
                )
        else:
            tasks_col.update_one({"_id": task["_id"]}, {"$set": update_fields})
        updated_doc = TaskService.get_task(team_id, task_id)

        # Trigger Zapier Task Completed Webhook ONLY on explicit completion (never on drag-and-drop)
        if trigger_automation and new_status == "Completed" and old_status != "Completed":
            dispatch_webhook_in_background(
                ZapierService.send_task_completed_webhook(
                    updated_doc,
                    completed_by=completed_by_info
                )
            )

        return updated_doc

    @staticmethod
    def update_task(team_id: str, task_id: str, current_user: dict, req: TaskUpdateRequest) -> Dict[str, Any]:
        tasks_col = get_col("tasks")
        member_col = get_col("member_profiles")

        task = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")

        access = TaskService.resolve_user_access(team_id, current_user)
        is_admin = access["is_leader"]
        is_assignee = (
            (access["current_member_id"] and task.get("assigned_member_id") == access["current_member_id"])
            or (access["user_email"] and (task.get("assigned_member_email") or "").strip().lower() == access["user_email"])
        )
        old_status = task.get("status")

        if req.approval_status is not None:
            raise HTTPException(
                status_code=403,
                detail="Use the Team Leader approval or rejection action to change approval status."
            )
        completing_task = req.status == "Completed" and old_status != "Completed"
        if completing_task and str(task.get("approval_status") or "").lower() != "approved":
            raise HTTPException(
                status_code=400,
                detail="Only approved tasks can be marked as Completed."
            )
        if completing_task and (is_admin or not is_assignee):
            raise HTTPException(
                status_code=403,
                detail="Only the assigned team member can complete this task."
            )
        if (
            completing_task
            and req.assigned_member_id is not None
            and req.assigned_member_id != task.get("assigned_member_id")
        ):
            raise HTTPException(
                status_code=403,
                detail="A task cannot be reassigned and completed in the same action."
            )

        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}

        if req.status is not None:
            if req.status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status '{req.status}'")
            updates["status"] = req.status

        # If not admin, can only update status and description
        if not is_admin:
            if not is_assignee:
                raise HTTPException(status_code=403, detail="Unauthorized to edit this task.")
            if req.description is not None:
                updates["description"] = req.description.strip()
        else:
            # Admin can edit all fields
            if req.title is not None:
                updates["title"] = req.title.strip()
            if req.description is not None:
                updates["description"] = req.description.strip()
            if req.priority is not None:
                if req.priority not in VALID_PRIORITIES:
                    raise HTTPException(status_code=400, detail=f"Invalid priority '{req.priority}'")
                updates["priority"] = req.priority
            if req.deadline is not None:
                updates["deadline"] = req.deadline.strip() if req.deadline else None
            if req.meeting_title is not None:
                updates["meeting_title"] = req.meeting_title.strip()
            if req.required_skills is not None:
                updates["required_skills"] = req.required_skills

            # Handle reassignment of member
            if req.assigned_member_id is not None:
                old_member_id = task.get("assigned_member_id")
                new_member_id = req.assigned_member_id

                if old_member_id != new_member_id:
                    # Remove from old member
                    if old_member_id:
                        member_col.update_one(
                            {"team_id": team_id, "member_id": old_member_id},
                            {"$pull": {"assigned_tasks": task_id}}
                        )
                    # Lookup and attach new member
                    m_name, m_role, m_email = TaskService._find_member_details(team_id, new_member_id)
                    updates["assigned_member_id"] = new_member_id
                    updates["assigned_member_name"] = m_name
                    updates["assigned_member_role"] = m_role
                    updates["assigned_member_email"] = m_email

                    if new_member_id:
                        member_col.update_one(
                            {"team_id": team_id, "member_id": new_member_id},
                            {"$addToSet": {"assigned_tasks": task_id}}
                        )

        completed_by_info = None
        if completing_task:
            completed_by_info = {
                "member_id": access.get("current_member_id") or current_user.get("user_id", ""),
                "name": current_user.get("name") or task.get("assigned_member_name") or "Team Member",
                "email": (current_user.get("email") or task.get("assigned_member_email") or "").strip().lower(),
            }
            updates["completed_at"] = datetime.utcnow()
            updates["completed_by_id"] = completed_by_info["member_id"]
            updates["completed_by_name"] = completed_by_info["name"]
            updates["completed_by_email"] = completed_by_info["email"]

            owner_clauses = []
            if access.get("current_member_id"):
                owner_clauses.append({"assigned_member_id": access["current_member_id"]})
            if access.get("user_email"):
                owner_clauses.append({
                    "assigned_member_email": {
                        "$regex": f"^{re.escape(access['user_email'])}$",
                        "$options": "i"
                    }
                })
            update_result = tasks_col.update_one(
                {
                    "_id": task["_id"],
                    "status": {"$ne": "Completed"},
                    "approval_status": {"$in": ["Approved", "approved"]},
                    "$or": owner_clauses
                },
                {"$set": updates}
            )
            if update_result.matched_count == 0:
                latest = tasks_col.find_one({"_id": task["_id"]})
                if latest and latest.get("status") == "Completed":
                    return TaskService.get_task(team_id, task_id, current_user=current_user)
                raise HTTPException(
                    status_code=409,
                    detail="Task assignment or status changed. Refresh and try again."
                )
        else:
            tasks_col.update_one({"_id": task["_id"]}, {"$set": updates})
        updated_doc = TaskService.get_task(team_id, task_id)

        # Trigger webhook if newly marked Completed
        if completing_task and completed_by_info:
            dispatch_webhook_in_background(
                ZapierService.send_task_completed_webhook(
                    updated_doc,
                    completed_by=completed_by_info
                )
            )

        return updated_doc

    @staticmethod
    def delete_task(team_id: str, task_id: str, current_user: dict) -> bool:
        user_role = current_user.get("role", "Member")
        is_admin = user_role.lower() in ["admin", "team lead", "manager", "team lead / admin"]
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only administrators can delete tasks.")

        tasks_col = get_col("tasks")
        member_col = get_col("member_profiles")

        task = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")

        # Remove from assigned member
        if task.get("assigned_member_id"):
            member_col.update_one(
                {"team_id": team_id, "member_id": task["assigned_member_id"]},
                {"$pull": {"assigned_tasks": task_id}}
            )

        tasks_col.delete_one({"_id": task["_id"]})
        return True

    @staticmethod
    def approve_task(team_id: str, task_id: str, current_user: dict) -> Dict[str, Any]:
        """
        Human Approval Workflow:
        Validates the task, marks approval_status='Approved', assigns member,
        and triggers Zapier task_approved webhook (ZAP 1).
        """
        TaskService.require_team_leader(team_id, current_user)

        tasks_col = get_col("tasks")
        member_col = get_col("member_profiles")

        task = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

        current_approval = str(task.get("approval_status") or "").strip().lower()
        if current_approval == "approved":
            return TaskService.get_task(team_id, task_id)
        if current_approval not in {"pending", "awaiting approval", "needs review"}:
            raise HTTPException(status_code=409, detail="Only pending tasks can be approved.")

        now = datetime.utcnow()
        update_result = tasks_col.update_one(
            {
                "_id": task["_id"],
                "approval_status": {
                    "$in": [
                        "Pending", "pending",
                        "Awaiting Approval", "awaiting approval",
                        "Needs Review", "needs review"
                    ]
                }
            },
            {
                "$set": {
                    "approval_status": "Approved",
                    "approved_by": current_user.get("user_id"),
                    "approved_by_name": current_user.get("name", "Admin"),
                    "approved_at": now,
                    "updated_at": now
                }
            }
        )
        if update_result.matched_count == 0:
            latest = tasks_col.find_one({"_id": task["_id"]})
            if latest and str(latest.get("approval_status") or "").strip().lower() == "approved":
                return TaskService.get_task(team_id, task_id)
            raise HTTPException(status_code=409, detail="Task approval status changed. Refresh and try again.")

        # Attach to member profile assigned_tasks if member exists
        if task.get("assigned_member_id"):
            member_col.update_one(
                {"team_id": team_id, "member_id": task["assigned_member_id"]},
                {"$addToSet": {"assigned_tasks": task_id}}
            )

        updated_doc = TaskService.get_task(team_id, task_id)

        # Trigger Zapier Approved Task Webhook
        dispatch_webhook_in_background(
            ZapierService.send_task_approved_webhook(
                updated_doc,
                approved_by_name=current_user.get("name", "Admin")
            )
        )

        return updated_doc

    @staticmethod
    def reject_task(team_id: str, task_id: str, current_user: dict) -> Dict[str, Any]:
        """Rejects an AI-recommended task."""
        TaskService.require_team_leader(team_id, current_user)

        tasks_col = get_col("tasks")
        task = tasks_col.find_one({"team_id": team_id, "task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

        current_approval = str(task.get("approval_status") or "").strip().lower()
        if current_approval == "rejected":
            return TaskService.get_task(team_id, task_id)
        if current_approval not in {"pending", "awaiting approval", "needs review"}:
            raise HTTPException(status_code=409, detail="Only pending tasks can be rejected.")

        update_result = tasks_col.update_one(
            {
                "_id": task["_id"],
                "approval_status": {
                    "$in": [
                        "Pending", "pending",
                        "Awaiting Approval", "awaiting approval",
                        "Needs Review", "needs review"
                    ]
                }
            },
            {
                "$set": {
                    "approval_status": "Rejected",
                    "rejected_by": current_user.get("user_id"),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if update_result.matched_count == 0:
            latest = tasks_col.find_one({"_id": task["_id"]})
            if latest and str(latest.get("approval_status") or "").strip().lower() == "rejected":
                return TaskService.get_task(team_id, task_id)
            raise HTTPException(status_code=409, detail="Task approval status changed. Refresh and try again.")
        return TaskService.get_task(team_id, task_id)
