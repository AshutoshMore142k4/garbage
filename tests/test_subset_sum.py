from ledgerguard.l1_deterministic.subset_sum import find_subset


def test_finds_exact_two_way_split():
    candidates = [("p1", 1000), ("p2", 2000), ("p3", 3000)]
    result = find_subset(candidates, target_paise=3000)
    assert result.found
    assert set(result.payment_ids) in ({"p1", "p2"}, {"p3"})


def test_finds_larger_group_with_noise_candidates():
    candidates = [("noise1", 999), ("p1", 500), ("p2", 700), ("p3", 300), ("noise2", 111)]
    result = find_subset(candidates, target_paise=1500)
    assert result.found
    assert sum({"p1": 500, "p2": 700, "p3": 300, "noise1": 999, "noise2": 111}[pid] for pid in result.payment_ids) == 1500


def test_returns_not_found_when_no_subset_sums_to_target():
    candidates = [("p1", 100), ("p2", 200)]
    result = find_subset(candidates, target_paise=999)
    assert not result.found
    assert not result.over_budget


def test_respects_max_group_size():
    # Ten candidates of 1 each; target 10 needs all ten, which exceeds a group cap of 5.
    candidates = [(f"p{i}", 1) for i in range(10)]
    result = find_subset(candidates, target_paise=10, max_group_size=5)
    assert not result.found


def test_over_budget_on_pathological_input_terminates_promptly():
    # Many small, mutually-prime-ish amounts with a low node budget: the search space would
    # blow up combinatorially without the bound, so this must return quickly with over_budget.
    candidates = [(f"p{i}", 7 + i) for i in range(60)]
    result = find_subset(candidates, target_paise=10_000, max_search_nodes=100)
    assert result.over_budget
    assert not result.found


def test_zero_or_negative_target_is_not_found():
    assert not find_subset([("p1", 100)], target_paise=0).found
    assert not find_subset([("p1", 100)], target_paise=-5).found
