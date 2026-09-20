from collections.abc import Callable
from dataclasses import replace
from time import sleep

from rj_studio_ai.conversation_context import (
    ConversationContext,
    ConversationContextBuilder,
    ConversationContextTooLarge,
)
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import AIReply, InboundMessage
from rj_studio_ai.generation import (
    GenerationFailure,
    GenerationMetric,
    ReplyGenerator,
    TransientGenerationError,
)
from rj_studio_ai.persistence import (
    GenerationClaimResult,
    GenerationState,
    SqliteConversationStore,
)


class RetryableWebhookError(RuntimeError):
    """The provider should retry because no safe acknowledgement is ready."""


class MessageResponder:
    def __init__(
        self,
        *,
        store: SqliteConversationStore,
        generator: ReplyGenerator,
        safe_failure_reply: str,
        context_builder: ConversationContextBuilder | None = None,
        sleeper: Callable[[float], None] = sleep,
        ordering_poll_seconds: float = 0.05,
        maximum_ordering_wait_seconds: float = 1.0,
        retry_backoff_seconds: float = 0.1,
        minimum_generation_budget_seconds: float = 0.1,
    ) -> None:
        if not safe_failure_reply.strip():
            raise ValueError("Safe failure reply must not be empty")
        self._store = store
        self._generator = generator
        self._safe_failure_reply = safe_failure_reply
        self._context_builder = context_builder
        self._sleeper = sleeper
        self._ordering_poll_seconds = ordering_poll_seconds
        self._maximum_ordering_wait_seconds = maximum_ordering_wait_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._minimum_generation_budget_seconds = minimum_generation_budget_seconds

    def handle(
        self,
        message: InboundMessage,
        *,
        deadline: ExecutionDeadline,
    ) -> AIReply:
        lifecycle = self._store.admit_generation(
            message,
            lock_timeout=deadline.work_budget(),
        )
        terminal_reply = self._terminal_reply(lifecycle)
        if terminal_reply is not None:
            return terminal_reply
        canonical_message = replace(message, body=lifecycle.inbound_body)

        ordering_wait_started_with: float | None = None
        while True:
            if lifecycle.state is GenerationState.SUPPRESSED:
                raise RetryableWebhookError("AI Reply is suppressed")

            if lifecycle.state is GenerationState.RETRYABLE and lifecycle.attempt_count >= 2:
                lifecycle = self._claim_exhausted_finalization(lifecycle, deadline)
                terminal_reply = self._terminal_reply(lifecycle)
                if terminal_reply is not None:
                    return terminal_reply
                if lifecycle.acquired:
                    return self._complete_owned_reply(
                        lifecycle,
                        self._safe_failure_reply,
                        deadline,
                    )
            elif not lifecycle.acquired:
                self._require_generation_budget(deadline)
                lifecycle = self._store.claim_generation(
                    canonical_message,
                    lock_timeout=self._claim_lock_timeout(deadline),
                )

            terminal_reply = self._terminal_reply(lifecycle)
            if terminal_reply is not None:
                return terminal_reply

            if lifecycle.acquired:
                return self._generate_and_complete(canonical_message, lifecycle, deadline)

            if lifecycle.state is GenerationState.RETRYABLE and lifecycle.attempt_count >= 2:
                continue

            if lifecycle.blocked_by_predecessor or lifecycle.state is GenerationState.PROCESSING:
                if ordering_wait_started_with is None:
                    ordering_wait_started_with = deadline.remaining_budget()
                self._wait_once(deadline, ordering_wait_started_with)
                continue

            raise RetryableWebhookError("Generation claim is not currently available")

    def _generate_and_complete(
        self,
        message: InboundMessage,
        claim: GenerationClaimResult,
        deadline: ExecutionDeadline,
    ) -> AIReply:
        if claim.owner_token is None:
            raise RetryableWebhookError("Generation claim owner is unavailable")
        if deadline.work_budget() < self._minimum_generation_budget_seconds:
            released = self._store.mark_generation_retryable(
                inbound_message_id=claim.inbound_message_id,
                owner_token=claim.owner_token,
                lock_timeout=deadline.remaining_budget(),
            )
            if not released:
                raise RetryableWebhookError(
                    "Generation claim with exhausted budget could not be released"
                )
            raise RetryableWebhookError("No useful generation budget remains")
        try:
            context = self._build_context(claim, message, deadline)
        except ConversationContextTooLarge:
            return self._complete_owned_reply(claim, self._safe_failure_reply, deadline)
        try:
            generated = self._generator.generate(
                message,
                context=context,
                remaining_budget=deadline.work_budget(),
            )
            reply_body = generated.reply_body
            if not isinstance(reply_body, str) or not reply_body.strip():
                raise TransientGenerationError("invalid_generation_result", generated.metric)
            if deadline.work_budget() <= 0.0:
                raise TransientGenerationError("generation_deadline", generated.metric)
            self._record_metric(claim, generated.metric, deadline)
        except TransientGenerationError as error:
            self._record_metric(claim, error.metric, deadline)
            return self._handle_generation_failure(message, claim, deadline, error)
        except GenerationFailure as error:
            self._record_metric(claim, error.metric, deadline)
            self._release_for_retryable_failure(claim, deadline)
            raise RetryableWebhookError("Generation provider is unavailable") from error

        return self._complete_owned_reply(claim, reply_body, deadline)

    def _build_context(
        self,
        claim: GenerationClaimResult,
        message: InboundMessage,
        deadline: ExecutionDeadline,
    ) -> ConversationContext:
        if self._context_builder is None:
            return ConversationContext(history=(), knowledge=())
        return self._context_builder.build(
            inbound_message_id=claim.inbound_message_id,
            current_body=message.body,
            lock_timeout=deadline.work_budget(),
        )

    def _record_metric(
        self,
        claim: GenerationClaimResult,
        metric: GenerationMetric | None,
        deadline: ExecutionDeadline,
    ) -> None:
        if metric is None:
            return
        self._store.record_generation_metric(
            inbound_message_id=claim.inbound_message_id,
            attempt_number=claim.attempt_count,
            metric=metric,
            lock_timeout=deadline.remaining_budget(),
        )

    def _release_for_retryable_failure(
        self,
        claim: GenerationClaimResult,
        deadline: ExecutionDeadline,
    ) -> None:
        if claim.owner_token is None:
            raise RetryableWebhookError("Generation claim owner is unavailable")
        released = self._store.mark_generation_retryable(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            lock_timeout=deadline.remaining_budget(),
        )
        if not released:
            raise RetryableWebhookError("Generation claim could not be released")

    def _handle_generation_failure(
        self,
        message: InboundMessage,
        claim: GenerationClaimResult,
        deadline: ExecutionDeadline,
        error: TransientGenerationError,
    ) -> AIReply:
        if claim.owner_token is None:
            raise RetryableWebhookError("Generation claim owner is unavailable") from error
        if claim.attempt_count >= 2:
            return self._complete_owned_reply(claim, self._safe_failure_reply, deadline)

        released = self._store.mark_generation_retryable(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            lock_timeout=deadline.remaining_budget(),
        )
        if not released:
            raise RetryableWebhookError("Generation claim could not be released") from error
        if (
            deadline.work_budget()
            < self._retry_backoff_seconds + self._minimum_generation_budget_seconds
        ):
            raise RetryableWebhookError("No budget remains for a generation retry") from error

        self._sleeper(self._retry_backoff_seconds)
        self._require_generation_budget(deadline)
        retry_claim = self._store.claim_generation(
            message,
            lock_timeout=self._claim_lock_timeout(deadline),
        )
        terminal_reply = self._terminal_reply(retry_claim)
        if terminal_reply is not None:
            return terminal_reply
        if retry_claim.acquired:
            return self._generate_and_complete(message, retry_claim, deadline)
        raise RetryableWebhookError("Generation retry claim is not available") from error

    def _claim_exhausted_finalization(
        self,
        lifecycle: GenerationClaimResult,
        deadline: ExecutionDeadline,
    ) -> GenerationClaimResult:
        if deadline.remaining_budget() <= 0.0:
            raise RetryableWebhookError("No budget remains for safe finalization")
        return self._store.claim_exhausted_finalization(
            inbound_message_id=lifecycle.inbound_message_id,
            lock_timeout=deadline.remaining_budget(),
        )

    def _complete_owned_reply(
        self,
        claim: GenerationClaimResult,
        reply_body: str,
        deadline: ExecutionDeadline,
    ) -> AIReply:
        if claim.owner_token is None:
            raise RetryableWebhookError("Generation claim owner is unavailable")
        completed = self._store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body=reply_body,
            lock_timeout=deadline.remaining_budget(),
        )
        if not completed:
            raise RetryableWebhookError("Generation completion lost ownership")
        return AIReply(body=reply_body)

    def _wait_once(
        self,
        deadline: ExecutionDeadline,
        wait_started_with: float,
    ) -> None:
        wait_spent = wait_started_with - deadline.remaining_budget()
        wait_remaining = self._maximum_ordering_wait_seconds - wait_spent
        work_budget = deadline.work_budget()
        sleep_budget = work_budget - self._minimum_generation_budget_seconds
        duration = min(self._ordering_poll_seconds, wait_remaining, sleep_budget)
        if duration <= 0.0:
            raise RetryableWebhookError("Conversation predecessor is still active")
        self._sleeper(duration)

    def _require_generation_budget(self, deadline: ExecutionDeadline) -> None:
        if deadline.work_budget() < self._minimum_generation_budget_seconds:
            raise RetryableWebhookError("No useful generation budget remains")

    def _claim_lock_timeout(self, deadline: ExecutionDeadline) -> float:
        return max(
            0.0,
            deadline.work_budget() - self._minimum_generation_budget_seconds,
        )

    @staticmethod
    def _terminal_reply(lifecycle: GenerationClaimResult) -> AIReply | None:
        if lifecycle.state is not GenerationState.COMPLETED:
            return None
        if lifecycle.reply_body is None:
            raise RetryableWebhookError("Completed generation has no durable reply")
        return AIReply(body=lifecycle.reply_body)
