import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.utils.security import create_access_token
from app.database.mongo import get_col
from app.services.scheduler_service import SchedulerService
from app.services.chat_service import ChatService, chat_manager
from app.services.webrtc_service import meeting_signaling_manager
from app.agents.transcription_agent import TranscriptionAgent
from app.agents.task_extraction_agent import TaskExtractionAgent

client = TestClient(app)

@pytest.fixture
def mock_team_lead():
    user_id = "test_lead_001"
    email = "leader@meetmind.ai"
    team_id = "team_alpha"
    role = "Team Leader"
    
    # Ensure user exists in test db
    users_col = get_col("users")
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "email": email, "team_id": team_id, "role": role, "name": "Team Leader Alpha"}},
        upsert=True
    )
    
    token = create_access_token({"user_id": user_id, "email": email, "team_id": team_id, "role": role})
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "team_id": team_id}

@pytest.fixture
def mock_viewer_different_team():
    user_id = "test_viewer_999"
    email = "viewer@otherteam.ai"
    team_id = "team_beta"
    role = "Viewer"
    
    users_col = get_col("users")
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "email": email, "team_id": team_id, "role": role, "name": "Viewer Beta"}},
        upsert=True
    )
    token = create_access_token({"user_id": user_id, "email": email, "team_id": team_id, "role": role})
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "team_id": team_id}

def test_workspace_chat_access_and_isolation(mock_team_lead, mock_viewer_different_team):
    # 1. Team Leader sends message to their team workspace
    send_res = client.post(
        f"/api/workspaces/{mock_team_lead['team_id']}/chat/messages",
        headers=mock_team_lead["headers"],
        json={"content": "Hello Team Alpha! Real-time workspace chat is live."}
    )
    assert send_res.status_code == 201
    msg_data = send_res.json()
    assert msg_data["content"] == "Hello Team Alpha! Real-time workspace chat is live."
    assert msg_data["team_id"] == "team_alpha"

    # 2. Team Leader fetches messages
    get_res = client.get(
        f"/api/workspaces/{mock_team_lead['team_id']}/chat/messages",
        headers=mock_team_lead["headers"]
    )
    assert get_res.status_code == 200
    assert len(get_res.json()["messages"]) >= 1

    # 3. User from different team is strictly denied access
    forbidden_res = client.get(
        f"/api/workspaces/{mock_team_lead['team_id']}/chat/messages",
        headers=mock_viewer_different_team["headers"]
    )
    assert forbidden_res.status_code == 403
    assert "Access denied" in forbidden_res.json()["detail"]

def test_natural_language_meeting_scheduler(mock_team_lead):
    # 1. Parse natural language command
    parse_res = client.post(
        "/api/meetings/schedule/parse-command",
        headers=mock_team_lead["headers"],
        json={
            "command": "Schedule a Sprint Planning meeting tomorrow at 10 PM with all active team members.",
            "timezone": "Asia/Kolkata"
        }
    )
    assert parse_res.status_code == 200
    preview = parse_res.json()
    assert preview["status"] == "preview_ready"
    assert "extracted" in preview
    assert preview["extracted"]["meeting_title"] is not None

    # 2. Confirm and persist schedule
    get_col("scheduled_meetings").delete_many({"team_id": mock_team_lead["team_id"]})
    confirm_res = client.post(
        "/api/meetings/schedule",
        headers=mock_team_lead["headers"],
        json={
            "meeting_title": "Sprint Planning Meeting",
            "agenda": "Review sprint backlog and architecture",
            "date": "2026-11-26",
            "time": "22:00",
            "timezone": "Asia/Kolkata",
            "duration_minutes": 45,
            "selected_participant_ids": []
        }
    )
    assert confirm_res.status_code == 201
    created_meeting = confirm_res.json()
    assert created_meeting["meeting_status"] == "scheduled"
    assert created_meeting["room_id"].startswith("room_")

    # 3. Retrieve upcoming meetings list
    upcoming_res = client.get("/api/meetings/upcoming", headers=mock_team_lead["headers"])
    assert upcoming_res.status_code == 200
    upcoming_data = upcoming_res.json()
    assert upcoming_data["total"] >= 1
    assert any(m["meeting_id"] == created_meeting["meeting_id"] for m in upcoming_data["upcoming_meetings"])

def test_webrtc_ice_servers_endpoint(mock_team_lead):
    res = client.get("/api/meetings/ice-servers", headers=mock_team_lead["headers"])
    assert res.status_code == 200
    data = res.json()
    assert "ice_servers" in data
    assert len(data["ice_servers"]) >= 1
    assert data["topology"] == "mesh"

def test_vad_silence_detection():
    # Audio with no clear speech should trigger VAD warning and produce 0 fake tasks
    transcript_empty = ""
    ext_res = TaskExtractionAgent.execute(transcript_text=transcript_empty, diarized_segments=[])
    assert ext_res["status"] == "success"
    # Never invent tasks from empty transcript
    assert ext_res["extracted_tasks"] == []
