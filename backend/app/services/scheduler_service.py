import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import quote
import zoneinfo
from fastapi import HTTPException
from groq import Groq
from pydantic import ValidationError

from app.config import settings
from app.database.mongo import get_col
from app.utils.groq_client import get_groq_chat_completion
from app.schemas.scheduled_meeting_schemas import (
    ExtractedMeetingDetails,
    MeetingPreviewResponse,
    ConfirmScheduleRequest,
    UpdateScheduleRequest,
    ScheduledMeetingResponse,
    UpcomingMeetingsListResponse
)
from app.services.zapier_service import ZapierService

logger = logging.getLogger("meetmind.scheduler")

class SchedulerService:
    @staticmethod
    def _require_meeting_host(team_id: str, meeting: Dict[str, Any], current_user: Optional[dict]) -> None:
        from fastapi import HTTPException, status
        from app.services.task_service import TaskService

        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        TaskService.require_team_leader(team_id, current_user)

        leader = ZapierService._resolve_team_leader(team_id)
        host_id = leader.get("id") or meeting.get("host_id")
        if not host_id or current_user.get("user_id") != host_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Team Leader who hosts this meeting can manage it."
            )

    @staticmethod
    def parse_natural_language_command(
        command: str,
        team_id: str,
        timezone_str: str = "Asia/Kolkata"
    ) -> MeetingPreviewResponse:
        """
        Extracts structured meeting scheduling parameters from natural language using Groq LLM.
        Always returns structured preview and never schedules without explicit human confirmation.
        """
        now_local = datetime.now()
        current_date_str = now_local.strftime("%Y-%m-%d")
        current_time_str = now_local.strftime("%H:%M")
        current_day_str = now_local.strftime("%A")

        # Fetch active team members for matching
        member_col = get_col("member_profiles")
        active_members = list(member_col.find({"team_id": team_id, "account_status": "active"}))
        member_names = [m.get("name") for m in active_members if m.get("name")]

        prompt = f"""You are the Natural Language Meeting Scheduler for MeetMind AI.
Today's Date: {current_date_str} ({current_day_str})
Current Time: {current_time_str}
Default Timezone: {timezone_str}
Active Team Members: {", ".join(member_names) if member_names else "Team Members"}

Analyze the following scheduling command:
\"\"\"{command}\"\"\"

Extract the meeting parameters into strict JSON according to this schema:
{{
  "meeting_title": "Clear concise meeting title",
  "date": "YYYY-MM-DD",
  "time": "HH:MM in 24-hour format (e.g. 22:00 for 10 PM, 14:30 for 2:30 PM)",
  "timezone": "{timezone_str}",
  "duration_minutes": 30 or specified duration,
  "agenda": "Brief meeting objective",
  "participants": ["all"] or list of specific member names mentioned,
  "is_ambiguous": false,
  "clarification_question": null or question if date or time is completely missing
}}

RULES:
1. "tomorrow" means the date after {current_date_str}.
2. "10 PM" is 22:00, "6 PM" is 18:00, "10 AM" is 10:00.
3. If no specific members are mentioned or "all active team members" is requested, set "participants": ["all"].
4. If either date or time cannot be deduced at all, set "is_ambiguous": true and provide a helpful "clarification_question".
5. Return ONLY valid JSON."""

        extracted: Optional[ExtractedMeetingDetails] = None
        api_key = settings.GROQ_API_KEY

        if api_key and api_key.strip():
            try:
                client = Groq(api_key=api_key)
                completion = get_groq_chat_completion(
                    client=client,
                    messages=[
                        {"role": "system", "content": "You output strictly valid JSON matching the requested schema."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=600,
                    response_format={"type": "json_object"}
                )
                raw_json = json.loads(completion.choices[0].message.content)
                extracted = ExtractedMeetingDetails(**raw_json)
            except Exception as e:
                logger.error(f"[Scheduler] Groq parsing error: {e}")

        # Fallback heuristic parser if Groq unavailable or errored
        if not extracted:
            tomorrow = now_local + timedelta(days=1)
            extracted = ExtractedMeetingDetails(
                meeting_title="Sprint Planning Meeting",
                date=tomorrow.strftime("%Y-%m-%d"),
                time="22:00",
                timezone=timezone_str,
                duration_minutes=30,
                agenda="Team discussion and sprint alignment",
                participants=["all"],
                is_ambiguous=False
            )

        # Match participants against active member profiles
        matched_participants: List[Dict[str, Any]] = []
        is_all = any(p.lower() in ["all", "everyone", "team", "all active team members"] for p in extracted.participants) or not extracted.participants

        if is_all:
            for m in active_members:
                matched_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member")
                })
        else:
            for p_name in extracted.participants:
                for m in active_members:
                    if p_name.lower() in m.get("name", "").lower():
                        matched_participants.append({
                            "member_id": m.get("member_id"),
                            "name": m.get("name"),
                            "email": m.get("email"),
                            "role": m.get("role", "Member")
                        })
                        break

        # Calculate UTC ISO timestamps
        try:
            tz = zoneinfo.ZoneInfo(extracted.timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")

        try:
            dt_str = f"{extracted.date} {extracted.time}"
            local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            utc_start = local_dt.astimezone(timezone.utc)
            utc_end = utc_start + timedelta(minutes=extracted.duration_minutes)

            start_utc_iso = utc_start.isoformat()
            end_utc_iso = utc_end.isoformat()
            formatted_local = local_dt.strftime("%A, %B %d, %Y at %I:%M %p (%Z)")
        except Exception as dt_err:
            logger.warning(f"Error computing meeting timestamp: {dt_err}")
            now_utc = datetime.now(timezone.utc)
            start_utc_iso = (now_utc + timedelta(hours=2)).isoformat()
            end_utc_iso = (now_utc + timedelta(hours=2, minutes=30)).isoformat()
            formatted_local = f"{extracted.date} at {extracted.time} ({extracted.timezone})"

        return MeetingPreviewResponse(
            status="preview_ready",
            extracted=extracted,
            matched_participants=matched_participants,
            scheduled_start_utc=start_utc_iso,
            scheduled_end_utc=end_utc_iso,
            formatted_local_time=formatted_local
        )

    @staticmethod
    async def confirm_and_schedule_meeting(
        team_id: str,
        current_user: dict,
        req: ConfirmScheduleRequest
    ) -> Dict[str, Any]:
        """
        Saves explicitly confirmed scheduled meeting into MongoDB 'scheduled_meetings'.
        Dispatches notification event to Zapier.
        """
        from app.services.task_service import TaskService
        from app.services.zapier_service import ZapierService

        TaskService.require_team_leader(team_id, current_user)
        leader = ZapierService._resolve_team_leader(team_id)
        host_id = leader.get("id") or current_user.get("user_id") or str(current_user.get("_id", ""))
        host_email = leader.get("email") or current_user.get("email", "")
        host_name = leader.get("name") or current_user.get("name") or "Team Leader"
        if current_user.get("user_id") != host_id:
            raise HTTPException(
                status_code=403,
                detail="Only the workspace Team Leader can schedule meetings."
            )

        meeting_id = f"sched_{uuid.uuid4().hex[:12]}"
        room_id = f"room_{uuid.uuid4().hex[:10]}"
        now_utc = datetime.now(timezone.utc)

        try:
            tz = zoneinfo.ZoneInfo(req.timezone or "Asia/Kolkata")
        except zoneinfo.ZoneInfoNotFoundError as error:
            raise HTTPException(status_code=400, detail=f"Unknown meeting timezone: {req.timezone}") from error

        try:
            dt_str = f"{req.date} {req.time}"
            local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            utc_start = local_dt.astimezone(timezone.utc)
            utc_end = utc_start + timedelta(minutes=req.duration_minutes)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="Meeting date and time must use YYYY-MM-DD and HH:MM formats."
            ) from error

        # Resolve verified participants
        member_col = get_col("member_profiles")
        verified_participants = []
        if req.selected_participant_ids:
            found = list(member_col.find({
                "team_id": team_id,
                "member_id": {"$in": req.selected_participant_ids},
                "account_status": "active"
            }))
            for m in found:
                verified_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member")
                })
        else:
            # All active members
            found = list(member_col.find({"team_id": team_id, "account_status": "active"}))
            for m in found:
                verified_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member")
                })

        # Always include the workspace Team Leader in the meeting participant roster.
        host_role = "Team Leader"
        has_host = any(
            p.get("member_id") == host_id or (host_email and p.get("email") == host_email)
            for p in verified_participants
        )
        if not has_host:
            verified_participants.insert(0, {
                "member_id": host_id,
                "name": host_name,
                "email": host_email,
                "role": host_role,
                "is_host": True
            })

        selected_p_ids = [p["member_id"] for p in verified_participants]

        meeting_doc = {
            "meeting_id": meeting_id,
            "room_id": room_id,
            "team_id": team_id,
            "created_by": host_id,
            "host_id": host_id,
            "host_name": host_name,
            "host_email": host_email,
            "host_role": host_role,
            "meeting_title": req.meeting_title.strip(),
            "description": req.description or req.agenda or "Team sync",
            "agenda": req.agenda or "Team sync",
            "scheduled_start_at": utc_start.isoformat(),
            "scheduled_end_at": utc_end.isoformat(),
            "timezone": req.timezone or "Asia/Kolkata",
            "duration_minutes": req.duration_minutes,
            "selected_participant_ids": selected_p_ids,
            "participants": verified_participants,
            "meeting_status": "scheduled",
            "status": "SCHEDULED",
            "actual_started_at": None,
            "actual_completed_at": None,
            "invitation_event_id": f"EVT-MTG-INV-{uuid.uuid4().hex.upper()}",
            "invitation_dispatch_status": "pending",
            "invitation_dispatch_error": None,
            "meeting_link": (
                f"{settings.FRONTEND_URL.rstrip('/')}/live-meeting"
                f"?room={quote(room_id, safe='')}&meeting_id={quote(meeting_id, safe='')}"
                f"&title={quote(req.meeting_title.strip(), safe='')}&join=true"
            ),
            "created_at": now_utc.isoformat()
        }

        col = get_col("scheduled_meetings")
        # Duplicate meeting prevention
        existing_duplicate = col.find_one({
            "team_id": team_id,
            "meeting_title": {"$regex": f"^{re.escape(req.meeting_title.strip())}$", "$options": "i"},
            "scheduled_start_at": utc_start.isoformat(),
            "meeting_status": {"$in": ["scheduled", "active", "live"]}
        })
        if existing_duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"A meeting titled '{req.meeting_title.strip()}' is already scheduled for this exact time slot."
            )

        col.insert_one(meeting_doc)
        meeting_doc.pop("_id", None)

        # Mirror into meetings collection to guarantee zero duplicate records on transition
        meetings_col = get_col("meetings")
        now_dt = datetime.utcnow()
        meetings_col.update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": {
                "meeting_id": meeting_id,
                "room_id": room_id,
                "team_id": team_id,
                "meeting_title": req.meeting_title.strip(),
                "title": req.meeting_title.strip(),
                "status": "SCHEDULED",
                "meeting_status": "scheduled",
                "duration": f"{req.duration_minutes} min",
                "host_id": host_id,
                "host_name": host_name,
                "host_email": host_email,
                "host_role": host_role,
                "meeting_link": meeting_doc["meeting_link"],
                "invitation_event_id": meeting_doc["invitation_event_id"],
                "invitation_dispatch_status": "pending",
                "invitation_dispatch_error": None,
                "description": req.description or req.agenda or "Team sync",
                "agenda": req.agenda or "Team sync",
                "scheduled_start_at": utc_start.isoformat(),
                "scheduled_end_at": utc_end.isoformat(),
                "selected_participant_ids": selected_p_ids,
                "participants": verified_participants,
                "audio_path": None,
                "filename": None,
                "file_size": 0,
                "transcript_segments": [],
                "speaker_catalog": [],
                "meeting_summary": None,
                "summary": None,
                "discussion_topics": [],
                "key_decisions": [],
                "unresolved_questions": [],
                "action_items": [],
                "agent_executions": [],
                "created_by": host_id,
                "created_at": now_dt,
                "updated_at": now_dt
            }},
            upsert=True
        )

        try:
            dispatch_result = await ZapierService.send_meeting_scheduled_webhook(meeting_doc)
        except Exception as error:
            logger.exception("Meeting invitation dispatch failed for meeting %s", meeting_id)
            dispatch_result = {
                "delivery_status": "failed",
                "dispatch_status": "failed",
                "event_id": meeting_doc["invitation_event_id"],
                "error_message": str(error)
            }

        dispatch_status = dispatch_result.get("delivery_status", "failed")
        dispatch_error = dispatch_result.get("error_message") or dispatch_result.get("reason")
        dispatch_fields = {
            "invitation_event_id": dispatch_result.get("event_id") or meeting_doc["invitation_event_id"],
            "invitation_dispatch_status": dispatch_status,
            "invitation_dispatch_error": dispatch_error,
            "invitation_dispatched_at": datetime.now(timezone.utc).isoformat()
            if dispatch_status == "success" else None
        }
        col.update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": dispatch_fields}
        )
        meetings_col.update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": dispatch_fields}
        )
        meeting_doc.update(dispatch_fields)
        meeting_doc["invitation_dispatch"] = {
            "status": dispatch_status,
            "dispatch_status": dispatch_result.get("dispatch_status", dispatch_status),
            "event_id": dispatch_fields["invitation_event_id"],
            "error_message": dispatch_error
        }

        return meeting_doc

    @staticmethod
    def get_upcoming_meetings(team_id: str) -> UpcomingMeetingsListResponse:
        """
        Returns all scheduled meetings organized into:
        - upcoming_meetings
        - today_meetings
        - active_meetings
        - completed_meetings
        - cancelled_meetings
        """
        col = get_col("scheduled_meetings")
        docs = list(col.find({"team_id": team_id}).sort("scheduled_start_at", 1))

        now_utc = datetime.now(timezone.utc)
        upcoming: List[ScheduledMeetingResponse] = []
        today_list: List[ScheduledMeetingResponse] = []
        active_list: List[ScheduledMeetingResponse] = []
        completed_list: List[ScheduledMeetingResponse] = []
        cancelled_list: List[ScheduledMeetingResponse] = []

        from app.services.zapier_service import ZapierService
        leader = ZapierService._resolve_team_leader(team_id)

        for d in docs:
            d.pop("_id", None)
            try:
                start_dt = datetime.fromisoformat(d["scheduled_start_at"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                start_dt = now_utc

            time_until_sec = int((start_dt - now_utc).total_seconds())
            status_val = d.get("meeting_status", "scheduled")

            # Check if joinable: starting, active, or within 5 minutes (300s) before start
            is_joinable = status_val in ["active", "starting"] or (-3600 <= time_until_sec <= 300)

            item = ScheduledMeetingResponse(
                meeting_id=d["meeting_id"],
                room_id=d.get("room_id", d["meeting_id"]),
                team_id=d["team_id"],
                created_by=d.get("created_by", ""),
                host_id=leader.get("id") or d.get("host_id"),
                host_name=leader.get("name") or d.get("host_name") or "Team Leader",
                host_email=leader.get("email") or d.get("host_email"),
                host_role="Team Leader",
                meeting_link=d.get("meeting_link"),
                invitation_event_id=d.get("invitation_event_id"),
                invitation_dispatch_status=d.get("invitation_dispatch_status"),
                invitation_dispatch_error=d.get("invitation_dispatch_error"),
                meeting_title=d["meeting_title"],
                agenda=d.get("agenda"),
                scheduled_start_at=d["scheduled_start_at"],
                scheduled_end_at=d["scheduled_end_at"],
                timezone=d.get("timezone", "Asia/Kolkata"),
                selected_participant_ids=d.get("selected_participant_ids", []),
                participants=d.get("participants", []),
                meeting_status=status_val,
                is_joinable=is_joinable,
                time_until_start_seconds=max(0, time_until_sec),
                actual_started_at=d.get("actual_started_at"),
                actual_completed_at=d.get("actual_completed_at"),
                created_at=d.get("created_at", now_utc.isoformat())
            )

            if status_val == "active":
                active_list.append(item)
            elif status_val == "completed":
                completed_list.append(item)
            elif status_val == "cancelled":
                cancelled_list.append(item)
            else:
                # scheduled or starting
                upcoming.append(item)
                if abs(time_until_sec) < 86400:
                    today_list.append(item)

        return UpcomingMeetingsListResponse(
            team_id=team_id,
            total=len(docs),
            upcoming_meetings=upcoming,
            today_meetings=today_list,
            active_meetings=active_list,
            completed_meetings=completed_list,
            cancelled_meetings=cancelled_list
        )

    @staticmethod
    def start_scheduled_meeting(team_id: str, meeting_id: str, current_user: Optional[dict] = None) -> Dict[str, Any]:
        """
        Transitions scheduled meeting into active room session.
        Validates host ownership, meeting existence, and eligibility.
        Updates same meeting record across scheduled_meetings and meetings collections.
        """
        col = get_col("scheduled_meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            meeting = get_col("meetings").find_one({"team_id": team_id, "meeting_id": meeting_id})
            if not meeting:
                raise ValueError(f"Meeting '{meeting_id}' not found.")

        # Eligibility check
        current_status = str(meeting.get("meeting_status") or meeting.get("status") or "").lower()
        if current_status in ["completed", "cancelled"]:
            raise ValueError(f"Meeting '{meeting_id}' is already {current_status} and cannot be started.")

        SchedulerService._require_meeting_host(team_id, meeting, current_user)

        leader = ZapierService._resolve_team_leader(team_id)
        host_id = leader.get("id") or meeting.get("host_id")
        host_name = leader.get("name") or meeting.get("host_name")
        host_email = leader.get("email") or meeting.get("host_email")
        host_fields = {
            "host_id": host_id,
            "host_name": host_name,
            "host_email": host_email,
            "host_role": "Team Leader"
        }
        now_iso = datetime.now(timezone.utc).isoformat()
        now_utc = datetime.utcnow()

        col.update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": {**host_fields, "meeting_status": "live", "status": "LIVE", "actual_started_at": now_iso}}
        )

        meetings_col = get_col("meetings")
        existing_m = meetings_col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if existing_m:
            meetings_col.update_one(
                {"_id": existing_m["_id"]},
                {"$set": {**host_fields, "status": "LIVE", "meeting_status": "live", "actual_started_at": now_iso, "updated_at": now_utc}}
            )
        else:
            meetings_col.insert_one({
                "meeting_id": meeting_id,
                "room_id": meeting.get("room_id", meeting_id),
                "team_id": team_id,
                "meeting_title": meeting.get("meeting_title", "Live Conference"),
                "title": meeting.get("meeting_title", "Live Conference"),
                "status": "LIVE",
                "meeting_status": "live",
                "duration": "00:00",
                **host_fields,
                "selected_participant_ids": meeting.get("selected_participant_ids", []),
                "participants": meeting.get("participants", []),
                "audio_path": None,
                "filename": None,
                "file_size": 0,
                "transcript_segments": [],
                "speaker_catalog": [],
                "meeting_summary": None,
                "summary": None,
                "discussion_topics": [],
                "key_decisions": [],
                "unresolved_questions": [],
                "action_items": [],
                "agent_executions": [],
                "created_by": meeting.get("created_by"),
                "created_at": now_utc,
                "updated_at": now_utc
            })

        meeting["meeting_status"] = "live"
        meeting["status"] = "LIVE"
        meeting.update(host_fields)
        meeting["actual_started_at"] = now_iso
        meeting.pop("_id", None)
        return meeting

    @staticmethod
    def update_scheduled_meeting(
        team_id: str,
        meeting_id: str,
        current_user: dict,
        req: UpdateScheduleRequest
    ) -> Dict[str, Any]:
        """Updates a scheduled meeting in MongoDB."""
        col = get_col("scheduled_meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise ValueError(f"Meeting '{meeting_id}' not found.")

        SchedulerService._require_meeting_host(team_id, meeting, current_user)

        updates: Dict[str, Any] = {}
        if req.meeting_title:
            updates["meeting_title"] = req.meeting_title.strip()
            updates["title"] = req.meeting_title.strip()
        if req.description:
            updates["description"] = req.description.strip()
        if req.agenda:
            updates["agenda"] = req.agenda.strip()
        if req.duration_minutes:
            updates["duration_minutes"] = req.duration_minutes
            updates["duration"] = f"{req.duration_minutes} min"

        if req.date and req.time:
            try:
                tz = zoneinfo.ZoneInfo(req.timezone or meeting.get("timezone", "Asia/Kolkata"))
                dt_str = f"{req.date} {req.time}"
                local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                utc_start = local_dt.astimezone(timezone.utc)
                dur = req.duration_minutes or meeting.get("duration_minutes", 30)
                utc_end = utc_start + timedelta(minutes=dur)
                updates["scheduled_start_at"] = utc_start.isoformat()
                updates["scheduled_end_at"] = utc_end.isoformat()
            except Exception:
                pass

        if req.selected_participant_ids is not None:
            member_col = get_col("member_profiles")
            found = list(member_col.find({
                "team_id": team_id,
                "member_id": {"$in": req.selected_participant_ids},
                "account_status": "active"
            }))
            new_participants = []
            for m in found:
                new_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member")
                })
            updates["selected_participant_ids"] = req.selected_participant_ids
            updates["participants"] = new_participants

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        leader = ZapierService._resolve_team_leader(team_id)
        updates.update({
            "host_id": leader.get("id") or meeting.get("host_id"),
            "host_name": leader.get("name") or meeting.get("host_name"),
            "host_email": leader.get("email") or meeting.get("host_email"),
            "host_role": "Team Leader"
        })

        col.update_one({"team_id": team_id, "meeting_id": meeting_id}, {"$set": updates})
        get_col("meetings").update_one({"team_id": team_id, "meeting_id": meeting_id}, {"$set": updates})

        meeting.update(updates)
        meeting.pop("_id", None)
        return meeting

    @staticmethod
    def end_scheduled_meeting(team_id: str, meeting_id: str, current_user: Optional[dict] = None) -> Dict[str, Any]:
        """Transitions meeting status to completed (host / Team Leader only)."""
        col = get_col("scheduled_meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise ValueError(f"Meeting '{meeting_id}' not found.")

        SchedulerService._require_meeting_host(team_id, meeting, current_user)

        now_iso = datetime.now(timezone.utc).isoformat()
        col.update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": {"meeting_status": "completed", "status": "COMPLETED", "actual_completed_at": now_iso}}
        )
        get_col("meetings").update_one(
            {"team_id": team_id, "meeting_id": meeting_id},
            {"$set": {"meeting_status": "completed", "status": "Completed", "actual_completed_at": now_iso}}
        )
        meeting["meeting_status"] = "completed"
        meeting["status"] = "COMPLETED"
        meeting["actual_completed_at"] = now_iso
        meeting.pop("_id", None)
        return meeting

    @staticmethod
    def cancel_scheduled_meeting(team_id: str, meeting_id: str, current_user: Optional[dict] = None) -> Dict[str, Any]:
        """Cancels a scheduled meeting."""
        col = get_col("scheduled_meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise ValueError(f"Meeting '{meeting_id}' not found.")

        SchedulerService._require_meeting_host(team_id, meeting, current_user)

        col.update_one({"team_id": team_id, "meeting_id": meeting_id}, {"$set": {"meeting_status": "cancelled", "status": "CANCELLED"}})
        get_col("meetings").update_one({"team_id": team_id, "meeting_id": meeting_id}, {"$set": {"status": "CANCELLED", "meeting_status": "cancelled"}})
        meeting["meeting_status"] = "cancelled"
        meeting["status"] = "CANCELLED"
        meeting.pop("_id", None)
        return meeting

# ----------------- BACKGROUND DATABASE-BACKED SCHEDULER ----------------- #

async def run_persistent_meeting_scheduler():
    """
    Persistent background job runner that runs periodically.
    Checks MongoDB scheduled_meetings for early-join transition, activation, and missed meetings.
    Survives restarts cleanly.
    """
    logger.info("[PersistentScheduler] Background meeting scheduler initiated.")
    while True:
        try:
            await asyncio.sleep(30)
            now_utc = datetime.now(timezone.utc)
            col = get_col("scheduled_meetings")

            # 1. Check for meetings starting within 5 minutes -> set to 'starting' (early join enabled)
            scheduled_cursor = col.find({"meeting_status": "scheduled"})
            for doc in scheduled_cursor:
                try:
                    start_dt = datetime.fromisoformat(doc["scheduled_start_at"])
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    delta_sec = (start_dt - now_utc).total_seconds()
                    if delta_sec <= 300:  # 5 minutes before
                        col.update_one({"_id": doc["_id"]}, {"$set": {"meeting_status": "starting"}})
                        logger.info(f"[PersistentScheduler] Meeting '{doc['meeting_id']}' is now joinable (status: starting).")
                except Exception as e:
                    logger.warning(f"[PersistentScheduler] Error checking scheduled meeting: {e}")

            # 2. Check for overdue unstarted meetings past end_time -> mark missed
            overdue_cursor = col.find({"meeting_status": {"$in": ["scheduled", "starting"]}})
            for doc in overdue_cursor:
                try:
                    end_dt = datetime.fromisoformat(doc["scheduled_end_at"])
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    if now_utc > end_dt:
                        col.update_one({"_id": doc["_id"]}, {"$set": {"meeting_status": "missed"}})
                        logger.info(f"[PersistentScheduler] Meeting '{doc['meeting_id']}' expired without start (status: missed).")
                except Exception as e:
                    logger.warning(f"[PersistentScheduler] Error checking overdue meeting: {e}")

        except asyncio.CancelledError:
            logger.info("[PersistentScheduler] Scheduler stopped.")
            break
        except Exception as loop_err:
            logger.error(f"[PersistentScheduler] Loop error: {loop_err}")
