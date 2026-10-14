"""One attempt in the sandbox: an outcome per test, the statuses, the set cap, the import rule in the program."""

import pytest

pytest.importorskip("evalplus")

from code_model_reliability.judge import execute  # noqa: E402

PROGRAM = (
    "import time\n"
    "def f(x):\n"
    "    if x == 2:\n        time.sleep(3)\n"
    "    if x == 3:\n        return -1\n"
    "    if x == 4:\n        raise ValueError('boom')\n"
    "    return x * 2\n"
)
INPUTS = [[1], [2], [3], [4], [5]]
EXPECTED = [2, 4, 6, 8, 10]
TIMES = [0.01] * 5


def run(program, **kw):
    args = dict(floor_s=1.0, factor=4.0, set_cap_s=60.0, memory_bytes=None, stop_at_first=False)
    args.update(kw)
    return execute.run_suite("humaneval", "f", program, INPUTS, EXPECTED, TIMES, 0, **args)


def test_every_outcome_kind_is_recorded_and_the_status_is_fail():
    result = run(PROGRAM)
    assert result.outcomes == "PTWEP"
    assert result.status == execute.FAIL
    assert result.time_outs == [1] and result.failing_tests == [1, 2, 3]
    assert result.time_limits == [1.0] * 5
    assert result.elapsed[1] is not None and 0.9 < result.elapsed[1] < 2.5


def test_stop_at_first_leaves_the_rest_not_run():
    result = run(PROGRAM, stop_at_first=True)
    assert result.outcomes == "PTAAA" and result.status == execute.FAIL


def test_a_correct_program_passes():
    result = run("def f(x):\n    return x * 2\n")
    assert result.status == execute.PASS and result.outcomes == "PPPPP"


def test_a_definition_error_fails_without_running_a_test():
    result = run("def f(x)\n    return x\n")
    assert result.status == execute.FAIL and result.outcomes == "AAAAA"


def test_the_set_cap_kills_the_suite_with_status_timeout():
    slow = "import time\ndef f(x):\n    time.sleep(5)\n    return x * 2\n"
    result = run(slow, floor_s=10.0, set_cap_s=1.0)
    assert result.status == execute.TIMEOUT and result.killed_at_cap
    assert result.set_cap_s == 3.0, "min(cap, sum of limits) + 1 + 1 when every test is run"


def test_without_a_cap_the_summed_limits_bound_the_suite():
    result = run("def f(x):\n    return x * 2\n", floor_s=1.0, set_cap_s=None)
    assert result.status == execute.PASS
    assert result.set_cap_s == 5.0 + 2.0, "the summed limits plus the two seconds"


def test_judged_program_applies_the_rules():
    prompt = "from typing import List\n\ndef f(x: List[int]) -> int:\n    pass\n"
    assert execute.judged_program(prompt, "def f(x):\n    return 1\n", False, False) == "def f(x):\n    return 1\n"
    assert execute.judged_program(prompt, "def f(x):\n    return 1\n", True, False).startswith("from typing import List\n")
    assert "from typing import List, Dict" in execute.judged_program(prompt, "def f(x):\n    return 1\n", True, True)
