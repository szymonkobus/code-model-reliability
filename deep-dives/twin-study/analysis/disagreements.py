#!/usr/bin/env python3
"""disagreements.py — aggregate the clear disagreements (Fisher p < 0.001) by direction and pattern; merge into data/results.json under 'reading'."""
import csv, json, collections, os
D = 'deep-dives/twin-study/data'
tw = list(csv.DictReader(open(f'{D}/per_twin.csv'))); pp = list(csv.DictReader(open(f'{D}/per_pair.csv')))
clear = [r for r in pp if r['clear'] == 'True']
by = collections.defaultdict(lambda: [0, 0])
for r in clear: by[r['twin']][0 if float(r['diff_points']) > 0 else 1] += 1
sysr = [t for t in tw if int(t['n_clear']) >= 3]; same = [t for t in sysr if t['clear_same_sign'] == 'True']
rp = json.load(open(f'{D}/read_pairs.json'))
out = {'clear_pairs': len(clear), 'clear_twin_easier': sum(1 for r in clear if float(r['diff_points']) > 0), 'clear_twin_harder': sum(1 for r in clear if float(r['diff_points']) < 0),
       'total_flips_80_points': sum(1 for r in clear if abs(float(r['diff_points'])) >= 80),
       'twins_with_any_clear': len(by), 'twins_with_3plus_clear': len(sysr), 'twins_same_direction_3plus': len(same),
       'same_direction_easier': sum(1 for t in same if float(t['mean_diff_points']) > 0), 'same_direction_harder': sum(1 for t in same if float(t['mean_diff_points']) < 0),
       'twins_both_directions_3plus': sum(1 for t, (e, h) in by.items() if e >= 1 and h >= 1 and e + h >= 3),
       'identical_twins_clear_arms': sum(int(t['n_clear']) for t in tw if t['identical'] == 'True'), 'identical_twins': sum(1 for t in tw if t['identical'] == 'True'),
       'clear_by_style': {s: {'twins_3plus': sum(1 for t in sysr if t['style'] == s), 'twins': sum(1 for t in tw if t['style'] == s)} for s in sorted({t['style'] for t in tw})},
       'read_pairs': len(rp['pairs']), 'read_classes': dict(collections.Counter(p['class'] for p in rp['pairs'])),
       'read_easier': sum(1 for p in rp['pairs'] if p['twin_easier'] is True), 'read_harder': sum(1 for p in rp['pairs'] if p['twin_easier'] is False)}
R = json.load(open(f'{D}/results.json')); R['reading'] = out
json.dump(R, open(f'{D}/results.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
