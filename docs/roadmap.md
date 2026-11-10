# Roadmap and parallel development plan

## Where we are (v0.1.0)

The core workflow works end to end and is tested: word -> hear -> record -> analyse (phoneme GOP,
validated on speechocean762) -> score -> grounded feedback -> next word, plus adaptive sessions,
dashboard, history, privacy controls, CI and Docker. See the status table in the README.

## How the original build was parallelised

The architecture was designed so these streams only meet at contracts:

```mermaid
flowchart TB
  C0[Contracts: AnalysisResult, FeedbackResponse, OpenAPI] --> FE[Frontend screens on mocks]
  C0 --> BE[Backend API on fake analyzer]
  C0 --> AI[AI feedback on recorded analyses]
  WDB[Word database] --> SP[Speech pipeline]
  ENG[Engine selection + validation] --> SP
  SP --> CAL[Calibration]
  FE --> INT[Integration + E2E]
  BE --> INT
  AI --> INT
  CAL --> INT
  INT --> REL[Release]
```

| Can start immediately (parallel) | Depends on |
|---|---|
| Frontend UI with mock API | contract only |
| Backend auth, sessions, persistence | contract only (fake analyzer) |
| AI prompts, guardrails, knowledge base | contract + a few recorded analyses |
| Word database | nothing |
| Speech engine evaluation | dataset access |
| Calibration | engine choice |
| Integration / E2E | all of the above |

## Next milestones

```mermaid
gantt
  dateFormat  YYYY-MM-DD
  title Next milestones (indicative)
  section M1 Hardening
  CI E2E, branch protection (QA-1/2)   :m1a, 2026-11-16, 10d
  Mic check, a11y audit (FE-1/2)        :m1b, 2026-11-16, 14d
  Rate limits, auth flows (BE-1/2)      :m1c, 2026-11-16, 14d
  Human reference audio (SP-2)          :m1d, 2026-11-16, 21d
  Child-friendly tone (AI-2)            :m1e, 2026-11-16, 5d
  section M2 Evidence
  wav2vec2 validation (SP-1)            :m2a, 2026-12-07, 10d
  Feedback eval set (AI-1)              :m2b, 2026-12-07, 14d
  Privacy review (QA-4)                 :m2c, 2026-12-07, 21d
  SLP-rated dataset (SP-4)              :m2d, after m2c, 30d
  Learned scorer (SP-5)                 :m2e, after m2a, 21d
  section M3 Practitioners
  Roles and sharing (BE-4)              :m3a, after m2c, 21d
  Practitioner dashboard (FE-4)         :m3b, after m3a, 21d
  Minimal pairs (FE-5)                  :m3c, 2027-01-11, 10d
```

Full task list with owners, sizes and dependencies: [task_breakdown.md](task_breakdown.md).
