from pathlib import Path

import yaml

from rj_studio_ai.llm_decision import Intent


def test_synthetic_intent_seed_covers_the_approved_catalog_and_availability_guard() -> None:
    document = yaml.safe_load(
        (Path(__file__).parents[1] / "docs/evals/V1/intent-cases.yaml").read_text(encoding="utf-8")
    )

    assert document["version"] == 1
    cases = document["cases"]
    covered_intents = {intent for case in cases for intent in case["expected_intents"]}
    assert covered_intents == {intent.value for intent in Intent}
    availability_cases = [
        case for case in cases if "appointment_interest" in case["expected_intents"]
    ]
    assert all(
        "confirmed_availability" in case.get("forbidden_claims", []) for case in availability_cases
    )
    assert any(len(case["expected_intents"]) > 1 for case in cases)
