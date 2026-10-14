"""The extractor: every shipped version's logic is its published stamp's, and each returns the recorded program on
the fixture replies."""

import json
import pathlib

import pytest

from code_model_reliability.generate import extract as X

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "generate"


def replies():
    with open(FIXTURES / "replies.jsonl", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_every_version_matches_its_published_stamp():
    assert set(X.VERSIONS) == set(X.PUBLISHED_STAMPS) == set(X.LOGIC_SHA256)
    for stamp, module in X.VERSIONS.items():
        assert X.logic_sha256(module.__file__) == X.LOGIC_SHA256[stamp], stamp
        assert module.__name__.rsplit(".", 1)[-1] == "v2_" + stamp.split("@", 1)[1]
    assert len({X.LOGIC_SHA256[s] for s in X.VERSIONS}) == len(X.VERSIONS)  # five versions, five rule sets
    assert X.CURRENT_STAMP in X.VERSIONS and X.extract is X.VERSIONS[X.CURRENT_STAMP].extract
    assert X.logic_sha256() == X.LOGIC_SHA256[X.CURRENT_STAMP]


@pytest.mark.parametrize("row", replies(), ids=lambda r: r["name"])
def test_fixture_reply(row):
    assert set(row["expected"]) == set(X.VERSIONS), "the fixture carries every stamped version's output"
    for stamp, expected in row["expected"].items():
        assert X.extract_under(stamp)(row["raw"], row["entry_point"]) == expected, stamp
    assert X.extract(row["raw"], row["entry_point"]) == row["expected"][X.CURRENT_STAMP]


def test_the_versions_differ_where_the_rules_changed():
    rows = {r["name"]: r["expected"] for r in replies()}
    first, current = "v2@1f4d747f86f4cf98", X.CURRENT_STAMP
    unclosed = rows["an unclosed thinking tag before the answer"]
    assert "def add" in unclosed[current] and "def add" not in unclosed[first]  # the first version swallowed the rest
    assert "def add" not in unclosed["v2@0b0abd79e863a451"] and "def add" in unclosed["v2@4ab50996111c1be5"]
    literal = rows["a literal assigned to the entry point's name in a later block"]
    assert literal[first] != literal[current] and literal["v2@0b0abd79e863a451"] == literal[current]
    plain = rows["fenced reply with prose around it"]
    assert len(set(plain.values())) == 1


def test_unknown_stamp_is_refused():
    with pytest.raises(KeyError):
        X.extract_under("v2@0000000000000000")


def test_explain_names_the_rule_applied():
    one_block = X.explain("```python\ndef add(a, b):\n    return a + b\n```", "add")
    assert one_block["how"] == "whole-reply-minus-edge-fence-lines"  # the fence lines removed, the reply is the program
    assert one_block["code"] == "def add(a, b):\n    return a + b"
    with_prose = X.explain("Here:\n```python\ndef add(a, b):\n    return a + b\n```\nDone.", "add")
    assert with_prose["how"] == "last-block-defining-entry" and with_prose["n_code_blocks"] == 1
    assert X.explain("no code here", "add")["how"] == "no-code"


def test_a_generator_is_kept_and_demonstrations_are_dropped():
    code = X.extract("```python\ndef evens(n):\n    for i in range(n):\n        yield i\n\nprint(list(evens(4)))\n```", "evens")
    assert "yield i" in code and "print" not in code
