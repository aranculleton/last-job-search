#!/usr/bin/env python3
"""A posting the person added themselves (a link or its text, from the page's "Add a job"),
scored by the chat that took the `evaluate` work, kept beside the rounds.

The page asks for the link or the text and whether they applied already; `job.add` queues
the work (tools/app_actions.py). The chat that claims it scores the posting the way /apply
Step 1 does (the gates, then the four weighted dimensions, fit first), and writes the row
here with `add`; a posting they already applied for is also confirmed applied with its day
(confirm.py applied --new). The page's jobs list shows these first, with their score and
Draft this, until the person decides on each, the way it shows a round's rows.

    python3 tools/added_jobs.py add <row.json>     # {"title", "company", "url", "fit", ...}
    python3 tools/added_jobs.py list
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import person  # noqa: E402

FILE = ("documents", "rounds", "added", "jobs.json")
# The fields a round row carries that the page reads (run_round.SUMMARY_FIELDS' own names).
FIELDS = ("title", "company", "location", "url", "apply_url", "fit", "fit_why", "salary",
          "deadline", "questions", "near", "bar", "bar_reason", "portal")


def path() -> str:
    return person.state(*FILE)


def load() -> list:
    try:
        with open(path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return []
    return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []


def _same(a: dict, b: dict) -> bool:
    from lookup_score import norm
    ua, ub = norm(a.get("url") or ""), norm(b.get("url") or "")
    if ua and ub:
        return ua == ub
    return (str(a.get("company") or "").strip().lower(), str(a.get("title") or "").strip()
            .lower()) == (str(b.get("company") or "").strip().lower(),
                          str(b.get("title") or "").strip().lower())


def add(row: dict, today: str = "") -> tuple[int, bool]:
    """Keep one added posting: (its number on the list, whether it is new). The same
    posting added twice is one row, its score brought up to date."""
    if not str(row.get("title") or "").strip() or not str(row.get("company") or "").strip():
        raise ValueError("a posting needs its title and its employer")
    rows = load()
    clean = {k: row[k] for k in FIELDS if k in row}
    clean["added_on"] = today or dt.date.today().isoformat()
    for n, r in enumerate(rows, 1):
        if _same(r, clean):
            r.update({k: v for k, v in clean.items() if k != "added_on"})
            _save(rows)
            return n, False
    rows.append(clean)
    _save(rows)
    return len(rows), True


def _save(rows: list) -> None:
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["list"]:
        for n, r in enumerate(load(), 1):
            print(f"added-{n}: {r.get('title')} at {r.get('company')} ({r.get('fit', '-')})")
        return 0
    if len(argv) == 2 and argv[0] == "add":
        try:
            with open(argv[1], encoding="utf-8") as fh:
                row = json.load(fh)
            n, new = add(row)
        except (OSError, ValueError) as e:
            print(f"added_jobs: not added: {e}")
            return 1
        print(f"added_jobs: added-{n} {'added' if new else 'brought up to date'}: "
              f"{row.get('title')} at {row.get('company')}")
        return 0
    print(__doc__.strip().split("\n\n")[-1])
    return 2


if __name__ == "__main__":
    sys.exit(main())
