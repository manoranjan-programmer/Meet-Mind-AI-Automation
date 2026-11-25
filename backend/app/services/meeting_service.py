import os
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from app.database.mongo import get_col
from app.schemas.meeting_schemas import (
    MeetingCompleteRequest, 
    MeetingStartRequest,
    TaskApproveMeetingRequest,
    TaskEditMeetingRequest
)
from app.services.zapier_service import ZapierService, dispatch_webhook_in_background
from app.services.storage_service import StorageService
from app.agents.audio_capture_agent import AudioCaptureAgent
from app.agents.transcription_agent import TranscriptionAgent
from app.utils.pdf_generator import generate_meeting_summary_pdf

class MeetingService:
    @staticmethod
    def authoritative_host_id(team_id: str, meeting: Optional[Dict[str, Any]] = None) -> str:
        """Return the host account ID resolved from trusted workspace records."""
        leader = ZapierService._resolve_team_leader(team_id)
        if leader.get("id"):
            return str(leader["id"])
        if meeting and meeting.get("host_id"):
            return str(meeting["host_id"])
        return ""

    @staticmethod
    def require_meeting_host(team_id: str, meeting_id: str, current_user: dict) -> Dict[str, Any]:
        """Require the authenticated Team Leader recorded as this meeting's host."""
        from app.services.task_service import TaskService
        TaskService.require_team_leader(team_id, current_user)

        meeting = get_col("scheduled_meetings").find_one({
            "team_id": team_id,
            "meeting_id": meeting_id
        })
        if not meeting:
            meeting = get_col("meetings").find_one({
                "team_id": team_id,
                "meeting_id": meeting_id
            })
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        host_id = MeetingService.authoritative_host_id(team_id, meeting)
        if not host_id or current_user.get("user_id") != host_id:
            raise HTTPException(
                status_code=403,
                detail="Only the Team Leader who hosts this meeting can manage it."
            )
        return meeting

    @staticmethod
    def _generate_meeting_id(team_id: str, current_user: dict) -> str:
        from app.services.task_service import TaskService
        TaskService.require_team_leader(team_id, current_user)
        leader = ZapierService._resolve_team_leader(team_id)
        host_id = leader.get("id") or current_user.get("user_id")
        if not host_id or current_user.get("user_id") != host_id:
            raise HTTPException(
                status_code=403,
                detail="Only the workspace Team Leader can create a meeting."
            )

        col = get_col("meetings")
        count = col.count_documents({}) + 1
        m_id = f"MTG-{count:03d}"
        while col.find_one({"meeting_id": m_id}):
            count += 1
            m_id = f"MTG-{count:03d}"
        return m_id

    @staticmethod
    def upload_meeting_audio(
        team_id: str,
        current_user: dict,
        file_bytes: bytes,
        filename: str,
        meeting_title: str,
        participants: Optional[List[str]] = None,
        duration: str = "00:00"
    ) -> Dict[str, Any]:
        """
        Agent 1 Audio Capture:
        Saves audio file into local uploads directory and creates initial meeting record.
        """
        from app.services.task_service import TaskService
        TaskService.require_team_leader(team_id, current_user)
        leader = ZapierService._resolve_team_leader(team_id)
        col = get_col("meetings")
        meeting_id = MeetingService._generate_meeting_id(team_id, current_user)

        # Execute Agent 1
        capture_res = AudioCaptureAgent.execute(
            meeting_id=meeting_id,
            team_id=team_id,
            audio_bytes=file_bytes,
            filename=filename
        )

        now = datetime.utcnow()
        meeting_doc = {
            "meeting_id": meeting_id,
            "team_id": team_id,
            "meeting_title": meeting_title.strip() if meeting_title else "Uploaded Meeting Recording",
            "title": meeting_title.strip() if meeting_title else "Uploaded Meeting Recording",
            "duration": duration,
            "participants": participants or [],
            "audio_path": capture_res["storage_path"],
            "filename": capture_res["filename"],
            "file_size": capture_res["file_size"],
            "status": "Uploaded",
            "meeting_summary": None,
            "summary": None,
            "key_decisions": [],
            "action_items": [],
            "agent_executions": [{
                "agent_id": 1,
                "name": AudioCaptureAgent.NAME,
                "status": "success",
                "duration": capture_res["execution_duration"],
                "timestamp": now.isoformat()
            }],
            "team_lead_email": leader.get("email") or current_user.get("email", ""),
            "created_by": current_user.get("user_id"),
            "host_id": leader.get("id") or current_user.get("user_id"),
            "host_name": leader.get("name") or current_user.get("name"),
            "host_email": leader.get("email") or current_user.get("email"),
            "host_role": "Team Leader",
            "created_at": now,
            "updated_at": now
        }

        res = col.insert_one(meeting_doc)
        meeting_doc["_id"] = str(res.inserted_id)
        meeting_doc["id"] = str(res.inserted_id)

        return meeting_doc

    @staticmethod
    async def process_meeting(
        team_id: str,
        meeting_id: str,
        current_user: dict,
        force_retranscribe: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes LangGraph Multi-Agent Pipeline:
        Transcription -> Diarization -> Analysis -> Task Extraction ->
        Task Assignment -> Validation -> MongoDB Persistence -> Automation Dispatch
        """
        from app.workflows.meeting_graph import run_meeting_workflow

        MeetingService.require_meeting_host(team_id, meeting_id, current_user)
        col = get_col("meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        job_id = f"JOB-{uuid.uuid4().hex[:8]}"
        col.update_one(
            {"_id": meeting["_id"]},
            {"$set": {
                "status": "Processing",
                "processing_job_id": job_id,
                "current_stage": "validating_audio",
                "error_message": None,
                "updated_at": datetime.utcnow(),
            }},
        )

        seg_col = get_col("transcript_segments")
        existing_segs = []
        existing_text = ""
        if not force_retranscribe:
            existing_segs = list(seg_col.find({"team_id": team_id, "meeting_id": meeting_id}).sort("start", 1))
            existing_text = " ".join([s.get("text", "") for s in existing_segs if s.get("text")]).strip()

        audio_path = meeting.get("audio_path", "")
        audio_diag = meeting.get("audio_diagnostics") or {}
        if audio_path and os.path.exists(audio_path) and not audio_diag.get("decodable"):
            audio_diag = StorageService.inspect_audio_file(audio_path, meeting.get("content_type"))

        host_name = meeting.get("host_name") or current_user.get("name") or "Host"

        initial_state = {
            "meeting_id": meeting_id,
            "processing_job_id": job_id,
            "team_id": team_id,
            "meeting_title": meeting.get("meeting_title", "Team Meeting"),
            "audio_path": audio_path,
            "force_retranscribe": force_retranscribe,
            "host_name": host_name,
            "selected_participant_ids": meeting.get("selected_participant_ids", []),
            "participants": meeting.get("participants", []),
            "team_lead_email": current_user.get("email", meeting.get("team_lead_email", "")),
            "duration": meeting.get("duration", "00:00"),
            "status": "Processing",
            "current_stage": "validating_audio",
            "error": None,
            "audio_diagnostics": audio_diag,
            "transcript_text": existing_text,
            "transcript_segments": existing_segs,
            "diarized_segments": [],
            "speaker_catalog": meeting.get("speaker_catalog", []),
            "summary": "",
            "discussion_topics": [],
            "key_decisions": [],
            "unresolved_questions": [],
            "important_outcomes": [],
            "extracted_tasks": [],
            "assigned_tasks": [],
            "validated_tasks": [],
            "agent_executions": meeting.get("agent_executions", []),
            "automation_dispatched": False,
        }

        try:
            await run_meeting_workflow(initial_state)
            updated = col.find_one({"_id": meeting["_id"]})
            updated["id"] = str(updated["_id"])
            updated["_id"] = str(updated["_id"])

            tasks_col = get_col("tasks")
            db_tasks = list(tasks_col.find({"team_id": team_id, "meeting_id": meeting_id}))
            for t in db_tasks:
                t["id"] = str(t["_id"])
                t["_id"] = str(t["_id"])
            updated["extracted_tasks"] = db_tasks

            updated_segs = list(seg_col.find({"team_id": team_id, "meeting_id": meeting_id}).sort("start", 1))
            for s in updated_segs:
                s["id"] = str(s["_id"])
                s["_id"] = str(s["_id"])
            updated["transcript_segments"] = updated_segs

            return updated
        except Exception as e:
            col.update_one({"_id": meeting["_id"]}, {"$set": {"status": "failed", "error_message": str(e)}})
            raise HTTPException(status_code=500, detail=f"Multi-agent processing failed: {str(e)}")

    @staticmethod
    def get_meeting_transcript(team_id: str, meeting_id: str) -> List[Dict[str, Any]]:
        seg_col = get_col("transcript_segments")
        cursor = seg_col.find({"team_id": team_id, "meeting_id": meeting_id}).sort("start", 1)
        segments = []
        for doc in cursor:
            doc["id"] = str(doc["_id"])
            doc["_id"] = str(doc["_id"])
            segments.append(doc)
        return segments

    @staticmethod
    def get_meeting_summary(team_id: str, meeting_id: str) -> Dict[str, Any]:
        meeting = MeetingService.get_meeting(team_id, meeting_id)
        return {
            "meeting_id": meeting["meeting_id"],
            "title": meeting.get("meeting_title", meeting.get("title")),
            "summary": meeting.get("meeting_summary", meeting.get("summary")),
            "discussion_topics": meeting.get("discussion_topics", []),
            "key_decisions": meeting.get("key_decisions", []),
            "unresolved_questions": meeting.get("unresolved_questions", []),
            "action_items": meeting.get("action_items", [])
        }

    @staticmethod
    def export_meeting_pdf(team_id: str, meeting_id: str) -> bytes:
        meeting = MeetingService.get_meeting(team_id, meeting_id)
        return generate_meeting_summary_pdf(meeting)

    @staticmethod
    def complete_meeting(team_id: str, current_user: dict, req: MeetingCompleteRequest) -> Dict[str, Any]:
        """
        Stores meeting analysis and AI summary in MongoDB Atlas `meetings` collection.
        If status is 'failed' or if transcription/analysis failed, stores record without triggering Zapier.
        If successful, triggers `send_meeting_completed_webhook`.
        """
        from app.services.task_service import TaskService
        TaskService.require_team_leader(team_id, current_user)
        col = get_col("meetings")
        leader = ZapierService._resolve_team_leader(team_id)
        host_id = leader.get("id") or current_user.get("user_id")
        host_name = leader.get("name") or current_user.get("name")
        host_email = leader.get("email") or current_user.get("email")

        meeting_id = req.meeting_id or MeetingService._generate_meeting_id(team_id, current_user)
        if req.meeting_id:
            MeetingService.require_meeting_host(team_id, meeting_id, current_user)

        # 1. Handle explicit failure scenario (e.g. Transcription or Analysis failed)
        if req.status == "failed":
            failed_doc = {
                "meeting_id": meeting_id,
                "team_id": team_id,
                "meeting_title": req.meeting_title,
                "title": req.meeting_title,
                "duration": req.duration or "00:00",
                "participants": req.participants or [],
                "meeting_summary": None,
                "summary": None,
                "key_decisions": [],
                "action_items": [],
                "team_lead_email": host_email or "",
                "host_id": host_id,
                "host_name": host_name,
                "host_email": host_email,
                "host_role": "Team Leader",
                "status": "failed",
                "error_message": req.error_message or "Meeting processing failed",
                "created_by": current_user.get("user_id"),
                "created_at": datetime.utcnow()
            }
            existing = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
            if existing:
                col.update_one({"_id": existing["_id"]}, {"$set": failed_doc})
                failed_doc["_id"] = str(existing["_id"])
                failed_doc["id"] = str(existing["_id"])
            else:
                res = col.insert_one(failed_doc)
                failed_doc["_id"] = str(res.inserted_id)
                failed_doc["id"] = str(res.inserted_id)
            return failed_doc

        # 2. Validation for successful completion: meeting_summary is mandatory
        if not req.meeting_summary or not req.meeting_summary.strip():
            raise HTTPException(
                status_code=400,
                detail="Meeting summary is required to complete meeting analysis."
            )

        # 3. Build and persist meeting document
        meeting_doc = {
            "meeting_id": meeting_id,
            "team_id": team_id,
            "meeting_title": req.meeting_title.strip(),
            "title": req.meeting_title.strip(),
            "duration": req.duration or "00:00",
            "participants": req.participants or [],
            "meeting_summary": req.meeting_summary.strip(),
            "summary": req.meeting_summary.strip(),
            "key_decisions": req.key_decisions or [],
            "action_items": req.action_items or [],
            "team_lead_email": host_email or "",
            "host_id": host_id,
            "host_name": host_name,
            "host_email": host_email,
            "host_role": "Team Leader",
            "status": "Completed",
            "created_by": current_user.get("user_id"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        existing = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if existing:
            col.update_one({"_id": existing["_id"]}, {"$set": meeting_doc})
            meeting_doc["_id"] = str(existing["_id"])
            meeting_doc["id"] = str(existing["_id"])
        else:
            res = col.insert_one(meeting_doc)
            meeting_doc["_id"] = str(res.inserted_id)
            meeting_doc["id"] = str(res.inserted_id)

        # 4. Trigger Zapier Meeting Completed Webhook only after successful persistence
        dispatch_webhook_in_background(
            ZapierService.send_meeting_completed_webhook(meeting_doc)
        )

        return meeting_doc

    @staticmethod
    def list_meetings(team_id: str) -> List[Dict[str, Any]]:
        col = get_col("meetings")
        cursor = col.find({"team_id": team_id}).sort("created_at", -1)
        meetings = []
        for doc in cursor:
            doc["id"] = str(doc["_id"])
            doc["_id"] = str(doc["_id"])
            meetings.append(doc)
        return meetings

    @staticmethod
    def get_meeting(team_id: str, meeting_id: str) -> Dict[str, Any]:
        col = get_col("meetings")
        doc = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")
        doc["id"] = str(doc["_id"])
        doc["_id"] = str(doc["_id"])
        return doc

    @staticmethod
    def start_meeting(
        team_id: str,
        current_user: dict,
        req: MeetingStartRequest
    ) -> Dict[str, Any]:
        """
        Initializes an active meeting session in MongoDB with selected participants.
        """
        title = req.meeting_title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Meeting title is required.")

        member_col = get_col("member_profiles")
        
        # Verify selected participants belong to this team and are active
        selected_ids = req.selected_participant_ids or []
        verified_participants = []

        if selected_ids:
            found_members = list(member_col.find({
                "team_id": team_id,
                "member_id": {"$in": selected_ids},
                "account_status": "active"
            }))
            for m in found_members:
                verified_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member"),
                    "profile_image": m.get("profile_image")
                })
        elif req.participants:
            # If participant objects passed
            for p in req.participants:
                p_id = p.get("member_id") if isinstance(p, dict) else str(p)
                m = member_col.find_one({"team_id": team_id, "member_id": p_id, "account_status": "active"})
                if m:
                    verified_participants.append({
                        "member_id": m.get("member_id"),
                        "name": m.get("name"),
                        "email": m.get("email"),
                        "role": m.get("role", "Member")
                    })
                    selected_ids.append(m.get("member_id"))
        else:
            # Default: all active team members
            active_members = list(member_col.find({"team_id": team_id, "account_status": "active"}))
            for m in active_members:
                verified_participants.append({
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "email": m.get("email"),
                    "role": m.get("role", "Member")
                })
                selected_ids.append(m.get("member_id"))

        # Only Team Leader can start a new meeting session
        from app.services.task_service import TaskService
        from app.services.zapier_service import ZapierService
        TaskService.require_team_leader(team_id, current_user)

        # Ensure host is the workspace's Team Leader
        leader = ZapierService._resolve_team_leader(team_id)
        host_user_id = leader.get("id") or current_user.get("user_id") or str(current_user.get("_id", ""))
        host_email = leader.get("email") or current_user.get("email", "")
        host_name = leader.get("name") or current_user.get("name") or "Team Leader"
        host_role = "Team Leader"

        if not verified_participants:
            host_m = member_col.find_one({"team_id": team_id, "email": host_email}) if host_email else None
            effective_host_id = (host_m and host_m.get("member_id")) or host_user_id or f"host_{uuid.uuid4().hex[:8]}"
            verified_participants.append({
                "member_id": effective_host_id,
                "name": host_name,
                "email": host_email,
                "role": host_role,
                "is_host": True
            })
            if not selected_ids:
                selected_ids = [effective_host_id]

        col = get_col("meetings")
        meeting_id = MeetingService._generate_meeting_id(team_id, current_user)
        now = datetime.utcnow()

        meeting_doc = {
            "meeting_id": meeting_id,
            "team_id": team_id,
            "meeting_title": title,
            "title": title,
            "status": "In Progress",
            "duration": "00:00",
            "host_id": host_user_id,
            "host_name": host_name,
            "host_email": host_email,
            "host_role": host_role,
            "selected_participant_ids": selected_ids,
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
            "team_lead_email": current_user.get("email", ""),
            "created_by": current_user.get("user_id"),
            "created_at": now,
            "updated_at": now
        }

        res = col.insert_one(meeting_doc)
        meeting_doc["_id"] = str(res.inserted_id)
        meeting_doc["id"] = str(res.inserted_id)
        return meeting_doc

    @staticmethod
    def upload_meeting_audio_file(
        team_id: str,
        meeting_id: str,
        file_bytes: bytes,
        filename: str,
        duration: str = "00:00",
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Saves meeting audio into local uploads directory, validates it, and updates meeting metadata."""
        import logging
        log = logging.getLogger("meetmind.meeting_service")
        col = get_col("meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        log.info(f"AUDIO_UPLOAD_STARTED | meeting_id={meeting_id} bytes={len(file_bytes)} filename={filename}")
        capture_res = AudioCaptureAgent.execute(
            meeting_id=meeting_id,
            team_id=team_id,
            audio_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            validate_audio=True,
        )
        diag = capture_res.get("diagnostics", {})
        log.info(
            f"AUDIO_UPLOAD_COMPLETED | meeting_id={meeting_id} size={capture_res['file_size']} "
            f"dedup={capture_res.get('deduplicated', False)}"
        )
        log.info(
            f"AUDIO_VALIDATION_COMPLETED | meeting_id={meeting_id} decodable={diag.get('decodable')} "
            f"duration_s={diag.get('duration_seconds')} sr={diag.get('sample_rate')} "
            f"ch={diag.get('channels')} is_silent={diag.get('is_silent')}"
        )

        updates = {
            "audio_path": capture_res["storage_path"],
            "filename": capture_res["filename"],
            "file_size": capture_res["file_size"],
            "content_type": capture_res.get("content_type"),
            "audio_diagnostics": diag,
            "duration": duration,
            "updated_at": datetime.utcnow(),
        }
        col.update_one({"_id": meeting["_id"]}, {"$set": updates})
        meeting.update(updates)
        meeting["_id"] = str(meeting["_id"])
        meeting["id"] = str(meeting["_id"])
        return meeting

    @staticmethod
    def transcribe_meeting_chunk(
        team_id: str,
        meeting_id: str,
        chunk_bytes: bytes,
        filename: str = "chunk.webm",
        start_offset: float = 0.0,
        speaker_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Transcribes incoming audio chunk and persists segments progressively."""
        col = get_col("meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        seg_col = get_col("transcript_segments")
        existing_count = seg_col.count_documents({"team_id": team_id, "meeting_id": meeting_id})
        
        # Calculate start offset from existing segments if not passed
        if start_offset == 0.0 and existing_count > 0:
            last_seg = seg_col.find_one({"team_id": team_id, "meeting_id": meeting_id}, sort=[("end", -1)])
            if last_seg and "end" in last_seg:
                start_offset = float(last_seg["end"])

        res = TranscriptionAgent.transcribe_bytes(
            audio_bytes=chunk_bytes,
            filename=filename,
            start_offset=start_offset
        )

        effective_speaker = speaker_name.strip() if speaker_name and speaker_name.strip() else "Speaker 1"
        now = datetime.utcnow()
        saved_segments = []
        for idx, s in enumerate(res.get("segments", [])):
            raw_text = s.get("text", "").strip()
            # If explicit speaker passed and not already in raw text, format text nicely
            formatted_text = raw_text
            if speaker_name and not raw_text.lower().startswith(f"{speaker_name.lower()}:"):
                formatted_text = f"{speaker_name}: {raw_text}"

            seg_doc = {
                "meeting_id": meeting_id,
                "team_id": team_id,
                "segment_id": existing_count + idx + 1,
                "speaker_id": effective_speaker,
                "speaker_label": effective_speaker,
                "suggested_name": effective_speaker,
                "start": s.get("start", start_offset),
                "end": s.get("end", start_offset + 3.0),
                "text": formatted_text,
                "created_at": now
            }
            if raw_text:
                seg_col.insert_one(seg_doc)
                seg_doc["_id"] = str(seg_doc["_id"])
                saved_segments.append(seg_doc)

        return {
            "status": "success",
            "new_segments": saved_segments,
            "full_text": res.get("full_text", ""),
            "total_segments": existing_count + len(saved_segments)
        }

    @staticmethod
    async def complete_meeting_session(
        team_id: str,
        meeting_id: str,
        current_user: dict,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        duration: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes full final analysis, diarization, LangGraph multi-agent pipeline, and persists results."""
        MeetingService.require_meeting_host(team_id, meeting_id, current_user)
        col = get_col("meetings")
        meeting = col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        has_new_audio = bool(file_bytes and filename)
        if has_new_audio:
            MeetingService.upload_meeting_audio_file(
                team_id=team_id,
                meeting_id=meeting_id,
                file_bytes=file_bytes,
                filename=filename,
                duration=duration or meeting.get("duration", "00:00"),
                content_type=content_type,
            )
        elif duration:
            col.update_one({"_id": meeting["_id"]}, {"$set": {"duration": duration}})

        # Always force authoritative full-file transcription when new audio was uploaded
        result = await MeetingService.process_meeting(
            team_id=team_id,
            meeting_id=meeting_id,
            current_user=current_user,
            force_retranscribe=has_new_audio,
        )

        # Synchronize scheduled_meetings only if meeting genuinely completed
        if result.get("status") == "Completed":
            try:
                from datetime import timezone as dt_tz
                get_col("scheduled_meetings").update_one(
                    {"meeting_id": meeting_id},
                    {"$set": {
                        "meeting_status": "completed",
                        "status": "COMPLETED",
                        "actual_completed_at": datetime.now(dt_tz.utc).isoformat(),
                        "duration": duration or meeting.get("duration", "00:00"),
                    }},
                )
            except Exception:
                pass

        return result

    @staticmethod
    def get_meeting_analysis(team_id: str, meeting_id: str) -> Dict[str, Any]:
        """Retrieves full analysis deliverables, transcript, speakers, and action items."""
        meeting = MeetingService.get_meeting(team_id, meeting_id)
        seg_col = get_col("transcript_segments")
        tasks_col = get_col("tasks")

        segments = list(seg_col.find({"team_id": team_id, "meeting_id": meeting_id}).sort("start", 1))
        for s in segments:
            s["id"] = str(s["_id"])
            s["_id"] = str(s["_id"])

        extracted_tasks = list(tasks_col.find({"team_id": team_id, "meeting_id": meeting_id}))
        for t in extracted_tasks:
            t["id"] = str(t["_id"])
            t["_id"] = str(t["_id"])

        return {
            "meeting_id": meeting["meeting_id"],
            "team_id": meeting["team_id"],
            "meeting_title": meeting.get("meeting_title", meeting.get("title")),
            "title": meeting.get("meeting_title", meeting.get("title")),
            "duration": meeting.get("duration", "00:00"),
            "status": meeting.get("status", "Completed"),
            "selected_participant_ids": meeting.get("selected_participant_ids", []),
            "participants": meeting.get("participants", []),
            "meeting_summary": meeting.get("meeting_summary", meeting.get("summary")),
            "summary": meeting.get("meeting_summary", meeting.get("summary")),
            "discussion_topics": meeting.get("discussion_topics", []),
            "key_decisions": meeting.get("key_decisions", []),
            "unresolved_questions": meeting.get("unresolved_questions", []),
            "action_items": meeting.get("action_items", []),
            "speaker_catalog": meeting.get("speaker_catalog", []),
            "agent_executions": meeting.get("agent_executions", []),
            "transcript_segments": segments,
            "extracted_tasks": extracted_tasks,
            "created_at": meeting.get("created_at"),
            "completed_at": meeting.get("completed_at")
        }

    @staticmethod
    def approve_meeting_task(
        team_id: str,
        meeting_id: str,
        task_id: str,
        current_user: dict,
        req: Optional[TaskApproveMeetingRequest] = None
    ) -> Dict[str, Any]:
        """Approves task from meeting (Team Leader only), allowing optional leader adjustments prior to Zapier dispatch."""
        from app.services.task_service import TaskService
        from app.schemas.task_schemas import TaskUpdateRequest

        TaskService.require_team_leader(team_id, current_user)
        task = get_col("tasks").find_one({
            "team_id": team_id,
            "meeting_id": meeting_id,
            "task_id": task_id
        })
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found for this meeting.")

        # Apply any overrides prior to approval if leader edited/reassigned
        if req:
            update_data = TaskUpdateRequest(
                priority=req.priority,
                deadline=req.deadline,
                assigned_member_id=req.assigned_member_id,
                assigned_member_name=req.assigned_member_name,
                assigned_member_email=req.assigned_member_email,
                assigned_member_role=req.assigned_member_role
            )
            TaskService.update_task(team_id=team_id, task_id=task_id, current_user=current_user, req=update_data)

        # Approve and dispatch Zapier webhook
        res = TaskService.approve_task(team_id=team_id, task_id=task_id, current_user=current_user)
        if "_id" in res:
            res["_id"] = str(res["_id"])
        if "id" not in res and "_id" in res:
            res["id"] = str(res["_id"])
        return res

    @staticmethod
    def edit_meeting_task(
        team_id: str,
        meeting_id: str,
        task_id: str,
        current_user: dict,
        req: TaskEditMeetingRequest
    ) -> Dict[str, Any]:
        """Updates task details before human approval."""
        from app.services.task_service import TaskService
        from app.schemas.task_schemas import TaskUpdateRequest

        TaskService.require_team_leader(team_id, current_user)
        task = get_col("tasks").find_one({
            "team_id": team_id,
            "meeting_id": meeting_id,
            "task_id": task_id
        })
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found for this meeting.")

        update_data = TaskUpdateRequest(
            title=req.title,
            description=req.description,
            priority=req.priority,
            deadline=req.deadline,
            assigned_member_id=req.assigned_member_id,
            assigned_member_name=req.assigned_member_name,
            assigned_member_email=req.assigned_member_email,
            assigned_member_role=req.assigned_member_role
        )
        res = TaskService.update_task(team_id=team_id, task_id=task_id, current_user=current_user, req=update_data)
        if "_id" in res:
            res["_id"] = str(res["_id"])
        if "id" not in res and "_id" in res:
            res["id"] = str(res["_id"])
        return res

    @staticmethod
    def get_meeting_diagnostics(team_id: str, meeting_id: str) -> Dict[str, Any]:
        """Provides full stage-by-stage pipeline inspection for a given meeting."""
        meetings_col = get_col("meetings")
        meeting = meetings_col.find_one({"team_id": team_id, "meeting_id": meeting_id})
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found.")

        seg_col = get_col("transcript_segments")
        tasks_col = get_col("tasks")
        member_col = get_col("member_profiles")
        logs_col = get_col("automation_logs")
        from app.config import settings

        # 1. Audio status & diagnostics
        audio_path = meeting.get("audio_path", "")
        audio_exists = bool(audio_path and os.path.exists(audio_path))
        audio_size = os.path.getsize(audio_path) if audio_exists else 0
        audio_diag = meeting.get("audio_diagnostics") or (
            StorageService.inspect_audio_file(audio_path, meeting.get("content_type")) if audio_exists else {}
        )

        # 2. Transcripts
        segments = list(seg_col.find({"team_id": team_id, "meeting_id": meeting_id}).sort("start", 1))
        for s in segments:
            s["id"] = str(s["_id"])
            s["_id"] = str(s["_id"])
        total_transcript_words = sum(len(s.get("text", "").split()) for s in segments)
        raw_transcript = " ".join(s.get("text", "") for s in segments if s.get("text", ""))

        # 3. Tasks in DB
        db_tasks = list(tasks_col.find({"team_id": team_id, "meeting_id": meeting_id}))
        for t in db_tasks:
            t["id"] = str(t["_id"])
            t["_id"] = str(t["_id"])

        # 4. Workspace members
        active_members = list(member_col.find({"team_id": team_id, "account_status": "active"}))
        for m in active_members:
            m["id"] = str(m["_id"])
            m["_id"] = str(m["_id"])

        # 5. Automation logs
        meeting_logs = list(logs_col.find({"team_id": team_id, "meeting_id": meeting_id}))
        for l in meeting_logs:
            l["id"] = str(l["_id"])
            l["_id"] = str(l["_id"])

        return {
            "meeting_id": meeting_id,
            "team_id": team_id,
            "processing_job_id": meeting.get("processing_job_id"),
            "current_stage": meeting.get("current_stage"),
            "title": meeting.get("meeting_title", meeting.get("title", "")),
            "status": meeting.get("status"),
            "error_message": meeting.get("error_message"),
            "audio": {
                "audio_path": audio_path,
                "file_exists": audio_exists,
                "file_size_bytes": audio_size,
                "duration": meeting.get("duration", "00:00"),
                "filename": meeting.get("filename"),
                "mime_type": audio_diag.get("mime_type") or meeting.get("content_type"),
                "sample_rate": audio_diag.get("sample_rate", 0),
                "channels": audio_diag.get("channels", 0),
                "decoded_duration_seconds": audio_diag.get("duration_seconds", 0.0),
                "dbfs": audio_diag.get("dbfs"),
                "max_dbfs": audio_diag.get("max_dbfs"),
                "is_silent": audio_diag.get("is_silent"),
                "has_speech_signal": audio_diag.get("has_speech_signal"),
                "decodable": audio_diag.get("decodable", False),
            },
            "transcription": {
                "status": meeting.get("transcription_status"),
                "vad_status": meeting.get("vad_status"),
                "vad_message": meeting.get("vad_message"),
                "segment_count": len(segments),
                "total_words": total_transcript_words,
                "raw_transcript_preview": raw_transcript[:500] if raw_transcript else "",
                "segments": segments
            },
            "diarization": {
                "speaker_catalog": meeting.get("speaker_catalog", []),
                "distinct_speakers": list({s.get("speaker_id") for s in segments if s.get("speaker_id")})
            },
            "task_pipeline": {
                "total_tasks_in_db": len(db_tasks),
                "tasks": db_tasks,
                "extracted_tasks_in_meeting_doc": meeting.get("extracted_tasks", [])
            },
            "agent_telemetry": meeting.get("agent_executions", []),
            "members_available_for_matching": [
                {
                    "member_id": m.get("member_id"),
                    "name": m.get("name"),
                    "role": m.get("role"),
                    "email": m.get("email"),
                    "technical_skills": m.get("technical_skills", [])
                }
                for m in active_members
            ],
            "automation_safety": {
                "enable_automation_dispatch": getattr(settings, "ENABLE_AUTOMATION_DISPATCH", False),
                "automation_dispatched": meeting.get("automation_dispatched", False),
                "automation_logs_count": len(meeting_logs)
            }
        }
