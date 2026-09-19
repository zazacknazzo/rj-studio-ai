import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from rj_studio_ai.domain import InboundMessage, MessageRecord
from rj_studio_ai.generation import GenerationMetric
from rj_studio_ai.migrations import MigrationManager


class PersistenceUnavailable(RuntimeError):
    """Raised when SQLite cannot complete a persistence operation."""


class GenerationState(StrEnum):
    PROCESSING = "processing"
    RETRYABLE = "retryable"
    COMPLETED = "completed"
    SUPPRESSED = "suppressed"


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


class SqliteConversationStore:
    _generation_lease = timedelta(seconds=30)
    _maximum_generation_attempts = 2

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._migrations = MigrationManager(database_path)

    def initialize(self) -> None:
        self._migrations.upgrade()

    def migrations_are_current(self) -> bool:
        return self._migrations.is_current()

    def is_writable(self) -> bool:
        if not self._database_path.is_file():
            return False
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE alembic_version SET version_num = version_num")
                connection.rollback()
        except sqlite3.Error:
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
                now=now,
                lock_timeout=lock_timeout,
            )
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

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
                messages_deleted = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (conversation_id,),
                    ).fetchone()[0]
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

            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (?, ?, NULL, 'outbound', ?, ?, ?)
                """,
                (
                    conversation_id,
                    message.provider,
                    reply_body,
                    timestamp,
                    inbound_message_id,
                ),
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
                WHERE current.id = ?
                  AND predecessor_processing.state NOT IN ('completed', 'suppressed')
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
        now: datetime | None,
        lock_timeout: float | None,
    ) -> bool:
        with self._connect(lock_timeout) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_time = self._utc_time(now)
            timestamp = current_time.isoformat()
            inbound = connection.execute(
                """
                SELECT conversation_id, provider
                FROM messages
                WHERE id = ? AND direction = 'inbound'
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
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (?, ?, NULL, 'outbound', ?, ?, ?)
                """,
                (conversation_id, str(inbound[1]), reply_body, timestamp, inbound_message_id),
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
                raise sqlite3.IntegrityError("Exhausted generation state changed during claim")
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
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at
                ) VALUES (?, ?, ?, 'inbound', ?, ?)
                RETURNING id
                """,
                (
                    conversation_id,
                    message.provider,
                    message.provider_message_id,
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

    def _connect(self, timeout_seconds: float | None = None) -> sqlite3.Connection:
        timeout = 5.0 if timeout_seconds is None else max(0.0, timeout_seconds)
        connection = sqlite3.connect(self._database_path, timeout=timeout)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
