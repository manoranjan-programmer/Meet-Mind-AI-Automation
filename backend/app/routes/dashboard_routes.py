from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user
from app.database.mongo import get_col
from app.services.task_service import TaskService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    team_id = current_user["team_id"]
    
    member_col = get_col("member_profiles")
    meetings_col = get_col("meetings")
    tasks_col = get_col("tasks")
    
    # Member stats
    total_members = member_col.count_documents({"team_id": team_id})
    available_members = member_col.count_documents({"team_id": team_id, "availability": "Available"})
    busy_members = member_col.count_documents({"team_id": team_id, "availability": "Busy"})
    
    # Meeting stats
    total_meetings = meetings_col.count_documents({"team_id": team_id})
    
    # Role-based task scope: Team Leaders see all team tasks; Team Members see only their assigned tasks
    access = TaskService.resolve_user_access(team_id, current_user)
    task_scope = (
        {"team_id": team_id}
        if access["is_leader"]
        else {"$and": [{"team_id": team_id}, access["assignee_filter"]]}
    )

    total_tasks = tasks_col.count_documents(task_scope)
    pending_tasks = tasks_col.count_documents({"$and": [task_scope, {"approval_status": {"$in": ["Pending", "Needs Review", "Awaiting Approval"]}}]})
    approved_tasks = tasks_col.count_documents({"$and": [task_scope, {"approval_status": "Approved"}]})
    completed_tasks = tasks_col.count_documents({"$and": [task_scope, {"status": "Completed"}]})

    # Recent meetings
    recent_meetings_cur = meetings_col.find({"team_id": team_id}).sort("created_at", -1).limit(5)
    recent_meetings = []
    for m in recent_meetings_cur:
        recent_meetings.append({
            "meeting_id": m.get("meeting_id"),
            "title": m.get("title", "Untitled Meeting"),
            "date": m.get("created_at"),
            "duration": m.get("duration", "0:00"),
            "status": m.get("status", "Completed")
        })

    # Recent members
    recent_members_cur = member_col.find({"team_id": team_id}).sort("created_at", -1).limit(5)
    recent_members = []
    for rm in recent_members_cur:
        recent_members.append({
            "member_id": rm.get("member_id"),
            "name": rm.get("name"),
            "role": rm.get("role"),
            "availability": rm.get("availability"),
            "registration_method": rm.get("registration_method", "manual")
        })

    # Recent tasks (scoped to user role)
    recent_tasks_cur = tasks_col.find(task_scope).sort("created_at", -1).limit(5)
    recent_tasks = []
    for rt in recent_tasks_cur:
        recent_tasks.append({
            "task_id": rt.get("task_id"),
            "title": rt.get("title"),
            "assigned_member_name": rt.get("assigned_member_name", "Unassigned"),
            "priority": rt.get("priority", "Medium"),
            "status": rt.get("status", "To Do"),
            "deadline": rt.get("deadline")
        })

    return {
        "total_members": total_members,
        "available_members": available_members,
        "busy_members": busy_members,
        "total_meetings": total_meetings,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "approved_tasks": approved_tasks,
        "completed_tasks": completed_tasks,
        "recent_meetings": recent_meetings,
        "recent_members": recent_members,
        "recent_tasks": recent_tasks
    }
