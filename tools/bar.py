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
            named outright (BAR_NAMED_PUBLIC), or any other public body unless
            the posting states a range that reaches the target band
            (BAR_PUBLIC). Public-adjacent employers on the profile's target
            list (BAR_PUBLIC_TARGETS) never land here.
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
    with open(lock, "a+", encoding="utf-8") as fh:
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
        tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(p) or ".", delete=False,
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
        if paid:
            return PAY, _PUBLIC_PAID.format(cur=CUR, mid=mid, target=TARGET_MIDPOINT)
        return EXCLUDED, _PUBLIC_WHY

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
    j = judgement(name)
    if j and j.get("verdict") in (PAY, PRESTIGE, SIGNAL, NONE):
        return j["verdict"], f"judged {j.get('date', '')}: {j.get('why', '')}".replace(" :", ":")
    if mid is not None:
        return NONE, (f"stated range midpoint {CUR}{mid:,} is under the {CUR}{TARGET_MIDPOINT:,} "
                      f"target band, and {UNLISTED}")
    return NONE, f"no stated range, and {UNLISTED}"


def clears(company: str | None, posting: str = "") -> bool:
    return verdict(company, posting)[0] in (PAY, PRESTIGE, SIGNAL)


def unjudged(path: str | None = None) -> list[str]:
    """The employers in a saved shortlist (the newest in documents/rounds/ by default)
    that no list names and nobody has judged, each once, in shortlist order."""
    if not path:
        from run_round import round_order
        found = sorted(glob.glob(person.state("documents", "rounds", "*.json")),
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


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print('usage: python3 tools/bar.py "<company>" ["<company>" ...]\n'
              '       python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"\n'
              '       python3 tools/bar.py unjudged [documents/rounds/<round>.json]\n\n'
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
