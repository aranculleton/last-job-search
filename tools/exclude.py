#!/usr/bin/env python3
"""Rule a posting out, or lift a ruling, in job_scraper/seen_jobs.json.

A ruling is only as good as the reason behind it, and reasons change: the person
starts learning French, gets a permit that clears a citizenship bar, decides a sector
is fine after all. So every exclusion records what it rests on:

    basis "rules"   the person's own screening rules (profile/10-triage-blockers.md,
                    profile/04-job-evaluation.md and the gate settings in search.py),
                    with their fingerprint. When the rules change, the exclusion stops
                    blocking and the posting is screened again the next time a round
                    finds it (tools/throttle.py ruled_out). Nothing is fetched before then.
    basis "person"  the person's own words ("not this kind of company"). It holds until
                    they change their mind, and then `lift` takes it off.

Employer-level rulings are read fresh every round and need nothing here: the bar's
excluded sectors and declined employers (tools/bar.py) and do_not_target.json, whose
entries expire on their own `review_after` date.

Rulings made before this file existed say nothing about what they rest on, so they
cannot lapse by themselves. `review` lists them grouped by reason, once; each group is
checked against the person's current rules and either lifted (it no longer holds) or
stamped with what it rests on (the profile upgrade rulings-review does this with nobody
asking). Queue decisions (a same-employer duplicate, the company throttle) and the bar's
verdicts are re-made every round already and are never part of it.

Usage:
    python3 tools/exclude.py add <url> --title "<title>" --company "<company>" --reason "<why>" [--basis person]
    python3 tools/exclude.py lift "<words in the reason>" [--why "<what changed>"]
    python3 tools/exclude.py review       # older rulings with no basis, grouped by reason
    python3 tools/exclude.py stamp "<words in the reason>" --basis rules|person
    python3 tools/exclude.py rules        # the current rules fingerprint
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from lookup_score import norm  # noqa: E402

SEEN = person.state("job_scraper", "seen_jobs.json")
RULE_DOCS = ("10-triage-blockers.md", "04-job-evaluation.md")
# The search.py settings a posting can be cut on. The rest of the file (what to
# search for, where, how to score) decides nothing a ruling rests on, so editing it
# never lifts one.
GATE_NAMES = ("DEGREE_FLAGS", "DESIGNATED_TITLE", "DESIGNATION", "ELIGIBILITY",
              "ELIGIBILITY_ALWAYS", "ELIGIBILITY_CUT_REASON", "ELIGIBILITY_NOT_BY_PERMIT",
              "ELIGIBILITY_STATUS_TERMS", "ENTITLED", "INTERNAL_ONLY", "INTERNAL_ONLY_TITLE",
              "LANGUAGES_HELD", "LANGUAGE_GATE", "LOCATION", "NEGATIVE", "PERMIT_ACCEPTED",
              "POSITIVE",
              "RESEARCH_ML", "SALARY_CUT_BELOW", "SALARY_FLOOR", "TITLE_LANGUAGE",
              "WORKDAY_INTERNAL_SITES", "YEARS_HELD")
BASES = ("rules", "person")


def _stable(value) -> str:
    """A regex prints its pattern and flags, a dict sorts: the same rules, the same text."""
    if hasattr(value, "pattern"):
        return f"re({value.pattern!r},{value.flags})"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k!r}:{_stable(v)}" for k, v in sorted(value.items(), key=str)) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_stable(v) for v in value]
        return "[" + ",".join(sorted(items) if isinstance(value, (set, frozenset)) else items) + "]"
    return repr(value)


def rules_fingerprint() -> str:
    """Twelve hex characters that change when, and only when, a ruling's basis does."""
    h = hashlib.sha256()
    for name in RULE_DOCS:
        path = person.path(name) if person.exists(name) else ""
        h.update(name.encode())
        if path:
            with open(path, "rb") as fh:
                h.update(fh.read())
    s = person.module("search") if person.exists("search.py") else None
    for name in GATE_NAMES:
        h.update(f"{name}={_stable(getattr(s, name, None))}".encode())
    return h.hexdigest()[:12]


def _load(path=SEEN) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {"seen": {}}
    data.setdefault("seen", {})
    return data


def _save(data, path=SEEN) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def add(url: str, reason: str, title: str = "", company: str = "", basis: str = "rules",
        today: str = "", path=SEEN) -> dict:
    if basis not in BASES:
        raise ValueError(f"basis is one of {', '.join(BASES)}")
    if not reason.strip():
        raise ValueError("a ruling needs its reason: one that cannot say why blocks nothing")
    k = norm(url) or url
    data = _load(path)
    entry = data["seen"].get(k) or {}
    entry.update({"url": entry.get("url") or url, "title": title or entry.get("title", ""),
                  "company": company or entry.get("company", ""), "status": "excluded",
                  "exclusion_reason": reason.strip(), "basis": basis,
                  "excluded_date": today or dt.date.today().isoformat()})
    if basis == "rules":
        entry["rules"] = rules_fingerprint()
    else:
        entry.pop("rules", None)
    data["seen"][k] = entry
    _save(data, path)
    return entry


def lift(words: str, why: str = "", today: str = "", path=SEEN) -> list:
    """Every exclusion whose reason holds `words`, lifted. Returns the lifted entries."""
    needle = words.strip().lower()
    if len(needle) < 3:
        raise ValueError("lift needs words from the reason, not a letter or two")
    data = _load(path)
    out = []
    for entry in data["seen"].values():
        if not isinstance(entry, dict) or (entry.get("status") or "").lower() != "excluded":
            continue
        if needle in str(entry.get("exclusion_reason") or "").lower():
            entry.update({"status": "lifted", "lifted_date": today or dt.date.today().isoformat(),
                          "lifted_because": why or "the person changed their mind"})
            out.append(entry)
    if out:
        _save(data, path)
    return out


def _needs_review(entry) -> bool:
    """Does this ruling block while saying nothing about what it rests on?"""
    import throttle
    if not isinstance(entry, dict) or (entry.get("status") or "").lower() != "excluded":
        return False
    if entry.get("basis"):
        return False
    reason = str(entry.get("exclusion_reason") or "")
    # These already stop blocking or never did, and a fact about the posting (closed,
    # a duplicate, already applied) is not a ruling to review.
    return not (not reason.strip() or reason.lower().startswith(throttle.RE_EVALUATED)
                or throttle.QUEUE_DECISION.search(reason) or throttle.is_stale_exclusion(reason)
                or throttle._NOT_A_VERDICT.search(reason))


def unreviewed(path=SEEN) -> list:
    """Exclusions that block and say nothing about what they rest on."""
    return [e for e in _load(path)["seen"].values() if _needs_review(e)]


def _group(reason: str) -> str:
    import re
    return re.split(r"[:;.(,]", reason.strip().lower())[0].strip()[:60] or "(no reason)"


def review(path=SEEN) -> list:
    """[(group, count, an example reason)] for the unreviewed rulings, biggest first."""
    groups: dict[str, list] = {}
    for e in unreviewed(path):
        groups.setdefault(_group(str(e.get("exclusion_reason"))), []).append(e)
    return sorted(((g, len(es), str(es[0].get("exclusion_reason"))[:160]) for g, es in groups.items()),
                  key=lambda x: -x[1])


def stamp(words: str, basis: str, today: str = "", path=SEEN) -> int:
    """Record what the unreviewed rulings whose reason holds `words` rest on."""
    if basis not in BASES:
        raise ValueError(f"basis is one of {', '.join(BASES)}")
    needle = words.strip().lower()
    if len(needle) < 3:
        raise ValueError("stamp needs words from the reason, not a letter or two")
    data = _load(path)
    fp = rules_fingerprint()
    n = 0
    for entry in data["seen"].values():
        if not _needs_review(entry):
            continue
        if needle not in str(entry.get("exclusion_reason") or "").lower():
            continue
        entry["basis"] = basis
        entry["reviewed_date"] = today or dt.date.today().isoformat()
        if basis == "rules":
            entry["rules"] = fp
        n += 1
    if n:
        _save(data, path)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    a_.add_argument("url")
    a_.add_argument("--reason", required=True)
    a_.add_argument("--title", default="")
    a_.add_argument("--company", default="")
    a_.add_argument("--basis", choices=BASES, default="rules")
    l_ = sub.add_parser("lift")
    l_.add_argument("words")
    l_.add_argument("--why", default="")
    sub.add_parser("rules")
    sub.add_parser("review")
    s_ = sub.add_parser("stamp")
    s_.add_argument("words")
    s_.add_argument("--basis", choices=BASES, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "review":
        rows = review()
        print(f"exclude: {sum(n for _, n, _ in rows)} older ruling(s) with no basis, in {len(rows)} group(s)")
        for g, n, eg in rows:
            print(f"  {n:>4}  {g}\n        e.g. {eg}")
        return 0
    if a.cmd == "stamp":
        print(f"exclude: {stamp(a.words, a.basis)} ruling(s) stamped ({a.basis})")
        return 0
    if a.cmd == "rules":
        print(rules_fingerprint())
        return 0
    if a.cmd == "add":
        e = add(a.url, a.reason, a.title, a.company, a.basis)
        print(f"exclude: {e.get('title') or a.url} ruled out ({a.basis}): {e['exclusion_reason'][:100]}")
        return 0
    lifted = lift(a.words, a.why)
    print(f"exclude: {len(lifted)} ruling(s) lifted")
    for e in lifted[:20]:
        print(f"  {e.get('title')} ({e.get('company')}): {str(e.get('exclusion_reason'))[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
