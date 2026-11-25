import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database.mongo import connect_to_mongo, close_mongo_connection
from app.services.scheduler_service import run_persistent_meeting_scheduler
from app.services.zapier_service import run_persistent_automation_outbox, ZapierService
from app.routes.auth_routes import router as auth_router
from app.routes.team_routes import router as team_router, teams_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.task_routes import router as task_router
from app.routes.automation_routes import router as automation_router
from app.routes.agent_routes import router as agent_router
from app.routes.analytics_routes import router as analytics_router
from app.routes.meeting_routes import router as meeting_router, meeting_ws_router
from app.routes.invitation_routes import router as invitation_router
from app.routes.chat_routes import router as chat_router, ws_router as chat_ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("meetmind")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting MeetMind AI Backend...")
    try:
        connect_to_mongo()
        # Clean up / mark stale unhandled outbox records from previous sessions
        # to ensure no automated replay occurs on backend startup
        cleaned = ZapierService.cleanup_stale_outbox_on_startup()
        if cleaned > 0:
            logger.info(f"Startup outbox sanitization: marked {cleaned} pending/retrying event(s) as stale_skipped.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB on startup: {e}")

    scheduler_task = asyncio.create_task(run_persistent_meeting_scheduler())

    outbox_task = None
    if settings.ENABLE_OUTBOX_BACKGROUND_WORKER and settings.ENABLE_STARTUP_OUTBOX_DISPATCH:
        logger.info("Starting persistent automation outbox background runner...")
        outbox_task = asyncio.create_task(run_persistent_automation_outbox())
    else:
        logger.info("Automation outbox background runner is disabled on startup (ENABLE_STARTUP_OUTBOX_DISPATCH=False). No webhooks will be replayed on boot.")

    yield
    # Shutdown
    scheduler_task.cancel()
    if outbox_task:
        outbox_task.cancel()
    logger.info("Shutting down MeetMind AI Backend...")
    close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="MeetMind AI – Intelligent Meeting Assistant and Autonomous Task Assignment System",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows Vite frontend, local network, Vercel/Render
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(team_router, prefix=settings.API_PREFIX)
app.include_router(teams_router, prefix=settings.API_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_PREFIX)
app.include_router(task_router, prefix=settings.API_PREFIX)
app.include_router(automation_router, prefix=settings.API_PREFIX)
app.include_router(agent_router, prefix=settings.API_PREFIX)
app.include_router(analytics_router, prefix=settings.API_PREFIX)
app.include_router(meeting_router, prefix=settings.API_PREFIX)
app.include_router(invitation_router, prefix=settings.API_PREFIX)
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(chat_ws_router)
app.include_router(meeting_ws_router)

@app.get("/")
def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
