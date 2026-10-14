"""Builds the two site pages: the authored shells under ``site/`` in the repository plus the data bundles, into one
output directory (``docs/site/`` by default), one directory per page under its public name.

What travels is what each page's own code fetches, and nothing else: the page's ``index.html``, the scripts and the
stylesheet it names (the shared kit files under ``site/kit/`` copied beside it), and ``data/`` holding the manifest
and the files the manifest names. Paths inside a page are relative to the page's root, so a copy serves from any
directory. Before the build is done the copy is checked: every asset the page names exists, every literal fetch in
its scripts resolves, every data file parses as JSON, no path leaves the page and no address names a host, and every
script passes ``node --check`` when node is installed. The same inputs build the same bytes: no clock, no stamp.

Command line: ``cmr site --data data --out docs/site [--fit <fit>] [--shells <dir>] [--no-node]``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

from .data import load_fit, load_registry, require_names
from .site_data import write_bundles

PAGES = ("capability-vs-reliability", "failure-vs-difficulty")
KIT_DIR = "kit"
TEXT_SUFFIXES = (".html", ".js", ".css")

ASSET_RX = re.compile(r"""<(?:script|link)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
FETCH_LITERAL_RX = re.compile(r"""fetch\(\s*(?:MOUNT\s*\+\s*)?["']([^"']+)["']""")
HOST_RX = re.compile(r"""https?://(?!www\.w3\.org/)""", re.I)   # the SVG namespace is a name, not an address
ABSOLUTE_RX = re.compile(r"""(?:\b(?:src|href)\s*=\s*|fetch\(\s*)["']/""", re.I)


class SiteError(Exception):
    """A copy that does not satisfy the page checks; the message lists every problem."""


def default_shells() -> Path:
    """The authored shells in a checkout of the repository: ``site/`` beside ``src/``."""
    return Path(__file__).resolve().parents[3] / "site"


def shell_assets(index_html: str) -> list[str]:
    """The scripts and stylesheets a page's HTML names, in order, without duplicates."""
    seen: list[str] = []
    for m in ASSET_RX.finditer(index_html):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def copy_shell(shells: Path, page: str, page_out: Path) -> list[str]:
    """Copy a page's ``index.html`` and every asset it names into ``page_out``; an asset comes from the page's own
    directory or from the shared kit directory. Returns the copied names."""
    src_dir = shells / page
    index = src_dir / "index.html"
    if not index.exists():
        raise SiteError(f"{page}: no shell at {index}")
    page_out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(index, page_out / "index.html")
    copied = ["index.html"]
    for name in shell_assets(index.read_text(encoding="utf-8")):
        if "/" in name or name.startswith("."):
            raise SiteError(f"{page}: index.html names {name!r}; a page's assets sit beside it, named without a path")
        for candidate in (src_dir / name, shells / KIT_DIR / name):
            if candidate.exists():
                shutil.copyfile(candidate, page_out / name)
                copied.append(name)
                break
        else:
            raise SiteError(f"{page}: index.html names {name!r}, which is neither in {src_dir} nor in {shells / KIT_DIR}")
    return copied


def node_available() -> bool:
    return shutil.which("node") is not None


def check_page(page_dir: Path, use_node: bool = True) -> list[str]:
    """Every problem with a built page, as one line each; an empty list is a pass."""
    problems: list[str] = []
    page = page_dir.name
    index = page_dir / "index.html"
    if not index.exists():
        return [f"{page}: no index.html"]
    html = index.read_text(encoding="utf-8")
    for name in shell_assets(html):
        if not (page_dir / name).exists():
            problems.append(f"{page}: index.html names {name}, which is not in the copy")
    texts = [p for p in sorted(page_dir.iterdir()) if p.suffix in TEXT_SUFFIXES]
    for path in texts:
        text = path.read_text(encoding="utf-8")
        if HOST_RX.search(text):
            problems.append(f"{page}/{path.name}: names a host (http:// or https://)")
        if ABSOLUTE_RX.search(text):
            problems.append(f"{page}/{path.name}: a path starting with / leaves the page; paths are relative to the page's root")
        if path.suffix == ".js":
            for m in FETCH_LITERAL_RX.finditer(text):
                target = page_dir / m.group(1)
                if not target.exists():
                    problems.append(f"{page}/{path.name}: fetches {m.group(1)}, which is not in the copy")
            if use_node and node_available():
                r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
                if r.returncode != 0:
                    problems.append(f"{page}/{path.name}: node --check failed: {(r.stderr or r.stdout).strip()[:400]}")
    manifest = page_dir / "data" / "manifest.json"
    if not manifest.exists():
        problems.append(f"{page}: no data/manifest.json")
    else:
        try:
            man = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{page}: data/manifest.json does not parse: {e}")
            man = {}
        for key, name in (man.get("files") or {}).items():
            f = page_dir / "data" / name
            if not f.exists():
                problems.append(f"{page}: the manifest names {name} for {key}, which is not in the copy")
                continue
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                problems.append(f"{page}: data/{name} does not parse: {e}")
    return problems


def page_bytes(page_dir: Path) -> int:
    return sum(p.stat().st_size for p in page_dir.rglob("*") if p.is_file())


def build_site(data: Path, out: Path, fit: str | None = None, shells: Path | None = None, use_node: bool = True) -> dict:
    """Build both pages under ``out`` from the shells and the published tables; raise ``SiteError`` when a page fails
    its checks. Returns a report: per page the files copied, the bundle manifest and the size in bytes."""
    data, out = Path(data), Path(out)
    shells = Path(shells) if shells else default_shells()
    if not shells.exists():
        raise SiteError(f"no shells directory at {shells}; pass --shells with the repository's site/ directory")
    fit_ = load_fit(data, fit)
    registry = load_registry(data)
    require_names(registry, fit_.arms)   # before anything is written: a refused build leaves no copy behind
    report: dict = {"fit": fit_.name, "pages": {}}
    for page in PAGES:
        page_out = out / page
        if page_out.exists():
            shutil.rmtree(page_out)
        report["pages"][page] = {"files": copy_shell(shells, page, page_out)}
    manifests = write_bundles(fit_, registry, out)
    problems: list[str] = []
    for page in PAGES:
        page_out = out / page
        report["pages"][page]["manifest"] = manifests[page]
        report["pages"][page]["bytes"] = page_bytes(page_out)
        problems.extend(check_page(page_out, use_node=use_node))
    report["node_checked"] = bool(use_node and node_available())
    if problems:
        raise SiteError("\n".join(problems))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmr site", description="build the two site pages from the shells and the published tables")
    parser.add_argument("--data", default="data", help="the data directory (results/published/<fit>/ and runs/registry/ under it)")
    parser.add_argument("--fit", default=None, help="the published fit to build from; the newest when not given")
    parser.add_argument("--out", default="docs/site", help="where the two page directories are written")
    parser.add_argument("--shells", default=None, help="the authored shells; the repository's site/ directory when not given")
    parser.add_argument("--no-node", action="store_true", help="skip node --check on the scripts")
    args = parser.parse_args(argv)
    try:
        report = build_site(Path(args.data), Path(args.out), args.fit, Path(args.shells) if args.shells else None, use_node=not args.no_node)
    except SiteError as e:
        print(f"cmr site: the copy failed its checks:\n{e}")
        return 1
    for page, r in report["pages"].items():
        print(f"{page}: {len(r['files'])} shell files, {len(r['manifest']['files'])} data files, {r['bytes'] / 1e6:.1f} MB -> {Path(args.out) / page}")
    print("scripts checked with node" if report["node_checked"] else "node not found: the scripts' syntax was not checked")
    return 0
