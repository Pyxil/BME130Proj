# Team guide

How five teams build this product in parallel without stepping on each other.

## 1. Project overview

SayItRight is a pronunciation-practice web app: word -> listen -> record -> sound-by-sound score ->
grounded feedback -> next word, with adaptive practice and progress tracking. Read
[docs/architecture.md](docs/architecture.md) first; [docs/validation.md](docs/validation.md) explains what
the scores do and do not mean.

## 2. Teams, ownership and interfaces

| Team | Owns | Provides | Consumes | Test in isolation with |
|---|---|---|---|---|
| **Frontend / UI** | `frontend/` | screens, recording, charts, accessibility | OpenAPI contract (`docs/openapi.json` -> generated TS types) | `npm run dev:mock`, `npm test` |
| **Backend** | `backend/` | REST API, auth, sessions, persistence, adaptive planner | `PronunciationAnalyzer.analyze`, `FeedbackService.generate` | `pytest backend/tests` (fake analyzer, temp DB) |
| **Speech processing** | `speech_analysis/`, `data/`, `scripts/*calibrat*`, `scripts/evaluate_*` | `AnalysisResult` contract, engines, calibration, word DB | word entries (`data/words.json`) | `pytest speech_analysis`, `pytest -m model`, validation script |
| **AI development** | `ai_feedback/` | `FeedbackResponse`, prompts, guardrails, knowledge base | `AnalysisResult` | `pytest ai_feedback/tests` with recorded analyses |
| **Testing / integration** | `e2e/`, `.github/`, `docker-compose.yml`, Dockerfiles | CI, E2E, releases | everything | `python scripts/dev.py check`, `python scripts/dev.py e2e` |

Ownership is enforced with `.github/CODEOWNERS` (replace the placeholder team handles).

**Interface rule:** teams integrate only through contracts:
`speech_analysis/contracts.py`, `ai_feedback/contracts.py`, `backend/schemas` -> `docs/openapi.json`.
Changing a contract requires a PR labelled `contract-change`, approval from every consuming team,
regenerated artifacts (`python scripts/dev.py contracts`) and a CHANGELOG entry. Additive, optional fields
are non-breaking; renames/removals bump `CONTRACT_VERSION`'s major version.

## 3. Claiming and completing tasks

1. Work is tracked as GitHub Issues on the project board (columns: Backlog -> Ready -> In progress ->
   In review -> Done), grouped into milestones (see [docs/roadmap.md](docs/roadmap.md)). The initial task
   list is in [docs/task_breakdown.md](docs/task_breakdown.md); create the issues with
   `python scripts/create_github_issues.py --create` (requires `gh auth login`).
2. Pick an issue in **Ready** for your team, assign yourself, move it to **In progress**. One owner per issue.
3. Unclear scope? Comment on the issue before coding. Blocked? Add the `blocked` label and link the blocker.
4. Done = merged PR + acceptance criteria checked + docs updated. The PR closes the issue (`Closes #123`).

Labels: `team: frontend|backend|speech|ai|qa-integration`, `type: bug|feature|task|docs`,
`contract-change`, `privacy`, `good first issue`, `blocked`.

## 4. Branches and commits

- `main` is always releasable and protected (PR + green CI + 1 code-owner approval; no force pushes).
- Branch names: `<type>/<issue>-<short-description>`, types `feat`, `fix`, `chore`, `docs`, `test`,
  `refactor`, `exp` (experiments). Examples: `feat/42-phoneme-practice-mode`, `fix/57-safari-recording`.
- Commits: [Conventional Commits](https://www.conventionalcommits.org): `feat(speech): add wav2vec2 calibration`.
- Keep PRs small (< 400 changed lines where possible); rebase on `main` before requesting review.

## 5. Pull requests and code review

- Open a draft PR early; fill in the template (testing, contracts, privacy).
- CI must pass: lint, type checks, unit/API tests, migrations on PostgreSQL, contract drift, word-DB drift,
  Docker builds. Speech changes also trigger the model workflow.
- Reviewers: code owners are requested automatically; contract changes need every consuming team.
- Review for correctness, tests, naming, accessibility (UI), privacy (no recordings or keys), and honest
  claims (no clinical language, no invented scores).
- Squash-merge with a Conventional Commit title.

## 6. Testing individual modules

See the table in [docs/development_guide.md](docs/development_guide.md#tests). Golden rules:
- Unit tests must not need network or models (mark model tests with `@pytest.mark.model`).
- Scoring changes need the fixture tests **and** a validation run on speechocean762 (attach the numbers).
- UI changes need component tests where practical and screenshots in the PR.

## 7. Documenting changes

- User-visible or contract changes: `CHANGELOG.md`.
- Design decisions: a short ADR in `docs/adr/NNNN-title.md` (context, options, decision, consequences).
- API: docstrings on routes/schemas feed OpenAPI automatically; update `docs/api_documentation.md` for
  behaviour changes.
- Validation numbers live only in `docs/validation.md` + `docs/validation_results.json` (no copies elsewhere
  except the README summary).

## 8. Integration procedure

1. **Contract first.** Agree the schema change in an issue; land the contract PR (with defaults so old
   clients keep working).
2. **Parallel build.** Frontend develops against mocks (regenerate fixtures from a backend branch with
   `python -m backend.scripts.generate_frontend_fixtures`); backend develops against the fake analyzer;
   speech/AI develop against recorded fixtures.
3. **Integrate behind configuration.** New engines/providers are selected by environment variables
   (`SA_ENGINE`, `LLM_PROVIDER`), so they can merge before becoming the default.
4. **Verify.** `python scripts/dev.py check`, then the browser E2E (`python scripts/dev.py e2e`) on the
   integrated branch; the QA team signs off the milestone.
5. **Release.** Tag `vX.Y.Z` on `main`, update CHANGELOG, build images.

## 9. Ways of working

- Weekly planning per milestone; short async stand-ups in the team channel.
- Questions about the speech pipeline -> speech team; about prompts or tone -> AI team; about API shape ->
  backend team; about CI or environments -> QA/integration team.
- When in doubt about a user-facing claim, choose the more cautious wording.
