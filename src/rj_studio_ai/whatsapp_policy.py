"""Offline WhatsApp evidence policy; no HTTP, credentials or activation authority."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from rj_studio_ai.domain import OutboundMessage

SERVICE_WINDOW = timedelta(hours=24)
IDEMPOTENCY_MAXIMUM_AGE = timedelta(hours=24)


class EligibilityKind(StrEnum):
    FREE_FORM = "free_form"
    APPROVED_TEMPLATE = "approved_template"
    UNPROVEN = "unproven"
    CHANNEL_BLOCKED = "channel_blocked"
    OPERATIONAL_UNKNOWN = "operational_unknown"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    kind: EligibilityKind
    reason: str

    @property
    def eligible(self) -> bool:
        return self.kind in {EligibilityKind.FREE_FORM, EligibilityKind.APPROVED_TEMPLATE}


@dataclass(frozen=True, slots=True)
class InboundWindowEvidence:
    """First authenticated receipt of one logical Customer Message, selected by storage."""

    source_at: datetime | None
    event_at: datetime
    received_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class ConsentEvidence:
    channel_id: str
    customer_address: str
    evidence_ref: str
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True, repr=False)
class TemplateEvidence:
    """Trusted approval evidence, never inferred from an LLM or a template name."""

    channel_id: str
    customer_address: str
    evidence_ref: str
    template_name: str
    language: str
    payload_fingerprint: str
    approved_at: datetime
    expires_at: datetime
    status: str = "approved"
    purpose: str = "service_response"


def _aware(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    try:
        return value.astimezone(UTC) if value.utcoffset() is not None else None
    except (OverflowError, ValueError):
        return None


def _policy_time(now: datetime, high_water: datetime | None) -> datetime | None:
    current = _aware(now)
    previous = _aware(high_water)
    if current is None or (high_water is not None and previous is None):
        return None
    if previous is not None and current < previous:
        return None
    return current


def _consent_valid(
    consent: ConsentEvidence | None, channel: str, customer: str, now: datetime
) -> bool:
    if consent is None:
        return False
    granted, expires = _aware(consent.granted_at), _aware(consent.expires_at)
    return bool(
        consent.channel_id == channel
        and consent.customer_address == customer
        and isinstance(consent.evidence_ref, str)
        and consent.evidence_ref.strip()
        and consent.revoked_at is None
        and granted is not None
        and expires is not None
        and granted <= now < expires
    )


def evaluate_free_form(
    *,
    channel_id: str,
    customer_address: str,
    evidence: tuple[InboundWindowEvidence, ...],
    consent: ConsentEvidence | None,
    now: datetime,
    high_water: datetime | None = None,
) -> EligibilityDecision:
    """Classify message policy only; the store must also check every operational gate."""
    current = _policy_time(now, high_water)
    if current is None:
        return EligibilityDecision(EligibilityKind.UNPROVEN, "clock_unproven")
    if not _consent_valid(consent, channel_id, customer_address, current):
        return EligibilityDecision(EligibilityKind.UNPROVEN, "consent_unproven")
    for item in evidence:
        source, event, receipt = (
            _aware(item.source_at),
            _aware(item.event_at),
            _aware(item.received_at),
        )
        if source is None or event is None or receipt is None:
            continue
        # Subtraction avoids overflow for datetime.max and keeps the exact boundary.
        if source <= event <= receipt <= current and current - source < SERVICE_WINDOW:
            return EligibilityDecision(EligibilityKind.FREE_FORM, "customer_window_open")
    return EligibilityDecision(EligibilityKind.UNPROVEN, "customer_window_unproven")


def evaluate_template(
    *,
    channel_id: str,
    customer_address: str,
    template_name: str,
    language: str,
    payload_fingerprint: str,
    template: TemplateEvidence | None,
    consent: ConsentEvidence | None,
    now: datetime,
    high_water: datetime | None = None,
) -> EligibilityDecision:
    """Offline approval classification; this does not create or dispatch a template."""
    current = _policy_time(now, high_water)
    if current is None:
        return EligibilityDecision(EligibilityKind.UNPROVEN, "clock_unproven")
    if not _consent_valid(consent, channel_id, customer_address, current):
        return EligibilityDecision(EligibilityKind.UNPROVEN, "consent_unproven")
    if template is not None:
        approved, expires = _aware(template.approved_at), _aware(template.expires_at)
        if (
            template.channel_id == channel_id
            and template.customer_address == customer_address
            and isinstance(template.evidence_ref, str)
            and template.evidence_ref.strip()
            and template.template_name == template_name
            and bool(template_name.strip())
            and template.language == language
            and bool(language.strip())
            and template.payload_fingerprint == payload_fingerprint
            and bool(payload_fingerprint.strip())
            and template.status == "approved"
            and template.purpose == "service_response"
            and approved is not None
            and expires is not None
            and approved <= current < expires
        ):
            return EligibilityDecision(EligibilityKind.APPROVED_TEMPLATE, "template_proven")
    return EligibilityDecision(EligibilityKind.UNPROVEN, "template_unproven")


def payload_fingerprint(message: OutboundMessage) -> str:
    """Bind the canonical free-form intent, not future HTTP serialization bytes."""
    canonical = json.dumps(
        ["telnyx", "free_form", message.sender_address, message.recipient_address, message.body],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "v1:" + hashlib.sha256(canonical).hexdigest()


class IdempotencyAge(StrEnum):
    WITHIN_DOCUMENTED_MAXIMUM = "within_documented_maximum"
    EXPIRED = "expired"
    UNPROVEN = "unproven"


def idempotency_age(
    *, first_submission_at: datetime | None, now: datetime, high_water: datetime | None = None
) -> IdempotencyAge:
    """The documented 'up to 24h' is an upper bound, never permission to resend."""
    current, first = _policy_time(now, high_water), _aware(first_submission_at)
    if current is None or first is None or first > current:
        return IdempotencyAge.UNPROVEN
    if current - first >= IDEMPOTENCY_MAXIMUM_AGE:
        return IdempotencyAge.EXPIRED
    return IdempotencyAge.WITHIN_DOCUMENTED_MAXIMUM


class SubmissionResultKind(StrEnum):
    RETRYABLE = "retryable"
    UNKNOWN = "unknown"
    KEY_CONFLICT = "key_conflict"


@dataclass(frozen=True, slots=True)
class SubmissionResultPolicy:
    kind: SubmissionResultKind
    reason: str
    # No provider response currently proves a safe automatic retry in this policy.
    automatic_retry: bool = field(default=False)


def classify_submission_result(
    *,
    submission_started: bool,
    proven_not_submitted: bool = False,
    http_status: int | None = None,
    error_code: str | None = None,
) -> SubmissionResultPolicy:
    """Classify hypothetical/future adapter evidence; no HTTP is performed here.

    A timeout alone is not proof. The future adapter must supply verified response
    fields; this function does not parse a body or treat arbitrary 409/422 alike.
    """
    if http_status == 422 and error_code == "10027":
        return SubmissionResultPolicy(SubmissionResultKind.KEY_CONFLICT, "key_payload_conflict")
    if http_status == 409 and error_code == "10036":
        return SubmissionResultPolicy(SubmissionResultKind.UNKNOWN, "provider_in_progress")
    if proven_not_submitted and not submission_started and http_status is None:
        return SubmissionResultPolicy(
            SubmissionResultKind.RETRYABLE, "local_not_submitted", automatic_retry=True
        )
    return SubmissionResultPolicy(SubmissionResultKind.UNKNOWN, "submission_unproven")
