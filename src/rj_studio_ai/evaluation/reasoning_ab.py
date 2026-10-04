"""Authorized, serial medium/low experiment. Synthetic data; no Phase B path."""

import argparse
import json
import logging
import secrets
import subprocess
from decimal import Decimal
from pathlib import Path

import httpx
from dotenv import dotenv_values

from rj_studio_ai.evaluation.live import SMOKE_CASES, live_summary, run_live_phase
from rj_studio_ai.evaluation.live_billing import (
    LIVE_INPUT_RESERVATION_MARGIN,
    LIVE_INPUT_TOKEN_LIMIT,
    LIVE_MAX_OUTPUT_TOKENS,
    BudgetLedger,
    LivePricing,
)
from rj_studio_ai.evaluation.records import PRODUCT_E2E_LATENCY_LIMIT_MS, check_privacy, fingerprint
from rj_studio_ai.evaluation.suite import load_suite

CAP = Decimal("0.30")
EFFORTS = ("medium", "low")


def admit_next_pair(ledger):
    """No future-pair reservations. The input preflight enforces this per-call ceiling."""
    if ledger.blocked or ledger.outstanding is not None:
        raise ValueError("unresolved_submission")
    bound = (
        2
        * (
            (LIVE_INPUT_TOKEN_LIMIT + LIVE_INPUT_RESERVATION_MARGIN)
            * ledger.pricing.cache_write_usd_per_million
            + LIVE_MAX_OUTPUT_TOKENS * ledger.pricing.output_usd_per_million
        )
        / 1_000_000
    )
    actual = sum(ledger.charged.values())
    if actual + bound > min(CAP, ledger.global_cap, ledger.phase_a_cap):
        raise ValueError("pair_budget_exhausted")
    return {"actual_spend_before_usd": str(actual), "maximum_safe_reservation_usd": str(bound)}


class PairRequests:
    """Hash the actual request before send; only effort may differ between arms."""

    def __init__(self):
        self.effort = "medium"
        self.hashes = {}
        self.seen = set()

    def check(self, request):
        path = request.url.path
        key = (self.effort, path)
        if key in self.seen or path not in {"/v1/responses/input_tokens", "/v1/responses"}:
            raise ValueError("ab_configuration_mismatch")
        self.seen.add(key)
        payload = json.loads(request.content)
        if payload.pop("reasoning") != {"effort": self.effort}:
            raise ValueError("ab_configuration_mismatch")
        digest = fingerprint(payload)
        if self.effort == "medium":
            self.hashes[path] = digest
        elif self.hashes.get(path) != digest:
            raise ValueError("ab_configuration_mismatch")


def write_json(path, value):
    check_privacy(value)
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def blind_packet(output, pairs):
    """Randomize display labels independently; keep effort mapping outside the form."""
    lines = [
        "# Revisão humana — comparação de respostas",
        "",
        "Notas em branco. Sem juiz automático.",
        "",
    ]
    mapping = []
    for number, pair in enumerate(pairs, 1):
        arms = list(EFFORTS)
        if secrets.randbelow(2):
            arms.reverse()
        lines += [f"## CASO {number}", "", f"Customer: {pair['medium']['scenario']}", ""]
        row = {"case_id": pair["case_id"]}
        for label, effort in zip(("A", "B"), arms, strict=True):
            lines += [f"Response {label}:", "", pair[effort]["response"], ""]
            row[label] = effort
        lines += [
            "Avaliação manual (A / B / equivalente; sem pontuação automática):",
            "",
            "- Entendimento e relevância: ____",
            "- Clarificação: ____",
            "- Iniciativa comercial: ____",
            "- Autonomia e condução: ____",
            "- Naturalidade e persona Lívia: ____",
            "- Fallback inadequado: ____",
            "",
            "Observação livre: ____________________",
            "",
        ]
        mapping.append(row)
    text = "\n".join(lines)
    check_privacy({"review": text})
    with (output / "human-review-formulario.md").open("x", encoding="utf-8") as file:
        file.write(text)
    write_json(output / "human-review-mapping.json", mapping)


def arm_summary(records, pricing):
    samples = tuple(s for record in records for s in record.samples)
    contracts = tuple(c for record in records for c in record.contracts)
    summary = live_summary(samples, contracts, pricing)
    summary["model_max_ms"] = max((a.latency_ms for s in samples for a in s.attempts), default=None)
    summary["observed_e2e_max_ms"] = max(
        (s.e2e_latency_ms for s in samples if s.attempts), default=None
    )
    summary["observed_e2e_above_8s"] = sum(
        s.e2e_latency_ms > PRODUCT_E2E_LATENCY_LIMIT_MS for s in samples if s.attempts
    )
    summary["reasoning_tokens_per_reply"] = (
        summary["reasoning_tokens"] / summary["completed_model_replies"]
        if summary["reasoning_tokens"] is not None and summary["completed_model_replies"]
        else None
    )
    p95 = summary["billable_e2e_p95_ms"]
    summary["official_latency_gate"] = (
        "pending_evidence"
        if p95 is None or summary["unknown_billing_attempts"]
        else "pass"
        if p95 <= PRODUCT_E2E_LATENCY_LIMIT_MS
        else "fail"
    )
    return summary


def comparison_deltas(arms, completed_pairs):
    """Low minus medium; unknown values stay unknown, partial populations are explicit."""
    medium, low = (arms[effort] for effort in EFFORTS)

    def difference(control, candidate):
        return candidate - control if control is not None and candidate is not None else None

    values = {
        key: difference(medium[key], low[key])
        for key in (
            "model_p50_ms",
            "model_p95_ms",
            "model_max_ms",
            "billable_e2e_p50_ms",
            "billable_e2e_p95_ms",
            "observed_e2e_max_ms",
            "observed_e2e_above_8s",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reasoning_tokens_per_reply",
            "estimated_cost_usd",
            "cost_per_1000_replies_usd",
        )
    }
    values["matched_population"] = all(
        arm["completed_model_replies"] == arm["live_calls"] == completed_pairs
        for arm in arms.values()
    )
    values["completed_pairs"] = completed_pairs
    values["population"] = "all_observed_arm_attempts"
    for key in ("p50_ms", "p95_ms"):
        component = "production_equivalent_e2e_ms"
        values["production_equivalent_" + key] = difference(
            medium["latency_breakdown"]["components"][component][key],
            low["latency_breakdown"]["components"][component][key],
        )
    values["check_differences"] = {
        metric: {
            key: difference(medium["metrics"].get(metric, {}).get(key), ratio[key])
            for key in ("numerator", "denominator")
        }
        for metric, ratio in low["metrics"].items()
    }
    values["critical_failure_delta"] = (
        low["critical_failures"]["numerator"] - medium["critical_failures"]["numerator"]
    )
    return values


def recommendation(arms, completed_pairs, stop_effort, stop_code):
    if stop_effort == "low" and stop_code == "critical_failure":
        return "MEDIUM WINS", "LOW REJECT: critical safety failure"
    if completed_pairs != len(SMOKE_CASES):
        return "INCONCLUSIVE", "insufficient completed pairs"
    medium, low = (arms[effort] for effort in EFFORTS)
    if any(r["numerator"] < r["denominator"] for r in low["metrics"].values()):
        return "INCONCLUSIVE", "product-check differences require human review"
    gain = 1 - Decimal(str(low["billable_e2e_p95_ms"])) / Decimal(
        str(medium["billable_e2e_p95_ms"])
    )
    if gain >= Decimal("0.20"):
        return "LOW WINS", "provisional technical result; human conversational review pending"
    if gain < Decimal("0.05"):
        return "MEDIUM WINS", "negligible observed latency gain; small sample"
    return "INCONCLUSIVE", "latency improvement below predeclared material threshold"


def execute_ab(suite, *, api_key, output, revision, transport=None, progress=None):
    cases = {case.contract.case_id: case for case in suite.cases}
    if any(
        identifier not in cases or cases[identifier].contract.turns != 1
        for identifier in SMOKE_CASES
    ):
        raise ValueError("ab_invalid_case_plan")
    output.mkdir(mode=0o700)
    pricing = LivePricing.load()
    ledger = BudgetLedger(output / "spend.jsonl", pricing, phase_a_cap=CAP, global_cap=CAP)
    records = {effort: [] for effort in EFFORTS}
    pairs, admissions = [], []
    stop_code = stop_effort = None
    try:
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            for number, identifier in enumerate(SMOKE_CASES, 1):
                try:
                    admission = admit_next_pair(ledger)
                except ValueError as error:
                    stop_code = str(error)
                    break
                admission.update(case_id=identifier)
                admissions.append(admission)
                write_json(output / f"pair-{number:02}-admission.json", admission)
                comparison = PairRequests()
                client.event_hooks["request"] = [comparison.check]
                pair = {"case_id": identifier}
                for effort in EFFORTS:
                    comparison.effort = effort
                    directory = output / f"{number:02}-{effort}"
                    directory.mkdir(mode=0o700)
                    record, packet = run_live_phase(
                        suite,
                        [(identifier, 1)],
                        "A",
                        api_key=api_key,
                        output=directory,
                        revision=revision,
                        ledger=ledger,
                        client=client,
                        reasoning_effort=effort,
                    )
                    write_json(directory / "trusted-response.json", packet)
                    records[effort].append(record)
                    if progress:
                        progress(
                            {
                                "case": number,
                                "effort": effort,
                                "status": record.status,
                                "stop_code": record.stop_code,
                                "settled_spend_usd": str(sum(ledger.charged.values())),
                            }
                        )
                    if record.status != "completed" or len(packet) != 1 or ledger.blocked:
                        stop_code = record.stop_code or "ab_incomplete_pair"
                        stop_effort = effort
                        break
                    pair[effort] = packet[0]
                if stop_code:
                    break
                admission["spend_after_usd"] = str(sum(ledger.charged.values()))
                admission["requests_match_except_effort"] = True
                pairs.append(pair)
        arms = {effort: arm_summary(records[effort], pricing) for effort in EFFORTS}
        classification, reason = recommendation(arms, len(pairs), stop_effort, stop_code)
        report = {
            "revision": revision,
            "cap_usd": str(CAP),
            "actual_cost_usd": None if ledger.blocked else str(sum(ledger.charged.values())),
            "budget_upper_bound_usd": str(ledger.upper_bound_usd),
            "completed_pairs": len(pairs),
            "stop_code": stop_code,
            "stop_effort": stop_effort,
            "admissions": admissions,
            "arms": arms,
            "low_minus_medium": comparison_deltas(arms, len(pairs)),
            "recommendation": classification,
            "recommendation_reason": reason,
            "human_review": "pending",
            "phase_b_executed": False,
            "ticket_12": "in-progress",
            "agentic_surface": "PASS WITH NOTES",
        }
        write_json(output / "report.json", report)
        write_json(output / "trusted-responses.json", pairs)
        if len(pairs) >= 6:
            blind_packet(output, pairs)
        return report
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error("explicit paid authorization required")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        parser.error("clean working tree required")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    logging.getLogger("dotenv.main").disabled = True
    key = dotenv_values(".env").get("OPENAI_API_KEY")
    if not key:
        parser.error("OPENAI_API_KEY absent")
    try:
        report = execute_ab(
            load_suite(Path("docs/evals/V1")),
            api_key=key,
            output=args.output,
            revision=revision,
            progress=lambda row: print(json.dumps(row), flush=True),
        )
    except Exception:
        print("ab_execution_failed; inspect local sanitized records; no automatic resume")
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("completed_pairs", "actual_cost_usd", "stop_code", "recommendation")
            }
        )
    )


if __name__ == "__main__":
    main()
