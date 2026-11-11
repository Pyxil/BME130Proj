#!/usr/bin/env python3
"""Cross-platform developer task runner (Windows, macOS, Linux).

    python scripts/dev.py setup [--ml]      create .venv, install everything, download voices, init DB
                                            (--ml adds the optional neural phoneme model, ~2 GB)
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
    python scripts/dev.py smoke             start the real backend + dev server and check them end to end

On Windows run it as `py -3.12 scripts/dev.py ...`, on macOS as `python3.12 scripts/dev.py ...`.
"""

from __future__ import annotations

import os
import platform
import re
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


def node_version() -> tuple[int, int] | None:
    """(major, minor) of the `node` on PATH, or None if it is missing or unreadable."""
    node = shutil.which("node")
    if node is None:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout
        major, minor = (int(x) for x in out.strip().lstrip("v").split(".")[:2])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return major, minor


def launcher() -> str:
    """How the docs tell people to start Python on this OS."""
    return {"Windows": "py -3.12", "Darwin": "python3.12"}.get(platform.system(), "python3")


def check_tools(args: list[str]) -> None:
    system = platform.system()
    mac, win = system == "Darwin", system == "Windows"
    if sys.version_info < (3, 11):  # noqa: UP036 - dev.py may be launched with an old system Python (macOS 3.9)
        if mac:
            hint = ("macOS's built-in python3 is too old. Install Python 3.12 with `brew install python@3.12`, "
                    "then run `python3.12 scripts/dev.py setup`.")
        elif win:
            hint = ("Install Python 3.12 (`winget install Python.Python.3.12` or python.org), "
                    "then run `py -3.12 scripts/dev.py setup`.")
        else:
            hint = "Install Python 3.11-3.13."
        sys.exit(f"Python 3.11+ is required (this is {platform.python_version()}). {hint}")
    if win and sys.version_info >= (3, 13) and "--ml" in args:
        sys.exit(f"On Windows the optional phoneme model needs Python 3.11 or 3.12 (this is "
                 f"{platform.python_version()}): one of its packages, editdistance, has no ready-made Windows "
                 "build for newer versions, and building it needs Microsoft's C++ tools. Run "
                 "`py -3.12 scripts/dev.py setup --ml` (install it with `winget install Python.Python.3.12`), "
                 "or leave out --ml: the default signal analysis does not need it.")
    if mac and platform.machine() == "x86_64" and sys.version_info >= (3, 13) and "--ml" in args:
        sys.exit("PyTorch has no Intel-Mac builds for Python 3.13+. Use `python3.12 scripts/dev.py setup --ml` "
                 "(or leave out --ml: the default signal analysis does not need PyTorch).")
    install_node = ("with `brew install node`" if mac else
                    "with `winget install OpenJS.NodeJS.LTS`, then open a new terminal" if win else
                    "from https://nodejs.org (current LTS)")
    version = node_version()
    if shutil.which(NPM) is None or version is None:
        sys.exit(f"Node.js 22.12+ is required for the frontend. Install it {install_node}.")
    if version < (22, 12):  # Vite 8 and Vitest 5 need it
        sys.exit(f"Node.js {version[0]}.{version[1]} is too old for the frontend tools (needs 22.12+). "
                 f"Install it {install_node}.")


def write_env_file() -> None:
    """Create .env from .env.example with a freshly generated SECRET_KEY."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    text = text.replace("\nSECRET_KEY=\n", f"\nSECRET_KEY={secrets.token_urlsafe(48)}\n", 1)
    (ROOT / ".env").write_text(text, encoding="utf-8")
    print("created .env from .env.example (with a random SECRET_KEY)")


def venv_python_version() -> tuple[int, int] | None:
    """(major, minor) of the Python that created .venv, read from its pyvenv.cfg."""
    try:
        text = (VENV / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^version(?:_info)?\s*=\s*(\d+)\.(\d+)", text, re.MULTILINE)
    return (int(m.group(1)), int(m.group(2))) if m else None


def ensure_venv() -> None:
    """Create .venv, or recreate it when it is broken or was made with a different Python.

    A .venv left behind by another Python (an earlier run with a newer `python`, or one an editor
    created) would otherwise be reused and fail later, e.g. building editdistance on Windows.
    """
    if VENV.exists():
        made_with, running = venv_python_version(), sys.version_info[:2]
        if PY.exists() and made_with in (None, running):
            return
        if made_with not in (None, running):
            reason = (f"it was made with Python {made_with[0]}.{made_with[1]}, "
                      f"but setup is running on {running[0]}.{running[1]}")
        else:
            reason = "it has no Python interpreter (an earlier setup was interrupted?)"
        print(f"recreating .venv: {reason}")
        try:
            shutil.rmtree(VENV)
        except OSError as exc:
            sys.exit(f"Could not delete .venv ({exc}). Close anything that uses it (the backend, VS Code), "
                     "delete the .venv folder, and run setup again.")
    print("creating .venv")
    venv.create(VENV, with_pip=True)


def migrate_env_file() -> None:
    """Switch an untouched old default (SA_ENGINE=auto) to the new default analysis (signal)."""
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    if "\nSA_ENGINE=auto\n" in text:
        env.write_text(text.replace("\nSA_ENGINE=auto\n", "\nSA_ENGINE=signal\n", 1), encoding="utf-8")
        print("updated .env: SA_ENGINE=signal (signal analysis is now the default; "
              "set SA_ENGINE=allosaurus to use the optional phoneme model)")


def setup(args: list[str]) -> None:
    check_tools(args)
    ensure_venv()
    run([py(), "-m", "pip", "install", "--upgrade", "pip"])
    run([py(), "-m", "pip", "install", "-e", ".[dev,llm,postgres]"])
    if "--ml" in args:  # optional neural phoneme model (for comparison with the signal analysis)
        if platform.system() == "Linux":  # avoid the multi-GB CUDA build on Linux
            run([py(), "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"])
        run([py(), "-m", "pip", "install", "-e", ".[ml]"])
        run([py(), "scripts/download_models.py"])
    else:
        run([py(), "scripts/download_models.py", "--skip-allosaurus"])
    if not (ROOT / ".env").exists():
        write_env_file()
    else:
        migrate_env_file()
    run([NPM, "ci"], cwd=ROOT / "frontend")
    run([py(), "-m", "backend.database.init_db"])
    py_cmd = launcher()
    print(f"\nSetup complete. Start the app in two terminals:\n  {py_cmd} scripts/dev.py backend\n"
          f"  {py_cmd} scripts/dev.py frontend\nthen open http://localhost:5173")


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
    elif cmd == "smoke":
        run([py(), "scripts/smoke_test.py", *args])
    else:
        print(f"unknown command {cmd!r}\n{__doc__}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
