import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import DeliveryStatus, DeliveryStatusReceived, InboundMessage
from rj_studio_ai.maintenance import main as maintenance_main
from rj_studio_ai.persistence import (
    DeliveryState,
    DeliveryStatusDisposition,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
MESSAGE_SID = "SM" + "3" * 32


def _store(path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(path)
    store.initialize()
    return store


def _pending(store: SqliteConversationStore) -> int:
    message = InboundMessage(
        provider="twilio",
        provider_message_id="SM-inbound-status",
        customer_address="whatsapp:+5511999999999",
        recipient_address="whatsapp:+14155238886",
        body="Mensagem sintética",
    )
    claim = store.claim_generation(message, now=NOW)
    assert claim.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta sintética",
        delivery_state=DeliveryState.PENDING,
        now=NOW + timedelta(seconds=1),
    )
    return claim.inbound_message_id


def _event(status: DeliveryStatus) -> DeliveryStatusReceived:
    return DeliveryStatusReceived(
        provider="twilio",
        provider_message_id=MESSAGE_SID,
        status=status,
        safe_error_code=("provider_undelivered" if status is DeliveryStatus.FAILED else None),
    )


def _accept(store: SqliteConversationStore) -> int:
    inbound_id = _pending(store)
    accepted = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance(provider_message_id=MESSAGE_SID)]
        ),
        timeout_seconds=2.0,
    ).run_once(now=NOW + timedelta(seconds=2))
    assert accepted is not None
    assert accepted.state is DeliveryState.ACCEPTED
    return inbound_id


def test_status_callbacks_advance_monotonically_and_duplicates_are_idempotent(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "status.db")
    inbound_id = _accept(store)

    assert store.record_delivery_status(_event(DeliveryStatus.SENT), now=NOW) is (
        DeliveryStatusDisposition.APPLIED
    )
    assert store.record_delivery_status(_event(DeliveryStatus.DELIVERED), now=NOW) is (
        DeliveryStatusDisposition.APPLIED
    )
    assert store.record_delivery_status(_event(DeliveryStatus.SENT), now=NOW) is (
        DeliveryStatusDisposition.IGNORED
    )
    assert store.record_delivery_status(_event(DeliveryStatus.DELIVERED), now=NOW) is (
        DeliveryStatusDisposition.IGNORED
    )
    assert store.record_delivery_status(_event(DeliveryStatus.READ), now=NOW) is (
        DeliveryStatusDisposition.APPLIED
    )

    delivery = store.get_delivery_for_inbound(inbound_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.READ


def test_failed_callback_is_terminal_and_blocks_success_regression(tmp_path: Path) -> None:
    store = _store(tmp_path / "failed.db")
    inbound_id = _accept(store)

    assert store.record_delivery_status(_event(DeliveryStatus.FAILED), now=NOW) is (
        DeliveryStatusDisposition.APPLIED
    )
    assert store.record_delivery_status(_event(DeliveryStatus.DELIVERED), now=NOW) is (
        DeliveryStatusDisposition.IGNORED
    )

    delivery = store.get_delivery_for_inbound(inbound_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.FAILED
    assert delivery.safe_error_code == "provider_undelivered"


def test_blocked_delivery_inspection_is_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "blocked-inspection.db"
    store = _store(database_path)
    inbound_id = _accept(store)
    assert store.record_delivery_status(_event(DeliveryStatus.FAILED), now=NOW) is (
        DeliveryStatusDisposition.APPLIED
    )
    delivery = store.get_delivery_for_inbound(inbound_id)
    assert delivery is not None

    result = maintenance_main(["--database-path", str(database_path), "list-blocked-deliveries"])
    output = capsys.readouterr().out

    assert result == 0
    assert f"delivery_id={delivery.delivery_id}" in output
    assert "state=failed" in output
    assert "reason=provider_undelivered" in output
    assert "Resposta sintética" not in output
    assert "whatsapp:" not in output


@pytest.mark.parametrize(
    ("early_statuses", "expected"),
    [
        ([DeliveryStatus.SENT], DeliveryState.SENT),
        ([DeliveryStatus.DELIVERED, DeliveryStatus.SENT], DeliveryState.DELIVERED),
        ([DeliveryStatus.READ, DeliveryStatus.DELIVERED], DeliveryState.READ),
        ([DeliveryStatus.DELIVERED, DeliveryStatus.FAILED], DeliveryState.FAILED),
    ],
)
def test_status_before_local_acceptance_is_retained_and_merged_once(
    tmp_path: Path,
    early_statuses: list[DeliveryStatus],
    expected: DeliveryState,
) -> None:
    database_path = tmp_path / f"early-{expected}.db"
    store = _store(database_path)
    inbound_id = _pending(store)

    for status in early_statuses:
        disposition = store.record_delivery_status(_event(status), now=NOW)
        assert disposition in {
            DeliveryStatusDisposition.BUFFERED,
            DeliveryStatusDisposition.IGNORED,
        }

    restarted = SqliteConversationStore(database_path)
    finalized = OutboundDeliveryRunner(
        store=restarted,
        sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance(provider_message_id=MESSAGE_SID)]
        ),
        timeout_seconds=2.0,
    ).run_once(now=NOW + timedelta(seconds=2))

    assert finalized is not None
    assert finalized.state is expected
    delivery = restarted.get_delivery_for_inbound(inbound_id)
    assert delivery is not None
    assert delivery.state is expected
    with sqlite3.connect(database_path) as connection:
        buffered = connection.execute("SELECT COUNT(*) FROM pending_delivery_statuses").fetchone()[
            0
        ]
    assert buffered == 0
