"""FastAPI entry point:  python -m uvicorn backend.main:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.api import agent_routes, analytics_routes, auth_routes, memory_routes, task_routes, workflow_routes
from backend.config import settings
from backend.database import init_db
from backend.services import scheduler
from backend.services import task_service as ts
from integrations import gemini_client, tavily_client
from utils.logger import get_logger

logger = get_logger("main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    n = ts.recover_interrupted()
    if n:
        logger.warning("Marked %s interrupted task(s) as failed", n)
    if not gemini_client.is_configured():
        logger.warning("GEMINI_API_KEY is not set - agents cannot call the LLM until it is configured in .env")
    if settings.scheduler_enabled:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="AgentFlow AI", version="1.0.0", description="Multi-agent AI task automation backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth_routes.router, task_routes.router, task_routes.files_router, agent_routes.router, workflow_routes.router,
          memory_routes.router, analytics_routes.router):
    app.include_router(r)


@app.exception_handler(SQLAlchemyError)
async def db_error(_: Request, exc: SQLAlchemyError):
    logger.exception("Database error")
    return JSONResponse({"detail": "Database error - please try again"}, status_code=503)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "gemini_configured": gemini_client.is_configured(), "tavily_configured": tavily_client.is_configured()}
