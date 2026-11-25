import logging
from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from app.config import settings

logger = logging.getLogger(__name__)

class MongoDBManager:
    client: MongoClient = None
    db: Database = None

db_manager = MongoDBManager()

def connect_to_mongo():
    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
    db_manager.client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    db_manager.db = db_manager.client[settings.DATABASE_NAME]
    # Ping to check connection
    db_manager.client.admin.command('ping')
    logger.info(f"Successfully connected to MongoDB database '{settings.DATABASE_NAME}'")
    init_db_indexes()

def close_mongo_connection():
    if db_manager.client:
        try:
            db_manager.client.close()
        except Exception:
            pass
        db_manager.client = None
        db_manager.db = None
        logger.info("MongoDB connection closed.")

def get_database() -> Database:
    if db_manager.client is None or db_manager.db is None:
        connect_to_mongo()
    return db_manager.db

def get_col(collection_name: str):
    return get_database()[collection_name]

def init_db_indexes():
    """Ensure indexes for all collections according to specifications."""
    try:
        db = get_database()
        
        # 1. users: unique email
        db.users.create_index([("email", ASCENDING)], unique=True)
        db.users.create_index([("team_id", ASCENDING)])
        
        # 2. teams: team_id
        db.teams.create_index([("team_id", ASCENDING)], unique=True)
        
        # 3. member_profiles:
        # Enforce unique membership within the appropriate team: (team_id, email)
        # Drop old member_id_1 unique index if it exists
        try:
            db.member_profiles.drop_index("member_id_1")
        except Exception:
            pass
            
        db.member_profiles.create_index(
            [("team_id", ASCENDING), ("email", ASCENDING)],
            unique=True
        )
        db.member_profiles.create_index(
            [("team_id", ASCENDING), ("member_id", ASCENDING)],
            unique=True
        )
        db.member_profiles.create_index([("member_id", ASCENDING)])
        db.member_profiles.create_index([("account_status", ASCENDING)])
        db.member_profiles.create_index([("availability", ASCENDING)])
        
        # 4. team_invitations:
        db.team_invitations.create_index([("token_hash", ASCENDING)], unique=True)
        db.team_invitations.create_index([("team_id", ASCENDING), ("email", ASCENDING)])
        db.team_invitations.create_index([("expires_at", ASCENDING)])
        
        # 5. meetings:
        db.meetings.create_index([("meeting_id", ASCENDING)], unique=True)
        db.meetings.create_index([("team_id", ASCENDING)])
        
        # 6. transcript_segments:
        db.transcript_segments.create_index([("meeting_id", ASCENDING)])
        
        # 7. tasks:
        try:
            db.tasks.drop_index("task_id_1")
        except Exception:
            pass
        db.tasks.create_index([("team_id", ASCENDING), ("task_id", ASCENDING)], unique=True)
        db.tasks.create_index([("task_id", ASCENDING)])
        db.tasks.create_index([("team_id", ASCENDING)])
        db.tasks.create_index([("assigned_member_id", ASCENDING)])
        
        # 8. notifications:
        db.notifications.create_index([("recipient_email", ASCENDING)])
        db.notifications.create_index([("team_id", ASCENDING)])
        
        # 9. automation_logs:
        db.automation_logs.create_index([("task_id", ASCENDING)])
        db.automation_logs.create_index([("team_id", ASCENDING)])
        db.automation_logs.create_index([("event_id", ASCENDING)])

        # 10. workspace_messages:
        db.workspace_messages.create_index([("team_id", ASCENDING), ("created_at", ASCENDING)])
        db.workspace_messages.create_index([("message_id", ASCENDING)], unique=True)
        db.workspace_messages.create_index([("team_id", ASCENDING), ("message_id", ASCENDING)])

        # 11. scheduled_meetings:
        db.scheduled_meetings.create_index([("meeting_id", ASCENDING)], unique=True)
        db.scheduled_meetings.create_index([("team_id", ASCENDING), ("scheduled_start_at", ASCENDING)])
        db.scheduled_meetings.create_index([("meeting_status", ASCENDING)])

        # 12. automation_outbox:
        db.automation_outbox.create_index([("event_id", ASCENDING)], unique=True)
        db.automation_outbox.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
        
        logger.info("MongoDB collections and indexes successfully verified.")
    except Exception as e:
        logger.error(f"Error initializing indexes: {e}")
