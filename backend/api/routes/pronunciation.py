"""Audio upload + analysis, attempt history and recording playback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from speech_analysis.audio_processing import AudioDecodeError, decode_audio, encode_wav

from ...core.config import get_settings
from ...core.deps import get_current_user
from ...database.session import get_db
from ...models import Attempt, AttemptPhoneme, User, Word
from ...schemas import TOO_LARGE, UNPROCESSABLE, AttemptList, AttemptOut, ErrorResponse
from ...services import recordings
from ...services.adaptive import replan_remaining
from ...services.analysis import AnalysisService, get_analysis_service
from ...services.progress import attempt_summary
from .sessions import get_owned_session

router = APIRouter(tags=["pronunciation"])

_MAGIC = (b"RIFF", b"OggS", b"\x1aE\xdf\xa3", b"ID3", b"\xff\xfb", b"fLaC")
ALLOWED_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "audio/webm", "audio/ogg",
                 "audio/mpeg", "audio/mp4", "audio/flac", "video/webm", "application/octet-stream"}


async def read_upload(upload: UploadFile, limit: int) -> bytes:
    if upload.content_type and upload.content_type.split(";")[0].strip().lower() not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported content type {upload.content_type}")
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Recording too large (max {limit // 1000} kB)")
    if len(data) < 44:
        raise HTTPException(422, "Recording is empty")
    if not (data.startswith(_MAGIC) or data[4:8] == b"ftyp"):
        raise HTTPException(415, "File is not a recognised audio format")
    return data


def attempt_out(a: Attempt, best: int | None = None) -> AttemptOut:
    return AttemptOut(attempt_id=a.id, attempt_number=a.attempt_number, word_id=a.word_id, session_id=a.session_id,
                      created_at=a.created_at, analysis=a.analysis, feedback=a.feedback,
                      has_recording=a.recording is not None, word_best_score=best)


@router.post("/pronunciation/analyze", response_model=AttemptOut,
             responses={413: TOO_LARGE, 415: {"model": ErrorResponse}, 422: UNPROCESSABLE})
async def analyze_pronunciation(
    audio: UploadFile = File(..., description="Recording (16 kHz mono WAV preferred)"),
    word_id: int = Form(...),
    session_id: str | None = Form(None),
    store_recording: bool = Form(False, description="Keep the audio (only if the user has consented)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AttemptOut:
    data = await read_upload(audio, get_settings().max_upload_bytes)
    word = db.get(Word, word_id)
    if word is None:
        raise HTTPException(404, "Word not found")
    session = get_owned_session(db, session_id, user) if session_id else None
    if session is not None and word_id not in session.word_ids:
        raise HTTPException(422, "Word is not part of this session")
    try:
        result = await run_in_threadpool(svc.analyze, data, word.as_entry())
    except AudioDecodeError as exc:
        raise HTTPException(422, f"Could not read the recording: {exc}") from exc

    previous = db.scalar(select(func.count()).select_from(Attempt)
                         .where(Attempt.user_id == user.id, Attempt.word_id == word_id)) or 0
    a = Attempt(user_id=user.id, session_id=session.id if session else None, word_id=word_id,
                attempt_number=previous + 1, status=result.status, overall_score=result.overall_score,
                rating=result.rating, confidence=result.confidence, word_recognized=result.word_recognized,
                phonetically_accurate=result.phonetically_accurate, engine=result.engine.name,
                analysis=result.model_dump(mode="json"))
    db.add(a)
    db.flush()
    for p in result.phoneme_scores or []:
        if p.score is not None:
            db.add(AttemptPhoneme(attempt_id=a.id, user_id=user.id, phoneme=p.phoneme, arpabet=p.arpabet,
                                  position=p.index, score=p.score, status=p.status, realized_as=p.likely_realization))
    if store_recording and user.store_recordings_consent:
        wav = data if data.startswith(b"RIFF") else encode_wav(*decode_audio(data))
        recordings.store(db, user.id, a.id, wav)
    if session is not None and result.status == "assessed":
        db.flush()
        replan_remaining(db, session, user)
    db.commit()
    db.refresh(a)
    best = db.scalar(select(func.max(Attempt.overall_score))
                     .where(Attempt.user_id == user.id, Attempt.word_id == word_id))
    return attempt_out(a, best)


@router.get("/attempts", response_model=AttemptList)
def list_attempts(word_id: int | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AttemptList:
    stmt = select(Attempt).where(Attempt.user_id == user.id)
    if word_id is not None:
        stmt = stmt.where(Attempt.word_id == word_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Attempt.created_at.desc()).offset(offset).limit(limit)).scalars()
    return AttemptList(total=total, items=[attempt_summary(a) for a in rows])


def _owned_attempt(db: Session, attempt_id: str, user: User) -> Attempt:
    a = db.get(Attempt, attempt_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Attempt not found")
    return a


@router.get("/attempts/{attempt_id}", response_model=AttemptOut, responses={404: {"model": ErrorResponse}})
def get_attempt(attempt_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AttemptOut:
    return attempt_out(_owned_attempt(db, attempt_id, user))


@router.get("/attempts/{attempt_id}/recording", response_class=Response,
            responses={200: {"content": {"audio/wav": {}}}, 404: {"model": ErrorResponse}})
def get_recording(attempt_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    a = _owned_attempt(db, attempt_id, user)
    if a.recording is None:
        raise HTTPException(404, "No recording stored for this attempt")
    with open(a.recording.path, "rb") as fh:
        return Response(content=fh.read(), media_type="audio/wav", headers={"Cache-Control": "private, no-store"})


@router.delete("/attempts/{attempt_id}/recording", status_code=204)
def delete_recording(attempt_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    a = _owned_attempt(db, attempt_id, user)
    if a.recording is not None:
        path = a.recording.path
        db.delete(a.recording)
        db.commit()
        recordings.delete_files([path])
    return Response(status_code=204)
