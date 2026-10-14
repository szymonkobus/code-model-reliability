#!/usr/bin/env python3
"""Same custody interface as openai_gen.py / claude_gen_external.py: build/submit/
status/fetch/resubmit/export, per-bench workdir, dedup by key, coverage-gated
export with .PARTIAL. naming. Wire format is the SDK's batches surface: build
writes a JSONL of {"key": <cid>, "request": {contents, generationConfig}},
submit uploads it and creates one batch job per chunk, fetch downloads the
result file and dedupes by key.

Gemini batch constraint: ONE MODEL PER BATCH JOB (the model is a property of
the job, not the request line) — build asserts a single model per bench.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_gen import cid, read_jsonl  # noqa: E402

WORKROOT = Path(__file__).resolve().parent / "work-gemini"
OUTROOT = Path(__file__).resolve().parent / "runs-gemini"
CHUNK = int(os.environ.get("GEMINI_GEN_CHUNK", "45000"))
PARAM_ALLOW = {"max_output_tokens", "temperature", "top_p", "thinking_config",
               "response_mime_type"}


def client():
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        sys.exit("no Gemini key: set GEMINI_API_KEY in the environment.")
    from google import genai
    return genai.Client(api_key=k)


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
    return {json.loads(l)["key"] for l in open(p)}


def submitted_ids(wd):
    p = wd / "submitted.txt"
    return set(p.read_text().split()) if p.exists() else set()


def cmd_build(args):
    wd = workdir(args.bench)
    lines = read_jsonl(args.prompts)
    reqs, ids, models = [], set(), set()
    for row in lines:
        tid = row["task_id"]
        assert tid not in ids, f"duplicate task_id {tid}"
        ids.add(tid)
        assert "model" in row, f"{tid}: per-line model required"
        models.add(row["model"])
        params = dict(row.get("params", {}))
        bad = set(params) - PARAM_ALLOW
        assert not bad, f"{tid}: params outside transport allowlist: {bad}"
        assert "max_output_tokens" in params, f"{tid}: max_output_tokens required"
        assert ("prompt" in row) != ("contents" in row), \
            f"{tid}: exactly one of prompt/contents required"
        contents = row["contents"] if "contents" in row else [
            {"role": "user", "parts": [{"text": row["prompt"]}]}]
        n = args.n_override or row.get("n", args.n)
        for s in range(args.sample_start, args.sample_start + n):   # --sample-start S: samples S..S+n-1 (scale-up top-ups keep 0..2 elsewhere)
            reqs.append({
                "key": cid(tid, s),
                "request": {"contents": contents, "generation_config": params},
            })
    assert len(models) == 1, f"Gemini batch = one model per job; got {sorted(models)}"
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
    (wd / "meta.json").write_text(json.dumps(
        dict(bench=args.bench, model=models.pop(), requests=len(reqs), sample_start=args.sample_start,
             tasks={t: n for t, n in cid_map.items()}), indent=1))
    print(f"built {len(reqs)} requests ({len(ids)} tasks) -> {wd}/requests.jsonl")


LABEL = None

def submit_chunk(wd, state, chunk, model, note):
    c = client()
    tmp = wd / f"upload-{note}.jsonl"
    with open(tmp, "w") as f:
        for r in chunk:
            f.write(json.dumps(r) + "\n")
    up = c.files.upload(file=str(tmp), config={"mime_type": "application/jsonl",
                                               "display_name": f"{LABEL + '-' if LABEL else ''}{wd.name}-{note}"})
    job = c.batches.create(model=model, src=up.name,
                           config={"display_name": f"{LABEL + '-' if LABEL else ''}{wd.name}-{note}"})
    state["batches"].append({"name": job.name, "src": up.name,
                             "note": note, "n": len(chunk), **({"label": LABEL} if LABEL else {})})
    save_state(wd, state)
    with open(wd / "submitted.txt", "a") as f:
        f.write("".join(r["key"] + "\n" for r in chunk))
    caps = sorted({r["request"]["generation_config"].get("max_output_tokens")
                   for r in chunk})
    temps = sorted({str(r["request"]["generation_config"].get("temperature", "VENDOR-DEFAULT"))
                    for r in chunk})
    print(f"submitted batch {job.name} ({len(chunk)} requests, {note})")
    print(f"submitted: bench={wd.name} requests={len(chunk)} model={model} "
          f"max-token card={caps} temperature={temps} ")


def cmd_submit(args):
    wd = workdir(args.bench)
    meta = json.loads((wd / "meta.json").read_text())
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd) | submitted_ids(wd)
    todo = [r for r in reqs if r["key"] not in done]
    if not todo:
        print("nothing to submit — all keys already have results or are in flight")
        return
    state = load_state(wd)
    for i in range(0, len(todo), CHUNK):
        submit_chunk(wd, state, todo[i:i + CHUNK], meta["model"],
                     note=f"initial-{len(state['batches'])}")


TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
            "JOB_STATE_EXPIRED"}


def cmd_status(args):
    wd = workdir(args.bench)
    c = client()
    for b in load_state(wd)["batches"]:
        job = c.batches.get(name=b["name"])
        print(f"{b['name']} [{b['note']}] {job.state.name if hasattr(job.state,'name') else job.state}")


def cmd_fetch(args):
    wd = workdir(args.bench)
    state = load_state(wd)
    c = client()
    seen = succeeded_ids(wd)
    n_new = n_err = 0
    errored = []
    with open(wd / "results.jsonl", "a") as out:
        for b in state["batches"]:
            if b.get("fetched"):
                continue
            job = c.batches.get(name=b["name"])
            st = job.state.name if hasattr(job.state, "name") else str(job.state)
            if st not in TERMINAL:
                print(f"{b['name']} still {st}; skipping")
                continue
            dest = getattr(job, "dest", None)
            fname = getattr(dest, "file_name", None) if dest else None
            if not fname:
                print(f"{b['name']} {st} with no result file (job-level failure)")
                b["fetched"] = True
                save_state(wd, state)
                continue
            blob = c.files.download(file=fname)
            text = blob.decode() if isinstance(blob, bytes) else str(blob)
            for line in text.splitlines():
                if not line.strip():
                    continue
                res = json.loads(line)
                k = res.get("key")
                if res.get("error"):
                    n_err += 1
                    errored.append({"key": k, "error": res["error"]})
                    continue
                if k in seen:
                    continue
                resp = res.get("response") or {}
                cands = resp.get("candidates") or []
                parts = (cands[0].get("content") or {}).get("parts") if cands else None
                txt = "".join(p.get("text", "") for p in (parts or []))
                out.write(json.dumps({
                    "key": k,
                    "model": resp.get("modelVersion") or resp.get("model_version") or "",
                    "finish_reason": (cands[0].get("finishReason") or
                                      cands[0].get("finish_reason")) if cands else None,
                    "text": txt,
                    "usage": resp.get("usageMetadata") or resp.get("usage_metadata") or {},
                }) + "\n")
                seen.add(k)
                n_new += 1
            b["fetched"] = True
            save_state(wd, state)
    if errored:
        with open(wd / "errored.jsonl", "w") as f:
            f.write("".join(json.dumps(e) + "\n" for e in errored))
    print(f"fetched {n_new} new; {n_err} errored; total {len(seen)}")


def cmd_resubmit(args):
    wd = workdir(args.bench)
    meta = json.loads((wd / "meta.json").read_text())
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd)
    todo = [r for r in reqs if r["key"] not in done]
    if not todo:
        print("nothing missing")
        return
    print(f"resubmitting {len(todo)}")
    state = load_state(wd)
    submit_chunk(wd, state, todo, meta["model"], note=f"resubmit-{len(state['batches'])}")


def cmd_export(args):
    wd = workdir(args.bench)
    meta = json.loads((wd / "meta.json").read_text())
    results = {r["key"]: r for r in read_jsonl(wd / "results.jsonl")} \
        if (wd / "results.jsonl").exists() else {}
    OUTROOT.mkdir(parents=True, exist_ok=True)
    n_expected = sum(meta["tasks"].values())
    s0 = int(meta.get("sample_start", 0))
    complete = (len(results) >= n_expected) and all(
        cid(t, i) in results for t, n in meta["tasks"].items() for i in range(s0, s0 + n))
    suffix = ".completions.jsonl" if complete else ".completions.PARTIAL.jsonl"
    out_path = OUTROOT / f"{args.bench}{suffix}"
    missing, empty, truncated, models = [], 0, 0, set()
    n_written = 0
    with open(out_path, "w") as f:
        for tid, n in meta["tasks"].items():
            for s in range(s0, s0 + n):
                r = results.get(cid(tid, s))
                if r is None:
                    missing.append(cid(tid, s))
                    continue
                models.add(r.get("model") or meta["model"])
                if r.get("finish_reason") == "MAX_TOKENS": truncated += 1
                if not (r.get("text") or "").strip(): empty += 1
                usage = r.get("usage") or {}
                out_tok = usage.get("candidatesTokenCount") or usage.get("candidates_token_count")
                fr_raw = r.get("finish_reason")
                fr = {"STOP": "stop", "MAX_TOKENS": "length",
                      "SAFETY": "content_filter", "RECITATION": "recitation",
                      "MALFORMED_FUNCTION_CALL": "malformed_function_call",
                      "OTHER": "other"}.get(fr_raw, (fr_raw or "").lower() or None)
                f.write(json.dumps({
                    "task_id": tid, "sample": s, "text": r["text"],
                    "finish_reason": fr,
                    "finish_reason_raw": fr_raw,
                    "tokens": out_tok,
                    "output_tokens": out_tok,
                    "input_tokens": usage.get("promptTokenCount") or usage.get("prompt_token_count"),
                    "thinking_tokens": usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count"),
                    "model": r.get("model") or meta["model"],
                    "lane": r.get("lane") or "batch",   # sync re-fire rows (gemini_sync.py) carry lane "sync"; batch rows default
                }) + "\n")
                n_written += 1
    print(f"wrote {out_path}: {n_written} completions | missing {len(missing)} | "
          f"empty {empty} | truncated {truncated} | models {sorted(models)}")
    if missing:
        print("MISSING — wrote PARTIAL file; run resubmit + fetch, then re-export. First:", missing[:5])
        sys.exit(1)
    bad = (empty + truncated) / max(n_written, 1)
    if bad > 0.005:
        print(f"WARNING: {bad:.2%} empty/truncated — investigate before judging")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "submit", "status", "fetch", "resubmit", "export"])
    p.add_argument("--bench", required=True)
    p.add_argument("--prompts")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--sample-start", type=int, default=0)
    p.add_argument("--n-override", type=int, default=None)
    p.add_argument("--label", default=None, help="batch label token (a frame's TOKEN) prefixed to the batch display names")
    args = p.parse_args()
    global LABEL; LABEL = args.label or None
    globals()[f"cmd_{args.cmd}"](args)


if __name__ == "__main__":
    main()
