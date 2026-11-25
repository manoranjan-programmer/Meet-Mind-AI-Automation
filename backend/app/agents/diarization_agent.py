import re
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("meetmind.agent3")


class DiarizationAgent:
    """
    Agent 3: Speaker Diarization Agent
    Responsibilities:
      - Identifies distinct speaker turns / clusters from transcript segments
      - Preserves timestamps on every segment
      - In a single-member workspace/meeting, attributes all spoken segments to the verified host
      - In multi-participant meetings, maps verified self-identifications, explicit prefixes, or manual mappings
      - Never invents fake speakers or assumes Speaker 1 is always host in multi-participant meetings without evidence
    """
    AGENT_ID = 3
    NAME = "Speaker Diarization Agent"

    @staticmethod
    def execute(
        segments: List[Dict[str, Any]],
        participants: Optional[List[Any]] = None,
        manual_mappings: Optional[Dict[str, str]] = None,
        host_name: Optional[str] = None,
        active_attendees: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[{DiarizationAgent.NAME}] Running diarization for {len(segments)} segments")

        if not segments:
            return {
                "status": "success",
                "diarized_segments": [],
                "speaker_catalog": [],
                "total_speakers": 0,
                "execution_duration": round(time.time() - start_time, 3),
            }

        try:
            diarized_segments: List[Dict[str, Any]] = []
            speaker_catalog: Dict[str, Dict[str, Any]] = {}
            speaker_counter = 1

            # Build lookup of registered participants (preferring actual connected live attendees if provided)
            participant_source = active_attendees if (active_attendees and len(active_attendees) > 0) else (participants or [])
            participant_by_name: Dict[str, Dict[str, Any]] = {}
            active_names: List[str] = []
            for p in participant_source:
                if isinstance(p, dict):
                    full_name = (p.get("name") or "").strip()
                    if full_name:
                        participant_by_name[full_name.lower()] = p
                        if full_name not in active_names:
                            active_names.append(full_name)
                elif isinstance(p, str):
                    full_name = p.strip()
                    if full_name and full_name not in active_names:
                        active_names.append(full_name)

            # Single-speaker live session: only 1 authenticated participant connected (or solo workspace)
            is_single_member = len(active_names) == 1 or (len(active_names) == 0 and bool(host_name and host_name.strip()))
            sole_member_name = active_names[0] if len(active_names) == 1 else (host_name.strip() if host_name else "")
            sole_meta = participant_by_name.get(sole_member_name.lower(), {}) if sole_member_name else {}

            if is_single_member and sole_member_name:
                speaker_catalog["Speaker 1"] = {
                    "speaker_id": "Speaker 1",
                    "speaker_label": sole_member_name,
                    "suggested_name": sole_member_name,
                    "member_id": sole_meta.get("member_id"),
                    "email": sole_meta.get("email"),
                    "role": sole_meta.get("role"),
                    "verified": True,
                    "confidence": 1.0,
                    "voice_signature": f"VOX-{abs(hash(sole_member_name)) % 10000:04d}",
                }

                for idx, seg in enumerate(segments):
                    text = (seg.get("text") or "").strip()
                    diarized_segments.append({
                        "segment_id": seg.get("segment_id", idx + 1),
                        "speaker_id": "Speaker 1",
                        "speaker_label": sole_member_name,
                        "suggested_name": sole_member_name,
                        "member_id": sole_meta.get("member_id"),
                        "email": sole_meta.get("email"),
                        "verified": True,
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": text,
                    })

                return {
                    "status": "success",
                    "diarized_segments": diarized_segments,
                    "speaker_catalog": list(speaker_catalog.values()),
                    "total_speakers": 1,
                    "execution_duration": round(time.time() - start_time, 3),
                }

            last_addressed_speaker = None
            current_unverified_speaker_id = "Speaker 1"

            def _get_or_create_verified_speaker(name: str, conf: float) -> str:
                nonlocal speaker_counter
                for sid, sinfo in speaker_catalog.items():
                    if sinfo.get("suggested_name") == name:
                        return sid
                new_sid = f"Speaker {speaker_counter}"
                speaker_counter += 1
                speaker_catalog[new_sid] = {
                    "speaker_id": new_sid,
                    "speaker_label": name,
                    "suggested_name": name,
                    "verified": True,
                    "confidence": conf,
                    "voice_signature": f"VOX-{abs(hash(name)) % 10000:04d}",
                }
                return new_sid

            for idx, seg in enumerate(segments):
                text = (seg.get("text") or "").strip()
                speaker_match = re.match(r"^([A-Z][a-zA-Z\s]{1,20}):\s*(.*)", text)

                self_id_match = None
                for p_name in active_names:
                    pattern = (
                        rf"\b(?:this is|i am|i'm|it's|it is|here is|my name is)\s+{re.escape(p_name)}\b"
                        rf"|\b{re.escape(p_name)}\s+(?:here|speaking)\b"
                    )
                    if re.search(pattern, text, re.IGNORECASE):
                        self_id_match = p_name
                        break

                addressed_match = None
                for p_name in active_names:
                    addr_pattern = rf"\b(?:hey|hi|hello)?\s*{re.escape(p_name)}\s*[,!?]|\b(?:can you|could you|please)\s+{re.escape(p_name)}\b"
                    if re.search(addr_pattern, text, re.IGNORECASE):
                        addressed_match = p_name
                        break

                if speaker_match:
                    identified_name = speaker_match.group(1).strip()
                    speech_text = speaker_match.group(2).strip()
                    speaker_id = _get_or_create_verified_speaker(identified_name, 0.95)
                    last_addressed_speaker = addressed_match

                elif self_id_match:
                    speech_text = text
                    speaker_id = _get_or_create_verified_speaker(self_id_match, 0.90)
                    last_addressed_speaker = addressed_match

                elif last_addressed_speaker and re.search(r"\b(?:yes|sure|i will|i'll|i can|absolutely|done|on it|okay|ok)\b", text, re.IGNORECASE):
                    speech_text = text
                    speaker_id = _get_or_create_verified_speaker(last_addressed_speaker, 0.88)
                    last_addressed_speaker = None

                else:
                    speech_text = text
                    # Keep speaker consistent unless a pause > 1.5s suggests a potential turn change
                    prev_end = segments[idx - 1].get("end", 0.0) if idx > 0 else 0.0
                    cur_start = seg.get("start", 0.0)
                    if idx > 0 and len(active_names) > 1 and (cur_start - prev_end) > 1.5:
                        next_cluster = (len(speaker_catalog) % max(1, len(active_names))) + 1
                        current_unverified_speaker_id = f"Speaker {next_cluster}"

                    speaker_id = current_unverified_speaker_id
                    manual_name = (manual_mappings or {}).get(speaker_id)
                    if manual_name:
                        suggested_name = manual_name
                        verified = True
                        conf = 1.0
                        label = manual_name
                    else:
                        suggested_name = "Unknown Speaker"
                        verified = False
                        conf = 0.50
                        label = speaker_id

                    if speaker_id not in speaker_catalog:
                        speaker_catalog[speaker_id] = {
                            "speaker_id": speaker_id,
                            "speaker_label": label,
                            "suggested_name": suggested_name,
                            "verified": verified,
                            "confidence": conf,
                            "voice_signature": f"VOX-CLUSTER-{len(speaker_catalog) + 1:02d}",
                        }
                    last_addressed_speaker = addressed_match

                current_speaker_meta = speaker_catalog.get(speaker_id, {})
                diarized_segments.append({
                    "segment_id": seg.get("segment_id", idx + 1),
                    "speaker_id": speaker_id,
                    "speaker_label": current_speaker_meta.get("speaker_label", speaker_id),
                    "suggested_name": current_speaker_meta.get("suggested_name", "Unknown Speaker"),
                    "verified": current_speaker_meta.get("verified", False),
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": speech_text,
                })

            return {
                "status": "success",
                "diarized_segments": diarized_segments,
                "speaker_catalog": list(speaker_catalog.values()),
                "total_speakers": len(speaker_catalog),
                "execution_duration": round(time.time() - start_time, 3),
            }
        except Exception as e:
            logger.error(f"[{DiarizationAgent.NAME}] Diarization failed gracefully: {e}")
            # Preserve transcript segments even if diarization fails
            fallback_segs = [
                {
                    "segment_id": s.get("segment_id", i + 1),
                    "speaker_id": "Speaker 1",
                    "speaker_label": "Speaker 1",
                    "suggested_name": "Unknown Speaker",
                    "verified": False,
                    "start": s.get("start", 0.0),
                    "end": s.get("end", 0.0),
                    "text": (s.get("text") or "").strip(),
                }
                for i, s in enumerate(segments)
            ]
            return {
                "status": "partial",
                "error": str(e),
                "diarized_segments": fallback_segs,
                "speaker_catalog": [],
                "total_speakers": 1 if fallback_segs else 0,
                "execution_duration": round(time.time() - start_time, 3),
            }
