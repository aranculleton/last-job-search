#!/usr/bin/env python3
"""Building a person's work history with them, when they have no resume: one job a message.

Setup's first message offers it ("No resume? Say "build one with me" and I'll make it with
you."), and "build my resume" starts it at any time. The fastest source comes first, and the
questions ask only what that source leaves out:

  1. on their computer, their own LinkedIn page, read in the browser the chat uses (the
     networking skill's reading step, which signs in when it needs to), written as
     own_profile.py's SHAPE and seeded with `seed --paste <that file> --browser`;
  2. else a LinkedIn download already taken (documents/linkedin/, `export.py take`): `seed`;
  3. else, on a computer only, the text of their LinkedIn page pasted, if they want to;
  4. else nothing, and the questions start from the newest job.

Then one message a job, newest first, each asking three things at most: the job itself
(title, employer, town, months), two or three things that mattered with a number where they
have one, and the tools. A job the seed already holds is shown back and asked only for what
it lacks. Then one message for education, certificates (held or still in progress),
languages and anything else. Like JSON Resume's `work` entries (position, name, dates,
highlights) and an interview that asks one question at a time and keeps each answer, as
open-source resume builders do; the "with a number" ask is the measurable-result part of the
X-Y-Z bullet recruiters describe.

A phone chat is never asked for a file, a download or a PDF (LinkedIn's own help says Save
to PDF is not in its mobile app, and nothing confirms a profile can be copied there), and
its first message says they can talk instead of typing (Claude's mobile apps take dictation:
the microphone in the message box). A computer chat, Windows or Mac, has no step outside the
chat. Every message is at most place.SHORT_WORDS words.

Their answers are the source, and nothing is invented: Claude writes each job into
01-candidate-profile.md (`### Title - Employer (dates), City`) and bullets.py in their words,
with no number they did not give, and anything unclear as `[CONFIRM: ...]`.

    python3 tools/history_interview.py seed [<ZIP or folder>] [--paste F [--browser]] [--out seed.json]
    python3 tools/history_interview.py ask --on phone|computer [--seed seed.json] [--done N | --rest]
    python3 tools/history_interview.py walk --on phone|computer [--seed seed.json] [--jobs N]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import place  # noqa: E402

PLACES = ("phone", "computer")
MAX_JOBS = 5          # asked in detail, newest first; older ones are a line each, as given
WORDS = place.SHORT_WORDS
EXAMPLE = '"Shift lead, Riverside Cafe, Leeds, Mar 2022 to now. Trained 6 new starters. Square, Excel."'
THREE = ("1. Title, employer, town, dates\n"
         "2. Two or three things that mattered, with a number if you have one\n"
         "3. Tools you used")
MIC = "Or talk instead: use the microphone in the message box."
PASTE = "Or paste your LinkedIn page's text instead."
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _when(text: str) -> tuple:
    """(year, month) from "Mar 2023", "2023-03", "03/2023" or "2023", for ordering; (0, 0)
    when it says none (a job still held sorts by its start like any other)."""
    t = str(text or "").strip().lower()
    y = re.search(r"\b(19|20)\d{2}\b", t)
    if not y:
        return (0, 0)
    m = re.search(r"\b([a-z]{3})[a-z]*\b", t)
    month = _MONTHS.get(m.group(1), 0) if m else 0
    if not month:
        n = re.search(r"\b(\d{1,2})[/-]" + y.group(0) + r"|" + y.group(0) + r"-(\d{1,2})\b", t)
        month = int(next(g for g in n.groups() if g)) if n else 0
    return (int(y.group(0)), month)


def _span(start: str, end: str) -> str:
    s, e = str(start or "").strip(), str(end or "").strip()
    if not s:
        return e
    return f"{s} to {e or 'now'}"


def seed(src=None, paste: str = "", browser: bool = False) -> dict:
    """What a LinkedIn download (or their page, read or pasted) already says, newest job
    first: {"source", "jobs", "education", "certifications", "skills", "note"}. Empty lists
    when nothing is there; `note` is one plain line when a file was not UTF-8."""
    import export
    import own_profile
    if paste:
        got = own_profile.from_paste(paste, "browser" if browser else "paste")
        note = ""
    else:
        got = own_profile.from_export(src)
        note = export.encoding_line([export.read(k, src) for k in export.GROUPS["profile"]])
    got = got or {}
    jobs = [{"title": str(p.get("title") or "").strip(),
             "employer": str(p.get("company") or "").strip(),
             "place": str(p.get("location") or "").strip(),
             "start": str(p.get("started") or "").strip(),
             "end": str(p.get("finished") or "").strip(),
             "description": str(p.get("description") or "").strip()}
            for p in got.get("positions") or [] if p.get("title") or p.get("company")]
    jobs.sort(key=lambda j: (_when(j["start"]), not j["end"]), reverse=True)
    return {"source": got.get("source", ""), "jobs": jobs,
            "education": got.get("education") or [],
            "certifications": got.get("certifications") or [],
            "skills": got.get("skills") or [], "note": note}


def _job_line(j: dict) -> str:
    town = str(j.get("place") or "").split(",")[0].strip()   # "Leeds, England, United Kingdom"
    bits = [x for x in (j.get("title"), j.get("employer"), town) if x]
    when = _span(j.get("start"), j.get("end"))
    return ", ".join(bits) + (f", {when}" if when else "")


def ask(on: str, done: int = 0, s: dict | None = None, rest: bool = False) -> str:
    """The message to send after `done` jobs are answered (0: the first), or with `rest`
    the last one: education, certificates, languages, anything else. "" when the jobs are
    done and only `rest` is left."""
    if on not in PLACES:
        raise ValueError(f"--on is one of {', '.join(PLACES)}")
    s = s or {}
    jobs = list(s.get("jobs") or [])
    if rest:
        if s.get("education") or s.get("certifications"):
            return ("Last one: anything to add to your education or certificates (say if one "
                    "is still in progress), the languages you speak, and anything else you're "
                    "good at?")
        return ("Last one: where you studied (subject and years), any certificates (say if "
                "one is still in progress), the languages you speak, and anything else "
                "you're good at?")
    if jobs:
        asked = jobs[:MAX_JOBS]
        if done < len(asked):
            j = asked[done]
            head = "I have your jobs from LinkedIn, so just a few questions.\n" if done == 0 else ""
            if j.get("description"):
                q = ("Anything to add, a result with a number if you have one? Or say "
                     "\"fine as it is\".")
            else:
                q = ("Two or three things you did there that mattered, with a number if you "
                     "have one? And the tools you used?")
            out = f"{head}{_job_line(j)}. {q}"
            return out + (f"\n{MIC}" if on == "phone" and done == 0 else "")
        if done == len(asked) and len(jobs) <= MAX_JOBS:
            oldest = asked[-1].get("employer") or "that"
            return (f"Anything before {oldest} worth a line, with the same three things? Or "
                    "say \"that's all\".")
        return ""
    if done == 0:
        tail = MIC if on == "phone" else PASTE
        return f"Let's build it together, newest job first. Your latest:\n{THREE}\nLike: {EXAMPLE}\n{tail}"
    if done < MAX_JOBS:
        return "Thanks. The job before that, the same three things? Or say \"that's all\"."
    return ""


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'.,/&-]*", text))


def walk(on: str, s: dict | None = None, jobs: int = 3) -> list[str]:
    """Every message a person who answers `jobs` jobs is sent, in order."""
    out = []
    for n in range(jobs + 1):
        m = ask(on, n, s)
        if not m:
            break
        out.append(m)
    out.append(ask(on, s=s, rest=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sd = sub.add_parser("seed", help="what a LinkedIn download, or their page, already says")
    sd.add_argument("src", nargs="?", default=None,
                    help="the ZIP or its folder; documents/linkedin/ by default")
    sd.add_argument("--paste", default="", help="their page as own_profile.py SHAPE, written "
                                                "from a read in the browser or a paste")
    sd.add_argument("--browser", action="store_true",
                    help="with --paste: it was read in their browser, not pasted")
    sd.add_argument("--out", default="")
    for name in ("ask", "walk"):
        p = sub.add_parser(name)
        p.add_argument("--on", required=True, choices=PLACES)
        p.add_argument("--seed", default="", help="the file `seed --out` wrote")
        if name == "ask":
            p.add_argument("--done", type=int, default=0, help="jobs answered so far")
            p.add_argument("--rest", action="store_true", help="the last message")
        else:
            p.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    if a.cmd == "seed":
        got = seed(a.src, a.paste, a.browser)
        text = json.dumps(got, indent=1, ensure_ascii=False)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            print(f"seed: {len(got['jobs'])} jobs, {len(got['education'])} places studied, "
                  f"{len(got['certifications'])} certificates, in {a.out}")
        else:
            print(text)
        if got["note"]:
            print(got["note"], file=sys.stderr)
        return 0
    s = None
    if a.seed:
        with open(a.seed, encoding="utf-8") as fh:
            s = json.load(fh)
    if a.cmd == "ask":
        print(ask(a.on, a.done, s, a.rest) or "nothing more about jobs: send `--rest`")
        return 0
    msgs = walk(a.on, s, a.jobs)
    for i, m in enumerate(msgs, 1):
        print(f"--- {i} ({words(m)} words)\n{m}")
    print(f"=== {len(msgs)} messages, {sum(words(m) for m in msgs)} words, "
          f"{datetime.date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
