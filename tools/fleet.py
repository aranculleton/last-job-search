#!/usr/bin/env python3
"""What every Claude session working on this repo has done, from git alone.

## Why this exists

Several sessions can run against this repo at once, each in its own container,
each on its own branch, none able to see the others. The only thing they share is
`origin`. That works, and it is also why the repo feels confusing: there is no
view of the fleet, so the honest answer to "what are my agents doing" has been
to read a tangled log and guess.

CLAUDE.md already carries the rule that stops the worst version of this: a
branch that runs far past master holds work the next session cannot see, and
that session builds a second copy of it.

The rule is right and nothing measured whether it was being followed. This
does. It invents no state: branches, commits and dates are all already in git,
and a view derived from them cannot go stale the way a hand-kept status file
does.

WHAT IT CHECKS, in the order that matters:

  divergence   a branch far ahead of master is that failure starting again,
               and the number is the warning
  staleness    a branch nobody has touched in days is either abandoned or is
               work the next session will duplicate
  master       who has been landing what, so the tangle has a shape
  rewrites     every recorded state of master should be an ancestor of the
               current one; anything else means history was rewritten under a
               session that had already started from it

    python3 tools/fleet.py
    python3 tools/fleet.py --days 3

Exit 0 all clear, 1 if something needs a person.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import subprocess
import sys

# A branch this far past master is the divergence failure starting again.
DIVERGENCE_WARN = 25
# A branch untouched this long is abandoned or about to be duplicated.
STALE_DAYS = 3


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def branches() -> list[dict]:
    out = []
    raw = git("for-each-ref", "--format=%(refname:short)%09%(committerdate:short)%09%(authorname)",
              "refs/remotes/origin")
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, date = parts[0], parts[1]
        if name.endswith("/master") or name.endswith("/HEAD"):
            continue
        counts = git("rev-list", "--left-right", "--count", f"origin/master...{name}")
        behind, ahead = (counts.split() + ["0", "0"])[:2]
        out.append({"name": name, "date": date,
                    "behind": int(behind or 0), "ahead": int(ahead or 0),
                    "author": parts[2] if len(parts) > 2 else ""})
    return sorted(out, key=lambda b: b["date"], reverse=True)


def via_pull_request(subject: str) -> bool:
    """Did this commit land through a pull request?

    A merge commit reads "Merge pull request #12 from owner/branch"; a squash or
    rebase merge ends "(#12)". Only the second was counted, so a repo that merges
    the ordinary way reported every pull request as a direct push and printed a
    false alarm on every run.
    """
    s = subject.strip()
    return s.startswith("Merge pull request #") or (s.endswith(")") and "(#" in s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=2,
                    help="how much master history to summarize (default 2)")
    a = ap.parse_args()

    subprocess.run(["git", "fetch", "origin", "--prune", "-q"], capture_output=True)
    today = dt.date.today()
    findings: list[str] = []

    print("\nfleet: sessions working on this repo, from git\n")

    # --- branches in flight ------------------------------------------------
    bs = branches()
    if not bs:
        print("  no branches besides master: nothing is in flight")
    else:
        print(f"  {'branch':46} {'ahead':>6} {'behind':>7} {'last commit':>12}")
        for b in bs:
            try:
                age = (today - dt.date.fromisoformat(b["date"])).days
            except ValueError:
                age = 0
            flag = ""
            if b["ahead"] >= DIVERGENCE_WARN:
                flag = "  DIVERGING"
                findings.append(
                    f"{b['name']} is {b['ahead']} commits past master. The rule in "
                    f"CLAUDE.md exists because a branch that runs far past master gets "
                    f"its work rebuilt from scratch by another session. Merge it.")
            elif age >= STALE_DAYS and b["ahead"]:
                flag = f"  STALE {age}d"
                findings.append(
                    f"{b['name']} has {b['ahead']} unmerged commit(s) and nothing has "
                    f"touched it for {age} days. Either land it or say it is dead: "
                    f"another session cannot see it and will redo the work.")
            print(f"  {b['name'][:46]:46} {b['ahead']:>6} {b['behind']:>7} "
                  f"{b['date']:>12}{flag}")

    # --- what landed on master --------------------------------------------
    since = (today - dt.timedelta(days=a.days)).isoformat()
    # %x09 is a tab. %09 is the literal two characters "09", which git log
    # prints verbatim, so the split below never split and every field landed
    # in p[0]: the summary reported 0 pull requests and 0 merge commits on a
    # window that had both. `for-each-ref` above uses a different format
    # language where %09 does mean tab, which is exactly why this was easy to
    # get wrong in one place and right in the other.
    log = git("log", f"--since={since}", "--format=%h%x09%an%x09%ad%x09%s",
              "--date=short", "origin/master")
    lines = [ln.split("\t") for ln in log.splitlines() if ln]
    print(f"\n  master, last {a.days} day(s): {len(lines)} commit(s)")
    if lines:
        by_day = collections.Counter(p[2] for p in lines if len(p) > 2)
        for day in sorted(by_day, reverse=True):
            print(f"    {day}  {by_day[day]:3d} commit(s)")
        merges = sum(1 for p in lines if len(p) > 3 and p[3].startswith("Merge "))
        prs = sum(1 for p in lines if len(p) > 3 and via_pull_request(p[3]))
        print(f"    of those: {prs} via a pull request, {merges} merge commit(s)")
        if lines and prs == 0:
            findings.append(
                "nothing reached master through a pull request in this window. A pull "
                "request is where a change is checked before every other session starts "
                "from it; branch protection requiring one is the only thing that "
                "enforces it.")

    # --- was master rewritten under anyone ---------------------------------
    reflog = [ln.split()[0] for ln in git("reflog", "show", "origin/master").splitlines()]
    rewritten = [s for s in reflog
                 if subprocess.run(["git", "merge-base", "--is-ancestor", s, "origin/master"],
                                   capture_output=True).returncode != 0]
    if reflog:
        if rewritten:
            findings.append(
                f"master was rewritten: {len(rewritten)} earlier state(s) are no longer "
                f"ancestors of it. Any session that started before that is building on "
                f"history which no longer exists.")
        else:
            print(f"\n  master: {len(reflog)} recorded state(s), all ancestors of the "
                  f"current one (never rewritten)")

    print()
    if findings:
        print("  NEEDS A PERSON\n")
        for f in findings:
            print(f"    - {f}\n")
        return 1
    print("  Nothing diverged, nothing stale.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
