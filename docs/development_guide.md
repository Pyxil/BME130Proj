# Development guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11-3.13 | 3.12 in Docker and CI |
| Node.js | 22.12+ (any current LTS) | Vite 8 and Vitest 5 need it; `dev.py setup` checks |
| Git | any recent | |
| ffmpeg | optional | decode non-WAV uploads (the web client sends WAV) |
| espeak-ng | optional | only to rebuild British variants of the word database; fallback TTS |
| Docker | optional | `docker compose up --build` runs everything |

Works on Windows, macOS and Linux: step-by-step for [macOS](#macos-apple-silicon-or-intel) and
[Windows](#windows) below. The [setup workflow](../.github/workflows/setup-smoke.yml) runs this exact setup on
all three every week and whenever setup files change.

## macOS (Apple Silicon or Intel)

```bash
xcode-select --install                         # Git and compilers (skip if already installed)
# Homebrew, if you don't have it: https://brew.sh
brew install python@3.12 node                  # required
brew install ffmpeg espeak-ng                  # optional (non-WAV uploads, fallback TTS)
git clone https://github.com/Pyxil/BME130Proj.git && cd BME130Proj
python3.12 scripts/dev.py setup                # ~5-10 min: venv, PyTorch, models, Node packages, database
python3.12 scripts/dev.py backend              # terminal 1 -> http://localhost:8000/docs
python3.12 scripts/dev.py frontend             # terminal 2 -> open http://localhost:5173
```

- Use **Python 3.12**: the `python3` that ships with macOS is too old, and PyTorch has no Intel-Mac builds
  for Python 3.13+. `dev.py` checks this and tells you what to do.
- The first time you press Record, the browser asks for the microphone. If macOS blocks it, enable your
  browser under **System Settings > Privacy & Security > Microphone**. Use Chrome if you can: it is what
  the automated tests use. Safari should work on `localhost` (the recorder handles Safari's audio rules)
  but has not been tested on a real Mac yet.
- Python from python.org instead of Homebrew: if model downloads fail with a certificate error, run
  *Install Certificates.command* in `/Applications/Python 3.12/` (the script also falls back to certifi).
- Docker Desktop alternative: `docker compose up --build`, then open http://localhost:8080.

## Windows

In **PowerShell** (Start menu > *Terminal* or *Windows PowerShell*):

```powershell
winget install Python.Python.3.12              # or the installer from python.org
winget install OpenJS.NodeJS.LTS
winget install Git.Git
# close and reopen the terminal so the new commands are found
cd $HOME
git clone https://github.com/Pyxil/BME130Proj.git
cd BME130Proj
py -3.12 scripts/dev.py setup                  # ~5-10 min: venv, PyTorch, models, Node packages, database
py -3.12 scripts/dev.py backend                # terminal 1 -> http://localhost:8000/docs
py -3.12 scripts/dev.py frontend               # terminal 2 -> open http://localhost:5173
```

- No `winget`? Use the installers from python.org, nodejs.org (LTS) and git-scm.com instead.
- `py` is the Python launcher that comes with Python; `py -3.12` picks 3.12 even when other versions are
  installed. If typing `python` opens the Microsoft Store, ignore it and use `py -3.12`.
- Keep the project out of folders that OneDrive syncs (Desktop, Documents): OneDrive locks files while it
  syncs, and very long paths can break the PyTorch install. `C:\Users\<you>\BME130Proj` (from `cd $HOME`)
  is fine. If the Python installer offers *Disable path length limit*, accept it.
- Microphone: **Settings > Privacy & security > Microphone**: turn on *Microphone access* and *Let desktop
  apps access your microphone*, then allow it when the browser asks. Use Edge or Chrome.
- Windows on ARM (e.g. Snapdragon laptops): if PyTorch does not install, use the x64 Python installer from
  python.org, or run `py -3.12 scripts/dev.py setup --no-ml` (acoustic scores only, no sound-by-sound scores).
- No `make` needed: `py -3.12 scripts/dev.py help` lists every task.
- Docker Desktop alternative (WSL 2): `docker compose up --build`, then open http://localhost:8080.

## First-time setup

```bash
git clone https://github.com/Pyxil/BME130Proj.git && cd BME130Proj
python scripts/dev.py setup        # or: python scripts/dev.py setup --no-ml   (skip PyTorch, ~2 GB smaller)
```

What `setup` does (equivalent manual steps):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,llm,postgres]"
pip install torch --index-url https://download.pytorch.org/whl/cpu   # Linux: CPU wheel avoids CUDA downloads
pip install -e ".[ml]"                                                # Allosaurus
python scripts/download_models.py                                     # ./models (Allosaurus + Piper voices)
cp .env.example .env            # Windows: copy; dev.py setup also fills in a random SECRET_KEY
cd frontend && npm ci && cd ..
python -m backend.database.init_db                                    # Alembic migrations + seed 135 words
```

Without `.[ml]` the analyzer runs in **acoustic baseline** mode: no phoneme scores, clearly labelled in
results and in the UI.

## Running services independently

| Service | Command | URL |
|---|---|---|
| Backend API | `python scripts/dev.py backend` (`uvicorn backend.main:app --reload`) | http://localhost:8000/docs |
| Frontend | `python scripts/dev.py frontend` (`npm run dev` in `frontend/`) | http://localhost:5173 |
| Frontend without backend | `python scripts/dev.py mock` (`npm run dev:mock`) | http://localhost:5173 ("Mock data" badge) |
| Whole stack in Docker | `docker compose up --build` | http://localhost:8080 |
| Stop Docker stack | `docker compose down` (add `-v` to delete the database volume) | |

All components read one configuration file, the repository-root `.env` (backend settings, `SA_*` analysis
settings, `LLM_*`/`ANTHROPIC_API_KEY` feedback settings and the frontend's `VITE_*` values). Variables already
set in your shell take precedence. The Vite dev server proxies `/api` to `VITE_API_PROXY_TARGET`
(default `http://127.0.0.1:8000`). The dev server listens on localhost only; `npm run dev -- --host`
exposes it to your network on purpose.
Microphone access works on `localhost` or HTTPS only.

### Using the analysis library alone (speech team)

```python
from speech_analysis.pipeline import PronunciationAnalyzer, load_words
words = {w["word"]: w for w in load_words()}
result = PronunciationAnalyzer().analyze(open("my.wav", "rb").read(), words["rabbit"])
print(result.model_dump_json(indent=2))
```

### Using the feedback engine alone (AI team)

```python
from ai_feedback import FeedbackService, FeedbackRequest
import json
analysis = json.load(open("frontend/src/mocks/fixtures.json"))["samples"]["rabbit_r_as_w"]["analysis"]
print(FeedbackService().generate(FeedbackRequest(analysis=analysis)).model_dump_json(indent=2))
```

Set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=ollama`, to exercise an LLM.

## Tests

| Scope | Command |
|---|---|
| Everything fast (no models) | `python scripts/dev.py test` |
| Python only | `pytest -q -m "not model"` |
| Speech library unit tests | `pytest speech_analysis/tests/test_units.py speech_analysis/tests/test_ctc_gop.py` |
| Pipeline with real models | `pytest -m model` (needs `scripts/download_models.py`) |
| AI feedback | `pytest ai_feedback/tests` |
| Backend API | `pytest backend/tests` (uses a temporary SQLite DB and a fake analyzer) |
| Frontend | `cd frontend && npm test` |
| Lint / types | `python scripts/dev.py lint` |
| All CI checks | `python scripts/dev.py check` |
| Browser end-to-end | start backend + frontend, then `python scripts/dev.py e2e` |
| Live backend + dev server check | `python scripts/dev.py smoke` (stop running servers first) |
| Accuracy on real speech | see [validation.md](validation.md#reproduce) |

Deterministic fixtures: `speech_analysis/tests/fixtures/` (synthetic recordings with controlled errors,
regenerate with `scripts/generate_test_fixtures.py`, then commit). Frontend mock data is recorded from the
real backend: `python -m backend.scripts.generate_frontend_fixtures`.

## Database migrations (Alembic)

```bash
# 1. change backend/models/__init__.py
python scripts/dev.py makemigration "add streak counter to users"
# 2. review backend/alembic/versions/<new>.py (autogenerate is not perfect)
python scripts/dev.py migrate          # upgrade + seed
alembic -c backend/alembic.ini downgrade -1   # make sure downgrade works
```

CI applies all migrations on PostgreSQL and SQLite, runs `alembic check` (models and migrations must
match) and tests downgrade.

## Shared contracts

| Contract | Source of truth | Regenerate |
|---|---|---|
| REST API | FastAPI routes + `backend/schemas` | `python scripts/dev.py contracts` |
| Analysis result | `speech_analysis/contracts.py` | same (writes `docs/schemas/*.json`) |
| Feedback | `ai_feedback/contracts.py` | same |
| TypeScript types | generated `frontend/src/types/api.generated.ts` | `npm run gen:api` |
| Word database | `data/source/words.csv` | `python scripts/build_word_database.py` (needs `cmudict`, espeak-ng) |

## Adding words

Add a row to `data/source/words.csv` (word, difficulty, category, focus phones in ARPAbet, optional
overrides such as `us_override` = `AH0 R AW1 N D|ER0 AW1 N D`), run `python scripts/build_word_database.py`,
review the diff of `data/words.json`, then `python -m backend.database.init_db --seed`.
Human reference recordings can be dropped into `data/reference_audio/<word>.wav` (or `<word>_gb.wav`).

## Troubleshooting

- *"Allosaurus model not found"*: run `python scripts/download_models.py`.
- *No reference audio (404)*: Piper voices missing; the UI falls back to browser speech synthesis.
- *Microphone permission denied*: allow it in the browser's site settings; use localhost or HTTPS.
- *Slow first analysis*: models load lazily; `WARMUP_ON_START=true` loads them in the background at start.
- *Port 8000 or 5173 already in use*: a backend or frontend is still running in another terminal; stop it
  with Ctrl+C.
- *Setup stops with a Python or Node.js version message*: install the version it names, open a new
  terminal, and run setup again (it picks up where it left off).
