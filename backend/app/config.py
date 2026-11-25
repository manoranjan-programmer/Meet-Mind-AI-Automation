from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "MeetMind AI"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "meetmind_ai"
    
    # Security
    JWT_SECRET: str = "meetmind-super-secure-jwt-secret-key-32chars-min-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 1440  # 24 hours
    INVITATION_EXPIRE_HOURS: int = 168  # 7 days
    
    # AI Services (Groq)
    GROQ_API_KEY: Optional[str] = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    WHISPER_MODEL: str = "whisper-large-v3"
    HF_TOKEN: Optional[str] = None
    ENABLE_AUTOMATION_DISPATCH: bool = False
    
    # Audio Storage
    UPLOAD_DIR: str = "uploads"
    MAX_AUDIO_SIZE_MB: int = 50
    
    # Automation (Zapier Webhooks)
    ZAPIER_TASK_APPROVED_WEBHOOK_URL: Optional[str] = None
    ZAPIER_APPROVED_TASK_WEBHOOK_URL: Optional[str] = None
    ZAPIER_WEBHOOK_URL: Optional[str] = None
    
    ZAPIER_MEETING_COMPLETED_WEBHOOK_URL: Optional[str] = None
    MEETING_INVITATION_WEBHOOK_URL: Optional[str] = None
    ZAPIER_MEETING_SCHEDULED_WEBHOOK_URL: Optional[str] = None
    ZAPIER_TASK_COMPLETED_WEBHOOK_URL: Optional[str] = None
    ZAPIER_TEAM_MEMBER_ADDED_WEBHOOK_URL: Optional[str] = None
    ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL: Optional[str] = None
    
    # Automation Outbox & Startup Replay Settings
    ENABLE_STARTUP_OUTBOX_DISPATCH: bool = False
    ENABLE_OUTBOX_BACKGROUND_WORKER: bool = False
    OUTBOX_MAX_EVENT_AGE_MINUTES: int = 60
    OUTBOX_INITIAL_STARTUP_DELAY_SECONDS: float = 60.0
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:5173"

    # WebRTC ICE & Signaling
    RTC_STUN_SERVERS: str = "stun:stun.l.google.com:19302,stun:stun1.l.google.com:19302"
    RTC_TURN_SERVER: Optional[str] = None
    RTC_TURN_USERNAME: Optional[str] = None
    RTC_TURN_CREDENTIAL: Optional[str] = None
    
    @property
    def task_approved_webhook_url(self) -> Optional[str]:
        return (
            self.ZAPIER_TASK_APPROVED_WEBHOOK_URL 
            or self.ZAPIER_APPROVED_TASK_WEBHOOK_URL 
            or self.ZAPIER_WEBHOOK_URL 
            or ""
        )

    @property
    def meeting_completed_webhook_url(self) -> Optional[str]:
        return self.ZAPIER_MEETING_COMPLETED_WEBHOOK_URL or ""

    @property
    def meeting_invitation_webhook_url(self) -> Optional[str]:
        return (
            self.MEETING_INVITATION_WEBHOOK_URL
            or self.ZAPIER_MEETING_SCHEDULED_WEBHOOK_URL
            or ""
        )

    @property
    def task_completed_webhook_url(self) -> Optional[str]:
        return self.ZAPIER_TASK_COMPLETED_WEBHOOK_URL or ""

    @property
    def team_member_added_webhook_url(self) -> Optional[str]:
        return self.ZAPIER_TEAM_MEMBER_ADDED_WEBHOOK_URL or ""

    @property
    def team_invitation_created_webhook_url(self) -> Optional[str]:
        return self.ZAPIER_TEAM_INVITATION_CREATED_WEBHOOK_URL or ""

    # Legacy alias
    @property
    def approved_task_webhook_url(self) -> Optional[str]:
        return self.task_approved_webhook_url
    
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
