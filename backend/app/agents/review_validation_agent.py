import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("meetmind.agent7")

class ReviewValidationAgent:
    """
    Agent 7: Review and Validation Agent
    Responsibilities:
      - Validates extracted deliverables and assignment recommendations
      - Checks for duplicate task titles within the meeting
      - Identifies missing deadlines or unassigned members
      - Sets approval_status="Awaiting Approval" so tasks require human sign-off
      - Flags uncertain AI recommendations (confidence < 0.7) for administrative attention
    """
    AGENT_ID = 7
    NAME = "Review and Validation Agent"

    @staticmethod
    def execute(
        assigned_tasks: List[Dict[str, Any]],
        meeting_id: str,
        selected_participant_ids: Optional[List[str]] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{ReviewValidationAgent.NAME}] Validating {len(assigned_tasks)} task recommendations")

        validated_tasks: List[Dict[str, Any]] = []
        validation_flags: List[str] = []
        seen_titles = set()

        for idx, task in enumerate(assigned_tasks):
            title = (task.get("title") or "").strip()
            confidence = task.get("confidence_score", 0.5)
            assigned_id = task.get("assigned_member_id")
            deadline = task.get("deadline")
            evidence = (task.get("evidence") or "").strip()

            flags = []

            # Check duplicate titles
            if title.lower() in seen_titles:
                flags.append("Duplicate deliverable title detected")
                validation_flags.append(f"Task '{title}' has a duplicate title.")
            else:
                seen_titles.add(title.lower())

            # Check participant constraint: must be a selected participant
            if assigned_id and selected_participant_ids:
                if assigned_id not in selected_participant_ids:
                    flags.append("Assigned member is not among the selected meeting attendees")
                    validation_flags.append(f"Task '{title}' assigned to non-attendee {assigned_id}.")

            # Check unassigned member
            if not assigned_id or task.get("assigned_member_name") == "Unassigned":
                flags.append("No suitable team member matched automatically")

            # Check missing deadline
            if not deadline:
                flags.append("No explicit deadline detected in conversation")

            # Check missing evidence
            if not evidence:
                flags.append("No transcript evidence quote captured")

            # Check low confidence
            if confidence < 0.7 and assigned_id:
                flags.append("Lower confidence score (<0.7) requires human verification")

            validated_tasks.append({
                **task,
                "task_id": f"TSK-AI-{meeting_id}-{idx + 1:02d}",
                "meeting_id": meeting_id,
                "status": "To Do",
                "approval_status": "Awaiting Approval",  # Human approval mandatory
                "validation_flags": flags,
                "is_flagged": len(flags) > 0
            })

        duration_sec = round(time.time() - start_time, 3)
        logger.info(f"[{ReviewValidationAgent.NAME}] Validated {len(validated_tasks)} tasks ({len(validation_flags)} flags)")

        return {
            "status": "success",
            "validated_tasks": validated_tasks,
            "validation_flags": validation_flags,
            "total_validated": len(validated_tasks),
            "execution_duration": duration_sec
        }
