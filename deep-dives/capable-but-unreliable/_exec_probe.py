"""Child process: exec a judged solution, call the entry point on each failing input, report what happens.
stdin: JSON {"solution": str, "entry": str, "inputs": [[args...], ...]}; stdout: JSON list of outcomes."""
import sys, json, signal, resource, io, contextlib
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
d = json.loads(sys.stdin.read()); out = []
class TO(Exception): pass
def alarm(*a): raise TO()
signal.signal(signal.SIGALRM, alarm)
ns = {}
signal.alarm(5)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        exec(d["solution"], ns)
    define = "ok"
except TO: define = "timeout"
except BaseException as e: define = type(e).__name__ + ": " + str(e)[:120]
signal.alarm(0)
if define != "ok":
    print(json.dumps({"define": define, "calls": []})); sys.exit(0)
fn = ns.get(d["entry"])
if not callable(fn):
    print(json.dumps({"define": "entry_missing", "calls": []})); sys.exit(0)
for args in d["inputs"][:3]:
    signal.alarm(5)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r = fn(*args) if isinstance(args, list) else fn(args)
        out.append({"outcome": "returned", "repr": repr(r)[:80]})
    except TO: out.append({"outcome": "timeout"})
    except BaseException as e: out.append({"outcome": "raised", "exc": type(e).__name__, "msg": str(e)[:100]})
    signal.alarm(0)
print(json.dumps({"define": "ok", "calls": out}))
