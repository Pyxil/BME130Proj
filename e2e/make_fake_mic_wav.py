#!/usr/bin/env python3
"""Create a WAV for Chromium's fake microphone (--use-file-for-fake-audio-capture).

    python e2e/make_fake_mic_wav.py rabbit out.wav                # correct pronunciation
    python e2e/make_fake_mic_wav.py rabbit out.wav --swap R:W     # controlled error ("wabbit")

The file contains 1.0 s of room noise, the synthesised word (Piper TTS) and
2.5 s of trailing noise so the recorder's silence auto-stop triggers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_analysis.audio_processing.io import resample  # noqa: E402
from speech_analysis.pipeline import load_words  # noqa: E402
from speech_analysis.tts.piper import PiperVoice, arpabet_to_espeak_ipa  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("word")
    ap.add_argument("out", type=Path)
    ap.add_argument("--swap", help="replace the first phone A with B, e.g. R:W")
    ap.add_argument("--voice", default="en_US-libritts_r-medium")
    ap.add_argument("--speaker", type=int, default=12)
    args = ap.parse_args()
    entry = next(w for w in load_words() if w["word"].lower() == args.word.lower())
    arpa = list(entry["arpabet"])
    if args.swap:
        a, b = args.swap.split(":")
        i = next(i for i, p in enumerate(arpa) if p.rstrip("012") == a)
        arpa[i] = b + arpa[i][len(a):]
    voice = PiperVoice.from_dir(ROOT / "models" / "piper" / args.voice)
    y = voice.synthesize_ipa(arpabet_to_espeak_ipa(arpa), speaker_id=args.speaker, noise_scale=0.333, noise_w=0.333)
    y = resample(y, voice.sample_rate, 48000) * 0.45
    rng = np.random.default_rng(0)
    noise = lambda s: rng.normal(0, 4e-4, int(48000 * s)).astype(np.float32)  # noqa: E731
    out = np.concatenate([noise(1.0), y + rng.normal(0, 4e-4, len(y)).astype(np.float32), noise(2.5)])
    sf.write(args.out, out, 48000, subtype="PCM_16")
    print(f"{args.out}: '{entry['word']}' as {' '.join(arpa)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
