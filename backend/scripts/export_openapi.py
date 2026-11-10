#!/usr/bin/env python3
"""Export API contracts for other teams.

Writes ``docs/openapi.json`` (from FastAPI) and JSON Schemas for the analysis
result, feedback response and the LLM output schema into ``docs/schemas/``.
The frontend generates TypeScript types from ``docs/openapi.json``
(``npm run gen:api``).  With ``--check`` the script fails if the committed
files are stale, which CI uses to catch unannounced contract changes.

    python -m backend.scripts.export_openapi [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("AUTO_MIGRATE", "false")
os.environ.setdefault("WARMUP_ON_START", "false")


def render() -> dict[Path, str]:
    from ai_feedback.contracts import LLM_OUTPUT_SCHEMA, FeedbackResponse
    from backend.main import create_app
    from speech_analysis.contracts import AnalysisResult

    def dump(obj) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    return {
        ROOT / "docs" / "openapi.json": dump(create_app().openapi()),
        ROOT / "docs" / "schemas" / "analysis_result.schema.json": dump(AnalysisResult.model_json_schema()),
        ROOT / "docs" / "schemas" / "feedback_response.schema.json": dump(FeedbackResponse.model_json_schema()),
        ROOT / "docs" / "schemas" / "llm_feedback_output.schema.json": dump(LLM_OUTPUT_SCHEMA),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    stale = []
    for path, text in render().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("Contract files are out of date (run: python -m backend.scripts.export_openapi):", file=sys.stderr)
        for s in stale:
            print(f"  {s}", file=sys.stderr)
        return 1
    if args.check:
        print("contracts up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
