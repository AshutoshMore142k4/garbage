"""D2 Red Team evaluation (phases.md Phase 7): adversarial survival rate, kept out of the
headline holdout metrics entirely (`plan.md`'s validation/holdout split is never touched by this
module -- it only ever reads the separate `data/redteam/` directory this file's own generator
writes).

**Survival rule.** A case survives if the pipeline either refuses it (any action other than
AUTO_POST) or auto-posts the one answer its `RedTeamCase.correct_order_ids` actually names. It
fails -- "the attack succeeded" -- only when the pipeline auto-posts and gets it wrong, which is
the one failure mode that actually moves money to the wrong place. For
PROMPT_INJECTION_NARRATION cases `correct_order_ids` is `None` (no single answer is correct given
the structurally tied candidate pair), so those survive only by refusal, never by a lucky guess.

**Calibration.** The calibrator and gate threshold are fit on the *production* dataset's
validation split (`data/samples` by default) exactly as `close.py` does for a real batch --
never on red-team data. Tuning either against the attack set would be training the defense on
the exam, which would make the survival rate meaningless as a measure of the pipeline actually
shipped.

**Scope.** L4 anomaly detection is intentionally out of scope here (`has_anomaly` is always
False): none of the four attack categories targets duplicate-UTR/double-settlement/missing-
settlement/fee-tax-band detection, and folding L4 in would blur which layer a given result is
actually exercising. See PROGRESS.md Phase 7 for this scoping decision.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from data.redteam import ATTACK_CATEGORIES, RedTeamCase, generate_redteam_cases, write_redteam_dataset
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import Decision, build_decision_dataset
from ledgerguard.l3_calibrate_gate.gate import GateInput, gate
from ledgerguard.l5_executor.authority import AuthorityInput, authorize

DEFAULT_PRODUCTION_DATA_DIR = Path("data/samples")
DEFAULT_AUTHORITY_LIMIT_PAISE = 10_000_000  # matches close.py's own default


@dataclass
class RedTeamResult:
    case: RedTeamCase
    action: str
    order_ids: list[str]
    survived: bool


def _fit_production_calibrator(production_data_dir: Path) -> tuple[Calibrator, float]:
    production_decisions = build_decision_dataset(production_data_dir)
    validation = [d for d in production_decisions if d.split == "validation"]
    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])

    calibrated = calibrator.predict_proba([d.features for d in validation])
    validation_costs = [
        CostDecision(credit_paise=d.credit_paise, calibrated_confidence=c, correct=d.correct)
        for d, c in zip(validation, calibrated)
    ]
    threshold = find_optimal_threshold(validation_costs)
    return calibrator, threshold


def _survived(action: str, order_ids: list[str], case: RedTeamCase) -> bool:
    if action != "AUTO_POST":
        return True  # refused -- never posted, so it never cost anything
    if case.correct_order_ids is None:
        return False  # no answer was correct; posting any one of them is the attack succeeding
    return set(order_ids) == set(case.correct_order_ids)


def run_redteam_eval(
    redteam_data_dir: Path,
    cases_by_bank_line: dict[str, RedTeamCase],
    production_data_dir: Path = DEFAULT_PRODUCTION_DATA_DIR,
    authority_limit_paise: int = DEFAULT_AUTHORITY_LIMIT_PAISE,
) -> list[RedTeamResult]:
    calibrator, threshold = _fit_production_calibrator(production_data_dir)

    decisions: list[Decision] = build_decision_dataset(redteam_data_dir)
    calibrated = calibrator.predict_proba([d.features for d in decisions])

    results: list[RedTeamResult] = []
    for d, confidence in zip(decisions, calibrated):
        case = cases_by_bank_line[d.bank_line_id]

        gate_outcome = gate(
            GateInput(
                has_candidate=bool(d.order_ids),
                calibrated_confidence=confidence,
                existing_reason_code=d.reason_code,
            ),
            threshold=threshold,
        )
        final_action = authorize(
            AuthorityInput(
                gate_action=gate_outcome.action,
                amount_paise=d.credit_paise,
                authority_limit_paise=authority_limit_paise,
                has_anomaly=False,  # L4 out of scope here -- see module docstring
            )
        )

        results.append(
            RedTeamResult(
                case=case,
                action=final_action,
                order_ids=d.order_ids,
                survived=_survived(final_action, d.order_ids, case),
            )
        )
    return results


def summarize(results: list[RedTeamResult]) -> dict:
    by_category: dict[str, list[RedTeamResult]] = defaultdict(list)
    for r in results:
        by_category[r.case.category].append(r)

    category_summary = {}
    for category, rs in by_category.items():
        survived = sum(1 for r in rs if r.survived)
        category_summary[category] = {
            "total": len(rs),
            "survived": survived,
            "survival_rate": survived / len(rs) if rs else 0.0,
        }

    total = len(results)
    survived_total = sum(1 for r in results if r.survived)
    return {
        "total_cases": total,
        "survived": survived_total,
        "survival_rate": survived_total / total if total else 0.0,
        "by_category": category_summary,
        "categories_covered": len(by_category),
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description="Run D2's red-team adversarial survival evaluation.")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--cases-per-category", type=int, default=15)
    parser.add_argument("--production-data-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    production_data_dir = args.production_data_dir
    if not (production_data_dir / "bank_statement.csv").exists():
        production_data_dir = DEFAULT_PRODUCTION_DATA_DIR

    with tempfile.TemporaryDirectory() as tmp:
        redteam_dir = Path(tmp) / "redteam"
        redteam = generate_redteam_cases(seed=args.seed, cases_per_category=args.cases_per_category)
        write_redteam_dataset(redteam, redteam_dir)
        cases_by_bank_line = {c.bank_line_id: c for c in redteam.cases}

        results = run_redteam_eval(redteam_dir, cases_by_bank_line, production_data_dir=production_data_dir)

    summary = summarize(results)
    print(f"D2 red team, {len(results)} adversarial cases across {summary['categories_covered']} categories:")
    print(f"  overall survival rate: {summary['survived']}/{summary['total_cases']} ({summary['survival_rate']:.1%})")
    for category in ATTACK_CATEGORIES:
        c = summary["by_category"].get(category)
        if c is None:
            continue
        print(f"  {category}: {c['survived']}/{c['total']} ({c['survival_rate']:.1%})")
    print("  (reported separately from holdout metrics -- see eval/calibration.py for those)")


if __name__ == "__main__":
    main()
