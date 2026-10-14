#!/usr/bin/env python3
import importlib.util, json, os, sys

def load(path):
    spec = importlib.util.spec_from_file_location("bench_import_staged", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def read_tasks(p):
    out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            d = json.loads(line); out[d["task_id"].split("/", 1)[-1]] = d
    return out

def hygiene(prompt):
    # the docstring went through _sanitize_doc (backslashes doubled), so a literal backslash-r pair shows as four chars
    p = prompt.replace("\\\\r", "").replace("\r", "").replace(" ", " ").replace("\t", " ")
    for ch in "​‌‍﻿":
        p = p.replace(ch, "")
    return p

def main():
    M = load(sys.argv[1]); work = sys.argv[2]; slugs = sys.argv[3:]
    rows = {}
    for line in open(os.path.join(work, "leetcode_rows.jsonl"), encoding="utf-8"):
        r = json.loads(line); rows[r["task_id"]] = r
    old = read_tasks(os.path.join(work, "out_old", "tasks_converted.jsonl"))
    new = read_tasks(os.path.join(work, "out_new", "tasks_converted.jsonl"))
    same = diff = 0; examples = []
    for slug in sorted(set(old) & set(new)):
        if hygiene(old[slug]["prompt"]) == new[slug]["prompt"]:
            same += 1
        else:
            diff += 1
            if len(examples) < 3:
                a, b = hygiene(old[slug]["prompt"]), new[slug]["prompt"]
                i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
                examples.append((slug, repr(a[max(0, i-40):i+40]), repr(b[max(0, i-40):i+40])))
    print("prompt check over %d records converted by both: hygiene-only %d, other differences %d" % (same + diff, same, diff))
    for e in examples: print("   ", e)
    for slug in slugs:
        r = rows.get(slug); o = old.get(slug)
        if not r or not o:
            print(slug, ": no row or no old record"); continue
        ep = (r.get("entry_point") or "").strip(); fname = ep.split(".")[-1].split("(")[0]
        params, header = M.leetcode_signature(r["starter_code"], fname)
        ret_is_str = M.return_annotation_is_str(r["starter_code"], fname)
        inputs, expected, bad = [], [], 0
        for io in r.get("input_output") or []:
            try:
                args = M.parse_kwarg_call(io["input"], params)
                exp = M.parse_str_output(io["output"]) if ret_is_str else M.parse_literal(io["output"])
            except (ValueError, SyntaxError, KeyError):
                bad += 1; continue
            inputs.append(args); expected.append(exp)
        code = o["prompt"] + o["canonical_solution"]
        ok, mism, errs, tmax = M.run_and_compare(code, fname, inputs, expected, str_return=ret_is_str)
        print("\n%s: ret_is_str=%s pairs=%d (unparsable %d) ok=%s mismatches=%d errors=%d" % (slug, ret_is_str, len(inputs), bad, ok, len(mism), len(errs)))
        res, fatal = M.houseconv.run_reference(code, [inputs[i] for i in mism[:6]], 10.0) if mism else ({}, None)
        for k, i in enumerate(mism[:6]):
            print("   test %d input=%s expected=%r got_raw=%r" % (i, json.dumps(inputs[i])[:60], expected[i], (res.get(k) or {}).get("out")))
        for e in errs[:4]:
            print("   err:", e[:200])

if __name__ == "__main__":
    main()
