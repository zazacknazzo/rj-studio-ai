"""Allowlisted eval-only observation; never exports prose or provider payloads."""

from contextlib import contextmanager
from typing import Literal
from unittest.mock import patch

from pydantic import StrictBool, model_validator

from rj_studio_ai import application
from rj_studio_ai.evaluation.records import Identifier, RecordModel, check_privacy
from rj_studio_ai.handoff import HandoffReason, safe_handoff_reason
from rj_studio_ai.llm_decision import FactReplyPart, Intent


class DecisionTrace(RecordModel):
    selected_fact_ids: tuple[Identifier, ...]
    proposed_intents: tuple[Intent, ...] = ()
    proposed_knowledge_refs: tuple[Identifier, ...] = ()
    reply_part_kinds: tuple[Literal["phrase", "fact"], ...] = ()
    reply_part_fact_refs: tuple[Identifier, ...] = ()
    proposed_handoff: StrictBool | None = None
    normalized_handoff_reason: HandoffReason | None = None
    finalizer_handoff: StrictBool | None = None
    finalizer_reason_code: HandoffReason | None = None
    override_code: HandoffReason | Literal["invalid_reference", "invalid_decision"] | None = None
    final_rendered_fact_ids: tuple[Identifier, ...] = ()
    whether_safe_fallback_was_used: StrictBool = False

    @model_validator(mode="after")
    def private_metadata(self):
        check_privacy(self.model_dump(mode="json"))
        return self


class DecisionTraceCapture:
    """One serial eval execution; retain only metadata and approved render candidates."""

    def __init__(self):
        self.trace = None
        self._render_candidates = {}

    def propose(self, payload, context):
        selected = tuple(f.id for f in context.knowledge)
        payload = payload if isinstance(payload, dict) else {}

        def references(values):
            if not isinstance(values, (list, tuple)):
                return ()
            # Unknown model IDs may themselves contain PII/credentials. Never copy them.
            return tuple(
                value if value in selected else "unavailable-reference" for value in values
            )

        intents = payload.get("intents", ())
        parts = payload.get("reply_parts", ())
        parts = (
            [p for p in parts if isinstance(p, dict)] if isinstance(parts, (list, tuple)) else []
        )
        handoff = payload.get("handoff")
        reason = payload.get("handoff_reason")
        self.trace = DecisionTrace(
            selected_fact_ids=selected,
            proposed_intents=tuple(i for i in intents if isinstance(i, str) and i in set(Intent))
            if isinstance(intents, (list, tuple))
            else (),
            proposed_knowledge_refs=references(payload.get("knowledge_refs", ())),
            reply_part_kinds=tuple(p["kind"] for p in parts if p.get("kind") in ("fact", "phrase")),
            reply_part_fact_refs=references(
                [p.get("knowledge_ref") for p in parts if p.get("kind") == "fact"]
            ),
            proposed_handoff=handoff if type(handoff) is bool else None,
            normalized_handoff_reason=safe_handoff_reason(reason)
            if handoff is True and isinstance(reason, str)
            else None,
        )
        self._render_candidates = {}

    def rejected(self, code):
        self.trace = self.trace.model_copy(update={"override_code": code})

    def finalized(self, decision, result, context, customer_message, finalizer):
        if self.trace is None:
            self.propose(decision.model_dump(mode="json"), context)
        reason = safe_handoff_reason(result.handoff_reason) if result.handoff else None
        override = reason
        if decision.handoff and result.handoff:
            # Probe only the pure deterministic finalizer with a reason marker.
            # A model branch echoes it; earlier trusted policies retain their code.
            # This result is never sent, persisted, or substituted for the actual result.
            marker = "eval-model-request-marker"
            probe = finalizer(
                decision.model_copy(update={"handoff_reason": marker}),
                customer_message=customer_message,
                context=context,
            )
            if probe.handoff_reason == marker and self.trace.proposed_handoff is True:
                override = HandoffReason.MODEL_REQUEST
        self.trace = self.trace.model_copy(
            update={
                "finalizer_handoff": result.handoff,
                "finalizer_reason_code": reason,
                "override_code": override,
            }
        )
        facts = {f.id: f.statement for f in context.knowledge}
        self._render_candidates = {
            part.knowledge_ref: facts[part.knowledge_ref]
            for part in result.reply_parts
            if isinstance(part, FactReplyPart)
        }

    def finish(self, body, *, safe_fallback, persisted_handoff_reason=None):
        if body and persisted_handoff_reason and self.trace.finalizer_handoff is False:
            self.trace = self.trace.model_copy(
                update={
                    "override_code": safe_handoff_reason(persisted_handoff_reason),
                }
            )
        return DecisionTrace.model_validate(
            {
                **self.trace.model_dump(),
                "final_rendered_fact_ids": tuple(
                    identifier
                    for identifier, statement in self._render_candidates.items()
                    if body and statement in body
                ),
                "whether_safe_fallback_was_used": safe_fallback
                or (
                    self.trace.finalizer_handoff is True
                    and self.trace.override_code != "model_requested_handoff"
                )
                or bool(
                    body and persisted_handoff_reason and self.trace.finalizer_handoff is False
                ),
            }
        )


@contextmanager
def capture_finalizer(capture):
    """Scope an observer to the isolated serial eval; restore the application seam on exit."""
    finalizer = application.finalize_reply

    def observed(decision, *, customer_message, context):
        result = finalizer(decision, customer_message=customer_message, context=context)
        capture.finalized(decision, result, context, customer_message, finalizer)
        return result

    with patch.object(application, "finalize_reply", observed):
        yield
