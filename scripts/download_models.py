#!/usr/bin/env python3
"""Download the models used by the analysis pipeline into ./models.

    python scripts/download_models.py            # Allosaurus English model + default Piper voices
    python scripts/download_models.py --wav2vec2 # also the experimental wav2vec2 phoneme model (~1.3 GB)

Sources (official releases):
* Allosaurus ``eng2102`` - https://github.com/xinjli/allosaurus/releases (GPL-3.0)
* Piper voices (ONNX) - https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models
  - en_US-libritts_r-medium (LibriTTS-R, CC BY 4.0)
  - en_GB-vctk-medium (VCTK, CC BY 4.0)
* wav2vec2 ``facebook/wav2vec2-lv-60-espeak-cv-ft`` - Hugging Face Hub (Apache-2.0)
"""

from __future__ import annotations

import argparse
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
ALLOSAURUS = "https://github.com/xinjli/allosaurus/releases/download/v1.0/{name}.tar.gz"
PIPER = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-{voice}.tar.bz2"
DEFAULT_VOICES = ["en_US-libritts_r-medium", "en_GB-vctk-medium"]


def _open(url: str):
    try:
        return urllib.request.urlopen(url, timeout=120)  # noqa: S310 - fixed https URLs
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
        # python.org builds of Python on macOS ship without a CA bundle until
        # "Install Certificates.command" is run; certifi (installed with httpx) fixes it.
        try:
            import certifi
        except ImportError:
            sys.exit("HTTPS certificate check failed. On macOS run 'Install Certificates.command' from "
                     "/Applications/Python 3.x/ or `pip install certifi`, then retry.")
        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(url, timeout=120, context=ctx)  # noqa: S310


def _download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    with _open(url) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh, length=1 << 20)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)) or member.issym() or member.islnk():
            raise RuntimeError(f"unsafe path in archive: {member.name}")
    tar.extractall(dest)  # noqa: S202 - members validated above


def allosaurus(name: str = "eng2102") -> None:
    out = MODELS / "allosaurus" / name
    if (out / "model.pt").exists():
        print(f"allosaurus/{name}: already present")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f"{name}.tar.gz"
        _download(ALLOSAURUS.format(name=name), archive)
        with tarfile.open(archive) as tar:
            _safe_extract(tar, out.parent)
    print(f"allosaurus/{name}: ok")


def piper(voice: str) -> None:
    out = MODELS / "piper" / voice
    if list(out.glob("*.onnx")):
        print(f"piper/{voice}: already present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "voice.tar.bz2"
        _download(PIPER.format(voice=voice), archive)
        with tarfile.open(archive) as tar:
            _safe_extract(tar, Path(tmp))
        src = Path(tmp) / f"vits-piper-{voice}"
        out.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.suffix in {".onnx", ".json", ".txt"} or f.name == "MODEL_CARD":
                shutil.copy2(f, out / f.name)
    print(f"piper/{voice}: ok")


def wav2vec2(model_id: str) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("pip install -e .[wav2vec2] first")
    path = snapshot_download(model_id, allow_patterns=["*.json", "*.bin", "*.safetensors", "*.txt"])
    print(f"wav2vec2 {model_id}: cached at {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allosaurus-model", default="eng2102")
    ap.add_argument("--voices", nargs="*", default=DEFAULT_VOICES)
    ap.add_argument("--skip-allosaurus", action="store_true")
    ap.add_argument("--wav2vec2", action="store_true")
    ap.add_argument("--wav2vec2-model", default="facebook/wav2vec2-lv-60-espeak-cv-ft")
    args = ap.parse_args()
    if not args.skip_allosaurus:
        allosaurus(args.allosaurus_model)
    for v in args.voices:
        piper(v)
    if args.wav2vec2:
        wav2vec2(args.wav2vec2_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
