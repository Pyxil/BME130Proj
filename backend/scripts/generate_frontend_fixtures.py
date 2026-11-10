#!/usr/bin/env python3
"""Record real backend responses as fixtures for the frontend mock mode.

Runs the actual API in-process (real analysis if models are installed) on the
committed test recordings and writes ``frontend/src/mocks/fixtures.json``.
Re-run after contract changes:  python -m backend.scripts.generate_frontend_fixtures
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TMP = tempfile.mkdtemp(prefix="fixtures-")
os.environ.update({"DATABASE_URL": f"sqlite:///{_TMP}/fx.db", "RECORDINGS_DIR": f"{_TMP}/rec",
                   "WARMUP_ON_START": "false", "LLM_PROVIDER": "rule_based"})

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

FIX = ROOT / "speech_analysis" / "tests" / "fixtures"


def main() -> None:
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "fixtures@example.com", "password": "fixtures123"}).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        words = c.get("/api/words").json()["items"]
        by_word = {w["word"]: w for w in words}
        samples = {}
        for name, word in [("rabbit_r_as_w", "rabbit"), ("butterfly_correct_us", "butterfly"),
                           ("quality_noisy", "rabbit")]:
            r = c.post("/api/pronunciation/analyze", headers=h, data={"word_id": by_word[word]["id"]},
                       files={"audio": ("a.wav", (FIX / f"{name}.wav").read_bytes(), "audio/wav")})
            r.raise_for_status()
            attempt = r.json()
            fb = c.post("/api/feedback", headers=h, json={"attempt_id": attempt["attempt_id"]}).json()
            samples[name] = {"analysis": attempt["analysis"], "feedback": fb}
        out = {
            "_note": "Recorded from the real backend by backend/scripts/generate_frontend_fixtures.py. Do not edit.",
            "words": words,
            "word_variants": {w["id"]: c.get(f"/api/words/{w['id']}").json()["variants"] for w in words},
            "phonemes": c.get("/api/words/phonemes").json(),
            "samples": samples,
            "status": c.get("/api/system/status").json(),
        }
    path = ROOT / "frontend" / "src" / "mocks" / "fixtures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
