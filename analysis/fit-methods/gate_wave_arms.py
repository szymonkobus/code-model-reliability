#!/usr/bin/env python
"""gate_wave_arms.py <wave dir> [--label L] [--rehearsal] [-- <extra depth8_gate_read.py args>]"""
import sys, os, json, subprocess, hashlib

R = ''
HERE = os.path.dirname(os.path.abspath(__file__))


def sha16(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''): h.update(b)
    return h.hexdigest()[:16]


def main(a):
    if len(a) < 2: print(__doc__); return 2
    wave = a[1].rstrip('/')
    extra = a[a.index('--') + 1:] if '--' in a else []
    label = a[a.index('--label') + 1] if '--label' in a else os.path.basename(wave)
    reh = '--rehearsal' in a[:a.index('--')] if '--' in a else '--rehearsal' in a
    meta = json.load(open(os.path.join(wave, 'meta.json')))
    per = meta.get('per_arm') or {}
    inputs = sorted(f for f in os.listdir(os.path.join(wave, 'inputs')) if f.endswith('.npz'))
    print(f"gate wave arms — {label}: {os.path.basename(wave)} | layout {str(meta.get('layout_key') or meta.get('layout'))[:60]} | {len(inputs)} input(s), {len(per)} per_arm leaf(s) | gate args {' '.join(extra) or '(none)'}")
    out = []
    for f in inputs:
        stem = f[:-4]; npz = os.path.join(wave, 'inputs', f)
        pa = per.get(stem) or {}
        fl = next((pa.get(k) for k in ('file', 'attempts_file', 'per_attempt_file', 'source', 'composed_file', 'kept_file') if isinstance(pa.get(k), dict)), {})
        fp = str(fl.get('path') or next((pa.get(k) for k in ('file', 'attempts_file', 'per_attempt_file', 'source', 'composed_file', 'kept_file') if isinstance(pa.get(k), str)), '') or '')
        if not fp:
            print(f"  {stem}: NO composed file named in per_arm — not read"); out.append((stem, 'UNREAD')); continue
        fpa = fp if fp.startswith('/') else os.path.join(R, fp)
        if not os.path.exists(fpa):
            print(f"  {stem}: the composed file {fp} is not on disk — not read"); out.append((stem, 'UNREAD')); continue
        disk = sha16(fpa); named = str(fl.get('sha16') or '')[:16]
        cmd = [sys.executable, os.path.join(HERE, 'depth8_gate_read.py'), fpa, npz] + extra + ['--label', f"{label}:{stem}"] + (['--rehearsal'] if reh else [])
        r = subprocess.run(cmd, capture_output=True, text=True)
        lines = (r.stdout + r.stderr).splitlines()
        verdict = next((l for l in lines if l.startswith('VERDICT')), 'VERDICT: (none printed)')
        hold = next((l for l in lines if l.startswith('HOLD')), '')
        unf = next((l for l in lines if 'UNFOLDED' in l), '')
        print(f"  {stem}: {verdict[:120]}" + (f" | {hold[:220]}" if hold else '') + (f" | file sha16 on disk {disk} ≠ per_arm {named}" if named and disk != named else ''))
        out.append((stem, 'PASS' if r.returncode == 0 else 'HOLD'))
    n_pass = sum(1 for _, v in out if v == 'PASS')
    print(f"SUMMARY {label}: {n_pass} PASS, {sum(1 for _, v in out if v == 'HOLD')} HOLD, {sum(1 for _, v in out if v == 'UNREAD')} unread of {len(out)}")
    return 0 if n_pass == len(out) else 2


if __name__ == '__main__': sys.exit(main(sys.argv))
