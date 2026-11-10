"""Practice word database and reference pronunciation audio."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_feedback.knowledge import phoneme_note
from speech_analysis.phoneme_analysis.phonemes import PHONEMES

from ...database.session import get_db
from ...models import Word
from ...schemas import ErrorResponse, PhonemeOption, WordDetail, WordList, WordSummary
from ...services.analysis import AnalysisService, get_analysis_service

router = APIRouter(prefix="/words", tags=["words"])
_VOWEL_IPA = {("ə" if a == "AH" else p.ipa) for a, p in PHONEMES.items() if p.kind == "vowel"} | {"ə", "ər", "ɜr"}


@router.get("", response_model=WordList)
def list_words(
    difficulty: str | None = Query(None, pattern="^(easy|medium|hard)$"),
    category: str | None = None,
    phoneme: str | None = Query(None, max_length=8, description="IPA symbol the word must contain"),
    q: str | None = Query(None, max_length=64),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> WordList:
    stmt = select(Word)
    if difficulty:
        stmt = stmt.where(Word.difficulty == difficulty)
    if category:
        stmt = stmt.where(Word.category == category)
    if q:
        stmt = stmt.where(Word.word.ilike(f"%{q}%"))
    words = db.execute(stmt.order_by(Word.id)).scalars().all()
    if phoneme:
        words = [w for w in words if phoneme in w.phonemes]
    return WordList(total=len(words), items=[WordSummary.model_validate(w) for w in words[offset: offset + limit]])


@router.get("/phonemes", response_model=list[PhonemeOption])
def list_phonemes(db: Session = Depends(get_db)) -> list[PhonemeOption]:
    """Sounds available for targeted practice, with how many words contain each."""
    counts: Counter = Counter()
    for (phs,) in db.execute(select(Word.phonemes)):
        counts.update(set(phs))
    out = []
    for ph, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        note = phoneme_note(ph)
        out.append(PhonemeOption(phoneme=ph, label=note["label"] if note else ph,
                                 kind="vowel" if ph in _VOWEL_IPA else "consonant", word_count=n))
    return out


@router.get("/categories", response_model=list[dict])
def list_categories(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Word.category, Word.category_label, func.count()).group_by(Word.category, Word.category_label))
    return [{"category": c, "label": lbl, "count": n} for c, lbl, n in rows]


@router.get("/{word_id}", response_model=WordDetail, responses={404: {"model": ErrorResponse}})
def get_word(word_id: int, db: Session = Depends(get_db)) -> WordDetail:
    word = db.get(Word, word_id)
    if word is None:
        raise HTTPException(404, "Word not found")
    return WordDetail.model_validate(word.as_entry() | {"notes": word.notes})


@router.get("/{word_id}/audio", response_class=Response,
            responses={200: {"content": {"audio/wav": {}}}, 404: {"model": ErrorResponse}})
async def word_audio(
    word_id: int,
    variant: str = Query("us", max_length=8),
    speed: str = Query("normal", pattern="^(normal|slow)$"),
    db: Session = Depends(get_db),
    svc: AnalysisService = Depends(get_analysis_service),
) -> Response:
    """Reference pronunciation (human recording > Piper neural TTS > espeak-ng)."""
    word = db.get(Word, word_id)
    if word is None:
        raise HTTPException(404, "Word not found")
    res = await run_in_threadpool(svc.reference_audio, word.as_entry(), variant, speed == "slow")
    if res is None:
        raise HTTPException(404, "No reference audio engine available; use browser speech synthesis")
    wav, source = res
    return Response(content=wav, media_type="audio/wav",
                    headers={"X-Reference-Source": source, "Cache-Control": "public, max-age=86400"})
