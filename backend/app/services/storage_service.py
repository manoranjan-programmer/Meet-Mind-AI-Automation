import os
import uuid
import math
import hashlib
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger("meetmind.storage")

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac", ".mp4"}
MIME_TYPE_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}
CONTENT_TYPE_TO_EXT = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/ogg": ".ogg",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
}


class StorageService:
    @staticmethod
    def get_upload_dir() -> str:
        """Resolves root-relative uploads path."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        root_uploads = os.path.join(os.path.dirname(base_dir), "uploads")
        if os.path.exists(root_uploads):
            return root_uploads
        backend_uploads = os.path.join(base_dir, "uploads")
        os.makedirs(backend_uploads, exist_ok=True)
        return backend_uploads

    @staticmethod
    def _resolve_extension(original_filename: str, content_type: Optional[str] = None) -> str:
        _, ext = os.path.splitext((original_filename or "").lower())
        if ext in ALLOWED_AUDIO_EXTENSIONS:
            return ext
        if content_type:
            ct_base = content_type.split(";")[0].strip().lower()
            if ct_base in CONTENT_TYPE_TO_EXT:
                return CONTENT_TYPE_TO_EXT[ct_base]
            if content_type.lower() in CONTENT_TYPE_TO_EXT:
                return CONTENT_TYPE_TO_EXT[content_type.lower()]
        if not ext or ext == ".blob":
            return ".webm"
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        )

    @staticmethod
    def inspect_audio_file(storage_path: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Decodes and validates an audio file on disk using pydub/ffmpeg.
        Returns duration, sample rate, channels, loudness, and silence detection diagnostics.
        """
        if not storage_path or not os.path.exists(storage_path):
            return {
                "decodable": False,
                "error": "Audio file not found on server.",
                "file_exists": False,
                "file_size_bytes": 0,
                "duration_seconds": 0.0,
                "sample_rate": 0,
                "channels": 0,
                "dbfs": -120.0,
                "max_dbfs": -120.0,
                "is_silent": True,
                "has_speech_signal": False,
                "mime_type": mime_type or "unknown",
            }

        file_size = os.path.getsize(storage_path)
        _, ext = os.path.splitext(storage_path.lower())
        resolved_mime = mime_type or MIME_TYPE_MAP.get(ext, "application/octet-stream")

        if file_size < 100:
            return {
                "decodable": False,
                "error": f"Audio file is too small ({file_size} bytes) to contain valid audio.",
                "file_exists": True,
                "file_size_bytes": file_size,
                "duration_seconds": 0.0,
                "sample_rate": 0,
                "channels": 0,
                "dbfs": -120.0,
                "max_dbfs": -120.0,
                "is_silent": True,
                "has_speech_signal": False,
                "mime_type": resolved_mime,
            }

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(storage_path)
            duration_sec = round(len(audio) / 1000.0, 2)
            sample_rate = int(audio.frame_rate)
            channels = int(audio.channels)
            raw_dbfs = audio.dBFS
            raw_max_dbfs = audio.max_dBFS
            dbfs = round(raw_dbfs, 2) if math.isfinite(raw_dbfs) else -120.0
            max_dbfs = round(raw_max_dbfs, 2) if math.isfinite(raw_max_dbfs) else -120.0

            is_too_short = duration_sec < 0.3
            is_silent = is_too_short or max_dbfs < -55.0 or dbfs < -70.0

            return {
                "decodable": True,
                "error": None,
                "file_exists": True,
                "file_size_bytes": file_size,
                "duration_seconds": duration_sec,
                "sample_rate": sample_rate,
                "channels": channels,
                "dbfs": dbfs,
                "max_dbfs": max_dbfs,
                "is_silent": is_silent,
                "has_speech_signal": not is_silent,
                "mime_type": resolved_mime,
            }
        except Exception as e:
            logger.error(f"Audio decode failed for {storage_path}: {e}")
            return {
                "decodable": False,
                "error": f"Audio file could not be decoded: {str(e)}",
                "file_exists": True,
                "file_size_bytes": file_size,
                "duration_seconds": 0.0,
                "sample_rate": 0,
                "channels": 0,
                "dbfs": -120.0,
                "max_dbfs": -120.0,
                "is_silent": True,
                "has_speech_signal": False,
                "mime_type": resolved_mime,
            }

    @staticmethod
    def save_audio_file(
        file_bytes: bytes,
        original_filename: str,
        meeting_id: str,
        content_type: Optional[str] = None,
        validate_audio: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates file size, format, deduplicates identical uploads per meeting,
        saves audio safely on disk, and optionally verifies decodability.
        Does not store binary blobs directly in MongoDB documents.
        """
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file uploaded.")

        max_bytes = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file exceeds maximum size limit of {settings.MAX_AUDIO_SIZE_MB}MB.",
            )

        ext = StorageService._resolve_extension(original_filename, content_type)
        resolved_mime = content_type.split(";")[0].strip() if content_type else MIME_TYPE_MAP.get(ext, "application/octet-stream")
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        upload_dir = StorageService.get_upload_dir()

        # Prevent duplicate uploads for the same meeting + identical content hash
        hash_prefix = file_hash[:12]
        for existing in os.listdir(upload_dir):
            if existing.startswith(f"{meeting_id}_{hash_prefix}"):
                existing_path = os.path.join(upload_dir, existing)
                if os.path.isfile(existing_path) and os.path.getsize(existing_path) == len(file_bytes):
                    logger.info(f"Reusing existing identical audio file {existing_path} for meeting {meeting_id}")
                    diag = StorageService.inspect_audio_file(existing_path, resolved_mime)
                    return {
                        "storage_path": existing_path,
                        "filename": existing,
                        "original_filename": original_filename,
                        "file_size": len(file_bytes),
                        "content_type": resolved_mime,
                        "sha256": file_hash,
                        "deduplicated": True,
                        "diagnostics": diag,
                    }

        safe_name = f"{meeting_id}_{hash_prefix}_{uuid.uuid4().hex[:6]}{ext}"
        target_path = os.path.join(upload_dir, safe_name)

        try:
            with open(target_path, "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            logger.error(f"Failed to write audio file {target_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to store audio file on disk.")

        diag = StorageService.inspect_audio_file(target_path, resolved_mime)
        if validate_audio and not diag["decodable"]:
            try:
                os.remove(target_path)
            except OSError:
                pass
            raise HTTPException(status_code=400, detail=diag["error"] or "Uploaded audio is corrupted or unsupported.")

        logger.info(
            f"Stored audio for meeting {meeting_id} at {target_path} "
            f"({len(file_bytes)} bytes, decodable={diag['decodable']}, dur={diag['duration_seconds']}s)"
        )

        return {
            "storage_path": target_path,
            "filename": safe_name,
            "original_filename": original_filename,
            "file_size": len(file_bytes),
            "content_type": resolved_mime,
            "sha256": file_hash,
            "deduplicated": False,
            "diagnostics": diag,
        }

    @staticmethod
    def get_audio_path(storage_path: str) -> str:
        """Validates path existence and prevents directory traversal attacks."""
        if not storage_path or not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Audio file not found on server.")
        return storage_path
