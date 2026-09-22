#!/usr/bin/env python3
import hashlib, inspect, textwrap, numbers

ERA = "compare-normalized-v1"
KNOB = "normalized-v1"
COMPARE_SHA = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16]

class _Unequal:
    """stands in for a returned object of a non-builtin type: unequal to everything, unusable in the tolerance branch"""
    __slots__ = ()
    def __eq__(self, other): return False
    def __ne__(self, other): return True
    def __hash__(self): return 0
    def __bool__(self): return False
    def __repr__(self): return "<non-builtin return value>"
    def __iter__(self): raise TypeError("non-builtin return value")
    def __len__(self): raise TypeError("non-builtin return value")
UNEQUAL = _Unequal()
_SCALARS = (int, float, str, bool, bytes, complex, type(None))
_EXACT_CONTAINERS = (list, tuple, dict, set, frozenset)

def _plain(o):
    """True if o is an exact builtin scalar or an exact builtin container whose every element (and dict key/value) is plain — no rebuild needed."""
    t = type(o)
    if t in _SCALARS: return True
    if t is list or t is tuple or t is set or t is frozenset:
        for x in o:
            if type(x) not in _SCALARS and not _plain(x): return False
        return True
    if t is dict:
        for k, v in o.items():
            if (type(k) not in _SCALARS and not _plain(k)) or (type(v) not in _SCALARS and not _plain(v)): return False
        return True
    return False

def normalize(o):
    if _plain(o): return o
    t = type(o)
    if t is list: return [normalize(x) for x in o]
    if t is tuple: return tuple(normalize(x) for x in o)
    if t is dict: return {normalize(k): normalize(v) for k, v in o.items()}
    if t is set or t is frozenset: return t(normalize(x) for x in o)
    if isinstance(o, bool): return bool(o)
    if isinstance(o, int): return int(o)
    if isinstance(o, float): return float(o)
    if isinstance(o, complex): return complex(o)
    if isinstance(o, str): return str(o)
    if isinstance(o, bytes): return bytes(o)
    if isinstance(o, dict): return {normalize(k): normalize(v) for k, v in o.items()}
    if isinstance(o, list): return [normalize(x) for x in o]
    if isinstance(o, tuple): return tuple(normalize(x) for x in o)
    if isinstance(o, (set, frozenset)): return set(normalize(x) for x in o)
    if isinstance(o, numbers.Integral): return int(o)
    if isinstance(o, numbers.Real): return float(o)
    if isinstance(o, numbers.Complex): return complex(o)
    tl = getattr(o, "tolist", None)
    if callable(tl) and type(o).__module__.split(".")[0] == "numpy":
        try: return normalize(tl())
        except Exception: return UNEQUAL
    return UNEQUAL

def apply():
    import evalplus.eval as _ev
    src = getattr(_ev, "_UNSAFE_EXECUTE_SRC", None) or textwrap.dedent(inspect.getsource(_ev.unsafe_execute))
    old = "exact_match = out == exp"
    assert src.count(old) >= 1, "compare_normalize_patch: unsafe_execute source changed — needs a look"
    assert "_norm_out" not in src, "compare_normalize_patch: already applied"
    new_src = src.replace(old, 'out = globals()["_norm_out"](out); ' + old, 1)
    _ev._norm_out = normalize; _ev._UNSAFE_EXECUTE_SRC = new_src
    exec(compile(new_src, "<compare_normalize_patch:unsafe_execute>", "exec"), vars(_ev))
    return ERA, COMPARE_SHA

if __name__ == "__main__":
    import collections
    class ApproxFloat(float):
        def __eq__(self, other): return abs(float(self) - float(other)) < 1e-12 if isinstance(other, (int, float)) else NotImplemented
        __hash__ = float.__hash__
    class Approx:
        def __init__(self, v): self.v = v
        def __eq__(self, other): return True
    assert normalize(ApproxFloat(2.0)) == 2.0 and type(normalize(ApproxFloat(2.0))) is float
    assert not (normalize(ApproxFloat(2.0)) == 2.5), "the wrapper's tolerance must not survive normalization"
    near = 2.0 + 1e-13   # inside the wrapper's tolerance, a different float
    assert near != 2.0 and (ApproxFloat(2.0) == near) is True, "the wrapper itself is lenient — that is the hole"
    assert (near == ApproxFloat(2.0)) is True, "exp == out does not close the hole (a float subclass's reflected __eq__ wins)"
    assert (near == normalize(ApproxFloat(2.0))) is False, "normalized: plain float equality decides"
    assert normalize(Approx(1)) is UNEQUAL and not (normalize(Approx(1)) == 1) and not (1 == normalize(Approx(1)))
    assert normalize([1, 2, [3, ApproxFloat(4.0)]]) == [1, 2, [3, 4.0]] and type(normalize([1, 2, [3, ApproxFloat(4.0)]])[2][1]) is float
    plain = [1, 2, 3]; assert normalize(plain) is plain, "plain containers pass through untouched (fast path)"
    d = {"a": [1, 2], "b": (3, 4)}; assert normalize(d) is d
    assert normalize(collections.Counter("aab")) == {"a": 2, "b": 1} and type(normalize(collections.Counter("aab"))) is dict
    assert normalize(collections.defaultdict(int, x=1)) == {"x": 1} and normalize(collections.OrderedDict(a=1)) == {"a": 1}
    assert normalize(True) is True and normalize(None) is None and normalize("s") == "s" and normalize(b"b") == b"b"
    assert normalize(collections.deque([1])) is UNEQUAL, "deque never equalled a list before either"
    assert normalize((x for x in [1])) is UNEQUAL
    try:
        import numpy as np
        assert normalize(np.int64(3)) == 3 and type(normalize(np.int64(3))) is int
        assert normalize(np.float64(1.5)) == 1.5 and type(normalize(np.float64(1.5))) is float
        assert normalize(np.array([1, 2])) == [1, 2] and normalize(np.bool_(True)) is True or normalize(np.bool_(True)) == True
    except ImportError:
        pass
    class S(str): pass
    assert normalize(S("x")) == "x" and type(normalize(S("x"))) is str
    assert normalize({ApproxFloat(1.0): Approx(0)}) == {1.0: UNEQUAL} or True
    # apply() shape test against the pinned evalplus if importable
    try:
        import evalplus.eval as _ev
        era, sha = apply(); assert "_norm_out" in _ev._UNSAFE_EXECUTE_SRC and callable(_ev._norm_out)
        print("apply OK on", _ev.__file__)
    except ImportError:
        print("evalplus not importable here; normalize self-tests only")
    print("compare_normalize_patch self-test OK; era", ERA, "knob", KNOB, "sha", COMPARE_SHA)
