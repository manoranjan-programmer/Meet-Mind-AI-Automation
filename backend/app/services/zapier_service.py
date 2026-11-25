import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from urllib.parse import quote
from zoneinfo import ZoneInfo
import httpx
from bson import ObjectId

from app.config import settings
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.zapier")

DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5
OUTBOX_POLL_INTERVAL_SECONDS = 30.0


def mask_webhook_url(url: Optional[str]) -> str:
    """Mask sensitive catch hook paths in audit logs to protect credentials."""
    if not url:
        return "NOT_CONFIGURED"
    parts = url.split("hooks.zapier.com/hooks/catch/")
    if len(parts) > 1:
        prefix = parts[0] + "hooks.zapier.com/hooks/catch/"
        return prefix + "******"
    return url[:25] + "******"


def get_webhook_url_for_event(event_type: str) -> Optional[str]:
    """Resolves backend environment webhook URL based on event type."""
    if event_type == "task_approved":
        return settings.task_approved_webhook_url
    elif event_type == "meeting_completed":
        return settings.meeting_completed_webhook_url
    elif event_type == "task_completed":
        return settings.task_completed_webhook_url
    elif event_type == "team_member_added":
        return settings.team_member_added_webhook_url
    elif event_type == "team_invitation_created":
        return settings.team_invitation_created_webhook_url
    elif event_type == "meeting_scheduled":
        return settings.meeting_invitation_webhook_url
    return None


class ZapierService:
    """
    Centralized, resilient, database-backed automation engine for MeetMind AI.
    Features:
      - Automation Outbox Pattern (MongoDB `automation_outbox`)
      - Guaranteed delivery surviving server/container restarts
      - Strict idempotency via `processed_events`
      - Granular lifecycle tracking:
          * pending
          * processing
          * webhook_accepted
          * zapier_action_success
          * email_action_success
          * delivery_unconfirmed
          * failed
          * retrying
      - Universal recipient aliases preventing Zapier filter/mapping drops
      - Controlled exponential backoff retries
    """

    @staticmethod
    def _create_outbox_record(
        event_id: str,
        event_type: str,
        reference_id: str,
        payload: Dict[str, Any],
        webhook_url: str,
        team_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> ObjectId:
        """Persists automation event into MongoDB outbox before HTTP attempt."""
        outbox_col = get_col("automation_outbox")
        now = datetime.utcnow()
        doc = {
            "event_id": event_id,
            "correlation_id": correlation_id or payload.get("correlation_id"),
            "event_type": event_type,
            "reference_id": reference_id,
            "team_id": team_id,
            "payload": payload,
            "webhook_url": webhook_url,
            "status": "pending",
            "attempt_count": 0,
            "retry_count": 0,
            "max_retries": MAX_RETRIES,
            "next_retry_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now
        }
        res = outbox_col.insert_one(doc)
        return res.inserted_id

    @staticmethod
    def _record_processed_event(event_id: str, event_type: str, reference_id: str):
        """Records event in processed_events collection for idempotency verification."""
        try:
            col = get_col("processed_events")
            col.update_one(
                {"event_id": event_id},
                {
                    "$setOnInsert": {
                        "event_id": event_id,
                        "event_type": event_type,
                        "reference_id": reference_id,
                        "processed_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.warning(f"Failed to record processed_event {event_id}: {e}")

    @staticmethod
    def cleanup_stale_outbox_on_startup() -> int:
        """
        Executed strictly during FastAPI server startup.
        Marks any pending or retrying outbox events from prior sessions as 'stale_skipped',
        preventing any automatic or accidental dispatch upon server startup or reboot.
        """
        try:
            outbox_col = get_col("automation_outbox")
            now = datetime.utcnow()
            result = outbox_col.update_many(
                {"status": {"$in": ["pending", "retrying"]}},
                {
                    "$set": {
                        "status": "stale_skipped",
                        "last_error": "Marked stale on startup to prevent unwanted webhook replay",
                        "next_retry_at": None,
                        "updated_at": now
                    }
                }
            )
            return result.modified_count
        except Exception as e:
            logger.warning(f"Could not clean up stale outbox records on startup: {e}")
            return 0

    @staticmethod
    def _is_event_already_processed(event_id: str, event_type: str, reference_id: str) -> bool:
        """Checks processed_events, automation_logs, and automation_outbox to prevent duplicate dispatches."""
        try:
            pe_col = get_col("processed_events")
            if pe_col.find_one({"event_id": event_id}):
                return True
            if reference_id and pe_col.find_one({"reference_id": reference_id, "event_type": event_type}):
                return True
            logs_col = get_col("automation_logs")
            success_log = logs_col.find_one({
                "$or": [
                    {"event_id": event_id},
                    {"reference_id": reference_id, "event_type": event_type} if reference_id else {"event_id": event_id}
                ],
                "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
            })
            if success_log:
                return True
            return False
        except Exception as e:
            logger.warning(f"Error checking processed status for {event_id}: {e}")
            return False

    @staticmethod
    async def _post_with_retries(
        webhook_url: str,
        payload: Dict[str, Any],
        event_id: str,
        event_type: str,
        reference_id: str,
        webhook_type: str,
        team_id: Optional[str] = None,
        outbox_id: Optional[ObjectId] = None,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes HTTP POST to Zapier Catch Hook with controlled exponential retries.
        Logs every attempt into the automation_logs and updates automation_outbox.
        """
        logs_col = get_col("automation_logs")
        outbox_col = get_col("automation_outbox")
        now = datetime.utcnow()
        corr_id = correlation_id or payload.get("correlation_id")
        corr_tag = f"[{corr_id}] " if corr_id else ""

        recipient = (
            payload.get("team_leader_email")
            or payload.get("assigned_email")
            or payload.get("recipient_email")
            or payload.get("email")
            or payload.get("invited_email")
            or payload.get("team_lead_email")
            or payload.get("to_email")
            or ""
        )

        # 0. Check global safety toggle to prevent any accidental external automation dispatches
        if not getattr(settings, "ENABLE_AUTOMATION_DISPATCH", False):
            logger.info(
                f"[AUTOMATION DISABLED] Skipping HTTP POST for Zapier webhook [{event_type}] "
                f"ref {reference_id} because ENABLE_AUTOMATION_DISPATCH is False."
            )
            log_entry = {
                "event_id": event_id,
                "correlation_id": corr_id,
                "event_type": event_type,
                "reference_id": reference_id,
                "task_id": reference_id if event_type in ["task_approved", "task_completed"] else None,
                "meeting_id": reference_id if event_type == "meeting_completed" else payload.get("meeting_id"),
                "webhook_type": webhook_type,
                "recipient": recipient,
                "recipient_email": recipient,
                "delivery_status": "skipped",
                "dispatch_status": "skipped",
                "zapier_status": "skipped",
                "gmail_status": "skipped",
                "status": "skipped",
                "attempt_count": 0,
                "retry_count": 0,
                "response_status": "skipped",
                "status_code": 200,
                "error_message": "Automation dispatch globally disabled by ENABLE_AUTOMATION_DISPATCH=false",
                "team_id": team_id,
                "masked_url": mask_webhook_url(webhook_url),
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            logs_col.insert_one(log_entry)
            if outbox_id:
                outbox_col.update_one(
                    {"_id": outbox_id},
                    {"$set": {"status": "skipped", "last_error": "Automation dispatch disabled by config", "updated_at": now}}
                )
            return {
                "success": True,
                "status": "skipped",
                "delivery_status": "skipped",
                "dispatch_status": "skipped",
                "zapier_status": "skipped",
                "gmail_status": "skipped",
                "status_code": 200,
                "event_id": event_id,
                "reason": "automation_disabled_by_config"
            }

        # 1. Initialize or query log entry in MongoDB
        log_entry = {
            "event_id": event_id,
            "correlation_id": corr_id,
            "event_type": event_type,
            "reference_id": reference_id,
            "task_id": reference_id if event_type in ["task_approved", "task_completed"] else None,
            "meeting_id": reference_id if event_type == "meeting_completed" else payload.get("meeting_id"),
            "webhook_type": webhook_type,
            "recipient": recipient,
            "recipient_email": recipient,
            "delivery_status": "pending",
            "dispatch_status": "processing",
            "zapier_status": "pending",
            "gmail_status": "pending",
            "status": "pending",
            "attempt_count": 0,
            "retry_count": 0,
            "response_status": None,
            "status_code": None,
            "error_message": None,
            "team_id": team_id,
            "masked_url": mask_webhook_url(webhook_url),
            "payload": payload,
            "created_at": now,
            "updated_at": now
        }
        res_insert = logs_col.insert_one(log_entry)
        log_db_id = res_insert.inserted_id

        attempt = 0
        last_error: Optional[str] = None
        response_code: Optional[int] = None
        response_text: Optional[str] = None
        is_success = False
        is_retryable = True

        backoff = INITIAL_BACKOFF_SECONDS

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            while attempt < MAX_RETRIES:
                attempt += 1
                try:
                    logger.info(
                        f"Dispatching Zapier webhook [{event_type}] attempt {attempt}/{MAX_RETRIES} "
                        f"for ref {reference_id} (event: {event_id})"
                    )
                    resp = await client.post(
                        webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    response_code = resp.status_code
                    response_text = resp.text[:400]

                    # Treat 2xx and Zapier status 200/201/202 as success
                    if 200 <= resp.status_code < 300:
                        is_success = True
                        last_error = None
                        is_retryable = False
                        break
                    elif 400 <= resp.status_code < 500:
                        # Client error (e.g. 404, 400, 422) - strictly non-retryable
                        last_error = f"HTTP {resp.status_code}: {response_text}"
                        is_retryable = False
                        break
                    else:
                        # 5xx server error: retryable
                        last_error = f"HTTP {resp.status_code}: {response_text}"
                        is_retryable = True

                except (httpx.TimeoutException, httpx.NetworkError, httpx.RequestError) as e:
                    last_error = f"{type(e).__name__}: {str(e)}"
                    is_retryable = True
                    logger.warning(
                        f"Transient network error on Zapier webhook {event_type} attempt {attempt}: {last_error}"
                    )
                except Exception as e:
                    last_error = f"Unexpected dispatch error: {str(e)}"
                    is_retryable = False
                    break

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff *= 2

        # 2. Derive standardized status fields
        updated_at = datetime.utcnow()
        if is_success:
            final_delivery_status = "success"
            final_dispatch_status = "webhook_accepted"
            final_zapier_status = "zapier_action_success"
            final_gmail_status = "gmail_accepted"
            gmail_notice = "Email accepted by Gmail; inbox delivery not independently confirmed (check Spam/Promotions if not in inbox)."
            outbox_status = "webhook_accepted"
            next_retry = None
            ZapierService._record_processed_event(event_id, event_type, reference_id)
        else:
            final_delivery_status = "failed"
            final_dispatch_status = "failed"
            final_zapier_status = "failed"
            final_gmail_status = "delivery_unconfirmed"
            gmail_notice = f"Webhook delivery failed: {last_error}"
            outbox_status = "failed" if (not is_retryable or attempt >= MAX_RETRIES) else "retrying"
            next_retry = updated_at + timedelta(seconds=60) if outbox_status == "retrying" else None

        # 3. Update automation_logs
        logs_col.update_one(
            {"_id": log_db_id},
            {
                "$set": {
                    "delivery_status": final_delivery_status,
                    "dispatch_status": final_dispatch_status,
                    "zapier_status": final_zapier_status,
                    "gmail_status": final_gmail_status,
                    "gmail_notice": gmail_notice,
                    "status": final_delivery_status,
                    "attempt_count": attempt,
                    "retry_count": max(0, attempt - 1),
                    "response_status": response_code,
                    "status_code": response_code,
                    "error_message": last_error,
                    "response_body": response_text,
                    "updated_at": updated_at
                }
            }
        )

        # 4. Update automation_outbox if outbox_id provided
        if outbox_id:
            outbox_col.update_one(
                {"_id": outbox_id},
                {
                    "$set": {
                        "status": outbox_status,
                        "attempt_count": attempt,
                        "retry_count": max(0, attempt - 1),
                        "response_status": response_code,
                        "last_error": last_error,
                        "next_retry_at": next_retry,
                        "updated_at": updated_at
                    }
                }
            )

        logger.info(
            f"Zapier webhook {event_type} finished: status={final_delivery_status} ({final_dispatch_status}), "
            f"attempts={attempt}, code={response_code}"
        )

        return {
            "event_id": event_id,
            "delivery_status": final_delivery_status,
            "dispatch_status": final_dispatch_status,
            "zapier_status": final_zapier_status,
            "gmail_status": final_gmail_status,
            "gmail_notice": gmail_notice,
            "status": final_delivery_status,
            "attempt_count": attempt,
            "retry_count": max(0, attempt - 1),
            "response_status": response_code,
            "error_message": last_error,
            "log_id": str(log_db_id)
        }

    # =========================================================================
    # EVENT 1: APPROVED TASK
    # =========================================================================
    @staticmethod
    async def send_task_approved_webhook(
        task_doc: Dict[str, Any],
        approved_by_name: str = "Admin"
    ) -> Dict[str, Any]:
        """
        Event 1: Approved Task.
        Triggered only after a team leader approves a task.
        Payload strictly adheres to:
        {
          "event": "task_approved",
          "event_id": "unique_event_id",
          "task_id": "actual_task_id",
          "meeting_id": "actual_meeting_id",
          "meeting_title": "actual_meeting_title",
          "task_title": "actual_task_title",
          "description": "actual_task_description",
          "assigned_member": "actual_member_name",
          "assigned_email": "actual_member_email",
          "priority": "actual_priority",
          "deadline": "actual_deadline_or_null",
          "status": "Approved",
          "approval_status": "approved"
        }
        """
        logs_col = get_col("automation_logs")
        task_id = str(task_doc.get("task_id") or "")
        team_id = str(task_doc.get("team_id") or "")

        # 1. Validation: Task must be approved
        approval_status = str(task_doc.get("approval_status") or "").lower()
        if approval_status not in ["approved"]:
            logger.warning(f"Task {task_id} approval_status='{task_doc.get('approval_status')}'. Skipping webhook.")
            return {
                "delivery_status": "skipped",
                "reason": "unapproved_task",
                "message": f"Task '{task_id}' has approval_status='{task_doc.get('approval_status')}'. Only approved tasks can trigger Zapier."
            }

        # 2. Idempotency Check
        existing_success = logs_col.find_one({
            "reference_id": task_id,
            "event_type": "task_approved",
            "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
        })
        if existing_success:
            logger.info(f"Task {task_id} approved notification already delivered. Skipping duplicate.")
            return {
                "delivery_status": "skipped",
                "reason": "already_delivered",
                "message": f"Approved notification for task '{task_id}' was already dispatched.",
                "event_id": existing_success.get("event_id"),
                "log_id": str(existing_success["_id"])
            }

        # 3. Format payload with real MongoDB data
        event_id = f"EVT-TSK-APP-{uuid.uuid4().hex[:8].upper()}"
        deadline_val = task_doc.get("deadline")
        if isinstance(deadline_val, datetime):
            deadline_str = deadline_val.isoformat() + "Z"
        elif isinstance(deadline_val, str) and deadline_val.strip() and deadline_val.strip().lower() not in ("none", "null", "undefined"):
            deadline_str = deadline_val.strip()
        elif deadline_val and not isinstance(deadline_val, str):
            deadline_str = str(deadline_val)
        else:
            deadline_str = "Not specified"

        base_frontend_url = (settings.FRONTEND_URL or "").strip().rstrip("/")
        lower_url = base_frontend_url.lower()
        is_invalid_url = (
            not base_frontend_url
            or not (lower_url.startswith("https://") or lower_url.startswith("http://"))
            or "example.com" in lower_url
            or "insert_dashboard_url_field_here" in lower_url
        )
        if is_invalid_url:
            logger.error(
                "FRONTEND_URL is missing or invalid (cannot be example.com or a placeholder). "
                "Configure FRONTEND_URL in backend/.env or Render environment variables."
            )
            review_task_url = ""
        else:
            review_task_url = f"{base_frontend_url}/tasks/{task_id}"

        # Resolve member email and name from member_profiles if not present
        assigned_email = task_doc.get("assigned_member_email") or ""
        assigned_member = task_doc.get("assigned_member_name") or "Unassigned"
        if (not assigned_email or assigned_member == "Unassigned") and task_doc.get("assigned_member_id"):
            member_col = get_col("member_profiles")
            m = member_col.find_one({"team_id": team_id, "member_id": task_doc["assigned_member_id"]})
            if m:
                assigned_email = m.get("email", assigned_email)
                assigned_member = m.get("name", assigned_member)

        # Enforce validation: Must have a recipient email
        if not assigned_email:
            assigned_email = "official.manoranjanworks@gmail.com"

        task_title = task_doc.get("title") or task_doc.get("task_title") or "Approved Task"
        task_desc = task_doc.get("description") or ""
        meeting_id = task_doc.get("meeting_id") or "manual"
        meeting_title = task_doc.get("meeting_title") or "Sprint Planning Sync"
        priority = task_doc.get("priority") or "Medium"

        # Strictly formatted payload with universal aliases
        payload = {
            "event": "task_approved",
            "event_id": event_id,
            "task_id": task_id,
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "task_title": task_title,
            "description": task_desc,
            "assigned_member": assigned_member,
            "assigned_email": assigned_email,
            "priority": priority,
            "deadline": deadline_str,
            "status": "Approved",
            "approval_status": "approved",
            "dashboard_url": review_task_url,
            "task_url": review_task_url,
            "review_url": review_task_url,
            "app_url": base_frontend_url,
            "frontend_url": base_frontend_url,
            # Universal aliases for Zapier field mappings
            "title": task_title,
            "task_description": task_desc,
            "recipient_email": assigned_email,
            "to_email": assigned_email,
            "to": assigned_email,
            "email": assigned_email,
            "assigned_name": assigned_member,
            "approved_by": approved_by_name,
            "email_subject": f"MeetMind AI – Approved Task: {task_title}",
            "email_body": (
                f"Hello {assigned_member},\n\n"
                f"A new task has been approved for you in MeetMind AI.\n\n"
                f"Task Title: {task_title}\n"
                f"Description: {task_desc}\n"
                f"Meeting: {meeting_title}\n"
                f"Priority: {priority}\n"
                f"Deadline: {deadline_str}\n"
                f"Status: Approved\n"
                + (f"Review Task in Dashboard: {review_task_url}\n\n" if review_task_url else "\n")
                + "Best regards,\nMeetMind AI Automation Engine"
            )
        }

        # 4. Outbox persistence
        webhook_url = settings.task_approved_webhook_url
        if not webhook_url or not webhook_url.strip():
            logger.error("ZAPIER_TASK_APPROVED_WEBHOOK_URL is not configured.")
            now = datetime.utcnow()
            log_doc = {
                "event_id": event_id,
                "event_type": "task_approved",
                "reference_id": task_id,
                "task_id": task_id,
                "webhook_type": "task_approved",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": "ZAPIER_TASK_APPROVED_WEBHOOK_URL is not configured in backend environment",
                "team_id": team_id,
                "masked_url": "NOT_CONFIGURED",
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            res = logs_col.insert_one(log_doc)
            return {
                "delivery_status": "failed",
                "error_message": log_doc["error_message"],
                "event_id": event_id,
                "log_id": str(res.inserted_id)
            }

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="task_approved",
            reference_id=task_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="task_approved",
            reference_id=task_id,
            webhook_type="task_approved",
            team_id=team_id,
            outbox_id=outbox_id
        )

    # =========================================================================
    # EVENT 2: MEETING COMPLETED
    # =========================================================================
    @staticmethod
    async def send_meeting_completed_webhook(meeting_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Event 2: Meeting Completed.
        Triggered only when a meeting is genuinely completed and its summary is saved.
        Payload strictly adheres to:
        {
          "event": "meeting_completed",
          "event_id": "unique_event_id",
          "meeting_id": "actual_meeting_id",
          "meeting_title": "actual_meeting_title",
          "meeting_date": "actual_meeting_date",
          "duration": "actual_duration",
          "participants": [],
          "meeting_summary": "actual_summary",
          "key_decisions": [],
          "action_items": [],
          "team_lead_email": "actual_team_lead_email"
        }
        """
        logs_col = get_col("automation_logs")
        meeting_id = str(meeting_doc.get("meeting_id") or "")
        team_id = str(meeting_doc.get("team_id") or "")

        # 1. Validation: Meeting summary required
        summary = meeting_doc.get("meeting_summary") or meeting_doc.get("summary")
        if not summary or str(summary).strip() == "":
            logger.warning(f"Meeting {meeting_id} missing AI summary. Skipping webhook.")
            return {
                "delivery_status": "skipped",
                "reason": "incomplete_analysis",
                "message": "Meeting must have an AI summary before triggering completion webhook."
            }

        # 2. Idempotency Check
        existing_success = logs_col.find_one({
            "reference_id": meeting_id,
            "event_type": "meeting_completed",
            "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
        })
        if existing_success:
            logger.info(f"Meeting {meeting_id} completed webhook already dispatched. Skipping duplicate.")
            return {
                "delivery_status": "skipped",
                "reason": "already_delivered",
                "event_id": existing_success.get("event_id"),
                "log_id": str(existing_success["_id"])
            }

        # 3. Format payload
        event_id = f"EVT-MTG-CMP-{uuid.uuid4().hex[:8].upper()}"
        m_date = meeting_doc.get("meeting_date") or meeting_doc.get("created_at") or datetime.utcnow()
        if isinstance(m_date, datetime):
            m_date_str = m_date.isoformat() + "Z"
        else:
            m_date_str = str(m_date)

        raw_participants = meeting_doc.get("participants", [])
        if isinstance(raw_participants, list):
            participants_list = [str(p) for p in raw_participants]
        elif raw_participants:
            participants_list = [str(raw_participants)]
        else:
            participants_list = []

        raw_decisions = meeting_doc.get("key_decisions", [])
        if isinstance(raw_decisions, list):
            decisions_list = [str(d) for d in raw_decisions]
        elif raw_decisions:
            decisions_list = [str(raw_decisions)]
        else:
            decisions_list = []

        raw_actions = meeting_doc.get("action_items", [])
        if isinstance(raw_actions, list):
            action_items_list = [
                item.get("title", str(item)) if isinstance(item, dict) else str(item)
                for item in raw_actions
            ]
        elif raw_actions:
            action_items_list = [str(raw_actions)]
        else:
            action_items_list = []

        team_lead_email = (
            meeting_doc.get("team_lead_email")
            or meeting_doc.get("created_by_email")
            or "official.manoranjanworks@gmail.com"
        )
        meeting_title = meeting_doc.get("meeting_title") or meeting_doc.get("title") or "Meeting Summary"
        duration_str = str(meeting_doc.get("duration") or "00:30:00")

        payload = {
            "event": "meeting_completed",
            "event_id": event_id,
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "meeting_date": m_date_str,
            "duration": duration_str,
            "participants": participants_list,
            "meeting_summary": str(summary),
            "key_decisions": decisions_list,
            "action_items": action_items_list,
            "team_lead_email": team_lead_email,
            # Universal aliases for Zapier field mappings
            "recipient_email": team_lead_email,
            "to_email": team_lead_email,
            "to": team_lead_email,
            "email": team_lead_email,
            "title": meeting_title,
            "summary": str(summary),
            "participants_text": ", ".join(participants_list),
            "key_decisions_text": "; ".join(decisions_list),
            "action_items_text": "; ".join(action_items_list),
            "email_subject": f"MeetMind AI – Meeting Summary: {meeting_title}",
            "email_body": (
                f"Meeting: {meeting_title}\n"
                f"Date: {m_date_str}\n"
                f"Duration: {duration_str}\n"
                f"Participants: {', '.join(participants_list)}\n\n"
                f"Executive Summary:\n{summary}\n\n"
                f"Key Decisions:\n" + ("\n- ".join([""] + decisions_list) if decisions_list else "None recorded") + "\n\n"
                f"Action Items:\n" + ("\n- ".join([""] + action_items_list) if action_items_list else "None recorded") + "\n\n"
                f"Best regards,\nMeetMind AI Intelligence"
            )
        }

        # 4. Outbox persistence
        webhook_url = settings.meeting_completed_webhook_url
        if not webhook_url or not webhook_url.strip():
            logger.error("ZAPIER_MEETING_COMPLETED_WEBHOOK_URL is not configured.")
            now = datetime.utcnow()
            log_doc = {
                "event_id": event_id,
                "event_type": "meeting_completed",
                "reference_id": meeting_id,
                "meeting_id": meeting_id,
                "webhook_type": "meeting_completed",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": "ZAPIER_MEETING_COMPLETED_WEBHOOK_URL is not configured in backend environment",
                "team_id": team_id,
                "masked_url": "NOT_CONFIGURED",
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            res = logs_col.insert_one(log_doc)
            return {
                "delivery_status": "failed",
                "error_message": log_doc["error_message"],
                "event_id": event_id,
                "log_id": str(res.inserted_id)
            }

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="meeting_completed",
            reference_id=meeting_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="meeting_completed",
            reference_id=meeting_id,
            webhook_type="meeting_completed",
            team_id=team_id,
            outbox_id=outbox_id
        )

    # =========================================================================
    # EVENT 3: TASK COMPLETED
    # =========================================================================
    @staticmethod
    def _resolve_team_leader(team_id: str) -> Dict[str, str]:
        """
        Resolves the workspace's Team Leader from MongoDB (teams -> users -> member_profiles).
        Never trusts client-supplied Team Leader emails.
        """
        if not team_id:
            return {"id": "", "name": "", "email": ""}

        teams_col = get_col("teams")
        users_col = get_col("users")
        member_col = get_col("member_profiles")

        team = teams_col.find_one({"team_id": team_id})
        if team:
            leader_uid = team.get("admin_id") or team.get("leader_id") or team.get("created_by")
            if leader_uid:
                u = users_col.find_one({"user_id": leader_uid})
                if u and u.get("email"):
                    return {
                        "id": u.get("user_id", ""),
                        "name": u.get("name", "Team Leader"),
                        "email": u.get("email", "").strip().lower(),
                    }

        leader_role_regex = {"$regex": "^(admin|team leader|team lead|team_leader|manager|team lead / admin|team leader / admin)$", "$options": "i"}
        leader_user = users_col.find_one({"team_id": team_id, "role": leader_role_regex})
        if leader_user and leader_user.get("email"):
            return {
                "id": leader_user.get("user_id", ""),
                "name": leader_user.get("name", "Team Leader"),
                "email": leader_user.get("email", "").strip().lower(),
            }

        leader_member = member_col.find_one({"team_id": team_id, "role": leader_role_regex, "account_status": "active"})
        if leader_member and leader_member.get("email"):
            leader_user = users_col.find_one({"email": leader_member["email"].strip().lower()})
            return {
                "id": leader_user.get("user_id", "") if leader_user else "",
                "name": (leader_user or {}).get("name") or leader_member.get("name", "Team Leader"),
                "email": leader_member.get("email", "").strip().lower(),
            }

        return {"id": "", "name": "", "email": ""}

    @staticmethod
    async def send_task_completed_webhook(
        task_doc: Dict[str, Any],
        team_lead_email: Optional[str] = None,
        completed_by: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Event 3: Task Completed.
        Triggered ONLY when an authenticated member explicitly marks a task as Completed.
        Sends notification to the workspace's Team Leader via ZAPIER_TASK_COMPLETED_WEBHOOK_URL.
        """
        logs_col = get_col("automation_logs")
        task_id = str(task_doc.get("task_id") or "")
        team_id = str(task_doc.get("team_id") or "")

        # 1. Validation: Status must be Completed
        if str(task_doc.get("status", "")).lower() != "completed":
            return {
                "delivery_status": "skipped",
                "reason": "task_not_completed",
                "message": f"Task '{task_id}' has status='{task_doc.get('status')}'. Only Completed tasks trigger this event."
            }

        # 2. Idempotency Check
        existing_success = logs_col.find_one({
            "reference_id": task_id,
            "event_type": "task_completed",
            "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
        })
        if existing_success:
            logger.info(f"Task {task_id} completion notification already delivered. Skipping duplicate.")
            return {
                "delivery_status": "skipped",
                "reason": "already_delivered",
                "event_id": existing_success.get("event_id"),
                "log_id": str(existing_success["_id"])
            }

        # 3. Resolve Team Leader from MongoDB (never use member's email as recipient)
        leader = ZapierService._resolve_team_leader(team_id)
        if not leader.get("email"):
            err_msg = f"Cannot send task_completed notification: Team Leader email not found in MongoDB for workspace '{team_id}'."
            logger.error(err_msg)
            now = datetime.utcnow()
            event_id = f"EVT-TSK-CMP-{uuid.uuid4().hex[:8].upper()}"
            res = logs_col.insert_one({
                "event_id": event_id,
                "event_type": "task_completed",
                "reference_id": task_id,
                "task_id": task_id,
                "webhook_type": "task_completed",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": err_msg,
                "team_id": team_id,
                "masked_url": mask_webhook_url(settings.task_completed_webhook_url),
                "payload": {},
                "created_at": now,
                "updated_at": now,
            })
            return {
                "delivery_status": "failed",
                "error_message": err_msg,
                "event_id": event_id,
                "log_id": str(res.inserted_id),
            }

        # 4. Format exact JSON payload with real MongoDB values
        event_id = f"EVT-TSK-CMP-{uuid.uuid4().hex[:8].upper()}"
        completed_at_val = task_doc.get("completed_at")
        if isinstance(completed_at_val, datetime):
            completed_at_iso = completed_at_val.isoformat() + "Z"
        elif completed_at_val:
            completed_at_iso = str(completed_at_val)
        else:
            completed_at_iso = datetime.utcnow().isoformat() + "Z"

        task_title = task_doc.get("title") or task_doc.get("task_title") or "Completed Task"
        task_desc = task_doc.get("description") or ""
        meeting_id = str(task_doc.get("meeting_id") or "")
        meeting_title = str(task_doc.get("meeting_title") or "")

        cb = completed_by or {}
        completed_by_id = str(cb.get("member_id") or task_doc.get("completed_by_id") or task_doc.get("assigned_member_id") or "")
        completed_by_name = str(cb.get("name") or task_doc.get("completed_by_name") or task_doc.get("assigned_member_name") or "")
        completed_by_email = str(cb.get("email") or task_doc.get("completed_by_email") or task_doc.get("assigned_member_email") or "")

        base_frontend_url = (settings.FRONTEND_URL or "").strip().rstrip("/")
        lower_url = base_frontend_url.lower()
        if (
            not base_frontend_url
            or not (lower_url.startswith("https://") or lower_url.startswith("http://"))
            or "example.com" in lower_url
            or "insert_dashboard_url_field_here" in lower_url
        ):
            dashboard_url = ""
        else:
            dashboard_url = f"{base_frontend_url}/tasks/{task_id}"

        payload = {
            "event_type": "task_completed",
            "event_id": event_id,
            "workspace_id": team_id,
            "task_id": task_id,
            "task_title": task_title,
            "task_description": task_desc,
            "task_status": "Completed",
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "completed_at": completed_at_iso,
            "completed_by_id": completed_by_id,
            "completed_by_name": completed_by_name,
            "completed_by_email": completed_by_email,
            "team_leader_id": leader["id"],
            "team_leader_name": leader["name"],
            "team_leader_email": leader["email"],
            "dashboard_url": dashboard_url,
        }

        # 5. Outbox persistence & dispatch via ZAPIER_TASK_COMPLETED_WEBHOOK_URL
        webhook_url = settings.task_completed_webhook_url
        if not webhook_url or not webhook_url.strip():
            logger.error("ZAPIER_TASK_COMPLETED_WEBHOOK_URL is not configured.")
            now = datetime.utcnow()
            log_doc = {
                "event_id": event_id,
                "event_type": "task_completed",
                "reference_id": task_id,
                "task_id": task_id,
                "webhook_type": "task_completed",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": "ZAPIER_TASK_COMPLETED_WEBHOOK_URL is not configured in backend environment",
                "team_id": team_id,
                "masked_url": "NOT_CONFIGURED",
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            res = logs_col.insert_one(log_doc)
            return {
                "delivery_status": "failed",
                "error_message": log_doc["error_message"],
                "event_id": event_id,
                "log_id": str(res.inserted_id)
            }

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="task_completed",
            reference_id=task_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="task_completed",
            reference_id=task_id,
            webhook_type="task_completed",
            team_id=team_id,
            outbox_id=outbox_id
        )

    # =========================================================================
    # EVENT 4: TEAM MEMBER ADDED
    # =========================================================================
    @staticmethod
    async def send_team_member_added_webhook(
        member_doc: Dict[str, Any],
        team_name: str = ""
    ) -> Dict[str, Any]:
        """
        Event 4: Team Member Added.
        Triggered only after a team member has been successfully created and activated in MongoDB.
        Payload strictly adheres to:
        {
          "event": "team_member_added",
          "event_id": "unique_event_id",
          "member_id": "actual_member_id",
          "team_id": "actual_team_id",
          "team_name": "actual_team_name",
          "name": "actual_member_name",
          "email": "actual_member_email",
          "role": "actual_member_role",
          "account_status": "active"
        }
        """
        logs_col = get_col("automation_logs")
        member_id = str(member_doc.get("member_id") or "")
        team_id = str(member_doc.get("team_id") or "")
        member_email = str(member_doc.get("email") or "").strip().lower()

        # 1. Validation
        if not member_id or not member_email:
            return {
                "delivery_status": "skipped",
                "reason": "invalid_member_document",
                "message": "Member document must include member_id and email."
            }

        # 2. Idempotency Check
        existing_success = logs_col.find_one({
            "reference_id": member_id,
            "event_type": "team_member_added",
            "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
        })
        if existing_success:
            logger.info(f"Team member {member_id} welcome webhook already dispatched. Skipping duplicate.")
            return {
                "delivery_status": "skipped",
                "reason": "already_delivered",
                "event_id": existing_success.get("event_id"),
                "log_id": str(existing_success["_id"])
            }

        # 3. Resolve team name
        if not team_name and team_id:
            teams_col = get_col("teams")
            t_doc = teams_col.find_one({"team_id": team_id})
            if t_doc:
                team_name = t_doc.get("name") or "MeetMind Workspace"
            else:
                team_name = "MeetMind Workspace"
        elif not team_name:
            team_name = "MeetMind Workspace"

        event_id = f"EVT-MEM-ADD-{uuid.uuid4().hex[:8].upper()}"
        member_name = member_doc.get("name") or "Team Member"
        member_role = member_doc.get("role") or "Member"

        payload = {
            "event": "team_member_added",
            "event_id": event_id,
            "member_id": member_id,
            "team_id": team_id,
            "team_name": team_name,
            "name": member_name,
            "email": member_email,
            "role": member_role,
            "account_status": "active",
            # Universal aliases for Zapier field mappings
            "recipient_email": member_email,
            "to_email": member_email,
            "to": member_email,
            "assigned_email": member_email,
            "email_subject": f"Welcome to {team_name} on MeetMind AI",
            "email_body": (
                f"Hello {member_name},\n\n"
                f"You have been successfully added to {team_name} as a {member_role}.\n\n"
                f"Workspace URL: {settings.FRONTEND_URL}\n"
                f"Account Status: Active\n\n"
                f"Welcome aboard!\nMeetMind AI Team"
            )
        }

        # 4. Outbox persistence
        webhook_url = settings.team_member_added_webhook_url
        if not webhook_url or not webhook_url.strip():
            logger.error("ZAPIER_TEAM_MEMBER_ADDED_WEBHOOK_URL is not configured.")
            now = datetime.utcnow()
            log_doc = {
                "event_id": event_id,
                "event_type": "team_member_added",
                "reference_id": member_id,
                "webhook_type": "team_member_added",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": "ZAPIER_TEAM_MEMBER_ADDED_WEBHOOK_URL is not configured in backend environment",
                "team_id": team_id,
                "masked_url": "NOT_CONFIGURED",
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            res = logs_col.insert_one(log_doc)
            return {
                "delivery_status": "failed",
                "error_message": log_doc["error_message"],
                "event_id": event_id,
                "log_id": str(res.inserted_id)
            }

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="team_member_added",
            reference_id=member_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="team_member_added",
            reference_id=member_id,
            webhook_type="team_member_added",
            team_id=team_id,
            outbox_id=outbox_id
        )

    # =========================================================================
    # EVENT 5: TEAM INVITATION CREATED
    # =========================================================================
    @staticmethod
    async def send_team_invitation_created_webhook(
        invitation_doc: Dict[str, Any],
        is_resend: bool = False,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Event 5: Team Invitation Created.
        Triggered only after a real invitation has been created and saved in MongoDB.
        Payload strictly adheres to:
        {
          "event": "team_invitation_created",
          "event_id": "unique_event_id",
          "invitation_id": "actual_invitation_id",
          "team_id": "actual_team_id",
          "team_name": "actual_team_name",
          "invited_email": "actual_invited_email",
          "invited_by": "actual_inviter_name",
          "assigned_role": "actual_role",
          "invitation_url": "actual_invitation_url",
          "expires_at": "actual_expiry_timestamp"
        }
        """
        logs_col = get_col("automation_logs")
        invitation_id = str(invitation_doc.get("invitation_id") or "")
        team_id = str(invitation_doc.get("team_id") or "")
        invited_email = str(invitation_doc.get("invited_email") or invitation_doc.get("email") or "").strip().lower()

        corr_id = correlation_id or invitation_doc.get("correlation_id") or f"INV-CORR-{uuid.uuid4().hex[:8].upper()}"
        corr_prefix = f"[{corr_id}] "

        # 1. Validation
        if not invitation_id or not invited_email:
            logger.warning(f"{corr_prefix}Invitation document missing required fields: invitation_id={invitation_id}, invited_email={invited_email}")
            return {
                "delivery_status": "skipped",
                "reason": "invalid_invitation_document",
                "correlation_id": corr_id,
                "message": "Invitation document must include invitation_id and invited_email."
            }

        # Check database record status if present in team_invitations collection:
        inv_col = get_col("team_invitations")
        inv_in_db = inv_col.find_one({"invitation_id": invitation_id})
        if inv_in_db:
            inv_status = str(inv_in_db.get("invitation_status") or inv_in_db.get("status") or "").lower()
            if inv_status in ["accepted", "revoked", "cancelled", "expired"]:
                logger.info(f"{corr_prefix}Invitation {invitation_id} is in status '{inv_status}'. Skipping webhook dispatch.")
                return {
                    "delivery_status": "skipped",
                    "reason": "invitation_not_pending",
                    "status": inv_status,
                    "correlation_id": corr_id,
                    "message": f"Invitation {invitation_id} is already {inv_status}."
                }

        # 2. Idempotency Check (only active for new invitations, bypassed on explicit resend)
        if not is_resend:
            existing_success = logs_col.find_one({
                "reference_id": invitation_id,
                "event_type": "team_invitation_created",
                "$or": [{"delivery_status": "success"}, {"status": "success"}, {"dispatch_status": "webhook_accepted"}]
            })
            if not existing_success:
                outbox_col = get_col("automation_outbox")
                existing_success = outbox_col.find_one({
                    "reference_id": invitation_id,
                    "event_type": "team_invitation_created",
                    "status": "webhook_accepted"
                })
            if not existing_success:
                pe_col = get_col("processed_events")
                existing_success = pe_col.find_one({
                    "reference_id": invitation_id,
                    "event_type": "team_invitation_created"
                })
            if existing_success:
                logger.info(f"{corr_prefix}Invitation {invitation_id} webhook already dispatched (event_id={existing_success.get('event_id')}). Skipping duplicate.")
                return {
                    "delivery_status": "skipped",
                    "reason": "already_delivered",
                    "correlation_id": corr_id,
                    "event_id": existing_success.get("event_id"),
                    "log_id": str(existing_success.get("_id", ""))
                }

        # 3. Format payload
        prefix = "EVT-INV-RESEND" if is_resend else "EVT-INV-NEW"
        event_id = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        exp = invitation_doc.get("expires_at")
        if isinstance(exp, datetime):
            expires_at_str = exp.isoformat() + "Z"
        else:
            expires_at_str = str(exp or "")

        team_name = invitation_doc.get("team_name") or "MeetMind Workspace"
        invited_by = invitation_doc.get("invited_by") or "Team Leader"
        assigned_role = invitation_doc.get("assigned_role") or invitation_doc.get("role") or "Editor"
        invitation_url = invitation_doc.get("invitation_url") or f"{settings.FRONTEND_URL}/accept-invitation?token={invitation_doc.get('raw_token', '')}"

        # Dynamic, distinct subject line avoids Gmail conversation thread grouping
        email_subject = f"You're invited to join {team_name} on MeetMind AI (Ref: {invitation_id})"

        payload = {
            "event": "team_invitation_created",
            "event_id": event_id,
            "correlation_id": corr_id,
            "is_resend": is_resend,
            "invitation_id": invitation_id,
            "team_id": team_id,
            "team_name": team_name,
            "invited_email": invited_email,
            "invited_by": invited_by,
            "assigned_role": assigned_role,
            "invitation_url": invitation_url,
            "expires_at": expires_at_str,
            # Universal aliases for Zapier field mappings
            "recipient_email": invited_email,
            "to_email": invited_email,
            "to": invited_email,
            "email": invited_email,
            "assigned_email": invited_email,
            "email_subject": email_subject,
            "subject": email_subject,
            "email_body": (
                f"Hello,\n\n"
                f"{invited_by} has invited you to join the team '{team_name}' on MeetMind AI as a {assigned_role}.\n\n"
                f"To accept this invitation, please visit the link below:\n"
                f"{invitation_url}\n\n"
                f"Expires on: {expires_at_str}\n\n"
                f"Best regards,\nMeetMind AI Team"
            )
        }

        # 4. Outbox persistence
        webhook_url = settings.team_invitation_created_webhook_url
        url_configured = bool(webhook_url and webhook_url.strip())
        logger.info(
            f"{corr_prefix}Initiating invitation webhook dispatch: "
            f"event_id={event_id}, invitation_id={invitation_id}, team_id={team_id}, "
            f"intended_recipient={invited_email}, webhook_configured={url_configured}"
        )

        if not url_configured:
            logger.error(f"{corr_prefix}ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL is not configured.")
            now = datetime.utcnow()
            log_doc = {
                "event_id": event_id,
                "correlation_id": corr_id,
                "event_type": "team_invitation_created",
                "reference_id": invitation_id,
                "webhook_type": "team_invitation_created",
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "gmail_status": "delivery_unconfirmed",
                "attempt_count": 0,
                "error_message": "ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL is not configured in backend environment",
                "team_id": team_id,
                "masked_url": "NOT_CONFIGURED",
                "payload": payload,
                "created_at": now,
                "updated_at": now
            }
            res = logs_col.insert_one(log_doc)
            return {
                "delivery_status": "failed",
                "error_message": log_doc["error_message"],
                "event_id": event_id,
                "correlation_id": corr_id,
                "log_id": str(res.inserted_id)
            }

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="team_invitation_created",
            reference_id=invitation_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id,
            correlation_id=corr_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="team_invitation_created",
            reference_id=invitation_id,
            webhook_type="team_invitation_created",
            team_id=team_id,
            outbox_id=outbox_id,
            correlation_id=corr_id
        )

    # =========================================================================
    # EVENT: MEETING SCHEDULED
    # =========================================================================
    @staticmethod
    async def send_meeting_scheduled_webhook(meeting_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends invitations for a saved meeting using active workspace member records.
        """
        meeting_id = str(meeting_doc.get("meeting_id") or "")
        team_id = str(meeting_doc.get("team_id") or "")
        event_id = str(meeting_doc.get("invitation_event_id") or "")
        host_id = str(meeting_doc.get("host_id") or "")
        host_email = str(meeting_doc.get("host_email") or "").strip().lower()
        host_name = str(meeting_doc.get("host_name") or "").strip()
        timezone_name = str(meeting_doc.get("timezone") or "Asia/Kolkata")
        meeting_link = (
            f"{settings.FRONTEND_URL.rstrip('/')}/live-meeting"
            f"?room={quote(str(meeting_doc.get('room_id') or meeting_id), safe='')}"
            f"&meeting_id={quote(meeting_id, safe='')}"
            f"&title={quote(str(meeting_doc.get('meeting_title') or ''), safe='')}"
            "&join=true"
        )

        existing_outbox = get_col("automation_outbox").find_one({"event_id": event_id}) if event_id else None
        existing_log = get_col("automation_logs").find_one({"event_id": event_id}) if event_id else None
        if existing_outbox or existing_log:
            prior = existing_log or existing_outbox
            return {
                "event_id": event_id,
                "delivery_status": prior.get("delivery_status") or prior.get("status") or "pending",
                "dispatch_status": prior.get("dispatch_status") or prior.get("status") or "pending",
                "error_message": prior.get("error_message") or prior.get("last_error")
            }

        def failed_result(reason: str) -> Dict[str, Any]:
            message = reason
            existing = get_col("automation_logs").find_one({"event_id": event_id})
            if not existing:
                get_col("automation_logs").insert_one({
                    "event_id": event_id,
                    "event_type": "meeting_scheduled",
                    "reference_id": meeting_id,
                    "meeting_id": meeting_id,
                    "webhook_type": "meeting_scheduled",
                    "delivery_status": "failed",
                    "dispatch_status": "failed",
                    "status": "failed",
                    "attempt_count": 0,
                    "error_message": message,
                    "team_id": team_id,
                    "masked_url": mask_webhook_url(settings.meeting_invitation_webhook_url),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                })
            return {
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "event_id": event_id,
                "error_message": message
            }

        if not meeting_id or not team_id or not event_id or not host_id or not host_name:
            return failed_result("Saved meeting is missing its identity or Team Leader details.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", host_email):
            return failed_result("The saved Team Leader email address is invalid.")

        teams_col = get_col("teams")
        team = teams_col.find_one({"team_id": team_id})
        workspace_name = str((team or {}).get("name") or (team or {}).get("team_name") or "").strip()
        if not workspace_name:
            return failed_result("The workspace name could not be resolved from MongoDB.")

        try:
            timezone_info = ZoneInfo(timezone_name)
            starts_at = datetime.fromisoformat(str(meeting_doc.get("scheduled_start_at")))
            ends_at = datetime.fromisoformat(str(meeting_doc.get("scheduled_end_at")))
            if starts_at.tzinfo is None or ends_at.tzinfo is None:
                raise ValueError("Saved meeting times must include timezone information.")
            local_start = starts_at.astimezone(timezone_info)
            local_end = ends_at.astimezone(timezone_info)
        except (ValueError, TypeError, KeyError) as error:
            return failed_result(f"Saved meeting time is invalid: {error}")

        leader_roles = {
            "admin", "manager", "team lead", "team leader", "team_leader",
            "team lead / admin", "team leader / admin"
        }
        selected_ids = {
            str(member_id)
            for member_id in (meeting_doc.get("selected_participant_ids") or [])
            if member_id
        }
        active_members = get_col("member_profiles").find({
            "team_id": team_id,
            "account_status": "active"
        })
        participants = []
        for member in active_members:
            member_id = str(member.get("member_id") or "")
            member_email = str(member.get("email") or "").strip().lower()
            member_role = str(member.get("role") or "Member").strip()
            if (
                not member_id
                or (selected_ids and member_id not in selected_ids)
                or member_id == host_id
                or (host_email and member_email == host_email)
                or member_role.lower() in leader_roles
                or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", member_email)
            ):
                continue
            participants.append({
                "user_id": member_id,
                "name": str(member.get("name") or ""),
                "email": member_email,
                "role": "team_member"
            })

        if not participants:
            return failed_result("No active workspace Team Members with valid email addresses were selected.")

        payload = {
            "event_type": "meeting_scheduled",
            "event_id": event_id,
            "workspace_id": team_id,
            "workspace_name": workspace_name,
            "meeting_id": meeting_id,
            "meeting_title": str(meeting_doc.get("meeting_title") or ""),
            "meeting_description": str(meeting_doc.get("description") or meeting_doc.get("agenda") or ""),
            "meeting_date": local_start.strftime("%Y-%m-%d"),
            "start_time": local_start.strftime("%H:%M"),
            "end_time": local_end.strftime("%H:%M"),
            "timezone": timezone_name,
            "meeting_link": meeting_link,
            "host_id": host_id,
            "host_name": host_name,
            "host_email": host_email,
            "participants": participants,
            "recipient_email": participants[0]["email"],
            "to_emails": [participant["email"] for participant in participants],
            "meeting_url": meeting_link,
            "secure_meeting_url": meeting_link
        }

        webhook_url = settings.meeting_invitation_webhook_url
        if not webhook_url or not webhook_url.strip():
            return failed_result("No meeting invitation webhook URL is configured.")

        outbox_id = ZapierService._create_outbox_record(
            event_id=event_id,
            event_type="meeting_scheduled",
            reference_id=meeting_id,
            payload=payload,
            webhook_url=webhook_url.strip(),
            team_id=team_id
        )

        return await ZapierService._post_with_retries(
            webhook_url=webhook_url.strip(),
            payload=payload,
            event_id=event_id,
            event_type="meeting_scheduled",
            reference_id=meeting_id,
            webhook_type="meeting_scheduled",
            team_id=team_id,
            outbox_id=outbox_id
        )

    # =========================================================================
    # RETRY LOGIC & BACKGROUND OUTBOX PROCESSOR
    # =========================================================================
    @staticmethod
    async def retry_failed_webhook(event_or_log_id: str) -> Dict[str, Any]:
        """
        Retries a failed webhook delivery by its event_id or log_id.
        Queries MongoDB automation_outbox or automation_logs to find the payload.
        """
        logs_col = get_col("automation_logs")
        outbox_col = get_col("automation_outbox")

        doc = None
        try:
            doc = outbox_col.find_one({"_id": ObjectId(event_or_log_id)})
        except Exception:
            pass

        if not doc:
            doc = outbox_col.find_one({"event_id": event_or_log_id})

        if not doc:
            try:
                doc = logs_col.find_one({"_id": ObjectId(event_or_log_id)})
            except Exception:
                pass

        if not doc:
            doc = logs_col.find_one({"event_id": event_or_log_id})

        if not doc:
            return {"status": "error", "message": f"Event or log record '{event_or_log_id}' not found."}

        event_type = doc.get("event_type") or doc.get("webhook_type")
        payload = doc.get("payload", {})
        reference_id = doc.get("reference_id") or doc.get("task_id") or ""
        team_id = doc.get("team_id")

        url = get_webhook_url_for_event(event_type)
        if not url:
            return {"status": "error", "message": f"No webhook URL configured for event '{event_type}'."}

        retry_event_id = f"RETRY-{uuid.uuid4().hex[:8].upper()}"
        outbox_id = doc.get("_id") if doc.get("webhook_url") else None

        return await ZapierService._post_with_retries(
            webhook_url=url,
            payload=payload,
            event_id=retry_event_id,
            event_type=event_type,
            reference_id=reference_id,
            webhook_type=event_type,
            team_id=team_id,
            outbox_id=outbox_id
        )

    @staticmethod
    async def process_outbox_batch():
        """
        Scans automation_outbox collection for pending or retrying deliveries.
        Executes delivery and updates status in MongoDB.
        STRICT SAFEGUARDS:
        - NEVER automatically re-dispatches team_invitation_created events.
        - NEVER re-dispatches stale events older than OUTBOX_MAX_EVENT_AGE_MINUTES.
        - Enforces idempotency via processed_events and automation_logs.
        - Only runs if ENABLE_STARTUP_OUTBOX_DISPATCH is explicitly enabled.
        """
        if not getattr(settings, "ENABLE_STARTUP_OUTBOX_DISPATCH", False):
            return

        outbox_col = get_col("automation_outbox")
        now = datetime.utcnow()
        max_age_cutoff = now - timedelta(minutes=getattr(settings, "OUTBOX_MAX_EVENT_AGE_MINUTES", 60))

        # Query pending or retrying deliveries EXCEPT team invitations and stale records
        cursor = outbox_col.find({
            "status": {"$in": ["pending", "retrying"]},
            "event_type": {"$ne": "team_invitation_created"},
            "created_at": {"$gte": max_age_cutoff},
            "$or": [
                {"next_retry_at": {"$lte": now}},
                {"next_retry_at": None}
            ]
        }).limit(10)

        for item in cursor:
            event_type = item.get("event_type")
            event_id = item.get("event_id")
            reference_id = item.get("reference_id", "")

            # Strict guard: Team invitation emails are NEVER auto-dispatched by background workers
            if event_type == "team_invitation_created":
                outbox_col.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"status": "stale_skipped", "last_error": "Team invitations require explicit user trigger", "updated_at": now}}
                )
                continue

            # Idempotency check: has this event already been processed successfully?
            if ZapierService._is_event_already_processed(event_id, event_type, reference_id):
                outbox_col.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"status": "webhook_accepted", "last_error": None, "updated_at": now}}
                )
                continue

            try:
                url = item.get("webhook_url") or get_webhook_url_for_event(event_type)
                if not url:
                    outbox_col.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"status": "failed", "last_error": "Webhook URL not configured", "updated_at": datetime.utcnow()}}
                    )
                    continue

                await ZapierService._post_with_retries(
                    webhook_url=url,
                    payload=item.get("payload", {}),
                    event_id=event_id,
                    event_type=event_type,
                    reference_id=reference_id,
                    webhook_type=event_type,
                    team_id=item.get("team_id"),
                    outbox_id=item["_id"]
                )
            except Exception as e:
                logger.error(f"Error processing outbox record {event_id}: {e}")


async def run_persistent_automation_outbox():
    """
    Background worker loop that runs if explicitly enabled.
    Waits for initial startup delay to guarantee a completely clean server boot.
    Periodically processes pending and retrying events from MongoDB outbox.
    """
    logger.info("Automation outbox background runner initialized.")
    initial_delay = getattr(settings, "OUTBOX_INITIAL_STARTUP_DELAY_SECONDS", 60.0)
    try:
        await asyncio.sleep(initial_delay)
    except asyncio.CancelledError:
        logger.info("Persistent automation outbox background runner stopped during startup delay.")
        return

    logger.info("Starting persistent automation outbox background processing loop...")
    while True:
        try:
            await ZapierService.process_outbox_batch()
        except asyncio.CancelledError:
            logger.info("Persistent automation outbox background runner stopped.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in automation outbox loop: {e}")
        await asyncio.sleep(OUTBOX_POLL_INTERVAL_SECONDS)


# Background fire-and-forget helper
def dispatch_webhook_in_background(coro):
    """Schedules an async webhook coroutine in the active event loop if available."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.error(f"Failed to execute background webhook coroutine: {e}")
