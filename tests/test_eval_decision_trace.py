import json
from pathlib import Path

import httpx
import pytest

from rj_studio_ai import application
from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.evaluation.decision_trace import (
    DecisionTrace,
    DecisionTraceCapture,
    capture_finalizer,
)
from rj_studio_ai.evaluation.live import execute_live
from rj_studio_ai.evaluation.records import check_privacy
from rj_studio_ai.evaluation.runner import synthetic_facts
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


def multi_fact_context():
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-multiple-facts"
    )
    return ConversationContext((), synthetic_facts(case))


def multi_fact_decision(**overrides):
    return fixture_decision(
        **{
            "intents": ["price", "hours"],
            "knowledge_refs": ["price-corte", "hours-corte"],
            "reply_parts": [
                {"kind": "fact", "knowledge_ref": "price-corte"},
                {"kind": "fact", "knowledge_ref": "hours-corte"},
            ],
            **overrides,
        }
    )


def trace_at_finalizer(decision, context):
    capture = DecisionTraceCapture()
    capture.propose(decision.model_dump(mode="json"), context)
    with capture_finalizer(capture):
        finalized = application.finalize_reply(
            decision, customer_message="Preço e horário?", context=context
        )
    return capture.finish(finalized.reply_text, safe_fallback=False), finalized


def test_trace_identifies_model_requested_handoff_without_exporting_raw_reason():
    decision = multi_fact_decision(handoff=True, handoff_reason="Untrusted free-form explanation")
    trace, finalized = trace_at_finalizer(decision, multi_fact_context())
    assert finalized.handoff is True
    assert trace.proposed_handoff is True
    assert trace.normalized_handoff_reason == "model_requested_handoff"
    assert trace.finalizer_handoff is True
    assert trace.override_code == "model_requested_handoff"
    assert trace.final_rendered_fact_ids == ()
    assert "Untrusted free-form explanation" not in trace.model_dump_json()


@pytest.mark.parametrize(
    ("decision_overrides", "missing_policy", "expected_code"),
    [
        (
            {"reply_parts": [{"kind": "fact", "knowledge_ref": "price-corte"}]},
            False,
            "missing_critical_fact",
        ),
        (
            {
                "knowledge_refs": ["invented-ref"],
                "reply_parts": [{"kind": "fact", "knowledge_ref": "invented-ref"}],
            },
            False,
            "unavailable_knowledge",
        ),
        ({}, True, "unavailable_mandatory_policy"),
    ],
)
def test_trace_distinguishes_finalizer_missing_fact_invalid_ref_and_policy(
    decision_overrides, missing_policy, expected_code
):
    context = multi_fact_context()
    if missing_policy:
        service = type(context.knowledge[0]).model_validate(
            {
                **context.knowledge[0].model_dump(),
                "id": "service-corte",
                "category": "service",
                "statement": "Serviço sintético de corte.",
                "mandatory_policy_ids": ["missing-policy"],
            }
        )
        context = ConversationContext((), (*context.knowledge, service))
    trace, finalized = trace_at_finalizer(multi_fact_decision(**decision_overrides), context)
    assert trace.proposed_handoff is False
    assert finalized.handoff is True
    assert trace.finalizer_handoff is True
    assert trace.finalizer_reason_code == expected_code
    assert trace.override_code == expected_code
    assert trace.final_rendered_fact_ids == ()
    assert trace.whether_safe_fallback_was_used is True


def test_trace_lists_only_facts_actually_rendered_and_restores_finalizer():
    original = application.finalize_reply
    baseline = original(
        multi_fact_decision(), customer_message="Preço e horário?", context=multi_fact_context()
    )
    trace, finalized = trace_at_finalizer(multi_fact_decision(), multi_fact_context())
    assert finalized == baseline
    assert finalized.handoff is False
    assert trace.selected_fact_ids == ("price-corte", "hours-corte")
    assert trace.proposed_intents == ("price", "hours")
    assert trace.reply_part_kinds == ("fact", "fact")
    assert trace.reply_part_fact_refs == ("price-corte", "hours-corte")
    assert trace.final_rendered_fact_ids == ("price-corte", "hours-corte")
    assert trace.whether_safe_fallback_was_used is False
    assert application.finalize_reply is original


def test_trace_sanitizes_untrusted_ids_reasons_and_drops_prose_and_reasoning():
    capture = DecisionTraceCapture()
    capture.propose(
        {
            "intents": ["price", "hours", {"invalid": "value"}],
            "knowledge_refs": ["price-corte", "sk-synthetic-forbidden"],
            "reply_parts": [
                {"kind": "fact", "knowledge_ref": "sk-synthetic-forbidden"},
                {"kind": ["invalid-kind"]},
            ],
            "handoff": True,
            "handoff_reason": "Authorization: Bearer sk-synthetic-forbidden",
            "reply_text": "Untrusted prose must not be exported",
            "reasoning": "Hidden reasoning must not be exported",
            "critical_claims": [{"value": "untrusted claim text"}],
        },
        multi_fact_context(),
    )
    trace = capture.finish(None, safe_fallback=True)
    assert trace.proposed_knowledge_refs == ("price-corte", "unavailable-reference")
    assert trace.reply_part_fact_refs == ("unavailable-reference",)
    assert trace.normalized_handoff_reason == "model_requested_handoff"
    check_privacy(trace.model_dump(mode="json"))
    encoded = trace.model_dump_json()
    for forbidden in (
        "sk-synthetic",
        "Authorization",
        "Untrusted prose",
        "Hidden reasoning",
        "untrusted claim text",
    ):
        assert forbidden not in encoded
    with pytest.raises(ValueError):
        DecisionTrace.model_validate({**trace.model_dump(), "provider_payload": {}})


def test_trusted_policy_wins_even_when_model_proposes_same_handoff_reason():
    context = multi_fact_context()
    service = type(context.knowledge[0]).model_validate(
        {
            **context.knowledge[0].model_dump(),
            "id": "service-risk",
            "category": "service",
            "requires_human_consultation": True,
        }
    )
    context = ConversationContext((), (*context.knowledge, service))
    trace, _ = trace_at_finalizer(
        multi_fact_decision(handoff=True, handoff_reason="requires_human_consultation"), context
    )
    assert trace.proposed_handoff is True
    assert trace.override_code == "requires_human_consultation"
    assert trace.whether_safe_fallback_was_used is True


def test_observer_restores_runtime_seam_after_failure():
    original = application.finalize_reply
    with pytest.raises(RuntimeError), capture_finalizer(DecisionTraceCapture()):
        raise RuntimeError("synthetic observation failure")
    assert application.finalize_reply is original


def test_single_case_diagnostic_is_traced_capped_and_cannot_promote_to_phase_b(tmp_path):
    calls = []

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "completed",
                "output": [
                    {"type": "reasoning", "summary": [{"text": "hidden-reasoning-not-exported"}]},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": multi_fact_decision().model_dump_json()}
                        ],
                    },
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "total_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 40},
                },
            },
        )

    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=tmp_path / "run",
        revision="33f16ad",
        case_id="grounding-multiple-facts",
        transport=httpx.MockTransport(transport),
    )
    assert len(calls) == 1
    assert report["phase_a_status"] == "completed"
    assert report["phase_b_executed"] is False
    assert report["execution_scope"] == "single_case_diagnostic"
    assert report["global_cap_usd"] == report["phase_a_cap_usd"] == 0.2
    sample = json.loads((tmp_path / "run" / "A-001-sample.json").read_text())
    assert sample["decision_trace"]["finalizer_handoff"] is False
    assert sample["decision_trace"]["final_rendered_fact_ids"] == ["price-corte", "hours-corte"]
    assert sample["checks"] == {
        "trusted_facts": "pass",
        "handoff_policy": "pass",
        "decision_contract": "pass",
    }
    assert all(
        "hidden-reasoning-not-exported" not in p.read_text() for p in (tmp_path / "run").iterdir()
    )


@pytest.mark.parametrize(
    ("overrides", "code", "finalizer_called"),
    [
        (
            {
                "knowledge_refs": ["unavailable-fact"],
                "reply_parts": [{"kind": "fact", "knowledge_ref": "unavailable-fact"}],
            },
            "invalid_reference",
            False,
        ),
        (
            {"reply_parts": [{"kind": "fact", "knowledge_ref": "price-corte"}]},
            "missing_critical_fact",
            True,
        ),
    ],
)
def test_live_trace_identifies_adapter_rejection_vs_actual_finalizer_override(
    tmp_path, overrides, code, finalizer_called
):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": multi_fact_decision(**overrides).model_dump_json(),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "total_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 40},
                },
            },
        )

    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=tmp_path / "run",
        revision="33f16ad",
        case_id="grounding-multiple-facts",
        transport=httpx.MockTransport(transport),
    )
    assert report["phase_a_status"] == "blocked"
    assert report["phase_b_executed"] is False
    sample = json.loads((tmp_path / "run" / "A-001-sample.json").read_text())
    trace = sample["decision_trace"]
    assert trace["override_code"] == code
    assert trace["finalizer_handoff"] is (True if finalizer_called else None)
    assert trace["final_rendered_fact_ids"] == []
    assert trace["whether_safe_fallback_was_used"] is True
