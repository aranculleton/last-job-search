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

The rules it keeps, from Step 6b: match company and role the way the rest of
the app does (one employer key, one title rule); update an open match rather
than duplicating it and never move it backwards; append beside a final one;
never reorder or restructure the CSV; never touch another row; never write
`seen_jobs.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outreach  # noqa: E402
import csv_store  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402
from company_key import key as company_key  # noqa: E402
from throttle import FINAL, _same_title  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = person.state("job_search_tracker.csv")
HEADER = ["date", "company", "sector", "role", "role_type", "channel", "status",
          "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
          "source", "deadline"]
# A final status is throttle.FINAL, imported rather than copied: the copy that
# lived here lacked `declined`, so a declined row read as open and a new draft
# for the same role overwrote its outcome. The match is the throttle's too: one
# employer key ("Acme Analytics" is "Acme Analytics Inc.") and one title rule
# ("Sr. Analyst" is "Senior Analyst"), where a raw lower-case comparison
# appended a second row for an application already on file.

# Where a posting from an employer's own applicant tracking system is applied
# to: their careers page, which /apply Step 6b calls `online`. The keys of
# tools/ats_boards.py FETCH (a test pins them equal).
EMPLOYER_BOARDS = frozenset({"greenhouse", "lever", "ashby", "workday"})


def _same_application(row: dict, new: dict) -> bool:
    return (company_key(row.get("company")) == company_key(new["company"])
            and _same_title(row.get("role"), new["role"]))


def _channel(portal) -> str:
    """`online` for an employer's own board, `portal` for a job board, "" when unknown."""
    portal = str(portal or "").strip().lower()
    if portal in ("", "pasted"):    # /apply's posting from no board: the person's call
        return ""
    return "online" if portal in EMPLOYER_BOARDS else "portal"


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
        # A posting /apply staged on its own has a fit and nothing else; "opportunity
        # None, priority None" in the notes reads as a fault.
        ("Scores: " + ", ".join("%s %s" % (k, meta[k]) for k in ("fit", "opportunity", "priority")
                                if meta.get(k) is not None) + "."
         if fit is not None else ""),
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
        "channel": _channel(meta.get("portal")),
        "status": "drafted",
        "contact_person": "",
        "fit_rating": "" if fit is None else str(int(round(float(fit)))),
        "notes": notes,
        "cv_file": docpaths.resume_rel(abbr),
        "cover_letter_file": docpaths.letter_rel(abbr),
        "source": meta.get("url", ""),
        "deadline": draft.get("deadline", "") or meta.get("deadline", "") or "",
    }


def record(drafts: list[dict], metas: dict[str, dict], today: str, round_name: str = "",
           path: str = TRACKER) -> list[tuple[str, dict]]:
    """Apply the batch to the tracker. Returns [(action, row)] with action added/updated.

    Written through tools/csv_store.py: the file's own columns and line ending
    are kept, so one new row is one changed line. A plain DictWriter rewrote
    every "\\n" as "\\r\\n", and after a column added by hand it appended a
    second `deadline`.
    """
    rows = csv_store.read_rows(path, HEADER)
    done = []
    for d in drafts:
        new = _row_for(d, metas.get(d["abbr"].upper(), {}), today, round_name)
        open_match = next((r for r in rows if _same_application(r, new)
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
    csv_store.write_rows(path, rows, HEADER)
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
    # The same matching as tools/outreach.py: the abbr the draft arrived with,
    # then the name its files were written under, which every row records.
    for d in drafts:
        supplied = (d.get("abbr") or "").upper()
        d["abbr"] = outreach.R.final_abbr(d)
        if supplied in metas and d["abbr"].upper() not in metas:
            metas[d["abbr"].upper()] = metas[supplied]
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
