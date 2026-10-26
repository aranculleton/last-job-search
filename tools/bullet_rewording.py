#!/usr/bin/env python3
"""A resume bullet reworded for one application, to name a skill the person said yes to.

A yes from `tools/stage_picks.py consent` reached the skills line, and the summary or the
letter where the posting asks for it, while the bullets came unchanged from
`profile/bullets.py` through `tools/allocate.py`. So a skill the person had just claimed
sat alone on the skills line with no work beside it that used it. People say yes to skills
that are plausible for them anyway, so a light, honest tweak to a bullet beats a keyword on
its own.

So a draft object may carry `bullet_rewordings`: a few of the bullets the allocator chooses,
each the same bullet with the same facts and numbers and the consented skill named where
the real work plausibly involved it.

    "bullet_rewordings": [{"id": "BH_REPORT", "skill": "Looker",
                           "text": "Owned the Power BI and Looker service-level reporting ..."}]

They apply to that application's resume and nothing else: `render_application.build()`
uses the reworded text in place of the library's for that draft only, `tools/outreach.py`
keeps them in the application's `draft.json` so a re-render reproduces them, and nothing
here or anywhere else writes them back to the profile. The allocator still decides which
bullets are on the page; a rewording of a bullet the page has no room for is not used.

THE GUARD, all of it code (`problems`), run by the code audit (`tools/draft_audit.py`) and
again by the renderer, which uses no rewording that fails it:

  numbers   the numeric tokens are the same multiset: every run of digits, and every figure
            `check_numbers.figures` reads, words included ("four hours"), with the
            consented skill's own name left out of both (a skill can carry a digit: GA4)
  kept      every word of the original is still there, and every tool or skill it names
            (`vocabulary`): a tool used at a named employer is never replaced by the yes,
            only joined by it
  added     the only words added are the consented skill's own and the linking words in
            LINKING; the only skill added is one the person said yes to for this
            application, and never one they said no to
  related   the work plausibly involved the skill (`related`, below)
  few       at most MAX_REWORDINGS, each a bullet the library holds, each once

"Work it clearly had nothing to do with", made a rule (`related`). A consented skill
belongs with a bullet when any of these holds, and with no other:

  1. family   the skill is in a tool family (`bridges.FAMILIES`, which a profile extends in
              skills.py FAMILIES) and the bullet's text already names another member of
              it: Looker beside the Power BI reporting it would sit next to
  2. theme    the skill's name, its family's name or a family member's name carries a
              theme cue (`allocate.THEME_CUES`, which a profile extends in bullets.py
              THEME_CUES) and the bullet is tagged with that theme in bullets.py:
              Snowflake, a cloud data warehouse, in a bullet tagged sql or cloud
  3. bridge   the profile's own bridge for the skill (skills.py BRIDGES) names in its
              `have` something the bullet's text names word for word

These are the tables the app already uses to say which tools stand in for each other and
what each bullet is about, so the rule never needs a list of its own. A skill that none of
them ties to any chosen bullet stays on the skills line alone. A profile widens the rule
only by saying more about the skill, never about one bullet.

    python3 tools/bullet_rewording.py <draft.json> [--yes A B ...]   # the guard, on a draft
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

FIELD = "bullet_rewordings"
# "At most a few bullets": enough to put a yes beside the work that used it, never a
# resume rewritten around the posting.
MAX_REWORDINGS = 3
# The words a rewording may add besides the skill's own: what joins a tool to the work
# ("in Python, SQL and Snowflake", "on Snowflake", "using Looker"). Never a verb, an
# adjective or a qualifier, each of which would be a new claim.
LINKING = frozenset("""a an the and or in on with using via through into onto from for to of
by as at its their both across within alongside plus""".split())

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:[.'][a-z0-9]+)*")
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def plain(text) -> str:
    """A bullet's words as a reader reads them (draft_pack.plain): its LaTeX gone."""
    import draft_pack
    return draft_pack.plain(str(text or "")).replace("’", "'").replace("‘", "'")


def _named_rx(name: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(re.sub(r"\s+", " ", str(name).strip()))
                      + r"(?!\w)", re.I)


def named(name: str, text: str) -> bool:
    """Whether `text` names `name`, as a whole word or phrase, in any case."""
    return bool(str(name or "").strip()) and bool(_named_rx(name).search(plain(text)))


def clean_names(items) -> list[str]:
    return list(dict.fromkeys(re.sub(r"\s+", " ", str(x)).strip() for x in items or ()
                              if str(x).strip()))


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(plain(text).lower())


# ------------------------------------------------------------------ the library

def original(bid: str) -> str | None:
    """The profile's own text for a bullet id (an old id kept for old drafts resolves to
    the bullet it names), or None when the library holds no such bullet."""
    import bullet_library as BL
    bid = str(bid or "").strip()
    if bid in BL.TEXT:
        return BL.TEXT[bid]
    target = BL.RENDER_ALIASES.get(bid)
    return BL.TEXT.get(target) if target else None


def _themes(bid: str) -> set:
    import bullet_library as BL
    bid = str(bid or "").strip()
    return set(BL.THEMES.get(bid) or BL.THEMES.get(BL.RENDER_ALIASES.get(bid, ""), ()) or ())


def employer(bid: str) -> str:
    import bullet_library as BL
    bid = str(bid or "").strip()
    return BL.EMPLOYER.get(bid) or BL.EMPLOYER.get(BL.RENDER_ALIASES.get(bid, ""), "") or ""


# ------------------------------------------------------------------ what names a skill

@functools.lru_cache(maxsize=1)
def vocabulary() -> tuple:
    """((name, pattern), ...): every tool and skill the app and the profile can name. The
    profile's inventory (skills.py ITEMS), the tool families (bridges.FAMILIES), the
    profile's bridges and not-held list, and what the fit score docks as not held."""
    import bridges
    skills = person.module("skills")
    out = [(item, re.compile(pat, re.I)) for _cat, item, pat in getattr(skills, "ITEMS", ())]
    for _fam, *members in bridges.FAMILIES:
        out += [(name, re.compile(pat, re.I)) for name, pat in members]
    out += [(e["asked"], re.compile(e["pattern"], re.I)) for e in getattr(skills, "BRIDGES", ())
            if e.get("pattern")]
    out += [(name, re.compile(pat, re.I))
            for name, (pat, _why) in (getattr(skills, "NOT_HELD", None) or {}).items() if pat]
    search = person.module("search") if person.exists("search.py") else None
    out += [("", rx if hasattr(rx, "finditer") else re.compile(rx, re.I))
            for rx, _pts, _why in (getattr(search, "FIT_MISSING", None) or ())]
    return tuple(out)


def mentions(text: str) -> dict:
    """{name: [(start, end), ...]} for each tool or skill `text` names (vocabulary())."""
    body = plain(text)
    out: dict = {}
    for name, rx in vocabulary():
        for m in rx.finditer(body):
            if m.group(0).strip():
                out.setdefault(name or m.group(0), []).append(m.span())
    return out


# ------------------------------------------------------------------ the numbers

def numbers(text: str, leave_out=()) -> tuple[list, list]:
    """(figures, digit runs), each sorted: every number `text` states, as check_numbers
    reads one (value and unit, magnitudes folded, words included) and as bare digits. The
    names in `leave_out` (the consented skills) are taken out first."""
    import check_numbers as N
    body = plain(text)
    for name in leave_out:
        body = _named_rx(name).sub(" ", body)
    figs = []
    for _a, _b, value, unit, _shown in N.figures(body):
        try:
            n = float(str(value).replace(",", ""))
        except ValueError:
            continue
        u = re.sub(r"\s+", " ", (unit or "").lower()).rstrip("s")
        u = N._UNIT_ALIAS.get(u, u)
        if u in N._MAGNITUDE:
            n, u = n * N._MAGNITUDE[u], ""
        figs.append((round(n, 6), u))
    return sorted(figs), sorted(_DIGITS.findall(body.replace(",", "")))


# ------------------------------------------------------------------ related

def _cue_themes(words: str) -> set:
    import allocate
    low = str(words or "").lower()
    return {t for t, pats in allocate.CUE_RE.items() if any(p.search(low) for p in pats)}


def _families(skill: str) -> list:
    """[(family, [(name, compiled pattern), ...])] for each tool family `skill` is in."""
    import bridges
    out = []
    for fam, *members in bridges.FAMILIES:
        rxs = [(name, re.compile(pat, re.I)) for name, pat in members]
        if any(rx.search(skill) for _n, rx in rxs) or \
                any(name.casefold() == skill.casefold() for name, _ in rxs):
            out.append((fam, rxs))
    return out


def related(skill: str, bid: str) -> str:
    """Why the work bullet `bid` describes plausibly involved `skill`, or "" when nothing
    ties them: the module docstring's three rules, in order."""
    text = plain(original(bid) or "")
    if not text:
        return ""
    fams = _families(skill)
    for fam, members in fams:
        for name, rx in members:
            if not rx.search(skill) and name.casefold() != skill.casefold() and rx.search(text):
                return f"{skill} is the same kind of tool ({fam}) as {name}, which this work names"
    names = [skill] + [fam for fam, _m in fams] + [n for _f, ms in fams for n, _rx in ms]
    cued = set().union(*(_cue_themes(n) for n in names))
    hit = sorted(cued & _themes(bid))
    if hit:
        kind = f" (a {fams[0][0]})" if fams else ""
        return (f"{skill}{kind} is {' and '.join(hit)} work, and bullets.py tags this bullet "
                f"{' and '.join(hit)}")
    for e in getattr(person.module("skills"), "BRIDGES", ()):
        if e.get("pattern") and re.search(e["pattern"], skill, re.I):
            for have in e.get("have") or ():
                if named(have, text):
                    return f"the profile's bridge for {skill} names {have}, which this work names"
    return ""


def candidates(posting: str, yes, budget: int = 12) -> list[dict]:
    """[{"id", "employer", "text", "skills"}]: the bullets the allocator chooses for this
    posting that a yes may be named in, each with the yes answers it is related to and does
    not name already. What the drafting pack offers (tools/draft_pack.py)."""
    import allocate
    yes = clean_names(yes)
    if not yes:
        return []
    out = []
    for emp, ids in allocate.allocate(posting or "", budget=budget).items():
        for bid in ids:
            text = original(bid) or ""
            fit = [y for y in yes if not named(y, text) and related(y, bid)]
            if fit:
                out.append({"id": bid, "employer": emp, "text": plain(text), "skills": fit})
    return out


# ------------------------------------------------------------------ the guard

def _problem(bid, rule, text, fix) -> dict:
    return {"id": str(bid or ""), "rule": rule, "text": str(text)[:220], "fix": fix}


SHAPE = 'bullet_rewordings is a list of {"id": <bullet id>, "skill": <a yes>, "text": <the bullet>}'


def check_one(bid: str, new: str, yes, no=(), skill=None) -> list[dict]:
    """What is wrong with rewording bullet `bid` as `new`, for an application whose yes
    answers are `yes` and no answers `no`. [] when the guard accepts it."""
    out = []
    old = original(bid)
    if old is None:
        return [_problem(bid, "unknown-bullet", bid, "no bullet in the profile has this id: "
                         "reword only a bullet the drafting pack lists")]
    yes, no = clean_names(yes), clean_names(no)
    po, pn = plain(old), plain(new)
    if not yes:
        return [_problem(bid, "no-yes", pn, "a bullet is reworded only to name a skill the "
                         "person said yes to for this application, and there is none: leave "
                         "bullet_rewordings out")]
    added = [y for y in yes if named(y, pn) and not named(y, po)]
    if skill:
        for s in clean_names(skill if isinstance(skill, list) else [skill]):
            if s.casefold() not in {y.casefold() for y in yes}:
                out.append(_problem(bid, "unconsented-skill", s, "the person did not say yes "
                                    "to this for this application: name only a yes"))
    if not added:
        out.append(_problem(bid, "names-no-yes", pn, "it names none of the person's yes "
                            "answers, which is all a rewording is for: name one, or leave the "
                            "bullet out of bullet_rewordings"))
    # Numbers: the same, every one.
    f_old, d_old = numbers(po, yes)
    f_new, d_new = numbers(pn, yes)
    if f_old != f_new or d_old != d_new:
        out.append(_problem(bid, "numbers", pn, "the numbers must be the profile's own, every "
                            f"one: it has {', '.join(d_old) or 'none'} and this has "
                            f"{', '.join(d_new) or 'none'}"))
    # Every tool and skill the work names stays named.
    m_old, m_new = mentions(po), mentions(pn)
    gone = [n for n in m_old if n not in m_new]
    where = employer(bid)
    for n in gone:
        swap = f", and {', '.join(added)} is named instead" if added else ""
        out.append(_problem(bid, "tool-replaced", n, f"{n} is what this work at {where or 'the employer'} "
                            f"used{swap}: a yes is named beside the tool the work used, never "
                            "in its place"))
    # Nothing added but the yes: no other tool, and never a no.
    spans = [m.span() for y in yes for m in _named_rx(y).finditer(pn)]
    flagged_words: set = set()
    for n, at in m_new.items():
        if n in m_old:
            continue
        if all(any(a >= s and b <= e for s, e in spans) for a, b in at):
            continue
        said_no = [x for x in no if _named_rx(x).search(pn)]
        rule, fix = (("declined-skill", "the person said no to claiming this: take it out")
                     if said_no else ("unconsented-skill", "the person did not say yes to this "
                                      "for this application: name only a yes"))
        out.append(_problem(bid, rule, n, fix))
        flagged_words |= set(tokens(n))
    for x in no:
        if named(x, pn) and not named(x, po) and not any(p["text"] == x for p in out):
            out.append(_problem(bid, "declined-skill", x, "the person said no to claiming "
                                "this: take it out"))
            flagged_words |= set(tokens(x))
    t_old, t_new = set(tokens(po)), set(tokens(pn))
    allowed = set(LINKING) | {w for y in yes for w in tokens(y)}
    extra = sorted(t_new - t_old - allowed - flagged_words)
    if extra:
        out.append(_problem(bid, "words-added", ", ".join(extra), "a rewording adds the yes "
                            "and a linking word (in, on, with, using, and) and nothing else: "
                            "every other word is a new claim"))
    dropped = sorted(t_old - t_new - set(LINKING) - {w for n in gone for w in tokens(n)})
    if dropped:
        out.append(_problem(bid, "words-dropped", ", ".join(dropped), "keep every word of the "
                            "profile's bullet: a qualifier taken out changes what it claims"))
    # The work plausibly involved the skill.
    for y in added:
        if not related(y, bid):
            out.append(_problem(bid, "unrelated", y, f"nothing in the profile ties {y} to "
                                "this work (its tool family, its themes in bullets.py, the "
                                "profile's bridges): leave it on the skills line"))
    return out


def problems(rewordings, yes=(), no=()) -> list[dict]:
    """Everything the guard refuses in a draft's bullet_rewordings, [] when it accepts it."""
    if rewordings in (None, "", [], {}):
        return []
    if not isinstance(rewordings, list):
        return [_problem("", "malformed", type(rewordings).__name__, SHAPE)]
    out = []
    if len(rewordings) > MAX_REWORDINGS:
        out.append(_problem("", "too-many", f"{len(rewordings)} rewordings",
                            f"at most {MAX_REWORDINGS} bullets are reworded for one "
                            "application: keep the ones where the yes matters most"))
    seen = set()
    for r in rewordings:
        if not (isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"].strip()
                and isinstance(r.get("text"), str) and r["text"].strip()):
            out.append(_problem("", "malformed", str(r)[:80], SHAPE))
            continue
        bid = r["id"].strip()
        if bid in seen:
            out.append(_problem(bid, "duplicate", bid, "one rewording a bullet"))
            continue
        seen.add(bid)
        out += check_one(bid, r["text"], yes, no, r.get("skill"))
    return out


def usable(a: dict) -> tuple[dict, list[str]]:
    """({bullet id: plain text}, [why each one left out]) for a draft about to be rendered:
    every rewording the guard accepts for this draft's own answers (consented_skills,
    declined_skills), and none it refuses. The renderer uses these and nothing else, so a
    draft.json edited by hand can never put an unguarded claim on the page."""
    got = a.get(FIELD)
    if got in (None, "", [], {}):
        return {}, []
    yes, no = a.get("consented_skills") or [], a.get("declined_skills") or []
    if not isinstance(got, list):
        return {}, [f"{FIELD} is not a list, so none is used"]
    use, why = {}, []
    over = len(got) > MAX_REWORDINGS
    for r in got:
        if not isinstance(r, dict) or not str(r.get("id") or "").strip():
            why.append(f"a rewording with no bullet id is not used: {str(r)[:60]}")
            continue
        bid = r["id"].strip()
        if over:
            why.append(f"{bid} is not used: more than {MAX_REWORDINGS} bullets are reworded")
            continue
        bad = check_one(bid, str(r.get("text") or ""), yes, no, r.get("skill")) \
            if str(r.get("text") or "").strip() else [_problem(bid, "malformed", "", SHAPE)]
        if bad or bid in use:
            why.append(f"{bid} is not used, the profile's own bullet is: "
                       + ("; ".join(f"{p['rule']} ({p['text']})" for p in bad) or "reworded twice"))
            use.pop(bid, None)
            continue
        use[bid] = plain(r["text"])
    return use, why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check a draft's reworded resume bullets.")
    ap.add_argument("draft", help="a draft object, or a list of them (drafts.json, draft.json)")
    ap.add_argument("--yes", nargs="*", help="the yes answers (default: the draft's own)")
    ap.add_argument("--no", nargs="*", help="the no answers (default: the draft's own)")
    args = ap.parse_args(argv)
    with open(args.draft, encoding="utf-8") as fh:
        got = json.load(fh)
    bad = 0
    for d in got if isinstance(got, list) else [got]:
        yes = args.yes if args.yes is not None else d.get("consented_skills") or []
        no = args.no if args.no is not None else d.get("declined_skills") or []
        for p in problems(d.get(FIELD), yes, no):
            bad += 1
            print(f"{d.get('company', '?')}: {p['id'] or FIELD}: [{p['rule']}] {p['text']}: {p['fix']}")
    if not bad:
        print("every reworded bullet passes the guard")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
