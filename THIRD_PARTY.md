# Third-party components and data

| Component | Use | Licence | Notes |
|---|---|---|---|
| [Allosaurus](https://github.com/xinjli/allosaurus) + `eng2102` model | Phone recognition (default engine) | GPL-3.0 | Optional dependency (`.[ml]`); review GPL obligations before distributing builds |
| [Piper](https://github.com/rhasspy/piper) voices via [sherpa-onnx releases](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models) | Reference pronunciation audio | Voice-specific | Defaults: `en_US-libritts_r-medium` (LibriTTS-R, CC BY 4.0), `en_GB-vctk-medium` (VCTK, CC BY 4.0). Attribution required |
| ONNX Runtime | Runs Piper voices | MIT | |
| [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) | US pronunciations in `data/words.json` | BSD-2-Clause | Build time only |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) | British variants (build time), fallback TTS | GPL-3.0 | Called as an external program |
| [speechocean762](https://github.com/jimbozhang/speechocean762) | Validation and calibration | CC BY 4.0 | Not redistributed; calibration curves and metrics derived from it |
| wav2vec2 `facebook/wav2vec2-lv-60-espeak-cv-ft` | Experimental engine | Apache-2.0 | Not downloaded by default |
| librosa, NumPy, SciPy, soundfile | Signal processing | ISC / BSD | |
| FastAPI, SQLAlchemy, Alembic, Pydantic, PyJWT | Backend | MIT / BSD | |
| React, React Router, Recharts, Tailwind CSS, Vite | Frontend | MIT | |
| Atkinson Hyperlegible, Noto Sans (Google Fonts) | UI fonts | OFL | Loaded from Google Fonts |
| Anthropic Python SDK | Optional Claude feedback | MIT | API usage governed by Anthropic's terms |

Test fixtures in `speech_analysis/tests/fixtures/` are synthetic recordings
generated with the two CC BY 4.0 Piper voices above.
