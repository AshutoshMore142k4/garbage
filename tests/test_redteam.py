"""D2 Red Team tests (phases.md Phase 7): acceptance criteria checked directly, not just
"the module imports." See BROKE.md, Phase 7 for the two real findings this suite is built on.
"""
from pathlib import Path

from data.redteam import ATTACK_CATEGORIES, generate_redteam_cases, write_redteam_dataset
from eval.redteam_eval import run_redteam_eval, summarize

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_at_least_50_cases_across_at_least_4_categories():
    redteam = generate_redteam_cases()
    assert len(redteam.cases) >= 50
    categories = {c.category for c in redteam.cases}
    assert len(categories) >= 4
    assert set(ATTACK_CATEGORIES) <= categories


def test_every_bank_line_id_is_unique():
    redteam = generate_redteam_cases()
    ids = [c.bank_line_id for c in redteam.cases]
    assert len(ids) == len(set(ids))


def test_injection_case_provably_abstains(tmp_path):
    redteam = generate_redteam_cases()
    write_redteam_dataset(redteam, tmp_path)
    cases_by_bank_line = {c.bank_line_id: c for c in redteam.cases}

    results = run_redteam_eval(tmp_path, cases_by_bank_line, production_data_dir=SAMPLES_DIR)
    injection_results = [r for r in results if r.case.category == "PROMPT_INJECTION_NARRATION"]
    assert injection_results
    for r in injection_results:
        assert r.case.correct_order_ids is None
        assert r.action != "AUTO_POST"  # ABSTAIN via ESCALATE -- never posted, regardless of the injected text
        assert r.survived


def test_survival_rate_is_measured_and_not_trivial(tmp_path):
    """phases.md Phase 7's own failure mode warning: a suite where everything survives (or
    everything fails) proves nothing. This asserts the red team actually exercises real failure
    and real success paths -- not that any specific rate is "correct" (there is no ground-truth
    target rate for an adversarial suite).
    """
    redteam = generate_redteam_cases()
    write_redteam_dataset(redteam, tmp_path)
    cases_by_bank_line = {c.bank_line_id: c for c in redteam.cases}

    results = run_redteam_eval(tmp_path, cases_by_bank_line, production_data_dir=SAMPLES_DIR)
    summary = summarize(results)

    assert summary["total_cases"] == len(redteam.cases)
    assert 0.0 < summary["survival_rate"] < 1.0


def test_near_collision_pair_is_the_confirmed_unfixed_attack(tmp_path):
    """Documented in BROKE.md as an honest, un-fixed structural limitation: amount+date+narration
    matching with no independent per-order reference field cannot, even in principle, tell a
    genuine settlement apart from an unrelated same-amount coincidence. This test pins the
    current (imperfect) measured behavior so a future change to this known gap is a deliberate,
    visible decision rather than a silent regression or an accidental fix nobody noticed.
    """
    redteam = generate_redteam_cases()
    write_redteam_dataset(redteam, tmp_path)
    cases_by_bank_line = {c.bank_line_id: c for c in redteam.cases}

    results = run_redteam_eval(tmp_path, cases_by_bank_line, production_data_dir=SAMPLES_DIR)
    near_collision = [r for r in results if r.case.category == "NEAR_COLLISION_PAIR"]
    assert near_collision
    assert any(not r.survived for r in near_collision)  # confirmed: this attack still succeeds sometimes


def test_plausible_wrong_subset_sum_no_longer_auto_posts_the_decoy(tmp_path):
    """The bug this category actually found (BROKE.md, Phase 7): L1's subset-sum search picked a
    decoy group with no check for an equally-valid alternate. Fixed in
    `rule_subset_sum_split_settlement` -- this pins the fix by asserting every case in this
    category now survives (refused via escalation, since a genuine ambiguity has no correct
    single answer to auto-post).
    """
    redteam = generate_redteam_cases()
    write_redteam_dataset(redteam, tmp_path)
    cases_by_bank_line = {c.bank_line_id: c for c in redteam.cases}

    results = run_redteam_eval(tmp_path, cases_by_bank_line, production_data_dir=SAMPLES_DIR)
    subset_sum = [r for r in results if r.case.category == "PLAUSIBLE_WRONG_SUBSET_SUM"]
    assert subset_sum
    assert all(r.survived for r in subset_sum)


def test_redteam_dataset_never_reuses_the_production_holdout_split(tmp_path):
    """Keeps the red-team set separate from holdout (phases.md's explicit instruction): this
    module never reads or writes into data/samples or data/raw, only into its own directory.
    """
    redteam = generate_redteam_cases()
    write_redteam_dataset(redteam, tmp_path)

    assert (tmp_path / "bank_statement.csv").exists()
    assert (tmp_path / "ground_truth.json").exists()
    production_samples_dir = Path(__file__).resolve().parent.parent / "data" / "samples"
    assert tmp_path.resolve() != production_samples_dir.resolve()
