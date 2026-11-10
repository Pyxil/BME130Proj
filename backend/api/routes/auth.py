"""Registration, login, profile, consent and data-deletion endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...core.deps import get_current_user
from ...core.security import create_access_token, hash_password, verify_password
from ...database.session import get_db
from ...models import Attempt, PracticeSession, Recording, User
from ...schemas import ErrorResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut, UserUpdate
from ...services import recordings

router = APIRouter(tags=["auth & users"])


def _token(user: User) -> TokenResponse:
    token, expires = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires, user=UserOut.model_validate(user))


@router.post("/auth/register", response_model=TokenResponse, status_code=201,
             responses={409: {"model": ErrorResponse}})
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=body.email, display_name=body.display_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return _token(user)


@router.post("/auth/login", response_model=TokenResponse, responses={401: {"model": ErrorResponse}})
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return _token(user)


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/users/me", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    data = body.model_dump(exclude_unset=True)
    if "store_recordings_consent" in data and data["store_recordings_consent"] != user.store_recordings_consent:
        user.consent_updated_at = datetime.now(UTC)
    for k, v in data.items():
        if v is not None:
            setattr(user, k, v)
    db.commit()
    return user


@router.delete("/users/me/recordings", response_model=dict)
def delete_my_recordings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    n = recordings.delete_all_for_user(db, user.id)
    db.commit()
    return {"deleted": n}


@router.delete("/users/me/data", status_code=204)
def delete_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Delete all practice data (attempts, sessions, recordings) but keep the account."""
    recordings.delete_all_for_user(db, user.id)
    db.execute(delete(Attempt).where(Attempt.user_id == user.id))
    db.execute(delete(PracticeSession).where(PracticeSession.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.delete("/users/me", status_code=204)
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Delete the account and everything linked to it."""
    paths = [r.path for r in db.execute(select(Recording).where(Recording.user_id == user.id)).scalars()]
    db.execute(delete(Attempt).where(Attempt.user_id == user.id))
    db.delete(user)
    db.commit()
    recordings.delete_files(paths)
    return Response(status_code=204)


@router.get("/users/me/export", response_model=dict)
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Machine-readable export of everything stored about the user (recordings listed, not embedded)."""
    attempts = db.execute(select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.created_at)).scalars()
    sessions = db.execute(select(PracticeSession).where(PracticeSession.user_id == user.id)).scalars()
    return {
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "sessions": [{"id": s.id, "mode": s.mode, "word_ids": s.word_ids, "started_at": s.started_at.isoformat(),
                      "status": s.status} for s in sessions],
        "attempts": [{"id": a.id, "word_id": a.word_id, "created_at": a.created_at.isoformat(),
                      "overall_score": a.overall_score, "rating": a.rating, "analysis": a.analysis,
                      "feedback": a.feedback, "has_recording": a.recording is not None} for a in attempts],
    }
