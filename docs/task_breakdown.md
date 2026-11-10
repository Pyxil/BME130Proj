# Initial task breakdown

Generated from `docs/tasks.json` by `scripts/create_github_issues.py --write-markdown`.
Create the GitHub issues with `python scripts/create_github_issues.py --create --apply`.

## M1 Hardening & onboarding

Make the working MVP robust across browsers and ready for real users.

| ID | Team | Task | Size | Depends on |
|---|---|---|---|---|
| QA-1 | qa-integration | Set up branch protection, CODEOWNERS teams and the project board | S | - |
| QA-2 | qa-integration | Run the browser E2E test in CI | M | - |
| QA-3 | qa-integration | Cross-browser recording test matrix | M | - |
| FE-1 | frontend | Microphone check before the first word | M | - |
| FE-2 | frontend | Accessibility audit and fixes | M | - |
| FE-3 | frontend | Phoneme timeline on results | S | - |
| BE-1 | backend | Rate limiting and request quotas | M | - |
| BE-2 | backend | Password reset and refresh tokens | M | - |
| BE-3 | backend | Custom word management | M | - |
| SP-2 | speech | Human reference recordings | M | - |
| AI-2 | ai | Child-friendly feedback tone | S | - |

## M2 Evidence & quality

Stronger validation, better models, evaluated AI feedback.

| ID | Team | Task | Size | Depends on |
|---|---|---|---|---|
| SP-1 | speech | Validate and calibrate the wav2vec2 engine | M | - |
| SP-3 | speech | Model-based syllable detection | M | - |
| SP-4 | speech | Consented isolated-word dataset rated by SLPs | L | QA-4 |
| SP-5 | speech | Learned scorer on GOP features | L | SP-1 |
| AI-1 | ai | Evaluation set for AI feedback | L | - |
| AI-3 | ai | SLP review of the articulation knowledge base | M | - |
| QA-4 | qa-integration | Privacy review and data retention | L | - |

## M3 Practitioner features

Therapist/caregiver workflows, richer exercises.

| ID | Team | Task | Size | Depends on |
|---|---|---|---|---|
| BE-4 | backend | Practitioner and caregiver roles | L | QA-4 |
| FE-4 | frontend | Practitioner dashboard | L | BE-4 |
| FE-5 | frontend | Minimal-pair exercises | M | - |
| SP-6 | speech | Short phrase practice | L | SP-1 |
