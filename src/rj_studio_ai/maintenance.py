import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rj_studio_ai.config import Settings
from rj_studio_ai.persistence import SqliteConversationStore


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rj-studio-maintenance")
    parser.add_argument("--database-path", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="Apply pending database migrations")

    purge = subparsers.add_parser(
        "purge-messages",
        help="Delete Messages older than the configured retention period",
    )
    purge.add_argument("--retention-days", type=_positive_integer)

    delete = subparsers.add_parser(
        "delete-conversation",
        help="Delete one Conversation and all of its Messages",
    )
    delete.add_argument("--provider", required=True)
    delete.add_argument("--customer-address", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    database_path = args.database_path or settings.database_path
    store = SqliteConversationStore(database_path)
    store.initialize()

    if args.command == "migrate":
        print("Database migrations are current.")
        return 0

    if args.command == "purge-messages":
        retention_days = args.retention_days or settings.message_retention_days
        reference_time = now or datetime.now(UTC)
        result = store.purge_messages_older_than(reference_time - timedelta(days=retention_days))
        print(
            f"Deleted messages={result.messages_deleted} "
            f"conversations={result.conversations_deleted}."
        )
        return 0

    result = store.delete_conversation(
        provider=args.provider,
        customer_address=args.customer_address,
    )
    print(
        f"Deleted messages={result.messages_deleted} conversations={result.conversations_deleted}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
