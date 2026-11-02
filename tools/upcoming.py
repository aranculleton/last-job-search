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
_TEST = re.compile(r"\b(?:test|assessment|case study|take[- ]home|exercise|challenge|hirevue|"
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
_ZONE = r"(?:\s*\(?\s*(?-i:([A-Z]{2,5}))\b)?"
_RANGE = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + r"\s*(?:-|–|to)\s*"
                    r"(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + _ZONE, re.I)
_ONE = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.h](\d{2}))?\s*" + _MER + _ZONE, re.I)


def _zone_word(word: str, home: str) -> str | None:
    """The zone a written word names, `home` where none is written, None where the word reads
    as a zone the app does not know ("IST", "BRT"): a time read in the wrong zone is worse
    than no time."""
    import app_model
    w = str(word or "").upper()
    if not w:
        return home
    if w in app_model._ZONE_WORDS:
        return app_model._ZONE_WORDS[w]
    return None if w.endswith("T") else home


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
    if not found:
        return None
    # The first written; at one place, the longest reading (a range, an am or pm).
    _at, _len, time_, end, word = min(found)
    zone = _zone_word(word, home)
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


def add(title: str, day: str, time_: str = "", note: str = "", eid: str = "") -> dict:
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
           **({"note": " ".join(str(note).split())[:200]} if str(note or "").strip() else {})}
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
          go=None, note=None, minutes=None, home="") -> dict:
    """One thing on the list. A timed one sits on the day it falls on where the person is:
    18:00 in California is the next morning in London, and the interview's own card says so
    (the release review, 2026-11-02)."""
    start = _moment(day, time_, zone) if time_ else None
    if start and home:
        day = _local_day(start, home)
    if start:
        if end_time:
            end = _moment(day, end_time, zone)
            if not end or end <= start:
                end = None
        else:
            end = None
        end = end or start + dt.timedelta(minutes=minutes or 60)
    return {"id": iid, "kind": kind, "title": title, "with": with_ or None, "day": day,
            "time": time_ or None, "zone": zone if start else None,
            "start": _iso(start) if start else None, "end": _iso(end) if start else None,
            "all_day": not start, "place": where, "go": go, "note": note}


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

    def ahead(day) -> bool:
        d = app_model._date(day)
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
        _folder, _files, stages = open_actions.stages(row)
        for s in stages:
            if s.get("done") or not _is_day(s.get("date")):
                continue
            label = str(s.get("label") or "Interview")
            day = str(s["date"])
            test = bool(_TEST.search(label))
            time_ = str(s.get("time") or "")
            zone = (_zone_word(s.get("zone"), home) if s.get("zone") else
                    call_zone.get((ckey(company), day, time_), home))
            if zone is None:              # a zone the app does not know: no time, never a wrong one
                time_, zone = "", home
            who = app_model._third_party(s.get("with"), names) if s.get("with") else ""
            item = _item("test" if test else "interview",
                         f"up-{rid}-{_slug(label)}-{day}" + (f"-{time_.replace(':', '')}" if time_ else ""),
                         (f"{label} due: {company}" if test and not time_ else
                          f"{label}: {company}"), day, time_, zone,
                         with_=company, go={"to": "interviews", "item": "int-" + rid[4:]},
                         note=(f"{role}" + (f", with {who}" if who else "")) or None,
                         minutes=30 if _SHORT.search(label) else 60, home=home)
            if ahead(item["day"]):
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
                     minutes=30, home=home)
        if ahead(item["day"]):
            out.append(item)
    for e in added():
        text = app_model.scrub(e.get("title"), names) or "Booked"
        item = _item("event", f"up-{e['id']}", text, str(e["day"]), str(e.get("time") or ""),
                     home, where=place(text), note=app_model.scrub(e.get("note"), names) or None,
                     home=home)
        item["own"] = e["id"]
        if ahead(item["day"]):
            out.append(item)
    out.sort(key=lambda i: (i["day"], i["start"] or "", i["title"].lower()))
    for i in out:
        i["cal"] = links(i, page_url, today)
        i["rev"] = app_model.rev_of(i["id"], i["day"], i["start"], i["end"], i["title"], i["note"])
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


def vevent(item: dict, page_url: str = "", stamp: dt.datetime | dt.date | None = None) -> str:
    """One VEVENT, CRLF lines; `calendar()` wraps one or more. Its UID is the item's own, so
    adding it again where a calendar keeps UIDs updates it rather than adding a second. Its
    DTSTAMP is the day the list was made, at midnight UTC, never the clock: a stamp to the
    second changed the page's whole version on every run, and woke the page for nothing."""
    if isinstance(stamp, dt.datetime):
        stamp = stamp.strftime("%Y%m%dT%H%M%SZ")
    else:
        stamp = (stamp or dt.datetime.now(dt.timezone.utc).date()).strftime("%Y%m%dT000000Z")
    lines = ["BEGIN:VEVENT", f"UID:{item['id']}.last-job-search", f"DTSTAMP:{stamp}"]
    if item["all_day"]:
        a, b = _days(item)
        lines += [f"DTSTART;VALUE=DATE:{a.replace('-', '')}", f"DTEND;VALUE=DATE:{b.replace('-', '')}"]
        alarm = "-PT9H"           # the afternoon before
    else:
        fmt = lambda s: s.replace("-", "").replace(":", "")  # noqa: E731
        lines += [f"DTSTART:{fmt(item['start'])}", f"DTEND:{fmt(item['end'])}"]
        alarm = "-PT1H"
    lines.append("SUMMARY:" + _esc(item["title"]))
    body = _details(item, page_url)
    if body:
        lines.append("DESCRIPTION:" + _esc(body))
    if item.get("place"):
        lines.append("LOCATION:" + _esc(item["place"]))
    if page_url:
        lines.append("URL;VALUE=URI:" + page_url)
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc(item["title"]),
              f"TRIGGER:{alarm}", "END:VALARM", "END:VEVENT"]
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
