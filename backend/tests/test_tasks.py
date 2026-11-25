import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongo import get_col

client = TestClient(app)

def test_complete_task_management_flow():
    # 1. Register an Admin
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"lead_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Sarah Connor",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Tasks Team {suffix}",
        "role": "Admin"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    team_id = reg_res.json()["user"]["team_id"]
    admin_headers = {"Authorization": f"Bearer {token}"}

    # 2. Add two members manually
    m1_res = client.post("/api/team/members", json={
        "name": "Jai",
        "email": f"jai_{suffix}@example.com",
        "role": "Frontend Developer",
        "skills": ["React", "JavaScript"],
        "experience": "Intermediate",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=admin_headers)
    assert m1_res.status_code == 201
    jai_id = m1_res.json()["member_id"]

    m2_res = client.post("/api/team/members", json={
        "name": "Arun",
        "email": f"arun_{suffix}@example.com",
        "role": "Backend Developer",
        "skills": ["Python", "FastAPI", "MongoDB"],
        "experience": "Advanced",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=admin_headers)
    assert m2_res.status_code == 201
    arun_id = m2_res.json()["member_id"]

    # 3. Create a task assigned to Jai
    create_payload = {
        "title": "Develop login page using React",
        "description": "Build responsive dark theme login page with validation",
        "assigned_member_id": jai_id,
        "priority": "High",
        "deadline": "2026-12-01",
        "meeting_id": f"MTG-{suffix}",
        "meeting_title": "Sprint Planning #1",
        "required_skills": ["React", "JavaScript"]
    }
    task1_res = client.post("/api/tasks", json=create_payload, headers=admin_headers)
    assert task1_res.status_code == 201
    t1_data = task1_res.json()
    assert t1_data["title"] == "Develop login page using React"
    assert t1_data["assigned_member_name"] == "Jai"
    assert t1_data["assigned_member_role"] == "Frontend Developer"
    assert t1_data["status"] == "To Do"
    assert t1_data["approval_status"] == "Approved"
    task1_id = t1_data["task_id"]

    # Check that task was recorded in automation_logs
    logs_col = get_col("automation_logs")
    log_doc = logs_col.find_one({"task_id": task1_id})
    assert log_doc is not None
    assert log_doc["event_type"] == "task_approved"

    # 4. Create second task assigned to Arun
    create_payload_2 = {
        "title": "Build Auth API using FastAPI",
        "description": "JWT authentication and bcrypt password hashing",
        "assigned_member_id": arun_id,
        "priority": "Critical",
        "deadline": "2026-11-28",
        "meeting_title": "Sprint Planning #1",
        "required_skills": ["Python", "FastAPI"]
    }
    task2_res = client.post("/api/tasks", json=create_payload_2, headers=admin_headers)
    assert task2_res.status_code == 201
    task2_id = task2_res.json()["task_id"]

    # 5. Retrieve tasks with filters & check counts
    list_res = client.get("/api/tasks", headers=admin_headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data["tasks"]) == 2
    assert list_data["counts"]["todo"] == 2
    assert list_data["counts"]["total"] == 2
    assert "Sprint Planning #1" in list_data["meetings"]

    # Filter by priority "Critical"
    crit_res = client.get("/api/tasks?priority=Critical", headers=admin_headers)
    assert crit_res.status_code == 200
    assert len(crit_res.json()["tasks"]) == 1
    assert crit_res.json()["tasks"][0]["task_id"] == task2_id

    # Filter by assigned member (Jai)
    jai_tasks_res = client.get(f"/api/tasks?assigned_member_id={jai_id}", headers=admin_headers)
    assert jai_tasks_res.status_code == 200
    assert len(jai_tasks_res.json()["tasks"]) == 1
    assert jai_tasks_res.json()["tasks"][0]["task_id"] == task1_id

    # Search by title "login"
    search_res = client.get("/api/tasks?search=login", headers=admin_headers)
    assert search_res.status_code == 200
    assert len(search_res.json()["tasks"]) == 1

    # 6. Retrieve single task details
    single_res = client.get(f"/api/tasks/{task1_id}", headers=admin_headers)
    assert single_res.status_code == 200
    assert single_res.json()["task_id"] == task1_id

    # 7. Update status: To Do -> In Progress -> Review -> Completed
    st_res1 = client.patch(f"/api/tasks/{task1_id}/status", json={"status": "In Progress"}, headers=admin_headers)
    assert st_res1.status_code == 200
    assert st_res1.json()["status"] == "In Progress"

    st_res2 = client.patch(f"/api/tasks/{task1_id}/status", json={"status": "Review"}, headers=admin_headers)
    assert st_res2.status_code == 200
    assert st_res2.json()["status"] == "Review"

    st_res3 = client.patch(f"/api/tasks/{task1_id}/status", json={"status": "Completed"}, headers=admin_headers)
    assert st_res3.status_code == 200
    assert st_res3.json()["status"] == "Completed"

    # Verify counts reflect change
    counts_res = client.get("/api/tasks", headers=admin_headers)
    assert counts_res.json()["counts"]["completed"] == 1
    assert counts_res.json()["counts"]["todo"] == 1

    # Invalid status should return 400
    bad_st_res = client.patch(f"/api/tasks/{task1_id}/status", json={"status": "Done"}, headers=admin_headers)
    assert bad_st_res.status_code == 400

    # 8. Edit task details: Reassign task1 from Jai to Arun
    edit_res = client.patch(f"/api/tasks/{task1_id}", json={
        "title": "Develop login & 2FA page using React",
        "assigned_member_id": arun_id,
        "priority": "Medium"
    }, headers=admin_headers)
    assert edit_res.status_code == 200
    edited = edit_res.json()
    assert edited["title"] == "Develop login & 2FA page using React"
    assert edited["assigned_member_id"] == arun_id
    assert edited["assigned_member_name"] == "Arun"
    assert edited["assigned_member_role"] == "Backend Developer"
    assert edited["priority"] == "Medium"

    # Verify Jai's assigned_tasks no longer contains task1, and Arun's does
    member_col = get_col("member_profiles")
    jai_doc = member_col.find_one({"team_id": team_id, "member_id": jai_id})
    arun_doc = member_col.find_one({"team_id": team_id, "member_id": arun_id})
    assert task1_id not in (jai_doc.get("assigned_tasks") or [])
    assert task1_id in (arun_doc.get("assigned_tasks") or [])

    # 9. Delete task
    del_res = client.delete(f"/api/tasks/{task1_id}", headers=admin_headers)
    assert del_res.status_code == 200
    del_check = client.get(f"/api/tasks/{task1_id}", headers=admin_headers)
    assert del_check.status_code == 404
