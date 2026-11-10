"""Feedback orchestration: payload -> LLM -> validate -> (fallback to rules)."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from ..contracts import LLM_OUTPUT_SCHEMA, FeedbackRequest, FeedbackResponse, Recommendation
from ..prompts import SYSTEM_PROMPT, user_message
from ..providers import LLMProvider, ProviderError, create_provider
from .guardrails import validate
from .rules import progress_note, rule_based_feedback

log = logging.getLogger(__name__)
_UNSET = object()


class FeedbackService:
    def __init__(self, provider: LLMProvider | None | object = _UNSET):
        self._provider = provider

    @property
    def provider(self) -> LLMProvider | None:
        if self._provider is _UNSET:
            try:
                self._provider = create_provider()
            except Exception as exc:  # noqa: BLE001 - misconfiguration falls back to rules
                log.warning("LLM provider unavailable: %s", exc)
                self._provider = None
        return self._provider  # type: ignore[return-value]

    def describe(self) -> dict:
        p = self.provider
        return {"mode": "llm" if p else "rule_based", "provider": getattr(p, "name", None),
                "model": getattr(p, "model", None)}

    def generate(self, req: FeedbackRequest) -> FeedbackResponse:
        if req.analysis.get("status") != "assessed":
            return rule_based_feedback(req)
        provider = self.provider
        if provider is None:
            return rule_based_feedback(req)
        try:
            raw = provider.generate(SYSTEM_PROMPT, user_message(req), LLM_OUTPUT_SCHEMA)
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            parsed = FeedbackResponse(
                summary=str(data.get("summary", "")),
                recommendations=[Recommendation(**r) for r in data.get("recommendations", [])],
                encouragement=str(data.get("encouragement", "")),
                progress_note=str(data.get("progress_note", "")),
                source=f"llm:{provider.name}:{provider.model}",
            )
        except (ProviderError, ValidationError, ValueError, TypeError) as exc:
            log.warning("LLM feedback failed, using rules: %s", exc)
            return rule_based_feedback(req, reason=f"LLM unavailable: {exc}")

        out, notes = validate(req, parsed)
        out.guardrail_notes = notes
        issues = req.analysis.get("identified_issues") or []
        if issues and not out.recommendations:
            fb = rule_based_feedback(req, reason="LLM output failed grounding checks; used rule-based tips")
            fb.summary = out.summary or fb.summary
            fb.guardrail_notes = notes + fb.guardrail_notes
            fb.source = f"{out.source}+rule_based"
            return fb
        if not out.summary:
            out.summary = rule_based_feedback(req).summary
        if not out.progress_note:
            out.progress_note = progress_note(req)
        return out
