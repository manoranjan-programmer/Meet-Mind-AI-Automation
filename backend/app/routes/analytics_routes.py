from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user
from app.database.mongo import get_col

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/metrics")
def get_analytics_metrics(current_user: dict = Depends(get_current_user)):
    team_id = current_user["team_id"]
    tasks_col = get_col("tasks")
    members_col = get_col("member_profiles")
    meetings_col = get_col("meetings")

    # Tasks by status
    todo = tasks_col.count_documents({"team_id": team_id, "status": "To Do"})
    in_progress = tasks_col.count_documents({"team_id": team_id, "status": "In Progress"})
    review = tasks_col.count_documents({"team_id": team_id, "status": "Review"})
    completed = tasks_col.count_documents({"team_id": team_id, "status": "Completed"})
    total_tasks = tasks_col.count_documents({"team_id": team_id})

    # Priority distribution
    critical = tasks_col.count_documents({"team_id": team_id, "priority": "Critical"})
    high = tasks_col.count_documents({"team_id": team_id, "priority": "High"})
    medium = tasks_col.count_documents({"team_id": team_id, "priority": "Medium"})
    low = tasks_col.count_documents({"team_id": team_id, "priority": "Low"})

    # Team members
    total_members = members_col.count_documents({"team_id": team_id})
    available_members = members_col.count_documents({"team_id": team_id, "availability": "Available"})
    busy_members = members_col.count_documents({"team_id": team_id, "availability": "Busy"})

    # Completion rate
    completion_rate = round((completed / total_tasks * 100), 1) if total_tasks > 0 else 0.0

    return {
        "total_tasks": total_tasks,
        "completion_rate": completion_rate,
        "status_distribution": [
            {"status": "To Do", "count": todo, "color": "#F59E0B"},
            {"status": "In Progress", "count": in_progress, "color": "#2563EB"},
            {"status": "Review", "count": review, "color": "#7C3AED"},
            {"status": "Completed", "count": completed, "color": "#059669"}
        ],
        "priority_distribution": [
            {"priority": "Critical", "count": critical, "color": "#EF4444"},
            {"priority": "High", "count": high, "color": "#F59E0B"},
            {"priority": "Medium", "count": medium, "color": "#2563EB"},
            {"priority": "Low", "count": low, "color": "#94A3B8"}
        ],
        "team_metrics": {
            "total_members": total_members,
            "available_members": available_members,
            "busy_members": busy_members
        }
    }
