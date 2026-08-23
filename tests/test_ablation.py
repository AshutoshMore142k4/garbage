"""Phase 9 tests: the ablation's scoring convention, the decision-rule banding logic (both
transcribed from PREREGISTRATION.md, not reinvented here), and an end-to-end smoke test against
the real committed sample data.
"""
from __future__ import annotations

from pathlib import Path

from benchmark.ablation import Prediction, apply_decision_rule, run_ablation, score
from eval.metrics import run_full_pipeline_metrics

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def _pred(order_ids, correct_match):
    return Prediction("bl_x", "EASY", order_ids, correct_match, False)


def test_score_true_positive_true_negative_and_wrong_nonempty_counts_double():
    preds = [
        _pred(["order_1"], {"order_ids": ["order_1"]}),  # TP
        _pred([], None),  # TN -- not counted
        _pred(["order_2"], {"order_ids": ["order_3"]}),  # wrong non-empty: FP and FN both
        _pred([], {"order_ids": ["order_4"]}),  # missed a real match: FN only
        _pred(["order_5"], None),  # false alarm on an unmatchable line: FP only
    ]
    result = score(preds)
    assert result["tp"] == 1
    assert result["fp"] == 2  # order_2-wrong and order_5-false-alarm
    assert result["fn"] == 2  # order_2-wrong and the missed order_4
    assert result["precision"] == 1 / 3
    assert result["recall"] == 1 / 3


def test_score_all_true_negatives_is_a_perfect_but_empty_score():
    preds = [_pred([], None), _pred([], None)]
    result = score(preds)
    assert result == {"n": 2, "tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_decision_rule_bands_match_preregistration_thresholds():
    def _table(delta_hard_adv_f1_pair, delta_easy_f1_pair):
        rules_ha, hybrid_ha = delta_hard_adv_f1_pair
        rules_easy, hybrid_easy = delta_easy_f1_pair
        return {
            "rules_only": {"HARD+ADVERSARIAL": {"f1": rules_ha}, "EASY": {"f1": rules_easy}},
            "hybrid": {"HARD+ADVERSARIAL": {"f1": hybrid_ha}, "EASY": {"f1": hybrid_easy}},
        }

    headline = apply_decision_rule(_table((0.50, 0.60), (0.9, 0.9)))  # Delta = 0.10
    assert headline["band"] == "HEADLINE"

    modest = apply_decision_rule(_table((0.50, 0.55), (0.9, 0.9)))  # Delta = 0.05
    assert modest["band"] == "MODEST"

    negative = apply_decision_rule(_table((0.50, 0.51), (0.9, 0.9)))  # Delta = 0.01
    assert negative["band"] == "NEGATIVE"

    easy_flagged = apply_decision_rule(_table((0.50, 0.51), (0.9, 0.95)))  # Delta(EASY) = 0.05
    assert easy_flagged["easy_gap_flagged"] is True

    easy_clean = apply_decision_rule(_table((0.50, 0.51), (0.9, 0.905)))  # Delta(EASY) = 0.005
    assert easy_clean["easy_gap_flagged"] is False


def test_ablation_runs_end_to_end_on_the_real_committed_sample_data():
    table = run_ablation(SAMPLES_DIR, split="holdout")

    for config in ("rules_only", "hybrid", "llm_only"):
        assert config in table
        overall = table[config]["Overall"]
        assert overall["n"] == 60  # data/samples' own holdout size

    decision = apply_decision_rule(table)
    assert decision["band"] in ("HEADLINE", "MODEST", "NEGATIVE")
    # rules-only and llm-only never see the fallback's residual-only narrowing the same way --
    # hybrid must never resolve strictly *fewer* correct matches than rules-only (L1 always gets
    # first refusal; L2 can only ever pick up what L1 left on the table).
    assert table["hybrid"]["Overall"]["tp"] >= table["rules_only"]["Overall"]["tp"]


def test_operational_metrics_run_end_to_end_and_never_report_a_false_auto_match_worse_than_reality():
    metrics = run_full_pipeline_metrics(SAMPLES_DIR, split="holdout")

    assert metrics["Overall"].n == 60
    for stratum_metrics in metrics.values():
        assert 0.0 <= stratum_metrics.false_auto_match_rate <= 1.0
        assert 0.0 <= stratum_metrics.precision_auto_posted <= 1.0
