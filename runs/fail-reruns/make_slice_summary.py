import glob, gzip, json, math
from collections import defaultdict
from itertools import combinations
W = 'runs/fail-reruns'

vec = {}
tasks_needed = set()
hv = json.load(open('deep-dives/rare-failures/meta/consistency_validation.json'))
resolved = json.load(open(f'{W}/validation_cells.json'))
for key in resolved:
    bench, arm, tid = key.split('_', 2)
    tasks_needed.add(tid.replace('-', '/', 1))
for t in tasks_needed:
    for pp in glob.glob(f"{W}/parts/{t.replace('/','-')}__c*.json"):
        r = json.load(open(pp))
        for sid, s in r['shapes'].items():
            vec[(t, sid)] = ('EXEC:' + s['exec_error'].split('(')[0]
                             if s.get('exec_error') is not None else s['vector'])
att = defaultdict(dict)
for line in gzip.open(f'{W}/attempts.jsonl.gz', 'rt'):
    a = json.loads(line)
    att[(a['cell'], a['task_id'])][a['sample']] = a['shape']
tp = fp = fn = 0
for key, cell in resolved.items():
    bench, arm, tid = key.split('_', 2)
    task = tid.replace('-', '/', 1)
    lab = {i: ci for ci, cl in enumerate(hv['hand_clusters'][key]) for i in cl}
    fps = {i: vec[(task, att[(cell, task)][i])] for i in lab
           if (task, att[(cell, task)].get(i)) in vec}
    for i, j in combinations(sorted(fps), 2):
        sp, st_ = fps[i] == fps[j], lab[i] == lab[j]
        tp += sp and st_; fp += sp and not st_; fn += st_ and not sp
rows = json.load(open(f'{W}/slice_q2_rows.json'))
import statistics as st
def rank_rho(bench):
    pa = defaultdict(list); pb = defaultdict(list)
    for r in rows:
        a, b = r['cell'].split('|')
        if b != bench: continue
        pa[a].append((r['H_ff'], r['n'])); pb[a].append((r['H_full'], r['n']))
    arms = sorted(pa)
    def agg(d, a): tot = sum(n for _, n in d[a]); return sum(h*n for h, n in d[a])/tot
    ra = {a: i for i, a in enumerate(sorted(arms, key=lambda a: agg(pa, a)))}
    rb = {a: i for i, a in enumerate(sorted(arms, key=lambda a: agg(pb, a)))}
    n = len(arms); d2 = sum((ra[a]-rb[a])**2 for a in arms)
    return 1 - 6*d2/(n*(n**2-1))
summary = {
  'q1': {'precision_fullset': round(tp/(tp+fp), 3), 'recall_fullset': round(tp/(tp+fn), 3),
         'precision_firstfail': hv['fp']['precision'], 'recall_firstfail': hv['fp']['recall'],
         'precision_shape': hv['shape_alpha']['precision'], 'recall_shape': hv['shape_alpha']['recall'],
         'n_cases': hv['hand_cases']},
  'q2': {'rows': len(rows),
         'mean_classes_firstfail': round(st.mean([r['K_ff'] for r in rows]), 2),
         'mean_classes_fullset': round(st.mean([r['K_full'] for r in rows]), 2),
         'mean_dH_bits': round(st.mean([r['H_full']-r['H_ff'] for r in rows]), 3),
         'rank_rho_humaneval': round(rank_rho('humaneval'), 3),
         'rank_rho_mbpp': round(rank_rho('mbpp'), 3)}}
json.dump(summary, open(f'{W}/out/slice_summary.json', 'w'), indent=1)
print(json.dumps(summary))
