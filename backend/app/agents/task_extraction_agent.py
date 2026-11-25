import time
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ValidationError, model_validator
from groq import Groq
from app.config import settings
from app.utils.groq_client import (
    get_groq_chat_completion,
    extract_json_from_llm_response,
    classify_groq_error,
)

logger = logging.getLogger("meetmind.agent5")


class ExtractedTaskSchema(BaseModel):
    title: str = Field(..., min_length=2, description="Short imperative task title")
    description: Optional[str] = Field("", description="Clear description of what needs to be accomplished")
    related_discussion: Optional[str] = Field("", description="Discussion context surrounding this task")
    requester: Optional[str] = Field(None, description="Person who requested or suggested the task, or null")
    explicit_owner: Optional[str] = Field(None, description="Person who explicitly accepted responsibility ('I will...', 'I can...'), or null")
    is_explicit_commitment: bool = Field(False, description="True if a speaker explicitly accepted responsibility")
    deadline: Optional[str] = Field(None, description="Explicit deadline or date if mentioned in dialogue, else null")
    priority: str = Field("Medium", description="Critical, High, Medium, or Low")
    required_skills: List[str] = Field(default_factory=list, description="Extracted technical skills needed for the task")
    evidence: Optional[str] = Field("", description="Verbatim quote from the meeting proving this task and responsibility")
    timestamp: Optional[str] = Field(None, description="Timestamp of supporting segment, e.g. '00:12'")
    confidence: float = Field(0.85, ge=0.0, le=1.0, description="Extraction confidence score 0.0-1.0")


class TaskExtractionResponseSchema(BaseModel):
    extracted_tasks: List[ExtractedTaskSchema] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_task_list(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "extracted_tasks" not in data:
                tasks = data.get("tasks") or data.get("action_items") or data.get("items") or []
                data["extracted_tasks"] = tasks
        elif isinstance(data, list):
            data = {"extracted_tasks": data}
        return data


def _format_ts(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _match_timestamp_from_segments(evidence: str, diarized_segments: List[Dict[str, Any]]) -> Optional[str]:
    if not diarized_segments:
        return None
    ev_lower = (evidence or "").strip().lower()
    if ev_lower:
        # Remove leading "Speaker:" if present
        if ":" in ev_lower:
            ev_body = ev_lower.split(":", 1)[1].strip()
        else:
            ev_body = ev_lower
        for seg in diarized_segments:
            seg_txt = (seg.get("text") or "").strip().lower()
            if seg_txt and (seg_txt in ev_lower or (ev_body and ev_body[:24] in seg_txt)):
                return _format_ts(float(seg.get("start", 0.0)))
    return _format_ts(float(diarized_segments[0].get("start", 0.0)))


class TaskExtractionAgent:
    """
    Agent 5: Action Item Extraction & Responsibility Agent
    Responsibilities:
      - Extracts genuine, actionable tasks from actual meeting dialogue
      - Strictly distinguishes Requester vs Discussant vs Acceptor
      - Extracts deadlines ONLY when explicitly confirmed in transcript
      - Gathers verbatim evidence quote and timestamp
      - Never invents deliverables or swallows API failures
    """
    AGENT_ID = 5
    NAME = "Task Extraction Agent"

    @staticmethod
    def execute(
        transcript_text: str,
        diarized_segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{TaskExtractionAgent.NAME}] Extracting action items from transcript ({len(transcript_text)} chars)")

        formatted_lines = []
        for s in (diarized_segments or []):
            speaker_name = s.get("speaker_label") or s.get("suggested_name") or s.get("speaker_id") or "Speaker"
            line_text = (s.get("text") or "").strip()
            ts = _format_ts(float(s.get("start", 0.0)))
            if line_text:
                if line_text.lower().startswith(f"{speaker_name.lower()}:"):
                    formatted_lines.append(f"[{ts}] {line_text}")
                else:
                    formatted_lines.append(f"[{ts}] {speaker_name}: {line_text}")

        attributed_dialogue = "\n".join(formatted_lines) if formatted_lines else (transcript_text or "").strip()

        if not attributed_dialogue:
            return {
                "status": "success",
                "extracted_tasks": [],
                "task_count": 0,
                "execution_duration": round(time.time() - start_time, 3),
            }

        api_key = (settings.GROQ_API_KEY or "").strip()
        if not api_key:
            return {
                "status": "error",
                "error_code": "auth_error",
                "error": "GROQ_API_KEY is not configured. Cannot extract tasks.",
                "extracted_tasks": [],
                "task_count": 0,
                "execution_duration": round(time.time() - start_time, 3),
            }

        last_error: Optional[Dict[str, str]] = None
        for attempt in range(1, 3):
            try:
                client = Groq(api_key=api_key, timeout=60.0)
                prompt = f"""You are the Action Item Extraction AI Agent for MeetMind AI.
Analyze the following meeting transcript and extract ONLY genuine, actionable tasks discussed or agreed upon.
If there are NO genuine actionable tasks in the transcript, return {{"extracted_tasks": []}}.

CRITICAL RULES:
1. DISTINGUISH DISCUSSION VS REAL TASKS:
   - Only extract actionable work items, features, fixes, or deliverables.
   - Do NOT invent tasks from greetings, filler, or casual remarks.
2. RESPONSIBILITY ATTRIBUTION:
   - "requester": Person who requested, assigned, or suggested the task, or null.
   - "explicit_owner": ONLY the person who explicitly accepted, committed to, or agreed to do the work (e.g. "I will...", "I'll handle...", "naan pandren"), or null.
   - If no one explicitly committed, set "explicit_owner": null and "is_explicit_commitment": false.
3. TAMIL / TANGLISH / ENGLISH:
   - Dialogue may include Tamil or Tanglish. Extract the deliverable title in clear English and attribute the speaking participant.
4. DEADLINES:
   - Extract a deadline ONLY if explicitly mentioned (e.g. "by Friday", "by tomorrow"). Otherwise null.
5. PRIORITY: Must be one of: Critical, High, Medium, Low.
6. EVIDENCE & TIMESTAMP: Include the verbatim quote and the segment timestamp (e.g. "00:12").
7. CONFIDENCE: Float between 0.0 and 1.0 reflecting how clearly the task was stated.

Transcript:
\"\"\"
{attributed_dialogue}
\"\"\"

Return ONLY a valid JSON object matching this schema:
{{
  "extracted_tasks": [
    {{
      "title": "Short imperative task title",
      "description": "Clear description of deliverables",
      "related_discussion": "Summary of discussion context",
      "requester": "Name or null",
      "explicit_owner": "Name or null",
      "is_explicit_commitment": true,
      "deadline": "Explicit deadline or null",
      "priority": "Critical / High / Medium / Low",
      "required_skills": ["Skill1"],
      "evidence": "Verbatim transcript quote",
      "timestamp": "00:00",
      "confidence": 0.9
    }}
  ]
}}"""

                completion = get_groq_chat_completion(
                    client=client,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a precise task extraction agent that outputs strictly validated JSON matching the schema based only on the transcript.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=1400,
                    response_format={"type": "json_object"},
                )

                raw_content = completion.choices[0].message.content or ""
                cleaned_json = extract_json_from_llm_response(raw_content)
                parsed = json.loads(cleaned_json)
                validated = TaskExtractionResponseSchema.model_validate(parsed)

                task_dicts = []
                for t in validated.extracted_tasks:
                    d = t.model_dump()
                    if not d.get("timestamp"):
                        d["timestamp"] = _match_timestamp_from_segments(d.get("evidence", ""), diarized_segments)
                    task_dicts.append(d)

                duration_sec = round(time.time() - start_time, 3)
                logger.info(f"[{TaskExtractionAgent.NAME}] Successfully extracted {len(task_dicts)} tasks via Groq in {duration_sec}s")

                return {
                    "status": "success",
                    "extracted_tasks": task_dicts,
                    "task_count": len(task_dicts),
                    "execution_duration": duration_sec,
                }

            except (ValidationError, json.JSONDecodeError) as val_err:
                logger.warning(f"[{TaskExtractionAgent.NAME}] Attempt {attempt} JSON/schema error: {val_err}")
                last_error = {"error_code": "invalid_json", "message": f"Task extraction JSON validation failed: {val_err}"}
            except Exception as e:
                last_error = classify_groq_error(e)
                logger.error(f"[{TaskExtractionAgent.NAME}] Groq task extraction error on attempt {attempt}: {last_error['message']}")
                break

        return {
            "status": "error",
            "error_code": (last_error or {}).get("error_code", "api_error"),
            "error": (last_error or {}).get("message", "Task extraction failed."),
            "extracted_tasks": [],
            "task_count": 0,
            "execution_duration": round(time.time() - start_time, 3),
        }
