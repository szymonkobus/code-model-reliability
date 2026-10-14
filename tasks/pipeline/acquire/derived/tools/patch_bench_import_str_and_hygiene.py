#!/usr/bin/env python3
"""class 4  a str-returning method's digit-string outputs were stored as ints ('00000' -> 0, '123' -> 123): the dataset's
           output text and the reference's printed result both went through literal_eval. Seven landed records
           (convert-a-number-to-hexadecimal, reverse-only-letters, to-lower-case, reformat-phone-number, zigzag-conversion,
           convert-to-base-2, encode-number). Fix: when the starter's return annotation is exactly `str`, an expected output
           is the quoted literal's value or else the raw text as written, and the reference's result text is the value.
  class 5  scrape hygiene: literal backslash-r pairs ('Example 1:\\r', 20 statements) broke the example extractor on 29
           records (official tests promoted as base_input although the statement carries examples); zero-width U+200B
           (25), non-breaking spaces and tabs (50) sat in docstrings. Fix: clean the statement before example extraction
           and the docstring; the counts go to the conversion metrics (statement_cleaned).
"""
import argparse, ast, difflib, hashlib, os, shutil, sys

OLD_MD5 = "53365292"

EDITS = [
    # E1 run_and_compare: signature + docstring
    ('def run_and_compare(full_code, entry_point, inputs, expected, timeout=10.0):\n'
     '    """Sandbox-run entry_point on inputs; compare to expected values.\n'
     '    Returns (ok_all, mismatches, errors, max_t). Child returns repr() for\n'
     '    non-str results; compare via literal_eval when possible."""\n',
     'def run_and_compare(full_code, entry_point, inputs, expected, timeout=10.0,\n'
     '                    str_return=False):\n'
     '    """Sandbox-run entry_point on inputs; compare to expected values.\n'
     '    Returns (ok_all, mismatches, errors, max_t). Child returns repr() for\n'
     '    non-str results; compare via literal_eval when possible, or as the text\n'
     '    itself when str_return (a str-returning method: \'00000\' stays \'00000\';\n'
     '    train-check-lcds-m9-2, 25 Sep 2026)."""\n'),
    # E2 run_and_compare: the result parse
    ('        got_raw = r["out"]\n'
     '        exp = expected[i]\n'
     '        try:\n'
     '            got = ast.literal_eval(got_raw)\n'
     '        except (ValueError, SyntaxError):\n'
     '            got = got_raw          # plain string return\n',
     '        got_raw = r["out"]\n'
     '        exp = expected[i]\n'
     '        if str_return:\n'
     '            got = got_raw          # the text is the value for a str return\n'
     '        else:\n'
     '            try:\n'
     '                got = ast.literal_eval(got_raw)\n'
     '            except (ValueError, SyntaxError):\n'
     '                got = got_raw          # plain string return\n'),
    # E3 helpers: return_annotation_is_str + parse_str_output, before _HELPER_NAMES
    ('_HELPER_NAMES = ("ListNode", "TreeNode", "list_node", "tree_node", "is_same_list", "is_same_tree")\n',
     'def return_annotation_is_str(starter_code, fname):\n'
     '    """True when the starter\'s return annotation is exactly str. Expected\n'
     '    outputs and the reference\'s results are then kept as strings: the\n'
     '    dataset writes a digit string unquoted and literal_eval made it an int\n'
     '    (\'00000\' -> 0) on seven landed records — convert-a-number-to-hexadecimal,\n'
     '    to-lower-case, zigzag-conversion, ... (train-check-lcds-m9-2, 25 Sep 2026)."""\n'
     '    m = re.search(_RET_ANN_RE_T % re.escape(fname), starter_code or "")\n'
     '    return bool(m) and m.group(1).strip() == "str"\n'
     '\n'
     '\n'
     'def parse_str_output(s, strict=False):\n'
     '    """An expected output of a str-returning method: the quoted literal\'s\n'
     '    value; None for the null words; else the raw text AS WRITTEN, whitespace\n'
     '    included (the dataset writes most string outputs unquoted — \'123-456-78\',\n'
     '    \'\\\\nnew\\\\nline\\\\n\' — and an unquoted digit string is the string itself,\n'
     '    never the number). strict (statement examples): only a quoted string\n'
     '    literal is accepted; anything else raises, and the example is skipped\n'
     '    as before (an unterminated capture such as \'"110"\\\\nExplantion: ...\' must\n'
     '    never become an expected value)."""\n'
     '    t = s or ""\n'
     '    ts = t.strip()\n'
     '    if ts in ("None", "null"):\n'
     '        return None\n'
     '    try:\n'
     '        v = ast.literal_eval(ts)\n'
     '    except (ValueError, SyntaxError):\n'
     '        if strict:\n'
     '            raise\n'
     '        return t\n'
     '    if strict and not isinstance(v, str):\n'
     '        raise ValueError("example output of a str method is not a string literal")\n'
     '    return v if isinstance(v, str) else t\n'
     '\n'
     '\n'
     '_HELPER_NAMES = ("ListNode", "TreeNode", "list_node", "tree_node", "is_same_list", "is_same_tree")\n'),
    # E4 convert_leetcode: ret_is_str beside ret_forbids_none
    ('    ret_forbids_none = return_annotation_forbids_none(rec.get("starter_code") or "", fname)\n',
     '    ret_forbids_none = return_annotation_forbids_none(rec.get("starter_code") or "", fname)\n'
     '    ret_is_str = return_annotation_is_str(rec.get("starter_code") or "", fname)\n'
     '    m["return_is_str"] = ret_is_str\n'),
    # E5 dataset pairs
    ('            exp = parse_literal(io["output"])\n',
     '            exp = (parse_str_output(io["output"]) if ret_is_str\n'
     '                   else parse_literal(io["output"]))\n'),
    # E6 statement examples (strict: a quoted literal or the example is skipped)
    ('            exp = parse_literal(mm.group(2))\n',
     '            exp = (parse_str_output(mm.group(2), strict=True) if ret_is_str\n'
     '                   else parse_literal(mm.group(2)))\n'),
    # E10 dataset pairs whose recorded output is the generator\'s own error text
    ('    dropped_none = 0\n'
     '    for io in rec.get("input_output") or []:\n'
     '        try:\n'
     '            args = parse_kwarg_call(io["input"], params)\n',
     '    dropped_none = dropped_error = 0\n'
     '    for io in rec.get("input_output") or []:\n'
     '        out_txt = io.get("output") if isinstance(io, dict) else None\n'
     '        if isinstance(out_txt, str) and out_txt.lstrip().startswith("Error:"):\n'
     '            dropped_error += 1   # the dataset generator\'s own exception text\n'
     '            continue             # (reformat-phone-number, number = "1": IndexError)\n'
     '        try:\n'
     '            args = parse_kwarg_call(io["input"], params)\n'),
    ('    m.update(n_base=len(base_in), n_plus=len(plus_in),\n'
     '             n_dropped_nonliteral=dropped, n_example_parse_fail=ex_bad,\n'
     '             n_dropped_none_expected=dropped_none)\n',
     '    m.update(n_base=len(base_in), n_plus=len(plus_in),\n'
     '             n_dropped_nonliteral=dropped, n_example_parse_fail=ex_bad,\n'
     '             n_dropped_none_expected=dropped_none,\n'
     '             n_dropped_error_output=dropped_error)\n'),
    ('    if dropped_none:\n'
     '        warnings.append("dropped %d dataset IO pair(s) whose expected output "\n'
     '                        "is None against a return annotation that excludes "\n'
     '                        "None (reference fell through: guarantee-violating "\n'
     '                        "inputs, out of domain by construction)" % dropped_none)\n',
     '    if dropped_none:\n'
     '        warnings.append("dropped %d dataset IO pair(s) whose expected output "\n'
     '                        "is None against a return annotation that excludes "\n'
     '                        "None (reference fell through: guarantee-violating "\n'
     '                        "inputs, out of domain by construction)" % dropped_none)\n'
     '    if dropped_error:\n'
     '        warnings.append("dropped %d dataset IO pair(s) whose recorded output "\n'
     '                        "is the generator\'s own error text (\'Error: ...\'): "\n'
     '                        "inputs the official solution could not handle, out "\n'
     '                        "of domain by construction" % dropped_error)\n'),
    # E11 the example extractor stops at a misspelt Explanation ("Explantion" on convert-to-base-2)
    ('    r"Input:?\\s*(.+?)\\s*Output:?\\s*(.+?)(?=\\s*(?:Explanation|Example|"\n',
     '    r"Input:?\\s*(.+?)\\s*Output:?\\s*(.+?)(?=\\s*(?:Explan\\w*|Example|"\n'),
    # E7 the reference run of convert_leetcode
    ('    ok, mism, errs, tmax = run_and_compare(prompt + canonical, fname,\n'
     '                                           inputs, expected)\n'
     '    m.update(ref_max_test_s=tmax)\n',
     '    ok, mism, errs, tmax = run_and_compare(prompt + canonical, fname,\n'
     '                                           inputs, expected,\n'
     '                                           str_return=ret_is_str)\n'
     '    m.update(ref_max_test_s=tmax)\n'),
    # E8 convert_leetcode: clean the statement first
    ('    m = {"source": "leetcode"}\n'
     '    desc = rec.get("problem_description") or ""\n',
     '    m = {"source": "leetcode"}\n'
     '    desc, m["statement_cleaned"] = clean_statement(\n'
     '        rec.get("problem_description") or "")\n'),
    # E9 clean_statement, before parse_literal
    ('def parse_literal(s):\n',
     '_ZERO_WIDTH = "\\u200b\\u200c\\u200d\\ufeff"\n'
     '\n'
     '\n'
     'def clean_statement(desc):\n'
     '    """Scrape hygiene before example extraction and the docstring (train-\n'
     '    check-lcds-m9-2/-3, 25 Sep 2026): literal backslash-r pairs (\'Example\n'
     '    1:\\\\r\' — they broke the example extractor on 29 landed records, whose\n'
     '    base_input became promoted official tests), real carriage returns,\n'
     '    zero-width characters (U+200B), non-breaking spaces and tabs. Returns\n'
     '    (text, counts by class); an empty dict when nothing was there."""\n'
     '    out, n = desc or "", {}\n'
     '    for name, old, new in (("literal_cr", "\\\\r", ""), ("cr", "\\r", ""),\n'
     '                           ("nbsp", "\\u00a0", " "), ("tab", "\\t", " ")):\n'
     '        c = out.count(old)\n'
     '        if c:\n'
     '            n[name] = c\n'
     '            out = out.replace(old, new)\n'
     '    zw = sum(out.count(ch) for ch in _ZERO_WIDTH)\n'
     '    if zw:\n'
     '        n["zero_width"] = zw\n'
     '        for ch in _ZERO_WIDTH:\n'
     '            out = out.replace(ch, "")\n'
     '    return out, n\n'
     '\n'
     '\n'
     'def parse_literal(s):\n'),
]


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("--out", default=""); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check and not a.out:
        sys.exit("REFUSED: give --out <staged path> or --check")
    raw = open(a.src, "rb").read()
    if not md5(raw).startswith(OLD_MD5):
        sys.exit("REFUSED: %s has md5 %s, not %s..." % (a.src, md5(raw), OLD_MD5))
    src = raw.decode("utf-8")
    new = src
    for i, (o, n) in enumerate(EDITS, 1):
        c = new.count(o)
        if c != 1:
            sys.exit("REFUSED: edit E%d anchor occurs %d times, not once:\n%s" % (i, c, o[:200]))
        new = new.replace(o, n)
    ast.parse(new)
    diff = "".join(difflib.unified_diff(src.splitlines(True), new.splitlines(True), "bench_import.py (%s)" % md5(raw)[:8], "patched"))
    print(diff)
    print("patched md5 %s | %d -> %d bytes | %d edits" % (md5(new.encode("utf-8")), len(raw), len(new.encode("utf-8")), len(EDITS)))
    if a.check:
        print("--check: nothing written")
        return
    if os.path.abspath(a.out) == os.path.abspath(a.src):
        sys.exit("REFUSED: --out is the source itself; the file of record moves only by the adopt step")
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    shutil.copymode(a.src, tmp)
    os.replace(tmp, a.out)
    print("staged:", a.out, "md5", md5(open(a.out, "rb").read()))


if __name__ == "__main__":
    main()
