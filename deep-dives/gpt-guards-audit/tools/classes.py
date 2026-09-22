#!/usr/bin/env python3
"""The five census classes and how each failed attempt maps onto them.
  sensible guard              guard_raise whose task-level sensibility majority is sensible_guard
  over-guarding, no basis     guard_raise whose task-level majority is no_sensible_basis
  impossible import / bug     import_crash (incl. `from typing import int`), entry point missing (renamed or
                              extraction), incidental exception, timeout, guard judged not_a_guard
  refusal                     reply with no code / explicit refusal (none observed; scan in census)
  other                       plain wrong answer (wrong_value) and right value in the wrong number type
                              (matches_canonical under tolerance; judged fail)
"""
import json, os, collections
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES = ['sensible guard', 'over-guarding, no basis', 'impossible import / bug', 'refusal', 'other']

def sensibility_majority():
    votes = collections.defaultdict(list)
    p = os.path.join(HERE, 'data/guard_sensibility.jsonl')
    if os.path.exists(p):
        for l in open(p):
            r = json.loads(l)
            if r.get('verdict'): votes[r['task']].append(r['verdict'])
    out = {}
    for t, vs in votes.items():
        c = collections.Counter(vs).most_common()
        out[t] = {'majority': c[0][0], 'votes': dict(collections.Counter(vs)), 'n': len(vs)}
    return out

def load_census():
    rows = []
    for f in ('data/census_board.jsonl', 'data/census_pool.jsonl'):
        for l in open(os.path.join(HERE, f)): rows.append(json.loads(l))
    return rows

def map_class(r, sens):
    m = r['class_mech']
    if m == 'guard_raise':
        s = sens.get(r['task'], {}).get('majority')
        if s == 'no_sensible_basis': return 'over-guarding, no basis'
        if s == 'not_a_guard': return 'impossible import / bug'
        return 'sensible guard'
    if m in ('import_crash', 'entry_missing', 'incidental_raise', 'timeout', 'unresolved', 'no_failing_input'): return 'impossible import / bug'
    if m in ('wrong_value', 'matches_canonical'): return 'other'
    return 'other'

def census_table(threshold=5):
    sens = sensibility_majority()
    rows = load_census()
    tab = {m: collections.Counter() for m in ('gpt-5-nano', 'gpt-5-mini')}
    for r in rows:
        if r['difficulty_pct'] is None or r['difficulty_pct'] >= threshold: continue
        tab[r['model']][map_class(r, sens)] += 1
    return tab, sens

if __name__ == '__main__':
    for thr in (5, 20):
        tab, sens = census_table(thr)
        print('threshold', thr)
        for m, c in tab.items(): print(' ', m, sum(c.values()), dict(c))
