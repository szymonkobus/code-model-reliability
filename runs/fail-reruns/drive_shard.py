"""Array-task driver: run one shard of payload files through runner_vec.py.
Resume-safe: per-payload part files, skip existing. Usage:
  python3 drive_shard.py <shard.jsonl> <parts_dir> <venv_python> <runner> [workers]
Shard rows: {payload_id, benchmark, task_id, prompt, canonical_solution,
             entry_point, atol, base_input, plus_input, shapes:{sid:code}}
"""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

shard_path, parts_dir, venv_py, runner = sys.argv[1:5]
workers = int(sys.argv[5]) if len(sys.argv) > 5 else 4
PAYLOAD_TIMEOUT = int(sys.argv[6]) if len(sys.argv) > 6 else 7200
os.makedirs(parts_dir, exist_ok=True)

payloads = [json.loads(l) for l in open(shard_path)]
todo = [p for p in payloads
        if not os.path.exists(f"{parts_dir}/{p['payload_id']}.json")]
print(f'[plan] {len(payloads)} payloads, {len(todo)} to run', flush=True)

def parse_result_stdout(out):
    txt = out.lstrip()
    try:
        obj, _ = json.JSONDecoder().raw_decode(txt)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for line in reversed(txt.splitlines()):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None

def run_one(p):
    pid = p['payload_id']
    pp = f'{parts_dir}/{pid}.json'
    t0 = time.time()
    try:
        r = subprocess.run(
            [venv_py, runner], input=json.dumps(p), capture_output=True,
            text=True, timeout=PAYLOAD_TIMEOUT,
            env={'PYTHONHASHSEED': '0', 'PATH': '/usr/bin:/bin',
                 **({'EVALPLUS_MAX_MEMORY_BYTES': v} if (v := os.environ.get(
                     'EVALPLUS_MAX_MEMORY_BYTES')) else {})})
    except subprocess.TimeoutExpired:
        open(f'{parts_dir}/{pid}.err', 'w').write(
            f'PAYLOAD_TIMEOUT after {PAYLOAD_TIMEOUT}s\n')
        return pid, 'PAYLOAD_TIMEOUT', time.time() - t0
    if r.returncode != 0:
        err_pp = f'{parts_dir}/{pid}.err'
        open(err_pp, 'w').write(f'rc={r.returncode}\n{r.stderr[-3000:]}')
        return pid, f'rc={r.returncode}', time.time() - t0
    res = parse_result_stdout(r.stdout)
    if res is None:
        open(f'{parts_dir}/{pid}.err', 'w').write(
            f'BAD_STDOUT: no parseable result object in the runner stdout\n'
            f'--- stdout head ---\n{r.stdout[:3000]}\n--- stderr tail ---\n{r.stderr[-2000:]}')
        return pid, 'BAD_STDOUT', time.time() - t0
    tmp = pp + '.tmp'
    json.dump(res, open(tmp, 'w'))
    os.replace(tmp, pp)
    return pid, 'ok', time.time() - t0

n_done = n_err = 0
with ThreadPoolExecutor(max_workers=workers) as ex:
    for pid, status, dt in ex.map(run_one, todo):
        if status == 'ok':
            n_done += 1
            if dt > 120 or n_done % 200 == 0:
                print(f'[done {n_done}/{len(todo)}] {pid} {dt:.0f}s', flush=True)
        else:
            n_err += 1
            print(f'[ERR] {pid}: {status} ({dt:.0f}s)', flush=True)
print(f'[shard complete] ok={n_done} err={n_err} skipped={len(payloads)-len(todo)}',
      flush=True)
