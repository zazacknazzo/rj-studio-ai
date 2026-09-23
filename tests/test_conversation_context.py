import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rj_studio_ai.conversation_context import (
    ConversationContextBuilder,
    ConversationContextLimits,
    ConversationContextTooLarge,
)
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.persistence import (
    DeliveryState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _message(message_id: str, customer: str, body: str) -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id=message_id,
        customer_address=customer,
        recipient_address="studio",
        body=body,
    )


def _store(database_path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(database_path)
    store.initialize()
    return store


def _knowledge(path: Path) -> SalonKnowledgeRepository:
    path.write_text("version: 1\nfacts: []\n", encoding="utf-8")
    repository = SalonKnowledgeRepository(path)
    repository.load()
    return repository


def _knowledge_with_corte(path: Path) -> SalonKnowledgeRepository:
    path.write_text(
        """
version: 1
facts:
  - id: service-corte
    category: service
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Serviço sintético de corte.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
""".lstrip(),
        encoding="utf-8",
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()
    return repository


def test_builder_uses_canonical_prior_turns_in_conversation_order(tmp_path: Path) -> None:
    store = _store(tmp_path / "context.db")
    first = store.claim_generation(_message("first", "customer-a", "Quero progressiva"), now=NOW)
    assert first.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Vamos avaliar seu cabelo.",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW + timedelta(seconds=1),
    )
    current = store.admit_generation(
        _message("current", "customer-a", "Meu cabelo é comprido"),
        now=NOW + timedelta(seconds=2),
    )

    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    ).build(
        inbound_message_id=current.inbound_message_id,
        current_body=current.inbound_body,
    )

    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "Quero progressiva"),
        ("ai_attendant", "Vamos avaliar seu cabelo."),
    ]


def test_builder_excludes_pending_reply_until_provider_acceptance(tmp_path: Path) -> None:
    store = _store(tmp_path / "delivery-visibility.db")
    first = store.claim_generation(_message("first", "customer-a", "Primeira"), now=NOW)
    assert first.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta ainda não aceita",
        delivery_state=DeliveryState.PENDING,
        now=NOW,
    )
    current = store.admit_generation(
        _message("current", "customer-a", "Segunda"),
        now=NOW + timedelta(seconds=1),
    )
    builder = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    )

    before_acceptance = builder.build(
        inbound_message_id=current.inbound_message_id,
        current_body=current.inbound_body,
    )
    OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-visible")]),
        timeout_seconds=1.0,
    ).run_once(now=NOW + timedelta(seconds=2))
    after_acceptance = builder.build(
        inbound_message_id=current.inbound_message_id,
        current_body=current.inbound_body,
    )

    assert [(turn.role, turn.body) for turn in before_acceptance.history] == [
        ("customer", "Primeira")
    ]
    assert [(turn.role, turn.body) for turn in after_acceptance.history] == [
        ("customer", "Primeira"),
        ("ai_attendant", "Resposta ainda não aceita"),
    ]


@pytest.mark.parametrize(
    ("delivery_state", "is_visible"),
    [
        (DeliveryState.PENDING, False),
        (DeliveryState.SENDING, False),
        (DeliveryState.RETRYABLE, False),
        (DeliveryState.UNKNOWN, False),
        (DeliveryState.ACCEPTED, True),
        (DeliveryState.SENT, True),
        (DeliveryState.DELIVERED, True),
        (DeliveryState.READ, True),
        (DeliveryState.FAILED, False),
        (DeliveryState.CANCELLED, False),
        (DeliveryState.ACCEPTED_LEGACY, True),
    ],
)
def test_builder_obeys_every_delivery_visibility_state(
    tmp_path: Path,
    delivery_state: DeliveryState,
    is_visible: bool,
) -> None:
    database_path = tmp_path / f"context-{delivery_state}.db"
    store = _store(database_path)
    prior = store.claim_generation(_message("prior", "customer-a", "Customer"), now=NOW)
    assert prior.owner_token is not None
    initial_state = (
        DeliveryState.ACCEPTED_LEGACY
        if delivery_state is DeliveryState.ACCEPTED_LEGACY
        else DeliveryState.PENDING
    )
    assert store.complete_generation(
        inbound_message_id=prior.inbound_message_id,
        owner_token=prior.owner_token,
        reply_body="AI Reply",
        delivery_state=initial_state,
        now=NOW,
    )

    if delivery_state is DeliveryState.SENDING:
        assert store.claim_next_delivery(now=NOW) is not None
    elif delivery_state in {
        DeliveryState.RETRYABLE,
        DeliveryState.UNKNOWN,
        DeliveryState.ACCEPTED,
        DeliveryState.FAILED,
        DeliveryState.SENT,
        DeliveryState.DELIVERED,
        DeliveryState.READ,
    }:
        outcomes: dict[DeliveryState, ProviderAcceptance | Exception] = {
            DeliveryState.RETRYABLE: OutboundRetryableError("retryable"),
            DeliveryState.UNKNOWN: OutboundOutcomeUnknown("unknown"),
            DeliveryState.ACCEPTED: ProviderAcceptance("PM-context"),
            DeliveryState.FAILED: OutboundPermanentError("failed"),
            DeliveryState.SENT: ProviderAcceptance("PM-context"),
            DeliveryState.DELIVERED: ProviderAcceptance("PM-context"),
            DeliveryState.READ: ProviderAcceptance("PM-context"),
        }
        OutboundDeliveryRunner(
            store=store,
            sender=DeterministicFakeOutboundSender(outcomes=[outcomes[delivery_state]]),
            timeout_seconds=1.0,
        ).run_once(now=NOW)
        if delivery_state in {DeliveryState.SENT, DeliveryState.DELIVERED, DeliveryState.READ}:
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "UPDATE outbound_deliveries SET state = ?, updated_at = ?",
                    (delivery_state, NOW.isoformat()),
                )
    elif delivery_state is DeliveryState.CANCELLED:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                UPDATE outbound_deliveries
                SET state = 'cancelled', next_attempt_at = NULL, updated_at = ?
                """,
                (NOW.isoformat(),),
            )

    current = store.admit_generation(
        _message("current", "customer-a", "Atual"),
        now=NOW + timedelta(seconds=1),
    )
    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / f"knowledge-{delivery_state}.yaml"),
        limits=ConversationContextLimits(),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    expected = [("customer", "Customer")]
    if is_visible:
        expected.append(("ai_attendant", "AI Reply"))
    assert [(turn.role, turn.body) for turn in context.history] == expected


def test_builder_isolates_the_current_conversation_and_uses_logical_reply_order(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "isolation.db")
    first = store.claim_generation(_message("first", "customer-a", "Primeira"), now=NOW)
    current = store.admit_generation(
        _message("current", "customer-a", "Segunda"), now=NOW + timedelta(seconds=1)
    )
    other = store.claim_generation(_message("other", "customer-b", "Outra conversa"), now=NOW)
    assert first.owner_token is not None
    assert other.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=other.inbound_message_id,
        owner_token=other.owner_token,
        reply_body="Resposta de B",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW + timedelta(seconds=2),
    )
    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta de A",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW + timedelta(seconds=2),
    )

    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "Primeira"),
        ("ai_attendant", "Resposta de A"),
    ]


def test_builder_keeps_only_the_newest_twelve_recent_prior_messages(tmp_path: Path) -> None:
    store = _store(tmp_path / "count.db")
    for number in range(7):
        claim = store.claim_generation(
            _message(f"prior-{number}", "customer-a", f"Customer {number}"),
            now=NOW + timedelta(minutes=number),
        )
        assert claim.owner_token is not None
        assert store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body=f"AI {number}",
            delivery_state=DeliveryState.ACCEPTED_LEGACY,
            now=NOW + timedelta(minutes=number, seconds=1),
        )
    current = store.admit_generation(
        _message("current", "customer-a", "Atual"), now=NOW + timedelta(minutes=8)
    )

    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert context.history_may_be_incomplete
    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "Customer 1"),
        ("ai_attendant", "AI 1"),
        ("customer", "Customer 2"),
        ("ai_attendant", "AI 2"),
        ("customer", "Customer 3"),
        ("ai_attendant", "AI 3"),
        ("customer", "Customer 4"),
        ("ai_attendant", "AI 4"),
        ("customer", "Customer 5"),
        ("ai_attendant", "AI 5"),
        ("customer", "Customer 6"),
        ("ai_attendant", "AI 6"),
    ]


def test_builder_applies_the_thirty_day_boundary_from_the_persisted_current_message(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "age.db")
    outside = store.claim_generation(
        _message("outside", "customer-a", "Fora da janela"),
        now=NOW - timedelta(days=30, seconds=1),
    )
    assert outside.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=outside.inbound_message_id,
        owner_token=outside.owner_token,
        reply_body="Resposta antiga",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW - timedelta(days=30, seconds=1),
    )
    boundary = store.claim_generation(
        _message("boundary", "customer-a", "No limite"),
        now=NOW - timedelta(days=30),
    )
    assert boundary.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=boundary.inbound_message_id,
        owner_token=boundary.owner_token,
        reply_body="Resposta no limite",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW - timedelta(days=30),
    )
    current = store.admit_generation(_message("current", "customer-a", "Atual"), now=NOW)

    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert context.history_may_be_incomplete
    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "No limite"),
        ("ai_attendant", "Resposta no limite"),
    ]


def test_builder_trims_oldest_history_and_rejects_an_oversized_current_message(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "budget.db")
    old = store.claim_generation(
        _message("old", "customer-a", "x" * 300), now=NOW - timedelta(minutes=2)
    )
    assert old.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=old.inbound_message_id,
        owner_token=old.owner_token,
        reply_body="Resposta antiga",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW - timedelta(minutes=2),
    )
    recent = store.claim_generation(
        _message("recent", "customer-a", "Recente"), now=NOW - timedelta(minutes=1)
    )
    assert recent.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=recent.inbound_message_id,
        owner_token=recent.owner_token,
        reply_body="Resposta recente",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW - timedelta(minutes=1),
    )
    current = store.admit_generation(_message("current", "customer-a", "Atual"), now=NOW)
    builder = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(
            history_token_budget=80,
            total_input_token_budget=500,
            prompt_overhead_token_budget=0,
        ),
    )

    context = builder.build(
        inbound_message_id=current.inbound_message_id, current_body=current.inbound_body
    )
    assert context.history_may_be_incomplete
    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "Recente"),
        ("ai_attendant", "Resposta recente"),
    ]
    with pytest.raises(ConversationContextTooLarge):
        builder.build(inbound_message_id=current.inbound_message_id, current_body="x" * 501)


def test_builder_keeps_current_message_and_approved_knowledge_ahead_of_old_history(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "knowledge-priority.db")
    prior = store.claim_generation(
        _message("prior", "customer-a", "Mensagem antiga"), now=NOW - timedelta(minutes=1)
    )
    assert prior.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=prior.inbound_message_id,
        owner_token=prior.owner_token,
        reply_body="Resposta antiga",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
        now=NOW - timedelta(minutes=1),
    )
    current = store.admit_generation(_message("current", "customer-a", "Quero corte"), now=NOW)

    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge_with_corte(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(
            history_token_budget=2_000,
            total_input_token_budget=300,
            prompt_overhead_token_budget=0,
        ),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert [fact.id for fact in context.knowledge] == ["service-corte"]
    assert [(turn.role, turn.body) for turn in context.history] == [
        ("customer", "Mensagem antiga"),
        ("ai_attendant", "Resposta antiga"),
    ]


def test_builder_drops_trailing_knowledge_when_rendering_separators_would_exceed_budget(
    tmp_path: Path,
) -> None:
    source = tmp_path / "knowledge.yaml"
    source.write_text(
        """
version: 1
facts:
  - id: corte-a
    category: service
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Primeiro fato sintético.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
  - id: corte-b
    category: policy
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Segundo fato sintético.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
""".lstrip(),
        encoding="utf-8",
    )
    repository = SalonKnowledgeRepository(source)
    facts = repository.load()
    store = _store(tmp_path / "knowledge-budget.db")
    current = store.admit_generation(_message("current", "customer-a", "Quero corte"), now=NOW)
    current_cost = len(f"Customer: {current.inbound_body}".encode())
    rendered_facts_cost = sum(len(fact.context_text().encode()) for fact in facts)
    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=repository,
        limits=ConversationContextLimits(
            history_token_budget=1,
            total_input_token_budget=(
                current_cost + len(b"Approved Salon Knowledge:\n") + rendered_facts_cost
            ),
            prompt_overhead_token_budget=0,
        ),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert [fact.id for fact in context.knowledge] == ["corte-a"]


def test_builder_drops_a_service_when_its_required_policy_cannot_fit(tmp_path: Path) -> None:
    source = tmp_path / "knowledge.yaml"
    source.write_text(
        """
version: 1
facts:
  - id: corte-a
    category: service
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Serviço sintético.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
    mandatory_policy_ids: [corte-b]
  - id: corte-b
    category: policy
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Política obrigatória sintética.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
""".lstrip(),
        encoding="utf-8",
    )
    repository = SalonKnowledgeRepository(source)
    facts = repository.load()
    store = _store(tmp_path / "knowledge-dependency-budget.db")
    current = store.admit_generation(_message("current", "customer-a", "Quero corte"), now=NOW)
    current_cost = len(f"Customer: {current.inbound_body}".encode())
    rendered_facts_cost = sum(len(fact.context_text().encode()) for fact in facts)
    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=repository,
        limits=ConversationContextLimits(
            history_token_budget=1,
            total_input_token_budget=(
                current_cost + len(b"Approved Salon Knowledge:\n") + rendered_facts_cost
            ),
            prompt_overhead_token_budget=0,
        ),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)

    assert context.knowledge == ()


def test_builder_fails_safe_when_persisted_history_has_an_invalid_timestamp(tmp_path: Path) -> None:
    database_path = tmp_path / "malformed-history.db"
    store = _store(database_path)
    prior = store.claim_generation(_message("prior", "customer-a", "Mensagem anterior"), now=NOW)
    assert prior.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=prior.inbound_message_id,
        owner_token=prior.owner_token,
        reply_body="Resposta anterior",
        now=NOW,
    )
    current = store.admit_generation(
        _message("current", "customer-a", "Atual"), now=NOW + timedelta(seconds=1)
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE messages SET created_at = 'invalid' WHERE id = ?",
            (prior.inbound_message_id,),
        )
    builder = ConversationContextBuilder(
        store=store,
        salon_knowledge=_knowledge(tmp_path / "knowledge.yaml"),
        limits=ConversationContextLimits(),
    )

    with pytest.raises(PersistenceUnavailable, match="invalid Message timestamp"):
        builder.build(
            inbound_message_id=current.inbound_message_id, current_body=current.inbound_body
        )
