#!/usr/bin/env python3
"""Derive EvalPlus-format input contracts from provenance.declared_input_shapes (certify's stage-0 gate needs them),
verify each contract against EVERY base+plus input, and rewrite a records file in place (TEMP+RENAME) with only the
contract field changed. Format matches shipped EasyTail/HumanEval records:
    "\\n    assert <cond>, \\"invalid inputs\\" # $_CONTRACT_$\\n..."
Usage: python3 tools/easypilot/add_contracts.py FILE [FILE ...] [--force] [--manifest MANIFEST.json]"""
import argparse, hashlib, json, os, sys, time

SEAT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SEAT, "tools"))
from derive_input_types import arg_names  # noqa: E402

LINE = '    assert {cond}, "invalid inputs" # $_CONTRACT_$\n'


def cond_for(name, shape):
    s = (shape or "any").strip()
    if s == "int":
        return f"isinstance({name}, int) and not isinstance({name}, bool)"
    if s == "float":
        return f"isinstance({name}, (int, float)) and not isinstance({name}, bool)"
    if s == "bool":
        return f"isinstance({name}, bool)"
    if s == "str":
        return f"isinstance({name}, str)"
    if s == "None":
        return f"{name} is None"
    if s.startswith("list[") and s.endswith("]"):
        inner = s[5:-1]
        if inner == "int":
            return f"isinstance({name}, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in {name})"
        if inner == "float":
            return f"isinstance({name}, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in {name})"
        if inner == "str":
            return f"isinstance({name}, list) and all(isinstance(v, str) for v in {name})"
        if inner.startswith("list[int]"):
            return f"isinstance({name}, list) and all(isinstance(r, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in r) for r in {name})"
        if inner.startswith("list[") or inner.startswith("tuple["):
            return f"isinstance({name}, list) and all(isinstance(r, (list, tuple)) for r in {name})"
        return f"isinstance({name}, list)"
    if s.startswith("tuple["):
        return f"isinstance({name}, (tuple, list))"
    if s.startswith("dict["):
        return f"isinstance({name}, dict)"
    if s.startswith(("set[", "frozenset[")):
        return f"isinstance({name}, (set, frozenset, list))"
    return None  # any: no assertion


def contract_for(names, shapes):
    conds = [cond_for(n, sh) for n, sh in zip(names, shapes)]
    conds = [c for c in conds if c]
    return ("\n" + "".join(LINE.format(cond=c) for c in conds)) if conds else ""


def verify(contract, names, inputs):
    src = f"def _chk({', '.join(names)}):\n" + (contract.strip("\n") + "\n" if contract.strip() else "") + "    return True\n"
    g = {}; exec(src, g)
    for i, args in enumerate(inputs):
        try:
            g["_chk"](*args)
        except AssertionError:
            return f"contract rejects input #{i}: {json.dumps(args)[:80]}"
        except TypeError as e:
            return f"arity/type problem at input #{i}: {e}"
    return None


def process(path, force=False):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    changed, problems = 0, []
    for r in recs:
        if r.get("contract") and not force:
            continue
        names = arg_names(r["prompt"], r["entry_point"]) or []
        shapes = r.get("provenance", {}).get("declared_input_shapes") or []
        if not names or len(shapes) != len(names):
            problems.append((r["task_id"], f"names {names} vs shapes {shapes}")); continue
        c = contract_for(names, shapes)
        err = verify(c, names, r["base_input"] + r["plus_input"])
        if err:
            problems.append((r["task_id"], err)); continue
        r["contract"] = c; changed += 1
    body = "".join(json.dumps(r) + "\n" for r in recs)
    with open(path + ".tmp", "w") as f:
        f.write(body)
    os.replace(path + ".tmp", path)
    return changed, len(recs), problems, hashlib.sha256(body.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+"); ap.add_argument("--force", action="store_true"); ap.add_argument("--manifest", nargs="*", default=[])
    a = ap.parse_args()
    for i, p in enumerate(a.files):
        changed, n, problems, sha = process(p, a.force)
        print(json.dumps({"file": os.path.basename(p), "records": n, "contracts_added": changed, "problems": problems, "sha256": sha[:16]}))
        if i < len(a.manifest) and os.path.exists(a.manifest[i]):
            m = json.load(open(a.manifest[i])); m["sha256"] = sha; m["contracts_added"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            m["contract_source"] = "derived from provenance.declared_input_shapes; verified against every base+plus input"
            json.dump(m, open(a.manifest[i], "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
