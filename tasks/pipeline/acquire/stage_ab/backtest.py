#!/usr/bin/env python3
"""Stage A driver: run the admission screens blind over the existing pool,
join against the audit labels, and score hit rate / false-alarm rate.

False alarms are additionally scored against KNOWN-GENUINE HARD tasks
(label genuine AND mean strong-panel fail rate >= 50% in the recorded
128-attempt matrix) — the tasks the every-strong-model-fails heuristic
most wants to eat.
"""

import argparse
import concurrent.futures
import csv
import json
import os
import random
import sys
import time

import screens as S

LABEL_FILES = [
    "tasks/labels/labels_humaneval.jsonl",
    "tasks/labels/labels_mbpp.jsonl",
]
DEFECTIVE_LABELS = {"underspecification", "contradiction"}
GENUINE_LABELS = {"regular", "tricky"}
HARD_GENUINE_FAILRATE = 0.50   # mean strong-panel fail rate for "hard"
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "artifacts")


def load_labels():
    labels = {}
    for path in LABEL_FILES:
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                labels[r["task_id"]] = r["label"]
    return labels


def mean_strong_fail(tid, fail_matrix):
    row = fail_matrix.get(tid)
    if not row:
        return None
    rates = [row[m][0] / row[m][1] for m in S.STRONG_MODELS if m in row]
    return sum(rates) / len(rates) if rates else None


def pick_sample(n, labels, fail_matrix, seed):
    """Seeded stratified sample: keep the defective/genuine mix, force in
    at least one defective and one known-genuine-hard task when available."""
    rng = random.Random(seed)
    tids = sorted(labels)
    defective = [t for t in tids if labels[t] in DEFECTIVE_LABELS]
    genuine = [t for t in tids if labels[t] in GENUINE_LABELS]
    hard = [t for t in genuine
            if (mean_strong_fail(t, fail_matrix) or 0) >= HARD_GENUINE_FAILRATE]
    n_def = min(len(defective), max(1, round(n * len(defective) / len(tids))))
    n_hard = min(len(hard), 1) if n >= 5 else 0
    picked = rng.sample(defective, n_def) + rng.sample(hard, n_hard)
    rest = [t for t in genuine if t not in picked]
    picked += rng.sample(rest, max(0, min(n - len(picked), len(rest))))
    return sorted(picked[:n])


def rate(num, den):
    return "%d/%d (%.1f%%)" % (num, den, 100 * num / den) if den else "0/0 (–)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, metavar="N",
                    help="run on a seeded stratified sample of N tasks "
                         "(smoke mode); omit for the full pool")
    ap.add_argument("--seed", type=int, default=S.SEED)
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel task executions (default 4)")
    ap.add_argument("--out", default=ARTIFACTS,
                    help="artifacts directory (default ./artifacts)")
    args = ap.parse_args()

    t0 = time.time()
    labels = load_labels()
    pool = S.load_pool()
    missing = sorted(set(labels) - set(pool)) + sorted(set(pool) - set(labels))
    if missing:
        print("WARNING: label/pool id mismatch on %d tasks: %s"
              % (len(missing), missing[:5]), file=sys.stderr)
    ctx = S.Ctx(pool)

    tids = (pick_sample(args.sample, labels, ctx.fail_matrix, args.seed)
            if args.sample else sorted(set(labels) & set(pool)))
    mode = ("SAMPLE n=%d seed=%d" % (len(tids), args.seed)
            if args.sample else "FULL POOL n=%d" % len(tids))
    print("Stage A back-test — %s — screens blind to labels" % mode)

    # ---- execute (screens are blind: they see only task data + fail matrix)
    def prewarm(tid):
        ctx.get_exec(pool[tid])
        return tid
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for k, _ in enumerate(ex.map(prewarm, tids), 1):
            if k % 25 == 0 or k == len(tids):
                print("  executed %d/%d tasks (%.0fs)"
                      % (k, len(tids), time.time() - t0), file=sys.stderr)

    results = {tid: S.run_all_screens(pool[tid], ctx) for tid in tids}

    # ---- join against ground truth and score
    screen_names = [fn.__name__.replace("screen_", "")
                    for fn in S.ALL_SCREENS]
    defective = [t for t in tids if labels[t] in DEFECTIVE_LABELS]
    genuine = [t for t in tids if labels[t] in GENUINE_LABELS]
    hard_genuine = [t for t in genuine
                    if (mean_strong_fail(t, ctx.fail_matrix) or 0)
                    >= HARD_GENUINE_FAILRATE]

    flags = {t: {r["screen"] for r in results[t] if r["verdict"] == "flag"}
             for t in tids}

    def union_flag(t, exclude=()):
        return bool(flags[t] - set(exclude))

    # per-screen table
    lines = []
    hdr = ("%-32s %8s %14s %20s %26s"
           % ("screen", "flagged", "hits(def=%d)" % len(defective),
              "false-alarms(gen=%d)" % len(genuine),
              "hard-genuine eaten(n=%d)" % len(hard_genuine)))
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for name in screen_names:
        fl = [t for t in tids if name in flags[t]]
        lines.append("%-32s %8d %14s %20s %26s" % (
            name, len(fl),
            rate(sum(1 for t in fl if t in defective), len(defective)),
            rate(sum(1 for t in fl if t in genuine), len(genuine)),
            rate(sum(1 for t in fl if t in hard_genuine), len(hard_genuine))))
    for label, excl in [("UNION (any screen)", ()),
                        ("UNION minus mutation_adequacy",
                         ("mutation_adequacy",))]:
        fl = [t for t in tids if union_flag(t, excl)]
        lines.append("%-32s %8d %14s %20s %26s" % (
            label, len(fl),
            rate(sum(1 for t in fl if t in defective), len(defective)),
            rate(sum(1 for t in fl if t in genuine), len(genuine)),
            rate(sum(1 for t in fl if t in hard_genuine), len(hard_genuine))))
    table = "\n".join(lines)

    gate = (
        "Gate readout: hit rate = flagged known-defective tasks "
        "(underspecification+contradiction) / all known-defective in run; "
        "false-alarm rate = flagged known-genuine / all known-genuine; "
        "hard-genuine eaten = flagged known-genuine hard tasks (mean "
        "strong-panel fail rate >= %.0f%%) — the every-strong-model-fails "
        "row of that column is the deliberate stress test."
        % (100 * HARD_GENUINE_FAILRATE))

    print()
    print(table)
    print()
    print(gate)
    print("Elapsed: %.0fs" % (time.time() - t0))

    # ---- artifacts
    os.makedirs(args.out, exist_ok=True)
    tag = "sample%d" % len(tids) if args.sample else "full"
    verdicts_path = os.path.join(args.out, "verdicts_%s.csv" % tag)
    with open(verdicts_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "label", "label_class", "mean_strong_fail",
                    "screen", "verdict", "reason"])
        for t in tids:
            cls = ("defective" if labels[t] in DEFECTIVE_LABELS else
                   "genuine-hard" if t in hard_genuine else "genuine")
            msf = mean_strong_fail(t, ctx.fail_matrix)
            for r in results[t]:
                w.writerow([t, labels[t], cls,
                            "" if msf is None else round(msf, 4),
                            r["screen"], r["verdict"], r["reason"]])
    summary_path = os.path.join(args.out, "summary_%s.txt" % tag)
    with open(summary_path, "w") as f:
        f.write("Stage A back-test — %s\n\n%s\n\n%s\n" % (mode, table, gate))
    print("Artifacts: %s , %s" % (verdicts_path, summary_path))


if __name__ == "__main__":
    main()
