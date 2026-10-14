#!/usr/bin/env python3
import argparse, collections, hashlib, json, os, re, sys

STAMP = "53365292b82da9d944ad0445ce1c5660"
_RES_10K = re.compile(r"(?<![\d^.*])10(1[0-8]|[2-9])(?![\d^])")
_RES_2K = re.compile(r"(?<![\d^.*])2(1[5-6]|3[0-2]|6[3-4])(?![\d^])")
_RES_MOD = re.compile(r"\b109\s*\+\s*7\b")
_CMP_LINE = re.compile(r"(<=|>=|≤|≥|(?<!-)<(?!-)|(?<!-)>(?!-)|==|modulo|\bmod\b)", re.I)
_BIT_LINE = re.compile(r"\[\s*-\s*2(?:1[5-6]|3[0-2]|6[3-4])\s*,\s*2(?:1[5-6]|3[0-2]|6[3-4])\s*-\s*1\s*\]|32-bit|64-bit|signed integer|overflow", re.I)


def flattened_residual(prompt):
    """Count flattened shapes left in the docstring (after the def line) on the lines the rules govern."""
    i = prompt.find("def ")
    doc = prompt[i:] if i >= 0 else prompt
    ten_k = two_k = 0
    for line in doc.split("\n"):
        if _CMP_LINE.search(line.replace("->", " ")):
            ten_k += len(_RES_10K.findall(line))
        if _BIT_LINE.search(line) or _CMP_LINE.search(line.replace("->", " ")):
            two_k += len(_RES_2K.findall(line))
    return {"ten_k": ten_k, "two_k": two_k, "modulus": len(_RES_MOD.findall(doc))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-raw", required=True)
    ap.add_argument("--convdir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--importer", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_import.py"))
    a = ap.parse_args()
    md5 = hashlib.md5(open(a.importer, "rb").read()).hexdigest()
    if md5 != STAMP:
        sys.exit("importer md5 %s is not the stamp of record %s; stopping" % (md5, STAMP))

    raw = {}
    for line in open(a.shard_raw):
        r = json.loads(line)
        raw[r["task_id"]] = {"split": r.get("_split") or ("test" if "test" in (r.get("_row") or "") else "train"),
                             "difficulty": r.get("difficulty"), "row": r.get("_row"),
                             "exponents_restored": r.get("_exponents_restored") or {"n": 0, "replacements": []},
                             "domain_screen": r.get("_domain_screen"), "display_form": bool(r.get("_display_form_inputs"))}

    report_in = os.path.join(a.convdir, "conversion_report.jsonl")
    tasks_in = os.path.join(a.convdir, "tasks_converted.jsonl")
    tasks_dir = os.path.join(a.outdir, "tasks")
    os.makedirs(tasks_dir, exist_ok=True)

    converted = {}
    if os.path.exists(tasks_in):
        for line in open(tasks_in):
            t = json.loads(line)
            slug = t["task_id"].split("/", 1)[1]
            converted[slug] = t

    rows, by_status, by_reason = [], collections.Counter(), collections.Counter()
    written = []
    for line in open(report_in):
        rep = json.loads(line)
        slug = rep["cand_id"].split("/", 1)[1]
        m = rep.get("metrics") or {}
        tests_kept = None
        if "n_base" in m and "n_plus" in m:
            tests_kept = m["n_base"] + m["n_plus"]
        meta = raw.get(slug, {})
        status = rep["status"]
        by_status[status] += 1
        if status != "converted":
            by_reason[rep["reason"].split(" (")[0][:80]] += 1
        exp = meta.get("exponents_restored") or {"n": 0, "replacements": []}
        row = {"cand_id": "lcds/%s" % slug, "status": status, "reason": rep["reason"],
               "tests_kept": tests_kept, "split": meta.get("split"),
               "difficulty": meta.get("difficulty"), "elapsed_s": rep.get("elapsed_s"),
               "exponents_restored": exp["n"],
               "bit_range_rule_fired": bool(exp.get("bit_range_rule")),
               "domain_dropped": len((meta.get("domain_screen") or {}).get("dropped", [])),
               "constraints_skipped": len((meta.get("domain_screen") or {}).get("constraints_skipped", []))}
        if status == "converted":
            t = converted.get(slug)
            if t is None:
                row["status"] = "needs-human"
                row["reason"] = "report says converted but no record in tasks_converted.jsonl"
                by_status["converted"] -= 1
                by_status["needs-human"] += 1
            elif meta.get("display_form"):
                row["status"] = "needs-human"
                row["reason"] = "display-form inputs: LeetCode's shown binary strings stored as digit runs and read as decimals for an int parameter; the dataset's outputs were computed on that reading"
                by_status["converted"] -= 1
                by_status["needs-human"] += 1
                by_reason["display-form inputs"] += 1
            elif flattened_residual(t["prompt"])["modulus"] or flattened_residual(t["prompt"])["two_k"]:
                fr = flattened_residual(t["prompt"])
                what = "modulus" if fr["modulus"] else "2^k-class bound"
                row["status"] = "needs-human"
                row["reason"] = "flattened %s not restored in the final statement (%s)" % (what, json.dumps(fr))
                row["flattened_residual"] = fr
                by_status["converted"] -= 1
                by_status["needs-human"] += 1
                by_reason["flattened %s not restored" % what] += 1
            else:
                out = dict(t)
                out["task_id"] = "lcds/%s" % slug
                out["contract"] = ""
                prov = dict(t.get("provenance") or {})
                prov["source_dataset"] = "newfacade/LeetCodeDataset#%s" % meta.get("split")
                prov["slug"] = slug
                out["provenance"] = prov
                conv = dict(t.get("conversion") or {})
                conv["importer"] = "bench_import.py"
                conv["importer_md5"] = md5
                conv["exponents_restored"] = exp
                if meta.get("domain_screen") is not None:
                    conv["domain_screen"] = meta["domain_screen"]
                conv["flattened_residual"] = flattened_residual(t["prompt"])
                row["flattened_residual"] = conv["flattened_residual"]
                out["conversion"] = conv
                out["twin_of_live"] = None
                content = {k: t.get(k) for k in ("prompt", "entry_point", "canonical_solution",
                                                 "base_input", "plus_input", "atol")}
                out["content_sha"] = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                out["content_sha_rule"] = "sha256 of sorted-key compact JSON over prompt, entry_point, canonical_solution, base_input, plus_input, atol"
                cert_fields = ["task_id", "prompt", "entry_point", "canonical_solution", "base_input", "plus_input", "atol", "expected_output"]
                out["content_sha256"] = hashlib.sha256(json.dumps({k: out.get(k) for k in cert_fields}, sort_keys=True).encode()).hexdigest()
                out["content_sha256_rule"] = "the certifier's (training_certify.py CONTENT_FIELDS): sha256 of json.dumps sort_keys=True, default separators, over task_id, prompt, entry_point, canonical_solution, base_input, plus_input, atol, expected_output"
                fname = "lcds__%s.json" % slug
                path = os.path.join(tasks_dir, fname)
                tmp = path + ".part"
                with open(tmp, "w") as f:
                    json.dump(out, f)
                os.replace(tmp, path)
                row["file"] = fname
                row["content_sha"] = out["content_sha"]
                row["content_sha256"] = out["content_sha256"]
                written.append(fname)
        rows.append(row)

    tmp = os.path.join(a.outdir, "report.jsonl.part")
    with open(tmp, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp, os.path.join(a.outdir, "report.jsonl"))
    manifest = {"shard_raw": os.path.basename(a.shard_raw), "candidates": len(rows),
                "by_status": dict(by_status), "by_reason": dict(by_reason),
                "files": written, "importer_md5": md5,
                "by_difficulty_converted": dict(collections.Counter(r["difficulty"] for r in rows if r["status"] == "converted")),
                "exponents_restored_records": sum(1 for r in rows if r["status"] == "converted" and r["exponents_restored"]),
                "exponents_restored_places": sum(r["exponents_restored"] for r in rows if r["status"] == "converted"),
                "bit_range_rule_records": sum(1 for r in rows if r["status"] == "converted" and r["bit_range_rule_fired"]),
                "domain_dropped_pairs": sum(r["domain_dropped"] for r in rows),
                "domain_dropped_records": sum(1 for r in rows if r["domain_dropped"]),
                "records_with_constraints_skipped": sum(1 for r in rows if r["status"] == "converted" and r["constraints_skipped"]),
                "flattened_residual_records": sum(1 for r in rows if r["status"] == "converted" and any((r.get("flattened_residual") or {}).values())),
                "by_split_converted": dict(collections.Counter(r["split"] for r in rows if r["status"] == "converted"))}
    tmp = os.path.join(a.outdir, "manifest.json.part")
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1)
    os.replace(tmp, os.path.join(a.outdir, "manifest.json"))
    print("[lcds-finish] %s: %s; %d files" % (manifest["shard_raw"], dict(by_status), len(written)))


if __name__ == "__main__":
    main()
