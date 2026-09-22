"""Post-assemble sanity checks for board_verified_J.json."""
import json
from collections import Counter

META = 'deep-dives/rare-failures/meta'
out = json.load(open(f'{META}/board_verified_J.json'))
screen = json.load(open(f'{META}/board_screen.json'))

for cell in ['gemma-12b|humaneval', 'gemma-12b|mbpp']:
    c = out[cell]
    sc = screen[cell]
    want = {(x['task_id'], x['sample'], 'primary') for x in sc['primary']} | \
           {(x['task_id'], x['sample'], 'helper') for x in sc['helper']}
    got = {(a['task_id'], a['sample'], a['screen_kind']) for a in c['attempt_verdicts']}
    assert want == got, f'{cell}: attempt coverage mismatch'
    assert len(c['attempt_verdicts']) == len(want), f'{cell}: dup attempts'

    vc = Counter(a['verdict'] for a in c['attempt_verdicts'])
    assert c['totals']['verified_correct_attempts'] == vc['correct']
    assert sum(t['verdicts']['correct'] for t in c['per_task']) == vc['correct']
    assert sum(t['candidate_attempts'] for t in c['per_task']) == len(want)
    for t in c['per_task']:
        assert t['candidate_attempts'] == sum(t['verdicts'].values())
        assert t['verified_correct_attempts'] == t['verdicts']['correct']
    ct = sum(1 for t in c['per_task'] if t['verdicts']['correct'] > 0)
    assert c['totals']['casualty_tasks'] == ct
    pp = round(vc['correct'] / c['totals']['denominator_attempts'] * 100, 4)
    assert c['totals']['pass_points'] == pp
    assert pp <= sc['ceiling_pt'] + 1e-9
    assert c['candidates']['attempts_executed'] + c['candidates']['attempts_syntax_dead'] \
        + c['candidates']['attempts_unverifiable'] == c['candidates']['total']
    assert vc['unverifiable'] == len(c['unverifiable']) == c['candidates']['attempts_unverifiable']
    assert vc['syntax'] == c['candidates']['attempts_syntax_dead']
    print(cell, 'OK:', dict(vc), '| pass_points', pp, '| casualty_tasks', ct,
          '| ceiling', sc['ceiling_pt'])
print('all checks passed')
