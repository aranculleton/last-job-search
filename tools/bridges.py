#!/usr/bin/env python3
"""What the candidate actually has that sits next to what a posting asked for.

A posting is a wish list. It names ten tools and the team uses six, and the one
missing item is almost never what decides the hire. The screen was treating them
as bars: a posting docked ten points for the word "LLM" whether it said "build
and deploy LLM applications", "familiarity with LLMs is a plus", or "our
platform uses LLMs". Roles the candidate should obviously have gone for were
scoring below the floor on a word.

This module is the answer to that, and it is the honest one. For anything a
posting asks for, it says which of three things is true:

  HELD      the candidate has it, and the screen should stop treating it as a risk
  BRIDGE    they have something close enough to do the job and to say so out loud
  GAP       they do not have it and nothing here pretends otherwise

A BRIDGE is not a euphemism. "I use Metabase daily and used Superset at my last
employer; they are the same job with different menus" is true, it is what a
hiring manager wants to hear, and it survives the follow-up question. That last
part is why this module exists instead of simply widening the skills inventory:
a claim that does not survive the follow-up question costs more than the
application was worth. A developer who lists Rust gets a Rust question in the
screen.

So the rule the whole file follows: **frame generously, never claim falsely.**
Apply for the role, lead with the adjacent thing, name the gap plainly if asked,
and let the rest of the resume carry the argument.

    from bridges import assess
    assess("Strong Tableau background required")
    # -> [Assessment(asked='Tableau', verdict='bridge', ...)], for a profile whose
    #    BRIDGES say Tableau is bridged from the tool they use now
"""

from __future__ import annotations

import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

# verdicts, strongest first
HELD = "held"
BRIDGE = "bridge"
GAP = "gap"

Assessment = namedtuple("Assessment", "asked verdict have line note")

# ---------------------------------------------------------------------------
# The map is the profile's (skills.py BRIDGES): one entry per capability a
# posting might ask for, with `asked`, the `pattern` a posting spells it with,
# the `verdict`, and for a BRIDGE its `strength`.
#
# `have` is what the candidate genuinely holds that does the same work. `line`
# is how to say it: one sentence, true, and usable in a cover letter, an
# interview answer or a recruiter reply without adjustment. `strength` decides
# how much the screen should still worry: "near" costs almost nothing, "far" is
# a real gap that a good application can still survive.
# ---------------------------------------------------------------------------
MAP = person.module("skills").BRIDGES

_COMPILED = [(re.compile(e["pattern"], re.I), e) for e in MAP]
# What the fit score already knows is not held (search.py FIT_MISSING) is a gap here
# too, wherever the map says nothing about it, so a document is never drafted to
# claim a skill the score is docking the posting for. The gap is named by what the
# posting wrote ("PySpark"), and the entry's reason ("big-data engineering is not
# held") is its note: named by the reason, the pack asked "What is your experience
# with big-data engineering is not held?".
_MISSING = [(rx, why) for rx, _pts, why in
            (getattr(person.module("search"), "FIT_MISSING", None) or ())]


# Tools a field treats as interchangeable. A posting asking for one, from somebody
# who holds another of the same family, is a near bridge in any field: Tableau and
# Power BI, Azure and AWS, Xero and QuickBooks. Only a person's own BRIDGES covered
# this, so a field /setup never wrote one for docked the posting in full and left the
# held tool off the resume. The held tool is what is shown and said; the one asked
# for goes on a document only with the person's yes (unheld_asked, below). A profile adds its field's own in skills.py FAMILIES, same
# shape: (what the family is, (name, pattern), (name, pattern), ...).
FAMILIES = [
    ("dashboard tool", ("Power BI", r"\bpower\s?bi\b"), ("Tableau", r"\btableau\b"),
     ("Looker", r"\blooker\b(?!\s*studio)"), ("Looker Studio", r"\blooker studio\b|\bdata studio\b"),
     ("Qlik", r"\bqlik\w*\b"), ("Metabase", r"\bmetabase\b"), ("Superset", r"(?-i:\bSuperset\b)"),
     ("MicroStrategy", r"\bmicrostrategy\b")),
    ("cloud platform", ("AWS", r"\bAWS\b|\bamazon web services\b"),
     ("Azure", r"\bazure\b(?!\s*(?:sql|data factory|devops|synapse))"),
     ("Google Cloud", r"\bgoogle cloud\b|\bGCP\b")),
    ("cloud data warehouse", ("Snowflake", r"\bsnowflake\b"), ("BigQuery", r"\bbig\s?query\b"),
     ("Redshift", r"\bredshift\b"), ("Synapse", r"\bsynapse\b"), ("Databricks", r"\bdatabricks\b")),
    ("workflow orchestrator", ("Airflow", r"\bairflow\b"), ("Dagster", r"\bdagster\b"),
     ("Prefect", r"(?-i:\bPrefect\b)"), ("Azure Data Factory", r"\bazure data factory\b|\bADF\b")),
    ("spreadsheet", ("Excel", r"(?-i:\bExcel\b)"), ("Google Sheets", r"\bgoogle sheets\b")),
    ("statistics package", ("SAS", r"(?-i:\bSAS\b)"), ("SPSS", r"\bSPSS\b"), ("Stata", r"\bstata\b")),
    ("CRM", ("Salesforce", r"\bsalesforce\b"), ("HubSpot", r"\bhubspot\b"),
     ("Dynamics 365", r"\bdynamics 365\b|\bmicrosoft dynamics\b"), ("Zoho CRM", r"\bzoho\b")),
    ("work tracker", ("Jira", r"\bjira\b"), ("Asana", r"\basana\b"), ("Trello", r"\btrello\b"),
     ("Monday.com", r"\bmonday\.com\b"), ("Azure DevOps", r"\bazure devops\b")),
    ("design tool", ("Figma", r"\bfigma\b"), ("Sketch", r"(?-i:\bSketch\b)"),
     ("Adobe XD", r"\badobe xd\b")),
    ("accounting package", ("Xero", r"\bxero\b"), ("QuickBooks", r"\bquickbooks\b"),
     ("Sage", r"(?-i:\bSage\b)"), ("NetSuite", r"\bnetsuite\b")),
    ("health record system", ("Epic", r"(?-i:\bEpic\b)(?=\s+(?:EHR|EMR|Systems|certif\w*))"),
     ("Cerner", r"\bcerner\b|\boracle health\b"), ("Meditech", r"\bmeditech\b")),
    ("product analytics tool", ("Amplitude", r"(?-i:\bAmplitude\b)"), ("Mixpanel", r"\bmixpanel\b"),
     ("Google Analytics", r"\bgoogle analytics\b|\bGA4\b")),
    ("code host", ("GitHub", r"\bgithub\b"), ("GitLab", r"\bgitlab\b"), ("Bitbucket", r"\bbitbucket\b")),
]
_SKILLS = person.module("skills")
FAMILIES = FAMILIES + [tuple(f) for f in getattr(_SKILLS, "FAMILIES", None) or ()]


def _merged(families) -> list:
    """Families of one name as one family: a profile's "CRM" from its field's market table
    and the app's own "CRM" are the same kind of tool, so a tool in either bridges to a tool
    in the other, and a tool both name is assessed once, not twice (2026-10-25)."""
    out: dict[str, list] = {}
    for fam, *members in families:
        have = out.setdefault(str(fam).casefold(), [fam])
        names = {str(m[0]).casefold() for m in have[1:]}
        have += [m for m in members if str(m[0]).casefold() not in names]
    return [tuple(f) for f in out.values()]


FAMILIES = _merged(FAMILIES)
_FAMILY_RX = [(fam, [(name, re.compile(pat, re.I)) for name, pat in members])
              for fam, *members in FAMILIES]
# What the person holds: the skills inventory, the list a resume may claim from.
_HELD_RX = [(item, re.compile(pat, re.I)) for _cat, item, pat in getattr(_SKILLS, "ITEMS", ())]


def _held(name: str) -> list:
    """The inventory items that are this tool."""
    return [item for item, rx in _HELD_RX if rx.search(name)]


# A skill the profile already covers under another name is not asked about. A held part
# covers the whole it belongs to (Azure Data Factory is Azure, Redshift is AWS), and a
# listed synonym covers its term (model serving is model deployment). The question asked
# whether the person could claim "Azure" of somebody whose profile lists Azure Data
# Factory, and "model deployment" of somebody who lists model serving and MLflow.
#
# This only removes a question. It never puts a word on a document: a covered skill is
# not a yes, so the skills line still prints only what the inventory holds, as it is
# named there. (what a posting asks, as a pattern on the name it gave; the held
# inventory names that cover it.) A profile adds its field's own in skills.py COVERED_BY.
COVERED_BY = [
    (r"^(?:microsoft\s+)?azure(?:\s+cloud)?$",
     r"\bazure\s+(?:data factory|sql|synapse|databricks|machine learning|ml|functions|"
     r"data lake|blob|cosmos)"),
    (r"^(?:aws|amazon web services)$",
     r"\baws\b|\b(?:amazon\s+)?(?:s3|redshift|sagemaker|athena|glue|emr|kinesis|lambda|ec2|"
     r"dynamodb)\b"),
    (r"^(?:gcp|google cloud(?: platform)?)$",
     r"\bbig\s?query\b|\bvertex ai\b|\bdataflow\b|\bcloud composer\b|\bgoogle cloud\b|\bgcp\b"),
    (r"^(?:model (?:deployment|serving)|deploying models|model productioni[sz]ation)$",
     r"\bmodel (?:deployment|serving)\b|\bdeploying models\b|\bmodel productioni[sz]ation\b"),
    (r"^(?:ci ?/ ?cd|continuous (?:integration|delivery|deployment))$",
     r"\bci ?/ ?cd\b|\bcontinuous (?:integration|delivery|deployment)\b|\bgithub actions\b|"
     r"\bgitlab ci\b|\bjenkins\b"),
    (r"^(?:etl|elt)$", r"\betl\b|\belt\b"),
    (r"^postgres(?:ql)?$", r"\bpostgres(?:ql)?\b"),
    (r"^(?:kubernetes|k8s)$", r"\bkubernetes\b|\bk8s\b"),
    (r"^(?:llms?|large language models?)$", r"\bllms?\b|\blarge language models?\b"),
    (r"^version control$", r"\bgit\b|\bgithub\b|\bgitlab\b|\bbitbucket\b"),
    (r"^(?:apache\s+)?spark$", r"\bpyspark\b|\bspark\b"),
]
COVERED_BY = COVERED_BY + [tuple(c) for c in getattr(_SKILLS, "COVERED_BY", None) or ()]
_COVERED_RX = [(re.compile(asked, re.I), re.compile(by, re.I)) for asked, by in COVERED_BY]


def covered_by(name: str) -> list:
    """The held inventory items that already cover a skill asked for under another name:
    its parts, or its synonyms. [] when nothing does."""
    asked = re.sub(r"\s+", " ", str(name or "")).strip(" .,;:()")
    out = []
    for asked_rx, by_rx in _COVERED_RX:
        if asked_rx.search(asked):
            out += [h for h, _rx in _HELD_RX if by_rx.search(h) and h not in out]
    return out


def family_bridges(text, skip=frozenset()):
    """A near bridge for each tool the text names that the person does not hold, from one
    they do hold in the same family. Never one the text names that they hold."""
    out = []
    for fam, members in _FAMILY_RX:
        for name, rx in members:
            if name in skip or not rx.search(text or "") or _held(name):
                continue
            have = []
            for other, _ in members:
                if other != name:
                    have += [h for h in _held(other) if h not in have]
            if have:
                out.append(Assessment(name, BRIDGE, tuple(have),
                                      f"{have[0]} is the {fam} I work in.",
                                      f"near: the same kind of tool ({fam}); show {have[0]}, "
                                      f"and {name} only with the person's yes"))
    return out


def unheld_asked(text):
    """Every skill the text names that the profile does not hold, in the text's own
    spelling (what an applicant tracking system screens on), each as
    {"skill", "have", "why"}: the held tools it sits beside, and why it is not held.

    Nothing here decides whether it goes on a document. The person is asked about each
    one before anything is drafted (tools/stage_picks.py), because only they know: they
    may use it and never said, have learned it since saying they could not, or judge
    they can back it up. Left off unasked, it can be the word an ATS screen fails on.
    """
    text = text or ""
    out = {}

    def add(name, have=(), why=""):
        name = re.sub(r"\s+", " ", str(name)).strip(" .,;:()")
        if not name or _held(name) or covered_by(name):
            return
        got = out.setdefault(name.casefold(), {"skill": name, "have": [], "why": why})
        got["have"] += [h for h in have if h not in got["have"]]
        got["why"] = got["why"] or why

    def spelled(rx):
        return list(dict.fromkeys(m.group(0) for m in rx.finditer(text)))

    for a in family_bridges(text):
        add(a.asked, a.have, f"not on the profile; the same kind of tool as {a.have[0]}")
    for rx, e in _COMPILED:
        if e["verdict"] != HELD:
            for s in spelled(rx):
                add(s, e.get("have") or (), e.get("note", "") or "not held, by the profile's own map")
    for pat, why in getattr(_SKILLS, "NOT_HELD", {}).values():
        if pat:
            for s in spelled(re.compile(pat, re.I)):
                add(s, (), why)
    for rx, _pts, why in (getattr(person.module("search"), "FIT_MISSING", None) or ()):
        for s in spelled(rx):
            add(s, (), why or "the fit score docks it as not held")
    low = text.casefold()
    return sorted(out.values(), key=lambda x: (low.find(x["skill"].casefold()), x["skill"]))


def held_beside(name):
    """The held tools a skill sits beside: its family's, or the profile's bridge for it."""
    for _fam, members in _FAMILY_RX:
        if any(rx.search(name) for _, rx in members):
            have = []
            for other, rx in members:
                if not rx.search(name):
                    have += [h for h in _held(other) if h not in have]
            if have:
                return have
    for rx, e in _COMPILED:
        if rx.search(name) and e.get("have"):
            return list(e["have"])
    return []


# A gap asked for as a preference ranks the role down; it is never a reason not to
# apply. "Preferred: a degree in statistics, mathematics or actuarial science"
# came back as an actuarial credential gap, "do not apply", the same verdict as
# "Required: ACAS or FCAS", and a drafter reading it literally dropped a role the
# rules say to rank.
# text_screen's definition of a preference, so "a bonus-eligible role" is not one
# here either, plus the degree that offers a choice of subjects.
from text_screen import PREFERRED as _PREFERRED  # noqa: E402
_PREFERENCE = re.compile(_PREFERRED.pattern + r"|\bdegree in\b[^.;]{0,80}\bor\b", re.I)
_DO_NOT_APPLY = re.compile(r"\s*\b(?:so )?do not apply\b[^.]*\.?", re.I)


def assess(text):
    """Every mapped capability the text mentions, with the honest verdict."""
    out, seen, claimed = [], set(), set()
    parts = [p for p in re.split(r"(?<=[.;!?])\s+|\n+", text or "") if p.strip()] or [text or ""]
    for rx, e in _COMPILED:
        if e["asked"] in seen or not rx.search(text or ""):
            continue
        seen.add(e["asked"])
        note = e.get("note", "")
        hits = [p for p in parts if rx.search(p)]
        if e["verdict"] == GAP and hits and all(_PREFERENCE.search(p) for p in hits):
            note = (_DO_NOT_APPLY.sub(" ", note).strip() + " Asked as a preference here: it "
                    "ranks the role down, and is never a reason not to apply.").strip()
        out.append(Assessment(e["asked"], e["verdict"], tuple(e.get("have") or ()),
                              e.get("line", ""), note))
        claimed.update(hits)
    for a in family_bridges(text, skip=frozenset(seen)):
        seen.add(a.asked)
        out.append(a)
        claimed.update(p for p in parts if a.asked.lower() in p.lower())
    for rx, why in _MISSING:
        hits = [p for p in parts if rx.search(p)]
        # Only where the map is silent: a sentence it already judged keeps its verdict.
        if not hits or set(hits) & claimed:
            continue
        for p in hits:
            for m in rx.finditer(p):
                name = re.sub(r"\s+", " ", m.group(0)).strip()
                if name and name.casefold() not in {x.casefold() for x in seen}:
                    seen.add(name)
                    out.append(Assessment(name, GAP, (), "", " ".join(str(why or "").split())))
    order = {HELD: 0, BRIDGE: 1, GAP: 2}
    return sorted(out, key=lambda a: order[a.verdict])


def strength_of(asked):
    for e in MAP:
        if e["asked"] == asked:
            return e.get("strength", "near")
    return "near"


def gaps(text):
    """Only the ones nothing covers. These are what to concede, if anything."""
    return [a for a in assess(text) if a.verdict == GAP]


# What a skill gap asks of the person: to LEARN it, or to show the EVIDENCE they
# already hold. An upskilling plan that sends someone on a course for a tool they
# already do the same job with costs weeks that one honest sentence would have saved.
LEARN = "learn"
EVIDENCE = "evidence"


def nudge(skill):
    """{"skill", "nudge": EVIDENCE | LEARN, "have", "say", "why"} for one gap's name.

    EVIDENCE when the profile holds it or holds something that does the same job (a
    HELD or BRIDGE verdict here): what to show and the sentence to say it in. LEARN when
    nothing covers it, with the profile's own reason when it gives one.
    """
    found = assess(str(skill or ""))
    for a in found:
        if a.verdict in (HELD, BRIDGE):
            return {"skill": str(skill), "nudge": EVIDENCE, "have": list(a.have),
                    "say": a.line, "why": a.note}
    why = next((a.note for a in found if a.note), "")
    return {"skill": str(skill), "nudge": LEARN, "have": held_beside(str(skill or "")),
            "say": "", "why": why}


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print('usage: python3 tools/bridges.py "<posting text>": each skill it asks for, '
              "what the profile holds for it, and what to say\n"
              '       python3 tools/bridges.py --nudge "<skill>"...: learn it, or show the '
              "evidence already held")
        sys.exit(0)
    if sys.argv[1:2] == ["--nudge"]:
        # One gap a line: learn it, or show the evidence already held (/upskill reads it).
        for skill in sys.argv[2:]:
            got = nudge(skill)
            print("%-24s %-8s %s" % (got["skill"], got["nudge"], "; ".join(got["have"])[:60]))
            if got["say"]:
                print("    say: %s" % got["say"])
            if got["why"]:
                print("    why: %s" % got["why"])
        sys.exit(0)
    body = " ".join(sys.argv[1:]) or "Power BI or Tableau, SAP a plus, CIPS preferred."
    for a in assess(body):
        print("%-24s %-7s %s" % (a.asked, a.verdict, ", ".join(a.have)[:60]))
        if a.line:
            print("    say: %s" % a.line)
        if a.note:
            print("    note: %s" % a.note)
