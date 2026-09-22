import sys
from pathlib import Path

_W = Path(__file__).resolve().parent
_FLAG = None   # the drop-in extractor is switched on with EXTRACTOR_DROPIN=1 in the environment
_SHA = (_W / "vendor" / "extractors.sha256").read_text().strip()
sys.path.insert(0, str(_W / "vendor"))
from evalplus.sanitize import sanitize as _pinned  # noqa: E402

DROPIN = __import__("os").environ.get("EXTRACTOR_DROPIN") == "1"
_V2FLAG = None   # the second extractor is switched on with EXTRACTOR_V2=1 in the environment
V2 = __import__("os").environ.get("EXTRACTOR_V2") == "1"
if V2:
    import extractor_v2 as _v2  # noqa: E402
    EXTRACTOR_STAMP = _v2.version_stamp()
    assert EXTRACTOR_STAMP == "v2@06fc16bf54fd0e82", f"vendored extractor_v2 stamp drifted: {EXTRACTOR_STAMP}"
elif DROPIN:
    from extractors import v_pruned as _dropin  # noqa: E402
    EXTRACTOR_STAMP = f"v_pruned@{_SHA}"
else:
    EXTRACTOR_STAMP = "pinned-evalplus@26d6d00b"


def sanitize(text, entrypoint=None):
    if V2:
        return _v2.extract(text, entrypoint)
    if DROPIN:
        return _dropin(text, entrypoint)
    return _pinned(text, entrypoint=entrypoint) if entrypoint else _pinned(text)
