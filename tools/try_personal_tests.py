#!/usr/bin/env python3
"""A person's own tests, run against this app tree before it reaches them.

    python3 tools/try_personal_tests.py <their repo> [--ref origin/master]

The maintainer runs it on their own repo before every release (MAINTAINING.md,
"Releases"): 3.5.0 moved the employer boards into openroles and broke 48 of the
maintainer's own tests, which nobody ran until the next sync did.

It copies that repo at `--ref` into a temporary directory, keeps only its personal
files (tools/personal_paths.py), puts this app tree (HEAD) in place of the rest the way
a sync does, runs its profile/tests there and prints what the sync would say. Nothing in either repository is changed. Exit 0 when they pass, 1 when some
fail, 2 when they could not be run.
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))


def _extract(repo: str, ref: str, into: str, paths: tuple = ()) -> None:
    tar = subprocess.run(["git", "-C", repo, "archive", "--format=tar", ref, *paths],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(into, filter="data") if sys.version_info >= (3, 12) else t.extractall(into)


def _drop_app_files(root: str) -> None:
    """Remove every file of the copy that is the app's, so one this release deleted is
    gone, as after a sync, and only the person's own files remain."""
    from personal_paths import is_personal
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            if not is_personal(os.path.relpath(path, root).replace(os.sep, "/")):
                os.remove(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo", help="the person's repository, read only")
    ap.add_argument("--ref", default="origin/master")
    a = ap.parse_args(argv)
    import sync_app
    with tempfile.TemporaryDirectory(prefix="ljs_try_") as tmp:
        try:
            _extract(a.repo, a.ref, tmp)
            _drop_app_files(tmp)
            _extract(HERE, "HEAD", tmp)
        except (subprocess.CalledProcessError, OSError, tarfile.TarError) as e:
            print(f"try_personal_tests: could not copy the trees: {e}", file=sys.stderr)
            return 2
        if not os.path.isdir(os.path.join(tmp, "profile", "tests")):
            print("try_personal_tests: no profile/tests in that repo")
            return 0
        saved = {k: os.environ.pop(k) for k in ("LJS_PROFILE", "LJS_STATE") if k in os.environ}
        try:
            failures = sync_app.own_test_failures(tmp)
        finally:
            os.environ.update(saved)
        if failures is None:
            print("try_personal_tests: the tests could not be run", file=sys.stderr)
            return 2
        if not failures:
            print("Their own tests pass on this tree.")
            return 0
        print(sync_app.own_tests_report(failures, tmp))
        return 1


if __name__ == "__main__":
    sys.exit(main())
