"""The extractor the published attempts were judged through, in every version the verdicts rest on: the rule that
takes the program out of a model's reply.

``extract(reply, entry_point)`` is the current version; ``extract_under(stamp)`` gives any published version. A
version is named by a stamp, ``v2@<sha16>``, the first sixteen hex digits of the sha256 of the extractor file's
bytes as it ran, and the registry names the stamp each set's verdict files carry. The modules under
``extractors`` hold the versions, one per stamp; their documentation was rewritten for a reader, so their own byte
stamps are not the published ones, and each module's logic is held to its stamp by ``logic_sha256``, a hash of
the module's syntax tree with comments and docstrings removed, which the tests compare with the values recorded
here.

The judge harness's own sanitizer at the pinned commit, which the generation path applies as it writes a sample,
stays reachable as ``harness_sanitize``: it keeps the longest span of lines that parses and drops a function
without a return statement (so a correct generator function judged as missing), and the published attempts were
re-extracted from their raw replies with these versions before the re-judge.

Reads a reply and an entry-point name. Writes nothing.
"""

from __future__ import annotations

import ast
import hashlib
import os
from typing import Callable

from .extractors import (
    v2_0b0abd79e863a451,
    v2_1f4d747f86f4cf98,
    v2_4ab50996111c1be5,
    v2_90dae7e9e3e530bd,
    v2_9ac5071166f8adaa,
)

VERSIONS = {
    "v2@1f4d747f86f4cf98": v2_1f4d747f86f4cf98,
    "v2@0b0abd79e863a451": v2_0b0abd79e863a451,
    "v2@4ab50996111c1be5": v2_4ab50996111c1be5,
    "v2@90dae7e9e3e530bd": v2_90dae7e9e3e530bd,
    "v2@9ac5071166f8adaa": v2_9ac5071166f8adaa,
}
"""Every published version by stamp, oldest first; the module behind each."""

CURRENT_STAMP = "v2@9ac5071166f8adaa"
"""The current version: the one the wave 2 attempts were landed under."""

PUBLISHED_STAMPS = {
    "v2@1f4d747f86f4cf98": "the first published version, carried by most wave 1 verdict files",
    "v2@0b0abd79e863a451": "adds: an assignment is the entry point's definition only when its value can be a function "
                           "(a literal assigned to the name in a later block no longer displaces the function); some wave 1 verdict files",
    "v2@4ab50996111c1be5": "adds: an unclosed thinking tag is left in place as text instead of swallowing the rest of the reply; "
                           "a reply whose fence lines are stray (a closer left at the end, a fence quoted in a docstring) is read "
                           "whole once those lines are removed; a few wave 1 verdict files",
    "v2@90dae7e9e3e530bd": "adds: a fence opener glued to prose is split onto its own line; a decorator line opens a parse "
                           "segment that runs through the definition it decorates; a few wave 1 verdict files",
    "v2@9ac5071166f8adaa": "adds: an unclosed final block whose last line is a whole statement inside a body is read as cut "
                           "off at the token limit; the wave 2 landings (the current version)",
}
"""What each version added to the one before it, and which published attempts carry it. A verdict stands as
judged under its version; the registry row names the stamps a set's files carry."""

LOGIC_SHA256 = {
    "v2@1f4d747f86f4cf98": "378b2711db09363823bd751b79267f248b416a8735bf1e3da25ca51be3d8c6ae",
    "v2@0b0abd79e863a451": "7b10d608a1e68cc82363956de3bc2c59d4395f793296a99509b7252f8b30a770",
    "v2@4ab50996111c1be5": "9fefd4030b3b58467b624555d1cb4111971b35acec7820e6a1b16b58cfcf7b66",
    "v2@90dae7e9e3e530bd": "92e6363a3c03a63f4bf428c0f0c4f094ada696ccee93aa8ec135524e895081f6",
    "v2@9ac5071166f8adaa": "96cbf459d08b1d6b5794700ae708fae172982b8c49c7e82a9bd099bbd4c6ec37",
}
"""``logic_sha256`` of the file behind each stamp; the tests hold each shipped module to it."""

CURRENT_LOGIC_SHA256 = LOGIC_SHA256[CURRENT_STAMP]

extract = VERSIONS[CURRENT_STAMP].extract
explain = VERSIONS[CURRENT_STAMP].explain
VERSION = VERSIONS[CURRENT_STAMP].VERSION


def extract_under(stamp: str) -> Callable[[str, str], str]:
    """The ``extract`` function of a published version, by stamp; an unknown stamp is an error."""
    return VERSIONS[stamp].extract


def _strip_docstrings(tree):
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                    and isinstance(first.value.value, str):
                del body[0]
    return tree


def _canonical(node):
    """A rendering of a syntax tree that leaves out empty fields, so it is the same across Python versions that add
    optional fields to a node."""
    if isinstance(node, ast.AST):
        parts = []
        for field in node._fields:
            value = getattr(node, field, None)
            if value is None or value == []:
                continue
            parts.append(f"{field}={_canonical(value)}")
        return f"{type(node).__name__}({','.join(parts)})"
    if isinstance(node, list):
        return "[" + ",".join(_canonical(x) for x in node) + "]"
    return repr(node)


def logic_sha256(path: str | None = None) -> str:
    """sha256 over a module's syntax tree with comments and docstrings removed: equal for two files that differ
    only in their documentation. ``path`` defaults to the current version's file."""
    with open(path or os.path.abspath(VERSIONS[CURRENT_STAMP].__file__), "rb") as f:
        source = f.read().decode("utf-8")
    tree = _strip_docstrings(ast.parse(source))
    return hashlib.sha256(_canonical(tree).encode("utf-8")).hexdigest()


def version_stamp() -> str:
    """The byte stamp of the shipped current module (not a published stamp; see the module docstring)."""
    return VERSIONS[CURRENT_STAMP].version_stamp()


def harness_sanitize(text: str, entrypoint: str | None = None) -> str:
    """The judge harness's own sanitizer at the pinned commit, for comparison with ``extract``; needs the harness
    installed (the package's ``judge`` extra)."""
    from evalplus.sanitize import sanitize

    return sanitize(text, entrypoint=entrypoint) if entrypoint else sanitize(text)
