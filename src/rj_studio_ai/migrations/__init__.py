import sqlite3
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


class MigrationManager:
    """Apply and inspect this package's Alembic migrations."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._config = Config()
        self._config.set_main_option("script_location", str(Path(__file__).parent))

    def upgrade(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._engine().connect() as connection:
            self._config.attributes["connection"] = connection
            command.upgrade(self._config, "head")

    def is_current(self) -> bool:
        if not self._database_path.is_file():
            return False
        try:
            with self._engine().connect() as connection:
                current = MigrationContext.configure(connection).get_current_revision()
                inspector = inspect(connection)
                schema_matches = self._schema_matches(connection, inspector)
            expected = ScriptDirectory.from_config(self._config).get_current_head()
        except SQLAlchemyError:
            return False
        return current == expected and schema_matches

    @staticmethod
    def _schema_matches(connection: Connection, inspector: Inspector) -> bool:
        if not {"alembic_version", "conversations", "messages", "message_processing"}.issubset(
            inspector.get_table_names()
        ):
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
        )

    def _engine(self) -> Engine:
        url = URL.create("sqlite+pysqlite", database=str(self._database_path.absolute()))
        engine = create_engine(url)
        event.listen(engine, "connect", _disable_legacy_transaction_control)
        event.listen(engine, "begin", _begin_transaction)
        return engine


def _disable_legacy_transaction_control(
    connection: DBAPIConnection,
    _: object,
) -> None:
    if isinstance(connection, sqlite3.Connection):
        connection.isolation_level = None


def _begin_transaction(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")
