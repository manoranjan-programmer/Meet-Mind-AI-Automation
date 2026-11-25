import os
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from app.middleware.auth import get_current_user
from app.schemas.meeting_schemas import (
    MeetingCompleteRequest, 
    MeetingResponse, 
    MeetingListResponse,
    MeetingStartRequest,
    TaskApproveMeetingRequest,
    TaskEditMeetingRequest
)
from app.schemas.task_schemas import TaskResponse
from app.schemas.scheduled_meeting_schemas import (
    ParseScheduleCommandRequest,
    MeetingPreviewResponse,
    ConfirmScheduleRequest,
    UpdateScheduleRequest,
    ScheduledMeetingResponse,
    UpcomingMeetingsListResponse
)
from app.config import settings
from app.services.meeting_service import MeetingService
from app.services.storage_service import StorageService
from app.services.scheduler_service import SchedulerService
from app.services.webrtc_service import meeting_signaling_manager
from app.middleware.workspace_auth import require_workspace_member, require_workspace_leader, verify_workspace_access
from app.utils.security import decode_access_token
from fastapi import WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/meetings", tags=["Meeting Management"])
meeting_ws_router = APIRouter(tags=["Meeting WebRTC Signaling"])

@router.get("/ice-servers")
def get_ice_servers(current_user: dict = Depends(get_current_user)):
    """Provides WebRTC STUN and TURN configurations for real video/audio peer connections."""
    ice_servers = []
    stun_urls = [s.strip() for s in settings.RTC_STUN_SERVERS.split(",") if s.strip()]
    if stun_urls:
        ice_servers.append({"urls": stun_urls})

    if settings.RTC_TURN_SERVER:
        turn_cfg = {"urls": settings.RTC_TURN_SERVER}
        if settings.RTC_TURN_USERNAME:
            turn_cfg["username"] = settings.RTC_TURN_USERNAME
        if settings.RTC_TURN_CREDENTIAL:
            turn_cfg["credential"] = settings.RTC_TURN_CREDENTIAL
        ice_servers.append(turn_cfg)

    return {
        "ice_servers": ice_servers,
        "max_mesh_peers": 8,
        "topology": "mesh",
        "recommendation": "For 10+ concurrent users, Selective Forwarding Unit (SFU) is recommended."
    }

# ----------------- REAL-TIME WEBRTC SIGNALING WEBSOCKET ----------------- #

@meeting_ws_router.websocket("/ws/meetings/{meeting_id}/signaling")
async def meeting_webrtc_signaling(
    websocket: WebSocket,
    meeting_id: str,
    token: Optional[str] = Query(None)
):
    """
    WebSocket signaling channel for real-time WebRTC audio/video mesh conference.
    Exchanges SDP offers, answers, ICE candidates, and track states.
    """
    if not token:
        await websocket.close(code=1008)
        return

    token_payload = decode_access_token(token)
    user_id = token_payload.get("user_id") if token_payload else None
    if not user_id:
        await websocket.close(code=1008)
        return

    from app.database.mongo import get_col
    current_user = get_col("users").find_one({"user_id": user_id})
    if not current_user:
        await websocket.close(code=1008)
        return

    mtg_doc = (
        get_col("scheduled_meetings").find_one({
            "$or": [{"room_id": meeting_id}, {"meeting_id": meeting_id}]
        })
        or get_col("meetings").find_one({
            "$or": [{"room_id": meeting_id}, {"meeting_id": meeting_id}]
        })
    )
    if not mtg_doc or not mtg_doc.get("team_id"):
        await websocket.close(code=1008)
        return

    try:
        verify_workspace_access(team_id=mtg_doc["team_id"], current_user=current_user)
    except HTTPException:
        await websocket.close(code=1008)
        return

    host_id = MeetingService.authoritative_host_id(mtg_doc["team_id"], mtg_doc)
    peer_is_host = bool(host_id and current_user.get("user_id") == host_id)
    await websocket.accept()
    current_peer_id = None

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                msg = json.loads(text_data)
                event_type = msg.get("event")
                data = msg.get("data", {})

                if event_type == "join_room":
                    current_peer_id = data.get("peer_id")
                    user_info = {
                        "user_id": current_user.get("user_id"),
                        "name": current_user.get("name") or "Participant",
                        "role": "Team Leader" if peer_is_host else "Participant",
                        "is_host": peer_is_host,
                        "video_enabled": data.get("video_enabled", False),
                        "audio_enabled": data.get("audio_enabled", True)
                    }
                    await meeting_signaling_manager.join_room(
                        meeting_id=meeting_id,
                        peer_id=current_peer_id,
                        user_info=user_info,
                        websocket=websocket
                    )

                elif event_type in ["offer", "answer", "ice_candidate"]:
                    target_peer = data.get("target_peer_id")
                    signal_data = data.get("signal")
                    if target_peer and signal_data:
                        await meeting_signaling_manager.relay_signal(
                            meeting_id=meeting_id,
                            from_peer_id=current_peer_id,
                            target_peer_id=target_peer,
                            event=event_type,
                            signal_data=signal_data
                        )

                elif event_type == "track_state_changed":
                    await meeting_signaling_manager.update_track_state(
                        meeting_id=meeting_id,
                        peer_id=current_peer_id,
                        video_enabled=data.get("video_enabled"),
                        audio_enabled=data.get("audio_enabled"),
                        screen_sharing=data.get("screen_sharing")
                    )

                elif event_type == "meeting_chat_message":
                    await meeting_signaling_manager.broadcast_chat_message(
                        meeting_id=meeting_id,
                        from_peer_id=current_peer_id,
                        sender_name=data.get("sender_name", "Participant"),
                        text=data.get("text", "")
                    )

                elif event_type == "end_meeting":
                    # Only the meeting host can broadcast meeting_ended to all participants
                    if meeting_signaling_manager.is_peer_host(meeting_id, current_peer_id):
                        await meeting_signaling_manager.broadcast_to_room(
                            meeting_id=meeting_id,
                            event="meeting_ended",
                            data={"ended_by": current_user.get("name") or "Team Leader"},
                            exclude_peer_id=current_peer_id
                        )

                elif event_type == "leave_room":
                    if current_peer_id:
                        await meeting_signaling_manager.leave_room(meeting_id, current_peer_id)
                        current_peer_id = None

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"[WebRTC WS] Error handling signal message: {e}")

    except WebSocketDisconnect:
        if current_peer_id:
            await meeting_signaling_manager.leave_room(meeting_id, current_peer_id)
    except Exception as e:
        logger.error(f"[WebRTC WS] Unexpected error: {e}")
        if current_peer_id:
            await meeting_signaling_manager.leave_room(meeting_id, current_peer_id)

# ----------------- SCHEDULED MEETINGS & NATURAL LANGUAGE SCHEDULER ----------------- #

@router.post("/schedule/parse-command", response_model=MeetingPreviewResponse)
def parse_schedule_command(
    req: ParseScheduleCommandRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Parses natural language meeting scheduling commands using Groq LLM.
    Returns structured preview with confirmation prompt. Does not save until confirmed.
    """
    verify_workspace_access(
        team_id=current_user.get("team_id"),
        current_user=current_user,
        allowed_roles=["Team Leader"]
    )
    team_id = current_user.get("team_id")
    return SchedulerService.parse_natural_language_command(
        command=req.command,
        team_id=team_id,
        timezone_str=req.timezone
    )

@router.post("/schedule", status_code=201)
async def confirm_schedule_meeting(
    req: ConfirmScheduleRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Explicitly confirms and saves a scheduled meeting into MongoDB.
    Dispatches automated meeting invitation notification.
    """
    team_id = current_user.get("team_id")
    return await SchedulerService.confirm_and_schedule_meeting(
        team_id=team_id,
        current_user=current_user,
        req=req
    )

@router.get("/upcoming", response_model=UpcomingMeetingsListResponse)
def get_upcoming_meetings(
    team_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns upcoming, today's, active, completed, and cancelled meetings for the workspace.
    """
    user_team_id = current_user.get("team_id")
    if team_id and team_id != user_team_id:
        raise HTTPException(status_code=403, detail="Access denied: Cannot view meetings from another workspace.")
    target_team = user_team_id
    verify_workspace_access(team_id=target_team, current_user=current_user)
    return SchedulerService.get_upcoming_meetings(team_id=target_team)

@router.get("/room/{room_id}")
def get_meeting_by_room_id(
    room_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Looks up meeting metadata by room_id with workspace isolation and authoritative host details."""
    from app.database.mongo import get_col
    from app.services.zapier_service import ZapierService
    team_id = current_user.get("team_id")
    verify_workspace_access(team_id=team_id, current_user=current_user)
    col = get_col("scheduled_meetings")
    m = col.find_one({"team_id": team_id, "$or": [{"room_id": room_id}, {"meeting_id": room_id}]})
    if not m:
        m = get_col("meetings").find_one({"team_id": team_id, "$or": [{"room_id": room_id}, {"meeting_id": room_id}]})
    if not m:
        raise HTTPException(status_code=404, detail=f"Meeting room '{room_id}' not found.")
    leader = ZapierService._resolve_team_leader(team_id)
    if leader.get("id"):
        m["host_id"] = leader["id"]
    if leader.get("name"):
        m["host_name"] = leader["name"]
    if leader.get("email"):
        m["host_email"] = leader["email"]
    m["host_role"] = "Team Leader"
    m["id"] = str(m["_id"])
    m.pop("_id", None)
    return m

@router.post("/{meeting_id}/start-session")
def start_scheduled_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Starts a scheduled meeting, making it active/live."""
    team_id = current_user.get("team_id")
    try:
        return SchedulerService.start_scheduled_meeting(
            team_id=team_id,
            meeting_id=meeting_id,
            current_user=current_user
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.put("/{meeting_id}", response_model=ScheduledMeetingResponse)
@router.post("/{meeting_id}/edit-schedule", response_model=ScheduledMeetingResponse)
def edit_scheduled_meeting(
    meeting_id: str,
    req: UpdateScheduleRequest,
    current_user: dict = Depends(get_current_user)
):
    """Edits a scheduled meeting in MongoDB."""
    team_id = current_user.get("team_id")
    try:
        return SchedulerService.update_scheduled_meeting(
            team_id=team_id,
            meeting_id=meeting_id,
            current_user=current_user,
            req=req
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/{meeting_id}/end-session")
def end_scheduled_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Ends an active scheduled meeting."""
    team_id = current_user.get("team_id")
    try:
        return SchedulerService.end_scheduled_meeting(
            team_id=team_id,
            meeting_id=meeting_id,
            current_user=current_user
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/{meeting_id}/cancel")
def cancel_scheduled_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancels a scheduled meeting."""
    team_id = current_user.get("team_id")
    try:
        return SchedulerService.cancel_scheduled_meeting(
            team_id=team_id,
            meeting_id=meeting_id,
            current_user=current_user
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/start", status_code=201)
def start_meeting(
    req: MeetingStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Initializes a new live meeting session in MongoDB with verified active participants.
    """
    team_id = current_user["team_id"]
    return MeetingService.start_meeting(team_id=team_id, current_user=current_user, req=req)

@router.post("/{meeting_id}/audio")
async def upload_meeting_audio_file(
    meeting_id: str,
    file: UploadFile = File(...),
    duration: Optional[str] = Form("00:00"),
    current_user: dict = Depends(get_current_user)
):
    """
    Uploads complete recorded audio file for an active meeting session.
    """
    team_id = current_user["team_id"]
    MeetingService.require_meeting_host(team_id, meeting_id, current_user)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    return MeetingService.upload_meeting_audio_file(
        team_id=team_id,
        meeting_id=meeting_id,
        file_bytes=file_bytes,
        filename=file.filename or "recording.webm",
        duration=duration or "00:00",
        content_type=file.content_type,
    )

@router.post("/{meeting_id}/transcribe")
async def transcribe_meeting_chunk(
    meeting_id: str,
    file: UploadFile = File(...),
    start_offset: Optional[float] = Form(0.0),
    speaker_name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Progressively transcribes audio chunks in real-time during the meeting session.
    """
    team_id = current_user["team_id"]
    MeetingService.require_meeting_host(team_id, meeting_id, current_user)
    file_bytes = await file.read()
    if not file_bytes:
        return {"status": "empty", "new_segments": [], "total_segments": 0}
    return MeetingService.transcribe_meeting_chunk(
        team_id=team_id,
        meeting_id=meeting_id,
        chunk_bytes=file_bytes,
        filename=file.filename or "chunk.webm",
        start_offset=start_offset or 0.0,
        speaker_name=speaker_name
    )

@router.post("/{meeting_id}/complete")
async def complete_meeting_endpoint(
    meeting_id: str,
    file: Optional[UploadFile] = File(None),
    duration: Optional[str] = Form(None),
    active_attendee_emails: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Finalizes the meeting session, uploads final audio if provided,
    runs final Whisper transcription pass, speaker diarization, LangGraph multi-agent analysis,
    and triggers Zapier meeting_completed webhook.
    """
    team_id = current_user["team_id"]
    file_bytes = None
    filename = None
    content_type = None
    if file:
        file_bytes = await file.read()
        filename = file.filename or "recording.webm"
        content_type = file.content_type

    parsed_attendees = None
    if active_attendee_emails:
        try:
            raw_list = json.loads(active_attendee_emails)
            if isinstance(raw_list, list):
                parsed_attendees = [str(x) for x in raw_list if x]
        except Exception:
            parsed_attendees = [x.strip() for x in active_attendee_emails.split(",") if x.strip()]

    return await MeetingService.complete_meeting_session(
        team_id=team_id,
        meeting_id=meeting_id,
        current_user=current_user,
        file_bytes=file_bytes,
        filename=filename,
        duration=duration,
        content_type=content_type,
        active_attendee_emails=parsed_attendees,
    )


@router.post("/{meeting_id}/map-speakers")
def map_meeting_speakers_endpoint(
    meeting_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Maps unidentified speakers (e.g. Speaker 1) to registered team members and updates pending tasks."""
    team_id = current_user["team_id"]
    mappings = body.get("mappings") if isinstance(body, dict) else {}
    return MeetingService.map_meeting_speakers(
        team_id=team_id,
        meeting_id=meeting_id,
        current_user=current_user,
        mappings=mappings or {},
    )


@router.post("/{meeting_id}/retry-transcription")
async def retry_meeting_transcription(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Re-runs Whisper transcription on the saved audio file and full LangGraph analysis."""
    team_id = current_user["team_id"]
    return await MeetingService.process_meeting(
        team_id=team_id,
        meeting_id=meeting_id,
        current_user=current_user,
        force_retranscribe=True,
    )


@router.post("/{meeting_id}/retry-analysis")
async def retry_meeting_analysis(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Re-runs LangGraph AI analysis reusing the existing saved transcript without re-uploading audio."""
    team_id = current_user["team_id"]
    return await MeetingService.process_meeting(
        team_id=team_id,
        meeting_id=meeting_id,
        current_user=current_user,
        force_retranscribe=False,
    )

@router.get("/{meeting_id}/analysis")
def get_meeting_analysis(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves complete meeting analysis deliverables including summary, topics, decisions,
    tasks, speakers, and agent execution telemetry.
    """
    team_id = current_user["team_id"]
    return MeetingService.get_meeting_analysis(team_id, meeting_id)

@router.get("/{meeting_id}/diagnostics")
def get_meeting_diagnostics(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Internal diagnostic endpoint returning detailed stage-by-stage pipeline telemetry:
    audio verification, transcript segments, LLM extraction outputs,
    member matching resolution, and automation safety status.
    """
    team_id = current_user["team_id"]
    return MeetingService.get_meeting_diagnostics(team_id, meeting_id)

@router.post("/{meeting_id}/tasks/approve", response_model=TaskResponse)
def approve_meeting_task(
    meeting_id: str,
    req: TaskApproveMeetingRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Approves an extracted task from this meeting and triggers the Zapier task_approved webhook.
    """
    team_id = current_user["team_id"]
    return MeetingService.approve_meeting_task(
        team_id=team_id,
        meeting_id=meeting_id,
        task_id=req.task_id,
        current_user=current_user,
        req=req
    )

@router.post("/{meeting_id}/tasks/edit", response_model=TaskResponse)
def edit_meeting_task(
    meeting_id: str,
    req: TaskEditMeetingRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Allows the team leader to edit or reassign an extracted task prior to approval.
    """
    team_id = current_user["team_id"]
    return MeetingService.edit_meeting_task(
        team_id=team_id,
        meeting_id=meeting_id,
        task_id=req.task_id,
        current_user=current_user,
        req=req
    )

@router.get("/{meeting_id}/tasks")
def get_meeting_tasks(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves all tasks extracted from a specific meeting session.
    """
    team_id = current_user["team_id"]
    from app.database.mongo import get_col
    tasks_col = get_col("tasks")
    tasks = list(tasks_col.find({"team_id": team_id, "meeting_id": meeting_id}))
    for t in tasks:
        t["id"] = str(t["_id"])
        t["_id"] = str(t["_id"])
    return {"tasks": tasks, "total": len(tasks)}

@router.post("/upload", status_code=201)
async def upload_meeting_audio(
    file: UploadFile = File(...),
    meeting_title: str = Form("Sprint Planning & Feature Sync"),
    participants: Optional[str] = Form("Jai, Arun, Priya, Karthik"),
    duration: Optional[str] = Form("00:00"),
    current_user: dict = Depends(get_current_user)
):
    """
    Agent 1 Audio Capture:
    Uploads audio file (WAV, MP3, M4A, WebM) into local uploads directory.
    Stores initial meeting document in MongoDB.
    """
    team_id = current_user["team_id"]
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Parse participants
    parsed_participants: List[str] = []
    if participants:
        try:
            parsed = json.loads(participants)
            if isinstance(parsed, list):
                parsed_participants = [str(p).strip() for p in parsed]
        except Exception:
            parsed_participants = [p.strip() for p in participants.split(",") if p.strip()]

    meeting_doc = MeetingService.upload_meeting_audio(
        team_id=team_id,
        current_user=current_user,
        file_bytes=file_bytes,
        filename=file.filename or "recording.webm",
        meeting_title=meeting_title,
        participants=parsed_participants,
        duration=duration or "00:00"
    )

    return meeting_doc

@router.post("/{meeting_id}/process")
async def process_meeting_pipeline(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Executes the 8-Agent LangGraph Pipeline:
    Transcription (Whisper) -> Speaker Diarization -> Meeting Analysis (Groq LLaMA 3.3) ->
    Task Extraction -> Intelligent Task Assignment -> Review & Validation ->
    MongoDB Persistence (Tasks queue awaiting human approval) -> Zapier meeting_completed webhook.
    """
    team_id = current_user["team_id"]
    result = await MeetingService.process_meeting(
        team_id=team_id,
        meeting_id=meeting_id,
        current_user=current_user
    )
    return result

@router.get("/{meeting_id}/audio")
def get_meeting_audio(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Streams stored meeting audio file for browser playback."""
    team_id = current_user["team_id"]
    meeting = MeetingService.get_meeting(team_id, meeting_id)
    audio_path = meeting.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio recording not found on server.")

    content_type = "audio/webm"
    if audio_path.endswith(".mp3"):
        content_type = "audio/mpeg"
    elif audio_path.endswith(".wav"):
        content_type = "audio/wav"
    elif audio_path.endswith(".m4a"):
        content_type = "audio/mp4"

    return FileResponse(
        path=audio_path,
        media_type=content_type,
        filename=os.path.basename(audio_path)
    )

@router.get("/{meeting_id}/transcript")
def get_meeting_transcript(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieves speaker-attributed transcript segments from MongoDB."""
    team_id = current_user["team_id"]
    return MeetingService.get_meeting_transcript(team_id, meeting_id)

@router.get("/{meeting_id}/summary")
def get_meeting_summary(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieves AI executive summary, key decisions, discussion topics, and action items."""
    team_id = current_user["team_id"]
    return MeetingService.get_meeting_summary(team_id, meeting_id)

@router.get("/{meeting_id}/export-pdf")
def export_meeting_pdf(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generates and downloads a PDF of the meeting intelligence report."""
    team_id = current_user["team_id"]
    pdf_bytes = MeetingService.export_meeting_pdf(team_id, meeting_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=meetmind_{meeting_id}_summary.pdf"}
    )

@router.post("/complete", response_model=MeetingResponse, status_code=201)
def complete_meeting(
    req: MeetingCompleteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Directly persists completed meeting summary and delivers Zapier webhook.
    """
    team_id = current_user["team_id"]
    return MeetingService.complete_meeting(team_id=team_id, current_user=current_user, req=req)

@router.get("", response_model=MeetingListResponse)
def list_meetings(current_user: dict = Depends(get_current_user)):
    """List archived meetings and transcripts for the authenticated user's team."""
    team_id = current_user["team_id"]
    meetings = MeetingService.list_meetings(team_id)
    return MeetingListResponse(meetings=meetings, total=len(meetings))

@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve full meeting analysis and deliverables."""
    team_id = current_user["team_id"]
    return MeetingService.get_meeting(team_id, meeting_id)
