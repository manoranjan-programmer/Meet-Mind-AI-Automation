import os
import uuid
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END

from app.config import settings
from app.agents.transcription_agent import TranscriptionAgent
from app.agents.diarization_agent import DiarizationAgent
from app.agents.meeting_analyst_agent import MeetingAnalystAgent
from app.agents.task_extraction_agent import TaskExtractionAgent
from app.agents.task_assignment_agent import TaskAssignmentAgent
from app.agents.review_validation_agent import ReviewValidationAgent
from app.agents.automation_agent import AutomationAgent
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.workflow")


def _log_stage(
    event_name: str,
    meeting_id: str,
    job_id: str,
    stage: str,
    status: str,
    duration: float = 0.0,
    error: Optional[str] = None,
):
    logger.info(
        f"{event_name} | meeting_id={meeting_id} job_id={job_id} "
        f"stage={stage} status={status} duration={duration}s"
        + (f" error={error}" if error else "")
    )


class MeetingState(TypedDict, total=False):
    meeting_id: str
    processing_job_id: str
    team_id: str
    meeting_title: str
    audio_path: str
    force_retranscribe: bool
    host_name: Optional[str]
    selected_participant_ids: Optional[List[str]]
    participants: List[Any]
    team_lead_email: str
    duration: str
    status: str
    current_stage: str
    error: Optional[str]
    audio_diagnostics: Dict[str, Any]
    transcription_status: str
    vad_status: str
    vad_message: Optional[str]
    transcript_text: str
    transcript_segments: List[Dict[str, Any]]
    diarized_segments: List[Dict[str, Any]]
    speaker_catalog: List[Dict[str, Any]]
    summary: str
    discussion_topics: List[str]
    key_decisions: List[str]
    unresolved_questions: List[str]
    important_outcomes: List[str]
    extracted_tasks: List[Dict[str, Any]]
    responsible_tasks: List[Dict[str, Any]]
    assigned_tasks: List[Dict[str, Any]]
    prioritized_tasks: List[Dict[str, Any]]
    validated_tasks: List[Dict[str, Any]]
    agent_executions: List[Dict[str, Any]]
    automation_dispatched: bool


def _append_execution(state: MeetingState, agent_id: int, name: str, status: str, duration: float, error: Optional[str] = None) -> List[Dict[str, Any]]:
    executions = list(state.get("agent_executions", []))
    record: Dict[str, Any] = {
        "agent_id": agent_id,
        "name": name,
        "status": status,
        "duration": duration,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if error:
        record["error"] = error
    executions.append(record)
    return executions


# ----------------- LANGGRAPH NODES ----------------- #

def transcript_understanding_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 1: Transcript Understanding Agent (Whisper transcription & timestamp preservation)"""
    t0 = time.time()
    mid = state.get("meeting_id", "")
    job_id = state.get("processing_job_id", "")
    audio_path = state.get("audio_path", "")
    force_retranscribe = bool(state.get("force_retranscribe", False))
    existing_text = (state.get("transcript_text") or "").strip()
    existing_segments = state.get("transcript_segments", [])

    _log_stage("TRANSCRIPTION_STARTED", mid, job_id, "transcribing", "started")

    if not force_retranscribe and existing_text and existing_segments and any((s.get("text") or "").strip() for s in existing_segments):
        logger.info(f"Reusing saved transcript ({len(existing_segments)} segments) for meeting {mid}")
        res = {
            "status": "success",
            "speech_detected": True,
            "vad_status": "speech_detected",
            "full_text": existing_text,
            "segments": existing_segments,
            "audio_diagnostics": state.get("audio_diagnostics", {}),
        }
    elif audio_path and os.path.exists(audio_path):
        res = TranscriptionAgent.execute(audio_path, audio_diagnostics=state.get("audio_diagnostics"))
    else:
        res = {
            "status": "error",
            "error": f"No audio file found at '{audio_path}' and no saved transcript segments for meeting {mid}.",
            "speech_detected": False,
            "vad_status": "no_audio",
            "full_text": "",
            "segments": [],
        }

    duration = round(time.time() - t0, 3)
    t_status = res.get("status", "error")
    t_error = res.get("error")
    _log_stage("TRANSCRIPTION_COMPLETED", mid, job_id, "transcribing", t_status, duration, t_error)

    return {
        "transcription_status": t_status,
        "vad_status": res.get("vad_status", ""),
        "vad_message": res.get("vad_message"),
        "audio_diagnostics": res.get("audio_diagnostics") or state.get("audio_diagnostics", {}),
        "transcript_text": res.get("full_text", ""),
        "transcript_segments": res.get("segments", []),
        "error": t_error if t_status == "error" else state.get("error"),
        "current_stage": "transcribing",
        "agent_executions": _append_execution(state, 1, "Transcript Understanding Agent", t_status, duration, t_error),
    }


def _route_after_transcription(state: MeetingState) -> str:
    t_status = state.get("transcription_status", "")
    text = (state.get("transcript_text") or "").strip()
    if t_status == "error":
        return "persist"
    if t_status == "no_speech" or not text:
        return "persist"
    return "speaker_analysis"


def speaker_analysis_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 2: Speaker Analysis Agent (Diarization & participant mapping)"""
    t0 = time.time()
    mid = state.get("meeting_id", "")
    job_id = state.get("processing_job_id", "")
    segments = state.get("transcript_segments", [])
    participants = state.get("participants", [])
    host_name = state.get("host_name")

    res = DiarizationAgent.execute(segments=segments, participants=participants, host_name=host_name)
    duration = round(time.time() - t0, 3)
    d_status = res.get("status", "success")
    _log_stage("DIARIZATION_COMPLETED", mid, job_id, "identifying_speakers", d_status, duration, res.get("error"))

    return {
        "diarized_segments": res.get("diarized_segments", []),
        "speaker_catalog": res.get("speaker_catalog", []),
        "current_stage": "identifying_speakers",
        "agent_executions": _append_execution(state, 2, "Speaker Analysis Agent", d_status, duration, res.get("error")),
    }


def discussion_analysis_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 3 & 4: Meeting Summary & Discussion Analysis Agent"""
    t0 = time.time()
    mid = state.get("meeting_id", "")
    job_id = state.get("processing_job_id", "")
    transcript_text = state.get("transcript_text", "")
    segments = state.get("diarized_segments", []) or state.get("transcript_segments", [])
    title = state.get("meeting_title", "Team Meeting")

    res = MeetingAnalystAgent.execute(
        transcript_text=transcript_text,
        diarized_segments=segments,
        meeting_title=title,
    )
    duration = round(time.time() - t0, 3)
    a_status = res.get("status", "success")
    a_error = res.get("error")
    _log_stage("MEETING_ANALYSIS_COMPLETED", mid, job_id, "analyzing_meeting", a_status, duration, a_error)

    return {
        "summary": res.get("meeting_summary", ""),
        "discussion_topics": res.get("discussion_topics", []),
        "key_decisions": res.get("key_decisions", []),
        "unresolved_questions": res.get("unresolved_questions", []),
        "important_outcomes": res.get("important_outcomes", []),
        "error": a_error if a_status == "error" else state.get("error"),
        "current_stage": "analyzing_meeting",
        "agent_executions": _append_execution(state, 3, "Meeting Summary & Discussion Agent", a_status, duration, a_error),
    }


def decision_extraction_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 5: Decision Extraction Agent (Validates & structures confirmed decisions from state)"""
    t0 = time.time()
    decisions = [d.strip() for d in (state.get("key_decisions") or []) if isinstance(d, str) and d.strip()]
    duration = round(time.time() - t0, 3)
    return {
        "key_decisions": decisions,
        "agent_executions": _append_execution(state, 4, "Decision Extraction Agent", "success", duration),
    }


def action_item_extraction_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 6: Action Item Extraction Agent"""
    t0 = time.time()
    mid = state.get("meeting_id", "")
    job_id = state.get("processing_job_id", "")
    transcript_text = state.get("transcript_text", "")
    segments = state.get("diarized_segments", []) or state.get("transcript_segments", [])

    res = TaskExtractionAgent.execute(
        transcript_text=transcript_text,
        diarized_segments=segments,
    )
    duration = round(time.time() - t0, 3)
    e_status = res.get("status", "success")
    e_error = res.get("error")
    _log_stage("TASK_EXTRACTION_COMPLETED", mid, job_id, "extracting_tasks", e_status, duration, e_error)

    return {
        "extracted_tasks": res.get("extracted_tasks", []),
        "error": e_error if e_status == "error" else state.get("error"),
        "current_stage": "extracting_tasks",
        "agent_executions": _append_execution(state, 5, "Action Item Extraction Agent", e_status, duration, e_error),
    }


def responsibility_identification_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 7: Responsibility Identification Agent"""
    t0 = time.time()
    tasks = state.get("extracted_tasks", [])
    responsible_tasks = []

    for t in tasks:
        is_committed = bool(t.get("is_explicit_commitment", False))
        acceptor = t.get("explicit_owner")
        evidence = t.get("evidence", "")

        responsible_tasks.append({
            **t,
            "has_responsible_acceptor": is_committed and bool(acceptor),
            "acceptor": acceptor,
            "evidence": evidence,
        })

    duration = round(time.time() - t0, 3)
    return {
        "responsible_tasks": responsible_tasks,
        "agent_executions": _append_execution(state, 6, "Responsibility Identification Agent", "success", duration),
    }


def team_skill_matching_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 8: Team Skill Matching Agent"""
    t0 = time.time()
    team_id = state.get("team_id", "")
    tasks = state.get("responsible_tasks", []) or state.get("extracted_tasks", [])
    selected_p_ids = state.get("selected_participant_ids", [])
    participants = state.get("participants", [])

    res = TaskAssignmentAgent.execute(
        team_id=team_id,
        extracted_tasks=tasks,
        selected_participant_ids=selected_p_ids,
        participants=participants,
        speaker_catalog=state.get("speaker_catalog", []),
    )
    duration = round(time.time() - t0, 3)

    return {
        "assigned_tasks": res.get("assigned_tasks", []),
        "agent_executions": _append_execution(state, 7, "Team Skill Matching Agent", res.get("status", "success"), duration),
    }


def priority_analysis_node(state: MeetingState) -> Dict[str, Any]:
    """Priority refinement based on explicit urgency cues."""
    t0 = time.time()
    assigned = state.get("assigned_tasks", [])
    prioritized = []

    for t in assigned:
        evidence_lower = (t.get("evidence") or "").lower()
        title_lower = (t.get("title") or "").lower()

        if any(w in evidence_lower or w in title_lower for w in ["critical", "asap", "emergency", "blocker", "p0"]):
            prio = "Critical"
        elif any(w in evidence_lower or w in title_lower for w in ["urgent", "important", "high priority", "by today", "by tomorrow"]):
            prio = "High"
        elif any(w in evidence_lower or w in title_lower for w in ["low priority", "optional", "nice to have", "backlog"]):
            prio = "Low"
        else:
            prio = t.get("priority") or "Medium"

        prioritized.append({**t, "priority": prio})

    duration = round(time.time() - t0, 3)
    return {
        "prioritized_tasks": prioritized,
        "agent_executions": _append_execution(state, 8, "Priority Analysis Agent", "success", duration),
    }


def final_validation_node(state: MeetingState) -> Dict[str, Any]:
    """Agent 9: Final Validation Agent"""
    t0 = time.time()
    prioritized = state.get("prioritized_tasks", []) or state.get("assigned_tasks", [])
    meeting_id = state.get("meeting_id", "")
    selected_p_ids = state.get("selected_participant_ids", [])
    team_id = state.get("team_id", "")

    res = ReviewValidationAgent.execute(
        assigned_tasks=prioritized,
        meeting_id=meeting_id,
        selected_participant_ids=selected_p_ids,
        team_id=team_id,
    )
    duration = round(time.time() - t0, 3)

    return {
        "validated_tasks": res.get("validated_tasks", []),
        "current_stage": "ready_for_review",
        "agent_executions": _append_execution(state, 9, "Final Validation Agent", res.get("status", "success"), duration),
    }


def persist_node(state: MeetingState) -> Dict[str, Any]:
    """MongoDB Persistence: Meetings, Segments, Tasks (preventing duplicates on retry)"""
    from app.services.task_service import TaskService

    meeting_id = state.get("meeting_id", "")
    team_id = state.get("team_id", "")
    meetings_col = get_col("meetings")
    tasks_col = get_col("tasks")
    segments_col = get_col("transcript_segments")

    now = datetime.utcnow()
    t_status = state.get("transcription_status", "success")
    err_msg = state.get("error")

    if t_status == "error" or err_msg:
        final_status = "failed"
    elif t_status == "no_speech":
        final_status = "No Speech"
    else:
        final_status = "Completed"

    meeting_doc = {
        "meeting_id": meeting_id,
        "team_id": team_id,
        "processing_job_id": state.get("processing_job_id"),
        "meeting_title": state.get("meeting_title"),
        "title": state.get("meeting_title"),
        "duration": state.get("duration", "00:00"),
        "selected_participant_ids": state.get("selected_participant_ids", []),
        "participants": state.get("participants", []),
        "meeting_summary": state.get("summary", ""),
        "summary": state.get("summary", ""),
        "discussion_topics": state.get("discussion_topics", []),
        "key_decisions": state.get("key_decisions", []),
        "unresolved_questions": state.get("unresolved_questions", []),
        "important_outcomes": state.get("important_outcomes", []),
        "extracted_tasks": state.get("validated_tasks", []),
        "action_items": [t.get("title") for t in state.get("validated_tasks", [])],
        "team_lead_email": state.get("team_lead_email", ""),
        "status": final_status,
        "current_stage": state.get("current_stage", "ready_for_review"),
        "error_message": err_msg,
        "transcription_status": t_status,
        "vad_status": state.get("vad_status", ""),
        "vad_message": state.get("vad_message"),
        "transcript_text": state.get("transcript_text", ""),
        "audio_path": state.get("audio_path"),
        "audio_diagnostics": state.get("audio_diagnostics", {}),
        "speaker_catalog": state.get("speaker_catalog", []),
        "agent_executions": state.get("agent_executions", []),
        "completed_at": now if final_status == "Completed" else None,
        "updated_at": now,
    }
    meetings_col.update_one({"meeting_id": meeting_id}, {"$set": meeting_doc}, upsert=True)

    # Persist transcript segments cleanly (only overwrite if we have new segments or retranscribed)
    segs_to_save = state.get("diarized_segments") or state.get("transcript_segments") or []
    if segs_to_save:
        segments_col.delete_many({"meeting_id": meeting_id})
        for seg in segs_to_save:
            seg_doc = {
                **seg,
                "meeting_id": meeting_id,
                "team_id": team_id,
                "created_at": now,
            }
            segments_col.insert_one(seg_doc)

    # Prevent duplicate or stale tasks when AI analysis is retried:
    # Remove previous unapproved AI tasks for this meeting before inserting new ones.
    if final_status == "Completed":
        tasks_col.delete_many({
            "team_id": team_id,
            "meeting_id": meeting_id,
            "approval_status": "Awaiting Approval",
        })

    for t in state.get("validated_tasks", []):
        t_id = t.get("task_id")
        if not t_id:
            t_id = TaskService._generate_task_id(team_id)
            t["task_id"] = t_id

        # Skip overwriting if this task_id was already Approved/Rejected by human
        existing_task = tasks_col.find_one({"team_id": team_id, "task_id": t_id})
        if existing_task and existing_task.get("approval_status") in ("Approved", "Rejected"):
            continue

        task_doc = {
            "task_id": t_id,
            "team_id": team_id,
            "meeting_id": meeting_id,
            "meeting_title": state.get("meeting_title"),
            "title": t.get("title"),
            "description": t.get("description", ""),
            "related_discussion": t.get("related_discussion", ""),
            "requester": t.get("requester"),
            "priority": t.get("priority", "Medium"),
            "deadline": t.get("deadline"),
            "required_skills": t.get("required_skills", []),
            "evidence": t.get("evidence", ""),
            "timestamp": t.get("timestamp"),
            "confidence_score": t.get("confidence_score", t.get("confidence", 0.0)),
            "assigned_member_id": t.get("assigned_member_id"),
            "assigned_member_name": t.get("assigned_member_name", "Unassigned"),
            "assigned_member_role": t.get("assigned_member_role", "Unassigned"),
            "assigned_member_email": t.get("assigned_member_email", ""),
            "assignment_reason": t.get("assignment_reason", ""),
            "status": "To Do",
            "approval_status": "Awaiting Approval",
            "validation_flags": t.get("validation_flags", []),
            "created_at": now,
            "updated_at": now,
        }
        tasks_col.update_one(
            {"team_id": team_id, "task_id": t_id},
            {"$set": task_doc},
            upsert=True,
        )

    return {"status": final_status}


async def automation_node(state: MeetingState) -> Dict[str, Any]:
    """Automation Node: Dispatches meeting completed event ONLY if enabled and successful"""
    if state.get("status") != "Completed" or not getattr(settings, "ENABLE_AUTOMATION_DISPATCH", False):
        logger.info("Automation dispatch skipped (disabled or meeting not Completed).")
        return {"automation_dispatched": False}

    meeting_doc = {
        "meeting_id": state.get("meeting_id"),
        "team_id": state.get("team_id"),
        "meeting_title": state.get("meeting_title"),
        "duration": state.get("duration", "00:00"),
        "participants": state.get("participants", []),
        "meeting_summary": state.get("summary", ""),
        "key_decisions": state.get("key_decisions", []),
        "action_items": [t.get("title") for t in state.get("validated_tasks", [])],
        "team_lead_email": state.get("team_lead_email", ""),
    }

    res = await AutomationAgent.dispatch_meeting_completed(meeting_doc)
    logger.info(f"Automation node completed with delivery status: {res.get('delivery_status')}")
    return {"automation_dispatched": True}


# ----------------- LANGGRAPH BUILDER ----------------- #

def build_meeting_graph():
    workflow = StateGraph(MeetingState)

    workflow.add_node("transcript_understanding", transcript_understanding_node)
    workflow.add_node("speaker_analysis", speaker_analysis_node)
    workflow.add_node("discussion_analysis", discussion_analysis_node)
    workflow.add_node("decision_extraction", decision_extraction_node)
    workflow.add_node("action_item_extraction", action_item_extraction_node)
    workflow.add_node("responsibility_identification", responsibility_identification_node)
    workflow.add_node("team_skill_matching", team_skill_matching_node)
    workflow.add_node("priority_analysis", priority_analysis_node)
    workflow.add_node("final_validation", final_validation_node)
    workflow.add_node("persist", persist_node)
    workflow.add_node("automate", automation_node)

    workflow.set_entry_point("transcript_understanding")
    workflow.add_conditional_edges(
        "transcript_understanding",
        _route_after_transcription,
        {
            "speaker_analysis": "speaker_analysis",
            "persist": "persist",
        },
    )
    workflow.add_edge("speaker_analysis", "discussion_analysis")
    workflow.add_edge("discussion_analysis", "decision_extraction")
    workflow.add_edge("decision_extraction", "action_item_extraction")
    workflow.add_edge("action_item_extraction", "responsibility_identification")
    workflow.add_edge("responsibility_identification", "team_skill_matching")
    workflow.add_edge("team_skill_matching", "priority_analysis")
    workflow.add_edge("priority_analysis", "final_validation")
    workflow.add_edge("final_validation", "persist")
    workflow.add_edge("persist", "automate")
    workflow.add_edge("automate", END)

    return workflow.compile()


meeting_pipeline_graph = build_meeting_graph()


async def run_meeting_workflow(initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the full LangGraph meeting intelligence pipeline."""
    mid = initial_state.get("meeting_id", "")
    job_id = initial_state.get("processing_job_id") or f"JOB-{uuid.uuid4().hex[:8]}"
    initial_state["processing_job_id"] = job_id

    t0 = time.time()
    _log_stage("LANGGRAPH_STARTED", mid, job_id, "langgraph_pipeline", "started")
    final_state = await meeting_pipeline_graph.ainvoke(initial_state)
    duration = round(time.time() - t0, 3)
    _log_stage(
        "LANGGRAPH_COMPLETED",
        mid,
        job_id,
        final_state.get("current_stage", "ready_for_review"),
        final_state.get("status", "Completed"),
        duration,
        final_state.get("error"),
    )
    return final_state
