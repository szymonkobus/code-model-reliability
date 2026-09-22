#!/usr/bin/env python3
"""Lens (c): family and mode. All 55 fitted arms of the board + focused-half fit: capability and reliability of record,
thinking twins (same base, thinking on vs off), and where the set sits. Outputs out/family_mode.json."""
import json, re
SET=json.load(open('out/set_of_record.json'))
rows=SET['all_rows']; inset={x['page_id'] for x in SET['set']}
def base_of(pid):
    return re.sub(r'(-Thinking|-thinking|\s\(think\))$','',pid)
by_id={x['page_id']:x for x in rows}
pairs=[]
for x in rows:
    pid=x['page_id']
    if pid.endswith('-Thinking') or pid.endswith('-thinking'):
        b=base_of(pid)
        if b in by_id:
            p=by_id[b]
            pairs.append(dict(base=p['label'], think=x['label'], cap_plain=p['cap_pct'], cap_think=x['cap_pct'], rel_plain=p['rel_pct'], rel_think=x['rel_pct'],
                              cap_tasks_plain=p['cap_tasks_below'], cap_tasks_think=x['cap_tasks_below'], rel_tasks_plain=p['rel_tasks_below'], rel_tasks_think=x['rel_tasks_below'],
                              in_set=[p['page_id'] in inset, pid in inset]))
# the set by family / mode
fam={}
for x in SET['set']:
    pid=x['page_id']; f=pid.split('/')[0] if '/' in pid else pid
    fam.setdefault(f,[]).append(x['label'])
# overall relation across all non-partial arms: rank correlation cap vs rel, and the residual spread within the set vs overall
import math
full=[x for x in rows if not x['partial']]
def spearman(a,b):
    def rk(v):
        o=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for k,i in enumerate(o): r[i]=k
        return r
    ra,rb=rk(a),rk(b); n=len(a); ma=sum(ra)/n; mb=sum(rb)/n
    cov=sum((ra[i]-ma)*(rb[i]-mb) for i in range(n)); va=sum((r-ma)**2 for r in ra); vb=sum((r-mb)**2 for r in rb)
    return cov/math.sqrt(va*vb)
rho=spearman([x['cap_pct'] for x in full],[x['rel_pct'] for x in full])
out=dict(thinking_pairs=pairs, set_by_maker=fam, n_full_arms=len(full), spearman_cap_rel_all=rho,
         set_rel_range_tasks=[min(x['rel_tasks_below'] for x in SET['set']), max(x['rel_tasks_below'] for x in SET['set'])],
         all_rel_range_tasks=[min(x['rel_tasks_below'] for x in full), max(x['rel_tasks_below'] for x in full)],
         set_sorted=[dict(label=x['label'], cap_pct=round(x['cap_pct'],1), cap_tasks=x['cap_tasks_below'], rel_pct=round(x['rel_pct'],2), rel_tasks=x['rel_tasks_below'], think=('think' in x['stem']), maker=x['page_id'].split('/')[0]) for x in sorted(SET['set'], key=lambda x:x['rel_pct'])])
json.dump(out,open('out/family_mode.json','w'),indent=1)
print("thinking twins (same base):")
for p in pairs: print(f"  {p['base']:22s} cap {p['cap_plain']:5.1f} -> think {p['cap_think']:5.1f} | rel {p['rel_plain']:6.2f} ({p['rel_tasks_plain']:3d} tasks) -> think {p['rel_think']:6.2f} ({p['rel_tasks_think']:3d} tasks) {'*set*' if any(p['in_set']) else ''}")
print("\nset by maker:", fam)
print("spearman cap vs rel over all", len(full), "full arms:", round(rho,3))
print("reliability range in the set (tasks):", out['set_rel_range_tasks'], " over all full arms:", out['all_rel_range_tasks'])
for s in out['set_sorted']: print(f"  {s['label']:26s} {'think' if s['think'] else 'plain':5s} {s['maker']:12s} cap {s['cap_pct']} ({s['cap_tasks']}) rel {s['rel_pct']} ({s['rel_tasks']})")
