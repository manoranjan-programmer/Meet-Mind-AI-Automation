import os
import io
import wave
import math
import struct
import tempfile
from unittest.mock import patch, MagicMock
import pytest

from app.config import settings
from app.services.storage_service import StorageService
from app.agents.transcription_agent import TranscriptionAgent
from app.agents.diarization_agent import DiarizationAgent
from app.agents.meeting_analyst_agent import MeetingAnalystAgent
from app.agents.task_extraction_agent import TaskExtractionAgent
from app.workflows.meeting_graph import run_meeting_workflow


def _make_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000, amplitude: int = 0) -> bytes:
    """Generates a valid mono PCM WAV in memory (amplitude=0 -> pure silence, >0 -> sine tone)."""
    buf = io.BytesIO()
    n_samples = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(amplitude * math.sin(2.0 * math.pi * 440.0 * i / sample_rate)) if amplitude > 0 else 0
            frames += struct.pack("<h", val)
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def test_corrupted_audio_rejected_by_storage():
    with pytest.raises(Exception) as exc_info:
        StorageService.save_audio_file(
            file_bytes=b"NOT_A_REAL_AUDIO_FILE_BYTES_1234567890" * 5,
            original_filename="corrupt.webm",
            meeting_id="MTG-TEST-CORRUPT",
            validate_audio=True,
        )
    assert "decoded" in str(exc_info.value).lower() or "400" in str(exc_info.value)


def test_silence_detection_blocks_whisper_and_never_fakes_transcript():
    silent_wav = _make_wav_bytes(duration_sec=1.5, amplitude=0)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(silent_wav)
        temp_path = tf.name

    try:
        diag = StorageService.inspect_audio_file(temp_path)
        assert diag["decodable"] is True
        assert diag["sample_rate"] == 16000
        assert diag["channels"] == 1
        assert diag["duration_seconds"] >= 1.4
        assert diag["is_silent"] is True
        assert diag["has_speech_signal"] is False

        res = TranscriptionAgent.execute(temp_path, audio_diagnostics=diag)
        assert res["status"] == "no_speech"
        assert res["speech_detected"] is False
        assert res["full_text"] == ""
        assert res["segments"] == []
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_non_silent_audio_passes_validation_and_deduplicates():
    tone_wav = _make_wav_bytes(duration_sec=1.2, amplitude=8000)
    meta1 = StorageService.save_audio_file(
        file_bytes=tone_wav,
        original_filename="test_tone.wav",
        meeting_id="MTG-TEST-TONE",
        content_type="audio/wav",
        validate_audio=True,
    )
    meta2 = StorageService.save_audio_file(
        file_bytes=tone_wav,
        original_filename="test_tone.wav",
        meeting_id="MTG-TEST-TONE",
        content_type="audio/wav",
        validate_audio=True,
    )
    try:
        assert meta1["diagnostics"]["decodable"] is True
        assert meta1["diagnostics"]["is_silent"] is False
        assert meta1["diagnostics"]["has_speech_signal"] is True
        assert meta2["deduplicated"] is True
        assert meta1["storage_path"] == meta2["storage_path"]
    finally:
        if os.path.exists(meta1["storage_path"]):
            os.remove(meta1["storage_path"])


def test_transcription_error_never_returns_fake_dialogue():
    tone_wav = _make_wav_bytes(duration_sec=1.0, amplitude=8000)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(tone_wav)
        temp_path = tf.name

    try:
        # 1. Missing API key
        with patch.object(settings, "GROQ_API_KEY", ""):
            res = TranscriptionAgent.execute(temp_path)
            assert res["status"] == "error"
            assert res["error_code"] == "auth_error"
            assert res["full_text"] == ""
            assert "Jai:" not in res["full_text"]

        # 2. Mocked Groq rate limit error
        with patch.object(settings, "GROQ_API_KEY", "gsk_test_key"):
            with patch("app.agents.transcription_agent.Groq") as mock_groq:
                mock_client = MagicMock()
                mock_client.audio.transcriptions.create.side_effect = RuntimeError("429 rate_limit_exceeded")
                mock_groq.return_value = mock_client

                res = TranscriptionAgent.execute(temp_path)
                assert res["status"] == "error"
                assert res["error_code"] == "rate_limit"
                assert res["full_text"] == ""
                assert res["segments"] == []
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_single_person_diarization_attributes_to_host():
    segments = [
        {"segment_id": 1, "start": 0.0, "end": 3.5, "text": "I will finish the audio validation module by Friday."},
        {"segment_id": 2, "start": 3.8, "end": 6.2, "text": "Also we need to update the UI waveform."},
    ]
    res = DiarizationAgent.execute(segments=segments, participants=[], host_name="Mano Ranjan")
    assert res["status"] == "success"
    assert res["total_speakers"] == 1
    assert all(s["speaker_label"] == "Mano Ranjan" for s in res["diarized_segments"])


def test_analyst_and_task_extraction_never_swallow_groq_errors():
    with patch.object(settings, "GROQ_API_KEY", ""):
        a_res = MeetingAnalystAgent.execute("Some real transcript text.", [])
        assert a_res["status"] == "error"
        assert a_res["error_code"] == "auth_error"

        t_res = TaskExtractionAgent.execute("I will fix the bug.", [])
        assert t_res["status"] == "error"
        assert t_res["error_code"] == "auth_error"


@pytest.mark.anyio
async def test_langgraph_reuses_transcript_and_prevents_duplicate_tasks():
    assert settings.ENABLE_AUTOMATION_DISPATCH is False

    from app.database.mongo import connect_to_mongo, get_col
    connect_to_mongo()
    mid = "MTG-TEST-RETRY-IDEMP"
    tid = "team_test_retry"

    try:
        mock_analyst = {
            "status": "success",
            "meeting_summary": "Host agreed to fix audio capture.",
            "discussion_topics": ["Audio capture"],
            "key_decisions": ["Use WebM Opus"],
            "unresolved_questions": [],
            "important_outcomes": ["Improved capture"],
        }
        mock_tasks = {
            "status": "success",
            "extracted_tasks": [
                {
                    "title": "Fix audio capture",
                    "description": "Fix MediaRecorder",
                    "related_discussion": "Audio capture",
                    "requester": None,
                    "explicit_owner": "Mano Ranjan",
                    "is_explicit_commitment": True,
                    "deadline": "Friday",
                    "priority": "High",
                    "required_skills": ["React"],
                    "evidence": "I will fix audio capture by Friday.",
                    "timestamp": "00:00",
                    "confidence": 0.95,
                }
            ],
        }

        with patch("app.workflows.meeting_graph.MeetingAnalystAgent.execute", return_value=mock_analyst), \
             patch("app.workflows.meeting_graph.TaskExtractionAgent.execute", return_value=mock_tasks):
            state = {
                "meeting_id": mid,
                "team_id": tid,
                "meeting_title": "Solo Sync",
                "audio_path": "",
                "force_retranscribe": False,
                "host_name": "Mano Ranjan",
                "participants": [{"member_id": "MEM-1", "name": "Mano Ranjan", "role": "Host", "email": "mano@example.com"}],
                "selected_participant_ids": ["MEM-1"],
                "transcript_text": "I will fix audio capture by Friday.",
                "transcript_segments": [{"segment_id": 1, "start": 0.0, "end": 4.0, "text": "I will fix audio capture by Friday."}],
            }
            # Run twice (simulating Retry AI Analysis)
            await run_meeting_workflow(dict(state))
            final = await run_meeting_workflow(dict(state))

            assert final["status"] == "Completed"
            assert final["automation_dispatched"] is False

            tasks_col = get_col("tasks")
            saved_tasks = list(tasks_col.find({"team_id": tid, "meeting_id": mid}))
            assert len(saved_tasks) == 1
            assert saved_tasks[0]["assigned_member_name"] == "Mano Ranjan"
            assert saved_tasks[0]["timestamp"] == "00:00"
    finally:
        get_col("meetings").delete_many({"meeting_id": mid})
        get_col("tasks").delete_many({"meeting_id": mid})
        get_col("transcript_segments").delete_many({"meeting_id": mid})
