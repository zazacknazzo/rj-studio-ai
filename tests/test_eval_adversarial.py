from pathlib import Path

from rj_studio_ai.evaluation import runner
from rj_studio_ai.evaluation.suite import load_suite

SUITE = Path(__file__).parents[1] / "docs/evals/V1"


def test_prohibited_unlisted_hour_is_detected_without_exact_answer_coupling(monkeypatch):
    real_finalize = runner.finalize_reply

    def contaminated(decision, *, customer_message, context):
        result = real_finalize(decision, customer_message=customer_message, context=context)
        if customer_message == "Que horas abre amanhã?":
            # Seed excludes 08h; a different invented hour must also fail.
            result = result.model_copy(
                update={"reply_text": result.reply_text + " Abrimos às 07h."}
            )
        return result

    monkeypatch.setattr(runner, "finalize_reply", contaminated)
    record = runner.dry_run(load_suite(SUITE), revision="631782a")
    assert record.summary.critical_failures.numerator > 0
    assert record.gates()["safety"] == "fail"
