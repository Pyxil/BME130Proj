#!/usr/bin/env python3
"""Turn docs/tasks.json into GitHub issues, labels and milestones (or a Markdown table).

    python scripts/create_github_issues.py --write-markdown          # regenerate docs/task_breakdown.md
    python scripts/create_github_issues.py --create                  # dry run: print what would be created
    python scripts/create_github_issues.py --create --apply [--repo owner/name]

Requires the GitHub CLI (`gh auth login`) for --create --apply.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "docs" / "tasks.json"
OUT = ROOT / "docs" / "task_breakdown.md"
TEAM_LABELS = {"frontend": "team: frontend", "backend": "team: backend", "speech": "team: speech",
               "ai": "team: ai", "qa-integration": "team: qa-integration"}


def body(task: dict) -> str:
    lines = [task["description"], "", "### Acceptance criteria", *[f"- [ ] {a}" for a in task["acceptance"]]]
    if task["depends"]:
        lines += ["", "### Depends on", ", ".join(task["depends"])]
    lines += ["", f"Estimate: {task['size']} - Task ID: {task['id']}"]
    return "\n".join(lines)


def write_markdown(data: dict) -> None:
    ms = {m["id"]: m for m in data["milestones"]}
    out = ["# Initial task breakdown", "",
           "Generated from `docs/tasks.json` by `scripts/create_github_issues.py --write-markdown`.",
           "Create the GitHub issues with `python scripts/create_github_issues.py --create --apply`.", ""]
    for mid, m in ms.items():
        out += [f"## {m['title']}", "", m["description"], "",
                "| ID | Team | Task | Size | Depends on |", "|---|---|---|---|---|"]
        for t in data["tasks"]:
            if t["milestone"] == mid:
                out.append(f"| {t['id']} | {t['team']} | {t['title']} | {t['size']} | {', '.join(t['depends']) or '-'} |")
        out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


def gh(args: list[str], apply: bool) -> None:
    print("gh " + " ".join(args))
    if apply:
        subprocess.run(["gh", *args], check=False)


def create(data: dict, apply: bool, repo: str | None) -> None:
    repo_args = ["--repo", repo] if repo else []
    for label in [*TEAM_LABELS.values(), "type: task", "contract-change", "privacy", "blocked"]:
        gh(["label", "create", label, "--force", *repo_args], apply)
    for m in data["milestones"]:
        target = repo or "{owner}/{repo}"
        gh(["api", f"repos/{target}/milestones", "-f", f"title={m['title']}", "-f", f"description={m['description']}"], apply)
    titles = {m["id"]: m["title"] for m in data["milestones"]}
    for t in data["tasks"]:
        gh(["issue", "create", "--title", f"[{t['id']}] {t['title']}", "--body", body(t),
            "--label", TEAM_LABELS[t["team"]], "--label", "type: task", "--milestone", titles[t["milestone"]],
            *repo_args], apply)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-markdown", action="store_true")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--apply", action="store_true", help="actually call gh (otherwise dry run)")
    ap.add_argument("--repo")
    args = ap.parse_args()
    data = json.loads(TASKS.read_text(encoding="utf-8"))
    if args.write_markdown:
        write_markdown(data)
    if args.create:
        create(data, args.apply, args.repo)
    if not (args.write_markdown or args.create):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
