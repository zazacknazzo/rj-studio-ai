import sqlite3
from functools import partial
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError

from rj_studio_ai.sqlite import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    SqliteDurabilityError,
    SqliteDurabilityState,
    configure_sqlite_connection,
    inspect_sqlite_connection,
    require_file_backed_database,
)


class MigrationManager:
    """Apply and inspect this package's Alembic migrations."""

    def __init__(
        self,
        database_path: Path,
        *,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
    ) -> None:
        self._database_path = database_path
        self._busy_timeout_seconds = busy_timeout_seconds
        self._config = Config()
        self._config.set_main_option("script_location", str(Path(__file__).parent))

    def upgrade(self) -> None:
        require_file_backed_database(self._database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = self._engine(set_journal_mode=True)
        try:
            with engine.connect() as connection:
                self._config.attributes["connection"] = connection
                command.upgrade(self._config, "head")
        finally:
            self._config.attributes.pop("connection", None)
            engine.dispose()

    def is_current(self) -> bool:
        if not self._database_path.is_file():
            return False
        engine = self._engine(set_journal_mode=False)
        try:
            with engine.connect() as connection:
                current = MigrationContext.configure(connection).get_current_revision()
                inspector = inspect(connection)
                schema_matches = self._schema_matches(connection, inspector)
            expected = ScriptDirectory.from_config(self._config).get_current_head()
        except (SQLAlchemyError, SqliteDurabilityError):
            return False
        finally:
            engine.dispose()
        return current == expected and schema_matches

    def connection_durability_state(self) -> SqliteDurabilityState:
        require_file_backed_database(self._database_path)
        engine = self._engine(set_journal_mode=False)
        try:
            with engine.connect() as connection:
                raw_connection = connection.connection.driver_connection
                if not isinstance(raw_connection, sqlite3.Connection):
                    raise SqliteDurabilityError("Migration connection is not SQLite")
                return inspect_sqlite_connection(raw_connection)
        finally:
            engine.dispose()

    @staticmethod
    def _schema_matches(connection: Connection, inspector: Inspector) -> bool:
        if not {
            "alembic_version",
            "conversations",
            "messages",
            "message_processing",
            "generation_metrics",
            "outbound_deliveries",
            "delivery_attempts",
        }.issubset(inspector.get_table_names()):
            return False
        required_columns = {
            "conversations": {
                "id",
                "provider",
                "customer_address",
                "created_at",
                "updated_at",
            },
            "messages": {
                "id",
                "conversation_id",
                "provider",
                "provider_message_id",
                "recipient_address",
                "direction",
                "body",
                "created_at",
                "in_reply_to_message_id",
            },
            "message_processing": {
                "inbound_message_id",
                "state",
                "owner_token",
                "lease_expires_at",
                "attempt_count",
                "created_at",
                "updated_at",
            },
            "generation_metrics": {
                "id",
                "inbound_message_id",
                "attempt_number",
                "provider",
                "model",
                "configuration",
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "estimated_cost_microusd",
                "outcome",
                "error_code",
                "created_at",
            },
            "outbound_deliveries": {
                "id",
                "outbound_message_id",
                "provider",
                "provider_channel_id",
                "recipient_address",
                "state",
                "owner_token",
                "lease_expires_at",
                "attempt_count",
                "next_attempt_at",
                "provider_message_id",
                "safe_error_code",
                "accepted_at",
                "created_at",
                "updated_at",
            },
            "delivery_attempts": {
                "id",
                "outbound_delivery_id",
                "attempt_number",
                "owner_token",
                "outcome",
                "provider_message_id",
                "safe_error_code",
                "started_at",
                "completed_at",
            },
        }
        for table, required in required_columns.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            if not required.issubset(actual):
                return False

        conversation_uniques = {
            frozenset(item["column_names"])
            for item in inspector.get_unique_constraints("conversations")
        }
        message_uniques = {
            frozenset(item["column_names"]) for item in inspector.get_unique_constraints("messages")
        }
        reply_indexes = {
            item["name"]: (tuple(item["column_names"]), bool(item["unique"]))
            for item in inspector.get_indexes("messages")
        }
        message_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("messages")
        }
        processing_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("message_processing")
        }
        processing_checks = {
            item["name"] for item in inspector.get_check_constraints("message_processing")
        }
        metric_uniques = {
            frozenset(item["column_names"])
            for item in inspector.get_unique_constraints("generation_metrics")
        }
        metric_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("generation_metrics")
        }
        metric_checks = {
            item["name"] for item in inspector.get_check_constraints("generation_metrics")
        }
        delivery_uniques = {
            frozenset(item["column_names"])
            for item in inspector.get_unique_constraints("outbound_deliveries")
        }
        delivery_indexes = {
            item["name"]: (tuple(item["column_names"]), bool(item["unique"]))
            for item in inspector.get_indexes("outbound_deliveries")
        }
        delivery_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("outbound_deliveries")
        }
        delivery_checks = {
            item["name"] for item in inspector.get_check_constraints("outbound_deliveries")
        }
        attempt_uniques = {
            frozenset(item["column_names"])
            for item in inspector.get_unique_constraints("delivery_attempts")
        }
        attempt_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("delivery_attempts")
        }
        attempt_checks = {
            item["name"] for item in inspector.get_check_constraints("delivery_attempts")
        }
        processing_triggers = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        return (
            frozenset({"provider", "customer_address"}) in conversation_uniques
            and frozenset({"provider", "provider_message_id"}) in message_uniques
            and reply_indexes.get("uq_messages_in_reply_to") == (("in_reply_to_message_id",), True)
            and reply_indexes.get("ix_messages_conversation_created")
            == (("conversation_id", "created_at", "id"), False)
            and reply_indexes.get("ix_messages_conversation_direction_id")
            == (("conversation_id", "direction", "id"), False)
            and (("conversation_id",), "conversations", ("id",)) in message_foreign_keys
            and (("in_reply_to_message_id",), "messages", ("id",)) in message_foreign_keys
            and (("inbound_message_id",), "messages", ("id",)) in processing_foreign_keys
            and {
                "ck_message_processing_state",
                "ck_message_processing_attempt_count",
                "ck_message_processing_claim_shape",
                "ck_message_processing_suppressed_attempts",
            }.issubset(processing_checks)
            and {
                "message_processing_requires_inbound_insert",
                "message_processing_requires_inbound_update",
                "completed_processing_requires_reply_insert",
                "completed_processing_requires_reply_update",
                "suppressed_processing_rejects_reply_insert",
                "suppressed_processing_rejects_reply_update",
                "suppressed_processing_rejects_existing_reply_insert",
                "suppressed_processing_rejects_existing_reply_update",
                "terminal_processing_state_is_immutable",
                "completed_processing_protects_reply_delete",
                "completed_processing_protects_reply_update",
                "create_processing_for_inbound_message",
            }.issubset(processing_triggers)
            and frozenset({"inbound_message_id", "attempt_number"}) in metric_uniques
            and (("inbound_message_id",), "messages", ("id",)) in metric_foreign_keys
            and {
                "ck_generation_metrics_attempt",
                "ck_generation_metrics_latency",
                "ck_generation_metrics_outcome",
                "ck_generation_metrics_error_shape",
            }.issubset(metric_checks)
            and frozenset({"outbound_message_id"}) in delivery_uniques
            and delivery_indexes.get("uq_outbound_deliveries_provider_message")
            == (("provider", "provider_message_id"), True)
            and delivery_indexes.get("ix_outbound_deliveries_due")
            == (("state", "next_attempt_at", "id"), False)
            and delivery_indexes.get("ix_outbound_deliveries_stale")
            == (("state", "lease_expires_at", "id"), False)
            and (("outbound_message_id",), "messages", ("id",)) in delivery_foreign_keys
            and {
                "ck_outbound_deliveries_state",
                "ck_outbound_deliveries_attempt_count",
                "ck_outbound_deliveries_claim_shape",
                "ck_outbound_deliveries_schedule_shape",
                "ck_outbound_deliveries_provider_id_shape",
                "ck_outbound_deliveries_acceptance_shape",
                "ck_outbound_deliveries_error_shape",
            }.issubset(delivery_checks)
            and frozenset({"outbound_delivery_id", "attempt_number"}) in attempt_uniques
            and (("outbound_delivery_id",), "outbound_deliveries", ("id",)) in attempt_foreign_keys
            and {
                "ck_delivery_attempts_attempt_number",
                "ck_delivery_attempts_owner_token",
                "ck_delivery_attempts_outcome",
                "ck_delivery_attempts_completion_shape",
                "ck_delivery_attempts_evidence_shape",
            }.issubset(attempt_checks)
            and {
                "outbound_delivery_requires_ai_reply_insert",
                "outbound_delivery_requires_ai_reply_update",
                "outbound_delivery_protects_message_identity",
                "completed_processing_requires_delivery_insert",
                "completed_processing_requires_delivery_update",
                "completed_processing_protects_delivery_delete",
                "outbound_delivery_identity_is_immutable",
                "outbound_delivery_acceptance_evidence_is_immutable",
                "outbound_delivery_state_transition",
                "delivery_attempt_requires_current_claim",
                "delivery_attempt_finalization_requires_current_claim",
                "delivery_attempt_identity_is_immutable",
                "terminal_delivery_attempt_is_immutable",
            }.issubset(processing_triggers)
        )

    def _engine(self, *, set_journal_mode: bool) -> Engine:
        url = URL.create("sqlite+pysqlite", database=str(self._database_path.absolute()))
        engine = create_engine(
            url,
            connect_args={"timeout": self._busy_timeout_seconds},
        )
        event.listen(
            engine,
            "connect",
            partial(
                _configure_migration_connection,
                busy_timeout_seconds=self._busy_timeout_seconds,
                set_journal_mode=set_journal_mode,
            ),
        )
        event.listen(engine, "begin", _begin_transaction)
        return engine


def _configure_migration_connection(
    connection: DBAPIConnection,
    _: object,
    *,
    busy_timeout_seconds: float,
    set_journal_mode: bool,
) -> None:
    if isinstance(connection, sqlite3.Connection):
        connection.isolation_level = None
        configure_sqlite_connection(
            connection,
            busy_timeout_seconds=busy_timeout_seconds,
            set_journal_mode=set_journal_mode,
        )


def _begin_transaction(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")
