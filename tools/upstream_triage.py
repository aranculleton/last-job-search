#!/usr/bin/env python3
"""Triage upstream commits this fork has not picked up yet.

Emits a Markdown report that sorts the behind-list into "worth reviewing" vs
"probably skip", so a human decides what to merge/port. It never merges,
pushes, or edits anything - it only reads git history and prints. This is the
deliberate report/act boundary: on a fork "applies cleanly" is not "correct" -
a commit for portals the fork dropped can cherry-pick fine and still be wrong,
and that silent-wrong case is worse than a conflict. So the report stops at
ready-to-run cherry-pick lines; a human runs them.

This is the commit-level companion to check_upstream_updates.py. That tool
answers "which of my personalized framework files changed" (version stamps);
this one answers "which upstream commits deserve my attention" (commit history).
Two tools, two questions - each cross-references the other in its output.

Two signals drive the sort:

1. Already applied? A cherry-pick lands with a NEW sha but the same patch, so a
   raw sha comparison misreports it as missing. We compute git patch-ids for the
   fork-only commits and treat any upstream commit whose patch-id (or exact
   subject) matches as already applied.

2. Relevant to this fork? A commit that only touches files this fork deleted
   (e.g. removed demo portals) is almost certainly N/A. Each touched path is read
   against HEAD and the upstream commit the fork was made from: a path that base
   had and HEAD lacks, or one inside a folder that base had and the fork deleted,
   is the fork's removal; a path neither had is new upstream work, worth reviewing.

This app's history starts afresh at 3.0.0 and shares no commit with upstream, so
git finds no merge base. FORK_POINT records the upstream commit it was made from,
and the count starts there: without it, "behind" was every commit upstream ever
made, and every file upstream added since read as one the app removed.
(The new-path and removed-folder reading are from ai-job-search, #585 and #656.)

Usage: python tools/upstream_triage.py [--remote upstream] [--branch master] [--base <sha>]
Exits 0 always (a report, not a gate). Prints a note to stderr and exits 0 if
the upstream ref is unavailable, so a scheduled job degrades gracefully.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace"
    ).stdout


# The upstream commit this app was made from: ai-job-search at v1.7.0 plus the commits
# through PR #413, 2 September 2026 (CHANGELOG-upstream.md says the same).
FORK_POINT = "9833a5dcb75dcbeefb053c09f77639356de834a3"


def rev_list(*specs: str) -> list[str]:
    out = git("rev-list", "--no-merges", *specs).strip()
    return out.splitlines() if out else []


def is_commit(ref: str) -> bool:
    r = subprocess.run(["git", "cat-file", "-e", f"{ref}^{{commit}}"], capture_output=True)
    return r.returncode == 0


def fork_base(ref: str, given: str | None = None) -> tuple[str | None, bool]:
    """(the upstream commit this fork was made from, whether git found it as a merge base).

    --base when given, else the merge base of HEAD and `ref`, else FORK_POINT when this
    clone holds it, else None: then nothing tells a removed path from a new one."""
    if given:
        return git("rev-parse", "--verify", f"{given}^{{commit}}").strip(), False
    try:
        return git("merge-base", "HEAD", ref).strip(), True
    except subprocess.CalledProcessError:
        pass
    return (FORK_POINT, False) if is_commit(FORK_POINT) else (None, False)


def patch_id(sha: str) -> str | None:
    """Stable patch-id for a commit, or None if it has no diff."""
    show = subprocess.run(
        ["git", "show", sha], capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace"
    ).stdout
    r = subprocess.run(
        ["git", "patch-id", "--stable"], input=show, capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    line = r.stdout.strip()
    return line.split()[0] if line else None


def subject(sha: str) -> str:
    return git("show", "-s", "--format=%s", sha).strip()


def files_touched(sha: str) -> list[str]:
    out = git("show", "--name-only", "--format=", sha).strip()
    return [f for f in out.splitlines() if f]


def path_exists(path: str, ref: str = "HEAD") -> bool:
    # The committed tree, not the working tree, is authoritative for "does this fork
    # still ship it".
    r = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"], capture_output=True
    )
    return r.returncode == 0


def removed_here(path: str, base: str | None) -> bool:
    """Whether a path HEAD lacks is one this fork removed: the base had it, or the nearest
    folder above it that either side has is one only the base has (a test upstream added
    to a portal the fork deleted). A path in neither is new upstream work. With no base,
    nothing says it was removed."""
    if base is None:
        return False
    if path_exists(path, base):
        return True
    parts = path.split("/")[:-1]
    for depth in range(len(parts), 0, -1):
        parent = "/".join(parts[:depth])
        if path_exists(parent):
            return False
        if path_exists(parent, base):
            return True
    return False


def disabled_portal_prefixes(root: str = ".agents/skills") -> list[str]:
    """Path prefixes of portal skills this fork ships with `enabled: false`.

    `path_exists` answers "does this fork still ship it", which is the right
    question for a commit touching a file that was deleted. It is the wrong
    question for a portal that is still on disk and switched off: an upstream
    fix to it applies perfectly here and means nothing. The four Danish portals
    sat here switched off until 2026-10 (they are deleted now), and every
    upstream fix to one arrived in the weekly report under "worth reviewing",
    which is how a report gets skimmed and then ignored.

    Read from the SKILL.md rather than from a list in this file, so enabling a
    portal is a one-line change in one place and the triage follows it.
    """
    prefixes = []
    if not os.path.isdir(root):
        return prefixes
    for name in sorted(os.listdir(root)):
        skill = os.path.join(root, name, "SKILL.md")
        if not os.path.isfile(skill):
            continue
        try:
            with open(skill, encoding="utf-8") as fh:
                head = fh.read(4000)
        except OSError:
            continue
        for line in head.splitlines():
            stripped = line.strip()
            if stripped.startswith("enabled:"):
                value = stripped.split(":", 1)[1].split("#", 1)[0].strip().lower()
                if value in ("false", "no", "0"):
                    # Compared with git's paths, which take "/" on every computer: joined
                    # with os.path the prefix was ".agents/skills\\name/" on Windows.
                    prefixes.append(root.replace(os.sep, "/").rstrip("/") + f"/{name}/")
                break
    return prefixes


def remote_slug(remote: str) -> str | None:
    """owner/repo for a GitHub remote, or None if it can't be parsed."""
    try:
        url = git("remote", "get-url", remote).strip()
    except subprocess.CalledProcessError:
        return None
    for sep in ("github.com/", "github.com:"):
        if sep in url:
            path = url.split(sep, 1)[1]
            return path[:-4] if path.endswith(".git") else path
    return None


def load_wontport(path: str) -> list[str]:
    """SHA prefixes the fork has decided never to port; missing file -> []."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return []
    entries = []
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def commit_cell(short: str, sha: str, slug: str | None) -> str:
    if slug:
        return f"[`{short}`](https://github.com/{slug}/commit/{sha})"
    return f"`{short}`"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", default="upstream")
    ap.add_argument("--branch", default="master")
    ap.add_argument("--wontport", default=".github/upstream-wontport.txt")
    ap.add_argument("--base", help="the upstream commit this fork was made from "
                                   "(default: the merge base, else FORK_POINT)")
    args = ap.parse_args()
    ref = f"{args.remote}/{args.branch}"
    slug = remote_slug(args.remote)
    wontport = load_wontport(args.wontport)

    try:
        git("rev-parse", "--verify", ref)
    except subprocess.CalledProcessError:
        print(
            f"note: {ref} not available (add the remote and fetch it first); "
            "nothing to triage.",
            file=sys.stderr,
        )
        print(f"_Upstream ref `{ref}` was not available when this ran._")
        return 0

    base, shared = fork_base(ref, args.base)
    behind = rev_list(ref, "^HEAD", *([f"^{base}"] if base and not shared else []))
    if not behind:
        print(f"Up to date with `{ref}`. Nothing to review. :white_check_mark:")
        _print_crossref(ref)
        return 0

    fork_only = rev_list(f"{ref}..HEAD")
    fork_patch_ids = {p for p in (patch_id(s) for s in fork_only) if p}
    fork_subjects = {subject(s) for s in fork_only}

    disabled = disabled_portal_prefixes()

    review: list[tuple[str, str, str, list[str]]] = []
    skip: list[tuple[str, str, str, str]] = []

    for sha in behind:
        subj = subject(sha)
        short = sha[:9]
        if patch_id(sha) in fork_patch_ids or subj in fork_subjects:
            skip.append((short, sha, subj, "already applied (cherry-picked)"))
            continue
        if any(sha.startswith(e) for e in wontport):
            skip.append((short, sha, subj, "on the fork's won't-port list"))
            continue
        touched = files_touched(sha)
        present = [f for f in touched if path_exists(f) or not removed_here(f, base)]
        # A commit whose only surviving footprint is the changelog is one whose
        # real change lives in files this fork removed - the code doesn't apply,
        # only a doc line would. Low signal; demote it.
        #
        # A portal this fork ships switched off is the same situation wearing a
        # different shape: the file is still here, the commit applies cleanly,
        # and the code it fixes never runs.
        substantive = [f for f in present
                       if f != "CHANGELOG.md"
                       and not any(f.startswith(p) for p in disabled)]
        if touched and not present:
            skip.append((short, sha, subj, "touches only files not in this fork"))
        elif present and not substantive:
            only_disabled = any(f.startswith(p) for f in present for p in disabled)
            skip.append((short, sha, subj,
                         "only touches portals this fork has disabled"
                         if only_disabled else
                         "changelog-only footprint in this fork"))
        else:
            review.append((short, sha, subj, substantive))

    lines: list[str] = []
    since = (f" since `{base[:9]}`, the commit this fork was made from" if base and not shared
             else "")
    lines.append(f"Upstream `{ref}` has **{len(behind)}** commit(s) this fork lacks{since}: "
                 f"**{len(review)}** worth reviewing, **{len(skip)}** probably skippable.")
    if base is None:
        lines.append("")
        lines.append("_This fork and upstream share no history and the commit it was made "
                     "from is not here, so this counts all of upstream's history and cannot "
                     "tell a file the fork removed from a new one. Fetch upstream in full or "
                     "pass `--base <sha>`._")
    lines.append("")
    lines.append("_This is a triage report. Nothing was merged - review and port by hand._")
    lines.append("")

    lines.append("### Worth reviewing")
    if review:
        lines.append("")
        lines.append("| Commit | Subject | Fork files it touches |")
        lines.append("|---|---|---|")
        for short, sha, subj, present in review:
            shown = ", ".join(f"`{p}`" for p in present[:4]) or "_(new/shared paths)_"
            if len(present) > 4:
                shown += f" +{len(present) - 4} more"
            lines.append(f"| {commit_cell(short, sha, slug)} | {subj} | {shown} |")
        # Ready-to-run cherry-pick lines - still information, not action. The
        # report stops here on purpose; a human runs (and verifies) these.
        lines.append("")
        lines.append("<details><summary>Ready-to-run cherry-picks (review each before running)</summary>")
        lines.append("")
        lines.append("```bash")
        for _short, sha, subj, _ in review:
            lines.append(f"git cherry-pick {sha}  # {subj}")
        lines.append("```")
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("")
        lines.append("_None._")
    lines.append("")

    lines.append("### Probably skip")
    if skip:
        lines.append("")
        lines.append("| Commit | Subject | Why |")
        lines.append("|---|---|---|")
        for short, sha, subj, why in skip:
            lines.append(f"| {commit_cell(short, sha, slug)} | {subj} | {why} |")
    else:
        lines.append("")
        lines.append("_None._")

    print("\n".join(lines))
    _print_crossref(ref)
    return 0


def _print_crossref(ref: str) -> None:
    print()
    print(
        "_For personalized-file version stamps (which methodology files changed), "
        f"run `python tools/check_upstream_updates.py --remote {ref.split('/')[0]}`._"
    )


if __name__ == "__main__":
    sys.exit(main())
