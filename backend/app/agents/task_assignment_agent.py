import re
import time
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.agent6")

# Bidirectional skill-domain equivalences so broad AI-extracted skills
# (e.g. "Frontend Development", "AI Agent Development") match concrete member skills
# (e.g. "React", "JavaScript", "Python", "LangGraph").
SKILL_DOMAINS: Dict[str, Set[str]] = {
    "frontend": {
        "frontend", "front-end", "frontend development", "front-end development",
        "frontend developer", "ui development", "web development", "web",
        "react", "reactjs", "react.js", "next.js", "nextjs", "vue", "vuejs",
        "angular", "svelte", "javascript", "js", "typescript", "ts",
        "html", "html5", "css", "css3", "tailwind", "tailwindcss", "vite", "redux",
    },
    "backend": {
        "backend", "back-end", "backend development", "back-end development",
        "backend developer", "api", "rest", "rest api", "graphql", "microservices",
        "python", "fastapi", "django", "flask", "node", "nodejs", "node.js",
        "express", "java", "spring", "spring boot", "go", "golang", "c#", ".net",
    },
    "database": {
        "database", "db", "mongodb", "mongo", "mongodb atlas", "mongoose",
        "sql", "postgresql", "postgres", "mysql", "sqlite", "redis", "dynamodb",
    },
    "ai_agents": {
        "ai", "ai agent", "ai agents", "ai agent development", "agentic ai",
        "artificial intelligence", "machine learning", "ml", "deep learning",
        "llm", "llms", "langgraph", "langchain", "groq", "openai", "gemini",
        "nlp", "whisper", "speech recognition", "rag", "prompt engineering", "python",
    },
    "design": {
        "design", "ui", "ux", "ui/ux", "ui design", "ux design", "ui/ux designer",
        "figma", "sketch", "adobe xd", "wireframe", "wireframing", "prototyping",
    },
    "testing": {
        "testing", "qa", "quality assurance", "tester", "qa engineer",
        "automated testing", "unit testing", "integration testing", "e2e",
        "pytest", "selenium", "playwright", "cypress", "jest",
    },
    "devops": {
        "devops", "deployment", "ci/cd", "docker", "kubernetes", "aws", "ec2",
        "render", "vercel", "git", "github", "linux", "nginx",
    },
    "mobile": {
        "mobile", "mobile development", "react native", "flutter", "android",
        "ios", "swift", "kotlin",
    },
}


def _expand_domains(skill_text: str) -> Set[str]:
    norm = skill_text.strip().lower()
    if not norm:
        return set()
    matched_domains: Set[str] = set()
    for domain, keywords in SKILL_DOMAINS.items():
        if norm in keywords or any(kw in norm or norm in kw for kw in keywords if len(kw) >= 3):
            matched_domains.add(domain)
    return matched_domains


class TaskAssignmentAgent:
    """
    Agent 6: Intelligent Speaker-Based & Weighted Skill Task Assignment Agent
    Assignment Rules:
      Priority 1: Explicit verbal acceptance ('I will do this', 'I can handle this') -> Assign to that participant.
      Priority 2: Directed request + verbal agreement -> Assign to agreed participant.
      Priority 3: Weighted skill, role, availability & workload matching against MongoDB member_profiles.
      Priority 4: If no eligible member matches -> Mark as UNASSIGNED with confidence 0.0.
    """
    AGENT_ID = 6
    NAME = "Intelligent Task Assignment Agent"

    @staticmethod
    def _score_candidate(
        member: Dict[str, Any],
        required_skills: List[str],
        task_title: str = "",
        task_desc: str = "",
    ) -> Tuple[float, float, List[str]]:
        """
        Returns (total_score, skill_ratio, matched_evidence_list) for a candidate member.
        Returns (0.0, 0.0, []) if there is zero skill or role relevance.
        """
        raw_skills = member.get("technical_skills") or member.get("skills") or []
        member_skills = [str(s).strip().lower() for s in raw_skills if str(s).strip()]
        member_role = str(member.get("role") or "").strip().lower()

        member_domains: Set[str] = set()
        for ms in member_skills:
            member_domains |= _expand_domains(ms)
        role_domains = _expand_domains(member_role) if member_role else set()

        effective_reqs = list(required_skills)
        if not effective_reqs:
            # Infer domain cues from task title/description if required_skills was empty
            inferred = _expand_domains(f"{task_title} {task_desc}")
            effective_reqs = list(inferred)

        if not effective_reqs:
            return 0.0, 0.0, []

        skill_points = 0.0
        matched_labels: List[str] = []

        for req in effective_reqs:
            req_l = req.strip().lower()
            if not req_l:
                continue

            # 1. Direct or substring match against member's explicit skills
            direct_hit = next((ms for ms in member_skills if req_l == ms or req_l in ms or ms in req_l), None)
            if direct_hit:
                skill_points += 1.0
                matched_labels.append(f"{req} ({direct_hit})")
                continue

            # 2. Semantic domain equivalence match against member's skills
            req_domains = _expand_domains(req_l)
            domain_overlap = req_domains & member_domains
            if domain_overlap:
                skill_points += 0.85
                matched_labels.append(f"{req} (~{', '.join(sorted(domain_overlap))})")
                continue

            # 3. Role-level match (e.g. Frontend Developer role for Frontend Development)
            role_overlap = req_domains & role_domains
            if role_overlap or (member_role and any(tok in member_role for tok in req_l.split() if len(tok) >= 4)):
                skill_points += 0.65
                matched_labels.append(f"{req} (role: {member.get('role')})")

        if skill_points <= 0.0:
            return 0.0, 0.0, []

        skill_ratio = min(1.0, skill_points / max(1, len(effective_reqs)))
        skill_score = skill_ratio * 0.70

        availability = str(member.get("availability") or "Available").strip().lower()
        if availability == "available":
            avail_score = 0.15
        elif availability == "busy":
            avail_score = 0.05
        else:
            avail_score = 0.0

        current_load = len(member.get("assigned_tasks") or [])
        max_load = max(1, int(member.get("maximum_workload") or 5))
        capacity_ratio = max(0.0, (max_load - current_load) / max_load)
        workload_score = capacity_ratio * 0.15

        total_score = round(min(0.95, skill_score + avail_score + workload_score), 2)
        return total_score, round(skill_ratio, 2), matched_labels

    @staticmethod
    def execute(
        team_id: str,
        extracted_tasks: List[Dict[str, Any]],
        selected_participant_ids: Optional[List[str]] = None,
        participants: Optional[List[Any]] = None,
        speaker_catalog: Optional[Any] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{TaskAssignmentAgent.NAME}] Matching tasks with team {team_id} member profiles")

        member_col = get_col("member_profiles")
        all_team_members = list(member_col.find({"team_id": team_id, "account_status": "active"}))

        if participants:
            for p in participants:
                if isinstance(p, dict) and p.get("name") and not any(
                    m.get("member_id") == p.get("member_id") or m.get("name") == p.get("name")
                    for m in all_team_members
                ):
                    all_team_members.append(p)

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

        attending_members: List[Dict[str, Any]] = []
        if selected_participant_ids:
            attending_members = [m for m in all_team_members if m.get("member_id") in selected_participant_ids]

        if not attending_members and participants:
            for p in participants:
                if isinstance(p, dict):
                    attending_members.append(p)
                elif isinstance(p, str):
                    matched = next(
                        (m for m in all_team_members if m.get("name", "").lower() == p.lower() or m.get("email", "").lower() == p.lower()),
                        None,
                    )
                    if matched:
                        attending_members.append(matched)

        if not attending_members:
            attending_members = all_team_members

        # Prefer attending members for verbal commitment; allow full active team pool for skill matching
        eligible_candidates = attending_members if (selected_participant_ids and len(attending_members) > 0) else all_team_members
        skill_pool = all_team_members if all_team_members else eligible_candidates

        is_single_member_session = len(attending_members) == 1
        sole_attendee = attending_members[0] if is_single_member_session else None

        assigned_tasks: List[Dict[str, Any]] = []

        for task in extracted_tasks:
            raw_explicit_owner = task.get("explicit_owner")
            required_skills = [s.strip().lower() for s in (task.get("required_skills") or []) if str(s).strip()]
            evidence = task.get("evidence", "")

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

            # Priority 1: Explicit verbal acceptance
            if explicit_owner and not is_generic_speaker:
                owner_clean = explicit_owner.strip().lower()
                for m in eligible_candidates:
                    m_name = m.get("name", "").strip().lower()
                    m_email = m.get("email", "").strip().lower()
                    first_name = m_name.split()[0] if m_name else ""
                    if (
                        owner_clean == m_name
                        or owner_clean in m_name
                        or (first_name and owner_clean == first_name)
                        or owner_clean in m_email
                    ):
                        matched_member = m
                        confidence_score = 0.98
                        assignment_reason = f"Explicitly accepted and committed by attendee {m.get('name')} in meeting dialogue."
                        break

            # Single-member verbal commitment rule
            if not matched_member and is_single_member_session and sole_attendee:
                has_commitment = bool(
                    re.search(
                        r"\b(?:I will|I'll|I can handle|I am going to|I'll do|I can do|I will develop|I'll build|I will build)\b",
                        evidence,
                        re.IGNORECASE,
                    )
                )
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

            # Priority 3: Weighted Semantic Skill, Role, Availability & Workload Matching
            if not matched_member and skill_pool:
                scored_candidates = []
                for m in skill_pool:
                    if str(m.get("availability") or "").strip().lower() in ("unavailable", "offline"):
                        continue
                    total_score, skill_ratio, matched_labels = TaskAssignmentAgent._score_candidate(
                        member=m,
                        required_skills=required_skills,
                        task_title=task.get("title") or "",
                        task_desc=task.get("description") or "",
                    )
                    if total_score > 0.0 and skill_ratio > 0.0:
                        current_load = len(m.get("assigned_tasks") or [])
                        scored_candidates.append((total_score, skill_ratio, -current_load, m, matched_labels))

                if scored_candidates:
                    scored_candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
                    best_score, _, _, best_member, best_matches = scored_candidates[0]
                    matched_member = best_member
                    confidence_score = best_score
                    avail_label = best_member.get("availability", "Available")
                    load_count = len(best_member.get("assigned_tasks") or [])
                    max_load = best_member.get("maximum_workload") or 5
                    assignment_reason = (
                        f"Matched by skills/role ({', '.join(best_matches[:3])}), "
                        f"availability ({avail_label}), and workload ({load_count}/{max_load})."
                    )

            # Priority 4: UNASSIGNED (Never fabricate or assign to Team Leader automatically)
            if matched_member:
                assigned_name = matched_member.get("name")
                assigned_id = matched_member.get("member_id") or matched_member.get("user_id")
                assigned_role = matched_member.get("role", "Member")
                assigned_email = matched_member.get("email", "")
            else:
                assigned_name = "Unassigned"
                assigned_id = None
                assigned_role = "Unassigned"
                assigned_email = ""
                confidence_score = 0.0
                req_str = ", ".join(task.get("required_skills") or []) or "unspecified skills"
                assignment_reason = (
                    f"No active workspace member matched required skills ({req_str}) or explicit commitment. "
                    "Marked as Unassigned for Team Leader review."
                )

            assigned_tasks.append({
                "title": task.get("title"),
                "description": task.get("description", ""),
                "related_discussion": task.get("related_discussion", ""),
                "requester": task.get("requester"),
                "priority": task.get("priority", "Medium"),
                "deadline": task.get("deadline"),
                "required_skills": task.get("required_skills", []),
                "evidence": task.get("evidence", ""),
                "timestamp": task.get("timestamp"),
                "confidence": confidence_score,
                "assigned_member_id": assigned_id,
                "assigned_member_name": assigned_name,
                "assigned_member_role": assigned_role,
                "assigned_member_email": assigned_email,
                "confidence_score": confidence_score,
                "assignment_reason": assignment_reason,
            })

        duration_sec = round(time.time() - start_time, 3)
        logger.info(f"[{TaskAssignmentAgent.NAME}] Assigned {len(assigned_tasks)} tasks in {duration_sec}s")

        return {
            "status": "success",
            "assigned_tasks": assigned_tasks,
            "execution_duration": duration_sec,
        }
