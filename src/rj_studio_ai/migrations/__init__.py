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
            "pending_delivery_statuses",
            "conversation_handoffs",
            "appointment_intakes",
            "inbound_event_receipts",
            "operational_events",
            "operational_event_aliases",
            "conversation_automation_controls",
            "human_pause_effects",
            "conversation_operation_ids",
            "automation_operation_receipts",
        }.issubset(inspector.get_table_names()):
            return False
        if not MigrationManager._operations_schema_matches(connection, inspector):
            return False
        if not MigrationManager._pause_schema_matches(inspector):
            return False
        if not MigrationManager._operational_schema_matches(inspector):
            return False
        inbound_columns = {item["name"] for item in inspector.get_columns("inbound_event_receipts")}
        if not {
            "id",
            "provider",
            "channel_id",
            "customer_address",
            "event_id",
            "provider_message_id",
            "occurred_at",
            "received_at",
            "aliases_json",
            "message_occurred_at",
        }.issubset(inbound_columns):
            return False
        inbound_indexes = {
            item["name"]: item for item in inspector.get_indexes("inbound_event_receipts")
        }
        for name, columns, unique in (
            ("uq_inbound_event_scope", ["provider", "channel_id", "event_id"], True),
            ("ix_inbound_event_message", ["provider", "provider_message_id"], False),
        ):
            index = inbound_indexes.get(name)
            if index is None or index["column_names"] != columns or bool(index["unique"]) != unique:
                return False
        required_columns = {
            "appointment_intakes": {
                "preferred_day",
                "request_kind",
                "recovery_offered",
                "conversation_id",
                "episode_token",
                "state",
                "desired_service",
                "preferred_time",
                "professional_preference",
                "clarification_count",
                "awaiting_field",
                "last_inbound_message_id",
                "handoff_token",
                "updated_at",
            },
            "conversation_handoffs": {
                "conversation_id",
                "active",
                "owner_token",
                "reason_code",
                "activated_at",
                "released_at",
            },
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
                "automation_revision",
                "inbound_message_id",
                "state",
                "owner_token",
                "lease_expires_at",
                "attempt_count",
                "created_at",
                "updated_at",
            },
            "generation_metrics": {
                "cached_input_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
                "response_status",
                "incomplete_reason",
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
                "handoff_token",
                "submission_started_at",
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
            "pending_delivery_statuses": {
                "id",
                "provider",
                "provider_message_id",
                "status",
                "safe_error_code",
                "received_at",
                "updated_at",
            },
        }
        for table, required in required_columns.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            if not required.issubset(actual):
                return False

        handoff_checks = {
            item["name"] for item in inspector.get_check_constraints("conversation_handoffs")
        }
        handoff_indexes = {
            item["name"]: (tuple(item["column_names"]), bool(item["unique"]))
            for item in inspector.get_indexes("conversation_handoffs")
        }
        handoff_foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
            )
            for item in inspector.get_foreign_keys("conversation_handoffs")
        }
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
        pending_status_uniques = {
            frozenset(item["column_names"])
            for item in inspector.get_unique_constraints("pending_delivery_statuses")
        }
        pending_status_checks = {
            item["name"] for item in inspector.get_check_constraints("pending_delivery_statuses")
        }
        processing_triggers = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        return (
            inspector.get_pk_constraint("appointment_intakes")["constrained_columns"]
            == ["conversation_id"]
            and {
                "ck_intake_preferred_day",
                "ck_intake_request_kind",
                "ck_intake_recovery",
                "ck_intake_state",
                "ck_intake_questions",
                "ck_intake_episode",
                "ck_intake_lifecycle",
                "ck_intake_desired_service",
                "ck_intake_preferred_time",
                "ck_intake_professional_preference",
            }.issubset(
                {item["name"] for item in inspector.get_check_constraints("appointment_intakes")}
            )
            and any(
                item["constrained_columns"] == ["conversation_id"]
                and item["referred_table"] == "conversations"
                and item["referred_columns"] == ["id"]
                and item["options"].get("ondelete") == "CASCADE"
                for item in inspector.get_foreign_keys("appointment_intakes")
            )
            and {
                "operational_pause_cancels_outbound_insert",
                "operational_pause_cancels_outbound_update",
                "operational_pause_cancels_ready_delivery_insert",
                "operational_pause_cancels_ready_delivery_update",
                "operational_pause_rejects_delivery_authorization",
                "operational_pause_suppresses_insert",
                "operational_pause_suppresses_update",
                "operational_pause_rejects_reply_insert",
                "operational_pause_rejects_reply_update",
                "operational_pause_rejects_claim_insert",
                "operational_pause_rejects_claim_update",
                "operational_pause_suppresses_admission",
                "ai_reply_rejects_active_handoff",
                "processing_rejects_active_handoff",
                "submission_evidence_is_immutable",
            }.issubset(processing_triggers)
            and inspector.get_pk_constraint("conversation_handoffs")["constrained_columns"]
            == ["conversation_id"]
            and (("conversation_id",), "conversations", ("id",)) in handoff_foreign_keys
            and {
                "ck_handoff_active",
                "ck_handoff_reason_owner",
                "ck_handoff_release_shape",
            }.issubset(handoff_checks)
            and handoff_indexes.get("ix_handoffs_active") == (("active", "conversation_id"), False)
            and delivery_indexes.get("uq_delivery_handoff_confirmation")
            == (("handoff_token",), True)
            and frozenset({"provider", "customer_address"}) in conversation_uniques
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
                "ck_processing_automation_revision",
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
            and frozenset({"provider", "provider_message_id"}) in pending_status_uniques
            and {
                "ck_pending_delivery_status_state",
                "ck_pending_delivery_status_error_shape",
            }.issubset(pending_status_checks)
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

    @staticmethod
    def _operations_schema_matches(connection: Connection, inspector: Inspector) -> bool:
        structures = {
            "conversation_operation_ids": ({"conversation_id", "opaque_id"}, "CASCADE"),
            "automation_operation_receipts": (
                {
                    "operation_id",
                    "conversation_id",
                    "operator_id",
                    "action",
                    "expected_revision",
                    "result_json",
                    "created_at",
                },
                "RESTRICT",
            ),
        }
        for table, (columns, deletion) in structures.items():
            if not columns.issubset({c["name"] for c in inspector.get_columns(table)}):
                return False
            if not any(
                f["constrained_columns"] == ["conversation_id"]
                and f["referred_table"] == "conversations"
                and f["options"].get("ondelete") == deletion
                for f in inspector.get_foreign_keys(table)
            ):
                return False
        for table, check in (
            ("conversation_operation_ids", "ck_operation_identity"),
            ("automation_operation_receipts", "ck_operation_receipt"),
        ):
            if check not in {c["name"] for c in inspector.get_check_constraints(table)}:
                return False
        if inspector.get_pk_constraint("automation_operation_receipts")["constrained_columns"] != [
            "operation_id"
        ]:
            return False
        if not any(
            u["column_names"] == ["opaque_id"]
            for u in inspector.get_unique_constraints("conversation_operation_ids")
        ):
            return False
        triggers = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        return {
            "conversation_operation_identity",
            "conversation_operation_identity_immutable",
            "automation_receipt_immutable",
        }.issubset(triggers) and "resumed_at" in {
            c["name"] for c in inspector.get_columns("conversation_automation_controls")
        }

    @staticmethod
    def _pause_schema_matches(inspector: Inspector) -> bool:
        for table, columns, check in (
            (
                "conversation_automation_controls",
                {"conversation_id", "channel_id", "paused", "revision", "updated_at"},
                "ck_automation_control",
            ),
            (
                "human_pause_effects",
                {
                    "event_record_id",
                    "conversation_id",
                    "provider",
                    "channel_id",
                    "customer_address",
                    "provider_message_id",
                    "applied_at",
                    "revision",
                },
                "ck_human_pause_revision",
            ),
        ):
            if not columns.issubset({item["name"] for item in inspector.get_columns(table)}):
                return False
            if check not in {item["name"] for item in inspector.get_check_constraints(table)}:
                return False
            if not any(
                item["constrained_columns"] == ["conversation_id"]
                and item["referred_table"] == "conversations"
                and item["options"].get("ondelete") == "RESTRICT"
                for item in inspector.get_foreign_keys(table)
            ):
                return False
        return any(
            item["name"] == "uq_human_pause_message"
            and item["unique"]
            and item["column_names"]
            == ["provider", "channel_id", "customer_address", "provider_message_id"]
            for item in inspector.get_indexes("human_pause_effects")
        )

    @staticmethod
    def _operational_schema_matches(inspector: Inspector) -> bool:
        required_columns = {
            "operational_events": {
                "id",
                "provider",
                "scope_kind",
                "scope_id",
                "event_id",
                "kind",
                "origin",
                "occurred_at",
                "received_at",
                "provider_message_id",
                "customer_address",
                "message_occurred_at",
                "original_namespace",
                "original_message_id",
                "availability",
                "reason",
            },
            "operational_event_aliases": {"event_record_id", "namespace", "message_id"},
        }
        required_indexes = {
            "operational_events": {
                "uq_operational_event_scope": (
                    ("provider", "scope_kind", "scope_id", "event_id"),
                    True,
                ),
                "ix_operational_message": (
                    ("provider", "scope_kind", "scope_id", "provider_message_id"),
                    False,
                ),
            },
            "operational_event_aliases": {
                "uq_operational_alias": (("event_record_id", "namespace", "message_id"), True),
                "ix_operational_alias_reference": (("namespace", "message_id"), False),
            },
        }
        for table, columns in required_columns.items():
            if not columns.issubset({item["name"] for item in inspector.get_columns(table)}):
                return False
            indexes = {
                item["name"]: (tuple(item["column_names"]), bool(item["unique"]))
                for item in inspector.get_indexes(table)
            }
            if any(indexes.get(name) != shape for name, shape in required_indexes[table].items()):
                return False
        checks = {item["name"] for item in inspector.get_check_constraints("operational_events")}
        alias_checks = {
            item["name"] for item in inspector.get_check_constraints("operational_event_aliases")
        }
        return (
            {"ck_operational_identity", "ck_operational_scope", "ck_operational_shape"}.issubset(
                checks
            )
            and "ck_operational_alias_identity" in alias_checks
            and any(
                item["constrained_columns"] == ["event_record_id"]
                and item["referred_table"] == "operational_events"
                and item["referred_columns"] == ["id"]
                and item.get("options", {}).get("ondelete") == "CASCADE"
                for item in inspector.get_foreign_keys("operational_event_aliases")
            )
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
