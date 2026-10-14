import hashlib, json, os, sys, time

R = ''
T = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/'
ROW_PFX = ('/arms/', '/elements_of_record/', '/composite_gate_failed_arms', '/frame_disclosure', '/series/', '/crossings_of_record/rows')

def leaves(d, pre='', out=None):
    if out is None: out = {}
    if isinstance(d, dict):
        for k, v in d.items(): leaves(v, pre + '/' + str(k), out)
    elif isinstance(d, list):
        for i, v in enumerate(d): leaves(v, pre + '/' + str(i), out)
    else: out[pre] = d
    return out

def is_row_leaf(k):
    if k.startswith('/elements_of_record_basis'): return False
    return any(k.startswith(p) for p in ROW_PFX)

def main(argv):
    row = None
    if '--row' in argv:
        i = argv.index('--row'); row = (argv[i + 1], argv[i + 2]); argv = argv[:i] + argv[i + 3:]
    a = leaves(json.load(open(argv[1]))); b = leaves(json.load(open(argv[2])))
    mx = int(argv[3]) if len(argv) > 3 else 60
    keys = sorted(set(a) | set(b))
    n = 0; row_hits = []
    for k in keys:
        if k in a and k in b and a[k] == b[k]: continue
        n += 1
        if is_row_leaf(k): row_hits.append(k)
        if n > mx: continue
        if k not in a: print(f"ADDED   {k} = {str(b[k])[:90]!r}")
        elif k not in b: print(f"REMOVED {k} = {str(a[k])[:90]!r}")
        else: print(f"CHANGED {k}: {str(a[k])[:70]!r} -> {str(b[k])[:70]!r}")
    print(f"{n} leaf path(s) differ ({len(a)} leaves in a, {len(b)} in b); row, figure or gate leaves among them: {len(row_hits)}" + (f" — first {row_hits[0]}" if row_hits else ''))
    if row:
        verdict = 'HOLD' if row_hits else 'CLEAN'
        reason = (f"{len(row_hits)} row/figure/gate leaf path(s) differ, first {row_hits[0]}" if row_hits else '').replace('\t', ' ')[:300]
        stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        os.makedirs(T + 'state', exist_ok=True)
        if row[0] == 'flip':
            sha12 = hashlib.sha256(open(argv[2], 'rb').read()).hexdigest()[:12]
            with open(T + 'state/flip_reads.tsv', 'a') as f:
                f.write('\t'.join([stamp, os.path.basename(argv[2]), sha12, verdict, (reason or row[1])]) + '\n')
            print(f"VERDICT: {verdict} (flip row written for {os.path.basename(argv[2])} {sha12}: {row[1]})")
        else:
            sha12 = hashlib.sha256(open(argv[1], 'rb').read()).hexdigest()[:12]
            with open(T + 'state/staging_reads.tsv', 'a') as f:
                f.write('\t'.join([stamp, os.path.relpath(os.path.abspath(argv[1]), R), sha12, row[0], verdict, row[1], reason]) + '\n')
            print(f"VERDICT: {verdict} (row written: {row[0]} {sha12} {row[1]})")
        return 0 if verdict == 'CLEAN' else 2
    return 0

if __name__ == '__main__': sys.exit(main(sys.argv))
