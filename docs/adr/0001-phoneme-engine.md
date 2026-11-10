# ADR 0001: Phoneme engine for pronunciation scoring

- Status: accepted (2026-11-10)
- Deciders: speech team

## Context

Scoring must be phoneme-aware (a recognisable word can still contain a wrong
sound), use free/open-source components, run on CPU, and be replaceable.
Constraints during development: PyPI, npm and GitHub releases were reachable;
the Hugging Face Hub was not.

## Options considered

| Option | Result |
|---|---|
| Speech-to-text word match | Rejected: says nothing about individual sounds. |
| PocketSphinx HMM-GMM (bundled en-US model) | Prototyped. Alignment works, but GOP did not separate correct from wrong productions; free phone choice was wrong even on clean TTS speech. Kept out of the product. |
| **Allosaurus `eng2102` CTC phone recogniser** (GPL-3.0, GitHub release, ~43 MB) | **Chosen.** Frame posteriors over 38 English phones enable substitution-aware CTC GOP. Validated on speechocean762 (phone AUC 0.91, r = 0.47 after calibration). Weakness: 8 kHz features. |
| wav2vec2 `facebook/wav2vec2-lv-60-espeak-cv-ft` (Apache-2.0, 1.2 GB) | Implemented behind the same interface (`SA_ENGINE=wav2vec2`), unit-tested with stubs, **not validated**. Likely better on fricatives (16 kHz). |

## Decision

Use Allosaurus by default; keep the engine behind
`speech_analysis.phoneme_analysis.engines.base.PhonemeEngine`; scoring,
calibration and the API depend only on `EngineOutput`. Without any engine the
pipeline runs a labelled *acoustic baseline* that never reports phoneme scores.

## Consequences

- PyTorch is required for phoneme-level scoring (CPU wheels are enough).
- Allosaurus is GPL-3.0: review licensing before distributing a combined build.
- Switching engines requires re-running calibration and validation
  (`scripts/evaluate_speechocean762.py` + `scripts/fit_calibration.py`); the
  calibration file is keyed by engine id, so an uncalibrated engine falls back
  to `score = 100 x posterior` and says so in results.
