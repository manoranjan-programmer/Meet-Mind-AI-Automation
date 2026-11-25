from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000, description="Message text content")
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    attachment_name: Optional[str] = None

class ChatMessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000, description="Updated message text content")

class ChatMessageResponse(BaseModel):
    message_id: str
    team_id: str
    sender_id: str
    sender_name: str
    sender_email: str
    sender_avatar: Optional[str] = None
    sender_role: str = "Member"
    content: str
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    attachment_name: Optional[str] = None
    is_edited: bool = False
    read_by: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class ChatMessageListResponse(BaseModel):
    team_id: str
    messages: List[ChatMessageResponse]
    total_count: int
    has_more: bool = False

class ChatMemberItem(BaseModel):
    member_id: str
    name: str
    email: str
    role: str
    profile_image: Optional[str] = None
    is_online: bool = False
    last_seen: Optional[datetime] = None

class ChatMemberListResponse(BaseModel):
    team_id: str
    total_members: int
    online_count: int
    members: List[ChatMemberItem]

class UnreadCountResponse(BaseModel):
    team_id: str
    unread_count: int
