#!/usr/bin/env python3
"""Does the employer of someone the person is writing to have an open role that fits?

Asked before a reply to an offer to refer, and before a follow-up to someone at an employer,
is drafted (issue 233). A contact wrote "if you see any positions that interest you, let me
know and I'd be happy to refer you", and the reply only thanked them: nothing looked at the
employer's board, though it was on file, so the person had to ask "did you scan the roles to
see if there's anything he can refer?".

Nothing here fetches or scores in a new way. The board is the one profile/boards.py names for
the employer (apply_link.board_for), read the way a round reads it (ats_boards.FETCH, through
apply_link._read_board); each role passes the round's own gates (prefilter's place and title
verdicts; not its age limit, since a role open on the board today is open) and gets the round's fit (fit.fit, with the lift a live contact gives a role
at their employer, as fit.py's main counts it). A role fits at the follow-up's own bar
(followup_drafts.POSTING_FIT). A careers site is read page by page at the pace its robots.txt
asks, which is a search's work and never a card's (apply_link.UNCHECKABLE): it is said so,
never guessed at.

    check(company, contact_name="")  -> {"board", "checked", "role", "fits", "read", "said"}

`said` is the one line the card or the chat carries: the role that fits, "No open role there
fits yet", or that the employer has no board on file. Each board is read once a run.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# What the card or the chat says, in the person's words.
NONE_FITS = "No open role there fits yet"
NO_BOARD = "%s has no careers board on file, so its open roles were not checked"
SITE_ONLY = ("%s's careers site is read only in a job search, so its open roles were not "
             "checked here")
NOT_READ = "%s's careers board could not be read just now (%s), so its open roles were not checked"

# Each employer's board read once a run, by its key: a brief drafts for several people at
# one employer, and each would read the same board again. Cleared by `forget()`, which
# followup_drafts.drafts calls as each run starts, so a later run reads the board afresh.
_SEEN: dict = {}


def forget() -> None:
    """Read every board afresh from here on (a test, or a new run in one process)."""
    _SEEN.clear()


def _bar() -> float:
    try:
        import followup_drafts
        return float(followup_drafts.POSTING_FIT)
    except Exception:  # noqa: BLE001
        return 60.0


def _score(row: dict, contact_name: str = "") -> float | None:
    """The round's fit for one role, or None where the round's own gates cut it."""
    import fit as fit_mod
    import prefilter
    # The round's place and title gates. Not its age limit: a role still open on the
    # employer's own board today is open, however long ago it went up.
    if prefilter.location_verdict(row.get("location") or "", row.get("title") or "")[0] == "FAIL" \
            or prefilter.title_verdict(row.get("title") or "")[0] == "FAIL":
        return None
    lifts = ()
    if contact_name:
        lifts = ((fit_mod.REFERRAL_BONUS, "live contact at this employer (%s), so this is not "
                                          "a cold application" % contact_name),)
    try:
        return float(fit_mod.fit(row, lifts=lifts)["fit"])
    except Exception:  # noqa: BLE001  a role the scorer cannot read is not called a fit
        return None


def _applied(company: str, tracker=()) -> set:
    """The titles already applied to at this employer, as followup_drafts matches them."""
    import followup_drafts
    from company_key import key
    k = key(company)
    return {followup_drafts._slug(followup_drafts._clean_title(r.get("role")))
            for r in tracker or () if key(r.get("company")) == k}


def check(company, contact_name: str = "", tracker=(), read=None) -> dict:
    """The employer's open roles against the person's search.

    {"board": a board is on file, "checked": it was read, "role": the best role that fits
    ({"title", "company", "url", "fit", "from": "board"}) or {}, "fits": every role that fits,
    best first, "read": how many roles were read, "said": the one line to show}. `read` is
    (employer, kind, token) -> (rows, why none), default the round's reader."""
    import apply_link
    company = " ".join(str(company or "").split())
    out = {"board": False, "checked": False, "role": {}, "fits": [], "read": 0, "said": ""}
    if not company:
        out["said"] = NO_BOARD % "Their employer"
        return out
    board = apply_link.board_for(company)
    if not board:
        out["said"] = NO_BOARD % company
        return out
    employer, kind, token = board
    out["board"] = True
    if kind in apply_link.UNCHECKABLE:
        out["said"] = SITE_ONLY % company
        return out
    from company_key import key
    cache = (key(employer), contact_name)
    if read is None and cache in _SEEN:
        return dict(_SEEN[cache])
    try:
        rows, why = (read or apply_link._read_board)(employer, kind, token)
    except Exception as e:  # noqa: BLE001  a board that will not answer is said so
        rows, why = [], "%s" % type(e).__name__
    if not rows and why and "nothing matching" not in str(why):
        out["said"] = NOT_READ % (company, " ".join(str(why).split())[:80])
        return out
    out["checked"] = True
    out["read"] = len(rows or ())
    bar = _bar()
    done = _applied(company, tracker)
    import followup_drafts
    fits = []
    for r in rows or ():
        title = " ".join(str(r.get("title") or "").split())
        if not title or followup_drafts._slug(followup_drafts._clean_title(title)) in done:
            continue
        score = _score(r, contact_name)
        if score is None or score < bar:
            continue
        fits.append({"title": title, "company": company, "url": str(r.get("url") or ""),
                     "fit": int(round(score)), "location": str(r.get("location") or ""),
                     "from": "board"})
    fits.sort(key=lambda f: -f["fit"])
    out["fits"] = fits
    if fits:
        best = fits[0]
        out["role"] = best
        out["said"] = ("%s is open on %s's careers board and fits your search (fit %d)"
                       % (best["title"], company, best["fit"])
                       + (": " + best["url"] if best["url"] else ""))
    else:
        out["said"] = "%s: %d open role(s) read on %s's careers board" % (
            NONE_FITS, out["read"], company)
    if read is None:
        _SEEN[cache] = dict(out)
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Check an employer's open roles against your search.")
    ap.add_argument("company")
    ap.add_argument("--contact", default="", help="the contact there, whose referral lifts a fit")
    a = ap.parse_args(argv)
    got = check(a.company, contact_name=a.contact)
    print(got["said"])
    for f in got["fits"][1:5]:
        print("  also: %s (fit %d)%s" % (f["title"], f["fit"], ": " + f["url"] if f["url"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
