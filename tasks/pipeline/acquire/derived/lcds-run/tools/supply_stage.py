#!/usr/bin/env python3
import argparse, collections, json, os, re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--exclude", required=True)
    ap.add_argument("--outdir", required=True); ap.add_argument("--shard-size", type=int, default=25)
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    excl = set(l.strip().upper() for l in open(a.exclude) if l.strip())
    os.makedirs(a.outdir, exist_ok=True)
    kept, dropped = [], collections.Counter()
    buckets = collections.Counter(); ge5 = 0; pyref = 0; n_in = 0
    for line in open(a.inp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        n_in += 1
        r = json.loads(line)
        cid = r.get("cand_id", "")
        m = re.match(r"(?:ccplus|openr1)/(\d+)_([A-Za-z]\d?)$", cid)
        key = ("%s_%s" % (m.group(1), m.group(2).upper())) if m else None
        if key is None:
            dropped["no_codeforces_key"] += 1; continue
        if key in excl:
            dropped["twin_key_excluded"] += 1; continue
        if r.get("input_mode") not in (None, "stdio"):
            dropped["input_mode_" + str(r.get("input_mode"))] += 1; continue
        kept.append(line)
        rt = r.get("rating")
        buckets[str((rt // 200) * 200) if isinstance(rt, int) else "none"] += 1
        ge5 += len(r.get("tests") or []) >= 5
        pyref += bool(r.get("reference_candidates"))
    shards = []
    for i in range(0, len(kept), a.shard_size):
        name = "s%03d.jsonl" % (i // a.shard_size)
        with open(os.path.join(a.outdir, name), "w", encoding="utf-8") as f:
            f.write("\n".join(kept[i:i + a.shard_size]) + "\n")
        shards.append(name)
    man = {"in": n_in, "dropped": dict(dropped), "kept": len(kept), "by_rating_bucket": dict(sorted(buckets.items())),
           "kept_with_5_or_more_tests": ge5, "kept_with_python_reference": pyref, "shards": len(shards), "shard_size": a.shard_size,
           "exclusion_keys": len(excl), "source": a.inp}
    with open(a.manifest, "w") as f:
        json.dump(man, f, indent=1)
    print("STAGE", json.dumps(man))


if __name__ == "__main__":
    main()
