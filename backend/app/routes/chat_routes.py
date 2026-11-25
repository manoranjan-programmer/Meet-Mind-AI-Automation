import json
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from app.middleware.auth import get_current_user
from app.middleware.workspace_auth import require_workspace_member, verify_workspace_access
from app.utils.security import decode_access_token
from app.database.mongo import get_col
from app.schemas.chat_schemas import (
    ChatMessageCreate,
    ChatMessageUpdate,
    ChatMessageResponse,
    ChatMessageListResponse,
    ChatMemberListResponse,
    UnreadCountResponse
)
from app.services.chat_service import ChatService, chat_manager

logger = logging.getLogger("meetmind.chat_routes")
router = APIRouter(prefix="/workspaces", tags=["Workspace Chat"])
ws_router = APIRouter(tags=["Workspace Chat WebSocket"])

# ----------------- HTTP REST ENDPOINTS ----------------- #

@router.get("/{team_id}/chat/messages", response_model=ChatMessageListResponse)
def get_chat_messages(
    team_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None),
    member_user: dict = Depends(require_workspace_member)
):
    """
    Retrieves chronological message history for the workspace group chat.
    Enforces active membership in the workspace.
    """
    user_id = member_user.get("user_id")
    result = ChatService.get_messages(
        team_id=team_id,
        user_id=user_id,
        limit=limit,
        before=before
    )
    return result

@router.post("/{team_id}/chat/messages", response_model=ChatMessageResponse, status_code=201)
async def post_chat_message(
    team_id: str,
    req: ChatMessageCreate,
    member_user: dict = Depends(require_workspace_member)
):
    """
    Sends a message to the workspace group chat and broadcasts it in real-time.
    """
    msg = ChatService.send_message(
        team_id=team_id,
        sender_user=member_user,
        content=req.content,
        attachment_url=req.attachment_url,
        attachment_type=req.attachment_type,
        attachment_name=req.attachment_name
    )

    # Broadcast to team members connected via WebSocket
    await chat_manager.broadcast_to_team(
        team_id=team_id,
        event="message_created",
        data=msg
    )

    return msg

@router.patch("/{team_id}/chat/messages/{message_id}", response_model=ChatMessageResponse)
async def edit_chat_message(
    team_id: str,
    message_id: str,
    req: ChatMessageUpdate,
    member_user: dict = Depends(require_workspace_member)
):
    """
    Edits a message. Authorized only for the original sender or Team Leader.
    """
    try:
        updated = ChatService.edit_message(
            team_id=team_id,
            message_id=message_id,
            user_id=member_user.get("user_id"),
            user_role=member_user.get("effective_role", "Member"),
            new_content=req.content
        )
        await chat_manager.broadcast_to_team(
            team_id=team_id,
            event="message_edited",
            data=updated
        )
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))

@router.delete("/{team_id}/chat/messages/{message_id}")
async def delete_chat_message(
    team_id: str,
    message_id: str,
    member_user: dict = Depends(require_workspace_member)
):
    """
    Deletes a message. Authorized only for the original sender or Team Leader.
    """
    try:
        res = ChatService.delete_message(
            team_id=team_id,
            message_id=message_id,
            user_id=member_user.get("user_id"),
            user_role=member_user.get("effective_role", "Member")
        )
        await chat_manager.broadcast_to_team(
            team_id=team_id,
            event="message_deleted",
            data={"message_id": message_id, "team_id": team_id}
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))

@router.get("/{team_id}/chat/members", response_model=ChatMemberListResponse)
def get_chat_members(
    team_id: str,
    member_user: dict = Depends(require_workspace_member)
):
    """
    Returns active workspace members and their real-time presence indicators.
    """
    return ChatService.get_chat_members(team_id=team_id)

@router.get("/{team_id}/chat/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    team_id: str,
    member_user: dict = Depends(require_workspace_member)
):
    """Returns number of unread messages for this user in this workspace."""
    count = ChatService.get_unread_count(team_id=team_id, user_id=member_user.get("user_id"))
    return {"team_id": team_id, "unread_count": count}

# ----------------- REAL-TIME WEBSOCKET ----------------- #

@ws_router.websocket("/ws/workspaces/{team_id}/chat")
async def workspace_chat_websocket(
    websocket: WebSocket,
    team_id: str,
    token: Optional[str] = Query(None)
):
    """
    FastAPI WebSocket endpoint for private workspace group chats.
    Authenticates sender, verifies active workspace membership, and broadcasts events.
    """
    # 1. Authenticate WebSocket connection
    if not token:
        # Check Authorization header if available
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    payload = decode_access_token(token)
    if not payload or not payload.get("user_id"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("user_id")
    users_col = get_col("users")
    user = users_col.find_one({"user_id": user_id})
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Verify active workspace membership
    try:
        verified_member = verify_workspace_access(team_id=team_id, current_user=user)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Connect to team room
    await chat_manager.connect(team_id=team_id, user_id=user_id, websocket=websocket)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                msg_payload = json.loads(text_data)
                event_type = msg_payload.get("event")
                data = msg_payload.get("data", {})

                if event_type == "send_message":
                    content = data.get("content", "").strip()
                    if content:
                        new_msg = ChatService.send_message(
                            team_id=team_id,
                            sender_user=verified_member,
                            content=content,
                            attachment_url=data.get("attachment_url"),
                            attachment_type=data.get("attachment_type"),
                            attachment_name=data.get("attachment_name")
                        )
                        await chat_manager.broadcast_to_team(
                            team_id=team_id,
                            event="message_created",
                            data=new_msg
                        )

                elif event_type == "typing":
                    # Broadcast typing indicator to other team members
                    await chat_manager.broadcast_to_team(
                        team_id=team_id,
                        event="typing",
                        data={"user_id": user_id, "name": verified_member.get("name"), "is_typing": data.get("is_typing", True)},
                        exclude_user_id=user_id
                    )

                elif event_type == "mark_read":
                    ChatService.mark_messages_read(team_id=team_id, user_id=user_id)
                    await chat_manager.broadcast_to_team(
                        team_id=team_id,
                        event="message_read",
                        data={"user_id": user_id, "team_id": team_id}
                    )

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"[WorkspaceChat WS] Error handling socket message: {e}")

    except WebSocketDisconnect:
        await chat_manager.disconnect(team_id=team_id, user_id=user_id, websocket=websocket)
    except Exception as e:
        logger.error(f"[WorkspaceChat WS] Unexpected error: {e}")
        await chat_manager.disconnect(team_id=team_id, user_id=user_id, websocket=websocket)
