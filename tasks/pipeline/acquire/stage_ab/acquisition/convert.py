#!/usr/bin/env python3
"""{task_id, prompt, entry_point, canonical_solution, base_input, plus_input,
   atol}  + provenance/conversion metadata blocks

Honesty: every candidate gets a status — converted / needs-human(reason) /
rejected(reason) — and the reference is executed against every kept test in
a sandboxed subprocess (rlimits + per-test SIGALRM, no network imports
survive the rewrite screen). A candidate converts ONLY if some reference
reproduces the official expected output exactly on all kept tests.

Usage:
  python3 convert.py --in artifacts/candidates_raw.smoke.jsonl \
                     --outdir artifacts/smoke
Offline: no network. Pure stdlib.
"""

import argparse
import ast
import copy
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# house screen constants mirrored (see ../screens.py) — used to warn early,
# never to silently drop candidates
HOUSE_PAYLOAD_LIMIT = 1_000_000
HOUSE_TIMEOUT_S = 1.0
HOUSE_RUNTIME_MARGIN = 10
MIN_TESTS = 5
MIN_DISTINCT_OUTPUTS = 2

PER_TEST_TIMEOUT = 10.0     # generous conversion-time limit (Python-scaled)
MEMORY_LIMIT_MB = 1536   # shared 16GB box: keep reference runs under ~2GB
MAX_REFS_TRIED = 8
OUTPUT_CAP = 4_000_000      # runaway-output guard in the child

BANNED_MODULES = {"socket", "requests", "urllib", "http", "subprocess",
                  "random", "secrets"}
# exit/quit: fine in the conversion sandbox, but the pinned house judge nulls
# builtins.exit, so a reference using exit(print(0)) raises TypeError at
# judge time (audit wave-2, openr1/1770_F) — reject; next reference is tried
BANNED_CALLS = {"open", "exec", "eval", "exit", "quit"}   # `input` handled by rename
ENTRY_POINT = "solve"

# ------------------------------------------------------------ canonical form

CANON_SRC = '''\
def _canon(s):
    lines = [l.rstrip() for l in s.replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\\n".join(lines)
'''
_canon_ns = {}
exec(CANON_SRC, _canon_ns)
canon = _canon_ns["_canon"]

OUTPUT_CONVENTION = (
    "Return the answer exactly as the judge expects it printed: a single "
    "string, lines joined with '\\n', no trailing whitespace on any line "
    "and no trailing newline. The comparison is exact."
)

# ------------------------------------------------- statement sample tests
# CC+ ships the whole Codeforces statement as one text blob with no
# machine-readable examples (n_by_kind.example == 0); the visible set was
# vacuous for those tasks in the pilot. Parse the Examples section's
# Input/Output blocks back out. A mis-parse cannot corrupt a task: the
# extracted pairs join the kept tests, and conversion still requires the
# reference to reproduce every kept expected output byte-exactly.

_EX_HDR_RE = re.compile(r"^[ \t]*Examples?[ \t]*$", re.M)
_NOTE_RE = re.compile(r"^[ \t]*Note[ \t]*$", re.M)
_IO_SPLIT_RE = re.compile(r"^[ \t]*(Input|Output)[ \t]*$", re.M)


def extract_sample_tests(description):
    """Statement blob -> [{'input','output'}] from the Examples section."""
    if not description:
        return []
    m = _EX_HDR_RE.search(description)
    if not m:
        return []
    tail = description[m.end():]
    stop = _NOTE_RE.search(tail)
    if stop:
        tail = tail[:stop.start()]
    parts = _IO_SPLIT_RE.split(tail)
    pairs, cur_in = [], None
    for i in range(1, len(parts) - 1, 2):
        label, block = parts[i], parts[i + 1].strip("\n")
        if label == "Input":
            cur_in = block
        elif label == "Output" and cur_in is not None:
            pairs.append({"input": cur_in, "output": block})
            cur_in = None
    return pairs


def attach_sample_tests(rec):
    """If a record carries no example-kind tests, extract samples from the
    statement and attach them: officials identical to a sample are re-kinded
    'example'; unmatched samples are prepended as new example tests.
    Returns the number of samples found (0 = nothing to do)."""
    samples = extract_sample_tests(rec["statement"].get("description"))
    if not samples:
        return 0
    by_io = {}
    for t in rec["tests"]:
        by_io[(canon(t.get("input") or ""), canon(t.get("output") or ""))] = t
    new = []
    for s in samples:
        key = (canon(s["input"]), canon(s["output"]))
        if key in by_io:
            by_io[key]["kind"] = "example"
        else:
            inp = s["input"]
            if inp and not inp.endswith("\n"):
                inp += "\n"
            new.append({"input": inp, "output": s["output"],
                        "kind": "example"})
    rec["tests"] = new + rec["tests"]
    rec["_examples_in_description"] = True
    return len(samples)


# STRONG = the statement explicitly licenses printing any of several
# outputs; these flag wherever they appear. WEAK = phrases like "multiple
# solutions" that also occur innocently (notes explaining that several
# optimal CONFIGURATIONS exist while the required output is a unique
# count — measured FP: openr1/1779_G); weak patterns skip Note/Examples
# text and yield to an adjacent tie-break clause ("...print the
# lexicographically smallest"), which restores a unique oracle.
_ANY_STRONG = [
    r"\b(?:print|output)\s+any\b(?!\s*(?:extra|additional|other|whitespace|space|leading|trailing))",
    r"\bany of them\b",
    r"\bany one of them\b",
    r"\bany of (?:these|those)\b",
    r"\bany of the (?:possible|valid|correct)?\s*(?:answers|solutions)\b",
    r"\bany such (?:answer|solution|sequence|array|string|arrangement|permutation|order(?:ing)?|pair|set|tree|graph|way)\b",
    r"\bany valid (?:answer|solution|sequence|array|string|arrangement|permutation|order(?:ing)?|pair|set|construction)\b",
    r"\bany (?:correct|possible) (?:answer|solution)\b",
    r"\b(?:answer|solution)s?\s+(?:is|are)\s+not\s+(?:necessarily\s+)?unique\b",
    r"\b(?:print|output)[^.\n]{0,80}\bin any order\b",
    # implicit-construction class (audit wave-2, ccplus/1469_D): the output
    # is a construction/sequence and the statement WAIVES minimality — any
    # valid construction is accepted by the source checker, so an exact
    # single-reference oracle is unsound even with no lexical "print any".
    r"\b(?:don.?t|do not|need not|not (?:have|need|required|obliged)) (?:have )?to minimi[sz]e\b",
    r"\bnot necessarily (?:minimal|minimum|optimal|shortest|the smallest)\b",
]
_ANY_CASE = [
    r"\bin any (?:case|register)\s*\(?(?:upper or lower|lower or upper)?\)?",
    r"\bcase[- ]insensitive",
    r"\b(?:lower|upper)\s?-?case\s+or\s+(?:lower|upper)\s?-?case\b",
    r"\b(?:upper|lower)\s+or\s+(?:upper|lower)\s?-?case\b",
]
_ANY_WEAK = [
    r"\bif (?:there (?:are|exist)|it has)\s+(?:multiple|several|more than one)\b",
    r"\b(?:multiple|several)\s+(?:possible\s+)?(?:answers|solutions)\b",
]
_ANY_STRONG_RES = [re.compile(p, re.I) for p in _ANY_STRONG]
# "following code:" + blank line + a prose sentence (no code-ish tokens on
# the next line) => the block itself was dropped at import
_DROPPED_BLOCK_RE = re.compile(
    r"(?:following|below|this) (?:code|pseudo-?code|algorithm|procedure|"
    r"program|function)[^.\n]{0,60}:[ \t]*\n[ \t]*\n[ \t]*"
    r"(?=[A-Z][^\n=(){}\[\];]{0,200}\.)", re.I)
_ANY_WEAK_RES = [re.compile(p, re.I) for p in _ANY_WEAK]
_ANY_CASE_RES = [re.compile(p, re.I) for p in _ANY_CASE]

_WORD_TOK_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def case_pin_text(expected):
    words = []
    for e in expected:
        for w in _WORD_TOK_RE.findall(e):
            if w not in words:
                words.append(w)
        if len(words) > 12:
            break
    if not words:
        return ""
    shown = ", ".join(words[:8])
    return ("The statement may permit any letter case, but this judge "
            "compares strings EXACTLY — print words in exactly this "
            "casing: %s." % shown)
_TIEBREAK_RE = re.compile(
    r"smallest|largest|lexicograph|minim(?:um|al|ize)|maxim(?:um|al|ize)|"
    r"earliest|latest|shortest|longest|unique", re.I)


def _strip_note_examples(description):
    """Cut the statement blob at its Examples/Note section (CC+ embeds the
    whole Codeforces page in `description`)."""
    if not description:
        return ""
    cut = len(description)
    for rx in (_EX_HDR_RE, _NOTE_RE):
        m = rx.search(description)
        if m:
            cut = min(cut, m.start())
    return description[:cut]


def _ctx(text, m):
    lo = max(0, m.start() - 30)
    return "...%s..." % text[lo:m.end() + 30].replace("\n", " ").strip()


def detect_any_of_them(rec):
    """Return ("multi", ctx) for true multi-answer statements (route out),
    ("case", ctx) for letter-case licensing only (pin casing in prompt),
    or None."""
    st = rec["statement"]
    full = "\n".join(filter(None, [st.get("description"),
                                   st.get("output_format"),
                                   st.get("note")]))
    for rx in _ANY_STRONG_RES:
        m = rx.search(full)
        if m:
            return "multi", _ctx(full, m)
    main = "\n".join(filter(None, [_strip_note_examples(st.get("description")),
                                   st.get("output_format")]))
    for rx in _ANY_WEAK_RES:
        m = rx.search(main)
        if m and not _TIEBREAK_RE.search(main[m.end():m.end() + 120]):
            return "multi", _ctx(main, m)
    for rx in _ANY_CASE_RES:
        m = rx.search(full)
        if m:
            return "case", _ctx(full, m)
    return None


# ------------------------------------------------------ output-layout pin
# Pilot disposition ccplus/1498_F: the statement did not pin one-line vs
# per-line integer output and the exact judge fails the other layout.
# Derive the layout mechanically from the official expected outputs of the
# kept tests and pin it in the prompt (prompt-time boundary rule).


def layout_pin(expected):
    """Observed-layout sentence appended to the output convention block."""
    if not expected:
        return ""
    lcs = [(e.count("\n") + 1) if e else 0 for e in expected]
    lines = [l for e in expected for l in e.split("\n")]
    spaced = [l for l in lines if " " in l.strip()]
    if max(lcs) <= 1:
        pin = ("Output layout (observed on the kept official tests): the "
               "expected output is a single line%s on every kept test; the "
               "Output section decides the line count for each input — "
               "keep exactly the line structure it prescribes."
               % (" with values separated by single spaces"
                  if spaced and all("  " not in l for l in spaced) else ""))
    else:
        if min(lcs) == max(lcs):
            span = "%d lines on every kept official test" % max(lcs)
        else:
            span = ("between %d and %d lines on the kept official tests"
                    % (min(lcs), max(lcs)))
        pin = ("Output layout (observed on the kept official tests): the "
               "expected output spans %s; the Output section decides the "
               "line count for each input. Keep exactly the line structure "
               "the Output section and the examples show — values printed "
               "on one line in the examples stay on one line; values on "
               "separate lines stay on separate lines." % span)
    return pin

# ------------------------------------------------------- reference screening


class RefReject(Exception):
    pass


class _InputRename(ast.NodeTransformer):
    """Uniformly rename the identifier `input` -> `_inp_`.

    Handles both `input()` calls (builtin semantics supplied by a shim) and
    the common `input = sys.stdin.readline` rebinding pattern."""

    def visit_Name(self, node):
        if node.id == "input":
            return ast.copy_location(
                ast.Name(id="_inp_", ctx=node.ctx), node)
        return node


def screen_reference(code):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError) as e:
        raise RefReject("does not parse as py3 (%s)" % type(e).__name__)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise RefReject("uses global/nonlocal (cannot inline into a "
                            "function body)")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in BANNED_MODULES:
                    raise RefReject("imports banned module %s" % a.name)
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in BANNED_MODULES:
                raise RefReject("imports banned module %s" % node.module)
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BANNED_CALLS:
                raise RefReject("calls banned builtin %s()" % f.id)
            if isinstance(f, ast.Attribute) and f.attr == "_exit":
                raise RefReject("calls os._exit (kills the judge process)")
    _reject_lookup_table(tree)
    tree = _InputRename().visit(tree)
    ast.fix_missing_locations(tree)
    return tree


def _reject_lookup_table(tree):
    """A reference that is a table of the graded inputs (audit wave-2,
    openr1/1717_E: `if n==3: print(1) ... elif n==10: print(134)`, no
    algorithm) reproduces every kept test trivially and can never
    regenerate an output — reject it so the next reference is tried.
    Shape: >= 5 if/elif branches comparing to a constant whose bodies only
    print constants, covering >= 80% of all branches, and no loop."""
    n_branches = n_const = 0
    loops = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.ListComp, ast.GeneratorExp,
                             ast.SetComp, ast.DictComp)):
            loops += 1
        if isinstance(node, ast.If):
            n_branches += 1
            t = node.test

            def _is_const_eq(e):
                return (isinstance(e, ast.Compare) and len(e.ops) == 1
                        and isinstance(e.ops[0], ast.Eq)
                        and any(isinstance(x, ast.Constant)
                                for x in (e.left, e.comparators[0])))
            # `n == 3` or `a == 3 and b == 2` (openr1/1644_F)
            const_cmp = _is_const_eq(t) or (
                isinstance(t, ast.BoolOp) and isinstance(t.op, ast.And)
                and all(_is_const_eq(v) for v in t.values))
            body_const = all(
                isinstance(b, ast.Expr) and isinstance(b.value, ast.Call)
                and all(isinstance(a, ast.Constant) for a in b.value.args)
                for b in node.body if not isinstance(b, ast.If))
            if const_cmp and body_const:
                n_const += 1
    if n_const >= 5 and n_const >= 0.8 * n_branches and loops == 0:
        raise RefReject("lookup-table reference (%d constant branches, no "
                        "algorithm) — cannot regenerate outputs" % n_const)


WRAPPER_PRELUDE = '''\
    import io as _io, sys as _sys
    _old_in, _old_out = _sys.stdin, _sys.stdout
    _sys.stdin = _io.StringIO(input_data)
    _sys.stdout = _cap = _io.StringIO()
    def _inp_(prompt=None):
        _l = _sys.stdin.readline()
        if not _l:
            raise EOFError
        return _l.rstrip("\\n")
    try:
'''

WRAPPER_POSTLUDE = '''\
    except SystemExit:
        pass
    finally:
        # References that run main() in a threading.Thread (big-stack
        # recursion idiom) return before the thread prints; join every
        # other thread BEFORE restoring stdout or the capture is empty on
        # any input longer than one scheduler slice (openr1/1709_E, 09-05).
        import threading as _thr
        for _t in _thr.enumerate():
            if _t is not _thr.current_thread() and not _t.daemon:
                _t.join()
        _sys.stdin, _sys.stdout = _old_in, _old_out
    _lines = [_l.rstrip() for _l in _cap.getvalue().replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n")]
    while _lines and _lines[-1] == "":
        _lines.pop()
    return "\\n".join(_lines)
'''


def build_canonical_solution(ref_code):
    """Reference submission -> indented body of solve(). RefReject on
    constructs the wrapper cannot honestly support."""
    tree = screen_reference(ref_code)
    try:
        body_src = ast.unparse(tree)
    except Exception as e:
        raise RefReject("unparse failed (%s)" % type(e).__name__)
    inlined = "".join("        %s\n" % l if l.strip() else "\n"
                      for l in body_src.split("\n"))
    return WRAPPER_PRELUDE + inlined + WRAPPER_POSTLUDE


# ---------------------------------------------------------------- the prompt

def _sanitize_doc(text):
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _rstrip_examples_section(description):
    m = _EX_HDR_RE.search(description or "")
    if not m:
        return description
    head, tail = description[:m.start()], description[m.start():]
    stop = _NOTE_RE.search(tail)
    ex, rest = (tail[:stop.start()], tail[stop.start():]) if stop else (tail, "")
    ex = "\n".join(l.rstrip() for l in ex.split("\n"))
    return head + ex + rest


def build_prompt(rec, layout=""):
    st = rec["statement"]
    desc = st.get("description") or ""
    if rec.get("_examples_in_description"):
        desc = _rstrip_examples_section(desc)
    parts = [desc]
    if st.get("input_format"):
        parts.append("Input\n-----\n" + st["input_format"])
    if st.get("output_format"):
        parts.append("Output\n------\n" + st["output_format"])
    examples = ([] if rec.get("_examples_in_description")
                else [t for t in rec["tests"] if t.get("kind") == "example"])
    if examples:
        # ALL statement examples (audit wave-2: the [:3] cap dropped
        # openr1/1419_F's 4th example — 53 live tasks affected), each line
        # rstripped (1547_E: source test text carried trailing spaces)
        ex_lines = []
        for i, t in enumerate(examples, 1):
            def _clean(x):
                return "\n".join(l.rstrip() for l in
                                 (x or "").strip("\n").split("\n"))
            ex_lines.append("Example %d\ninput:\n%s\noutput:\n%s"
                            % (i, _clean(t["input"]), _clean(t["output"])))
        parts.append("Examples\n--------\n" + "\n\n".join(ex_lines))
    if st.get("note"):
        parts.append("Note\n----\n" + st["note"])
    tl = rec.get("time_limit_s")
    # defensive unit normalization for already-fetched CC+ raws (ms stored
    # as s): no contest time limit exceeds 100 s
    if isinstance(tl, (int, float)) and tl > 100:
        tl = tl / 1000.0
        rec["time_limit_s"] = tl
    limits = ("The reference solves every test within the judged limits; "
              "an efficient algorithm is required (original limit: "
              "%s s for compiled languages, scaled generously for Python)."
              % tl) if tl else ""
    body = "\n\n".join(p.strip() for p in parts if p and p.strip())
    convention = OUTPUT_CONVENTION + (" " + layout if layout else "")
    doc = (
        "%s\n\n"
        "The function receives the problem's entire input as the string "
        "`input_data` (exactly the stdin text a contest submission would "
        "read, lines separated by '\\n').\n%s\n%s"
        % (body, convention, limits)).strip()
    body_ind = _sanitize_doc(doc).replace("\n", "\n    ")
    # blank docstring lines carry no indent-only whitespace
    body_ind = re.sub(r"\n[ \t]+(?=\n)", "\n", body_ind)
    return ('def %s(input_data: str) -> str:\n    """%s\n    """\n'
            % (ENTRY_POINT, body_ind))


# --------------------------------------------------------- sandboxed running

CHILD_SRC = r'''
import json, signal, sys, io, resource, time

spec = json.load(sys.stdin)
try:
    resource.setrlimit(resource.RLIMIT_AS,
                       (spec["mem_bytes"], spec["mem_bytes"]))
except (ValueError, OSError):
    pass

class _T(Exception): pass
def _alarm(s, f): raise _T()
signal.signal(signal.SIGALRM, _alarm)

gl = {"__name__": "__conv__"}
try:
    exec(compile(spec["full_code"], "<task>", "exec"), gl)
    fn = gl[spec["entry_point"]]
except BaseException as e:
    print(json.dumps({"fatal": "%s: %s" % (type(e).__name__, e)}), flush=True)
    sys.exit(0)

for i, args in enumerate(spec["inputs"]):
    t0 = time.perf_counter()
    try:
        signal.setitimer(signal.ITIMER_REAL, spec["timeout"])
        out = fn(*args)
        signal.setitimer(signal.ITIMER_REAL, 0)
        if not isinstance(out, str):
            out = repr(out)
        if len(out) > spec["output_cap"]:
            out = out[:spec["output_cap"]]
        print(json.dumps({"i": i, "ok": True, "out": out,
                          "t": round(time.perf_counter() - t0, 4)}),
              flush=True)
    except BaseException as e:
        signal.setitimer(signal.ITIMER_REAL, 0)
        err = "Timeout" if isinstance(e, _T) else type(e).__name__
        print(json.dumps({"i": i, "ok": False, "err": err,
                          "t": round(time.perf_counter() - t0, 4)}),
              flush=True)
'''


def run_reference(full_code, inputs, timeout=PER_TEST_TIMEOUT):
    """Execute entry point on each input in an isolated subprocess.
    Returns (results-by-index, fatal-or-None)."""
    spec = {"full_code": full_code, "entry_point": ENTRY_POINT,
            "inputs": inputs, "timeout": timeout,
            "mem_bytes": MEMORY_LIMIT_MB * 1024 * 1024,
            "output_cap": OUTPUT_CAP}
    budget = min(600, 30 + timeout * len(inputs) * 1.5)
    import os as _os, signal as _signal, tempfile as _tempfile
    with _tempfile.TemporaryFile(mode="w+", encoding="utf-8",
                                 errors="replace") as outf:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", CHILD_SRC],
            stdin=subprocess.PIPE, stdout=outf, stderr=subprocess.DEVNULL,
            text=True, start_new_session=True)
        try:
            proc.stdin.write(json.dumps(spec))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        deadline = time.monotonic() + budget
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        try:
            _os.killpg(proc.pid, _signal.SIGKILL)   # main (if hung) + children
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()
        outf.flush()
        outf.seek(0)
        out = outf.read()
    res, fatal = {}, None
    for line in out.splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(r, dict):   # stray reference output on the stream
            continue
        if "fatal" in r:
            fatal = r["fatal"]
        else:
            res[r["i"]] = r
    return res, fatal


# ----------------------------------------------------------- per-candidate

def payload_bytes(inputs, outputs):
    return (sum(len(repr(x)) for x in inputs)
            + sum(len(o) for o in outputs))


def select_tests(rec):
    base, plus, dropped = [], [], 0
    total = 0
    seen = set()   # dedup modulo canonical form: open-r1 suites carry
                   # trailing-newline copies of the examples (audit wave-2,
                   # openr1/1693_C, 1408_E) that must not count as tests
    dup = 0
    for t in rec["tests"]:
        inp, out = t.get("input") or "", t.get("output") or ""
        key = (canon(inp), canon(out))
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        sz = len(repr([inp])) + len(out)
        if total + sz > HOUSE_PAYLOAD_LIMIT * 0.9:
            dropped += 1
            continue
        total += sz
        (base if t.get("kind") == "example" else plus).append(
            {"input": inp, "expected": canon(out)})
    rec["_tests_dropped_duplicate"] = dup
    return base, plus, dropped, total


def convert_candidate(rec, timeout):
    """Returns (status, reason, task_or_None, metrics)."""
    metrics = {"refs_available": len(rec.get("reference_candidates") or [])}

    if rec.get("interaction_format"):
        return "rejected", "interactive problem", None, metrics
    if rec.get("input_mode") not in (None, "stdio"):
        return "rejected", "input_mode=%s" % rec.get("input_mode"), None, metrics
    if rec.get("source_dataset", "").startswith("open-r1") and \
            rec.get("has_custom_checker"):
        return ("rejected",
                "custom checker (multi-answer): not an exact oracle",
                None, metrics)

    # Markup-lossy statements (audit wave-2, ccplus/1436_C): CC+ statement
    # text carries "<image>" where the source page had an image, often
    # load-bearing (pseudocode, formulas). The content is unrecoverable, so
    # the prompt may be underspecified in a way no pin fixes; route out.
    # Known over-route: purely illustrative figures are lexically
    # indistinguishable and route out too (accepted; CC+ channel closed,
    # reserves exclude these records).
    st_ = rec["statement"]
    # Dropped code blocks (audit wave-2, openr1/1626_F): a <pre> block was
    # lost at import with NO placeholder — the statement promises code
    # ("You perform the following code with it:") and prose follows. Route
    # out; a placeholder scan cannot see this shape.
    body_ = "\n".join((st_.get(k) or "")
                      for k in ("description", "input_format", "output_format"))
    m_drop = _DROPPED_BLOCK_RE.search(body_)
    metrics["dropped_code_block"] = bool(m_drop)
    if m_drop:
        return ("needs-human", "markup-lossy statement: code/pseudocode block "
                "promised but missing (dropped at import, no placeholder): "
                "...%s..." % body_[max(0, m_drop.start() - 40):m_drop.end() + 40]
                .replace("\n", " ")[:160], None, metrics)
    n_img = sum((st_.get(k) or "").count("<image>")
                for k in ("description", "input_format", "output_format"))
    metrics["image_placeholders"] = n_img
    if n_img:
        return ("needs-human", "markup-lossy statement: %d <image> "
                "placeholder(s), content unrecoverable; prompt may be "
                "underspecified (audit class 2026-09-03)" % n_img,
                None, metrics)

    case_pin = ""
    hit = detect_any_of_them(rec)
    if hit:
        kind, ctx = hit
        metrics["any_of_them"] = ctx
        metrics["any_of_them_kind"] = kind
        if kind == "multi":
            return ("needs-human", "any-of-them statement (multi-answer): "
                    "exact oracle unsound regardless of reference "
                    "agreement; needs checker route. Matched: %s" % ctx[:160],
                    None, metrics)
        case_pin = "licensed"

    if not any(t.get("kind") == "example" for t in rec["tests"]):
        metrics["sample_tests_extracted"] = attach_sample_tests(rec)

    n_crlf = 0
    for t in rec["tests"]:
        inp = t.get("input")
        if inp and "\r" in inp:
            t["input"] = inp.replace("\r\n", "\n")
            n_crlf += 1
    metrics["crlf_normalized_tests"] = n_crlf

    base, plus, dropped, total = select_tests(rec)
    tests = base + plus
    if len(tests) < MIN_TESTS:
        n_dup = rec.get("_tests_dropped_duplicate", 0)
        metrics.update(n_base=len(base), n_plus=len(plus),
                       n_dropped_budget=dropped, payload_bytes=total,
                       tests_dropped_duplicate=n_dup)
        return ("rejected", "only %d distinct tests (%d duplicate%s dropped, "
                "%d over the 1MB house budget)"
                % (len(tests), n_dup, "" if n_dup == 1 else "s", dropped),
                None, metrics)
    promoted = 0
    if not base:
        base, plus = plus[:2], plus[2:]
        promoted = len(base)
        rec["_base_promoted"] = promoted
    if not base or not plus:
        return ("rejected", "empty base_input or plus_input after split "
                "(base %d, plus %d)" % (len(base), len(plus)), None, metrics)
    metrics.update(n_base=len(base), n_plus=len(plus),
                   n_dropped_budget=dropped, payload_bytes=total,
                   base_promoted=promoted)
    if len({t["expected"] for t in tests}) < MIN_DISTINCT_OUTPUTS:
        return ("rejected", "degenerate suite: all expected outputs equal",
                None, metrics)

    refs = rec.get("reference_candidates") or []
    if not refs:
        return ("needs-human", "no Python reference available "
                "(human translation or wider submission search needed)",
                None, metrics)

    cp = case_pin_text([t["expected"] for t in tests]) if case_pin else ""
    pin = (layout_pin([t["expected"] for t in tests]) + " " + cp).strip()
    metrics["layout_pin"] = pin
    prompt = build_prompt(rec, layout=pin)
    inputs = [[t["input"]] for t in tests]
    expected = [t["expected"] for t in tests]

    tried, agree_pairs = [], []
    for k, ref in enumerate(refs[:MAX_REFS_TRIED]):
        try:
            body = build_canonical_solution(ref["code"])
        except RefReject as e:
            tried.append("ref%d[%s]: %s" % (k, ref.get("language"), e))
            continue
        full_code = prompt + body
        try:
            compile(full_code, "<task>", "exec")
        except SyntaxError as e:
            tried.append("ref%d: assembled code does not compile (%s)" % (k, e))
            continue
        res, fatal = run_reference(full_code, inputs, timeout)
        if fatal:
            tried.append("ref%d: fatal on load: %s" % (k, fatal[:80]))
            continue
        bad = [i for i in range(len(inputs))
               if i not in res or not res[i]["ok"]]
        if bad:
            errs = {res[i]["err"] for i in bad if i in res}
            tried.append("ref%d: failed %d/%d tests (%s)"
                         % (k, len(bad), len(inputs),
                            ",".join(sorted(errs)) or "missing"))
            continue
        got = [res[i]["out"] for i in range(len(inputs))]
        mism = [i for i in range(len(inputs)) if got[i] != expected[i]]
        if mism:
            agree_pairs.append(got)
            tried.append("ref%d: output != official expected on %d/%d tests "
                         "(first mismatch test %d)"
                         % (k, len(mism), len(inputs), mism[0]))
            continue
        # success — this reference reproduces the official outputs exactly
        times = [res[i]["t"] for i in range(len(inputs))]
        metrics.update(ref_index=k, ref_language=ref.get("language"),
                       ref_origin=ref.get("origin"),
                       ref_max_test_s=max(times),
                       ref_mean_test_s=round(sum(times) / len(times), 4))
        warnings = []
        if rec.get("_base_promoted"):
            warnings.append("base_input = first %d official tests promoted "
                            "(no statement examples extractable)"
                            % rec["_base_promoted"])
        if max(times) > HOUSE_TIMEOUT_S / HOUSE_RUNTIME_MARGIN:
            warnings.append(
                "reference slowest test %.2fs exceeds house runtime margin "
                "(%.2fs) — will flag runtime_margin screen" %
                (max(times), HOUSE_TIMEOUT_S / HOUSE_RUNTIME_MARGIN))
        _float_tok = re.compile(r"^-?\d+\.\d+(e-?\d+)?$")
        if any(_float_tok.match(tok) for e in expected[:20]
               for tok in e.split()[:50]):
            warnings.append("expected outputs contain float tokens; exact "
                            "string compare — needs a tolerance decision")
        if rec.get("has_custom_checker") and \
                rec.get("source_dataset", "").startswith("ByteDance"):
            warnings.append("CC+ ships a testlib checker; exact-oracle "
                            "status is empirical (reference reproduced "
                            "official outputs byte-exactly on all kept "
                            "tests) — spot-check at review")
        task = {
            "task_id": rec["cand_id"],
            "prompt": prompt,
            "entry_point": ENTRY_POINT,
            "canonical_solution": body,
            "base_input": [[t["input"]] for t in base],
            "plus_input": [[t["input"]] for t in plus],
            "atol": 0,
            "expected_output": {"base": expected[:len(base)],
                                "plus": expected[len(base):]},
            "provenance": {**{k: rec[k] for k in
                           ("problem_key", "source_dataset", "source_row",
                            "title", "rating", "tags", "url", "license",
                            "dates", "time_limit_s", "duplicate_of")},
                           "layout_pinned": bool(pin),
                           "case_pinned": bool(cp)},
            "conversion": {"method": "stdin-stdout-inline-wrap",
                           "reference": {kk: ref.get(kk) for kk in
                                         ("language", "origin",
                                          "submission_id")},
                           "tests_dropped_at_fetch":
                               rec["tests_meta"]["n_dropped_oversize"],
                           "tests_dropped_at_budget": dropped,
                           "tests_dropped_duplicate":
                               rec.get("_tests_dropped_duplicate", 0),
                           "sample_tests_extracted":
                               metrics.get("sample_tests_extracted", 0),
                           "layout_pin": pin,
                           "warnings": warnings},
        }
        metrics["warnings"] = warnings
        return "converted", "ref%d exact on %d tests" % (k, len(tests)), \
            task, metrics

    # nothing converted — classify honestly
    metrics["tried"] = tried
    if len(agree_pairs) >= 2 and all(g == agree_pairs[0]
                                     for g in agree_pairs[1:]):
        return ("needs-human", "multi-answer suspect: %d references agree "
                "with each other but not with official outputs" %
                len(agree_pairs), None, metrics)
    if tried and all("Timeout" in t for t in tried):
        return ("needs-human", "all references exceed %.0fs/test in CPython "
                "(PyPy-only problem?)" % timeout, None, metrics)
    return ("needs-human", "no reference passed cleanly: %s"
            % "; ".join(tried[:4]), None, metrics)


# ----------------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True,
                    help="candidates_raw.jsonl from fetch_candidates.py")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", nargs="*", help="convert only these cand_ids")
    ap.add_argument("--timeout", type=float, default=PER_TEST_TIMEOUT,
                    help="per-test reference timeout, seconds (default %.0f)"
                    % PER_TEST_TIMEOUT)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    cands = []
    with open(args.inp) as f:
        for line in f:
            cands.append(json.loads(line))
    if args.ids:
        cands = [c for c in cands if c["cand_id"] in set(args.ids)]
    if args.limit:
        cands = cands[:args.limit]

    tasks_path = os.path.join(args.outdir, "tasks_converted.jsonl")
    report_path = os.path.join(args.outdir, "conversion_report.jsonl")
    counts = {"converted": 0, "needs-human": 0, "rejected": 0}
    done = set()
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add(r["cand_id"])
                    counts[r["status"]] += 1
                except Exception:
                    pass
    if done:
        print("[convert] resuming: %d candidates already done" % len(done),
              flush=True)
        cands = [c for c in cands if c["cand_id"] not in done]
    t0 = time.time()
    with open(tasks_path, "a") as tf, open(report_path, "a") as rf:
        for n, rec in enumerate(cands, 1):
            t1 = time.time()
            try:
                status, reason, task, metrics = convert_candidate(
                    rec, args.timeout)
            except Exception as e:   # converter bug — never hide it
                status, reason, task = "needs-human", \
                    "converter crashed: %s: %s" % (type(e).__name__, e), None
                metrics = {}
            counts[status] += 1
            if task:
                tf.write(json.dumps(task) + "\n")
                tf.flush()
            rf.write(json.dumps({
                "cand_id": rec["cand_id"], "rating": rec.get("rating"),
                "source": rec.get("source_dataset"),
                "status": status, "reason": reason,
                "elapsed_s": round(time.time() - t1, 1),
                "metrics": metrics}) + "\n")
            rf.flush()
            print("[convert] %2d/%d %-24s %-11s %s"
                  % (n, len(cands), rec["cand_id"], status, reason[:90]),
                  flush=True)
    print("\n[convert] yield: %d converted / %d needs-human / %d rejected "
          "of %d  (%.0fs)" % (counts["converted"], counts["needs-human"],
                              counts["rejected"], len(cands),
                              time.time() - t0))
    print("[convert] tasks  -> %s" % tasks_path)
    print("[convert] report -> %s" % report_path)


if __name__ == "__main__":
    main()
