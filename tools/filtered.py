#!/usr/bin/env python3
"""What a round filtered out and why, kept every round, and a way to bring one back.

    python3 tools/filtered.py show <round> [--rule <words>]      # what was filtered, numbered
    python3 tools/filtered.py back <round> <pick>... [--why "<their words>"]

A round drops most of what it finds: the free gates at the search (age, place, title),
what this search had already ruled out or first saw too long ago (the 14-day relist
rule), the stated-fact screen's cuts and the throttle's skips. Those were in the round's
own stage files, which a round that met its target deletes, so nothing showed the person
what was left out or let them overrule it.

`write()` keeps the list every round, at documents/rounds/filtered/<round>.json: title,
employer, place, link, the stage, the rule and the reason, no posting bodies. It sits in a
folder of its own because every reader of documents/rounds/*.json (stage_picks, bar.py,
why.py, a person's own tests) takes each file there as a round's shortlist, which is a list
of rows; this is not one.

`back` is the override, for a posting the person wants after all. A pick is the number
`show` prints, a link, or `Employer::title words`. It lifts any ruling this search wrote
against the posting (tools/exclude.py lift), and adds the posting to the end of that round's
shortlist, marked with why it was filtered, so `stage_picks.py stage <round> <rank>` drafts
it like any other pick. The rank it can be staged as is printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import person  # noqa: E402
from lookup_score import norm  # noqa: E402

FOLDER = "filtered"
# Where each stage writes what it dropped, inside a round's directory, and what the stage
# is called on the list. 00_scrape/dropped.json is the search's own free gates; the rest
# are run_round.py's stage files (its DIAGNOSTICS).
STAGES = ((os.path.join("00_scrape", "dropped.json"), "search"),
          ("01_dropped.json", "already seen"),
          ("03_screened_all.json", "screen"),
          ("06_skipped.json", "throttle"))
FIELDS = ("title", "company", "location", "url", "portal", "date")
REASON_CAP = 240


def _rows(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    data = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
    return [r for r in data if isinstance(r, dict)]


def _cuts(row: dict) -> list[str]:
    cuts = row.get("cuts")
    if isinstance(cuts, str):
        try:
            cuts = json.loads(cuts)
        except ValueError:
            cuts = [cuts]
    return [str(c) for c in cuts or [] if str(c).strip()]


def rule_of(stage: str, reason: str) -> str:
    """The rule a reason names, in a few words: "age (relist)", "location", "screen"."""
    if stage == "screen":
        return "screen"
    head = reason.split(":", 1)[0].strip().lower() if ":" in reason else reason.strip().lower()
    if head == "age" and "relist" in reason:
        return "age (relist)"
    return head[:40] or stage


def entries(round_dir: str) -> list[dict]:
    """Everything the round in `round_dir` filtered out, each posting once, in stage order."""
    out, seen = [], set()
    for rel, stage in STAGES:
        for r in _rows(os.path.join(round_dir, rel)):
            if stage == "search":
                reason = str(r.get("prefilter_reason") or r.get("prefilter") or "")
            elif stage == "already seen":
                reason = str(r.get("prefilter_reason") or r.get("exclusion_reason") or "")
            elif stage == "screen":
                if str(r.get("text_screen") or "").lower() != "cut":
                    continue
                reason = "; ".join(_cuts(r)) or str(r.get("exclusion_reason") or "")
            else:
                reason = str(r.get("skip_reason") or "")
            key = norm(r.get("url")) or r.get("url") or (r.get("company"), r.get("title"))
            if key in seen:
                continue
            seen.add(key)
            e = {k: r.get(k) for k in FIELDS if r.get(k) not in (None, "")}
            e.update(stage=stage, rule=rule_of(stage, reason),
                     reason=reason if len(reason) <= REASON_CAP else reason[:REASON_CAP - 3] + "...")
            out.append(e)
    return out


def path_for(summary_dir: str, name: str) -> str:
    return os.path.join(summary_dir, FOLDER, f"{name}.json")


def write(round_dir: str, summary_dir: str, name: str) -> str | None:
    """documents/rounds/filtered/<name>.json from the round's stage files, and its path."""
    found = entries(round_dir)
    counts: dict[str, int] = {}
    for e in found:
        counts[e["rule"]] = counts.get(e["rule"], 0) + 1
    path = path_for(summary_dir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # One posting a line: a round can filter a thousand, and a line each keeps the file a
    # third the size of an indented one and its changes readable.
    head = json.dumps({"round": name, "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1]))},
                      ensure_ascii=False)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head[:-1] + ', "filtered": [\n'
                 + ",\n".join(json.dumps(e, ensure_ascii=False) for e in found) + "\n]}\n")
    return path


def _summary_dir() -> str:
    return person.state("documents", "rounds")


def load(name: str, summary_dir: str | None = None) -> dict:
    path = path_for(summary_dir or _summary_dir(), name)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise SystemExit(f"filtered: no list for round {name} at {path}. A round writes one "
                         "from this version on.") from None
    return data if isinstance(data, dict) else {"filtered": data}


def _low(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def find(found: list[dict], pick: str) -> dict:
    """The entry a pick names: its number on the list, its link, or Employer::title words."""
    pick = str(pick).strip()
    if pick.isdigit():
        i = int(pick)
        if not 1 <= i <= len(found):
            raise SystemExit(f"filtered: {pick} is outside the list (1..{len(found)})")
        return found[i - 1]
    if re.match(r"^https?://", pick, re.I):
        hits = [e for e in found if norm(e.get("url")) == norm(pick)]
    elif "::" in pick:
        company, title = pick.split("::", 1)
        hits = [e for e in found
                if _low(company) in _low(e.get("company")) and _low(title) in _low(e.get("title"))]
    else:
        raise SystemExit(f"filtered: {pick!r} is not a number, a link or Employer::title words")
    if len(hits) != 1:
        named = "; ".join(f"{e.get('company')} | {e.get('title')}" for e in hits[:5])
        raise SystemExit(f"filtered: {pick!r} matched {len(hits)} postings"
                         + (f" ({named}); make it unique" if hits else ""))
    return hits[0]


def back(name: str, picks, why: str = "", round_dir: str | None = None,
         summary_dir: str | None = None, today: str = "", seen_path: str | None = None) -> list:
    """Bring each picked posting back: its rulings lifted, the round's shortlist given it.

    Returns [(entry, rank in the shortlist)]. The shortlist is every copy staging reads:
    the round directory's 06_shortlist.json when it is there, and the committed summary."""
    import exclude
    summary_dir = summary_dir or _summary_dir()
    today = today or dt.date.today().isoformat()
    found = load(name, summary_dir).get("filtered") or []
    chosen = [find(found, p) for p in picks]
    copies = [p for p in ((os.path.join(round_dir, "06_shortlist.json") if round_dir else None),
                          os.path.join(summary_dir, f"{name}.json")) if p and os.path.exists(p)]
    if not copies:
        raise SystemExit(f"filtered: round {name} has no shortlist to add to "
                         f"({os.path.join(summary_dir, name + '.json')} is missing)")
    done = []
    for e in chosen:
        note = (f"brought back {today}: filtered at the {e['stage']} ({e['reason']})"
                + (f"; the person: {why}" if why else ""))
        # Lifted by its link, and as a relist: a posting dropped on another posting's
        # ruling (the same title, employer and city) was dropped on it again next round.
        if e.get("url") or (e.get("title") and e.get("company")):
            exclude.lift(urls=[e["url"]] if e.get("url") else [], postings=[e],
                         why=why or "brought back by the person", today=today,
                         **({"path": seen_path} if seen_path else {}))
        row = {k: e[k] for k in FIELDS if e.get(k)}
        row["brought_back"] = note
        rank = None
        for path in copies:
            with open(path, encoding="utf-8") as fh:
                rows = json.load(fh)
            rows = rows if isinstance(rows, list) else list(rows.values())
            at = next((i for i, r in enumerate(rows) if isinstance(r, dict) and e.get("url")
                       and norm(r.get("url")) == norm(e["url"])), None)
            if at is None:
                rows.append(row)
                at = len(rows) - 1
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(rows, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
            rank = at + 1 if rank is None else rank
        done.append((e, rank))
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="What a round filtered out, and bringing one back.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("show", help="what a round filtered out, numbered")
    s.add_argument("round")
    s.add_argument("--rule", default="", help="only entries whose rule or reason has these words")
    b = sub.add_parser("back", help="bring filtered postings back into the round's shortlist")
    b.add_argument("round")
    b.add_argument("picks", nargs="+")
    b.add_argument("--why", default="", help="the person's words, kept with the posting")
    b.add_argument("--round-dir", default=None, help="the round's directory (rounds/<round>)")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_usage()
        return 2
    name = os.path.basename(os.path.normpath(a.round))
    if a.cmd == "show":
        data = load(name)
        found = data.get("filtered") or []
        want = _low(a.rule)
        print(f"round {name}: {len(found)} filtered out"
              + (" (" + ", ".join(f"{n} {k}" for k, n in (data.get("counts") or {}).items()) + ")"
                 if data.get("counts") else ""))
        for i, e in enumerate(found, 1):
            if want and want not in _low(e.get("rule")) and want not in _low(e.get("reason")):
                continue
            print(f"{i:>4}. {e.get('company', '')} | {e.get('title', '')} | {e['rule']}: "
                  f"{e['reason']} | {e.get('url', 'no link')}")
        return 0
    round_dir = a.round_dir or (a.round if os.path.isdir(a.round) else None)
    for e, rank in back(name, a.picks, why=a.why, round_dir=round_dir):
        print(f"back: {e.get('company')} | {e.get('title')} is number {rank} on round {name}'s "
              f"shortlist (it was filtered at the {e['stage']}: {e['rule']}). Stage it with "
              f"stage_picks.py stage {a.round} {rank}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
