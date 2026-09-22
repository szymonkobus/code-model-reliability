"""Rebuild intended solutions for group H candidates (v32-chat|humaneval).

Extraction ladder (matches board_verified_G method):
1. last parseable code fence containing def <entry_point> (exact AST name match)
2. nested-fence rescan (```python opened inside an unclosed fence)
3. implicit fence: segment before the first fence-marker line (whole reply
   when no markers exist)
Def-bearing but unparseable body -> genuine model failure (verdict wrong,
not executed). No def-bearing body -> unverifiable-degenerate.

Prune: drop top-level example statements (asserts, bare expressions/prints,
entry-point invocations, __main__ blocks); keep entry def plus transitively
referenced model-authored helpers/imports/constants (wildcard imports always
kept). Normalize via ast.unparse for shape dedup.
"""
import ast
import json
import re

META = 'deep-dives/rare-failures/meta'


def fence_bodies(text):
    """Return list of fenced bodies via line-based pairing of ``` markers."""
    lines = text.split('\n')
    bodies = []
    open_i = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith('```'):
            if open_i is None:
                open_i = i
            else:
                bodies.append('\n'.join(lines[open_i + 1:i]))
                open_i = None
    return bodies


def nested_fence_bodies(text):
    """Rescan: recover a ```python fence opened inside an unclosed fence."""
    lines = text.split('\n')
    marker_idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith('```')]
    bodies = []
    for j, i in enumerate(marker_idx):
        if re.match(r'```\s*python', lines[i].lstrip()):
            end = marker_idx[j + 1] if j + 1 < len(marker_idx) else len(lines)
            if isinstance(end, int) and end != i:
                stop = end if end < len(lines) else len(lines)
                bodies.append('\n'.join(lines[i + 1:stop]))
    return bodies


def has_entry_def(tree, entry):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry:
            return True
    return False


def choose_body(raw, entry):
    """Return (body, rung, parseable). rung in {def-fence, nested-fence, implicit-fence}."""
    textual = re.compile(r'def\s+' + re.escape(entry) + r'\s*\(')
    bodies = fence_bodies(raw)
    parseable_hits, textual_hits = [], []
    for b in bodies:
        try:
            tree = ast.parse(b)
        except SyntaxError:
            if textual.search(b):
                textual_hits.append(b)
            continue
        if has_entry_def(tree, entry):
            parseable_hits.append(b)
    if parseable_hits:
        return parseable_hits[-1], 'def-fence', True
    if textual_hits:
        return textual_hits[-1], 'def-fence', False
    # rung 2: nested-fence rescan
    for b in reversed(nested_fence_bodies(raw)):
        try:
            tree = ast.parse(b)
        except SyntaxError:
            continue
        if has_entry_def(tree, entry):
            return b, 'nested-fence', True
    # rung 3: implicit fence
    lines = raw.split('\n')
    first_marker = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith('```')), None)
    seg = raw if first_marker is None else '\n'.join(lines[:first_marker])
    if textual.search(seg):
        try:
            tree = ast.parse(seg)
            ok = has_entry_def(tree, entry)
        except SyntaxError:
            return seg, 'implicit-fence', False
        if ok:
            return seg, 'implicit-fence', True
    return None, None, False


def refs_in(node):
    """All Name identifiers referenced within a node (loads + stores + annotations)."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            pass  # root captured via the Name node
    return out


def target_names(node):
    out = set()
    if isinstance(node, ast.Assign):
        for t in node.targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    out.add(n.id)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        for n in ast.walk(node.target):
            if isinstance(n, ast.Name):
                out.add(n.id)
    return out


def is_main_block(node):
    if not isinstance(node, ast.If):
        return False
    t = node.test
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
            and t.left.id == '__name__')


def calls_entry(node, entry):
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == entry:
            return True
    return False


def prune(body, entry):
    """Prune module to entry def + transitively referenced helpers/imports/constants."""
    tree = ast.parse(body)
    stmts = list(tree.body)

    # classify top-level statements
    entry_idx = None
    providers = []  # (idx, binds:set, node, kind)
    for i, st in enumerate(stmts):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) and st.name == entry:
            entry_idx = i  # last one wins
    if entry_idx is None:
        raise ValueError('entry def not found at top level')

    for i, st in enumerate(stmts):
        if i == entry_idx:
            continue
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if st.name == entry:
                continue  # earlier duplicate of entry: drop
            providers.append((i, {st.name}, st, 'def'))
        elif isinstance(st, ast.Import):
            binds = {(a.asname or a.name.split('.')[0]) for a in st.names}
            providers.append((i, binds, st, 'import'))
        elif isinstance(st, ast.ImportFrom):
            if any(a.name == '*' for a in st.names):
                providers.append((i, {'*'}, st, 'import-star'))
            else:
                binds = {(a.asname or a.name) for a in st.names}
                providers.append((i, binds, st, 'import'))
        elif isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            providers.append((i, target_names(st), st, 'const'))
        elif isinstance(st, (ast.For, ast.While, ast.If, ast.With, ast.Try)):
            if is_main_block(st) or calls_entry(st, entry) or isinstance(st, ast.If) and False:
                continue  # example/__main__ block
            binds = set()
            for n in ast.walk(st):
                if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    binds |= target_names(n)
                elif isinstance(n, ast.For) and isinstance(n.target, ast.Name):
                    binds.add(n.target.id)
            providers.append((i, binds, st, 'precompute'))
        # Expr / Assert / everything else: stripped example statements

    keep = {entry_idx}
    needed = refs_in(stmts[entry_idx])
    changed = True
    while changed:
        changed = False
        for i, binds, st, kind in providers:
            if i in keep:
                continue
            if kind == 'import-star' or (binds & needed):
                keep.add(i)
                needed |= refs_in(st)
                changed = True

    kept = [stmts[i] for i in sorted(keep)]
    mod = ast.Module(body=kept, type_ignores=[])
    return ast.unparse(mod)


def main():
    cand = json.load(open(f'{META}/_h_work/cand_data.json'))
    entry = {'HumanEval/36': 'fizz_buzz', 'HumanEval/83': 'starts_one_ends',
             'HumanEval/138': 'is_equal_to_sum_even', 'HumanEval/39': 'prime_fib',
             'HumanEval/116': 'sort_array', 'HumanEval/145': 'order_by_points'}
    out = {}
    for key, v in cand.items():
        task = key.split('|')[0]
        ep = entry[task]
        body, rung, parseable = choose_body(v['raw'], ep)
        rec = {'kind': v['kind'], 'rung': rung, 'parseable': parseable}
        if body is None:
            rec['status'] = 'unverifiable'
        elif not parseable:
            rec['status'] = 'syntax-error'
            rec['body'] = body
        else:
            try:
                rec['shape'] = prune(body, ep)
                rec['status'] = 'ok'
            except SyntaxError:
                rec['status'] = 'syntax-error'
                rec['body'] = body
        out[key] = rec
    json.dump(out, open(f'{META}/_h_work/rebuilt.json', 'w'), indent=1)
    for k, r in out.items():
        print('#' * 20, k, r['kind'], r['rung'], r['status'])
        print(r.get('shape', r.get('body', ''))[:900])
        print()


if __name__ == '__main__':
    main()
