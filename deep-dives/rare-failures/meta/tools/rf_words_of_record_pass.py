#!/usr/bin/env python3
"""Usage: python3 rf_words_of_record_pass.py [--dry] [file ...]   (default: the eight documents build_site.py embeds)"""
import os
import re
import sys

L = 'deep-dives/rare-failures'
DEFAULT_FILES = [f'{L}/REPORT.md', f'{L}/REPORT_qwen3.md', f'{L}/REPORT_claude.md', f'{L}/REPORT_deepseek.md',
                 f'{L}/meta/META_REPORT.md', f'{L}/meta/findings/consistency_measure.md', f'{L}/README.md', f'{L}/harness_check.md']

# ordered literal replacements (longest and most specific first)
LITERAL = [
    ('in the the HumanEval/ and Mbpp/ halves of wave 1', 'in both halves of wave 1'),
    ('the HumanEval/ and Mbpp/ halves of wave 1 benchmarks', 'both halves of wave 1'),
    ('the HumanEval/ and Mbpp/ halves of wave 1', 'both halves of wave 1'),
    ('(Qwen2.5-14B HumanEval/ (plus))', '(Qwen2.5-14B, first half of wave 1)'),
    ('## Mbpp/ (plus) vs HumanEval/ (plus)', '## The second half of wave 1 against the first'),
    ('Mbpp/ (plus) mirrors', 'The second half of wave 1 mirrors'),
    ('whole-arm Mbpp/ (plus) pass@1', 'whole-model second-half pass@1'),
    ("the HumanEval/ half's", "the first half's"),
    ("the Mbpp/ half's", "the second half's"),
    ('| HumanEval/ half |', '| first half |'),
    ('| Mbpp/ half |', '| second half |'),
    ('the Mbpp/ wave 1 cell', 'the second-half result'),
    ('over the whole Mbpp/ arm', "over the model's whole second half"),
    ('the HumanEval/ half', 'the first half'),
    ('the Mbpp/ half', 'the second half'),
    ('The HumanEval/ half', 'The first half'),
    ('The Mbpp/ half', 'The second half'),
    ('On HumanEval/,', 'On the first half,'),
    ('On Mbpp/,', 'On the second half,'),
    ('(On Mbpp/', '(On the second half'),
    ('### HumanEval/:', '### The first half:'),
    ('### Mbpp/:', '### The second half:'),
    ('### Per model config, HumanEval/ only', '### Per model config, first half only'),
    ('### Per model config, Mbpp/ only', '### Per model config, second half only'),
    ('### The chat arm: same model, zero truncation', '### The chat model: the same weights without thinking, zero truncation'),
    ('HumanEval/ contributes', 'the first half contributes'),
    ('Mbpp/ contributes', 'the second half contributes'),
    ('Mbpp/ produces', 'The second half produces'),
    ('Mbpp/ also owns', 'The second half also owns'),
    ('HumanEval/ failures, by', 'First-half failures, by'),
    ('Mbpp/ replicates', 'The second half replicates'),
    ('sonnet-think Mbpp/:', 'sonnet-think, second half:'),
    ('Qwen3-1.7B Mbpp/ +0.04', 'Qwen3-1.7B second half +0.04'),
    ('Qwen3-32B HumanEval/ −0.41', 'Qwen3-32B first half −0.41'),
    ('benchmark gradient (Mbpp/', 'gradient between the halves (second half'),
    ('vs HumanEval/ 13%', 'vs first half 13%'),
    ('Mbpp/-thinking notes', 'second-half thinking notes'),
    ('Mbpp/-non-thinking notes', 'second-half non-thinking notes'),
    ('Mbpp/ canonical style', "the second half's canonical style"),
    ('26 of them Mbpp/)', '26 of them on the second half)'),
    ('with an Mbpp/ caveat', 'with a second-half caveat'),
    ('in HumanEval/ (plus) and', 'in both halves of wave 1'),
    ('Mbpp/ (plus) 128 times.', '128 times.'),
    ('the same evalplus and', 'the same test-runner and'),
    ('model × benchmark cells', 'model × half results'),
    ('both benchmarks', 'both halves of wave 1'),
    ('attempts). evalplus runs each solution', 'attempts). The test runner runs each solution'),
    ('recurrence of the evalplus', 'recurrence of the test-runner'),
    ('the evalplus test runner', 'the test runner'),
    ('evalplus (the test runner)', 'the test runner'),
    ('test-setup (evalplus) defect', 'test-setup defect'),
    ('Confirmed evalplus defect ledger', 'Confirmed test-runner defect ledger'),
    ('the confirmed evalplus defect ledger', 'the confirmed test-runner defect ledger'),
    ('known evalplus', 'known test-runner'),
    ('evalplus deep-recursion', 'test-runner deep-recursion'),
    ('the same evalplus and numpy versions', 'the same test-runner and numpy versions'),
    ('evalplus falls back', 'the test runner falls back'),
    ('evalplus runs each solution', 'the test runner runs each solution'),
    ('evalplus compare semantics', "the test runner's compare semantics"),
    ('the evalplus numpy type-check', "the test runner's numpy type-check"),
    ('two evalplus runner bugs', 'two test-runner bugs'),
    ('File the two evalplus bugs upstream (owner: us → evalplus)', 'File the two test-runner bugs upstream (owner: us → its maintainers)'),
    ('evalplus memory-cap kill', 'test-runner memory-cap kill'),
    ('Qwen2.5-era evalplus bug', 'Qwen2.5-era test-runner bug'),
    ('systematic evalplus harness bugs', 'systematic test-runner bugs'),
    ("evalplus's tolerance path", "the test runner's tolerance path"),
    ('| evalplus bug |', '| test-runner bug |'),
    # the retired nouns' articles
    ('an arm', 'a model'), ('An arm', 'A model'),
    ('opus|mbpp', '`opus|mbpp`'), ('opus|humaneval', '`opus|humaneval`'), ('sonnet|mbpp', '`sonnet|mbpp`'),
    ('claude-opus-5|humaneval', '`claude-opus-5|humaneval`'),
    ('corrected_recursion_{humaneval,mbpp}.json', '`corrected_recursion_{humaneval,mbpp}.json`'),
]
# regex fallbacks on what the literals left (prose only)
REGEX = [
    # a source name closing a line whose sentence runs on (the next line opens with the noun)
    (re.compile(r'Its Mbpp/$'), 'Its second-half'),
    (re.compile(r'former Mbpp/$'), 'former second-half'),
    (re.compile(r'102 Mbpp/$'), '102 second-half'),
    (re.compile(r'the 51 Mbpp/$'), 'the 51 second-half'),
    (re.compile(r'counting the HumanEval/$'), 'counting the first-half'),
    (re.compile(r'\bHumanEval/ (?=[a-z])'), 'first-half '),
    (re.compile(r'\bMbpp/ (?=[a-z])'), 'second-half '),
    (re.compile(r'\bHumanEval/(?!\d)'), 'the first half'),
    (re.compile(r'\bMbpp/(?!\d)'), 'the second half'),
    (re.compile(r'\bevalplus\b'), 'the test runner'),
    (re.compile(r'\bEvalPlus\b'), 'the test runner'),
    (re.compile(r'(?<![\w/-])arms(?![\w-]|\.\w)'), 'models'),
    (re.compile(r'(?<![\w/-])Arms(?![\w-]|\.\w)'), 'Models'),
    (re.compile(r'(?<![\w/-])arm(?![\w-]|\.\w)'), 'model'),
    (re.compile(r'(?<![\w/-])Arm(?![\w-]|\.\w)'), 'Model'),
    (re.compile(r'(?<![\w/-])cells(?![\w-]|\.\w)'), 'results'),
    (re.compile(r'(?<![\w/-])Cells(?![\w-]|\.\w)'), 'Results'),
    (re.compile(r'(?<![\w/-])cell(?![\w-]|\.\w)'), 'result'),
    (re.compile(r'(?<![\w/-])Cell(?![\w-]|\.\w)'), 'Result'),
]
SPAN = re.compile(r'`[^`\n]*`')


def rewrite_prose(s):
    for a, b in LITERAL:
        s = s.replace(a, b)
    for rx, b in REGEX:
        s = rx.sub(b, s)
    return s


def rewrite_line(s):
    out, pos = [], 0
    for m in SPAN.finditer(s):
        out.append(rewrite_prose(s[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(rewrite_prose(s[pos:]))
    return ''.join(out)


def rewrite(text):
    out, fenced = [], False
    for line in text.split('\n'):
        if line.lstrip().startswith('```'):
            fenced = not fenced
            out.append(line)
            continue
        out.append(line if fenced else rewrite_line(line))
    return '\n'.join(out)


def main(argv):
    dry = '--dry' in argv
    files = [a for a in argv[1:] if not a.startswith('--')] or DEFAULT_FILES
    total = 0
    for path in files:
        with open(path, encoding='utf-8') as f:
            old = f.read()
        new = rewrite(old)
        if new == old:
            print(f'{os.path.relpath(path, L)}: no change')
            continue
        n = 0
        for i, (a, b) in enumerate(zip(old.split('\n'), new.split('\n')), 1):
            if a != b:
                n += 1
                print(f'{os.path.relpath(path, L)}:{i}:\n  - {a}\n  + {b}')
        total += n
        if not dry:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new)
    print(f"{'would change' if dry else 'changed'} {total} line(s) over {len(files)} file(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
