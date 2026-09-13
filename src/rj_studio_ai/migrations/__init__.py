from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, Engine
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
                message_columns = {column["name"] for column in inspector.get_columns("messages")}
                reply_indexes = {
                    index["name"]: bool(index["unique"])
                    for index in inspector.get_indexes("messages")
                }
            expected = ScriptDirectory.from_config(self._config).get_current_head()
        except SQLAlchemyError:
            return False
        return (
            current == expected
            and "in_reply_to_message_id" in message_columns
            and reply_indexes.get("uq_messages_in_reply_to") is True
        )

    def _engine(self) -> Engine:
        url = URL.create("sqlite+pysqlite", database=str(self._database_path.absolute()))
        return create_engine(url)
