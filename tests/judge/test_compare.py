"""The comparison rule: normalisation, the float tolerance, the canonical stdout, the harness's oracles."""

import collections

import pytest

pytest.importorskip("evalplus")

from code_model_reliability.judge import compare  # noqa: E402


class ApproxFloat(float):
    def __eq__(self, other):
        return abs(float(self) - float(other)) < 1e-12 if isinstance(other, (int, float)) else NotImplemented

    __hash__ = float.__hash__


class Approx:
    def __init__(self, v):
        self.v = v

    def __eq__(self, other):
        return True


def test_normalize_strips_a_subclass_and_refuses_a_foreign_type():
    assert type(compare.normalize(ApproxFloat(2.0))) is float
    near = 2.0 + 1e-13
    assert (ApproxFloat(2.0) == near) is True, "the wrapper itself is lenient"
    assert (near == compare.normalize(ApproxFloat(2.0))) is False, "normalised: plain float equality decides"
    assert compare.normalize(Approx(1)) is compare.UNEQUAL
    assert not (compare.normalize(Approx(1)) == 1) and not (1 == compare.normalize(Approx(1)))
    assert compare.normalize(collections.Counter("aab")) == {"a": 2, "b": 1}
    assert type(compare.normalize(collections.Counter("aab"))) is dict
    assert compare.normalize(collections.deque([1])) is compare.UNEQUAL
    plain = [1, 2, [3, "x"]]
    assert compare.normalize(plain) is plain


def test_numbers_equal_is_tolerant_only_where_a_float_meets_a_number():
    assert compare.numbers_equal(752629165542741114880, 7.526291655427412e20)
    assert compare.numbers_equal(10**24, 1e24) and compare.numbers_equal(1e200, 10**200)
    assert compare.numbers_equal([1, 2.0000000001], [1, 2]) and not compare.numbers_equal([1, 2.001], [1, 2])
    assert not compare.numbers_equal(10**24, 10**24 + 1) and not compare.numbers_equal(2**53 + 1, 2**53)
    assert compare.numbers_equal("a", "a") and not compare.numbers_equal("a", "b")
    assert compare.numbers_equal(True, True) and not compare.numbers_equal(True, 1.0000001)
    assert compare.numbers_equal(0.1 + 0.2, 0.3) and not compare.numbers_equal(0.1, 0.10001)
    assert not compare.numbers_equal([1, 2], [1, 2, 3])
    assert compare.values_equal([1, 2, 3], [1, 2, 3])
    assert compare.values_equal((1, 2.0), [1, 2]), "a list and a tuple compare elementwise under the tolerance rule"
    assert not compare.values_equal((1, 2.5), [1, 2])


def test_stdout_canonical_form():
    assert compare.stdout_canonical("0\n") == "0" and compare.stdout_canonical("0\n\n") == "0"
    assert compare.stdout_canonical("a \r\nb\t\n\n") == "a\nb"
    assert compare.stdout_canonical("a\n\nb\n") == "a\n\nb"
    assert compare.stdout_canonical(" a") == " a"


def test_outputs_match_applies_the_rule_and_the_harness_float_branch():
    matched, _ = compare.outputs_match("humaneval", "f", 752629165542741114880, 7.526291655427412e20, 0, [[1]])
    assert matched
    matched, atol = compare.outputs_match("humaneval", "f", 1.00000001, 1.0, 0, [[1]])
    assert matched and atol == 1e-6, "a float expected value turns the harness's 1e-6 tolerance on"
    matched, _ = compare.outputs_match("humaneval", "f", "1\n2\n", "1\n2", 0, [["2 1"]], stdin_stdout=True)
    assert matched
    matched, _ = compare.outputs_match("humaneval", "f", "1\n2\n", "1\n2", 0, [["2 1"]], stdin_stdout=False)
    assert not matched
    matched, _ = compare.outputs_match("mbpp", "similar_elements", [3, 1], [1, 3], 0, [[(1, 3), (3, 1)]])
    assert matched, "a set-comparison oracle of the harness"
    matched, _ = compare.outputs_match("mbpp", "check_str", "yes", True, 0, [["abc"]])
    assert matched, "a not-None oracle of the harness"
    matched, _ = compare.outputs_match("humaneval", "f", Approx(0), 5, 0, [[1]])
    assert not matched, "a value of a foreign type is never equal"
