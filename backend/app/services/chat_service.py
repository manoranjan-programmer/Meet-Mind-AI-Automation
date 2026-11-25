import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from fastapi import WebSocket
from app.database.mongo import get_col

logger = logging.getLogger("meetmind.chat")

class WorkspaceChatManager:
    """
    Manages active WebSocket connections for private workspace group chats.
    Guarantees strict team isolation: messages and presence from Team A are never
    broadcast or leaked to Team B.
    """
    def __init__(self):
        # team_id -> user_id -> List[WebSocket]
        self._active_connections: Dict[str, Dict[str, List[WebSocket]]] = {}

    async def connect(self, team_id: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if team_id not in self._active_connections:
            self._active_connections[team_id] = {}
        if user_id not in self._active_connections[team_id]:
            self._active_connections[team_id][user_id] = []
            # Broadcast user came online to this team
            await self.broadcast_to_team(
                team_id=team_id,
                event="member_online",
                data={"user_id": user_id, "timestamp": datetime.utcnow().isoformat()},
                exclude_user_id=user_id
            )
        self._active_connections[team_id][user_id].append(websocket)
        logger.info(f"[WorkspaceChat] User '{user_id}' connected to team '{team_id}' chat")

    async def disconnect(self, team_id: str, user_id: str, websocket: WebSocket):
        if team_id in self._active_connections and user_id in self._active_connections[team_id]:
            try:
                self._active_connections[team_id][user_id].remove(websocket)
            except ValueError:
                pass
            if not self._active_connections[team_id][user_id]:
                del self._active_connections[team_id][user_id]
                # Broadcast member offline to this team
                await self.broadcast_to_team(
                    team_id=team_id,
                    event="member_offline",
                    data={"user_id": user_id, "timestamp": datetime.utcnow().isoformat()}
                )
            if not self._active_connections[team_id]:
                del self._active_connections[team_id]
        logger.info(f"[WorkspaceChat] User '{user_id}' disconnected from team '{team_id}' chat")

    async def broadcast_to_team(
        self,
        team_id: str,
        event: str,
        data: Dict[str, Any],
        exclude_user_id: Optional[str] = None
    ):
        """Broadcasts event strictly to members of the specified team_id."""
        if team_id not in self._active_connections:
            return
        
        dead_sockets = []
        payload = {"event": event, "data": data}

        for uid, sockets in self._active_connections[team_id].items():
            if exclude_user_id and uid == exclude_user_id:
                continue
            for ws in sockets:
                try:
                    await ws.send_json(payload)
                except Exception as e:
                    logger.warning(f"[WorkspaceChat] Error sending to socket: {e}")
                    dead_sockets.append((uid, ws))

        # Cleanup dead sockets
        for uid, ws in dead_sockets:
            if team_id in self._active_connections and uid in self._active_connections[team_id]:
                try:
                    self._active_connections[team_id][uid].remove(ws)
                except ValueError:
                    pass

    def is_user_online(self, team_id: str, user_id: str) -> bool:
        return bool(self._active_connections.get(team_id, {}).get(user_id))

    def get_online_user_ids(self, team_id: str) -> List[str]:
        return list(self._active_connections.get(team_id, {}).keys())

chat_manager = WorkspaceChatManager()

class ChatService:
    @staticmethod
    def send_message(
        team_id: str,
        sender_user: dict,
        content: str,
        attachment_url: Optional[str] = None,
        attachment_type: Optional[str] = None,
        attachment_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates and persists a message in MongoDB workspace_messages collection
        and schedules real-time broadcast to all connected team members.
        """
        now = datetime.utcnow()
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"

        message_doc = {
            "message_id": msg_id,
            "team_id": team_id,
            "sender_id": sender_user.get("user_id"),
            "sender_name": sender_user.get("name") or sender_user.get("email").split("@")[0],
            "sender_email": sender_user.get("email"),
            "sender_avatar": sender_user.get("profile_image"),
            "sender_role": sender_user.get("role") or sender_user.get("effective_role", "Member"),
            "content": content.strip(),
            "attachment_url": attachment_url,
            "attachment_type": attachment_type,
            "attachment_name": attachment_name,
            "is_edited": False,
            "read_by": [sender_user.get("user_id")],
            "created_at": now,
            "updated_at": now
        }

        col = get_col("workspace_messages")
        col.insert_one(message_doc)
        message_doc.pop("_id", None)
        return message_doc

    @staticmethod
    def get_messages(
        team_id: str,
        user_id: str,
        limit: int = 50,
        before: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves chat messages for this workspace in chronological order with pagination.
        Also marks fetched messages as read by this user.
        """
        col = get_col("workspace_messages")
        query: Dict[str, Any] = {"team_id": team_id}
        if before:
            try:
                before_dt = datetime.fromisoformat(before)
                query["created_at"] = {"$lt": before_dt}
            except Exception:
                pass

        total_count = col.count_documents({"team_id": team_id})
        # Fetch latest 'limit' messages
        cursor = col.find(query).sort("created_at", -1).limit(limit)
        docs = list(cursor)
        docs.reverse()  # Chronological order for chat display

        for d in docs:
            d.pop("_id", None)

        # Mark unread messages as read by this user
        col.update_many(
            {"team_id": team_id, "read_by": {"$ne": user_id}},
            {"$addToSet": {"read_by": user_id}}
        )

        return {
            "team_id": team_id,
            "messages": docs,
            "total_count": total_count,
            "has_more": len(docs) == limit
        }

    @staticmethod
    def edit_message(
        team_id: str,
        message_id: str,
        user_id: str,
        user_role: str,
        new_content: str
    ) -> Dict[str, Any]:
        """Edits message content. Only author or Team Leader can edit."""
        col = get_col("workspace_messages")
        msg = col.find_one({"team_id": team_id, "message_id": message_id})
        if not msg:
            raise ValueError(f"Message '{message_id}' not found.")

        # Check permissions: author or Team Leader
        if msg["sender_id"] != user_id and user_role not in ["Team Leader", "Team Lead", "Admin"]:
            raise PermissionError("You do not have permission to edit this message.")

        now = datetime.utcnow()
        col.update_one(
            {"_id": msg["_id"]},
            {"$set": {"content": new_content.strip(), "is_edited": True, "updated_at": now}}
        )
        msg["content"] = new_content.strip()
        msg["is_edited"] = True
        msg["updated_at"] = now
        msg.pop("_id", None)
        return msg

    @staticmethod
    def delete_message(
        team_id: str,
        message_id: str,
        user_id: str,
        user_role: str
    ) -> Dict[str, Any]:
        """Deletes message. Only author or Team Leader can delete."""
        col = get_col("workspace_messages")
        msg = col.find_one({"team_id": team_id, "message_id": message_id})
        if not msg:
            raise ValueError(f"Message '{message_id}' not found.")

        if msg["sender_id"] != user_id and user_role not in ["Team Leader", "Team Lead", "Admin"]:
            raise PermissionError("You do not have permission to delete this message.")

        col.delete_one({"_id": msg["_id"]})
        return {"status": "deleted", "message_id": message_id, "team_id": team_id}

    @staticmethod
    def get_unread_count(team_id: str, user_id: str) -> int:
        col = get_col("workspace_messages")
        return col.count_documents({
            "team_id": team_id,
            "sender_id": {"$ne": user_id},
            "read_by": {"$ne": user_id}
        })

    @staticmethod
    def get_chat_members(team_id: str) -> Dict[str, Any]:
        """Returns workspace members with online presence flags."""
        member_col = get_col("member_profiles")
        members = list(member_col.find({"team_id": team_id, "account_status": "active"}))
        
        online_uids = set(chat_manager.get_online_user_ids(team_id))
        member_items = []
        for m in members:
            # Check online status by member_id or by user account ID
            is_on = m.get("member_id") in online_uids or m.get("user_id") in online_uids
            member_items.append({
                "member_id": m.get("member_id"),
                "name": m.get("name"),
                "email": m.get("email"),
                "role": m.get("role", "Member"),
                "profile_image": m.get("profile_image"),
                "is_online": is_on,
                "last_seen": datetime.utcnow() if is_on else None
            })

        online_count = sum(1 for item in member_items if item["is_online"])
        return {
            "team_id": team_id,
            "total_members": len(member_items),
            "online_count": online_count,
            "members": member_items
        }
