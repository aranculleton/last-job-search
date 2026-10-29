"""Every release is checked where people actually run the app, not only where CI does.

On 2026-10-29 a message card fitted a phone in one font and pushed it 37px sideways in
another, the clock-moved check was a release step done by hand and skipped, and the page
wrote "29 oct." inside an English sentence on a French device. tools/everywhere.sh runs the
page in Safari's engine, Firefox, a Mac's and Windows' type, French and German, and the far
time zones, and the rest with the clock moved on, in the far time zones, from an odd folder
and on the newest Python; .github/workflows/everywhere.yml runs it on every release.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "tools", "everywhere.sh")
SRC = open(SH, encoding="utf-8").read()
WF = os.path.join(ROOT, ".github", "workflows", "everywhere.yml")


def test_every_variant_is_there():
    got = subprocess.run(["bash", SH, "list"], capture_output=True, text=True, encoding="utf-8")
    assert got.returncode == 0
    for v in ("safari", "firefox", "mac-type", "windows-type", "french", "german", "ahead", "behind",
              "30-days", "90-days", "400-days", "odd-folder", "newest-python"):
        assert re.search(r"\b" + re.escape(v) + r"\b", got.stdout), v


def test_a_variant_that_cannot_run_is_never_passed():
    assert "SKIP" in SRC and 'EVERYWHERE_STRICT:-}" = 1' in SRC


def test_it_runs_on_every_release_free_and_never_on_a_private_copy():
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load(open(WF, encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert "paths" not in (on.get("pull_request") or {})        # any change can break these
    assert set(wf["jobs"]) == {"page", "suite"}                  # two summaries, never fifteen
    for job in wf["jobs"].values():
        assert "!github.event.repository.private" in job["if"] and "'Release '" in job["if"]
        steps = "\n".join(str(s.get("run", "")) for s in job["steps"])
        assert "tools/everywhere.sh" in steps
        assert any(s.get("env", {}).get("EVERYWHERE_STRICT") == "1" for s in job["steps"])


def test_the_harness_opens_the_page_in_the_engine_language_and_zone_asked():
    js = open(os.path.join(ROOT, "tests", "app_page", "harness.js"), encoding="utf-8").read()
    for name in ("LJS_PW_ENGINE", "LJS_PW_LOCALE", "LJS_PW_TZ"):
        assert name in js


def test_the_page_writes_dates_and_numbers_in_english_on_any_device():
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert "Intl.DateTimeFormat(undefined" not in js and "Intl.NumberFormat(undefined" not in js
    assert ".toLocaleString()" not in js
    assert 'LOC = /^en(-|$)/i.test(l) ? l : "en-GB"' in js
