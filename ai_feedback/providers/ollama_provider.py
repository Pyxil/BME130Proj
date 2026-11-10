"""Local open-source LLM via Ollama's native REST API (no cloud, free).

Configuration: ``OLLAMA_HOST`` (default http://localhost:11434) and
``OLLAMA_MODEL`` (default ``llama3.1:8b``).  Uses Ollama's ``format`` field
with a JSON schema (structured outputs, Ollama >= 0.5).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import ProviderError


class OllamaProvider:
    name = "ollama"

    def __init__(self) -> None:
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
        self.timeout = float(os.environ.get("LLM_TIMEOUT_S", "60"))

    def generate(self, system: str, user: str, schema: dict) -> str:
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - configured local URL
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        text = (data.get("message") or {}).get("content")
        if not text:
            raise ProviderError("empty Ollama response")
        return text
