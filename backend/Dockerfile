# syntax=docker/dockerfile:1
# Backend API + speech analysis + AI feedback (one image; build context = repository root).
#
#   docker build -f backend/Dockerfile -t voice-therapy-backend .
#   docker build -f backend/Dockerfile --build-arg INSTALL_ML=true .   # add the optional phoneme model
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg: fallback decoder for non-WAV uploads; espeak-ng: fallback TTS and word-database builds.
ARG APT_PACKAGES="ffmpeg espeak-ng"
RUN if [ -n "$APT_PACKAGES" ]; then \
      apt-get update && apt-get install -y --no-install-recommends $APT_PACKAGES && rm -rf /var/lib/apt/lists/* ; \
    fi

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY speech_analysis ./speech_analysis
COPY ai_feedback ./ai_feedback
COPY data/words.json ./data/words.json
COPY data/reference_audio ./data/reference_audio
COPY scripts ./scripts

# INSTALL_ML=true installs CPU-only PyTorch + Allosaurus (phoneme-level scoring);
# false gives a small image that runs the clearly-labelled acoustic baseline.
# DOWNLOAD_MODELS=true fetches the Allosaurus model and Piper voices from their GitHub releases.
ARG INSTALL_ML=false
ARG DOWNLOAD_MODELS=true
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install -e ".[postgres,llm]" \
 && if [ "$INSTALL_ML" = "true" ]; then \
      pip install torch --index-url "$TORCH_INDEX_URL" && pip install allosaurus ; \
    fi \
 && if [ "$DOWNLOAD_MODELS" = "true" ]; then \
      if [ "$INSTALL_ML" = "true" ]; then python scripts/download_models.py ; \
      else python scripts/download_models.py --skip-allosaurus ; fi ; \
    fi

RUN useradd --create-home --uid 1000 app && mkdir -p /app/data/recordings /app/data/cache && chown -R app /app/data
USER app

ENV APP_ENV=production \
    AUTO_MIGRATE=true \
    WARMUP_ON_START=true
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
