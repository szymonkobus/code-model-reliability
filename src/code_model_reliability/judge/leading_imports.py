"""The leading-imports rule: a task prompt's leading import lines are placed before the judged program.

A task prompt may open with import lines (``from typing import List``, ``from heapq import *``); a model that
relies on them without repeating them has written a correct function for the task's own environment, so the
judge supplies that environment. The rule, in its version ``RULE``:

- the prompt's leading import block (its ``import`` and ``from ... import`` lines before the first other line,
  blank lines and comments skipped) is written first, in the prompt's order;
- for every ``from M import *`` in that block the module name is bound too (``import M``), because a program may
  use ``heapq.heappush`` after a star import; a module whose star export is its own name (``bisect``) is bound
  only when the program uses the module qualified and never calls the name bare;
- ``from builtins import *`` follows, restoring every builtin a star import shadowed (``pow`` after
  ``from math import *``);
- a top-level ``from __future__`` line in the program is lifted to the very top, where Python requires it;
- where the program repeats one of the prompt's star-import lines at top level, the module binding and the
  builtins line are inserted again right after it, so the echo does not undo the restore.

A prompt without leading imports leaves the program unchanged. ``apply_typing`` adds, for the completion form,
a first line importing the common typing names (``RULE_TYPING``), so a trailing block with typed signatures does
not fail the whole module at import. Reads and writes nothing; pure functions on text.
"""

from __future__ import annotations

import re

RULE = "leading-imports-v4.1-self-shadowing-refined"
RULE_TYPING = "typing-prelude-v5"

BUILTINS_LINE = "from builtins import *"
TYPING_PRELUDE = (
    "from typing import List, Dict, Tuple, Optional, Set, Any, Union, Callable, Iterable, Sequence, Mapping, "
    "Iterator, Generator, DefaultDict, Deque, FrozenSet\n"
)
# Modules whose star export is a callable of the module's own name: after ``from bisect import *`` the name
# ``bisect`` is the function, and binding the module over it would break ``bisect(a, x)``.
SELF_SHADOWING = frozenset(("bisect", "random", "time", "copy", "datetime", "array"))

_IMPORT_LINE = re.compile(r"^(import|from)\s")
_STAR_LINE = re.compile(r"^from\s+\S+\s+import\s+\*\s*$")
_STAR_MODULE = re.compile(r"^from\s+([\w\.]+)\s+import\s+\*\s*$")
_FUTURE_LINE = re.compile(r"^from __future__ import [^\n]+$")


def leading_imports(prompt: str) -> list[str]:
    """The prompt's leading import lines, verbatim and in order; blank lines and comments are skipped, the first
    other line ends the block, and imports later in the prompt are not taken."""
    out: list[str] = []
    for line in prompt.splitlines():
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        if _IMPORT_LINE.match(line):
            out.append(line)
            continue
        break
    return out


def star_modules(prompt: str) -> list[str]:
    """The modules the leading block star-imports, in order, once each; a relative star import has no name."""
    out: list[str] = []
    for line in leading_imports(prompt):
        m = _STAR_MODULE.match(line.strip())
        if not m:
            continue
        mod = m.group(1)
        if mod.startswith(".") or mod in out:
            continue
        out.append(mod)
    return out


def _uses_qualified(program: str, mod: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(mod) + r"\.\w+", program) is not None


def _calls_bare(program: str, mod: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(mod) + r"\s*\(", program) is not None


def module_bindings(prompt: str, program: str = "") -> list[str]:
    """The modules to bind with ``import M`` after the block: every star-imported module, except a self-shadowing
    one unless the program uses it qualified and never calls its name bare."""
    out: list[str] = []
    for mod in star_modules(prompt):
        if mod in SELF_SHADOWING and not (_uses_qualified(program, mod) and not _calls_bare(program, mod)):
            continue
        out.append(mod)
    return out


def echoed_star_lines(prompt: str, program: str) -> list[str]:
    """The prompt's star-import lines that the program repeats as top-level lines (column 0, compared stripped)."""
    stars = {line.strip() for line in leading_imports(prompt) if _STAR_LINE.match(line.strip())}
    return [ln for ln in program.splitlines() if ln and not ln[0].isspace() and ln.strip() in stars]


def hoist_future(program: str) -> tuple[list[str], str]:
    """Lift the program's top-level ``from __future__`` lines out; returns them and the program without them."""
    future: list[str] = []
    rest: list[str] = []
    for line in program.splitlines(keepends=True):
        if line and not line[0].isspace() and _FUTURE_LINE.match(line.strip()):
            future.append(line.strip())
        else:
            rest.append(line)
    return future, "".join(rest)


def apply(prompt: str, program: str) -> str:
    """The judged program under the leading-imports rule; the program itself when the prompt has no leading imports."""
    lines = leading_imports(prompt)
    if not lines:
        return program
    future, program = hoist_future(program)
    binds = module_bindings(prompt, program)
    head = (
        "".join(f + "\n" for f in future)
        + "".join(line + "\n" for line in lines)
        + "".join("import " + m + "\n" for m in binds)
        + BUILTINS_LINE
        + "\n\n"
    )
    # stripped star line -> module name ("" for a relative star import, which binds nothing)
    stars: dict[str, str] = {}
    for line in lines:
        if _STAR_LINE.match(line.strip()):
            m = _STAR_MODULE.match(line.strip())
            mod = m.group(1) if m else ""
            stars[line.strip()] = "" if mod.startswith(".") else mod
    if not stars or not echoed_star_lines(prompt, program):
        return head + program
    out: list[str] = []
    for line in program.splitlines(keepends=True):
        out.append(line)
        if line and not line[0].isspace() and line.strip() in stars:
            if not line.endswith("\n"):
                out.append("\n")
            mod = stars[line.strip()]
            if mod and mod in binds:
                out.append("import " + mod + "\n")
            out.append(BUILTINS_LINE + "\n")
    return head + "".join(out)


def apply_typing(prompt: str, program: str, with_imports: bool = True) -> str:
    """The judged program for the completion form: the leading-imports rule (when ``with_imports``) and then the
    typing prelude first, after any ``from __future__`` line. A program's own later binding of a typing name
    overrides the prelude, as with the module bindings."""
    base = apply(prompt, program) if with_imports else program
    future, rest = hoist_future(base)
    return "".join(f + "\n" for f in future) + TYPING_PRELUDE + rest
