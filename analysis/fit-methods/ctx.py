#!/usr/bin/env python3
"""ctx.py <file> <regex> [width=200] [max=6] — print each match of the regex (case-insensitive) with `width` characters of
context on either side, whitespace collapsed; a replacement for wide-context greps that ugrep refuses (its regex complexity
limit on `.{0,N}` over multibyte text). Reads the file whole; never recursive."""
import re, sys

path = sys.argv[1]; pat = sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 200
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 6
t = open(path, errors="replace").read()
n = 0
for m in re.finditer(pat, t, re.I):
    s = re.sub(r"\s+", " ", t[max(0, m.start() - width): m.end() + width])
    print(f"[{m.start()}] …{s}…\n"); n += 1
    if n >= mx: break
print(f"{n} match(es) shown of {len(re.findall(pat, t, re.I))}")
