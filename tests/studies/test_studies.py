"""Tests of the study folder's shared pieces: the typing-import cleaning rule and the published-table readers."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

STUDIES = Path(__file__).resolve().parents[2] / "studies"
sys.path.insert(0, str(STUDIES))
import tables  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cleaning = load("cleaning", STUDIES / "typing-import-cleaning" / "cleaning.py")


def test_cleaning_removes_only_the_impossible_names():
    program = "from typing import List, int\n\ndef f(x: int) -> List[int]:\n    return [x]\n"
    assert cleaning.clean(program) == "from typing import List\n\ndef f(x: int) -> List[int]:\n    return [x]\n"
    assert cleaning.changed(program)


def test_cleaning_drops_a_line_that_empties_and_keeps_the_line_break():
    program = "from typing import int as _int  # a note\ndef f(n):\n    return n\n"
    cleaned = cleaning.clean(program)
    assert cleaned == "\ndef f(n):\n    return n\n"
    assert cleaned.count("\n") == program.count("\n")


def test_cleaning_leaves_an_ordinary_line_byte_for_byte():
    program = "from typing import List,  Dict  # kept\nfrom math import floor\nfloat = 3\n"
    assert cleaning.clean(program) == program
    assert not cleaning.changed(program)


def test_cleaning_handles_every_removed_name():
    program = "from typing import Integer, Integral, bool, float, str, Optional\n"
    assert cleaning.clean(program) == "from typing import Optional\n"


def test_sha256_sorted_is_over_the_sorted_ids_joined_by_line_breaks():
    import hashlib

    ids = ["b/2", "a/1", "a/10"]
    assert tables.sha256_sorted(ids) == hashlib.sha256("a/1\na/10\nb/2".encode()).hexdigest()


def test_fisher_exact_p_on_two_plain_tables():
    assert tables.fisher_exact_p(5, 10, 5, 10) == pytest.approx(1.0)
    assert tables.fisher_exact_p(10, 10, 0, 10) < 0.001


def test_jeffreys_logit_is_finite_at_the_ends():
    import math

    assert math.isfinite(tables.jeffreys_logit(0, 128))
    assert math.isfinite(tables.jeffreys_logit(128, 128))
    assert tables.jeffreys_logit(64, 128) == pytest.approx(0.0)


def test_readers_on_a_small_tree(tmp_path: Path):
    data = tmp_path / "data"
    fit = data / "results" / "published" / "abc123"
    fit.mkdir(parents=True)
    (fit / "cells.csv").write_text("arm,task_id,failures,attempts\nA,t/1,3,128\nA,t/2,0,128\n", encoding="utf-8")
    (fit / "axis.csv").write_text("task_id,difficulty_z,difficulty_sd,n_arms,mean_failure_rate,n_attempts\nt/1,-2.5,0.1,1,0.02,128\n", encoding="utf-8")
    (data / "tasks" / "wave-1").mkdir(parents=True)
    (data / "tasks" / "wave-1" / "kept_tasks.json").write_text(json.dumps({"tasks": ["t/1"], "count": 1}), encoding="utf-8")
    assert tables.fit_dir(data).name == "abc123"
    assert tables.read_cells(fit)[("A", "t/1")] == (3, 128)
    assert tables.read_axis(fit)["t/1"] == pytest.approx(-2.5)
    assert tables.read_kept_wave1(data)["tasks"] == ["t/1"]
    with pytest.raises(SystemExit):
        tables.fit_dir(data, "nothing-here")
