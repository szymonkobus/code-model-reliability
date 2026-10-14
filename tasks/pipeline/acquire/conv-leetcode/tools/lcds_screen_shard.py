#!/usr/bin/env python3
"""python3 lcds_screen_shard.py --in <raw shard> --out <screened shard>"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_import as bi           # the pipeline's importer (md5 of record); read-only use of two readers
from domain_screen import parse_signature, parse_constraints, type_ok

_BIN_RUN = re.compile(r"=\s*[01]{16,}\b")


def screen_record(rec):
    desc = rec.get("problem_description") or ""
    ep = (rec.get("entry_point") or "").strip()
    fname = ep.split(".")[-1].split("(")[0]
    try:
        params, header = bi.leetcode_signature(rec.get("starter_code") or "", fname)
    except Exception as e:
        return rec, {"error": "starter parse failed: %s" % e}
    prompt = "%s\n    \"\"\"%s\n    \"\"\"\n" % (header, desc.replace("\n", "\n    "))
    sig = parse_signature(prompt, fname)
    preds, skipped = parse_constraints(prompt, sig)
    ann = {n: a for n, a in sig}
    kept, dropped = [], []
    display_form = False
    for io in rec.get("input_output") or []:
        inp = io.get("input", "")
        try:
            args = bi.parse_kwarg_call(inp, params)
            json.dumps(args)         # a pair with a non-JSON value (an abbreviated list parsed to Ellipsis) is the converter's to drop
        except Exception:
            kept.append(io)          # the converter drops what it cannot parse; not this screen's call
            continue
        if _BIN_RUN.search(inp):
            # a decimal literal never starts with 0; a run of 0/1 digits for an int parameter is a shown binary
            # string when it has leading zeros or the statement says the input is a binary string
            for (n, a), v in zip(sig, args):
                m = re.search(r"%s\s*=\s*([01]{16,})\b" % re.escape(n), inp)
                if a.replace(" ", "") == "int" and isinstance(v, int) and m and (m.group(1).startswith("0") or "binary string" in desc.lower()):
                    display_form = True
        by = {n: v for (n, _), v in zip(sig, args)}
        why = []
        for (n, a), v in zip(sig, args):
            if a and not type_ok(v, a):
                why.append("%s=%s is not of the stated type %s" % (n, json.dumps(v, default=str)[:40], a))
        for text, fn in preds:
            try:
                why.extend(fn(by))
            except Exception:
                pass
        if why:
            dropped.append({"input": inp[:300], "why": why[:4]})
        else:
            kept.append(io)
    out = dict(rec)
    out["input_output"] = kept
    out["_domain_screen"] = {"constraints_evaluated": [t for t, _ in preds], "constraints_skipped": skipped,
                             "dropped": dropped, "n_before": len(rec.get("input_output") or []), "kept": len(kept),
                             "rule": "domain_screen.py (train-conv-leetcode): a stored input violating an evaluated constraint of the docstring is dropped at source; constraints_skipped are read by the checker"}
    if display_form:
        out["_display_form_inputs"] = True
    return out, out["_domain_screen"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    n = n_drop = n_rec_drop = n_under5 = n_disp = 0
    tmp = a.out + ".part"
    with open(a.inp) as f, open(tmp, "w") as g:
        for line in f:
            rec = json.loads(line)
            out, ds = screen_record(rec)
            n += 1
            if ds.get("dropped"):
                n_rec_drop += 1; n_drop += len(ds["dropped"])
            if ds.get("kept", 99) < 5:
                n_under5 += 1
            if out.get("_display_form_inputs"):
                n_disp += 1
            g.write(json.dumps(out, default=str) + "\n")
    os.replace(tmp, a.out)
    print("[lcds-screen] %s: %d records; %d records lost %d out-of-domain pairs; %d records now under 5 pairs; %d display-form"
          % (os.path.basename(a.inp), n, n_rec_drop, n_drop, n_under5, n_disp), flush=True)


if __name__ == "__main__":
    main()
