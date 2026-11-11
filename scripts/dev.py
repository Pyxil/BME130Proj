#!/usr/bin/env python3
"""Cross-platform developer task runner (Windows, macOS, Linux).

    python scripts/dev.py setup [--no-ml]   create .venv, install everything, download models, init DB
    python scripts/dev.py backend           run the API with auto-reload (http://localhost:8000)
    python scripts/dev.py frontend          run the Vite dev server (http://localhost:5173)
    python scripts/dev.py mock              frontend with the in-browser mock API (no backend needed)
    python scripts/dev.py test [--models]   Python + frontend tests (--models adds model integration tests)
    python scripts/dev.py lint              ruff, eslint, TypeScript
    python scripts/dev.py check             everything CI checks (lint, tests, contract and data drift)
    python scripts/dev.py migrate           apply Alembic migrations + seed words
    python scripts/dev.py makemigration "message"
    python scripts/dev.py contracts         regenerate OpenAPI/JSON schemas and frontend TypeScript types
    python scripts/dev.py e2e               browser end-to-end test (backend and frontend must be running)
"""

from __future__ import annotations

import os
import platform
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
IS_WIN = platform.system() == "Windows"
PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
NPM = "npm.cmd" if IS_WIN else "npm"


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, env={**os.environ, **(env or {})})


def py() -> str:
    return str(PY) if PY.exists() else sys.executable


def check_tools(args: list[str]) -> None:
    mac = platform.system() == "Darwin"
    if sys.version_info < (3, 11):  # noqa: UP036 - dev.py may be launched with an old system Python (macOS 3.9)
        hint = ("macOS's built-in python3 is too old. Install Python 3.12 with `brew install python@3.12`, "
                "then run `python3.12 scripts/dev.py setup`." if mac else "Install Python 3.11-3.13.")
        sys.exit(f"Python 3.11+ is required (this is {platform.python_version()}). {hint}")
    if mac and platform.machine() == "x86_64" and sys.version_info >= (3, 13) and "--no-ml" not in args:
        sys.exit("PyTorch has no Intel-Mac builds for Python 3.13+. Use `python3.12 scripts/dev.py setup` "
                 "(or add --no-ml for the acoustic baseline).")
    if shutil.which(NPM) is None:
        sys.exit("Node.js 20+ is required for the frontend" + (" (`brew install node`)." if mac else "."))


def write_env_file() -> None:
    """Create .env from .env.example with a freshly generated SECRET_KEY."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    text = text.replace("\nSECRET_KEY=\n", f"\nSECRET_KEY={secrets.token_urlsafe(48)}\n", 1)
    (ROOT / ".env").write_text(text, encoding="utf-8")
    print("created .env from .env.example (with a random SECRET_KEY)")


def setup(args: list[str]) -> None:
    check_tools(args)
    if not VENV.exists():
        print("creating .venv")
        venv.create(VENV, with_pip=True)
    run([py(), "-m", "pip", "install", "--upgrade", "pip"])
    run([py(), "-m", "pip", "install", "-e", ".[dev,llm,postgres]"])
    if "--no-ml" not in args:
        if platform.system() == "Linux":  # avoid the multi-GB CUDA build on Linux
            run([py(), "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"])
        run([py(), "-m", "pip", "install", "-e", ".[ml]"])
        run([py(), "scripts/download_models.py"])
    else:
        run([py(), "scripts/download_models.py", "--skip-allosaurus"])
    if not (ROOT / ".env").exists():
        write_env_file()
    run([NPM, "ci"], cwd=ROOT / "frontend")
    run([py(), "-m", "backend.database.init_db"])
    print("\nSetup complete. Next: `python scripts/dev.py backend` and `python scripts/dev.py frontend`.")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    fe = ROOT / "frontend"
    if cmd == "setup":
        setup(args)
    elif cmd == "backend":
        run([py(), "-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000"])
    elif cmd == "frontend":
        run([NPM, "run", "dev"], cwd=fe)
    elif cmd == "mock":
        run([NPM, "run", "dev:mock"], cwd=fe)
    elif cmd == "test":
        marker = [] if "--models" in args else ["-m", "not model"]
        run([py(), "-m", "pytest", "-q", *marker])
        run([NPM, "test"], cwd=fe)
    elif cmd == "lint":
        run([py(), "-m", "ruff", "check", "backend", "speech_analysis", "ai_feedback", "scripts"])
        run([NPM, "run", "lint"], cwd=fe)
        run([NPM, "run", "typecheck"], cwd=fe)
    elif cmd == "check":
        main_args = sys.argv
        for sub in (["lint"], ["test"]):
            sys.argv = [main_args[0], *sub]
            main()
        run([py(), "-m", "backend.scripts.export_openapi", "--check"])
        run([py(), "scripts/build_word_database.py", "--check"])
    elif cmd == "migrate":
        run([py(), "-m", "backend.database.init_db"])
    elif cmd == "makemigration":
        if not args:
            sys.exit('usage: dev.py makemigration "describe the change"')
        run([py(), "-m", "alembic", "-c", "backend/alembic.ini", "revision", "--autogenerate", "-m", args[0]])
    elif cmd == "contracts":
        run([py(), "-m", "backend.scripts.export_openapi"])
        run([NPM, "run", "gen:api"], cwd=fe)
    elif cmd == "e2e":
        run(["node", "e2e/practice-flow.cjs"], env={"PYTHON": py()})
    else:
        print(f"unknown command {cmd!r}\n{__doc__}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
