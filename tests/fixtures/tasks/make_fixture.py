#!/usr/bin/env python3
"""Write the task-data fixture: a data/tasks-shaped package with four small tasks of this repository's own.

Run from anywhere: ``python3 tests/fixtures/tasks/make_fixture.py``. Deterministic: the same files every time. The
fixture has wave 1 as two ids, wave 2 as three tasks (two with text, one shipped as a pointer whose upstream row is
cached under ``upstream/``), and wave 2 parked as one task the audit does not keep. Every hash is computed by the
package's own recipe, so the tests check the recipe against the files it produced.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))
from code_model_reliability.tasks.content import content_sha256, list_sha256  # noqa: E402

TASKS = {
    "fx/add_two": {
        "prompt": 'def add_two(a: int, b: int) -> int:\n    """Return the sum of a and b.\n\n    >>> add_two(1, 2)\n    3\n    """\n',
        "entry_point": "add_two",
        "canonical_solution": "    return a + b\n",
        "base_input": [[1, 2], [0, 0], [-1, 1]],
        "plus_input": [[10, 20], [-5, -7], [100, -100], [2147483648, 1]],
        "atol": 0,
        "expected_output": None,
    },
    "fx/count_vowels": {
        "prompt": 'def count_vowels(s: str) -> int:\n    """Return how many characters of s are vowels (a, e, i, o, u), in either case.\n\n    >>> count_vowels("hello")\n    2\n    """\n',
        "entry_point": "count_vowels",
        "canonical_solution": '    return sum(1 for c in s.lower() if c in "aeiou")\n',
        "base_input": [["hello"], ["xyz"], ["AEIOU"]],
        "plus_input": [["Programming"], [""], ["Why"], ["aEiOu bcd"]],
        "atol": 0,
        "expected_output": None,
    },
    "fxp/is_even": {
        "prompt": 'def is_even(n: int) -> bool:\n    """Return True when n is even.\n\n    >>> is_even(2)\n    True\n    """\n',
        "entry_point": "is_even",
        "canonical_solution": "    return n % 2 == 0\n",
        "base_input": [[2], [3]],
        "plus_input": [[0], [-4], [-7], [1000000000]],
        "atol": 0,
        "expected_output": None,
    },
    "fx/clip": {
        "prompt": 'def clip(x: int, lo: int, hi: int) -> int:\n    """Return x limited to the range lo..hi.\n\n    >>> clip(5, 0, 10)\n    5\n    """\n',
        "entry_point": "clip",
        "canonical_solution": "    return max(lo, min(x, hi))\n",
        "base_input": [[5, 0, 10], [-1, 0, 10]],
        "plus_input": [[11, 0, 10], [5, 10, 0]],
        "atol": 0,
        "expected_output": None,
    },
}
LABELS = {"fx/w1_a": "regular", "fx/w1_b": "tricky", "fx/add_two": "regular", "fx/count_vowels": "tricky",
          "fxp/is_even": "regular", "fx/clip": "underspecification"}
JUSTIFICATION = {"fx/count_vowels": "The examples show lower-case words only, while the extended tests include upper-case vowels the statement does name.",
                 "fx/clip": "The statement does not say what happens when lo is greater than hi, and one extended test exercises it."}
SETS = {"wave_1": ["fx/w1_a", "fx/w1_b"], "wave_2": ["fx/add_two", "fx/count_vowels", "fxp/is_even"], "wave_2_parked": ["fx/clip"]}
KEEP = ("regular", "tricky")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prov(tid: str) -> dict:
    if tid.startswith("fxp/"):
        return {"source_dataset": "fixture/upstream", "problem_key": tid.split("/")[1], "source_row": "rows.jsonl#0",
                "title": tid.split("/")[1], "license": "fixture", "dates": {"source_date": "2024-01-01", "fetched": "2024-02-01"}}
    return {"channel": "fixture", "method": "written for the tests", "generator": "make_fixture", "date_generated": "2024-01-01"}


def write_jsonl(path: pathlib.Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    records = {tid: {"task_id": tid, **fields} for tid, fields in TASKS.items()}
    hashes = {tid: content_sha256(rec) for tid, rec in records.items()}
    kept = {k: [t for t in ids if LABELS[t] in KEEP] for k, ids in SETS.items()}

    sets = {
        "_rule": "the members of record of the fixture sets; a sha256 over each sorted list is the set's identity",
        "label_rule": {"keep_labels": list(KEEP), "excluded_labels": ["contradiction", "underspecification"], "rule": "a task is kept iff its current label is a keep label"},
        "sets": {k: {"members": ids, "kept": kept[k], "count": len(ids), "kept_count": len(kept[k]),
                     "sha256_sorted_members": list_sha256(ids), "sha256_sorted_kept": list_sha256(kept[k])} for k, ids in SETS.items()},
        "wave_1_plus_2": {"kept_count": len(kept["wave_1"]) + len(kept["wave_2"]), "sha256_sorted_kept": list_sha256(kept["wave_1"] + kept["wave_2"])},
        "folded_twins": {"focused": [], "parked": []},
        "wave_2_members_not_kept": [],
        "wave_2_parked_members_not_kept": [{"task_id": "fx/clip", "reason": "underspecification"}],
    }
    (HERE / "sets.json").write_text(json.dumps(sets, indent=1) + "\n", encoding="utf-8")

    rows = []
    for k, ids in SETS.items():
        for tid in ids:
            fam = tid.split("/")[0]
            rows.append({"task_id": tid, "set": k, "kept": LABELS[tid] in KEEP, "not_kept_reason": "" if LABELS[tid] in KEEP else LABELS[tid],
                         "family": fam, "kind": "converted" if fam == "fxp" else "generated",
                         "source_set": "fixture/upstream" if fam == "fxp" else "none (written for the tests)",
                         "source_task": tid.split("/")[1] if fam == "fxp" else "", "licence_as_recorded": "fixture",
                         "label": LABELS[tid], "status": "complete-for-admission", "content_sha256": hashes.get(tid, "")})
    write_jsonl(HERE / "attribution.jsonl", rows)
    (HERE / "sources.json").write_text(json.dumps({"sources": [
        {"id": "fx", "name": "fixture tasks", "families": ["fx"], "redistribution": "ours", "what_it_is": "four tiny tasks written for the tests", "licence_as_recorded": "this repository's data licence"},
        {"id": "fxp", "name": "fixture upstream", "families": ["fxp"], "redistribution": "pointer", "what_it_is": "a stand-in for an upstream whose terms permit pointers only", "licence_as_recorded": "pointers only"},
    ]}, indent=1) + "\n", encoding="utf-8")

    certs = []
    for k in ("wave_2", "wave_2_parked"):
        for tid in SETS[k]:
            certs.append({"task_id": tid, "content_sha256": hashes[tid], "superseded_prev_sha256": None, "set": "frame", "in_frame": True,
                          "status": "complete-for-admission", "fit_keep_set": LABELS[tid] in KEEP,
                          "audit_label": {"label": LABELS[tid], "source_round": "round-1", "justification": JUSTIFICATION.get(tid)},
                          "band_aim": "easy", "band_aim_basis": "fixture", "conversion": {"kind": "fixture"}, "provenance": prov(tid)})
    write_jsonl(HERE / "certificates.jsonl", certs)

    (HERE / "wave-1").mkdir(exist_ok=True)
    (HERE / "wave-1" / "kept_tasks.json").write_text(json.dumps({"keep_labels": list(KEEP), "count": len(kept["wave_1"]),
                                                                   "sha256_sorted": list_sha256(kept["wave_1"]), "tasks": sorted(kept["wave_1"])}, indent=1) + "\n", encoding="utf-8")

    for k, folder in (("wave_2", "wave-2"), ("wave_2_parked", "wave-2-parked")):
        out = HERE / folder
        out.mkdir(exist_ok=True)
        part = out / "tasks-part-01.jsonl"   # plain in the fixture (small and readable); the real parts are gzip-compressed and the loader reads both
        n_text = 0
        pointers = []
        with open(part, "w", encoding="utf-8") as gz:
            for tid in sorted(SETS[k]):
                rec = dict(records[tid])
                rec["content_sha256"] = hashes[tid]
                rec["kept_by_audit"] = LABELS[tid] in KEEP
                rec["io_mode"] = "function"
                rec["provenance"] = prov(tid)
                if tid == "fx/count_vowels":
                    rec["input_shapes"] = ["str"]
                if tid == "fx/clip":
                    rec["plus_inputs_removed"] = [[5, 10, 0]]
                if tid.startswith("fxp/"):
                    # the pointer task was re-issued after conversion with one extended input removed: the upstream
                    # conversion (upstream/converted.jsonl) still carries it, and the pointer's recipe removes it
                    first = dict(records[tid])
                    first["plus_input"] = first["plus_input"] + [[42]]
                    pointers.append({"task_id": tid, "content_sha256": hashes[tid], "kept_by_audit": rec["kept_by_audit"], "io_mode": "function",
                                     "provenance": prov(tid), "reason": "upstream-terms",
                                     "rebuild": {"converter": "leetcode", "first_emission_sha256": content_sha256(first),
                                                 "plus_inputs_removed_at_reissue": [[42]], "base_inputs_removed_at_reissue": []},
                                     "note": "The statement is not redistributed; rebuild from the upstream row named in provenance with the converter named under rebuild, removing the inputs listed there."})
                    continue
                gz.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                n_text += 1
        write_jsonl(out / "restricted.jsonl", pointers)
        (out / "manifest.json").write_text(json.dumps({
            "set": k.replace("_", " "), "set_key": k, "members": len(SETS[k]), "kept_by_audit": len(kept[k]), "full_text_tasks": n_text,
            "pointer_tasks": len(pointers), "pointers_by_reason": {"upstream-terms": len(pointers)} if pointers else {},
            "sha256_sorted_members": list_sha256(SETS[k]), "sha256_sorted_kept": list_sha256(kept[k]),
            "hash_recipe": "sha256(json.dumps({task_id, prompt, entry_point, canonical_solution, base_input, plus_input, atol, expected_output}, sort_keys=True))",
            "parts": [{"file": part.name, "records": n_text, "bytes": part.stat().st_size, "sha256": sha(part)}]}, indent=1) + "\n", encoding="utf-8")

    labels = [{"task_id": tid, "set": next(k for k, ids in SETS.items() if tid in ids), "label": lab, "source_round": "round-1",
               "justification": JUSTIFICATION.get(tid)} for tid, lab in LABELS.items()]
    write_jsonl(HERE / "labels" / "labels.jsonl", labels)
    write_jsonl(HERE / "labels" / "label_history.jsonl", [{"task_id": "fx/count_vowels", "set": "wave_2", "label_before": "regular", "label_after": "tricky",
                                                           "review_round": "round-1", "day_recorded": "2024-03-01", "day_applied": "2024-03-02",
                                                           "justification": JUSTIFICATION["fx/count_vowels"]}])

    # the pointer task's upstream row, converted: what a rebuild produces (the first emission, with the input the
    # re-issue later removed)
    first = dict(records["fxp/is_even"])
    first["plus_input"] = first["plus_input"] + [[42]]
    write_jsonl(HERE / "upstream" / "converted.jsonl", [first])
    print(json.dumps(hashes, indent=1))


if __name__ == "__main__":
    main()
