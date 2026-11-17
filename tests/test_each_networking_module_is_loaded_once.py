"""Each networking module is one module, whichever of its two names imports it (issue 339).

Some tools write `import state` (with tools/network on the path) and others `from network
import state` (with tools/ on it). Both found tools/network/state.py, and Python kept it twice,
as `state` and as `network.state`: a page build loaded five networking modules twice (state,
surface, schema, compose and tone). Each copy had its own caches and settings, so work cached
in one was done again in the other, a test that patched one left the other as it was, and
anything compared by identity differed between the two.

Checked on the real path: the main entry points imported and a page built from the example's
small search, then every file under tools/ that sys.modules holds counted by module, and every
module a loaded tool holds by name checked to be the one sys.modules holds. And an import that
fails part way, as in a copy with no profile yet, leaves neither name holding half a module.
"""
from __future__ import annotations

import glob
import importlib
import os
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
for _p in (os.path.join(TOOLS, "network"), TOOLS, os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_state  # noqa: E402

# The tools a chat or the page starts from, which between them import the networking modules
# by both names.
ENTRY_POINTS = ("app_model", "app", "app_actions", "open_actions", "followup_drafts",
                "followups", "outreach", "holds", "tweak", "what_works", "shown",
                "record_drafts", "voice_check")


# A name under `tools.` is a test's own import (tests/test_verify_pdf.py imports
# `tools.verify_pdf`): the app puts tools/ itself on the path and never loads a tool so. Left
# in, the check read whichever test ran before it in the same worker (CI, 2026-11-17:
# `tools.verify_pdf` and `verify_pdf`), never the build.
def _app_name(name: str) -> bool:
    return not name.startswith("tools.")


def _loaded_twice() -> dict:
    """{file under tools/: its names} for each file sys.modules holds as two modules or more,
    under the names the app imports by."""
    tools = os.path.realpath(TOOLS) + os.sep
    by_file: dict = {}
    for name, mod in list(sys.modules.items()):
        if not _app_name(name):
            continue
        f = getattr(mod, "__file__", None)
        if f and os.path.realpath(f).startswith(tools):
            by_file.setdefault(os.path.realpath(f), {}).setdefault(id(mod), []).append(name)
    return {os.path.relpath(f, ROOT): sorted(n for names in mods.values() for n in names)
            for f, mods in by_file.items() if len(mods) > 1}


def _held_copies() -> list:
    """(tool, the name it holds, the file) for each module a loaded tool holds that is not the
    module sys.modules has for that file: a copy loaded by the other name and kept."""
    tools = os.path.realpath(TOOLS) + os.sep
    by_file = {}
    for name, mod in list(sys.modules.items()):
        if not _app_name(name):
            continue
        f = getattr(mod, "__file__", None)
        if f and os.path.realpath(f).startswith(tools):
            by_file.setdefault(os.path.realpath(f), mod)
    out = []
    for holder in list(by_file.values()):
        for attr, val in list(vars(holder).items()):
            f = getattr(val, "__file__", None) if isinstance(val, types.ModuleType) else None
            if f and os.path.realpath(f) in by_file and by_file[os.path.realpath(f)] is not val:
                out.append((holder.__name__, attr, os.path.relpath(f, ROOT)))
    return out


def test_a_page_build_loads_no_module_twice(tmp_path, monkeypatch):
    st = app_state.small(str(tmp_path / "state"))
    monkeypatch.setenv("LJS_STATE", st)
    monkeypatch.setenv("LJS_COPY", "private")
    monkeypatch.delenv("LJS_TODAY", raising=False)
    for name in ENTRY_POINTS:
        importlib.import_module(name)
    import app_model
    app_model.build(*app_model.clock(app_state.TODAY, app_state.NOW))
    assert _loaded_twice() == {}
    assert _held_copies() == []


def test_every_networking_module_is_one_module_by_both_names():
    """Not only the five a build reached: a module imported by either name is the other."""
    for path in sorted(glob.glob(os.path.join(TOOLS, "network", "*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        plain = importlib.import_module(name)
        assert importlib.import_module("network." + name) is plain, name
        assert sys.modules[name] is sys.modules["network." + name], name


def test_an_import_that_fails_part_way_leaves_neither_name(tmp_path):
    """With no profile yet, importing the message log's module fails part way. Neither name may
    then hold the half-made module: the setup on the page imported it again once the profile
    was written, and was given the half one, with nothing in it past the line that failed."""
    code = ("import sys\n"
            f"sys.path[:0] = [{TOOLS!r}, {os.path.join(TOOLS, 'network')!r}]\n"
            "import person\n"
            "for route in ('from network import state', 'import state'):\n"
            "    try:\n"
            "        exec(route)\n"
            "    except person.NoProfile:\n"
            "        pass\n"
            "    print('state' in sys.modules, 'network.state' in sys.modules)\n")
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no_profile_yet"),
               LJS_STATE=str(tmp_path / "state"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split() == ["False", "False", "False", "False"], r.stdout + r.stderr
