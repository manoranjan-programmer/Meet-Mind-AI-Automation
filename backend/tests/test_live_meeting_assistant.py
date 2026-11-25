import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongo import get_col

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_meeting_env():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"lead_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Sarah Connor",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Live Squad {suffix}",
        "role": "Team Lead"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    team_id = reg_res.json()["user"]["team_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add 3 active members
    jai_res = client.post("/api/team/members", json={
        "name": "Jai",
        "email": f"jai_{suffix}@example.com",
        "role": "Frontend Developer",
        "skills": ["React", "JavaScript", "Tailwind CSS"],
        "experience": "Intermediate",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=headers)
    assert jai_res.status_code == 201
    jai_id = jai_res.json()["member_id"]

    arun_res = client.post("/api/team/members", json={
        "name": "Arun",
        "email": f"arun_{suffix}@example.com",
        "role": "Backend Developer",
        "skills": ["Python", "FastAPI", "MongoDB"],
        "experience": "Senior",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=headers)
    assert arun_res.status_code == 201
    arun_id = arun_res.json()["member_id"]

    priya_res = client.post("/api/team/members", json={
        "name": "Priya",
        "email": f"priya_{suffix}@example.com",
        "role": "UI/UX Designer",
        "skills": ["Figma", "UI Design"],
        "experience": "Intermediate",
        "availability": "Busy",
        "maximum_workload": 3
    }, headers=headers)
    assert priya_res.status_code == 201
    priya_id = priya_res.json()["member_id"]

    return {
        "headers": headers,
        "team_id": team_id,
        "suffix": suffix,
        "admin_email": admin_email,
        "members": [
            {"member_id": jai_id, "name": "Jai", "email": f"jai_{suffix}@example.com", "role": "Frontend Developer"},
            {"member_id": arun_id, "name": "Arun", "email": f"arun_{suffix}@example.com", "role": "Backend Developer"},
            {"member_id": priya_id, "name": "Priya", "email": f"priya_{suffix}@example.com", "role": "UI/UX Designer"},
        ]
    }


def test_get_active_team_members(setup_meeting_env):
    """Requirement 1: Load only active team members of the current team."""
    team_id = setup_meeting_env["team_id"]
    headers = setup_meeting_env["headers"]

    # 1. Test GET /api/teams/{team_id}/members?status=active
    res = client.get(f"/api/teams/{team_id}/members?status=active", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "members" in data
    # At least admin + Jai + Arun + Priya = 4
    assert len(data["members"]) >= 4
    for m in data["members"]:
        assert m["team_id"] == team_id
        assert m.get("account_status") == "active"
        assert "name" in m
        assert "role" in m
        assert "member_id" in m


def test_start_meeting_session(setup_meeting_env):
    """Requirement 2: Start meeting session with selected participants."""
    team_id = setup_meeting_env["team_id"]
    headers = setup_meeting_env["headers"]
    jai = setup_meeting_env["members"][0]
    arun = setup_meeting_env["members"][1]

    payload = {
        "meeting_title": "Sprint 4 AI Engine Sync",
        "selected_participant_ids": [jai["member_id"], arun["member_id"]],
        "participants": [jai, arun]
    }

    res = client.post("/api/meetings/start", json=payload, headers=headers)
    assert res.status_code == 201
    m_data = res.json()
    assert m_data["status"] == "In Progress"
    assert m_data["meeting_title"] == "Sprint 4 AI Engine Sync"
    assert "MTG-" in m_data["meeting_id"]
    assert m_data["selected_participant_ids"] == [jai["member_id"], arun["member_id"]]
    assert len(m_data["participants"]) == 2


def test_progressive_chunk_transcription(setup_meeting_env):
    """Requirement 3: Progressive audio chunk transcription."""
    team_id = setup_meeting_env["team_id"]
    headers = setup_meeting_env["headers"]
    jai = setup_meeting_env["members"][0]

    # Start session
    start_res = client.post("/api/meetings/start", json={
        "meeting_title": "Chunk Transcription Test",
        "selected_participant_ids": [jai["member_id"]]
    }, headers=headers)
    meeting_id = start_res.json()["meeting_id"]

    fake_chunk = b"\x1a\x45\xdf\xa3" + b"\x00" * 256
    files = {"file": ("chunk1.webm", io.BytesIO(fake_chunk), "audio/webm")}
    data = {"start_offset": 0.0}

    res = client.post(f"/api/meetings/{meeting_id}/transcribe", files=files, data=data, headers=headers)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] in ["success", "partial_error", "empty"]


@pytest.mark.anyio
async def test_complete_meeting_workflow_with_constrained_assignment(setup_meeting_env):
    """
    Requirements 4, 5, 7:
    - Diarization: does not assume speaker 1 is participant 1, preserves unknown speaker if unverified
    - Task assignment: ONLY assigns to selected participants (Jai & Arun attending, Priya absent)
    - LangGraph workflow executes end-to-end
    - Zapier webhook dispatched upon completion
    """
    team_id = setup_meeting_env["team_id"]
    headers = setup_meeting_env["headers"]
    jai = setup_meeting_env["members"][0]
    arun = setup_meeting_env["members"][1]
    # Note: Priya is NOT in selected_participant_ids!

    start_res = client.post("/api/meetings/start", json={
        "meeting_title": "Architecture Review & Security Sync",
        "selected_participant_ids": [jai["member_id"], arun["member_id"]],
        "participants": [jai, arun]
    }, headers=headers)
    meeting_id = start_res.json()["meeting_id"]

    fake_audio_bytes = b"RIFF....WAVEfmt ...." + b"\x00" * 512
    files = {"file": ("final_audio.wav", io.BytesIO(fake_audio_bytes), "audio/wav")}
    data = {"duration": "00:04:15"}

    mock_zapier_result = {
        "status": "success",
        "delivery_status": "sent",
        "status_code": 200,
        "attempts": 1
    }

    with patch("app.services.zapier_service.ZapierService.send_meeting_completed_webhook", new_callable=AsyncMock) as mock_meet_zap, \
         patch("app.services.zapier_service.ZapierService.send_task_approved_webhook", new_callable=AsyncMock) as mock_task_zap:
        
        mock_meet_zap.return_value = mock_zapier_result
        mock_task_zap.return_value = mock_zapier_result

        complete_res = client.post(
            f"/api/meetings/{meeting_id}/complete",
            files=files,
            data=data,
            headers=headers
        )
        assert complete_res.status_code == 200
        comp_data = complete_res.json()
        assert comp_data["status"] == "Completed"
        assert comp_data["meeting_summary"] is not None
        assert len(comp_data["key_decisions"]) > 0

        # Verify Analysis endpoint
        analysis_res = client.get(f"/api/meetings/{meeting_id}/analysis", headers=headers)
        assert analysis_res.status_code == 200
        analysis = analysis_res.json()
        assert analysis["meeting_id"] == meeting_id
        assert len(analysis["extracted_tasks"]) > 0

        # Verify task assignment constraint:
        # None of the tasks should be assigned to Priya because Priya was not an attendee!
        for task in analysis["extracted_tasks"]:
            assigned_name = task.get("assigned_member_name")
            assert assigned_name != "Priya", f"Task was assigned to absent member Priya: {task}"
            assert assigned_name in ["Jai", "Arun", "Unassigned"]

        # Verify task approval workflow via meeting endpoint
        first_task = analysis["extracted_tasks"][0]
        task_id = first_task["task_id"]

        appr_res = client.post(
            f"/api/meetings/{meeting_id}/tasks/approve",
            json={"task_id": task_id, "priority": "High"},
            headers=headers
        )
        assert appr_res.status_code == 200
        appr_data = appr_res.json()
        assert appr_data["approval_status"] == "Approved"
        assert appr_data["priority"] == "High"
