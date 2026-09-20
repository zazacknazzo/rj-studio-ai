import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rj_studio_ai.application import MessageResponder, RetryableWebhookError
from rj_studio_ai.config import Settings
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.recovery import PendingGenerationRecovery, RecoveryNotAvailable
from rj_studio_ai.runtime import generator_from_settings


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
    subparsers.add_parser(
        "list-pending-generations",
        help="List retryable or stale inbound Messages without Customer content",
    )

    recover = subparsers.add_parser(
        "recover-generation",
        help="Recover one selected eligible inbound Message through the normal lifecycle",
    )
    recover.add_argument("--inbound-message-id", type=_positive_integer, required=True)

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

    if args.command in {"list-pending-generations", "recover-generation"}:
        recovery = PendingGenerationRecovery(
            store=store,
            responder=MessageResponder(
                store=store,
                generator=generator_from_settings(settings),
                safe_failure_reply=settings.automatic_reply,
            ),
        )

    if args.command == "list-pending-generations":
        candidates = recovery.list_pending()
        if not candidates:
            print("No pending generated Messages.")
            return 0
        for candidate in candidates:
            lease_expires_at = (
                candidate.lease_expires_at.isoformat() if candidate.lease_expires_at else "none"
            )
            print(
                f"inbound_message_id={candidate.inbound_message_id} "
                f"conversation_id={candidate.conversation_id} "
                f"state={candidate.state.value} attempts={candidate.attempt_count} "
                f"received_at={candidate.created_at.isoformat()} "
                f"lease_expires_at={lease_expires_at} "
                f"stale={'yes' if candidate.is_stale else 'no'} "
                f"blocked_by_predecessor={'yes' if candidate.blocked_by_predecessor else 'no'}"
            )
        return 0

    if args.command == "recover-generation":
        try:
            result = recovery.recover(args.inbound_message_id)
        except (RecoveryNotAvailable, RetryableWebhookError, PersistenceUnavailable) as error:
            print(
                f"Recovery not completed inbound_message_id={args.inbound_message_id} "
                f"reason={type(error).__name__}."
            )
            return 1
        if result.reply_persisted:
            print(f"Recovery completed inbound_message_id={result.inbound_message_id}.")
            return 0
        print(
            f"Recovery not completed inbound_message_id={result.inbound_message_id} "
            "reason=no_reply."
        )
        return 1

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
