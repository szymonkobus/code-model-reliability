"""The built copies read headless: both pages draw at desktop and phone width with no console error, no failed request
and no fail line, and the export button produces a file. Needs node and playwright for node with its chromium
(``PLAYWRIGHT_NODE_PATH`` may name the directory holding the playwright module); skipped where they are absent."""

import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time

import pytest

from code_model_reliability.plot.site import build_site

HERE = pathlib.Path(__file__).resolve().parent
SHELLS = HERE.parents[1] / "site"
PAGES = ("capability-vs-reliability", "failure-vs-difficulty")


def playwright_env():
    """The environment that resolves ``require('playwright')`` under node, or None."""
    if shutil.which("node") is None:
        return None
    env = dict(os.environ)
    extra = os.environ.get("PLAYWRIGHT_NODE_PATH")
    if extra:
        env["NODE_PATH"] = extra + ((os.pathsep + env["NODE_PATH"]) if env.get("NODE_PATH") else "")
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True, env=env)
    return env if r.returncode == 0 else None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(playwright_env() is None, reason="node with the playwright module is not installed")
def test_both_pages_render_headless(data_dir, tmp_path):
    env = playwright_env()
    out = tmp_path / "site"
    build_site(data_dir, out, shells=SHELLS, use_node=False)
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(out)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        r = subprocess.run(["node", str(HERE / "render_check.js"), f"http://127.0.0.1:{port}/", str(tmp_path / "shots"), *PAGES],
                           capture_output=True, text=True, env=env, timeout=600)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    rows = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
    assert len(rows) == 2 * len(PAGES), r.stdout + r.stderr
    for row in rows:
        assert row["drawn"], row
        assert not row["fail_line"], row
        assert row["console_errors"] == [] and row["failed_requests"] == [], row
        assert row["chips"] > 0 and row["switches"] > 0, row
        assert row["flags"] >= 1, row                                   # the fixture's failed-gate arm is flagged on its chip
        if row["view"] == "desktop":
            assert row["exported"] and not row["exported"].startswith("FAILED"), row
