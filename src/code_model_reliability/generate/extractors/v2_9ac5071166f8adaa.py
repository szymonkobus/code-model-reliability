"""The current extractor version (stamp v2@9ac5071166f8adaa): one pure function from a model's raw reply to the
program the judge runs.

    extract(raw_reply, entry_point) -> judged code (str)

The wave 2 attempts were landed under this version (the earlier versions, which most wave 1 verdict files carry,
sit beside it; ``generate.extract.PUBLISHED_STAMPS`` lists what each added). The judge harness's own sanitizer,
which the generation path applies as it writes samples,
is kept reachable as ``harness_sanitize`` for comparison; it searches the longest span of lines that parses and
drops generator functions, and the attempts were re-extracted from their raw replies with this function before
judging. Reads a reply and an entry-point name; writes nothing.

Rules:
 1. Read the answer part only: <think>...</think> spans are removed; code inside them is never the answer.
 2. Split the reply at its code fences (any tag; a reply that starts inside a fence; a fence left open by a
    cut-off; a search/replace diff yields its replace side; a reply without fences is one block).
 3. Parse each block with statement-level repair: on a syntax error the broken top-level statement and everything
    after it are dropped, complete functions before it are kept. The longest-parseable-span search is never used.
 4. The answer block is the LAST block that binds the required name at module level (def, assignment, or a def
    inside if/try/with). If none does, the last block with any function definition (the judge then fails it on the
    name, which is the model's own fault).
 5. Earlier blocks that define names the answer block uses (helpers, imports, constants) are added in front.
 6. Keep the program, drop demonstrations: imports, functions, classes and assignments stay, and so does any module-level
    statement that builds or changes a name the required function reaches (a loop filling a table, an if/try that binds
    a value, a `table.append(...)` call) and any set-up call on an imported module (`sys.setrecursionlimit(...)`); prints,
    asserts, example calls of the module's own functions, bare expressions and the __main__ guard go. Functions without
    a return, decorated functions and generators are kept. A function or class defined twice keeps only its LAST
    definition (the model's settled version, and what Python would run).
 7. Keep what the required name can reach through its free names (scope-aware: a demo assignment that only shares a
    parameter's name is not a dependency), plus every import, so unrelated leftover code cannot fail the module at
    import time.
 8. Never repair the model's work: no renaming, no unwrapping string-wrapped code, no supplying the prompt's imports.

Output is the model's own source text for each kept top-level statement (decorators included, inline comments
kept), joined by blank lines. When nothing parses anywhere, the answer part's last code-looking block is returned
as written (it will fail to compile in the judge, which is the correct verdict for an answer without valid code).

Pure: no I/O, no randomness, standard library only (ast and re). A version is named by a stamp, ``v2@<sha16>``,
the first sixteen hex digits of the sha256 of the extractor file's bytes as it was run; this file's documentation
was rewritten for a reader, so its byte stamp differs from the published stamps while its logic is the same, which
``logic_sha256`` checks: the hash of the module's syntax tree with comments and docstrings removed. The reachability
rule (keep what the required name reaches) is the harness sanitizer's, re-done on the standard-library syntax tree
with the collection rules above.
"""
import ast
import builtins
import hashlib
import re
import sys

sys.setrecursionlimit(20000)

VERSION = "v2"


def version_stamp():
    """The byte stamp of this file: ``v2@`` and the first sixteen hex digits of its sha256."""
    with open(__file__, "rb") as f:
        return f"{VERSION}@{hashlib.sha256(f.read()).hexdigest()[:16]}"


BUILTINS = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "self", "cls"}
NONCODE_TAGS = {"text", "txt", "bash", "sh", "shell", "console", "output", "json", "yaml", "markdown", "md", "diff",
                "plaintext", "xml", "html", "css", "js", "javascript", "c", "cpp", "java", "go", "rust", "sql"}
FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*([\w+#.-]*)[^\n]*$")
# a fence OPENER glued to prose on the same line ("Add tests.```python", "</thinking>```python"): the marker carries a
# language tag that ends the line, and the text before it is prose (not blank, not a block-quote prefix, not a comment,
# no quote characters). Split onto its own line so the fence is read. A bare marker glued to text (a
# closer after the last code line, a stray marker after a docstring, a marker inside a docstring's LaTeX) is left alone.
GLUED_FENCE = re.compile(r"^(?P<pre>[^\n]*?\S)[ \t]*(?P<fence>(?:`{3,}|~{3,})[ \t]*[A-Za-z0-9+#.-]+)[ \t]*$", re.M)   # an OPENER: the marker carries an ASCII language tag


def split_glued_fences(text):
    # Only prose is split away from a marker. A comment line (pseudo-code fences inside code), a line holding a string
    # literal or docstring quotes (a stray marker after a docstring's closing quotes), a block-quote prefix, or a second
    # marker on the line leave the line as it is: the reply keeps its reading.
    def _split(m):
        pre = m.group("pre")
        if re.fullmatch(r"[ \t>]*", pre) or "`" in pre or "~" in pre:
            return m.group(0)
        if pre.lstrip().startswith("#") or '"' in pre or "'''" in pre or re.search(r"[=(\[{,:]\s*'", pre):
            return m.group(0)
        return pre + "\n" + m.group("fence")
    return GLUED_FENCE.sub(_split, text)
THINK_OPEN = re.compile(r"<think>", re.I)
THINK_CLOSE = re.compile(r"</think>", re.I)
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
ANCHOR_RE = re.compile(r"^(def |class |import |from \S+ import |@|async def )", re.M)
DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
COMPOUND = (ast.If, ast.Try, ast.With, ast.For, ast.While)
try:  # 3.11+
    COMPOUND = COMPOUND + (ast.TryStar,)
except AttributeError:
    pass


# --------------------------------------------------------------------------- 1. answer part
def strip_think(text):
    """Remove CLOSED <think>...</think> spans (a thinking channel the model closed before answering). An unclosed
    <think> is left in place as text: models without a thinking channel write a literal "<think>" preamble and then
    their answer, and a reply cut off by the token limit never closes its tag; swallowing the rest would turn the
    answer that follows into nothing (the pinned sanitizer kept that code). The tag itself is prose to the parser."""
    out, pos = [], 0
    while True:
        m = THINK_OPEN.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        c = THINK_CLOSE.search(text, m.end())
        if not c:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        pos = c.end()
    ans = "".join(out)
    return THINK_CLOSE.sub("", ans)  # a stray closing tag (thinking stored separately) is dropped


# --------------------------------------------------------------------------- 2. blocks
def _looks_like_code(s):
    return bool(re.search(r"^(def |class |import |from \S+ import |@|async def |\w+\s*=\s*lambda\b)", s, re.M))


def fenced_blocks(text):
    """List of (tag, code, closed). Handles the prefilled-fence case (the reply begins as code and its first fence
    line is a bare closer), a tagged fence opened while inside a block (the model forgot to close), an unclosed
    final block (cut-off), and the search/replace diff format (replace sides become blocks)."""
    if "<<<<<<< SEARCH" in text:
        # Both sides of every hunk become blocks, in order: in a real diff the replace side is the later block and wins
        # when it binds the entry point; a model that puts its code on the search side and tests on the replace side
        # (a habit of some models) keeps its code. Any '>>>>>>> ...' marker closes a hunk; a bare '=======' line separates sides.
        reps = []
        for m in re.finditer(r"<<<<<<< SEARCH(?:/REPLACE)?[^\n]*\n(.*?)(?=<<<<<<< SEARCH|\Z)", text, re.S):
            parts = re.split(r"(?m)^>>>>>>> [^\n]*$", m.group(1), 1)
            body, closed = parts[0], len(parts) > 1
            for side in re.split(r"(?m)^=======[ \t]*$", body, 1):
                side = side.strip("\n")
                if side.strip() and side.strip() != "=======":
                    reps.append(("python", side, closed))
        if reps:
            return reps
    lines = text.split("\n")
    blocks, cur, tag, inside, seen_fence = [], [], None, False, False
    for ln in lines:
        m = FENCE_LINE.match(ln)
        if m:
            t = m.group(2)
            if not inside:
                if not seen_fence and _looks_like_code("\n".join(cur)):
                    blocks.append(("python", "\n".join(cur), True))  # code before the first fence line
                    if t == "":
                        cur, tag, inside, seen_fence = [], None, False, True
                        continue
                inside, tag, cur, seen_fence = True, t, [], True
            else:
                if t:  # tagged fence while inside: close the current block, open a new one
                    if "\n".join(cur).strip():
                        blocks.append((tag, "\n".join(cur), False))
                    inside, tag, cur = True, t, []
                else:
                    blocks.append((tag, "\n".join(cur), True))
                    inside, tag, cur = False, None, []
            continue
        cur.append(ln)
    if inside:
        blocks.append((tag, "\n".join(cur), False))
    return blocks


# --------------------------------------------------------------------------- 3. parsing with repair
def parse_src(code):
    """(tree, source_that_parsed, repaired). Repair: on a SyntaxError at line L drop the enclosing top-level
    statement (decorators included) and everything after it, retry (<= 8 rounds); a prefix that ends in a complete
    function is kept when the error is inside trailing junk."""
    if code is None:
        return None, None, False
    try:
        return ast.parse(code), code, False
    except (SyntaxError, ValueError):
        pass
    lines = code.split("\n")
    ind = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    if ind and min(ind) > 0:
        d = min(ind)
        lines = [l[d:] if len(l) >= d else l for l in lines]
    for _ in range(8):
        src = "\n".join(lines)
        try:
            return ast.parse(src), src, True
        except SyntaxError as e:
            idx = min(max((e.lineno or len(lines)) - 1, 0), len(lines) - 1)
            S = idx
            while S > 0 and (not lines[S].strip() or lines[S][0].isspace()):
                S -= 1
            while S > 0 and lines[S - 1].lstrip().startswith("@"):
                S -= 1
            if idx > S:
                for cut in range(idx, max(S, idx - 60), -1):
                    pre = "\n".join(lines[:cut])
                    try:
                        t = ast.parse(pre)
                    except (SyntaxError, ValueError):
                        continue
                    last = t.body[-1] if t.body else None
                    if isinstance(last, (ast.FunctionDef, ast.AsyncFunctionDef)) and last.body and \
                            any(isinstance(b, (ast.Return, ast.Raise)) for b in last.body):
                        return t, pre, True
                    break
            if S <= 0:
                return None, None, False
            lines = lines[:S]
        except ValueError:
            return None, None, False
    return None, None, False


def segment_parse(text):
    """Split at column-0 anchors (def/class/import/@) and keep the segments that parse on their own."""
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if ANCHOR_RE.match(l)]
    if not starts:
        return None, None
    # a decorator line opens a segment that runs through the def/class it decorates (and any decorators stacked below
    # it); cutting there would leave a decorator-only segment that cannot parse and a def without its decorator
    merged, dec_open = [], False
    for i in starts:
        if dec_open and re.match(r"^(def |class |async def |@)", lines[i]):
            dec_open = lines[i].startswith("@")
            continue
        merged.append(i)
        dec_open = lines[i].startswith("@")
    starts = merged
    if starts[0] != 0:
        starts = [0] + starts
    segs = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        t, s, _ = parse_src("\n".join(lines[a:b]))
        if t is not None and t.body:
            segs.append(s.rstrip())
    while segs:
        code = "\n".join(segs)
        try:
            return ast.parse(code), code
        except (SyntaxError, ValueError):
            segs.pop()
    return None, None


def parse_block(code, entry):
    """Best parse of one block: whole-block repair first, segment parse when that lost the entry or definitions."""
    tree, src, repaired = parse_src(code)
    if tree is None or repaired:
        t2, s2 = segment_parse(code)
        if t2 is not None and (tree is None or _better(t2, tree, entry)):
            tree, src = t2, s2
    return tree, src


def _better(t2, t1, entry):
    k1, k2 = entry_kind(t1, entry), entry_kind(t2, entry)
    if k2 in ("def", "assign", "compound") and k1 not in ("def", "assign", "compound"):
        return True
    return sum(len(v) for v in top_defs(t2).values()) > sum(len(v) for v in top_defs(t1).values())


# --------------------------------------------------------------------------- names
def _target_names(t):
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        r = []
        for e in t.elts:
            r += _target_names(e)
        return r
    return []


def bound_names(node):
    """Names a top-level statement binds at module level (compound statements: everything they define inside)."""
    out = []
    if isinstance(node, DEF_TYPES):
        out.append(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            out += _target_names(t)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        out += _target_names(node.target)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for a in node.names:
            out.append((a.asname or a.name).split(".")[0])
    elif isinstance(node, COMPOUND):
        for m in ast.walk(node):
            if isinstance(m, DEF_TYPES):
                out.append(m.name)
            elif isinstance(m, ast.Assign):
                for t in m.targets:
                    out += _target_names(t)
            elif isinstance(m, (ast.Import, ast.ImportFrom)):
                for a in m.names:
                    out.append((a.asname or a.name).split(".")[0])
    return out


def top_defs(tree):
    out = {}
    if tree is None:
        return out
    for n in tree.body:
        for nm in bound_names(n):
            if not isinstance(n, COMPOUND):
                out.setdefault(nm, []).append(n)
    return out


CALLABLE_VALUES = (ast.Lambda, ast.Name, ast.Attribute, ast.Call, ast.Subscript, ast.IfExp)


def _binds_callable(node, entry):
    """Does this assignment bind `entry` to something that can be a function (a lambda, an alias, a call such as a
    decorator applied by hand, a lookup)? `count = 0` in a loop snippet binds the name but cannot be the entry point;
    taking it as the definition would judge the snippet instead of the function the model wrote in an earlier block."""
    if isinstance(node, (ast.Assign, ast.AnnAssign)) and entry in bound_names(node):
        return node.value is not None and isinstance(node.value, CALLABLE_VALUES)
    return False


def _compound_binds_entry(node, entry):
    for m in ast.walk(node):
        if isinstance(m, DEF_TYPES) and m.name == entry:
            return True
        if isinstance(m, (ast.Import, ast.ImportFrom)) and entry in bound_names(m):
            return True
        if _binds_callable(m, entry):
            return True
    return False


def entry_kind(tree, entry):
    """'def' | 'assign' | 'class' | 'compound' | 'method' | 'nested' | None. An assignment counts only when its value
    can be a function (see _binds_callable)."""
    if tree is None:
        return None
    for n in reversed(tree.body):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == entry:
            return "def"
        if isinstance(n, ast.ClassDef) and n.name == entry:
            return "class"
        if _binds_callable(n, entry):
            return "assign"
    for n in tree.body:
        if isinstance(n, COMPOUND) and _compound_binds_entry(n, entry):
            return "compound"
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == entry:
                    return "method"
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == entry:
            return "nested"
    return None


def free_names(tree):
    """Names loaded anywhere in tree, not bound anywhere in it, not builtins."""
    if tree is None:
        return set()
    bound, loaded = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            (loaded if isinstance(n.ctx, ast.Load) else bound).add(n.id)
        elif isinstance(n, DEF_TYPES):
            bound.add(n.name)
            if not isinstance(n, ast.ClassDef):
                a = n.args
                for p in a.args + a.posonlyargs + a.kwonlyargs:
                    bound.add(p.arg)
                if a.vararg:
                    bound.add(a.vararg.arg)
                if a.kwarg:
                    bound.add(a.kwarg.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, ast.comprehension):
            bound.update(_target_names(n.target))
        elif isinstance(n, ast.Lambda):
            a = n.args
            for p in a.args + a.posonlyargs + a.kwonlyargs:
                bound.add(p.arg)
    return {x for x in loaded - bound if x not in BUILTINS}


def stmt_free_names(node):
    """Names a top-level statement needs from module scope: its free names (loads not bound inside it — parameters,
    locals, comprehension variables and inner definitions are bound), plus names it declares `global`. Attribute
    chains contribute their base name. This is scope-aware, so a demonstration assignment that merely shares a
    parameter's name is not a dependency."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return set()
    free = set(free_names(node))
    for n in ast.walk(node):
        if isinstance(n, ast.Global):
            free.update(n.names)
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        # an assignment's own targets are not dependencies, but its value's loads are (x = f(y) needs f and y);
        # free_names already treats stored names as bound, which is right for the targets
        pass
    return free - set(bound_names(node)) - BUILTINS


# --------------------------------------------------------------------------- 4-7. choose, assemble, collect
DEMO_CALLS = {"print", "pprint", "exit", "quit", "input", "display", "breakpoint", "help"}
# module-level calls on an imported module that configure the run-time and are kept (matched on the final attribute name);
# everything else at module level that calls into a module — doctest.testmod(), unittest.main(), sys.exit(), sys.stdout.write(...),
# os.system(...) — is a demonstration or a harness, not the answer, and is dropped
SETUP_ATTRS = {"setrecursionlimit", "set_int_max_str_digits", "seed", "stack_size", "filterwarnings", "simplefilter",
               "setrlimit", "getcontext", "set_printoptions", "setswitchinterval", "field_size_limit", "set_start_method",
               "disable", "enable", "setlocale"}


def _call_root(call):
    f = call.func
    while isinstance(f, (ast.Attribute, ast.Subscript)):
        f = f.value
    return f.id if isinstance(f, ast.Name) else None


def _is_main_guard(n):
    return isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)


def classify(n, module_defs, imported):
    """What a top-level statement is for the judged module:
    import | def | bind (assignment) | compound (for/while/if/try/with: kept when it feeds a reachable name or holds a
    definition) | mutate (a method call on a module-level name: kept when that name is reachable) | setup (a call on an
    imported module, e.g. sys.setrecursionlimit) | drop (docstrings, prints, asserts, example calls, bare expressions,
    the __main__ guard, pass/raise/del)."""
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        return "import"
    if isinstance(n, DEF_TYPES):
        return "def"
    if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return "bind"
    if isinstance(n, ast.Expr):
        v = n.value
        call = v.value if isinstance(v, ast.Await) else v
        if not isinstance(call, ast.Call):
            return "drop"
        root = _call_root(call)
        if root is None or root in DEMO_CALLS or root in module_defs:
            return "drop"
        if isinstance(call.func, (ast.Attribute, ast.Subscript)):
            if root in imported:
                last = call.func.attr if isinstance(call.func, ast.Attribute) else None
                return "setup" if last in SETUP_ATTRS else "drop"
            return "mutate"
        return "drop"
    if _is_main_guard(n):
        return "drop"
    if isinstance(n, COMPOUND):
        return "compound"
    return "drop"


def affected_names(n):
    """Module-level names a statement binds or changes: assignment targets, loop/with targets, nested definitions,
    subscript/attribute stores (`t[i] = ...`) and method calls (`t.append(...)`) on a module-level name."""
    out = set(bound_names(n))
    if isinstance(n, DEF_TYPES):
        return out
    for m in ast.walk(n):
        if isinstance(m, (ast.Subscript, ast.Attribute)) and isinstance(getattr(m, "ctx", None), (ast.Store, ast.Del)):
            b = m
            while isinstance(b, (ast.Subscript, ast.Attribute)):
                b = b.value
            if isinstance(b, ast.Name):
                out.add(b.id)
        elif isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute):
            b = m.func.value
            while isinstance(b, (ast.Subscript, ast.Attribute)):
                b = b.value
            if isinstance(b, ast.Name):
                out.add(b.id)
        elif isinstance(m, ast.For):
            out.update(_target_names(m.target))
        elif isinstance(m, ast.withitem) and m.optional_vars is not None:
            out.update(_target_names(m.optional_vars))
        elif isinstance(m, ast.AugAssign):
            out.update(_target_names(m.target))
    return out


def _node_lines(n, lines):
    start = n.lineno
    if isinstance(n, DEF_TYPES) and n.decorator_list:
        start = min([start] + [d.lineno for d in n.decorator_list])
    return "\n".join(lines[start - 1:n.end_lineno]).rstrip()


def collect(src, entry):
    """Rule 6 + 7 over one parsed source: the program the required name reaches (definitions, the statements that build
    or change the names it uses, set-up calls on imported modules) and every import; demonstrations dropped."""
    tree, src2, _ = parse_src(src)
    if tree is None:
        return None
    lines = src2.split("\n")
    module_defs = {n.name for n in tree.body if isinstance(n, DEF_TYPES)}
    imported = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                imported.add((a.asname or a.name).split(".")[0])
    kinds = [(n, classify(n, module_defs, imported)) for n in tree.body]
    stmts = [n for n, k in kinds if k != "drop"]
    kind_of = {id(n): k for n, k in kinds}
    if not stmts:
        return ""
    binds = {}
    for i, n in enumerate(stmts):
        for nm in affected_names(n):
            binds.setdefault(nm, []).append(i)
    keep = {i for i, n in enumerate(stmts) if kind_of[id(n)] in ("import", "setup")}
    queue = list(binds.get(entry, []))
    seen = set(queue)
    while queue:
        i = queue.pop()
        keep.add(i)
        for nm in stmt_free_names(stmts[i]):
            for j in binds.get(nm, []):
                if j not in seen:
                    seen.add(j)
                    queue.append(j)
    # rule 6: a name defined twice keeps its LAST definition (the model's settled version; what Python would run);
    # earlier drafts of the same function or class are dropped, assignments are left as they are
    last_def = {}
    for i in sorted(keep):
        if isinstance(stmts[i], DEF_TYPES):
            last_def[stmts[i].name] = i
    keep = {i for i in keep if not isinstance(stmts[i], DEF_TYPES) or last_def[stmts[i].name] == i}
    return "\n\n".join(_node_lines(stmts[i], lines) for i in sorted(keep))


def _looks_cut(code, repaired):
    """An unclosed block whose last line sits inside a body (indented) and is not a whole statement: the reply was cut
    off (token limit) inside a definition. A complete unclosed block ends with a whole statement ('    return x')."""
    lines = [l for l in code.split("\n") if l.strip()]
    if not lines or not re.match(r"[ \t]", lines[-1]):
        return False
    if repaired:
        return True
    try:
        t = ast.parse(lines[-1].strip())
    except (SyntaxError, ValueError):
        return True
    if not t.body:
        return True  # a comment line
    st = t.body[0]
    return isinstance(st, ast.Expr) and isinstance(st.value, (ast.Name, ast.Attribute))  # 'retur', 'self.x'


TERMINAL_STMTS = (ast.Return, ast.Raise, ast.Pass, ast.Break, ast.Continue)


def _cut_on_line_boundary(src, code, entry):
    """An UNCLOSED final block whose last line is a whole statement can still be a reply cut off at
    the token limit on a line boundary. It is read as cut when (a) its last line sits inside a body (indented), (b) that line
    is not a natural ending (return / raise / pass / break / continue / yield), and (c) the definition it sits in belongs to
    the program the entry point keeps (collect), i.e. the cut damaged the judged program and not a trailing helper or demo.
    A block that ends with a whole 'return x' is a complete block whose closing fence the model forgot (unchanged)."""
    lines = [l for l in code.split("\n") if l.strip()]
    if not lines or not re.match(r"[ \t]", lines[-1]):
        return False
    try:
        t = ast.parse(lines[-1].strip())
    except (SyntaxError, ValueError):
        return False          # not a whole statement: _looks_cut already answers
    if not t.body or isinstance(t.body[0], TERMINAL_STMTS):
        return False
    if isinstance(t.body[0], ast.Expr) and isinstance(t.body[0].value, (ast.Yield, ast.YieldFrom)):
        return False
    kept = collect(src, entry)
    if not kept or not kept.strip():
        return False
    kl = [l for l in kept.split("\n") if l.strip()]
    return kl[-1].strip() == lines[-1].strip()


def _code_blocks(answer, entry):
    blocks = fenced_blocks(answer)
    py = []
    for i, (tag, code, closed) in enumerate(blocks):
        tl = (tag or "").lower()
        tree, src = parse_block(code, entry)
        if tree is None:
            continue
        defs = top_defs(tree)
        if tl in NONCODE_TAGS and not any(isinstance(n, DEF_TYPES) for ns in defs.values() for n in ns):
            continue
        py.append({"idx": i, "code": src, "tree": tree, "defs": defs, "kind": entry_kind(tree, entry),
                   "cut": (not closed) and (_looks_cut(code, src.strip() != code.strip()) or _cut_on_line_boundary(src, code, entry))})
    return blocks, py


def longest_parseable_prefix(code, max_tries=600):
    """The longest line-prefix of code (from its first def/class/import/@ line) that parses and binds something: what a
    cut-off or half-broken function leaves the judge. The pinned sanitizer judged this prefix; keeping that reading for
    code that binds the entry point no other way means the corrected extractor cannot turn those verdicts into
    SyntaxErrors (the truncated body is judged as before, not the raw text)."""
    lines = code.split("\n")
    start = next((i for i, l in enumerate(lines) if ANCHOR_RE.match(l)), 0)
    if start:
        try:
            ast.parse("\n".join(lines[:start]))
        except SyntaxError as e:
            if "unterminated triple-quoted" in (e.msg or ""):
                return None, None  # the first code-looking line sits inside a string literal: the model quoted its code
        except ValueError:
            pass
    lines = lines[start:]
    n = len(lines)
    step = max(1, -(-n // max_tries))
    for k in range(n, 0, -step):
        src = "\n".join(lines[:k]).rstrip()
        try:
            t = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        if t.body:
            return t, src
    return None, None


def _strip_edge_fences(lines):
    """The lines without fence marker lines (and blank lines) at the start and end of the reply."""
    i, j = 0, len(lines)
    while i < j and (not lines[i].strip() or FENCE_LINE.match(lines[i])):
        i += 1
    while j > i and (not lines[j - 1].strip() or FENCE_LINE.match(lines[j - 1])):
        j -= 1
    return lines[i:j]


def locate(answer, entry):
    """(program_source or None, how, blocks, py_blocks)."""
    # 0. a reply that parses whole IS the program: its fence lines, if any, sit inside string literals (a docstring
    #    quoting an example), so splitting it at fences would cut the code
    try:
        t0 = ast.parse(answer)
    except (SyntaxError, ValueError):
        t0 = None
    if t0 is not None and entry_kind(t0, entry) in ("def", "assign", "compound"):
        return answer.strip("\n"), "whole-reply-parses", [], []
    # 0b. a reply that is code with stray fence LINES (a closing fence left at the end, a fence quoted in a docstring that
    #     the model also closed) parses once the fence lines themselves are removed; if it then binds the entry point it
    #     is the program (removing marker lines cannot create code)
    lines = answer.split("\n")
    if any(FENCE_LINE.match(ln) for ln in lines):
        # first only the marker lines at the reply's ends (a stray closer after the program; a docstring keeps any fence it
        # quotes), then every marker line (a fence quoted in a docstring that the model also closed mid-program)
        for cand, how in ((_strip_edge_fences(lines), "whole-reply-minus-edge-fence-lines"),
                          ([ln for ln in lines if not FENCE_LINE.match(ln)], "whole-reply-minus-fence-lines")):
            stripped = "\n".join(cand)
            try:
                t1 = ast.parse(stripped)
            except (SyntaxError, ValueError):
                continue
            if entry_kind(t1, entry) in ("def", "assign", "compound"):
                return stripped.strip("\n"), how, [], []
    blocks, py = _code_blocks(answer, entry)
    chosen, how = None, None
    ep = [b for b in py if b["kind"] in ("def", "assign", "compound")]
    if ep:
        chosen, how = ep[-1], "last-block-defining-entry"
        if chosen.get("cut"):
            # the last block was cut off inside a definition (a repeat or rewrite the token limit ended): an earlier
            # complete block binding the entry point is the model's settled answer
            whole = [b for b in ep if not b.get("cut")]
            if whole:
                chosen, how = whole[-1], "last-complete-block-defining-entry"
    if chosen is None and len(blocks) >= 2:
        # a fence line inside a string literal closed the block early: the span from the first fence line to the last
        # is the program when it parses and binds the entry point
        lines = answer.split("\n")
        fl = [i for i, ln in enumerate(lines) if FENCE_LINE.match(ln)]
        if len(fl) >= 2:
            tree, src = parse_block("\n".join(lines[fl[0] + 1:fl[-1]]), entry)
            if tree is not None and entry_kind(tree, entry) in ("def", "assign", "compound"):
                chosen, how = {"idx": -4, "code": src, "tree": tree, "defs": top_defs(tree), "kind": entry_kind(tree, entry)}, "outer-fence-span"
    if chosen is None and not py:
        # no block parses on its own (or the reply has no fences): the reply as one block, repaired at the statement
        tree, src = parse_block(answer, entry)
        if tree is not None and entry_kind(tree, entry) in ("def", "assign", "compound"):
            chosen, how = {"idx": -2, "code": src, "tree": tree, "defs": top_defs(tree), "kind": entry_kind(tree, entry)}, "whole-reply-repaired"
    if chosen is None:
        # cut-off code: the longest parseable prefix of the last code-looking block (or of the reply) that binds the entry
        # point; the pinned sanitizer's reading, kept so that no verdict turns on a syntax error the cut-off caused.
        # Runs BEFORE any block without the entry point is accepted: a reply whose function was cut off must not be
        # judged on its imports or helpers alone.
        cands = [(i, code) for i, (tag, code, _) in enumerate(blocks) if (tag or "").lower() not in NONCODE_TAGS and code.strip()] or [(-1, answer)]
        for i, code in reversed(cands):
            tree, src = longest_parseable_prefix(code)
            if tree is not None and entry_kind(tree, entry) in ("def", "assign", "compound"):
                chosen, how = {"idx": i, "code": src, "tree": tree, "defs": top_defs(tree), "kind": entry_kind(tree, entry)}, "longest-parseable-prefix"
                break
    if chosen is None and py:
        withdef = [b for b in py if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for ns in b["defs"].values() for n in ns)]
        if withdef:
            chosen, how = withdef[-1], "last-block-with-a-function"
    if chosen is None and not blocks:
        tree, src = parse_block(answer, entry)
        if tree is not None and any(isinstance(n, DEF_TYPES) for ns in top_defs(tree).values() for n in ns):
            chosen, how = {"idx": -1, "code": src, "tree": tree, "defs": top_defs(tree), "kind": entry_kind(tree, entry)}, "whole-reply-unfenced"
    if chosen is None:
        return None, "no-code", blocks, py
    parts, fn = [], free_names(chosen["tree"])
    if fn:
        for b in py:
            if b is chosen or b["idx"] >= chosen["idx"]:
                continue
            if fn & set(b["defs"].keys()):
                parts.append(b["code"])
    parts.append(chosen["code"])
    return "\n\n".join(parts), how, blocks, py


def _fallback_text(answer, blocks):
    """Nothing parses: return the last code-looking block as written (fence lines removed), else the answer part."""
    for tag, code, _closed in reversed(blocks):
        if (tag or "").lower() not in NONCODE_TAGS and code.strip():
            return code.strip("\n")
    return answer.strip("\n")


def extract(raw, entry):
    """The judged code for one reply. Pure function of (raw, entry)."""
    raw = ANSI_RE.sub("", raw or "")
    answer = split_glued_fences(strip_think(raw))
    program, how, blocks, py = locate(answer, entry)
    if program is None:
        return _fallback_text(answer, blocks)
    out = collect(program, entry)
    if out is None:  # the assembled program does not parse (should not happen: every part parsed); keep the chosen block
        out = collect(py[-1]["code"], entry) if py else None
    if out is None:
        return _fallback_text(answer, blocks)
    return out


def explain(raw, entry):
    """Diagnostic twin of extract(): the same result plus how it was chosen."""
    raw = ANSI_RE.sub("", raw or "")
    answer = split_glued_fences(strip_think(raw))
    program, how, blocks, py = locate(answer, entry)
    return {"how": how, "n_blocks": len(blocks), "n_code_blocks": len(py), "code": extract(raw, entry)}


if __name__ == "__main__":
    import json
    data = sys.stdin.read()
    try:
        row = json.loads(data)
        print(extract(row["raw"], row["entry_point"]))
    except json.JSONDecodeError:
        print(extract(data, sys.argv[1] if len(sys.argv) > 1 else ""))
