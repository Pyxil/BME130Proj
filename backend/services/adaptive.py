"""Adaptive exercise selection.

The planner estimates a *weakness* for every phoneme from the user's recent
phoneme scores (exponentially weighted, shrunk towards a neutral prior when
there is little data) and ranks words by how much practice they give on weak
sounds.  Mastered words are de-prioritised, words never tried get a small
novelty bonus, and difficulty follows the user's recent average.

All constants are product heuristics, configurable here and documented in
docs/architecture.md; they are not clinical rules.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, AttemptPhoneme, PracticeSession, User, Word

HALF_LIFE_DAYS = 14.0
PRIOR_STRENGTH = 3.0  # pseudo-observations of a neutral score
NEUTRAL_SCORE = 85.0
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def phoneme_weakness(db: Session, user_id: int, limit: int = 1500) -> dict[str, float]:
    """0 (no difficulty) .. 1 (consistently poor) for each phoneme the user has practised."""
    rows = db.execute(
        select(AttemptPhoneme.phoneme, AttemptPhoneme.score, AttemptPhoneme.created_at)
        .where(AttemptPhoneme.user_id == user_id)
        .order_by(AttemptPhoneme.created_at.desc())
        .limit(limit)
    ).all()
    now = datetime.now(UTC)
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for ph, score, ts in rows:
        ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        w = 0.5 ** ((now - ts).total_seconds() / 86400 / HALF_LIFE_DAYS)
        acc[ph][0] += w * score
        acc[ph][1] += w
    out = {}
    for ph, (s, w) in acc.items():
        mean = (s + PRIOR_STRENGTH * NEUTRAL_SCORE) / (w + PRIOR_STRENGTH)
        out[ph] = round(max(0.0, min(1.0, (NEUTRAL_SCORE + 5 - mean) / 40.0)), 3)
    return out


def _word_history(db: Session, user_id: int) -> dict[int, dict]:
    rows = db.execute(
        select(Attempt.word_id, Attempt.overall_score, Attempt.rating, Attempt.created_at)
        .where(Attempt.user_id == user_id, Attempt.status == "assessed")
        .order_by(Attempt.created_at)
    ).all()
    hist: dict[int, dict] = {}
    for wid, score, rating, _ts in rows:
        h = hist.setdefault(wid, {"attempts": 0, "best": None, "last": None, "last_rating": None})
        h["attempts"] += 1
        h["best"] = score if h["best"] is None else max(h["best"], score)
        h["last"], h["last_rating"] = score, rating
    return hist


def recent_average(db: Session, user_id: int, n: int = 15) -> float | None:
    rows = db.execute(
        select(Attempt.overall_score).where(Attempt.user_id == user_id, Attempt.status == "assessed")
        .order_by(Attempt.created_at.desc()).limit(n)
    ).scalars().all()
    return sum(rows) / len(rows) if rows else None


def _difficulty_band(avg: float | None) -> set[str]:
    if avg is None:
        return {"easy", "medium"}
    if avg >= 88:
        return {"medium", "hard"}
    if avg >= 75:
        return {"easy", "medium", "hard"}
    return {"easy", "medium"}


def word_priority(word: Word, weakness: dict[str, float], hist: dict[int, dict], band: set[str]) -> float:
    sounds = set(word.phonemes)
    weak = sorted((weakness.get(p, 0.0) for p in sounds), reverse=True)
    focus = sum(weak[:2]) + 0.5 * sum(weakness.get(t, 0.0) for t in word.target_sounds)
    h = hist.get(word.id)
    score = 1.0 + 3.0 * focus
    if h is None:
        score += 0.6  # novelty
    else:
        if h["last_rating"] == "mastered":
            score -= 1.5
        elif h["last_rating"] == "needs_practice":
            score += 1.0
    if word.difficulty not in band:
        score -= 1.0
    return score


def plan_words(db: Session, user: User, mode: str, phoneme: str | None, size: int,
               rng: random.Random | None = None) -> list[int]:
    rng = rng or random.Random()
    words = db.execute(select(Word)).scalars().all()
    hist = _word_history(db, user.id)
    if mode in {"easy", "medium", "hard"}:
        pool = [w for w in words if w.difficulty == mode]
        rng.shuffle(pool)
        return [w.id for w in pool[:size]]
    if mode == "random":
        pool = list(words)
        rng.shuffle(pool)
        return [w.id for w in pool[:size]]
    if mode == "phoneme":
        if not phoneme:
            raise ValueError("mode 'phoneme' requires a phoneme")
        pool = [w for w in words if phoneme in w.phonemes]
        if not pool:
            raise ValueError(f"no practice words contain /{phoneme}/")
        # target-sound words first, then easier words first, shuffled within groups
        rng.shuffle(pool)
        pool.sort(key=lambda w: (phoneme not in w.target_sounds, DIFFICULTY_ORDER[w.difficulty]))
        return [w.id for w in pool[:size]]
    if mode == "missed":
        missed = [w for w in words if w.id in hist and hist[w.id]["last_rating"] in {"needs_practice", "satisfactory"}]
        missed.sort(key=lambda w: hist[w.id]["last"] if hist[w.id]["last"] is not None else 0)
        if missed:
            return [w.id for w in missed[:size]]
        mode = "adaptive"  # nothing missed yet: fall back to adaptive
    # adaptive
    weakness = phoneme_weakness(db, user.id)
    band = _difficulty_band(recent_average(db, user.id))
    scored = [(word_priority(w, weakness, hist, band) + rng.random() * 0.4, w) for w in words]
    scored.sort(key=lambda x: -x[0])
    return [w.id for _, w in scored[:size]]


def focus_phonemes(db: Session, user_id: int, k: int = 3) -> list[str]:
    weak = phoneme_weakness(db, user_id)
    return [p for p, v in sorted(weak.items(), key=lambda x: -x[1]) if v >= 0.25][:k]


def replan_remaining(db: Session, session: PracticeSession, user: User) -> None:
    """In adaptive mode, re-rank the words not yet reached using the latest results."""
    if session.mode != "adaptive":
        return
    done = session.word_ids[: session.current_index + 1]
    remaining = session.word_ids[session.current_index + 1:]
    if len(remaining) < 2:
        return
    words = {w.id: w for w in db.execute(select(Word).where(Word.id.in_(remaining))).scalars()}
    weakness = phoneme_weakness(db, user.id)
    hist = _word_history(db, user.id)
    band = _difficulty_band(recent_average(db, user.id))
    remaining.sort(key=lambda wid: -word_priority(words[wid], weakness, hist, band) if wid in words else 0)
    session.word_ids = done + remaining


def improvement(scores: list[int]) -> float | None:
    if len(scores) < 6:
        return None
    k = min(10, len(scores) // 2)
    return round(sum(scores[-k:]) / k - sum(scores[:k]) / k, 1)
