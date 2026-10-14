#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_gen import (  # noqa: E402
    cid, client, load_state, read_jsonl, save_state,
    submit_requests, submitted_ids, succeeded_ids,
)

MODEL_SNAPSHOT = "claude-haiku-4-5-20251001"
WORKROOT = Path(__file__).resolve().parent / "work-external"
OUTROOT = Path(__file__).resolve().parent / "runs-external"


def workdir(bench):
    d = WORKROOT / bench
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_build(args):
    wd = workdir(args.bench)
    lines = read_jsonl(args.prompts)
    reqs, ids = [], set()
    for row in lines:
        tid = row["task_id"]
        assert tid not in ids, f"duplicate task_id {tid}"
        ids.add(tid)
        params = dict(row.get("params", {}))
        model = row.get("model", MODEL_SNAPSHOT)
        # 5-family rejects temperature (400) and needs its thinking card explicit;
        # haiku keeps the T=0.8 convention. Cards match the chart-arm registry.
        five_family = model.startswith(("claude-sonnet-5", "claude-opus-5",
                                        "claude-fable-5", "claude-opus-4-6", "claude-haiku-5-5"))
        thinking_card = isinstance(params.get("thinking"), dict) and \
            params["thinking"].get("type") in ("enabled", "adaptive")
        if five_family:
            assert "temperature" not in params, f"{tid}: temperature illegal on {model}"
            if not args.thinking and not model.startswith("claude-fable-5"):
                params.setdefault("thinking", {"type": "disabled"})
        elif thinking_card:
            assert params.get("temperature", 1) == 1, \
                f"{tid}: temperature must be 1 (or omitted) with thinking enabled"
        else:
            params.setdefault("temperature", 0.8)
        assert "max_tokens" in params, f"{tid}: params.max_tokens required"
        if args.thinking:
            # recorded delta: bench max_tokens becomes judge-side expectation;
            # API params follow the published haiku-thinking arm exactly
            assert not five_family, f"{tid}: --thinking is the haiku fixed-budget card; 5-family thinking needs its own card"
            params["temperature"] = 1
            params["max_tokens"] = 36864
            params["thinking"] = {"type": "enabled", "budget_tokens": 32768}
        if "stop_sequences" in params:
            ss = params["stop_sequences"]
            assert isinstance(ss, list) and ss and all(isinstance(x, str) for x in ss), \
                f"{tid}: stop_sequences must be a non-empty list of strings"
            thinking_on = args.thinking or (
                isinstance(params.get("thinking"), dict)
                and params["thinking"].get("type") in ("enabled", "adaptive"))
            assert not thinking_on, \
                f"{tid}: stops are forbidden on thinking cards (recorded protocol)"
        assert not {"top_p", "top_k", "system"} & params.keys(), \
            f"{tid}: param outside recorded protocol"
        assert ("prompt" in row) != ("messages" in row),             f"{tid}: exactly one of prompt/messages required"
        msgs = row["messages"] if "messages" in row else [
            {"role": "user", "content": row["prompt"]}]
        n = args.n_override or row.get("n", args.n)
        for s in range(args.sample_start, args.sample_start + n):   # --sample-start S: attempts carry sample indices S..S+n-1 (scale-up top-ups keep the smoke-scale 0..2)
            reqs.append({
                "custom_id": cid(tid, s),
                "params": {
                    "model": row.get("model", MODEL_SNAPSHOT),
                    "messages": msgs,
                    **params,
                },
            })
    with open(wd / "requests.jsonl", "w") as f:
        for r in reqs:
            f.write(json.dumps(r) + "\n")
    # task order + per-task n preserved for export; cid map handles charset collisions
    cid_map = {}
    for row in lines:
        n = args.n_override or row.get("n", args.n)
        cid_map[row["task_id"]] = n
        base = cid(row["task_id"], 0)[:-6]
        for other, _ in cid_map.items():
            if other != row["task_id"] and cid(other, 0)[:-6] == base:
                sys.exit(f"custom_id collision after encoding: {other!r} vs {row['task_id']!r}")
    (wd / "meta.json").write_text(json.dumps(
        dict(bench=args.bench,
             model=(lambda ms: ms[0] if len(ms) == 1 else ms)(
                 sorted({r["params"]["model"] for r in reqs})),
             requests=len(reqs), sample_start=args.sample_start,
             tasks={t: n for t, n in cid_map.items()}), indent=1))
    print(f"built {len(reqs)} requests ({len(ids)} tasks) -> {wd}/requests.jsonl")


def cmd_submit(args):
    wd = workdir(args.bench)
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd) | submitted_ids(wd)
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing to submit — all custom_ids already have results or are in flight")
        return
    submit_requests(wd, todo, load_state(wd), note="initial")


def cmd_status(args):
    wd = workdir(args.bench)
    c = client()
    for b in load_state(wd)["batches"]:
        r = c.messages.batches.retrieve(b["id"])
        print(f"{b['id']} [{b['note']}] {r.processing_status} {r.request_counts}")


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
                thinking = [(getattr(blk, "thinking", "") or "") for blk in m.content if blk.type == "thinking"]
                redacted = sum(1 for blk in m.content if blk.type == "redacted_thinking")
                out.write(json.dumps({
                    "custom_id": res.custom_id, "model": m.model, "message_id": getattr(m, "id", None),
                    "stop_reason": m.stop_reason, "text": text,
                    "thinking_chars": thinking_chars,
                    "thinking": thinking, "redacted_thinking_blocks": redacted, "batch": b["id"],
                    "usage": {"input_tokens": m.usage.input_tokens,
                              "output_tokens": m.usage.output_tokens},
                }) + "\n")
                seen.add(res.custom_id)
                n_new += 1
            b["fetched"] = True; b["created_at"] = str(getattr(r, "created_at", None) or ""); b["ended_at"] = str(getattr(r, "ended_at", None) or ""); b["fetched_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())
            save_state(wd, state)
    if errored:
        (wd / "errored.jsonl").write_text("".join(json.dumps(e) + "\n" for e in errored))
    print(f"fetched {n_new} new; {n_err} errored/canceled/expired; total {len(seen)}")


def cmd_resubmit(args):
    wd = workdir(args.bench)
    reqs = read_jsonl(wd / "requests.jsonl")
    done = succeeded_ids(wd)
    todo = [r for r in reqs if r["custom_id"] not in done]
    if not todo:
        print("nothing missing")
        return
    print(f"resubmitting {len(todo)}")
    ch = int(os.environ.get("CLAUDE_EXT_RESUBMIT_CHUNK", "0") or 0)
    if ch > 0:
        for i in range(0, len(todo), ch):
            submit_requests(wd, todo[i:i + ch], load_state(wd), note=f"resubmit-{i // ch + 1}")
    else:
        submit_requests(wd, todo, load_state(wd), note="resubmit")


def cmd_export(args):
    wd = workdir(args.bench)
    meta = json.loads((wd / "meta.json").read_text())
    results = {r["custom_id"]: r for r in read_jsonl(wd / "results.jsonl")}
    OUTROOT.mkdir(parents=True, exist_ok=True)
    n_expected = sum(meta["tasks"].values())
    dupes = len(read_jsonl(wd / "results.jsonl")) - len(results)
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
                if r["stop_reason"] == "refusal": refusals += 1
                if r["stop_reason"] == "max_tokens": truncated += 1
                if not r["text"].strip(): empty += 1
                f.write(json.dumps({
                    "task_id": tid, "sample": s, "text": r["text"],
                    "stop_reason": r["stop_reason"],
                    "thinking_chars": r.get("thinking_chars", 0),
                    "thinking": r.get("thinking"), "redacted_thinking_blocks": r.get("redacted_thinking_blocks"), "batch": r.get("batch"),
                    "tokens": r["usage"]["output_tokens"],
                    "output_tokens": r["usage"]["output_tokens"],
                    "input_tokens": r["usage"]["input_tokens"],
                    "model": r["model"],
                    "message_id": r.get("message_id"),
                }) + "\n")
                n_written += 1
    print(f"wrote {out_path}: {n_written} completions | missing {len(missing)} | "
          f"empty {empty} | refusals {refusals} | truncated {truncated} | models {sorted(models)}")
    if dupes:
        print(f"NOTE: {dupes} duplicate result rows in ledger (deduped by custom_id)")
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
    p.add_argument("--n", type=int, default=128)
    p.add_argument("--sample-start", type=int, default=0, help="first sample index (top-ups: 3 keeps the smoke-scale 0..2 in their own landing)")
    p.add_argument("--n-override", type=int, default=None,
                   help="force n per task (validation wave: 1)")
    p.add_argument("--thinking", action="store_true",
                   help="haiku-thinking regime: T=1, budget 32768, max_tokens 36864")
    args = p.parse_args()
    globals()[f"cmd_{args.cmd}"](args)


if __name__ == "__main__":
    main()
