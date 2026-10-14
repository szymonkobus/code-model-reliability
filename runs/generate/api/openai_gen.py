#!/usr/bin/env python3
"""Same custody interface as the Anthropic drivers (build/submit/status/fetch/
resubmit/export, per-bench workdir state, dedup by custom_id, coverage-gated
export with .PARTIAL. naming) — only the wire format changes:
  upload requests file (purpose=batch) -> create /v1/batches -> poll ->
  download output/error files keyed by custom_id.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from claude_gen import cid, read_jsonl  # noqa: E402  (id encoding + jsonl reader shared)

BASE = "https://api.openai.com/v1"
WORKROOT = Path(__file__).resolve().parent / "work-openai"
OUTROOT = Path(__file__).resolve().parent / "runs-openai"
CHUNK = int(os.environ.get("OPENAI_GEN_CHUNK", "45000"))          # < 50k/batch cap
MAX_FILE_BYTES = 180 * 1024 * 1024                                # < 200MB file cap
PARAM_ALLOW = {"max_tokens", "max_completion_tokens", "temperature",
               "reasoning_effort", "top_p", "seed", "response_format"}


def key():
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        sys.exit("no OpenAI key: set OPENAI_API_KEY in the environment.")
    return k


def api(method, path, timeout=120, **kw):
    r = httpx.request(method, BASE + path, timeout=timeout,
                      headers={"Authorization": f"Bearer {key()}"}, **kw)
    if r.status_code >= 400:
        sys.exit(f"OpenAI API {r.status_code} on {path}: {r.text[:400]}")
    return r


def workdir(bench):
    d = WORKROOT / bench
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(wd):
    p = wd / "state.json"
    return json.loads(p.read_text()) if p.exists() else {"batches": []}


def save_state(wd, state):
    tmp = wd / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(wd / "state.json")


def succeeded_ids(wd):
    p = wd / "results.jsonl"
    if not p.exists():
        return set()
    return {json.loads(l)["custom_id"] for l in open(p)}


def submitted_ids(wd):
    p = wd / "submitted.txt"
    return set(p.read_text().split()) if p.exists() else set()


def cmd_build(args):
    wd = workdir(args.bench)
    lines = read_jsonl(args.prompts)
    reqs, ids = [], set()
    for row in lines:
        tid = row["task_id"]
        assert tid not in ids, f"duplicate task_id {tid}"
        ids.add(tid)
        assert "model" in row, f"{tid}: per-line model required (frontier candidates vary)"
        params = dict(row.get("params", {}))
        bad = set(params) - PARAM_ALLOW
        assert not bad, f"{tid}: params outside transport allowlist: {bad}"
        assert ("max_tokens" in params) or ("max_completion_tokens" in params), \
            f"{tid}: a max-token cap is required (which name is the candidate card's call)"
        assert ("prompt" in row) != ("messages" in row), \
            f"{tid}: exactly one of prompt/messages required"
        msgs = row["messages"] if "messages" in row else [
            {"role": "user", "content": row["prompt"]}]
        n = args.n_override or row.get("n", args.n)
        for s in range(args.sample_start, args.sample_start + n):   # --sample-start S: samples S..S+n-1 (scale-up top-ups keep 0..2 elsewhere)
            reqs.append({
                "custom_id": cid(tid, s),
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {"model": row["model"], "messages": msgs, **params},
            })
    with open(wd / "requests.jsonl", "w") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    cid_map = {}
    for row in lines:
        n = args.n_override or row.get("n", args.n)
        cid_map[row["task_id"]] = n
        base = cid(row["task_id"], 0)[:-6]
        for other in cid_map:
            if other != row["task_id"] and cid(other, 0)[:-6] == base:
                sys.exit(f"custom_id collision after encoding: {other!r} vs {row['task_id']!r}")
    models = sorted({r["body"]["model"] for r in reqs})
    (wd / "meta.json").write_text(json.dumps(
        dict(bench=args.bench, models=models, requests=len(reqs), sample_start=args.sample_start,
             tasks={t: n for t, n in cid_map.items()}), indent=1))
    print(f"built {len(reqs)} requests ({len(ids)} tasks, models {models}) -> {wd}/requests.jsonl")


LABEL = None

def submit_chunk(wd, state, chunk, note):
    payload = "".join(json.dumps(r) + "\n" for r in chunk).encode()
    up = api("POST", "/files", timeout=600,
             files={"file": (f"{wd.name}-{note}.jsonl", payload)},
             data={"purpose": "batch"}).json()
    b = api("POST", "/batches", json={
        "input_file_id": up["id"],
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h",
        **({"metadata": {"description": f"{LABEL} {wd.name}"}} if LABEL else {}),
    }).json()
    state["batches"].append({"id": b["id"], "input_file_id": up["id"],
                             "note": note, "n": len(chunk), **({"label": LABEL} if LABEL else {})})
    save_state(wd, state)
    with open(wd / "submitted.txt", "a") as f:
        f.write("".join(r["custom_id"] + "\n" for r in chunk))
    meta = json.loads((wd / "meta.json").read_text())
    caps = sorted({r["body"].get("max_completion_tokens") or r["body"].get("max_tokens")
                   for r in chunk})
    temps = sorted({str(r["body"].get("temperature", "VENDOR-DEFAULT")) for r in chunk})
    print(f"submitted batch {b['id']} ({len(chunk)} requests, {note})")
    print(f"submitted: bench={wd.name} requests={len(chunk)} models={meta['models']} "
          f"max-token card={caps} temperature={temps} window=24h")


def cmd_submit(args):
    wd = workdir(args.bench)
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd) | submitted_ids(wd)
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing to submit — all custom_ids already have results or are in flight")
        return
    state = load_state(wd)
    i = 0
    while i < len(todo):
        chunk, size = [], 0
        while i < len(todo) and len(chunk) < CHUNK and size < MAX_FILE_BYTES:
            line = json.dumps(todo[i])
            chunk.append(todo[i]); size += len(line) + 1; i += 1
        submit_chunk(wd, state, chunk, note=f"initial-{len(state['batches'])}")


def cmd_status(args):
    wd = workdir(args.bench)
    for b in load_state(wd)["batches"]:
        r = api("GET", f"/batches/{b['id']}").json()
        print(f"{b['id']} [{b['note']}] {r['status']} {r.get('request_counts')}")


def download_file(fid):
    return api("GET", f"/files/{fid}/content", timeout=600).text


def cmd_fetch(args):
    wd = workdir(args.bench)
    state = load_state(wd)
    seen = succeeded_ids(wd)
    n_new = n_err = 0
    errored = []
    with open(wd / "results.jsonl", "a") as out:
        for b in state["batches"]:
            if b.get("fetched"):
                continue
            r = api("GET", f"/batches/{b['id']}").json()
            if r["status"] not in ("completed", "failed", "expired", "cancelled"):
                print(f"{b['id']} still {r['status']}; skipping")
                continue
            for fid_key in ("output_file_id", "error_file_id"):
                fid = r.get(fid_key)
                if not fid:
                    continue
                for line in download_file(fid).splitlines():
                    res = json.loads(line)
                    resp = res.get("response") or {}
                    if res.get("error") or resp.get("status_code") != 200:
                        n_err += 1
                        errored.append({"custom_id": res["custom_id"],
                                        "error": res.get("error") or resp.get("body", {}).get("error")})
                        continue
                    if res["custom_id"] in seen:
                        continue
                    body = resp["body"]
                    ch = body["choices"][0]
                    msg = ch["message"]
                    out.write(json.dumps({
                        "custom_id": res["custom_id"], "model": body["model"],
                        "finish_reason": ch.get("finish_reason"),
                        "text": msg.get("content") or "",
                        "refusal": msg.get("refusal"),
                        "usage": body.get("usage", {}),
                    }) + "\n")
                    seen.add(res["custom_id"])
                    n_new += 1
            b["fetched"] = True
            save_state(wd, state)
    if errored:
        with open(wd / "errored.jsonl", "w") as f:
            f.write("".join(json.dumps(e) + "\n" for e in errored))
    print(f"fetched {n_new} new; {n_err} errored; total {len(seen)}")


def cmd_resubmit(args):
    wd = workdir(args.bench)
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd)
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing missing")
        return
    print(f"resubmitting {len(todo)}")
    state = load_state(wd)
    submit_chunk(wd, state, todo, note=f"resubmit-{len(state['batches'])}")


def cmd_export(args):
    wd = workdir(args.bench)
    meta = json.loads((wd / "meta.json").read_text())
    results = {r["custom_id"]: r for r in read_jsonl(wd / "results.jsonl")} \
        if (wd / "results.jsonl").exists() else {}
    OUTROOT.mkdir(parents=True, exist_ok=True)
    n_expected = sum(meta["tasks"].values())
    s0 = int(meta.get("sample_start", 0))
    complete = (len(results) >= n_expected) and all(
        cid(t, i) in results for t, n in meta["tasks"].items() for i in range(s0, s0 + n))
    suffix = ".completions.jsonl" if complete else ".completions.PARTIAL.jsonl"
    out_path = OUTROOT / f"{args.bench}{suffix}"
    missing, empty, refusals, truncated, models = [], 0, 0, 0, set()
    n_written = 0
    with open(out_path, "w") as f:
        for tid, n in meta["tasks"].items():
            for s in range(s0, s0 + n):
                r = results.get(cid(tid, s))
                if r is None:
                    missing.append(cid(tid, s))
                    continue
                models.add(r["model"])
                if r.get("refusal"): refusals += 1
                if r.get("finish_reason") == "length": truncated += 1
                if not (r.get("text") or "").strip(): empty += 1
                f.write(json.dumps({
                    "task_id": tid, "sample": s, "text": r["text"],
                    "finish_reason": r.get("finish_reason"),
                    "refusal": r.get("refusal"),
                    "tokens": (r.get("usage") or {}).get("completion_tokens"),
                    "output_tokens": (r.get("usage") or {}).get("completion_tokens"),
                    "input_tokens": (r.get("usage") or {}).get("prompt_tokens"),
                    "model": r["model"],
                }) + "\n")
                n_written += 1
    print(f"wrote {out_path}: {n_written} completions | missing {len(missing)} | "
          f"empty {empty} | refusals {refusals} | truncated {truncated} | models {sorted(models)}")
    if missing:
        print("MISSING — wrote PARTIAL file; run resubmit + fetch, then re-export. First:", missing[:5])
        sys.exit(1)
    bad = (empty + refusals + truncated) / max(n_written, 1)
    if bad > 0.005:
        print(f"WARNING: {bad:.2%} empty/refused/truncated — investigate before judging")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "submit", "status", "fetch", "resubmit", "export"])
    p.add_argument("--bench", required=True)
    p.add_argument("--prompts")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--sample-start", type=int, default=0)
    p.add_argument("--n-override", type=int, default=None)
    p.add_argument("--label", default=None, help="batch label token (a frame's TOKEN) written into each batch's metadata description")
    args = p.parse_args()
    global LABEL; LABEL = args.label or None
    globals()[f"cmd_{args.cmd}"](args)


if __name__ == "__main__":
    main()
