"""A portal's CLI runs under Node, or under Bun where there is no Node.

Every search and detail call ran `node`, and nothing installed it: env_check and
setup_env.sh looked for Bun alone. On a computer with Bun and no Node every probe
failed with a FileNotFoundError, read as "left to the scrape", and the round ended
exit 2, "thin market", having searched nothing (2026-10-25). The committed build
(dist/cli.mjs) is plain JavaScript that Bun runs as it is.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import portals  # noqa: E402


@pytest.fixture
def which(monkeypatch):
    found = {}
    portals.runtime.cache_clear()
    monkeypatch.setattr(portals.shutil, "which", lambda name, *a, **k: found.get(name))
    yield found
    portals.runtime.cache_clear()


def test_node_first_then_bun_and_always_two_words(which):
    which.update(node="/usr/bin/node", bun="/home/x/.bun/bin/bun")
    assert portals.runtime() == ("/usr/bin/node", "--no-warnings")
    portals.runtime.cache_clear()
    del which["node"]
    # Two words either way, so a portal's CLI is the third word of every command.
    assert portals.runtime() == ("/home/x/.bun/bin/bun", "run")


def test_neither_is_said_plainly_never_as_a_thin_market(which, monkeypatch, tmp_path, capsys):
    with pytest.raises(portals.NoRuntime, match=r"Node or Bun.*env_check\.py --fix"):
        portals.runtime()
    import scrape_wide
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(tmp_path / "s")])
    assert scrape_wide.main() == 1
    err = capsys.readouterr().err
    assert "need Node or Bun" in err and "env_check.py --fix" in err


def test_every_call_goes_through_it():
    for name in ("scrape_wide.py", "hydrate.py"):
        with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as fh:
            src = fh.read()
        assert '"node"' not in src and "portals.runtime()" in src


@pytest.mark.skipif(not portals.shutil.which("bun"), reason="bun is not here")
def test_bun_runs_the_committed_build():
    import subprocess
    cli = os.path.join(ROOT, ".agents", "skills", "freehire-search", "cli", "dist", "cli.mjs")
    out = subprocess.run([portals.shutil.which("bun"), "run", cli, "--help"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert "freehire-cli" in out.stdout and "USAGE" in out.stdout
    if portals.shutil.which("node"):            # the same answer as Node gives, exit code too
        node = subprocess.run([portals.shutil.which("node"), "--no-warnings", cli, "--help"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert (node.returncode, node.stdout) == (out.returncode, out.stdout)
