"""Health, status and progress endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_feedback import FeedbackService
from speech_analysis.contracts import CONTRACT_VERSION

from ...core.config import get_settings
from ...core.deps import get_current_user
from ...database.session import get_db
from ...models import User, Word
from ...schemas import ProgressOut, SystemStatus
from ...services.analysis import AnalysisService, get_analysis_service
from ...services.progress import compute_progress
from .feedback import get_feedback_service

router = APIRouter(tags=["system & progress"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/system/status", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db), svc: AnalysisService = Depends(get_analysis_service),
                  fb: FeedbackService = Depends(get_feedback_service)) -> SystemStatus:
    return SystemStatus(
        status="ok", environment=get_settings().app_env, contract_version=CONTRACT_VERSION,
        analysis_engine=svc.status(), feedback=fb.describe(), reference_audio=svc.reference_status(),
        words=db.scalar(select(func.count()).select_from(Word)) or 0,
    )


@router.get("/users/me/progress", response_model=ProgressOut)
def my_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProgressOut:
    return compute_progress(db, user)
