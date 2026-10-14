"""LeetCodeDataset rows into tasks (the ``leetcode-solution-wrap`` method).

A row of the dataset carries the problem statement, the starter code (a ``Solution`` class with an empty method), a
completion (the same class with the method written) and input-output pairs. The task's prompt is the dataset's
prompt (the imports and the starter's leading text) followed by the method's signature as a module-level function
and the statement as its docstring; the reference wraps the completion and calls ``Solution().<method>(...)``; the
base tests are the examples parsed from the statement, the extended tests the dataset's pairs; the comparison is
exact (``atol`` 0). A row converts only when its reference reproduces every kept expected value.
"""

from __future__ import annotations

import ast
import json
import re

from .common import (MIN_TESTS, has_float, has_nonfinite, json_stable, multi_answer_phrase, parse_call_arguments,
                     parse_literal, run_and_compare, sanitize_doc)

SOURCE_DATASET = "newfacade/LeetCodeDataset"
LICENCE_AS_RECORDED = "apache-2.0 (dataset card) over LeetCode material"
STRUCTURE_TYPES_RE = re.compile(r"\b(ListNode|TreeNode|Node|GraphNode)\b")
EXAMPLE_RE = re.compile(
    r"Input:?\s*(.+?)\s*Output:?\s*(.+?)(?=\s*(?:Explanation|Example|Constraints|Note|Follow-up|$))", re.S
)


def method_signature(starter_code: str, method: str) -> tuple[list[str], str]:
    """The method's parameter names and its signature as a module-level ``def`` line, from the starter code. A starter
    ships the method with an empty body, which the parser rejects; the header is then read by bracket matching."""
    try:
        tree = ast.parse(starter_code)
    except (SyntaxError, IndentationError):
        i = starter_code.find("def %s" % method)
        if i < 0:
            raise ValueError("def %s not found in the starter code" % method)
        depth = 0
        j = i
        while j < len(starter_code):
            ch = starter_code[j]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                break
            j += 1
        header = re.sub(r"\s+", " ", starter_code[i:j + 1])
        tree = ast.parse("%s\n    pass" % header)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method:
            params = [a.arg for a in node.args.args if a.arg != "self"]
            src = ast.unparse(node)
            header = src.split("\n", 1)[0]
            header = header.replace("(self, ", "(").replace("(self)", "()")
            return params, header
    raise ValueError("method %s not found in the starter code" % method)


def convert_row(row: dict) -> tuple[str, str, dict | None, dict]:
    """One dataset row to (status, reason, task or None, metrics); status is converted, needs-human or rejected."""
    metrics: dict = {"source": "leetcode"}
    description = row.get("problem_description") or ""
    slug = row.get("task_id")
    phrase = multi_answer_phrase(description)
    metrics["multi_answer"] = phrase
    if phrase:
        return "needs-human", "a multi-answer statement has no exact oracle: %s" % phrase[:140], None, metrics
    if STRUCTURE_TYPES_RE.search(row.get("starter_code") or ""):
        return "rejected", "a structure-typed signature (ListNode, TreeNode) is not representable as literals", None, metrics
    entry = (row.get("entry_point") or "").strip()
    method = entry.split(".")[-1].split("(")[0]
    try:
        params, header = method_signature(row["starter_code"], method)
    except (ValueError, SyntaxError) as e:
        return "needs-human", "the starter code did not parse: %s" % e, None, metrics
    completion = row.get("completion") or ""
    if "class Solution" not in completion:
        return "needs-human", "the completion is not a Solution class", None, metrics

    # extended tests: the dataset's input-output pairs
    plus_in, plus_exp, dropped = [], [], 0
    for io in row.get("input_output") or []:
        try:
            args = parse_call_arguments(io["input"], params)
            exp = parse_literal(io["output"])
        except (ValueError, SyntaxError, KeyError):
            dropped += 1
            continue
        if has_nonfinite(args) or has_nonfinite(exp):
            return "rejected", "a non-finite float in the tests does not round-trip through JSON", None, metrics
        if not json_stable(args) or not json_stable(exp):
            dropped += 1
            continue
        plus_in.append(args)
        plus_exp.append(exp)

    # base tests: the examples of the statement; an example that repeats a dataset pair moves it out of the extended set
    base_in, base_exp, bad_examples = [], [], 0
    for m in EXAMPLE_RE.finditer(description):
        try:
            args = parse_call_arguments(m.group(1), params)
            exp = parse_literal(m.group(2))
        except (ValueError, SyntaxError):
            bad_examples += 1
            continue
        if not json_stable(args) or not json_stable(exp):
            bad_examples += 1
            continue
        key = json.dumps(args)
        drop = next((j for j, a in enumerate(plus_in) if json.dumps(a) == key), None)
        if drop is not None:
            del plus_in[drop], plus_exp[drop]
        base_in.append(args)
        base_exp.append(exp)
    metrics.update(n_base=len(base_in), n_plus=len(plus_in), n_dropped_nonliteral=dropped, n_example_parse_fail=bad_examples)

    if len(base_in) + len(plus_in) < MIN_TESTS:
        return "rejected", "only %d literal tests" % (len(base_in) + len(plus_in)), None, metrics
    if any(has_float(v) for v in base_exp + plus_exp):
        return "rejected", "float expected values: the comparison is exact (atol 0), a tolerance task is not converted", None, metrics

    prompt = "%s\n%s\n    \"\"\"%s\n    \"\"\"\n" % ((row.get("prompt") or "").rstrip(), header,
                                                     sanitize_doc(description).replace("\n", "\n    "))
    body_lines = ["    %s" % line if line.strip() else "" for line in completion.split("\n")]
    canonical = "\n".join(body_lines).rstrip() + ("\n    return Solution().%s(%s)\n" % (method, ", ".join(params)))

    inputs = base_in + plus_in
    expected = base_exp + plus_exp
    ok, mismatches, errors, slowest = run_and_compare(prompt + canonical, method, inputs, expected)
    metrics["reference_slowest_s"] = slowest
    if not ok:
        return ("needs-human", "the reference differs or fails on %d of %d tests (%s)"
                % (len(mismatches) + len(errors), len(inputs), "; ".join(errors[:3]) or "value mismatch"), None, metrics)
    warnings = []
    if slowest > 0.1:
        warnings.append("the reference's slowest test took %.2f s, over the 0.10 s margin" % slowest)
    task = {
        "task_id": "leetcode/%s" % slug,
        "prompt": prompt,
        "entry_point": method,
        "canonical_solution": canonical,
        "base_input": base_in,
        "plus_input": plus_in,
        "atol": 0,
        "expected_output": {"base": base_exp, "plus": plus_exp},
        "provenance": {
            "problem_key": slug, "source_dataset": SOURCE_DATASET, "source_row": row.get("_row"), "title": slug,
            "rating": None, "difficulty": row.get("difficulty"), "tags": row.get("tags"),
            "url": "https://leetcode.com/problems/%s/" % slug, "license": LICENCE_AS_RECORDED,
            "dates": {"source_date": row.get("estimated_date"), "fetched": row.get("_fetched_at")},
            "time_limit_s": None,
        },
        "conversion": {"method": "leetcode-solution-wrap", "reference": {"origin": "dataset completion"},
                       "tests_dropped_at_fetch": 0, "tests_dropped_at_budget": dropped,
                       "sample_tests_extracted": len(base_in), "warnings": warnings},
    }
    return "converted", "the reference is exact on %d tests" % len(inputs), task, metrics
