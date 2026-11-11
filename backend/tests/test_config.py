"""Settings parsing as produced by .env.example and docker-compose."""

from __future__ import annotations

import os

import pytest

from backend.core.config import _DEV_SECRET, Settings, load_env_file


def test_comma_separated_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080, http://localhost:5173")
    assert Settings().cors_origins == ["http://localhost:8080", "http://localhost:5173"]


def test_json_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.example"]')
    assert Settings().cors_origins == ["http://a.example"]


def test_empty_secret_key_falls_back_to_dev_default(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "")
    assert Settings().secret_key == _DEV_SECRET


def test_production_rejects_dev_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError):
        Settings().check_production()


def test_env_file_values_reach_other_packages(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER_PROBE=anthropic\nSA_ENGINE_PROBE=allosaurus\nALREADY_SET_PROBE=from-file\n")
    monkeypatch.setenv("ALREADY_SET_PROBE", "from-shell")
    monkeypatch.delenv("LLM_PROVIDER_PROBE", raising=False)
    monkeypatch.delenv("SA_ENGINE_PROBE", raising=False)
    assert load_env_file(env) is True
    assert os.environ["LLM_PROVIDER_PROBE"] == "anthropic"
    assert os.environ["SA_ENGINE_PROBE"] == "allosaurus"
    assert os.environ["ALREADY_SET_PROBE"] == "from-shell"  # the shell environment wins
    for k in ("LLM_PROVIDER_PROBE", "SA_ENGINE_PROBE"):
        monkeypatch.delenv(k, raising=False)


def test_env_example_parses_cleanly(monkeypatch):
    """Every variable in .env.example must be accepted (this is what `dev.py setup` copies to .env)."""
    from dotenv import dotenv_values

    from backend.core.config import REPO_ROOT

    for key, value in dotenv_values(REPO_ROOT / ".env.example").items():
        monkeypatch.setenv(key, value or "")
    s = Settings()
    assert s.cors_origins and s.secret_key == _DEV_SECRET
