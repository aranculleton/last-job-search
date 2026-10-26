#!/usr/bin/env python3
"""Tweak: one change to one output, applied by the chat that claims the work item.

TWEAKS.md (2026-10-25). The page sends a `tweak` work item (`args`: `target {id, output,
rev}`, `changes [{p, v}]`, `text`, `keep`); the chat that claims it runs this, and this
decides everything code can:

    python3 tools/tweak.py table                      the rows the page builds each panel from
    python3 tools/tweak.py plan  --work <item.json>   checked, costed and keyed; what will run
    python3 tools/tweak.py apply --work <item.json>   do it, or say what needs writing
    python3 tools/tweak.py merge --work <item.json> --round <dir>   a redraft back, audited
    python3 tools/tweak.py undo  --work <item.json>   the change before it, back
    python3 tools/tweak.py promote [--add N]          words asked for three times, as a button

Code only, no model: a resume or letter's look, size, spacing, colour, a bullet swapped for
another true one, who the letter is addressed to (draft.json changed, then fit_to_page and
verify_batch, the checks every application gets); a first note's length, opening, ask,
order and what it includes, built again from its parts (tools/network/parts.py) through
the same composer and its gates; and the page's own views, which change nothing here.

A wording change (the summary, the letter's tone, one part of it, or the person's own
words in the box) is a redraft of only those fields. `apply` stages the kept draft into a
scratch round (`stage_kept`) so both audits run on it exactly as on a new draft, and prints
the packet: the fields as they stand, their claims, the person's words fenced
(untrusted.fence_wish). The chat's own model writes the fields, the model auditor reads
them, `stage_picks.py audit` and `assemble` run, and `merge` brings it back.

Same inputs, same result, no new call (5.3): every change is keyed on the target, the
draft as it stands, the changes, the words and the rules, and kept in the output's
`tweaks.json` with the draft before and after. A key seen before is "already done", or
its kept result is put back and rendered: a wording result is never written twice. Nothing
here ever offers what TWEAKS.md section 4 rules out (NEVER).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(ROOT, "templates"), os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

TWEAKS_FILE = "tweaks.json"
BUTTONS_FILE = "tweaks.json"            # profile/tweaks.json: the person's own buttons
WISH_MAX = 400
BUTTONS_PER_KIND = 2
PROMOTE_AFTER = 3
PROMOTE_DAYS = 90
OVERLAP = 0.6

# The letter's own fields, and the resume's summary: what a redraft may touch.
TEXT_FIELDS = ("summary", "p1", "p2", "lead", "cl_bullets", "p4", "tools")
PART_NAMES = {"p1": "the opening", "p2": "the company paragraph", "cl_bullets":
              "the three bullets", "p4": "the closing", "summary": "the summary",
              "lead": "the lead-in"}

DESIGN_NAMES = ("standard", "classic", "modern", "compact", "spacious")
STYLE_NAMES = ("black", "navy", "burgundy", "forest", "teal", "plum", "slate", "blue")
ORDERS = ("them_first", "me_second", "question_then_me", "me_first")


def _row(p, outputs, label, control, values, state, how, hint, fields=(), model=()):
    """`model`: the values of a mixed row that need writing (L1 "full"); the rest are code."""
    return {"p": p, "outputs": tuple(outputs), "label": label, "control": control,
            "values": tuple(values), "state": state, "how": how, "hint": hint,
            "fields": tuple(fields), "model": tuple(model)}


# One table: the page builds each panel from it (app_model `tweaks`), the chat plans and
# applies from it, and the tests read it. `how` is the writer: design, style, bullets, fill,
# skills, letter_length, contact_person and parts change one output by code; search, pack
# and brief write the person's settings (tools/profile_set.py) and redo what reads them;
# redraft is the chat's own model, both audits after; page is the page's own view.
TWEAKS = (
    _row("R1", ("resume", "letter"), "Look", "choice", DESIGN_NAMES, 1, "design",
         "Changes fonts, margins and where your name sits. Your words stay; one weak bullet "
         "may come off or go on to keep one page."),
    _row("R2", ("resume", "letter"), "Text size", "toggle", ("standard", "larger"), 1, "design",
         "Larger text is easier to read but fits one bullet fewer."),
    _row("R3", ("resume", "letter"), "Spacing", "steps", ("tighter", "standard", "roomier"), 1,
         "design", "Roomier looks calmer and fits fewer bullets."),
    _row("R4", ("resume", "letter"), "Name and dates", "choice",
         ("name-left", "name-centre", "name-right", "dates-left", "dates-right", "rules",
          "no-rules"), 1, "design", "Layout only."),
    _row("R5", ("resume", "letter"), "Colour", "swatches", STYLE_NAMES, 1, "style",
         "Only the colour of your name, headings and bullet marks. Every word stays where it is."),
    _row("R6", ("resume",), "Bullets", "per-bullet", ("another",), 1, "bullets",
         "Swaps in another true bullet from your own history. Nothing is invented."),
    _row("R7", ("resume",), "Amount", "toggle", ("fuller", "space"), 1, "fill",
         "Leaves white space instead of adding bullets. Never fewer than each job's minimum."),
    _row("R9", ("resume",), "Skills line", "steps", ("fewer", "standard", "more"), 1, "skills",
         "How many skills show. Only skills you hold; the posting's own words come first."),
    _row("R8", ("resume",), "Summary words", "chips", ("plainer", "more_formal", "shorter"), 2,
         "redraft", "Rewrites only the summary. It cannot add anything you haven't said.",
         ("summary",)),
    _row("L1", ("letter",), "Length", "steps", ("short", "standard", "full"), 1, "letter_length",
         "Shorter letters get finished. The app keeps letters between 200 and 250 words.",
         ("p1", "lead", "p4"), model=("full",)),
    _row("L2", ("letter",), "Tone", "chips", ("plainer", "more_formal", "warmer"), 2, "redraft",
         "Rewrites the opening, lead-in, bullets and closing in this tone. Facts do not change.",
         ("p1", "lead", "cl_bullets", "p4")),
    _row("L4", ("letter",), "Redo only", "chips", ("p1", "p2", "cl_bullets", "p4"), 2, "redraft",
         "Rewrites just that part and re-checks it."),
    _row("L5", ("letter",), "Addressed to", "text", (), 1, "contact_person",
         "Only a name you or the posting gave."),
    _row("M1", ("message",), "Length", "toggle", ("brief", "standard"), 1, "parts",
         "Brief drops the opening line and the question; the plan's limit always holds."),
    _row("M2", ("message",), "Formality", "steps", ("formal", "standard", "casual"), 1, "parts",
         "Contractions, greeting and exclamation marks only. Facts stay."),
    _row("M3", ("message",), "Opening", "choice", ("usual", "none"), 1, "parts",
         "How the note starts."),
    _row("M4", ("message",), "The ask", "choice", ("another", "pointer"), 1, "parts",
         "How it ends. Asks for a chat, never the job."),
    _row("M5", ("message",), "Order", "choice", ORDERS, 1, "parts",
         "Which sentence comes first."),
    _row("M6", ("message",), "What to include", "toggles",
         ("work_auth:on", "work_auth:off", "about_me:on", "about_me:off"), 1, "parts",
         "Recruiters need your work rights. The words are fixed so they stay true."),
    _row("M8", ("message",), "Mention what you share", "toggle", ("on", "off"), 1, "parts",
         "Names the school or employer you both have. Only one you both have."),
    _row("M7", ("message",), "Another reason, or warmer", "chips",
         ("reason", "question", "warmer"), 2, "redraft",
         "Rewrites that part from what was read about them."),
    _row("J1", ("jobs",), "Minimum score", "choice", ("all", "60", "75"), 0, "page",
         "Below 60 is a long shot."),
    _row("J2", ("jobs",), "Work style", "chips", ("any", "remote", "hybrid", "on-site"), 0, "page",
         "From the place text on each posting; not every posting says."),
    _row("J3", ("jobs",), "How new", "choice", ("any", "3", "7"), 0, "page",
         "Old postings are often closed."),
    _row("J4", ("jobs",), "Pay", "choice", ("any", "stated", "at_target"), 0, "page",
         "Most postings omit pay; omitting it costs a role nothing."),
    _row("J5", ("jobs",), "Sort", "choice", ("match", "newest", "deadline"), 0, "page", ""),
    _row("J6", ("jobs",), "Search window", "choice", ("7", "14", "30"), 2, "search",
         "Longer finds older, more often closed, postings."),
    _row("J7", ("jobs",), "Where", "places", (), 2, "search", "Adds places to search and keep."),
    _row("J8", ("jobs",), "Job titles", "titles", (), 2, "search",
         "A title must also pass the title filter, or it is searched and then dropped."),
    _row("J9", ("jobs",), "Employers to watch", "text", (), 2, "search",
         "Reads its own careers page."),
    _row("J10", ("jobs",), "Job sites", "toggles", (), 2, "search",
         "A site that is off gets no request."),
    _row("J11", ("jobs",), "How wide", "steps", ("quick", "standard", "wide"), 2, "search",
         "Wider reads more pages of each site."),
    _row("J12", ("jobs",), "Pay floor", "number", (), 2, "search",
         "A stated range whose top is below this is flagged; below your cut line it is dropped."),
    _row("I1", ("interview",), "Stage and format", "form",
         ("screen", "behavioural", "technical", "case", "coding", "presentation"), 1, "pack",
         "Which stage this is for, and its format: as assumed, and said so."),
    _row("I2", ("interview",), "How much", "steps", ("one_screen", "standard", "everything"), 1,
         "pack", "The one screen is what you read in the minutes before."),
    _row("I3", ("interview",), "Sections shown", "ticks", (), 1, "pack",
         "Hiding changes what you see, not what is checked."),
    _row("I4", ("interview",), "Answer length", "steps", ("60", "90", "120"), 2, "redraft",
         "The time you will actually have. About 150 words a minute."),
    _row("I5", ("interview",), "Draft answers", "choice", ("1", "3", "5"), 2, "redraft",
         "Marked Draft until you confirm. Written from your profile only."),
    _row("B1", ("brief",), "Length", "steps", ("short", "standard", "long"), 1, "brief",
         "How many owed items it lists."),
    _row("B2", ("brief",), "News items", "choice", ("0", "1", "3", "5"), 1, "brief",
         "Fewer is quicker to read."),
    _row("B3", ("brief",), "What counts", "toggles",
         ("employers", "market", "bank", "targets"), 1, "brief",
         "Which news gets searched. The news on your right to work is always looked for."),
    _row("B4", ("brief",), "Days and time", "schedule", (), 1, "brief",
         "At most once a day."),
    _row("B5", ("brief",), "Parts shown", "ticks", ("since", "next_three", "tip"), 1, "brief",
         "What is owed is always shown."),
    _row("P1", ("page",), "Theme", "choice", ("system", "light", "dark"), 0, "page", ""),
    _row("P2", ("page",), "Text size", "choice", ("small", "standard", "large"), 0, "page", ""),
    _row("P3", ("page",), "Density", "choice", ("comfortable", "compact"), 0, "page", ""),
    _row("P5", ("page",), "Jobs list", "choice", ("to_look_at", "applied"), 0, "page", ""),
)
BY_P = {r["p"]: r for r in TWEAKS}

# TWEAKS.md section 4: what is never offered, as words no row's label, value or hint may
# carry, and settings no value may reach. The tests hold the table to it.
NEVER_WORDS = ("impressive", "bolder", "add numbers", "stronger verbs", "keywords",
               "make it better", "same opening", "core competencies", "mention what i lack",
               "ignore warm", "relax", "hex", "bold", "italic")
NEVER_VALUES = {"R2": ("smaller",), "R3": ()}

# Words typed in the box that mean a row's own value, read by code before any model.
LEXICON = {
    "message": ((r"\b(?:shorter|too long|wordy|too much)\b", "M1", "brief"),
                (r"\bno (?:opener|opening line)\b", "M3", "none")),
    "resume": ((r"\b(?:bigger|larger) (?:text|font|letters)\b", "R2", "larger"),
               (r"\b(?:roomier|less cramped|more space)\b", "R3", "roomier"),
               (r"\b(?:tighter|more compact)\b", "R3", "tighter")),
    "letter": ((r"\b(?:too formal|stiff|stilted|corporate|plainer)\b", "L2", "plainer"),
               (r"\bmore formal\b", "L2", "more_formal"),
               (r"\bwarmer\b", "L2", "warmer")),
}


class Refused(Exception):
    """A tweak that cannot run as asked: said in plain words, nothing changed."""

    def __init__(self, text: str = "", nearest: dict | None = None):
        super().__init__(text)
        # The nearest version that keeps the rule, for the panel to offer in one tap:
        # {"changes": [...], "text": the note it makes, "why": one plain line}.
        self.nearest = nearest


def table(output: str | None = None) -> list[dict]:
    """The rows for one kind of output (all of them with none), as the page reads them."""
    import app_alerts
    out = []
    for r in TWEAKS:
        if output and output not in r["outputs"]:
            continue
        out.append({"p": r["p"], "outputs": list(r["outputs"]), "label": r["label"],
                    "control": r["control"], "values": list(r["values"]),
                    "state": r["state"], "cost": app_alerts.COSTS[r["state"]],
                    "code": r["how"] != "redraft", "page_only": r["how"] == "page",
                    "model_values": list(r["model"]), "hint": r["hint"]})
    return out


# ------------------------------------------------------------------ reading the work item


def read_work(path: str) -> dict:
    """The work item as the database dump holds it, in any of its shapes."""
    with open(path, encoding="utf-8") as fh:
        got = json.load(fh)
    if isinstance(got, dict) and "data" in got and "kind" not in got:
        got = got["data"]
    if not isinstance(got, dict) or got.get("kind") != "tweak":
        raise Refused("That is not a tweak.")
    return got


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def md5_file(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()
    except OSError:
        return ""


def _wish(text) -> str:
    return " ".join(str(text or "").split())[:WISH_MAX]


def _rules() -> str:
    try:
        import draft_pack
        return draft_pack.rules_hash()
    except Exception:  # noqa: BLE001
        return ""


def key_of(target_id: str, before: str, changes: list, text: str) -> str:
    """The same tweak on the same draft under the same rules is the same key (5.3)."""
    return hashlib.sha1(_canon({"t": target_id, "d": before,
                                "c": sorted(_canon(c) for c in changes),
                                "w": _wish(text).lower(), "r": _rules()}).encode()).hexdigest()[:10]


# ------------------------------------------------------------------ what the tweak is on


def resolve(work: dict) -> dict:
    """{output, item, folder, file}: the page's item this tweak is on, as it stands now."""
    import app_model
    args = work.get("args") or {}
    target = args.get("target") or {}
    tid, output = str(target.get("id") or ""), str(target.get("output") or "")
    if output == "page":
        return {"output": output, "item": {"id": tid}, "folder": "", "file": ""}
    if output in ("jobs", "brief"):
        # The person's search and brief settings: the record of what was changed and how to
        # take it back lives beside the rounds and the briefs.
        folder = person.state("documents", "rounds" if output == "jobs" else "briefs")
        os.makedirs(folder, exist_ok=True)
        return {"output": output, "item": {"id": tid or output}, "folder": folder, "file": ""}
    if output == "interview":
        model, targets = app_model.build(only={"interviews"})
        item = next((i for i in model.get("interviews") or [] if i["id"] == tid), None)
        if item is None:
            raise Refused("That interview is no longer on your page.")
        import outreach
        folder = outreach.app_folder(item["company"], item["role"])
        os.makedirs(folder, exist_ok=True)
        return {"output": output, "item": item, "folder": folder,
                "file": os.path.join(folder, "interview_prep.md")}
    if output in ("resume", "letter"):
        model, _ = app_model.build(only={"ready"})
        item = next((i for i in model.get("ready") or [] if i["id"] == tid), None)
        if item is None:
            raise Refused("That draft is no longer on your page.")
        if item["status"] != "drafted":
            raise Refused("This one has gone already, so it stays as it was sent. Make a copy "
                          "for another role instead.")
        folder = person.state("documents", "applications", item["slug"])
        path = os.path.join(folder, "draft.json")
        if not item["slug"] or not os.path.isfile(path):
            raise Refused("This draft has no kept draft.json to change: draft it again.")
        return {"output": output, "item": item, "folder": folder, "file": path}
    if output == "message":
        model, _ = app_model.build(only={"messages"})
        item = next((i for i in model.get("messages") or [] if i["id"] == tid), None)
        if item is None:
            raise Refused("That message is no longer waiting to go.")
        folder = person.state("documents", "network", item["contact"])
        return {"output": output, "item": item, "folder": folder,
                "file": os.path.join(folder, "draft.md")}
    raise Refused(f"There is nothing to tweak called {output or 'that'}.")


def check(work: dict, where: dict | None = None) -> list[dict]:
    """The changes, each against the table; a stale target or an unknown value refused."""
    args = work.get("args") or {}
    target = args.get("target") or {}
    output = str(target.get("output") or "")
    changes = [c for c in args.get("changes") or [] if isinstance(c, dict)]
    if not changes and not _wish(args.get("text")) and not args.get("undo"):
        raise Refused("Choose a change.")
    if where is not None and target.get("rev") and where["item"].get("rev") not in (None, "") \
            and str(target["rev"]) != str(where["item"]["rev"]):
        raise Refused("It changed since you saw it: look again.")
    out = []
    for c in changes:
        p, v = str(c.get("p") or ""), c.get("v")
        if p.startswith("custom:"):
            out.append({"p": p, "v": v, "row": {"how": "redraft", "state": 2, "fields": (),
                                                "label": "Your button"}})
            continue
        row = BY_P.get(p)
        if row is None or output not in row["outputs"]:
            raise Refused(f"{p or 'That'} is not a change that can be made here.")
        vals = v if isinstance(v, list) else [v]
        why = _invalid(row, v)
        if why:
            raise Refused(f"{row['label']}: {why}")
        if any(x in NEVER_VALUES.get(p, ()) for x in vals):
            raise Refused(f"{row['label']}: that is never offered.")
        out.append({"p": p, "v": v, "row": row})
    for p, v in _lexicon(output, args.get("text")):
        if not any(c["p"] == p for c in out):
            out.append({"p": p, "v": v, "row": BY_P[p], "from_words": True})
    return out


def _invalid(row: dict, v) -> str:
    """Why `v` is not a value this row takes, or "" when it is."""
    control, values = row["control"], row["values"]
    if control == "per-bullet":
        return "" if isinstance(v, dict) and v.get("swap") else "say which bullet to swap"
    if control == "text":
        ok = isinstance(v, str) and 0 < len(v.strip()) <= 80
        return "" if ok else "give a name" + (", or say the team" if row["p"] == "L5" else "")
    if control in ("places", "titles"):
        if not isinstance(v, dict) or len(v) != 1:
            return "add or remove one at a time"
        (what, val), = v.items()
        if what == "remote" and control == "places":
            return "" if isinstance(val, bool) else "remote is on or off"
        return "" if what in ("add", "remove") and isinstance(val, str) and 1 < len(val) <= 80 \
            else "add or remove one at a time"
    if control == "toggles" and not values:
        return "" if isinstance(v, dict) and v and all(isinstance(x, bool) for x in v.values()) \
            else "say which to turn on or off"
    if control == "toggles":
        if isinstance(v, dict):
            bad = [k for k, x in v.items() if k not in values or not isinstance(x, bool)]
            return "" if v and not bad else f"{', '.join(map(str, bad)) or 'nothing'} cannot be changed here"
    if control == "number":
        return "" if isinstance(v, int) and not isinstance(v, bool) and 1_000 <= v <= 1_000_000 \
            else "give a yearly amount"
    if control == "form":
        if not isinstance(v, dict):
            return "say the stage or the format"
        if v.get("format") and v["format"] not in values:
            return f"{v['format']!r} is not one of the formats"
        return "" if any(v.get(k) for k in ("stage", "date", "with", "format")) else \
            "say the stage or the format"
    if control == "ticks":
        if not isinstance(v, list):
            return "say which to hide"
        allowed = values or _pack_sections()
        bad = [x for x in v if x not in allowed]
        return "" if not bad else f"{', '.join(map(str, bad))} cannot be hidden"
    if control == "schedule":
        if not isinstance(v, dict):
            return "say the days and the time"
        days, at = v.get("days"), str(v.get("time") or "")
        if not (isinstance(days, list) and days and all(d in range(1, 8) for d in days)):
            return "choose at least one day"
        return "" if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", at) else "give a time like 07:40"
    vals = v if isinstance(v, list) else [v]
    if control in ("toggles", "chips") and isinstance(v, dict):
        return "choose from the list"
    return "" if all(x in values for x in vals) else f"{v!r} is not one of the choices"


def _pack_sections() -> tuple:
    try:
        import interview_pack
        return tuple(x for x in interview_pack.SECTIONS if x not in interview_pack.NEVER_HIDDEN)
    except Exception:  # noqa: BLE001
        return ()


def _lexicon(output: str, text) -> list[tuple[str, str]]:
    """The table's own values the person's words name, read by code first (TWEAKS.md 6)."""
    words = _wish(text).lower()
    return [(p, v) for rx, p, v in LEXICON.get(output, ()) if words and re.search(rx, words)]


def _words_left(output: str, text) -> str:
    """The person's words, unless every one of them was a value the table already has."""
    words = _wish(text)
    if not words:
        return ""
    rest = words.lower()
    for rx, _p, _v in LEXICON.get(output, ()):
        rest = re.sub(rx, " ", rest)
    rest = re.sub(r"\b(?:please|make it|a bit|bit|it|the|a|more|less|and|just)\b", " ", rest)
    return words if re.search(r"[a-z]{3,}", rest) else ""


def plan(work: dict, where: dict | None = None) -> dict:
    """{key, state, cost, code_only, rewrites, page_only}: what one Apply will do."""
    import app_alerts
    where = where or resolve(work)
    changes = check(work, where)
    args = work.get("args") or {}
    words = _words_left(where["output"], args.get("text"))
    redraft = words or any(_needs_model(c) for c in changes)
    state = max([2 if _needs_model(c) else c["row"]["state"] for c in changes]
                + ([2] if words else []) + [0])
    fields = sorted({f for c in changes for f in _fields_of(c)})
    page_only = bool(changes) and all(c["row"]["how"] == "page" for c in changes) and not words
    before = md5_file(where["file"]) if where["file"] else _settings_now(changes)
    return {"key": key_of(where["item"].get("id", ""), before,
                          [{"p": c["p"], "v": c["v"]} for c in changes], args.get("text")),
            "state": state, "cost": app_alerts.COSTS[state], "code_only": not redraft,
            "page_only": page_only, "rewrites": fields if not words else ["named by the writer"],
            "words": words, "changes": [{"p": c["p"], "v": c["v"]} for c in changes],
            "before": before}


def _needs_model(c) -> bool:
    row = c["row"]
    return row["how"] == "redraft" or (isinstance(c["v"], str) and c["v"] in row.get("model", ()))


def _fields_of(c) -> list[str]:
    row = c["row"]
    if not _needs_model(c):
        return []
    if c["p"] == "L4":
        return list(c["v"] if isinstance(c["v"], list) else [c["v"]])
    return list(row["fields"])


# ------------------------------------------------------------------ the record of tweaks


def _log_path(where: dict) -> str:
    return os.path.join(where["folder"], TWEAKS_FILE)


def log(where: dict) -> dict:
    try:
        with open(_log_path(where), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_log(where: dict, data: dict) -> None:
    with open(_log_path(where), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def _snapshot(where: dict) -> str:
    """The output as it stands, kept beside it under its md5 (draft.<md5>.json, or the
    note's draft.<md5>.md with its parts), so an undo or a repeat needs no rewriting."""
    m = md5_file(where["file"])
    ext = os.path.splitext(where["file"])[1]
    dst = os.path.join(where["folder"], f"draft.{m}{ext}")
    if m and not os.path.exists(dst):
        shutil.copyfile(where["file"], dst)
    if where["output"] == "message":
        import parts
        src = parts.path(where["item"]["contact"])
        if src and os.path.isfile(src):
            shutil.copyfile(src, os.path.join(where["folder"], f"draft.{m}.parts.json"))
    return m


def _restore(where: dict, m: str) -> bool:
    ext = os.path.splitext(where["file"])[1]
    src = os.path.join(where["folder"], f"draft.{m}{ext}")
    if not os.path.isfile(src):
        return False
    shutil.copyfile(src, where["file"])
    if where["output"] == "message":
        import parts
        sp = os.path.join(where["folder"], f"draft.{m}.parts.json")
        if os.path.isfile(sp):
            shutil.copyfile(sp, parts.path(where["item"]["contact"]))
    return True


# ------------------------------------------------------------------ running the checks


def run_step(step: str, path: str) -> tuple[int, str]:
    """fit (fit_to_page.py) or verify (verify_batch.py) on a kept draft.json. LJS_TWEAK_RENDER
    names another command to run instead (the tests' stand-in for LaTeX)."""
    stand_in = os.environ.get("LJS_TWEAK_RENDER")
    if stand_in:
        # Windows paths carry backslashes, which a POSIX split reads as escapes.
        cmd = [x[1:-1] if len(x) > 1 and x[0] == x[-1] and x[0] in "\"'" else x
               for x in shlex.split(stand_in, posix=os.name != "nt")] + [step, path]
    else:
        cmd = [sys.executable, os.path.join(_HERE, {"fit": "fit_to_page.py",
                                                    "verify": "verify_batch.py"}[step]), path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _render(where: dict) -> tuple[bool, str]:
    code, out = run_step("fit", where["file"])
    if code:
        return False, "It could not be made: " + (out.strip().splitlines() or ["no reason given"])[-1]
    code, out = run_step("verify", where["file"])
    last = (out.strip().splitlines() or [""])[-1]
    if code not in (0, 3):
        return False, "A check failed after the change: " + last
    return True, last


# ------------------------------------------------------------------ the writers


def _design_spec(d: dict) -> dict:
    spec = d.get("design")
    if isinstance(spec, str) and spec:
        return {"name": spec}
    return dict(spec) if isinstance(spec, dict) else {}


def _set_design(d: dict, spec: dict) -> None:
    spec = {k: v for k, v in spec.items() if v is not None}
    if not spec:
        d.pop("design", None)
    elif set(spec) == {"name"}:
        d["design"] = spec["name"]
    else:
        d["design"] = spec
    # fit_to_page shrank the old design to fit; a new look starts from the look itself
    # (TWEAKS.md 9.1), or it is shrunk again for nothing.
    d["design_step"] = 0


def _design(d: dict, p: str, v) -> str:
    import doc_design
    spec = _design_spec(d)
    if p == "R1":
        _set_design(d, {"name": doc_design.check_design(v)})
        return f"the {v} look"
    if p == "R2":
        spec["body_size"] = 12 if v == "larger" else None
        _set_design(d, spec)
        return "larger text" if v == "larger" else "standard text size"
    if p == "R3":
        if v == "standard":
            spec.pop("margin_mm", None)
            spec.pop("line_spread", None)
        else:
            vals, _name, _why = doc_design.choose(dict(d, design_step=0))
            after = doc_design.adjusted(vals, "tighter" if v == "tighter" else "roomier")
            spec["margin_mm"] = after["margin_mm"]
        _set_design(d, spec)
        return f"{v} spacing"
    key, value = doc_design.ADJUST[v]
    spec[key] = value
    if key == "body_font":
        spec["heading_font"] = value
    _set_design(d, spec)
    return v.replace("-", " ")


def _style(d: dict, v) -> str:
    import doc_style
    d["style"] = doc_style.check(v)
    return f"{v} colour"


def _bullets(d: dict, v) -> str:
    """Swap one bullet for the strongest true one from the same employer that is not on the
    page and does not repeat one that is (bullet_library CONFLICTS)."""
    import allocate
    from bullet_library import CONFLICTS, LIB
    old = str(v.get("swap"))
    jobs = d.get("jobs") or []
    job = next((j for j in jobs if old in (j.get("bullets") or [])), None)
    if job is None:
        raise Refused("That bullet is not on this resume.")
    used = {b for j in jobs for b in j.get("bullets") or []}
    rest = [b for b in job["bullets"] if b != old]
    blocked = set()
    for b in rest:
        blocked |= CONFLICTS.get(b, set())
    scores = allocate.bullet_scores(d.get("posting") or d.get("role") or "")
    pool = [b for b in LIB.get(job["employer"], []) if b not in used and b not in blocked
            and not (CONFLICTS.get(b, set()) & set(rest))]
    if not pool:
        raise Refused(f"There is no other true bullet from {job['employer']} to swap in.")
    new = max(pool, key=lambda b: (scores.get(b, 0.0), b))
    job["bullets"] = [new if b == old else b for b in job["bullets"]]
    return f"another bullet from {job['employer']}"


_NAME = re.compile(r"^[^\W\d_][\w .'\-]{0,79}$", re.U)


def _contact(d: dict, v: str) -> str:
    name = " ".join(str(v or "").split())
    if not name or name.lower() in ("the team", "team", "hiring team"):
        d.pop("contact_person", None)
        return "addressed to the team"
    if not _NAME.match(name):
        raise Refused("Give a name, or say the team.")
    d["contact_person"] = name
    return f"addressed to {name}"


def _note_overrides(record: dict, changes: list) -> dict:
    """What changes in the note's parts, by the table's rows."""
    import compose
    args = record.get("args") or {}
    out = {}
    for c in changes:
        p, v = c["p"], c["v"]
        if p == "M1":
            out["shape"] = "brief" if v == "brief" else (
                args.get("shape") if args.get("shape") not in (None, "brief") else "shared")
        elif p == "M3":
            if v == "none":
                out["opener"] = ""
            # "usual": the saved "" is dropped from the parts (_message), so the bank chooses
        elif p == "M4":
            if v == "pointer":
                out["shape"] = "pointer"
            else:
                reader = args.get("reader") or compose.reader_type(
                    args.get("title") or "", args.get("seniority") or "peer",
                    bool(args.get("recruiter")))
                options = [o for o in compose.options("ask", reader, compose.ASK) if o]
                now = args.get("ask") if isinstance(args.get("ask"), str) else \
                    compose.phrase("ask", reader, args.get("variant_key") or "",
                                   fallback=compose.ASK)
                if len(options) < 2:
                    raise Refused("There is no other way to ask for this reader yet.")
                out["ask"] = options[(options.index(now) + 1) % len(options)] \
                    if now in options else options[0]
        elif p == "M5":
            out["order"] = v
        elif p == "M8":
            if v == "off":
                out["common_ground"] = ""
            elif not str(args.get("common_ground") or "").strip():
                ground = _shared_ground(record.get("contact") or "")
                if not ground:
                    raise Refused("Nothing you both have is on record for them: no school or "
                                  "employer in common.")
                out["common_ground"] = ground
        elif p == "M6":
            what, on = str(v).split(":")
            if what == "work_auth":
                out["work_auth"] = on == "on"
            elif on == "off":
                out["about_me"] = ""
            # about_me on: the saved "" is dropped from the parts (_message)
    return out


def _shared_ground(cid: str) -> str:
    """"We were both at <school>" / "We both worked at <employer>", from the contact's own
    route (alumni of the person's school or past employer), or ""."""
    try:
        import state
        c = state.already_contacted(state.load_contacts(person.state("network_contacts.csv")),
                                    contact_id=cid) or {}
    except Exception:  # noqa: BLE001
        return ""
    route = str(c.get("route") or "").lower()
    detail = re.sub(r"\s+alumni$", "", " ".join(str(c.get("route_detail") or "").split()), flags=re.I)
    if not detail:
        return ""
    if route in ("alumni_school", "alumni") and re.search(r"universit|college|school", detail,
                                                          re.I):
        short = re.sub(r"^(?:the )?university of ", "", detail, flags=re.I)
        return f"We were both at {short}"
    if route in ("alumni_employer", "alumni"):
        return f"We both worked at {detail}"
    return ""


def _plain_rule(error: str, record: dict, changes: list) -> str:
    """One plain line for why a note cannot be made as asked."""
    import compose
    args = record.get("args") or {}
    first = (str(args.get("name") or "").split() or ["They"])[0]
    reader = args.get("reader") or compose.reader_type(
        args.get("title") or "", args.get("seniority") or "peer", bool(args.get("recruiter")))
    low = str(error).lower()
    asked = {c["p"]: c["v"] for c in changes}
    if "char" in low or "limit" in low or "long" in low:
        return "That would run over the note's character limit, which LinkedIn holds hard."
    if "stock phrase" in low or "reads_as_generated" in low:
        return ("Said formally, the opening line reads as a stock phrase, so the nearest "
                "version leaves it out.")
    if reader == "peer" and str(asked.get("M6", "")).startswith("work_auth:on"):
        return f"{first} is a peer: a first note to a peer never states your work rights."
    if reader == "peer" and ("job" in low or "hiring" in low or "role" in low or "M4" in asked):
        return (f"{first} is a peer: a first note to a peer never asks about openings or "
                "names the role you want.")
    return "That would break a rule for first notes: " + str(error).split("\n")[0][:160]


def _nearest(cid: str, record: dict, changes: list, error: str):
    """The nearest note the rules allow: the asked changes less the one that breaks a rule,
    or the brief shape when it is the length. Returns a Refused carrying it."""
    import parts
    why = _plain_rule(error, record, changes)
    asked = {c["p"]: c["v"] for c in changes}
    tries = [[c for c in changes if c is not drop] for drop in changes] if len(changes) > 1 \
        else []
    if "M3" not in asked:
        tries.append(list(changes) + [{"p": "M3", "v": "none", "row": BY_P["M3"]}])
    tries.append([dict(c) for c in changes if c["p"] != "M1"] + [{"p": "M1", "v": "brief",
                                                                  "row": BY_P["M1"]}])
    if str(asked.get("M4", "")) == "another" or "M4" in asked:
        tries.append([c for c in changes if c["p"] != "M4"]
                     + [{"p": "M4", "v": "pointer", "row": BY_P["M4"]}])
    for t in tries:
        if not t:
            continue
        try:
            rec = record
            for c in t:
                if c["p"] == "M2":
                    rec = dict(rec, formality=c["v"])
            note, _used = parts.replay(cid, _note_overrides(rec, t), rec)
            problem = _note_problem(str(note), rec)
        except Exception:  # noqa: BLE001
            continue
        if not problem:
            return Refused(why, {"changes": [{"p": c["p"], "v": c["v"]} for c in t],
                                 "text": str(note), "why": why})
    # Nothing nearer keeps the rule: the note as it is, said so.
    return Refused(why, {"changes": [], "text": str(record.get("text") or "") or None,
                         "why": why})


def _note_problem(text: str, record: dict) -> str:
    """The first rule the final words break (the register is applied after the composer
    ran, so its words are checked again), or ""."""
    import compose
    args = record.get("args") or {}
    try:
        found = compose.validate(text, "connection", name=args.get("name") or None,
                                 seniority=args.get("seniority") or "peer",
                                 recruiter=bool(args.get("recruiter")), title=args.get("title")
                                 or "", reader=args.get("reader"), work_auth=args.get("work_auth"),
                                 card_only=bool(args.get("card_only")))
    except Exception as e:  # noqa: BLE001
        return str(e)
    return f"{found[0].rule}: {found[0].text}" if found else ""


def _message(where: dict, changes: list) -> str:
    """The note again from its parts, with the changes, through the composer's own gates and
    reading.py draft, which keeps the new parts beside it. A change that would break a rule
    for first notes (what a peer may be told, the plan's character limit) is refused with
    the nearest version the rules allow, and one plain line saying why."""
    import parts
    cid = where["item"]["contact"]
    record = parts.load(cid, where["item"]["text"])
    if record is None:
        if all(c["p"] == "M2" for c in changes):
            return _message_register(where, changes[-1]["v"])
        raise Refused("NO_PARTS")
    record = dict(record, contact=cid, text=where["item"]["text"])
    try:
        overrides = _note_overrides(record, changes)
    except Refused as e:
        if not any(c["p"] == "M4" for c in changes) or e.nearest:
            raise
        alt = [c for c in changes if c["p"] != "M4"] + [{"p": "M4", "v": "pointer",
                                                        "row": BY_P["M4"]}]
        try:
            note, _u = parts.replay(cid, _note_overrides(record, alt), record)
        except Exception:  # noqa: BLE001
            raise e from None
        if _note_problem(str(note), record):
            raise e from None
        raise Refused(str(e) + " The nearest asks who to speak to instead.",
                      {"changes": [{"p": c["p"], "v": c["v"]} for c in alt],
                       "text": str(note), "why": "Ask who to speak to instead."}) from None
    for c in changes:
        if c["p"] == "M2":
            record = dict(record, formality=c["v"])
    # Back to the usual: the part the note was made without goes, and the composer's own
    # default chooses it again.
    drop = {k for c in changes for k, hit in (("opener", c["p"] == "M3" and c["v"] == "usual"),
                                              ("about_me", c["p"] == "M6" and c["v"] == "about_me:on"))
            if hit and record["args"].get(k) == ""}
    if drop:
        record = dict(record, args={k: v for k, v in record["args"].items() if k not in drop})
    try:
        note, _used = parts.replay(cid, overrides, record)
        problem = _note_problem(str(note), record)
    except Exception as e:  # noqa: BLE001  the composer's own refusal, in its words
        problem = str(e)
    if problem:
        raise _nearest(cid, record, changes, problem)
    tmp = os.path.join(where["folder"], ".tweak_note.txt")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(str(note) + "\n")
    # The note keeps the standing it was written with: written from the card alone, or
    # waiting on a read of their page (reading.py draft holds it to the same rules again).
    import reading
    flags = (["--card-only"] if reading.card_only_draft(cid) else
             ["--wait-for-read"] if where["item"].get("hold") else [])
    try:
        r = subprocess.run([sys.executable, os.path.join(_HERE, "network", "reading.py"), "draft",
                            cid, tmp, *flags], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if r.returncode:
        raise Refused("The note was refused: " + ((r.stdout + r.stderr).strip().splitlines()
                                                    or ["no reason given"])[-1])
    return "the note written again from its parts"


def message_gate(text: str, mtype: str, cid: str) -> tuple[list, list]:
    """(findings that stop it, warnings left standing in plain words) for any message, as
    every draft gets them before it is shown: compose.validate (the person's never-say
    phrases among its checks, tone.py) and compose.advise (followup_drafts.gate)."""
    import app_model
    import followup_drafts
    import state
    c = state.already_contacted(state.load_contacts(person.state("network_contacts.csv")),
                                contact_id=cid) or {}
    found, _warned = followup_drafts.gate(text, app_model.COMPOSE_KIND.get(mtype, "reply"),
                                          name=app_model.first_name(c.get("name")),
                                          title=str(c.get("title") or ""),
                                          company=str(c.get("company") or ""), contact=cid)
    return found, app_model.message_warnings(text, mtype, c)


def _message_register(where: dict, level: str) -> str:
    """Formality (M2) on any message, by code: an InMail, an email, a reply, a follow-up, a
    referral ask or a thank-you, its subject kept. The words go through the gate again and
    the plan's limit holds: over it, the register is refused, never cut."""
    import advice
    import state
    item = where["item"]
    raw = open(where["file"], encoding="utf-8").read()
    subject, body = state.split_subject(item.get("text") or "")
    body = body.strip()
    new = advice.formality(body, level)
    if new == body:
        raise Refused("It reads that way already.")
    limit = item.get("limit")
    if limit and len(new) > limit:
        raise Refused(f"That would run the message to {len(new)} characters, over its "
                      f"{limit}: it stays as it is.", {"changes": [], "text": body,
                                                       "why": "Over the character limit."})
    found, _w = message_gate(new, item.get("type") or item.get("kind") or "reply",
                             item["contact"])
    if found:
        raise Refused("That would break a rule for this message: " + found[0])
    if body not in raw:
        raise Refused("The draft changed since: look again.")
    with open(where["file"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(raw.replace(body, new, 1))
    return f"the message made {level}"


# ------------------------------------------------------------------ settings: search, prep, brief


def _search_get(key: str, default=None):
    import profile_set
    got = profile_set.get("search.py", key)
    return default if got in (profile_set.MISSING, None) else got


def _location_names() -> tuple[str | None, str | None]:
    """The names of the lists LOCATION reads its metro and its outside places from, so a
    place added to the search is also one the location filter keeps (TWEAKS.md 9.7)."""
    import ast
    try:
        with open(person.path("search.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except OSError:
        return None, None
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LOCATION"
                                             for t in n.targets) and isinstance(n.value, ast.Call):
            kw = {k.arg: k.value for k in n.value.keywords}
            metro, outside = kw.get("metro"), kw.get("outside")
            return (metro.id if isinstance(metro, ast.Name) else None,
                    outside.id if isinstance(outside, ast.Name) else None)
    return None, None


def _writes(c: dict, where: dict, keep: bool) -> tuple[list, list, list]:
    """(writes, then, said) for one settings change: each write ("line", file, key, value)
    or ("json", key, value) or ("routine", key, cron); then, the work to queue after."""
    p, v = c["p"], c["v"]
    search = {"kind": "search", "title": "Finding jobs", "args": {}}
    if p == "J6":
        days = int(v)
        if keep:
            return [("line", "search.py", "JOB_AGE_DAYS", days)], [search], \
                [f"searches look back {days} days from now on"]
        return [], [dict(search, args={"jobage": days})], [f"this search looks back {days} days"]
    if p == "J11":
        pages = {"quick": 1, "standard": None, "wide": 8}[v]
        if keep:
            return [("line", "search.py", "SCRAPE_PAGES", pages)], [search], \
                [f"{v} searches from now on"]
        return [], [dict(search, args={"pages": pages} if pages else {})], [f"a {v} search"]
    if p == "J7":
        (what, val), = v.items()
        places = list(_search_get("SCRAPE_LOCATIONS", []) or [])
        if what == "remote":
            remote = list(_search_get("SCRAPE_REMOTE_LOCATIONS", []) or [])
            home = str(places[-1] if places else "")
            new = (remote or ([home] if home else [])) if val else []
            return [("line", "search.py", "SCRAPE_REMOTE_LOCATIONS", new)], [search], \
                ["remote roles " + ("included" if val else "left out")]
        if what == "add":
            if val in places:
                return [], [], [f"{val} is searched already"]
            out = [("line", "search.py", "SCRAPE_LOCATIONS", places + [val])]
            metro, outside = _location_names()
            town = val.split(",")[0].strip().lower()
            if metro:
                have = list(_search_get(metro, []) or [])
                if town and town not in [str(x).lower() for x in have]:
                    out.append(("line", "search.py", metro, have + [town]))
            if outside:
                left = list(_search_get(outside, []) or [])
                if town in [str(x).lower() for x in left]:
                    out.append(("line", "search.py", outside,
                                [x for x in left if str(x).lower() != town]))
            return out, [search], [f"{val} searched and kept"]
        if val not in places:
            return [], [], [f"{val} is not searched"]
        return [("line", "search.py", "SCRAPE_LOCATIONS", [x for x in places if x != val])], \
            [search], [f"{val} no longer searched"]
    if p == "J8":
        (what, val), = v.items()
        titles = list(_search_get("SCRAPE_QUERIES", []) or [])
        if what == "add":
            keeps = [rx for rx in _search_get("POSITIVE", []) or [] if re.search(rx, val, re.I)]
            if not keeps:
                raise Refused(f"\"{val}\" would be searched and then dropped by your title "
                              "filter: use a title with a word it keeps.")
            if val.lower() in [t.lower() for t in titles]:
                return [], [], [f"\"{val}\" is searched already"]
            return [("line", "search.py", "SCRAPE_QUERIES", titles + [val])], [search], \
                [f"\"{val}\" searched"]
        return [("line", "search.py", "SCRAPE_QUERIES",
                 [t for t in titles if t.lower() != val.lower()])], [search], \
            [f"\"{val}\" no longer searched"]
    if p == "J9":
        name = " ".join(v.split())
        have = list(_search_get("SCRAPE_EMPLOYERS", []) or [])
        out = [] if name.lower() in [str(x).lower() for x in have] else \
            [("line", "search.py", "SCRAPE_EMPLOYERS", have + [name])]
        board = {"kind": "research", "title": f"Find {name}'s own job board",
                 "args": {"topic": "employers", "employer": name}}
        return out, [board, search], [f"{name} watched"]
    if p == "J10":
        import portals as portals_mod
        known = set(getattr(portals_mod, "APP_PORTALS", ()) or ()) | set(_known_portals())
        bad = [k for k in v if known and k not in known]
        if bad:
            raise Refused(f"{', '.join(bad)} is not a job site this search has.")
        now = dict(_search_get("PORTALS", {}) or {})
        now.update(v)
        return [("line", "search.py", "PORTALS", now)], [search], \
            [f"{k} {'on' if on else 'off'}" for k, on in v.items()]
    if p == "J12":
        cut = _search_get("SALARY_CUT_BELOW", 0) or 0
        if v < cut:
            raise Refused(f"That is under your cut line ({cut:,}): a stated range under it is "
                          "dropped already.")
        return [("line", "search.py", "SALARY_FLOOR", int(v))], [search], \
            [f"pay floor {int(v):,}"]
    if p == "I2":
        return [("json", "prep.detail", v)], [], [f"the pack shows {v.replace('_', ' ')}"]
    if p == "I3":
        return [("json", "prep.hide", sorted(set(v)))], [], \
            [("hidden: " + ", ".join(v)) if v else "every section shown"]
    if p == "B1":
        return [("json", "brief.length", v)], [], [f"a {v} brief"]
    if p == "B2":
        return [("json", "brief.news", int(v))], [], [f"{v} news item{'s' if v != '1' else ''}"]
    if p == "B3":
        import brief
        off = set(brief.setting("leave_out"))
        for group, on in v.items():
            (off.discard if on else off.add)(group)
        return [("json", "brief.leave_out", sorted(off))], [], \
            [f"{g} news {'on' if on else 'off'}" for g, on in v.items()]
    if p == "B5":
        return [("json", "brief.hide", sorted(set(v)))], [], \
            [("hidden from the brief: " + ", ".join(v)) if v else "every part shown"]
    if p == "B4":
        import routines
        days = ",".join(str(d) for d in sorted(set(v["days"])))
        hh, mm = v["time"].split(":")
        try:
            zone = person.home_zone_named(person.directory()) or "UTC"
        except Exception:  # noqa: BLE001
            zone = "UTC"
        cron = f"CRON_TZ={zone} {int(mm)} {int(hh)} * * {days}"
        if not routines.at_most_daily(cron):
            raise Refused("A brief runs at most once a day.")
        return [("routine", "morning_brief", cron)], [], [f"the brief at {v['time']}, days {days}"]
    raise Refused("That is not a setting this can change.")


def _rules_fingerprint() -> str:
    try:
        import exclude
        person.reset()
        return exclude.rules_fingerprint()
    except Exception:  # noqa: BLE001
        return ""


def _lapsed_count() -> int:
    try:
        import exclude
        return sum(len(es) for _g, es in exclude.lapsed())
    except Exception:  # noqa: BLE001
        return 0


def _known_portals() -> list[str]:
    try:
        import portals as portals_mod
        return [str(x.get("name") if isinstance(x, dict) else x) for x in portals_mod.enabled()]
    except Exception:  # noqa: BLE001
        return []


def _now_value(w: tuple):
    import profile_set
    if w[0] == "line":
        return profile_set.get(w[1], w[2])
    if w[0] == "json":
        return profile_set.get_json(w[1])
    return _routine(w[1]).get("cron")


def _settings_now(changes: list) -> str:
    """A hash of what the settings these changes touch hold now (the tweak's "before")."""
    try:
        return hashlib.md5(_canon([[c.get("p"), _canon_safe(c)] for c in changes]).encode()
                           ).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def _canon_safe(c) -> str:
    return _canon({"p": c.get("p"), "v": c.get("v")})


def _routines_path() -> str:
    import app_setup
    return os.path.join(app_setup.profile_dir(), "routines.json")


def _routine(key: str) -> dict:
    try:
        with open(_routines_path(), encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError):
        return {}
    return next((r for r in reg.get("routines") or [] if r.get("key") == key), {})


def _set_routine(key: str, cron: str | None) -> dict:
    with open(_routines_path(), encoding="utf-8") as fh:
        reg = json.load(fh)
    r = next((r for r in reg.get("routines") or [] if r.get("key") == key), None)
    if r is None:
        raise Refused("There is no brief set up yet to change: say \"set up my brief\" in a chat.")
    before = r.get("cron")
    r["cron"] = cron
    with open(_routines_path(), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return {"routine": key, "before": before, "trigger_id": r.get("trigger_id")}


def _write(w: tuple) -> dict:
    import profile_set
    if w[0] == "line":
        return profile_set.set_line(w[1], w[2], w[3])
    if w[0] == "json":
        return profile_set.set_json(w[1], w[2])
    return _set_routine(w[1], w[2])


def _unwrite(rec: dict) -> None:
    import profile_set
    if rec.get("routine"):
        _set_routine(rec["routine"], rec.get("before"))
    else:
        profile_set.undo(rec)


def _pack_again(where: dict, form: dict | None = None) -> tuple[bool, str]:
    """The interview pack built again, with the stage and format the person gave (I1), or
    as it was (I2, I3): interview_pack.py pack --write, the one writer of the pack."""
    cmd = [sys.executable, os.path.join(_HERE, "interview_pack.py"), "pack",
           where["item"]["company"]]
    for k, flag in (("stage", "--stage"), ("date", "--date"), ("with", "--with"),
                    ("format", "--format")):
        if form and form.get(k):
            cmd += [flag, str(form[k])]
    cmd.append("--write")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    last = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return r.returncode == 0, (last[-1] if last else "")


def _apply_settings(work: dict, where: dict, p: dict) -> dict:
    """Search, prep and brief rows: the person's own settings written (profile_set), what
    reads them redone (a search queued, the pack built again, the brief's schedule), and
    every write kept so the tweak can be taken back exactly."""
    keep = bool((work.get("args") or {}).get("keep"))
    changes = [dict(c, row=BY_P[c["p"]]) for c in p["changes"]]
    writes, then, said = [], [], []
    for c in changes:
        if c["p"] == "I1":
            continue
        try:
            w, t, s_ = _writes(c, where, keep)
        except Refused as e:
            return {"status": "refused", "summary": str(e)}
        writes += w
        then += [x for x in t if x not in then]
        said += s_
    if writes and all(_now_value(w) == w[-1] for w in writes) and not any(
            c["p"] in ("I1", "J6", "J11") for c in changes):
        return {"status": "cached", "summary": "Already done: it is as you asked.", "key": p["key"]}
    done = []
    rules_before = _rules_fingerprint()
    try:
        for w in writes:
            done.append(dict(_write(w), after=w[-1], how=list(w[:-1])))
    except Exception as e:  # noqa: BLE001  one write refused: none of them stand
        for rec in reversed(done):
            _unwrite(rec)
        return {"status": "refused", "summary": str(e)}
    out = {"status": "done", "key": p["key"]}
    form = next((c["v"] for c in changes if c["p"] == "I1"), None)
    if where["output"] == "interview":
        ok, line = _pack_again(where, form)
        if not ok:
            for rec in reversed(done):
                _unwrite(rec)
            return {"status": "failed", "summary": "The pack could not be built: " + line}
        said.append("the pack built again" + (f" for the {form.get('format')} stage"
                                               if form and form.get("format") else ""))
    # A change to the screening rules (a place the location filter keeps, a title filter, a
    # pay floor) lapses the rulings made under the old ones: each is looked at again when a
    # search finds it (exclude.py lapsed), and the person is told how many.
    lapsed = _lapsed_count() if rules_before and _rules_fingerprint() != rules_before else 0
    if lapsed:
        said.append(f"{lapsed} earlier ruling{'s' if lapsed != 1 else ''} looked at again "
                    "next search")
    tools = [{"name": "update_trigger", "trigger_id": r["trigger_id"],
              "cron_expression": next(w[2] for w in writes if w[0] == "routine")}
             for r in done if r.get("routine") and r.get("trigger_id")]
    data = log(where)
    data[p["key"]] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "output": where["output"], "changes": p["changes"], "writes": done,
                      "said": said}
    _save_log(where, data)
    out.update(summary="Done: " + "; ".join(said) + ".", then=then, tools=tools,
               undo={"action": "tweak.undo", "value": {"key": p["key"]}})
    return out


# ------------------------------------------------------------------ apply


def _load_draft(where: dict):
    import fit_to_page
    apps, read_in = fit_to_page.load(where["file"])
    return apps, read_in


def _save_draft(where: dict, apps, read_in) -> None:
    import fit_to_page
    fit_to_page.save(where["file"], apps, read_in)


def apply(work: dict, today: dt.date | None = None) -> dict:
    """Do the tweak, or say what needs writing. Returns {status, summary, key, ...}:
    done, cached (already so), needs_model (staged for a redraft), or refused."""
    today = today or dt.date.today()
    try:
        work = _with_buttons(work)
    except Refused as e:
        return {"status": "refused", "summary": str(e)}
    args = work.get("args") or {}
    try:
        where = resolve(work)
        if args.get("undo"):
            return undo(work, where)
        p = plan(work, where)
    except Refused as e:
        return {"status": "refused", "summary": str(e)}
    if p["page_only"]:
        return {"status": "done", "summary": "Changed on your page.", "key": p["key"]}
    words = p["words"]
    if words:
        # The page's box never reaches the chat's hook: held like any reaction said here.
        import learned
        learned.note(words, where["output"])
    now = md5_file(where["file"])
    seen = log(where).get(p["key"])
    same = next((k for k, v in log(where).items() if isinstance(v, dict)
                 and v.get("result_md5") == now and v.get("changes") == p["changes"]
                 and _wish(v.get("words")) == _wish(p["words"])), None)
    if (seen and seen.get("result_md5") == now) or same:
        # The same tweak again on what it made: nothing to do, nothing rendered.
        return {"status": "cached", "summary": "Already done: it is as you asked.",
                "key": same or p["key"]}
    if seen and seen.get("result_md5") and _restore(where, seen["result_md5"]):
        # The same tweak on the same draft before: its kept result back, never written twice.
        ok, line = (_render(where) if where["output"] in ("resume", "letter") else (True, ""))
        status = "done" if ok else "failed"
        return {"status": status, "summary": ("Done again from the kept result, no new "
                                              "writing. " + line).strip() if ok else line,
                "key": p["key"]}
    if not p["code_only"]:
        code = [c for c in p["changes"] if c["p"] in BY_P
                and not _needs_model(dict(c, row=BY_P[c["p"]]))]
        if code and where["output"] == "interview":
            # A pack setting and answers to write in one Apply: the setting first (the pack
            # built again), then the answers staged on the pack as it now stands.
            first = _apply_settings(work, where, dict(p, changes=code, key=p["key"] + "-set"))
            if first["status"] in ("refused", "failed"):
                return first
            p = dict(p, changes=[c for c in p["changes"] if c not in code])
        return stage(work, where, p, today)
    if where["output"] in ("jobs", "brief", "interview"):
        return _apply_settings(work, where, p)
    before = _snapshot(where)
    try:
        said = _apply_code(where, p)
    except Refused as e:
        if str(e) == "NO_PARTS":
            return stage(work, where, p, today, why="This note was not written from its parts, "
                         "so changing it is a rewrite.")
        _restore(where, before)
        got = {"status": "refused", "summary": str(e)}
        if getattr(e, "nearest", None):
            got["nearest"] = e.nearest
        return got
    if where["output"] == "message":
        ok, line = True, ""
    else:
        ok, line = _render(where)
    if not ok:
        _restore(where, before)
        if where["output"] != "message":
            _render(where)
        return {"status": "failed", "summary": line, "key": p["key"]}
    after = _snapshot(where)
    kept, kept_said = keep(work, where, p)
    data = log(where)
    data[p["key"]] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "output": where["output"], "changes": p["changes"], "before_md5": before,
                      "result_md5": after, "said": said, "checks": line, "kept": kept}
    _save_log(where, data)
    return {"status": "done", "summary": "Done: " + "; ".join(said) + "." + (
        f" Kept as your usual: {kept_said}." if kept_said else ""), "key": p["key"],
            "checks": line, "undo": {"action": "tweak.undo", "value": {"key": p["key"]}}}


def _apply_code(where: dict, p: dict) -> list[str]:
    changes = [dict(c, row=BY_P[c["p"]]) for c in p["changes"]]
    if where["output"] == "message":
        return [_message(where, changes)]
    apps, read_in = _load_draft(where)
    d = apps[0]
    said = []
    for c in changes:
        how = c["row"]["how"]
        if how == "design":
            said.append(_design(d, c["p"], c["v"]))
        elif how == "style":
            said.append(_style(d, c["v"]))
        elif how == "bullets":
            said.append(_bullets(d, c["v"]))
        elif how == "contact_person":
            said.append(_contact(d, c["v"]))
        elif how == "fill":
            d["fill"] = c["v"]
            said.append("the page filled" if c["v"] == "fuller" else "some space left")
        elif how == "skills":
            d["skills_max"] = c["v"]
            said.append(f"{c['v']} skills on the line")
        elif how == "letter_length":
            said.append(_letter_length(d, c["v"]))
    _save_draft(where, apps, read_in)
    return said


LETTER_WORDS = {"short": 205, "standard": 230}


def _letter_length(d: dict, v: str) -> str:
    """Shorter by code (fit_to_page trims to the draft's `max_words`, in its own order: the
    bullets, then the close, then the opening, never the company paragraph first); "full"
    is a redraft, never here. A move that cannot exist is refused, not faked."""
    import fit_to_page
    now = fit_to_page.body_words(d) if all(d.get(k) for k in ("p1", "p2", "p4")) else None
    want = LETTER_WORDS[v]
    if now is not None and now <= want and v == "short":
        raise Refused(f"The letter is {now} words already, as short as the app lets a letter go.")
    d["max_words"] = want
    return f"the letter held to about {want} words"


def _scope_path(base: str, scope: str) -> list:
    """Where a kept look or colour goes: the person's own (documents.<base>), a kind of
    employer's, or one employer's, as doc_design and doc_style read them."""
    if scope.startswith("kind:"):
        return ["documents", base + "s", "kinds", scope[5:]]
    if scope.startswith("employer:"):
        return ["documents", base + "s", "employers", scope[9:]]
    return ["documents", base]


def _keep_one(c: dict, where: dict, scope: str) -> tuple[list, list]:
    """(records, setting names) for one change kept: the setting its row names, written so a
    later output starts there; [] for a change no setting holds (a learned rule only)."""
    import profile_set
    p, v = c["p"], c["v"]
    if p in ("R1", "R2", "R3", "R4"):
        path = _scope_path("design", scope)
        old = profile_set.get_json(path)
        d = {"design": None if old == profile_set.MISSING else old}
        _design(d, p, v)
        return [profile_set.set_json(path, d.get("design"))], [" ".join(["person.json"] + path)]
    if p == "R5":
        path = _scope_path("style", scope)
        return [profile_set.set_json(path, v)], [" ".join(["person.json"] + path)]
    if p in ("R7", "R9"):
        key = "documents.fill" if p == "R7" else "documents.skills_max"
        return [profile_set.set_json(key, None if v in ("fuller", "standard") else v)], \
            [f"person.json {key}"]
    if p == "L1" and v in LETTER_WORDS:
        return [profile_set.set_json("documents.letter_words",
                                     None if v == "standard" else LETTER_WORDS[v])], \
            ["person.json documents.letter_words"]
    if p == "M2" and v in ("formal", "casual"):
        voice = dict(profile_set.get("networking.py", "VOICE") or {})
        voice["contractions"] = v == "casual"
        return [profile_set.set_line("networking.py", "VOICE", voice)], ["networking.py VOICE"]
    if p == "M3" and v == "none":
        return [profile_set.set_line("networking.py", "OPENER", "")], ["networking.py OPENER"]
    if p == "M6" and str(v).startswith("work_auth:"):
        import parts
        record = parts.load(where["item"].get("contact", "")) or {}
        reader = (record.get("args") or {}).get("reader") or "peer"
        table = dict(profile_set.get("networking.py", "ELIGIBILITY") or {})
        table[reader] = str(v).endswith(":on")
        return [profile_set.set_line("networking.py", "ELIGIBILITY", table)], \
            ["networking.py ELIGIBILITY"]
    return [], []


def keep(work: dict, where: dict, p: dict) -> tuple[list, str]:
    """"Keep this for next time": each kept change written into the setting its row names
    (person.json documents, networking.py) and recorded as the person's own rule through
    learned.py, so no update changes it. Returns (the records, which undo_keep takes back
    exactly, and the plain line to say). Nothing is kept unless the page asked."""
    want = (work.get("args") or {}).get("keep") or {}
    if not want:
        return [], ""
    import learned
    scope = str(want.get("scope") or "all")
    params = want.get("params")
    records, names, said = [], [], []
    for c in p["changes"]:
        if params and c["p"] not in params or c["p"] not in BY_P:
            continue
        recs, where_to = _keep_one(c, where, scope)
        records += recs
        names += where_to
        said.append(f"{BY_P[c['p']]['label'].lower()} {str(c['v']).replace('_', ' ')}")
    if not said:
        return [], ""
    whom = {"kind:": "for {} employers", "employer:": "for {}"}
    tail = next((f.format(scope.split(":", 1)[1]) for k, f in whom.items()
                 if scope.startswith(k)), "")
    area = "messages" if where["output"] == "message" else "documents"
    entry = learned.record(area, "Kept from the page: " + "; ".join(said),
                           f"Every {where['output']} {tail + ' ' if tail else ''}starts with "
                           + "; ".join(said), applied_to=names, via="page tweak",
                           output=where["output"], answers=False)
    records.append({"learned": len(learned.load()), "rule": entry["rule"]})
    return records, "; ".join(said)


def undo_keep(records: list) -> None:
    """Take a keep back: each setting as it was, and its learned rule retired."""
    import learned
    import profile_set
    for rec in reversed(records or []):
        if rec.get("learned"):
            try:
                learned.retire(int(rec["learned"]))
            except SystemExit:
                pass
        else:
            profile_set.undo(rec)


# ------------------------------------------------------------------ redrafts: both audits


def slug_of(where: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "_", where["item"].get("slug", "x").lower()).strip("_") or "x"


def stage_kept(where: dict, round_dir: str) -> dict:
    """A scratch round holding the kept draft, as `stage_picks.py stage` would have written
    it, so `stage_picks.py audit` and `assemble` run on a redraft exactly as on a new one:
    picks.json (the person's answers kept), the posting behind its fence, the draft, and the
    employer research it was written from."""
    import untrusted
    from company_key import key as company_key
    apps, read_in = _load_draft(where)
    d = dict(apps[0])
    slug = slug_of(where)
    os.makedirs(round_dir, exist_ok=True)
    posting = d.pop("posting", "") or ""
    pfile = os.path.join(round_dir, f"posting_{slug}.md")
    with open(pfile, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(untrusted.fence(posting))
    pick = {"slug": slug, "company": d.get("company", ""), "role": d.get("role", ""),
            "abbr": d.get("abbr", ""), "file": pfile,
            "skills_yes": list(d.get("consented_skills") or []),
            "skills_no": list(d.get("declined_skills") or []), "ask_first": [], "hold": []}
    with open(os.path.join(round_dir, "picks.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump([pick], fh, indent=1, ensure_ascii=False)
    d.pop("posting_from", None)
    with open(os.path.join(round_dir, f"draft_{slug}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)
    research = person.state("company_research", f"{company_key(d.get('company', ''))}.json")
    if os.path.isfile(research):
        shutil.copyfile(research, os.path.join(round_dir, f"research_{slug}.json"))
    return {"slug": slug, "pick": pick, "draft": d}


def packet(d: dict, fields: list[str], p: dict, wish: str) -> dict:
    """What the chat's own model is given to rewrite: only these fields as they stand, their
    claims, the change asked for, the person's rules, and their words fenced."""
    import learned
    import untrusted
    asked = [f"{BY_P[c['p']]['label']}: {c['v']}" for c in p["changes"] if c["p"] in BY_P
             and BY_P[c["p"]]["how"] == "redraft"]
    claims = [c for c in d.get("claim_map") or [] if isinstance(c, dict)
              and (not fields or c.get("field") in fields)]
    rules = "\n".join(x for x in (learned.brief("documents"), learned.brief("voice")) if x)
    return {"fields": {f: d.get(f) for f in (fields or TEXT_FIELDS) if f in d},
            "claim_map": claims, "asked": asked,
            "wish": untrusted.fence_wish(wish) if wish else None, "rules": rules,
            "write": ("Rewrite only these fields, in the draft file named, and their claim_map "
                      "entries; every other field stays word for word. Nothing the profile "
                      "does not hold, no number that is not in it, no skill the person has "
                      "not said yes to; the letter's walls hold (200 to 250 words, three "
                      "one-sentence bullets, no bold or italics). Name the fields you changed "
                      "in fields_changed.")}


# ------------------------------------------------------------------ interview answers (I4, I5)


def _answer_sections(text: str) -> tuple[list, dict]:
    """(every line outside Your answers, {normalised question: the block's lines}) of an
    interview pack, so a redraft of some answers can be held to those answers alone."""
    import interview_pack as ip
    outside, blocks, cur, inside = [], {}, None, False
    for line in str(text or "").splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            inside = m.group(1) == "Your answers"
            cur = None
            outside.append(line)
            continue
        if not inside:
            outside.append(line)
            continue
        q = re.match(r"^### (.*)$", line)
        if q:
            cur = ip.what_works.norm(q.group(1).strip())
            blocks[cur] = [line]
        elif cur is None:
            outside.append(line)
        else:
            blocks[cur].append(line)
    return outside, blocks


def _answers_asked(where: dict, p: dict) -> tuple[list, int]:
    """(the questions to draft or fit, the seconds an answer has): I5 the next N with no
    answer yet, I4 the written answers too long, or far too short, for the time chosen."""
    import interview_pack as ip
    import voice_check
    text = open(where["file"], encoding="utf-8").read()
    blocks = ip.answer_blocks(ip.owned_sections(text).get("Your answers"))
    asked = {c["p"]: c["v"] for c in p["changes"]}
    seconds = int(asked["I4"]) if "I4" in asked else ip.answer_seconds(text)
    budget = voice_check.SPOKEN_WPM * seconds // 60
    out = []
    if "I5" in asked:
        out += [q for q, body in blocks.values()
                if not " ".join(ip.spoken(body)).strip()][:int(asked["I5"])]
    if "I4" in asked:
        for q, body in blocks.values():
            n = len(" ".join(ip.spoken(body)).split())
            if n and (n > budget or n < budget * 0.6) and q not in out:
                out.append(q)
    return out, seconds


def _stage_interview(work: dict, where: dict, p: dict) -> dict:
    """Answers drafted or fitted to a time: the packet for the session's own model, the pack
    kept as it is now, and the steps. Written from the profile only, each draft marked
    Draft until the person confirms it (/interview rule 2)."""
    import learned
    import untrusted
    import voice_check
    if not os.path.isfile(where["file"]):
        return {"status": "refused", "summary": "The pack is not built yet: build it first."}
    questions, seconds = _answers_asked(where, p)
    if not questions:
        return {"status": "cached", "key": p["key"],
                "summary": ("Every answer is written already." if any(
                    c["p"] == "I5" for c in p["changes"]) else
                    f"Every written answer fits {seconds} seconds already.")}
    round_dir = person.state("rounds", f"tweak_{p['key']}")
    os.makedirs(round_dir, exist_ok=True)
    before = _snapshot(where)
    words = voice_check.SPOKEN_WPM * seconds // 60
    drafts = any(c["p"] == "I5" for c in p["changes"])
    pkt = {"file": where["file"], "questions": questions, "seconds": seconds, "words": words,
           "drafts": drafts, "before_md5": before,
           "wish": untrusted.fence_wish(p["words"]) if p["words"] else None,
           "rules": "\n".join(x for x in (learned.brief("interview"), learned.brief("voice"))
                              if x),
           "write": ("Write the answer under each question named, in Your answers, as the "
                     "person would say it: from profile/01-candidate-profile.md and their own "
                     "stories only, \"I\" where the question asks what they did, about "
                     f"{words} words ({seconds} seconds at {voice_check.SPOKEN_WPM} words a "
                     "minute)." + (f" Each starts with the line \"{_draft_mark()}\"." if drafts
                                   else "") + " Nothing else in the file changes.")}
    pfile = os.path.join(round_dir, "packet.json")
    with open(pfile, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkt, fh, indent=1, ensure_ascii=False)
    company = where["item"].get("company", "")
    return {"status": "needs_model", "key": p["key"], "round": round_dir, "packet": pfile,
            "summary": f"{len(questions)} answer{'s' if len(questions) != 1 else ''} to "
                       + ("draft for you to confirm" if drafts else f"fit {seconds} seconds")
                       + ": the session's own model writes them, then the pack's check runs.",
            "steps": [
                f"1. Write the answers {pfile} names into {where['file']}, on this session's "
                "own model (never a smaller one).",
                f"2. python3 tools/interview_pack.py check \"{company}\"",
                f"3. python3 tools/tweak.py merge --work <this item> --round {round_dir}",
            ] + (["The person's words went on the reaction list: record or skip them "
                  "(learned.py record or skip, --via \"page tweak\") before the turn ends."]
                 if p["words"] else [])}


# ------------------------------------------------------------------ a message rewritten (M7, words)


def _reader_rules(cid: str) -> str:
    """What this reader may be told, from compose.READER_TYPES and the person's settings."""
    import compose
    import state
    c = state.already_contacted(state.load_contacts(person.state("network_contacts.csv")),
                                contact_id=cid) or {}
    reader = compose.reader_type(str(c.get("title") or ""))
    said = {"recruiter": "a recruiter: may be told the role wanted and your work rights, and "
                         "asked whether they are hiring or for a referral",
            "decision_maker": "a decision-maker: may be told the role wanted; asked only the "
                              "open ask (anything coming up), never whether they are hiring",
            "peer": "a peer: never told the role wanted or your work rights, never asked "
                    "whether they are hiring or for a referral, unless this message is the "
                    "referral ask after a conversation"}.get(reader, reader)
    return f"The reader is {said}."


def _stage_message(work: dict, where: dict, p: dict, why: str = "") -> dict:
    """A message rewritten by the session's own model, any of the seven kinds: the packet
    holds the words as they stand, what was asked (the person's words fenced), the reader's
    rules, the limit, and the person's own rules and what has worked (learned.py brief
    messages, what_works.py brief messages). merge checks the new words with the same gate
    every draft gets before anything is shown."""
    import learned
    import untrusted
    item = where["item"]
    round_dir = person.state("rounds", f"tweak_{p['key']}")
    os.makedirs(round_dir, exist_ok=True)
    try:
        import state
        import what_works
        c = state.already_contacted(state.load_contacts(person.state("network_contacts.csv")),
                                    contact_id=item.get("contact") or "") or {}
        worked = what_works.brief_messages(
            state.load_contacts(person.state("network_contacts.csv")),
            state.load_threads(person.state("network_threads.csv")),
            route=what_works.route_group(c.get("route")) if c else None,
            channel={"linkedin_note": "connection", "linkedin_message": "message"}.get(
                item.get("channel"), item.get("channel")))
    except Exception:  # noqa: BLE001  what worked is guidance: none is never a stop
        worked = ""
    asked = [f"{BY_P[c['p']]['label']}: {c['v']}" for c in p["changes"] if c["p"] in BY_P]
    pkt = {"contact": item.get("contact"), "type": item.get("type") or item.get("kind"),
           "subject": item.get("subject"), "body": item.get("body") or item.get("text"),
           "limit": item.get("limit"), "asked": asked,
           "wish": untrusted.fence_wish(p["words"]) if p["words"] else None,
           "reader": _reader_rules(item.get("contact") or ""),
           "rules": learned.brief("messages"), "worked": worked if isinstance(worked, str)
           else "", "before_md5": _snapshot(where),
           "write": ("Rewrite the message as asked, in the person's voice, keeping every fact "
                     "it states and adding none the profile and the thread do not hold. Keep "
                     "within the limit (never cut to fit: write it shorter). Write the words "
                     "as they will be pasted into message.txt here, a first line \"Subject: "
                     "...\" only where it has a subject.")}
    pfile = os.path.join(round_dir, "packet.json")
    with open(pfile, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkt, fh, indent=1, ensure_ascii=False)
    return {"status": "needs_model", "key": p["key"], "round": round_dir, "packet": pfile,
            "summary": (why + " " if why else "") + "This needs rewriting: the session's own "
                       "model writes it from the packet, then the message checks run.",
            "steps": [f"1. Write the message from {pfile} into {round_dir}/message.txt, on "
                      "this session's own model, with the networking skill.",
                      f"2. python3 tools/tweak.py merge --work <this item> --round {round_dir}"]
            + (["The person's words went on the reaction list: record or skip them "
                "(learned.py record or skip, --via \"page tweak\") before the turn ends."]
               if p["words"] else []),
            "words": p["words"]}


def _merge_message(work: dict, where: dict, p: dict, round_dir: str) -> dict:
    import state
    try:
        new = open(os.path.join(round_dir, "message.txt"), encoding="utf-8").read().strip()
        pkt = json.load(open(os.path.join(round_dir, "packet.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "refused", "summary": "There is no rewritten message yet."}
    item = where["item"]
    subject, body = state.split_subject(new)
    body = body.strip()
    limit = item.get("limit")
    if limit and len(body) > limit:
        return {"status": "refused", "summary": f"It is {len(body)} characters, over the "
                f"{limit} this message can be: write it shorter (it is never cut)."}
    found, warned = message_gate(body, item.get("type") or item.get("kind") or "reply",
                                 item["contact"])
    if found:
        return {"status": "refused", "summary": "Not fit to show yet: " + "; ".join(found[:3])}
    raw = open(where["file"], encoding="utf-8").read()
    old = item.get("text") or ""
    if md5_file(where["file"]) != pkt.get("before_md5") or old not in raw:
        return {"status": "refused", "summary": "The draft changed since: look again."}
    with open(where["file"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(raw.replace(old, (f"Subject: {subject}\n\n" if subject else "") + body, 1))
    after = _snapshot(where)
    kept, _kept_said = keep(work, where, p)
    data = log(where)
    data[p["key"]] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "output": "message", "changes": p["changes"], "words": p["words"],
                      "before_md5": pkt["before_md5"], "result_md5": after,
                      "said": ["the message rewritten"], "kept": kept}
    _save_log(where, data)
    return {"status": "done", "key": p["key"], "summary": "Done: the message rewritten.",
            "warnings": warned, "undo": {"action": "tweak.undo", "value": {"key": p["key"]}}}


def _draft_mark() -> str:
    import interview_pack as ip
    return ip.DRAFT_MARK


def _merge_interview(work: dict, where: dict, p: dict, round_dir: str) -> dict:
    """The answers the model wrote, held to the packet: only the questions it named
    changed, each fit to say in the time (prep.unsayable), a draft marked as one; anything
    else changed puts the pack back as it was."""
    import interview_pack as ip
    try:
        with open(os.path.join(round_dir, "packet.json"), encoding="utf-8") as fh:
            pkt = json.load(fh)
    except (OSError, ValueError):
        return {"status": "refused", "summary": "There is no packet for this tweak."}
    old = os.path.join(where["folder"], f"draft.{pkt['before_md5']}.md")
    try:
        was = open(old, encoding="utf-8").read()
        now = open(where["file"], encoding="utf-8").read()
    except OSError:
        return {"status": "refused", "summary": "The pack as it was is not kept: nothing to "
                                                "hold the answers to."}
    named = {ip.what_works.norm(q) for q in pkt["questions"]}
    out_was, b_was = _answer_sections(was)
    out_now, b_now = _answer_sections(now)
    moved = [b_was[k][0][4:] for k in b_was if k not in named and b_was[k] != b_now.get(k)]
    if out_was != out_now or moved or set(b_now) - set(b_was):
        _restore(where, pkt["before_md5"])
        return {"status": "refused", "summary": "More changed than was asked"
                + (f" ({', '.join(moved)})" if moved else "") + ": the pack is back as it was."}
    blocks = ip.answer_blocks(ip.owned_sections(now).get("Your answers"))
    problems = []
    for k in named:
        q, body = blocks.get(k, (k, []))
        mine = ip.spoken(body)
        if not " ".join(mine).strip():
            problems.append(f"{q}: not written")
            continue
        problems += [f"{q}: {why}" for why in ip.prep.unsayable(mine, q, pkt["seconds"])]
        if pkt.get("drafts") and not ip.drafted(body):
            problems.append(f"{q}: a draft must start with its Draft line")
    if problems:
        return {"status": "refused", "summary": "Not fit to show yet: " + "; ".join(problems)
                + ". Fix them in the pack and merge again."}
    after = _snapshot(where)
    kept, _kept_said = keep(work, where, p)
    said = [f"{'drafted' if pkt.get('drafts') else 'fitted to ' + str(pkt['seconds']) + ' seconds'}"
            f": {q}" for q in pkt["questions"]]
    data = log(where)
    data[p["key"]] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "output": where["output"], "changes": p["changes"], "words": p["words"],
                      "before_md5": pkt["before_md5"], "result_md5": after, "said": said,
                      "kept": kept}
    _save_log(where, data)
    import shown
    try:
        shown.copy(where["file"])
    except Exception:  # noqa: BLE001  the copy to send is a convenience; the pack is the record
        pass
    return {"status": "done", "key": p["key"],
            "summary": "Done: " + "; ".join(said) + "." + (
                " Each is marked Draft until you confirm it." if pkt.get("drafts") else ""),
            "undo": {"action": "tweak.undo", "value": {"key": p["key"]}}}


def stage(work: dict, where: dict, p: dict, today: dt.date, why: str = "") -> dict:
    """The redraft path: a scratch round and the packet, and the commands in order."""
    if where["output"] == "message":
        return _stage_message(work, where, p, why)
    if where["output"] == "interview":
        return _stage_interview(work, where, p)
    work_id = re.sub(r"[^\w~.-]+", "_", str(work.get("id") or p["key"]))
    round_dir = person.state("rounds", f"tweak_{p['key']}")
    staged = stage_kept(where, round_dir)
    fields = [f for f in p["rewrites"] if f in TEXT_FIELDS]
    pkt = packet(staged["draft"], fields, p, p["words"])
    pfile = os.path.join(round_dir, "packet.json")
    with open(pfile, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkt, fh, indent=1, ensure_ascii=False)
    slug = staged["slug"]
    return {"status": "needs_model", "key": p["key"], "round": round_dir, "packet": pfile,
            "summary": "Some of this needs writing: the session's own model rewrites "
                       + (", ".join(PART_NAMES.get(f, f) for f in fields) or
                          "what the person's words ask for") + ", then both audits run.",
            "steps": [
                f"1. Rewrite the fields in {round_dir}/draft_{slug}.json from {pfile}, on this "
                "session's own model (never a smaller one).",
                f"2. The model audit of that draft: the grounding-auditor, writing "
                f"{round_dir}/model_audit_{slug}.json.",
                f"3. python3 tools/stage_picks.py audit {round_dir}",
                f"4. python3 tools/stage_picks.py assemble {round_dir}",
                f"5. python3 tools/tweak.py merge --work <this item> --round {round_dir}",
            ] + (["The person's words went on the reaction list: record or skip them "
                  "(learned.py record or skip, --via \"page tweak\") before the turn ends."]
                 if p["words"] else []),
            "work": work_id}


def merge(work: dict, round_dir: str, today: dt.date | None = None) -> dict:
    """The audited redraft back into the kept draft: only the fields the tweak named may
    have changed; then the note is rebuilt, the documents made and checked, and the result
    kept under the tweak's key, so the same request is never written again."""
    today = today or dt.date.today()
    try:
        where = resolve(work)
        p = plan(work, where)
    except Refused as e:
        return {"status": "refused", "summary": str(e)}
    if where["output"] == "interview":
        return _merge_interview(work, where, p, round_dir)
    if where["output"] == "message":
        return _merge_message(work, where, p, round_dir)
    try:
        with open(os.path.join(round_dir, "drafts.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {"status": "refused", "summary": "There is no assembled draft: the audits have "
                                                "not both passed."}
    if not got:
        return {"status": "refused", "summary": "The audits did not pass it."}
    a = got[0]
    apps, _read_in = _load_draft(where)
    old = apps[0]
    allowed = set(p["rewrites"]) if p["rewrites"] != ["named by the writer"] else set(TEXT_FIELDS)
    moved = [f for f in TEXT_FIELDS if f not in allowed and old.get(f) != a.get(f)]
    if moved:
        return {"status": "refused", "summary": "More changed than was asked ("
                + ", ".join(PART_NAMES.get(f, f) for f in moved) + "): nothing was kept."}
    before = _snapshot(where)
    import outreach
    outreach.write(dict(a), {}, today.isoformat())
    ok, line = _render(where)
    if not ok:
        _restore(where, before)
        _render(where)
        return {"status": "failed", "summary": line, "key": p["key"]}
    after = _snapshot(where)
    kept, _kept_said = keep(work, where, p)
    data = log(where)
    data[p["key"]] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "kept": kept,
                      "output": where["output"], "changes": p["changes"], "words": p["words"],
                      "before_md5": before, "result_md5": after,
                      "fields": {f: a.get(f) for f in allowed if f in a},
                      "said": [f"rewrote {PART_NAMES.get(f, f)}" for f in sorted(allowed)
                               if old.get(f) != a.get(f)], "checks": line}
    _save_log(where, data)
    return {"status": "done", "summary": "Done: " + ("; ".join(data[p["key"]]["said"]) or
                                                     "nothing needed changing") + ".",
            "key": p["key"], "checks": line,
            "undo": {"action": "tweak.undo", "value": {"key": p["key"]}}}


def undo(work: dict, where: dict | None = None) -> dict:
    """The output as it was before a tweak, while nothing else has changed it since."""
    where = where or resolve(work)
    key = str((work.get("args") or {}).get("undo") or "")
    rec = log(where).get(key)
    if not rec:
        return {"status": "refused", "summary": "There is nothing to undo there."}
    if rec.get("writes") is not None:
        # A settings tweak: each setting back as it was, while each still holds what the
        # tweak wrote (anything changed since is the person's, and stays).
        if any(_now_value(tuple(r["how"]) + (None,)) != r["after"] for r in rec["writes"]):
            return {"status": "refused", "summary": "It has changed since: say what you want "
                                                    "in a chat."}
        for r in reversed(rec["writes"]):
            _unwrite(r)
        line = ""
        if where["output"] == "interview":
            _ok, line = _pack_again(where)
        undo_keep(rec.get("kept") or [])
        rec["undone"] = True
        data = log(where)
        data[key] = rec
        _save_log(where, data)
        return {"status": "done", "summary": "Back as it was.", "key": key,
                "tools": [{"name": "update_trigger", "trigger_id": r["trigger_id"],
                           "cron_expression": r["before"]} for r in rec["writes"]
                          if r.get("routine") and r.get("trigger_id")]}
    if md5_file(where["file"]) != rec.get("result_md5"):
        return {"status": "refused", "summary": "It has changed since: say what you want in a chat."}
    if not _restore(where, rec["before_md5"]):
        return {"status": "refused", "summary": "The version before is not kept: say what you "
                                                "want in a chat."}
    undo_keep(rec.get("kept") or [])
    ok, line = (_render(where) if where["output"] in ("resume", "letter") else (True, ""))
    if not ok:
        _restore(where, rec["result_md5"])
        return {"status": "failed", "summary": line}
    return {"status": "done", "summary": "Back as it was.", "key": key}


# ------------------------------------------------------------------ the person's own buttons


def _buttons_path() -> str:
    import app_setup
    return os.path.join(app_setup.profile_dir(), BUTTONS_FILE)


def buttons() -> list[dict]:
    try:
        with open(_buttons_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        rows = got.get("buttons") if isinstance(got, dict) else None
        return [b for b in rows or [] if isinstance(b, dict)]
    except (OSError, ValueError):
        return []


def _overlap(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def promote(today: dt.date | None = None) -> list[dict]:
    """What the person typed into the Tweak box three times in 90 days about one kind of
    output, grouped by its words (learned.content_words), as an offer: a table value they keep
    choosing becomes their usual; anything else, a button of their own. Code, no model."""
    import learned
    today = today or dt.date.today()
    data = learned.file_data()
    said = [r for r in list(data.get("entries") or []) + list(data.get("skipped") or [])
            if isinstance(r, dict) and r.get("via") == "page tweak"]
    have = {(b.get("text") or "").lower() for b in buttons()}
    groups: list[dict] = []
    for r in said:
        try:
            day = dt.date.fromisoformat(str(r.get("date") or "")[:10])
        except ValueError:
            continue
        if (today - day).days > PROMOTE_DAYS:
            continue
        words = learned.content_words(r.get("said"))
        out = str(r.get("output") or "")
        # Words that name a table value group by that value ("shorter please", "still too
        # long"); anything else by the words they share.
        mapped = (_lexicon(out, r.get("said")) or [None])[0]
        g = next((g for g in groups if g["output"] == out and (
            (mapped and g["mapped"] == mapped) or
            (not mapped and not g["mapped"] and _overlap(g["words"], words) >= OVERLAP))), None)
        if g is None:
            g = {"output": out, "words": set(words), "said": [], "last": day, "mapped": mapped}
            groups.append(g)
        g["said"].append(str(r.get("said") or ""))
        g["words"] |= words
        g["last"] = max(g["last"], day)
    offers = []
    no = declined()
    for g in groups:
        if len(g["said"]) < PROMOTE_AFTER:
            continue
        text = g["said"][-1]
        if text.lower() in have:
            continue
        if g["mapped"]:
            p, v = g["mapped"]
            oid = _offer_id("usual", g["output"], p, v)
            if _declined_lately(no.get(oid), today):
                continue
            offers.append({"id": oid, "kind": "usual", "output": g["output"], "p": p, "v": v,
                           "times": len(g["said"]),
                           "line": f"You ask for {BY_P[p]['label'].lower()}: {v.replace('_', ' ')} "
                                   "a lot. Make it your usual?"})
        else:
            label = " ".join(w.capitalize() for w in
                             [w for w in re.findall(r"[a-z']+", text.lower())
                              if w in g["words"]][:3]) or "My tweak"
            oid = _offer_id("button", g["output"], text.lower())
            if _declined_lately(no.get(oid), today):
                continue
            offers.append({"id": oid, "kind": "button", "output": g["output"], "label": label,
                           "text": text, "times": len(g["said"]),
                           "line": f"Add a button for \"{text[:60]}\"?"})
    return offers


REASK_DAYS = 30


def _offer_id(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


def _declined_lately(day, today: dt.date) -> bool:
    """A No is for now, never for ever: it comes back after REASK_DAYS (the app's rule)."""
    try:
        return (today - dt.date.fromisoformat(str(day)[:10])).days < REASK_DAYS
    except ValueError:
        return False


def _buttons_data() -> dict:
    try:
        with open(_buttons_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_buttons_data(data: dict) -> None:
    path = _buttons_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def declined() -> dict:
    got = _buttons_data().get("declined")
    return got if isinstance(got, dict) else {}


def offer(oid: str, today: dt.date | None = None) -> dict | None:
    return next((o for o in promote(today) if o["id"] == oid), None)


def answer_offer(o: dict, yes: bool, today: dt.date | None = None) -> dict:
    """The person's answer to an offer. Yes to a usual keeps it like any "Keep this for next
    time" (the setting its row names, and a learned rule); yes to a button adds it; no is
    kept with its day, and the offer comes back after REASK_DAYS. Returns what undo_offer
    takes back."""
    today = today or dt.date.today()
    if not yes:
        data = _buttons_data()
        before = (data.get("declined") or {}).get(o["id"])
        data.setdefault("declined", {})[o["id"]] = today.isoformat()
        _save_buttons_data(data)
        return {"declined": o["id"], "before": before}
    if o["kind"] == "button":
        row = add_button(o, today)
        return {"button": row["id"]}
    where = {"output": o["output"], "item": {}}
    records, said = keep({"args": {"keep": {"scope": "all"}}}, where,
                         {"changes": [{"p": o["p"], "v": o["v"]}]})
    return {"kept": records, "said": said}


def undo_offer(rec: dict) -> None:
    data = _buttons_data()
    if rec.get("declined"):
        if rec.get("before"):
            data.setdefault("declined", {})[rec["declined"]] = rec["before"]
        else:
            (data.get("declined") or {}).pop(rec["declined"], None)
        _save_buttons_data(data)
    elif rec.get("button"):
        data["buttons"] = [b for b in data.get("buttons") or [] if b.get("id") != rec["button"]]
        _save_buttons_data(data)
    else:
        undo_keep(rec.get("kept") or [])


def add_button(offer: dict, today: dt.date | None = None) -> dict:
    """The person said yes: their words as a button on that kind of output, replayed
    through the same fence each time. At most two a kind: the oldest goes."""
    today = today or dt.date.today()
    rows = buttons()
    mine = [b for b in rows if offer["output"] in (b.get("kinds") or [])]
    if len(mine) >= BUTTONS_PER_KIND:
        oldest = min(mine, key=lambda b: str(b.get("added") or ""))
        rows = [b for b in rows if b is not oldest]
    bid = hashlib.sha1((offer["output"] + offer["text"].lower()).encode()).hexdigest()[:8]
    row = {"id": bid, "label": offer["label"], "kinds": [offer["output"]], "text": offer["text"],
           "area": "documents" if offer["output"] in ("resume", "letter") else "messages",
           "state": 2, "added": today.isoformat()}
    rows = [b for b in rows if b.get("id") != bid] + [row]
    data = _buttons_data()
    data["buttons"] = rows
    _save_buttons_data(data)
    return row


def custom_words(p: str) -> str:
    """A button's saved words (p "custom:<id>"), replayed as the person's own words."""
    bid = p.split(":", 1)[1] if ":" in p else ""
    got = next((b for b in buttons() if b.get("id") == bid), None)
    if got is None:
        raise Refused("That button is no longer there.")
    return str(got.get("text") or "")


# ------------------------------------------------------------------ what the panel opens on


def hints() -> dict:
    """{"tweak": shown}: the one-time Tweak hint, seen once on any device (profile/tips.json
    page_hints), and never shown to someone who turned tips off."""
    try:
        import tips
        state = tips.load()
    except Exception:  # noqa: BLE001
        return {"tweak": False}
    seen = bool((state.get("page_hints") or {}).get("tweak")) or bool(state.get("off"))
    return {"tweak": seen}


def hint_seen(name: str, day: dt.date) -> str | None:
    """Record a page hint as seen; returns what was there before (None for nothing)."""
    import tips
    state = tips.load()
    hints_ = dict(state.get("page_hints") or {})
    before = hints_.get(name)
    hints_[name] = day.isoformat()
    state["page_hints"] = hints_
    tips.save(state)
    return before


def usual() -> dict:
    """{output: {p: value}}: what each panel opens on as "Your usual", read from the settings
    themselves (never a copy), so a setting changed by hand shows too."""
    import profile_set
    out: dict = {"resume": {}, "letter": {}, "message": {}, "jobs": {}, "brief": {},
                 "interview": {}}

    def j(key, default=None):
        got = profile_set.get_json(key)
        return default if got == profile_set.MISSING else got
    design = j("documents.design")
    if isinstance(design, str):
        out["resume"]["R1"] = out["letter"]["R1"] = design
    elif isinstance(design, dict) and design.get("name"):
        out["resume"]["R1"] = out["letter"]["R1"] = design["name"]
    if isinstance(design, dict) and design.get("body_size") == 12:
        out["resume"]["R2"] = out["letter"]["R2"] = "larger"
    for p, key in (("R5", "documents.style"), ("R7", "documents.fill"),
                   ("R9", "documents.skills_max")):
        got = j(key)
        if got:
            out["resume"][p] = got
            if p == "R5":
                out["letter"][p] = got
    words = j("documents.letter_words")
    if words:
        out["letter"]["L1"] = next((k for k, n in LETTER_WORDS.items() if n == words), "standard")
    for p, key in (("B1", "brief.length"), ("B2", "brief.news"), ("I2", "prep.detail")):
        got = j(key)
        if got not in (None, ""):
            out["brief" if p.startswith("B") else "interview"][p] = str(got)
    age = _search_get("JOB_AGE_DAYS")
    if age:
        out["jobs"]["J6"] = str(age)
    pages = _search_get("SCRAPE_PAGES")
    if pages:
        out["jobs"]["J11"] = {1: "quick", 8: "wide"}.get(pages, "standard")
    floor = _search_get("SALARY_FLOOR")
    if floor:
        out["jobs"]["J12"] = floor
    voice = profile_set.get("networking.py", "VOICE")
    if isinstance(voice, dict) and "contractions" in voice:
        out["message"]["M2"] = "casual" if voice["contractions"] else "standard"
    if profile_set.get("networking.py", "OPENER") == "":
        out["message"]["M3"] = "none"
    return {k: v for k, v in out.items() if v}


def rules() -> dict:
    """{output: [the person's own active rules for it]}: the "Your usual" lines a panel opens
    on, from learned.py, newest first, at most three a kind."""
    import learned
    areas = {"resume": "documents", "letter": "documents", "message": "messages",
             "jobs": "search", "interview": "interview", "brief": "other"}
    out = {}
    try:
        over = learned.superseded()
        rows = [r for r in learned.load() if r.get("status", "active") == "active"
                and not over.get(learned.entry_key(r))]
    except Exception:  # noqa: BLE001
        return {}
    for output, area in areas.items():
        got = [{"rule": r["rule"], "since": r.get("date")} for r in reversed(rows)
               if r.get("area") == area and (not r.get("output") or r.get("output") == output)]
        if got:
            out[output] = got[:3]
    return out


# ------------------------------------------------------------------ the command


def merge_works(works: list[dict]) -> dict:
    """Several tweaks queued on one output, as one (app.py next claims them together): the
    changes in the order asked, a later choice for the same row replacing an earlier one,
    the person's words joined, any keep kept. One wake, one render, one audit."""
    if len(works) == 1:
        return works[0]
    targets = {str(((w.get("args") or {}).get("target") or {}).get("id") or "") for w in works}
    if len(targets) != 1:
        raise Refused("Those are tweaks to different things: each runs on its own.")
    changes: dict = {}
    words, keep = [], {}
    for w in works:
        a = w.get("args") or {}
        for c in a.get("changes") or []:
            if isinstance(c, dict):
                changes[str(c.get("p"))] = c
        if _wish(a.get("text")):
            words.append(_wish(a.get("text")))
        keep = a.get("keep") or keep
    first = works[0]
    args = dict(first.get("args") or {}, changes=list(changes.values()),
                text=" ".join(words) or None, keep=keep or None)
    args["target"] = dict((works[-1].get("args") or {}).get("target") or {})
    return dict(first, args=args)


def _with_buttons(work: dict) -> dict:
    """A custom button's change, as the person's own words (5.3: the same words each time)."""
    args = dict(work.get("args") or {})
    custom = [c for c in args.get("changes") or [] if str(c.get("p") or "").startswith("custom:")]
    if custom:
        words = " ".join(custom_words(c["p"]) for c in custom)
        args["text"] = " ".join(x for x in (args.get("text"), words) if x)
        args["changes"] = [c for c in args.get("changes") or [] if c not in custom]
    return dict(work, args=args)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("table")
    t.add_argument("output", nargs="?")
    for name in ("plan", "apply", "undo"):
        s = sub.add_parser(name)
        s.add_argument("--work", required=True, action="append",
                       help="the work item; give it again for each tweak claimed with it")
    m = sub.add_parser("merge")
    m.add_argument("--work", required=True, action="append")
    m.add_argument("--round", required=True)
    pr = sub.add_parser("promote")
    pr.add_argument("--add", type=int, default=0, help="add offer N (from 1) as a button")
    pr.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "table":
        print(json.dumps(table(a.output), indent=1, ensure_ascii=False))
        return 0
    if a.cmd == "promote":
        today = dt.date.fromisoformat(a.today) if a.today else None
        offers = promote(today)
        if a.add:
            if not 1 <= a.add <= len(offers) or offers[a.add - 1]["kind"] != "button":
                print("tweak: no button offer with that number")
                return 2
            print(json.dumps(add_button(offers[a.add - 1], today), ensure_ascii=False))
            return 0
        print(json.dumps(offers, indent=1, ensure_ascii=False))
        return 0
    try:
        work = _with_buttons(merge_works([read_work(w) for w in a.work]))
    except (OSError, ValueError, Refused) as e:
        print(json.dumps({"status": "refused", "summary": str(e)}))
        return 1
    if a.cmd == "plan":
        try:
            got = plan(work)
        except Refused as e:
            got = {"status": "refused", "summary": str(e)}
    elif a.cmd == "apply":
        got = apply(work)
    elif a.cmd == "merge":
        got = merge(work, a.round)
    else:
        got = undo(work)
    print(json.dumps(got, indent=1, ensure_ascii=False))
    return 0 if got.get("status") not in ("refused", "failed") else 1


if __name__ == "__main__":
    sys.exit(main())
