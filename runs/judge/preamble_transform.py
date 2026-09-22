#!/usr/bin/env python3
import re
RULE = "leading-imports-v4.1-self-shadowing-refined"
RULE_V4 = "leading-imports-v4-module-names-bound"
RULE_V3 = "leading-imports-v3-echo-neutral"
SELF_SHADOWING = frozenset(("bisect", "random", "time", "copy", "datetime", "array"))
RULE_V2 = "leading-imports-v2-builtins-restored"
_STAR = re.compile(r"^from\s+\S+\s+import\s+\*\s*$")
BUILTINS_LINE = "from builtins import *"
_IMP = re.compile(r"^(import|from)\s")
def leading_imports(prompt: str) -> list:
    out = []
    for line in prompt.splitlines():
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        if _IMP.match(line):
            out.append(line)
            continue
        break
    return out
def echoed_star_lines(prompt: str, solution: str) -> list:
    pstars = {l.strip() for l in leading_imports(prompt) if _STAR.match(l.strip())}
    return [ln for ln in solution.splitlines() if ln and not ln[0].isspace() and ln.strip() in pstars]
def apply_v2(prompt: str, solution: str) -> str:
    lines = leading_imports(prompt)
    if not lines:
        return solution
    return "".join(l + "\n" for l in lines) + BUILTINS_LINE + "\n\n" + solution
_STAR_MOD = re.compile(r"^from\s+([\w\.]+)\s+import\s+\*\s*$")
def _text_binds_module(solution: str, mod: str) -> bool:
    """True if the solution itself binds the name `mod` with a plain import (`import mod` / `import mod.sub`, not `as`)."""
    for ln in solution.splitlines():
        m = re.match(r"^\s*import\s+(.+?)\s*(#.*)?$", ln)
        if not m: continue
        for item in m.group(1).split(","):
            item = item.strip()
            if " as " in item: continue
            if item == mod or item.startswith(mod + "."): return True
    return False
def module_bindings_v3(prompt: str, solution: str) -> list:
    lines = leading_imports(prompt); plain = set(); need = []
    for l in lines:
        m2 = re.match(r"^\s*import\s+([\w\.]+(?:\s*,\s*[\w\.]+)*)", l)
        if m2: plain.update(x.strip() for x in m2.group(1).split(","))
    for l in lines:
        m = _STAR_MOD.match(l.strip())
        if not m: continue
        mod = m.group(1)
        if mod in plain or mod in need: continue
        if not re.search(r"(?<![\w.])" + re.escape(mod) + r"\.\w+", solution): continue
        if _text_binds_module(solution, mod): continue
        need.append(mod)
    return need
def star_modules(prompt: str) -> list:
    """V4: every module the prompt's leading block star-imports (`from M import *`), header order, deduplicated; a relative star import
    (`from . import *`) has no importable name and is skipped. Not conditioned on the solution text (that was V3's refinement)."""
    out = []
    for l in leading_imports(prompt):
        m = _STAR_MOD.match(l.strip())
        if not m: continue
        mod = m.group(1)
        if mod.startswith(".") or mod in out: continue
        out.append(mod)
    return out
def _uses_qualified(solution: str, mod: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(mod) + r"\.\w+", solution) is not None
def _calls_bare(solution: str, mod: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(mod) + r"\s*\(", solution) is not None
def module_bindings(prompt: str, solution: str = "") -> list:
    out = []
    for mod in star_modules(prompt):
        if mod in SELF_SHADOWING and not (_uses_qualified(solution, mod) and not _calls_bare(solution, mod)): continue
        out.append(mod)
    return out
_FUTURE = re.compile(r"^from __future__ import [^\n]+$")

def hoist_future(solution: str):
    fut, rest = [], []
    for ln in solution.splitlines(keepends=True):
        if ln and not ln[0].isspace() and _FUTURE.match(ln.strip()):
            fut.append(ln.strip())
        else:
            rest.append(ln)
    return fut, "".join(rest)

def apply(prompt: str, solution: str) -> str:
    lines = leading_imports(prompt)
    if not lines:
        return solution
    fut, solution = hoist_future(solution)
    pre = "".join(f + "\n" for f in fut)
    binds = module_bindings(prompt, solution)
    head = pre + "".join(l + "\n" for l in lines) + "".join("import " + m + "\n" for m in binds) + BUILTINS_LINE + "\n\n"
    pstars = {}                                     # stripped star line → module name ("" for a relative star import: nothing to bind)
    for l in lines:
        if _STAR.match(l.strip()):
            m = _STAR_MOD.match(l.strip()); mod = m.group(1) if m else ""
            pstars[l.strip()] = "" if mod.startswith(".") else mod
    if not pstars or not echoed_star_lines(prompt, solution):
        return head + solution                      # == V3 byte for byte when no echo (V3 == V2 when no binding and no __future__ line)
    out = []
    for ln in solution.splitlines(keepends=True):
        out.append(ln)
        if ln and not ln[0].isspace() and ln.strip() in pstars:   # an echoed top-level star import: re-bind the module (V4 echo clause, V4.1: same predicate as the head), restore builtins (V3)
            if not ln.endswith("\n"): out.append("\n")
            if pstars[ln.strip()] and pstars[ln.strip()] in binds: out.append("import " + pstars[ln.strip()] + "\n")
            out.append(BUILTINS_LINE + "\n")
    return head + "".join(out)
if __name__ == "__main__":
    demo = "from typing import List\n\n# helper import\nimport math\ndef f(x):\n    import os\n    return x\n"
    assert leading_imports(demo) == ["from typing import List", "import math"], leading_imports(demo)
    assert apply(demo, "def f(x):\n    return x\n") == "from typing import List\nimport math\nfrom builtins import *\n\ndef f(x):\n    return x\n"
    assert apply("def g():\n    pass\n", "X") == "X"
    hq = "from heapq import *\nfrom typing import *\ndef f(a):\n    pass\n"
    qual = "def f(a):\n    heapq.heappush(a, 1)\n    return a\n"
    nsq = {}; exec(apply(hq, qual), nsq); assert nsq["f"]([]) == [1], "module binding: heapq.heappush must resolve"
    try:
        nsv = {}; exec(apply_v2(hq, qual), nsv); nsv["f"]([]); raise SystemExit("V2 shape should NameError on heapq.heappush")
    except NameError:
        pass
    def v4head(v2out, mods): return v2out.replace(BUILTINS_LINE + "\n\n", "".join("import %s\n" % m for m in mods) + BUILTINS_LINE + "\n\n", 1)
    assert apply(hq, qual).startswith("from heapq import *\nfrom typing import *\nimport heapq\nimport typing\n" + BUILTINS_LINE), apply(hq, qual)[:120]
    assert module_bindings(hq, qual) == ["heapq", "typing"] == star_modules(hq), "V4 binds every star-imported module"
    plain_use = "def f(a):\n    heappush(a, 1)\n    return a\n"
    assert apply(hq, plain_use) == v4head(apply_v2(hq, plain_use), ["heapq", "typing"]), "V4 == V2 + the module bindings when nothing is echoed"
    own = "import heapq\ndef f(a):\n    heapq.heappush(a, 1)\n    return a\n"
    nso1 = {}; exec(apply(hq, own), nso1); assert nso1["f"]([]) == [1], "a text that binds the module itself still runs (duplicate plain import is harmless)"
    assert module_bindings(hq, own) == ["heapq", "typing"], "V4 binding is unconditional"
    assert module_bindings("import heapq\nfrom heapq import *\ndef f(a):\n    pass\n", qual) == ["heapq"], "V4: emitted even when the header imports plainly"
    # V3's conditional refinement kept as module_bindings_v3 (era-flip census reference)
    assert module_bindings_v3(hq, qual) == ["heapq"] and module_bindings_v3(hq, plain_use) == [] and module_bindings_v3(hq, own) == []
    assert module_bindings_v3(hq, "import heapq as hp\ndef f(a):\n    heapq.heappush(a, 1)\n") == ["heapq"], "`import heapq as hp` does not bind heapq"
    assert module_bindings_v3("import heapq\nfrom heapq import *\ndef f(a):\n    pass\n", qual) == []
    over = "heapq = None\ndef f(a):\n    return heapq\n"
    nso = {}; exec(apply(hq, over), nso); assert nso["f"]([]) is None, "the text's own assignment overrides the binding"
    # V4 specimens: (1) a BARE module reference (no `heapq.`) — V3 left it unbound (NameError), V4 binds it
    bare = "def f(a):\n    h = heapq\n    h.heappush(a, 2)\n    return a\n"
    v3shape = "".join(l + "\n" for l in leading_imports(hq)) + BUILTINS_LINE + "\n\n" + bare   # V3 output for a text with no qualified use
    try:
        nsb = {}; exec(v3shape, nsb); nsb["f"]([]); raise SystemExit("V3 shape should NameError on the bare reference")
    except NameError:
        pass
    nsb2 = {}; exec(apply(hq, bare), nsb2); assert nsb2["f"]([]) == [2], "V4: bare module reference resolves"
    # (2) echo clause: `import bisect` then the echoed `from bisect import *` rebinds bisect to a FUNCTION; V4 re-binds the module after the echo
    bh = "from bisect import *\nfrom typing import *\ndef f(a, x):\n    pass\n"
    becho = "import bisect\nfrom bisect import *\ndef f(a, x):\n    return bisect.bisect_right(a, x)\n"
    v3echo = "".join(l + "\n" for l in leading_imports(bh)) + "import bisect\n" + BUILTINS_LINE + "\n\n" + becho.replace("from bisect import *\n", "from bisect import *\n" + BUILTINS_LINE + "\n", 1)
    try:
        nse = {}; exec(v3echo, nse); nse["f"]([1, 2, 3], 2); raise SystemExit("V3 echo shape should AttributeError (bisect is the function)")
    except AttributeError:
        pass
    outb = apply(bh, becho); nse2 = {}; exec(outb, nse2); assert nse2["f"]([1, 2, 3], 2) == 2, "V4 echo clause: module re-bound after the echoed star line"
    assert "\nfrom bisect import *\nimport bisect\n" + BUILTINS_LINE + "\n" in outb.split("\n\n", 1)[1], outb
    assert outb.startswith("from bisect import *\nfrom typing import *\nimport bisect\nimport typing\n" + BUILTINS_LINE + "\n\n"), outb[:140]
    # (3) self-shadowing star export used qualified without an echo: bound in the head
    rh = "from random import *\ndef f():\n    pass\n"
    nsr = {}; exec(apply(rh, "def f():\n    return random.randint(1, 1)\n"), nsr); assert nsr["f"]() == 1
    # (4) a relative star import has no importable name: nothing emitted, no `import .`
    assert star_modules("from . import *\nimport math\ndef f():\n    pass\n") == [] and "import .\n" not in apply("from . import *\ndef f():\n    pass\n", "def f():\n    return 1\n")
    # (5) a model's own star import (not in the prompt block) and a module the prompt does not import stay model-side
    assert module_bindings(hq, "from fractions import *\ndef f(a):\n    return math.pi\n") == ["heapq", "typing"]
    # V4.1 specimens (self-shadowing modules): bare call keeps the star-exported callable; qualified-only binds; both → V3 behaviour (no bind)
    bare_call = "def f(a, x):\n    return bisect(a, x)\n"                          # correct code under `from bisect import *`
    assert module_bindings(bh, bare_call) == ["typing"], module_bindings(bh, bare_call)
    nsc = {}; exec(apply(bh, bare_call), nsc); assert nsc["f"]([1, 2, 3], 2) == 2, "V4.1: bare bisect(a, x) still calls the function"
    v4shape = "".join(l + "\n" for l in leading_imports(bh)) + "import bisect\nimport typing\n" + BUILTINS_LINE + "\n\n" + bare_call
    try:
        nsv4 = {}; exec(v4shape, nsv4); nsv4["f"]([1, 2, 3], 2); raise SystemExit("V4 shape should TypeError: module is not callable")
    except TypeError:
        pass
    assert module_bindings(bh, becho) == ["bisect", "typing"], "qualified use, no bare call → bound (the V4 echo case still works)"
    both = "def f(a, x):\n    return bisect(a, x) + bisect.bisect_left(a, x)\n"
    assert module_bindings(bh, both) == ["typing"], "both idioms → V3 behaviour, no binding"
    echo_bare = "from bisect import *\ndef f(a, x):\n    return bisect(a, x)\n"          # echoed star line + bare call: no `import bisect` after the echo
    oeb = apply(bh, echo_bare); assert "import bisect" not in oeb, oeb
    nse3 = {}; exec(oeb, nse3); assert nse3["f"]([1, 2, 3], 2) == 2
    assert module_bindings("from heapq import *\ndef f(a):\n    pass\n", "def f(a):\n    return heapq\n") == ["heapq"], "non-self-shadowing modules still bind unconditionally"
    assert module_bindings("from random import *\ndef f():\n    pass\n", "def f():\n    return random()\n") == [], "random() bare keeps the function"
    assert module_bindings("from random import *\ndef f():\n    pass\n", "def f():\n    return random.randint(1, 1)\n") == ["random"]
    # future_refinement specimens: a text opening with a __future__ line compiles with the header prepended (future line first),
    # a text without one is byte-identical to before, and a __future__ line after a leading comment/docstring is hoisted too
    futxt = "from __future__ import annotations\ndef f(x: List[int]) -> int:\n    return len(x)\n"
    outf = apply(demo, futxt); assert outf.startswith("from __future__ import annotations\nfrom typing import List\nimport math\n"), outf[:120]
    compile(outf, "<judged>", "exec"); nsf = {}; exec(outf, nsf); assert nsf["f"]([1, 2]) == 2
    try:
        compile("from typing import List\n" + futxt, "<v3>", "exec"); raise SystemExit("header-first shape should fail to compile")
    except SyntaxError:
        pass
    assert apply(demo, "def f(x):\n    return x\n") == "from typing import List\nimport math\nfrom builtins import *\n\ndef f(x):\n    return x\n"
    late = "# solution\n\"\"\"doc\"\"\"\nfrom __future__ import annotations\ndef g():\n    return 1\n"
    compile(apply(demo, late), "<late>", "exec")
    # v2 case: a star import that shadows pow must not break 3-argument pow in the judged program
    star = "from math import *\nfrom operator import *\ndef h(a, b, m):\n    pass\n"
    prog = apply(star, "def h(a, b, m):\n    return pow(a, b, m)\n")
    ns = {}; exec(prog, ns); assert ns["h"](3, 4, 5) == 1, "3-arg pow must work under the preamble"
    bad = "".join(l + "\n" for l in leading_imports(star)) + "\n" + "def h(a, b, m):\n    return pow(a, b, m)\n"
    try:
        ns2 = {}; exec(bad, ns2); ns2["h"](3, 4, 5); raise SystemExit("v1 shape should have failed (pow shadowed)")
    except TypeError:
        pass
    # v3 cases: an echoed prompt star import is neutralised; a self-added star import and plain text stay byte-identical to V2
    echo = "from math import *\nfrom operator import *\ndef h(a, b, m):\n    return pow(a, b, m)\n"
    ns3 = {}; exec(apply(star, echo), ns3); assert ns3["h"](3, 4, 5) == 1, "V3: echoed header must not re-shadow pow"
    try:
        ns4 = {}; exec(apply_v2(star, echo), ns4); ns4["h"](3, 4, 5); raise SystemExit("V2 shape should have failed on the echoed header")
    except TypeError:
        pass
    late = '"""doc"""\nimport sys\nfrom math import *\ndef h(a, b, m):\n    return pow(a, b, m)\n'   # echo AFTER a docstring (scope_refinement)
    ns5 = {}; exec(apply(star, late), ns5); assert ns5["h"](3, 4, 5) == 1, "V3: a late top-level echo must not re-shadow pow"
    nested = "def k():\n    from math import *\n    return 1\n" + "def h(a, b, m):\n    return pow(a, b, m)\n"   # indented import: not an echo
    assert apply(star, nested) == v4head(apply_v2(star, nested), ["math", "operator"]), "V4 == V2 + head bindings when the star import is nested (not top-level)"
    own = "from fractions import *\ndef h(a, b, m):\n    return pow(a, b, m)\n"
    assert apply(star, own) == v4head(apply_v2(star, own), ["math", "operator"]), "V4 == V2 + head bindings when the star import is the model's own"
    assert apply(star, "def h(a, b, m):\n    return pow(a, b, m)\n") == v4head(apply_v2(star, "def h(a, b, m):\n    return pow(a, b, m)\n"), ["math", "operator"])
    assert apply(demo, "def f(x):\n    return x\n") == apply_v2(demo, "def f(x):\n    return x\n"), "no star import in the block → byte-identical to V2/V3"
    print("preamble_transform self-test OK; rule", RULE)
