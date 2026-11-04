#!/usr/bin/env python3
"""Does this employer clear the bar the profile sets?

A candidate's bar is a rule they have stated: the kind of employer worth an
application. Left in prose it is applied by eye, every round, by a model paid to
strike the same employers out again; a rule a person has stated twice belongs
in code. The bar itself, the employers it names and the reasons printed are
the profile's (search.py, BAR_*); this module reads them and applies them in a
fixed order. A verdict of pay, prestige or signal clears the bar; none does not.

Verdicts, first match wins:

  excluded  a hard rule the profile states: a sector (BAR_EXCLUDED), an
            employer declined by name (BAR_DECLINED), a public-sector agency
            named outright (BAR_NAMED_PUBLIC), or any other public body, by
            name (BAR_PUBLIC) or by its posting saying what it is
            (PUBLIC_SAID, with the employer the subject, and read last, only
            for an employer on none of the lists and judged by nobody), unless
            the posting states a range that reaches the target band.
            Public-adjacent employers on the profile's target list
            (BAR_PUBLIC_TARGETS) never land here.
  pay       a stated range whose midpoint reaches the target band, or a tier-1
            employer, whose pay is top of market by definition.
  prestige  a tier-2 employer, a public body the profile names as a prestige
            exception (BAR_PUBLIC_PRESTIGE), or a target-list public-adjacent
            employer.
  signal    frontier AI (BAR_FRONTIER), elite-VC and YC-backed, or an
            established technology company: the name that says where the next
            move is going rather than how big the employer is.
  none      none of the three. FLAGGED, NOT CUT. An unknown name with no stated
            range is exactly the case where the posting knows more than this
            file, and "rank down, do not cut" still holds for everything except
            the stated hard rules. Its reason says when the employer is on none
            of the profile's lists (`listed()` is False): then the verdict says
            nothing about the employer, only that nobody has judged it yet. A
            global bank and a financial-data firm came back "none" for a person
            whose lists were written for another sector, and read as failing the
            bar in networking. Claude judges such a name once and records it
            (`bar.py judge`, profile/employers_judged.json), and every later
            verdict reads the judgement.

    python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"
    python3 tools/bar.py unjudged [documents/rounds/<round>.json]

    python3 tools/bar.py "Quayside Foods" "City of Somewhere" "Acme AI"
"""

from __future__ import annotations

import contextlib
import datetime
import glob
import hashlib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import company_key as _ck  # noqa: E402
from company_key import key as company_key  # noqa: E402
from opportunity import YC_AND_BACKED, _names_in, tier  # noqa: E402
from sector import tech_name  # noqa: E402
from text_screen import salary_range  # noqa: E402

EXCLUDED, PAY, PRESTIGE, SIGNAL, NONE = "excluded", "pay", "prestige", "signal", "none"

import person  # noqa: E402

_S = person.module("search")
CUR = getattr(_S, "CURRENCY_SYMBOL", "$")
TARGET_MIDPOINT = getattr(_S, "BAR_TARGET_MIDPOINT", _S.SALARY_TARGET)
_NEVER = re.compile(r"(?!x)x")
EXCLUDED_RULES = list(getattr(_S, "BAR_EXCLUDED", []))
DECLINED = dict(getattr(_S, "BAR_DECLINED", {}))
PUBLIC_PRESTIGE, _PRESTIGE_WHY = getattr(_S, "BAR_PUBLIC_PRESTIGE", (_NEVER, ""))
PENSIONS, _TARGETS_WHY = getattr(_S, "BAR_PUBLIC_TARGETS", (_NEVER, ""))
NAMED_PUBLIC, _NAMED_WHY = getattr(_S, "BAR_NAMED_PUBLIC", (_NEVER, ""))
PUBLIC, _PUBLIC_PAID, _PUBLIC_WHY = getattr(_S, "BAR_PUBLIC", (_NEVER, "", ""))
# A different company wearing a tiered company's name: `_names_in` matches a
# short tiered name inside a longer, unrelated one.
COLLISIONS = getattr(_S, "BAR_COLLISIONS", _NEVER)
FRONTIER = set(getattr(_S, "BAR_FRONTIER", ()))

# A public body the profile's names miss, read from its own posting. The public rule read
# only the employer's name, so a provincial agency named on none of the profile's lists came
# back "none", a flag and never a cut, and reached a shortlist although the profile excludes
# public bodies (2026-11-03). Its posting said what it was. Only the employer describing
# itself counts: "is a Crown agency", "an agency of the Government of", "join the ... Public
# Service". A posting about working with public bodies ("our public sector clients") names
# a client, not the employer, and is never read as one. Read only where the profile
# excludes public bodies (BAR_PUBLIC), and the paid exception holds as for a name.
#
# And only with the employer as the subject: "We are a ...", "<the employer> is a ...",
# "join the ... Public Service". Any "is a/as the <public body>" anywhere matched a
# consultancy's "clients within the federal public service" and a bank's "OSFI, as the
# federal regulatory body", and both came back excluded (the release review, 2026-11-03).
# It is read only for an employer on none of the profile's lists, too (verdict).
_PUBLIC_KIND = (r"(?:(?:crown|provincial|federal|state|government|governmental|municipal|"
                r"regulatory|executive|non-departmental public)\s+(?:agency|corporation|body|"
                r"authority)|public\s+(?:agency|body|authority)|(?:agency|body|corporation|"
                r"department)\s+of\s+the\s+(?:government|province|state)\s+of)\b")
_ITS_KIND = r"(?:an?|the)\s+(?:[\w-]+\s+){0,3}?" + _PUBLIC_KIND
PUBLIC_SAID = re.compile(r"\b(?:we\s+are|we're|we’re)\s+(?P<said>" + _ITS_KIND + ")"
                         r"|\b(?P<joins>(?:join|joining)\s+the\s+(?:[\w.]+\s+){0,2}"
                         r"(?:public|civil)\s+service)\b", re.I)


def _named(company: str) -> re.Pattern | None:
    """The employer's own name, then "is a <public body>" or ", a <public body>"."""
    names = {" ".join(str(company or "").split()), own_name(company)}
    alts = ["\\W+".join(re.escape(w) for w in n.split()) for n in names if n and n.split()]
    if not alts:
        return None
    return re.compile(r"\b(?:%s)\b(?:\s*\([^)]{0,60}\))?(?:\s*,\s*(?P<app>%s)|\s+(?P<is>is\s+%s))"
                      % ("|".join(sorted(alts, key=len, reverse=True)), _ITS_KIND, _ITS_KIND),
                      re.I)


def public_said(posting: str = "", company: str = "") -> str:
    """The words in which a posting says its own employer is a public body, or "": "we are
    a crown agency", "<company> is a provincial agency", "join the ... Public Service".
    Nothing is read when the profile does not exclude public bodies."""
    if PUBLIC is _NEVER:
        return ""
    text = str(posting or "")
    named = _named(company)
    m = (named.search(text) if named else None) or PUBLIC_SAID.search(text)
    if not m:
        return ""
    said = next(v for v in m.groupdict().values() if v)
    return " ".join(said.split())


def excluded_by_name(company: str | None) -> str:
    """Why the employer's name alone excludes it, or "".

    The bar's rules that read nothing but the name: an excluded sector, an
    employer declined by name, a public agency named outright. The prefilter
    applies these before hydrate fetches a body nobody will read. A public body
    with a well-paid posting (BAR_PUBLIC) needs the posting, so it is not here.
    """
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    for rx, why in EXCLUDED_RULES:
        if rx.search(both):
            return why
    if k in DECLINED:
        return DECLINED[k]
    if PUBLIC_PRESTIGE.search(both) or PENSIONS.search(both):
        return ""
    return _NAMED_WHY if NAMED_PUBLIC.search(both) else ""


UNLISTED = ("not on your employer lists yet, so this says nothing about it: judge its pay, "
            "prestige and signal once (`python3 tools/bar.py judge \"<company>\" <verdict> "
            "\"<why>\"`); never a reason to drop it unjudged")
NO_BAR = "your profile sets no bar for employers, so this says nothing about it"
JUDGED_FILE = "employers_judged.json"
_judged_cache: dict = {}


def _judged_path() -> str:
    return person.path(JUDGED_FILE)


def own_name(name: str | None) -> str:
    """An employer's name as itself: case, accents, punctuation and its legal form set
    aside, its line of business kept. A judgement is found by this, never by the
    company key, which drops "Insurance", "Software" or "Global" from the end: a
    judgement of "Brackwater Software" was read for "Brackwater Insurance"."""
    s = _ck.PAREN.sub(" ", _ck.fold(str(name or "")).lower())
    s = _ck.SUFFIX.sub(" ", s)
    s = re.sub(r"\band\b", " ", _ck.PUNCT.sub(" ", s))
    s = _ck.SPACE.sub(" ", s).strip()
    return _ck.TRAILING_FORM.sub("", s).strip()


class Unreadable(ValueError):
    """profile/employers_judged.json is there and cannot be read."""


def _read_judged(p: str) -> dict:
    """The judged file as stored, {} when there is none; Unreadable when it is there and
    does not parse (a merge can leave conflict markers in it, and it has no merge driver)."""
    try:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise Unreadable(f"profile/{JUDGED_FILE} could not be opened ({e})") from None
    if not text.strip():
        return {}
    try:
        got = json.loads(text)
    except ValueError:
        got = None
    if not isinstance(got, dict):
        markers = re.search(r"^(?:<{7}|={7}|>{7})", text, re.M)
        raise Unreadable(
            f"profile/{JUDGED_FILE} cannot be read"
            + (" (a merge left conflict markers in it)" if markers else "")
            + ": keep the right version of each entry, delete the marker lines, then "
              "judge again. Nothing was written to it.")
    return got


def judged() -> dict:
    """The employers judged by `judge`: {stored key: {verdict, why, name, date}}. The
    profile's tier lists outrank it; it fills only what they leave unnamed. A file that
    cannot be read is said once, and read as no judgements until it is fixed."""
    try:
        p = _judged_path()
        m = os.path.getmtime(p)
    except (OSError, person.NoProfile):
        return {}
    if _judged_cache.get("at") != (p, m):
        try:
            got = _read_judged(p)
        except Unreadable as e:
            if _judged_cache.get("said") != (p, m):
                print(f"bar: {e} Until then no judgement in it is read.", file=sys.stderr)
            _judged_cache["said"] = (p, m)
            got = {}
        _judged_cache.update(at=(p, m), rows=got, by_name={
            own_name(r.get("name") or k): r for k, r in got.items() if isinstance(r, dict)})
    return _judged_cache["rows"]


def judgement(company: str | None) -> dict | None:
    """The judgement recorded for this employer by its own name, or None."""
    judged()
    return _judged_cache.get("by_name", {}).get(own_name(company)) if company else None


@contextlib.contextmanager
def _one_writer(p: str):
    """One `judge` at a time for the file, across processes: two chats judging at once
    each wrote their own row over the other's, or crashed on the shared temporary file."""
    lock = os.path.join(tempfile.gettempdir(), "ljs-judged-%s.lock"
                        % hashlib.sha1(os.path.abspath(p).encode()).hexdigest()[:16])
    with open(lock, "a+", encoding="utf-8", newline="\n") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:                      # Windows
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                pass
        yield


def judge(company: str, what: str, why: str, today: str | None = None) -> str:
    """Record a judgement of an employer no list names. Returns the line to say.

    Refuses, naming the file, to write over a judged file it cannot read: it used to
    read such a file as empty and write back only the new row."""
    if what not in (PAY, PRESTIGE, SIGNAL, NONE):
        raise ValueError(f"a judgement is pay, prestige, signal or none, not {what!r}")
    why = " ".join(str(why or "").split())
    if not why:
        raise ValueError("say why, in a few words: it is printed beside every verdict")
    name = own_name(company)
    if not name or not company_key(company):
        raise ValueError("no employer name to judge")
    p = _judged_path()
    with _one_writer(p):
        rows = _read_judged(p)
        rows = {k: r for k, r in rows.items()
                if not (isinstance(r, dict) and own_name(r.get("name") or k) == name)}
        rows[name] = {"name": company, "verdict": what, "why": why,
                      "date": today or datetime.date.today().isoformat()}
        tmp = tempfile.NamedTemporaryFile("w", newline="\n", dir=os.path.dirname(p) or ".", delete=False,
                                          encoding="utf-8", suffix=".tmp")
        with tmp:
            json.dump(dict(sorted(rows.items())), tmp, indent=2, ensure_ascii=False)
            tmp.write("\n")
        os.replace(tmp.name, p)
    _judged_cache.clear()
    return f"{company}: {what} ({why}), kept in profile/{JUDGED_FILE}"


def listed(company: str | None) -> bool:
    """Whether any of the profile's bar or tier lists names this employer, or it has been
    judged, so that its verdict says something about it."""
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    if excluded_by_name(company) or tier(name)[0] or COLLISIONS.search(both) or judgement(name):
        return True
    if any(rx.search(both) for rx in (PUBLIC_PRESTIGE, PENSIONS, NAMED_PUBLIC, PUBLIC)):
        return True
    c = f" {k} "
    return bool(_names_in(c, FRONTIER) or _names_in(c, YC_AND_BACKED)
                or tech_name(name) or tech_name(k))


def verdict(company: str | None, posting: str = "") -> tuple[str, str]:
    """(verdict, reason). See the module docstring for the order and meaning."""
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    lo, hi, _ = salary_range(posting or "")
    mid = (lo + hi) // 2 if lo and hi else None
    paid = mid is not None and mid >= TARGET_MIDPOINT

    why = excluded_by_name(company)
    if why:
        return EXCLUDED, why
    if PUBLIC_PRESTIGE.search(both):
        return PRESTIGE, _PRESTIGE_WHY
    if PENSIONS.search(both):
        pass  # a target-list public-adjacent employer is never public sector
    elif PUBLIC.search(both):
        if public_paid(lo, hi):
            return PAY, public_paid_why(lo)
        return EXCLUDED, _PUBLIC_WHY

    # An employer on none of the lists and judged by nobody: only now is its posting read
    # for what the employer says it is, and a public body it describes is held to the
    # public rule, its stricter paid exception included, before the midpoint rule below.
    said = "" if listed(name) else public_said(posting, name)
    if said:
        if public_paid(lo, hi):
            return PAY, public_paid_why(lo)
        return EXCLUDED, _PUBLIC_WHY + f' (the posting says it: "{said}")'

    collided = bool(COLLISIONS.search(both))
    score, why = (0, "") if collided else tier(name)
    if score >= 30:
        return PAY, f"{why}; top-of-market pay"
    if paid:
        return PAY, f"stated range midpoint {CUR}{mid:,} reaches the {CUR}{TARGET_MIDPOINT:,} target band"
    if score >= 20:
        return PRESTIGE, why
    if PENSIONS.search(both):
        return PRESTIGE, _TARGETS_WHY
    if not collided:
        c = f" {k} "
        hit = _names_in(c, FRONTIER)
        if hit:
            return SIGNAL, f"frontier AI ({hit})"
        hit = _names_in(c, YC_AND_BACKED)
        if hit:
            return SIGNAL, f"YC or top-tier backed ({hit})"
        hit = tech_name(name) or tech_name(k)
        if hit:
            return SIGNAL, f"established technology company ({hit})"
    if score < 0 or collided:
        return NONE, why or "a different company wearing a listed employer's name"
    stated = applies()
    j = judgement(name)
    if j and j.get("verdict") in ((PAY, PRESTIGE, SIGNAL, NONE) if stated else (PAY, PRESTIGE, SIGNAL)):
        return j["verdict"], f"judged {j.get('date', '')}: {j.get('why', '')}".replace(" :", ":")
    if not stated:
        # No bar of pay, prestige or signal in this profile: "none" says nothing about the
        # employer, and a "none" a chat judged on someone else's words never counts (X-18).
        return NONE, NO_BAR
    if mid is not None:
        return NONE, (f"stated range midpoint {CUR}{mid:,} is under the {CUR}{TARGET_MIDPOINT:,} "
                      f"target band, and {UNLISTED}")
    return NONE, f"no stated range, and {UNLISTED}"


def public_paid(lo, hi) -> bool:
    """The one exception a public body has: pay, held to a stricter bar than any other
    employer's (the public rule is "more stringent than others"). The bottom of the stated
    range reaches the target, not its midpoint: a provincial agency's six-month contract
    whose midpoint was 2% over the target passed as well paid, and was ranked up (2026-11-03)."""
    return lo is not None and hi is not None and lo >= TARGET_MIDPOINT


def public_paid_why(lo) -> str:
    return (f"public body, but even the bottom of its stated range, {CUR}{lo:,}, reaches the "
            f"{CUR}{TARGET_MIDPOINT:,} target: the one exception for a public body")


def is_public(company: str | None, posting: str = "") -> bool:
    """Whether the profile's public rule reads this employer as a public body: by name
    (BAR_NAMED_PUBLIC, BAR_PUBLIC) or by what its posting says it is, never a prestige
    exception or a target-list public-adjacent employer. The opportunity score gives a
    public body no employer-tier lift, whatever tier list names it."""
    name = str(company or "")
    both = f"{name} {company_key(name)}"
    if PUBLIC_PRESTIGE.search(both) or PENSIONS.search(both):
        return False
    if NAMED_PUBLIC.search(both) or PUBLIC.search(both):
        return True
    return bool(posting) and not listed(name) and bool(public_said(posting, name))


def clears(company: str | None, posting: str = "") -> bool:
    return verdict(company, posting)[0] in (PAY, PRESTIGE, SIGNAL)


def applies() -> bool:
    """Does the person's own profile state a bar of pay, prestige or signal: an employer tier
    (employers.py TIER_1, TIER_2) or a frontier list (search.py BAR_FRONTIER)? With none,
    every employer would come back "none", which says nothing. A judgement is not a bar: the
    brief had every chat judge employers on one person's words ("pay, prestige or signal"),
    and once one was judged, every stranger's follow-ups there vanished (X-18)."""
    import opportunity
    return bool(getattr(opportunity, "TIER_1", None) or getattr(opportunity, "TIER_2", None)
                or FRONTIER)


def hold_question(company: str, posting: str = "") -> dict | None:
    """The question a pick waits on before it is drafted, when its employer clears none of the
    bar: {id, question}, or None. One employer was drafted with its bar "none" and unjudged, against
    the person's rule that an employer clearing none of pay, prestige or signal does not go on
    the list (2026-11-03). Judged since (`judge`), it clears or it asks; the person may still
    say draft it."""
    if not applies():
        return None
    what, _why = verdict(company, posting)
    if what != NONE:
        return None
    j = judgement(company)
    if j:
        plain = "judged %s: %s" % (j.get("date", ""), j.get("why", "")) if j.get("why") else \
            "judged as clearing none"
    else:
        lo, hi, _ = salary_range(posting or "")
        plain = ("its stated pay is under your target, and nobody has judged it yet" if lo and hi
                 else "it states no pay and is on none of your employer lists, and nobody has "
                      "judged it yet")
    return {"id": "bar", "question": "%s clears none of your bar of pay, prestige or signal "
                                     "(%s). Do you still want it drafted?" % (company, plain)}


def unjudged(path: str | None = None) -> list[str]:
    """The employers in a saved shortlist (the newest in documents/rounds/ by default)
    that no list names and nobody has judged, each once, in shortlist order. None where the
    profile states no bar: there is nothing to judge them against (X-18)."""
    if not applies():
        return []
    if not path:
        from run_round import round_order
        found = sorted(glob.glob(os.path.join(glob.escape(person.state("documents", "rounds")), "*.json")),
                       key=round_order)
        if not found:
            return []
        path = found[-1]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("rows", data.get("shortlist", [])) if isinstance(data, dict) else data
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        name = (r or {}).get("company") if isinstance(r, dict) else None
        k = company_key(name or "")
        if name and k not in seen and not listed(name):
            seen.add(k)
            out.append(name)
    return out


def unjudged_contacts(today=None) -> list[str]:
    """The employers of people with a follow-up owed (tools/open_actions.py) that no list
    names and nobody has judged, each once: judged, an employer that clears nothing stops
    filling the person's To do (the maintainer, 2026-10-26). None where the profile states no
    bar (X-18)."""
    if not applies():
        return []
    import csv_store
    import open_actions
    def rows(name):
        p = person.state(name)
        return csv_store.dict_rows(p) if os.path.isfile(p) else []
    contacts = rows("network_contacts.csv")
    threads = rows("network_threads.csv")
    tracker = csv_store.tracker()
    today = today or datetime.date.today()
    book = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    out, seen = [], set()
    for i in open_actions.due_items(contacts, threads, tracker, today):
        if i.get("half") != "contact" or i.get("kind") == "reply":
            continue
        name = str(book.get(i.get("contact_id") or "", {}).get("company") or "").strip()
        k = company_key(name)
        if name and k not in seen and not listed(name):
            seen.add(k)
            out.append(name)
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print('usage: python3 tools/bar.py "<company>" ["<company>" ...]\n'
              '       python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"\n'
              '       python3 tools/bar.py unjudged [documents/rounds/<round>.json]\n'
              '       python3 tools/bar.py unjudged --contacts\n\n'
              + __doc__.strip().split("\n\n")[0])
        return 0 if argv else 2
    if argv[0] == "judge":
        if len(argv) != 4:
            print('usage: python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"')
            return 2
        try:
            print(judge(argv[1], argv[2], argv[3]))
        except ValueError as e:                  # Unreadable among them
            print(f"bar: {e}")
            return 2
        return 0
    if argv[0] == "unjudged" and not applies():
        print("no bar: your profile states none, so no employer is judged or ruled out for it")
        return 0
    if argv[0] == "unjudged" and argv[1:] == ["--contacts"]:
        names = unjudged_contacts()
        print("\n".join(names) if names else "every employer with a follow-up owed is on a list or judged")
        return 0
    if argv[0] == "unjudged":
        names = unjudged(argv[1] if len(argv) > 1 else None)
        print("\n".join(names) if names else "every employer in the shortlist is on a list or judged")
        return 0
    for n in argv:
        v, why = verdict(n)
        print(f"{n:<34} {v:<9} {why}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
