# Changelog

All notable changes are documented here (format: [Keep a Changelog](https://keepachangelog.com)).
Contract changes (OpenAPI, `AnalysisResult`, `FeedbackResponse`) must be listed under **Contract**.

## [0.2.0] - 2026-11-11

### Added
- Signals-and-systems scoring engine, now the default (`speech_analysis/signal_analysis`): high-pass and
  pre-emphasis filters, windowed FFT, short-time energy, zero-crossing rate, spectral centroid, band
  energies, MFCCs with cepstral mean/variance normalisation, pitch by autocorrelation; dynamic time warping
  against standard recordings with vocal tract length normalisation; similarity per syllable (or start /
  vowel / end); minimal-pair standards for common mistakes ("wabbit"); word identification by template
  matching against every practice word. No speech-recognition model is used.
- Results screen: part-by-part chips, a loudness chart of the recording against the standard, the common
  mistakes checked, and the closest words.
- `scripts/calibrate_signal.py`: calibrates the signal scorer and validates it on generated voices that are
  not used as standards (results in docs/validation.md).

### Changed
- The neural phoneme model (Allosaurus) is optional, for comparison: `dev.py setup --ml` and
  `SA_ENGINE=allosaurus`. Setup and the Docker image no longer install PyTorch by default, and
  `dev.py setup` switches an untouched `SA_ENGINE=auto` in `.env` to the new default `signal`.

### Contract
- `CONTRACT_VERSION` 1.1.0 (additive): `AnalysisResult.signal_analysis`; component names
  `spectral_similarity`, `minimal_pair_contrast`, `loudness_contour`, `pitch_contour`; issue types
  `part_mismatch`, `stress_pattern`, `pitch_pattern`.

## [0.1.3] - 2026-11-11

### Fixed
- Windows: setup failed with "Failed building wheel for editdistance" when `.venv` had been made with
  Python 3.13 or newer (e.g. by an earlier run with a newer `python`, or by VS Code); that package has no
  Windows builds for those versions. `dev.py setup` now replaces a `.venv` made with a different Python
  (or left incomplete), and on Windows asks for Python 3.11 or 3.12 before installing the speech model.

## [0.1.2] - 2026-11-11

### Added
- Windows setup instructions; `dev.py setup` gives Windows-specific hints and checks the Node.js version.
- `scripts/smoke_test.py` (`dev.py smoke`): starts the real backend and Vite dev server and checks sign-up,
  reference audio, scoring of a correct and a mispronounced recording, and the dev-server proxy.
- CI workflow running the documented setup, all tests (with the speech models) and the smoke test on
  Windows, macOS and Linux.

### Fixed
- Text files and espeak-ng output are always read as UTF-8 (Windows defaults to a legacy code page).
- The Vite dev server listens on localhost only (no firewall prompt, not exposed to the network) and proxies
  to `127.0.0.1:8000` instead of `localhost`, which can resolve to IPv6 first.

## [0.1.1] - 2026-11-11

### Fixed
- Backend crashed at startup when `CORS_ORIGINS` was comma-separated (as in `.env.example` and
  docker-compose); an empty `SECRET_KEY=` produced an empty signing key.
- The repository-root `.env` is now loaded for every component (API key, `LLM_*`, `SA_*`, `VITE_*`).
- Safari: the recorder's AudioContext is created inside the click; reference audio is prefetched so
  playback starts within the user gesture.
- `docs/openapi.json` is now generated identically on Python 3.12 and 3.13 (3.13 renamed the 413/422
  status phrases), so the CI contract check passes.

### Added
- macOS setup instructions; `dev.py setup` checks the Python/Node versions with Mac-specific hints and
  writes a random `SECRET_KEY` into the new `.env`; model downloads fall back to certifi.

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
