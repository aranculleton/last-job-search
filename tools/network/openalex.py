#!/usr/bin/env python3
"""People at an employer who have published recently, from OpenAlex.

An optional discovery source, off unless profile/networking.py sets
`OPENALEX = True`. It is worth having where the people worth meeting write papers
(research science, pharma, applied ML, quantitative finance, academia) and adds
little anywhere else, so /setup turns it on only for a field like that.

OpenAlex (openalex.org) is a free, open index of research papers and their
authors. Its API needs a free key for anything but a trickle: without one, every
request counts against a daily allowance shared by everyone on the same IP
address, which a cloud container's shared address has always spent. The key is
read from the environment variable OPENALEX_API_KEY and never written anywhere.

What comes back is a lead, like a search snippet: a name, the employer the paper
lists, the paper and its date. It goes through triage and the read like any
other result.

Usage:
    python3 tools/network/openalex.py "<employer>" [--country CA] [--years 2]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import person  # noqa: E402

_NET = person.module("networking") if person.exists("networking.py") else None
ENABLED = bool(getattr(_NET, "OPENALEX", False))
API = "https://api.openalex.org"
KEY_ENV = "OPENALEX_API_KEY"


class OpenAlexError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    key = os.environ.get(KEY_ENV, "").strip()
    req = urllib.request.Request(f"{API}/{path}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "last-job-search"})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise OpenAlexError(
                "OpenAlex's daily allowance is spent" + ("" if key else
                f" (no key: set {KEY_ENV} to a free key from openalex.org)")) from None
        raise OpenAlexError(f"OpenAlex answered HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise OpenAlexError(f"OpenAlex is unreachable: {e}") from None


def institution(company: str, country: str = "", fetch=_get) -> dict | None:
    """The OpenAlex institution for an employer: a company in their country first."""
    found = fetch("institutions", {"search": company, "per_page": 10,
                                   "select": "id,display_name,type,country_code"}).get("results", [])
    if country:
        found = [i for i in found if (i.get("country_code") or "").upper() == country.upper()] or found
    companies = [i for i in found if i.get("type") == "company"]
    return (companies or found or [None])[0]


def people_at(company: str, country: str = "", years: int = 2, today: dt.date | None = None,
              fetch=_get) -> dict:
    """Authors who listed this employer on a paper in the last `years` years, newest first."""
    inst = institution(company, country, fetch)
    if not inst:
        return {"institution": None, "people": []}
    iid = inst["id"].rsplit("/", 1)[-1]
    since = ((today or dt.date.today()) - dt.timedelta(days=365 * years)).isoformat()
    works = fetch("works", {
        "filter": f"authorships.institutions.id:{iid},from_publication_date:{since}",
        "sort": "publication_date:desc", "per_page": 50,
        "select": "id,title,publication_date,authorships"}).get("results", [])
    people: dict[str, dict] = {}
    for w in works:
        for a in w.get("authorships") or []:
            if not any((i.get("id") or "").endswith(iid) for i in a.get("institutions") or []):
                continue
            author = a.get("author") or {}
            name = (author.get("display_name") or a.get("raw_author_name") or "").strip()
            if not name or name in people:
                continue
            people[name] = {"name": name, "company": company,
                            "employer_on_paper": inst.get("display_name", ""),
                            "kind": "paper", "text": w.get("title") or "",
                            "date": w.get("publication_date") or "", "url": w.get("id") or "",
                            "orcid": author.get("orcid") or ""}
    return {"institution": inst, "people": list(people.values())}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("company")
    ap.add_argument("--country", default=person.country())
    ap.add_argument("--years", type=int, default=2)
    a = ap.parse_args(argv)
    if not ENABLED:
        print("openalex: off (profile/networking.py OPENALEX); it is for fields where people publish")
        return 0
    try:
        out = people_at(a.company, a.country, a.years)
    except OpenAlexError as e:
        print(f"openalex: {e}")
        return 2
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
