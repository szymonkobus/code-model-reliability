"""The typing-import cleaning applied to the gpt-5 arms' answers before judging (rule ``typing-builtins-v1``).

Some answers of the two gpt-5 arms open with a line such as ``from typing import int``: the typing module exports no
such name, so the whole program fails at import before any test runs, although the function below the line is often
correct. The rule, applied to the answer text before the judge grades it: in every ``from typing import ...`` line of
the program, remove the names ``int``, ``Integer``, ``Integral``, ``bool``, ``float`` and ``str``; a line that empties
is dropped, its line break kept so that line numbers do not move; a line that names none of them is returned
unchanged; nothing else in the program changes. The judge then grades the cleaned text with its ordinary settings.

``clean(program)`` returns the cleaned text and ``changed(program)`` says whether the rule touches it. Run as a script,
``python cleaning.py <samples.jsonl> <out.jsonl>`` cleans the ``solution`` field of every row and prints the counts.
"""
from __future__ import annotations

import json
import re
import sys

RULE = "typing-builtins-v1"
REMOVED_NAMES = frozenset({"int", "Integer", "Integral", "bool", "float", "str"})
TYPING_LINE = re.compile(r"^(\s*)from typing import ([^\n#]*)(#.*)?$", re.M)


def clean(program: str) -> str:
    def fix(m: re.Match) -> str:
        names = [x.strip() for x in m.group(2).split(",") if x.strip()]
        keep = [x for x in names if x.split(" as ")[0].strip() not in REMOVED_NAMES]
        if len(keep) == len(names):
            return m.group(0)   # nothing removed: the line stays byte for byte, so the rule is a no-op off the carrier set
        if not keep:
            return ""           # the line empties and is dropped; the line break after it stays
        return f"{m.group(1)}from typing import {', '.join(keep)}{m.group(3) or ''}"

    return TYPING_LINE.sub(fix, program)


def changed(program: str) -> bool:
    return clean(program) != program


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: cleaning.py <samples.jsonl> <out.jsonl>", file=sys.stderr)
        return 2
    rows = touched = 0
    with open(argv[1], encoding="utf-8") as src, open(argv[2], "w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            rows += 1
            for key in ("solution", "completion"):
                if isinstance(row.get(key), str):
                    cleaned = clean(row[key])
                    if cleaned != row[key]:
                        row[key] = cleaned
                        touched += 1
                        break
            dst.write(json.dumps(row) + "\n")
    print(json.dumps({"rule": RULE, "rows": rows, "changed": touched}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
