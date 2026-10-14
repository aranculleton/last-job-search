#!/usr/bin/env python3
"""Record a rendered batch in the tracker, the way /apply Step 6b says to.

    python3 tools/record_drafts.py <drafts.json> <apps_in.json> [--today YYYY-MM-DD] [--round r1]

Run after `tools/fit_to_page.py` (which fixes each draft's `abbr`) and
`tools/outreach.py` (which archives the posting). For every draft it writes one
tracker row at `status=drafted`, or refreshes an open row for the same company
and role, and writes `screening_answers.md` beside the archived posting.

## Why this is code

Step 6b was followed by hand for every batch, and the hand got one column wrong
repeatedly. The `fit_rating` column is documented as "the overall
score from Step 1 as a bare number, 0-100", and the batch path copied the
shortlist's `priority` into it instead: fit times opportunity, uncapped. A row
could go in above 100 on a 0-100 scale, or ten points under its fit, and
nobody could tell from the row. This writes `fit`, and
keeps priority and opportunity in the notes where they are labelled.

The rules it keeps, from Step 6b: match company and role case-insensitively;
update an open match rather than duplicating it and never move it backwards;
append beside a final one; never reorder or restructure the CSV; never touch
another row; never write `seen_jobs.json`.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outreach  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = person.state("job_search_tracker.csv")
HEADER = ["date", "company", "sector", "role", "role_type", "channel", "status",
          "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
          "source", "deadline"]
# The Final statuses of /outcome's tracker status vocabulary, legacy spellings included.
FINAL = {"hired", "rejected", "no_response", "no response", "offer_declined",
         "offer declined", "withdrawn"}


def _same(a: str, b: str) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _row_for(draft: dict, meta: dict, today: str, round_name: str) -> dict:
    fit = meta.get("fit")
    body = (draft.get("notes_for_tracker") or "").strip()
    # Drafters write the round into their own note as often as not, and the row
    # already starts with it, which would read "r1. r1.".
    if round_name and body.lower().startswith(round_name.lower() + "."):
        body = body[len(round_name) + 1:].lstrip()
    notes = " ".join(x for x in (
        f"{round_name}." if round_name else "",
        body,
        (f"Scores: fit {fit}, opportunity {meta.get('opportunity')}, "
         f"priority {meta.get('priority')}." if fit is not None else ""),
        (f"Bar: {meta['bar']} ({meta.get('bar_reason', '')})." if meta.get("bar") else ""),
        # CLAUDE.md: the company-throttle override is "named explicitly". A
        # second application at an employer is a decision, and the row is
        # where the next reader looks for why it was made.
        (meta.get("throttle_override_note") or ""),
        (meta.get("warm_route_note") or ""),
        (meta.get("outreach_pending_note") or ""),
    ) if x).strip()
    abbr = draft["abbr"]
    return {
        "date": today, "company": draft["company"], "sector": draft.get("sector", ""),
        "role": draft["role"], "role_type": draft.get("role_type", ""),
        "channel": "portal" if meta.get("portal") else "", "status": "drafted",
        "contact_person": "",
        "fit_rating": "" if fit is None else str(int(round(float(fit)))),
        "notes": notes,
        "cv_file": docpaths.resume_rel(abbr),
        "cover_letter_file": docpaths.letter_rel(abbr),
        "source": meta.get("url", ""), "deadline": draft.get("deadline", "") or "",
    }


def record(drafts: list[dict], metas: dict[str, dict], today: str, round_name: str = "",
           path: str = TRACKER) -> list[tuple[str, dict]]:
    """Apply the batch to the tracker. Returns [(action, row)] with action added/updated."""
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
            header = rows and list(rows[0].keys()) or HEADER
    except OSError:
        rows, header = [], HEADER
    if header[-1] != "deadline":
        header = header + ["deadline"]
    done = []
    for d in drafts:
        new = _row_for(d, metas.get(d["abbr"].upper(), {}), today, round_name)
        open_match = next((r for r in rows if _same(r.get("company"), new["company"])
                           and _same(r.get("role"), new["role"])
                           and (r.get("status") or "").strip().lower() not in FINAL), None)
        if open_match is None:
            rows.append(new)
            done.append(("added", new))
            continue
        # Never move an open row backwards: refresh the documents and the score,
        # keep its status, and only move the date if nothing was ever sent.
        for col in ("cv_file", "cover_letter_file", "fit_rating", "source"):
            if new[col]:
                open_match[col] = new[col]
        if new["deadline"]:
            open_match["deadline"] = new["deadline"]
        if (open_match.get("status") or "").strip().lower() == "drafted":
            open_match["date"] = today
        open_match["notes"] = ((open_match.get("notes") or "").rstrip() + " | redrafted").strip(" |")
        done.append(("updated", open_match))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") or "" for k in header})
    return done


def screening(draft: dict) -> str:
    slug = outreach.slug(draft["company"], draft["role"], draft["abbr"])
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "screening_answers.py"),
                          "--slug", slug, "--company", draft["company"], "--role", draft["role"]],
                         capture_output=True, text=True)
    return slug if out.returncode == 0 else f"{slug}: FAILED {out.stderr.strip()[-200:]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("drafts")
    ap.add_argument("apps_in")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--round", default="", help="round name for the notes, e.g. r1")
    ap.add_argument("--no-screening", action="store_true")
    a = ap.parse_args()
    drafts = json.load(open(a.drafts, encoding="utf-8"))
    raw = json.load(open(a.apps_in, encoding="utf-8"))
    metas = {m["abbr"].upper(): m for m in (raw if isinstance(raw, list) else raw.values())
             if m.get("abbr")}
    missing = [d["company"] for d in drafts if d["abbr"].upper() not in metas]
    if missing:
        print("no shortlist row (apps_in.json) for: " + ", ".join(missing)
              + ". Their fit, source and portal come from there; stage with tools/stage_picks.py.")
        return 1
    for action, row in record(drafts, metas, a.today, a.round):
        print(f"{action:<8} {row['company']} | {row['role']} | fit {row['fit_rating']} | {row['cv_file']}")
    if not a.no_screening:
        for d in drafts:
            print("screening answers:", screening(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
