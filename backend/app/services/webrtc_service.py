import json
import logging
from typing import Dict, Any, Optional, List
from fastapi import WebSocket

logger = logging.getLogger("meetmind.webrtc")

class MeetingSignalingManager:
    """
    FastAPI WebSocket Signaling Server for WebRTC multi-user peer-to-peer mesh.
    Relays SDP offers, answers, ICE candidates, track toggles, and room state.
    Designed for small-to-medium team collaboration (up to 6-8 participants per mesh).
    For 10+ participants, SFU (Selective Forwarding Unit) architecture is recommended.
    """
    def __init__(self):
        # meeting_id -> peer_id -> peer_info
        self._rooms: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def join_room(
        self,
        meeting_id: str,
        peer_id: str,
        user_info: Dict[str, Any],
        websocket: WebSocket
    ):
        if meeting_id not in self._rooms:
            self._rooms[meeting_id] = {}

        # Save peer registration
        peer_data = {
            "websocket": websocket,
            "peer_id": peer_id,
            "user_id": user_info.get("user_id"),
            "name": user_info.get("name") or "Participant",
            "role": user_info.get("role") or "Member",
            "is_host": bool(user_info.get("is_host")),
            "video_enabled": user_info.get("video_enabled", False),
            "audio_enabled": user_info.get("audio_enabled", True),
            "screen_sharing": False
        }

        # 1. Gather existing peers to inform the new entrant
        existing_peers = [
            {
                "peer_id": pid,
                "user_id": pdata["user_id"],
                "name": pdata["name"],
                "role": pdata["role"],
                "is_host": pdata["is_host"],
                "video_enabled": pdata["video_enabled"],
                "audio_enabled": pdata["audio_enabled"],
                "screen_sharing": pdata["screen_sharing"]
            }
            for pid, pdata in self._rooms[meeting_id].items()
        ]

        # Register current peer
        self._rooms[meeting_id][peer_id] = peer_data

        # 2. Send room state & existing peers list to the new peer
        await websocket.send_json({
            "event": "room_joined",
            "data": {
                "meeting_id": meeting_id,
                "peer_id": peer_id,
                "existing_peers": existing_peers
            }
        })

        # 3. Notify all existing peers that a new peer joined
        new_peer_notice = {
            "peer_id": peer_id,
            "user_id": peer_data["user_id"],
            "name": peer_data["name"],
            "role": peer_data["role"],
            "is_host": peer_data["is_host"],
            "video_enabled": peer_data["video_enabled"],
            "audio_enabled": peer_data["audio_enabled"]
        }
        await self.broadcast_to_room(
            meeting_id=meeting_id,
            event="peer_joined",
            data=new_peer_notice,
            exclude_peer_id=peer_id
        )

        logger.info(f"[WebRTC] Peer '{peer_id}' ({peer_data['name']}) joined meeting '{meeting_id}' (Total peers: {len(self._rooms[meeting_id])})")

    async def leave_room(self, meeting_id: str, peer_id: str):
        if meeting_id in self._rooms and peer_id in self._rooms[meeting_id]:
            leaving_peer = self._rooms[meeting_id].pop(peer_id)
            # Notify remaining peers
            await self.broadcast_to_room(
                meeting_id=meeting_id,
                event="peer_left",
                data={"peer_id": peer_id, "name": leaving_peer.get("name")}
            )
            if not self._rooms[meeting_id]:
                del self._rooms[meeting_id]
            logger.info(f"[WebRTC] Peer '{peer_id}' left meeting '{meeting_id}'")

    async def relay_signal(
        self,
        meeting_id: str,
        from_peer_id: str,
        target_peer_id: str,
        event: str,
        signal_data: Dict[str, Any]
    ):
        """Relays WebRTC offer, answer, or ice_candidate directly to targeted peer."""
        room = self._rooms.get(meeting_id)
        if not room:
            return
        target = room.get(target_peer_id)
        if target:
            try:
                await target["websocket"].send_json({
                    "event": event,
                    "data": {
                        "from_peer_id": from_peer_id,
                        "signal": signal_data
                    }
                })
            except Exception as e:
                logger.warning(f"[WebRTC] Failed to relay signal to peer '{target_peer_id}': {e}")

    async def update_track_state(
        self,
        meeting_id: str,
        peer_id: str,
        video_enabled: Optional[bool] = None,
        audio_enabled: Optional[bool] = None,
        screen_sharing: Optional[bool] = None
    ):
        room = self._rooms.get(meeting_id)
        if not room or peer_id not in room:
            return
        peer = room[peer_id]
        if video_enabled is not None:
            peer["video_enabled"] = video_enabled
        if audio_enabled is not None:
            peer["audio_enabled"] = audio_enabled
        if screen_sharing is not None:
            peer["screen_sharing"] = screen_sharing

        await self.broadcast_to_room(
            meeting_id=meeting_id,
            event="track_state_changed",
            data={
                "peer_id": peer_id,
                "video_enabled": peer["video_enabled"],
                "audio_enabled": peer["audio_enabled"],
                "screen_sharing": peer["screen_sharing"]
            }
        )

    async def broadcast_chat_message(
        self,
        meeting_id: str,
        from_peer_id: str,
        sender_name: str,
        text: str
    ):
        await self.broadcast_to_room(
            meeting_id=meeting_id,
            event="meeting_chat_message",
            data={
                "from_peer_id": from_peer_id,
                "sender_name": sender_name,
                "text": text
            }
        )

    async def broadcast_to_room(
        self,
        meeting_id: str,
        event: str,
        data: Dict[str, Any],
        exclude_peer_id: Optional[str] = None
    ):
        room = self._rooms.get(meeting_id)
        if not room:
            return

        dead_peers = []
        payload = {"event": event, "data": data}

        for pid, pdata in room.items():
            if exclude_peer_id and pid == exclude_peer_id:
                continue
            try:
                await pdata["websocket"].send_json(payload)
            except Exception as e:
                logger.warning(f"[WebRTC] Error broadcasting to peer '{pid}': {e}")
                dead_peers.append(pid)

        for pid in dead_peers:
            if meeting_id in self._rooms and pid in self._rooms[meeting_id]:
                del self._rooms[meeting_id][pid]

    def get_room_peers(self, meeting_id: str) -> List[Dict[str, Any]]:
        room = self._rooms.get(meeting_id, {})
        return [
            {
                "peer_id": pid,
                "user_id": pdata["user_id"],
                "name": pdata["name"],
                "role": pdata["role"],
                "is_host": pdata["is_host"],
                "video_enabled": pdata["video_enabled"],
                "audio_enabled": pdata["audio_enabled"],
                "screen_sharing": pdata["screen_sharing"]
            }
            for pid, pdata in room.items()
        ]

    def is_peer_host(self, meeting_id: str, peer_id: Optional[str]) -> bool:
        peer = self._rooms.get(meeting_id, {}).get(peer_id or "")
        return bool(peer and peer.get("is_host"))

meeting_signaling_manager = MeetingSignalingManager()
