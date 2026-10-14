#!/usr/bin/env python3
"""Claude on the reliability charts: generate evalplus-format samples via the
Anthropic Messages Batches API, then judge with the pinned local harness.

Why not evalplus's own anthropic backend at the pin:
  - make_model drops **kwargs for every API backend -> max_new_tokens stuck at 768
  - gen/util/anthropic_request.py hardcodes top_p=0.95 -> 400 on Claude 5 family
  - serial requests, no Batches API, retry loop can hot-spin, content[0] assumed text
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

WORKROOT = Path(os.environ.get("CLAUDE_GEN_WORKROOT", Path(__file__).resolve().parent / "work"))
OUTROOT = Path(os.environ.get("CLAUDE_GEN_OUTROOT", Path(__file__).resolve().parent / "runs-claude"))

INSTRUCTION = (
    "Please provide a self-contained Python script that solves the following "
    "problem in a markdown code block:"
)  # codegen.py:222 at the pin

# evalplus provider/utility.py EOS + the chat-mode fence stop (vllm.py:44).
EOS_STOPS = ["<|endoftext|>", "<|endofmask|>", "</s>", "\nif __name__", "\ndef main(", "\nprint("]
FENCE_STOP = "\n```\n"

N_SAMPLES_DEFAULT = 128
BATCH_MAX_REQUESTS = int(os.environ.get("CLAUDE_GEN_CHUNK", 100_000))

ARMS = {
    "haiku": dict(
        model="claude-haiku-4-5-20251001",
        chart_name="claude-haiku-4-5",
        temp_label="0.8",
        params=dict(max_tokens=4096, temperature=0.8,
                    stop_sequences=EOS_STOPS),
    ),
    "haiku-thinking": dict(
        model="claude-haiku-4-5-20251001",
        chart_name="claude-haiku-4-5-thinking",
        temp_label="1.0",  # thinking forces temperature=1 on Haiku
        params=dict(max_tokens=36864,
                    thinking={"type": "enabled", "budget_tokens": 32768}),
        # no stop_sequences on thinking arms: avoid any chance of stops
        # interacting with reasoning; verify in pilot before relaxing.
    ),
    "sonnet": dict(
        model="claude-sonnet-5",
        chart_name="claude-sonnet-5",
        temp_label="1.0",  # sampling params not settable; provider default
        params=dict(max_tokens=4096, thinking={"type": "disabled"},
                    stop_sequences=EOS_STOPS),
    ),
    "sonnet-thinking": dict(
        model="claude-sonnet-5",
        chart_name="claude-sonnet-5-thinking",
        temp_label="1.0",
        params=dict(max_tokens=36864,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "high"}),
    ),
    "opus": dict(
        model="claude-opus-5",
        chart_name="claude-opus-5",
        temp_label="1.0",
        # thinking:disabled is only legal at effort <= high on Opus 5
        params=dict(max_tokens=4096, thinking={"type": "disabled"},
                    output_config={"effort": "high"},
                    stop_sequences=EOS_STOPS),
    ),
    "opus-thinking": dict(
        model="claude-opus-5",
        chart_name="claude-opus-5-thinking",
        temp_label="1.0",
        params=dict(max_tokens=36864,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "high"}),
    ),
    "haiku55": dict(
        model="claude-haiku-5-5",
        chart_name="claude-haiku-5-5",
        temp_label="1.0",  # sampling params not settable; provider default
        params=dict(max_tokens=4096, thinking={"type": "disabled"},
                    stop_sequences=EOS_STOPS),
    ),
    "haiku55-thinking": dict(
        model="claude-haiku-5-5",
        chart_name="claude-haiku-5-5-thinking",
        temp_label="1.0",
        params=dict(max_tokens=36864,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "high"}),
    ),
    "sonnet55": dict(
        model="claude-sonnet-5-5",
        chart_name="claude-sonnet-5-5",
        temp_label="1.0",  # sampling params not settable; provider default
        params=dict(max_tokens=4096, thinking={"type": "between_tools"},
                    stop_sequences=EOS_STOPS),
    ),
    "sonnet55-thinking": dict(
        model="claude-sonnet-5-5",
        chart_name="claude-sonnet-5-5-thinking",
        temp_label="1.0",
        params=dict(max_tokens=36864,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "high"}),
    ),
    "haiku-greedy": dict(
        model="claude-haiku-4-5-20251001",
        chart_name="claude-haiku-4-5",
        temp_label="0.0",  # greedy column; only Claude model where T=0 exists
        params=dict(max_tokens=4096, temperature=0.0,
                    stop_sequences=EOS_STOPS + [FENCE_STOP]),
    ),
}

DATASETS = {"humaneval": 164, "mbpp": 378}


def load_tasks(dataset):
    if dataset == "humaneval":
        from evalplus.data import get_human_eval_plus
        return get_human_eval_plus()
    from evalplus.data import get_mbpp_plus
    return get_mbpp_plus()


def cid(task_id, sidx):
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)
    suffix = f"__s{sidx:03d}"
    if len(base) + len(suffix) > 64:
        import hashlib
        digest = hashlib.sha1(task_id.encode()).hexdigest()[:8]
        base = base[: 64 - len(suffix) - 9] + "-" + digest
    return base + suffix


def workdir(arm, dataset):
    d = WORKROOT / dataset / arm
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_jsonl(path):
    if not Path(path).exists():
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def load_state(wd):
    p = wd / "state.json"
    return json.loads(p.read_text()) if p.exists() else {"batches": []}


def save_state(wd, state):
    (wd / "state.json").write_text(json.dumps(state, indent=2))


def succeeded_ids(wd):
    return {r["custom_id"] for r in read_jsonl(wd / "results.jsonl")}


def cmd_build(args):
    arm = ARMS[args.arm]
    tasks = load_tasks(args.dataset)
    ids = list(tasks)[: args.limit_tasks] if args.limit_tasks else list(tasks)
    wd = workdir(args.arm, args.dataset)
    reqs = []
    for task_id in ids:
        task = tasks[task_id]
        prompt = task["prompt"].strip() + "\n"          # codegen.py:70
        content = INSTRUCTION + f"\n```python\n{prompt.strip()}\n```\n"
        for s in range(args.n):
            reqs.append({
                "custom_id": cid(task_id, s),
                "params": {
                    "model": arm["model"],
                    "messages": [{"role": "user", "content": content}],
                    **arm["params"],
                },
            })
    out = wd / "requests.jsonl"
    with open(out, "w") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    meta = dict(arm=args.arm, dataset=args.dataset, n=args.n,
                tasks=len(ids), requests=len(reqs), model=arm["model"])
    (wd / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"built {len(reqs)} requests ({len(ids)} tasks x {args.n}) -> {out}")


def client():
    _d = str(Path(__file__).resolve().parent)
    if _d not in sys.path: sys.path.insert(0, _d)
    from wif_client import client as _wif_client
    return _wif_client("batch")


def submitted_ids(wd):
    p = wd / "submitted.txt"
    return set(p.read_text().split()) if p.exists() else set()


def submit_requests(wd, reqs, state, note):
    c = client()
    cap = int(os.environ.get("CLAUDE_GEN_MAX_BATCHES_PER_CALL", 0)) or None
    n_created = 0
    for i in range(0, len(reqs), BATCH_MAX_REQUESTS):
        if cap and n_created >= cap:
            print(f"stopping after {n_created} batch(es) this call (pacing cap)")
            break
        n_created += 1
        chunk = reqs[i : i + BATCH_MAX_REQUESTS]
        b = c.messages.batches.create(requests=chunk)
        state["batches"].append({"id": b.id, "n": len(chunk), "note": note,
                                 "submitted_at": b.created_at.isoformat()})
        save_state(wd, state)
        with open(wd / "submitted.txt", "a") as f:
            f.write("".join(r["custom_id"] + "\n" for r in chunk))
        print(f"submitted batch {b.id} ({len(chunk)} requests, {note})")


def cmd_submit(args):
    wd = workdir(args.arm, args.dataset)
    reqs = read_jsonl(wd / "requests.jsonl")
    if not reqs:
        sys.exit("no requests.jsonl — run build first")
    done = succeeded_ids(wd) | submitted_ids(wd)  # results + in-flight chunks
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing to submit — all custom_ids already have results or are in flight")
        return
    submit_requests(wd, todo, load_state(wd), note="initial")


def cmd_status(args):
    wd = workdir(args.arm, args.dataset)
    c = client()
    for b in load_state(wd)["batches"]:
        r = c.messages.batches.retrieve(b["id"])
        print(f"{b['id']} [{b['note']}] {r.processing_status} {r.request_counts}")


def cmd_fetch(args):
    wd = workdir(args.arm, args.dataset)
    state = load_state(wd)
    c = client()
    seen = succeeded_ids(wd)
    n_new = n_err = 0
    errored = []
    with open(wd / "results.jsonl", "a") as out:
        for b in state["batches"]:
            if b.get("fetched"):
                continue
            r = c.messages.batches.retrieve(b["id"])
            if r.processing_status != "ended":
                print(f"{b['id']} still {r.processing_status}; skipping")
                continue
            for res in c.messages.batches.results(b["id"]):
                if res.result.type != "succeeded":
                    n_err += 1
                    errored.append({"custom_id": res.custom_id, "type": res.result.type})
                    continue
                if res.custom_id in seen:
                    continue
                m = res.result.message
                text = "".join(blk.text for blk in m.content if blk.type == "text")
                thinking_chars = sum(len(getattr(blk, "thinking", "") or "")
                                     for blk in m.content if blk.type == "thinking")
                rec = {
                    "custom_id": res.custom_id,
                    "model": m.model,
                    "stop_reason": m.stop_reason,
                    "text": text,
                    "thinking_chars": thinking_chars,
                    "usage": {"input_tokens": m.usage.input_tokens,
                              "output_tokens": m.usage.output_tokens},
                }
                out.write(json.dumps(rec) + "\n")
                seen.add(res.custom_id)
                n_new += 1
            b["fetched"] = True
            save_state(wd, state)
    if errored:
        (wd / "errored.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in errored))
    print(f"fetched {n_new} new results; {n_err} errored/canceled/expired "
          f"(see errored.jsonl); total on disk: {len(seen)}")


def cmd_resubmit(args):
    wd = workdir(args.arm, args.dataset)
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd)
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing missing — resubmit not needed")
        return
    print(f"resubmitting {len(todo)} missing/errored requests")
    submit_requests(wd, todo, load_state(wd), note="resubmit")


def cmd_finalize(args):
    from evalplus.sanitize import sanitize
    arm = ARMS[args.arm]
    wd = workdir(args.arm, args.dataset)
    meta = json.loads((wd / "meta.json").read_text())
    tasks = load_tasks(args.dataset)
    ids = list(tasks)[: meta["tasks"]]
    results = {r["custom_id"]: r for r in read_jsonl(wd / "results.jsonl")}

    expected = meta["tasks"] * meta["n"]
    missing, empty, refusals, truncated = [], 0, 0, 0
    out_tokens, think_chars, model_versions = [], [], set()

    outdir = OUTROOT / args.dataset
    outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{arm['chart_name']}_anthropic_temp_{arm['temp_label']}"
    f_san = open(outdir / f"{stem}.jsonl", "w")
    f_raw = open(outdir / f"{stem}.raw.jsonl", "w")
    f_rec = open(outdir / f"{stem}.records.jsonl", "w")

    for task_id in ids:
        entry = tasks[task_id]["entry_point"]
        for s in range(meta["n"]):
            key = cid(task_id, s)
            r = results.get(key)
            if r is None:
                missing.append(key)
                raw = ""
            else:
                raw = r["text"]
                model_versions.add(r["model"])
                out_tokens.append(r["usage"]["output_tokens"])
                think_chars.append(r.get("thinking_chars", 0))
                if r["stop_reason"] == "refusal":
                    refusals += 1
                if r["stop_reason"] == "max_tokens":
                    truncated += 1
                if not raw.strip():
                    empty += 1
            f_raw.write(json.dumps({"task_id": task_id, "solution": raw}) + "\n")
            f_san.write(json.dumps(
                {"task_id": task_id, "solution": sanitize(raw, entrypoint=entry)}) + "\n")
            if r is not None:
                f_rec.write(json.dumps({"task_id": task_id, "sample": s, **r}) + "\n")
    for f in (f_san, f_raw, f_rec):
        f.close()

    n = len(out_tokens)
    print(f"wrote {outdir / (stem + '.jsonl')}")
    print(f"expected {expected} | got {n} | missing {len(missing)} | "
          f"empty {empty} | refusals {refusals} | max_tokens-truncated {truncated}")
    if n:
        st = sorted(out_tokens)
        print(f"output tokens: mean {sum(out_tokens)/n:.0f} "
              f"median {st[n//2]} p90 {st[int(n*0.9)]} max {st[-1]}")
        tc = [t for t in think_chars if t]
        if tc:
            print(f"thinking chars (visible/summarized): n={len(tc)} "
                  f"mean {sum(tc)/len(tc):.0f}")
    print("model version(s) served:", sorted(model_versions))
    if missing:
        print("MISSING — run resubmit before judging. First few:", missing[:5])
        sys.exit(1)
    frac_bad = (empty + refusals + truncated) / max(n, 1)
    if frac_bad > 0.005:
        print(f"WARNING: {frac_bad:.2%} empty/refused/truncated — "
              "investigate before judging (infrastructure failure, not model skill)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "submit", "status", "fetch", "resubmit", "finalize"])
    p.add_argument("--arm", required=True, choices=list(ARMS))
    p.add_argument("--dataset", required=True, choices=list(DATASETS))
    p.add_argument("--n", type=int, default=N_SAMPLES_DEFAULT)
    p.add_argument("--limit-tasks", type=int, default=None)
    args = p.parse_args()
    globals()[f"cmd_{args.cmd}"](args)


if __name__ == "__main__":
    main()
