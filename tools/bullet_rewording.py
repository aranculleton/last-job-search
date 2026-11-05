#!/usr/bin/env python3
"""A resume bullet reworded for one application, to name a skill the person holds or said
yes to.

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

A skill the profile holds (skills.py ITEMS: deep learning, BigQuery) is the person's
standing yes, so it gets the same: where the posting names a held skill by name and no
bullet on the page names it, one to three of the chosen bullets are reworded to name it,
with no question asked (the maintainer, 2026-11-04: "If I say yes to a skill, we aren't
just dumping it at the bottom, we're integrating it into existing bullet points without
needing to ask me exact specifics"). `held_named` says which, one skill at a time
("PySpark" from "Apache Spark, PySpark"), and the code audit fails a resume where one sits
on the skills line alone while a bullet on the page could take it (`unplaced`). Where no
chosen bullet is work it plausibly belonged to, it stays on the skills line, and the audit
says so as a note rather than forcing it into unrelated work.

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
  added     the only words added are the skill's own and the linking words in LINKING;
            the only skill added is one the person said yes to for this application or a
            held one the posting names (`held_named`), and never one they said no to
  related   the work plausibly involved the skill (`related`, below)
  few       at most MAX_REWORDINGS, each a bullet the library holds, each once

"Work it clearly had nothing to do with", made a rule (`related`). A skill belongs with a
bullet when any of these holds, and with no other:

  1. family   the skill is in a tool family (`bridges.FAMILIES`, which a profile extends in
              skills.py FAMILIES) and the bullet's text already names another member of
              it: Looker beside the Power BI reporting it would sit next to
  2. theme    the skill's name, its family's name or a family member's name carries a
              theme cue (`allocate.THEME_CUES`, which a profile extends in bullets.py
              THEME_CUES) and the bullet is tagged with that theme in bullets.py:
              Snowflake, a cloud data warehouse, in a bullet tagged sql or cloud
  3. bridge   the profile's own bridge for the skill (skills.py BRIDGES) names in its
              `have` something the bullet's text names word for word
  4. profile  the candidate profile names the skill in that employer's own section, a
              bullet or its additional detail (`profile_work`): Google Analytics in a
              growth bullet at the employer whose section says the work was done in
              Google Analytics. What the person's own profile says they used somewhere is
              always related to the work there.

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


def skill_names(items) -> list[str]:
    """Each single skill the names in `items` carry: a yes recorded under a grouped name
    ("Apache Spark, PySpark") is each of its skills (skills_block.parts), so a bullet naming
    one of them names a yes."""
    import skills_block
    return clean_names(p for x in clean_names(items) for p in skills_block.parts(x))


def _squash(text: str) -> str:
    return re.sub(r"[\s\-.]+", "", str(text or "")).casefold()


def held_named(posting: str, company: str = "") -> list[str]:
    """The skills the profile holds (skills.py ITEMS) that this posting names by name, one
    skill at a time and as the profile spells it: "PySpark" where the item is "Apache
    Spark, PySpark", "BigQuery" for a posting's "Big Query". Each is the person's standing
    yes, so a bullet may be reworded to name it without asking.

    Only a skill the posting writes counts. An item its pattern finds under a looser word
    ("forecast" for demand forecasting, "stakeholders" for stakeholder reporting) is the
    work the bullets already describe, not a name a screen looks for, and an item that is
    also the employer's name (a company named after a tool) is not a skill mention."""
    body = plain(posting)
    if not body.strip():
        return []
    import skills_block
    out = []
    for _cat, item, pat in getattr(person.module("skills"), "ITEMS", ()):
        rx = re.compile(pat, re.I)
        found = [m.group(0) for m in rx.finditer(body) if m.group(0).strip()]
        if not found or (company and rx.search(str(company))):
            continue
        out += [p for p in skills_block.parts(item)
                if named(p, body) or any(_squash(f) == _squash(p) for f in found)]
    return clean_names(out)


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


_WORK: dict = {}


def profile_work() -> dict:
    """{employer key: [text, ...]}: what the candidate profile says the work at each
    employer was, its bullets and their additional detail (draft_pack.facts, the reader
    every fact id comes from), and never the resume library's trimmed copies. Read again
    when the profile's file changes (its time and size)."""
    import company_key
    try:
        where = person.path("01-candidate-profile.md")
        st = os.stat(where)
        stamp = (where, st.st_mtime_ns, st.st_size)
    except (OSError, person.NoProfile):
        return {}
    if _WORK.get("stamp") != stamp:
        import draft_pack
        work: dict = {}
        try:
            facts = draft_pack.facts()
        except Exception as e:  # a profile the reader cannot parse names nothing anywhere
            # Said, never silent: the rule then ties nothing, and the audit and the render
            # would both refuse what the profile places, which is the safe side.
            print(f"bullet_rewording: the candidate profile could not be read for where "
                  f"each skill was used ({e}); that rule ties nothing", file=sys.stderr)
            facts = []
        for f in facts:
            if f.get("resume") or f.get("kind") not in ("bullet", "detail", "reserve"):
                continue
            work.setdefault(company_key.key(f.get("employer") or ""), []).append(f["text"])
        _WORK.update(stamp=stamp, work=work)
    return _WORK["work"]


def _employer_name(bid: str) -> str:
    """The employer a bullet is at, as roles.py names it: bullets.py LIB is keyed by role,
    and an older title at one employer is "<employer> | <title>"."""
    key = employer(bid)
    try:
        import allocate
        return (allocate.BY_KEY.get(key) or {}).get("employer") or key
    except Exception:          # no roles to read: the library's key is the employer
        return key


def _profile_names_it(skill: str, bid: str) -> str:
    """The employer whose own section of the candidate profile names `skill`, when it is
    the employer of bullet `bid`; else "". The skill is matched as check_claims grounds a
    skill: any case, a space or a hyphen between words."""
    import check_claims
    import company_key
    emp = _employer_name(bid)
    if not emp or not str(skill or "").strip():
        return ""
    rx = check_claims.skill_pattern(skill)
    texts = profile_work().get(company_key.key(emp), ())
    return emp if any(rx.search(t) for t in texts) else ""


def related(skill: str, bid: str) -> str:
    """Why the work bullet `bid` describes plausibly involved `skill`, or "" when nothing
    ties them: the module docstring's four rules, in order."""
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
    emp = _profile_names_it(skill, bid)
    if emp:
        return f"the candidate profile names {skill} in the work at {emp}"
    return ""


def candidates(posting: str, yes, budget: int = 12, held=None, company: str = "",
               no=()) -> list[dict]:
    """[{"id", "employer", "text", "skills", "held"}]: the bullets the allocator chooses
    for this posting that a skill may be named in, each with the skills it is related to
    and does not name already. `skills` is every one of them: the yes answers, and the held
    skills the posting names (`held_named`, unless `held` is given) that no chosen bullet
    names yet, which are also in `held`. What the drafting pack offers (tools/draft_pack.py)."""
    import allocate
    yes = skill_names(yes)
    alloc = allocate.allocate(posting or "", budget=budget)
    page = [original(b) or "" for ids in alloc.values() for b in ids]
    said = {x.casefold() for x in yes} | {x.casefold() for x in skill_names(no)}
    held = [h for h in skill_names(held_named(posting, company) if held is None else held)
            if h.casefold() not in said and not any(named(h, t) for t in page)]
    if not (yes or held):
        return []
    out = []
    for emp, ids in alloc.items():
        for bid in ids:
            text = original(bid) or ""
            fit = [y for y in yes + held if not named(y, text) and related(y, bid)]
            if fit:
                out.append({"id": bid, "employer": emp, "text": plain(text), "skills": fit,
                            "held": [y for y in fit if y in held]})
    return out


# ------------------------------------------------------------------ the guard

def _problem(bid, rule, text, fix) -> dict:
    return {"id": str(bid or ""), "rule": rule, "text": str(text)[:220], "fix": fix}


SHAPE = 'bullet_rewordings is a list of {"id": <bullet id>, "skill": <a yes>, "text": <the bullet>}'


def check_one(bid: str, new: str, yes, no=(), skill=None, held=()) -> list[dict]:
    """What is wrong with rewording bullet `bid` as `new`, for an application whose yes
    answers are `yes`, no answers `no`, and whose posting names the held skills `held`
    (held_named). [] when the guard accepts it. A held skill is the person's standing yes:
    it passes every other rule exactly as a yes does."""
    out = []
    old = original(bid)
    if old is None:
        return [_problem(bid, "unknown-bullet", bid, "no bullet in the profile has this id: "
                         "reword only a bullet the drafting pack lists")]
    no = clean_names(no)
    nos = {x.casefold() for x in no}
    yes = clean_names(skill_names(yes) + [h for h in skill_names(held) if h.casefold() not in nos])
    po, pn = plain(old), plain(new)
    if not yes:
        return [_problem(bid, "no-yes", pn, "a bullet is reworded only to name a skill the "
                         "person said yes to for this application, or one they hold that the "
                         "posting names, and there is none: leave bullet_rewordings out")]
    added = [y for y in yes if named(y, pn) and not named(y, po)]
    if skill:
        for s in skill_names(skill if isinstance(skill, list) else [skill]):
            if s.casefold() not in {y.casefold() for y in yes}:
                out.append(_problem(bid, "unconsented-skill", s, "the person did not say yes "
                                    "to this for this application, and it is not a skill "
                                    "they hold that the posting names: name only one of those"))
    if not added:
        out.append(_problem(bid, "names-no-yes", pn, "it names none of the person's yes "
                            "answers or the held skills the posting names, which is all a "
                            "rewording is for: name one, or leave the bullet out of "
                            "bullet_rewordings"))
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
                                      "for this application, and it is not a skill they hold "
                                      "that the posting names: name only one of those"))
        out.append(_problem(bid, rule, n, fix))
        flagged_words |= set(tokens(n))
    for x in no:
        if named(x, pn) and not named(x, po) and not any(p["text"] == x for p in out):
            out.append(_problem(bid, "declined-skill", x, "the person said no to claiming "
                                "this: take it out"))
            flagged_words |= set(tokens(x))
    t_old, t_new = set(tokens(po)), set(tokens(pn))
    # The words of a skill the text names whole, never a word of one it does not: a held
    # "data quality testing" lends no "testing" to a bullet that names only BigQuery.
    allowed = set(LINKING) | {w for y in yes if named(y, pn) for w in tokens(y)}
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


def problems(rewordings, yes=(), no=(), held=()) -> list[dict]:
    """Everything the guard refuses in a draft's bullet_rewordings, [] when it accepts it.
    `held` is the held skills the posting names (held_named)."""
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
        out += check_one(bid, r["text"], yes, no, r.get("skill"), held)
    return out


def held_all() -> list[str]:
    """Every single skill the profile holds (skills.py ITEMS), as it spells them."""
    import skills_block
    return clean_names(p for _c, item, _p in getattr(person.module("skills"), "ITEMS", ())
                       for p in skills_block.parts(item))


def answers(a: dict, pick: dict | None = None, posting: str | None = None) -> tuple:
    """(yes, no, held): what a draft's rewordings are judged against, the one reading the
    code audit (tools/draft_audit.py) and the renderer (usable, through fit_to_page and
    render_application) both take. The answers are the pick's where it has them, else the
    draft's own (assemble copies one into the other); `held` is the held skills the posting
    names, and with no posting text to hand (a kept draft.json re-rendered without its
    job_posting.md) every held skill, since holding one is the person's yes whatever the
    posting. The audit refused nothing the render then took, but the render refused a held
    skill the audit had passed, and printed the profile's own bullet (the maintainer,
    2026-11-05: the two checks disagreed)."""
    pick = pick if isinstance(pick, dict) else {}
    a = a if isinstance(a, dict) else {}
    yes = list(pick.get("skills_yes") or a.get("consented_skills") or [])
    no = list(pick.get("skills_no") or a.get("declined_skills") or [])
    text = str((a.get("posting") if posting is None else posting) or "")
    company = str(a.get("company") or pick.get("company") or "")
    held = held_named(text, company) if text.strip() else held_all()
    return yes, no, held


def usable(a: dict) -> tuple[dict, list[str]]:
    """({bullet id: plain text}, [why each one left out]) for a draft about to be rendered:
    every rewording the guard accepts for this draft's own answers (consented_skills,
    declined_skills) and the held skills its posting names, and none it refuses. The
    renderer uses these and nothing else, so a draft.json edited by hand can never put an
    unguarded claim on the page."""
    got = a.get(FIELD)
    if got in (None, "", [], {}):
        return {}, []
    yes, no, held = answers(a)
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
        bad = check_one(bid, str(r.get("text") or ""), yes, no, r.get("skill"), held) \
            if str(r.get("text") or "").strip() else [_problem(bid, "malformed", "", SHAPE)]
        if bad or bid in use:
            why.append(f"{bid} is not used, the profile's own bullet is: "
                       + ("; ".join(f"{p['rule']} ({p['text']})" for p in bad) or "reworded twice"))
            use.pop(bid, None)
            continue
        use[bid] = plain(r["text"])
    return use, why


def unplaced(posting: str, bullets, rewordings=None, yes=(), no=(),
             company: str = "") -> tuple[list[dict], list[str]]:
    """(problems, notes) for each skill the person said yes to, or holds and the posting
    names (held_named), that no bullet on this resume names, `bullets` being the ids the
    page prints (read with this draft's rewordings the guard accepts).

    A problem where a bullet on the page could take it (`related`) and the rewordings have
    room: one already reworded is such a bullet, or fewer than MAX_REWORDINGS are used. The
    skill would otherwise sit on the skills line alone, which is "dumping it at the bottom"
    (the maintainer, 2026-11-04). A note, never a failure, where nothing can take it: no
    bullet on the page is work the profile ties it to, or the rewordings are spent on
    bullets that are not. Forcing it into unrelated work would be the claim the guard
    exists to refuse, so there it stays on the skills line, and the note says why."""
    ids = [str(b).strip() for b in bullets or () if str(b).strip()]
    nos = {x.casefold() for x in clean_names(no)}
    skills = [s for s in clean_names(skill_names(yes) + held_named(posting, company))
              if s.casefold() not in nos]
    if not ids or not skills:
        return [], []
    a = {FIELD: rewordings, "consented_skills": list(yes or ()), "declined_skills": list(no or ()),
         "posting": posting, "company": company}
    use, _why = usable(a)
    page = {b: use.get(b) or plain(original(b) or "") for b in ids}
    reworded = {str(r.get("id") or "").strip() for r in rewordings or ()
                if isinstance(r, dict)} if isinstance(rewordings, list) else set()
    room = len(reworded) < MAX_REWORDINGS
    out, notes = [], []
    for s in skills:
        if any(named(s, t) for t in page.values()):
            continue
        takers = [b for b in ids if not named(s, original(b) or "") and related(s, b)]
        open_ = [b for b in takers if room or b in reworded]
        if open_:
            out.append(_problem("", "skill-not-in-work", s,
                                f"the posting names {s}, which the person holds or said yes "
                                "to, and no bullet on this resume names it, so it sits on the "
                                "skills line alone: without asking, name it in one to three of "
                                f"these bullets, the work that plausibly used it ({', '.join(open_)}), "
                                "in bullet_rewordings"))
        elif takers:
            notes.append(f"{s} stays on the skills line: {MAX_REWORDINGS} bullets are reworded "
                         "already, and none of them is work it belongs to")
        else:
            notes.append(f"{s} stays on the skills line alone: no bullet on this resume is "
                         "work the profile ties it to (its tool family, its themes, its "
                         "bridges, or the profile naming it at that employer)")
    return out, notes


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
        d_yes, d_no, held = answers(d)
        yes = args.yes if args.yes is not None else d_yes
        no = args.no if args.no is not None else d_no
        for p in problems(d.get(FIELD), yes, no, held):
            bad += 1
            print(f"{d.get('company', '?')}: {p['id'] or FIELD}: [{p['rule']}] {p['text']}: {p['fix']}")
    if not bad:
        print("every reworded bullet passes the guard")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
