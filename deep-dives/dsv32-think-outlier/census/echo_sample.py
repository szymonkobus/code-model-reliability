#!/usr/bin/env python3
"""Prompt-echo share on a stratified random sample of cut attempts (the full echo pass hit its wall): for up to N cut attempts per
task family, the share of the thinking's first 20,000 characters covered by >= 30-character blocks shared with the task prompt.
Usage: echo_sample.py <config_dir> <certshards_dir> <attempts.tsv> <out.json> [per_family=60]"""
import json, sys, os, glob, csv, random, difflib, collections
cfg_dir, certs_dir, att_tsv, out = sys.argv[1:5]; PER = int(sys.argv[5]) if len(sys.argv) > 5 else 60
prompts = {}
for f in glob.glob(f'{certs_dir}/*.jsonl'):
    for l in open(f):
        try: d = json.loads(l)
        except Exception: continue
        if 'task_id' in d and 'prompt' in d: prompts[d['task_id']] = d['prompt']
rows = list(csv.DictReader(open(att_tsv), delimiter='\t'))
byfam = collections.defaultdict(list)
for r in rows: byfam[r['task_id'].split('/')[0]].append(r)
random.seed(7); want = {}
for fam, lst in byfam.items():
    for r in random.sample(lst, min(PER, len(lst))): want[(r['shard'], r['task_id'], int(r['sample']))] = fam
res = collections.defaultdict(list); tok_share = collections.defaultdict(list); n_found = 0
for rf in sorted(glob.glob(f'{cfg_dir}/*/*/*.records.jsonl')):
    shard = rf.split('/')[-3]
    if not any(k[0] == shard for k in want): continue
    with open(rf) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            key = (shard, r.get('task_id'), r.get('sample'))
            if key not in want: continue
            th = (r.get('think_text') or '')[:20000]; p = prompts.get(r['task_id'])
            if not p or not th: continue
            sm = difflib.SequenceMatcher(None, th, p, autojunk=False); cov = sum(n for a, b, n in sm.get_matching_blocks() if n >= 30)
            res[want[key]].append(cov / len(th)); n_found += 1
def q(a):
    a = sorted(a); return [round(a[int(len(a) * p)] if int(len(a) * p) < len(a) else a[-1], 4) for p in (0.1, 0.5, 0.9)] if a else None
summary = dict(config=os.path.basename(cfg_dir.rstrip('/')), sampled=n_found, per_family={f: dict(n=len(v), echo_share_10_50_90=q(v), share_over_10pct=sum(1 for x in v if x > 0.1) / len(v)) for f, v in res.items()},
               overall=dict(n=n_found, echo_share_10_50_90=q([x for v in res.values() for x in v]), share_over_10pct=sum(1 for v in res.values() for x in v if x > 0.1) / max(1, n_found)))
json.dump(summary, open(out, 'w'), indent=1); print(json.dumps(summary, indent=1))
