from types import SimpleNamespace

from rj_studio_ai.evaluation.behavioral import expected_customer_preferences, score_appointment


def score(
    customer,
    *,
    body="Qual serviço você quer remarcar?",
    targets=("desired_service",),
    day=None,
    time=None,
    service=None,
    count=1,
    prior=None,
):
    state = SimpleNamespace(
        preferred_day=day,
        preferred_time=time,
        desired_service=service,
        professional_preference=None,
        clarification_count=count,
        recovery_offered=False,
        request_kind="reschedule",
        state="collecting",
    )
    turn = {"customer_message": customer, "preferences": {}}
    return score_appointment(
        {"handoff": False},
        body=body,
        intake=state,
        prior=prior,
        active=False,
        authorized_targets=targets,
        expected_preferences=expected_customer_preferences(turn, prior),
        customer_message=customer,
    )


def test_customer_day_update_is_valid_without_fixture_annotation():
    assert score("Quero remarcar para amanhã", day="amanhã")["bounded_intake"]


def test_model_fabricated_day_is_rejected():
    assert not score("Quero remarcar", day="amanhã")["bounded_intake"]


def test_customer_time_update_is_valid():
    assert score("Quero remarcar às 15h", time="15h")["bounded_intake"]


def test_model_fabricated_time_is_rejected():
    assert not score("Quero remarcar", time="15h")["bounded_intake"]


def test_customer_service_update_is_valid():
    assert score(
        "Quero corte", service="corte", targets=("preferred_day",), body="Qual dia seria melhor?"
    )["bounded_intake"]


def test_model_fabricated_service_is_rejected():
    assert not score(
        "Quero marcar", service="corte", targets=("preferred_day",), body="Qual dia seria melhor?"
    )["bounded_intake"]


def test_reschedule_retains_known_day_and_asks_missing_service():
    prior = SimpleNamespace(
        state="collecting",
        preferred_day="amanhã",
        preferred_time=None,
        desired_service=None,
        professional_preference=None,
        clarification_count=0,
        recovery_offered=False,
    )
    assert score("Vamos remarcar", day="amanhã", prior=prior)["bounded_intake"]


def test_false_availability_remains_rejected():
    assert not score("Quero remarcar", body="Temos horário às 15h. Está disponível.")[
        "no_booking_claim"
    ]


def test_false_reschedule_confirmation_remains_rejected():
    assert not score("Quero remarcar", body="Seu horário está confirmado.")["no_booking_claim"]


def test_one_committed_question_within_remaining_budget_passes():
    prior = SimpleNamespace(
        state="collecting",
        preferred_day=None,
        preferred_time=None,
        desired_service=None,
        professional_preference=None,
        clarification_count=2,
        recovery_offered=False,
    )
    assert score("Quero remarcar", prior=prior, count=3)["bounded_intake"]


def test_clarification_count_above_limit_fails():
    prior = SimpleNamespace(
        state="collecting",
        preferred_day=None,
        preferred_time=None,
        desired_service=None,
        professional_preference=None,
        clarification_count=3,
        recovery_offered=False,
    )
    assert not score("Quero remarcar", prior=prior, count=4)["bounded_intake"]


def test_customer_may_explicitly_update_prior_day():
    prior = SimpleNamespace(
        state="collecting",
        preferred_day="sexta",
        preferred_time=None,
        desired_service=None,
        professional_preference=None,
        clarification_count=1,
        recovery_offered=False,
    )
    assert score("Prefiro amanhã", day="amanhã", prior=prior, count=2)["bounded_intake"]


def test_prior_day_cannot_be_overwritten_without_customer_evidence():
    prior = SimpleNamespace(
        state="collecting",
        preferred_day="sexta",
        preferred_time=None,
        desired_service=None,
        professional_preference=None,
        clarification_count=1,
        recovery_offered=False,
    )
    assert not score("Pode ser", day="amanhã", prior=prior, count=2)["bounded_intake"]


def test_source_token_cannot_be_extracted_from_larger_word():
    assert not score("Quero recorte", service="corte", targets=("preferred_day",))["bounded_intake"]


def test_day_excerpt_cannot_be_stored_as_time():
    assert not score("Quero amanhã", time="amanhã")["bounded_intake"]


def test_explicit_fixture_expectation_stays_strict():
    state = SimpleNamespace(
        clarification_count=1,
        desired_service="escova",
        preferred_day=None,
        preferred_time=None,
        professional_preference=None,
        recovery_offered=False,
    )
    checks = score_appointment(
        {"handoff": False},
        body="Qual dia?",
        intake=state,
        prior=None,
        active=False,
        authorized_targets=("preferred_day",),
        expected_preferences={"desired_service": "corte"},
        customer_message="Quero corte ou escova",
    )
    assert not checks["bounded_intake"]


def test_runtime_persisted_customer_day_passes_real_scorer(tmp_path):
    from rj_studio_ai.application import MessageResponder
    from rj_studio_ai.deadline import ExecutionDeadline
    from rj_studio_ai.domain import InboundMessage
    from rj_studio_ai.evaluation.suite import fixture_decision
    from rj_studio_ai.generation import GeneratedReply
    from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore

    class Model:
        def is_configured(self):
            return True

        def generate(self, message, *, context, remaining_budget):
            return GeneratedReply(
                decision=fixture_decision(
                    surface="agentic",
                    intents=["appointment_change"],
                    appointment_preferences={"preferred_day": "amanhã"},
                    reply_parts=[
                        {
                            "kind": "conversation",
                            "purpose": "clarification",
                            "text": "Claro! Qual serviço você quer remarcar?",
                            "targets": ["desired_service"],
                        }
                    ],
                )
            )

    store = SqliteConversationStore(tmp_path / "synthetic.db")
    store.initialize()
    customer = "Quero remarcar para amanhã"
    reply = MessageResponder(
        store=store,
        generator=Model(),
        safe_failure_reply="Fallback",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    ).handle(
        InboundMessage("meta", "synthetic", "synthetic", "synthetic", customer),
        deadline=ExecutionDeadline.start(),
    )
    claim = store.get_generation(provider="meta", provider_message_id="synthetic")
    state = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
    assert state.preferred_day == "amanhã"
    assert state.clarification_count == 1
    assert not store.list_active_handoffs()
    checks = score_appointment(
        {"handoff": False},
        body=reply.body,
        intake=state,
        prior=None,
        active=False,
        authorized_targets=("desired_service",),
        expected_preferences=expected_customer_preferences(
            {"customer_message": customer, "preferences": {}}, None
        ),
        customer_message=customer,
    )
    assert all(checks.values())
