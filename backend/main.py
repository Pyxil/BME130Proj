"""FastAPI application entry point.

    uvicorn backend.main:app --reload --port 8000

Interactive API docs: http://localhost:8000/docs (OpenAPI at /openapi.json).
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from speech_analysis.contracts import CONTRACT_VERSION

from .api.routes import auth, feedback, pronunciation, sessions, system, words
from .core.config import get_settings

log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_migrate:
        from .database.init_db import migrate, seed_words

        migrate()
        n = seed_words()
        log.info("database ready (%d words)", n)
    if settings.warmup_on_start:
        from .services.analysis import get_analysis_service

        threading.Thread(target=lambda: get_analysis_service().warmup(), daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pronunciation Practice API",
        version=CONTRACT_VERSION,
        description=(
            "Speech and pronunciation practice: word database, audio analysis with phoneme-level scoring, "
            "AI feedback, adaptive sessions and progress tracking. Scores are automated practice estimates, "
            "not clinical assessments."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Reference-Source"],
    )
    for r in (auth.router, words.router, sessions.router, pronunciation.router, feedback.router, system.router):
        app.include_router(r, prefix="/api")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
