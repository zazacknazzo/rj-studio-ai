from pathlib import Path

import yaml


def test_grounding_seed_covers_critical_truth_uncertainty_and_handoff_cases() -> None:
    document = yaml.safe_load(
        (Path(__file__).parents[1] / "docs/evals/V1/grounding-cases.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert document["version"] == 1
    cases = document["cases"]
    ids = {case["id"] for case in cases}
    assert len(ids) == len(cases)
    assert {
        "grounding-wrong-price-correct-ref",
        "grounding-price-requires-evaluation",
        "grounding-no-availability",
        "grounding-false-customer-price",
        "grounding-prompt-injection",
        "grounding-technical-human-required",
        "grounding-mandatory-policy",
    }.issubset(ids)
    assert all("customer_message" in case and "synthetic_knowledge" in case for case in cases)
    assert any("mandatory_handoff" in case.get("checks", []) for case in cases)
    assert any("uncertainty_or_handoff" in case.get("checks", []) for case in cases)
