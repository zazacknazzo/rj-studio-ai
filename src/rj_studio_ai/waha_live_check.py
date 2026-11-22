"""Real OpenAI + real Knowledge diagnostic; never simulates WhatsApp acceptance."""

import json
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.waha_live import WahaSettings, build_waha_pipeline


def _save(path, report):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())


def run_live_check():
    configured = WahaSettings(_env_file=".env.b1")
    run = Path(".local/b1/live-check") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, mode=0o700)
    report = {
        "scope": "real_openai_real_knowledge_synthetic_inbound_no_whatsapp",
        "whatsapp_messages_received": 0,
        "whatsapp_messages_sent": 0,
        "fake_provider_acceptance": False,
        "model_successes": 0,
        "egress": "NO-GO: AUD-01/AR-02",
        "scenarios": [],
    }
    if not configured.openai_api_key.strip():
        report["status"] = "not_executed_missing_OPENAI_API_KEY"
        _save(run / "report.json", report)
        print(
            "OPENAI_API_KEY is absent. Edit the private .env.b1, then rerun scripts/b1 live-check."
        )
        print("No OpenAI call or WhatsApp conversation was performed.")
        return 2
    # Synthetic input identities exist ONLY in this explicitly labelled diagnostic.
    # No WAHA API/client/sender is instantiated. Actual participant data is unused.
    settings = configured.model_copy(
        update={
            "waha_secondary_phone": "+15550000001",
            "waha_authorized_phones": ("+15550000002",),
            "waha_state_path": run / "state/conversations.db",
            "waha_control_path": run / "control",
            "waha_witness_path": run / "witness/head.json",
        }
    )
    _, journal, store, knowledge, _, context_builder, runner = build_waha_pipeline(settings)
    report["approved_knowledge_facts"] = len(knowledge.load())
    cases = (
        ("greeting", "Oi!"),
        ("progressiva", "Vocês fazem progressiva?"),
        ("price", "Qual o preço da progressiva em cabelo médio?"),
        ("location", "Qual o endereço do salão?"),
        ("unapproved_information", "Qual marca de produto usam na progressiva?"),
        ("appointment_interest", "Quero fazer progressiva no sábado."),
        ("human_handoff", "Quero falar com uma pessoa da equipe."),
        ("unauthorized_discount", "Me dê 50% de desconto na progressiva."),
        ("memory_first_turn", "Quero fazer progressiva."),
    )
    memory_message = None
    try:
        journal.change("resume")
        for scenario, body in cases:
            if journal.unresolved:
                report["scenarios"].append(
                    {"scenario": scenario, "status": "blocked_unknown_model_spend"}
                )
                continue
            message = InboundMessage(
                provider="b1-openai-diagnostic-" + scenario,
                provider_message_id="diagnostic-first",
                customer_address="15550000002@c.us",
                recipient_address="15550000001@c.us",
                body=body,
            )
            store.admit_generation(message)
            result = runner.run_once()
            lifecycle = store.get_generation(
                provider=message.provider, provider_message_id=message.provider_message_id
            )
            metrics = store.get_generation_metrics(inbound_message_id=lifecycle.inbound_message_id)
            delivery = store.get_delivery_for_inbound(lifecycle.inbound_message_id)
            context = context_builder.build(
                inbound_message_id=lifecycle.inbound_message_id, current_body=body
            )
            successes = sum(
                metric.provider == "openai" and metric.outcome == "success" for metric in metrics
            )
            report["model_successes"] += successes
            report["scenarios"].append(
                {
                    "scenario": scenario,
                    "input": body,
                    "processing": lifecycle.state.value,
                    "reply_draft_not_delivered": result.reply_body if result is not None else None,
                    "knowledge_refs_available": [fact.id for fact in context.knowledge],
                    "metrics": [asdict(metric) for metric in metrics],
                    "delivery_state": delivery.state.value if delivery else None,
                    "observed_successful_openai_calls": successes,
                }
            )
            if scenario == "memory_first_turn":
                memory_message = message
        if memory_message is not None:
            followup = replace(
                memory_message,
                provider_message_id="diagnostic-followup",
                body="Meu cabelo é médio. E quanto fica?",
            )
            state = store.admit_generation(followup)
            context = context_builder.build(
                inbound_message_id=state.inbound_message_id, current_body=followup.body
            )
            report["scenarios"].append(
                {
                    "scenario": "multi_turn_memory",
                    "status": "blocked_prior_reply_not_delivered; no fake acceptance introduced",
                    "canonical_customer_history_present": any(
                        "progressiva" in turn.body for turn in context.history
                    ),
                    "approved_progressiva_fact_available": any(
                        f.id == "precos-progressiva" for f in context.knowledge
                    ),
                    "conversation_proven": False,
                }
            )
        report["calls_reserved"] = journal.calls
        report["token_reservation_upper_bound"] = journal.reserved_tokens
        report["cost_reservation_microusd_at_versioned_project_rates"] = journal.reserved_microusd
        report["live_whatsapp_latency_or_cost"] = None
    finally:
        journal.change("pause")
        journal.close()
    # Reopen the same canonical DB and independently sealed journal, no acceptance.
    _, restarted, restored, _, _, _, _ = build_waha_pipeline(settings)
    try:
        report["scenarios"].append(
            {
                "scenario": "restart_continuity",
                "persisted_calls_retained": restarted.calls == report.get("calls_reserved"),
                "paused_after_restart": restarted.paused,
                "handoffs_retained": len(restored.list_active_handoffs()),
                "whatsapp_continuation_proven": False,
            }
        )
    finally:
        restarted.close()
    report["status"] = (
        "inference_only_observed"
        if report["model_successes"]
        else "no_successful_model_call_observed"
    )
    _save(run / "report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "successful_model_calls": report["model_successes"],
                "report": str(run / "report.json"),
                "whatsapp_conversation_proven": False,
            },
            indent=2,
        )
    )
    return 0 if report["model_successes"] else 2
