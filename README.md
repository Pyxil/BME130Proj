# SayItRight: AI-assisted pronunciation practice

A web application for practising English pronunciation word by word. The app
shows a word, plays a reference pronunciation, records the user, scores the
recording **sound by sound** (0-100), explains what may need work, and adapts
the next words to the sounds the user finds hardest.

> **Not a medical device.** Scores are automated practice estimates. They have
> been validated against expert ratings of *non-native* speech (see
> [docs/validation.md](docs/validation.md)) but **not clinically validated**, and
> the app must not be used to diagnose speech or language conditions.

| Exercise | Results with sound-by-sound feedback | Progress dashboard |
|---|---|---|
| ![Exercise screen](docs/images/02-exercise.png) | ![Results](docs/images/06-results-error.png) | ![Dashboard](docs/images/07-dashboard.png) |

## What works today

| Area | Status |
|---|---|
| Word display, reference audio (neural TTS / human recordings / browser fallback), recording with live waveform and silence auto-stop | Working |
| Recording quality gate (silence, too quiet, clipping, noise, cut-off): asks to re-record instead of scoring | Working, tested |
| Phoneme-level scoring with a pretrained phone recogniser (Allosaurus) + substitution/deletion-aware CTC GOP | Working, **validated on speechocean762** |
| Accent tolerance (US/UK/dictionary variants + allophone rules) | Working, tested |
| DTW acoustic similarity, syllable completeness, timing; configurable weights | Working (heuristic, documented) |
| AI feedback grounded in measured issues (Claude, or local Ollama), rule-based fallback, guardrails | Working; LLM path unit-tested with stubs (no API key in dev environment) |
| Adaptive sessions, practice modes, progress tracking, dashboard, history | Working, tested |
| Accounts (JWT), consent-gated recording storage, data export/deletion | Working, tested |
| wav2vec2 phoneme engine | Implemented, **not validated** (model hub unreachable in the dev environment) |

## Quick start

### Option A: Docker (one command)

```bash
docker compose up --build
```

Open http://localhost:8080 (API docs at http://localhost:8000/docs). The first build
downloads CPU PyTorch and the speech models (~1.5 GB).
For a small image without the phoneme model (acoustic baseline only), run
`INSTALL_ML=false docker compose up --build`.

### Option B: Local development (Windows, macOS, Linux)

Requirements: Python 3.11+, Node 20+. Then:

```bash
python scripts/dev.py setup      # venv, Python + Node dependencies, models, database
python scripts/dev.py backend    # http://localhost:8000
python scripts/dev.py frontend   # http://localhost:5173 (in a second terminal)
```

`scripts/dev.py` is a cross-platform task runner (`make <target>` works too on
macOS/Linux). See [docs/development_guide.md](docs/development_guide.md) for manual
steps, running each service on its own, and the frontend **mock mode** that needs
no backend.

### Enable AI-written feedback (optional)

Without an LLM the app uses deterministic, rule-based feedback built from the
same measured issues. To use Claude, set in `.env`:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
# LLM_MODEL defaults to claude-opus-5-5
```

Or run a free local model with [Ollama](https://ollama.com): `LLM_PROVIDER=ollama`,
`OLLAMA_MODEL=llama3.1:8b`. The Claude provider uses structured JSON output and
server-side refusal fallbacks (`fallbacks: "default"`).

## How scoring works (short version)

1. **Quality gate.** Recordings that are silent, too quiet, clipped, noisy or cut off are rejected with a specific message.
2. **Phoneme GOP.** The Allosaurus English phone recogniser gives frame-level CTC posteriors. For each expected
   phone we compare the likelihood of the expected sequence with versions where that phone is replaced by
   every other phone or deleted (substitution-aware Goodness of Pronunciation). This catches fluent-but-wrong
   sounds (e.g. "wabbit"), which forced alignment alone would accept.
3. **Calibration.** Posteriors are mapped to 0-100 with per-phone curves fitted to expert ratings
   (speechocean762 train split); a word-level curve converts sound scores into an expected expert word rating.
4. **Overall score** = 60% sounds + 20% DTW acoustic similarity + 10% syllables + 10% timing (configurable).
5. **Confidence and status:** `assessed`, `inconclusive` or `retry_required`; "word recognised" and
   "phonetically accurate" are reported separately.

Held-out results (2,500 utterances, 47,369 phones): mispronunciation detection **AUC 0.91**,
phone-level correlation with experts **r = 0.47**, word-level **r = 0.48**. Details, limitations and
how to rerun: [docs/validation.md](docs/validation.md).

## Repository layout

```
frontend/          React + TypeScript + Vite + Tailwind + Recharts (UI team)
backend/           FastAPI, SQLAlchemy, Alembic, auth, sessions, progress (backend team)
speech_analysis/   audio processing, features, phoneme engines, scoring, TTS (speech team)
ai_feedback/       prompts, LLM providers, guardrails, articulation knowledge base (AI team)
data/              word database (words.json, built from data/source/words.csv)
docs/              architecture, API, development, deployment, validation, roadmap, tasks
e2e/               browser end-to-end test (Playwright, fake microphone)
scripts/           setup, model download, evaluation, calibration, word DB build
.github/           CI workflows, issue and PR templates
```

## Documentation

- [docs/architecture.md](docs/architecture.md): components, data flow, scoring pipeline, database
- [docs/api_documentation.md](docs/api_documentation.md): endpoints, schemas, errors
- [docs/development_guide.md](docs/development_guide.md): setup, testing each module, migrations
- [docs/deployment.md](docs/deployment.md): configuration per environment, production checklist
- [docs/validation.md](docs/validation.md): evaluation method and results
- [docs/roadmap.md](docs/roadmap.md) and [docs/task_breakdown.md](docs/task_breakdown.md): planning
- [TEAM_GUIDE.md](TEAM_GUIDE.md) and [CONTRIBUTING.md](CONTRIBUTING.md): how the team works

## Licences and attribution

The project licence has not been chosen yet. Third-party components and their licences
(Allosaurus GPL-3.0, Piper voices CC BY 4.0, CMUdict BSD, speechocean762 CC BY 4.0, ...) are
listed in [THIRD_PARTY.md](THIRD_PARTY.md). Check them before distributing builds.
