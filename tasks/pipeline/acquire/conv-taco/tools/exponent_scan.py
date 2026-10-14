#!/usr/bin/env python3
"""Some TACO-verified statements were scraped without their superscripts:
"1 ≤ n ≤ 105" for 10^5, "2·105" for 2·10^5, "≤ 1018" for 10^18, "modulo
109 + 7" for 10^9 + 7. Such a bound misleads a reader (the tests exceed
the stated bound) and the modulus is wrong as written. The LaTeX form
"$10^5$" is intact and passes.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KNOW = os.path.join(os.path.dirname(HERE), "knowledge")
INCOMING = "tasks/build/training-pool/incoming"
TASK_DIR = os.path.join(INCOMING, "taco")
LANDINGS = os.path.join(INCOMING, "LANDINGS.md")
HELD_DIR = os.path.join(KNOW, "held_flattened")

_CMP = r"(?:\\le|\\leq|≤|<=|<)\s*"
_WORDED = (r"(?:exceed(?:s|ing)?|at most|no more than|not more than|up to|"
           r"at least|no less than|not less than|less than|greater than|"
           r"more than|not exceeding|does not exceed|doesn't exceed)\s+")
PATTERNS = {
    "A": re.compile(r"\b109\s*\+\s*7\b"),
    "B": re.compile(_CMP + r"(?:[1-9]\s*[·*×]\s*)?10[1-9]\b(?!\s*[.,]\d)(?!\^)"),
    "C": re.compile(_CMP + r"(?:[1-9]\s*[·*×]\s*)?101[0-9]\b(?!\^)"),
    "D": re.compile(r"\b[1-9]\s*[·*×]\s*10[1-9]\b(?!\^)"),
    "E": re.compile(_WORDED + r"(?:[1-9]\s*[·*×]\s*)?10(?:[1-9]|1[0-9])\b"
                    r"(?!\s*[.,]\d)(?!\^)", re.I),
}
REASON = ("flattened exponent in the source statement (a superscript lost "
          "at scrape, e.g. '≤ 105' for 10^5 or '109 + 7' for 10^9 + 7): held "
          "back, never listed, until a repair pass restores the exponents")


def flattened_hits(prompt):
    hits = []
    for k, rx in PATTERNS.items():
        for m in rx.finditer(prompt or ""):
            hits.append({"class": k,
                         "context": prompt[max(0, m.start() - 40):m.end() + 20]
                         .replace("\n", " ")})
    return hits


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pull", action="store_true")
    a = ap.parse_args()
    marked = []
    for f in sorted(glob.glob(os.path.join(TASK_DIR, "*.json"))):
        rec = json.load(open(f))
        hits = flattened_hits(rec.get("prompt", ""))
        if hits:
            marked.append({"task_id": rec["task_id"], "path": f, "hits": hits})
    os.makedirs(KNOW, exist_ok=True)
    atomic_write(os.path.join(KNOW, "flattened_exponents.jsonl"),
                 "".join(json.dumps(m) + "\n" for m in marked))
    print("marked %d of %d landed records" % (
        len(marked), len(glob.glob(os.path.join(TASK_DIR, "*.json")))))
    for m in marked:
        print("  %-16s %s | %s" % (m["task_id"], m["hits"][0]["class"],
                                   m["hits"][0]["context"][:90]))
    if not a.pull or not marked:
        return

    landed = {}
    lp = os.path.join(KNOW, "landed_ids.txt")
    for line in open(lp):
        parts = line.split()
        if parts:
            landed[parts[0]] = parts[1] if len(parts) > 1 else "?"
    by_batch = {}
    for m in marked:
        b = landed.get(m["task_id"], "?")
        by_batch.setdefault(b, []).append(m)
    os.makedirs(HELD_DIR, exist_ok=True)
    touched = []
    for b, ms in sorted(by_batch.items()):
        list_path = os.path.join(INCOMING, b + ".txt")
        rep_path = os.path.join(INCOMING, b + ".report.jsonl")
        if not os.path.exists(list_path):
            print("no list for %s (%d records) — skipped" % (b, len(ms)))
            continue
        drop_paths = {m["path"] for m in ms}
        drop_ids = {m["task_id"] for m in ms}
        lines = [l for l in open(list_path).read().splitlines() if l.strip()]
        kept = [l for l in lines if l not in drop_paths]
        rows = [json.loads(l) for l in open(rep_path) if l.strip()]
        kept_rows = [r for r in rows if r["cand_id"] not in drop_ids]
        dropped_rows = [r for r in rows if r["cand_id"] in drop_ids]
        # report rows first, then the list (a reader of the list sees a
        # complete report), then the files leave the intake
        atomic_write(rep_path, "".join(json.dumps(r) + "\n" for r in kept_rows))
        atomic_write(list_path, "".join(l + "\n" for l in kept))
        for m in ms:
            if os.path.exists(m["path"]):
                shutil.move(m["path"], os.path.join(HELD_DIR,
                                                    os.path.basename(m["path"])))
            landed[m["task_id"]] = "held-flattened"
        with open(os.path.join(KNOW, "taco_not_converted.jsonl"), "a") as f:
            for m in ms:
                row = next((r for r in dropped_rows if r["cand_id"] == m["task_id"]),
                           {"cand_id": m["task_id"]})
                f.write(json.dumps(dict(row, status="needs-human", reason=REASON,
                                        flattened_hits=m["hits"],
                                        pulled_from=b, pulled_at=now_iso(),
                                        converted_status_before="converted")) + "\n")
        sha = sha256_file(list_path)
        touched.append((b, len(lines), len(kept), sha))
        form = kept_rows[0].get("form", "?") if kept_rows else "?"
        with open(LANDINGS, "a") as f:
            f.write("%s | %s.txt | %d records, form %s (list rewritten: %d "
                    "records with a flattened exponent in the source statement "
                    "held back, never to be checked as landed) | "
                    "likaixin/TACO-verified#train | sha256 of the list now %s | "
                    "twins excluded: unchanged | train-conv-taco\n"
                    % (now_iso(), b, len(kept), form, len(lines) - len(kept), sha))
    atomic_write(lp, "".join("%s %s\n" % (k, v) for k, v in sorted(landed.items())))
    # batches.tsv: rewrite the touched rows' count and sha
    bp = os.path.join(KNOW, "batches.tsv")
    out = []
    for line in open(bp):
        parts = line.rstrip("\n").split("\t")
        for b, n_old, n_new, sha in touched:
            if parts and parts[0] == b:
                parts[2] = str(n_new)
                parts[3] = sha
        out.append("\t".join(parts) + "\n")
    atomic_write(bp, "".join(out))
    print("\nPULLED %d records; lists rewritten:" % len(marked))
    for b, n_old, n_new, sha in touched:
        print("  %s %d -> %d records, sha256 %s" % (b, n_old, n_new, sha))


if __name__ == "__main__":
    main()
