import time
import json
import logging
from typing import Dict, Any, List
from groq import Groq
from app.config import settings
from app.utils.groq_client import (
    get_groq_chat_completion,
    extract_json_from_llm_response,
    classify_groq_error,
)

logger = logging.getLogger("meetmind.agent4")


class MeetingAnalystAgent:
    """
    Agent 4: Meeting Analyst Agent
    Responsibilities:
      - Analyzes the complete meeting transcript using Groq LLM
      - Generates executive summary, discussion topics, key decisions, unresolved questions, and outcomes
      - Returns validated structured JSON
      - Never fabricates summaries or silently swallows API errors
    """
    AGENT_ID = 4
    NAME = "Meeting Analyst Agent"

    @staticmethod
    def execute(
        transcript_text: str,
        diarized_segments: List[Dict[str, Any]],
        meeting_title: str = "Team Meeting",
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{MeetingAnalystAgent.NAME}] Analyzing meeting context ({len(transcript_text)} chars)")

        clean_text = (transcript_text or "").strip()
        if not clean_text:
            return {
                "status": "no_speech",
                "meeting_summary": "No speech detected in this meeting session.",
                "discussion_topics": [],
                "key_decisions": [],
                "unresolved_questions": [],
                "important_outcomes": [],
                "model": "none",
                "execution_duration": round(time.time() - start_time, 3),
            }

        api_key = (settings.GROQ_API_KEY or "").strip()
        if not api_key:
            return {
                "status": "error",
                "error_code": "auth_error",
                "error": "GROQ_API_KEY is not configured. Cannot run AI meeting analysis.",
                "meeting_summary": "",
                "discussion_topics": [],
                "key_decisions": [],
                "unresolved_questions": [],
                "important_outcomes": [],
                "model": settings.GROQ_MODEL,
                "execution_duration": round(time.time() - start_time, 3),
            }

        # Format diarized transcript if available for richer context
        formatted_lines = []
        for s in (diarized_segments or []):
            spk = s.get("speaker_label") or s.get("suggested_name") or s.get("speaker_id") or "Speaker"
            txt = (s.get("text") or "").strip()
            if txt:
                if txt.lower().startswith(f"{spk.lower()}:"):
                    formatted_lines.append(txt)
                else:
                    formatted_lines.append(f"[{s.get('start', 0.0)}s] {spk}: {txt}")
        context_transcript = "\n".join(formatted_lines) if formatted_lines else clean_text

        try:
            client = Groq(api_key=api_key, timeout=60.0)
            prompt = f"""You are the Meeting Analyst AI Agent for MeetMind AI.
Analyze the following meeting transcript (which may contain English, Tamil, or mixed Tamil-English/Tanglish) and return ONLY a valid JSON object (no markdown, no backticks, no extra text).

Meeting Title: {meeting_title}
Transcript:
\"\"\"
{context_transcript}
\"\"\"

Required JSON Structure:
{{
  "meeting_summary": "Concise 2-4 sentence executive summary based EXCLUSIVELY on the actual transcript. Do not invent facts.",
  "discussion_topics": ["Topic 1", "Topic 2"],
  "key_decisions": ["Only decisions explicitly confirmed in the transcript, or empty list if none"],
  "unresolved_questions": ["Open questions requiring follow-up if any"],
  "important_outcomes": ["Concrete outcomes if any"]
}}"""

            completion = get_groq_chat_completion(
                client=client,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise meeting intelligence analyst. Output ONLY strict JSON based exclusively on the provided transcript.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )

            raw_content = completion.choices[0].message.content or ""
            cleaned_json = extract_json_from_llm_response(raw_content)
            parsed = json.loads(cleaned_json)

            duration_sec = round(time.time() - start_time, 3)
            actual_model = getattr(completion, "model", settings.GROQ_MODEL)
            logger.info(f"[{MeetingAnalystAgent.NAME}] Analysis complete in {duration_sec}s using {actual_model}")

            return {
                "status": "success",
                "meeting_summary": (parsed.get("meeting_summary") or "").strip(),
                "discussion_topics": parsed.get("discussion_topics") or [],
                "key_decisions": parsed.get("key_decisions") or [],
                "unresolved_questions": parsed.get("unresolved_questions") or [],
                "important_outcomes": parsed.get("important_outcomes") or [],
                "model": actual_model,
                "execution_duration": duration_sec,
            }

        except Exception as e:
            classified = classify_groq_error(e)
            logger.error(f"[{MeetingAnalystAgent.NAME}] Groq analysis failed ({classified['error_code']}): {classified['message']}")
            return {
                "status": "error",
                "error_code": classified["error_code"],
                "error": classified["message"],
                "meeting_summary": "",
                "discussion_topics": [],
                "key_decisions": [],
                "unresolved_questions": [],
                "important_outcomes": [],
                "model": settings.GROQ_MODEL,
                "execution_duration": round(time.time() - start_time, 3),
            }
