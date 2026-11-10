# API documentation

Interactive docs: `http://localhost:8000/docs` (Swagger) and `/redoc`. The machine-readable contract is
[`docs/openapi.json`](openapi.json); JSON Schemas for the main payloads are in [`docs/schemas/`](schemas/).
TypeScript types are generated from the OpenAPI file (`npm run gen:api`); CI fails if any of these drift.

## Conventions
- Base path `/api`; JSON bodies; errors are `{"detail": "message"}` (422 validation errors list fields).
- Auth: `Authorization: Bearer <access_token>` from register/login. 401 = missing/invalid token.
- Objects owned by another user return 404 (never 403) to avoid leaking existence.
- Contract version: `AnalysisResult.contract_version` and `GET /api/system/status`. Breaking changes bump the
  major version and are listed in `CHANGELOG.md`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create account -> `TokenResponse` (201; 409 if email exists) |
| POST | `/api/auth/login` | Log in -> `TokenResponse` (401 on bad credentials) |
| GET / PATCH | `/api/users/me` | Profile; PATCH: `display_name`, `audience`, `preferred_accent`, `store_recordings_consent` |
| GET | `/api/users/me/progress` | Dashboard data (`ProgressOut`) |
| GET | `/api/users/me/export` | Everything stored about the user (JSON) |
| DELETE | `/api/users/me/recordings` | Delete all stored recordings -> `{deleted: n}` |
| DELETE | `/api/users/me/data` | Delete attempts, sessions, recordings (keep account) |
| DELETE | `/api/users/me` | Delete account and all data |
| GET | `/api/words` | Words; filters `difficulty`, `category`, `phoneme` (IPA), `q`, `limit`, `offset` |
| GET | `/api/words/{id}` | Word detail with variants and evaluation features |
| GET | `/api/words/{id}/audio?variant=us&speed=normal\|slow` | Reference WAV; header `X-Reference-Source: human\|piper\|espeak`; 404 -> use browser TTS |
| GET | `/api/words/phonemes` | Sounds available for targeted practice with word counts |
| GET | `/api/words/categories` | Categories with counts |
| POST | `/api/sessions` | Start a session `{mode, phoneme?, size}` -> `SessionOut` (201) |
| GET | `/api/sessions` | Recent sessions |
| GET | `/api/sessions/{id}` | Session progress (per-word attempts, best score, status) |
| POST | `/api/sessions/{id}/advance` | Next word (or `{current_index}`); completes after the last word |
| POST | `/api/sessions/{id}/complete` | Mark completed |
| POST | `/api/pronunciation/analyze` | **Upload and analyse** (multipart) -> `AttemptOut` |
| GET | `/api/attempts` | History (`word_id`, `limit`, `offset`) |
| GET | `/api/attempts/{id}` | Attempt with full analysis and stored feedback |
| GET / DELETE | `/api/attempts/{id}/recording` | Play / delete a stored recording |
| POST | `/api/feedback` | Grounded recommendations `{attempt_id}` or `{analysis}` -> `FeedbackResponse` |
| GET | `/api/health` | Liveness |
| GET | `/api/system/status` | Engine, calibration, weights, feedback mode, TTS voices, word count |

## Upload and analyse

```bash
curl -X POST http://localhost:8000/api/pronunciation/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -F audio=@recording.wav -F word_id=45 -F session_id=$SESSION -F store_recording=false
```

- `audio`: 16 kHz mono 16-bit WAV preferred (what the web client sends); WebM/OGG/MP3/MP4 accepted if the
  server has ffmpeg. Max 2 MB. 415 for non-audio, 413 for too large, 422 if the word is not in the session.
- `store_recording` is honoured only if the user consented in settings.

### `AnalysisResult` (abridged; recorded from the end-to-end test, "mirror" said with /r/ -> /w/)

```json
{
  "contract_version": "1.0.0",
  "word": "mirror",
  "status": "assessed",
  "overall_score": 69, "rating": "needs_practice",
  "word_recognized": true, "recognized_word": "mirror", "phonetically_accurate": false,
  "confidence": 1.0, "confidence_label": "high",
  "needs_retry": false,
  "matched_variant": {"id": "us", "accent": "General American", "ipa": "/ˈmɪrər/", "arpabet": ["M","IH1","R","ER0"]},
  "phoneme_scores": [
    {"index": 0, "phoneme": "m", "arpabet": "M", "score": 96, "posterior": 0.8262, "status": "good", "start_s": 0.31, "end_s": 0.33},
    {"index": 1, "phoneme": "ɪ", "arpabet": "IH1", "score": 84, "posterior": 0.0273, "status": "fair",
     "likely_realization": "u", "likely_realization_probability": 0.64},
    {"index": 2, "phoneme": "r", "arpabet": "R", "score": 59, "posterior": 0.0013, "status": "poor",
     "likely_realization": "w", "likely_realization_probability": 0.95, "start_s": 0.42, "end_s": 0.52},
    {"index": 3, "phoneme": "ər", "arpabet": "ER0", "score": 94, "posterior": 0.8148, "status": "good"}
  ],
  "components": [
    {"name": "phoneme_accuracy", "score": 71.9, "weight": 0.6, "available": true},
    {"name": "acoustic_similarity", "score": 79.2, "weight": 0.2, "available": true},
    {"name": "syllable_completeness", "score": 85.0, "weight": 0.1, "available": true},
    {"name": "temporal", "score": 99.2, "weight": 0.1, "available": true}
  ],
  "acoustic_similarity": 0.7921,
  "identified_issues": [
    {"id": "ph2-substitution", "type": "substitution", "severity": "moderate", "phoneme": "r", "realized_as": "w",
     "message": "The /r/ sound in the second syllable may have sounded more like /w/."},
    {"id": "ph1-substitution", "type": "substitution", "severity": "minor", "phoneme": "ɪ", "realized_as": "u",
     "message": "The /ɪ/ vowel in the first syllable may have sounded more like /u/."}
  ],
  "strengths": [{"id": "ph3-good", "message": "The /ər/ at the end of the word was clear."}],
  "quality": {"usable": true, "snr_db": 59.2, "issues": []},
  "engine": {"name": "allosaurus", "model": "eng2102", "phoneme_level": true,
             "calibration": "speechocean762 train (28277 phones)"},
  "disclaimer": "Scores are automated estimates intended for practice feedback..."
}
```

The overall score is capped at 69 because one sound scored below the strong-error threshold (60); the
weighted components alone give 77 (see `components[0].details.score_cap`).

`status` values:
- `assessed`: score present.
- `retry_required`: recording unusable (`retry_reason`, `quality.issues`); no score.
- `inconclusive`: analysis ran but confidence < 0.35; no score; ask to record again.

When no phoneme model is installed, `engine.phoneme_level` is `false`, `phoneme_scores` is `null`, and the
score uses only acoustic, syllable and timing components.

### `FeedbackResponse`

```json
{
  "summary": "'mirror' scored 69/100. Let's practise the sounds below.",
  "recommendations": [
    {"issue_id": "ph2-substitution",
     "tip": "Focus on the /r/ sound (r as in 'red'). It may have sounded more like /w/.",
     "articulation": "For /r/ keep your lips more relaxed instead of rounding them..."}
  ],
  "encouragement": "Listen to the example once more, then try again slowly.",
  "progress_note": "",
  "source": "rule_based",
  "grounded": true,
  "guardrail_notes": [],
  "disclaimer": "This feedback is generated automatically for practice..."
}
```

`source` is `llm:<provider>:<model>`, `rule_based`, or `llm:...+rule_based` when guardrails replaced the tips.
