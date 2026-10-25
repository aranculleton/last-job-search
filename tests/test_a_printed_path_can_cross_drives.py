"""On Windows, os.path.relpath raises when its two paths are on different drives (C: and
D:): a round written to the computer's temporary folder from a copy on another drive
crashed on its last line, twice, from two different print lines (2026-10-25). A path the
app prints or records goes through local_path.rel, which falls back to the full path.

The calls left below walk inside one folder (a tree, a checkout), where both paths are on
the same drive by construction. A new call fails here until it is one of those or uses
local_path.rel.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# file -> how many relpath calls it may keep: each walks inside one root it was given.
WALKS_INSIDE_ONE_ROOT = {
    "tools/build_app.py": 2,         # the app's own tree, out_dir under it
    "tools/build_versions.py": 1,    # the app's tracked files, under ROOT
    "tools/followups.py": 1,         # guarded: only when the note is under ROOT
    "tools/leak_scan.py": 1,         # a scanned tree's own files
    "tools/local_path.py": 2,        # rel itself
    "tools/network/state.py": 1,     # a walk of the state folder
    "tools/profile_names.py": 2,     # the app's own files, under ROOT
    "tools/save_state.py": 2,        # the checkout's files, under it
    "tools/setup_state.py": 1,       # the checkout's files, under it
    "tools/sync_app.py": 1,          # the checkout's files, under it
    "tools/try_personal_tests.py": 1,  # the checkout's files, under it
    "tools/what_works.py": 1,        # a walk of the documents folder
}


def test_no_new_relpath_that_can_cross_drives():
    found = {}
    for top in ("tools", "templates"):
        for dp, dns, fns in os.walk(os.path.join(ROOT, top)):
            dns[:] = [d for d in dns if d not in ("openroles", "__pycache__")]
            for fn in fns:
                if fn.endswith(".py"):
                    path = os.path.join(dp, fn)
                    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                    with open(path, encoding="utf-8") as fh:
                        n = len(re.findall(r"os\.path\.relpath\(", fh.read()))
                    if n:
                        found[rel] = n
    extra = {f: n for f, n in found.items() if n > WALKS_INSIDE_ONE_ROOT.get(f, 0)}
    assert not extra, ("use local_path.rel for a path the app prints or records, or add the "
                       f"call here with why both paths share a drive: {extra}")
