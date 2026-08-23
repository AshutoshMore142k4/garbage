"""D1 evaluation (phases.md Phase 8): runs three sequential batches, letting rules learned from
earlier batches' resolved exceptions shrink how often later batches need L2, and charts the
resulting decline to `eval/output/invocation_decay.png`.

**Why this uses its own generated dataset, not `data/samples`.** `data/samples`'s realistic,
mostly-easy mix (plan.md's own production-shaped fixture) only contains a handful of instances
per chaos category (`chaos_min_count` there is small) -- checked directly: only 2 bank lines in
the whole 300-line fixture escalate with a single, cleanly-learnable correct answer (the
DATE_SKEW_BOUNDARY "just past the tolerance window" half), nowhere near enough to demonstrate a
rule reaching the `hits >= 3` promotion bar across 3 sequential batches. This script instead
generates its own dataset via `data.generator.generate` with a higher `chaos_min_count`, purely
so there is *enough* repeated volume of the one genuinely-learnable escalation pattern in this
project's design (see `d1_rule_learning/propose.py`'s module docstring) to actually exercise and
measure the rule-learning loop -- a disclosed methodology choice, not a hidden one, and still
fully seeded/deterministic/$0 to reproduce.

**Why a human is simulated, not live.** No session in this project has ever had a live operator
or Anthropic credentials (PROGRESS.md/BROKE.md Phases 0/4) -- `propose.ResolvedException` is
built from ground truth's own known-correct answer, standing in for "a human resolved this
exception," the same substitution `l3_calibrate_gate/decisions.py` already makes for the L2 call
itself.

**Why "cost per 1,000" is an estimate, not a measured spend.** With no live token counter
available, `_approx_cost_per_call` reuses `client.py`'s exact real pricing table
(`PRICE_PER_MTOK_USD`) and worst-case output budget (`MAX_TOKENS`), substituting a documented
chars/4 approximation for the one missing piece -- an actual `count_tokens` call. Cost is
directly proportional to invocation count here (every call uses the same bounded prompt shape),
so this number moves in lockstep with the invocation rate by construction, not by coincidence.
"""
from __future__ import annotations

import json
import math
import random
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data.generator import generate, write_dataset
from ledgerguard.close import DEFAULT_AUTHORITY_LIMIT_PAISE
from ledgerguard.d1_rule_learning.compile import compile_rule
from ledgerguard.d1_rule_learning.promote import promote_rule, spec_id
from ledgerguard.d1_rule_learning.propose import ResolvedException, propose_rule
from ledgerguard.d1_rule_learning.validate import validate_rule
from ledgerguard.l0_normalize.normalize import normalize_timestamp
from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments
from ledgerguard.l2_llm_triage.client import MAX_TOKENS, PRICE_PER_MTOK_USD, TriageClient
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import decisions_for
from ledgerguard.l3_calibrate_gate.gate import GateInput, gate
from ledgerguard.l4_anomaly.detectors import detect_anomalies
from ledgerguard.l5_executor.authority import AuthorityInput, authorize
from ledgerguard.models import LearnedRule

DEFAULT_OUTPUT_DIR = Path("eval/output")
N_BATCHES = 3

DEFAULT_SEED = 42
DEFAULT_TOTAL_BANK_LINES = 900
DEFAULT_CHAOS_MIN_COUNT = 60  # see module docstring: data/samples doesn't have enough volume
DEFAULT_SHUFFLE_SEED = 0


@dataclass
class BatchStats:
    batch_index: int
    total: int
    invocation_count: int
    invocation_rate: float
    auto_post_count: int
    auto_post_correct: int
    precision_auto_post: float
    promoted_this_batch: list[str]
    cost_usd: float


def _approx_cost_per_call(model: str = "claude-opus-5") -> float:
    system_prompt = Path("prompts/residual_triage_v1.md").read_text(encoding="utf-8")
    representative_bank_line = {
        "credit_paise": 48_20_000,
        "value_date": "2026-03-07T00:00:00Z",
        "narration": "APEXRETAIL7F3A2C",
    }
    representative_candidates = [
        {
            "payment_id": f"pay_synth_{i:05d}",
            "order_id": f"order_synth_{i:05d}",
            "net_paise": 1_00_000 * i,
            "captured_at": "2026-03-05T00:00:00Z",
        }
        for i in range(1, 6)
    ]
    user_content = TriageClient._build_user_content(representative_bank_line, representative_candidates)
    approx_input_tokens = len(system_prompt + user_content) / 4  # documented approximation; see module docstring
    price = PRICE_PER_MTOK_USD.get(model, PRICE_PER_MTOK_USD["claude-opus-5"])
    return approx_input_tokens / 1_000_000 * price["input"] + MAX_TOKENS / 1_000_000 * price["output"]


def _sequential_batches(
    bank_lines: list[dict], ground_truth: dict, n_batches: int = N_BATCHES, shuffle_seed: int = 0
) -> list[list[dict]]:
    """Train+validation bank lines only -- holdout is never touched (same discipline as L3's
    calibrator), split into `n_batches` roughly-equal, deterministically-shuffled slices, so a
    rule learned from an earlier batch's exceptions can only ever help a later one.

    Deliberately *not* sorted by `value_date`: a settlement whose group spans several payments
    (SPLIT_SETTLEMENT) uses the *latest* member's date, which is an order statistic that skews
    toward the end of the date range as group size grows -- sorting batches by value_date would
    have concentrated that category's (already-known, Phase 3-era, out-of-scope-here) date-
    tolerance escalations disproportionately into the last batch, confounding "invocation rate
    changed" with "batch composition changed" rather than "rules were learned." A fixed-seed
    shuffle gives every batch a representative cross-section of categories instead, matching
    "three sequential customer-facing batches" (each an ordinary day's mixed traffic) rather than
    "three time-sorted slices of one long history."
    """
    eligible = [row for row in bank_lines if ground_truth[row["id"]]["split"] in ("train", "validation")]
    rng = random.Random(shuffle_seed)
    shuffled = list(eligible)
    rng.shuffle(shuffled)
    batch_size = math.ceil(len(shuffled) / n_batches)
    return [shuffled[i * batch_size : (i + 1) * batch_size] for i in range(n_batches)]


def _resolved_exceptions_from_batch(batch_decisions, bank_lines_by_id, payments_by_order_id, ground_truth):
    resolved = []
    for d in batch_decisions:
        if d.order_ids:
            continue  # already resolved by something -- not an exception at all
        expected = ground_truth[d.bank_line_id].get("correct_match")
        if expected is None or len(expected["order_ids"]) != 1:
            continue  # no correct answer to learn (NO_MATCH_EXISTS), or a multi-order group
        order_id = expected["order_ids"][0]
        payment = payments_by_order_id.get(order_id)
        if payment is None:
            continue
        row = bank_lines_by_id[d.bank_line_id]
        resolved.append(
            ResolvedException(
                bank_line_id=d.bank_line_id,
                narration=row["narration"],
                credit_paise=int(row["credit_paise"]),
                value_date=normalize_timestamp(row["value_date"]),
                chosen_payment_id=payment.payment_id,
                chosen_order_id=order_id,
                chosen_captured_at=payment.captured_at,
            )
        )
    return resolved


def run_rule_learning_eval(
    seed: int = DEFAULT_SEED,
    total_bank_lines: int = DEFAULT_TOTAL_BANK_LINES,
    chaos_min_count: int = DEFAULT_CHAOS_MIN_COUNT,
    n_batches: int = N_BATCHES,
    shuffle_seed: int = DEFAULT_SHUFFLE_SEED,
) -> list[BatchStats]:
    dataset = generate(seed=seed, total_bank_lines=total_bank_lines, chaos_min_count=chaos_min_count)
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        write_dataset(dataset, data_dir)
        bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
        payments = load_ledger_payments(data_dir / "internal_ledger.csv")
        ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    payments_by_order_id = {p.order_id: p for p in payments}
    bank_lines_by_id = {row["id"]: row for row in bank_lines}

    # Fit the calibrator/threshold once, on the full train+validation set resolved with built-in
    # rules only -- so later rule promotions change what gets auto-posted, never the yardstick
    # used to judge it (re-fitting per batch would conflate "the rate fell" with "the bar moved").
    baseline_decisions = decisions_for(bank_lines, payments, ground_truth)
    validation_baseline = [d for d in baseline_decisions if d.split == "validation"]
    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation_baseline], [d.correct for d in validation_baseline])
    calibrated_baseline = calibrator.predict_proba([d.features for d in validation_baseline])
    threshold = find_optimal_threshold(
        [
            CostDecision(credit_paise=d.credit_paise, calibrated_confidence=c, correct=d.correct)
            for d, c in zip(validation_baseline, calibrated_baseline)
        ]
    )

    batches = _sequential_batches(bank_lines, ground_truth, n_batches, shuffle_seed=shuffle_seed)
    cost_per_call = _approx_cost_per_call()

    promoted_rules: list[LearnedRule] = []
    seen_spec_ids: set[str] = set()
    stats: list[BatchStats] = []

    for i, batch_rows in enumerate(batches):
        extra_rules = tuple(compile_rule(r.spec, r.rule_id) for r in promoted_rules)
        decisions = decisions_for(batch_rows, payments, ground_truth, extra_rules=extra_rules)
        calibrated = calibrator.predict_proba([d.features for d in decisions])

        anomalies_by_bank_line = defaultdict(list)
        for flag in detect_anomalies(decisions, batch_rows, payments):
            if flag.bank_line_id:
                anomalies_by_bank_line[flag.bank_line_id].append(flag)

        invocation_count = sum(1 for d in decisions if d.resolver == "L2_LLM")
        auto_post_count = 0
        auto_post_correct = 0

        for d, conf in zip(decisions, calibrated):
            gate_outcome = gate(
                GateInput(has_candidate=bool(d.order_ids), calibrated_confidence=conf, existing_reason_code=d.reason_code),
                threshold=threshold,
            )
            final_action = authorize(
                AuthorityInput(
                    gate_action=gate_outcome.action,
                    amount_paise=d.credit_paise,
                    authority_limit_paise=DEFAULT_AUTHORITY_LIMIT_PAISE,
                    has_anomaly=bool(anomalies_by_bank_line.get(d.bank_line_id)),
                )
            )
            if final_action == "AUTO_POST":
                auto_post_count += 1
                if d.correct:
                    auto_post_correct += 1

        resolved_exceptions = _resolved_exceptions_from_batch(decisions, bank_lines_by_id, payments_by_order_id, ground_truth)

        promoted_this_batch = []
        for resolved in resolved_exceptions:
            spec = propose_rule(resolved)
            sid = spec_id(spec)
            if sid in seen_spec_ids:
                continue
            seen_spec_ids.add(sid)
            result = validate_rule(spec, bank_lines, payments, ground_truth)
            rule = promote_rule(spec, proposed_from=resolved.bank_line_id, result=result, promoted_at=f"batch-{i}")
            if rule.status == "PROMOTED":
                promoted_rules.append(rule)
                promoted_this_batch.append(rule.rule_id)

        total = len(decisions)
        stats.append(
            BatchStats(
                batch_index=i,
                total=total,
                invocation_count=invocation_count,
                invocation_rate=invocation_count / total if total else 0.0,
                auto_post_count=auto_post_count,
                auto_post_correct=auto_post_correct,
                precision_auto_post=(auto_post_correct / auto_post_count) if auto_post_count else 1.0,
                promoted_this_batch=promoted_this_batch,
                cost_usd=invocation_count * cost_per_call,
            )
        )

    return stats


def plot_invocation_decay(stats: list[BatchStats], out_path: Path) -> None:
    batches = [s.batch_index + 1 for s in stats]
    invocation_pct = [s.invocation_rate * 100 for s in stats]
    precision_pct = [s.precision_auto_post * 100 for s in stats]

    fig, ax1 = plt.subplots(figsize=(6, 4.5))
    ax1.plot(batches, invocation_pct, marker="o", color="tab:red", label="LLM invocation rate (%)")
    ax1.set_xlabel("Batch")
    ax1.set_ylabel("LLM invocation rate (%)", color="tab:red")
    ax1.set_xticks(batches)
    ax1.set_ylim(0, max(invocation_pct + [1.0]) * 1.2)

    ax2 = ax1.twinx()
    ax2.plot(batches, precision_pct, marker="s", color="tab:blue", label="Precision on AUTO_POST (%)")
    ax2.set_ylabel("Precision on AUTO_POST (%)", color="tab:blue")
    ax2.set_ylim(0, 105)

    ax1.set_title("D1: LLM invocation rate falls while precision holds")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    stats = run_rule_learning_eval()
    out_path = DEFAULT_OUTPUT_DIR / "invocation_decay.png"
    plot_invocation_decay(stats, out_path)

    print(f"D1 rule learning, seed={DEFAULT_SEED}, chaos_min_count={DEFAULT_CHAOS_MIN_COUNT}:")
    for s in stats:
        cost_per_1000 = (s.cost_usd / s.total * 1000) if s.total else 0.0
        print(
            f"  batch {s.batch_index + 1}: {s.total} bank lines, "
            f"LLM invocations {s.invocation_count} ({s.invocation_rate:.1%}), "
            f"AUTO_POST {s.auto_post_count} (precision {s.precision_auto_post:.1%}), "
            f"cost/1000 ${cost_per_1000:.4f}, promoted this batch: {s.promoted_this_batch or 'none'}"
        )
    print(f"  chart written to {out_path}")


if __name__ == "__main__":
    main()
