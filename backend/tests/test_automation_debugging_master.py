import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.config import settings
from app.database.mongo import get_col
from app.services.zapier_service import ZapierService
from app.services.automation_service import AutomationService

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_context():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"auto_master_{suffix}@meetmind.ai"
    reg_res = client.post("/api/auth/register", json={
        "name": "Auto Master Lead",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Master Auto Team {suffix}",
        "role": "Admin"
    })
    assert reg_res.status_code == 200
    data = reg_res.json()
    token = data["access_token"]
    team_id = data["user"]["team_id"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "team_id": team_id,
        "email": admin_email,
        "suffix": suffix
    }

# =========================================================================
# TEST 1: Task Approved Webhook & Outbox Persistence
# =========================================================================
@pytest.mark.anyio
async def test_task_approved_outbox_and_payload(auth_context):
    team_id = auth_context["team_id"]
    task_id = f"TSK-MST-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success", "attempt": "run"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await ZapierService.send_task_approved_webhook(
            task_doc={
                "task_id": task_id,
                "team_id": team_id,
                "title": "Database Sharding Implementation",
                "description": "Partition collections by team_id",
                "priority": "Critical",
                "deadline": "2026-12-15T18:00:00Z",
                "approval_status": "Approved",
                "status": "Pending",
                "assigned_member_name": "Arun Kumar",
                "assigned_member_email": "arun@meetmind.ai"
            }
        )

        assert result["delivery_status"] == "success"
        assert result["dispatch_status"] == "webhook_accepted"
        assert result["gmail_status"] == "gmail_accepted"

        # Verify call arguments
        call_args = mock_post.call_args
        json_sent = call_args[1]["json"]
        assert json_sent["event"] == "task_approved"
        assert json_sent["task_id"] == task_id
        assert json_sent["status"] == "Approved"
        assert json_sent["approval_status"] == "approved"
        assert json_sent["assigned_member"] == "Arun Kumar"
        assert json_sent["assigned_email"] == "arun@meetmind.ai"
        assert json_sent["priority"] == "Critical"

        # Verify MongoDB outbox state
        outbox_col = get_col("automation_outbox")
        outbox_doc = outbox_col.find_one({"reference_id": task_id, "event_type": "task_approved"})
        assert outbox_doc is not None
        assert outbox_doc["status"] == "webhook_accepted"

# =========================================================================
# TEST 2: Meeting Completed Webhook with Structured Arrays
# =========================================================================
@pytest.mark.anyio
async def test_meeting_completed_outbox_and_payload(auth_context):
    team_id = auth_context["team_id"]
    meeting_id = f"MTG-MST-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await ZapierService.send_meeting_completed_webhook({
            "meeting_id": meeting_id,
            "team_id": team_id,
            "meeting_title": "Sprint 44 Release Planning",
            "duration": "00:45:00",
            "participants": ["Jai", "Arun", "Priya"],
            "meeting_summary": "All 5 automation workflows verified and approved for production.",
            "key_decisions": ["Integrate MongoDB outbox", "Standardize universal aliases"],
            "action_items": [{"title": "Deploy Render blueprint"}, {"title": "Verify Vercel frontend"}],
            "team_lead_email": auth_context["email"]
        })

        assert result["delivery_status"] == "success"
        call_args = mock_post.call_args
        json_sent = call_args[1]["json"]

        assert json_sent["event"] == "meeting_completed"
        assert json_sent["meeting_id"] == meeting_id
        assert isinstance(json_sent["participants"], list)
        assert isinstance(json_sent["key_decisions"], list)
        assert isinstance(json_sent["action_items"], list)
        assert json_sent["team_lead_email"] == auth_context["email"]

# =========================================================================
# TEST 3: Task Completed Webhook (Event 3)
# =========================================================================
@pytest.mark.anyio
async def test_task_completed_webhook_trigger(auth_context):
    team_id = auth_context["team_id"]
    task_id = f"TSK-CMP-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await ZapierService.send_task_completed_webhook({
            "task_id": task_id,
            "team_id": team_id,
            "title": "Configure WebRTC Signaling Server",
            "assigned_member_name": "Karthik",
            "assigned_member_email": "karthik@meetmind.ai",
            "status": "Completed"
        }, team_lead_email=auth_context["email"])

        assert result["delivery_status"] == "success"
        call_args = mock_post.call_args
        json_sent = call_args[1]["json"]

        assert json_sent["event"] == "task_completed"
        assert json_sent["task_id"] == task_id
        assert json_sent["status"] == "Completed"
        assert json_sent["assigned_member"] == "Karthik"
        assert json_sent["assigned_email"] == "karthik@meetmind.ai"
        assert json_sent["team_lead_email"] == auth_context["email"]

# =========================================================================
# TEST 4: Team Member Added Webhook (Event 4)
# =========================================================================
@pytest.mark.anyio
async def test_team_member_added_webhook(auth_context):
    team_id = auth_context["team_id"]
    member_id = f"MEM-MST-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await ZapierService.send_team_member_added_webhook({
            "member_id": member_id,
            "team_id": team_id,
            "name": "Sarah Connor",
            "email": "sarah@meetmind.ai",
            "role": "Editor",
            "account_status": "active"
        }, team_name="Production Core Team")

        assert result["delivery_status"] == "success"
        call_args = mock_post.call_args
        json_sent = call_args[1]["json"]

        assert json_sent["event"] == "team_member_added"
        assert json_sent["member_id"] == member_id
        assert json_sent["team_id"] == team_id
        assert json_sent["email"] == "sarah@meetmind.ai"
        assert json_sent["account_status"] == "active"

# =========================================================================
# TEST 5: Team Invitation Created Webhook (Event 5)
# =========================================================================
@pytest.mark.anyio
async def test_team_invitation_created_webhook(auth_context):
    team_id = auth_context["team_id"]
    invitation_id = f"INV-MST-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await ZapierService.send_team_invitation_created_webhook({
            "invitation_id": invitation_id,
            "team_id": team_id,
            "team_name": "Production Core Team",
            "invited_email": "newhire@meetmind.ai",
            "invited_by": "Auto Master Lead",
            "assigned_role": "Editor",
            "invitation_url": "http://localhost:5173/accept-invitation?token=mocktoken123",
            "expires_at": "2026-12-01T00:00:00Z"
        })

        assert result["delivery_status"] == "success"
        call_args = mock_post.call_args
        json_sent = call_args[1]["json"]

        assert json_sent["event"] == "team_invitation_created"
        assert json_sent["invitation_id"] == invitation_id
        assert json_sent["invited_email"] == "newhire@meetmind.ai"
        assert json_sent["assigned_role"] == "Editor"

# =========================================================================
# TEST 6: Missing / Invalid Email Validation Fails Gracefully
# =========================================================================
@pytest.mark.anyio
async def test_missing_recipient_validation():
    # Attempting invitation webhook with empty invited_email
    res = await ZapierService.send_team_invitation_created_webhook({
        "invitation_id": "INV-INVALID-001",
        "team_id": "TEAM-001",
        "invited_email": ""
    })
    assert res["delivery_status"] == "skipped"
    assert res["reason"] == "invalid_invitation_document"

# =========================================================================
# TEST 7: Transient Failure with Exponential Backoff and Outbox Retrying State
# =========================================================================
@pytest.mark.anyio
async def test_transient_failure_retries_and_outbox(auth_context):
    team_id = auth_context["team_id"]
    task_id = f"TSK-FAIL-{uuid.uuid4().hex[:6]}"

    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_500

        result = await ZapierService.send_task_approved_webhook({
            "task_id": task_id,
            "team_id": team_id,
            "title": "Failing Task Verification",
            "approval_status": "Approved",
            "assigned_member_name": "Test",
            "assigned_member_email": "test@meetmind.ai"
        })

        assert result["delivery_status"] == "failed"
        assert result["attempt_count"] == 3  # MAX_RETRIES attempted

        # Verify Outbox item was preserved in MongoDB
        outbox_col = get_col("automation_outbox")
        outbox_item = outbox_col.find_one({"reference_id": task_id})
        assert outbox_item is not None
        assert outbox_item["attempt_count"] == 3

# =========================================================================
# TEST 8: Duplicate Dispatch Prevention (Idempotency)
# =========================================================================
@pytest.mark.anyio
async def test_idempotent_duplicate_prevention(auth_context):
    team_id = auth_context["team_id"]
    task_id = f"TSK-IDEMP-{uuid.uuid4().hex[:6]}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # First dispatch
        res1 = await ZapierService.send_task_approved_webhook({
            "task_id": task_id,
            "team_id": team_id,
            "title": "Idempotent Task",
            "approval_status": "Approved",
            "assigned_member_name": "Arun",
            "assigned_member_email": "arun@meetmind.ai"
        })
        assert res1["delivery_status"] == "success"

        # Immediate second dispatch
        res2 = await ZapierService.send_task_approved_webhook({
            "task_id": task_id,
            "team_id": team_id,
            "title": "Idempotent Task",
            "approval_status": "Approved",
            "assigned_member_name": "Arun",
            "assigned_member_email": "arun@meetmind.ai"
        })
        assert res2["delivery_status"] == "skipped"
        assert res2["reason"] == "already_delivered"

# =========================================================================
# TEST 9: Automation API Endpoints Verification
# =========================================================================
def test_automation_api_endpoints(auth_context):
    headers = auth_context["headers"]

    # 1. Health check endpoint
    h_res = client.get("/api/automation/health", headers=headers)
    assert h_res.status_code == 200
    h_data = h_res.json()
    assert h_data["status"] == "healthy"
    assert "outbox_metrics" in h_data
    assert "webhooks_configured" in h_data

    # 2. Logs listing endpoint
    l_res = client.get("/api/automation/logs?limit=10", headers=headers)
    assert l_res.status_code == 200
    l_data = l_res.json()
    assert "logs" in l_data
    assert "total" in l_data

    # 3. Overview endpoint
    o_res = client.get("/api/automation/overview", headers=headers)
    assert o_res.status_code == 200
    o_data = o_res.json()
    assert "total_executions" in o_data
    assert "integrations" in o_data
