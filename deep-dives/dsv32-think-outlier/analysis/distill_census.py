#!/usr/bin/env python3
"""Summarise the pool cut-answer census of the two distilled R1 arms (census/out/*.fast.json) for the page. Writes data/distill_census.json."""
import json, glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = {}
for f in sorted(glob.glob(f'{ROOT}/census/out/*.fast.json')):
    d = json.load(open(f)); k = 'llama8b' if 'Llama-8B' in d['config'] else 'qwen15b'
    cl = d['classes']; n = d['cut']
    rep = sum(v['n'] for c, v in cl.items() if c in ('exact_loop', 'line_loop', 'high_repetition'))
    loops = sum(v['n'] for c, v in cl.items() if c in ('exact_loop', 'line_loop'))
    code_before_loop = sum(v for k2, v in d['had_code_by_class'].items() if k2.startswith('exact_loop|code'))
    out[k] = dict(config=d['config'], attempts=d['rows'], cut=n, cut_share=d['cut_share'], tasks_with_cut=d['tasks_with_cut'], tasks=d['tasks_total'],
                  exact_loop_share=cl.get('exact_loop', {}).get('n', 0) / n, near_loop_share=cl.get('high_repetition', {}).get('n', 0) / n, progressing_share=cl.get('progressing', {}).get('n', 0) / n, repetition_share=rep / n,
                  never_closed_share=d['closure'].get('overlong', 0) / n, code_before_loop_share=code_before_loop / max(1, cl.get('exact_loop', {}).get('n', 1)),
                  loop_start_tokens=d['loop_start_tokens_pct'], tokens_inside_loop=d['tokens_inside_loop_pct'],
                  families={fam: v for fam, v in d['cut_by_family'].items()}, top_tasks=d['top_tasks'][:5], examples={c: [dict(task=e['task'], sample=e['sample'], tail=e['tail'][-220:]) for e in ex[:1]] for c, ex in d['examples'].items()})
for f in sorted(glob.glob(f'{ROOT}/census/out/*.echo_sample.json')):
    e = json.load(open(f)); k = 'llama8b' if 'Llama-8B' in e['config'] else 'qwen15b'
    if k in out: out[k]['echo'] = dict(sampled=e['sampled'], overall=e['overall'], per_family={fam: v['echo_share_10_50_90'] for fam, v in e['per_family'].items()})
json.dump(out, open(f'{ROOT}/data/distill_census.json', 'w'), indent=1); print({k: (v['cut'], round(v['repetition_share'], 3), round(v['progressing_share'], 3)) for k, v in out.items()})
