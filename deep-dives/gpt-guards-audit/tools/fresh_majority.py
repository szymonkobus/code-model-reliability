#!/usr/bin/env python3
"""Majority verdict per task from the fresh audit's votes -> data/fresh_audit_majority.json.
Then, if data/standing_labels.json exists (Part 3), list the disputes: a fresh 'fair' against an invalid
standing label (underspecification/contradiction), or a fresh 'underspecified'/'contradiction' against a
valid label (regular/tricky). Within-group differences are listed separately."""
import json, os, collections
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
votes = collections.defaultdict(list); meta = {}
for l in open(os.path.join(HERE, 'data/fresh_audit.jsonl')):
    r = json.loads(l)
    if not r.get('verdict'): continue
    votes[r['task']].append(r)
    meta[r['task']] = {'kind': r['kind'], 'source': r['source'], 'difficulty_pct': r['difficulty_pct'], 'input': r['input'], 'expected': r['expected'], 'alternative': r['alternative']}
out = {}
for t, vs in votes.items():
    c = collections.Counter(v['verdict'] for v in vs)
    top = c.most_common()
    verdict = top[0][0] if (len(top) == 1 or top[0][1] > top[1][1]) else 'split'
    conf = [v['confidence'] for v in vs if v['verdict'] == verdict and v['confidence'] is not None]
    out[t] = {**meta[t], 'verdict': verdict, 'votes': dict(c), 'n': len(vs),
              'confidence': round(sum(conf) / len(conf), 2) if conf else None,
              'alternative_reasonable_votes': sum(1 for v in vs if v.get('alternative_reasonable')),
              'reasonings': [v['reasoning'] for v in vs if v.get('reasoning')],
              'what_would_fix': [v['what_would_fix'] for v in vs if v.get('what_would_fix')]}
json.dump(out, open(os.path.join(HERE, 'data/fresh_audit_majority.json'), 'w'), indent=1)
kinds = collections.Counter((v['kind'], v['verdict']) for v in out.values())
print('fresh majorities:', dict(kinds))
lab_p = os.path.join(HERE, 'data/standing_labels.json')
if os.path.exists(lab_p):
    labels = json.load(open(lab_p))
    VALID = {'regular', 'tricky'}; INVALID = {'underspecification', 'contradiction'}
    disputes = []; minor = []
    for t, v in out.items():
        lb = labels.get(t, {}).get('label')
        if not lb: continue
        fresh_valid = v['verdict'] == 'fair'
        if v['verdict'] == 'split': minor.append((t, v['verdict'], lb)); continue
        if fresh_valid and lb in INVALID: disputes.append((t, v['verdict'], lb))
        elif (not fresh_valid) and lb in VALID: disputes.append((t, v['verdict'], lb))
        elif (not fresh_valid) and lb in INVALID and {'underspecified': 'underspecification', 'contradiction': 'contradiction'}[v['verdict']] != lb: minor.append((t, v['verdict'], lb))
    json.dump({'crossing': disputes, 'within_group': minor}, open(os.path.join(HERE, 'data/disputes.json'), 'w'), indent=1)
    print('crossing disputes:', disputes); print('within-group differences:', minor)
