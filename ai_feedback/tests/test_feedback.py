"""AI feedback: rule-based engine, grounding guardrails and provider integration (no network)."""

import json
import sys
import types

import pytest

from ai_feedback import FeedbackRequest, FeedbackService, PreviousAttempt
from ai_feedback.contracts import FeedbackResponse, Recommendation
from ai_feedback.recommendation_engine.guardrails import validate

ANALYSIS = {
    "word": "rabbit", "status": "assessed", "overall_score": 72, "rating": "satisfactory", "confidence_label": "high",
    "matched_variant": {"id": "us", "accent": "General American", "ipa": "/ˈræbət/", "arpabet": []},
    "phoneme_scores": [
        {"phoneme": "r", "score": 55, "status": "poor", "likely_realization": "w"},
        {"phoneme": "æ", "score": 96, "status": "good", "likely_realization": None},
        {"phoneme": "b", "score": 98, "status": "good", "likely_realization": None},
        {"phoneme": "ə", "score": 95, "status": "good", "likely_realization": None},
        {"phoneme": "t", "score": 97, "status": "good", "likely_realization": None},
    ],
    "identified_issues": [{"id": "ph0-substitution", "type": "substitution", "severity": "moderate", "phoneme": "r",
                           "realized_as": "w", "position": 0,
                           "message": "The /r/ sound at the start of the word may have sounded more like /w/."}],
    "strengths": [{"id": "ph2-good", "message": "The /b/ in the second syllable was clear.", "phoneme": "b"}],
}


def req(**kw):
    return FeedbackRequest(analysis=json.loads(json.dumps(ANALYSIS)), **kw)


def test_rule_based_uses_articulation_contrast():
    out = FeedbackService(provider=None).generate(req())
    assert out.source == "rule_based"
    assert out.recommendations[0].issue_id == "ph0-substitution"
    assert "lips" in out.recommendations[0].articulation  # r>w contrast note


def test_progress_note_uses_measured_scores():
    out = FeedbackService(provider=None).generate(req(previous_attempts=[PreviousAttempt(overall_score=60)]))
    assert "improved by 12 points" in out.progress_note


def _llm_out(**kw):
    base = dict(summary="Nice try.", encouragement="Keep going!", progress_note="", source="llm:test:x",
                recommendations=[Recommendation(issue_id="ph0-substitution", tip="Work on /r/ (as in 'red').",
                                                articulation="Relax your lips.")])
    base.update(kw)
    return FeedbackResponse(**base)


def test_guardrail_drops_invented_issue():
    out, notes = validate(req(), _llm_out(recommendations=[
        Recommendation(issue_id="ph9-made-up", tip="Your /s/ is lisped.", articulation="")]))
    assert out.recommendations == [] and notes


def test_guardrail_drops_unmeasured_sound():
    out, _ = validate(req(), _llm_out(recommendations=[
        Recommendation(issue_id="ph0-substitution", tip="Also fix the /θ/ sound.", articulation="")]))
    assert out.recommendations == []


def test_guardrail_blocks_diagnostic_language():
    out, _ = validate(req(), _llm_out(summary="This may indicate a speech disorder."))
    assert out.summary == ""


def test_guardrail_rejects_false_improvement_claim():
    r = req(previous_attempts=[PreviousAttempt(overall_score=90)])
    out, _ = validate(r, _llm_out(progress_note="You improved a lot!"))
    assert out.progress_note == ""


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, payload):
        self.payload = payload

    def generate(self, system, user, schema):
        assert "identified_issues" in user and schema["required"]
        return self.payload


def test_service_accepts_grounded_llm_output():
    payload = json.dumps({"summary": "Good effort on 'rabbit'.", "encouragement": "Try again!", "progress_note": "",
                          "recommendations": [{"issue_id": "ph0-substitution", "tip": "Focus on /r/ (as in 'red').",
                                               "articulation": "Keep your lips relaxed."}]})
    out = FeedbackService(provider=FakeProvider(payload)).generate(req())
    assert out.source == "llm:fake:fake-1" and out.recommendations and out.grounded


def test_service_falls_back_when_llm_output_is_invalid():
    out = FeedbackService(provider=FakeProvider("not json")).generate(req())
    assert out.source == "rule_based" and out.recommendations


def test_service_falls_back_when_all_tips_are_ungrounded():
    payload = json.dumps({"summary": "Ok.", "encouragement": "", "progress_note": "",
                          "recommendations": [{"issue_id": "invented", "tip": "x", "articulation": ""}]})
    out = FeedbackService(provider=FakeProvider(payload)).generate(req())
    assert out.source.endswith("rule_based") and out.recommendations[0].issue_id == "ph0-substitution"


def test_anthropic_provider_request_shape(monkeypatch):
    """Checks our use of the SDK (model, structured output, refusal fallbacks) without network."""
    calls = {}

    class Block:
        type = "text"
        text = json.dumps({"summary": "s", "recommendations": [], "encouragement": "e", "progress_note": ""})

    class Resp:
        stop_reason, stop_details, content, model = "end_turn", None, [Block()], "claude-opus-5-5"

    class Messages:
        def create(self, **kw):
            calls.update(kw)
            return Resp()

    class Client:
        def __init__(self, **kw):
            self.beta = types.SimpleNamespace(messages=Messages())

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Client
    for name in ["AuthenticationError", "PermissionDeniedError", "NotFoundError", "RateLimitError",
                 "BadRequestError", "APIStatusError", "APIConnectionError"]:
        setattr(fake, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    from ai_feedback.providers.anthropic_provider import AnthropicProvider

    text = AnthropicProvider().generate("sys", "user", {"type": "object"})
    assert json.loads(text)["summary"] == "s"
    assert calls["model"] == "claude-opus-5-5"
    assert calls["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in calls["betas"]
    assert calls["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in calls and "temperature" not in calls


def test_refusal_falls_back_to_rules():
    class RefusingProvider:
        name, model = "x", "y"

        def generate(self, *a):
            from ai_feedback.providers import ProviderError

            raise ProviderError("model declined the request")

    out = FeedbackService(provider=RefusingProvider()).generate(req())
    assert out.source == "rule_based"


@pytest.mark.parametrize("status", ["retry_required", "inconclusive"])
def test_no_llm_call_for_unscored_attempts(status):
    a = dict(ANALYSIS, status=status, retry_reason="Please record again.")
    out = FeedbackService(provider=FakeProvider("{}")).generate(FeedbackRequest(analysis=a))
    assert out.source == "rule_based" and not out.recommendations
