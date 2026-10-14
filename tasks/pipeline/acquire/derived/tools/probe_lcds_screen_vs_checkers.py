#!/usr/bin/env python3
import argparse, glob, importlib.util, json, os


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def flagged(mod, rec):
    inputs = list(rec["base_input"]) + list(rec["plus_input"])
    viol, evaluated, skipped = mod.screen(rec["prompt"], rec["entry_point"], inputs)
    out = {}
    for v in viol:
        i = int(v["where"].split()[1])
        out[i] = v["why"]
    return out, evaluated, skipped


def truth_indices(t, nb):
    idx = {}
    for i, why in (t.get("base") or {}).items():
        idx[int(i)] = why
    for i, why in (t.get("plus") or {}).items():
        idx[int(i) + nb] = why
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True); ap.add_argument("--old", default="")
    ap.add_argument("--predicates", required=True); ap.add_argument("--incoming", required=True)
    ap.add_argument("--show", type=int, default=40)
    a = ap.parse_args()
    new = load(a.new, "ds_new"); old = load(a.old, "ds_old") if a.old else None
    truth = {}
    for f in sorted(glob.glob(a.predicates)):
        truth.update(json.load(open(f)))
    tot = {"records": 0, "inputs": 0, "truth": 0}
    stats = {"new": {"caught": 0, "missed": 0, "extra": 0, "flagged": 0}, "old": {"caught": 0, "missed": 0, "extra": 0, "flagged": 0}}
    extras, gains = [], []
    ev = {"new": 0, "old": 0}
    for slug, t in sorted(truth.items()):
        f = os.path.join(a.incoming, "lcds__%s.json" % slug)
        if not os.path.exists(f):
            continue
        rec = json.load(open(f))
        nb = len(rec["base_input"])
        tr = truth_indices(t, nb)
        tot["records"] += 1; tot["inputs"] += nb + len(rec["plus_input"]); tot["truth"] += len(tr)
        fn, evn, skn = flagged(new, rec); ev["new"] += len(set(evn))
        stats["new"]["flagged"] += len(fn)
        stats["new"]["caught"] += len(set(fn) & set(tr)); stats["new"]["missed"] += len(set(tr) - set(fn)); stats["new"]["extra"] += len(set(fn) - set(tr))
        for i in sorted(set(fn) - set(tr)):
            extras.append((slug, i, fn[i][:2]))
        if old:
            fo, evo, sko = flagged(old, rec); ev["old"] += len(set(evo))
            stats["old"]["flagged"] += len(fo)
            stats["old"]["caught"] += len(set(fo) & set(tr)); stats["old"]["missed"] += len(set(tr) - set(fo)); stats["old"]["extra"] += len(set(fo) - set(tr))
            newly = set(fn) - set(fo)
            if newly:
                gains.append((slug, len(newly), len(newly & set(tr)), sorted(newly - set(tr))[:5], fn[sorted(newly)[0]][0][:90]))
    print("records %d, inputs %d, checkers' flagged inputs %d" % (tot["records"], tot["inputs"], tot["truth"]))
    for k in (("old",) if old else ()) + ("new",):
        s = stats[k]
        print("%s screen: flagged %d — caught %d of the checkers' %d, missed %d, EXTRA (screen only) %d; constraint lines evaluated %d"
              % (k, s["flagged"], s["caught"], tot["truth"], s["missed"], s["extra"], ev[k]))
    if old:
        print("--- records where the new screen flags inputs the old did not (slug, newly flagged, of them in the checkers' set, extras, a reason):")
        for g in gains[:a.show]:
            print("   ", g)
    print("--- EXTRA under the new screen (flagged by the screen, not by the checkers): %d" % len(extras))
    for e in extras[:a.show]:
        print("   ", e)


if __name__ == "__main__":
    main()
