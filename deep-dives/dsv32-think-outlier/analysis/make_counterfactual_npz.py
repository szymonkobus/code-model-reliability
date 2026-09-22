"""Write fitting-format inputs for the counterfactual fits of one arm:
  *_nocut.npz  — every attempt cut at the token cap removed (n and f both reduced)
  *_orig.npz   — byte-equivalent copy of fitting's inputs (the control fit)
Usage: make_counterfactual_npz.py <fitting inputs.npz> <samples.tsv> <outdir> <stem>"""
import sys, csv, collections, numpy as np, json
src, tsv, outdir, stem = sys.argv[1:5]
d = np.load(src, allow_pickle=False)
cut_n = collections.Counter(); cut_f = collections.Counter()
for r in csv.DictReader(open(tsv), delimiter='\t'):
    if r['fin'] == 'length':
        cut_n[r['task']] += 1
        if r['plus'] != 'pass': cut_f[r['task']] += 1
tids = d['task_ids'].tolist()
n2 = d['n'].copy(); f2 = d['f'].copy()
for i, t in enumerate(tids):
    n2[i] -= cut_n.get(t, 0); f2[i] -= cut_f.get(t, 0)
assert (f2 >= 0).all() and (n2 > 0).all() and (f2 <= n2).all()
np.savez(f'{outdir}/{stem}_orig.npz', model_id=d['model_id'], z_hat=d['z_hat'], sd=d['sd'], f=d['f'], n=d['n'], task_ids=d['task_ids'])
np.savez(f'{outdir}/{stem}_nocut.npz', model_id=d['model_id'], z_hat=d['z_hat'], sd=d['sd'], f=f2, n=n2, task_ids=d['task_ids'])
summary = dict(tasks=len(tids), attempts=int(d['n'].sum()), fails=int(d['f'].sum()), cut_attempts=int(sum(cut_n[t] for t in tids)), cut_fails=int(sum(cut_f[t] for t in tids)),
               attempts_nocut=int(n2.sum()), fails_nocut=int(f2.sum()), tasks_with_cuts=int(sum(1 for t in tids if cut_n.get(t, 0))))
json.dump(summary, open(f'{outdir}/{stem}_counterfactual_summary.json', 'w'), indent=1); print(summary)
