#!/usr/bin/env python3
"""An app bug found in the maintainer's own copy, filed as an issue on the app, checked first.

    python3 tools/app_bug.py check <body file> --title "<what breaks, in a few words>"

The maintainer asked (2026-11-11) for the app's bugs to stop being carried between chats by
hand: a chat in their own copy that finds one files it as an issue on the app's public
repository, labelled `from-copy`, where the builder picks it up. The app's repository is
public, so nothing of the person's may reach it: the issue's words are scanned first with the
same checks the push gate runs (`leak_scan.py --text` against a denylist built from this copy,
and `name_guard.py text`), and only words that pass are printed as the issue to create.

A copy that is not the maintainer's never files one: its chats give the person the link the
`app` skill describes ("Something looks wrong"), which they choose to press. This prints
that, and exits 2.

Exit 0 checked (the issue to create is printed and written beside the body file as JSON),
1 refused (what to reword is named, never the private word itself), 2 not the maintainer's
copy, 3 a usage error or a check that could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LABEL = "from-copy"
TOKENS_HOURS = 12            # the denylist is built again after this, as the push gate's is


def _tokens_path() -> str:
    """The denylist kept in this copy's git folder, never in its tree: it is personal data."""
    import sync_app
    gd = sync_app.run_git(ROOT, "rev-parse", "--git-common-dir")
    base = gd.stdout.strip() if gd.returncode == 0 else ""
    if base and not os.path.isabs(base):
        base = os.path.join(ROOT, base)
    return os.path.join(base or tempfile.gettempdir(), "ljs-app-bug-tokens")


def denylist(build=None) -> str:
    """The path of a denylist built from this copy (its profile, tracker, contacts and messages,
    as tools/build_app.py --tokens-out builds the push gate's), built again after TOKENS_HOURS."""
    path = _tokens_path()
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < TOKENS_HOURS * 3600
    if fresh and os.path.getsize(path) > 0:
        return path
    run = build or (lambda out, tokens: subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "build_app.py"), out, "--tokens-out", tokens],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600))
    with tempfile.TemporaryDirectory(prefix="ljs-app-bug-") as out:
        got = run(os.path.join(out, "app"), path)
    if getattr(got, "returncode", 1) != 0 or not os.path.exists(path):
        raise RuntimeError("the list of this copy's private words could not be built")
    return path


def findings(text: str, tokens_file: str) -> list[str]:
    """What in `text` the app must never carry: a word of this copy's (by its number in the
    denylist, never the word), an address, a phone number, a profile link, a name the app has
    never carried. [] when it may be filed."""
    import leak_scan
    with open(tokens_file, encoding="utf-8") as fh:
        tokens = leak_scan.tokens_from(fh.read().splitlines())
    with tempfile.TemporaryDirectory(prefix="ljs-app-bug-") as d:
        p = os.path.join(d, "issue.txt")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        out = list(leak_scan.scan_text([p], tokens))
        guard = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "name_guard.py"), "text", p],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120)
    if guard.returncode != 0:
        out += [ln for ln in (guard.stdout + guard.stderr).splitlines() if ln.strip()]
    return out


def issue(title: str, body: str, version: str) -> dict:
    """The issue as GitHub's issue tool takes it (method create)."""
    import app_setup
    owner, name = app_setup.APP_REPO.rstrip("/").split("/")[-2:]
    foot = f"\n\n---\nFiled from the maintainer's own copy, on version {version or 'unknown'}."
    return {"owner": owner, "repo": name, "title": title.strip(), "body": body.strip() + foot,
            "labels": [LABEL]}


def main(argv=None, build=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="scan an issue's words and print the issue to create")
    c.add_argument("body", help="a file holding what happened, the steps and the version")
    c.add_argument("--title", required=True)
    a = ap.parse_args(argv)
    import sync_app
    if not sync_app.maintainers():
        print("app_bug: this copy is not the app's maintainer's, so it files nothing itself. Give "
              "the person the link the app skill describes (chat.md, \"Something looks wrong\"), "
              "which they choose to press.")
        return 2
    try:
        with open(a.body, encoding="utf-8") as fh:
            body = fh.read()
    except OSError as e:
        print(f"app_bug: cannot read {a.body}: {e}")
        return 3
    if not a.title.strip() or not body.strip():
        print("app_bug: say what breaks in the title and what happened in the body.")
        return 3
    try:
        found = findings(a.title + "\n\n" + body, denylist(build))
    except Exception as e:  # noqa: BLE001  a check that could not run files nothing
        print(f"app_bug: nothing filed: {e}")
        return 3
    if found:
        print("app_bug: nothing filed. The issue would carry something of this copy's; reword "
              "these lines without any name, employer, place, address or message of theirs, "
              "then check it again:")
        for f in found:
            print(f"  {f}")
        return 1
    try:
        import release
        version = release.newest_section()[0]
    except Exception:  # noqa: BLE001  no CHANGELOG to read
        version = ""
    got = issue(a.title, body, version)
    out = os.path.splitext(a.body)[0] + ".issue.json"
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1)
    print(f"app_bug: checked. Create it with GitHub's issue tool (method create) using {out}, "
          f"labelled {LABEL}, then say in one line that it is filed for the app. Never with "
          "anything added after this check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
