import json, re, sys

_bound_line = re.compile(r'(<=|>=|≤|≥|(?<!-)<(?!-)|(?<!-)>(?!-)|==|modulo|mod\b|days)')
_mul = re.compile(r'(?<![\d.^])(\d+(?:\.\d+)?)( ?\* ?)10(1[0-8]|[3-9])(?![\d^])')
_pow = re.compile(r'(?<![\d.^*])10(1[0-8]|[3-9])(?![\d^])')
_pow2 = re.compile(r'(?<![\d^.*])2(1[5-6]|3[0-2]|6[3-4])(?![\d^])')   # 2^31 printed as 231, 2^63 as 263, 2^16 as 216

def restore_line(line):
    reps = []
    if not _bound_line.search(line.replace('->', ' ')):
        return line, reps
    def m1(m):
        new = f'{m.group(1)}{m.group(2)}10^{m.group(3)}'; reps.append((m.group(0), new)); return new
    line2 = _mul.sub(m1, line)
    def m2(m):
        new = f'10^{m.group(1)}'; reps.append((m.group(0), new)); return new
    line3 = _pow.sub(m2, line2)
    def m3(m):
        new = f'2^{m.group(1)}'; reps.append((m.group(0), new)); return new
    line4 = _pow2.sub(m3, line3)
    return line4, reps

def restore(statement):
    out = []; allreps = []
    for line in statement.split('\n'):
        l2, reps = restore_line(line)
        out.append(l2); allreps.extend((line.strip(), a, b) for a, b in reps)
    return '\n'.join(out), allreps

if __name__ == '__main__':
    IDENT = json.load(open('/tmp/train-check-parked-3/identity.json'))
    n = 0
    for tid, info in sorted(IDENT.items()):
        d = json.load(open(info['path'])); p = d['prompt']; stmt = p[p.find('def ' + d['entry_point'] + '('):]
        new, reps = restore(stmt)
        if reps:
            n += 1
            print(f'## {tid}')
            for line, a, b in reps: print(f'   {a!r} -> {b!r}   | {line[:120]}')
    print(f'{n} statements changed')
