# Convenience wrapper around scripts/dev.py (Windows users: call `python scripts/dev.py <target>` directly).
PY ?= python3

.PHONY: help setup setup-lite backend frontend mock test test-models lint check migrate contracts e2e up down

help:
	@$(PY) scripts/dev.py help

setup:        ; $(PY) scripts/dev.py setup
setup-lite:   ; $(PY) scripts/dev.py setup --no-ml
backend:      ; $(PY) scripts/dev.py backend
frontend:     ; $(PY) scripts/dev.py frontend
mock:         ; $(PY) scripts/dev.py mock
test:         ; $(PY) scripts/dev.py test
test-models:  ; $(PY) scripts/dev.py test --models
lint:         ; $(PY) scripts/dev.py lint
check:        ; $(PY) scripts/dev.py check
migrate:      ; $(PY) scripts/dev.py migrate
contracts:    ; $(PY) scripts/dev.py contracts
e2e:          ; $(PY) scripts/dev.py e2e
up:           ; docker compose up --build
down:         ; docker compose down
