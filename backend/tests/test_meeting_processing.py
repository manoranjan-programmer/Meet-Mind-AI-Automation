import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongo import get_col

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"meeting_lead_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Meeting Lead",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Meeting Squad {suffix}",
        "role": "Admin"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    team_id = reg_res.json()["user"]["team_id"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "team_id": team_id,
        "suffix": suffix,
        "email": admin_email
    }


def test_meeting_audio_upload_and_capture(auth_headers):
    """Tests Agent 1: Audio upload, storage abstraction, and metadata persistence."""
    fake_audio_bytes = b"RIFF....WAVEfmt ...." + b"\x00" * 512
    files = {"file": ("sprint_sync.wav", io.BytesIO(fake_audio_bytes), "audio/wav")}
    data = {
        "meeting_title": "Sprint 1 Kickoff Meeting",
        "participants": "Jai, Arun, Priya, Karthik",
        "duration": "00:05:30"
    }

    res = client.post("/api/meetings/upload", files=files, data=data, headers=auth_headers["headers"])
    assert res.status_code == 201
    m_data = res.json()
    assert m_data["status"] == "Uploaded"
    assert m_data["meeting_title"] == "Sprint 1 Kickoff Meeting"
    assert "MTG-" in m_data["meeting_id"]
    assert "audio_path" in m_data


@pytest.mark.anyio
async def test_meeting_pipeline_langgraph_execution(auth_headers):
    """
    Tests the full 8-Agent LangGraph workflow execution:
    Transcription -> Diarization -> Analysis -> Task Extraction ->
    Task Assignment -> Review/Validation -> Persistence -> Automation.
    """
    # 1. Upload initial audio
    fake_audio_bytes = b"RIFF....WAVEfmt ...." + b"\x00" * 512
    files = {"file": ("demo_conversation.wav", io.BytesIO(fake_audio_bytes), "audio/wav")}
    data = {
        "meeting_title": "Sprint Planning & Task Assignment",
        "participants": "Jai, Arun, Priya, Karthik",
        "duration": "00:03:45"
    }
    upload_res = client.post("/api/meetings/upload", files=files, data=data, headers=auth_headers["headers"])
    assert upload_res.status_code == 201
    meeting_id = upload_res.json()["meeting_id"]

    # 2. Add team members to database so Task Assignment agent matches real profiles
    client.post("/api/team/members", json={
        "name": "Jai",
        "email": f"jai_{auth_headers['suffix']}@example.com",
        "role": "Frontend Developer",
        "skills": ["React", "JavaScript", "CSS"],
        "experience": "Intermediate",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=auth_headers["headers"])

    client.post("/api/team/members", json={
        "name": "Arun",
        "email": f"arun_{auth_headers['suffix']}@example.com",
        "role": "Backend Developer",
        "skills": ["Python", "FastAPI", "MongoDB"],
        "experience": "Advanced",
        "availability": "Available",
        "maximum_workload": 5
    }, headers=auth_headers["headers"])

    # 3. Trigger LangGraph Process
    mock_zapier_response = MagicMock()
    mock_zapier_response.status_code = 200
    mock_zapier_response.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_zapier_response

        proc_res = client.post(f"/api/meetings/{meeting_id}/process", headers=auth_headers["headers"])
        assert proc_res.status_code == 200
        p_data = proc_res.json()
        assert p_data["status"] == "Completed"
        assert p_data["meeting_summary"] is not None
        assert len(p_data["key_decisions"]) > 0

    # 4. Verify transcript segments were persisted in MongoDB
    seg_res = client.get(f"/api/meetings/{meeting_id}/transcript", headers=auth_headers["headers"])
    assert seg_res.status_code == 200
    segments = seg_res.json()
    assert len(segments) > 0
    assert "text" in segments[0]
    assert "speaker_label" in segments[0]

    # 5. Verify extracted tasks are in approval queue (Awaiting Approval)
    task_res = client.get(f"/api/tasks?meeting_id={meeting_id}&approval_status=Awaiting Approval", headers=auth_headers["headers"])
    assert task_res.status_code == 200
    tasks_data = task_res.json()
    assert len(tasks_data["tasks"]) > 0
    first_task = tasks_data["tasks"][0]
    assert first_task["approval_status"] == "Awaiting Approval"
    assert first_task["assigned_member_name"] in ["Jai", "Arun", "Priya", "Karthik", "Unassigned"]

    # 6. Verify human approval workflow
    task_id = first_task["task_id"]
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_task_post:
        mock_task_post.return_value = mock_zapier_response

        appr_res = client.post(f"/api/tasks/{task_id}/approve", headers=auth_headers["headers"])
        assert appr_res.status_code == 200
        assert appr_res.json()["approval_status"] == "Approved"


def test_meeting_pdf_export(auth_headers):
    """Tests generating and downloading a meeting intelligence summary PDF report."""
    fake_audio_bytes = b"RIFF....WAVEfmt ...." + b"\x00" * 512
    files = {"file": ("report_audio.wav", io.BytesIO(fake_audio_bytes), "audio/wav")}
    upload_res = client.post("/api/meetings/upload", files=files, data={"meeting_title": "Executive PDF Meeting"}, headers=auth_headers["headers"])
    assert upload_res.status_code == 201
    meeting_id = upload_res.json()["meeting_id"]

    # Complete meeting summary
    comp_res = client.post("/api/meetings/complete", json={
        "meeting_id": meeting_id,
        "meeting_title": "Executive PDF Meeting",
        "meeting_summary": "Architecture review completed with unanimous approval from stakeholders.",
        "key_decisions": ["Deploy to production", "Maintain 100% test coverage"],
        "action_items": ["Verify Zapier Catch Hook", "Run load tests"],
        "status": "Completed"
    }, headers=auth_headers["headers"])
    assert comp_res.status_code == 201

    # Export PDF
    pdf_res = client.get(f"/api/meetings/{meeting_id}/export-pdf", headers=auth_headers["headers"])
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")


def test_ai_agent_executions_telemetry(auth_headers):
    """Tests the AI Agent telemetry and execution tracking endpoints."""
    res_status = client.get("/api/agents/status", headers=auth_headers["headers"])
    assert res_status.status_code == 200
    data = res_status.json()
    assert len(data["agents"]) == 8

    res_exec = client.get("/api/agents/executions", headers=auth_headers["headers"])
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert "executions" in exec_data
