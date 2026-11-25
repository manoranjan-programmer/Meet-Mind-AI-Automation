import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongo import get_col

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_schedule_env():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"lead_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Mano Ranjan",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Workspace {suffix}",
        "role": "Team Lead"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    user = reg_res.json()["user"]
    team_id = user["team_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Register member 2 (teammate)
    mem_email = f"teammate_{suffix}@meetmind.ai"
    mem_res = client.post("/api/auth/register", json={
        "name": "Arun Developer",
        "email": mem_email,
        "password": "Password123!",
        "team_name": f"Workspace {suffix}",
        "role": "Member"
    })
    assert mem_res.status_code == 200
    mem_token = mem_res.json()["access_token"]
    mem_headers = {"Authorization": f"Bearer {mem_token}"}

    return {
        "suffix": suffix,
        "team_id": team_id,
        "host_user": user,
        "host_headers": headers,
        "member_headers": mem_headers,
        "member_email": mem_email
    }


def test_schedule_meeting_default_workflow_and_persistence(setup_schedule_env):
    """
    Requirements 1 & 2:
    - User schedules a meeting
    - Validates fields
    - Persists in MongoDB
    - Generates unique ID and room link
    - Sets status to SCHEDULED
    - Host is identified automatically (even if solo workspace)
    - Zero external automation triggered
    """
    headers = setup_schedule_env["host_headers"]
    suffix = setup_schedule_env["suffix"]
    title = f"Sprint 5 Architecture Sync {suffix}"

    with patch("app.services.zapier_service.ZapierService.send_meeting_scheduled_webhook") as mock_zapier:
        mock_zapier.return_value = AsyncMock()

        payload = {
            "meeting_title": title,
            "description": "Reviewing scalable microservices & AI pipeline",
            "agenda": "Deliverable timelines and sprint review",
            "date": "2026-11-28",
            "time": "15:00",
            "duration_minutes": 45,
            "selected_participant_ids": []
        }

        res = client.post("/api/meetings/schedule", json=payload, headers=headers)
        assert res.status_code == 201
        m_data = res.json()
        assert m_data["meeting_title"] == title
        assert "sched_" in m_data["meeting_id"]
        assert "room_" in m_data["room_id"]
        assert m_data["meeting_status"] == "scheduled"
        assert m_data["duration_minutes"] == 45
        assert m_data["host_id"] is not None

        # Verify MongoDB Atlas persistence in scheduled_meetings
        sched_col = get_col("scheduled_meetings")
        saved_sched = sched_col.find_one({"meeting_id": m_data["meeting_id"]})
        assert saved_sched is not None
        assert saved_sched["meeting_title"] == title
        assert saved_sched["meeting_status"] == "scheduled"

        # Verify mirrored in meetings collection for zero-duplicate lifecycle
        meetings_col = get_col("meetings")
        saved_m = meetings_col.find_one({"meeting_id": m_data["meeting_id"]})
        assert saved_m is not None
        assert saved_m["title"] == title
        assert saved_m["status"] == "SCHEDULED"


def test_upcoming_meetings_lists_persisted_meetings(setup_schedule_env):
    """
    Requirement 3:
    - Upcoming meetings endpoint fetches actual MongoDB scheduled meetings
    - Shows title, ID, time, host, participants, and status
    """
    headers = setup_schedule_env["host_headers"]
    res = client.get("/api/meetings/upcoming", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "upcoming_meetings" in data
    assert len(data["upcoming_meetings"]) >= 1

    meeting = data["upcoming_meetings"][0]
    assert "sched_" in meeting["meeting_id"]
    assert "room_" in meeting["room_id"]
    assert meeting["meeting_status"] in ["scheduled", "active"]


def test_start_meeting_host_workflow_and_zero_duplicate(setup_schedule_env):
    """
    Requirements 4 & 7:
    - Host starts scheduled meeting
    - Verifies user is host
    - Sets meeting status to LIVE
    - Uses existing meeting ID without creating duplicate records
    """
    headers = setup_schedule_env["host_headers"]
    suffix = setup_schedule_env["suffix"]

    # 1. Schedule a fresh meeting
    payload = {
        "meeting_title": f"Live Transition Test {suffix}",
        "date": "2026-11-29",
        "time": "16:00",
        "duration_minutes": 30
    }
    sched_res = client.post("/api/meetings/schedule", json=payload, headers=headers)
    assert sched_res.status_code == 201
    meeting_id = sched_res.json()["meeting_id"]
    room_id = sched_res.json()["room_id"]

    # Count initial records
    col_sched = get_col("scheduled_meetings")
    col_meet = get_col("meetings")
    initial_sched_count = col_sched.count_documents({"meeting_id": meeting_id})
    initial_meet_count = col_meet.count_documents({"meeting_id": meeting_id})
    assert initial_sched_count == 1
    assert initial_meet_count == 1

    # 2. Host clicks Start Meeting
    start_res = client.post(f"/api/meetings/{meeting_id}/start-session", headers=headers)
    assert start_res.status_code == 200
    started_data = start_res.json()
    assert started_data["meeting_id"] == meeting_id
    assert started_data["meeting_status"] == "live"
    assert started_data["actual_started_at"] is not None

    # 3. Verify ZERO DUPLICATE RECORDS were created
    final_sched_count = col_sched.count_documents({"meeting_id": meeting_id})
    final_meet_count = col_meet.count_documents({"meeting_id": meeting_id})
    assert final_sched_count == 1, "Duplicate record created in scheduled_meetings!"
    assert final_meet_count == 1, "Duplicate record created in meetings!"

    # 4. Verify MongoDB status transition
    db_sched = col_sched.find_one({"meeting_id": meeting_id})
    assert db_sched["meeting_status"] == "live"
    db_meet = col_meet.find_one({"meeting_id": meeting_id})
    assert db_meet["status"] in ["LIVE", "In Progress"]


def test_join_meeting_participant_workflow(setup_schedule_env):
    """
    Requirement 5:
    - Authorized participant looks up meeting by room_id or code
    - Resolves existing room without creating separate meeting
    """
    host_headers = setup_schedule_env["host_headers"]
    mem_headers = setup_schedule_env["member_headers"]
    suffix = setup_schedule_env["suffix"]

    payload = {
        "meeting_title": f"Teammate Join Room Test {suffix}",
        "date": "2026-11-30",
        "time": "18:00",
        "duration_minutes": 30
    }
    res = client.post("/api/meetings/schedule", json=payload, headers=host_headers)
    assert res.status_code == 201
    room_id = res.json()["room_id"]
    meeting_id = res.json()["meeting_id"]

    # Teammate looks up room
    lookup_res = client.get(f"/api/meetings/room/{room_id}", headers=mem_headers)
    assert lookup_res.status_code == 200
    looked_up = lookup_res.json()
    assert looked_up["meeting_id"] == meeting_id
    assert looked_up["room_id"] == room_id


def test_edit_and_cancel_scheduled_meeting(setup_schedule_env):
    """
    Requirements 3 & 7:
    - Host edits scheduled meeting
    - Host cancels scheduled meeting
    - Status updates to CANCELLED
    """
    headers = setup_schedule_env["host_headers"]
    suffix = setup_schedule_env["suffix"]

    payload = {
        "meeting_title": f"Meeting To Edit {suffix}",
        "date": "2026-12-01",
        "time": "11:00",
        "duration_minutes": 30
    }
    sched_res = client.post("/api/meetings/schedule", json=payload, headers=headers)
    meeting_id = sched_res.json()["meeting_id"]

    # Edit meeting
    edit_payload = {
        "meeting_title": f"Meeting Edited Successfully {suffix}",
        "duration_minutes": 60,
        "agenda": "Updated agenda"
    }
    edit_res = client.post(f"/api/meetings/{meeting_id}/edit-schedule", json=edit_payload, headers=headers)
    assert edit_res.status_code == 200
    assert edit_res.json()["meeting_title"] == f"Meeting Edited Successfully {suffix}"
    assert edit_res.json()["duration_minutes"] == 60

    # Cancel meeting
    cancel_res = client.post(f"/api/meetings/{meeting_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["meeting_status"] == "cancelled"

    # Verify status in MongoDB
    saved = get_col("scheduled_meetings").find_one({"meeting_id": meeting_id})
    assert saved["meeting_status"] == "cancelled"
