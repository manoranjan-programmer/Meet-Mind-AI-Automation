import re
import time
import logging
from typing import Dict, Any, List, Optional
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.agent6")

class TaskAssignmentAgent:
    """
    Agent 6: Intelligent Speaker-Based Task Assignment Agent
    Assignment Rules:
      Priority 1: Explicit verbal acceptance ('I will do this', 'I can handle this') -> Assign to that participant.
      Priority 2: Directed request + verbal agreement ('Arun, can you build X?' -> 'Sure, I will') -> Assign to agreed participant.
      Priority 3: Team skill matching against MongoDB member_profiles ONLY if there is actual technical skill overlap.
      Priority 4: If no explicit assignee and no verified skill overlap -> Mark as UNASSIGNED.

    Special Rules:
      - Never assigns tasks randomly.
      - Never assigns every task to the host by default.
      - Never assigns a task just because a person's name was mentioned in discussion.
      - In a single-member workspace, tasks are assigned to the host ONLY if the host explicitly committed or verified skills match; otherwise UNASSIGNED.
    """
    AGENT_ID = 6
    NAME = "Intelligent Task Assignment Agent"

    @staticmethod
    def execute(
        team_id: str,
        extracted_tasks: List[Dict[str, Any]],
        selected_participant_ids: Optional[List[str]] = None,
        participants: Optional[List[Any]] = None,
        speaker_catalog: Optional[Any] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{TaskAssignmentAgent.NAME}] Matching tasks with team {team_id} member profiles")

        member_col = get_col("member_profiles")
        
        # 1. Fetch all active members in this workspace
        all_team_members = list(member_col.find({"team_id": team_id, "account_status": "active"}))

        # Merge directly supplied participant objects (e.g. from session state or unit tests)
        if participants:
            for p in participants:
                if isinstance(p, dict) and p.get("name") and not any(m.get("member_id") == p.get("member_id") or m.get("name") == p.get("name") for m in all_team_members):
                    all_team_members.append(p)

        # Build speaker identity lookup from catalog
        speaker_map: Dict[str, str] = {}
        if isinstance(speaker_catalog, dict):
            for spk_id, spk_info in speaker_catalog.items():
                if isinstance(spk_info, dict):
                    name = spk_info.get("speaker_label") or spk_info.get("suggested_name")
                    if name and name.lower() not in ["unknown speaker", "unknown"]:
                        speaker_map[spk_id.lower()] = name
        elif isinstance(speaker_catalog, list):
            for spk_info in speaker_catalog:
                if isinstance(spk_info, dict):
                    spk_id = spk_info.get("speaker_id", "")
                    name = spk_info.get("speaker_label") or spk_info.get("suggested_name")
                    if spk_id and name and name.lower() not in ["unknown speaker", "unknown"]:
                        speaker_map[spk_id.lower()] = name

        # 2. Determine attending members
        attending_members: List[Dict[str, Any]] = []
        if selected_participant_ids:
            attending_members = [m for m in all_team_members if m.get("member_id") in selected_participant_ids]
        
        if not attending_members and participants:
            for p in participants:
                if isinstance(p, dict):
                    attending_members.append(p)
                elif isinstance(p, str):
                    matched = next((m for m in all_team_members if m.get("name", "").lower() == p.lower() or m.get("email", "").lower() == p.lower()), None)
                    if matched:
                        attending_members.append(matched)

        if not attending_members:
            attending_members = all_team_members

        # If participants were explicitly selected for the meeting, only assign to attending members
        if selected_participant_ids and len(attending_members) > 0:
            eligible_candidates = attending_members
        else:
            eligible_candidates = all_team_members

        # In a single-member session
        is_single_member_session = len(attending_members) == 1
        sole_attendee = attending_members[0] if is_single_member_session else None

        assigned_tasks: List[Dict[str, Any]] = []

        for task in extracted_tasks:
            raw_explicit_owner = task.get("explicit_owner")
            is_explicit_commitment = task.get("is_explicit_commitment", False)
            required_skills = [s.strip().lower() for s in task.get("required_skills", []) if s.strip()]
            evidence = task.get("evidence", "")

            # Resolve speaker alias from catalog if applicable (e.g. 'Speaker 1' -> 'Mano ranjan G')
            explicit_owner = raw_explicit_owner
            if raw_explicit_owner and raw_explicit_owner.lower() in speaker_map:
                explicit_owner = speaker_map[raw_explicit_owner.lower()]

            matched_member: Optional[Dict[str, Any]] = None
            assignment_reason = ""
            confidence_score = 0.0

            is_generic_speaker = (
                not explicit_owner 
                or explicit_owner.lower() in ["unknown speaker", "unknown", "speaker"] 
                or bool(re.match(r"^Speaker\s*\d+$", explicit_owner.strip(), re.IGNORECASE))
            )

            # Priority 1: Explicit verbal acceptance ('I will...', 'I can handle...')
            if explicit_owner and not is_generic_speaker:
                owner_clean = explicit_owner.strip().lower()

                for m in eligible_candidates:
                    m_name = m.get("name", "").strip().lower()
                    m_email = m.get("email", "").strip().lower()
                    first_name = m_name.split()[0] if m_name else ""

                    if (owner_clean == m_name 
                        or owner_clean in m_name 
                        or (first_name and owner_clean == first_name)
                        or owner_clean in m_email):
                        matched_member = m
                        confidence_score = 0.98
                        assignment_reason = f"Explicitly accepted and committed by attendee {m.get('name')} in meeting dialogue."
                        break

            # Special single-member rule: Assign to sole attendee ONLY if they explicitly committed
            if not matched_member and is_single_member_session and sole_attendee:
                has_commitment = bool(re.search(r"\b(?:I will|I'll|I can handle|I am going to|I'll do|I can do|I will develop|I'll build|I will build)\b", evidence, re.IGNORECASE))
                if has_commitment or (explicit_owner and explicit_owner.lower() in ["speaker 1", sole_attendee.get("name", "").lower()]):
                    matched_member = sole_attendee
                    confidence_score = 0.95
                    assignment_reason = f"Single workspace attendee {sole_attendee.get('name')} explicitly committed to this deliverable."

            # Priority 2: Directed assignment with verbal agreement
            if not matched_member and not is_single_member_session:
                for m in eligible_candidates:
                    m_name = m.get("name", "").strip()
                    if m_name and len(m_name) >= 2:
                        first_name = m_name.split()[0]
                        pattern_directed = rf"\b(?:{re.escape(m_name)}|{re.escape(first_name)})\b.*?\b(?:will|can|agreed|taking|responsible|handle)\b"
                        if re.search(pattern_directed, evidence, re.IGNORECASE):
                            matched_member = m
                            confidence_score = 0.90
                            assignment_reason = f"Directed assignment to {m.get('name')} confirmed during conversation."
                            break

            # Priority 3: Skill matching against MongoDB member_profiles (ONLY with verified overlap)
            if not matched_member and required_skills and eligible_candidates:
                best_overlap_count = 0
                best_candidate = None
                
                for m in eligible_candidates:
                    member_skills = [s.strip().lower() for s in (m.get("technical_skills") or m.get("skills") or [])]
                    overlap = [rs for rs in required_skills if any(rs in ms or ms in rs for ms in member_skills)]
                    if len(overlap) > best_overlap_count:
                        best_overlap_count = len(overlap)
                        best_candidate = (m, overlap)

                if best_candidate and best_overlap_count > 0:
                    cand_member, matched_skills_list = best_candidate
                    if not is_single_member_session or best_overlap_count >= 1:
                        matched_member = cand_member
                        confidence_score = 0.78
                        assignment_reason = f"Suggested based on verified profile skill match: {', '.join(matched_skills_list[:3])}."

            # Priority 4: UNASSIGNED (Never randomly assign, never assign to host by default)
            if matched_member:
                assigned_name = matched_member.get("name")
                assigned_id = matched_member.get("member_id")
                assigned_role = matched_member.get("role", "Member")
                assigned_email = matched_member.get("email", "")
            else:
                assigned_name = "Unassigned"
                assigned_id = None
                assigned_role = "Unassigned"
                assigned_email = ""
                confidence_score = 0.0
                assignment_reason = "No explicit commitment or matching skill profile detected in workspace. Marked as Unassigned for team leader review."

            assigned_tasks.append({
                "title": task.get("title"),
                "description": task.get("description", ""),
                "related_discussion": task.get("related_discussion", ""),
                "requester": task.get("requester"),
                "priority": task.get("priority", "Medium"),
                "deadline": task.get("deadline"),  # Never invent deadline
                "required_skills": task.get("required_skills", []),
                "evidence": task.get("evidence", ""),
                "timestamp": task.get("timestamp"),
                "confidence": task.get("confidence", confidence_score),
                "assigned_member_id": assigned_id,
                "assigned_member_name": assigned_name,
                "assigned_member_role": assigned_role,
                "assigned_member_email": assigned_email,
                "confidence_score": confidence_score,
                "assignment_reason": assignment_reason
            })

        duration_sec = round(time.time() - start_time, 3)
        logger.info(f"[{TaskAssignmentAgent.NAME}] Assigned {len(assigned_tasks)} tasks in {duration_sec}s")

        return {
            "status": "success",
            "assigned_tasks": assigned_tasks,
            "execution_duration": duration_sec
        }
