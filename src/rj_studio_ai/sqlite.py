import sqlite3
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
SQLITE_SYNCHRONOUS_FULL = 2


class SqliteDurabilityError(sqlite3.DatabaseError):
    """Raised when SQLite cannot satisfy the required durability policy."""


@dataclass(frozen=True, slots=True)
class SqliteDurabilityState:
    journal_mode: str
    synchronous: int
    foreign_keys: int
    busy_timeout_ms: int

    def readiness_checks(self, *, expected_busy_timeout_ms: int) -> dict[str, str]:
        return {
            "sqlite_journal_mode": "ok" if self.journal_mode == "wal" else "failed",
            "sqlite_synchronous": (
                "ok" if self.synchronous == SQLITE_SYNCHRONOUS_FULL else "failed"
            ),
            "sqlite_foreign_keys": "ok" if self.foreign_keys == 1 else "failed",
            "sqlite_busy_timeout": (
                "ok" if self.busy_timeout_ms == expected_busy_timeout_ms else "failed"
            ),
        }


def busy_timeout_milliseconds(seconds: float) -> int:
    if not isfinite(seconds) or seconds < 0:
        raise SqliteDurabilityError("SQLite busy timeout must be finite and non-negative")
    milliseconds = int(seconds * 1_000)
    if seconds > 0 and milliseconds < 1:
        raise SqliteDurabilityError("SQLite busy timeout must be zero or at least one millisecond")
    return milliseconds


def require_file_backed_database(database_path: Path) -> None:
    value = str(database_path)
    if value == ":memory:" or value.startswith("file::memory:"):
        raise SqliteDurabilityError("Durable SQLite storage must be file-backed")


def apply_sqlite_connection_pragmas(
    connection: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
    set_journal_mode: bool,
) -> None:
    timeout_ms = busy_timeout_milliseconds(busy_timeout_seconds)
    if set_journal_mode:
        journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            raise SqliteDurabilityError("SQLite could not enter WAL journal mode")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {timeout_ms}")


def inspect_sqlite_connection(connection: sqlite3.Connection) -> SqliteDurabilityState:
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
    synchronous = connection.execute("PRAGMA synchronous").fetchone()
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
    busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
    if None in (journal_mode, synchronous, foreign_keys, busy_timeout):
        raise SqliteDurabilityError("SQLite did not report required pragma values")
    return SqliteDurabilityState(
        journal_mode=str(journal_mode[0]).lower(),
        synchronous=int(synchronous[0]),
        foreign_keys=int(foreign_keys[0]),
        busy_timeout_ms=int(busy_timeout[0]),
    )


def configure_sqlite_connection(
    connection: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
    set_journal_mode: bool,
) -> SqliteDurabilityState:
    apply_sqlite_connection_pragmas(
        connection,
        busy_timeout_seconds=busy_timeout_seconds,
        set_journal_mode=set_journal_mode,
    )
    state = inspect_sqlite_connection(connection)
    checks = state.readiness_checks(
        expected_busy_timeout_ms=busy_timeout_milliseconds(busy_timeout_seconds)
    )
    failed = [name for name, result in checks.items() if result != "ok"]
    if failed:
        raise SqliteDurabilityError(
            f"SQLite durability requirements are not effective: {', '.join(failed)}"
        )
    return state
