from pathlib import Path

import pytest
import yaml

from rj_studio_ai.evaluation.suite import load_suite

SUITE = Path(__file__).parents[1] / "docs/evals/V1"


def test_suite_indexes_previous_seeds_and_context_handoff_gaps():
    suite = load_suite(SUITE)
    assert len(suite.cases) == 53
    kinds = {case.kind for case in suite.cases}
    assert kinds == {"intent", "persona", "grounding", "appointment", "handoff", "context"}
    assert sum(case.kind == "grounding" for case in suite.cases) == 13
    assert sum(case.kind == "appointment" for case in suite.cases) == 13
    assert all(scenario for scenario in suite.critical_scenarios.values())
    assert len(suite.critical_scenarios) == 11
    assert suite.rubric["version"] == "livia-naturalness-v1"
    assert len(suite.rubric["dimensions"]) == 4


@pytest.mark.parametrize(
    "bad_data",
    [
        {"source_type": "real_customer"},
        {"customer_phone": "+5511999998888"},
        {"customer_message": "Use sk-ant-test-credential"},
        {"customer_message": "Envie para test@example.com"},
        {"customer_message": "Telefone +55.11.99999.8888"},
        {"customer_name": "Real Customer"},
    ],
)
def test_unapproved_customer_provenance_or_pii_fixture_is_rejected(tmp_path, bad_data):
    import shutil

    shutil.copytree(SUITE, tmp_path / "suite")
    path = tmp_path / "suite/intent-cases.yaml"
    data = yaml.safe_load(path.read_text())
    if "source_type" in bad_data:
        data.update(bad_data)
    else:
        data["cases"][0].update(bad_data)
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_suite(tmp_path / "suite")


@pytest.mark.parametrize("name", ["grounding-cases.yaml", "context-cases.yaml"])
def test_nested_customer_metadata_is_rejected(tmp_path, name):
    import shutil

    shutil.copytree(SUITE, tmp_path / "suite")
    path = tmp_path / "suite" / name
    data = yaml.safe_load(path.read_text())
    data["cases"][0]["expected"]["customer_name"] = "Synthetic Named Person"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_suite(tmp_path / "suite")


@pytest.mark.parametrize("field", ["reply_parts", "critical_claims", "appointment_preferences"])
def test_nested_proposal_customer_metadata_is_rejected_at_suite_load(tmp_path, field):
    import shutil

    shutil.copytree(SUITE, tmp_path / "suite")
    path = tmp_path / "suite/grounding-cases.yaml"
    data = yaml.safe_load(path.read_text())
    proposal = data["cases"][0]["proposal"]
    if field == "appointment_preferences":
        proposal[field] = {"customer_name": "Synthetic Private Name"}
    elif field == "critical_claims":
        proposal[field] = [
            {
                "fact_type": "price",
                "value": "R$ 120,00",
                "knowledge_ref": "price-corte",
                "customer_name": "Synthetic Private Name",
            }
        ]
    else:
        proposal[field][0]["customer_name"] = "Synthetic Private Name"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_suite(tmp_path / "suite")
