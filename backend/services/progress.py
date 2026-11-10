"""Progress and dashboard aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Attempt, AttemptPhoneme, PracticeSession, User
from ..schemas import (
    AttemptSummary,
    PhonemeStat,
    ProgressOut,
    ScorePoint,
    SessionSummary,
    WordProgress,
)
from .adaptive import improvement


def attempt_summary(a: Attempt) -> AttemptSummary:
    return AttemptSummary(
        id=a.id, word_id=a.word_id, word=a.word.word if a.word else "", session_id=a.session_id,
        created_at=a.created_at, attempt_number=a.attempt_number, status=a.status, overall_score=a.overall_score,
        rating=a.rating, confidence=a.confidence, has_recording=a.recording is not None,
        feedback_summary=(a.feedback or {}).get("summary") if a.feedback else None,
    )


def session_summary(db: Session, s: PracticeSession) -> SessionSummary:
    attempts = [a for a in s.attempts if a.status == "assessed"]
    scores = [a.overall_score for a in attempts if a.overall_score is not None]
    return SessionSummary(
        id=s.id, mode=s.mode, status=s.status, started_at=s.started_at, completed_at=s.completed_at,
        total_words=len(s.word_ids), words_attempted=len({a.word_id for a in attempts}), attempts=len(s.attempts),
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
    )


def compute_progress(db: Session, user: User) -> ProgressOut:
    attempts = db.execute(
        select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.created_at)
    ).scalars().all()
    assessed = [a for a in attempts if a.status == "assessed" and a.overall_score is not None]
    scores = [a.overall_score for a in assessed]

    by_day: dict[str, list[int]] = defaultdict(list)
    for a in assessed:
        by_day[a.created_at.date().isoformat()].append(a.overall_score)
    over_time = [ScorePoint(date=d, average_score=round(sum(v) / len(v), 1), attempts=len(v))
                 for d, v in sorted(by_day.items())]

    ph_rows = db.execute(
        select(AttemptPhoneme.phoneme, AttemptPhoneme.score, AttemptPhoneme.status, AttemptPhoneme.realized_as)
        .where(AttemptPhoneme.user_id == user.id)
    ).all()
    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "sum": 0, "poor": 0, "subs": Counter()})
    for ph, score, status, real in ph_rows:
        g = agg[ph]
        g["n"] += 1
        g["sum"] += score
        if status in {"poor", "missing"}:
            g["poor"] += 1
            if real:
                g["subs"][real] += 1
    stats = [
        PhonemeStat(phoneme=ph, attempts=g["n"], average_score=round(g["sum"] / g["n"], 1), poor_count=g["poor"],
                    poor_rate=round(g["poor"] / g["n"], 3),
                    common_substitution=g["subs"].most_common(1)[0][0] if g["subs"] else None)
        for ph, g in agg.items()
    ]
    stats.sort(key=lambda s: s.average_score)
    mis = sorted([s for s in stats if s.poor_count > 0], key=lambda s: (-s.poor_rate, -s.poor_count))[:6]

    words: dict[int, WordProgress] = {}
    for a in assessed:
        wp = words.get(a.word_id)
        if wp is None:
            wp = WordProgress(word_id=a.word_id, word=a.word.word, attempts=0, best_score=None, last_score=None,
                              last_rating=None, last_attempt_at=a.created_at)
            words[a.word_id] = wp
        wp.attempts += 1
        wp.best_score = a.overall_score if wp.best_score is None else max(wp.best_score, a.overall_score)
        wp.last_score, wp.last_rating, wp.last_attempt_at = a.overall_score, a.rating, a.created_at
    needing = sorted([w for w in words.values() if w.last_rating != "mastered"], key=lambda w: w.last_score or 0)[:8]

    sessions = db.execute(
        select(PracticeSession).where(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.started_at.desc()).limit(8)
    ).scalars().all()
    total_sessions = db.scalar(select(func.count()).select_from(PracticeSession)
                               .where(PracticeSession.user_id == user.id)) or 0
    return ProgressOut(
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        total_attempts=len(attempts),
        assessed_attempts=len(assessed),
        words_attempted=len({a.word_id for a in attempts}),
        words_completed=len(words),
        words_mastered=sum(1 for w in words.values() if w.last_rating == "mastered"),
        total_sessions=total_sessions,
        improvement=improvement(scores),
        score_over_time=over_time,
        phoneme_stats=stats,
        most_mispronounced=mis,
        words_needing_practice=needing,
        recent_sessions=[session_summary(db, s) for s in sessions],
        recent_attempts=[attempt_summary(a) for a in reversed(attempts[-10:])],
    )
