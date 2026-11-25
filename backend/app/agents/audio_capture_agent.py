import time
import logging
from typing import Dict, Any, Optional
from app.services.storage_service import StorageService

logger = logging.getLogger("meetmind.agent1")


class AudioCaptureAgent:
    """
    Agent 1: Audio Capture Agent
    Responsibilities:
      - Validates uploaded audio format, size, and decodability constraints
      - Stores audio securely in the uploads storage abstraction
      - Extracts audio diagnostics (duration, sample rate, channels, loudness, silence check)
    """
    AGENT_ID = 1
    NAME = "Audio Capture Agent"

    @staticmethod
    def execute(
        meeting_id: str,
        team_id: str,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        validate_audio: bool = True,
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{AudioCaptureAgent.NAME}] Capturing audio for meeting {meeting_id} ({len(audio_bytes)} bytes)")

        storage_meta = StorageService.save_audio_file(
            file_bytes=audio_bytes,
            original_filename=filename,
            meeting_id=meeting_id,
            content_type=content_type,
            validate_audio=validate_audio,
        )

        duration_sec = round(time.time() - start_time, 3)

        return {
            "status": "success",
            "meeting_id": meeting_id,
            "team_id": team_id,
            "storage_path": storage_meta["storage_path"],
            "filename": storage_meta["filename"],
            "file_size": storage_meta["file_size"],
            "content_type": storage_meta["content_type"],
            "sha256": storage_meta.get("sha256"),
            "deduplicated": storage_meta.get("deduplicated", False),
            "diagnostics": storage_meta.get("diagnostics", {}),
            "execution_duration": duration_sec,
        }
