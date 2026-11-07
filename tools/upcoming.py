#!/usr/bin/env python3
"""Everything booked or due ahead, in one list, and how to put each in a calendar.

The maintainer, 2026-11-02: "I keep losing track of things... there's no consistent way to
view upcoming things I've booked like interviews, calls etc." What was booked lived in three
places that never met: an application's interview stages (outcome.md), a contact marked
"call booked" (its day on the row, its time only in the words of its next action), and the
deadline on an application drafted and not yet sent. This puts them in one list, by day,
with what the person adds themselves, and nothing else: follow-ups and replies owed are To
do's, never the calendar's.

    python3 tools/upcoming.py list [--today D]       # the list, as the page gets it
    python3 tools/upcoming.py add "<what>" <day> [<HH:MM>] [--note "..."]
    python3 tools/upcoming.py remove <id>

A calendar is never connected and nothing is ever sent (CLAUDE.md: it never sends anything).
Each item carries the three ways to add it that need no account: a Google Calendar link, an
Outlook link, and an iCalendar event the page saves for Apple Calendar or any other app. One
Outlook, the personal one: a job search does not belong in the calendar of the job being left,
and Outlook on a computer takes the file (the maintainer, 2026-11-02: "do we need 2 for
outlook?"). The link formats are the ones spatie/calendar-links generates
(github.com/spatie/calendar-links, src/Generators, read 2026-11-02): Google's render?action=
TEMPLATE with dates in UTC, Outlook's compose deeplink with startdt and enddt, and an .ics of
RFC 5545 with CRLF lines, folded at 75 octets, text escaped.

Pure code, standard library; the only file it writes is the person's own
documents/upcoming.json, with what they added.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

KINDS = ("interview", "test", "call", "deadline", "event")
WINDOW_DAYS = 60          # how far ahead the list looks
DEADLINE_DAYS = 21        # an application's closing day shows this close, never sooner
EVENTS = ("documents", "upcoming.json")
EVENTS_MAX = 200

# A stage that is something to finish by a day, not a meeting: an online test, a case study.
_TEST = re.compile(r"\b(?:test|assessment(?! cent(?:re|er))|case study|take[- ]home|exercise|challenge|hirevue|"
                   r"coding task|assignment|questionnaire)\b", re.I)
# A short meeting: a screen or a call is half an hour; any other interview an hour.
_SHORT = re.compile(r"\b(?:screen|screening|call|chat|intro)\b", re.I)
_PLACES = (("teams", "Microsoft Teams"), ("zoom", "Zoom"), ("google meet", "Google Meet"),
           ("meet.google", "Google Meet"), ("webex", "Webex"), ("phone", "Phone"),
           ("in person", "In person"), ("on site", "In person"), ("onsite", "In person"),
           ("office", "In person"))
# A time written in a next action, as chats and the page write them: "2pm ET", "2:30 pm",
# "18:00-18:30 UK", "2-3pm", "14.30", "14h30". A zone is an upper-case word app_model knows
# beside it: "at" is a word, never Atlantic time (the release review, 2026-11-02).
_MER = r"(?:([ap])\.?\s*m\.?\b)?"
# The zone after a time: an upper-case word (ET, BST), or words a person writes ("Toronto
# time", "Eastern", "Pacific Time", "UK time"), read by the one reader (person.zone_in).
_ZONE = (r"(?:\s*\(?\s*(?-i:([A-Z]{2,5}\b|[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)?(?:[ \t]+(?i:time))?"
         r"|(?i:(?:uk|eastern|pacific|central|mountain|atlantic)[ \t]+time|eastern|pacific)\b)))?")
_NOON = re.compile(r"\b(?:at\s+)?(?:12\s+)?(noon|midday)\b" + _ZONE, re.I)
_RANGE = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + r"\s*(?:-|–|to)\s*"
                    r"(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + _ZONE, re.I)
_ONE = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + _ZONE, re.I)


def _zone_word(word: str, home: str) -> str | None:
    """The zone a written word names, `home` where none is written, None where it names no
    zone this can place: a time read in the wrong zone is worse than no time. A zone's own
    name ("America/Toronto", which a stage booked since 4.7 carries) is taken as it is; a
    word (EST, IST) is looked up in the standard library's own zones, the person's zone first
    where it uses the word, and a word two zones share at different hours places nothing."""
    import app_model
    raw = str(word or "").strip()
    if not raw:
        return home
    if "/" in raw:
        return raw if _known_zone(raw) else None
    if not re.fullmatch(r"[A-Z]{2,5}", raw):
        # Words, not an abbreviation: "Toronto time", "Eastern", "Pacific Time".
        return person.zone_in(raw, home) or None
    w = raw.upper()
    names = _zone_abbreviations().get(w) or set()
    # The person's own zone first, before the app's short list: in Shanghai CST is China's,
    # never Chicago's, and in Brisbane AEST is Brisbane's (the release review).
    if home in names:
        return home
    if w in app_model._ZONE_WORDS:
        got = app_model._ZONE_WORDS[w]
        # ET for a person in Toronto is Toronto's clock: their own city is named.
        return home if home and person._same_clock(got, home) else got
    if not names:
        return None
    offsets = {o for n in names for o in [_offsets(n)]}
    return min(names) if len(offsets) == 1 else None


def _known_zone(name: str) -> bool:
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _offsets(name: str) -> tuple:
    import zoneinfo
    z = zoneinfo.ZoneInfo(name)
    year = dt.date.today().year
    return tuple(dt.datetime(year, m, 15, 12, tzinfo=z).utcoffset() for m in (1, 7))


_ABBR: dict | None = None


def _zone_abbreviations() -> dict:
    """{"EST": {zone names}, ...}: every abbreviation the standard library's zones use, in
    January or July, built once. Numeric ones ("-03") are left out: nobody writes those."""
    global _ABBR
    if _ABBR is None:
        out: dict = {}
        try:
            import zoneinfo
            year = dt.date.today().year
            for name in zoneinfo.available_timezones():
                if not ("/" in name and name.split("/")[0] in (
                        "Africa", "America", "Antarctica", "Asia", "Atlantic", "Australia",
                        "Europe", "Indian", "Pacific")):
                    continue
                z = zoneinfo.ZoneInfo(name)
                for m in (1, 7):
                    abbr = dt.datetime(year, m, 15, 12, tzinfo=z).tzname() or ""
                    if re.fullmatch(r"[A-Z]{2,5}", abbr):
                        out.setdefault(abbr, set()).add(name)
        except Exception:  # noqa: BLE001  no zone data on this machine (Windows without tzdata)
            out = {}
        _ABBR = out
    return _ABBR


def _clock(h, m, mer) -> str | None:
    h, m = int(h), int(m or 0)
    if m > 59:
        return None
    if mer:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if mer.lower() == "p" else 0)
    elif h > 23:
        return None
    return f"{h:02d}:{m:02d}"


def call_time(text: str, home: str) -> dict | None:
    """The first time written in `text`, as {"time": "HH:MM", "end": "HH:MM" or None,
    "zone": an IANA zone}: the zone written beside it, else `home`. None where none is, or
    where the zone written is one the app does not know. A bare number is never a time: a
    time has minutes or an am or pm ("6 new roles", "10-12 people")."""
    text = str(text or "")
    found = []
    for m in _RANGE.finditer(text):
        sh, sm, smer, eh, em, emer, word = m.groups()
        if not (sm or em or smer or emer):
            continue
        if emer and not smer:
            # "2-3pm" is two to three in the afternoon; "11-1pm" starts in the morning.
            smer = emer if int(sh) % 12 + (12 if emer.lower() == "p" else 0) <= \
                int(eh) % 12 + (12 if emer.lower() == "p" else 0) else ("a" if emer.lower() == "p" else "p")
        start, end = _clock(sh, sm, smer), _clock(eh, em, emer)
        if start and end:
            found.append((m.start(), -len(m.group(0)), start, end, word))
    for m in _ONE.finditer(text):
        h, mi, mer, word = m.groups()
        if not (mi or mer):
            continue
        t = _clock(h, mi, mer)
        if t:
            found.append((m.start(), -len(m.group(0)), t, None, word))
    for m in _NOON.finditer(text):
        found.append((m.start(), -len(m.group(0)), "12:00", None, m.group(2)))
    if not found:
        return None
    # Two times offered ("12pm or Friday at 9am Eastern"): a choice, not a booking. The first
    # was taken as the booked one (the audit, 2026-11-03).
    starts = sorted({(at, t) for at, _l, t, _e, _w in found})
    if len({t for _a, t in starts}) > 1 and re.search(r"\bor\b", text, re.I):
        return None
    # The first written; at one place, the longest reading (a range, an am or pm).
    _at, _len, time_, end, word = min(found)
    zone = _zone_word(word, home)
    if zone is None and word and not re.fullmatch(r"[A-Z]{2,5}", word) \
            and not re.search(r"(?i)\btime$", word):
        zone = home          # a word after the time that is no zone ("2pm Thursday")
    return {"time": time_, "end": end, "zone": zone} if zone else None


def place(text: str) -> str | None:
    low = str(text or "").lower()
    for word, name in _PLACES:
        if re.search(r"\b" + re.escape(word) + r"\b", low):
            return name
    return None


def _moment(day: str, time_: str, zone: str) -> dt.datetime | None:
    """`day` at `time_` in `zone`, in UTC; None where the zone is unknown here."""
    try:
        import zoneinfo
        h, m = (int(x) for x in time_.split(":"))
        local = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(h, m),
                                    tzinfo=zoneinfo.ZoneInfo(zone or "UTC"))
    except Exception:  # noqa: BLE001  no zone data, or not a day
        return None
    return local.astimezone(dt.timezone.utc)


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_day(value) -> bool:
    """A day written as YYYY-MM-DD and real: Python 3.11 reads "20261104" and "2026-W45-3" as
    days too, and a list built on one broke on the next step (the release review, 2026-11-02)."""
    if not _DAY.match(str(value or "")):
        return False
    try:
        dt.date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ what the person added


def _events_path() -> str:
    return person.state(*EVENTS)


def added() -> list[dict]:
    try:
        with open(_events_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("events") if isinstance(data, dict) else data
    return [r for r in rows or [] if isinstance(r, dict) and r.get("id") and _is_day(r.get("day"))]


def _save(rows: list[dict]) -> None:
    path = _events_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"events": rows[-EVENTS_MAX:]}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def add(title: str, day: str, time_: str = "", note: str = "", eid: str = "",
        zone: str = "") -> dict:
    """Keep something the person booked that the app does not know of: what, the day, and
    a time where they gave one. Returns the row kept."""
    title = " ".join(str(title or "").split())[:120]
    if not title:
        raise ValueError("say what it is")
    if not _is_day(day):
        raise ValueError("a day like 2026-11-04")
    time_ = str(time_ or "").strip()
    if time_ and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_):
        raise ValueError("a time like 14:30")
    rows = added()
    eid = eid or "ev" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")[:18]
    row = {"id": eid, "title": title, "day": str(day),
           **({"time": f"{int(time_.split(':')[0]):02d}:{time_.split(':')[1]}"} if time_ else {}),
           **({"note": " ".join(str(note).split())[:200]} if str(note or "").strip() else {}),
           **({"zone": zone} if time_ and person.known_zone(zone) else {})}
    rows = [r for r in rows if r.get("id") != eid] + [row]
    _save(rows)
    return row


def remove(eid: str) -> dict | None:
    """Take one away; returns it, so it can be put back."""
    rows = added()
    gone = next((r for r in rows if r.get("id") == eid), None)
    if gone:
        _save([r for r in rows if r.get("id") != eid])
    return gone


# ------------------------------------------------------------------ the list


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40] or "x"


def _local_day(t: dt.datetime, home: str) -> str:
    """The day a moment falls on where the person is."""
    try:
        import zoneinfo
        return t.astimezone(zoneinfo.ZoneInfo(home)).date().isoformat()
    except Exception:  # noqa: BLE001  no zone data: the day in UTC
        return t.date().isoformat()


def _item(kind, iid, title, day, time_="", zone="", end_time="", with_="", where=None,
          go=None, note=None, minutes=None, home="", uid="") -> dict:
    """One thing on the list. A timed one sits on the day it falls on where the person is:
    18:00 in California is the next morning in London, and the interview's own card says so
    (the release review, 2026-11-02)."""
    start = _moment(day, time_, zone) if time_ else None
    if start:
        # The end on the day it was written for, in its own zone: worked out after the day
        # moved to the person's own, a 6pm Pacific call ran 24 and a half hours (the audit,
        # 2026-11-03). An end at or before the start runs past midnight.
        end = _moment(day, end_time, zone) if end_time else None
        if end and end <= start:
            end = end + dt.timedelta(days=1)
        if end and end - start > dt.timedelta(hours=12):
            end = None
        end = end or start + dt.timedelta(minutes=minutes or 60)
    if start and home:
        day = _local_day(start, home)
    return {"id": iid, "kind": kind, "title": title, "with": with_ or None, "day": day,
            "time": time_ or None, "zone": zone if start else None,
            "start": _iso(start) if start else None, "end": _iso(end) if start else None,
            "all_day": not start, "place": where, "go": go, "note": note,
            # The calendar's own id for it: the round, never its day, time or name, so a move
            # updates the event a calendar already holds rather than adding a second.
            "uid": uid or iid}


def call_tentative(text) -> bool:
    """A booked call asked for and not confirmed by them yet, as its line says it."""
    return bool(re.search(r"\bnot confirmed\b", str(text or ""), re.I))


def label(text) -> str:
    """A stage's name as a title starts: "initial round" is "Initial round"."""
    t = " ".join(str(text or "").split())
    return t[:1].upper() + t[1:]


SHORT_LABEL = 50


def short_label(text) -> str:
    """A stage's name for a title: its first clause, and before a colon where an employer's
    whole paragraph was stored as the name ("Initial round : two 60-minute virtual interviews
    with ... Interview 1: ..." is "Initial round", the maintainer, 2026-11-07). A short name
    is kept as it is ("Online test: case study")."""
    t = label(text)
    if len(t) <= SHORT_LABEL:
        return t
    cut = re.split(r",\s|\s\(|;\s|\.\s|\s[-\u2013\u2014]\s", t)[0].strip(" :.")
    if len(cut) > SHORT_LABEL and ":" in cut:
        cut = cut.split(":", 1)[0].strip()
    if len(cut) > SHORT_LABEL:
        cut = cut[:SHORT_LABEL].rsplit(" ", 1)[0].rstrip(" ,:;") + "\u2026"
    return label(cut)


def label_details(text) -> str:
    """The rest of a long stage name, for the round's details: "" where the name is short."""
    t = label(text)
    short = short_label(t)
    if short == t:
        return ""
    rest = t[len(short.rstrip("\u2026")):].lstrip(" :;,.-\u2013\u2014")
    return label(rest) if not short.endswith("\u2026") else t


def _days_words(days) -> str:
    """"Thu 12, Fri 13 or Thu 19 Nov": offered days said together."""
    got = [dt.date.fromisoformat(d) for d in days if _is_day(d)]
    if not got:
        return ""
    words = []
    for n, d in enumerate(got):
        last = n == len(got) - 1 or got[n + 1].month != d.month
        words.append(f"{d:%a} {d.day}" + (f" {d:%b}" if last else ""))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def build(ctx, page_url: str = "") -> list[dict]:
    """Everything booked or due from today to WINDOW_DAYS ahead, by day and time: each
    interview stage still to come (a test or a case study as something due that day), each
    networking call booked (none where an interview at that employer is the same day), the
    closing day of each application drafted and not yet sent (within DEADLINE_DAYS), and what
    the person added. Each with the ways to add it to a calendar (`cal`)."""
    import app_model
    import open_actions
    import throttle
    from company_key import key as ckey
    today = ctx.today
    last = today + dt.timedelta(days=WINDOW_DAYS)
    home = getattr(ctx, "zone", "") or "UTC"
    names = getattr(ctx, "names", ())
    out: list[dict] = []
    seen_days: dict = {}           # (employer, day): the clock times of its stages, "" untimed

    now = getattr(ctx, "now", None)

    def ahead(day, item=None) -> bool:
        d = app_model._date(day)
        if item and item.get("end") and now is not None:
            # Over: a timed one leaves at its end, never at midnight. It sat in Coming up and
            # on the Brief as today's for the rest of the evening (the audit, 2026-11-03).
            ends = app_model.parse_time(item["end"])
            if ends and ends <= now:
                return False
        return bool(d and today <= d <= last)

    # A booked call's written time, by employer and day: where an interview stage gives the
    # same clock time with no zone, the call's note says which zone it is in ("18:00-18:30
    # UK" beside a stage line of "18:00", read as the person's own zone, five hours out).
    call_zone = {}
    for c in ctx.contacts:
        if str(c.get("status") or "") == "call_booked":
            w = call_time(c.get("next_action"), home)
            if w and w["zone"] and w["zone"] != home:
                call_zone[(ckey(c.get("company") or ""), str(c.get("next_action_due") or "")[:10],
                           w["time"])] = w["zone"]

    for row, rid in zip(ctx.tracker, app_model.tracker_ids(ctx.tracker)):
        st = app_model._status(row)
        company = str(row.get("company") or "")
        role = str(row.get("role") or "")
        if not st:
            continue
        if st in throttle.UNSENT:
            drafted = str(row.get("cv_file") or "").strip() or \
                str(row.get("cover_letter_file") or "").strip()
            close = app_model._date(row.get("deadline"))
            if drafted and close and today <= close <= today + dt.timedelta(days=DEADLINE_DAYS):
                out.append(_item("deadline", f"up-dl-{rid}", f"Apply by: {role}, {company}",
                                 close.isoformat(), with_=company,
                                 go={"to": "drafts", "item": rid},
                                 note="The application is drafted and not sent yet."))
            continue
        if st in throttle.FINAL:
            continue
        # The build's own reading, once per application, where it has one (app_model.Ctx).
        _folder, _files, stages = getattr(ctx, "stages", open_actions.stages)(row)
        for n_, s in enumerate(stages):
            if not s.get("done") and not _is_day(s.get("date")) and s.get("offered"):
                # Invited, and the day is theirs to choose: the choice is due, on the day
                # they are to answer by, and it says the days offered (the audit, 2026-11-03).
                days = [d for d in s["offered"] if _is_day(d) and d >= today.isoformat()]
                if not days:
                    continue
                by = s.get("reply_by") if _is_day(s.get("reply_by")) else ""
                due = max(today.isoformat(), min(by or days[0], days[0]))
                name = short_label(s.get("label") or "Interview")
                item = _item("deadline", f"up-{rid}-choose-{n_}", f"Choose your day: {name}, "
                             f"{company}", due, with_=company,
                             go={"to": "interviews", "item": "int-" + rid[4:]},
                             note=f"Offered {_days_words(days)}. Tell them the day you choose.",
                             uid=f"up-{rid}-stage-{n_}-choose")
                item["offered"] = days
                if ahead(item["day"]):
                    out.append(item)
                continue
            if s.get("done") or not _is_day(s.get("date")):
                continue
            label_ = label(s.get("label") or "Interview")
            day = str(s["date"])
            # What it is and how long it lasts, as the stage was booked; only a stage booked
            # before 4.7, which says neither, is read from its English words.
            kind = str(s.get("kind") or "")
            test = kind == "test" if kind else bool(_TEST.search(label_))
            time_ = str(s.get("time") or "")
            zone = (_zone_word(s.get("zone"), home) if s.get("zone") else
                    call_zone.get((ckey(company), day, time_), home))
            if zone is None:              # a zone the app does not know: no time, never a wrong one
                time_, zone = "", home
            who = app_model._third_party(s.get("with"), names) if s.get("with") else ""
            item = _item("test" if test else "interview",
                         f"up-{rid}-{_slug(label_)}-{day}" + (f"-{time_.replace(':', '')}" if time_ else ""),
                         # Titled by the round's short name, never an employer's whole
                         # paragraph (the maintainer, 2026-11-07); its id keeps the full one.
                         (f"{short_label(label_)} due: {company}" if test and not time_ else
                          f"{short_label(label_)}: {company}"), day, time_, zone,
                         with_=company, where=place(s.get("place")) or (s.get("place") or None),
                         go={"to": "interviews", "item": "int-" + rid[4:]},
                         note=(f"{role}" + (f", with {who}" if who else "")) or None,
                         minutes=int(s.get("minutes") or 0) or (30 if _SHORT.search(label_) else 60),
                         home=home, uid=f"up-{rid}-stage-{n_}")
            # Asked for and not confirmed by them yet: Coming up and the Brief say so.
            item["tentative"] = bool(s.get("tentative"))
            if ahead(item["day"], item):
                out.append(item)
                seen_days.setdefault((ckey(company), day), set()).add(time_)
    for c in ctx.contacts:
        if str(c.get("status") or "") != "call_booked":
            continue
        day = str(c.get("next_action_due") or "")[:10]
        if not _is_day(day):
            continue
        company = str(c.get("company") or "")
        said = str(c.get("next_action") or "")
        when = call_time(said, home) or {}
        times = seen_days.get((ckey(company), day)) if company else None
        if times is not None and (not when.get("time") or "" in times or when["time"] in times):
            continue                      # the same day's interview stage says it already
        first = app_model.first_name(c.get("name")) or "them"
        cid = str(c.get("contact_id") or "")
        item = _item("call", f"up-call-{_slug(cid)}-{day}",
                     f"Call with {first}" + (f" ({company})" if company else ""), day,
                     when.get("time") or "", when.get("zone") or "", when.get("end") or "",
                     with_=company, where=place(said), go={"to": "contacts", "item": cid},
                     minutes=30, home=home, uid=f"up-call-{_slug(cid)}")
        item["tentative"] = call_tentative(said)
        if ahead(item["day"], item):
            out.append(item)
    for e in added():
        text = app_model.scrub(e.get("title"), names) or "Booked"
        # In the zone it was added in (the page sends the one it shows times in), else theirs.
        ez = str(e.get("zone") or "") if person.known_zone(str(e.get("zone") or "")) else home
        item = _item("event", f"up-{e['id']}", text, str(e["day"]), str(e.get("time") or ""),
                     ez, where=place(text), note=app_model.scrub(e.get("note"), names) or None,
                     home=home)
        item["own"] = e["id"]
        if ahead(item["day"], item):
            out.append(item)
    out.sort(key=lambda i: (i["day"], i["start"] or "", i["title"].lower()))
    for i in out:
        i["cal"] = links(i, page_url, today)
        i["rev"] = app_model.rev_of(i["id"], i["day"], i["start"], i["end"], i["title"], i["note"],
                                    i.get("tentative"))
    return out


# ------------------------------------------------------------------ calendars


def _details(item: dict, page_url: str) -> str:
    bits = [str(item.get("note") or "")]
    if page_url:
        bits.append("Your job search page: " + page_url)
    return "\n".join(b for b in bits if b)


def _days(item: dict) -> tuple[str, str]:
    d = dt.date.fromisoformat(item["day"])
    return d.isoformat(), (d + dt.timedelta(days=1)).isoformat()


def links(item: dict, page_url: str = "", made: dt.date | None = None) -> dict:
    """{"google", "outlook", "ics"}: the ways to add it that need no account connected. An all-day item's end is the next day, as every calendar reads it."""
    text, body, loc = item["title"], _details(item, page_url), item.get("place") or ""
    q = urllib.parse.quote
    if item["all_day"]:
        a, b = _days(item)
        g_dates = a.replace("-", "") + "/" + b.replace("-", "")
        o_start, o_end, allday = a, b, "true"
    else:
        s = item["start"].replace("-", "").replace(":", "")
        e = item["end"].replace("-", "").replace(":", "")
        g_dates = s + "/" + e
        o_start, o_end, allday = item["start"], item["end"], "false"
    google = ("https://calendar.google.com/calendar/render?action=TEMPLATE"
              f"&text={q(text)}&dates={g_dates}&details={q(body)}"
              + (f"&location={q(loc)}" if loc else ""))
    outlook = ("https://outlook.live.com/calendar/action/compose?path=%2Fcalendar%2Faction%2F"
               f"compose&rru=addevent&startdt={q(o_start)}&enddt={q(o_end)}&allday={allday}"
               f"&subject={q(text)}&body={q(body)}" + (f"&location={q(loc)}" if loc else ""))
    return {"google": google, "outlook": outlook, "ics": vevent(item, page_url, made)}


def _esc(text: str) -> str:
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 3.1: lines over 75 octets go on, after CRLF and one space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def reminder_minutes() -> int | None:
    """How long before a timed event its calendar reminder comes, in minutes, from the
    person's setting (person.json `calendar_reminder`); None for no reminder at all."""
    try:
        got = str(person.get("calendar_reminder", "60") or "60")
    except Exception:  # noqa: BLE001  no profile: the usual hour
        got = "60"
    return None if got == "off" else int(got) if got in ("15", "60", "120", "1440") else 60


def vevent(item: dict, page_url: str = "", stamp: dt.datetime | dt.date | None = None) -> str:
    """One VEVENT, CRLF lines; `calendar()` wraps one or more. Its UID is the item's own, so
    adding it again where a calendar keeps UIDs updates it rather than adding a second. Its
    DTSTAMP is the day the list was made, at midnight UTC, never the clock: a stamp to the
    second changed the page's whole version on every run, and woke the page for nothing."""
    if isinstance(stamp, dt.datetime):
        stamp = stamp.strftime("%Y%m%dT%H%M%SZ")
    else:
        stamp = (stamp or dt.datetime.now(dt.timezone.utc).date()).strftime("%Y%m%dT000000Z")
    # SEQUENCE grows with the day the list is made, so a calendar that holds this UID takes
    # the moved event as newer (RFC 5545 3.8.7.4).
    seq = (dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8])) - dt.date(2026, 1, 1)).days
    lines = ["BEGIN:VEVENT", f"UID:{item.get('uid') or item['id']}.last-job-search",
             f"DTSTAMP:{stamp}", f"SEQUENCE:{max(seq, 0)}"]
    # When it reminds them is theirs (Settings, Calendar reminders): an hour before unless they
    # chose otherwise, none at all if they said so; a day with no time, the afternoon before.
    remind = reminder_minutes()
    if item["all_day"]:
        a, b = _days(item)
        lines += [f"DTSTART;VALUE=DATE:{a.replace('-', '')}", f"DTEND;VALUE=DATE:{b.replace('-', '')}"]
        alarm = "-PT9H"           # the afternoon before
    else:
        fmt = lambda s: s.replace("-", "").replace(":", "")  # noqa: E731
        lines += [f"DTSTART:{fmt(item['start'])}", f"DTEND:{fmt(item['end'])}"]
        alarm = ({15: "-PT15M", 60: "-PT1H", 1440: "-P1D"}.get(remind, f"-PT{remind}M")
                 if remind else "")
    lines.append("SUMMARY:" + _esc(item["title"]))
    body = _details(item, page_url)
    if body:
        lines.append("DESCRIPTION:" + _esc(body))
    if item.get("place"):
        lines.append("LOCATION:" + _esc(item["place"]))
    if page_url:
        lines.append("URL;VALUE=URI:" + page_url)
    if remind is not None and alarm:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc(item["title"]),
                  f"TRIGGER:{alarm}", "END:VALARM"]
    lines.append("END:VEVENT")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def calendar(events: list[str]) -> str:
    """A whole .ics: one or more VEVENTs as `vevent` made them."""
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//last-job-search//Coming up//EN\r\n"
            "CALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n" + "".join(events) + "END:VCALENDAR\r\n")


# ------------------------------------------------------------------ command line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--today", default="")
    a_ = sub.add_parser("add")
    a_.add_argument("title")
    a_.add_argument("day")
    a_.add_argument("time", nargs="?", default="")
    a_.add_argument("--note", default="")
    r_ = sub.add_parser("remove")
    r_.add_argument("id")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        try:
            row = add(a.title, a.day, a.time, a.note)
        except ValueError as e:
            print(f"upcoming: {e}")
            return 1
        print(f"upcoming: kept {row['title']} on {row['day']}" + (f" at {row['time']}" if row.get("time") else ""))
        return 0
    if a.cmd == "remove":
        gone = remove(a.id)
        print(f"upcoming: took away {gone['title']}" if gone else f"upcoming: nothing called {a.id}")
        return 0 if gone else 1
    import app_model
    today, now = app_model.clock(a.today or None, None)
    ctx = app_model.Ctx(today, now)
    for i in build(ctx):
        when = i["day"] + (f" {i['time']}" if i["time"] else "")
        print(f"{when}  {i['kind']:9}  {i['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
