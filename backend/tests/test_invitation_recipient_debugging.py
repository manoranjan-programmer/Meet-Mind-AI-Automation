import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from bson import ObjectId

from app.main import app
from app.config import settings
from app.database.mongo import get_col
from app.services.team_service import TeamMemberService
from app.services.zapier_service import ZapierService
from app.services.automation_service import AutomationService

client = TestClient(app)

TARGET_RECIPIENT = "admin.jaiwant@gmail.com"

@pytest.fixture(scope="module")
def admin_user():
    suffix = uuid.uuid4().hex[:6]
    admin_email = f"lead_inv_test_{suffix}@meetmind.ai"
    res = client.post("/api/auth/register", json={
        "name": "Invitation Debug Admin",
        "email": admin_email,
        "password": "Password123!",
        "team_name": f"Debug Workspace {suffix}",
        "role": "Admin"
    })
    assert res.status_code == 200
    data = res.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "team_id": data["user"]["team_id"],
        "email": admin_email,
        "user_id": data["user"]["user_id"]
    }

# =========================================================================
# TEST 1: Full Invitation Lifecycle for admin.jaiwant@gmail.com
# =========================================================================
@pytest.mark.anyio
async def test_invitation_recipient_consistency_end_to_end(admin_user):
    headers = admin_user["headers"]
    team_id = admin_user["team_id"]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success", "attempt": "01a20d21-4f6a"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # 1. Frontend -> FastAPI: Submit invitation for TARGET_RECIPIENT
        invite_res = client.post(
            "/api/team/invitations",
            headers=headers,
            json={
                "email": TARGET_RECIPIENT,
                "role": "Editor",
                "message": "Welcome to MeetMind AI team!"
            }
        )
        assert invite_res.status_code == 201
        inv_data = invite_res.json()
        inv_id = inv_data["invitation_id"]

        assert inv_data["invited_email"] == TARGET_RECIPIENT
        assert inv_data["email"] == TARGET_RECIPIENT
        assert inv_data["assigned_role"] == "Editor"
        assert inv_data["invitation_url"].startswith(settings.FRONTEND_URL)

        # 2. Verify MongoDB team_invitations record
        inv_col = get_col("team_invitations")
        saved_inv = inv_col.find_one({"invitation_id": inv_id})
        assert saved_inv is not None
        assert saved_inv["invited_email"] == TARGET_RECIPIENT
        assert saved_inv["email"] == TARGET_RECIPIENT
        assert saved_inv["team_id"] == team_id
        assert saved_inv["invitation_status"] == "pending"
        correlation_id = saved_inv.get("correlation_id")
        assert correlation_id is not None
        assert correlation_id.startswith("INV-CORR-")

        # 3. Verify Outbox record in automation_outbox
        outbox_col = get_col("automation_outbox")
        outbox_item = outbox_col.find_one({
            "reference_id": inv_id,
            "event_type": "team_invitation_created"
        })
        assert outbox_item is not None
        assert outbox_item["correlation_id"] == correlation_id
        payload = outbox_item["payload"]

        # 4. Verify Payload recipient normalization across all aliases
        assert payload["event"] == "team_invitation_created"
        assert payload["invitation_id"] == inv_id
        assert payload["invited_email"] == TARGET_RECIPIENT
        assert payload["recipient_email"] == TARGET_RECIPIENT
        assert payload["to_email"] == TARGET_RECIPIENT
        assert payload["to"] == TARGET_RECIPIENT
        assert payload["email"] == TARGET_RECIPIENT
        assert payload["assigned_email"] == TARGET_RECIPIENT
        assert payload["correlation_id"] == correlation_id
        assert f"Ref: {inv_id}" in payload["email_subject"]

        # 5. Verify HTTP request sent to Zapier
        assert mock_post.called
        call_args = mock_post.call_args
        called_json = call_args[1]["json"]
        assert called_json["invited_email"] == TARGET_RECIPIENT
        assert called_json["recipient_email"] == TARGET_RECIPIENT
        assert called_json["to_email"] == TARGET_RECIPIENT

        # 6. Verify automation_logs audit entry
        logs_col = get_col("automation_logs")
        log_entry = logs_col.find_one({"reference_id": inv_id, "event_type": "team_invitation_created"})
        assert log_entry is not None
        assert log_entry["recipient"] == TARGET_RECIPIENT
        assert log_entry["recipient_email"] == TARGET_RECIPIENT
        assert log_entry["dispatch_status"] == "webhook_accepted"
        assert log_entry["correlation_id"] == correlation_id

        # 7. Call Diagnostic API endpoint
        diag_res = client.get(f"/api/automation/invitation-diagnostics/{inv_id}", headers=headers)
        assert diag_res.status_code == 200
        diag_data = diag_res.json()

        assert diag_data["invitation_id"] == inv_id
        assert diag_data["intended_recipient"] == TARGET_RECIPIENT
        assert diag_data["stored_recipient"] == TARGET_RECIPIENT
        assert diag_data["webhook_recipient"] == TARGET_RECIPIENT
        assert diag_data["recipient_match"] is True
        assert diag_data["mongo_save_status"] == "saved"
        assert diag_data["webhook_status"] == "webhook_accepted"
        assert diag_data["webhook_http_status"] == 200
        assert diag_data["correlation_id"] == correlation_id

# =========================================================================
# TEST 2: Resend Invitation Bypasses Initial Idempotency Guard
# =========================================================================
@pytest.mark.anyio
async def test_resend_invitation_dispatches_cleanly(admin_user):
    headers = admin_user["headers"]
    team_id = admin_user["team_id"]
    suffix = uuid.uuid4().hex[:6]
    recipient = f"resend_test_{suffix}@gmail.com"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "success"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # Create invitation
        res1 = client.post("/api/team/invitations", headers=headers, json={"email": recipient, "role": "Viewer"})
        assert res1.status_code == 201
        inv_id = res1.json()["invitation_id"]

        # Call Resend endpoint
        mock_post.reset_mock()
        resend_res = client.post(f"/api/team/invitations/{inv_id}/resend", headers=headers)
        assert resend_res.status_code == 200

        # Verify that mock_post WAS called on resend (not skipped by idempotency)
        assert mock_post.called
        call_args = mock_post.call_args
        called_json = call_args[1]["json"]
        assert called_json["is_resend"] is True
        assert called_json["event_id"].startswith("EVT-INV-RESEND-")
        assert called_json["invited_email"] == recipient

# =========================================================================
# TEST 3: Duplicate Active Invitation Rejected with 409
# =========================================================================
def test_duplicate_invitation_rejection(admin_user):
    headers = admin_user["headers"]
    suffix = uuid.uuid4().hex[:6]
    test_email = f"dup_guard_{suffix}@gmail.com"

    # First invite
    r1 = client.post("/api/team/invitations", headers=headers, json={"email": test_email, "role": "Editor"})
    assert r1.status_code == 201

    # Second invite with same email while first is still pending
    r2 = client.post("/api/team/invitations", headers=headers, json={"email": test_email, "role": "Editor"})
    assert r2.status_code == 409
    assert "pending invitation already exists" in r2.json()["detail"].lower()
