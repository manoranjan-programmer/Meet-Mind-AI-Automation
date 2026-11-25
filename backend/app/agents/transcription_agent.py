import os
import re
import time
import logging
import tempfile
from typing import List, Dict, Any, Optional
from groq import Groq
from app.config import settings
from app.services.storage_service import StorageService, MIME_TYPE_MAP
from app.utils.groq_client import classify_groq_error

logger = logging.getLogger("meetmind.agent2")

SUPPORTED_WHISPER_MODELS = {"whisper-large-v3", "whisper-large-v3-turbo"}


class TranscriptionAgent:
    """
    Agent 2: Transcription Agent
    Responsibilities:
      - Validates audio decodability, duration, and non-silent speech signal before API call
      - Converts speech audio into text using Groq Whisper API (whisper-large-v3 / turbo)
      - Automatically chunks audio files > 24MB using pydub with 5-second overlap
      - Preserves timestamps (start, end) across chunks with continuous offsets
      - Supports multilingual audio (English, Tamil, Tanglish)
      - Never fabricates fake transcripts or swallows API failures
    """
    AGENT_ID = 2
    NAME = "Transcription Agent"
    MAX_CHUNK_BYTES = 24 * 1024 * 1024  # 24 MB (Groq Whisper limit is 25MB)
    CHUNK_LENGTH_MS = 10 * 60 * 1000    # 10 minutes
    CHUNK_OVERLAP_MS = 5 * 1000         # 5 seconds overlap to avoid boundary loss
    REQUEST_TIMEOUT_SECONDS = 120.0
    WHISPER_PROMPT = (
        "Meeting discussion in English, Tamil, and mixed Tamil-English (Tanglish). "
        "Topics include software development, tasks, deadlines, sprint planning, and action items."
    )

    @staticmethod
    def _resolve_whisper_model() -> str:
        configured = (settings.WHISPER_MODEL or "").strip()
        if configured in SUPPORTED_WHISPER_MODELS:
            return configured
        logger.warning(f"[{TranscriptionAgent.NAME}] Configured WHISPER_MODEL '{configured}' is not in {SUPPORTED_WHISPER_MODELS}; using 'whisper-large-v3'.")
        return "whisper-large-v3"

    @staticmethod
    def _mime_for_path(storage_path: str) -> str:
        _, ext = os.path.splitext(storage_path.lower())
        return MIME_TYPE_MAP.get(ext, "audio/webm")

    @staticmethod
    def _parse_segments(raw_segments: Any, full_text: str, offset_sec: float = 0.0) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        for s in (raw_segments or []):
            if isinstance(s, dict):
                s_start = s.get("start", 0.0)
                s_end = s.get("end", 0.0)
                s_text = (s.get("text") or "").strip()
            else:
                s_start = getattr(s, "start", 0.0)
                s_end = getattr(s, "end", 0.0)
                s_text = (getattr(s, "text", "") or "").strip()

            if s_text:
                segments.append({
                    "segment_id": len(segments) + 1,
                    "start": round(offset_sec + float(s_start), 2),
                    "end": round(offset_sec + float(s_end), 2),
                    "text": s_text,
                })

        if not segments and full_text and full_text.strip():
            sentences = [sent.strip() for sent in re.split(r"(?<=[.!?])\s+", full_text.strip()) if sent.strip()]
            for idx, sent in enumerate(sentences):
                segments.append({
                    "segment_id": idx + 1,
                    "start": round(offset_sec + idx * 5.0, 2),
                    "end": round(offset_sec + (idx + 1) * 5.0, 2),
                    "text": sent,
                })
        return segments

    @staticmethod
    def execute(
        storage_path: str,
        language: Optional[str] = None,
        audio_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{TranscriptionAgent.NAME}] Starting Whisper transcription for {storage_path}")

        api_key = (settings.GROQ_API_KEY or "").strip()
        if not api_key:
            return {
                "status": "error",
                "error_code": "auth_error",
                "error": "GROQ_API_KEY is not configured. Cannot perform speech-to-text transcription.",
                "speech_detected": False,
                "vad_status": "error",
                "full_text": "",
                "segments": [],
                "model": TranscriptionAgent._resolve_whisper_model(),
                "execution_duration": round(time.time() - start_time, 3),
            }

        if not storage_path or not os.path.exists(storage_path):
            return {
                "status": "error",
                "error_code": "file_not_found",
                "error": f"Audio file not found at '{storage_path}'.",
                "speech_detected": False,
                "vad_status": "error",
                "full_text": "",
                "segments": [],
                "model": TranscriptionAgent._resolve_whisper_model(),
                "execution_duration": round(time.time() - start_time, 3),
            }

        diag = audio_diagnostics or StorageService.inspect_audio_file(storage_path)
        if not diag.get("decodable"):
            return {
                "status": "error",
                "error_code": "audio_corrupted",
                "error": diag.get("error") or "Uploaded audio file could not be decoded.",
                "speech_detected": False,
                "vad_status": "audio_corrupted",
                "audio_diagnostics": diag,
                "full_text": "",
                "segments": [],
                "model": TranscriptionAgent._resolve_whisper_model(),
                "execution_duration": round(time.time() - start_time, 3),
            }

        if diag.get("is_silent"):
            return {
                "status": "no_speech",
                "speech_detected": False,
                "vad_status": "no_speech_detected",
                "vad_message": (
                    f"Audio file is silent or too short ({diag.get('duration_seconds', 0)}s, "
                    f"max {diag.get('max_dbfs', -120)} dBFS). Please check your microphone and try again."
                ),
                "audio_diagnostics": diag,
                "full_text": "",
                "segments": [],
                "model": TranscriptionAgent._resolve_whisper_model(),
                "execution_duration": round(time.time() - start_time, 3),
            }

        model_name = TranscriptionAgent._resolve_whisper_model()
        file_size = os.path.getsize(storage_path)
        mime_type = diag.get("mime_type") or TranscriptionAgent._mime_for_path(storage_path)

        try:
            client = Groq(api_key=api_key, timeout=TranscriptionAgent.REQUEST_TIMEOUT_SECONDS)

            if file_size > TranscriptionAgent.MAX_CHUNK_BYTES:
                logger.info(
                    f"[{TranscriptionAgent.NAME}] Audio size ({file_size / (1024*1024):.1f}MB) > 24MB. "
                    "Splitting into overlapping chunks."
                )
                return TranscriptionAgent._transcribe_large_audio_in_chunks(
                    client=client,
                    storage_path=storage_path,
                    model_name=model_name,
                    language=language,
                    audio_diagnostics=diag,
                    start_time=start_time,
                )

            with open(storage_path, "rb") as audio_file:
                audio_bytes = audio_file.read()

            kwargs: Dict[str, Any] = {
                "file": (os.path.basename(storage_path), audio_bytes, mime_type),
                "model": model_name,
                "response_format": "verbose_json",
                "prompt": TranscriptionAgent.WHISPER_PROMPT,
            }
            if language:
                kwargs["language"] = language

            transcription = client.audio.transcriptions.create(**kwargs)

            raw_segments = getattr(transcription, "segments", []) or []
            full_text = (getattr(transcription, "text", "") or "").strip()
            segments = TranscriptionAgent._parse_segments(raw_segments, full_text, offset_sec=0.0)

            clean_speech = re.sub(r"\[.*?\]|\(.*?\)|[\s\.\,\!\?\-]", "", full_text).strip()
            duration_sec = round(time.time() - start_time, 3)

            if not clean_speech or len(clean_speech) < 2:
                logger.info(f"[{TranscriptionAgent.NAME}] Whisper returned empty/non-speech response.")
                return {
                    "status": "no_speech",
                    "speech_detected": False,
                    "vad_status": "no_speech_detected",
                    "vad_message": "Speech recognition returned no intelligible speech. Please check microphone clarity.",
                    "audio_diagnostics": diag,
                    "full_text": "",
                    "segments": [],
                    "model": model_name,
                    "execution_duration": duration_sec,
                }

            logger.info(f"[{TranscriptionAgent.NAME}] Transcribed {len(segments)} segments in {duration_sec}s using {model_name}")
            return {
                "status": "success",
                "speech_detected": True,
                "vad_status": "speech_detected",
                "audio_diagnostics": diag,
                "full_text": full_text,
                "segments": segments,
                "model": model_name,
                "execution_duration": duration_sec,
            }

        except Exception as e:
            classified = classify_groq_error(e)
            logger.error(f"[{TranscriptionAgent.NAME}] Whisper API failed ({classified['error_code']}): {classified['message']}")
            return {
                "status": "error",
                "error_code": classified["error_code"],
                "error": classified["message"],
                "speech_detected": False,
                "vad_status": "error",
                "audio_diagnostics": diag,
                "full_text": "",
                "segments": [],
                "model": model_name,
                "execution_duration": round(time.time() - start_time, 3),
            }

    @staticmethod
    def _transcribe_large_audio_in_chunks(
        client: Groq,
        storage_path: str,
        model_name: str,
        language: Optional[str],
        audio_diagnostics: Dict[str, Any],
        start_time: float,
    ) -> Dict[str, Any]:
        """
        Splits large audio into 10-minute slices with 5-second overlap using pydub,
        transcribes each slice in order, and merges segments without losing boundary speech.
        """
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(storage_path)
            total_duration_ms = len(audio)
            step_ms = TranscriptionAgent.CHUNK_LENGTH_MS - TranscriptionAgent.CHUNK_OVERLAP_MS

            chunks = []
            pos = 0
            while pos < total_duration_ms:
                end_pos = min(pos + TranscriptionAgent.CHUNK_LENGTH_MS, total_duration_ms)
                chunks.append((pos, audio[pos:end_pos]))
                if end_pos >= total_duration_ms:
                    break
                pos += step_ms

            all_segments: List[Dict[str, Any]] = []
            full_text_parts: List[str] = []
            last_end_time = -1.0

            for chunk_idx, (chunk_start_ms, chunk_audio) in enumerate(chunks):
                offset_sec = chunk_start_ms / 1000.0
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_chunk:
                    temp_chunk_path = temp_chunk.name

                try:
                    chunk_audio.export(temp_chunk_path, format="mp3", bitrate="64k")
                    with open(temp_chunk_path, "rb") as cf:
                        kwargs: Dict[str, Any] = {
                            "file": (os.path.basename(temp_chunk_path), cf.read(), "audio/mpeg"),
                            "model": model_name,
                            "response_format": "verbose_json",
                            "prompt": TranscriptionAgent.WHISPER_PROMPT,
                        }
                        if language:
                            kwargs["language"] = language

                        chunk_res = client.audio.transcriptions.create(**kwargs)

                    chunk_text = (getattr(chunk_res, "text", "") or "").strip()
                    raw_segs = getattr(chunk_res, "segments", []) or []
                    parsed = TranscriptionAgent._parse_segments(raw_segs, chunk_text, offset_sec=offset_sec)

                    for seg in parsed:
                        # Skip segments fully inside the already-transcribed overlap window
                        if chunk_idx > 0 and seg["end"] <= last_end_time + 0.5:
                            continue
                        seg["segment_id"] = len(all_segments) + 1
                        all_segments.append(seg)
                        full_text_parts.append(seg["text"])
                        last_end_time = max(last_end_time, seg["end"])

                finally:
                    if os.path.exists(temp_chunk_path):
                        os.remove(temp_chunk_path)

            full_text = " ".join(full_text_parts).strip()
            duration_sec = round(time.time() - start_time, 3)

            if not all_segments or not full_text:
                return {
                    "status": "no_speech",
                    "speech_detected": False,
                    "vad_status": "no_speech_detected",
                    "vad_message": "No clear speech was detected across audio chunks.",
                    "audio_diagnostics": audio_diagnostics,
                    "full_text": "",
                    "segments": [],
                    "model": model_name,
                    "execution_duration": duration_sec,
                    "chunks_processed": len(chunks),
                }

            return {
                "status": "success",
                "speech_detected": True,
                "vad_status": "speech_detected",
                "audio_diagnostics": audio_diagnostics,
                "full_text": full_text,
                "segments": all_segments,
                "model": model_name,
                "execution_duration": duration_sec,
                "chunks_processed": len(chunks),
            }

        except Exception as chunk_err:
            classified = classify_groq_error(chunk_err)
            logger.error(f"[{TranscriptionAgent.NAME}] Chunked transcription failed: {classified['message']}")
            return {
                "status": "error",
                "error_code": classified["error_code"],
                "error": classified["message"],
                "speech_detected": False,
                "vad_status": "error",
                "audio_diagnostics": audio_diagnostics,
                "full_text": "",
                "segments": [],
                "model": model_name,
                "execution_duration": round(time.time() - start_time, 3),
            }
