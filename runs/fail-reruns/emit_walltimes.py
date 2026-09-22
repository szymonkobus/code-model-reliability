"""Emit per-(task, shape) wall-time + timeout counts from part files.
out/shape_walltimes.jsonl.gz: {task_id, shape, wall_s, n_timeout, exec_error_class}
wall_s = runner-recorded per-shape wall seconds (GT time excluded; census
semantics 10s/call alarm). Synthesized process-death shapes have wall_s null.
standalone-v2 parts take precedence per (task, shape)."""
import glob, gzip, json, os
W = 'runs/fail-reruns'
rows = {}
rank = {}
import re as _re
def rank_of(sem):
    if sem is None: return 0.0
    if sem == 'standalone-v2': return 1.0
    m = _re.match(r'preamble-v([0-9.]+)$', sem)
    return 1.0 + float(m.group(1)) if m else 0.0   # preamble-v2 -> 3, v3 -> 4, v4 -> 5, v4.1 -> 5.1
import hashlib
CUR_SHA = hashlib.sha256(open(f'{W}/preamble_transform.py', 'rb').read()).hexdigest()
for pp in sorted(glob.glob(f'{W}/parts/*.json')):
    task = os.path.basename(pp).split('__')[0].replace('-', '/', 1)
    r = json.load(open(pp))
    rk = (rank_of(r.get('semantics')), 1 if r.get('transform_sha256') == CUR_SHA else 0)
    for sid, s in r['shapes'].items():
        k = (task, sid)
        if k in rank and rank[k] > rk:
            continue
        rank[k] = rk
        rows[k] = {'task_id': task, 'shape': sid, 'wall_s': s.get('wall_s'),
                   'n_timeout': s.get('n_timeout', 0),
                   'exec_error_class': (s['exec_error'].split('(')[0]
                                        if s.get('exec_error') else None)}
with gzip.open(f'{W}/out/shape_walltimes.jsonl.gz', 'wt') as f:
    for k in sorted(rows):
        f.write(json.dumps(rows[k]) + '\n')
print('walltime rows:', len(rows))
