def exact_period(tail):
    n = len(tail)
    for p in range(20, min(6000, n // 2) + 1):
        if tail[-p:] == tail[-2 * p:-p]: return p
    return None
def line_cycle(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for k in range(1, min(400, len(lines) // 2) + 1):
        if lines[-k:] == lines[-2 * k:-k]: return k, lines
    return None, lines
def rep_score(text, tail=6000):
    lines = [l.strip() for l in text[-tail:].split('\n') if l.strip()]
    if len(lines) < 5: return 0.0
    return 1 - len(set(lines)) / len(lines)
def classify(text):
    if not text or not text.strip(): return 'not_classifiable', None
    p = exact_period(text[-12000:])
    if p: return 'exact_loop', text[-p:]
    k, lines = line_cycle(text)
    if k: return 'line_loop', '\n'.join(lines[-k:])
    if rep_score(text) > 0.5: return 'high_repetition', None
    return 'progressing', None
def loop_start(text, cls, unit):
    if unit is None: return None
    probe = unit[:200] if cls == 'exact_loop' else unit.split('\n')[0]
    return text.find(probe)
def is_pure_repetition(cls): return cls in ('exact_loop', 'line_loop', 'high_repetition')
