#!/usr/bin/env python3
"""The person this copy of the app works for: one loader, by path.

Every fact about the candidate (name, contact line, work history, bullets,
skills, market, preferences, voice) lives in their profile directory, and no
tool hardcodes one. This module is the only way in.

Where the profile is:
    profile/ at the repo root, or wherever LJS_PROFILE points (a path, absolute
    or relative to the repo root). The app's own tests set LJS_PROFILE to
    profile.example/, a fictional person, so they run with nobody's real data.

What happens with no profile:
    NoProfile, whose message says to run /setup. There is deliberately NO
    fallback to the example person. A stranger who skipped /setup must get a
    loud error, never a resume under a fictional name, and never the example's
    market rules silently applied to their search.

Why by path and not `import profile`:
    `profile` is a standard-library module (the profiler), so a package of that
    name would shadow it or be shadowed by it depending on sys.path order. Each
    profile file is loaded from its path with importlib under a private module
    name instead.

Usage:
    import person
    person.module("bullets").LIB          # profile/bullets.py
    person.data("person")["identity"]     # profile/person.json
    person.get("identity.email")          # one dotted value from person.json
    person.path("01-candidate-profile.md")

    python3 tools/person.py dir           # the profile directory in use
    python3 tools/person.py get identity.email
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import python_floor  # noqa: E402

python_floor.require()

# The tools a person installed where a non-login shell does not look (MacTeX's
# /Library/TeX/texbin, Bun's ~/.bun/bin): on PATH for every tool, tools/local_path.py.
import local_path  # noqa: E402

local_path.extend()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = "LJS_PROFILE"
DEFAULT = "profile"
EXAMPLE = os.path.join(ROOT, "profile.example")


def in_example(path: str) -> bool:
    """Is `path` inside the app's example person (profile.example/)? The app's own tests and
    any chat in the app's checkout read it, so a tool run there records nothing into it."""
    return os.path.realpath(path).startswith(os.path.realpath(EXAMPLE) + os.sep)


# ------------------------------------------------------------------ the person's time zone
#
# One reader of a time zone from the words people write ("Eastern (Toronto time)", "10am ET",
# "Pacific Time", "UK", "Mississauga"), and one zone for the person: theirs, never the zone
# their brief is scheduled in. A person in Toronto whose brief ran on UK time had every time
# on the page, every calendar link and the page's "today" five hours out, because the
# person's TIMEZONE said "Eastern (Toronto time)", which named no zone the old reader knew,
# and the brief's schedule zone stood in for it (the audit, 2026-11-03).

# The words an invite writes beside a time, read as the place they name. One a place does
# not settle is left out: a time in a zone not known here keeps its day alone, never a wrong
# hour.
ZONE_WORDS = {"UTC": "UTC", "GMT": "Etc/GMT", "BST": "Europe/London", "UK": "Europe/London",
              "WET": "Europe/Lisbon", "WEST": "Europe/Lisbon", "CET": "Europe/Paris",
              "CEST": "Europe/Paris", "EET": "Europe/Athens", "EEST": "Europe/Athens",
              "ET": "America/New_York", "EST": "America/New_York", "EDT": "America/New_York",
              "CT": "America/Chicago", "CST": "America/Chicago", "CDT": "America/Chicago",
              "MT": "America/Denver", "AT": "America/Halifax", "AST": "America/Halifax",
              "ADT": "America/Halifax", "NST": "America/St_Johns", "NDT": "America/St_Johns",
              "AKST": "America/Anchorage", "AKDT": "America/Anchorage", "HST": "Pacific/Honolulu",
              "MST": "America/Denver", "MDT": "America/Denver", "PT": "America/Los_Angeles",
              "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles",
              "SGT": "Asia/Singapore", "HKT": "Asia/Hong_Kong", "JST": "Asia/Tokyo",
              "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney",
              "NZST": "Pacific/Auckland", "NZDT": "Pacific/Auckland"}
# A zone said in plain words, as people write it: "Eastern", "Pacific Time", "UK time".
PLAIN_ZONES = {"eastern": "America/New_York", "pacific": "America/Los_Angeles",
               "central": "America/Chicago", "mountain": "America/Denver",
               "atlantic": "America/Halifax", "newfoundland": "America/St_Johns",
               "alaska": "America/Anchorage", "hawaii": "Pacific/Honolulu",
               "uk": "Europe/London", "british": "Europe/London", "greenwich": "Etc/GMT",
               "irish": "Europe/Dublin", "central european": "Europe/Paris",
               "eastern european": "Europe/Athens", "western european": "Europe/Lisbon",
               "india": "Asia/Kolkata", "indian": "Asia/Kolkata", "japan": "Asia/Tokyo",
               "singapore": "Asia/Singapore", "utc": "UTC", "gmt": "Etc/GMT"}
# Places that sit in one time zone and are not a zone's own name, written folded (no
# accents). A zone's own city ("Toronto", "London", "New York") is found from the zone list.
PLACE_ZONES = {
    "ontario": "America/Toronto", "quebec": "America/Toronto",
    "mississauga": "America/Toronto", "brampton": "America/Toronto", "markham": "America/Toronto",
    "vaughan": "America/Toronto", "oakville": "America/Toronto", "ottawa": "America/Toronto",
    "waterloo": "America/Toronto", "montreal": "America/Toronto",
    "british columbia": "America/Vancouver", "alberta": "America/Edmonton",
    "calgary": "America/Edmonton", "manitoba": "America/Winnipeg",
    "saskatchewan": "America/Regina", "nova scotia": "America/Halifax",
    "new brunswick": "America/Moncton", "newfoundland and labrador": "America/St_Johns",
    "san francisco": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "san jose": "America/Los_Angeles", "palo alto": "America/Los_Angeles",
    "mountain view": "America/Los_Angeles", "california": "America/Los_Angeles",
    "boston": "America/New_York", "massachusetts": "America/New_York",
    "washington dc": "America/New_York", "philadelphia": "America/New_York",
    "atlanta": "America/New_York", "miami": "America/New_York", "new jersey": "America/New_York",
    "austin": "America/Chicago", "dallas": "America/Chicago", "houston": "America/Chicago",
    "texas": "America/Chicago", "illinois": "America/Chicago", "colorado": "America/Denver",
    "united kingdom": "Europe/London", "england": "Europe/London", "scotland": "Europe/London",
    "wales": "Europe/London", "northern ireland": "Europe/London", "uk": "Europe/London",
    "manchester": "Europe/London", "leeds": "Europe/London", "birmingham": "Europe/London",
    "edinburgh": "Europe/London", "glasgow": "Europe/London", "bristol": "Europe/London",
    "cambridge": "Europe/London", "oxford": "Europe/London", "ireland": "Europe/Dublin",
    "france": "Europe/Paris", "germany": "Europe/Berlin", "munich": "Europe/Berlin",
    "netherlands": "Europe/Amsterdam", "spain": "Europe/Madrid", "italy": "Europe/Rome",
    "milan": "Europe/Rome", "switzerland": "Europe/Zurich", "sweden": "Europe/Stockholm",
    "india": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "japan": "Asia/Tokyo",
    "new zealand": "Pacific/Auckland",
}
# Countries that span several zones: they name a continent, never a time.
WIDE_COUNTRIES = {"united states": "America", "usa": "America", "us": "America",
                  "canada": "America", "australia": "Australia", "brazil": "America",
                  "mexico": "America", "indonesia": "Asia"}
_IANA_RX = r"\b[A-Z][A-Za-z]+(?:/[A-Za-z0-9_+-]+)+\b"


def _fold(text) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or ""))
                   if not unicodedata.combining(c)).lower()


def known_zone(name: str) -> bool:
    """Does this computer have data for the zone named?"""
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(str(name or ""))
        return "/" in str(name) or str(name) == "UTC"
    except Exception:  # noqa: BLE001  not a zone, or no zone data here
        return False


_CITIES: dict | None = None


def zone_cities() -> dict:
    """{"toronto": "America/Toronto", ...}: every zone's own city, built once."""
    global _CITIES
    if _CITIES is None:
        out = {}
        try:
            import zoneinfo
            for z in sorted(zoneinfo.available_timezones()):
                if "/" in z and z.split("/")[0] in ("America", "Europe", "Asia", "Africa",
                                                    "Australia", "Pacific", "Atlantic",
                                                    "Indian"):
                    out.setdefault(z.rsplit("/", 1)[-1].replace("_", " ").lower(), z)
        except Exception:  # noqa: BLE001  no time zone data on this computer
            out = {}
        _CITIES = out
    return _CITIES


def _place_zone(part: str, cities: dict) -> str:
    import re
    p = " ".join(_fold(part).split()).strip(" .")
    if not p:
        return ""
    if p in PLACE_ZONES:
        return PLACE_ZONES[p]
    if p in cities:
        return cities[p]
    for name in sorted(list(PLACE_ZONES) + list(cities), key=len, reverse=True):
        if len(name) > 3 and re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), p):
            return PLACE_ZONES.get(name) or cities[name]
    return ""


def zone_for(location: str) -> str:
    """The time zone a place sits in, or "" when it names none for certain. The broadest
    part that names a continent decides between rival readings: "London, Ontario, Canada" is
    Toronto's time, and "Manchester, New Hampshire, United States" is none this knows."""
    cities = zone_cities()
    parts = [x for x in str(location or "").split(",") if x.strip()]
    zones = [_place_zone(x, cities) for x in parts]
    wide = [WIDE_COUNTRIES.get(_fold(x).strip(), "") for x in parts]
    anchor = next((w or (z.split("/")[0] if z else "") for z, w in
                   reversed(list(zip(zones, wide))) if w or z), "")
    for z in zones:
        if z and (not anchor or z.split("/")[0] == anchor):
            return z
    return ""


def _same_clock(a: str, b: str) -> bool:
    """Are two zones one family of clock, the same in winter or in summer (Toronto and New
    York; Vancouver and Los Angeles, now British Columbia keeps summer time all year; Phoenix
    and Denver)? Then the person's own zone is what the word means for them."""
    try:
        import datetime as _dt
        import zoneinfo
        za, zb = zoneinfo.ZoneInfo(a), zoneinfo.ZoneInfo(b)
        year = _dt.date.today().year
        return any(_dt.datetime(year, m, 15, 12, tzinfo=za).utcoffset()
                   == _dt.datetime(year, m, 15, 12, tzinfo=zb).utcoffset() for m in (1, 7))
    except Exception:  # noqa: BLE001
        return False


def zone_in(text, home: str = "") -> str:
    """The time zone the words name, or "": a zone's own name ("America/Toronto"), a place
    ("Toronto time", "Mississauga", "Manchester, UK"), a plain word ("Eastern", "Pacific
    Time", "UK time") or a word an invite writes beside a time (ET, BST). Where the words
    keep the same clock as `home` (ET for a person in Toronto), `home` is given, so the page
    names the person's own city."""
    import re
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    for m in re.finditer(_IANA_RX, raw):
        if known_zone(m.group(0)):
            return m.group(0)
    found = zone_for(raw) or zone_for(re.sub(r"\b(?:time|zone|standard|daylight)\b", " ", raw,
                                             flags=re.I))
    if not found:
        low = " ".join(re.sub(r"[^a-z ]+", " ", _fold(raw)).split())
        for words in sorted(PLAIN_ZONES, key=len, reverse=True):
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(words), low):
                found = PLAIN_ZONES[words]
                break
    if not found:
        for w in re.findall(r"\b[A-Z]{2,5}\b", raw):
            if w in ZONE_WORDS:
                found = ZONE_WORDS[w]
                break
    if found and home and home != found and _same_clock(found, home):
        return home
    return found if found and known_zone(found) else ""


def _profile_line(profile_dir: str, filename: str, name: str) -> str:
    """`NAME = "..."` from a profile file, read as text (the profile is not run here)."""
    import re
    try:
        with open(os.path.join(profile_dir, filename), encoding="utf-8") as fh:
            m = re.search(r"^%s\s*=\s*[\"'](.*?)[\"']" % name, fh.read(), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def home_zone_named(profile_dir: str) -> str:
    """The person's own time zone (an IANA name), or "" when nothing they wrote names one,
    so the page asks them. In this order: the page's own setting (person.json `time_zone`,
    Settings, Your time zone), networking.py TIMEZONE and HOME_CITY, and person.json
    identity.location, each read from the words written ("Eastern (Toronto time)" is
    Toronto's). Never the zone the brief is scheduled in (routines.json): that is when a
    message is sent, not where the person lives. Read as text, without running the profile,
    since it is wanted before anything else has loaded."""
    try:
        with open(os.path.join(profile_dir, "person.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    got = got if isinstance(got, dict) else {}
    setting = str(got.get("time_zone") or "")
    tz_words = _profile_line(profile_dir, "networking.py", "TIMEZONE")
    city = _profile_line(profile_dir, "networking.py", "HOME_CITY")
    where = str((got.get("identity") or {}).get("location") or "") \
        if isinstance(got.get("identity"), dict) else ""
    base = zone_for(city) or zone_for(where)
    for words in (setting, tz_words):
        z = zone_in(words, base)
        if z:
            return z
    return base


def cloud_day(env=None, profile_dir: str | None = None) -> str:
    """In a cloud chat, the person's own day: TZ set to their home zone, so `date.today()`
    is their date and not the cloud computer's. A cloud computer runs on UTC, and the brief
    for a person in Sydney, due on their Monday morning, was dated and worked out as Sunday
    (found 2026-10-25). Only in a cloud chat (CLAUDE_CODE_REMOTE), only where TZ is unset
    (an explicit TZ wins), only for the person's own profile (the app's own tests point
    LJS_PROFILE at the example person, whose zone is not the computer's), and only for a
    zone this computer has data for. Returns the zone it set, or ""."""
    env = os.environ if env is None else env
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() != "true" or env.get("TZ") \
            or env.get(ENV):
        return ""
    import time
    if not hasattr(time, "tzset"):
        return ""
    zone = home_zone_named(profile_dir or os.path.join(ROOT, DEFAULT))
    if not zone:
        return ""
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(zone)
    except Exception:  # noqa: BLE001  no data for that zone here: the computer's day stands
        return ""
    env["TZ"] = zone
    if env is os.environ:
        time.tzset()
    return zone


cloud_day()


def home_zone():
    """The person's own time zone as a tzinfo (home_zone_named, for the profile in use), or
    None where none is named or this computer has no data for it: then this computer's own
    clock."""
    try:
        import zoneinfo
        z = home_zone_named(os.path.dirname(path("person.json")))
        return zoneinfo.ZoneInfo(z) if z else None
    except Exception:  # noqa: BLE001  no profile, or no data for that zone here
        return None


def today(now=None):
    """The person's own day: the date in their zone, never the computer's, which in a cloud
    chat runs on UTC and on a laptop can sit in another zone than the profile names. The app's
    hook and the improvements' record count this one day: on two clocks, a Toronto evening
    marked an improvement started tomorrow and the hold started a second one (2026-11-03)."""
    import datetime as dt
    now = now or dt.datetime.now(dt.timezone.utc)
    z = home_zone()
    return (now.astimezone(z) if z else now.astimezone()).date()

# Another chat may hold the profile, or be writing it: look before starting again (2026-10-25).
SETUP_HINT = ("no profile here: run `python3 tools/place.py state` first (another chat may hold "
              "it or be writing it), and run /setup only if it finds none")


class NoProfile(RuntimeError):
    """The profile directory, or a file a tool needs from it, does not exist."""


def directory() -> str:
    """The profile directory in use. Raises NoProfile if it does not exist."""
    p = os.environ.get(ENV) or DEFAULT
    if not os.path.isabs(p):
        p = os.path.join(ROOT, p)
    p = os.path.normpath(p)
    if not os.path.isdir(p):
        raise NoProfile(f"{SETUP_HINT} (looked for {p})")
    return p


def exists(*parts: str) -> bool:
    """Whether a profile is in place (and, given parts, whether that file is)."""
    try:
        d = directory()
    except NoProfile:
        return False
    return os.path.exists(os.path.join(d, *parts)) if parts else True


def path(*parts: str) -> str:
    """A path inside the profile directory. The file need not exist."""
    return os.path.join(directory(), *parts)


def file(key: str, default: str) -> str:
    """One of the profile's documents, by its person.json `files` key.

    `files` maps a key (candidate_profile, evaluation, summary) to a path
    relative to the profile directory, so a profile whose documents still live
    elsewhere can point at them; the default is a name inside the profile.
    """
    return os.path.normpath(path(get(f"files.{key}", default)))


def _need(name: str) -> str:
    f = path(name)
    if not os.path.isfile(f):
        raise NoProfile(f"the profile has no {name} ({f}): run /setup for that part, or add it")
    return f


_modules: dict = {}
_data: dict = {}


def module(name: str):
    """Load profile/<name>.py by path and return it. Cached per file."""
    f = _need(name + ".py")
    if f not in _modules:
        spec = importlib.util.spec_from_file_location(f"ljs_profile_{name}", f)
        mod = importlib.util.module_from_spec(spec)
        # No compiled copy beside the profile: profile/__pycache__ is one more thing a forced
        # add commits, and these files are read once a run.
        was, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = was
        _modules[f] = mod
    return _modules[f]


def data(name: str = "person"):
    """Load profile/<name>.json and return it. Cached per file."""
    f = _need(name + ".json")
    if f not in _data:
        with open(f, encoding="utf-8") as fh:
            _data[f] = json.load(fh)
    return _data[f]


_MISSING = object()


def get(dotted: str, default=_MISSING):
    """One value from person.json by dotted key, e.g. "identity.email"."""
    node = data("person")
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif default is not _MISSING:
            return default
        else:
            raise KeyError(f"person.json has no {dotted!r}")
    return node


STATE_ENV = "LJS_STATE"


def state(*parts: str) -> str:
    """A path to the search's state: the tracker, the network CSVs, documents/.

    State lives at the repo root, beside the profile rather than inside it, so
    a person's tracker and contact book stay where they have always been.
    LJS_STATE moves the root, which is how the app's tests point the state
    tools at the example person's small fake tracker and contact book.
    """
    root = os.environ.get(STATE_ENV) or ROOT
    if not os.path.isabs(root):
        root = os.path.join(ROOT, root)
    return os.path.join(os.path.normpath(root), *parts)


def main_checkout() -> str | None:
    """The repository's main working folder when this one is a linked git worktree, else
    None. A local chat works in a worktree of its own (CLAUDE.md, "On the person's own
    computer"), and a worktree has none of the ignored files the main folder holds."""
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir", "--git-common-dir"], cwd=ROOT,
                           capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    got = r.stdout.split() if r.returncode == 0 else []
    if len(got) != 2:
        return None
    here, common = (os.path.realpath(os.path.join(ROOT, g)) for g in got)
    if here == common:
        return None
    main = os.path.dirname(common)
    return main if os.path.isdir(main) and main != os.path.realpath(ROOT) else None


def local_state(*parts: str) -> str:
    """A state file git does not carry (a connections export, a sync cursor), from this
    folder, or from the main checkout when this is a worktree that lacks it. In a worktree
    the connections export was simply not there, and a run found nothing, silently."""
    here = state(*parts)
    if os.path.exists(here) or os.environ.get(STATE_ENV):
        return here
    main = main_checkout()
    there = os.path.join(main, *parts) if main else ""
    return there if there and os.path.exists(there) else here


def text(name: str) -> str:
    """The contents of a text file in the profile (markdown, a phrase list)."""
    with open(_need(name), encoding="utf-8") as fh:
        return fh.read()


# Where US Letter is the standard paper. Everywhere else uses A4, which is also
# the default when the country is not known.
LETTER_COUNTRIES = frozenset({
    "US", "CA", "MX", "CL", "CO", "CR", "DO", "GT", "PA", "PH", "PR", "VE", "SV",
    "NI", "BZ",
})


def country() -> str:
    """The person's country as an ISO 3166 alpha-2 code, upper case, or "".

    identity.country in person.json; failing that, search.py PORTAL_COUNTRY,
    which every profile that scrapes already sets.
    """
    c = get("identity.country", "") or ""
    if not c:
        try:
            c = getattr(module("search"), "PORTAL_COUNTRY", "") or ""
        except NoProfile:
            c = ""
    return str(c).strip().upper()


def paper(kind: str = "resume") -> str:
    """The LaTeX paper option for a document: "letterpaper" or "a4paper".

    The country decides (US Letter across most of the Americas, A4 everywhere
    else), so nobody has to know which their market uses. An explicit setting
    wins: documents.letter_paper for the letter, then documents.paper for both.
    """
    if kind == "letter" and get("documents.letter_paper", ""):
        return get("documents.letter_paper")
    if get("documents.paper", ""):
        return get("documents.paper")
    return "letterpaper" if country() in LETTER_COUNTRIES else "a4paper"


REMOVE = object()


def update(change) -> dict:
    """Change person.json in one place, atomically: `change(data)` edits the parsed file in
    place, and the file is written whole (a temporary file, then a rename, so a reader never
    sees half of it). The one writer of person.json; returns the data written."""
    import json
    p = path("person.json")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    change(data)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)
    reset()
    return data


def put(dotted, value) -> object:
    """One value in person.json by dotted key (or a list of keys, for a name with a dot in
    it); REMOVE takes it out. Returns what was there before (_MISSING when nothing was)."""
    parts = list(dotted) if isinstance(dotted, (list, tuple)) else str(dotted).split(".")
    seen = {}

    def change(data):
        here = data
        for k in parts[:-1]:
            if not isinstance(here.get(k), dict):
                here[k] = {}
            here = here[k]
        seen["before"] = here.get(parts[-1], _MISSING)
        if value is REMOVE:
            here.pop(parts[-1], None)
        else:
            here[parts[-1]] = value
    update(change)
    return seen["before"]


MISSING = _MISSING


def reset() -> None:
    """Forget cached files. Tests that switch LJS_PROFILE call this."""
    _modules.clear()
    _data.clear()


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/person.py dir | get <dotted.key>")
        return 0
    try:
        if argv[:1] == ["dir"]:
            print(directory())
            return 0
        if len(argv) == 2 and argv[0] == "get":
            v = get(argv[1])
            print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            return 0
    except (NoProfile, KeyError) as e:
        print(f"person: {e}", file=sys.stderr)
        return 1
    print(__doc__.split("Usage:")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
