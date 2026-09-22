#!/usr/bin/env python3
import json, glob, collections, os

RF = os.path.dirname(os.path.abspath(__file__)).rsplit('/meta', 1)[0]

sub = {}
for line in open(f'{RF}/meta/sublabels.jsonl'):
    r = json.loads(line)
    sub[r['case_id']] = r['submode']
for p in sorted(glob.glob(f'{RF}/meta/sublabels/w*_shard_*.jsonl')):
    for line in open(p):
        r = json.loads(line)
        sub[r['case_id']] = r['submode']

typo = json.load(open(f'{RF}/meta/typo_tasks.json'))
kind_of = {}
for kind, lst in typo.items():
    if isinstance(lst, list):
        for e in lst:
            kind_of[e['task_id'] if isinstance(e, dict) else e] = kind

cases = {json.loads(l)['case_id']: json.loads(l) for l in open(f'{RF}/meta/cases.jsonl')}
bytask = collections.defaultdict(lambda: {'families': set(), 'cases': 0, 'attempts': 0})
for cid, s in sub.items():
    if s != 'renamed-required-entry-point' or cid not in cases:
        continue
    c = cases[cid]
    d = bytask[c['task_id']]
    d['families'].add(c['family'])
    d['cases'] += 1
    d['attempts'] += c['fail_count']

core = {t: d for t, d in bytask.items() if t in kind_of and len(d['families']) >= 2}
out = {'definition': 'typo_tasks identifier defect AND renamed-required-entry-point rare-band cases from >=2 families',
       'corpus_cases_at_generation': len(cases),
       'core_tasks': {t: {'kind': kind_of[t], 'families': sorted(d['families']),
                          'cases': d['cases'], 'attempts': d['attempts']}
                      for t, d in sorted(core.items())},
       'n_core': len(core)}
path = f'{RF}/meta/rename_class_core.json'
json.dump(out, open(path, 'w'), indent=1)
print(f'core: {len(core)} tasks -> {path}')
for t in sorted(core):
    d = core[t]
    print(f"  {t:14s} {kind_of[t]:10s} {d['cases']}c/{d['attempts']}att {sorted(d['families'])}")
