"""Habit detectors shared by the baseline and the intervention runs (text-level, pass/fail independent)."""
import re
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)
_BUILTINS = "int|float|str|bool|list|dict|set|tuple|Integer|Integral|Real|Number|complex|bytes"
_IMP = re.compile(r"^\s*from\s+typing\s+import\s+[^\n]*\b(?:%s)\b" % _BUILTINS, re.M)
_RAISE = re.compile(r"^\s*raise\s+\w", re.M)
_STDIN = re.compile(r"sys\.stdin|(?<![\w.])input\s*\(")
def code_of(text):
    """The code the board's extractor would see: fenced blocks joined; else the whole text."""
    blocks = _FENCE.findall(text or "")
    return "\n".join(blocks) if blocks else (text or "")
def detect(text, entry_point=None):
    code = code_of(text)
    out = {
        "impossible_import": bool(_IMP.search(code)),
        "guard_raise": bool(_RAISE.search(code)),
        "stdin": bool(_STDIN.search(code)),
        "entry_missing": bool(entry_point) and not re.search(r"^\s*def\s+%s\s*\(" % re.escape(entry_point), code, re.M),
    }
    return out
