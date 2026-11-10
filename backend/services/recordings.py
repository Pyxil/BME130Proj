"""Consent-gated storage of user recordings."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Recording

log = logging.getLogger(__name__)


def _user_dir(user_id: int) -> Path:
    d = get_settings().recordings_dir / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def store(db: Session, user_id: int, attempt_id: str, wav_bytes: bytes) -> Recording:
    path = _user_dir(user_id) / f"{attempt_id}.wav"  # server-generated name; never user input
    path.write_bytes(wav_bytes)
    rec = Recording(user_id=user_id, attempt_id=attempt_id, path=str(path), size_bytes=len(wav_bytes))
    db.add(rec)
    return rec


def delete_files(paths: list[str]) -> int:
    n = 0
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            n += 1
        except OSError as exc:
            log.warning("could not delete %s: %s", p, exc)
    return n


def delete_all_for_user(db: Session, user_id: int) -> int:
    recs = db.execute(select(Recording).where(Recording.user_id == user_id)).scalars().all()
    paths = [r.path for r in recs]
    for r in recs:
        db.delete(r)
    db.flush()
    return delete_files(paths)
