import ast, builtins, gzip, json, sys
from collections import Counter
BUILTINS = set(dir(builtins))

def bound_and_loaded(code):
    try: tree = ast.parse(code)
    except SyntaxError: return None, None
    bound, loaded = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (loaded if isinstance(node.ctx, ast.Load) else bound).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split('.')[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound, loaded

def preamble_bindings(src):
    """Module-level names the preamble binds when exec'd (imports incl.
    aliases, star-imports expanded by actually importing the module)."""
    tree = ast.parse(src)
    b = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for al in node.names: b.add((al.asname or al.name).split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for al in node.names:
                if al.name == '*':
                    mod = __import__(node.module, fromlist=['*'])
                    names = getattr(mod, '__all__', None) or [n for n in dir(mod) if not n.startswith('_')]
                    b.update(names)
                else:
                    b.add(al.asname or al.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in ast.walk(node):
                if isinstance(t, ast.Name) and not isinstance(t.ctx, ast.Load): b.add(t.id)
    return b

pre = preamble_bindings(open(sys.argv[1]).read())
print('preamble binds', len(pre), 'names; sample:', sorted(pre)[:12])
affected = {}
names = Counter()
for line in gzip.open('runs/fail-reruns/units.jsonl.gz', 'rt'):
    u = json.loads(line)
    bound, loaded = bound_and_loaded(u['code'])
    if bound is None: continue
    hits = (loaded - bound - BUILTINS) & pre
    if hits:
        affected[f"{u['task_id']}|{u['shape']}"] = sorted(hits)
        for h in hits: names[h] += 1
json.dump(affected, open('runs/fail-reruns/preamble_shapes.json', 'w'), indent=0)
print('affected shapes:', len(affected), '| top names:', names.most_common(10))
