import uuid
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.middleware.auth import get_current_user
from app.services.automation_service import AutomationService
from app.services.zapier_service import ZapierService

router = APIRouter(prefix="/automation", tags=["Automation Center"])


class WebhookTestRequest(BaseModel):
    webhook_type: str = Field(
        default="meeting_completed",
        description="One of: meeting_completed, team_member_added, team_invitation_created"
    )


@router.get("/health")
def get_automation_health(current_user: dict = Depends(get_current_user)):
    """
    Healthcheck endpoint verifying connection to MongoDB,
    status of the automation outbox, and webhook configurations.
    """
    return AutomationService.get_automation_health()


@router.get("/overview")
def get_automation_overview(current_user: dict = Depends(get_current_user)):
    """Returns overview statistics and recent logs for the Automation Center."""
    team_id = current_user.get("team_id")
    return AutomationService.get_automation_overview(team_id)


@router.get("/logs")
def list_automation_logs(
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by delivery status"),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves paginated automation execution logs from MongoDB with team isolation.
    """
    team_id = current_user.get("team_id")
    return AutomationService.list_logs(
        team_id=team_id,
        limit=limit,
        skip=skip,
        event_type=event_type,
        status=status
    )


@router.get("/logs/{event_id}")
def get_automation_log_detail(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves full details of an automation event log including payload,
    response snippets, and outbox state.
    """
    team_id = current_user.get("team_id")
    log = AutomationService.get_log_by_event_id(team_id, event_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation log '{event_id}' not found."
        )
    return log


@router.get("/invitation-diagnostics/{invitation_id}")
def get_invitation_diagnostics(
    invitation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns end-to-end diagnostic tracking for a specific team invitation,
    verifying recipient consistency across React, FastAPI, MongoDB, Outbox, and Zapier.
    """
    team_id = current_user.get("team_id")
    return AutomationService.get_invitation_diagnostics(team_id, invitation_id, current_user)


@router.post("/test-webhook")
async def test_webhook_endpoint(
    req: Optional[WebhookTestRequest] = None,
    webhook_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Diagnostic endpoint that triggers a real webhook dispatch to test connectivity
    and returns live execution status and Zapier/Gmail diagnostic telemetry.
    """
    target_type = (req.webhook_type if req and req.webhook_type else None) or webhook_type or "meeting_completed"
    return await AutomationService.test_webhook(target_type, current_user)


@router.post("/test")
async def test_zapier_webhook_legacy(
    webhook_type: Optional[str] = Query("meeting_completed"),
    current_user: dict = Depends(get_current_user)
):
    """Legacy alias for test-webhook."""
    return await AutomationService.test_webhook(webhook_type, current_user)


@router.post("/retry/{event_id}")
async def retry_automation_event(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retries a failed webhook delivery by its event_id or log_id.
    """
    res = await ZapierService.retry_failed_webhook(event_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res
