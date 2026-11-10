"""ORM models.  Schema changes require an Alembic migration (see docs/development_guide.md)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    audience: Mapped[str] = mapped_column(String(10), default="adult")  # adult | child (feedback tone)
    preferred_accent: Mapped[str] = mapped_column(String(10), default="us")  # reference playback: us | gb
    store_recordings_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    sessions: Mapped[list[PracticeSession]] = relationship(back_populates="user", cascade="all, delete-orphan",
                                                             passive_deletes=True)


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ipa: Mapped[str] = mapped_column(String(64))
    phonemes: Mapped[list] = mapped_column(JSON)
    arpabet: Mapped[list] = mapped_column(JSON)
    syllables: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    category_label: Mapped[str] = mapped_column(String(64), default="")
    target_sounds: Mapped[list] = mapped_column(JSON, default=list)
    evaluation_features: Mapped[list] = mapped_column(JSON, default=list)
    variants: Mapped[list] = mapped_column(JSON, default=list)
    stress_pattern: Mapped[list] = mapped_column(JSON, default=list)
    syllable_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def as_entry(self) -> dict:
        """The word-database dict format expected by speech_analysis."""
        return {
            "id": self.id, "word": self.word, "ipa": self.ipa, "phonemes": self.phonemes, "arpabet": self.arpabet,
            "syllables": self.syllables, "difficulty": self.difficulty, "category": self.category,
            "category_label": self.category_label, "target_sounds": self.target_sounds,
            "evaluation_features": self.evaluation_features, "variants": self.variants,
            "stress_pattern": self.stress_pattern, "syllable_breakdown": self.syllable_breakdown,
        }


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20))  # adaptive | random | easy | medium | hard | phoneme | missed
    target_phoneme: Mapped[str | None] = mapped_column(String(8), nullable=True)
    word_ids: Mapped[list] = mapped_column(JSON, default=list)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | completed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    attempts: Mapped[list[Attempt]] = relationship(back_populates="session", passive_deletes=True)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_user_word", "user_id", "word_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("practice_sessions.id", ondelete="SET NULL"),
                                                    nullable=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20))  # assessed | retry_required | inconclusive
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    word_recognized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    phonetically_accurate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    engine: Mapped[str] = mapped_column(String(40), default="")
    analysis: Mapped[dict] = mapped_column(JSON)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    session: Mapped[PracticeSession | None] = relationship(back_populates="attempts")
    word: Mapped[Word] = relationship()
    phoneme_results: Mapped[list[AttemptPhoneme]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    recording: Mapped[Recording | None] = relationship(back_populates="attempt", cascade="all, delete-orphan",
                                                         passive_deletes=True, uselist=False)


class AttemptPhoneme(Base):
    """Per-phoneme results, denormalised for fast progress queries."""

    __tablename__ = "attempt_phonemes"
    __table_args__ = (Index("ix_attempt_phonemes_user_phoneme", "user_id", "phoneme"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    phoneme: Mapped[str] = mapped_column(String(8))
    arpabet: Mapped[str] = mapped_column(String(8))
    position: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    realized_as: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Recording(Base):
    """Audio kept only when the user has opted in (``store_recordings_consent``)."""

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), unique=True)
    path: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(40), default="audio/wav")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    attempt: Mapped[Attempt] = relationship(back_populates="recording")
