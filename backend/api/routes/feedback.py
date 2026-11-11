"""AI-generated recommendations grounded in analysis results."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_feedback import FeedbackRequest, FeedbackResponse, FeedbackService, PreviousAttempt

from ...core.deps import get_current_user
from ...database.session import get_db
from ...models import Attempt, User
from ...schemas import UNPROCESSABLE, ErrorResponse, FeedbackRequestIn

router = APIRouter(tags=["feedback"])
_service: FeedbackService | None = None
_lock = threading.Lock()


def get_feedback_service() -> FeedbackService:
    global _service
    with _lock:
        if _service is None:
            _service = FeedbackService()
    return _service


@router.post("/feedback", response_model=FeedbackResponse,
             responses={404: {"model": ErrorResponse}, 422: UNPROCESSABLE})
async def generate_feedback(
    body: FeedbackRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    svc: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    attempt = None
    if body.attempt_id:
        attempt = db.get(Attempt, body.attempt_id)
        if attempt is None or attempt.user_id != user.id:
            raise HTTPException(404, "Attempt not found")
        if attempt.feedback:
            return FeedbackResponse.model_validate(attempt.feedback)
        earlier = db.execute(
            select(Attempt).where(Attempt.user_id == user.id, Attempt.word_id == attempt.word_id,
                                  Attempt.created_at < attempt.created_at, Attempt.status == "assessed")
            .order_by(Attempt.created_at)
        ).scalars().all()
        previous = [PreviousAttempt(overall_score=a.overall_score, created_at=a.created_at.isoformat(),
                                    phoneme_scores={p["phoneme"]: p["score"] for p in (a.analysis.get("phoneme_scores") or [])
                                                    if p.get("score") is not None})
                    for a in earlier[-5:]]
        req = FeedbackRequest(analysis=attempt.analysis, word=attempt.word.as_entry(), previous_attempts=previous,
                              audience=user.audience)
    elif body.analysis is not None:
        req = FeedbackRequest(analysis=body.analysis.model_dump(mode="json"), audience=user.audience)
    else:
        raise HTTPException(422, "Provide attempt_id or analysis")
    out = await run_in_threadpool(svc.generate, req)
    if attempt is not None:
        attempt.feedback = out.model_dump(mode="json")
        db.commit()
    return out
