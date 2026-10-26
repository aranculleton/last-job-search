#!/usr/bin/env python3
"""The public app, checked for the maintainer's own data, from the maintainer's own repo.

The app is public, so anything personal pushed to it is public at once, branches and
history included. Two gates stand in front of it: the leak scan a session runs before
every push (MAINTAINING.md), and the app's CI. CI could only check names through a
LEAK_TOKENS secret somebody had to rebuild and paste in by hand, so it fell behind: on
2026-10-19 it still knew employers the maintainer's own list had since forgotten, and
a list nobody maintains will fall behind again.

This needs no secret and no one. It runs in the maintainer's repo (the one whose GitHub
owner is the app's), where the names are: every sync of that repo builds the denylist
from the profile and the whole history of its state files (tools/build_app.py), fetches
the app's branches, and scans what changed since it last looked: every branch's files,
the commit messages, and the pull requests' titles and descriptions. Nothing is changed
anywhere. A finding is printed for Claude to put in front of the person before anything
else; a clean check says so in one line.

    python3 tools/app_watch.py            # what sync_app.py runs; a no-op in anyone else's repo
    python3 tools/app_watch.py --all      # everything again, and every match listed

Exit 0 clean or not the maintainer's repo, 1 with findings, 2 when the app could not be
reached. What it has scanned is remembered in .git/ljs-app-watch.json, never committed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

APP_URL = "https://github.com/aranculleton/last-job-search"
API = "https://api.github.com/repos/aranculleton/last-job-search/pulls?state=all&sort=updated&direction=desc&per_page=50"
REFS = "refs/ljs-app-watch/"
STATE = "ljs-app-watch.json"
UA = {"User-Agent": "last-job-search-app-watch/1 (+https://github.com/aranculleton/last-job-search)",
      "Accept": "application/vnd.github+json"}


def _git(*args: str, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          input=input, encoding="utf-8", errors="replace")


def app_url() -> str:
    return os.environ.get("LJS_APP_URL") or APP_URL


def _owner(url: str) -> str:
    url = url.strip().removesuffix(".git").rstrip("/")
    parts = url.replace(":", "/").split("/")
    return parts[-2].lower() if len(parts) >= 2 else ""


def is_maintainers() -> bool:
    """This repo is the maintainer's own: its GitHub owner is the app's, and it is not the
    app itself. Only that repo holds the names the app must never carry."""
    origin = _git("remote", "get-url", "origin")
    if origin.returncode != 0:
        return False
    mine, app = origin.stdout.strip().removesuffix(".git").rstrip("/"), app_url().rstrip("/")
    return bool(_owner(mine)) and _owner(mine) == _owner(app) and mine.lower() != app.lower() \
        and os.path.isdir(os.path.join(ROOT, "profile"))


def _example_words() -> str | None:
    """Every word of the app's invented example person, lowercased, when this repo's
    profile is that person; None for anyone else."""
    def name(folder: str) -> str:
        try:
            with open(os.path.join(ROOT, folder, "person.json"), encoding="utf-8") as fh:
                return str((json.load(fh).get("identity") or {}).get("name") or "").strip()
        except (OSError, ValueError, AttributeError):
            return ""
    theirs = name("profile.example")
    if not theirs or name("profile") != theirs:
        return None
    text = []
    for d, _, files in os.walk(os.path.join(ROOT, "profile.example")):
        for n in files:
            try:
                with open(os.path.join(d, n), encoding="utf-8", errors="replace") as fh:
                    text.append(fh.read())
            except OSError:
                pass
    return "\n".join(text).lower()


def _state_path() -> str:
    d = _git("rev-parse", "--git-common-dir").stdout.strip() or ".git"
    return os.path.join(d if os.path.isabs(d) else os.path.join(ROOT, d), STATE)


def _load() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    try:
        with open(_state_path(), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
    except OSError:
        pass


def fetch() -> dict[str, str] | None:
    """Every branch of the app, into a namespace of its own: {branch: sha}, or None."""
    r = _git("fetch", "--quiet", "--no-tags", "--prune", app_url(), f"+refs/heads/*:{REFS}*")
    if r.returncode != 0:
        return None
    out = _git("for-each-ref", "--format=%(refname) %(objectname)", REFS).stdout.split("\n")
    return {line.split()[0][len(REFS):]: line.split()[1] for line in out if line.strip()}


def _blobs(sha: str) -> dict[str, str]:
    """{path: blob sha} for every file in a commit's tree."""
    out = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "-z", sha],
                         capture_output=True).stdout.decode("utf-8", errors="replace")
    blobs = {}
    for entry in out.split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            blobs[path] = parts[2]
    return blobs


def _files_findings(files: dict[str, str], tokens) -> list[str]:
    """Scan these {path: blob} as one tree: each written out at its own path, so the
    path checks (a personal path, a binary) see what they would in a checkout."""
    import leak_scan
    if not files:
        return []
    with tempfile.TemporaryDirectory() as d:
        cat = subprocess.run(["git", "-C", ROOT, "cat-file", "--batch"],
                             input="".join(f"{b}\n" for b in files.values()).encode(),
                             capture_output=True).stdout
        for path in files:
            head, _, cat = cat.partition(b"\n")
            size = int(head.split()[2]) if len(head.split()) == 3 else 0
            data, cat = cat[:size], cat[size + 1:]
            full = os.path.join(d, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(data)
        return leak_scan.scan(d, tokens, leak_scan.load_allow(None), show=True, export=True)


def _text_findings(label: str, text: str, tokens) -> list[str]:
    import leak_scan
    # The app's own owner and name are public, in its address and in every line GitHub
    # writes for a merge ("Merge pull request #7 from <owner>/<branch>"); a file's copy
    # of the address is allowed the same way (leak_scan ALLOW).
    owner = _owner(app_url())
    if owner:
        text = re.sub(rf"(?<![\w.-]){re.escape(owner)}/", " /", text, flags=re.I)
    if not text.strip():
        return []
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, label)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return leak_scan.scan_text([path], tokens, show=True)


PER_PAGE = 50     # API's per_page
# Pages of pull requests read at most in one look: ten requests of the sixty an hour
# GitHub allows a reader with no account, and five hundred pull requests.
MAX_PAGES = 10


def _pull_requests(since: str) -> tuple[list[dict], str]:
    """The app's pull requests updated after `since` (an ISO time), newest first, and ""
    or why they could not all be read. Public data, read with no account.

    One page of fifty was read, so `--all` checked the fifty most recently updated and
    called it everything, and a look after more than fifty had changed moved its mark
    past the ones it never read. Pages are read until one reaches what was read before."""
    got: list = []
    for page in range(1, MAX_PAGES + 1):
        try:
            req = urllib.request.Request(f"{API}&page={page}", headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001  unreachable is reported, never fatal
            return [], f"pull request text not checked ({type(exc).__name__})"
        got += batch
        if len(batch) < PER_PAGE or str(batch[-1].get("updated_at") or "") <= since:
            return [p for p in got if str(p.get("updated_at") or "") > since], ""
    return ([p for p in got if str(p.get("updated_at") or "") > since],
            f"over {MAX_PAGES * PER_PAGE} pull requests changed; the rest wait for the next look")


def watch(everything: bool = False) -> tuple[list[str], str]:
    """(findings, summary). Findings name where, with the matched text: this runs only in
    the maintainer's private repo, for the maintainer."""
    import build_app
    import leak_scan
    when = build_app.recorded()
    # A copy set up as the app's own invented person (its profile copied from
    # profile.example/, to try the app) records that person's words, and the app carries
    # them on purpose: they are never this repo's to leak (2026-10-25).
    example = _example_words()
    ours = len(when)
    if example is not None:
        when = {t: w for t, w in when.items() if t.lstrip("=").lower() not in example}
    as_example = ours - len(when)
    denylist = list(when)
    digest = hashlib.sha1("\n".join(denylist).encode("utf-8")).hexdigest()[:16]
    # Numbered straight from the list, one number an entry: written to a file and read
    # back, an entry holding a line break (a quoted tracker cell) took two, and every
    # finding after it was judged by its neighbour's date.
    tokens = leak_scan.tokens_from(denylist
                                   + os.environ.get("LJS_LEAK_TOKENS", "").splitlines())
    heads = fetch()
    if heads is None:
        return [], f"the app could not be reached at {app_url()}"
    # A branch already merged into master adds nothing master's history does not hold,
    # and that history is permanent: what is worth knowing today is what is new.
    master = heads.get("master", "")
    heads = {b: s for b, s in heads.items() if b == "master" or not master
             or _git("merge-base", "--is-ancestor", s, master).returncode != 0}
    state = _load()
    fresh = everything or state.get("tokens") != digest
    seen = set() if fresh else set(state.get("blobs") or [])
    old_tips = [] if fresh else [s for s in state.get("tips") or []
                                 if _git("cat-file", "-e", s).returncode == 0]
    findings: list[str] = []
    # Every file any branch holds, each distinct one read once: the branches share
    # nearly all of them, and a tree takes seconds.
    todo: dict[str, tuple[str, str]] = {}
    queued: set[str] = set()
    for branch, sha in sorted(heads.items()):
        for path, blob in _blobs(sha).items():
            if blob not in seen and blob not in queued:
                queued.add(blob)
                todo[f"{branch}\0{path}"] = (blob, branch)
    by_branch: dict[str, dict[str, str]] = {}
    for key, (blob, branch) in todo.items():
        by_branch.setdefault(branch, {})[key.split("\0", 1)[1]] = blob
    # Which file version, commit or pull request each finding came from: those are read
    # again on the next look. Marking them read with the rest reported a leak once, and
    # every later sync said "clean" while it was still public (2026-10-25).
    source: dict[str, str] = {}
    for branch, files in sorted(by_branch.items()):
        for f in _files_findings(files, tokens):
            findings.append(f"branch {branch}: {f}")
            hit = next((b for path, b in files.items() if f.startswith(path + ":")), "")
            source[findings[-1]] = "blob " + hit
    # Commit messages new since the last look, on any branch, scanned as one text, and
    # those that had a finding last time, while a branch still holds them.
    new = _git("rev-list", *heads.values(), "--not", *old_tips).stdout.split() if heads else []
    held = [] if fresh else [c for c in state.get("held_commits") or [] if c not in new and any(
        _git("merge-base", "--is-ancestor", c, h).returncode == 0 for h in heads.values())]
    new += held
    commits = len(new)
    if new:
        log = _git("log", "--no-walk=unsorted", "--format=%H%x00%B%x01", *new).stdout
        lines, owner = [], []
        for entry in log.split("\x01"):
            if "\x00" not in entry:
                continue
            c, msg = entry.strip("\n").split("\x00", 1)
            for ln in msg.splitlines() or [""]:
                lines.append(ln)
                owner.append(c)
        for f in _text_findings("messages", "\n".join(lines), tokens):
            n = int(f.split(":", 2)[1]) if f.split(":", 2)[1].isdigit() else 1
            findings.append(f"commit {owner[n - 1][:12]} message: {f.split(': ', 1)[-1]}")
            source[findings[-1]] = "commit " + owner[n - 1]
    since = "" if fresh else str(state.get("prs_since") or "")
    prs, unread = _pull_requests(since)
    for p in prs:
        text = f"{p.get('title') or ''}\n{p.get('body') or ''}"
        for f in _text_findings("pr", text, tokens):
            findings.append(f"pull request #{p.get('number')}: {f.split(': ', 1)[-1]}")
            source[findings[-1]] = "pr " + str(p.get("updated_at") or "")
    # An entry the app carried before this repo recorded it is the app's own word, not
    # the person's: set aside the way the leak scan before a push sets it aside.
    findings, aside = build_app.without_aside(findings, denylist, when, f"{REFS}master", ROOT)
    still = {source.get(f, "") for f in findings}
    seen |= {b for b, _ in todo.values() if "blob " + b not in still}
    newest = max([str(p.get("updated_at") or "") for p in prs] + [since])
    # The pull request mark stops short of the oldest one with a finding, so it is read
    # again; once edited clean, its new time moves the mark past it.
    leaky = sorted(k[3:] for k in still if k.startswith("pr ") and k[3:])
    if leaky:
        newest = max([since] + [str(p.get("updated_at") or "") for p in prs
                                if str(p.get("updated_at") or "") < leaky[0]])
    _save({"tokens": digest, "blobs": sorted(seen), "tips": sorted(set(heads.values())),
           "held_commits": sorted(k[7:] for k in still if k.startswith("commit ")),
           "prs_since": newest if not unread else since})
    summary = (f"{len(heads)} branch(es), {len(todo)} new file version(s), {commits} commit "
               f"message(s) and {len(prs)} pull request(s) checked against {len(denylist)} "
               "entries from this repo" + (f"; {unread}" if unread else "")
               + (f"; {len(aside)} set aside, carried by the app before this repo recorded "
                  "them" if aside else "")
               + (f"; {as_example} set aside, the app's own example person"
                  if as_example else ""))
    return findings, summary


_ENTRY = re.compile(r"denylist entry \d+ \((.*)\)$")
_KIND = re.compile(r": (email address|phone number|LinkedIn profile)(?: (.+))?$")


def what(finding: str) -> str:
    """What a finding matched, for the one-line report: the denylist entry's words, the
    kind and value of a contact detail, or what the scan said about a path."""
    m = _ENTRY.search(finding)
    if m:
        return f"'{m.group(1)}'"
    m = _KIND.search(finding)
    if m:
        return f"{m.group(1)} {m.group(2)}" if m.group(2) else m.group(1)
    return finding.rsplit(": ", 1)[-1]


def headline(findings: list[str]) -> str:
    """One line for the person: how many matches, of what. The sync passed 40 file paths
    on as "tell the person exactly this" (2026-10-22), where one line said all of it:
    64 matches, every one the same greeting."""
    counts: dict[str, int] = {}
    places: dict[str, int] = {}
    for f in findings:
        counts[what(f)] = counts.get(what(f), 0) + 1
        place = ("commit messages" if f.startswith("commit ") else
                 "pull request text" if f.startswith("pull request ") else "files")
        places[place] = places.get(place, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    n = len(findings)
    where = (f"in the public app's {next(iter(places))}" if len(places) == 1 else
             "in the public app (" + ", ".join(f"{v} in {k}" for k, v in places.items()) + ")")
    if len(ranked) == 1:
        return f"{n} match(es) {where}, all of them {ranked[0][0]}"
    shown = ", ".join(f"{k} ({v})" for k, v in ranked[:5])
    more = f", and {len(ranked) - 5} more" if len(ranked) > 5 else ""
    return f"{n} matches {where}, of {len(ranked)} entries: {shown}{more}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not is_maintainers():
        return 0
    everything = "--all" in argv
    findings, summary = watch(everything=everything)
    if summary.startswith("the app could not be reached"):
        print(f"App watch: {summary}; checked again on the next sync.")
        return 2
    if findings:
        print(f"APP LEAK: {headline(findings)}. Claude: before anything else, tell the person "
              "this one line, and change nothing in the app without them.")
        if everything:
            for f in findings:
                print(f"  - {f}")
        else:
            print("  Every match, where it is: python3 tools/app_watch.py --all")
        return 1
    print(f"App watch: clean ({summary}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
