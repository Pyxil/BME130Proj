"""Live smoke test: start the real backend and Vite dev server, then use the app through HTTP.

This is what the cross-platform CI workflow runs after `dev.py setup` on Windows, macOS and
Linux, and it is handy locally after changing setup, configuration or dependencies:

    python scripts/dev.py smoke                    # backend + frontend dev server
    python scripts/dev.py smoke --no-frontend      # backend only
    python scripts/dev.py smoke --require-phonemes # fail unless the phoneme model is loaded

It uses the same ports as `dev.py backend` / `dev.py frontend` (8000 and 5173) so the default
proxy settings are exercised; stop those first, or pass --port / --frontend-port.  A temporary
account is created and deleted again.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "speech_analysis" / "tests" / "fixtures"


def port_in_use(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:  # e.g. IPv6 disabled
            continue
    return False


def start(name: str, cmd: list[str], cwd: Path, logs: Path, env: dict | None = None) -> subprocess.Popen:
    print(f"starting {name}: {' '.join(cmd)}", flush=True)
    log = open(logs / f"{name}.log", "w", encoding="utf-8")  # stays open while the child writes to it
    # Output goes to a file, never to our own pipe, so no child can keep a CI step waiting.
    return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})})


def wait_for(url: str, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=5, trust_env=False) as c:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"process for {url} exited with code {proc.returncode}")
            try:
                if c.get(url).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
    raise RuntimeError(f"timed out after {timeout:.0f}s waiting for {url}")


def analyze(c: httpx.Client, headers: dict, word_id: int, fixture: str) -> dict:
    with open(FIXTURES / fixture, "rb") as f:
        r = c.post("/pronunciation/analyze", headers=headers,
                   files={"audio": (fixture, f, "audio/wav")}, data={"word_id": str(word_id)})
    r.raise_for_status()
    return r.json()["analysis"]


def check_api(api: str, require_phonemes: bool) -> None:
    with httpx.Client(base_url=api, timeout=180, trust_env=False) as c:
        status = c.get("/system/status").raise_for_status().json()
        engine = status["analysis_engine"]
        print(f"engine: {engine['name']} (phoneme-level: {engine['phoneme_level']}), "
              f"reference voices: {status['reference_audio']['piper_voices']}, words: {status['words']}")
        if require_phonemes and not engine["phoneme_level"]:
            raise RuntimeError(f"phoneme model not loaded: {engine.get('notes')}")

        email = f"smoke-{uuid.uuid4().hex[:12]}@example.com"
        r = c.post("/auth/register", json={"email": email, "password": "smoke-test-password", "display_name": "Smoke"})
        r.raise_for_status()
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        try:
            words = c.get("/words", params={"limit": 200}, headers=headers).raise_for_status().json()["items"]
            word_id = next(w["id"] for w in words if w["word"] == "rabbit")

            audio = c.get(f"/words/{word_id}/audio", headers=headers).raise_for_status()
            if not audio.headers.get("content-type", "").startswith("audio/") or len(audio.content) < 1000:
                raise RuntimeError(f"reference audio looks wrong: {audio.headers.get('content-type')}")
            print(f"reference audio: {len(audio.content)} bytes ({audio.headers.get('content-type')})")

            good = analyze(c, headers, word_id, "rabbit_correct.wav")
            bad = analyze(c, headers, word_id, "rabbit_r_as_w.wav")
            issues = [i["message"] for i in bad["identified_issues"]]
            print(f"rabbit, correct: {good['status']} {good['overall_score']} ({good['rating']})")
            print(f"rabbit, /r/ as /w/: {bad['status']} {bad['overall_score']} ({bad['rating']}); issues: {issues}")
            if good["status"] != "assessed" or (good["overall_score"] or 0) < 80:
                raise RuntimeError("the correct recording should be assessed with a high score")
            if engine["phoneme_level"]:
                if (bad["overall_score"] or 0) >= good["overall_score"]:
                    raise RuntimeError("the mispronounced recording should score lower than the correct one")
                if not any(i.get("phoneme") == "r" for i in bad["identified_issues"]):
                    raise RuntimeError("the /r/ -> /w/ substitution should be reported")
        finally:
            with contextlib.suppress(httpx.HTTPError):  # remove the temporary account
                c.delete("/users/me", headers=headers)


def check_frontend(web: str) -> None:
    with httpx.Client(timeout=60, trust_env=False) as c:
        html = c.get(f"{web}/").raise_for_status().text
        if 'id="root"' not in html:
            raise RuntimeError("the dev server did not return the app's index.html")
        health = c.get(f"{web}/api/health").raise_for_status().json()  # through the Vite proxy
        if health.get("status") != "ok":
            raise RuntimeError(f"/api through the dev-server proxy returned {health}")
    print(f"frontend: {web} serves the app and proxies /api to the backend")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # IPA in messages must not crash a non-UTF-8 console
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description="Start the backend and dev server and check them end to end.")
    ap.add_argument("--port", type=int, default=8000, help="backend port (default 8000)")
    ap.add_argument("--frontend-port", type=int, default=5173, help="dev server port (default 5173)")
    ap.add_argument("--no-frontend", action="store_true", help="only check the backend")
    ap.add_argument("--require-phonemes", action="store_true", help="fail unless the phoneme model is loaded")
    ap.add_argument("--startup-timeout", type=float, default=300, help="seconds to wait for the backend")
    args = ap.parse_args()

    ports = [args.port] + ([] if args.no_frontend else [args.frontend_port])
    busy = [p for p in ports if port_in_use(p)]
    if busy:
        print(f"port(s) {busy} already in use: stop the running backend/frontend or pass --port/--frontend-port")
        return 2

    logs = Path(tempfile.mkdtemp(prefix="smoke-logs-"))
    procs: list[subprocess.Popen] = []
    try:
        backend = start("backend", [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(args.port)],
                        ROOT, logs)
        procs.append(backend)
        api = f"http://127.0.0.1:{args.port}/api"
        wait_for(f"{api}/health", backend, args.startup_timeout)
        check_api(api, args.require_phonemes)

        if not args.no_frontend:
            vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
            if not vite.exists():
                raise RuntimeError("frontend packages are missing: run `dev.py setup` (or `npm ci` in frontend/)")
            env = None if args.port == 8000 else {"VITE_API_PROXY_TARGET": f"http://127.0.0.1:{args.port}"}
            # node directly (not npm), so stopping it really stops the server on every OS
            frontend = start("frontend", ["node", str(vite), "--port", str(args.frontend_port), "--strictPort"],
                             ROOT / "frontend", logs, env)
            procs.append(frontend)
            web = f"http://localhost:{args.frontend_port}"
            wait_for(f"{web}/", frontend, 120)
            check_frontend(web)
        print("SMOKE TEST PASSED")
        return 0
    except Exception as exc:  # report everything with the server logs
        print(f"SMOKE TEST FAILED: {type(exc).__name__}: {exc}")
        for log in sorted(logs.glob("*.log")):
            print(f"--- last lines of {log.name} ---")
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))
        return 1
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
