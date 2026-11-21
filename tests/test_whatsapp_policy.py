"""Synthetic policy evidence only: these tests do not observe or send HTTP."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.whatsapp_policy import (
    ConsentEvidence,
    EligibilityDecision,
    EligibilityKind,
    IdempotencyAge,
    InboundWindowEvidence,
    SubmissionResultKind,
    TemplateEvidence,
    classify_submission_result,
    evaluate_free_form,
    evaluate_template,
    idempotency_age,
    payload_fingerprint,
)

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
CHANNEL = "synthetic-channel"
CUSTOMER = "bsuid:synthetic-customer"
ONE_US = timedelta(microseconds=1)
DAY = timedelta(hours=24)
CONSENT = ConsentEvidence(
    channel_id=CHANNEL,
    customer_address=CUSTOMER,
    evidence_ref="synthetic-consent-proof",
    granted_at=NOW - timedelta(days=3),
    expires_at=NOW + timedelta(days=3),
)
RECENT = InboundWindowEvidence(
    source_at=NOW - timedelta(hours=1),
    event_at=NOW - timedelta(minutes=59),
    received_at=NOW - timedelta(minutes=58),
)
TEMPLATE = TemplateEvidence(
    channel_id=CHANNEL,
    customer_address=CUSTOMER,
    evidence_ref="synthetic-template-proof",
    template_name="service_response_synthetic",
    language="pt_BR",
    payload_fingerprint="synthetic-payload-binding",
    approved_at=NOW - DAY,
    expires_at=NOW + DAY,
)


def _free_form(**overrides: object) -> EligibilityDecision:
    arguments = {
        "channel_id": CHANNEL,
        "customer_address": CUSTOMER,
        "evidence": (RECENT,),
        "consent": CONSENT,
        "now": NOW,
    }
    arguments.update(overrides)
    return evaluate_free_form(**arguments)


def _template(**overrides: object) -> EligibilityDecision:
    arguments = {
        "channel_id": CHANNEL,
        "customer_address": CUSTOMER,
        "template_name": TEMPLATE.template_name,
        "language": TEMPLATE.language,
        "payload_fingerprint": TEMPLATE.payload_fingerprint,
        "template": TEMPLATE,
        "consent": CONSENT,
        "now": NOW,
    }
    arguments.update(overrides)
    return evaluate_template(**arguments)


@pytest.mark.parametrize(
    ("age", "eligible"),
    [(timedelta(0), True), (DAY - ONE_US, True), (DAY, False), (DAY + ONE_US, False)],
)
def test_free_form_window_uses_exact_source_boundary(age: timedelta, eligible: bool) -> None:
    source = NOW - age
    evidence = InboundWindowEvidence(source, source, source)
    result = _free_form(evidence=(evidence,))
    assert result.eligible is eligible
    assert result.kind is (EligibilityKind.FREE_FORM if eligible else EligibilityKind.UNPROVEN)


@pytest.mark.parametrize("field", ["source_at", "event_at", "received_at"])
@pytest.mark.parametrize(
    "invalid", [None, "2026-11-20T11:00:00Z", 1795172400, NOW.replace(tzinfo=None)]
)
def test_missing_or_invalid_timestamp_cannot_open_window(field: str, invalid: object) -> None:
    evidence = replace(RECENT, **{field: invalid})
    assert _free_form(evidence=(evidence,)).kind is EligibilityKind.UNPROVEN


@pytest.mark.parametrize(
    "evidence",
    [
        InboundWindowEvidence(NOW, NOW - ONE_US, NOW),
        InboundWindowEvidence(NOW - DAY, NOW, NOW - ONE_US),
        InboundWindowEvidence(NOW - ONE_US, NOW, NOW + ONE_US),
        InboundWindowEvidence(NOW + ONE_US, NOW + ONE_US, NOW + ONE_US),
    ],
)
def test_contradictory_or_future_provenance_denies(evidence: InboundWindowEvidence) -> None:
    assert not _free_form(evidence=(evidence,)).eligible


def test_recent_receipt_or_event_does_not_extend_old_customer_window() -> None:
    delayed = InboundWindowEvidence(NOW - DAY, NOW - ONE_US, NOW)
    assert not _free_form(evidence=(delayed,)).eligible


def test_future_first_receipt_is_not_rehabilitated_when_clock_advances() -> None:
    contradictory = InboundWindowEvidence(NOW, NOW + ONE_US, NOW)
    assert not _free_form(evidence=(contradictory,)).eligible
    assert not _free_form(evidence=(contradictory,), now=NOW + timedelta(hours=1)).eligible


def test_replaying_same_evidence_does_not_extend_window() -> None:
    evidence = InboundWindowEvidence(NOW - DAY + ONE_US, NOW - ONE_US, NOW)
    assert _free_form(evidence=(evidence, evidence)).eligible
    assert not _free_form(evidence=(evidence, evidence), now=NOW + ONE_US).eligible


@pytest.mark.parametrize("reversed_order", [False, True])
def test_latest_qualifying_inbound_is_order_independent(reversed_order: bool) -> None:
    old = InboundWindowEvidence(NOW - timedelta(days=2), NOW - DAY, NOW - DAY)
    invalid = InboundWindowEvidence(None, NOW, NOW)
    evidence = (old, invalid, RECENT)
    if reversed_order:
        evidence = tuple(reversed(evidence))
    assert _free_form(evidence=evidence).kind is EligibilityKind.FREE_FORM


def test_no_customer_message_evidence_denies_even_with_consent() -> None:
    assert _free_form(evidence=()).kind is EligibilityKind.UNPROVEN


@pytest.mark.parametrize("evaluate", [_free_form, _template])
@pytest.mark.parametrize("invalid", [None, "2026-11-20T12:00:00Z", NOW.replace(tzinfo=None)])
def test_invalid_policy_clock_denies(evaluate, invalid: object) -> None:
    assert evaluate(now=invalid).kind is EligibilityKind.UNPROVEN


@pytest.mark.parametrize("evaluate", [_free_form, _template])
@pytest.mark.parametrize("high_water", [NOW + ONE_US, "invalid", NOW.replace(tzinfo=None)])
def test_clock_rollback_or_unproven_high_water_denies(evaluate, high_water: object) -> None:
    assert not evaluate(high_water=high_water).eligible


@pytest.mark.parametrize("evaluate", [_free_form, _template])
def test_equal_high_water_and_clock_correction_forward_allow(evaluate) -> None:
    assert evaluate(high_water=NOW).eligible
    assert evaluate(high_water=NOW - ONE_US).eligible


@pytest.mark.parametrize("evaluate", [_free_form, _template])
@pytest.mark.parametrize(
    "consent",
    [
        None,
        replace(CONSENT, channel_id="different-channel"),
        replace(CONSENT, customer_address="different-customer"),
        replace(CONSENT, evidence_ref=""),
        replace(CONSENT, evidence_ref=" \n "),
        replace(CONSENT, evidence_ref=None),
        replace(CONSENT, granted_at=NOW + ONE_US),
        replace(CONSENT, granted_at=None),
        replace(CONSENT, granted_at=NOW.replace(tzinfo=None)),
        replace(CONSENT, expires_at=NOW),
        replace(CONSENT, expires_at=NOW - ONE_US),
        replace(CONSENT, expires_at="invalid"),
        replace(CONSENT, expires_at=NOW.replace(tzinfo=None)),
        replace(CONSENT, revoked_at=NOW - DAY),
        replace(CONSENT, revoked_at=NOW),
        replace(CONSENT, revoked_at=NOW + DAY),
    ],
)
def test_consent_proof_is_separate_scoped_current_and_revocable(evaluate, consent) -> None:
    decision = evaluate(consent=consent)
    assert decision.kind is EligibilityKind.UNPROVEN
    assert not decision.eligible


@pytest.mark.parametrize("evaluate", [_free_form, _template])
def test_consent_granted_at_now_is_valid_but_expires_at_now_is_not(evaluate) -> None:
    consent = replace(CONSENT, granted_at=NOW, expires_at=NOW + ONE_US)
    assert evaluate(consent=consent).eligible
    assert not evaluate(consent=consent, now=NOW + ONE_US).eligible


def test_aware_offsets_represent_the_same_instant() -> None:
    local_zone = timezone(timedelta(hours=-3))
    local_evidence = InboundWindowEvidence(
        RECENT.source_at.astimezone(local_zone),
        RECENT.event_at.astimezone(local_zone),
        RECENT.received_at.astimezone(local_zone),
    )
    local_consent = replace(
        CONSENT,
        granted_at=CONSENT.granted_at.astimezone(local_zone),
        expires_at=CONSENT.expires_at.astimezone(local_zone),
    )
    assert _free_form(
        evidence=(local_evidence,),
        consent=local_consent,
        now=NOW.astimezone(local_zone),
        high_water=NOW,
    ).eligible


def test_approved_template_is_classified_separately_without_inbound_window() -> None:
    decision = _template()
    assert decision.kind is EligibilityKind.APPROVED_TEMPLATE
    assert decision.eligible
    assert not _free_form(evidence=()).eligible


@pytest.mark.parametrize(
    "template",
    [
        None,
        replace(TEMPLATE, channel_id="different-channel"),
        replace(TEMPLATE, customer_address="different-customer"),
        replace(TEMPLATE, evidence_ref=""),
        replace(TEMPLATE, evidence_ref=" \n "),
        replace(TEMPLATE, evidence_ref=None),
        replace(TEMPLATE, template_name="different-template"),
        replace(TEMPLATE, language="en_US"),
        replace(TEMPLATE, payload_fingerprint="different-payload"),
        replace(TEMPLATE, status="pending"),
        replace(TEMPLATE, status="paused"),
        replace(TEMPLATE, status="rejected"),
        replace(TEMPLATE, status="disabled"),
        replace(TEMPLATE, status="revoked"),
        replace(TEMPLATE, purpose="marketing"),
        replace(TEMPLATE, purpose="follow_up"),
        replace(TEMPLATE, purpose="campaign"),
        replace(TEMPLATE, approved_at=NOW + ONE_US),
        replace(TEMPLATE, approved_at=None),
        replace(TEMPLATE, approved_at=NOW.replace(tzinfo=None)),
        replace(TEMPLATE, expires_at=NOW),
        replace(TEMPLATE, expires_at=NOW - ONE_US),
        replace(TEMPLATE, expires_at="invalid"),
        replace(TEMPLATE, expires_at=NOW.replace(tzinfo=None)),
    ],
)
def test_unproven_template_cannot_be_authorized(template) -> None:
    assert _template(template=template).kind is EligibilityKind.UNPROVEN


@pytest.mark.parametrize("field", ["template_name", "language", "payload_fingerprint"])
def test_empty_template_identity_denies_even_if_evidence_matches(field: str) -> None:
    assert not _template(template=replace(TEMPLATE, **{field: ""}), **{field: ""}).eligible


def test_template_approval_interval_has_exclusive_expiry() -> None:
    proof = replace(TEMPLATE, approved_at=NOW, expires_at=NOW + ONE_US)
    assert _template(template=proof).eligible
    assert not _template(template=proof, now=NOW + ONE_US).eligible


@pytest.mark.parametrize(
    ("kind", "eligible"),
    [
        (kind, kind in {EligibilityKind.FREE_FORM, EligibilityKind.APPROVED_TEMPLATE})
        for kind in EligibilityKind
    ],
)
def test_only_proven_message_modalities_are_eligible(kind: EligibilityKind, eligible: bool) -> None:
    assert EligibilityDecision(kind, "synthetic_reason").eligible is eligible


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(0), IdempotencyAge.WITHIN_DOCUMENTED_MAXIMUM),
        (DAY - ONE_US, IdempotencyAge.WITHIN_DOCUMENTED_MAXIMUM),
        (DAY, IdempotencyAge.EXPIRED),
        (DAY + ONE_US, IdempotencyAge.EXPIRED),
    ],
)
def test_external_idempotency_upper_bound_is_exact(
    age: timedelta, expected: IdempotencyAge
) -> None:
    assert idempotency_age(first_submission_at=NOW - age, now=NOW) is expected


@pytest.mark.parametrize("first", [None, "invalid", NOW.replace(tzinfo=None), NOW + ONE_US])
def test_idempotency_protection_requires_proven_first_submission(first: object) -> None:
    assert idempotency_age(first_submission_at=first, now=NOW) is IdempotencyAge.UNPROVEN


@pytest.mark.parametrize("high_water", [NOW + ONE_US, "invalid", NOW.replace(tzinfo=None)])
def test_idempotency_protection_does_not_survive_unproven_clock(high_water: object) -> None:
    assert (
        idempotency_age(first_submission_at=NOW - ONE_US, now=NOW, high_water=high_water)
        is IdempotencyAge.UNPROVEN
    )


def test_idempotency_age_never_restarts_from_a_later_attempt() -> None:
    first = NOW - DAY
    assert idempotency_age(first_submission_at=first, now=NOW) is IdempotencyAge.EXPIRED
    assert (
        idempotency_age(first_submission_at=first, now=NOW + DAY, high_water=NOW)
        is IdempotencyAge.EXPIRED
    )


def test_local_non_submission_proof_is_the_only_automatic_retry() -> None:
    result = classify_submission_result(submission_started=False, proven_not_submitted=True)
    assert result.kind is SubmissionResultKind.RETRYABLE
    assert result.automatic_retry


@pytest.mark.parametrize("submission_started", [False, True])
def test_timeout_alone_is_unknown_even_before_marker(submission_started: bool) -> None:
    result = classify_submission_result(submission_started=submission_started)
    assert result.kind is SubmissionResultKind.UNKNOWN
    assert not result.automatic_retry


def test_possible_submission_overrides_local_retry_assertion() -> None:
    result = classify_submission_result(submission_started=True, proven_not_submitted=True)
    assert result.kind is SubmissionResultKind.UNKNOWN
    assert not result.automatic_retry


@pytest.mark.parametrize("submission_started", [False, True])
@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (409, "10036", SubmissionResultKind.UNKNOWN),
        (409, "other", SubmissionResultKind.UNKNOWN),
        (409, "10027", SubmissionResultKind.UNKNOWN),
        (422, "10027", SubmissionResultKind.KEY_CONFLICT),
        (422, "other", SubmissionResultKind.UNKNOWN),
        (422, "10036", SubmissionResultKind.UNKNOWN),
        (429, None, SubmissionResultKind.UNKNOWN),
        (500, None, SubmissionResultKind.UNKNOWN),
        (502, None, SubmissionResultKind.UNKNOWN),
        (503, "10016", SubmissionResultKind.UNKNOWN),
        (504, None, SubmissionResultKind.UNKNOWN),
        (413, "10007", SubmissionResultKind.UNKNOWN),
    ],
)
def test_synthetic_http_evidence_has_no_blanket_safe_retry(
    submission_started: bool, status: int, code: str | None, expected: SubmissionResultKind
) -> None:
    # Deliberately hypothetical; no HTTP response is produced or claimed as observed.
    result = classify_submission_result(
        submission_started=submission_started,
        proven_not_submitted=True,
        http_status=status,
        error_code=code,
    )
    assert result.kind is expected
    assert not result.automatic_retry


def test_expired_key_cannot_make_ambiguous_outcome_retryable() -> None:
    assert idempotency_age(first_submission_at=NOW - DAY, now=NOW) is IdempotencyAge.EXPIRED
    result = classify_submission_result(submission_started=True)
    assert result.kind is SubmissionResultKind.UNKNOWN
    assert not result.automatic_retry


def test_policy_results_do_not_expose_private_evidence() -> None:
    output = repr((_free_form(), _template(), CONSENT, TEMPLATE))
    assert CHANNEL not in output
    assert CUSTOMER not in output
    assert CONSENT.evidence_ref not in output
    assert TEMPLATE.evidence_ref not in output
    assert TEMPLATE.payload_fingerprint not in output


@pytest.mark.parametrize(
    "unrepresentable",
    [
        datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
        datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),
    ],
)
def test_unrepresentable_utc_timestamp_fails_closed(unrepresentable: datetime) -> None:
    assert not _free_form(evidence=(replace(RECENT, source_at=unrepresentable),)).eligible
    assert not _template(template=replace(TEMPLATE, approved_at=unrepresentable)).eligible
    assert idempotency_age(first_submission_at=unrepresentable, now=NOW) is IdempotencyAge.UNPROVEN


def test_maximum_datetime_uses_subtraction_without_overflow() -> None:
    now = datetime.max.replace(tzinfo=UTC) - ONE_US
    consent = replace(CONSENT, granted_at=now - DAY, expires_at=datetime.max.replace(tzinfo=UTC))
    evidence = InboundWindowEvidence(now, now, now)
    assert _free_form(evidence=(evidence,), consent=consent, now=now).eligible
    assert (
        idempotency_age(first_submission_at=now, now=now)
        is IdempotencyAge.WITHIN_DOCUMENTED_MAXIMUM
    )


def test_payload_binding_is_stable_across_retry_and_key_change() -> None:
    message = OutboundMessage(CHANNEL, CUSTOMER, "Conteúdo sintético ☕", submission_key="first")
    assert payload_fingerprint(message) == payload_fingerprint(replace(message))
    assert payload_fingerprint(message) == payload_fingerprint(
        replace(message, submission_key="different-key")
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"sender_address": "different-channel"},
        {"recipient_address": "different-customer"},
        {"body": "Resposta sintética\n"},
        {"body": "resposta sintética"},
    ],
)
def test_payload_binding_detects_identity_and_content_changes(changed: dict[str, str]) -> None:
    message = OutboundMessage(CHANNEL, CUSTOMER, "Resposta sintética")
    assert payload_fingerprint(message) != payload_fingerprint(replace(message, **changed))
