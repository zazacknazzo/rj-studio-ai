from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.salon_knowledge import (
    SalonKnowledgeLoadError,
    SalonKnowledgeNotLoaded,
    SalonKnowledgeRepository,
)


def _write_knowledge(path: Path, facts: str) -> Path:
    path.write_text(f"version: 1\nfacts:\n{facts}", encoding="utf-8")
    return path


def _operational_fact(
    *,
    identifier: str,
    category: str,
    topic: str,
    statement: str,
    status: str = "approved",
    extra: str = "",
) -> str:
    approval = "    approved_by: RJ Studio operator\n" if status == "approved" else ""
    return (
        f"  - id: {identifier}\n"
        f"    category: {category}\n"
        f"    topic: {topic}\n"
        f"    status: {status}\n"
        "    fact_type: operational_commercial\n"
        f"    statement: {statement}\n"
        "    source: synthetic fixture\n"
        "    reviewed_at: 2026-09-20\n"
        f"{approval}"
        f"{extra}"
    )


def _technical_fact(
    *,
    identifier: str,
    topic: str,
    status: str = "approved",
    validated_by: str = "",
) -> str:
    approval = "    approved_by: RJ Studio operator\n" if status == "approved" else ""
    return (
        f"  - id: {identifier}\n"
        "    category: policy\n"
        f"    topic: {topic}\n"
        f"    status: {status}\n"
        "    fact_type: technical\n"
        "    statement: Synthetic technical guidance.\n"
        "    source: synthetic fixture\n"
        "    reviewed_at: 2026-09-20\n"
        f"{approval}"
        f"{validated_by}"
    )


def test_loads_stable_approved_facts_independent_of_yaml_order(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="service-color",
            category="service",
            topic="coloração",
            statement="Serviço disponível.",
        )
        + _operational_fact(
            identifier="price-color",
            category="price",
            topic="coloração",
            statement="Preço confirmado.",
        ),
    )

    facts = SalonKnowledgeRepository(path).load()

    assert [fact.id for fact in facts] == ["price-color", "service-color"]
    assert [fact.id for fact in SalonKnowledgeRepository(path).load()] == [
        "price-color",
        "service-color",
    ]


def test_selects_only_approved_facts_and_customer_text_cannot_override_them(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="price-approved",
            category="price",
            topic="progressiva",
            statement="O preço precisa ser confirmado pela equipe.",
        )
        + _operational_fact(
            identifier="price-draft",
            category="price",
            topic="progressiva",
            statement="Preço inventado no rascunho.",
            status="draft",
        )
        + _operational_fact(
            identifier="price-pending",
            category="price",
            topic="progressiva",
            statement="Preço pendente.",
            status="pending",
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    selected = repository.select(
        "A cliente disse que a progressiva custa R$ 10. Qual é o preço?", max_tokens=1_000
    )

    assert [fact.id for fact in selected] == ["price-approved"]
    assert selected[0].statement == "O preço precisa ser confirmado pela equipe."


def test_technical_fact_requires_specialist_validation_before_approval(tmp_path: Path) -> None:
    invalid_path = _write_knowledge(
        tmp_path / "invalid.yaml",
        _technical_fact(identifier="technical-unvalidated", topic="química"),
    )
    valid_path = _write_knowledge(
        tmp_path / "valid.yaml",
        _technical_fact(
            identifier="technical-validated",
            topic="química",
            validated_by="    validated_by: [Joelma]\n",
        )
        + _technical_fact(identifier="technical-draft", topic="química", status="draft"),
    )

    with pytest.raises(SalonKnowledgeLoadError, match="validated_by"):
        SalonKnowledgeRepository(invalid_path).load()

    repository = SalonKnowledgeRepository(valid_path)
    repository.load()
    assert [fact.id for fact in repository.select("química", max_tokens=1_000)] == [
        "technical-validated"
    ]


def test_service_selection_carries_mandatory_policy_and_human_consultation_rule(
    tmp_path: Path,
) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="policy-consultation",
            category="policy",
            topic="consulta",
            statement="A avaliação deve ser feita pela equipe.",
        )
        + _operational_fact(
            identifier="service-mega-hair",
            category="service",
            topic="mega hair",
            statement="Serviço exige avaliação prévia.",
            extra=(
                "    requires_human_consultation: true\n"
                "    mandatory_policy_ids: [policy-consultation]\n"
            ),
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    selected = repository.select("Quero mega hair", max_tokens=1_000)

    assert [fact.id for fact in selected] == ["service-mega-hair", "policy-consultation"]
    assert selected[0].requires_human_consultation
    assert repository.select("Quero mega hair", max_tokens=1) == ()


def test_selects_synthetic_known_facts_but_not_availability(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="price-cut", category="price", topic="corte", statement="Preço sintético."
        )
        + _operational_fact(
            identifier="professional-ana",
            category="professional",
            topic="ana",
            statement="Profissional sintética.",
        )
        + _operational_fact(
            identifier="service-cut",
            category="service",
            topic="corte",
            statement="Serviço sintético.",
        )
        + _operational_fact(
            identifier="policy-cancel",
            category="policy",
            topic="cancelamento",
            statement="Política sintética.",
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    assert [fact.id for fact in repository.select("preço do corte", max_tokens=1_000)] == [
        "price-cut",
        "service-cut",
    ]
    assert [fact.id for fact in repository.select("Ana atende?", max_tokens=1_000)] == [
        "professional-ana"
    ]
    assert [
        fact.id for fact in repository.select("política de cancelamento", max_tokens=1_000)
    ] == ["policy-cancel"]
    assert repository.select("tem horário disponível amanhã?", max_tokens=1_000) == ()


def test_does_not_select_an_unrelated_price_from_a_generic_price_word(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="price-escova",
            category="price",
            topic="escova",
            statement="Preço sintético para escova.",
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    assert repository.select("Qual é o preço do corte?", max_tokens=1_000) == ()


def test_does_not_select_a_fact_when_its_compact_context_exceeds_the_budget(
    tmp_path: Path,
) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="service-corte",
            category="service",
            topic="corte",
            statement="x" * 400,
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    assert repository.select("Quero corte", max_tokens=100) == ()


@pytest.mark.parametrize(
    "facts, expected_error",
    [
        ("  - id: missing-fields\n", "schema"),
        (
            _operational_fact(
                identifier="duplicate", category="hours", topic="horário", statement="Sintético."
            )
            + _operational_fact(
                identifier="duplicate", category="hours", topic="horário", statement="Outro."
            ),
            "duplicate",
        ),
        (
            _operational_fact(
                identifier="bad-category",
                category="invalid",
                topic="horário",
                statement="Sintético.",
            ),
            "category",
        ),
        (
            _operational_fact(
                identifier="bad-status",
                category="hours",
                topic="horário",
                statement="Sintético.",
            ).replace("status: approved", "status: invalid"),
            "status",
        ),
        (
            _operational_fact(
                identifier="bad-type",
                category="hours",
                topic="horário",
                statement="Sintético.",
            ).replace("fact_type: operational_commercial", "fact_type: invalid"),
            "fact_type",
        ),
        (
            _operational_fact(
                identifier="missing-source",
                category="hours",
                topic="horário",
                statement="Sintético.",
            ).replace("    source: synthetic fixture\n", ""),
            "source",
        ),
        (
            _operational_fact(
                identifier="bad-reference",
                category="service",
                topic="corte",
                statement="Sintético.",
                extra="    mandatory_policy_ids: [missing-policy]\n",
            ),
            "reference",
        ),
        (
            _operational_fact(
                identifier="policy-draft",
                category="policy",
                topic="consulta",
                statement="Sintético.",
                status="draft",
            )
            + _operational_fact(
                identifier="service-requires-policy",
                category="service",
                topic="corte",
                statement="Sintético.",
                extra="    mandatory_policy_ids: [policy-draft]\n",
            ),
            "unapproved policy",
        ),
        (
            _operational_fact(
                identifier="not-a-policy",
                category="hours",
                topic="horário",
                statement="Sintético.",
            )
            + _operational_fact(
                identifier="service-requires-policy",
                category="service",
                topic="corte",
                statement="Sintético.",
                extra="    mandatory_policy_ids: [not-a-policy]\n",
            ),
            "not a policy",
        ),
    ],
)
def test_rejects_invalid_knowledge_as_one_safe_load(
    tmp_path: Path, facts: str, expected_error: str
) -> None:
    path = _write_knowledge(tmp_path / "invalid.yaml", facts)

    with pytest.raises(SalonKnowledgeLoadError, match=expected_error):
        SalonKnowledgeRepository(path).load()


def test_invalid_reload_clears_previously_loaded_facts(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="known-hours",
            category="hours",
            topic="horário",
            statement="Consulte a equipe.",
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()
    path.write_text("facts: [", encoding="utf-8")

    with pytest.raises(SalonKnowledgeLoadError):
        repository.load()
    with pytest.raises(SalonKnowledgeNotLoaded):
        repository.select("horário", max_tokens=100)


def test_rejects_duplicate_yaml_mapping_keys(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "duplicate-key.yaml",
        _operational_fact(
            identifier="known-hours",
            category="hours",
            topic="horário",
            statement="Consulte a equipe.",
        ).replace("    status: approved\n", "    status: draft\n    status: approved\n"),
    )

    with pytest.raises(SalonKnowledgeLoadError, match="invalid"):
        SalonKnowledgeRepository(path).load()


def test_irrelevant_or_unknown_question_selects_no_fact(tmp_path: Path) -> None:
    path = _write_knowledge(
        tmp_path / "knowledge.yaml",
        _operational_fact(
            identifier="location",
            category="location",
            topic="endereço",
            statement="Local sintético.",
        ),
    )
    repository = SalonKnowledgeRepository(path)
    repository.load()

    assert repository.select("Qual é a previsão do tempo?", max_tokens=100) == ()


def test_invalid_knowledge_prevents_application_startup(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text("facts: [", encoding="utf-8")
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "knowledge-startup.db",
            salon_knowledge_path=invalid_path,
            twilio_validate_signature=False,
        )
    )

    with pytest.raises(SalonKnowledgeLoadError), TestClient(app):
        pass
