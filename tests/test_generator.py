import json

from data.generator import CATEGORY_DIFFICULTY, generate, write_dataset

TEST_SIZE = 500
TEST_CHAOS_MIN = 8


def test_generation_is_byte_identical_for_same_seed(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    write_dataset(generate(seed=42, total_bank_lines=TEST_SIZE), out_a)
    write_dataset(generate(seed=42, total_bank_lines=TEST_SIZE), out_b)

    for name in ("bank_statement.csv", "internal_ledger.csv", "ground_truth.json", "chaos_manifest.json"):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), name


def test_different_seeds_produce_different_output(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    write_dataset(generate(seed=1, total_bank_lines=TEST_SIZE), out_a)
    write_dataset(generate(seed=2, total_bank_lines=TEST_SIZE), out_b)

    assert (out_a / "bank_statement.csv").read_bytes() != (out_b / "bank_statement.csv").read_bytes()


def test_every_chaos_category_appears_at_least_five_times():
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE, chaos_min_count=TEST_CHAOS_MIN)
    counts = {}
    for category in dataset.category_of.values():
        counts[category] = counts.get(category, 0) + 1

    for category in CATEGORY_DIFFICULTY:
        assert counts.get(category, 0) >= 5, f"{category} appeared only {counts.get(category, 0)} times"


def test_ground_truth_covers_every_bank_line():
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE)
    bank_line_ids = {bl.id for bl in dataset.bank_lines}
    assert set(dataset.ground_truth.keys()) == bank_line_ids
    assert len(dataset.ground_truth) == len(dataset.bank_lines)


def test_split_is_disjoint_and_roughly_60_20_20():
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE)
    by_split = {"train": 0, "validation": 0, "holdout": 0}
    seen_ids = set()
    for bank_line_id, gt in dataset.ground_truth.items():
        assert bank_line_id not in seen_ids
        seen_ids.add(bank_line_id)
        by_split[gt.split] += 1

    n = len(dataset.ground_truth)
    assert seen_ids == set(dataset.ground_truth.keys())
    assert 0.55 * n <= by_split["train"] <= 0.65 * n
    assert 0.15 * n <= by_split["validation"] <= 0.25 * n
    assert 0.15 * n <= by_split["holdout"] <= 0.25 * n


def test_holdout_contains_the_duplicate_vs_double_settlement_pair():
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE)
    dup_id = dataset.demo_pair["duplicate_utr_bank_line_id"]
    dbl_id = dataset.demo_pair["genuine_double_settlement_bank_line_id"]

    assert dataset.ground_truth[dup_id].split == "holdout"
    assert dataset.ground_truth[dbl_id].split == "holdout"

    dup_line = next(bl for bl in dataset.bank_lines if bl.id == dup_id)
    dbl_line = next(bl for bl in dataset.bank_lines if bl.id == dbl_id)
    assert dup_line.credit_paise == dbl_line.credit_paise
    assert dup_line.value_date == dbl_line.value_date
    assert dup_line.narration != dbl_line.narration


def test_no_match_and_duplicate_categories_have_null_correct_match():
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE)
    for bank_line_id, category in dataset.category_of.items():
        if category == "NO_MATCH_EXISTS":
            assert dataset.ground_truth[bank_line_id].correct_match is None
        if category == "DUPLICATE_UTR" and bank_line_id == dataset.demo_pair.get(
            "duplicate_utr_bank_line_id"
        ):
            assert dataset.ground_truth[bank_line_id].correct_match is None


def test_write_dataset_outputs_are_well_formed(tmp_path):
    dataset = generate(seed=42, total_bank_lines=TEST_SIZE)
    write_dataset(dataset, tmp_path)

    ground_truth = json.loads((tmp_path / "ground_truth.json").read_text())
    assert len(ground_truth) == len(dataset.bank_lines)

    manifest = json.loads((tmp_path / "chaos_manifest.json").read_text())
    assert manifest["total_bank_lines"] == len(dataset.bank_lines)
    assert sum(manifest["category_counts"].values()) == len(dataset.bank_lines)
