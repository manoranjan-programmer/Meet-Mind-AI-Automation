import re
import logging
from typing import Dict, Any, List, Optional
from groq import Groq
from app.config import settings

logger = logging.getLogger("meetmind.groq")

# Priority list of active Groq chat models to try
FALLBACK_CHAT_MODELS = [
    settings.GROQ_MODEL,
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


def extract_json_from_llm_response(content: str) -> str:
    """
    Strips <think>...</think> reasoning blocks and markdown code fences
    from LLM output so strict json.loads() succeeds cleanly.
    """
    if not content:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return cleaned


def classify_groq_error(exc: Exception) -> Dict[str, str]:
    """Classifies Groq API exceptions into structured error codes and actionable messages."""
    err_str = str(exc)
    err_lower = err_str.lower()
    if "401" in err_lower or "invalid_api_key" in err_lower or "authentication" in err_lower or "unauthorized" in err_lower:
        return {"error_code": "auth_error", "message": f"Groq API authentication failed: {err_str}"}
    if "model_not_found" in err_lower or "does not exist" in err_lower or "404" in err_lower:
        return {"error_code": "invalid_model", "message": f"Configured Groq model is unavailable or invalid: {err_str}"}
    if "429" in err_lower or "rate_limit" in err_lower or "quota" in err_lower:
        return {"error_code": "rate_limit", "message": f"Groq API rate limit or quota exceeded: {err_str}"}
    if "timeout" in err_lower or "timed out" in err_lower:
        return {"error_code": "timeout", "message": f"Groq API request timed out: {err_str}"}
    if "413" in err_lower or "too large" in err_lower or "maximum" in err_lower:
        return {"error_code": "file_too_large", "message": f"Audio file exceeds Groq API size limit: {err_str}"}
    return {"error_code": "api_error", "message": f"Groq API error: {err_str}"}


def get_groq_chat_completion(
    client: Groq,
    messages: List[Dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 1200,
    response_format: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Executes a Groq chat completion with automatic fallback to accessible models
    if the configured model returns 404 (model_not_found) or permissions error.
    """
    attempted_models = []
    last_exception = None

    models_to_try = []
    for m in FALLBACK_CHAT_MODELS:
        if m and m not in models_to_try:
            models_to_try.append(m)

    kwargs: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    for model_name in models_to_try:
        attempted_models.append(model_name)
        try:
            logger.info(f"Invoking Groq model '{model_name}'...")
            completion = client.chat.completions.create(
                model=model_name,
                **kwargs,
            )
            content = completion.choices[0].message.content
            if content and content.strip():
                return completion
            logger.warning(f"Groq model '{model_name}' returned empty response. Trying next model...")
        except Exception as e:
            last_exception = e
            classified = classify_groq_error(e)
            if classified["error_code"] == "auth_error":
                logger.error(classified["message"])
                raise
            logger.warning(f"Groq model '{model_name}' failed ({classified['error_code']}): {e}")
            continue

    if last_exception:
        raise last_exception
    raise RuntimeError(f"All attempted Groq models failed: {attempted_models}")
