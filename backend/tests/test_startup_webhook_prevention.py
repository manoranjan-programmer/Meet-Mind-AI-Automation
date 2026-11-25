import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app, lifespan
from app.config import settings
from app.database.mongo import get_col
from app.services.zapier_service import ZapierService


@pytest.fixture
def clean_test_outbox():
    outbox_col = get_col("automation_outbox")
    test_prefix = f"EVT-TEST-{uuid.uuid4().hex[:6]}"
    yield test_prefix
    outbox_col.delete_many({"event_id": {"$regex": f"^{test_prefix}"}})


@pytest.mark.anyio
async def test_startup_lifespan_does_not_dispatch_webhooks():
    """
    STRICT REQUIREMENT: Server startup must strictly initialize connections
    and internal resources without triggering any Zapier webhooks or emails.
    """
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Simulate FastAPI lifespan startup and shutdown
        async with lifespan(app):
            # Server is running in lifespan context
            pass

        # Absolutely NO HTTP POST requests must have occurred during startup/shutdown
        assert mock_post.call_count == 0, (
            f"Expected 0 webhook POST calls on startup, but got {mock_post.call_count}!"
        )


@pytest.mark.anyio
async def test_cleanup_stale_outbox_on_startup(clean_test_outbox):
    """
    Verify that any leftover pending or retrying outbox records from prior sessions
    are marked 'stale_skipped' on startup so they are never auto-replayed.
    """
    outbox_col = get_col("automation_outbox")
    event_id_pending = f"{clean_test_outbox}-PENDING"
    event_id_retrying = f"{clean_test_outbox}-RETRYING"

    # Insert mock leftover records
    outbox_col.insert_many([
        {
            "event_id": event_id_pending,
            "event_type": "team_invitation_created",
            "reference_id": f"INV-{uuid.uuid4().hex[:6]}",
            "status": "pending",
            "created_at": datetime.utcnow() - timedelta(minutes=10)
        },
        {
            "event_id": event_id_retrying,
            "event_type": "team_invitation_created",
            "reference_id": f"INV-{uuid.uuid4().hex[:6]}",
            "status": "retrying",
            "created_at": datetime.utcnow() - timedelta(minutes=5)
        }
    ])

    # Run cleanup
    cleaned = ZapierService.cleanup_stale_outbox_on_startup()
    assert cleaned >= 2

    # Verify both documents are marked as stale_skipped
    doc1 = outbox_col.find_one({"event_id": event_id_pending})
    doc2 = outbox_col.find_one({"event_id": event_id_retrying})

    assert doc1["status"] == "stale_skipped"
    assert doc1["next_retry_at"] is None
    assert doc2["status"] == "stale_skipped"
    assert doc2["next_retry_at"] is None


@pytest.mark.anyio
async def test_process_outbox_batch_never_replays_invitations(clean_test_outbox):
    """
    Verify that process_outbox_batch strictly excludes team_invitation_created events,
    preventing any automated re-sending of invitation emails across server reboots.
    """
    outbox_col = get_col("automation_outbox")
    event_id = f"{clean_test_outbox}-INV-AUTOREPLAY"

    outbox_col.insert_one({
        "event_id": event_id,
        "event_type": "team_invitation_created",
        "reference_id": f"INV-{uuid.uuid4().hex[:6]}",
        "status": "pending",
        "created_at": datetime.utcnow(),
        "payload": {
            "invited_email": "test@example.com",
            "team_id": "test_team"
        }
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Enable startup dispatch for test evaluation
        with patch.object(settings, "ENABLE_STARTUP_OUTBOX_DISPATCH", True):
            await ZapierService.process_outbox_batch()

        # Zero webhooks dispatched for team_invitation_created
        assert mock_post.call_count == 0

        # The invitation outbox item was safely skipped
        item = outbox_col.find_one({"event_id": event_id})
        assert item["status"] in ["stale_skipped", "pending"]


@pytest.mark.anyio
async def test_non_retryable_404_sets_failed_status_never_retrying(clean_test_outbox):
    """
    Verify that an HTTP 404 client error is treated as non-retryable and is marked
    as 'failed' immediately, preventing infinite retry loops.
    """
    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.text = "HTTP 404: Catch Hook not found"

    with patch.object(settings, "ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/test/inv"):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_404

            inv_id = f"INV-TEST-{uuid.uuid4().hex[:6]}"
            res = await ZapierService.send_team_invitation_created_webhook({
                "invitation_id": inv_id,
                "team_id": "team_123",
                "invited_email": "recipient@example.com"
            })

            assert res["delivery_status"] == "failed"

            # Check outbox document: must be 'failed', NEVER 'retrying'
            outbox_col = get_col("automation_outbox")
            outbox_doc = outbox_col.find_one({"reference_id": inv_id})
            assert outbox_doc is not None
            assert outbox_doc["status"] == "failed"
            assert outbox_doc["next_retry_at"] is None


@pytest.mark.anyio
async def test_invitation_idempotency_prevents_duplicate_dispatch():
    """
    Verify that an invitation cannot be dispatched twice if it has already been delivered.
    """
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.text = '{"status": "success"}'

    inv_id = f"INV-IDEMP-{uuid.uuid4().hex[:6]}"
    invitation = {
        "invitation_id": inv_id,
        "team_id": "team_xyz",
        "invited_email": "unique_invitee@example.com"
    }

    with patch.object(settings, "ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/test/inv"):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_200

            # First call succeeds
            res1 = await ZapierService.send_team_invitation_created_webhook(invitation, is_resend=False)
            assert res1["delivery_status"] == "success"
            assert mock_post.call_count == 1

            # Second duplicate call with same invitation_id is skipped
            res2 = await ZapierService.send_team_invitation_created_webhook(invitation, is_resend=False)
            assert res2["delivery_status"] == "skipped"
            assert res2["reason"] == "already_delivered"
            # Mock call count must NOT have increased
            assert mock_post.call_count == 1


@pytest.mark.anyio
async def test_inactive_or_accepted_invitation_is_skipped():
    """
    Verify that if an invitation is marked 'accepted', 'revoked', or 'expired' in the
    database, attempting to send the webhook aborts gracefully.
    """
    inv_col = get_col("team_invitations")
    inv_id = f"INV-ACCEPTED-{uuid.uuid4().hex[:6]}"

    inv_col.insert_one({
        "invitation_id": inv_id,
        "team_id": "team_abc",
        "invited_email": "accepted_user@example.com",
        "status": "accepted",
        "invitation_status": "accepted",
        "created_at": datetime.utcnow()
    })

    try:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            res = await ZapierService.send_team_invitation_created_webhook({
                "invitation_id": inv_id,
                "team_id": "team_abc",
                "invited_email": "accepted_user@example.com"
            })

            assert res["delivery_status"] == "skipped"
            assert res["reason"] == "invitation_not_pending"
            assert mock_post.call_count == 0
    finally:
        inv_col.delete_one({"invitation_id": inv_id})
