#!/usr/bin/env python3
import json, os, sys, hashlib
def load(p):
    with open(p) as f: return json.load(f)
def draws(cell):
    out = []
    for d in cell.get("draws") or []:
        if isinstance(d, dict): out.append((str(d.get("shard")), str(d.get("samples_sha256")), int(d.get("n") or 0), int(d.get("base") or 0), int(d.get("plus") or 0)))
    return out
def main():
    if len(sys.argv) < 4: print(__doc__); return 3
    try:
        ref = load(sys.argv[1]); live = load(sys.argv[2]); rb = open(sys.argv[3], "rb").read(); reach = json.loads(rb.decode("utf-8"))
    except Exception as e:
        print(f"LANDING-CHECK-V2 READ-ERROR {e}"); return 3
    reach_sha = hashlib.sha256(rb).hexdigest()[:16]
    rc, lc = ref.get("configs") or {}, live.get("configs") or {}
    keys = {}   # (config, task) -> set of (label, hash)
    for r in reach.get("rows") or []:
        if r.get("verdict") != "COPY": continue
        label = str(r.get("shard")) + str(r.get("part"))
        for cd in r.get("copied_draws") or []:
            keys.setdefault((str(r.get("config")), str(cd.get("task"))), set()).add((label, str(cd.get("samples_sha256"))))
    ok, findings, unserved_ok = 0, [], 0
    served_cells = 0
    for (cfg, task), ks in sorted(keys.items()):
        r = (rc.get(cfg) or {}).get(task); l = (lc.get(cfg) or {}).get(task)
        if not r or not l: findings.append(f"MISSING {cfg} x {task}: ref={'yes' if r else 'no'} live={'yes' if l else 'no'}"); continue
        rd, ld = draws(r), draws(l)
        fold = [d for d in rd if (d[0], d[1]) in ks]; keep = [d for d in rd if (d[0], d[1]) not in ks]
        if not fold:
            # reach v3: a copy file that was never judged into the census — nothing to fold; the cell must stand unchanged
            same = int(l.get("n") or 0) == int(r.get("n") or 0) and int(l.get("base") or 0) == int(r.get("base") or 0) and int(l.get("plus") or 0) == int(r.get("plus") or 0)
            if same: unserved_ok += 1
            else: findings.append(f"UNSERVED-COPY-BUT-MOVED {cfg} x {task}: no reference draw carries a keyed hash, yet the cell moved: ref n {r.get('n')} base {r.get('base')} plus {r.get('plus')} -> live n {l.get('n')} base {l.get('base')} plus {l.get('plus')}")
            continue
        served_cells += 1
        exp_n, exp_b, exp_p = int(r.get("n") or 0) - sum(d[2] for d in fold), int(r.get("base") or 0) - sum(d[3] for d in fold), int(r.get("plus") or 0) - sum(d[4] for d in fold)
        live_hashes = {(d[0], d[1]) for d in ld}
        gone_ok = all((d[0], d[1]) not in live_hashes for d in fold); kept_ok = all((d[0], d[1]) in live_hashes for d in keep)
        good = gone_ok and kept_ok and int(l.get("n") or 0) == exp_n and int(l.get("base") or 0) == exp_b and int(l.get("plus") or 0) == exp_p
        if good: ok += 1
        else: findings.append(f"KEYED {cfg} x {task}: expected n {exp_n} base {exp_b} plus {exp_p} with {len(fold)} draw(s) folded and {len(keep)} kept; live n {l.get('n')} base {l.get('base')} plus {l.get('plus')} folded_gone={gone_ok} kept_present={kept_ok}")
    falls, gone, rises = [], [], 0
    for cfg, tasks in rc.items():
        if not isinstance(tasks, dict): continue
        for task, r in tasks.items():
            if (cfg, task) in keys or not isinstance(r, dict): continue
            l = (lc.get(cfg) or {}).get(task)
            if l is None: gone.append(f"{cfg} x {task}"); continue
            if int(l.get("n") or 0) < int(r.get("n") or 0): falls.append(f"{cfg} x {task}: n {r.get('n')} -> {l.get('n')}")
            elif int(l.get("n") or 0) > int(r.get("n") or 0): rises += 1
    h = live.get("_pooled_copy_fold") or {}
    _rs = h.get("reaches") if isinstance(h.get("reaches"), list) else None
    if _rs is not None:
        _mine = [r for r in _rs if isinstance(r, dict) and str(r.get("sha16")) == reach_sha]
        header_ok = bool(h) and bool(_mine) and all(bool(r.get("pin_ok")) and str(r.get("pin")) == reach_sha for r in _mine) and int(h.get("rows_folded_at_read") or 0) > 0
        header_note = "reaches[]: " + ", ".join(f"{os.path.basename(str(r.get('path')))} pin_ok={r.get('pin_ok')} sha16={r.get('sha16')} cells={r.get('cells_listed')}" for r in _rs)
    else:
        header_ok = bool(h) and bool(h.get("pin_ok")) and str(h.get("reach_sha16")) == reach_sha and int(h.get("rows_folded_at_read") or 0) > 0
        header_note = "v2 header form"
    verdict = "PASS" if (ok == served_cells and ok + unserved_ok == len(keys) and not falls and not gone and header_ok) else "FAIL"
    print(f"LANDING-CHECK-V3 {live.get('_stamp')} vs {ref.get('_stamp')} {verdict} served_cells_ok={ok}/{served_cells} unserved_unchanged={unserved_ok}/{len(keys)-served_cells} falls_outside={len(falls)} gone={len(gone)} rises={rises} header_ok={header_ok} "
          f"(pin_ok={h.get('pin_ok')} reach_sha16={h.get('reach_sha16')} reach_file_sha16={reach_sha} cells_listed={h.get('cells_listed')} rows_folded_at_read={h.get('rows_folded_at_read')} note={h.get('note')} {header_note})")
    for f in findings[:80]: print("  " + f)
    for f in falls[:40]: print("  FALL-OUTSIDE " + f)
    for f in gone[:40]: print("  GONE " + f)
    return 0 if verdict == "PASS" else 2
if __name__ == "__main__": sys.exit(main())
