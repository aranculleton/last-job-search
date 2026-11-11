#!/usr/bin/env python3
"""Publish the newest CHANGELOG version as a release, once, when its PR lands.

Every person's repo follows the app's newest vX.Y.Z tag (tools/sync_app.py). The tag
used to be made by hand on the GitHub website after the release PR merged, a step
nothing reminded anyone of: 3.3.0 sat merged and unpublished, and a session cannot push
a tag. .github/workflows/release.yml runs this on every push to master that touches
CHANGELOG.md, so merging the release PR is the release.

    python3 tools/release.py cut X.Y.Z --headline "<one plain sentence for the person>"
    python3 tools/release.py newest            # the version, its date, and whether it is tagged
    python3 tools/release.py notes [X.Y.Z]     # the release notes a person reads
    python3 tools/release.py notes X.Y.Z --full    # the whole CHANGELOG section
    python3 tools/release.py publish           # tag and publish the newest, if it has no tag yet

`cut` names and dates the version on its own pull request, before that pull request's last
push, so merging it is the release (4.15.0 took a second pull request and two hours for the
rename alone). It renames [Unreleased] to [X.Y.Z] with today's date (UTC), opens a fresh
empty [Unreleased] above it and writes the headline as the section's first entry: the one
line a person who updates when they choose is told about the version (tools/sync_app.py,
brings()). It refuses when [Unreleased] is empty, when X.Y.Z is not newer than the newest
release, when the headline is longer than 140 characters or is not one plain sentence, and
when docs/NEXT_BUILDER.md does not name X.Y.Z yet. It never commits.

The notes are short on purpose: one line per change, its headline from the CHANGELOG, a
few plain words where a change needs the person, and one closing line on what to do. The
CHANGELOG keeps the detail, for the sessions that work on the app; the release page held
the whole section once, and to a person it read as walls of text.

It never moves, replaces or deletes a tag. A version already tagged (by hand, or by an
earlier run) is not tagged again, and one no newer than the newest tag is not released:
a fix to an old section's wording is not a release. The newest release's notes are
rewritten when they differ from what this file now makes of its section.

A release ships with the snapshot of its own public names (tools/public_names.py), which
the release PR writes, so the next release is checked against the names people have. This
job's checkout is thrown away with it, so a snapshot written here would be lost: publish
says when the release went out without one, and fails, after tagging, never before.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
HEAD = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - (\d{4}-\d{2}-\d{2})\s*$", re.M)


def sections(text: str | None = None) -> list[dict]:
    """Every released section, newest first: {"version", "date", "notes"}."""
    if text is None:
        with open(CHANGELOG, encoding="utf-8") as fh:
            text = fh.read()
    out = []
    for m in HEAD.finditer(text):
        end = re.compile(r"^## \[", re.M).search(text, m.end())
        body = text[m.end():end.start() if end else len(text)].strip()
        out.append({"version": ".".join(m.group(1, 2, 3)), "date": m.group(4), "notes": body})
    return out


_GROUP = {"Added": "New", "Fixed": "Fixed", "Changed": "Changed", "Removed": "Removed"}


def _needs(ids: list[str]) -> str:
    """"you" when any of these profile upgrades asks the person, "nobody" when they apply
    themselves, "" for none known."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import profile_upgrades
        found = [profile_upgrades.by_id(i) for i in ids if any(
            u.id == i for u in profile_upgrades.REGISTRY)]
    except Exception:  # noqa: BLE001  the notes never fail on a lookup
        return ""
    if not found:
        return ""
    return "you" if any(u.needs == "you" for u in found) else "nobody"


MAX_PER_GROUP = 8
CHANGELOG_URL = "https://github.com/aranculleton/last-job-search/blob/master/CHANGELOG.md"


def short(notes: str) -> str:
    """The release notes a person reads, from a CHANGELOG section."""
    groups: list[tuple[str, list[str]]] = []
    asks = set_up = 0
    entries: list[tuple[str, str]] = []           # (group, the entry's whole text)
    group = ""
    for line in notes.splitlines():
        h = re.match(r"^###\s+(.+?)\s*$", line)
        if h:
            group = _GROUP.get(h.group(1), h.group(1))
            continue
        if line.startswith("- "):
            entries.append((group, line[2:]))
        elif entries and line.startswith("  "):
            entries[-1] = (entries[-1][0], entries[-1][1] + " " + line.strip())
    for group, text in entries:
        m = re.match(r"\*\*(.+?)\*\*", text)
        head = (m.group(1) if m else re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]).strip()
        # Every line a sentence, however its heading ended ("...them:", "...found").
        head = head.rstrip(":;, ") + ("" if head.rstrip(":;, ").endswith((".", "!", "?")) else ".")
        up = re.search(r"Profile upgrade:\s*([^.(]*)", text)
        ids = re.findall(r"[a-z][a-z0-9-]+", up.group(1)) if up else []
        need = _needs(ids)
        if need == "you":
            asks += 1
            head += " (Claude asks you once)"
        elif need == "nobody":
            set_up += 1
            head += " (set up for you)"
        if not groups or groups[-1][0] != group:
            groups.append((group, []))
        groups[-1][1].append(head)
    out = []
    for group, heads in groups:
        # A big release is still a page someone reads: the first few of each kind (the
        # CHANGELOG puts the ones a person notices first), then a count.
        shown = heads[:MAX_PER_GROUP]
        more = len(heads) - len(shown)
        out += ([f"**{group}**"] if group else []) + [f"- {h}" for h in shown]
        out += ([f"- And {more} more ({CHANGELOG_URL})."] if more else []) + [""]
    # "Sets it up" only where there is something to set up: a release of fixes alone is
    # simply taken.
    out.append("What to do: nothing. Your next chat takes this update"
               + (" and sets it up" if asks or set_up else "")
               + (f", and asks you {asks} short question{'s' if asks != 1 else ''} once."
                  if asks else "."))
    return "\n".join(out)


def _gh(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["gh", *args]
    if os.environ.get("GITHUB_REPOSITORY"):
        cmd += ["--repo", os.environ["GITHUB_REPOSITORY"]]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _key(version: str) -> tuple:
    return tuple(int(x) for x in version.split("."))


def tags(root: str = ROOT) -> list[str]:
    out = subprocess.run(["git", "-C", root, "ls-remote", "--tags", "--refs", "origin", "v*"],
                         capture_output=True, text=True, check=True, timeout=60,
                         encoding="utf-8", errors="replace").stdout
    return [ln.split("refs/tags/", 1)[1] for ln in out.splitlines() if "refs/tags/" in ln]


# ------------------------------------------------------------------ cutting a version

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
UNRELEASED = re.compile(r"^## \[Unreleased\][^\n]*\n", re.M)
NEXT_BUILDER = os.path.join("docs", "NEXT_BUILDER.md")
HEADLINE_MAX = 140


def headline_problem(headline: str) -> str:
    """Why `headline` cannot open a version, or "". It is the one line a person who chose to
    update when they say is told (sync_app.brings), so it is one plain sentence they can read:
    sync_app leaves out, for anyone but the maintainer, a line that opens on a tool's name or
    mentions the maintainer, and cuts one past 140 characters."""
    h = headline.strip()
    if not h:
        return "the headline is empty: write one plain sentence for the person"
    if "\n" in h:
        return "the headline runs over more than one line: make it one sentence"
    if len(h) > HEADLINE_MAX:
        return (f"the headline is {len(h)} characters, and a person is told at most "
                f"{HEADLINE_MAX}: shorten it")
    if "*" in h or "`" in h:
        return "the headline has bold marks or code in it: write it as plain words"
    if "maintainer" in h.lower():
        return "the headline is about the maintainer, so a person would never be told it"
    if re.search(r"[.!?]\s+\S", h):
        return "the headline is more than one sentence: keep the first, put the rest below it"
    return ""


def _local_tags(root: str) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", root, "tag", "-l", "v*"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return r.stdout.split() if r.returncode == 0 else []


def _newest(versions) -> str:
    good = [v for v in versions if VERSION.match(v)]
    return max(good, key=_key) if good else ""


def _groups(body: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """A section's body as (the lines before its first ### heading, [(heading, lines)])."""
    lead: list[str] = []
    groups: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith("### "):
            groups.append((line[4:].strip(), []))
        elif groups:
            groups[-1][1].append(line)
        else:
            lead.append(line)
    return lead, groups


def _block(lines: list[str]) -> str:
    return "\n".join(lines).strip("\n")


def cut_text(text: str, version: str, headline: str, day: str) -> str:
    """CHANGELOG.md's text with [Unreleased] named `version` and dated `day`, a fresh empty
    [Unreleased] above it, and `headline` its first entry: the first under its Changed
    heading, which opens the section."""
    m = UNRELEASED.search(text)
    end = re.compile(r"^## \[", re.M).search(text, m.end())
    stop = end.start() if end else len(text)
    lead, groups = _groups(text[m.end():stop])
    changed = next((i for i, (name, _) in enumerate(groups) if name == "Changed"), None)
    first = [f"- **{headline.strip()}**"]
    if changed is not None:
        rest = _block(groups.pop(changed)[1])
        first += [rest] if rest else []
    parts = ["### Changed\n\n" + "\n".join(first)]
    if _block(lead):
        parts.append(_block(lead))
    parts += [f"### {name}\n\n{_block(lines)}" for name, lines in groups]
    section = f"## [{version}] - {day}\n\n" + "\n\n".join(parts) + "\n"
    return text[:m.start()] + "## [Unreleased]\n\n" + section + ("\n" + text[stop:] if end else "")


def cut(version: str, headline: str, root: str = ROOT, day: str | None = None) -> int:
    """Name and date [Unreleased] as `version`, headed by `headline`. 0 when done, 1 with one
    plain line saying why not. Never commits."""
    if not VERSION.match(version or ""):
        print(f"release: {version!r} is not a version number like 4.15.1")
        return 1
    why = headline_problem(headline)
    if why:
        print(f"release: nothing changed: {why}.")
        return 1
    path = os.path.join(root, "CHANGELOG.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = UNRELEASED.search(text)
    if not m:
        print("release: CHANGELOG.md has no [Unreleased] section to name.")
        return 1
    end = re.compile(r"^## \[", re.M).search(text, m.end())
    if not re.search(r"^- ", text[m.end():end.start() if end else len(text)], re.M):
        print("release: nothing changed: [Unreleased] has no entries, so there is nothing to "
              "release.")
        return 1
    known = [s["version"] for s in sections(text)] + [t[1:] for t in _local_tags(root)]
    try:
        known += [t[1:] for t in tags(root)]
    except (OSError, subprocess.SubprocessError):
        print("release: the app's releases on GitHub could not be read from here, so "
              f"{version} is checked against the CHANGELOG and this copy's own tags only.")
    newest = _newest(known)
    if newest and _key(version) <= _key(newest):
        print(f"release: nothing changed: {version} is not newer than {newest}, the newest "
              f"release.")
        return 1
    note = os.path.join(root, NEXT_BUILDER)
    try:
        with open(note, encoding="utf-8") as fh:
            named = re.search(r"(?<![\d.])" + re.escape(version) + r"(?!\d|\.\d)", fh.read())
    except OSError:
        named = None
    if not named:
        print(f"release: nothing changed: docs/NEXT_BUILDER.md does not name {version} yet. "
              f"Write the handover for {version} first, then cut it.")
        return 1
    day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut_text(text, version, headline, day))
    print(f"release: CHANGELOG.md now names {version} ({day}), opening on \"{headline.strip()}\", "
          f"with an empty [Unreleased] above it. Nothing is committed: commit it on this "
          f"version's pull request, and merging that pull request is the release.")
    return 0


def decide(newest: dict | None, existing: list[str]) -> str:
    """"" to publish `newest`, otherwise why not."""
    if not newest:
        return "no released section in CHANGELOG.md (only [Unreleased])"
    if not newest["notes"]:
        return f"{newest['version']} has no notes"
    tag = "v" + newest["version"]
    if tag in existing:
        return f"{tag} is already tagged"
    versions = [t[1:] for t in existing if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if versions and _key(newest["version"]) <= max(map(_key, versions)):
        return f"{tag} is not newer than v{max(versions, key=_key)}"
    return ""


def publish(sha: str | None = None) -> int:
    got = sections()
    newest = got[0] if got else None
    existing = tags()
    why = decide(newest, existing)
    text = short(newest["notes"]) if newest else ""
    if why:
        tag = "v" + newest["version"] if newest else ""
        if newest and tag in existing:
            return refresh(tag, text)
        print(f"release: nothing to publish: {why}")
        return 0
    tag = "v" + newest["version"]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
        notes = fh.name
    r = _gh(["release", "create", tag, "--title", tag, "--notes-file", notes,
             "--target", sha or os.environ.get("GITHUB_SHA") or "master"])
    os.unlink(notes)
    print(f"release: published {tag}" if r.returncode == 0 else (r.stderr or r.stdout))
    return r.returncode or names_kept(tag)


def names_kept(tag: str) -> int:
    """0 when this tree's snapshot of public names is its own, so the next release must
    keep what `tag` ships; otherwise 1, with the command that writes it. It never holds a
    release back: by the time it runs, the tag is out."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import public_names
        behind = public_names.stale()
    except Exception as e:  # noqa: BLE001  the release is out either way: say why, and fail
        print(f"release: {tag} is out, but its public names could not be read: {e}")
        return 1
    if not behind:
        return 0
    print(f"release: {tag} is out, but went without the snapshot of its public names. Run "
          f"`python3 tools/public_names.py snapshot` on master and land it, so the next "
          f"release is checked against what {tag} ships.")
    return 1


def refresh(tag: str, text: str) -> int:
    """The newest release's notes, rewritten when they differ from what its section now
    makes. Only the notes: the tag is never touched."""
    view = _gh(["release", "view", tag, "--json", "body", "--jq", ".body"])
    if view.returncode != 0:
        print(f"release: {tag} is tagged with no release to update")
        return 0
    if view.stdout.strip() == text.strip():
        print(f"release: {tag}'s notes are current")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
        notes = fh.name
    r = _gh(["release", "edit", tag, "--notes-file", notes])
    os.unlink(notes)
    print(f"release: {tag}'s notes rewritten" if r.returncode == 0 else (r.stderr or r.stdout))
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("cut", "newest", "notes", "publish") or "-h" in argv \
            or "--help" in argv:
        print(__doc__.split("\n\n")[2])
        return 0 if argv and ("-h" in argv or "--help" in argv) else 2
    if argv[0] == "cut":
        rest = argv[1:]
        headline = None
        if "--headline" in rest:
            i = rest.index("--headline")
            headline = rest[i + 1] if i + 1 < len(rest) else ""
            rest = rest[:i] + rest[i + 2:]
        if len(rest) != 1 or headline is None:
            print('release: say the version and its headline: python3 tools/release.py cut '
                  'X.Y.Z --headline "<one plain sentence for the person>"')
            return 2
        return cut(rest[0], headline)
    if argv[0] == "publish":
        return publish()
    got = sections()
    if argv[0] == "notes":
        rest = [a for a in argv[1:] if a != "--full"]
        want = rest[0] if rest else (got[0]["version"] if got else "")
        hit = next((s for s in got if s["version"] == want), None)
        if not hit:
            print(f"release: no section {want!r} in CHANGELOG.md", file=sys.stderr)
            return 1
        print(hit["notes"] if "--full" in argv else short(hit["notes"]))
        return 0
    if not got:
        print("release: no released section yet")
        return 0
    n = got[0]
    try:
        why = decide(n, tags())
    except subprocess.CalledProcessError:
        why = "(tags not readable here)"
    print(f"{n['version']} ({n['date']}): " + (why or "not tagged yet: merging it publishes it"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
