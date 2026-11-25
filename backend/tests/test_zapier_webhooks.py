import uuid
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.config import settings
from app.database.mongo import get_col
from app.services.zapier_service import ZapierService

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"zapier_admin_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Zapier Test Admin",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Zapier Auto Team {suffix}",
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


# =====================================================================
# TEST 1: Task approval triggers the correct webhook
# =====================================================================
@pytest.mark.anyio
async def test_task_approval_triggers_correct_webhook(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    task_id = f"TSK-APP-{suffix}"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # Execute direct ZapierService send_task_approved_webhook
        result = await ZapierService.send_task_approved_webhook(
            task_doc={
                "task_id": task_id,
                "team_id": team_id,
                "title": "Build Authentication Flow",
                "description": "Implement JWT and BCrypt in FastAPI",
                "priority": "High",
                "deadline": "2026-12-01",
                "approval_status": "Approved",
                "status": "Pending",
                "assigned_member_name": "Jai",
                "assigned_member_email": "jai@example.com"
            }
        )

        assert result["delivery_status"] == "success"
        assert mock_post.called

        # Verify payload structure matches specification
        call_args = mock_post.call_args
        called_url = call_args[0][0]
        called_json = call_args[1]["json"]

        assert called_url == settings.task_approved_webhook_url
        assert called_json["event"] == "task_approved"
        assert called_json["task_id"] == task_id
        assert called_json["approval_status"].lower() == "approved"
        assert called_json["status"] == "Approved"
        assert called_json["priority"] == "High"
        assert called_json["assigned_member"] == "Jai"
        assert called_json["assigned_email"] == "jai@example.com"

        # Verify log persisted in automation_logs
        logs_col = get_col("automation_logs")
        log_entry = logs_col.find_one({"reference_id": task_id, "event_type": "task_approved"})
        assert log_entry is not None
        assert log_entry["delivery_status"] == "success"


# =====================================================================
# TEST 2: Unapproved tasks do not trigger webhooks
# =====================================================================
@pytest.mark.anyio
async def test_unapproved_tasks_do_not_trigger_webhooks(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    task_id = f"TSK-UNAPP-{suffix}"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Create an unapproved task via API
        task_payload = {
            "task_id": task_id,
            "title": "Draft AI Task Not Yet Reviewed",
            "description": "Draft deliverable from Whisper STT",
            "priority": "Medium",
            "approval_status": "Pending",
            "meeting_title": "Draft Review"
        }

        res = client.post("/api/tasks", json=task_payload, headers=auth_headers["headers"])
        assert res.status_code == 201
        assert res.json()["approval_status"] == "Pending"

        # Verify directly with service: unapproved tasks must be rejected
        unapproved_doc = {
            "task_id": task_id,
            "team_id": team_id,
            "title": "Draft AI Task Not Yet Reviewed",
            "approval_status": "Pending"
        }
        res_service = await ZapierService.send_task_approved_webhook(unapproved_doc)
        assert res_service["delivery_status"] == "skipped"
        assert res_service["reason"] == "unapproved_task"
        assert not mock_post.called


# =====================================================================
# TEST 3: Meeting completion triggers the correct webhook
# =====================================================================
@pytest.mark.anyio
async def test_meeting_completion_triggers_correct_webhook(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    meeting_id = f"MTG-COMP-{suffix}"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        meeting_payload = {
            "meeting_id": meeting_id,
            "team_id": team_id,
            "meeting_title": "Architecture Review & Release Sync",
            "duration": "00:35:10",
            "participants": ["Sarah Connor", "Jai", "Arun", "Priya"],
            "meeting_summary": "Architectural sign-off on 8-agent LangGraph workflow and Zapier integrations.",
            "key_decisions": ["Deploy Zapier webhooks to production", "Run Whisper speech model locally"],
            "action_items": [
                {"title": "Deploy backend to Render", "assignee": "Arun"},
                {"title": "Verify Zapier Catch Hook", "assignee": "Sarah Connor"}
            ],
            "team_lead_email": auth_headers["email"],
            "status": "Completed"
        }

        # Verify service dispatch
        result = await ZapierService.send_meeting_completed_webhook(meeting_payload)
        assert result["delivery_status"] == "success"

        # Verify payload contents
        call_args = mock_post.call_args
        called_url = call_args[0][0]
        called_json = call_args[1]["json"]

        assert called_url == settings.meeting_completed_webhook_url
        assert called_json["event"] == "meeting_completed"
        assert called_json["meeting_id"] == meeting_id
        assert any("Sarah Connor" in str(p) for p in (called_json["participants"] if isinstance(called_json["participants"], list) else [called_json["participants"]]))
        assert "Architectural sign-off" in called_json["meeting_summary"]
        assert any("Deploy Zapier webhooks" in str(d) for d in (called_json["key_decisions"] if isinstance(called_json["key_decisions"], list) else [called_json["key_decisions"]]))

        # Verify log persisted
        logs_col = get_col("automation_logs")
        log_entry = logs_col.find_one({"reference_id": meeting_id, "event_type": "meeting_completed"})
        assert log_entry is not None
        assert log_entry["delivery_status"] == "success"


# =====================================================================
# TEST 4: Failed meeting analysis does not trigger the webhook
# =====================================================================
@pytest.mark.anyio
async def test_failed_meeting_analysis_does_not_trigger_webhook(auth_headers):
    suffix = uuid.uuid4().hex[:6]
    meeting_id = f"MTG-FAIL-{suffix}"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # 1. Calling /api/meetings/complete with status="failed"
        failed_payload = {
            "meeting_id": meeting_id,
            "meeting_title": "Failed Audio Recording Session",
            "status": "failed",
            "error_message": "Audio stream corrupted during MediaRecorder capture"
        }
        res = client.post("/api/meetings/complete", json=failed_payload, headers=auth_headers["headers"])
        assert res.status_code == 201
        assert res.json()["status"] == "failed"

        # Webhook must NOT have been called
        assert not mock_post.called

        # 2. Service directly rejects doc without summary
        res_service = await ZapierService.send_meeting_completed_webhook({
            "meeting_id": meeting_id,
            "meeting_title": "Failed Audio Recording Session",
            "meeting_summary": ""  # empty summary
        })
        assert res_service["delivery_status"] == "skipped"
        assert res_service["reason"] == "incomplete_analysis"
        assert not mock_post.called


# =====================================================================
# TEST 5: New team member registration triggers the correct webhook
# =====================================================================
@pytest.mark.anyio
async def test_new_team_member_registration_triggers_correct_webhook(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    member_id = f"MEM-TEST-{suffix}"
    member_email = f"karthik_{suffix}@example.com"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        member_data = {
            "member_id": member_id,
            "team_id": team_id,
            "name": "Karthik QA",
            "email": member_email,
            "role": "QA Automation Engineer",
            "account_status": "active"
        }

        # Call service directly to verify deterministic dispatch and payload
        result = await ZapierService.send_team_member_added_webhook(member_data, team_name="MeetMind Squad")
        assert result["delivery_status"] == "success"

        call_args = mock_post.call_args
        called_url = call_args[0][0]
        called_json = call_args[1]["json"]

        assert called_url == settings.team_member_added_webhook_url
        assert called_json["event"] == "team_member_added"
        assert called_json["member_id"] == member_id
        assert called_json["email"] == member_email
        assert called_json["name"] == "Karthik QA"
        assert called_json["role"] == "QA Automation Engineer"
        assert called_json["account_status"] == "active"

        # Verify log persisted
        logs_col = get_col("automation_logs")
        log_entry = logs_col.find_one({"reference_id": member_id, "event_type": "team_member_added"})
        assert log_entry is not None
        assert log_entry["delivery_status"] == "success"


# =====================================================================
# TEST 6: Duplicate member registration does not send another welcome notification
# =====================================================================
@pytest.mark.anyio
async def test_duplicate_member_registration_does_not_send_another_welcome_notification(auth_headers):
    suffix = uuid.uuid4().hex[:6]
    member_email = f"priya_dup_{suffix}@example.com"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # First registration -> 201
        res1 = client.post("/api/team/members", json={
            "name": "Priya Designer",
            "email": member_email,
            "role": "UI/UX Designer",
            "skills": ["Figma", "Tailwind CSS"],
            "availability": "Available"
        }, headers=auth_headers["headers"])
        assert res1.status_code == 201
        initial_call_count = mock_post.call_count

        # Second registration with SAME email -> 409 Conflict
        res2 = client.post("/api/team/members", json={
            "name": "Priya Designer Duplicate",
            "email": member_email,
            "role": "UI/UX Designer",
            "skills": ["Figma"],
            "availability": "Available"
        }, headers=auth_headers["headers"])
        assert res2.status_code == 409
        # Webhook count must NOT increase
        assert mock_post.call_count == initial_call_count


# =====================================================================
# TEST 7: Webhook failures are logged and can be retried
# =====================================================================
@pytest.mark.anyio
async def test_webhook_failures_are_logged_and_can_be_retried(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    task_id = f"TSK-RETRY-{suffix}"

    # Step 1: Simulate network outage/timeout across all retries
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post_fail:
        mock_post_fail.side_effect = httpx.ConnectTimeout("Connection timed out to Zapier catch hook")

        fail_result = await ZapierService.send_task_approved_webhook({
            "task_id": task_id,
            "team_id": team_id,
            "title": "Failed Task To Retry",
            "approval_status": "Approved"
        })

        assert fail_result["delivery_status"] == "failed"
        assert fail_result["attempt_count"] == 3  # All 3 exponential retries attempted
        assert "ConnectTimeout" in fail_result["error_message"]
        log_id = fail_result["log_id"]

    # Step 2: Outage resolved: Zapier webhook now returns 200 OK
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post_success:
        mock_post_success.return_value = mock_success

        retry_result = await ZapierService.retry_failed_webhook(log_id)
        assert retry_result["delivery_status"] == "success"
        assert mock_post_success.called


# =====================================================================
# TEST 8: Duplicate event dispatches are prevented (Idempotency)
# =====================================================================
@pytest.mark.anyio
async def test_duplicate_event_dispatches_are_prevented(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    task_id = f"TSK-IDEMP-{suffix}"

    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_success

        task_doc = {
            "task_id": task_id,
            "team_id": team_id,
            "title": "Idempotent Task Test",
            "approval_status": "Approved"
        }

        # First dispatch -> successful
        first_res = await ZapierService.send_task_approved_webhook(task_doc)
        assert first_res["delivery_status"] == "success"
        assert mock_post.call_count == 1

        # Second dispatch for the SAME task -> skipped due to idempotency!
        second_res = await ZapierService.send_task_approved_webhook(task_doc)
        assert second_res["delivery_status"] == "skipped"
        assert second_res["reason"] == "already_delivered"
        # Network post must NOT be called again
        assert mock_post.call_count == 1


# =====================================================================
# TEST 9: Missing webhook environment variables are handled safely
# =====================================================================
@pytest.mark.anyio
async def test_missing_webhook_environment_variables_handled_safely(auth_headers):
    team_id = auth_headers["team_id"]
    suffix = uuid.uuid4().hex[:6]
    task_id = f"TSK-NOWEBHOOK-{suffix}"

    # Temporarily clear task approved webhook URLs
    with patch.object(settings, "ZAPIER_TASK_APPROVED_WEBHOOK_URL", None), \
         patch.object(settings, "ZAPIER_APPROVED_TASK_WEBHOOK_URL", None), \
         patch.object(settings, "ZAPIER_WEBHOOK_URL", None):

        task_doc = {
            "task_id": task_id,
            "team_id": team_id,
            "title": "Task With No Configured Webhook",
            "approval_status": "Approved"
        }

        # Must NOT raise exception; returns safe failed status with logged audit entry
        res = await ZapierService.send_task_approved_webhook(task_doc)
        assert res["delivery_status"] == "failed"
        assert "not configured" in res["error_message"].lower()

        # Audit entry in MongoDB should exist
        logs_col = get_col("automation_logs")
        log_entry = logs_col.find_one({"event_id": res["event_id"]})
        assert log_entry is not None
        assert log_entry["masked_url"] == "NOT_CONFIGURED"
