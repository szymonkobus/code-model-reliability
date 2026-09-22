#!/usr/bin/env python3
"""All v_* return the SANITIZE-level output (post stage2, .strip() on the nonempty
branch, mirroring pinned sanitize()). code-extract-level callables are exposed
separately for algorithm-only timing.
"""
import re
from typing import List, Optional, Tuple

# --- pinned imports (caller must ensure evalplus + tree_sitter importable) ---
from evalplus.sanitize import code_extract as pinned_code_extract
from evalplus.sanitize import sanitize as pinned_sanitize
from evalplus.syncheck import syntax_check
import tree_sitter_python
from tree_sitter import Language, Node, Parser

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def pruned_exact_code_extract(text: str) -> str:
    text = ANSI_RE.sub("", text)
    lines = text.split("\n")
    n = len(lines)
    blank = [not l.strip() for l in lines]
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + (0 if blank[i] else 1)

    best_len = 0
    best_pair = (0, 0)
    for i in range(n):
        if suffix[i] <= best_len:  # P1: no later start can strictly beat best
            break
        j = n - 1
        prev_tested_invalid_at = None  # j index of last invalid parse (for P3)
        found = None
        while j >= i + 1:
            cnt = suffix[i] - suffix[j + 1]
            if cnt <= best_len:  # P2
                break
            skip = (
                prev_tested_invalid_at == j + 1
                and j + 1 < n
                and blank[j + 1]
            )
            if not skip:
                if syntax_check("\n".join(lines[i : j + 1])):
                    found = (j, cnt)
                    break
                prev_tested_invalid_at = j
            else:
                prev_tested_invalid_at = j  # transitively invalid (P3)
            j -= 1
        if found is not None:
            jf, cnt = found
            # P4: smallest valid j with equal count (trailing blanks only)
            j2 = jf
            while j2 - 1 >= i + 1 and blank[j2]:
                cand = j2 - 1
                if syntax_check("\n".join(lines[i : cand + 1])):
                    j2 = cand
                else:
                    break
            best_len = cnt
            best_pair = (i, j2)
    return "\n".join(lines[best_pair[0] : best_pair[1] + 1])


# ---------------------------------------------------------------------------
# anchor-heuristic code_extract (characterization candidate)
# ---------------------------------------------------------------------------
ANCHOR_RE = re.compile(r"^(def |class |import |from |@|async def )")


def anchor_code_extract(text: str) -> str:
    stripped = ANSI_RE.sub("", text)
    lines = stripped.split("\n")
    n = len(lines)
    blank = [not l.strip() for l in lines]
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + (0 if blank[i] else 1)
    anchors = [i for i in range(n) if ANCHOR_RE.match(lines[i])]

    best_len = 0
    best_pair = None
    for i in anchors:
        if suffix[i] <= best_len:
            continue  # anchors are not contiguous: continue, not break
        j = n - 1
        found = None
        while j >= i + 1:
            cnt = suffix[i] - suffix[j + 1]
            if cnt <= best_len:
                break
            if syntax_check("\n".join(lines[i : j + 1])):
                found = (j, cnt)
                break
            j -= 1
        if found is not None:
            jf, cnt = found
            j2 = jf
            while j2 - 1 >= i + 1 and blank[j2]:
                cand = j2 - 1
                if syntax_check("\n".join(lines[i : cand + 1])):
                    j2 = cand
                else:
                    break
            best_len = cnt
            best_pair = (i, j2)
    if best_pair is None:
        return pruned_exact_code_extract(text)
    return "\n".join(lines[best_pair[0] : best_pair[1] + 1])


CLASS_TYPE = "class_definition"
FUNCTION_TYPE = "function_definition"
IMPORT_TYPE = ["import_statement", "import_from_statement"]
IDENTIFIER_TYPE = "identifier"
RETURN_TYPE = "return_statement"
EXPRESSION_TYPE = "expression_statement"
ASSIGNMENT_TYPE = "assignment"
YIELD_TYPE = "yield"

_parser = None


def _get_parser() -> Parser:
    global _parser
    if _parser is None:
        _parser = Parser(Language(tree_sitter_python.language()))
    return _parser


def _traverse(node: Node):
    cursor = node.walk()
    depth = 0
    visited_children = False
    while True:
        if not visited_children:
            yield cursor.node
            if not cursor.goto_first_child():
                depth += 1
                visited_children = True
        elif cursor.goto_next_sibling():
            visited_children = False
        elif not cursor.goto_parent() or depth == 0:
            break
        else:
            depth -= 1


def _has_return(node: Node, allow_yield: bool) -> bool:
    for nd in _traverse(node):
        if nd.type == RETURN_TYPE:
            return True
        if allow_yield and nd.type == YIELD_TYPE:
            return True
    return False


def _get_definition_name(node: Node) -> Optional[str]:
    for child in node.children:
        if child.type == IDENTIFIER_TYPE:
            return child.text.decode("utf8")
    return None


def _get_deps(nodes):
    def dfs(node, deps):
        for child in node.children:
            if child.type == IDENTIFIER_TYPE:
                deps.add(child.text.decode("utf8"))
            else:
                dfs(child, deps)

    name2deps = {}
    for name, node in nodes:
        deps = set()
        dfs(node, deps)
        name2deps[name] = deps
    return name2deps


def _reachable(entrypoint, call_graph):
    queue = [entrypoint]
    visited = {entrypoint}
    while queue:
        current = queue.pop(0)
        if current not in call_graph:
            continue
        for neighbour in call_graph[current]:
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return visited


def stage2(code: str, entrypoint: Optional[str] = None, allow_yield: bool = False) -> str:
    code_bytes = bytes(code, "utf8")
    tree = _get_parser().parse(code_bytes)
    class_names, function_names, variable_names = set(), set(), set()
    import_nodes = []
    definition_nodes = []
    for child in tree.root_node.children:
        if child.type in IMPORT_TYPE:
            import_nodes.append(child)
        elif child.type == CLASS_TYPE:
            name = _get_definition_name(child)
            if not (
                name in class_names or name in variable_names or name in function_names
            ):
                definition_nodes.append((name, child))
                class_names.add(name)
        elif child.type == FUNCTION_TYPE:
            name = _get_definition_name(child)
            if not (
                name in function_names or name in variable_names or name in class_names
            ) and _has_return(child, allow_yield):
                definition_nodes.append((name, child))
                function_names.add(name)
        elif (
            child.type == EXPRESSION_TYPE
            and child.children
            and child.children[0].type == ASSIGNMENT_TYPE
        ):
            subchild = child.children[0]
            name = _get_definition_name(subchild)
            if not (
                name in variable_names or name in function_names or name in class_names
            ):
                definition_nodes.append((name, subchild))
                variable_names.add(name)

    if entrypoint:
        name2deps = _get_deps(definition_nodes)
        reachable = _reachable(entrypoint, name2deps)

    sanitized_output = b""
    for node in import_nodes:
        sanitized_output += code_bytes[node.start_byte : node.end_byte] + b"\n"
    for name, node in definition_nodes:
        if entrypoint and name not in reachable:
            continue
        sanitized_output += code_bytes[node.start_byte : node.end_byte] + b"\n"
    return sanitized_output[:-1].decode("utf8")


# ---------------------------------------------------------------------------
# fence + think-block machinery
# ---------------------------------------------------------------------------
FENCE_OPEN_RE = re.compile(r"^\s{0,3}```+[ \t]*([A-Za-z0-9_+#.-]*)")
FENCE_CLOSE_RE = re.compile(r"^\s{0,3}```+\s*$")
PYTHONISH = {"", "python", "py", "python3"}


def think_strip(text: str) -> str:
    """Remove <think>...</think> regions; unclosed <think> strips to EOF.
    If stripping leaves nothing nonblank, return the original text."""
    out = []
    in_think = False
    for line in text.split("\n"):
        s = line.strip()
        if not in_think and s.startswith("<think>"):
            in_think = True
            continue
        if in_think:
            if s.endswith("</think>") or s == "</think>":
                in_think = False
            continue
        out.append(line)
    res = "\n".join(out)
    return res if res.strip() else text


def fenced_blocks(text: str) -> List[Tuple[str, str, bool]]:
    """(tag, content, closed) per fenced block; unclosed final block included."""
    blocks = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if m:
            tag = m.group(1).lower()
            content = []
            j = i + 1
            closed = False
            while j < len(lines):
                if FENCE_CLOSE_RE.match(lines[j]):
                    closed = True
                    break
                content.append(lines[j])
                j += 1
            blocks.append((tag, "\n".join(content), closed))
            i = j + 1
        else:
            i += 1
    return blocks


# ---------------------------------------------------------------------------
# sanitize-level candidates
# ---------------------------------------------------------------------------
def v_pinned(text: str, entrypoint: Optional[str] = None) -> str:
    return pinned_sanitize(text, entrypoint)


def _pinned_shape_sanitize(code_extract_fn, text, entrypoint):
    """Pinned sanitize() flow with code_extract swapped at BOTH call sites
    (sanitize.py:116 pre-pass and :176 empty-fallback)."""
    pre = code_extract_fn(text)
    sanitized_code = stage2(pre, entrypoint).strip()
    if not sanitized_code:
        return code_extract_fn(text)
    return sanitized_code


def v_pruned(text: str, entrypoint: Optional[str] = None) -> str:
    return _pinned_shape_sanitize(pruned_exact_code_extract, text, entrypoint)


def v_anchor(text: str, entrypoint: Optional[str] = None) -> str:
    return _pinned_shape_sanitize(anchor_code_extract, text, entrypoint)


def _fenced_impl(text, entrypoint, allow_yield):
    t = think_strip(text)
    blocks = [c for tag, c, _closed in fenced_blocks(t) if tag in PYTHONISH]
    if blocks:
        code = "\n".join(reversed(blocks))  # keep-first dedup => keep-LAST block
        out = stage2(code, entrypoint, allow_yield).strip()
        if out:
            return out
    out = stage2(t, entrypoint, allow_yield).strip()
    if out:
        return out
    return t if t.strip() else text


def v_fenced(text: str, entrypoint: Optional[str] = None) -> str:
    return _fenced_impl(text, entrypoint, allow_yield=False)


def v_fenced_genfix(text: str, entrypoint: Optional[str] = None) -> str:
    return _fenced_impl(text, entrypoint, allow_yield=True)


def v_tswhole(text: str, entrypoint: Optional[str] = None) -> str:
    out = stage2(text, entrypoint).strip()
    return out if out else text


# code-extract-level callables for algorithm-only timing
CODE_EXTRACT_LEVEL = {
    "pinned": pinned_code_extract,
    "pruned_exact": pruned_exact_code_extract,
    "anchor": anchor_code_extract,
}

SANITIZE_LEVEL = {
    "pinned": v_pinned,
    "pruned_exact": v_pruned,
    "anchor": v_anchor,
    "fenced": v_fenced,
    "fenced_genfix": v_fenced_genfix,
    "tswhole": v_tswhole,
}

IDENTITY_GATED = ("pruned_exact",)
SEMANTIC_GATED = ("fenced", "fenced_genfix")
CHARACTERIZATION = ("anchor", "tswhole")
