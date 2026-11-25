import time
import logging
from typing import Dict, Any, Optional
from app.config import settings
from app.services.zapier_service import ZapierService

logger = logging.getLogger("meetmind.agent8")

class AutomationAgent:
    """
    Agent 8: Automation Agent
    Responsibilities:
      - Detects approved business events (e.g. meeting analysis complete, human task approval)
      - Dispatches resilient Zapier Catch Hook webhooks with exponential retries
      - Records delivery status in MongoDB automation_logs
      - Strictly enforces human approval: Never triggers task_approved webhook prior to human approval!
      - Obeys ENABLE_AUTOMATION_DISPATCH configuration to protect against accidental webhook triggers.
    """
    AGENT_ID = 8
    NAME = "Automation Agent"

    @staticmethod
    async def dispatch_meeting_completed(meeting_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Triggers Zapier meeting_completed webhook once analysis is saved in MongoDB."""
        if not getattr(settings, "ENABLE_AUTOMATION_DISPATCH", False):
            logger.info(f"[{AutomationAgent.NAME}] ENABLE_AUTOMATION_DISPATCH is False. Skipping meeting_completed webhook.")
            return {"status": "skipped", "delivery_status": "skipped", "reason": "automation_disabled_by_config"}
        start_time = time.time()
        logger.info(f"[{AutomationAgent.NAME}] Dispatching meeting_completed webhook for {meeting_doc.get('meeting_id')}")
        result = await ZapierService.send_meeting_completed_webhook(meeting_doc)
        result["execution_duration"] = round(time.time() - start_time, 3)
        return result

    @staticmethod
    async def dispatch_task_approved(task_doc: Dict[str, Any], approved_by_name: str = "Admin") -> Dict[str, Any]:
        """Triggers Zapier task_approved webhook strictly after human administrator approval."""
        if not getattr(settings, "ENABLE_AUTOMATION_DISPATCH", False):
            logger.info(f"[{AutomationAgent.NAME}] ENABLE_AUTOMATION_DISPATCH is False. Skipping task_approved webhook.")
            return {"status": "skipped", "delivery_status": "skipped", "reason": "automation_disabled_by_config"}
        start_time = time.time()
        logger.info(f"[{AutomationAgent.NAME}] Dispatching task_approved webhook for task {task_doc.get('task_id')}")
        result = await ZapierService.send_task_approved_webhook(task_doc, approved_by_name=approved_by_name)
        result["execution_duration"] = round(time.time() - start_time, 3)
        return result
