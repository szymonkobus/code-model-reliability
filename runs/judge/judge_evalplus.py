#!/usr/bin/env python
import sys
import evalplus.eval as _ev

_Value, _Array = _ev.Value, _ev.Array


def _value_nolock(typecode, *args, **kw):
    kw["lock"] = False
    return _Value(typecode, *args, **kw)


def _array_nolock(typecode, *args, **kw):
    kw["lock"] = False
    return _Array(typecode, *args, **kw)


_ev.Value = _value_nolock
_ev.Array = _array_nolock
PATCH_ID = "nolock-20260903"

import hashlib as _hashlib
import json
import os as _os
import sys as _sys

PREAMBLE_MODE = _os.environ.get("JUDGE_PREAMBLE", "")
FULL_OVERRIDE = _os.environ.get("JUDGE_GT_FULL_OVERRIDE", "")
_ovp = _os.environ.get("HUMANEVAL_OVERRIDE_PATH") or _os.environ.get("MBPP_OVERRIDE_PATH") or ""
if not FULL_OVERRIDE and _ovp.endswith(".scope.override.jsonl"):
    _cand = _os.path.join(_os.path.dirname(_os.path.dirname(_ovp)), "override.jsonl")
    if _os.path.exists(_cand):
        FULL_OVERRIDE = _cand
if FULL_OVERRIDE and not _os.path.exists(FULL_OVERRIDE):
    raise SystemExit(f"judge_evalplus.py: JUDGE_GT_FULL_OVERRIDE={FULL_OVERRIDE!r} does not exist")
if _ovp.endswith(".scope.override.jsonl") and not FULL_OVERRIDE:
    raise SystemExit(f"judge_evalplus.py: scoped override {_ovp!r} without a full override to derive the ground truth from (set JUDGE_GT_FULL_OVERRIDE)")
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _HERE)
import preamble_transform as _pt  # noqa: E402  (shared with the board route; byte-identical copy, sha stamped)

PREAMBLE_RULE = _pt.RULE
PREAMBLE_SHA = _hashlib.sha256(open(_os.path.join(_HERE, "preamble_transform.py"), "rb").read()).hexdigest()

PLUS_FILTER = _os.environ.get("JUDGE_PLUS_FILTER", "")
BOOL_FILTER_FILE = _os.path.join(_HERE, "bool_filtered_tasks.json")
BOOL_FILTER = {}
BOOL_FILTER_SHA = None
if PLUS_FILTER == "bool":
    BOOL_FILTER = {t: {json.dumps(x, sort_keys=True, separators=(",", ":")) for x in v.get("removed_inputs_raw_json", [])}
                   for t, v in json.load(open(BOOL_FILTER_FILE)).get("tasks", {}).items()}
    BOOL_FILTER_SHA = _hashlib.sha256(open(BOOL_FILTER_FILE, "rb").read()).hexdigest()
elif PLUS_FILTER:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_PLUS_FILTER={PLUS_FILTER!r} (only 'bool' is supported)")


KEPT_PLUS_IDX = {}   # task -> indices of the ORIGINAL plus inputs kept by the filter (aligns the derived ground-truth cache)


def _filter_problems(probs):
    """Drop the listed boolean-for-integer plus inputs in place (value match); returns (tasks_touched, inputs_removed)."""
    nt = ni = 0
    for t, removed in BOOL_FILTER.items():
        p = probs.get(t)
        if p is None or not removed: continue
        keep_idx = [i for i, inp in enumerate(p["plus_input"]) if json.dumps(inp, sort_keys=True, separators=(",", ":")) not in removed]
        rem = len(p["plus_input"]) - len(keep_idx)
        if rem: nt += 1; ni += rem; p["plus_input"] = [p["plus_input"][i] for i in keep_idx]; KEPT_PLUS_IDX[t] = keep_idx
    return nt, ni


INPUTS_MODE = _os.environ.get("JUDGE_INPUTS", "")
if INPUTS_MODE == "typed":
    import re as _re
    import mbpp_inputs_deserializer as _des  # noqa: E402
    import declared_input_types_converter as _dit
    TYPED_IDS = set(_des.TYPED_RULE_IDS)
    DECLARED = {}
    try:
        _dj = json.load(open(_os.path.join(_HERE, "declared_input_types.json")))
        DECLARED = {t: v for t, v in _dj.get("tasks", _dj).items() if isinstance(v, dict) and v.get("needs_typed_inputs")}
    except Exception as _e:
        print(f"judge_evalplus.py: declared_input_types.json unreadable ({_e}) — created tasks judged untyped", flush=True)

    def _typed_parent(task_id):
        base = _re.sub(r"~.*$", "", task_id or "")
        try:
            n = int(base.split("/")[-1])
        except ValueError:
            return None
        return n if (base.startswith("Mbpp/") and n in TYPED_IDS) else None

    def _is_typed_task(t):
        return _typed_parent(t) is not None or t in DECLARED

    def _type_problems(probs):
        nt = 0
        for t, p in probs.items():
            n = _typed_parent(t)
            if n is not None:
                p["base_input"] = _des.mbpp_deserialize_inputs(f"Mbpp/{n}", p["base_input"])
                p["plus_input"] = _des.mbpp_deserialize_inputs(f"Mbpp/{n}", p["plus_input"])
                nt += 1
            elif t in DECLARED:
                shapes = DECLARED[t].get("shapes") or []
                conv = lambda inp: [_dit.to_typed(a, shapes[i] if i < len(shapes) else "any") for i, a in enumerate(inp)]
                p["base_input"] = [conv(inp) for inp in p["base_input"]]
                p["plus_input"] = [conv(inp) for inp in p["plus_input"]]
                nt += 1
        return nt
elif INPUTS_MODE:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_INPUTS={INPUTS_MODE!r} (only 'typed' is supported)")

if PREAMBLE_MODE in ("imports", "imports+typing", "typing") or PLUS_FILTER == "bool" or INPUTS_MODE == "typed" or FULL_OVERRIDE:
    import evalplus.evaluate as _E
    _ORIG_TRUSTED_EXEC = _E.trusted_exec
    def _forked_trusted_exec(*_a, **_k):
        import multiprocessing as _mp
        _ctx = _mp.get_context("fork"); _rx, _tx = _ctx.Pipe(duplex=False)
        def _child(conn):
            try: conn.send(("ok", _ORIG_TRUSTED_EXEC(*_a, **_k)))
            except BaseException as _e: conn.send(("err", repr(_e)[:500]))
            finally:
                try: conn.close()
                except Exception: pass
        try: _p = _ctx.Process(target=_child, args=(_tx,)); _p.start(); _tx.close()
        except Exception as _e:
            print(f"GT ISOLATION: fork failed ({_e!r}) — canonical executed in-process (state may leak)", flush=True); return _ORIG_TRUSTED_EXEC(*_a, **_k)
        try: _status, _val = _rx.recv()
        except EOFError: _status, _val = "err", "child exited without a result"
        _p.join()
        if _status == "ok": return _val
        raise RuntimeError(f"GT ISOLATION: canonical failed in the forked child: {_val}")
    _E.trusted_exec = _forked_trusted_exec
    GT_ISOLATION = "fork-v1"
    print("GT ISOLATION fork-v1: ground-truth canonicals execute in forked children (process-global state cannot leak into the judge)", flush=True)
    _PROBLEMS = {}
    _HASH_TAG = ("-boolfiltered" if PLUS_FILTER == "bool" else "") + ("-typed" if INPUTS_MODE == "typed" else "")

    def _capture(fn):
        def wrapped(*a, **kw):
            probs = fn(*a, **kw)
            if PLUS_FILTER == "bool":
                nt, ni = _filter_problems(probs)
                print(f"PLUS FILTER bool (sha {BOOL_FILTER_SHA[:12]}): {ni} boolean-for-integer plus inputs ignored on {nt} of {len(probs)} problems")
            if INPUTS_MODE == "typed":
                nt = _type_problems(probs)
                print(f"TYPED INPUTS: {nt} of {len(probs)} problems deserialized with their MBPP parent's typed rule")
            _PROBLEMS.clear(); _PROBLEMS.update(probs)
            return probs
        return wrapped

    def _rekey(fn):
        def wrapped(*a, **kw):
            return fn(*a, **kw) + _HASH_TAG
        return wrapped

    _E.get_human_eval_plus = _capture(_E.get_human_eval_plus)
    _E.get_mbpp_plus = _capture(_E.get_mbpp_plus)
    GT_PROVENANCE = "original"
    if _HASH_TAG or FULL_OVERRIDE:
        _E.get_human_eval_plus_hash = _rekey(_E.get_human_eval_plus_hash)
        _E.get_mbpp_plus_hash = _rekey(_E.get_mbpp_plus_hash)
        import pickle as _pickle
        from evalplus.data.utils import CACHE_DIR as _CACHE_DIR
        _orig_gt = _E.get_groundtruth

        def _load_override_like_evalplus(_path):
            from evalplus.data.utils import stream_jsonl as _sjl
            _probs = {r["task_id"]: r for r in _sjl(_path)}
            _ds = _sys.argv[_sys.argv.index("--dataset") + 1] if "--dataset" in _sys.argv else ""
            if _ds == "mbpp":
                from evalplus.data.mbpp import mbpp_deserialize_inputs as _mdi
                for _t, _p in _probs.items():
                    _p["base_input"] = _mdi(_t, _p["base_input"]); _p["plus_input"] = _mdi(_t, _p["plus_input"])
            return _probs
        def _derived_groundtruth(problems, hashcode, tasks_only_output_not_none):
            global GT_PROVENANCE
            derived_path = _os.path.join(_CACHE_DIR, f"{hashcode}.pkl")
            base_hash = hashcode
            for tag in ("-boolfiltered", "-typed"): base_hash = base_hash.replace(tag, "")
            orig_path = _os.path.join(_CACHE_DIR, f"{base_hash}.pkl")
            _fresh_ref = False
            _KEEP_REF = (derived_path == orig_path) and _os.path.exists(derived_path)
            if FULL_OVERRIDE:
                # scoped judging: the reference is the FULL leg's original cache (md5 of the full override file = evalplus's key)
                with open(FULL_OVERRIDE, "rb") as _fh: full_hash = _hashlib.md5(_fh.read()).hexdigest()
                orig_path = _os.path.join(_CACHE_DIR, f"{full_hash}.pkl")
                _KEEP_REF = (derived_path == orig_path) and _os.path.exists(derived_path)   # v2 untagged-keep: computed once orig_path is final, before any remove
                if _os.path.exists(derived_path) and not _os.path.exists(derived_path + ".derived") and not _KEEP_REF:
                    try: _os.remove(derived_path)   # a fresh recompute under the trimmed key (pre-fix v17.32 judging): never trust it
                    except Exception: pass
                if not _os.path.exists(orig_path) and not _KEEP_REF:
                    full_problems = _load_override_like_evalplus(FULL_OVERRIDE)   # desfix-v2: as evalplus's loader for this --dataset, never the raw stream
                    print(f"GROUND TRUTH: no original cache for the full leg ({full_hash[:12]}) — computing it once from the full override ({len(full_problems)} tasks); the scoped cache derives from it")
                    _orig_gt(full_problems, full_hash, tasks_only_output_not_none)   # evalplus caches <full_hash>.pkl = the reference for this override
                    _fresh_ref = True
            if _os.path.exists(derived_path) and _os.path.exists(derived_path + ".derived"):
                GT_PROVENANCE = "derived-from-original"
                return _orig_gt(problems, hashcode, tasks_only_output_not_none)
            if _os.path.exists(derived_path) and not _KEEP_REF:
                try: _os.remove(derived_path)
                except Exception: pass
            if not _os.path.exists(orig_path):
                if KEPT_PLUS_IDX or INPUTS_MODE == "typed":
                    _raw = _load_override_like_evalplus(_ovp)   # desfix-v2
                    print(f"GROUND TRUTH: no original cache for this override ({base_hash[:12]}) — computing the reference from the RAW override ({len(_raw)} tasks, unfiltered inputs); this judging derives from it", flush=True)
                    _orig_gt(_raw, base_hash, tasks_only_output_not_none)   # evalplus writes CACHE_DIR/<base_hash>.pkl = orig_path
                    if not _os.path.exists(orig_path):
                        out = _orig_gt(problems, hashcode, tasks_only_output_not_none); GT_PROVENANCE = "fresh-unreferenced"; return out
                else:
                    out = _orig_gt(problems, hashcode, tasks_only_output_not_none)   # fresh; becomes the reference for this override
                    try:
                        with open(orig_path + ".tmp", "wb") as f: _pickle.dump(out, f)
                        _os.replace(orig_path + ".tmp", orig_path)
                    except Exception: pass
                    GT_PROVENANCE = "fresh-as-original"; return out
            with open(orig_path, "rb") as f: od = _pickle.load(f)
            out = {}; _RAW_PROBS = None; _HEALED = [0]
            for t, p in problems.items():
                e = od.get(t)
                if e is None:   # task absent from the original cache (override changed): compute this task fresh
                    ob, obt = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["base_input"], p["entry_point"], record_time=True, output_not_none=p["entry_point"] in tasks_only_output_not_none)
                    op, opt = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["plus_input"], p["entry_point"], record_time=True, output_not_none=p["entry_point"] in tasks_only_output_not_none)
                    out[t] = {"base": ob, "base_time": obt, "plus": op, "plus_time": opt}; continue
                keep = KEPT_PLUS_IDX.get(t)
                plus = list(e["plus"]); plus_time = list(e["plus_time"])
                _need = (max(keep) + 1) if keep else (0 if keep is not None else len(p["plus_input"]))
                if len(plus) < _need or len(plus_time) < _need or (keep is None and len(plus) != len(p["plus_input"])) or len(e["base"]) != len(p["base_input"]):
                    # a poisoned reference entry (written from filtered problems by a pre-fix launcher): HEAL it from the raw override's
                    # problem — original inputs, timings measured now — write the reference back atomically, then derive as usual.
                    if _RAW_PROBS is None:
                        _RAW_PROBS = _load_override_like_evalplus(FULL_OVERRIDE or _ovp)   # desfix-v2
                    _rp = _RAW_PROBS.get(t)
                    if _rp is None:
                        print(f"GROUND TRUTH: cache entry misaligned for {t} and no raw problem to heal from — recomputed fresh on the judged inputs", flush=True)
                        onn = p["entry_point"] in tasks_only_output_not_none
                        ob, obt = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["base_input"], p["entry_point"], record_time=True, output_not_none=onn)
                        op, opt = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["plus_input"], p["entry_point"], record_time=True, output_not_none=onn)
                        out[t] = {"base": ob, "base_time": obt, "plus": op, "plus_time": opt}; continue
                    onn = _rp["entry_point"] in tasks_only_output_not_none
                    ob, obt = _E.trusted_exec(_rp["prompt"] + _rp["canonical_solution"], _rp["base_input"], _rp["entry_point"], record_time=True, output_not_none=onn)
                    op, opt = _E.trusted_exec(_rp["prompt"] + _rp["canonical_solution"], _rp["plus_input"], _rp["entry_point"], record_time=True, output_not_none=onn)
                    print(f"GROUND TRUTH: cache entry misaligned for {t} (cached plus {len(plus)} base {len(e['base'])} vs raw override plus {len(_rp['plus_input'])} base {len(_rp['base_input'])}, keep {None if keep is None else len(keep)}) — reference entry healed from the raw override ({orig_path})", flush=True)
                    e = {"base": ob, "base_time": obt, "plus": op, "plus_time": opt}; od[t] = e; _HEALED[0] += 1
                    plus = list(e["plus"]); plus_time = list(e["plus_time"])
                if keep is not None:
                    plus = [plus[i] for i in keep]; plus_time = [plus_time[i] for i in keep]
                base, base_time = list(e["base"]), list(e["base_time"])
                if INPUTS_MODE == "typed" and _is_typed_task(t):
                    # typed inputs can change the canonical's return form (tuple vs list): recompute OUTPUTS on the typed call, keep the original timings
                    onn = p["entry_point"] in tasks_only_output_not_none
                    base, _ = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["base_input"], p["entry_point"], record_time=True, output_not_none=onn)
                    plus, _ = _E.trusted_exec(p["prompt"] + p["canonical_solution"], p["plus_input"], p["entry_point"], record_time=True, output_not_none=onn)
                assert len(plus) == len(p["plus_input"]) == len(plus_time) and len(base) == len(p["base_input"]) == len(base_time), f"derived ground truth misaligned for {t}"
                out[t] = {"base": base, "base_time": base_time, "plus": plus, "plus_time": plus_time}
            if _HEALED[0] and not _KEEP_REF:   # persist healed reference entries (poisoned by a pre-fix launcher) so later judgings derive with pinned timings; v2 untagged-keep: never on the shared reference itself
                try:
                    with open(orig_path + ".heal.tmp", "wb") as f: _pickle.dump(od, f)
                    _os.replace(orig_path + ".heal.tmp", orig_path)
                    print(f"GROUND TRUTH: {_HEALED[0]} reference entries healed and written back to {orig_path}", flush=True)
                except Exception as _he: print(f"GROUND TRUTH: healed entries not written back ({_he})", flush=True)
            elif _HEALED[0]: print(f"GROUND TRUTH: {_HEALED[0]} healed entries used in memory only (shared reference kept as it stands)", flush=True)
            _os.makedirs(_CACHE_DIR, exist_ok=True)
            if not _KEEP_REF:   # v2 untagged-keep: nothing is written on the shared reference path
                with open(derived_path + ".tmp", "wb") as f: _pickle.dump(out, f)
                _os.replace(derived_path + ".tmp", derived_path)
                open(derived_path + ".derived", "w").write(f"derived from {_os.path.basename(orig_path)} at {__import__('time').strftime('%Y-%m-%dT%H:%M:%SZ', __import__('time').gmtime())}; kept-plus-indices for {len(KEPT_PLUS_IDX)} filtered tasks; typed outputs recomputed with original timings\n")
            GT_PROVENANCE = "fresh-as-original" if _fresh_ref else "derived-from-original"
            print(f"GROUND TRUTH: derived from the original cache {_os.path.basename(orig_path)} (timings kept for every kept input){' — reference computed fresh just now' if _fresh_ref else ''}")
            if _KEEP_REF: print("GROUND TRUTH: shared reference kept as it stands (untagged judging: no remove, no recompute, no write on the reference path)", flush=True)
            return out

        _E.get_groundtruth = _derived_groundtruth
    _orig_load = _E.load_solutions

    def _load_with_preamble(*a, **kw):
        if PREAMBLE_MODE not in ("imports", "imports+typing", "typing"):
            yield from _orig_load(*a, **kw); return
        typing_mode = PREAMBLE_MODE in ("imports+typing", "typing")
        if typing_mode and not hasattr(_pt, "apply_typing"): raise SystemExit(f"judge_evalplus.py: JUDGE_PREAMBLE={PREAMBLE_MODE!r} needs preamble_transform V5-typing (apply_typing) — the copy here has no such function")
        n_pre = 0; n_tasks = sum(1 for p in _PROBLEMS.values() if _pt.leading_imports(p.get("prompt", "")))
        for s in _orig_load(*a, **kw):
            p = _PROBLEMS.get(s.get("task_id"))
            if p is not None and "solution" in s:
                new = _pt.apply_typing(p.get("prompt", ""), s["solution"], with_imports=(PREAMBLE_MODE == "imports+typing")) if typing_mode else _pt.apply(p.get("prompt", ""), s["solution"])
                if new != s["solution"]:
                    s = dict(s); s["solution"] = new; n_pre += 1
            yield s
        if typing_mode: print(f"PREAMBLE {PREAMBLE_MODE} ({getattr(_pt, 'RULE_TYPING', 'V5-typing')}; imports rule {PREAMBLE_RULE}; sha {PREAMBLE_SHA[:12]}): {n_tasks} of {len(_PROBLEMS)} problems carry leading import lines; {n_pre} attempts judged with the typing prelude{' + imports preamble' if PREAMBLE_MODE == 'imports+typing' else ''}")
        else: print(f"PREAMBLE imports ({PREAMBLE_RULE}, sha {PREAMBLE_SHA[:12]}): {n_tasks} of {len(_PROBLEMS)} problems carry leading import lines; {n_pre} attempts judged with the preamble")

    _E.load_solutions = _load_with_preamble
elif PREAMBLE_MODE:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_PREAMBLE={PREAMBLE_MODE!r} (supported: 'imports', 'imports+typing', 'typing')")

COMPARE_MODE = _os.environ.get("JUDGE_COMPARE", "")
if COMPARE_MODE == "normalized-v1":
    import compare_normalize_patch as _cnp
    _cera, _csha = _cnp.apply()
    print(f"COMPARE {_cera}: returned values normalized to plain builtins before the oracle comparison (compare sha {_csha})", flush=True)
elif COMPARE_MODE == "numeric-tolerant-v2":
    import compare_numeric_patch as _cnp2
    _cera, _csha = _cnp2.apply()
    print(f"COMPARE {_cera}: normalized-v1 + float-tolerant exact branch (rtol {_cnp2.RTOL}) (compare sha {_csha})", flush=True)
elif COMPARE_MODE:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_COMPARE={COMPARE_MODE!r} (supported: 'normalized-v1', 'numeric-tolerant-v2')")

STDOUT_COMPARE = _os.environ.get("JUDGE_STDOUT_COMPARE", "")
if STDOUT_COMPARE == "v2-symmetric":
    import stdout_compare_patch as _scp
    _era, _canon_sha = _scp.apply()
    print(f"STDOUT COMPARE {_era}: openr1/ccplus outputs canonicalized on both sides before comparison (stdout_canon sha {_canon_sha})", flush=True)
elif STDOUT_COMPARE:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_STDOUT_COMPARE={STDOUT_COMPARE!r} (only 'v2-symmetric' is supported)")

IO_MODE_SELECT = IO_MODE_SHA = None
if STDOUT_COMPARE == "v2-symmetric":
    import io_mode_patch as _iomp
    IO_MODE_SELECT, IO_MODE_SHA = _iomp.apply()
    print(f"IO MODE {IO_MODE_SELECT}: stdout-canonicalized compare selected by the record's io_mode when present (stdio | function), by task-id prefix otherwise (io_mode sha {IO_MODE_SHA})", flush=True)

TASK_CAP_S = _os.environ.get("JUDGE_TASK_CAP_S", "")
if TASK_CAP_S:
    import inspect as _inspect
    _src = _inspect.getsource(_ev.untrusted_check)
    _needle = 'os.getenv("EVALPLUS_TIMEOUT_PER_TASK", 60)'
    assert _src.count(_needle) == 1, "judge_evalplus.py: untrusted_check source changed — task cap patch needs a look"
    _src = _src.replace(_needle, 'float(os.getenv("EVALPLUS_TIMEOUT_PER_TASK", 60))')
    _ns = dict(vars(_ev)); exec(compile(_src, "<untrusted_check task-cap patch>", "exec"), _ns)
    _ev.untrusted_check = _ns["untrusted_check"]; _ev._UNTRUSTED_CHECK_SRC = _src
    import evalplus.evaluate as _E2; _E2.untrusted_check = _ev.untrusted_check   # evaluate imported the name at import time
    _os.environ["EVALPLUS_TIMEOUT_PER_TASK"] = str(float(TASK_CAP_S))
    print(f"TASK CAP: whole plus-set process cap = min({float(TASK_CAP_S):g} s, sum of per-input limits) + 1")

TIMEOUT_TAG = _os.environ.get("JUDGE_TIMEOUT_TAG", "")
if TIMEOUT_TAG == "v1":
    if not _os.environ.get("JUDGE_TIMEOUT_TAG_PATH"):
        raise SystemExit("judge_evalplus.py: JUDGE_TIMEOUT_TAG=v1 needs JUDGE_TIMEOUT_TAG_PATH (the per-judging side file)")
    import timeout_tag_patch as _ttp
    _tt_era, _tt_sha = _ttp.apply()
    print(f"TIME-LIMIT TAG: era {_tt_era} (sha {_tt_sha}) — per-input kinds/times and set kills recorded to {_os.environ['JUDGE_TIMEOUT_TAG_PATH']}")
elif TIMEOUT_TAG:
    raise SystemExit(f"judge_evalplus.py: unknown JUDGE_TIMEOUT_TAG={TIMEOUT_TAG!r} (only 'v1' is supported)")

if __name__ == "__main__":
    import multiprocessing
    assert multiprocessing.get_start_method(allow_none=True) in (None, "fork"), "nolock wrapper assumes fork start method"
    from evalplus.evaluate import main
    try:   # gt cache pre-existence (label only): does the dataset's untagged cache exist before judging?
        import evalplus.data as _ed
        from evalplus.data.utils import CACHE_DIR as _CD
        _h = _ed.get_human_eval_plus_hash() if _os.environ.get("HUMANEVAL_OVERRIDE_PATH") else _ed.get_mbpp_plus_hash()
        _GT_PRE_EXISTED = _os.path.exists(_os.path.join(_CD, f"{_h}.pkl"))
    except Exception:
        _GT_PRE_EXISTED = True
    FAIL_VECTOR = _os.environ.get("JUDGE_FAIL_VECTOR", "")
    if FAIL_VECTOR == "all-inputs-v1":
        if "--test-details" not in _sys.argv: _sys.argv.append("--test-details")
        print("FAIL VECTOR all-inputs-v1: every attempt runs all its inputs (evalplus --test-details, fast_check off); per-input failures recorded in the time-limit tag side file; eval_results *_fail_tests trimmed to the first failing input after the run")
    elif FAIL_VECTOR:
        raise SystemExit(f"judge_evalplus.py: unknown JUDGE_FAIL_VECTOR={FAIL_VECTOR!r} (only 'all-inputs-v1' is supported)")
    main()
    if FAIL_VECTOR == "all-inputs-v1":
        try:
            _argv = _sys.argv; _samp = _argv[_argv.index("--samples") + 1] if "--samples" in _argv else None
            if _samp and _samp.endswith(".jsonl"):
                _rp = _samp.replace(".jsonl", "_eval_results.json")
                if not _os.path.exists(_rp): _rp = _samp.replace(".jsonl", ".eval_results.json")
                _er = json.load(open(_rp)); _n_trim = 0
                for _t, _atts in (_er.get("eval") or {}).items():
                    for _r in _atts:
                        for _s in ("base", "plus"):
                            _ft = _r.get(f"{_s}_fail_tests")
                            if isinstance(_ft, list):
                                _r[f"{_s}_n_fail_inputs"] = len(_ft)
                                if len(_ft) > 1: _r[f"{_s}_fail_tests"] = _ft[:1]; _n_trim += 1
                _er["fail_vector"] = "all-inputs-v1"
                with open(_rp + ".tmp", "w") as _fh: json.dump(_er, _fh)
                _os.replace(_rp + ".tmp", _rp)
                print(f"FAIL VECTOR: eval_results *_fail_tests trimmed to the first failing input on {_n_trim} attempt-suites (counts kept in *_n_fail_inputs) → {_rp}")
        except Exception as _e:
            print(f"FAIL VECTOR: eval_results post-pass failed ({type(_e).__name__}: {_e}) — file left as evalplus wrote it (full raw fail_tests)")
    if IO_MODE_SELECT:   # io_mode_select / io_mode_sha into the eval_results top level (make_attempt_frag copies them into judge_knobs)
        try:
            _argv = _sys.argv; _samp = _argv[_argv.index("--samples") + 1] if "--samples" in _argv else None
            if _samp and _samp.endswith(".jsonl"):
                _rp = _samp.replace(".jsonl", "_eval_results.json")
                if not _os.path.exists(_rp): _rp = _samp.replace(".jsonl", ".eval_results.json")
                _er = json.load(open(_rp)); _er["io_mode_select"] = IO_MODE_SELECT; _er["io_mode_sha"] = IO_MODE_SHA
                with open(_rp + ".tmp", "w") as _fh: json.dump(_er, _fh)
                _os.replace(_rp + ".tmp", _rp)
                print(f"IO MODE: eval_results stamped io_mode_select={IO_MODE_SELECT} io_mode_sha={IO_MODE_SHA} → {_rp}")
        except Exception as _e:
            print(f"IO MODE: eval_results stamp failed ({type(_e).__name__}: {_e}) — rows carry no io_mode_select")
    # GT provenance sidecar for the consumer's judge_knobs.gt_cache (original | derived-from-original | fresh-as-original | fresh)
    try:
        _argv = _sys.argv; _samp = _argv[_argv.index("--samples") + 1] if "--samples" in _argv else None
        if _samp and _samp.endswith(".jsonl"):
            _prov = globals().get("GT_PROVENANCE")
            if not _prov:   # no derivation wrapper installed: 'original' only if the dataset's cache existed BEFORE this run, else this run computed it (first judging of this override = the reference)
                _prov = "original" if globals().get("_GT_PRE_EXISTED", True) else "fresh-as-original"
            open(_samp[:-6] + ".gt_cache", "w").write(_prov + "\n")
            try:
                import socket as _sk
                open(_samp[:-6] + ".gt_pkl", "w").write(f"{_h}.pkl@{_sk.gethostname()}\n")
            except Exception: pass
            try:
                import pickle as _pk, hashlib as _hl, json as _js, time as _tm, socket as _sk2
                _pkl = _os.path.join(_CD, f"{_h}.pkl")
                _mtl = float(_argv[_argv.index("--min-time-limit") + 1]) if "--min-time-limit" in _argv else 1.0
                _fac = float(_argv[_argv.index("--gt-time-limit-factor") + 1]) if "--gt-time-limit-factor" in _argv else 4.0
                _par = _argv[_argv.index("--parallel") + 1] if "--parallel" in _argv else _os.environ.get("JUDGE_PARALLEL")
                _pkb = open(_pkl, "rb").read(); _gt = _pk.loads(_pkb)
                _hdr = {"_header": True, "limits_sidecar": "v1", "written_at": _tm.strftime("%Y-%m-%dT%H:%M:%SZ", _tm.gmtime()), "host": _sk2.gethostname(),
                        "parallel": int(_par) if str(_par).isdigit() else _par, "cpus_per_task": _os.environ.get("SLURM_CPUS_PER_TASK"), "hint": _os.environ.get("SLURM_HINT") or "none",
                        "slurm_job": _os.environ.get("SLURM_JOB_ID"), "min_time_limit_s": _mtl, "factor": _fac, "rule": "per-input limit = max(min_time_limit_s, factor × canonical time)",
                        "gt_cache": _prov, "gt_pkl": f"{_h}.pkl", "gt_pkl_sha16": _hl.sha256(_pkb).hexdigest()[:16], "tasks": len(_gt)}
                _lp = _samp[:-6] + ".limits.ndjson"
                with open(_lp + ".tmp", "w") as _lf:
                    _lf.write(_js.dumps(_hdr) + "\n")
                    for _tid, _e in _gt.items():
                        _bt = [float(x) for x in (_e.get("base_time") or [])]; _pt = [float(x) for x in (_e.get("plus_time") or [])]
                        _lf.write(_js.dumps({"task_id": _tid, "base_gt_time_s": _bt, "plus_gt_time_s": _pt, "base_limit_s": [max(_mtl, _fac * t) for t in _bt], "plus_limit_s": [max(_mtl, _fac * t) for t in _pt]}) + "\n")
                _os.replace(_lp + ".tmp", _lp)
                print(f"LIMITS SIDECAR v1: {len(_gt)} tasks → {_lp} (min_time_limit {_mtl}, factor {_fac}, gt {_prov} {_h[:12]}.pkl)", flush=True)
            except Exception as _e:
                print(f"LIMITS SIDECAR: not written ({_e!r}) — verdicts unaffected", flush=True)
    except Exception:
        pass
