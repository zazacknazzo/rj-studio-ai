"""Allowlisted eval-only observation; never exports prose or provider payloads."""

from contextlib import contextmanager, nullcontext
from functools import partial
from typing import Literal
from unittest.mock import patch

from pydantic import StrictBool, model_validator

from rj_studio_ai import application
from rj_studio_ai.appointment_intake import reconcile_agentic_intake
from rj_studio_ai.evaluation.behavioral import actionable_information_question
from rj_studio_ai.evaluation.records import Identifier, RecordModel, check_privacy
from rj_studio_ai.handoff import HandoffReason, safe_handoff_reason
from rj_studio_ai.llm_decision import (
    ConversationalPurpose,
    ConversationalReplyPart,
    InformationTarget,
    Intent,
    NextConversationalAction,
    PreferenceTarget,
)


class DecisionTrace(RecordModel):
    selected_fact_ids: tuple[Identifier, ...]
    proposed_intents: tuple[Intent, ...] = ()
    proposed_knowledge_refs: tuple[Identifier, ...] = ()
    reply_part_kinds: tuple[Literal["phrase", "fact", "conversation"], ...] = ()
    conversational_purposes: tuple[ConversationalPurpose, ...] = ()
    proposed_next_action: NextConversationalAction | None = None
    proposed_information_targets: tuple[InformationTarget, ...] = ()
    retained_information_targets: tuple[InformationTarget, ...] = ()
    actionable_information_targets: tuple[InformationTarget, ...] = ()
    commercial_continuation_present: StrictBool = False
    # Heuristic product signal, never a safety gate or a claim about Customer intent.
    conversation_closed_early: StrictBool | None = None
    proposed_appointment_targets: tuple[PreferenceTarget, ...] = ()
    authorized_appointment_targets: tuple[PreferenceTarget, ...] = ()
    denied_appointment_targets: tuple[PreferenceTarget, ...] = ()
    authorized_handoff: StrictBool | None = None
    authorized_actions: tuple[Literal["ask_preference", "terminal_handoff"], ...] = ()
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
            reply_part_kinds=tuple(
                p["kind"] for p in parts if p.get("kind") in ("fact", "phrase", "conversation")
            ),
            conversational_purposes=tuple(
                p["purpose"]
                for p in parts
                if isinstance(p.get("purpose"), str) and p["purpose"] in set(ConversationalPurpose)
            ),
            proposed_appointment_targets=tuple(
                dict.fromkeys(
                    t
                    for p in parts
                    for t in (p["targets"] if isinstance(p.get("targets"), (list, tuple)) else ())
                    if isinstance(t, str) and t in set(PreferenceTarget)
                )
            ),
            proposed_next_action=payload.get("next_action")
            if isinstance(payload.get("next_action"), str)
            and payload["next_action"] in set(NextConversationalAction)
            else None,
            proposed_information_targets=tuple(
                dict.fromkeys(
                    t
                    for p in parts
                    for t in (
                        p["information_targets"]
                        if isinstance(p.get("information_targets"), (list, tuple))
                        else ()
                    )
                    if isinstance(t, str) and t in set(InformationTarget)
                )
            ),
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
                "retained_information_targets": tuple(
                    dict.fromkeys(
                        t
                        for part in result.reply_parts
                        if isinstance(part, ConversationalReplyPart)
                        and part.text in result.reply_text
                        for t in part.information_targets
                    )
                ),
                "actionable_information_targets": tuple(
                    dict.fromkeys(
                        t
                        for part in result.reply_parts
                        if isinstance(part, ConversationalReplyPart)
                        and part.text in result.reply_text
                        for t in part.information_targets
                        if actionable_information_question(part.text, t)
                    )
                ),
                "commercial_continuation_present": any(
                    isinstance(part, ConversationalReplyPart)
                    and part.text in result.reply_text
                    and part.purpose
                    in {ConversationalPurpose.COMMERCIAL_CONTINUATION, ConversationalPurpose.CTA}
                    for part in result.reply_parts
                ),
            }
        )
        facts = {f.id: f.statement for f in context.knowledge}
        # The finalizer adds mandatory policies to rendered references, without
        # modifying the proposed AST. Observe those too, then check persisted text.
        self._render_candidates = {
            reference: facts[reference]
            for reference in result.knowledge_refs
            if reference in facts and facts[reference] in result.reply_text
        }

    def finish(self, body, *, safe_fallback, persisted_handoff_reason=None):
        if body and persisted_handoff_reason and self.trace.finalizer_handoff is False:
            self.trace = self.trace.model_copy(
                update={
                    "override_code": safe_handoff_reason(persisted_handoff_reason),
                }
            )
        commercial_intents = {
            Intent.PRICE,
            Intent.SERVICE_INFORMATION,
            Intent.PROFESSIONAL,
            Intent.HOURS,
            Intent.LOCATION,
            Intent.PROMOTION_OR_DISCOUNT,
            Intent.APPOINTMENT_INTEREST,
        }
        continuing = self.trace.commercial_continuation_present or bool(
            self.trace.retained_information_targets or self.trace.authorized_appointment_targets
        )
        early_closure = None
        if (
            body
            and not safe_fallback
            and not persisted_handoff_reason
            and set(self.trace.proposed_intents) & commercial_intents
        ):
            if continuing:
                early_closure = False
            elif self.trace.proposed_next_action == NextConversationalAction.ANSWER_ONLY:
                early_closure = True
        return DecisionTrace.model_validate(
            {
                **self.trace.model_dump(),
                "conversation_closed_early": early_closure,
                "retained_information_targets": self.trace.retained_information_targets
                if body and not persisted_handoff_reason
                else (),
                "actionable_information_targets": self.trace.actionable_information_targets
                if body and not persisted_handoff_reason
                else (),
                "commercial_continuation_present": self.trace.commercial_continuation_present
                if body and not persisted_handoff_reason
                else False,
                "authorized_handoff": bool(persisted_handoff_reason),
                "authorized_actions": tuple(
                    (["terminal_handoff"] if persisted_handoff_reason else [])
                    + (
                        ["ask_preference"]
                        if self.trace.authorized_appointment_targets
                        and not persisted_handoff_reason
                        else []
                    )
                ),
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
def capture_finalizer(capture, *, timing=None):
    """Scope an observer to the isolated serial eval; restore the application seam on exit."""
    finalizer = application.finalize_reply

    def observed(decision, *, customer_message, context, **kwargs):
        with timing.measure("trusted_finalization_ms") if timing else nullcontext():
            result = finalizer(
                decision, customer_message=customer_message, context=context, **kwargs
            )
        intake = kwargs.get("appointment_intake")
        if intake is not None:
            intake = reconcile_agentic_intake(intake, result, prior=context.appointment_intake)
        if capture.trace is not None:
            proposed_targets = capture.trace.proposed_appointment_targets
            authorized = (
                tuple(intake.question_targets) if intake is not None and not result.handoff else ()
            )
            capture.trace = capture.trace.model_copy(
                update={
                    "authorized_appointment_targets": authorized,
                    "denied_appointment_targets": tuple(
                        t for t in proposed_targets if t not in authorized
                    ),
                }
            )
        with timing.measure("eval_bookkeeping_ms") if timing else nullcontext():
            capture.finalized(
                decision, result, context, customer_message, partial(finalizer, **kwargs)
            )
        return result

    with patch.object(application, "finalize_reply", observed):
        yield
