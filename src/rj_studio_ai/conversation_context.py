"""Bounded, privacy-minimized Conversation context for one generation attempt."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from rj_studio_ai.domain import MessageRecord
from rj_studio_ai.persistence import RecentContextHistory, SqliteConversationStore
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact, SalonKnowledgeRepository


class ConversationContextTooLarge(ValueError):
    """The canonical current Message cannot fit safely in the configured input budget."""


@dataclass(frozen=True, slots=True)
class ConversationContextLimits:
    maximum_prior_messages: int = 12
    maximum_age: timedelta = timedelta(days=30)
    history_token_budget: int = 2_000
    total_input_token_budget: int = 4_000
    prompt_overhead_token_budget: int = 400

    def __post_init__(self) -> None:
        if self.maximum_prior_messages < 1:
            raise ValueError("Conversation context requires a positive Message limit")
        if self.maximum_age <= timedelta():
            raise ValueError("Conversation context requires a positive age limit")
        if self.history_token_budget < 1:
            raise ValueError("Conversation history budget must be positive")
        if self.total_input_token_budget < 1:
            raise ValueError("Conversation input budget must be positive")
        if not 0 <= self.prompt_overhead_token_budget < self.total_input_token_budget:
            raise ValueError("Conversation prompt overhead must fit within the input budget")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    role: Literal["customer", "ai_attendant"]
    body: str


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Only prior customer-visible turns and approved Salon Knowledge reach the LLM seam."""

    history: tuple[ConversationTurn, ...]
    knowledge: tuple[SalonKnowledgeFact, ...]
    history_may_be_incomplete: bool = False


class ConversationContextBuilder:
    """Loads and trims canonical prior turns without exposing persistence metadata."""

    def __init__(
        self,
        *,
        store: SqliteConversationStore,
        salon_knowledge: SalonKnowledgeRepository,
        limits: ConversationContextLimits,
    ) -> None:
        self._store = store
        self._salon_knowledge = salon_knowledge
        self._limits = limits

    def build(
        self,
        *,
        inbound_message_id: int,
        current_body: str,
        lock_timeout: float | None = None,
    ) -> ConversationContext:
        current_cost = _current_message_cost(current_body)
        content_budget = (
            self._limits.total_input_token_budget - self._limits.prompt_overhead_token_budget
        )
        if current_cost > content_budget:
            raise ConversationContextTooLarge(
                "Current Message exceeds the Conversation context budget"
            )

        knowledge = self._select_knowledge(current_body, content_budget - current_cost)
        knowledge_cost = _knowledge_cost(knowledge)
        history_budget = min(
            self._limits.history_token_budget,
            content_budget - current_cost - knowledge_cost,
        )
        recent_history = self._store.load_recent_context_history(
            inbound_message_id=inbound_message_id,
            maximum_age=self._limits.maximum_age,
            maximum_messages=self._limits.maximum_prior_messages,
            lock_timeout=lock_timeout,
        )
        history, history_was_trimmed = _trim_history(recent_history, history_budget)
        return ConversationContext(
            history=history,
            knowledge=knowledge,
            history_may_be_incomplete=(recent_history.has_omitted_messages or history_was_trimmed),
        )

    def _select_knowledge(
        self,
        current_body: str,
        available_budget: int,
    ) -> tuple[SalonKnowledgeFact, ...]:
        if available_budget <= _knowledge_header_cost():
            return ()
        selected = self._salon_knowledge.select(
            current_body,
            max_tokens=available_budget - _knowledge_header_cost(),
        )
        while selected and _knowledge_cost(selected) > available_budget:
            selected = _drop_trailing_knowledge_group(selected)
        return selected


def _drop_trailing_knowledge_group(
    selected: tuple[SalonKnowledgeFact, ...],
) -> tuple[SalonKnowledgeFact, ...]:
    """Drop the final fact and Services whose required policies would be absent."""
    retained = selected[:-1]
    removed_ids = {selected[-1].id}
    while True:
        dependents = {
            fact.id for fact in retained if removed_ids.intersection(fact.mandatory_policy_ids)
        }
        new_dependents = dependents - removed_ids
        if not new_dependents:
            return tuple(fact for fact in retained if fact.id not in removed_ids)
        removed_ids.update(new_dependents)


def _trim_history(
    history: RecentContextHistory,
    budget: int,
) -> tuple[tuple[ConversationTurn, ...], bool]:
    selected: list[ConversationTurn] = []
    remaining_budget = budget
    was_trimmed = False
    for record in reversed(history.records):
        turn = _turn_from_record(record)
        cost = _turn_cost(turn)
        if cost > remaining_budget:
            was_trimmed = True
            break
        selected.append(turn)
        remaining_budget -= cost
    selected.reverse()
    if selected and selected[0].role == "ai_attendant":
        selected.pop(0)
        was_trimmed = True
    return tuple(selected), was_trimmed


def _turn_from_record(record: MessageRecord) -> ConversationTurn:
    if record.direction == "inbound":
        return ConversationTurn(role="customer", body=record.body)
    if record.direction == "outbound":
        return ConversationTurn(role="ai_attendant", body=record.body)
    raise ValueError("Stored Conversation history has an unsupported Message direction")


def _current_message_cost(body: str) -> int:
    return len(f"Customer: {body}".encode())


def _turn_cost(turn: ConversationTurn) -> int:
    label = "Customer" if turn.role == "customer" else "AI Attendant"
    return len(f"{label}: {turn.body}".encode())


def _knowledge_header_cost() -> int:
    return len(b"Approved Salon Knowledge:\n")


def _knowledge_cost(knowledge: tuple[SalonKnowledgeFact, ...]) -> int:
    if not knowledge:
        return 0
    separators = max(0, len(knowledge) - 1) * len(b"\n\n")
    return (
        _knowledge_header_cost()
        + separators
        + sum(len(fact.context_text().encode("utf-8")) for fact in knowledge)
    )
