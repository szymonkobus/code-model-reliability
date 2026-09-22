#!/usr/bin/env python3
import json, sys, os, glob, re, collections, difflib, random
cfg_dir, certs_dir, out = sys.argv[1:4]
prompts = {}
# (prompts not loaded in the fast variant)
def exact_period(tail):
    n = len(tail)
    for p in range(20, min(6000, n // 2) + 1):
        if tail[-p:] == tail[-2 * p:-p]: return p
    return None
def line_cycle(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for k in range(1, min(400, len(lines) // 2) + 1):
        if lines[-k:] == lines[-2 * k:-k]: return k, lines
    return None, lines
def rep_score(text, tail=6000):
    lines = [l.strip() for l in text[-tail:].split('\n') if l.strip()]
    if len(lines) < 5: return 0.0
    return 1 - len(set(lines)) / len(lines)
def echo_share(text, prompt):
    if not prompt or not text: return None
    t = text[:20000]; sm = difflib.SequenceMatcher(None, t, prompt, autojunk=False); cov = sum(n for a, b, n in sm.get_matching_blocks() if n >= 30)
    return cov / len(t)
def code_prose(text):
    code = sum(len(m) for m in re.findall(r'```.*?```', text, re.S)); return code / max(1, len(text))
stats = collections.Counter(); per_class = collections.defaultdict(list); rows_total = 0; cut_rows = 0; tasks_cut = collections.Counter(); tasks_all = collections.Counter()
starts = []; in_loop_tokens = []; echo = collections.defaultdict(list); codeshare = collections.defaultdict(list); had_code = collections.Counter(); closure_c = collections.Counter(); think_tok = []
families = collections.Counter(); per_family_rows = collections.Counter()
random.seed(1)
import time; t0 = time.time(); n_files = 0
att_fh = open(out.replace('.json', '') + '.attempts.tsv', 'w'); att_fh.write('task_id\tsample\tshard\tcut\tclass\tloop\tthink_tokens\tclosure\thad_code_before_end\tloop_start_tokens\n')
for rf in sorted(glob.glob(f'{cfg_dir}/*/*/*.records.jsonl')):
    shard = rf.split('/')[-3]; n_files += 1
    with open(out + '.progress', 'a') as pf: pf.write(f'{time.strftime("%H:%M:%S")} file {n_files} {shard} rows_so_far {rows_total} cut_so_far {cut_rows} classes {dict(stats)}\n')
    with open(rf) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            rows_total += 1; tid = r.get('task_id', ''); fam = tid.split('/')[0]; per_family_rows[fam] += 1; tasks_all[tid] += 1
            if r.get('think_finish_reason') != 'length': continue
            cut_rows += 1; tasks_cut[tid] += 1; families[fam] += 1
            th = r.get('think_text') or ''; tok = r.get('think_tokens') or 0; think_tok.append(tok); closure_c[r.get('closure')] += 1
            p = exact_period(th[-12000:]); k = None; lines = None
            if p: cls = 'exact_loop'; unit = th[-p:]; probe = unit[:200]
            else:
                k, lines = line_cycle(th)
                if k: cls = 'line_loop'; unit = '\n'.join(lines[-k:]); probe = lines[-k]
                elif rep_score(th) > 0.5: cls = 'high_repetition'; unit = None
                else: cls = 'progressing'; unit = None
            stats[cls] += 1
            hc = ('```' in th) or bool(re.search(r'^\s*def \w+\(', th, re.M)); had_code[(cls, hc)] += 1
            if unit is not None:
                st = th.find(probe); frac = st / max(1, len(th)); starts.append((cls, round(tok * frac))); in_loop_tokens.append(tok - round(tok * frac))
            e = None
            codeshare[cls].append(code_prose(th))
            att_fh.write(f"{tid}\t{r.get('sample')}\t{shard}\t1\t{cls}\t{1 if cls in ('exact_loop','line_loop') else 0}\t{tok}\t{r.get('closure')}\t{1 if hc else 0}\t{(round(tok * (th.find(probe) / max(1, len(th))))) if unit is not None else ''}\n")
            if len(per_class[cls]) < 40: per_class[cls].append(dict(task=tid, sample=r.get('sample'), shard=shard, think_tokens=tok, closure=r.get('closure'), had_code=hc, echo=e, tail=th[-320:].replace('\n', ' | '), head=th[:200].replace('\n', ' | ')))
def q(a, ps=(10, 50, 90)):
    a = sorted(a); return [a[int(len(a) * p / 100) if int(len(a) * p / 100) < len(a) else -1] for p in ps] if a else None
summary = dict(config=os.path.basename(cfg_dir.rstrip('/')), rows=rows_total, cut=cut_rows, cut_share=cut_rows / max(1, rows_total), tasks_with_cut=len(tasks_cut), tasks_total=len(tasks_all),
               classes={k: dict(n=v, share=v / max(1, cut_rows)) for k, v in stats.items()}, closure=dict(closure_c),
               had_code_by_class={f'{c}|{"code" if hc else "nocode"}': n for (c, hc), n in had_code.items()},
               loop_start_tokens_pct=q([s for c, s in starts]), tokens_inside_loop_pct=q(in_loop_tokens), think_tokens_pct=q(think_tok),
               echo_share_pct_by_class={c: q(v) for c, v in echo.items()}, fenced_code_share_by_class={c: q(v) for c, v in codeshare.items()},
               cut_by_family={f: dict(cut=n, rows=per_family_rows[f], share=n / max(1, per_family_rows[f])) for f, n in families.most_common()},
               top_tasks=[dict(task=t, cut=n, rows=tasks_all[t]) for t, n in tasks_cut.most_common(12)],
               examples={c: random.sample(v, min(3, len(v))) for c, v in per_class.items()})
att_fh.close(); json.dump(summary, open(out, 'w'), indent=1); print(json.dumps({k: summary[k] for k in ('config', 'rows', 'cut', 'cut_share', 'classes', 'closure', 'loop_start_tokens_pct', 'tokens_inside_loop_pct', 'think_tokens_pct')}, indent=1))
