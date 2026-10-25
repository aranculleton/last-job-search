#!/usr/bin/env python3
"""Which model and effort each kind of work wants, in one line, and only when it matters.

    python3 tools/model_guide.py apply --on "<this session's model>"   # a line, or nothing
    python3 tools/model_guide.py --on "<this session's model>"         # the day's check
    python3 tools/model_guide.py --all                                 # the whole table

A session runs it when a piece of work starts. It prints nothing when the model already
fits, so a fitting session spends no words on it. When it does not fit it says which way
to switch and why, in one line, and the work carries on: nobody is made to wait.

A script cannot see which model a session runs on, so the check rides on the one command
every session runs anyway: `sync_app.py --on "<model>"` prints the day's check (`summary`)
after the app's updates, and a sync run without `--on` says to add it.

The guide names tiers, not versions. A newer version of a family is the same tier, so
the table keeps working as models are released. A family it does not know is never
guessed at: it says so and how to place it. When a new family arrives, adding one line
to FAMILIES is the whole update. Effort is the same: low, medium and high are what the
table uses, and a product with other names for them maps to the nearest.

Why no evaluator that runs the same task on several models to compare them: it would
spend more than it saves at one person's volume. The checks that matter already run
whatever the model: everything an employer or a contact reads goes through
check_claims, check_numbers, voice_check and the grounding audit.
"""
from __future__ import annotations

import argparse
import re
import sys

# Today's name for each tier, as the model picker shows it. "frontier" is above what any
# work here asks for: Fable, the most capable model, at about two and a half times
# Opus's price per token, so a session on it is told what Opus and Sonnet cover.
TIERS = {"frontier": "Fable", "strongest": "Opus", "balanced": "Sonnet", "fast": "Haiku"}
# A model's family, read from its name or id ("claude-sonnet-5-5", "Opus 5.5"), to its tier.
# Mythos is Fable under another programme: the same model tier.
FAMILIES = {"fable": "frontier", "mythos": "frontier", "opus": "strongest",
            "sonnet": "balanced", "haiku": "fast"}
RANK = {"fast": 0, "balanced": 1, "strongest": 2, "frontier": 3}

# What each kind of work needs: (tier, effort, why). The why is what the person reads.
TASKS: dict[str, tuple[str, str, str]] = {
    "search": ("balanced", "medium",
               "a round is mostly scripts; the model reads the results and ranks the top"),
    "apply": ("strongest", "medium",
              "it writes what an employer reads, and every claim must hold; high for the "
              "one role that matters most"),
    "interview": ("strongest", "high",
                  "stories, likely questions and the answers to them reward the most care"),
    "outreach": ("strongest", "medium",
                 "a message to a person carries your name; tone and facts both matter"),
    "network": ("balanced", "medium",
                "finding and sorting people is searching and reading"),
    "tracking": ("balanced", "low",
                 "logging a result or reading what is owed is quick and runs on scripts"),
    "setup": ("strongest", "high",
              "done once, and everything after reads what it writes"),
    "research": ("balanced", "medium", "reading an employer's own pages"),
    "build": ("strongest", "high",
              "changing the app itself: code, tests and every person's repo downstream"),
    "advice": ("strongest", "medium", "career strategy and positioning are judgement"),
    "chat": ("balanced", "low", "a quick question about the search"),
}

# Commands and plain requests to the work above.
ALIASES = {
    "scrape": "search", "rank": "search", "expand": "search", "round": "search",
    "job search": "search", "shortlist": "search",
    "resume": "apply", "cover letter": "apply", "draft": "apply", "add-template": "apply",
    "reply": "outreach", "prep": "outreach", "message": "outreach",
    "threads": "tracking", "outcome": "tracking", "followups": "tracking",
    "html-report": "tracking",
    "reset": "tracking",
    "upgrade": "research", "add-portal": "build", "upskill": "advice",
}


# Each kind of work in a sentence the person reads.
LABELS = {
    "search": "searches", "apply": "applications", "interview": "interview prep",
    "outreach": "messages to people", "network": "finding people", "tracking": "tracking",
    "setup": "setup", "research": "employer research", "build": "changes to the app",
    "advice": "career advice", "chat": "quick questions",
}


def task_for(name: str) -> str:
    key = name.strip().lstrip("/").lower()
    if key in TASKS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    raise KeyError(name)


def tier_of(model: str) -> str | None:
    """The tier of a model name or id, or None for a family this guide does not know."""
    low = model.lower()
    for family, tier in FAMILIES.items():
        if re.search(rf"\b{family}\b", low.replace("-", " ")):
            return tier
    return None


def advise(name: str, on: str = "") -> str:
    """One line when the model on `on` is a poor fit for this work, else ""."""
    tier, effort, why = TASKS[task_for(name)]
    want = f"{TIERS[tier]} at {effort} effort"
    if not on:
        return f"Best on {want}: {why}."
    have = tier_of(on)
    if have is None:
        return (f"This guide does not know {on} yet. This work wants the {tier} model "
                f"({TIERS[tier]} today) at {effort} effort; if the picker lists {on} as more "
                f"capable than {TIERS['strongest']}, treat it as the strongest.")
    if have == tier:
        return ""
    if RANK[have] > RANK[tier] and tier == "strongest":
        return (f"Model: {TIERS[tier]} at {effort} effort does this well ({why}); "
                f"{TIERS[have]} spends more of your allowance on it, so switch if that matters.")
    if RANK[have] > RANK[tier]:
        return (f"Model: {TIERS[tier]} at {effort} effort is enough for this ({why}). "
                f"Switching from {TIERS[have]} saves tokens and loses nothing.")
    return (f"Model: this is worth {want} ({why}). Switch up in the model picker for it; "
            f"carrying on here meanwhile.")


def _join(items: list) -> str:
    words = [LABELS[k] for k in items]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def summary(on: str) -> str:
    """The day's check, in one or two sentences: what this model suits, and what wants another."""
    have = tier_of(on)
    if have is None:
        return (f"Model check: this guide does not know {on} yet; if the picker lists it as more "
                f"capable than {TIERS['strongest']}, treat it as the strongest "
                "(`python3 tools/model_guide.py --all` shows what each kind of work wants).")
    by_tier: dict[str, list] = {}
    for k, (tier, _, _) in TASKS.items():
        by_tier.setdefault(tier, []).append(k)
    name = TIERS[have]
    fits = by_tier.get(have, [])
    up = [(t, ks) for t, ks in by_tier.items() if RANK[t] > RANK[have]]
    down = [(t, ks) for t, ks in by_tier.items() if RANK[t] < RANK[have]]
    out = [f"Model check ({name}):"]
    if fits:
        out.append(f"right for {_join(fits)}.")
    elif not up:
        out.append("more than any of this needs.")
    if up:
        out.append(("Switch up for " if fits else "switch up for ") + "; ".join(f"{_join(ks)} ({TIERS[t]})"
                                                for t, ks in sorted(up, key=lambda x: RANK[x[0]]))
                   + ", in the model picker.")
    if down:
        out.append("; ".join(f"{TIERS[t]} covers {_join(ks)}"
                             for t, ks in sorted(down, key=lambda x: -RANK[x[0]]))
                   + ", for less of your allowance.")
    return " ".join(out)


def table() -> str:
    rows = [f"{'work':10} {'model':8} {'effort':7} why"]
    for k, (tier, effort, why) in TASKS.items():
        rows.append(f"{k:10} {TIERS[tier]:8} {effort:7} {why}")
    names = {}
    for alias, k in ALIASES.items():
        names.setdefault(k, []).append(alias)
    rows.append("")
    rows += [f"{k}: also {', '.join(sorted(v))}" for k, v in names.items()]
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("work", nargs="?", help="a command (apply, /scrape) or a kind of work")
    ap.add_argument("--on", default="", help="the model this session runs on")
    ap.add_argument("--all", action="store_true", help="print the whole table")
    a = ap.parse_args(argv)
    if not a.work and a.on and not a.all:
        print(summary(a.on))
        return 0
    if a.all or not a.work:
        print(table())
        return 0
    try:
        line = advise(a.work, a.on)
    except KeyError:
        print(f"model_guide: no entry for {a.work!r}; the nearest kind of work in --all applies.")
        return 0
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
