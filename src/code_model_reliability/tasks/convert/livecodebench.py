"""LiveCodeBench rows into tasks (the ``lcb-functional-join`` method).

LiveCodeBench ships problems and tests but no solutions. Its LeetCode problems are joined by their slug (the title,
lower-cased, runs of other characters to one hyphen) to LeetCodeDataset's completion for the same problem, which
becomes the reference. The prompt is LeetCodeDataset's prompt for the problem with the method's signature as a
module-level function and LiveCodeBench's statement as its docstring; the base tests are the public test cases,
the extended tests the private ones (functional cases only, one JSON literal per argument line); the comparison is
exact. A row converts only when the joined reference reproduces every kept expected value.
"""

from __future__ import annotations

import base64
import json
import pickle
import re
import zlib

from .common import MIN_TESTS, has_float, has_nonfinite, json_stable, multi_answer_phrase, run_and_compare, sanitize_doc
from .leetcode import method_signature

SOURCE_DATASET = "livecodebench/code_generation_lite#v6"
LICENCE_AS_RECORDED = "cc (dataset card) over LeetCode material"
REFERENCE_DATASET = "newfacade/LeetCodeDataset"


def slugify(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def decode_tests(raw) -> list:
    """The test-case field: a JSON list, possibly wrapped in base64, zlib and pickle for a large private suite."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        pass
    value = pickle.loads(zlib.decompress(base64.b64decode(raw)))
    return json.loads(value) if isinstance(value, str) else value


def parse_functional_case(case: dict, n_params: int) -> tuple[list, object]:
    """A functional case: the input is one JSON literal per line, one per positional argument; the output one literal."""
    lines = [l for l in (case.get("input") or "").split("\n") if l.strip()]
    if len(lines) != n_params:
        raise ValueError("argument count %d != %d parameters" % (len(lines), n_params))
    return [json.loads(l) for l in lines], json.loads(case.get("output"))


def convert_row(row: dict, references: dict[str, dict]) -> tuple[str, str, dict | None, dict]:
    """One LiveCodeBench row to (status, reason, task or None, metrics), with the LeetCodeDataset rows by slug as the
    references."""
    metrics: dict = {"source": "lcb"}
    description = row.get("question_content") or ""
    phrase = multi_answer_phrase(description)
    metrics["multi_answer"] = phrase
    if phrase:
        return "needs-human", "a multi-answer statement has no exact oracle: %s" % phrase[:140], None, metrics
    slug = slugify(row.get("question_title"))
    ref = references.get(slug)
    if ref is None:
        return "needs-human", "no joinable reference: slug %s is not in LeetCodeDataset" % slug, None, metrics
    method = row.get("_func_name")
    try:
        params, header = method_signature(row.get("starter_code") or ref["starter_code"], method)
    except (ValueError, SyntaxError) as e:
        return "needs-human", "the starter code did not parse: %s" % e, None, metrics
    completion = ref.get("completion") or ""
    if "class Solution" not in completion:
        return "needs-human", "the joined completion is not a Solution class", None, metrics

    base_in, base_exp, plus_in, plus_exp, dropped = [], [], [], [], 0
    try:
        public = decode_tests(row.get("public_test_cases"))
        private = decode_tests(row.get("private_test_cases"))
    except Exception as e:  # noqa: BLE001 — any decoding failure routes the row to review
        return "needs-human", "the test cases did not decode: %s" % e, None, metrics
    for cases, ins, exps in ((public, base_in, base_exp), (private, plus_in, plus_exp)):
        for case in cases:
            if (case.get("testtype") or "functional") != "functional":
                dropped += 1
                continue
            try:
                args, exp = parse_functional_case(case, len(params))
            except (ValueError, TypeError):
                dropped += 1
                continue
            if not json_stable(args) or not json_stable(exp):
                dropped += 1
                continue
            ins.append(args)
            exps.append(exp)
    metrics.update(n_base=len(base_in), n_plus=len(plus_in), n_dropped=dropped)
    if len(base_in) + len(plus_in) < MIN_TESTS:
        return "rejected", "only %d usable tests" % (len(base_in) + len(plus_in)), None, metrics
    if any(has_nonfinite(v) for v in base_in + plus_in + base_exp + plus_exp):
        return "rejected", "a non-finite float in the tests", None, metrics
    if any(has_float(v) for v in base_exp + plus_exp):
        return "rejected", "float expected values: the comparison is exact (atol 0), a tolerance task is not converted", None, metrics

    prompt = "%s\n%s\n    \"\"\"%s\n    \"\"\"\n" % ((ref.get("prompt") or "").rstrip(), header,
                                                     sanitize_doc(description).replace("\n", "\n    "))
    body_lines = ["    %s" % line if line.strip() else "" for line in completion.split("\n")]
    canonical = "\n".join(body_lines).rstrip() + ("\n    return Solution().%s(%s)\n" % (method, ", ".join(params)))
    inputs = base_in + plus_in
    expected = base_exp + plus_exp
    ok, mismatches, errors, slowest = run_and_compare(prompt + canonical, method, inputs, expected)
    metrics["reference_slowest_s"] = slowest
    if not ok:
        return ("needs-human", "the joined reference differs or fails on %d of %d tests (%s)"
                % (len(mismatches) + len(errors), len(inputs), "; ".join(errors[:3]) or "value mismatch"), None, metrics)
    task = {
        "task_id": "lcb/%s" % slug,
        "prompt": prompt,
        "entry_point": method,
        "canonical_solution": canonical,
        "base_input": base_in,
        "plus_input": plus_in,
        "atol": 0,
        "expected_output": {"base": base_exp, "plus": plus_exp},
        "provenance": {
            "problem_key": slug, "source_dataset": SOURCE_DATASET, "source_row": row.get("_row"),
            "title": row.get("question_title"), "rating": None, "difficulty": row.get("difficulty"),
            "tags": ["livecodebench"], "url": "https://leetcode.com/problems/%s/" % slug, "license": LICENCE_AS_RECORDED,
            "dates": {"source_date": row.get("contest_date"), "fetched": row.get("_fetched_at")},
            "time_limit_s": None, "reference_joined_from": REFERENCE_DATASET,
        },
        "conversion": {"method": "lcb-functional-join",
                       "reference": {"origin": "LeetCodeDataset completion (joined by slug)"},
                       "tests_dropped_at_fetch": dropped, "tests_dropped_at_budget": 0,
                       "sample_tests_extracted": len(base_in), "warnings": []},
    }
    return "converted", "the joined reference is exact on %d tests" % len(inputs), task, metrics
