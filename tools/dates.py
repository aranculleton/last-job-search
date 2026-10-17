#!/usr/bin/env python3
"""One reading of a date, for everything that ages a row, a message or a posting.

The tracker, the message log, a portal's posting date and a search snippet all
hand over dates, and eight helpers used to read them, each with its own rules.
The rules drifted: one helper read a timestamp and the next returned None on
it, so a post dated `2026-10-17T10:00:00` was a day old to one reader and
undated to another. This is the one definition. The helpers that remain are
thin wrappers that say which of its two widenings they want.

What is read, in order:
  date, datetime     as given; a datetime gives its date
  ISO at the start   `2026-10-17`, a timestamp (`2026-10-17T10:00:00Z`, or
                     with a space), or the date with a note after it
  other formats      `2026-10`, `2026-1-7`, `2026/10/17`, `17 October 2026`,
                     `October 2026`, `Oct 2026`, each optionally followed by a
                     `T` time; a month alone is its first day. Skipped with
                     `iso_only=True`
  anywhere           the first ISO date in the text, as in "sent 2026-10-17";
                     only with `anywhere=True`

`20261017` and week dates (`2026-W42-6`) are not read. `date.fromisoformat`
took them from Python 3.11 and refused them on 3.10, so what a helper read
used to depend on the Python running it.

It imports nothing from the app, so anything can import it, the throttle
included: state imports the throttle, so the throttle cannot import state.

Usage:
    from dates import as_date, days_since
    as_date("2026-10-17T10:00:00")                    # date(2026, 10, 17)
    days_since("2026-10-10", date(2026, 10, 17))      # 7
"""

from __future__ import annotations

import datetime
import re

# ASCII digits only: ISO 8601 has no others, and fromisoformat refuses them.
_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")

# What a search snippet or a profile page writes. "%Y-%m-%d" is here as well as
# in _ISO because strptime also takes an unpadded `2026-1-7`.
FORMATS = ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%d %B %Y", "%B %Y", "%b %Y")

# A time after a date: "T" and a digit. A bare split on "T" cut "OCT 2026" to "OC".
_TIME = re.compile(r"T(?=[0-9])")


def _ymd(m) -> datetime.date | None:
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def as_date(value, *, iso_only: bool = False,
            anywhere: bool = False) -> datetime.date | None:
    """A date from a date, a datetime or text, or None when there is nothing usable.

    `iso_only` reads only an ISO date at the start, which is what a portal or a
    tracker cell holds, and keeps "October 2026" from reading as 1 October.
    `anywhere` also takes the first ISO date inside text, for hand-edited rows
    where the date sits in a note. An impossible date (`2026-02-30`) is None,
    never the next date along.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = " ".join(str(value if value is not None else "").split())
    m = _ISO.match(text)
    if m:
        return _ymd(m)
    if not iso_only:
        head = _TIME.split(text, 1)[0]
        for fmt in FORMATS:
            try:
                return datetime.datetime.strptime(head, fmt).date()
            except ValueError:
                continue
    if anywhere:
        m = _ISO.search(text)
        if m:
            return _ymd(m)
    return None


def days_since(value, today=None, *, iso_only: bool = False,
               anywhere: bool = False) -> int | None:
    """Whole days from `value` to `today`, or None when `value` cannot be read.

    Negative when `value` is after `today`. `today` defaults to the real date
    and is read like `value`; the flags are `as_date`'s.
    """
    then = as_date(value, iso_only=iso_only, anywhere=anywhere)
    if then is None:
        return None
    now = as_date(today) if today else datetime.date.today()
    if now is None:
        raise ValueError(f"days_since needs a readable date for today, got {today!r}")
    return (now - then).days
