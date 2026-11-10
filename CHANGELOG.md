# Changelog

All notable changes are documented here (format: [Keep a Changelog](https://keepachangelog.com)).
Contract changes (OpenAPI, `AnalysisResult`, `FeedbackResponse`) must be listed under **Contract**.

## [0.1.0] - 2026-11-10

### Added
- Practice workflow: word display, reference audio, recording with waveform and auto-stop,
  analysis, score, grounded feedback, retry / next word, session summary.
- Speech analysis library: quality gate, features, Allosaurus CTC GOP with accent variants,
  DTW similarity, syllable and timing measures, calibrated scoring, confidence and status.
- Word database of 135 words (43 easy, 53 medium, 39 hard) with IPA, ARPAbet and US/UK variants.
- AI feedback: Claude / Ollama providers, rule-based fallback, grounding guardrails.
- Backend: JWT auth, adaptive sessions, attempts, progress, consent-gated recordings, data export/deletion.
- Frontend: practice setup, exercise, dashboard (charts), history, settings, mock mode.
- Validation on speechocean762; CI workflows; Docker Compose; team documentation.

### Contract
- `CONTRACT_VERSION` 1.0.0.
