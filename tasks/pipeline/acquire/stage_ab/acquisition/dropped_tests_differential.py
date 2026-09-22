#!/usr/bin/env python3
"""Per task: one KEPT test is re-run first as a harness control (must match).
Reuses convert.run_reference (contained child, 1536MB, own process group)
and convert.canon (per-line rstrip, trailing blank lines dropped).
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402  (run_reference, canon)

CAND_ID_RE = re.compile(r'"cand_id":\s*"([^"]+)"')


def key(s):
    return hashlib.sha1(convert.canon(s or "").encode("utf-8", "replace")).hexdigest()


def classify(r, expected_canon):
    if r is None:
        return "timeout", None            # killed at the group budget
    if not r.get("ok"):
        err = str(r.get("err") or "")
        return ("timeout" if "time" in err.lower() else "error"), err[:160]
    got = convert.canon(r.get("out") or "")
    if got == expected_canon:
        return "match", None
    return "mismatch", {"expected_head": expected_canon[:160], "actual_head": got[:160]}


def scan_task(task, cand, timeout, chunk, max_tests):
    t0 = time.time()
    kept = set(task["kept_input_keys"])
    tests = cand.get("tests") or []
    dropped, seen, control = [], set(), None
    for t in tests:
        k = key(t.get("input") or "")
        if k in kept:
            if control is None:
                control = t
            continue
        if k in seen:
            continue
        seen.add(k)
        dropped.append(t)
    row = {"task_id": task["task_id"], "survivor_file": task["survivor_file"],
           "candidate_file": cand.get("_file"),
           "n_tests_candidate": len(tests), "n_kept": task["n_kept"],
           "n_dropped_available": len(dropped),
           "tests_dropped_at_budget": task.get("tests_dropped_at_budget"),
           "tests_dropped_at_fetch": task.get("tests_dropped_at_fetch"),
           "has_custom_checker": cand.get("has_custom_checker"),
           "time_limit_s": task.get("time_limit_s"), "per_test_timeout_s": timeout}
    full_code = task["prompt"] + task["canonical_solution"]
    run_list = ([("control", control)] if control is not None else []) + \
               [("dropped", t) for t in dropped[:max_tests]]
    statuses, mismatches, errors = [], [], []
    control_status = None
    for start in range(0, len(run_list), chunk):
        part = run_list[start:start + chunk]
        res, fatal = convert.run_reference(
            full_code, [[t.get("input") or ""] for _, t in part], timeout)
        for i, (kind, t) in enumerate(part):
            exp = convert.canon(t.get("output") or "")
            if fatal and i not in res:
                st, detail = "fatal", fatal[:160]
            else:
                st, detail = classify(res.get(i), exp)
            if kind == "control":
                control_status = st
                if st != "match":
                    row["control_detail"] = detail
                continue
            statuses.append(st)
            if st == "mismatch":
                d = dict(detail)
                d["test_index_in_candidate"] = tests.index(t)
                d["input_head"] = (t.get("input") or "")[:100]
                d["input_bytes"] = len(t.get("input") or "")
                mismatches.append(d)
            elif st in ("error", "fatal") and len(errors) < 3:
                errors.append(detail)
    row.update({"control_status": control_status,
                "n_run": len(statuses),
                "n_match": statuses.count("match"),
                "n_mismatch": statuses.count("mismatch"),
                "n_timeout": statuses.count("timeout"),
                "n_error": statuses.count("error") + statuses.count("fatal"),
                "mismatches": mismatches[:6], "errors": errors,
                "elapsed_s": round(time.time() - t0, 1)})
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--cands", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--chunk", type=int, default=4)
    ap.add_argument("--max-tests", type=int, default=40)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--shard", default=None, help="k/n: run tasks with sorted index %% n == k")
    a = ap.parse_args()

    tasks = {}
    with open(a.tasks) as fh:
        for line in fh:
            if line.strip():
                t = json.loads(line)
                if a.ids is None or t["task_id"] in a.ids:
                    tasks[t["task_id"]] = t
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        tasks = {t: v for i, (t, v) in enumerate(sorted(tasks.items())) if i % n == k}
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["task_id"])
                except (ValueError, KeyError):
                    pass
    wanted = set(tasks) - done
    print("tasks %d, already done %d, to run %d" % (len(tasks), len(done), len(wanted)), flush=True)

    found = set()
    n_out = 0
    with open(a.out, "a") as out, cf.ProcessPoolExecutor(max_workers=a.workers) as pool:
        pending = set()

        def drain(block):
            nonlocal n_out
            if not pending:
                return
            done_f, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED if block else cf.ALL_COMPLETED)
            for f in done_f:
                pending.discard(f)
                try:
                    row = f.result()
                except Exception as e:  # never abort the scan on one task
                    row = {"task_id": f.task_id, "scan_error": "%s: %s" % (type(e).__name__, str(e)[:160])}
                out.write(json.dumps(row) + "\n")
                out.flush()
                n_out += 1
                if n_out % 25 == 0:
                    print("  written %d" % n_out, flush=True)

        for path in a.cands:
            print("streaming", path, flush=True)
            with open(path) as fh:
                for line in fh:
                    m = CAND_ID_RE.search(line[:400])
                    if not m or m.group(1) not in wanted or m.group(1) in found:
                        continue
                    cand = json.loads(line)
                    cand["_file"] = os.path.basename(path)
                    cid = cand["cand_id"]
                    found.add(cid)
                    fut = pool.submit(scan_task, tasks[cid], cand, a.timeout, a.chunk, a.max_tests)
                    fut.task_id = cid
                    pending.add(fut)
                    while len(pending) >= 2 * a.workers:
                        drain(block=True)
        while pending:
            drain(block=True)
        for cid in sorted(wanted - found):
            out.write(json.dumps({"task_id": cid, "scan_error": "candidate-not-found"}) + "\n")
            n_out += 1
    print("DONE rows written %d (not found %d)" % (n_out, len(wanted - found)), flush=True)

    # summary over the whole output file
    rows = [json.loads(l) for l in open(a.out) if l.strip()]
    ok = [r for r in rows if "n_run" in r]
    print("summary: tasks %d | with dropped tests available %d | any mismatch %d | any timeout %d | any error %d | control not match %d | scan errors %d" % (
        len(rows), sum(1 for r in ok if r["n_dropped_available"]), sum(1 for r in ok if r["n_mismatch"]),
        sum(1 for r in ok if r["n_timeout"]), sum(1 for r in ok if r["n_error"]),
        sum(1 for r in ok if r["control_status"] not in (None, "match")), sum(1 for r in rows if "scan_error" in r)))


if __name__ == "__main__":
    main()
