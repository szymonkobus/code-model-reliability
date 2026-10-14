"""The pooling of a cell's judging rows: validity by stamp, draws by identity, the walk key, the pool."""

from code_model_reliability.land import pooling

RULES = pooling.PoolingRules({
    "stamps_of_record": [
        "min_time_limit=15;mem=8GiB;task_timeout=300",
        "min_time_limit=15;mem=8GiB;preamble=imports;plus=bool-filtered;task_timeout=300",
        "min_time_limit=15;mem=8GiB;extractor=x2;task_timeout=300",
        "min_time_limit=15;mem=8GiB;task_timeout=sum-limits",
        "min_time_limit=15",
    ],
    "task_sets": {"import_bearing": ["t/imports"], "plus_filtered": ["t/filtered"], "typed_inputs": [], "canonical_floor": ["t/slow"], "typing_carrier": []},
    "task_effective_limits": {"t/slow": 537},
    "default_set_cap_s": 300,
})
PLAIN = "min_time_limit=15;mem=8GiB;task_timeout=300"
HOOKED = "min_time_limit=15;mem=8GiB;preamble=imports;plus=bool-filtered;task_timeout=300"
X2 = "min_time_limit=15;mem=8GiB;extractor=x2;task_timeout=300"
KNOBS = {"child_mem_budget_gib": 8, "compare": "numeric-tolerant-v2", "stdout_compare": "v2-symmetric-r2", "parallel": 4}


def row(task="t/plain", shard="s1", identity="h1", stamp=PLAIN, emitted="2", attempts=32, base=20, plus=18, **kw):
    knobs = dict(KNOBS)
    knobs.update(kw.pop("knobs", {}))
    return pooling.JudgingRow(arm="a", task_id=task, shard=shard, source=kw.pop("source", "runs"), identity=identity, stamp=stamp,
                              knobs=knobs, emitted=emitted, attempts=attempts, base_passes=base, plus_passes=plus, **kw)


def test_a_stamp_not_of_record_is_invalid_and_counted():
    kept, why = pooling.valid_rows([row(stamp="min_time_limit=15;mem=6GiB"), row()], RULES)
    assert len(kept) == 1 and why == {"stamp not of record": 1}


def test_grade_counts_applicable_corrections_only():
    assert pooling.grade(row(stamp=PLAIN), RULES) == 1, "the cap token is universal"
    assert pooling.grade(row(stamp=X2), RULES) == 2
    assert pooling.grade(row(task="t/plain", stamp=HOOKED), RULES) == 1, "set-bound tokens count on their sets only"
    assert pooling.grade(row(task="t/imports", stamp=HOOKED), RULES) == 2
    assert pooling.grade(row(task="t/slow", stamp="min_time_limit=15;mem=8GiB;task_timeout=sum-limits"), RULES) == 2, "sum-limits implies the cap and counts on the floor class"


def test_newest_judging_of_a_draw_wins_but_a_higher_grade_outranks_time():
    old = row(emitted="1", plus=10)
    new = row(emitted="2", plus=12)
    assert pooling.winner_of_draw([old, new], RULES).winner is new
    x2_old = row(emitted="1", stamp=X2, plus=11)
    assert pooling.winner_of_draw([x2_old, new], RULES).winner is x2_old


def test_tier_and_leniency():
    assert pooling.tier(row()) == 4
    assert pooling.tier(row(stamp="min_time_limit=15", knobs={"child_mem_budget_gib": None}, source="box")) == 1
    lenient = row(knobs={"compare": "exact"})
    assert pooling.more_lenient_than_current(lenient, RULES) is False, "a stricter comparison never loses by leniency"
    unknown = row(knobs={"compare": "something-new"})
    assert pooling.more_lenient_than_current(unknown, RULES) is True
    big_cap = row(task="t/slow", knobs={"task_timeout_s": 900})
    assert pooling.more_lenient_than_current(big_cap, RULES) is True
    right_cap = row(task="t/slow", knobs={"task_timeout_s": 537})
    assert pooling.more_lenient_than_current(right_cap, RULES) is False


def test_distinct_draws_pool_and_mixed_stamps_are_marked():
    rows = [row(shard="s1", identity="h1", plus=18), row(shard="s2", identity="h2", stamp=X2, plus=20),
            row(shard="s1", identity="h1", emitted="1", plus=5)]
    cell = pooling.compose_cell("a", "t/plain", rows, RULES)
    assert (cell.attempts, cell.plus_passes, cell.draws) == (64, 38, 2)
    assert cell.mixed_stamps and cell.stamps == sorted([PLAIN, X2])
    assert cell.failures == 26


def test_a_carried_copy_keeps_its_identity_and_a_second_generation_is_another_draw():
    same = [row(shard="s1", identity="h1", source="runs"), row(shard="s1", identity="h1", source="copy", emitted="3")]
    assert pooling.compose_cell("a", "t/plain", same, RULES).draws == 2, "a copy judged on the other cluster is its own draw key by source"
    two = [row(shard="s1", identity="h1"), row(shard="s1", identity="h2")]
    assert pooling.compose_cell("a", "t/plain", two, RULES).draws == 2


def test_time_out_override_counts_a_witnessed_pass():
    winner = row(emitted="2", plus=10, time_out_shas=("p1", "p2"))
    witness = row(emitted="1", plus=12, pass_shas=("p1",))
    result = pooling.winner_of_draw([winner, witness], RULES)
    assert result.overrides == 1 and result.winner.plus_passes == 11


def test_held_winner_takes_a_same_stamp_stand_in_or_is_set_aside():
    held = row(emitted="3", held=True, plus=15)
    same_stamp = row(emitted="2", plus=14)
    other_stamp = row(emitted="1", stamp=X2, plus=16)
    result = pooling.winner_of_draw([held, same_stamp], RULES)
    assert result.winner is same_stamp and result.same_stamp_stand_in
    result = pooling.winner_of_draw([held, other_stamp], RULES)
    assert result.winner is other_stamp, "the other stamp outranks by grade; the held row is not the top"
    only_held = pooling.winner_of_draw([row(held=True)], RULES)
    assert only_held.winner is None
    assert pooling.compose_cell("a", "t/plain", [row(held=True)], RULES) is None


def test_the_rules_file_of_the_package_loads_with_its_sets():
    rules = pooling.PoolingRules.load()
    assert "min_time_limit=15;mem=8GiB;task_timeout=300" in rules.stamps and len(rules.stamps) > 20
    assert len(rules.task_sets["import_bearing"]) > 300 and len(rules.task_sets["plus_filtered"]) >= 157
    assert len(rules.task_limits) == 34 and rules.default_limit is None
    assert "held_winner_composition" in rules.data["rules"] and rules.data["needs_restating"] == []
    assert pooling.stamp_is_of_record("min_time_limit=15;mem=6GiB", rules) is False


def test_compose_writes_cells_rows():
    cells = pooling.compose([row(), row(task="t/other", plus=32, base=32)], RULES)
    rows = pooling.cells_rows(cells)
    by_task = {r["task_id"]: r for r in rows}
    assert by_task["t/plain"]["failures"] == 14 and by_task["t/other"]["failures"] == 0
    assert by_task["t/plain"]["judging"] == PLAIN and [r["task_id"] for r in rows] == ["t/other", "t/plain"]
