#!/usr/bin/env python3
"""Look up a posting's already-computed fit score before paying to derive it again.

`/scrape` and `/rank` score every posting they present and write the result to
`job_scraper/seen_jobs.json`. `/apply` then used to re-derive the same weighted
evaluation from scratch, on exactly the postings the user selected - the most
expensive re-computation in the repo, and entirely avoidable.

It also solves a real dedup bug. The tracker's `source` column and the
`seen_jobs.json` key are both "the posting URL", but portals emit two forms:

    https://ca.linkedin.com/jobs/view/senior-insights-analyst-at-acme-1234567890
    https://www.linkedin.com/jobs/view/1234567890

A raw string match treats those as different postings. That let already-applied
roles show up as fresh resurfacing candidates. Normalizing
to the portal's numeric id fixes it, and every consumer should use `norm()` here
rather than rolling its own.

Usage:
    python3 tools/lookup_score.py "https://www.linkedin.com/jobs/view/1234567890"
    python3 tools/lookup_score.py 1234567890
    python3 tools/lookup_score.py --company "Harbour Freight" --title "Demand Planning"
    python3 tools/lookup_score.py --stale-after YYYY-MM-DD <url>

Exit status is 0 on a usable hit, 1 on a miss or a hit too thin to reuse, so a
caller can branch on it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

SEEN = person.state("job_scraper", "seen_jobs.json")
TRACKER = person.state("job_search_tracker.csv")


# Query parameters that say where the click came from and nothing about which
# job it is. Everything else in the query is kept, because on an applicant
# tracking system the query IS the job.
_TRACKING = re.compile(
    r"^(?:utm_\w+|gclid|fbclid|msclkid|mc_[ce]id|ref|referer|referrer|source|src|"
    r"trk|trackingId|origin|from|campaign|geoId|refId|lipi|licu|eBP|position|"
    r"pageNum|currentJobId|savedSearchId|distance|sortBy|f_\w+|"
    r"lever-origin|lever-source|_gl|hl|lang|locale|s|t)$", re.I)

# The job id an applicant tracking system puts in the query. Greenhouse-backed
# career pages are the common case in this corpus and they are the reason this
# exists: every Greenhouse job at an employer shares one path and differs only
# in `gh_jid`.
_ATS_ID_PARAM = ("gh_jid", "gh_src", "jobid", "job_id", "opportunityid",
                 "requisitionid", "req_id", "posting_id", "id")


def norm(url: str | None) -> str | None:
    """Normalize a posting URL (or bare id) to a stable dedup key.

    LinkedIn ids are the numeric tail of /jobs/view/<optional-slug->\\d+.

    Everything else keeps the parts of the query that identify the posting and
    drops the parts that identify the click. Dropping the whole query collapsed
    every Greenhouse job at one employer into a single key: two roles at one
    employer ("Analytics Engineer II" and "Senior Data Analyst") both normalized
    to `<employer>.careers/job`, so whichever was seen first permanently blocked
    the other.
    """
    if not url:
        return None
    u = url.strip()
    if re.fullmatch(r"\d{6,}", u):
        return "li:" + u
    m = re.search(r"/jobs/view/(?:[^/?]*-)?(\d{6,})", u)
    if m:
        return "li:" + m.group(1)
    head, _, query = u.partition("?")
    base = re.sub(r"^https?://(www\.)?", "", head).rstrip("/").lower()
    params = _query_pairs(query)
    for name in _ATS_ID_PARAM:
        if params.get(name):
            return "%s?%s=%s" % (base, name, params[name])
    keep = sorted((k, v) for k, v in params.items() if not _TRACKING.match(k))
    return base + ("?" + "&".join("%s=%s" % kv for kv in keep) if keep else "")


def _query_pairs(query: str) -> dict:
    """`{lowercased name: first value}`. Hand-written enough not to need urllib."""
    out = {}
    for part in (query or "").split("&"):
        if not part:
            continue
        name, _, value = part.partition("=")
        name = name.strip().lower()
        if name and name not in out:
            out[name] = value.strip()
    return out


def load_seen() -> dict:
    # UTF-8 by name, as it is written (ensure_ascii=False): on a computer whose default
    # is cp1252 an accented employer name was misread, or the read failed.
    with open(SEEN, encoding="utf-8") as fh:
        return json.load(fh)["seen"]


def find(key: str | None, company: str | None, title: str | None) -> tuple[str, dict] | None:
    seen = load_seen()
    if key:
        for url, rec in seen.items():
            if isinstance(rec, dict) and norm(url) == key:
                return url, rec
    if company:
        # Company+title matching is a fallback, and a dangerous one: reusing
        # another posting's score under this posting's name would put a wrong
        # fit judgment in front of the user with no visible sign it is wrong.
        # Two roles at one firm can share a 24-character title prefix, and a
        # company-only call has no title to disambiguate at all. So this path
        # returns a match ONLY when exactly one entry survives, and refuses
        # outright when it is ambiguous.
        #
        # The employer is compared by its key, as every other reader of the
        # state does: "Acme Analytics" missed a score stored under "Acme
        # Analytics Inc.", and /apply then paid to derive it a second time.
        co = company_key(company)
        hits = []
        for url, rec in seen.items():
            if not isinstance(rec, dict):
                continue
            if not co or company_key(rec.get("company")) != co:
                continue
            if title:
                t, rt = title.lower().strip(), (rec.get("title") or "").lower().strip()
                if not (t == rt or t in rt or rt in t):
                    continue
            hits.append((url, rec))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise Ambiguous(hits)
        return None
    return None


class Ambiguous(Exception):
    """More than one stored entry matched on company (and title). Never guess."""

    def __init__(self, hits):
        self.hits = hits
        super().__init__(f"{len(hits)} entries matched")


def tracker_rows_for(key: str | None, company: str | None) -> list[dict]:
    """Every tracker row for this posting, or for this employer under any form
    of its name. This is the check /apply relies on before drafting, and a raw
    name comparison said nothing about an application to "Acme Analytics Inc."
    when asked about "Acme Analytics"."""
    import csv_store
    co = company_key(company) if company else ""
    out = []
    for row in csv_store.read_rows(TRACKER):
        if key and norm(row.get("source")) == key:
            out.append(row)
        elif co and company_key(row.get("company")) == co:
            out.append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", help="posting URL or bare portal id")
    ap.add_argument("--company")
    ap.add_argument("--title")
    ap.add_argument("--stale-after",
                    help="treat a score dated before this ISO date as stale")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not (a.url or a.company):
        ap.error("give a posting URL/id, or --company")

    key = norm(a.url) if a.url else None
    try:
        hit = find(key, a.company, a.title)
    except Ambiguous as e:
        print("AMBIGUOUS: more than one stored entry matches. Refusing to guess - "
              "re-run with the posting URL, which is unambiguous.")
        for url, rec in e.hits:
            print(f"  {rec.get('company')} - {rec.get('title')}  "
                  f"score {rec.get('rank_score')}  {url}")
        return 1

    applied = tracker_rows_for(key, a.company)
    if applied:
        print("ALREADY IN TRACKER - confirm with the user before drafting again:")
        for r in applied:
            print(f"  {r['date']}  {r['company']} - {r['role']}  [{r['status']}]"
                  f"  fit {r.get('fit_rating')}")
        print()

    if not hit:
        print(f"MISS: no stored entry for {a.url or a.company}. Score it now against "
              f"12-scoring-brief.md.")
        return 1

    url, rec = hit
    score = rec.get("rank_score")
    if a.json:
        print(json.dumps({"url": url, **rec}, indent=1))
        return 0 if score is not None else 1

    print(f"HIT: {rec.get('company')} - {rec.get('title')}")
    print(f"  url:      {url}")
    print(f"  status:   {rec.get('status')}")
    if score is None:
        print("  score:    none stored (entry predates scoring, or came from a cheaper tier)")
        print("  -> derive the score now against 12-scoring-brief.md.")
        return 1
    print(f"  score:    {score}  ({rec.get('rank_verdict')})  scored {rec.get('rank_date')}")
    print(f"  salary:   {rec.get('salary') or 'not stated'}")
    for k in ("location_verdict", "language_gate"):
        if rec.get(k):
            print(f"  {k}: {rec[k]}")
    for k in ("strengths", "gaps"):
        for item in (rec.get(k) or []):
            print(f"  {k[:-1]}: {item}")
    if rec.get("exclusion_reason"):
        print(f"  EXCLUDED: {rec['exclusion_reason']}")

    if a.stale_after and (rec.get("rank_date") or "") < a.stale_after:
        print(f"\n  STALE: scored {rec.get('rank_date')}, before {a.stale_after}. Re-derive.")
        return 1

    print("\n  -> Reuse this score. Say in the report that it is reused and from when.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
