import glob, gzip, json, math, os
from datetime import datetime, timezone
from collections import Counter, defaultdict
W = 'runs/fail-reruns'
os.makedirs(f'{W}/out', exist_ok=True)

def load_plusfilter():
    p = f'{W}/out/plusfilter.json'
    if not os.path.exists(p): return None
    return {k: sorted(v) for k, v in json.load(open(p)).items()}
PLUSFILTER = load_plusfilter()
ABORT_REEXEC = set()
def mask_vector(task, fp, n_base):
    if PLUSFILTER is None or task not in PLUSFILTER or fp is None or fp.startswith('EXEC'):
        return fp
    keep = PLUSFILTER[task]
    if 'A' in fp: ABORT_REEXEC.add(task)
    return fp[:n_base] + ''.join(fp[n_base + i] for i in keep if n_base + i < len(fp))

import re as _re
def rank_of(sem):
    if sem is None: return 0.0
    if sem == 'standalone-v2': return 1.0
    m = _re.match(r'preamble-v([0-9.]+)$', sem)
    return 1.0 + float(m.group(1)) if m else 0.0   # preamble-v2 -> 3, v3 -> 4, v4 -> 5, v4.1 -> 5.1
import hashlib
CUR_SHA = hashlib.sha256(open(f'{W}/preamble_transform.py', 'rb').read()).hexdigest()
vec = {}
rank = {}
for pp in glob.glob(f'{W}/parts/*.json'):
    r = json.load(open(pp))
    task = os.path.basename(pp).split('__')[0].replace('-', '/', 1)
    rk = (rank_of(r.get('semantics')), 1 if r.get('transform_sha256') == CUR_SHA else 0)
    prefiltered = r.get('inputs') == 'boolfiltered-v1'
    for sid, s in r['shapes'].items():
        k = (task, sid)
        if k in rank and rank[k] > rk:
            continue
        if s.get('exec_error') is not None:
            fp = 'EXEC:' + s['exec_error'].split('(')[0]
        elif prefiltered:
            fp = s['vector']
        else:
            fp = mask_vector(task, s['vector'], r.get('n_base', 0))
        vec[k] = fp
        rank[k] = rk

with gzip.open(f'{W}/out/fullset_vectors.jsonl.gz', 'wt') as f:
    for (t, sh), fp in sorted(vec.items()):
        f.write(json.dumps({'task_id': t, 'shape': sh, 'fingerprint': fp}) + '\n')

# attempts -> per-(cell,task) fingerprint counters
att = defaultdict(list)  # (cell, task) -> [(sample, shape)]
for line in gzip.open(f'{W}/attempts.jsonl.gz', 'rt'):
    a = json.loads(line)
    att[(a['cell'], a['task_id'])].append((a['sample'], a['shape']))

def stats(counts):
    n = sum(counts); K = len(counts)
    modal = max(counts) / n
    coll = sum(c*(c-1) for c in counts) / (n*(n-1)) if n > 1 else 1.0
    H = -sum((c/n) * math.log2(c/n) for c in counts)
    Hmm = H + (K-1) / (2*n*math.log(2))
    return n, K, modal, coll, H, Hmm

theirs = {}
order = []
for line in open('deep-dives/rare-failures/meta/consistency_tasks.jsonl'):
    r = json.loads(line)
    theirs[(r['cell'], r['task_id'])] = r
    order.append((r['cell'], r['task_id']))

rows_done = 0
out_rows = []
for key in order:
    cell, task = key
    pairs = att.get(key, [])
    fps = []
    complete = True
    for sample, sh in pairs:
        f = vec.get((task, sh))
        if f is None: complete = False; break
        fps.append(f)
    if not complete or len(fps) < 2: continue
    cnt = Counter(fps)
    n, K, modal, coll, H, Hmm = stats(sorted(cnt.values()))
    t = theirs[key]
    modal_fp = max(cnt, key=cnt.get)
    out_rows.append({'cell': cell, 'task_id': task, 'n_fails': n,
        'fp': {'n': n, 'distinct': K, 'modal_share': round(modal, 4),
               'collision': round(coll, 4), 'H_bits': round(H, 4),
               'H_mm_bits': round(Hmm, 4)},
        'shape': t['shape'], 'modal_fp': modal_fp,
        'outcome_entropy_bits': t['outcome_entropy_bits']})
    rows_done += 1
with open(f'{W}/out/consistency_tasks_fullset.jsonl', 'w') as f:
    for r in out_rows:
        f.write(json.dumps(r) + '\n')

# board: fail-weighted aggregates per cell (their exact fields)
ref_board = json.load(open('deep-dives/rare-failures/meta/consistency_board.json'))
by_cell = defaultdict(list)
for r in out_rows:
    by_cell[r['cell']].append(r)
arms = {}
for cell, rs in sorted(by_cell.items()):
    W_n = sum(r['n_fails'] for r in rs)
    def fw(get): return round(sum(get(r) * r['n_fails'] for r in rs) / W_n, 4)
    ref = ref_board['arms'].get(cell, {})
    arms[cell] = {
        'tasks': ref.get('tasks'),
        'tasks_with_2plus_fails_executed': len(rs),
        'tasks_with_2plus_fails': ref.get('tasks_with_2plus_fails'),
        'fail_weighted_modal_share_fp': fw(lambda r: r['fp']['modal_share']),
        'fail_weighted_collision_fp': fw(lambda r: r['fp']['collision']),
        'fail_weighted_collision_shape': ref.get('fail_weighted_collision_shape'),
        'fail_entropy_bits_fp': fw(lambda r: r['fp']['H_bits']),
        'fail_entropy_bits_shape': ref.get('fail_entropy_bits_shape'),
        'renyi2_bits_fp': round(-math.log2(max(fw(lambda r: r['fp']['collision']), 1e-12)), 4),
        'mean_outcome_entropy_bits': ref.get('mean_outcome_entropy_bits'),
    }
json.dump({'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'method':
           'FULL fail-set fingerprint (exact per-test outcome vector from '
           're-execution of every failing alpha-shape against all base+plus '
           'tests; census harness semantics: 10s/call, 4GB RLIMIT, '
           'PYTHONHASHSEED=0) + alpha-renamed AST shape (unchanged, from '
           'rare-failures); per-task collision prob (unbiased, n>=2) and '
           'modal share; fail-weighted per-arm aggregation',
           'arms': arms},
          open(f'{W}/out/consistency_board_fullset.json', 'w'), indent=1)

# coverage
total_units = 0
for line in gzip.open(f'{W}/units.jsonl.gz', 'rt'): total_units += 1
cov = {'executed_units': len(vec), 'total_units': total_units,
       'rows_complete': rows_done, 'rows_total': len(order),
       'cells': len(by_cell),
       'plusfilter_active': PLUSFILTER is not None,
       'abort_reexec_tasks': sorted(ABORT_REEXEC)}
json.dump(cov, open(f'{W}/out/coverage.json', 'w'), indent=1)
print(cov)
