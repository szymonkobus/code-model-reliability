import argparse
import hashlib
import json
import os
import sys
from collections import Counter

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from evalplus.data import get_human_eval_plus, get_mbpp_plus
from evalplus.provider.utility import EOS
from evalplus.sanitize import sanitize

INSTR = "Please provide a self-contained Python script that solves the following problem in a markdown code block:"
RESP = "Below is a Python script with a self-contained function that solves the problem and passes corresponding tests:"
PIPELINE_STOPS = EOS + ["\n```\n"]

CARD = dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
THINK_BUDGET = 32768
ANSWER_BUDGET = 2048
MAX_MODEL_LEN = 40960  # hybrid max_position_embeddings


def base_prompt(tok, problem):
    user = f"{INSTR}\n```\n{problem.strip()}\n```\n"
    return tok.apply_chat_template(
        [{"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True,
    )


def compose_phase2(bp, trace):
    # Openness is judged on prompt+trace: some templates open <think> in
    # the prompt.
    if trace.endswith("</think>"):
        closure, mid = "natural", ""
    elif (bp + trace).rfind("<think>") > (bp + trace).rfind("</think>"):
        closure, mid = "forced", "\n</think>"
    else:
        closure, mid = "no_think", ""
    return bp + trace + mid + f"\n\n{RESP}\n```python\n", closure


def count_done(path):
    # Tolerates a torn final line (think.sbatch repairs the files; this only
    # matters if the runner is invoked directly after a crash).
    done = Counter()
    if os.path.exists(path):
        lines = open(path).read().splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                done[json.loads(line)["task_id"]] += 1
            except ValueError:
                if i == len(lines) - 1:
                    break
                raise
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("out", help="output path without suffix")
    ap.add_argument("--n", type=int, default=128)
    ap.add_argument("--dataset", choices=["humaneval", "mbpp"], default="humaneval")
    args = ap.parse_args()

    records_path = args.out + ".records.jsonl"
    samples_path = args.out + ".jsonl"
    tok = AutoTokenizer.from_pretrained(args.model)
    problems = {"humaneval": get_human_eval_plus, "mbpp": get_mbpp_plus}[args.dataset]()

    probe_bp = base_prompt(tok, next(iter(problems.values()))["prompt"])
    template_class = ("thinking-only (opens <think> in prompt)"
                      if probe_bp.rfind("<think>") > probe_bp.rfind("</think>")
                      else "hybrid (enable_thinking switch)")
    print(f"template_class: {template_class}")

    done = count_done(records_path)
    todo = {t: args.n - done[t] for t in problems if done[t] < args.n}
    print(f"{len(problems)} tasks; {sum(todo.values())} samples to generate "
          f"({len(problems) - len(todo)} tasks already complete)")
    if not todo:
        return

    llm = LLM(model=args.model, max_model_len=MAX_MODEL_LEN,
              enable_chunked_prefill=True, enable_prefix_caching=True)
    answer_sp = SamplingParams(n=1, max_tokens=ANSWER_BUDGET,
                               stop=PIPELINE_STOPS, **CARD)

    rec_f = open(records_path, "a")
    sam_f = open(samples_path, "a")
    closures = Counter()
    for task_id, k in todo.items():
        bp = base_prompt(tok, problems[task_id]["prompt"])
        think_sp = SamplingParams(n=k, max_tokens=THINK_BUDGET, stop=["</think>"],
                                  include_stop_str_in_output=True, **CARD)
        p1 = llm.generate([bp], think_sp)[0]
        p2_prompts, metas = [], []
        for i, o in enumerate(p1.outputs):
            p2, closure = compose_phase2(bp, o.text)
            closures[closure] += 1
            digest = hashlib.sha256(p2.encode()).hexdigest()
            p2_prompts.append(p2)
            metas.append((done[task_id] + i, o.text, len(o.token_ids),
                          o.finish_reason, closure, digest))
        for meta, out in zip(metas, llm.generate(p2_prompts, answer_sp)):
            idx, trace, ttok, tfin, closure, digest = meta
            ans = out.outputs[0]
            ans_text = ans.text.replace("\t", "    ")  # mirrors evalplus's provider
            record = {
                "model": args.model, "task_id": task_id, "sample": idx,
                "think_text": trace, "think_tokens": ttok,
                "think_finish_reason": tfin, "closure": closure,
                "answer_raw": ans_text, "answer_tokens": len(ans.token_ids),
                "answer_finish_reason": ans.finish_reason,
                "phase2_prompt_sha256": digest,
            }
            # Write-time reconstruction identity: the archived fields + this
            # file's code must reproduce the exact prompt bytes we sent.
            rebuilt, _ = compose_phase2(base_prompt(tok, problems[task_id]["prompt"]),
                                        record["think_text"])
            assert hashlib.sha256(rebuilt.encode()).hexdigest() == digest, \
                f"phase-2 prompt not reconstructible for {task_id} sample {idx}"
            rec_line = json.dumps(record) + "\n"
            sam_line = json.dumps({
                "task_id": task_id,
                "solution": sanitize(ans_text, entrypoint=problems[task_id]["entry_point"]),
            }) + "\n"
            rec_f.write(rec_line)
            sam_f.write(sam_line)
            rec_f.flush()
            sam_f.flush()
        print(f"{task_id}: +{k} (closures so far: {dict(closures)})")
    rec_f.close()
    sam_f.close()
    print(f"generation done: {samples_path}")


if __name__ == "__main__":
    main()
