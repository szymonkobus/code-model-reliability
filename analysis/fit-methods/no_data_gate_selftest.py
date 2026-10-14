#!/usr/bin/env python
import os, sys, json, csv, tempfile, shutil, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CFG = 'claude-test-5-5_batch'
BOARD_CFG = 'claude-test-5-5'


def main():
    d = tempfile.mkdtemp(prefix='fit_methods_no_data_selftest_')
    try:
        # the per-attempt file: T1 no refusals (8 answers, 2 fails); T2 slots 1 and 5 refused (slot 1 textless, fails; slot 5 a stub that passes), 6 written with 1 fail;
        # T3 refused on every answer (8 textless fails); B1 a board task under the other config, no refusals, 8 answers, 3 fails
        def cell(verdicts): return {'draws_in_pool_order': [{'class': 'continuation', 'shard': 's0', 'census_order': 0, 'attempts': [[v, v] for v in verdicts]}]}
        pa = {'_header': {'configuration': CFG, 'census': 'selftest'},
              'cells': {'T1': cell([1, 1, 0, 1, 1, 0, 1, 1]), 'T2': cell([1, 0, 1, 1, 0, 1, 1, 1]), 'T3': cell([0] * 8)}}
        pa_p = os.path.join(d, f'{CFG}.selftest.composed.json'); json.dump(pa, open(pa_p, 'w'))
        rec = {'rule': 'selftest', 'per_task_refusals': {
            'T2': {CFG: 2, 'total': 2, 'whole_cell_arms': [], 'written': {CFG: 6}, 'samples_refused': {CFG: [1, 5]}},
            'T3': {CFG: 8, 'total': 8, 'whole_cell_arms': [CFG], 'written': {CFG: 0}, 'samples_refused': {CFG: list(range(8))}}}}
        rec_p = os.path.join(d, 'refused_answers.json'); json.dump(rec, open(rec_p, 'w'))
        csv_p = os.path.join(d, 'unified_cells.csv')
        with open(csv_p, 'w', newline='') as fh:
            w = csv.writer(fh); w.writerow(['source', 'config', 'task_id', 'n', 'passes', 'fails', 'arm_id'])
            w.writerow(['board', BOARD_CFG, 'B1', 8, 5, 3, 'test']); w.writerow(['pool', CFG, 'T1', 8, 6, 2, 'test'])
            w.writerow(['pool', CFG, 'T2', 8, 6, 2, 'test']); w.writerow(['pool', CFG, 'T3', 8, 0, 8, 'test'])   # the intake at the TOTAL count (T2: slot 1 fails, slot 5 passes among the refused)
        right_p = os.path.join(d, 'right.npz'); np.savez(right_p, task_ids=np.array(['B1', 'T1', 'T2']), n=np.array([8, 8, 6]), f=np.array([3, 2, 1]))
        wrong_p = os.path.join(d, 'wrong.npz'); np.savez(wrong_p, task_ids=np.array(['B1', 'T1', 'T2', 'T3']), n=np.array([8, 8, 8, 8]), f=np.array([3, 2, 2, 8]))
        results = []
        for name, npz_p, want in (('right', right_p, 0), ('wrong', wrong_p, 2)):
            r1 = subprocess.run([PY, os.path.join(HERE, 'depth8_gate_read.py'), pa_p, npz_p, '--full', '--all-draws', '--only-file-cells', '--rehearsal', '--no-data', rec_p, '--label', f'selftest_{name}'], capture_output=True, text=True)
            r2 = subprocess.run([PY, os.path.join(HERE, 'intake_cells_gate_read.py'), csv_p, npz_p, '--configs', f'{BOARD_CFG},{CFG}', '--no-data', rec_p, '--label', f'selftest_{name}'], capture_output=True, text=True)
            for half, r in (('per-attempt', r1), ('intake', r2)):
                v = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith('VERDICT') or l.startswith('HOLD') or 'no-data' in l]
                ok = r.returncode == want
                results.append(ok)
                print(f"[{'ok' if ok else 'FAIL'}] {name} cut, {half} half: exit {r.returncode} (wanted {want})")
                for l in v[:6]: print('      ' + l[:300])
        print('SELFTEST', 'PASS' if all(results) else 'FAIL', f'({sum(results)} of {len(results)} readings as expected)')
        return 0 if all(results) else 1
    finally:
        shutil.rmtree(d)


if __name__ == '__main__': sys.exit(main())
