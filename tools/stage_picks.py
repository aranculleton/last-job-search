#!/usr/bin/env python3
"""The step between a ranked shortlist and a draft: stage the picks, then assemble.

A person picks postings from a round. Before this existed, the drafting session
did the rest by hand every time: find the rows in `06_shortlist.json`, write each
posting where a drafter could read it, work out the filename, build the
`apps_in.json` that `tools/outreach.py` wants, and afterwards stitch the drafted
fields, the posting text and the abbreviation back together into the
`drafts.json` that `tools/fit_to_page.py` renders. Each of those was a place to
get it slightly wrong, and one of them was a place to get it badly wrong:

**A second role at an employer overwrote the documents already sent to it.**
`doc_name.suffix("Acme")` is `Acme` whatever the role, and one round picked
second roles at three employers while `cv/<Prefix>_Resume_Acme.tex` and its
like were the resumes those employers had already received. `05-cv-templates.md` asks for a role token in that case, and nothing
enforced it, so the render would have replaced the record `/interview` reads
with a document the employer never saw. Staging now derives the name, checks
it against the tracker, and appends a PascalCase role token whenever the name
belongs to a different application.

    python3 tools/stage_picks.py stage <round_dir> <pick> [<pick> ...] [--both]
    python3 tools/stage_picks.py single <dir> --company C --role R --posting-file F [--url U] [--fit N]
    python3 tools/stage_picks.py consent <round_dir> <pick> --yes A B --no C [--draft | --skip]
    python3 tools/stage_picks.py audit <round_dir> [--only <slug> ...] [--json]
    python3 tools/stage_picks.py assemble <round_dir>

**Every skill a posting names that the profile does not hold is asked about first.**
`stage` prints one short question per pick (`bridges.unheld_asked`), and nothing is
drafted until `consent` records each answer. A yes puts it on this resume's skills line,
named as the posting spells it; a no keeps it off every document. Both travel with the
draft and are written into the documents' own header, which `check_claims.py` reads. The
app used to decide this alone, and left the tool off: only the person knows whether they
use it and never said, learned it since, or judge they can back it up, and the word left
off can be the one an applicant tracking system screens on.

**What each posting is, before any model reads it.** `stage` prints a code-only profile of
every pick (tools/posting_profile.py): contract or permanent and when it ends, the stated
pay and whether it is for the person's place, the years and degree asked, where and how it
is worked, whether this search has seen it before, and what is already running at the
employer. One pick was found to be a four-month fixed-term contract only after its
research agent had finished, though the posting said so. A fatal or surprising property
(a fixed-term contract, a pay band for another place, an application already in there, the
same role applied to before, a referral in flight, a posting ruled out before, a location
the gate fails) is a plain question, and so is a second role at one employer: **one role
per employer** unless `--both`. A pick waiting on such a question is held in `held.json`,
out of `picks.json`, so nothing is drafted for it; `consent <round_dir> <slug> --draft`
releases it, `--skip` drops it.

`single` is /apply's way in: one posting that came from no round, staged exactly
as a round's pick is, so a single application is drafted, rendered and verified by
the same tools as a batch.

A round's own `06_shortlist.json` is read when it is there; in a later session,
when the gitignored round directory is gone, the committed
`documents/rounds/<round>.json` is read instead, and each pick's body is fetched
from its board, or read from `<round_dir>/postings/<slug>.txt` when the board
will not give it.

A pick is a 1-based rank in `06_shortlist.json`, or `Company::title words`.

`stage` writes, under <round_dir>:
    picks/NN_<slug>.md   the posting, fenced by tools/untrusted.py, with the
                         shortlist's scores and routing notes above the fence
    picks.json           [{file, company, role, slug, abbr, ask_first}], the
                         `args.picks` of the saved draft-applications workflow;
                         `consent` adds skills_yes and skills_no. Only the picks
                         nothing is waiting on.
    held.json            the picks waiting on the person's answer, each with its
                         `hold` questions; `consent --draft` moves one to picks.json
    apps_in.json         the shortlist rows with `abbr`, for tools/outreach.py

`audit` is the grounding audit of each `<round_dir>/draft_<slug>.json` the workflow's
drafter writes, done by code first (tools/draft_audit.py): every rule the draft must
meet, and every question about its claim map. It writes `audit_<slug>.json` with the
verdict `pass` (nothing for the model to judge) or `needs_model`, and merges the model
auditor's `model_audit_<slug>.json` when there is one, re-checking its corrected draft.
`--only` audits just the roles that will be sent; `--json` prints only what fails.

`assemble` reads each `<round_dir>/audit_<slug>.json` (the whole audit: verdict,
corrected draft, changes and residual risks) and writes `<round_dir>/drafts.json`
with the posting text and the abbreviation filled in. A draft the audit rejected is
never rendered: it is reported with the audit's reasons. Nor is one still waiting on
the model auditor, one changed since its audit, or one audited against a profile that
has changed since. A pick with no audited draft is reported, never silently dropped.
An older audit file, from the agent auditor or holding the corrected draft alone, as a
one-element list, is still read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_name  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402
import untrusted  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = person.state("job_search_tracker.csv")

# Words that say nothing about which role this is. A token built from them
# ("Acme_Manager", "Acme_Associate") separates two files and tells a person
# reading the filename nothing. The profile's city and country words join them
# (_market_words below).
_FILLER = {
    "a", "an", "and", "the", "of", "for", "to", "in", "at", "with", "on",
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate",
    "manager", "director", "head", "specialist", "consultant", "analyst",
    "ii", "iii", "iv", "i", "1", "2", "3", "contract", "month", "months",
    "12", "fixed", "term", "remote", "hybrid",
    "global",
}


def _market_words():
    """The person's country and city: in every posting title, naming no role."""
    words = set(getattr(person.module("employers"), "NAME_FILLER", ())
                if person.exists("employers.py") else ())
    words |= {w.lower() for w in re.findall(r"[A-Za-z]+", person.get("identity.location", ""))
              if len(w) > 2}
    return words


_FILLER |= _market_words()


def slug(company: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (company or "").lower()).strip("_")
    return s or "employer"


def role_token(role: str, taken: set[str] | None = None) -> str:
    """A short PascalCase token naming the role, e.g. "PricingStrategy".

    Prefers what follows a dash or comma, because titles put the team there
    ("Manager - Pricing Strategy", "Associate, Data Science - Supply Chain
    Analytics"), and falls back to the whole title.
    """
    taken = taken or set()
    parts = [p for p in re.split(r"\s[-–—]\s|,|\(|\)", role or "") if p.strip()]
    candidates = list(reversed(parts)) + [role or ""]
    for text in candidates:
        words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if w.lower() not in _FILLER]
        if not words:
            continue
        for n in (2, 3, 1):
            tok = "".join(w[:1].upper() + w[1:] for w in words[:n])
            if tok and tok not in taken and len(tok) <= 24:
                return tok
    return "Role"


def _tracker_rows(path: str = TRACKER) -> list[dict]:
    return doc_name.tracker_rows(path)


def _norm(s: str) -> str:
    return doc_name._norm(s)


def owners(abbr: str, rows: list[dict]) -> list[dict]:
    """Tracker rows whose recorded documents already carry this name."""
    return doc_name.owners(abbr, rows)


def file_taken(abbr: str, root: str = ROOT) -> bool:
    """True when either document exists under this name in any letter case.

    `os.path.exists` is case-sensitive on Linux, where this runs, and the
    checkout is also opened on macOS, where `_Acme.tex` and `_ACME.tex`
    are the same file.
    """
    for folder, stem in (("cv", docpaths.resume_stem(abbr) + ".tex"),
                         ("cover_letters", docpaths.letter_stem(abbr) + ".tex")):
        try:
            names = os.listdir(os.path.join(root, folder))
        except OSError:
            continue
        if stem.casefold() in {n.casefold() for n in names}:
            return True
    return False


def choose_abbr(company: str, role: str, rows: list[dict], root: str = ROOT,
                claimed: set[str] | None = None) -> str:
    """The filename suffix for this application, never one another application owns.

    The plain company name is used when nothing holds it, or when the only
    holder is an unsent draft of this same role (a regenerated draft keeps its
    name). A name an application was sent under is never reused, whatever the
    role: a redraft of a role already applied to gets a role token, lengthened
    until it is free, so the documents the employer received stay as they were.
    """
    claimed = claimed if claimed is not None else set()
    base = doc_name.suffix(company, "")
    held = owners(base, rows)
    same = doc_name.reusable(base, role, rows)
    if base not in claimed and (not held or same) and (held or not file_taken(base, root)):
        return base
    tried: set[str] = set()
    for _ in range(6):
        tok = role_token(role, tried)
        tried.add(tok)
        abbr = doc_name.suffix(company, tok)
        # The redraft of a redraft keeps the token name its unsent draft has.
        free = (doc_name.reusable(abbr, role, rows) if owners(abbr, rows)
                else not file_taken(abbr, root))
        if abbr not in claimed and free:
            return abbr
    raise ValueError(
        f"no free filename for {company!r} / {role!r}: {base} and every role token tried "
        "belong to other applications. Pass a Company::title pick with a clearer title.")


def _find(shortlist: list[dict], pick: str) -> dict:
    if pick.isdigit():
        i = int(pick)
        if not 1 <= i <= len(shortlist):
            raise SystemExit(f"pick {pick} is outside the shortlist (1..{len(shortlist)})")
        return shortlist[i - 1]
    if "::" not in pick:
        raise SystemExit(f"pick {pick!r} is neither a rank nor Company::title words")
    company, title = pick.split("::", 1)
    hits = [r for r in shortlist
            if _norm(company) in _norm(r.get("company")) and _norm(title) in _norm(r.get("title"))]
    if len(hits) != 1:
        raise SystemExit(f"pick {pick!r} matched {len(hits)} shortlist rows; make it unique")
    return hits[0]


def load_shortlist(round_dir: str) -> list[dict]:
    """The round's shortlist: its own file, or the committed summary of it.

    `06_shortlist.json` lives in the gitignored round directory, so a later
    session (the person answering a shortlist hours after it was sent, in a new
    container) has only `documents/rounds/<round>.json`, which keeps the same
    rows in the same order without their bodies. `posting_text` fills those in.
    """
    path = os.path.join(round_dir, "06_shortlist.json")
    kept = person.state("documents", "rounds",
                        os.path.basename(os.path.normpath(round_dir)) + ".json")
    for p in (path, kept):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else list(data.values())
    raise SystemExit(f"stage: neither {path} nor {kept} exists. Pass the round directory the "
                     "shortlist came from (rounds/<name>), or stage a single posting with "
                     "`single`.")


def _hydrate(row: dict) -> dict:
    import hydrate
    return hydrate.fetch(row)


def posting_text(row: dict, round_dir: str, s: str, fetch=_hydrate) -> str:
    """The posting body: the shortlist's, a saved copy, or fetched from the board."""
    if (row.get("desc") or "").strip():
        return row["desc"]
    saved = os.path.join(round_dir, "postings", f"{s}.txt")
    if os.path.exists(saved):
        with open(saved, encoding="utf-8") as fh:
            return fh.read()
    got = fetch(row) or {}
    if (got.get("desc") or "").strip():
        return got["desc"]
    raise SystemExit(
        f"stage: no posting text for {row.get('company')} | {row.get('title')} "
        f"({got.get('hydrate_error') or 'nothing came back'}). Save the posting to {saved} "
        f"(WebFetch {row.get('url') or 'its link'}, or ask the person to paste it) and run "
        "stage again.")


def stage(round_dir: str, picks: list[str], rows: list[dict] | None = None,
          root: str = ROOT, shortlist: list[dict] | None = None,
          fetch=_hydrate, both: bool = False, today=None) -> list[dict]:
    """Stage the picks and return every one, each with its `hold` questions (empty when
    nothing waits on the person). picks.json gets the ones nothing waits on, held.json
    the rest. `both` is the person saying they want two roles at one employer."""
    import posting_profile
    from company_key import key as company_key
    shortlist = load_shortlist(round_dir) if shortlist is None else shortlist
    rows = _tracker_rows() if rows is None else rows
    os.makedirs(os.path.join(round_dir, "picks"), exist_ok=True)
    staged, apps_in, claimed, seen_slugs = [], [], set(), set()
    for n, pick in enumerate(picks, 1):
        r = _find(shortlist, pick)
        abbr = choose_abbr(r["company"], r["title"], rows, root, claimed)
        claimed.add(abbr)
        if doc_name.is_shouty(abbr):
            # A board that writes the employer in capitals gives a name in capitals, the
            # one thing a filename on an attachment must not look like.
            words = doc_name._words(r["company"])
            plain = "".join(w.capitalize() for w in words
                            if w.lower() not in doc_name.GENERIC)[:doc_name.MAX_CHARS]
            print(f"stage: the file name {abbr} is the employer's name in capitals, which "
                  "looks machine-made on an attachment. Add how the employer writes its own "
                  f"name to profile/employers.py ABBREVIATIONS, for example "
                  f"{' '.join(words).lower()!r}: {plain!r}, then stage again.",
                  file=sys.stderr)
        s = slug(r["company"])
        if s in seen_slugs:
            s = f"{s}_{n}"
        seen_slugs.add(s)
        r = dict(r, desc=posting_text(r, round_dir, s, fetch))
        asks = to_ask(r["desc"])
        prof = posting_profile.read(r, r["desc"], rows=rows, today=today)
        hold = posting_profile.questions(prof, r)
        path = os.path.join(round_dir, "picks", f"{n:02d}_{s}.md")
        head = [
            f"# {r['company']} | {r['title']}", "",
            f"- abbr: {abbr}",
            f"- location: {r.get('location', '')}",
            f"- posted: {r.get('date', '')}",
            f"- url: {r.get('url', '')}",
            f"- portal: {r.get('portal', '')}",
            f"- fit {r.get('fit')}, opportunity {r.get('opportunity')}, priority {r.get('priority')}",
            f"- flags: {json.dumps(r.get('flags') or [])}",
            f"- fit_why: {json.dumps(r.get('fit_why') or [])}",
            f"- warm_route_note: {r.get('warm_route_note') or ''}",
            f"- outreach_pending_note: {r.get('outreach_pending_note') or ''}",
            f"- throttle_override_note: {r.get('throttle_override_note') or ''}",
            f"- ask the person first: {_listed(asks) or 'nothing'}",
        ]
        # What code read from the posting, derived values only (no posting text above the
        # fence), so the researcher and the drafter know it as well as the person does.
        head += [f"- {line}" for line in posting_profile.lines(prof, quotes=False)]
        cc = _research_country(r)
        if cc:
            head.append(f"- research as: {cc}")
        head.append("")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n" + untrusted.fence(r.get("desc") or "") + "\n")
        staged.append({"file": path, "company": r["company"], "role": r["title"],
                       "slug": s, "abbr": abbr, "ask_first": [x["skill"] for x in asks],
                       "ask_beside": {x["skill"]: x["have"][:1] for x in asks if x["have"]},
                       "posting_profile": prof, "hold": hold})
        apps_in.append(dict({k: v for k, v in r.items() if k != "desc"}, abbr=abbr))
    # One role per employer, unless the person said both.
    by_employer: dict[str, list[dict]] = {}
    for p in staged:
        by_employer.setdefault(company_key(p["company"]) or p["slug"], []).append(p)
    for group in by_employer.values():
        if len(group) < 2 or both:
            continue
        named = _and([f"{p['role']} [{p['slug']}]" for p in group])
        for p in group:
            p["hold"].append({"id": ONE_PER_EMPLOYER, "question": (
                f"You picked {len(group)} roles at {group[0]['company']}: {named}. One role per "
                "employer is the default. Which one should I draft? (Say both if you want both.)")})
    _write_picks(round_dir, [p for p in staged if not p["hold"]],
                 [dict(p, status="waiting") for p in staged if p["hold"]])
    with open(os.path.join(round_dir, "apps_in.json"), "w", encoding="utf-8") as fh:
        json.dump(apps_in, fh, indent=1)
    return staged


ONE_PER_EMPLOYER = "one_per_employer"


def _research_country(row: dict) -> str:
    """The posting's country, for the research cache: "" when it is the person's own or
    cannot be told, so a home posting reads and writes the plain file as before."""
    try:
        import company_research
        cc = company_research.country_of(row.get("location"))
    except Exception:
        return ""
    return cc if cc and cc != person.country() else ""


def _write_picks(round_dir: str, released: list[dict], held: list[dict]) -> None:
    with open(os.path.join(round_dir, "picks.json"), "w", encoding="utf-8") as fh:
        json.dump(released, fh, indent=1)
    where = os.path.join(round_dir, "held.json")
    if held or os.path.exists(where):
        with open(where, "w", encoding="utf-8") as fh:
            json.dump(held, fh, indent=1)


def _read_held(round_dir: str) -> list[dict]:
    try:
        with open(os.path.join(round_dir, "held.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, list) else []
    except (OSError, ValueError):
        return []


def to_ask(posting: str) -> list[dict]:
    """The skills this posting names that the profile does not hold: bridges.unheld_asked."""
    import bridges
    return bridges.unheld_asked(posting)


def _listed(asks) -> str:
    return ", ".join(x["skill"] + (f" (you list {x['have'][0]})" if x.get("have") else "")
                     for x in asks)


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


# Said only when the person asks why: one sentence.
WHY_ASK = ("An applicant tracking system can screen on the exact word, so leaving one off can "
           "cost the interview, and claiming one you cannot back up can cost it later; only you "
           "know which it is.")


def question(pick: dict) -> str:
    """The one short question for a pick, or "" when there is nothing to ask."""
    names = unanswered(pick)
    if not names:
        return ""
    beside = pick.get("ask_beside") or {}
    shown = [n + (f" (you list {beside[n][0]})" if beside.get(n) else "") for n in names]
    one = len(names) == 1
    return (f"{pick['company']} asks for {_and(shown)}, which your profile doesn't list. "
            f"Can you claim {'it' if one else 'any of them'} and back {'it' if one else 'them'} "
            f"up in an interview? {'A yes puts it' if one else 'Each yes goes'} on this resume; "
            f"{'a no keeps it off' if one else 'each no stays off'}.")


def _fold(names) -> set[str]:
    return {str(n).strip().casefold() for n in names or () if str(n).strip()}


def unanswered(pick: dict) -> list[str]:
    """The skills a pick still waits on the person for. A pick staged before this step
    has no ask_first at all, and is read from its posting so it cannot slip through."""
    asked = pick.get("ask_first")
    if asked is None:
        try:
            with open(pick["file"], encoding="utf-8") as fh:
                asked = [x["skill"] for x in to_ask(untrusted.unfence(fh.read()))]
        except OSError:
            asked = []
    done = _fold(pick.get("skills_yes")) | _fold(pick.get("skills_no"))
    return [n for n in asked if n.casefold() not in done]


def _which(staged: list[dict], which: str) -> dict:
    w = _norm(which)
    hits = [p for p in staged if w in (_norm(p["slug"]), _norm(p["abbr"]))]
    hits = hits or [p for p in staged if w and w in _norm(p["company"])]
    if len(hits) != 1:
        raise SystemExit(f"consent: {which!r} matched {len(hits)} picks; use the slug or abbr "
                         "stage printed")
    return hits[0]


def consent(round_dir: str, which: str, yes=(), no=(), draft: bool = False,
            skip: bool = False) -> dict:
    """Record the person's answers for one pick, and return the pick.

    `yes` and `no` are the skills answers, kept in picks.json (or held.json for a pick
    still held). A yes and a no for the same skill is refused. A skill the posting names
    that the tool did not list (one the session saw reading it) is taken as given.

    `draft` answers the pick's held questions with "draft it": it moves to picks.json.
    When it was held as a second role at one employer, the others there still waiting
    only on that are skipped: one role per employer. `skip` drops the pick."""
    if draft and skip:
        raise SystemExit("consent: --draft and --skip for the same pick")
    path = os.path.join(round_dir, "picks.json")
    with open(path, encoding="utf-8") as fh:
        staged = json.load(fh)
    held = _read_held(round_dir)
    p = _which(staged + held, which)
    both = _fold(yes) & _fold(no)
    if both:
        raise SystemExit(f"consent: both yes and no for {', '.join(sorted(both))}")
    spelled = {n.casefold(): n for n in p.get("ask_first") or []}
    for key, got in (("skills_yes", yes), ("skills_no", no)):
        other = "skills_no" if key == "skills_yes" else "skills_yes"
        keep = [n for n in p.get(key) or [] if n.casefold() not in _fold(got) | _fold(
            yes if key == "skills_no" else no)]
        new = [spelled.get(str(n).strip().casefold(), str(n).strip()) for n in got if str(n).strip()]
        p[key] = list(dict.fromkeys(keep + new))
        p[other] = [n for n in p.get(other) or [] if n.casefold() not in _fold(got)]
    if draft and p in held:
        held.remove(p)
        p["answered"] = [q["id"] for q in p.get("hold") or []]
        p["hold"] = []
        p.pop("status", None)
        p.pop("skip_reason", None)
        staged.append(p)
        if ONE_PER_EMPLOYER in p["answered"]:
            from company_key import key as company_key
            for o in held:
                ids = {q["id"] for q in o.get("hold") or []}
                if (company_key(o["company"]) == company_key(p["company"]) and ids == {ONE_PER_EMPLOYER}
                        and o.get("status") != "skipped"):
                    o["status"] = "skipped"
                    o["skip_reason"] = f"one role per employer: you chose {p['role']}"
    elif skip:
        if p in staged:
            staged.remove(p)
            held.append(p)
        p["status"] = "skipped"
        p["skip_reason"] = "you said not to draft it"
    _write_picks(round_dir, staged, held)
    return p


def waiting(round_dir: str) -> list[dict]:
    """The held picks still waiting on the person, each with its questions."""
    return [p for p in _read_held(round_dir) if p.get("status") != "skipped"]


def _audited(got) -> tuple[str, dict | None, list[str]]:
    """(verdict, draft, residual risks) from an audit file, in either shape."""
    got = got[0] if isinstance(got, list) and got else got
    if not isinstance(got, dict):
        return "", None, []
    if "verdict" in got or isinstance(got.get("draft"), dict):
        return (str(got.get("verdict") or "").strip().lower(), got.get("draft"),
                [str(x) for x in got.get("residual_risks") or []])
    return "", got, []


def audit(round_dir: str, only=()) -> list[dict]:
    """The grounding audit of each draft, code first: tools/draft_audit.audit_round."""
    import draft_audit
    return draft_audit.audit_round(round_dir, only)


def _held_back(got) -> str:
    """Why an audit record written by `audit` may not be rendered yet, or "".

    A record from the agent auditor has no `mechanical` part and is read as before."""
    if not isinstance(got, dict) or not isinstance(got.get("mechanical"), dict):
        return ""
    mech = got["mechanical"]
    if str(got.get("verdict") or "") == "needs_model":
        why = ", ".join(mech.get("reasons") or []) or "a question code cannot settle"
        return f"waiting on the model auditor ({why})"
    import draft_audit
    import draft_pack
    if isinstance(got.get("draft"), dict) and mech.get("draft_md5") != draft_audit.md5(got["draft"]):
        return "changed since it was audited: run stage_picks.py audit again"
    if mech.get("rules_hash") and mech["rules_hash"] != draft_pack.rules_hash():
        return "the profile changed since it was audited: run stage_picks.py audit again"
    return ""


def assemble(round_dir: str) -> tuple[list[dict], list[str], list[str]]:
    """(drafts, picks with no audited draft, picks the audit rejected, with why)."""
    with open(os.path.join(round_dir, "picks.json"), encoding="utf-8") as fh:
        staged = json.load(fh)
    waiting = [f"{p['company']}: {', '.join(unanswered(p))}" for p in staged if unanswered(p)]
    if waiting:
        raise SystemExit("assemble: the person has not been asked about every skill their "
                         "profile does not list, so nothing is assembled:\n  "
                         + "\n  ".join(waiting) + "\nAsk them, record it with "
                         "`stage_picks.py consent`, and draft again: the drafter needs the answers.")
    drafts, missing, rejected = [], [], []
    for p in staged:
        path = os.path.join(round_dir, f"audit_{p['slug']}.json")
        try:
            with open(path, encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, json.JSONDecodeError):
            missing.append(p["company"])
            continue
        verdict, d, risks = _audited(got)
        # The audit is the last read before anything reaches an employer. A
        # reject used to rely on the auditor deleting its own file, and one it
        # left behind was rendered like any other draft.
        if verdict == "reject":
            rejected.append(f"{p['company']} | {p['role']}"
                            + (f": {'; '.join(risks)}" if risks else ""))
            continue
        if not isinstance(d, dict):
            missing.append(p["company"])
            continue
        held = _held_back(got)
        if held:
            missing.append(f"{p['company']} ({held})")
            continue
        d = {k: v for k, v in d.items() if k != "check_output"}
        with open(p["file"], encoding="utf-8") as fh:
            text = fh.read()
        posting = untrusted.unfence(text)
        if posting == text:
            # No fence means a pick written by hand, and its header carries the
            # scorer's notes. `unfence` would hand back the whole file, so the
            # allocator would target the scorer's words as if the employer had
            # written them, and a phrase from a fit_why note can land on the
            # skills line.
            raise SystemExit(f"{p['file']} has no untrusted fence; re-stage it with `stage`")
        d = dict(d, abbr=p["abbr"], posting=posting)
        d.setdefault("company", p["company"])
        # The person's answers, kept with the draft (draft.json) and written into the
        # documents' header: the skills line prints each yes, check_claims reads both.
        if p.get("skills_yes"):
            d["consented_skills"] = list(p["skills_yes"])
        if p.get("skills_no"):
            d["declined_skills"] = list(p["skills_no"])
        if risks:
            # What an interviewer could still probe, which the audit found and nothing
            # kept: the kept draft carries it to the interview pack.
            d.setdefault("residual_risks", risks)
        drafts.append(d)
    with open(os.path.join(round_dir, "drafts.json"), "w", encoding="utf-8") as fh:
        json.dump(drafts, fh, indent=1)
        fh.write("\n")
    return drafts, missing, rejected


def _report(staged: list[dict], round_dir: str) -> None:
    import posting_profile
    for p in staged:
        print(f"staged {p['abbr']:<28} {p['company']} | {p['role']}")
        for line in posting_profile.lines(p["posting_profile"]) if p.get("posting_profile") else ():
            print(f"    {line}")
    held = [p for p in staged if p.get("hold")]
    if held:
        print("\nASK THE PERSON BEFORE DRAFTING (nothing is drafted for these until they answer):")
        said = set()
        for p in held:
            for q in p["hold"]:
                if q["question"] in said:
                    continue
                said.add(q["question"])
                print(f"  [{p['slug']}] {q['question']}")
        print("Record each answer: python3 tools/stage_picks.py consent "
              f"{round_dir} <slug> --draft (draft it) or --skip (leave it)")
    asks = [(p, question(p)) for p in staged if question(p)]
    if asks:
        print("\nASK THE PERSON FIRST, before any drafting (each question as written; "
              "why, only if they ask: " + WHY_ASK + "):")
        for p, q in asks:
            print(f"  [{p['slug']}] {q}")
        print("Record each answer: python3 tools/stage_picks.py consent "
              f"{round_dir} <slug> --yes <skill> ... --no <skill> ...")
    if len(held) == len(staged):
        print("\nNothing to draft yet: every pick waits on an answer above.")
    print(f"\nargs for the draft-applications workflow: {os.path.join(round_dir, 'picks.json')}")


def _report_audit(results: list[dict]) -> None:
    said = {"pass": "pass   ", "fixed": "fixed  ", "needs_model": "MODEL  ", "reject": "REJECT ",
            "missing": "MISSING"}
    for r in results:
        mech = r.get("mechanical") or {}
        why = ""
        if r["verdict"] == "needs_model":
            why = "needs the model auditor: " + ", ".join(mech.get("reasons") or [])
        elif r["verdict"] == "missing":
            why = f"no draft_{r['slug']}.json"
        elif r.get("old"):
            why = "audited by the agent auditor"
        else:
            why = "code checks clean" if r["verdict"] == "pass" else ""
        print(f"{said.get(r['verdict'], r['verdict']):8} {r['slug']:<28} {why}")
    waiting = [r["slug"] for r in results if r["verdict"] == "needs_model"]
    if waiting:
        print("\nThe model auditor reads only these, one call each (python3 tools/draft_audit.py "
              "packet <round_dir> <slug> prints what it reads): " + ", ".join(waiting))


def main() -> int:
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("round_dir")
    s.add_argument("picks", nargs="+")
    s.add_argument("--both", action="store_true",
                   help="the person wants every role picked at one employer drafted")
    one = sub.add_parser("single", help="one posting that came from no round: /apply")
    one.add_argument("round_dir", help="a scratch directory for this application")
    one.add_argument("--company", required=True)
    one.add_argument("--role", required=True)
    one.add_argument("--posting-file", required=True,
                     help="the posting text, verbatim, as fetched or pasted")
    one.add_argument("--url", default="")
    one.add_argument("--location", default="")
    one.add_argument("--fit", type=int, help="the 0-100 fit /apply Step 1 scored")
    one.add_argument("--deadline", default="")
    c = sub.add_parser("consent", help="record the person's answers for one pick")
    c.add_argument("round_dir")
    c.add_argument("pick", help="the slug or abbr stage printed, or the company")
    c.add_argument("--yes", nargs="*", default=[], help="skills they will claim and back up")
    c.add_argument("--no", nargs="*", default=[], help="skills that stay off")
    c.add_argument("--draft", action="store_true",
                   help="they answered the held questions with: draft it")
    c.add_argument("--skip", action="store_true", help="they said not to draft this pick")
    au = sub.add_parser("audit", help="the grounding audit of each draft, code first")
    au.add_argument("round_dir")
    au.add_argument("--only", nargs="+", default=[],
                    help="the slugs to audit: the roles that will be sent")
    au.add_argument("--json", action="store_true",
                    help="print only what fails, as JSON (what the drafter reads)")
    a = sub.add_parser("assemble")
    a.add_argument("round_dir")
    args = ap.parse_args()
    if args.cmd == "audit":
        results = audit(args.round_dir, args.only)
        if args.json:
            import draft_audit
            print(json.dumps([draft_audit.failing(r) for r in results], indent=1,
                             ensure_ascii=False))
        else:
            _report_audit(results)
        return 0 if all(r["verdict"] in ("pass", "fixed") for r in results) else 1
    if args.cmd == "consent":
        p = consent(args.round_dir, args.pick, args.yes, args.no, draft=args.draft,
                    skip=args.skip)
        print(f"{p['company']}: yes {', '.join(p.get('skills_yes') or []) or '(none)'}; "
              f"no {', '.join(p.get('skills_no') or []) or '(none)'}")
        if p.get("status") == "skipped":
            print(f"not drafted: {p.get('skip_reason')}")
        elif p.get("hold"):
            print("held until they answer: " + " | ".join(q["question"] for q in p["hold"]))
        left = unanswered(p)
        print(f"still to ask: {', '.join(left)}" if left else "nothing left to ask for this pick")
        for o in waiting(args.round_dir):
            print(f"still held: [{o['slug']}] {o['company']} | {o['role']}")
        return 0
    if args.cmd == "single":
        with open(args.posting_file, encoding="utf-8") as fh:
            body = fh.read()
        row = {"company": args.company, "title": args.role, "url": args.url,
               "location": args.location, "portal": "pasted", "desc": body}
        if args.fit is not None:
            row["fit"] = args.fit
        if args.deadline:
            row["deadline"] = args.deadline
        _report(stage(args.round_dir, ["1"], shortlist=[row]), args.round_dir)
        return 0
    if args.cmd == "stage":
        _report(stage(args.round_dir, args.picks, both=args.both), args.round_dir)
        return 0
    drafts, missing, rejected = assemble(args.round_dir)
    print(f"assembled {len(drafts)} drafts into {os.path.join(args.round_dir, 'drafts.json')}")
    if rejected:
        print("REJECTED BY THE AUDIT, not rendered:\n  " + "\n  ".join(rejected))
    if missing:
        print("NO AUDITED DRAFT for: " + ", ".join(missing))
    return 1 if (missing or rejected) else 0


if __name__ == "__main__":
    raise SystemExit(main())
