"""Backend test setup: temporary SQLite database and a deterministic fake analyzer.

The fake lets the API, persistence and progression logic be tested without
audio models.  It is a test double, clearly separate from real analysis.
"""

from __future__ import annotations

import io
import os
import tempfile
import uuid

import numpy as np
import pytest
import soundfile as sf

_TMP = tempfile.mkdtemp(prefix="vt-tests-")
os.environ.update({
    "APP_ENV": "testing",
    "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
    "RECORDINGS_DIR": f"{_TMP}/recordings",
    "WARMUP_ON_START": "false",
    "AUTO_MIGRATE": "true",
    "LLM_PROVIDER": "rule_based",
})

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.services.analysis import get_analysis_service  # noqa: E402
from speech_analysis.contracts import (  # noqa: E402
    AnalysisResult,
    ComponentScore,
    EngineInfo,
    Issue,
    MatchedVariant,
    PhonemeScore,
    QualityIssue,
    QualityReport,
)


class FakeAnalysisService:
    """Returns a fixed result: first phoneme poor (sounded like 'w'), others good; silence -> retry."""

    def analyze(self, audio: bytes, word: dict) -> AnalysisResult:
        y, _ = sf.read(io.BytesIO(audio), dtype="float32")
        base = dict(analysis_id=str(uuid.uuid4()), word=word["word"], word_id=word["id"],
                    engine=EngineInfo(name="fake", phoneme_level=True))
        if np.max(np.abs(y)) < 1e-3:
            q = QualityReport(usable=False, duration_s=1.0, speech_duration_s=0, speech_start_s=0, speech_end_s=0,
                              issues=[QualityIssue(code="no_speech", message="No speech was detected.", blocking=True)])
            return AnalysisResult(**base, status="retry_required", confidence=0, confidence_label="low",
                                  needs_retry=True, retry_reason="No speech was detected.", quality=q)
        q = QualityReport(usable=True, duration_s=1.0, speech_duration_s=0.5, speech_start_s=0.2, speech_end_s=0.7, snr_db=40)
        scores = [PhonemeScore(index=i, phoneme=p, arpabet=a, score=55 if i == 0 else 95, posterior=0.1 if i == 0 else 0.95,
                               status="poor" if i == 0 else "good", likely_realization="w" if i == 0 else None)
                  for i, (p, a) in enumerate(zip(word["phonemes"], word["arpabet"]))]
        issue = Issue(id="ph0-substitution", type="substitution", severity="moderate", phoneme=word["phonemes"][0],
                      position=0, realized_as="w", message=f"The /{word['phonemes'][0]}/ sound may have sounded like /w/.")
        v = word["variants"][0]
        return AnalysisResult(
            **base, status="assessed", overall_score=78, rating="satisfactory", word_recognized=True,
            recognized_word=word["word"], phonetically_accurate=False, confidence=0.9, confidence_label="high",
            needs_retry=False, quality=q, phoneme_scores=scores, identified_issues=[issue],
            matched_variant=MatchedVariant(id=v["id"], accent=v["accent"], ipa=v["ipa"], arpabet=v["arpabet"]),
            components=[ComponentScore(name="phoneme_accuracy", score=77, weight=0.6, available=True)])

    def reference_audio(self, word, variant_id, slow):
        buf = io.BytesIO()
        sf.write(buf, np.zeros(1600, dtype=np.float32), 16000, format="WAV")
        return buf.getvalue(), "fake"

    def status(self):
        return {"name": "fake"}

    def reference_status(self):
        return {"piper_voices": []}


def wav_bytes(silent: bool = False, seconds: float = 1.0) -> bytes:
    t = np.arange(int(16000 * seconds)) / 16000
    y = np.zeros_like(t) if silent else 0.3 * np.sin(2 * np.pi * 220 * t)
    buf = io.BytesIO()
    sf.write(buf, y.astype(np.float32), 16000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.fixture(scope="session")
def client():
    app.dependency_overrides[get_analysis_service] = lambda: FakeAnalysisService()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correct-horse", "display_name": "Tester"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
