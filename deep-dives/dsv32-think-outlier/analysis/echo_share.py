"""Anatomy of cut answers (answers that hit the token cap) for one board arm with records-v2: what share of the answer's characters is
(a) the task prompt echoed back (signature + docstring; matched as blocks of >= 30 characters shared with the prompt), (b) comment or
docstring prose the model added, (c) code. Usage: echo_share.py <records.jsonl humaneval> <records.jsonl mbpp> <label>"""
import json, sys, re, difflib, collections, numpy as np, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
prompts = {}
for f in ('HumanEvalPlus-v0.1.10-boolfiltered.jsonl', 'MbppPlus-v0.2.0-boolfiltered.jsonl'):
    for l in open(f'{ROOT}/data/datasets/{f}'):
        d = json.loads(l); prompts[d['task_id']] = d['prompt']
def echo_chars(ans, prompt):
    sm = difflib.SequenceMatcher(None, ans, prompt, autojunk=False); cov = 0
    for a, b, n in sm.get_matching_blocks():
        if n >= 30: cov += n
    return cov
def prose_code_split(ans):
    """characters in comment lines or inside triple-quoted strings vs the rest (non-blank)"""
    prose = code = 0; in_doc = False
    for line in ans.split('\n'):
        s = line.strip()
        if not s: continue
        q = s.count('"""') + s.count("'''")
        if in_doc: prose += len(s); in_doc = (q % 2 == 0); continue
        if q: prose += len(s); in_doc = (q % 2 == 1); continue
        if s.startswith('#'): prose += len(s); continue
        code += len(s)
    return prose, code
def run(path, label):
    rows = []
    for l in open(path):
        r = json.loads(l)
        if r.get('think_finish_reason') != 'length': continue
        ans = r.get('answer_raw') or ''; p = prompts.get(r['task_id'], '')
        if not ans or not p: continue
        e = echo_chars(ans, p); prose, code = prose_code_split(ans); tot = len(ans)
        header_only = bool(re.search(r'^def \w+\(', ans, re.M)) and code <= len(re.findall(r'^def [^\n]*', ans, re.M) and ''.join(re.findall(r'^def [^\n]*', ans, re.M))) + 20
        rows.append(dict(task=r['task_id'], chars=tot, echo=e / tot, prose=prose / max(1, prose + code), code=code / max(1, prose + code), prompt_chars=len(p), header_only=header_only))
    return rows
out = {}
for path, ds in ((sys.argv[1], 'humaneval'), (sys.argv[2], 'mbpp')):
    rows = run(path, ds)
    if not rows: out[ds] = dict(cut=0); continue
    q = lambda k: [float(x) for x in np.percentile([r[k] for r in rows], [10, 50, 90])]
    out[ds] = dict(cut=len(rows), echo_share_pct=q('echo'), prose_share_pct=q('prose'), code_share_pct=q('code'), answer_chars_pct=q('chars'), prompt_chars_pct=q('prompt_chars'),
                   echo_over_50pct=sum(1 for r in rows if r['echo'] > 0.5), header_only=sum(1 for r in rows if r['header_only']))
print(sys.argv[3], json.dumps(out, indent=1))
json.dump(out, open(f'{ROOT}/data/echo_share_{sys.argv[3]}.json', 'w'), indent=1)
