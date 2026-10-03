from decimal import Decimal

import pytest

from rj_studio_ai.evaluation.live_billing import (
    BudgetLedger,
    LivePricing,
    Usage,
    UsageValidationError,
)


def test_cached_and_cache_write_tokens_are_charged_once():
    pricing = LivePricing.load()
    usage = Usage(
        input_tokens=1000,
        cached_tokens=200,
        cache_write_tokens=300,
        output_tokens=100,
        reasoning_tokens=40,
    )
    assert pricing.cost(usage) == Decimal("0.002770")


def test_reservation_precedes_submission_and_survives_restart(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = BudgetLedger(path, LivePricing.load(), phase_a_cap=Decimal("0.01"))
    reservation = ledger.reserve("A", input_bound=1000, output_bound=200)
    assert reservation == Decimal("0.0045")
    ledger.close()
    reopened = BudgetLedger(path, LivePricing.load(), phase_a_cap=Decimal("0.01"))
    with pytest.raises(ValueError, match="unresolved_submission"):
        reopened.reserve("A", input_bound=1000, output_bound=200)
    reopened.close()


def test_phase_cap_blocks_next_submission_and_unknown_usage_keeps_reservation(tmp_path):
    ledger = BudgetLedger(
        tmp_path / "spend.jsonl", LivePricing.load(), phase_a_cap=Decimal("0.0045")
    )
    reserved = ledger.reserve("A", input_bound=1000, output_bound=200)
    assert ledger.settle(None) is None
    assert ledger.upper_bound_usd == reserved
    with pytest.raises(ValueError, match="unresolved_submission"):
        ledger.reserve("A", input_bound=1, output_bound=1)
    ledger.close()


def test_phase_and_global_caps_are_shared_not_reset_between_phases(tmp_path):
    ledger = BudgetLedger(
        tmp_path / "spend.jsonl",
        LivePricing.load(),
        phase_a_cap=Decimal("0.005"),
        global_cap=Decimal("0.006"),
    )
    ledger.reserve("A", input_bound=1000, output_bound=200)
    ledger.settle(
        Usage(
            input_tokens=1000,
            cached_tokens=0,
            cache_write_tokens=0,
            output_tokens=200,
            reasoning_tokens=200,
        )
    )
    with pytest.raises(ValueError, match="budget_exhausted"):
        ledger.reserve("A", input_bound=1000, output_bound=200)
    with pytest.raises(ValueError, match="budget_exhausted"):
        ledger.reserve("B", input_bound=1000, output_bound=200)
    ledger.close()


def test_wrong_pricing_and_impossible_usage_are_rejected():
    with pytest.raises(ValueError):
        LivePricing.model_validate(
            {**LivePricing.load().model_dump(), "input_usd_per_million": "6"}
        )
    with pytest.raises(ValueError, match="usage_input_breakdown"):
        Usage(
            input_tokens=10,
            cached_tokens=8,
            cache_write_tokens=8,
            output_tokens=10,
            reasoning_tokens=0,
        )


def test_authorized_output_ceiling_is_reserved_and_cannot_silently_increase(tmp_path):
    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    with pytest.raises(ValueError, match="invalid_reservation"):
        ledger.reserve("A", input_bound=1000, output_bound=513)
    assert ledger.reserve("A", input_bound=1000, output_bound=512) == Decimal("0.00762")
    ledger.close()


@pytest.mark.parametrize("output_details", [None, {}, {"reasoning_tokens": None}])
def test_missing_reasoning_breakdown_is_unknown_and_does_not_change_exact_pricing(output_details):
    usage = Usage.from_response(
        {
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 100,
                "total_tokens": 1100,
                "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
                "output_tokens_details": output_details,
            }
        }
    )
    assert usage.reasoning_tokens is None
    assert usage.output_tokens == 100
    assert LivePricing.load().cost(usage) == Decimal("0.002770")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"input_tokens": None}, "usage_input_tokens_missing"),
        ({"output_tokens": None}, "usage_output_tokens_missing"),
        ({"total_tokens": None}, "usage_total_tokens_missing"),
        ({"input_tokens_details": None}, "usage_cache_breakdown_missing"),
        ({"input_tokens_details": {"cache_write_tokens": 0}}, "usage_cached_tokens_missing"),
        ({"input_tokens_details": {"cached_tokens": 0}}, "usage_cache_write_tokens_missing"),
        ({"input_tokens_details": []}, "usage_invalid_shape"),
        ({"output_tokens_details": []}, "usage_invalid_shape"),
        ({"input_tokens": True}, "usage_count_invalid"),
        ({"input_tokens": "1000"}, "usage_count_invalid"),
        ({"output_tokens": -1}, "usage_count_invalid"),
        ({"total_tokens": 1099}, "usage_total_mismatch"),
        (
            {"input_tokens_details": {"cached_tokens": 700, "cache_write_tokens": 400}},
            "usage_input_breakdown",
        ),
        ({"output_tokens_details": {"reasoning_tokens": 101}}, "usage_output_breakdown"),
    ],
)
def test_required_accounting_fields_and_invariants_have_controlled_failure_codes(changes, code):
    data = {
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
            "output_tokens_details": {"reasoning_tokens": 40},
            **changes,
        }
    }
    with pytest.raises(UsageValidationError) as error:
        Usage.from_response(data)
    assert error.value.code == code
    assert str(error.value) == code
