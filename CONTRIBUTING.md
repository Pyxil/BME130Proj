# Contributing

Thanks for helping! Start with [TEAM_GUIDE.md](TEAM_GUIDE.md) (team ownership, branches, reviews) and
[docs/development_guide.md](docs/development_guide.md) (setup and tests).

## Quick workflow

```bash
git switch -c feat/<issue>-<short-name>
python scripts/dev.py setup          # once
# ... make changes ...
python scripts/dev.py check          # lint, types, tests, contract and data drift
git commit -m "feat(frontend): show slow playback button"
git push -u origin HEAD              # open a draft PR and fill in the template
```

## Code style

- Python: ruff (`ruff check --fix`), type hints, docstrings on public functions; 120-char lines.
- TypeScript/React: ESLint + strict TypeScript; functional components and hooks; Tailwind utility classes;
  accessible markup (labels, roles, keyboard support, visible focus, colour never the only signal).
- Keep modules loosely coupled: the speech and AI packages must not import the backend.

## Rules that protect users

1. **Never commit recordings, personal data, API keys or `.env` files.** Use synthetic fixtures.
2. **No invented or random scores.** Every number must come from the recording; label mocks clearly.
3. **No clinical claims.** Do not describe scores as diagnoses or clinical assessments.
4. **Grounded feedback only.** The AI must not mention errors the analysis did not detect; keep the guardrails.
5. Scoring changes come with a validation run (`scripts/evaluate_speechocean762.py`) in the PR.

## Contract changes

If you touch `speech_analysis/contracts.py`, `ai_feedback/contracts.py`, `backend/schemas` or a route:

```bash
python scripts/dev.py contracts      # regenerates docs/openapi.json, docs/schemas, frontend types
```

Label the PR `contract-change`, get approval from consuming teams, and add a CHANGELOG entry.

## Database changes

Every model change needs an Alembic migration (`python scripts/dev.py makemigration "message"`); test
upgrade and downgrade.

## Reporting bugs and requesting features

Use the issue forms (bug, feature, development task). For security or privacy problems, contact the
maintainers privately instead of opening a public issue.
