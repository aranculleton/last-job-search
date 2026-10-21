#!/usr/bin/env python3
"""Where the person told each employer they are, when it is not one place for every one.

Someone who tells one employer they are in London and another that they are in Toronto
cannot be served from one location: the interview pack printed the profile's city to an
employer that had heard another, and the small talk asked how they were settling into a
city that employer did not know about. Each employer that heard a place of its own is kept
in person.json `identity.places_told` ({employer: place}), joined by company_key, and read
by the interview pack, the call prep and the message checks before the profile's own place.

    python3 tools/told.py                          # every employer and what it heard
    python3 tools/told.py "<Employer>" "<place>"   # record what one heard
    python3 tools/told.py "<Employer>" --clear     # back to the profile's own place
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

KEY = "places_told"
# identity.moved and identity.area when the person gives each employer their own answer:
# nothing single is said for everyone, and the place each heard is kept here instead.
PER_EMPLOYER = "per employer"


def places() -> dict:
    """{employer: place} as recorded, or {} when nothing is."""
    try:
        got = person.get("identity.places_told", {})
    except person.NoProfile:
        return {}
    return {str(k): str(v) for k, v in got.items() if str(v).strip()} \
        if isinstance(got, dict) else {}


def place(company: str) -> str:
    """The place this employer was told, or "" when it heard nothing of its own."""
    k = company_key(company or "")
    return next((v for c, v in places().items() if k and company_key(c) == k), "")


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", str(text or "").lower()) if len(w) > 2}


def _parts(where: str) -> list:
    """A place as its comma-separated names, lower-cased: "Chorlton, Manchester" is
    ["chorlton", "manchester"]."""
    return [" ".join(p.split()).lower() for p in str(where or "").split(",") if p.strip()]


def same_place(a: str, b: str) -> bool:
    """Do two written places name one place? "Leeds" and "Leeds, UK" do, and so do
    "Manchester" and "Chorlton, Manchester"; "London, UK" and "London, Ontario" do not, and
    neither do "York" and "New York": a place is matched by its whole names, never a word."""
    pa, pb = _parts(a), _parts(b)
    if not pa or not pb:
        return False
    if pa == pb:
        return True
    if len(pa) == 1 or len(pb) == 1:
        one, other = (pa, pb) if len(pa) == 1 else (pb, pa)
        return one[0] in other
    # Both qualified: the same first name, and the rest agreeing somewhere.
    return pa[0] == pb[0] and bool(set(pa[1:]) & set(pb[1:]))


def home() -> str:
    """The person's own place for everyone else: identity.area, else identity.location,
    never a value still marked to confirm or kept per employer."""
    for k in ("identity.area", "identity.location"):
        try:
            v = str(person.get(k, "") or "").strip()
        except person.NoProfile:
            return ""
        if v and "[CONFIRM" not in v and v.lower() != PER_EMPLOYER:
            return v
    return ""


def _homes() -> list:
    """Every way the profile writes the person's own place: identity.area and
    identity.location, whichever hold one."""
    out = []
    for k in ("identity.area", "identity.location"):
        try:
            v = str(person.get(k, "") or "").strip()
        except person.NoProfile:
            return []
        if v and "[CONFIRM" not in v and v.lower() != PER_EMPLOYER:
            out.append(v)
    return out


def differs(company: str) -> bool:
    """Did this employer hear a place other than the person's own? Then nothing written for
    the person's own place (a move, settling in, its neighbourhoods) is for this employer.
    Places are compared by their whole names (same_place): a city and its namesake in another
    country are two places."""
    told = place(company)
    return bool(told) and not any(same_place(told, h) for h in _homes())


# A sentence that says where the person lives or came from: "my partner and I came over from
# London to build our life in Toronto" was printed for an employer that believed they were in
# London (2026-10-21). Only a sentence with the person as the one living or moving counts: "I
# moved our reporting to dbt", "the dashboards live in Power BI" and "moving fast" said
# nothing about where anyone lives, and were flagged (2026-10-21).
_ME = (r"(?:\bI\b|\bwe\b|\bmy (?:partner|wife|husband|family|fianc[eé]e?|girlfriend|boyfriend) "
       r"and I\b|\bmy family\b|\bour family\b)")
_FILLER = (r"(?:\s*['’](?:ve|m|re|d|ll|s)\b|\s+(?:have|has|had|am|are|was|were|be|been|will|"
           r"would|could|should|just|recently|finally|now|currently|already|also|both|then|only|"
           r"first|eventually|actually|really|happily|still|since|all|like to|want to|hope to|"
           r"plan to|planning to|to|be|getting|got|came))*")
# A verb about living somewhere, strong enough to read a capitalised name after it as a place.
_LIVE = (r"(?:live|lives|living|lived|based|settled|settling|arrived|arriving|emigrated|"
         r"emigrating|came over|come over|coming over|made the move|make the move|"
         r"building (?:a|our|my) (?:life|home)|build (?:a|our|my) (?:life|home)|"
         r"built (?:a|our|my) (?:life|home)|call\w* \w+ home|home is)")
# A verb about moving: also how a change of job or tool is said ("I moved to Brindle & Hart", "we
# moved to Snowflake"), so after it only a place the profile knows counts.
_MOVE_VERB = r"(?:moved|moving|move|relocated|relocating|relocate)"
_STATEMENT = re.compile(r"%s%s\s+(%s|%s)\b" % (_ME, _FILLER, _LIVE, _MOVE_VERB), re.I)
# "Since moving to Leeds, I ...": the person is the one moving, said first.
_SINCE = re.compile(r"\b(?:since|after|before) (?:moving|relocating|arriving|coming over|"
                    r"emigrating)\b", re.I)
_OBJECT = re.compile(r"^\s*(?:it|them|this|that|these|those|our (?!family\b|life\b|home\b)|the|"
                     r"a|an|his|her|their|its|everything|all|some|most|every|each|"
                     r"[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*\s+(?:to|from|into|onto)\b)")
_AT = r"(?:in|to|from|into|near|around|over from|out of|back to|across to|here from|over to|at)"
_CAPITAL = re.compile(r"\b%s\s+(?:the\s+)?([A-Z][\w'’-]+(?:[ -](?:[A-Z][\w'’-]+|upon|on|de|"
                      r"la|le))*)" % _AT)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


def _known() -> list:
    """[(name, qualifier)] for the places the profile knows by name, longest first: the
    person's own (whole, and each of its names) and every place told to an employer. A
    qualifier ("UK" in "Manchester, UK") names no town of its own."""
    names, quals = set(), set()
    for where in _homes() + list(places().values()):
        parts = [" ".join(p.split()) for p in where.split(",") if p.strip()]
        if not parts:
            continue
        names.add(", ".join(parts))
        for i, p in enumerate(parts):
            core = re.sub(r"^(?:greater|metro|central|city of)\s+|\s+(?:area|region|metro|"
                          r"city|district)$", "", p, flags=re.I).strip()
            (names if i == 0 else quals).update(x for x in (p, core) if x)
    quals -= names
    out = [(n, False) for n in names] + [(q, True) for q in quals]
    return sorted((x for x in out if len(x[0]) > 1), key=lambda x: len(x[0]), reverse=True)


def _named(rest: str, strong: bool) -> list:
    """The places named in `rest`, each written as the sentence writes it: a place the profile
    knows, or after a living verb (`strong`) any capitalised name after "in", "from" or "to".
    Names joined by a comma are one place ("Leeds, UK"); a qualifier alone is none."""
    spans = []
    for name, qual in _known():
        for hit in re.finditer(r"(?<![\w-])%s(?![\w-])" % re.escape(name), rest, re.I):
            if not any(a <= hit.start() < b for a, b, _q in spans):
                spans.append((hit.start(), hit.end(), qual))
    if strong:
        for c in _CAPITAL.finditer(rest):
            a, b = c.span(1)
            if not any(x < b and a < y for x, y, _q in spans):
                spans.append((a, b, False))
    spans.sort()
    groups = []
    for a, b, qual in spans:
        if groups and re.fullmatch(r",\s*", rest[groups[-1][1]:a]):
            groups[-1] = (groups[-1][0], b, groups[-1][2] and qual)
        else:
            groups.append((a, b, qual))
    return [rest[a:b] for a, b, qual in groups if not qual]


def statements(answer: str) -> list:
    """[(what the sentence says, [the places it names])] for each sentence of `answer` that
    says where the person lives, lived or moved: the person as the one living or moving, and
    a place named as a place. A sentence about work that happens to use those verbs is not
    one."""
    out = []
    for sentence in _SENTENCES.split(str(answer or "")):
        m = _STATEMENT.search(sentence)
        start = m.end() if m else None
        strong = bool(m) and not re.match(_MOVE_VERB + r"$", m.group(1), re.I)
        if m is None:
            s2 = _SINCE.search(sentence)
            if not s2:
                continue
            start, strong = s2.end(), False
        rest = sentence[start:]
        if not strong and _OBJECT.match(rest):
            continue                     # "I moved it to Power BI": a thing moved, not them
        found = _named(rest, strong)
        if found:
            out.append(((m.group(0) if m else sentence[:start]) + rest[:60].rstrip(), found))
    return out


def clash(answer: str, company: str) -> str:
    """Why `answer` may say the wrong place to `company`, or "". Only a sentence saying where
    the person lives or moved, naming a place, is read (`statements`). Where this employer
    heard another place, one naming any place but the one it heard is named. Where the person
    tells different employers different places and nothing is recorded for this one, any
    such sentence is named, to check before it is said."""
    heard = place(company)
    said = statements(answer)
    if not said:
        return ""
    if heard and differs(company):
        other = [p for _s, ps in said for p in ps if not same_place(p, heard)]
        if other:
            return ("you told %s you are in %s, and this answer says \"%s\": say the same "
                    "place, or record what they hear now with python3 tools/told.py"
                    % (company, heard, other[0]))
        return ""
    if not heard and places():
        return ("you tell employers different places and nothing is recorded for %s: check "
                "\"%s\" matches what they heard, then record it with python3 tools/told.py "
                "\"%s\" \"<place>\"" % (company, said[0][1][0], company))
    return ""


def record(company: str, where: str = "", clear: bool = False) -> str:
    """Write what `company` heard into person.json; returns the line to say."""
    path = person.path("person.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    ident = data.setdefault("identity", {})
    told = {str(k): str(v) for k, v in (ident.get(KEY) or {}).items()}
    k = company_key(company)
    same = [c for c in told if company_key(c) == k]
    for c in same:
        told.pop(c)
    if not clear:
        if not str(where).strip():
            raise ValueError("say the place they were told, or --clear")
        told[company] = " ".join(str(where).split())
    if told:
        ident[KEY] = told
    else:
        ident.pop(KEY, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    person.reset()
    if clear:
        return ("%s: back to your own place (%s)." % (company, home() or "none recorded")
                if same else "%s: nothing was recorded for it." % company)
    return "%s heard: %s. Packs and message checks for %s use it." % (company, told[company],
                                                                    company)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("company", nargs="?")
    ap.add_argument("place", nargs="?", default="")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args(argv)
    try:
        if not a.company:
            got = places()
            print("\n".join("%s: %s" % kv for kv in sorted(got.items())) if got else
                  "Every employer hears your own place: %s." % (home() or "none recorded"))
            return 0
        print(record(a.company, a.place, a.clear))
    except person.NoProfile:
        print("told: no profile/ yet: /setup builds one.")
        return 1
    except ValueError as exc:
        print("told: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
