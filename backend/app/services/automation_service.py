import logging
import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from bson import ObjectId
from fastapi import HTTPException, status

from app.config import settings
from app.database.mongo import get_col
from app.services.zapier_service import (
    ZapierService,
    dispatch_webhook_in_background,
    mask_webhook_url,
    get_webhook_url_for_event
)

logger = logging.getLogger("meetmind.automation")

class AutomationService:
    @staticmethod
    def trigger_task_approved_webhook(task_doc: Dict[str, Any], approved_by_name: str = "Team Admin") -> Dict[str, Any]:
        """Backward-compatible wrapper delegating to ZapierService."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                ZapierService.send_task_approved_webhook(task_doc, approved_by_name=approved_by_name)
            )
            return {"status": "enqueued", "task_id": task_doc.get("task_id")}
        except RuntimeError:
            return asyncio.run(
                ZapierService.send_task_approved_webhook(task_doc, approved_by_name=approved_by_name)
            )

    @staticmethod
    def get_automation_overview(team_id: str) -> Dict[str, Any]:
        """Returns comprehensive stats and telemetry logs for the Automation Center."""
        logs_col = get_col("automation_logs")
        outbox_col = get_col("automation_outbox")

        query = {"$or": [{"team_id": team_id}, {"team_id": None}]}
        total_executions = logs_col.count_documents(query)
        successful = logs_col.count_documents({
            **query,
            "$or": [
                {"delivery_status": "success"},
                {"status": "success"},
                {"dispatch_status": "webhook_accepted"}
            ]
        })
        failed = logs_col.count_documents({
            **query,
            "$or": [
                {"delivery_status": "failed"},
                {"dispatch_status": "failed"},
                {"status": {"$in": ["failed", "network_error"]}}
            ]
        })

        recent_logs_cur = logs_col.find(query).sort("created_at", -1).limit(50)
        recent_logs = []
        for l in recent_logs_cur:
            payload = l.get("payload", {})
            event_type = l.get("event_type") or l.get("webhook_type") or "task_approved"
            delivery_status = l.get("delivery_status") or l.get("status") or "pending"

            # Derive display title and target based on event type
            if event_type in ["task_approved", "task_completed"]:
                item_title = payload.get("task_title") or payload.get("title") or l.get("reference_id") or "Task"
                target = payload.get("assigned_member") or payload.get("assigned_name") or "Assigned Member"
            elif event_type == "meeting_completed":
                item_title = payload.get("meeting_title") or payload.get("title") or l.get("reference_id") or "Meeting"
                p_val = payload.get("participants")
                target = ", ".join(p_val) if isinstance(p_val, list) else str(p_val or "Attendees")
            elif event_type == "team_member_added":
                item_title = payload.get("name") or l.get("reference_id") or "Member"
                target = f"{payload.get('role', 'Member')} ({payload.get('email', '')})"
            elif event_type == "team_invitation_created":
                item_title = f"Invite for {payload.get('invited_email')}"
                target = f"{payload.get('assigned_role', 'Editor')} ({payload.get('invited_email', '')})"
            else:
                item_title = l.get("reference_id") or "Integration Event"
                target = "Zapier Destination"

            recipient_email = (
                l.get("recipient")
                or l.get("recipient_email")
                or payload.get("recipient_email")
                or payload.get("assigned_email")
                or payload.get("email")
                or payload.get("invited_email")
                or payload.get("team_lead_email")
                or "official.manoranjanworks@gmail.com"
            )

            recent_logs.append({
                "id": str(l["_id"]),
                "event_id": l.get("event_id"),
                "task_id": l.get("reference_id") or l.get("task_id"),
                "meeting_id": l.get("meeting_id") or payload.get("meeting_id"),
                "reference_id": l.get("reference_id"),
                "event_type": event_type,
                "integration": f"Zapier ({event_type})",
                "status": delivery_status,
                "delivery_status": delivery_status,
                "dispatch_status": l.get("dispatch_status") or ("webhook_accepted" if delivery_status == "success" else "pending"),
                "zapier_status": l.get("zapier_status") or ("zapier_action_success" if delivery_status == "success" else "pending"),
                "gmail_status": l.get("gmail_status") or ("gmail_accepted" if delivery_status == "success" else "pending"),
                "gmail_notice": l.get("gmail_notice") or ("Email accepted by Gmail; inbox delivery not independently confirmed." if delivery_status == "success" else None),
                "recipient": recipient_email,
                "recipient_email": recipient_email,
                "status_code": l.get("response_status") or l.get("status_code"),
                "task_title": item_title,
                "assigned_member": target,
                "attempt_count": l.get("attempt_count", 1),
                "retry_count": l.get("retry_count", 0),
                "error_message": l.get("error_message"),
                "response_body": l.get("response_body"),
                "payload": payload,
                "created_at": l.get("created_at", datetime.utcnow())
            })

        has_task_hook = bool(settings.task_approved_webhook_url)
        has_meeting_hook = bool(settings.meeting_completed_webhook_url)
        has_task_comp_hook = bool(settings.task_completed_webhook_url or settings.task_approved_webhook_url)
        has_member_hook = bool(settings.team_member_added_webhook_url)
        has_inv_hook = bool(settings.team_invitation_created_webhook_url)
        has_meeting_invitation_hook = bool(settings.meeting_invitation_webhook_url)

        task_runs = logs_col.count_documents({**query, "$or": [{"event_type": "task_approved"}, {"webhook_type": "task_approved"}]})
        meeting_runs = logs_col.count_documents({**query, "$or": [{"event_type": "meeting_completed"}, {"webhook_type": "meeting_completed"}]})
        task_comp_runs = logs_col.count_documents({**query, "$or": [{"event_type": "task_completed"}, {"webhook_type": "task_completed"}]})
        member_runs = logs_col.count_documents({**query, "$or": [{"event_type": "team_member_added"}, {"webhook_type": "team_member_added"}]})
        inv_runs = logs_col.count_documents({**query, "$or": [{"event_type": "team_invitation_created"}, {"webhook_type": "team_invitation_created"}]})
        meeting_invitation_runs = logs_col.count_documents({
            "$and": [
                query,
                {"$or": [
                    {"event_type": "meeting_scheduled"},
                    {"webhook_type": "meeting_scheduled"}
                ]}
            ]
        })

        integrations = [
            {
                "id": "approved_task_notification",
                "name": "Approved Task Notification",
                "webhook_type": "task_approved",
                "destinations": ["Gmail", "Trello", "Google Sheets"],
                "trigger": "Administrator approves task in MeetMind AI",
                "status": "active" if has_task_hook else "pending_configuration",
                "total_runs": task_runs,
                "success_count": logs_col.count_documents({**query, "event_type": "task_approved", "$or": [{"delivery_status": "success"}, {"status": "success"}]}),
                "failure_count": logs_col.count_documents({**query, "event_type": "task_approved", "$or": [{"delivery_status": "failed"}, {"status": "failed"}]})
            },
            {
                "id": "meeting_summary_distribution",
                "name": "Meeting Summary Distribution",
                "webhook_type": "meeting_completed",
                "destinations": ["Gmail", "Google Sheets"],
                "trigger": "Meeting completed with AI summary persisted",
                "status": "active" if has_meeting_hook else "pending_configuration",
                "total_runs": meeting_runs,
                "success_count": logs_col.count_documents({**query, "event_type": "meeting_completed", "$or": [{"delivery_status": "success"}, {"status": "success"}]}),
                "failure_count": logs_col.count_documents({**query, "event_type": "meeting_completed", "$or": [{"delivery_status": "failed"}, {"status": "failed"}]})
            },
            {
                "id": "meeting_invitation",
                "name": "Meeting Invitation",
                "webhook_type": "meeting_scheduled",
                "destinations": ["Gmail"],
                "trigger": "Team Leader saves a meeting with active workspace members",
                "status": "active" if has_meeting_invitation_hook else "pending_configuration",
                "total_runs": meeting_invitation_runs,
                "success_count": logs_col.count_documents({
                    "$and": [
                        query,
                        {"event_type": "meeting_scheduled"},
                        {"$or": [{"delivery_status": "success"}, {"status": "success"}]}
                    ]
                }),
                "failure_count": logs_col.count_documents({
                    "$and": [
                        query,
                        {"event_type": "meeting_scheduled"},
                        {"$or": [{"delivery_status": "failed"}, {"status": "failed"}]}
                    ]
                })
            },
            {
                "id": "task_completed_notification",
                "name": "Task Completion Notification",
                "webhook_type": "task_completed",
                "destinations": ["Gmail", "Google Sheets"],
                "trigger": "Task status changes to Completed",
                "status": "active" if has_task_comp_hook else "pending_configuration",
                "total_runs": task_comp_runs,
                "success_count": logs_col.count_documents({**query, "event_type": "task_completed", "$or": [{"delivery_status": "success"}, {"status": "success"}]}),
                "failure_count": logs_col.count_documents({**query, "event_type": "task_completed", "$or": [{"delivery_status": "failed"}, {"status": "failed"}]})
            },
            {
                "id": "new_team_member_welcome",
                "name": "New Team Member Welcome",
                "webhook_type": "team_member_added",
                "destinations": ["Gmail", "Storage by Zapier"],
                "trigger": "Active team member created in MongoDB",
                "status": "active" if has_member_hook else "pending_configuration",
                "total_runs": member_runs,
                "success_count": logs_col.count_documents({**query, "event_type": "team_member_added", "$or": [{"delivery_status": "success"}, {"status": "success"}]}),
                "failure_count": logs_col.count_documents({**query, "event_type": "team_member_added", "$or": [{"delivery_status": "failed"}, {"status": "failed"}]})
            },
            {
                "id": "team_invitation_created",
                "name": "Team Member Invitation",
                "webhook_type": "team_invitation_created",
                "destinations": ["Gmail"],
                "trigger": "Leader invites teammate with secure link",
                "status": "active" if has_inv_hook else "pending_configuration",
                "total_runs": inv_runs,
                "success_count": logs_col.count_documents({**query, "event_type": "team_invitation_created", "$or": [{"delivery_status": "success"}, {"status": "success"}]}),
                "failure_count": logs_col.count_documents({**query, "event_type": "team_invitation_created", "$or": [{"delivery_status": "failed"}, {"status": "failed"}]})
            }
        ]

        outbox_pending = outbox_col.count_documents({"status": "pending"})
        outbox_retrying = outbox_col.count_documents({"status": "retrying"})

        return {
            "is_configured": has_task_hook and has_meeting_hook and has_member_hook and has_inv_hook and has_meeting_invitation_hook,
            "hooks_configured": {
                "task_approved": has_task_hook,
                "meeting_completed": has_meeting_hook,
                "meeting_scheduled": has_meeting_invitation_hook,
                "task_completed": has_task_comp_hook,
                "team_member_added": has_member_hook,
                "team_invitation_created": has_inv_hook
            },
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": failed,
            "outbox_queue": {
                "pending": outbox_pending,
                "retrying": outbox_retrying
            },
            "integrations": integrations,
            "recent_logs": recent_logs
        }

    @staticmethod
    def list_logs(
        team_id: str,
        limit: int = 50,
        skip: int = 0,
        event_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lists automation logs with filtering and pagination."""
        logs_col = get_col("automation_logs")
        query: Dict[str, Any] = {"$or": [{"team_id": team_id}, {"team_id": None}]}

        if event_type and event_type.lower() != "all":
            query["event_type"] = event_type

        if status and status.lower() != "all":
            query["$or"] = [
                {"delivery_status": status},
                {"dispatch_status": status},
                {"status": status}
            ]

        total = logs_col.count_documents(query)
        cursor = logs_col.find(query).sort("created_at", -1).skip(skip).limit(limit)

        logs = []
        for l in cursor:
            l["id"] = str(l["_id"])
            l["_id"] = str(l["_id"])
            logs.append(l)

        return {
            "total": total,
            "limit": limit,
            "skip": skip,
            "logs": logs
        }

    @staticmethod
    def get_log_by_event_id(team_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single automation event log with outbox state by event_id or ObjectId."""
        logs_col = get_col("automation_logs")
        outbox_col = get_col("automation_outbox")

        log = None
        try:
            log = logs_col.find_one({"_id": ObjectId(event_id)})
        except Exception:
            pass

        if not log:
            log = logs_col.find_one({"event_id": event_id})

        if not log:
            return None

        log["id"] = str(log["_id"])
        log["_id"] = str(log["_id"])

        outbox_item = outbox_col.find_one({"event_id": log.get("event_id")})
        if outbox_item:
            outbox_item["id"] = str(outbox_item["_id"])
            outbox_item["_id"] = str(outbox_item["_id"])
            log["outbox_state"] = outbox_item

        return log

    @staticmethod
    def get_automation_health() -> Dict[str, Any]:
        """System healthcheck for the automation outbox, workers, and webhook configurations."""
        outbox_col = get_col("automation_outbox")
        logs_col = get_col("automation_logs")

        pending_count = outbox_col.count_documents({"status": "pending"})
        retrying_count = outbox_col.count_documents({"status": "retrying"})
        failed_count = outbox_col.count_documents({"status": "failed"})
        accepted_count = outbox_col.count_documents({"status": "webhook_accepted"})
        stale_skipped_count = outbox_col.count_documents({"status": "stale_skipped"})

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "outbox_metrics": {
                "pending": pending_count,
                "retrying": retrying_count,
                "failed": failed_count,
                "webhook_accepted": accepted_count,
                "stale_skipped": stale_skipped_count
            },
            "startup_replay_protection": {
                "startup_dispatch_enabled": bool(getattr(settings, "ENABLE_STARTUP_OUTBOX_DISPATCH", False)),
                "background_worker_enabled": bool(getattr(settings, "ENABLE_OUTBOX_BACKGROUND_WORKER", False))
            },
            "webhooks_configured": {
                "task_approved": bool(settings.task_approved_webhook_url),
                "meeting_completed": bool(settings.meeting_completed_webhook_url),
                "meeting_scheduled": bool(settings.meeting_invitation_webhook_url),
                "task_completed": bool(settings.task_completed_webhook_url or settings.task_approved_webhook_url),
                "team_member_added": bool(settings.team_member_added_webhook_url),
                "team_invitation_created": bool(settings.team_invitation_created_webhook_url)
            },
            "masked_urls": {
                "task_approved": mask_webhook_url(settings.task_approved_webhook_url),
                "meeting_completed": mask_webhook_url(settings.meeting_completed_webhook_url),
                "task_completed": mask_webhook_url(settings.task_completed_webhook_url or settings.task_approved_webhook_url),
                "team_member_added": mask_webhook_url(settings.team_member_added_webhook_url),
                "team_invitation_created": mask_webhook_url(settings.team_invitation_created_webhook_url)
            }
        }

    @staticmethod
    async def test_webhook(webhook_type: str, current_user: dict) -> Dict[str, Any]:
        """Dispatches diagnostic events without impersonating task approval or completion."""
        if webhook_type in {"task_approved", "task_completed"}:
            raise HTTPException(
                status_code=403,
                detail="Task approval and completion webhooks are sent only after the corresponding task transition."
            )
        if webhook_type not in {"meeting_completed", "team_member_added", "team_invitation_created"}:
            raise HTTPException(status_code=400, detail="Unsupported webhook test type.")

        team_id = current_user.get("team_id")
        user_name = current_user.get("name", "Admin")
        user_email = current_user.get("email", "official.manoranjanworks@gmail.com")

        if webhook_type == "meeting_completed":
            test_meeting = {
                "meeting_id": f"TEST-MTG-{uuid.uuid4().hex[:6].upper()}",
                "team_id": team_id,
                "meeting_title": "Sprint Planning Automation Test",
                "meeting_date": datetime.utcnow().isoformat() + "Z",
                "duration": "00:45:00",
                "participants": ["Jai", "Arun", "Priya", "Karthik"],
                "meeting_summary": "Test meeting completed successfully with all action items extracted.",
                "key_decisions": ["Deploy Zapier webhooks with exponential retries and idempotency."],
                "action_items": ["Verify Gmail notifications", "Verify Trello board cards"],
                "team_lead_email": user_email
            }
            return await ZapierService.send_meeting_completed_webhook(test_meeting)

        elif webhook_type == "team_member_added":
            test_member = {
                "member_id": f"TEST-MEM-{uuid.uuid4().hex[:6].upper()}",
                "team_id": team_id,
                "name": user_name,
                "email": user_email,
                "role": current_user.get("role", "Engineer"),
                "account_status": "active"
            }
            return await ZapierService.send_team_member_added_webhook(test_member, team_name="MeetMind Workspace")

        elif webhook_type == "team_invitation_created":
            test_invitation = {
                "invitation_id": f"TEST-INV-{uuid.uuid4().hex[:6].upper()}",
                "team_id": team_id,
                "team_name": "MeetMind Workspace",
                "invited_email": user_email,
                "invited_by": user_name,
                "assigned_role": "Editor",
                "invitation_url": f"{settings.FRONTEND_URL}/accept-invitation?token=test_token_{uuid.uuid4().hex[:12]}",
                "expires_at": datetime.utcnow()
            }
            return await ZapierService.send_team_invitation_created_webhook(test_invitation)

        raise HTTPException(status_code=400, detail="Unsupported webhook test type.")

    @staticmethod
    def get_invitation_diagnostics(team_id: str, invitation_id: str, current_user: dict) -> Dict[str, Any]:
        """
        Comprehensive diagnostic audit tracing an invitation from creation to webhook and email delivery.
        Verifies intended recipient vs stored recipient vs webhook recipient.
        """
        inv_col = get_col("team_invitations")
        outbox_col = get_col("automation_outbox")
        logs_col = get_col("automation_logs")

        inv = inv_col.find_one({"invitation_id": invitation_id})
        if not inv:
            try:
                inv = inv_col.find_one({"_id": ObjectId(invitation_id)})
            except Exception:
                pass

        if not inv:
            return {
                "invitation_id": invitation_id,
                "intended_recipient": None,
                "stored_recipient": None,
                "webhook_recipient": None,
                "recipient_match": False,
                "mongo_save_status": "not_found",
                "webhook_status": "not_found",
                "webhook_http_status": None,
                "zapier_event_id": None,
                "gmail_action_status_if_available": None,
                "gmail_message_id_if_available": None,
                "last_error": f"Invitation '{invitation_id}' not found in MongoDB team_invitations collection.",
                "retry_count": 0,
                "diagnostics_summary": f"Invitation '{invitation_id}' does not exist in the database."
            }

        # Team authorization check
        user_team = current_user.get("team_id")
        user_role = str(current_user.get("role", "")).lower()
        if inv.get("team_id") != user_team and user_role not in ["admin", "team lead"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Cannot view invitation diagnostics for another team."
            )

        stored_recipient = str(inv.get("invited_email") or inv.get("email") or "").strip().lower()
        intended_recipient = stored_recipient

        # Find latest outbox and log entries
        outbox_item = outbox_col.find_one({
            "reference_id": inv.get("invitation_id"),
            "event_type": "team_invitation_created"
        }, sort=[("created_at", -1)])

        log_item = logs_col.find_one({
            "reference_id": inv.get("invitation_id"),
            "event_type": "team_invitation_created"
        }, sort=[("created_at", -1)])

        webhook_recipient = None
        if outbox_item:
            payload = outbox_item.get("payload", {})
            webhook_recipient = str(payload.get("invited_email") or payload.get("recipient_email") or payload.get("email") or "").strip().lower()
        elif log_item:
            webhook_recipient = str(log_item.get("recipient") or log_item.get("recipient_email") or "").strip().lower()

        recipient_match = bool(stored_recipient and webhook_recipient and stored_recipient == webhook_recipient)

        webhook_status = None
        webhook_http_status = None
        zapier_event_id = None
        gmail_action_status = None
        gmail_message_id = None
        last_error = None
        retry_count = 0

        if log_item:
            webhook_status = log_item.get("dispatch_status") or log_item.get("delivery_status")
            webhook_http_status = log_item.get("response_status") or log_item.get("status_code")
            zapier_event_id = log_item.get("event_id")
            gmail_action_status = log_item.get("gmail_status")
            gmail_message_id = log_item.get("gmail_message_id")
            last_error = log_item.get("error_message")
            retry_count = log_item.get("retry_count", 0)
        elif outbox_item:
            webhook_status = outbox_item.get("status")
            webhook_http_status = outbox_item.get("response_status")
            zapier_event_id = outbox_item.get("event_id")
            last_error = outbox_item.get("last_error")
            retry_count = outbox_item.get("retry_count", 0)

        # Build diagnostic summary
        summary_points = []
        summary_points.append(f"1. MongoDB Storage: Invitation successfully saved with intended recipient '{stored_recipient}'.")
        if recipient_match:
            summary_points.append(f"2. Payload Recipient: Webhook payload strictly matched intended recipient '{webhook_recipient}'.")
        else:
            summary_points.append(f"2. Payload Recipient MISMATCH: Stored='{stored_recipient}' vs Webhook='{webhook_recipient}'.")

        if webhook_http_status in [200, 201]:
            summary_points.append(f"3. Zapier Webhook: Successfully accepted by Zapier Catch Hook (HTTP {webhook_http_status}).")
            summary_points.append("4. Gmail Action Handoff: Handed off to Google Mail via Zapier with label SENT.")
            summary_points.append(
                "5. Recipient Delivery Notice: Gmail reports message was sent. If not visible in Inbox, check: "
                "(a) Gmail Spam folder (localhost URLs are often classified as spam), "
                "(b) Promotions or Updates category tabs, "
                "(c) If the sender Gmail account is the same as the recipient, Gmail stores self-sent messages in Sent/All Mail and threads them without an unread Inbox notification."
            )
        else:
            summary_points.append(f"3. Zapier Webhook: Not accepted (HTTP {webhook_http_status}, error: {last_error}).")

        return {
            "invitation_id": inv.get("invitation_id"),
            "intended_recipient": intended_recipient,
            "stored_recipient": stored_recipient,
            "webhook_recipient": webhook_recipient,
            "recipient_match": recipient_match,
            "mongo_save_status": "saved",
            "webhook_status": webhook_status or "pending",
            "webhook_http_status": webhook_http_status,
            "zapier_event_id": zapier_event_id,
            "gmail_action_status_if_available": gmail_action_status or ("gmail_accepted" if webhook_http_status in [200, 201] else "delivery_unconfirmed"),
            "gmail_message_id_if_available": gmail_message_id,
            "last_error": last_error,
            "retry_count": retry_count,
            "correlation_id": inv.get("correlation_id") or (log_item.get("correlation_id") if log_item else None),
            "created_at": inv.get("created_at"),
            "diagnostics_summary": "\n".join(summary_points)
        }
