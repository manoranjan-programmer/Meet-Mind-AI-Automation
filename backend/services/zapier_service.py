"""
Reusable Zapier webhook service re-export module for backend/services/zapier_service.py.
Delegates to app.services.zapier_service.
"""
from app.services.zapier_service import (
    ZapierService,
    dispatch_webhook_in_background,
    mask_webhook_url
)

# Explicit function exports as required by specification:
send_task_approved_webhook = ZapierService.send_task_approved_webhook
send_meeting_completed_webhook = ZapierService.send_meeting_completed_webhook
send_team_member_added_webhook = ZapierService.send_team_member_added_webhook
retry_failed_webhook = ZapierService.retry_failed_webhook

__all__ = [
    "ZapierService",
    "send_task_approved_webhook",
    "send_meeting_completed_webhook",
    "send_team_member_added_webhook",
    "retry_failed_webhook",
    "dispatch_webhook_in_background",
    "mask_webhook_url"
]
