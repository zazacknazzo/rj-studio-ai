import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from rj_studio_ai.domain import (
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessage,
    MessageRecord,
)
from rj_studio_ai.generation import GenerationMetric
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.sqlite import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    SqliteDurabilityError,
    SqliteDurabilityState,
    apply_sqlite_connection_pragmas,
    busy_timeout_milliseconds,
    configure_sqlite_connection,
    inspect_sqlite_connection,
    require_file_backed_database,
)


class PersistenceUnavailable(RuntimeError):
    """Raised when SQLite cannot complete a persistence operation."""


class GenerationRecoveryNotAvailable(RuntimeError):
    """Raised when an operator selects a Message that cannot be recovered."""


class GenerationRecoveryBlocked(GenerationRecoveryNotAvailable):
    """Raised when an earlier non-terminal Message prevents recovery."""


class GenerationState(StrEnum):
    PROCESSING = "processing"
    RETRYABLE = "retryable"
    COMPLETED = "completed"
    SUPPRESSED = "suppressed"


class DeliveryState(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    RETRYABLE = "retryable"
    UNKNOWN = "unknown"
    ACCEPTED = "accepted"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ACCEPTED_LEGACY = "accepted_legacy"


class DeliveryStatusDisposition(StrEnum):
    APPLIED = "applied"
    BUFFERED = "buffered"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class GenerationClaimResult:
    acquired: bool
    inbound_message_id: int
    state: GenerationState
    attempt_count: int
    owner_token: str | None
    lease_expires_at: datetime | None
    reply_body: str | None
    inbound_body: str
    blocked_by_predecessor: bool = False


@dataclass(frozen=True, slots=True)
class PurgeResult:
    messages_deleted: int
    conversations_deleted: int


@dataclass(frozen=True, slots=True)
class ConversationDeletionResult:
    messages_deleted: int
    conversations_deleted: int


@dataclass(frozen=True, slots=True)
class GenerationMetricRecord:
    attempt_number: int
    provider: str
    model: str
    configuration: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_microusd: int | None
    outcome: str
    error_code: str | None


@dataclass(frozen=True, slots=True)
class RecentContextHistory:
    """Bounded canonical turns plus whether older turns were omitted."""

    records: tuple[MessageRecord, ...]
    has_omitted_messages: bool


@dataclass(frozen=True, slots=True)
class PendingGeneration:
    """Safe operational metadata for a non-terminal inbound Message."""

    inbound_message_id: int
    conversation_id: int
    state: GenerationState
    attempt_count: int
    created_at: datetime
    lease_expires_at: datetime | None
    is_stale: bool
    blocked_by_predecessor: bool


@dataclass(frozen=True, slots=True)
class OutboundDeliveryRecord:
    delivery_id: int
    outbound_message_id: int
    inbound_message_id: int
    provider: str
    provider_channel_id: str
    recipient_address: str
    body: str
    state: DeliveryState
    attempt_count: int
    owner_token: str | None
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    provider_message_id: str | None
    safe_error_code: str | None
    accepted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryAttemptRecord:
    attempt_number: int
    outcome: str
    provider_message_id: str | None
    safe_error_code: str | None
    started_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeliveryMetricRecord:
    provider: str
    state: DeliveryState
    attempt_count: int
    acceptance_latency_ms: int | None
    latest_attempt_latency_ms: int | None
    safe_error_code: str | None


@dataclass(frozen=True, slots=True)
class BlockedDelivery:
    delivery_id: int
    conversation_id: int
    provider: str
    state: DeliveryState
    attempt_count: int
    safe_error_code: str
    updated_at: datetime


class SqliteConversationStore:
    _generation_lease = timedelta(seconds=30)
    _delivery_lease = timedelta(seconds=30)
    _maximum_generation_attempts = 2

    def __init__(
        self,
        database_path: Path,
        *,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
    ) -> None:
        self._database_path = database_path
        self._busy_timeout_seconds = busy_timeout_seconds
        self._migrations = MigrationManager(
            database_path,
            busy_timeout_seconds=busy_timeout_seconds,
        )

    def initialize(self) -> None:
        self._migrations.upgrade()

    def migrations_are_current(self) -> bool:
        return self._migrations.is_current()

    def sqlite_durability_checks(self) -> dict[str, str]:
        checks = {
            "sqlite_storage": "failed",
            "sqlite_journal_mode": "failed",
            "sqlite_synchronous": "failed",
            "sqlite_foreign_keys": "failed",
            "sqlite_busy_timeout": "failed",
        }
        try:
            require_file_backed_database(self._database_path)
            if not self._database_path.is_file():
                return checks
            checks["sqlite_storage"] = "ok"
            with closing(
                sqlite3.connect(
                    self._database_path,
                    timeout=self._busy_timeout_seconds,
                )
            ) as connection:
                apply_sqlite_connection_pragmas(
                    connection,
                    busy_timeout_seconds=self._busy_timeout_seconds,
                    set_journal_mode=False,
                )
                state = inspect_sqlite_connection(connection)
            checks.update(
                state.readiness_checks(
                    expected_busy_timeout_ms=busy_timeout_milliseconds(self._busy_timeout_seconds)
                )
            )
        except (sqlite3.Error, SqliteDurabilityError):
            return checks
        return checks

    def connection_durability_state(self) -> SqliteDurabilityState:
        with self._connect() as connection:
            return inspect_sqlite_connection(connection)

    def is_writable(self) -> bool:
        if not self._database_path.is_file():
            return False
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE alembic_version SET version_num = version_num")
                connection.rollback()
        except (sqlite3.Error, SqliteDurabilityError):
            return False
        return True

    def get_or_create_reply(self, message: InboundMessage, reply_body: str) -> str:
        try:
            return self._get_or_create_reply(message, reply_body)
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def claim_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        try:
            return self._claim_generation(message, now, lock_timeout)
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def admit_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        """Persist an inbound Message without acquiring its generation claim."""
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                inbound_message_id = self._get_or_create_inbound(
                    connection,
                    message,
                    current_time.isoformat(),
                )
                return self._generation_result(
                    connection,
                    inbound_message_id,
                    acquired=False,
                )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def mark_generation_retryable(
        self,
        *,
        inbound_message_id: int,
        owner_token: str,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> bool:
        if not owner_token.strip():
            raise ValueError("Generation owner token must not be empty")
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                updated = connection.execute(
                    """
                    UPDATE message_processing
                    SET state = 'retryable',
                        owner_token = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE inbound_message_id = ?
                      AND state = 'processing'
                      AND owner_token = ?
                      AND lease_expires_at > ?
                    """,
                    (
                        current_time.isoformat(),
                        inbound_message_id,
                        owner_token,
                        current_time.isoformat(),
                    ),
                ).rowcount
            return updated == 1
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def complete_generation(
        self,
        *,
        inbound_message_id: int,
        owner_token: str,
        reply_body: str,
        delivery_state: DeliveryState = DeliveryState.UNKNOWN,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> bool:
        if not owner_token.strip():
            raise ValueError("Generation owner token must not be empty")
        try:
            return self._complete_generation(
                inbound_message_id=inbound_message_id,
                owner_token=owner_token,
                reply_body=reply_body,
                delivery_state=delivery_state,
                now=now,
                lock_timeout=lock_timeout,
            )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def get_delivery_for_inbound(
        self,
        inbound_message_id: int,
    ) -> OutboundDeliveryRecord | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    {self._delivery_select()}
                    WHERE outbound.in_reply_to_message_id = ?
                    """,
                    (inbound_message_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error
        return None if row is None else self._delivery_record(row)

    def get_delivery_for_provider_inbound(
        self,
        *,
        provider: str,
        provider_message_id: str,
        lock_timeout: float | None = None,
    ) -> OutboundDeliveryRecord | None:
        try:
            with self._connect(lock_timeout) as connection:
                row = connection.execute(
                    f"""
                    {self._delivery_select()}
                    JOIN messages AS inbound ON inbound.id = outbound.in_reply_to_message_id
                    WHERE inbound.provider = ?
                      AND inbound.provider_message_id = ?
                      AND inbound.direction = 'inbound'
                    """,
                    (provider, provider_message_id),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error
        return None if row is None else self._delivery_record(row)

    def legacy_delivery_mode_is_safe(self) -> bool:
        """Reject rollback while proactive work could be stranded or duplicated."""
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT NOT EXISTS(
                        SELECT 1
                        FROM outbound_deliveries
                        WHERE state IN ('pending', 'sending', 'retryable')
                           OR (
                                state = 'unknown'
                                AND safe_error_code != 'legacy_unverified'
                           )
                    ) AND NOT EXISTS(
                        SELECT 1 FROM message_processing
                        WHERE state IN ('retryable', 'processing')
                    )
                    """
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Delivery mode safety is unavailable") from error
        return bool(row[0])

    def get_delivery(self, delivery_id: int) -> OutboundDeliveryRecord | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    {self._delivery_select()}
                    WHERE delivery.id = ?
                    """,
                    (delivery_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error
        return None if row is None else self._delivery_record(row)

    def get_delivery_attempts(self, delivery_id: int) -> list[DeliveryAttemptRecord]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        attempt_number,
                        outcome,
                        provider_message_id,
                        safe_error_code,
                        started_at,
                        completed_at
                    FROM delivery_attempts
                    WHERE outbound_delivery_id = ?
                    ORDER BY attempt_number
                    """,
                    (delivery_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error
        return [
            DeliveryAttemptRecord(
                attempt_number=int(row[0]),
                outcome=str(row[1]),
                provider_message_id=None if row[2] is None else str(row[2]),
                safe_error_code=None if row[3] is None else str(row[3]),
                started_at=datetime.fromisoformat(str(row[4])),
                completed_at=None if row[5] is None else datetime.fromisoformat(str(row[5])),
            )
            for row in rows
        ]

    def get_delivery_metric(self, delivery_id: int) -> DeliveryMetricRecord | None:
        """Return privacy-safe latency and outcome data for one delivery."""
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        delivery.provider,
                        delivery.state,
                        delivery.attempt_count,
                        inbound.created_at,
                        delivery.accepted_at,
                        delivery.safe_error_code,
                        attempt.started_at,
                        attempt.completed_at
                    FROM outbound_deliveries AS delivery
                    JOIN messages AS outbound ON outbound.id = delivery.outbound_message_id
                    JOIN messages AS inbound ON inbound.id = outbound.in_reply_to_message_id
                    LEFT JOIN delivery_attempts AS attempt
                      ON attempt.outbound_delivery_id = delivery.id
                     AND attempt.attempt_number = delivery.attempt_count
                    WHERE delivery.id = ?
                    """,
                    (delivery_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery metrics are unavailable") from error
        if row is None:
            return None
        inbound_at = datetime.fromisoformat(str(row[3]))
        accepted_at = None if row[4] is None else datetime.fromisoformat(str(row[4]))
        attempt_started = None if row[6] is None else datetime.fromisoformat(str(row[6]))
        attempt_completed = None if row[7] is None else datetime.fromisoformat(str(row[7]))
        return DeliveryMetricRecord(
            provider=str(row[0]),
            state=DeliveryState(str(row[1])),
            attempt_count=int(row[2]),
            acceptance_latency_ms=(
                None
                if accepted_at is None
                else max(0, round((accepted_at - inbound_at).total_seconds() * 1_000))
            ),
            latest_attempt_latency_ms=(
                None
                if attempt_started is None or attempt_completed is None
                else max(
                    0,
                    round((attempt_completed - attempt_started).total_seconds() * 1_000),
                )
            ),
            safe_error_code=None if row[5] is None else str(row[5]),
        )

    def list_blocked_deliveries(self) -> list[BlockedDelivery]:
        """List operational metadata for deliveries requiring human recovery."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        delivery.id,
                        outbound.conversation_id,
                        delivery.provider,
                        delivery.state,
                        delivery.attempt_count,
                        delivery.safe_error_code,
                        delivery.updated_at
                    FROM outbound_deliveries AS delivery
                    JOIN messages AS outbound ON outbound.id = delivery.outbound_message_id
                    WHERE delivery.state IN ('unknown', 'failed')
                    ORDER BY delivery.updated_at, delivery.id
                    """
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Blocked Outbound Deliveries are unavailable") from error
        return [
            BlockedDelivery(
                delivery_id=int(row[0]),
                conversation_id=int(row[1]),
                provider=str(row[2]),
                state=DeliveryState(str(row[3])),
                attempt_count=int(row[4]),
                safe_error_code=str(row[5]),
                updated_at=datetime.fromisoformat(str(row[6])),
            )
            for row in rows
        ]

    def claim_next_delivery(
        self,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> OutboundDeliveryRecord | None:
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                timestamp = current_time.isoformat()
                self._expire_ambiguous_delivery_claims(connection, timestamp)
                candidate = connection.execute(
                    """
                    SELECT delivery.id
                    FROM outbound_deliveries AS delivery
                    JOIN messages AS outbound ON outbound.id = delivery.outbound_message_id
                    JOIN messages AS inbound ON inbound.id = outbound.in_reply_to_message_id
                    JOIN message_processing AS processing
                      ON processing.inbound_message_id = inbound.id
                    WHERE delivery.state IN ('pending', 'retryable')
                      AND delivery.next_attempt_at <= ?
                      AND processing.state = 'completed'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM messages AS predecessor
                          JOIN message_processing AS predecessor_processing
                            ON predecessor_processing.inbound_message_id = predecessor.id
                          LEFT JOIN messages AS predecessor_reply
                            ON predecessor_reply.in_reply_to_message_id = predecessor.id
                           AND predecessor_reply.direction = 'outbound'
                          LEFT JOIN outbound_deliveries AS predecessor_delivery
                            ON predecessor_delivery.outbound_message_id = predecessor_reply.id
                          WHERE predecessor.conversation_id = inbound.conversation_id
                            AND predecessor.direction = 'inbound'
                            AND predecessor.id < inbound.id
                            AND (
                                predecessor_processing.state NOT IN ('completed', 'suppressed')
                                OR (
                                    predecessor_processing.state = 'completed'
                                    AND (
                                        predecessor_delivery.id IS NULL
                                        OR predecessor_delivery.state NOT IN (
                                            'accepted', 'sent', 'delivered', 'read',
                                            'accepted_legacy', 'cancelled'
                                        )
                                    )
                                )
                            )
                      )
                    ORDER BY delivery.next_attempt_at, delivery.id
                    LIMIT 1
                    """,
                    (timestamp,),
                ).fetchone()
                if candidate is None:
                    return None
                delivery_id = int(candidate[0])
                owner_token = uuid4().hex
                lease_expires_at = (current_time + self._delivery_lease).isoformat()
                updated = connection.execute(
                    """
                    UPDATE outbound_deliveries
                    SET state = 'sending',
                        owner_token = ?,
                        lease_expires_at = ?,
                        attempt_count = attempt_count + 1,
                        next_attempt_at = NULL,
                        safe_error_code = NULL,
                        updated_at = ?
                    WHERE id = ?
                      AND state IN ('pending', 'retryable')
                      AND next_attempt_at <= ?
                    """,
                    (owner_token, lease_expires_at, timestamp, delivery_id, timestamp),
                ).rowcount
                if updated != 1:
                    raise sqlite3.IntegrityError("Outbound Delivery claim changed")
                attempt_number = int(
                    connection.execute(
                        "SELECT attempt_count FROM outbound_deliveries WHERE id = ?",
                        (delivery_id,),
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO delivery_attempts (
                        outbound_delivery_id,
                        attempt_number,
                        owner_token,
                        outcome,
                        started_at
                    ) VALUES (?, ?, ?, 'started', ?)
                    """,
                    (delivery_id, attempt_number, owner_token, timestamp),
                )
                row = connection.execute(
                    f"""
                    {self._delivery_select()}
                    WHERE delivery.id = ?
                    """,
                    (delivery_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.IntegrityError("Claimed Outbound Delivery is unavailable")
                return self._delivery_record(row)
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error

    def delivery_claim_is_current(
        self,
        *,
        delivery_id: int,
        owner_token: str,
        now: datetime | None = None,
    ) -> bool:
        if not owner_token.strip():
            return False
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM outbound_deliveries
                        WHERE id = ?
                          AND state = 'sending'
                          AND owner_token = ?
                          AND lease_expires_at > ?
                    )
                    """,
                    (delivery_id, owner_token, self._utc_time(now).isoformat()),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error
        return bool(row[0])

    def finalize_delivery(
        self,
        *,
        delivery_id: int,
        owner_token: str,
        outcome: DeliveryState,
        provider_message_id: str | None = None,
        safe_error_code: str | None = None,
        retry_at: datetime | None = None,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> bool:
        if not owner_token.strip():
            raise ValueError("Delivery owner token must not be empty")
        if outcome not in {
            DeliveryState.ACCEPTED,
            DeliveryState.RETRYABLE,
            DeliveryState.UNKNOWN,
            DeliveryState.FAILED,
        }:
            raise ValueError("Invalid Outbound Delivery finalization outcome")
        if outcome is DeliveryState.ACCEPTED:
            if provider_message_id is None or not provider_message_id.strip():
                raise ValueError("Provider Acceptance requires a provider Message ID")
            safe_error_code = None
        elif safe_error_code is None or not safe_error_code.strip():
            raise ValueError("Delivery failure requires a safe error code")
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                timestamp = current_time.isoformat()
                if outcome is DeliveryState.RETRYABLE:
                    if retry_at is None:
                        raise ValueError("Retryable delivery requires a retry time")
                    retry_time = self._utc_time(retry_at)
                    if retry_time <= current_time:
                        raise ValueError("Delivery retry time must be in the future")
                    next_attempt_at = retry_time.isoformat()
                else:
                    if retry_at is not None:
                        raise ValueError("Only retryable delivery can have a retry time")
                    next_attempt_at = None
                current = connection.execute(
                    """
                    SELECT attempt_count, provider
                    FROM outbound_deliveries
                    WHERE id = ?
                      AND state = 'sending'
                      AND owner_token = ?
                      AND lease_expires_at > ?
                    """,
                    (delivery_id, owner_token, timestamp),
                ).fetchone()
                if current is None:
                    return False
                attempt_number = int(current[0])
                provider = str(current[1])
                accepted_at = timestamp if outcome is DeliveryState.ACCEPTED else None
                updated = connection.execute(
                    """
                    UPDATE delivery_attempts
                    SET outcome = ?,
                        provider_message_id = ?,
                        safe_error_code = ?,
                        completed_at = ?
                    WHERE outbound_delivery_id = ?
                      AND attempt_number = ?
                      AND owner_token = ?
                      AND outcome = 'started'
                    """,
                    (
                        outcome,
                        provider_message_id,
                        safe_error_code,
                        timestamp,
                        delivery_id,
                        attempt_number,
                        owner_token,
                    ),
                ).rowcount
                if updated != 1:
                    raise sqlite3.IntegrityError("Delivery Attempt ownership changed")
                delivery_updated = connection.execute(
                    """
                    UPDATE outbound_deliveries
                    SET state = ?,
                        owner_token = NULL,
                        lease_expires_at = NULL,
                        next_attempt_at = ?,
                        provider_message_id = ?,
                        safe_error_code = ?,
                        accepted_at = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND state = 'sending'
                      AND owner_token = ?
                      AND lease_expires_at > ?
                    """,
                    (
                        outcome,
                        next_attempt_at,
                        provider_message_id,
                        safe_error_code,
                        accepted_at,
                        timestamp,
                        delivery_id,
                        owner_token,
                        timestamp,
                    ),
                ).rowcount
                if delivery_updated != 1:
                    raise sqlite3.IntegrityError("Outbound Delivery ownership changed")
                if outcome is DeliveryState.ACCEPTED and provider_message_id is not None:
                    pending_status = connection.execute(
                        """
                        SELECT status, safe_error_code
                        FROM pending_delivery_statuses
                        WHERE provider = ? AND provider_message_id = ?
                        """,
                        (provider, provider_message_id),
                    ).fetchone()
                    if pending_status is not None:
                        self._apply_delivery_status(
                            connection,
                            delivery_id=delivery_id,
                            status=DeliveryStatus(str(pending_status[0])),
                            safe_error_code=(
                                None if pending_status[1] is None else str(pending_status[1])
                            ),
                            timestamp=timestamp,
                        )
                        connection.execute(
                            """
                            DELETE FROM pending_delivery_statuses
                            WHERE provider = ? AND provider_message_id = ?
                            """,
                            (provider, provider_message_id),
                        )
            return True
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error

    def record_delivery_status(
        self,
        event: DeliveryStatusReceived,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> DeliveryStatusDisposition:
        if not event.provider.strip() or not event.provider_message_id.strip():
            raise ValueError("Delivery status requires provider identity")
        if event.status is DeliveryStatus.FAILED:
            if event.safe_error_code is None or not event.safe_error_code.strip():
                raise ValueError("Failed delivery status requires a safe error code")
        elif event.safe_error_code is not None:
            raise ValueError("Successful delivery status cannot carry an error code")
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = self._utc_time(now).isoformat()
                delivery = connection.execute(
                    """
                    SELECT id
                    FROM outbound_deliveries
                    WHERE provider = ? AND provider_message_id = ?
                    """,
                    (event.provider, event.provider_message_id),
                ).fetchone()
                if delivery is not None:
                    applied = self._apply_delivery_status(
                        connection,
                        delivery_id=int(delivery[0]),
                        status=event.status,
                        safe_error_code=event.safe_error_code,
                        timestamp=timestamp,
                    )
                    return (
                        DeliveryStatusDisposition.APPLIED
                        if applied
                        else DeliveryStatusDisposition.IGNORED
                    )

                existing = connection.execute(
                    """
                    SELECT status
                    FROM pending_delivery_statuses
                    WHERE provider = ? AND provider_message_id = ?
                    """,
                    (event.provider, event.provider_message_id),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO pending_delivery_statuses (
                            provider, provider_message_id, status, safe_error_code,
                            received_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.provider,
                            event.provider_message_id,
                            event.status,
                            event.safe_error_code,
                            timestamp,
                            timestamp,
                        ),
                    )
                    return DeliveryStatusDisposition.BUFFERED

                current_status = DeliveryStatus(str(existing[0]))
                if self._delivery_status_rank(event.status) <= self._delivery_status_rank(
                    current_status
                ):
                    return DeliveryStatusDisposition.IGNORED
                connection.execute(
                    """
                    UPDATE pending_delivery_statuses
                    SET status = ?, safe_error_code = ?, updated_at = ?
                    WHERE provider = ? AND provider_message_id = ?
                    """,
                    (
                        event.status,
                        event.safe_error_code,
                        timestamp,
                        event.provider,
                        event.provider_message_id,
                    ),
                )
                return DeliveryStatusDisposition.BUFFERED
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Delivery status persistence is unavailable") from error

    @staticmethod
    def _delivery_status_rank(status: DeliveryStatus) -> int:
        return {
            DeliveryStatus.SENT: 1,
            DeliveryStatus.DELIVERED: 2,
            DeliveryStatus.READ: 3,
            DeliveryStatus.FAILED: 4,
        }[status]

    @staticmethod
    def _apply_delivery_status(
        connection: sqlite3.Connection,
        *,
        delivery_id: int,
        status: DeliveryStatus,
        safe_error_code: str | None,
        timestamp: str,
    ) -> bool:
        current = connection.execute(
            "SELECT state FROM outbound_deliveries WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        if current is None:
            raise sqlite3.IntegrityError("Outbound Delivery is unavailable")
        current_state = DeliveryState(str(current[0]))
        allowed = {
            DeliveryState.ACCEPTED: {
                DeliveryStatus.SENT,
                DeliveryStatus.DELIVERED,
                DeliveryStatus.READ,
                DeliveryStatus.FAILED,
            },
            DeliveryState.SENT: {
                DeliveryStatus.DELIVERED,
                DeliveryStatus.READ,
                DeliveryStatus.FAILED,
            },
            DeliveryState.DELIVERED: {DeliveryStatus.READ, DeliveryStatus.FAILED},
            DeliveryState.READ: {DeliveryStatus.FAILED},
        }
        if status not in allowed.get(current_state, set()):
            return False
        connection.execute(
            """
            UPDATE outbound_deliveries
            SET state = ?, safe_error_code = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                safe_error_code if status is DeliveryStatus.FAILED else None,
                timestamp,
                delivery_id,
            ),
        )
        return True

    def reconcile_legacy_delivery(
        self,
        *,
        delivery_id: int,
        resolution: DeliveryState,
        now: datetime | None = None,
    ) -> bool:
        if resolution not in {DeliveryState.ACCEPTED_LEGACY, DeliveryState.CANCELLED}:
            raise ValueError("Legacy reconciliation must accept or cancel the delivery")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = self._utc_time(now).isoformat()
                accepted_at = timestamp if resolution is DeliveryState.ACCEPTED_LEGACY else None
                safe_error_code = (
                    None if resolution is DeliveryState.ACCEPTED_LEGACY else "legacy_cancelled"
                )
                updated = connection.execute(
                    """
                    UPDATE outbound_deliveries
                    SET state = ?,
                        safe_error_code = ?,
                        accepted_at = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND state = 'unknown'
                      AND safe_error_code = 'legacy_unverified'
                      AND attempt_count = 0
                      AND owner_token IS NULL
                      AND lease_expires_at IS NULL
                    """,
                    (
                        resolution,
                        safe_error_code,
                        accepted_at,
                        timestamp,
                        delivery_id,
                    ),
                ).rowcount
            return updated == 1
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error

    def confirm_legacy_delivery(
        self,
        *,
        provider: str,
        inbound_provider_message_id: str,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> bool:
        """Record that the synchronous legacy reply was rendered successfully."""
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT delivery.id, delivery.state
                    FROM outbound_deliveries AS delivery
                    JOIN messages AS outbound
                      ON outbound.id = delivery.outbound_message_id
                    JOIN messages AS inbound
                      ON inbound.id = outbound.in_reply_to_message_id
                    WHERE inbound.provider = ?
                      AND inbound.provider_message_id = ?
                      AND inbound.direction = 'inbound'
                    """,
                    (provider, inbound_provider_message_id),
                ).fetchone()
                if row is None:
                    return False
                if str(row[1]) == DeliveryState.ACCEPTED_LEGACY:
                    return True
                timestamp = self._utc_time(now).isoformat()
                updated = connection.execute(
                    """
                    UPDATE outbound_deliveries
                    SET state = 'accepted_legacy',
                        safe_error_code = NULL,
                        accepted_at = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND state = 'unknown'
                      AND safe_error_code = 'legacy_unverified'
                      AND attempt_count = 0
                      AND owner_token IS NULL
                      AND lease_expires_at IS NULL
                    """,
                    (timestamp, timestamp, int(row[0])),
                ).rowcount
                return updated == 1
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Outbound Delivery persistence is unavailable") from error

    def claim_exhausted_finalization(
        self,
        *,
        inbound_message_id: int,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        """Claim only terminalization after both generation attempts are unavailable."""
        try:
            return self._claim_exhausted_finalization(
                inbound_message_id=inbound_message_id,
                now=now,
                lock_timeout=lock_timeout,
            )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def suppress_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
    ) -> GenerationClaimResult:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                inbound_message_id = self._get_or_create_inbound(
                    connection,
                    message,
                    current_time.isoformat(),
                )
                current = self._generation_result(
                    connection,
                    inbound_message_id,
                    acquired=False,
                )
                if current.state is GenerationState.RETRYABLE and current.attempt_count == 0:
                    connection.execute(
                        """
                        UPDATE message_processing
                        SET state = 'suppressed', updated_at = ?
                        WHERE inbound_message_id = ?
                        """,
                        (current_time.isoformat(), inbound_message_id),
                    )
                    return self._generation_result(
                        connection,
                        inbound_message_id,
                        acquired=False,
                    )
                return current
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def get_generation(
        self,
        *,
        provider: str,
        provider_message_id: str,
    ) -> GenerationClaimResult | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT processing.inbound_message_id
                    FROM message_processing AS processing
                    JOIN messages AS inbound
                      ON inbound.id = processing.inbound_message_id
                    WHERE inbound.provider = ?
                      AND inbound.provider_message_id = ?
                      AND inbound.direction = 'inbound'
                    """,
                    (provider, provider_message_id),
                ).fetchone()
                if row is None:
                    return None
                return self._generation_result(connection, int(row[0]), acquired=False)
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def list_pending_generations(self, *, now: datetime | None = None) -> list[PendingGeneration]:
        """List retryable or lease-expired work without exposing Customer content."""
        try:
            with self._connect() as connection:
                current_time = self._utc_time(now)
                rows = connection.execute(
                    """
                    SELECT
                        inbound.id,
                        inbound.conversation_id,
                        processing.state,
                        processing.attempt_count,
                        inbound.created_at,
                        processing.lease_expires_at,
                        EXISTS (
                            SELECT 1
                            FROM messages AS predecessor
                            JOIN message_processing AS predecessor_processing
                              ON predecessor_processing.inbound_message_id = predecessor.id
                            LEFT JOIN messages AS predecessor_reply
                              ON predecessor_reply.in_reply_to_message_id = predecessor.id
                             AND predecessor_reply.direction = 'outbound'
                            LEFT JOIN outbound_deliveries AS predecessor_delivery
                              ON predecessor_delivery.outbound_message_id = predecessor_reply.id
                            WHERE predecessor.conversation_id = inbound.conversation_id
                              AND predecessor.direction = 'inbound'
                              AND predecessor.id < inbound.id
                              AND (
                                  predecessor_processing.state NOT IN ('completed', 'suppressed')
                                  OR (
                                      predecessor_processing.state = 'completed'
                                      AND (
                                          predecessor_delivery.id IS NULL
                                          OR predecessor_delivery.state NOT IN (
                                              'accepted', 'sent', 'delivered', 'read',
                                              'accepted_legacy', 'cancelled'
                                          )
                                      )
                                  )
                              )
                        ) AS blocked_by_predecessor
                    FROM message_processing AS processing
                    JOIN messages AS inbound ON inbound.id = processing.inbound_message_id
                    WHERE processing.state = 'retryable'
                       OR (
                            processing.state = 'processing'
                        AND processing.lease_expires_at <= ?
                       )
                    ORDER BY inbound.id
                    """,
                    (current_time.isoformat(),),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error
        return [
            PendingGeneration(
                inbound_message_id=int(row[0]),
                conversation_id=int(row[1]),
                state=GenerationState(str(row[2])),
                attempt_count=int(row[3]),
                created_at=datetime.fromisoformat(str(row[4])),
                lease_expires_at=None if row[5] is None else datetime.fromisoformat(str(row[5])),
                is_stale=GenerationState(str(row[2])) is GenerationState.PROCESSING,
                blocked_by_predecessor=bool(row[6]),
            )
            for row in rows
        ]

    def load_recoverable_inbound_message(
        self,
        *,
        inbound_message_id: int,
        now: datetime | None = None,
    ) -> InboundMessage:
        """Return one selected eligible inbound Message without changing its lifecycle."""
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current_time = self._utc_time(now)
                row = connection.execute(
                    """
                    SELECT
                        inbound.provider,
                        inbound.provider_message_id,
                        conversation.customer_address,
                        inbound.recipient_address,
                        inbound.body,
                        processing.state,
                        processing.lease_expires_at,
                        EXISTS (
                            SELECT 1
                            FROM messages AS predecessor
                            JOIN message_processing AS predecessor_processing
                              ON predecessor_processing.inbound_message_id = predecessor.id
                            LEFT JOIN messages AS predecessor_reply
                              ON predecessor_reply.in_reply_to_message_id = predecessor.id
                             AND predecessor_reply.direction = 'outbound'
                            LEFT JOIN outbound_deliveries AS predecessor_delivery
                              ON predecessor_delivery.outbound_message_id = predecessor_reply.id
                            WHERE predecessor.conversation_id = inbound.conversation_id
                              AND predecessor.direction = 'inbound'
                              AND predecessor.id < inbound.id
                              AND (
                                  predecessor_processing.state NOT IN ('completed', 'suppressed')
                                  OR (
                                      predecessor_processing.state = 'completed'
                                      AND (
                                          predecessor_delivery.id IS NULL
                                          OR predecessor_delivery.state NOT IN (
                                              'accepted', 'sent', 'delivered', 'read',
                                              'accepted_legacy', 'cancelled'
                                          )
                                      )
                                  )
                              )
                        ) AS blocked_by_predecessor
                    FROM messages AS inbound
                    JOIN conversations AS conversation ON conversation.id = inbound.conversation_id
                    JOIN message_processing AS processing
                      ON processing.inbound_message_id = inbound.id
                    WHERE inbound.id = ? AND inbound.direction = 'inbound'
                    """,
                    (inbound_message_id,),
                ).fetchone()
                if row is None:
                    raise GenerationRecoveryNotAvailable("Inbound Message is unavailable")
                state = GenerationState(str(row[5]))
                lease_expires_at = None if row[6] is None else datetime.fromisoformat(str(row[6]))
                if state in {GenerationState.COMPLETED, GenerationState.SUPPRESSED}:
                    raise GenerationRecoveryNotAvailable("Inbound Message is terminal")
                if (
                    state is GenerationState.PROCESSING
                    and lease_expires_at is not None
                    and lease_expires_at > current_time
                ):
                    raise GenerationRecoveryNotAvailable("Inbound Message has an active claim")
                if bool(row[7]):
                    raise GenerationRecoveryBlocked("Inbound Message is blocked by a predecessor")
                provider_message_id = row[1]
                if provider_message_id is None:
                    raise GenerationRecoveryNotAvailable(
                        "Inbound Message has no provider identifier"
                    )
                return InboundMessage(
                    provider=str(row[0]),
                    provider_message_id=str(provider_message_id),
                    customer_address=str(row[2]),
                    recipient_address=str(row[3]),
                    body=str(row[4]),
                )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def record_generation_metric(
        self,
        *,
        inbound_message_id: int,
        attempt_number: int,
        metric: GenerationMetric,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> None:
        try:
            with self._connect(lock_timeout) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO generation_metrics (
                        inbound_message_id, attempt_number, provider, model, configuration,
                        latency_ms, input_tokens, output_tokens, total_tokens,
                        estimated_cost_microusd, outcome, error_code, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inbound_message_id,
                        attempt_number,
                        metric.provider,
                        metric.model,
                        metric.configuration,
                        metric.latency_ms,
                        metric.input_tokens,
                        metric.output_tokens,
                        metric.total_tokens,
                        metric.estimated_cost_microusd,
                        metric.outcome,
                        metric.error_code,
                        self._utc_time(now).isoformat(),
                    ),
                )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Generation metric persistence is unavailable") from error

    def get_generation_metrics(self, *, inbound_message_id: int) -> list[GenerationMetricRecord]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        attempt_number, provider, model, configuration, latency_ms,
                        input_tokens, output_tokens, total_tokens, estimated_cost_microusd,
                        outcome, error_code
                    FROM generation_metrics
                    WHERE inbound_message_id = ?
                    ORDER BY attempt_number
                    """,
                    (inbound_message_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Generation metric persistence is unavailable") from error
        return [
            GenerationMetricRecord(
                attempt_number=int(row[0]),
                provider=str(row[1]),
                model=str(row[2]),
                configuration=str(row[3]),
                latency_ms=int(row[4]),
                input_tokens=None if row[5] is None else int(row[5]),
                output_tokens=None if row[6] is None else int(row[6]),
                total_tokens=None if row[7] is None else int(row[7]),
                estimated_cost_microusd=None if row[8] is None else int(row[8]),
                outcome=str(row[9]),
                error_code=None if row[10] is None else str(row[10]),
            )
            for row in rows
        ]

    def purge_messages_older_than(self, cutoff: datetime) -> PurgeResult:
        if cutoff.utcoffset() is None:
            raise ValueError("Retention cutoff must include a timezone")
        cutoff_text = cutoff.astimezone(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._delete_terminal_delivery_lifecycle_before_cutoff(
                    connection,
                    cutoff_text,
                )
                messages_deleted = connection.execute(
                    "DELETE FROM messages WHERE created_at < ?",
                    (cutoff_text,),
                ).rowcount
                conversations_deleted = connection.execute(
                    """
                    DELETE FROM conversations
                    WHERE NOT EXISTS (
                        SELECT 1 FROM messages
                        WHERE messages.conversation_id = conversations.id
                    )
                    """
                ).rowcount
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error
        return PurgeResult(
            messages_deleted=messages_deleted,
            conversations_deleted=conversations_deleted,
        )

    def delete_conversation(
        self,
        *,
        provider: str,
        customer_address: str,
    ) -> ConversationDeletionResult:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT id FROM conversations
                    WHERE provider = ? AND customer_address = ?
                    """,
                    (provider, customer_address),
                ).fetchone()
                if row is None:
                    return ConversationDeletionResult(0, 0)
                conversation_id = int(row[0])
                nonterminal_delivery = connection.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM outbound_deliveries AS delivery
                        JOIN messages AS outbound
                          ON outbound.id = delivery.outbound_message_id
                        WHERE outbound.conversation_id = ?
                          AND delivery.state NOT IN (
                              'accepted', 'sent', 'delivered', 'read',
                              'failed', 'cancelled', 'accepted_legacy'
                          )
                    )
                    """,
                    (conversation_id,),
                ).fetchone()
                if bool(nonterminal_delivery[0]):
                    raise sqlite3.IntegrityError(
                        "Conversation has nonterminal Outbound Delivery work"
                    )
                messages_deleted = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (conversation_id,),
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    DELETE FROM message_processing
                    WHERE inbound_message_id IN (
                        SELECT outbound.in_reply_to_message_id
                        FROM outbound_deliveries AS delivery
                        JOIN messages AS outbound
                          ON outbound.id = delivery.outbound_message_id
                        WHERE outbound.conversation_id = ?
                    )
                    """,
                    (conversation_id,),
                )
                connection.execute(
                    """
                    DELETE FROM outbound_deliveries
                    WHERE outbound_message_id IN (
                        SELECT id FROM messages WHERE conversation_id = ?
                    )
                    """,
                    (conversation_id,),
                )
                conversations_deleted = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).rowcount
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error
        return ConversationDeletionResult(
            messages_deleted=messages_deleted,
            conversations_deleted=conversations_deleted,
        )

    @staticmethod
    def _delete_terminal_delivery_lifecycle_before_cutoff(
        connection: sqlite3.Connection,
        cutoff: str,
    ) -> None:
        eligible = """
            SELECT outbound.in_reply_to_message_id
            FROM outbound_deliveries AS delivery
            JOIN messages AS outbound ON outbound.id = delivery.outbound_message_id
            JOIN messages AS inbound ON inbound.id = outbound.in_reply_to_message_id
            WHERE inbound.created_at < ?
              AND outbound.created_at < ?
              AND delivery.state IN (
                  'accepted', 'sent', 'delivered', 'read',
                  'cancelled', 'accepted_legacy'
              )
        """
        connection.execute(
            f"""
            DELETE FROM message_processing
            WHERE inbound_message_id IN ({eligible})
            """,
            (cutoff, cutoff),
        )
        connection.execute(
            """
            DELETE FROM outbound_deliveries
            WHERE outbound_message_id IN (
                SELECT outbound.id
                FROM outbound_deliveries AS delivery
                JOIN messages AS outbound
                  ON outbound.id = delivery.outbound_message_id
                JOIN messages AS inbound
                  ON inbound.id = outbound.in_reply_to_message_id
                WHERE inbound.created_at < ?
                  AND outbound.created_at < ?
                  AND delivery.state IN (
                      'accepted', 'sent', 'delivered', 'read',
                      'cancelled', 'accepted_legacy'
                  )
            )
            """,
            (cutoff, cutoff),
        )

    def _get_or_create_reply(self, message: InboundMessage, reply_body: str) -> str:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inbound_message_id = self._get_or_create_inbound(
                connection,
                message,
                timestamp,
            )
            existing = connection.execute(
                """
                SELECT inbound.conversation_id, outbound.body
                FROM messages AS inbound
                LEFT JOIN messages AS outbound
                  ON outbound.in_reply_to_message_id = inbound.id
                 AND outbound.direction = 'outbound'
                WHERE inbound.id = ?
                """,
                (inbound_message_id,),
            ).fetchone()
            if existing is None:
                raise sqlite3.IntegrityError("Persisted inbound Message is unavailable")
            conversation_id = int(existing[0])
            if existing[1] is not None:
                return str(existing[1])

            outbound_message_id = int(
                connection.execute(
                    """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (?, ?, NULL, 'outbound', ?, ?, ?)
                RETURNING id
                """,
                    (
                        conversation_id,
                        message.provider,
                        reply_body,
                        timestamp,
                        inbound_message_id,
                    ),
                ).fetchone()[0]
            )
            self._insert_delivery(
                connection,
                outbound_message_id=outbound_message_id,
                provider=message.provider,
                provider_channel_id=message.recipient_address,
                recipient_address=message.customer_address,
                delivery_state=DeliveryState.UNKNOWN,
                timestamp=timestamp,
            )
            processing_updated = connection.execute(
                """
                UPDATE message_processing
                SET state = 'completed',
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE inbound_message_id = ?
                  AND state = 'retryable'
                  AND attempt_count = 0
                """,
                (timestamp, inbound_message_id),
            ).rowcount
            if processing_updated != 1:
                raise sqlite3.IntegrityError(
                    "Automatic Reply cannot overwrite generation processing state"
                )
            connection.execute(
                """
                UPDATE conversations SET updated_at = ? WHERE id = ?
                """,
                (timestamp, conversation_id),
            )
        return reply_body

    def _claim_generation(
        self,
        message: InboundMessage,
        now: datetime | None,
        lock_timeout: float | None,
    ) -> GenerationClaimResult:
        with self._connect(lock_timeout) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_time = self._utc_time(now)
            timestamp = current_time.isoformat()
            lease_expires_at = current_time + self._generation_lease
            inbound_message_id = self._get_or_create_inbound(
                connection,
                message,
                timestamp,
            )
            current = self._generation_result(
                connection,
                inbound_message_id,
                acquired=False,
            )
            if current.state in {GenerationState.COMPLETED, GenerationState.SUPPRESSED}:
                return current
            if current.state is GenerationState.PROCESSING:
                if current.lease_expires_at is not None and current.lease_expires_at > current_time:
                    return current
                if current.attempt_count >= self._maximum_generation_attempts:
                    connection.execute(
                        """
                        UPDATE message_processing
                        SET state = 'retryable',
                            owner_token = NULL,
                            lease_expires_at = NULL,
                            updated_at = ?
                        WHERE inbound_message_id = ?
                        """,
                        (timestamp, inbound_message_id),
                    )
                    return self._generation_result(
                        connection,
                        inbound_message_id,
                        acquired=False,
                    )
            predecessor = connection.execute(
                """
                SELECT predecessor.id
                FROM messages AS current
                JOIN messages AS predecessor
                  ON predecessor.conversation_id = current.conversation_id
                 AND predecessor.direction = 'inbound'
                 AND predecessor.id < current.id
                JOIN message_processing AS predecessor_processing
                  ON predecessor_processing.inbound_message_id = predecessor.id
                LEFT JOIN messages AS predecessor_reply
                  ON predecessor_reply.in_reply_to_message_id = predecessor.id
                 AND predecessor_reply.direction = 'outbound'
                LEFT JOIN outbound_deliveries AS predecessor_delivery
                  ON predecessor_delivery.outbound_message_id = predecessor_reply.id
                WHERE current.id = ?
                  AND (
                      predecessor_processing.state NOT IN ('completed', 'suppressed')
                      OR (
                          predecessor_processing.state = 'completed'
                          AND (
                              predecessor_delivery.id IS NULL
                              OR predecessor_delivery.state NOT IN (
                                  'accepted', 'sent', 'delivered', 'read',
                                  'accepted_legacy', 'cancelled'
                              )
                          )
                      )
                  )
                ORDER BY predecessor.id
                LIMIT 1
                """,
                (inbound_message_id,),
            ).fetchone()
            if predecessor is not None:
                return self._generation_result(
                    connection,
                    inbound_message_id,
                    acquired=False,
                    blocked_by_predecessor=True,
                )
            if current.attempt_count >= self._maximum_generation_attempts:
                return current

            owner_token = uuid4().hex
            connection.execute(
                """
                UPDATE message_processing
                SET state = 'processing',
                    owner_token = ?,
                    lease_expires_at = ?,
                    attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE inbound_message_id = ?
                """,
                (owner_token, lease_expires_at.isoformat(), timestamp, inbound_message_id),
            )
            return self._generation_result(
                connection,
                inbound_message_id,
                acquired=True,
                acquired_owner_token=owner_token,
            )

    def _complete_generation(
        self,
        *,
        inbound_message_id: int,
        owner_token: str,
        reply_body: str,
        delivery_state: DeliveryState,
        now: datetime | None,
        lock_timeout: float | None,
    ) -> bool:
        with self._connect(lock_timeout) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_time = self._utc_time(now)
            timestamp = current_time.isoformat()
            inbound = connection.execute(
                """
                SELECT
                    inbound.conversation_id,
                    inbound.provider,
                    inbound.recipient_address,
                    conversation.customer_address
                FROM messages AS inbound
                JOIN conversations AS conversation ON conversation.id = inbound.conversation_id
                WHERE inbound.id = ? AND inbound.direction = 'inbound'
                """,
                (inbound_message_id,),
            ).fetchone()
            if inbound is None:
                return False
            processing = connection.execute(
                """
                SELECT state, owner_token, lease_expires_at
                FROM message_processing
                WHERE inbound_message_id = ?
                """,
                (inbound_message_id,),
            ).fetchone()
            if (
                processing is None
                or processing[0] != GenerationState.PROCESSING
                or processing[1] != owner_token
                or processing[2] is None
                or datetime.fromisoformat(str(processing[2])) <= current_time
            ):
                return False

            conversation_id = int(inbound[0])
            outbound_message_id = int(
                connection.execute(
                    """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (?, ?, NULL, 'outbound', ?, ?, ?)
                RETURNING id
                """,
                    (conversation_id, str(inbound[1]), reply_body, timestamp, inbound_message_id),
                ).fetchone()[0]
            )
            self._insert_delivery(
                connection,
                outbound_message_id=outbound_message_id,
                provider=str(inbound[1]),
                provider_channel_id=str(inbound[2]),
                recipient_address=str(inbound[3]),
                delivery_state=delivery_state,
                timestamp=timestamp,
            )
            updated = connection.execute(
                """
                UPDATE message_processing
                SET state = 'completed',
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE inbound_message_id = ?
                  AND state = 'processing'
                  AND owner_token = ?
                  AND lease_expires_at > ?
                """,
                (timestamp, inbound_message_id, owner_token, timestamp),
            ).rowcount
            if updated != 1:
                raise sqlite3.IntegrityError("Generation ownership changed during completion")
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
        return True

    @staticmethod
    def _insert_delivery(
        connection: sqlite3.Connection,
        *,
        outbound_message_id: int,
        provider: str,
        provider_channel_id: str,
        recipient_address: str,
        delivery_state: DeliveryState,
        timestamp: str,
    ) -> int:
        if delivery_state not in {
            DeliveryState.PENDING,
            DeliveryState.UNKNOWN,
            DeliveryState.ACCEPTED_LEGACY,
        }:
            raise ValueError("Invalid initial Outbound Delivery state")
        next_attempt_at = timestamp if delivery_state is DeliveryState.PENDING else None
        safe_error_code = "legacy_unverified" if delivery_state is DeliveryState.UNKNOWN else None
        accepted_at = timestamp if delivery_state is DeliveryState.ACCEPTED_LEGACY else None
        return int(
            connection.execute(
                """
                INSERT INTO outbound_deliveries (
                    outbound_message_id,
                    provider,
                    provider_channel_id,
                    recipient_address,
                    state,
                    owner_token,
                    lease_expires_at,
                    attempt_count,
                    next_attempt_at,
                    provider_message_id,
                    safe_error_code,
                    accepted_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, 0, ?, NULL, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    outbound_message_id,
                    provider,
                    provider_channel_id,
                    recipient_address,
                    delivery_state,
                    next_attempt_at,
                    safe_error_code,
                    accepted_at,
                    timestamp,
                    timestamp,
                ),
            ).fetchone()[0]
        )

    @staticmethod
    def _expire_ambiguous_delivery_claims(
        connection: sqlite3.Connection,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            UPDATE delivery_attempts
            SET outcome = 'unknown',
                safe_error_code = 'sending_lease_expired',
                completed_at = ?
            WHERE outcome = 'started'
              AND EXISTS (
                  SELECT 1
                  FROM outbound_deliveries AS delivery
                  WHERE delivery.id = delivery_attempts.outbound_delivery_id
                    AND delivery.state = 'sending'
                    AND delivery.lease_expires_at <= ?
                    AND delivery.owner_token = delivery_attempts.owner_token
                    AND delivery.attempt_count = delivery_attempts.attempt_number
              )
            """,
            (timestamp, timestamp),
        )
        connection.execute(
            """
            UPDATE outbound_deliveries
            SET state = 'unknown',
                owner_token = NULL,
                lease_expires_at = NULL,
                next_attempt_at = NULL,
                safe_error_code = 'sending_lease_expired',
                updated_at = ?
            WHERE state = 'sending'
              AND lease_expires_at <= ?
            """,
            (timestamp, timestamp),
        )

    @staticmethod
    def _delivery_select() -> str:
        return """
            SELECT
                delivery.id,
                delivery.outbound_message_id,
                outbound.in_reply_to_message_id,
                delivery.provider,
                delivery.provider_channel_id,
                delivery.recipient_address,
                outbound.body,
                delivery.state,
                delivery.attempt_count,
                delivery.owner_token,
                delivery.lease_expires_at,
                delivery.next_attempt_at,
                delivery.provider_message_id,
                delivery.safe_error_code,
                delivery.accepted_at,
                delivery.created_at,
                delivery.updated_at
            FROM outbound_deliveries AS delivery
            JOIN messages AS outbound ON outbound.id = delivery.outbound_message_id
        """

    @staticmethod
    def _delivery_record(row: sqlite3.Row | tuple[object, ...]) -> OutboundDeliveryRecord:
        return OutboundDeliveryRecord(
            delivery_id=int(row[0]),
            outbound_message_id=int(row[1]),
            inbound_message_id=int(row[2]),
            provider=str(row[3]),
            provider_channel_id=str(row[4]),
            recipient_address=str(row[5]),
            body=str(row[6]),
            state=DeliveryState(str(row[7])),
            attempt_count=int(row[8]),
            owner_token=None if row[9] is None else str(row[9]),
            lease_expires_at=(None if row[10] is None else datetime.fromisoformat(str(row[10]))),
            next_attempt_at=(None if row[11] is None else datetime.fromisoformat(str(row[11]))),
            provider_message_id=None if row[12] is None else str(row[12]),
            safe_error_code=None if row[13] is None else str(row[13]),
            accepted_at=None if row[14] is None else datetime.fromisoformat(str(row[14])),
            created_at=datetime.fromisoformat(str(row[15])),
            updated_at=datetime.fromisoformat(str(row[16])),
        )

    def _claim_exhausted_finalization(
        self,
        *,
        inbound_message_id: int,
        now: datetime | None,
        lock_timeout: float | None,
    ) -> GenerationClaimResult:
        with self._connect(lock_timeout) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_time = self._utc_time(now)
            timestamp = current_time.isoformat()
            current = self._generation_result(
                connection,
                inbound_message_id,
                acquired=False,
            )
            if current.state in {GenerationState.COMPLETED, GenerationState.SUPPRESSED}:
                return current
            if current.attempt_count < self._maximum_generation_attempts:
                return current
            if (
                current.state is GenerationState.PROCESSING
                and current.lease_expires_at is not None
                and current.lease_expires_at > current_time
            ):
                return current

            owner_token = uuid4().hex
            lease_expires_at = current_time + self._generation_lease
            updated = connection.execute(
                """
                UPDATE message_processing
                SET state = 'processing',
                    owner_token = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE inbound_message_id = ?
                  AND attempt_count = 2
                  AND (
                    (state = 'retryable' AND owner_token IS NULL AND lease_expires_at IS NULL)
                    OR
                    (state = 'processing' AND lease_expires_at <= ?)
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM messages AS current_message
                      JOIN messages AS predecessor
                        ON predecessor.conversation_id = current_message.conversation_id
                       AND predecessor.direction = 'inbound'
                       AND predecessor.id < current_message.id
                      JOIN message_processing AS predecessor_processing
                        ON predecessor_processing.inbound_message_id = predecessor.id
                      LEFT JOIN messages AS predecessor_reply
                        ON predecessor_reply.in_reply_to_message_id = predecessor.id
                       AND predecessor_reply.direction = 'outbound'
                      LEFT JOIN outbound_deliveries AS predecessor_delivery
                        ON predecessor_delivery.outbound_message_id = predecessor_reply.id
                      WHERE current_message.id = message_processing.inbound_message_id
                        AND (
                            predecessor_processing.state NOT IN ('completed', 'suppressed')
                            OR (
                                predecessor_processing.state = 'completed'
                                AND (
                                    predecessor_delivery.id IS NULL
                                    OR predecessor_delivery.state NOT IN (
                                        'accepted', 'sent', 'delivered', 'read',
                                        'accepted_legacy', 'cancelled'
                                    )
                                )
                            )
                        )
                  )
                """,
                (
                    owner_token,
                    lease_expires_at.isoformat(),
                    timestamp,
                    inbound_message_id,
                    timestamp,
                ),
            ).rowcount
            if updated != 1:
                return self._generation_result(
                    connection,
                    inbound_message_id,
                    acquired=False,
                    blocked_by_predecessor=True,
                )
            return self._generation_result(
                connection,
                inbound_message_id,
                acquired=True,
                acquired_owner_token=owner_token,
            )

    def _get_or_create_inbound(
        self,
        connection: sqlite3.Connection,
        message: InboundMessage,
        timestamp: str,
    ) -> int:
        existing = connection.execute(
            """
            SELECT id
            FROM messages
            WHERE provider = ?
              AND provider_message_id = ?
              AND direction = 'inbound'
            """,
            (message.provider, message.provider_message_id),
        ).fetchone()
        if existing is not None:
            return int(existing[0])

        connection.execute(
            """
            INSERT INTO conversations (
                provider, customer_address, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, customer_address)
            DO NOTHING
            """,
            (message.provider, message.customer_address, timestamp, timestamp),
        )
        conversation_id = int(
            connection.execute(
                """
                SELECT id FROM conversations
                WHERE provider = ? AND customer_address = ?
                """,
                (message.provider, message.customer_address),
            ).fetchone()[0]
        )
        inbound_message_id = int(
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id, recipient_address,
                    direction, body, created_at
                ) VALUES (?, ?, ?, ?, 'inbound', ?, ?)
                RETURNING id
                """,
                (
                    conversation_id,
                    message.provider,
                    message.provider_message_id,
                    message.recipient_address,
                    message.body,
                    timestamp,
                ),
            ).fetchone()[0]
        )
        connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (timestamp, conversation_id),
        )
        return inbound_message_id

    def _generation_result(
        self,
        connection: sqlite3.Connection,
        inbound_message_id: int,
        *,
        acquired: bool,
        acquired_owner_token: str | None = None,
        blocked_by_predecessor: bool = False,
    ) -> GenerationClaimResult:
        row = connection.execute(
            """
            SELECT
                processing.state,
                processing.attempt_count,
                processing.lease_expires_at,
                outbound.body,
                inbound.body
            FROM message_processing AS processing
            JOIN messages AS inbound
              ON inbound.id = processing.inbound_message_id
            LEFT JOIN messages AS outbound
              ON outbound.in_reply_to_message_id = processing.inbound_message_id
             AND outbound.direction = 'outbound'
            WHERE processing.inbound_message_id = ?
            """,
            (inbound_message_id,),
        ).fetchone()
        if row is None:
            raise sqlite3.IntegrityError("Inbound Message has no processing lifecycle")
        lease_expires_at = None if row[2] is None else datetime.fromisoformat(str(row[2]))
        return GenerationClaimResult(
            acquired=acquired,
            inbound_message_id=inbound_message_id,
            state=GenerationState(str(row[0])),
            attempt_count=int(row[1]),
            owner_token=acquired_owner_token if acquired else None,
            lease_expires_at=lease_expires_at,
            reply_body=None if row[3] is None else str(row[3]),
            inbound_body=str(row[4]),
            blocked_by_predecessor=blocked_by_predecessor,
        )

    @staticmethod
    def _utc_time(value: datetime | None) -> datetime:
        resolved = value or datetime.now(UTC)
        if resolved.utcoffset() is None:
            raise ValueError("Generation time must include a timezone")
        return resolved.astimezone(UTC)

    def get_history(
        self,
        *,
        provider: str,
        customer_address: str,
    ) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT messages.direction, messages.body
                FROM messages
                JOIN conversations ON conversations.id = messages.conversation_id
                WHERE conversations.provider = ?
                  AND conversations.customer_address = ?
                ORDER BY messages.id
                """,
                (provider, customer_address),
            ).fetchall()
        return [MessageRecord(direction=row[0], body=row[1]) for row in rows]

    def load_recent_context_history(
        self,
        *,
        inbound_message_id: int,
        maximum_age: timedelta,
        maximum_messages: int,
        lock_timeout: float | None = None,
    ) -> RecentContextHistory:
        """Return bounded canonical prior turns in logical Conversation order."""
        if maximum_age <= timedelta():
            raise ValueError("Conversation context age must be positive")
        if maximum_messages < 1:
            raise ValueError("Conversation context Message limit must be positive")
        try:
            with self._connect(lock_timeout) as connection:
                current = connection.execute(
                    """
                    SELECT conversation_id, created_at
                    FROM messages
                    WHERE id = ? AND direction = 'inbound'
                    """,
                    (inbound_message_id,),
                ).fetchone()
                if current is None:
                    raise sqlite3.IntegrityError("Current inbound Message is unavailable")
                cutoff = datetime.fromisoformat(str(current[1])) - maximum_age
                rows = connection.execute(
                    """
                    SELECT candidate.direction, candidate.body, candidate.created_at
                    FROM messages AS candidate
                    WHERE candidate.conversation_id = ?
                      AND candidate.created_at >= ?
                      AND (
                            (candidate.direction = 'inbound' AND candidate.id < ?)
                         OR (candidate.direction = 'outbound'
                             AND candidate.in_reply_to_message_id < ?)
                      )
                      AND (
                            candidate.direction = 'inbound'
                         OR EXISTS (
                                SELECT 1
                                FROM outbound_deliveries AS delivery
                                WHERE delivery.outbound_message_id = candidate.id
                                  AND delivery.state IN (
                                      'accepted', 'sent', 'delivered', 'read',
                                      'accepted_legacy'
                                  )
                            )
                      )
                    ORDER BY
                        CASE
                            WHEN candidate.direction = 'inbound' THEN candidate.id
                            ELSE candidate.in_reply_to_message_id
                        END DESC,
                        CASE candidate.direction WHEN 'outbound' THEN 1 ELSE 0 END DESC
                    LIMIT ?
                    """,
                    (
                        int(current[0]),
                        cutoff.isoformat(),
                        inbound_message_id,
                        inbound_message_id,
                        maximum_messages + 1,
                    ),
                ).fetchall()
                older_message_exists = connection.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM messages AS candidate
                        WHERE candidate.conversation_id = ?
                          AND candidate.created_at < ?
                          AND (
                                (candidate.direction = 'inbound' AND candidate.id < ?)
                             OR (candidate.direction = 'outbound'
                                 AND candidate.in_reply_to_message_id < ?)
                          )
                          AND (
                                candidate.direction = 'inbound'
                             OR EXISTS (
                                    SELECT 1
                                    FROM outbound_deliveries AS delivery
                                    WHERE delivery.outbound_message_id = candidate.id
                                      AND delivery.state IN (
                                          'accepted', 'sent', 'delivered', 'read',
                                          'accepted_legacy'
                                      )
                                )
                          )
                    )
                    """,
                    (
                        int(current[0]),
                        cutoff.isoformat(),
                        inbound_message_id,
                        inbound_message_id,
                    ),
                ).fetchone()
        except (sqlite3.Error, ValueError) as error:
            raise PersistenceUnavailable(
                "Conversation context persistence is unavailable"
            ) from error
        has_omitted_messages = len(rows) > maximum_messages or bool(older_message_exists[0])
        history: list[MessageRecord] = []
        try:
            for direction, body, created_at in reversed(rows[:maximum_messages]):
                timestamp = datetime.fromisoformat(str(created_at))
                if timestamp.utcoffset() is None:
                    raise ValueError("Stored timestamp has no timezone")
                history.append(MessageRecord(direction=str(direction), body=str(body)))
        except ValueError as error:
            raise PersistenceUnavailable(
                "Conversation context has an invalid Message timestamp"
            ) from error
        return RecentContextHistory(
            records=tuple(history),
            has_omitted_messages=has_omitted_messages,
        )

    @contextmanager
    def _connect(
        self,
        timeout_seconds: float | None = None,
    ) -> Iterator[sqlite3.Connection]:
        require_file_backed_database(self._database_path)
        timeout = (
            self._busy_timeout_seconds
            if timeout_seconds is None
            else min(self._busy_timeout_seconds, max(0.0, timeout_seconds))
        )
        connection = sqlite3.connect(self._database_path, timeout=timeout)
        try:
            configure_sqlite_connection(
                connection,
                busy_timeout_seconds=timeout,
                set_journal_mode=False,
            )
        except Exception:
            connection.close()
            raise
        try:
            with connection:
                yield connection
        finally:
            connection.close()
