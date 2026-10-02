from decimal import Decimal

import pytest

from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing, Usage


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
