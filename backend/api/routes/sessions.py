"""Practice sessions: planned word queues with progress."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.deps import get_current_user
from ...database.session import get_db
from ...models import Attempt, PracticeSession, User, Word
from ...schemas import (
    ErrorResponse,
    SessionAdvance,
    SessionCreate,
    SessionOut,
    SessionSummary,
    SessionWordProgress,
    WordSummary,
)
from ...services.adaptive import focus_phonemes, plan_words
from ...services.progress import session_summary

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_owned_session(db: Session, session_id: str, user: User) -> PracticeSession:
    s = db.get(PracticeSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "Session not found")
    return s


def session_out(db: Session, s: PracticeSession) -> SessionOut:
    words = {w.id: w for w in db.execute(select(Word).where(Word.id.in_(s.word_ids))).scalars()}
    attempts = db.execute(select(Attempt).where(Attempt.session_id == s.id).order_by(Attempt.created_at)).scalars().all()
    per_word: dict[int, list[Attempt]] = {}
    for a in attempts:
        per_word.setdefault(a.word_id, []).append(a)
    items, all_scores = [], []
    for i, wid in enumerate(s.word_ids):
        w = words.get(wid)
        if w is None:
            continue
        att = per_word.get(wid, [])
        scored = [a for a in att if a.overall_score is not None]
        best = max((a.overall_score for a in scored), default=None)
        last = scored[-1] if scored else None
        if best is not None:
            all_scores.append(best)
        status = "pending" if not att else "mastered" if (last and last.rating == "mastered") else "attempted"
        items.append(SessionWordProgress(
            position=i, word=WordSummary.model_validate(w), attempts=len(att), best_score=best,
            last_score=last.overall_score if last else None, last_rating=last.rating if last else None, status=status))
    return SessionOut(
        id=s.id, mode=s.mode, target_phoneme=s.target_phoneme, status=s.status, started_at=s.started_at,
        completed_at=s.completed_at, current_index=s.current_index, total_words=len(items),
        words_attempted=sum(1 for it in items if it.attempts), words=items,
        average_score=round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        focus_phonemes=focus_phonemes(db, s.user_id) if s.mode == "adaptive" else [],
    )


@router.post("", response_model=SessionOut, status_code=201, responses={422: {"model": ErrorResponse}})
def create_session(body: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionOut:
    try:
        word_ids = plan_words(db, user, body.mode, body.phoneme, body.size)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not word_ids:
        raise HTTPException(422, "No words match this practice mode")
    s = PracticeSession(user_id=user.id, mode=body.mode, target_phoneme=body.phoneme, word_ids=word_ids)
    db.add(s)
    db.commit()
    return session_out(db, s)


@router.get("", response_model=list[SessionSummary])
def list_sessions(limit: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[SessionSummary]:
    rows = db.execute(select(PracticeSession).where(PracticeSession.user_id == user.id)
                      .order_by(PracticeSession.started_at.desc()).limit(limit)).scalars()
    return [session_summary(db, s) for s in rows]


@router.get("/{session_id}", response_model=SessionOut, responses={404: {"model": ErrorResponse}})
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionOut:
    return session_out(db, get_owned_session(db, session_id, user))


@router.post("/{session_id}/advance", response_model=SessionOut)
def advance(session_id: str, body: SessionAdvance | None = None, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> SessionOut:
    """Move to the next word (or a given index).  Past the last word the session completes."""
    s = get_owned_session(db, session_id, user)
    target = (body.current_index if body and body.current_index is not None else s.current_index + 1)
    if target >= len(s.word_ids):
        s.status, s.completed_at = "completed", datetime.now(UTC)
        s.current_index = len(s.word_ids) - 1
    else:
        s.current_index = target
    db.commit()
    return session_out(db, s)


@router.post("/{session_id}/complete", response_model=SessionOut)
def complete(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionOut:
    s = get_owned_session(db, session_id, user)
    if s.status != "completed":
        s.status, s.completed_at = "completed", datetime.now(UTC)
        db.commit()
    return session_out(db, s)
