import hashlib, json
from collections import defaultdict
from pathlib import Path


def task_samples_sha256(solutions_path):
    by_task = defaultdict(list)
    for l in open(solutions_path, encoding="utf-8"):
        r = json.loads(l)
        by_task[r["task_id"]].append(r["solution"])
    return {t: hashlib.sha256("\x00".join(sorted(s)).encode("utf-8")).hexdigest()
            for t, s in by_task.items()}


def samples_sha256(solutions_path):
    return hashlib.sha256(Path(solutions_path).read_bytes()).hexdigest()
