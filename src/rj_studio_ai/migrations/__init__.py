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
                schema_matches = self._schema_matches(inspector)
            expected = ScriptDirectory.from_config(self._config).get_current_head()
        except SQLAlchemyError:
            return False
        return current == expected and schema_matches

    @staticmethod
    def _schema_matches(inspector: Inspector) -> bool:
        if not {"alembic_version", "conversations", "messages"}.issubset(
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
        return (
            frozenset({"provider", "customer_address"}) in conversation_uniques
            and frozenset({"provider", "provider_message_id"}) in message_uniques
            and reply_indexes.get("uq_messages_in_reply_to") == (("in_reply_to_message_id",), True)
            and (("conversation_id",), "conversations", ("id",)) in message_foreign_keys
            and (("in_reply_to_message_id",), "messages", ("id",)) in message_foreign_keys
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
