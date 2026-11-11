# Deployment

## Environments

| Setting | development | testing (CI) | production |
|---|---|---|---|
| `APP_ENV` | `development` | `testing` | `production` |
| Database | SQLite file | temp SQLite + PostgreSQL service | PostgreSQL (required) |
| `SECRET_KEY` | dev default | test default | **required**, >= 32 random chars |
| Models | downloaded locally | fake analyzer; model job caches `models/` | baked into the image |
| LLM | optional | stubbed | optional (`LLM_PROVIDER`) |
| Recordings | local folder | temp folder | persistent volume, consent-gated |

`APP_ENV=production` makes the backend refuse to start with SQLite or a weak secret.

## Images

- `backend/Dockerfile` (context: repository root): Python 3.12 + Piper voices (the standard recordings for
  the default signal analysis); `INSTALL_ML=true` adds CPU PyTorch + Allosaurus for the optional phoneme
  model (~1.5 GB). The first start generates every word's standards (a few minutes; cached in the data
  volume). Runs as a non-root
  user, applies Alembic migrations and seeds words at startup (`AUTO_MIGRATE=true`), healthcheck on
  `/api/health`.
- `frontend/Dockerfile`: static build served by nginx; nginx proxies `/api` to `backend:8000` and sets
  security headers (`Permissions-Policy: microphone=(self)`).

```bash
docker compose up --build             # local stack on :8080 (frontend) and :8000 (API)
APP_ENV=production SECRET_KEY=... docker compose up -d --build
```

## Production checklist

- [ ] HTTPS everywhere (browsers only allow microphone access on secure origins). Terminate TLS at a load
      balancer or reverse proxy in front of the frontend container.
- [ ] `SECRET_KEY` from a secret manager; `ANTHROPIC_API_KEY` likewise (never in images or git).
- [ ] Managed PostgreSQL with backups; `DATABASE_URL=postgresql+psycopg://...`.
- [ ] Persistent volume for `/app/data/recordings` (only consented recordings) with a retention policy.
- [ ] `CORS_ORIGINS` set to the real frontend origin.
- [ ] CPU sizing: one analysis takes ~0.2-0.8 s of CPU after warm-up; `MAX_CONCURRENT_ANALYSES` per
      process (default 2). Scale horizontally with more backend replicas; models load per process (~1 GB RAM).
- [ ] Run `alembic upgrade head` as a release step if you disable `AUTO_MIGRATE` for multi-replica deploys.
- [ ] Logs and metrics: uvicorn access logs, analysis `processing_ms` in results; add OpenTelemetry if needed.
- [ ] Legal: licence review (Allosaurus GPL-3.0, voice CC BY attributions, see THIRD_PARTY.md), privacy
      notice, data processing agreement with the LLM provider if feedback is AI-generated.
- [ ] Do not present scores as clinical results (the UI and API carry disclaimers; keep them).

## Shared development environment

Point several developers at one PostgreSQL by setting `DATABASE_URL` in each `.env`; run migrations from
one place (`python -m backend.database.init_db`). Each developer can still run the backend locally with
their own models.
