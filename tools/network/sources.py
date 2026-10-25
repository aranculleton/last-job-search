#!/usr/bin/env python3
"""Where the people worth meeting can be found, for this person, and which places pay.

A LinkedIn title search finds executives and misses most of the people who reply.
The people a nurse, a software engineer, a lawyer or a graduate should meet are
named in different public places: a ward's team page, a repository's maintainers,
a firm's people directory, a chapter committee, a conference programme. So each
person gets their own plan, researched once by /setup for their field, level and
country (`PEOPLE_SOURCES` in profile/networking.py), and every run works down it.

    KINDS          the catalogue: what each kind of source finds and how to search it
    plan()         this person's kinds, in their order, or DEFAULT_PLAN
    ranked()       the plan reordered by what has drawn replies, once a kind has enough
    searches()     the searches one kind runs for one employer, inside the budget
    linkedin_check the search that finds someone's LinkedIn profile, results only

Speed is the budget. A kind marked `per_run` (a conference roster, a meetup's
organisers, an award list) is searched once and serves every employer in the
run. Each employer gets at most SEARCHES_PER_COMPANY searches across all its
kinds, and a run stops searching the moment the batch is full. All of this is
plain code: no model call decides the order.

Usage:
    python3 tools/network/sources.py                 # this person's plan, ranked
    python3 tools/network/sources.py "<employer>"...  # the run's searches, within the budget
    python3 tools/network/sources.py ladder --tools <browser,chrome,enable or none>
                                                     # what this chat can use, and what to say
    python3 tools/network/sources.py connections "<employer>"   # rung 1: who they already know there
    python3 tools/network/sources.py harvest <results.json> --company "<employer>" [--kind K]
                                                     # rungs 2 and 3: search results to a ranked list
"""
from __future__ import annotations

import datetime
import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

_NET = person.module("networking") if person.exists("networking.py") else None
# "declined" when the person would rather not export their connections: the
# connections kind then drops out of the plan instead of asking again every run.
CONNECTIONS_EXPORT = str(getattr(_NET, "CONNECTIONS_EXPORT", "") or "")


# scope: "per_company" is searched for each employer, "per_run" once for the run,
# "local" needs no search (a file or the browser). `searches` are WebSearch query
# templates with {company}, {function}, {city}, {country}, {school} and {year};
# linkedin=False runs them with LinkedIn excluded, so they reach the places a title
# search cannot. A person's plan can carry its own query for any kind (the third
# item of a PEOPLE_SOURCES entry), which is how a nurse's plan names the nursing
# body's branch committees and a lawyer's the firm directories of their city.
# Robots.txt and terms were checked for each kind on 2026-10-17; `limits` is what
# they allow.
Kind = namedtuple("Kind", "label finds pays_in scope searches linkedin limits")

KINDS = {
    "connections": Kind(
        "their own LinkedIn connections", "people they already know there, at any level",
        "everyone", "local", (), True, "their own export; read only"),
    "alumni_employer": Kind(
        "people who worked where they worked", "former colleagues' paths, any level",
        "everyone with a past employer", "per_run", (), True, ""),
    "alumni_school": Kind(
        "people from their school", "graduates of the same school or course",
        "everyone; most of all graduates and career changers", "per_run", (), True, ""),
    "alumni_story": Kind(
        "their school's alumni features", "graduates two to fifteen years ahead, by employer",
        "entry and mid levels in any field", "per_company",
        ('"{school}" alumni "{company}" (profile OR spotlight OR story)',), False, ""),
    "posting": Kind(
        "the people named on a posting", "the hiring manager or recruiter for that role",
        "everyone; most of all public sector, health and universities, where adverts name "
        "a contact for informal enquiries", "per_company",
        ('"{company}" {function} ("informal enquiries" OR "informal discussion" OR '
         '"for more information contact")',), False, "the name only, never the email"),
    "campus": Kind(
        "early-careers and graduate recruiters", "graduate scheme leads and campus recruiters",
        "entry level: banking, consulting, law, engineering, retail, accounting", "per_company",
        ('"{company}" ("graduate programme" OR "graduate program" OR "early careers") '
         '(recruiter OR "talent acquisition")',), True, ""),
    "posts": Kind(
        "hiring posts", "managers saying their team is hiring, dated",
        "everyone; a live signal", "per_company",
        ('"{company}" ("we\'re hiring" OR "join my team" OR "my team is hiring") {function} '
         'site:linkedin.com/posts',), True, ""),
    "hn_hiring": Kind(
        "Hacker News 'Who is hiring' threads", "founders and hiring managers posting roles",
        "software, data and startups", "per_company",
        ('"{company}" "who is hiring" site:news.ycombinator.com',), False,
        "search results only; the site's crawl-delay is 30 seconds"),
    "title_search": Kind(
        "a LinkedIn title search", "managers and senior people by title",
        "everyone; strongest for senior titles", "per_company", (), True, ""),
    "team_page": Kind(
        "the employer's own team and people pages", "leaders, heads of function and peers",
        "every white-collar field; strongest at small and mid-sized firms, agencies, law, "
        "consulting, finance and charities", "per_company",
        ('"{company}" ("meet the team" OR "our people" OR leadership OR "life at") {function}',),
        False, "robots.txt only"),
    "blog": Kind(
        "the employer's engineering, product and design blog", "the people doing the work, by byline",
        "software, data, product, design, research", "per_company",
        ('"{company}" (engineering OR tech OR product) blog {function}',), False,
        "Medium blocks its own search: reach it through web search"),
    "writing": Kind(
        "their own writing", "practitioners who publish under their name",
        "data, software, marketing, finance, health", "per_company",
        ('"{company}" {function} (site:medium.com OR site:substack.com OR site:dev.to)',), False,
        "the employer is self-declared: confirm it"),
    "roster": Kind(
        "conference and event speaker lists", "mid to senior practitioners who speak",
        "most fields with conferences", "per_run", (), False, "ask the page for every speaker"),
    "community": Kind(
        "meetups, user groups and professional-body committees",
        "organisers, chapter chairs and committee members",
        "every field with a professional body or meetups (nursing, accounting, engineering, "
        "HR, law, project management, teaching, tech); any level", "per_run",
        ('{function} (meetup OR "user group" OR chapter OR branch) {city} '
         '(organiser OR organizer OR committee OR chair)',), False,
        "public pages only; members' areas are out of scope"),
    "press": Kind(
        "trade press, appointments and podcasts", "people quoted, interviewed or newly appointed",
        "most fields; mid to senior", "per_company",
        ('"{company}" {function} (interview OR podcast OR "said")',
         '"{company}" ("appoints" OR "joins as" OR "promoted to") {function}'), False,
        "never past a paywall"),
    "awards": Kind(
        "award and shortlist pages", "people and teams recognised in their field",
        "HR, law, accounting, hospitality, nursing, teaching, engineering, sales, design",
        "per_run",
        ('{function} (award OR shortlist OR finalist OR "40 under 40" OR "30 under 30") '
         '{country} {year}',), False, "check they have not moved since"),
    "webinars": Kind(
        "the employer's case studies and webinars", "customer-facing and specialist staff",
        "sales, customer success, consulting, communications", "per_company",
        ('"{company}" ("case study" OR webinar) {function}',), False, ""),
    "papers": Kind(
        "research papers (OpenAlex)", "researchers who put the employer on a recent paper",
        "research science, pharma, academia, applied ML, quantitative finance", "per_company",
        (), False, "tools/network/openalex.py; a free key in a cloud session"),
    "patents": Kind(
        "patents", "inventors and R&D engineers, by assignee",
        "engineering, pharma, hardware, automotive", "per_company",
        ('"{company}" inventor patent {function}',), False,
        "Google Patents allows its /patent/ pages, not its search: reach them by web search"),
    "code": Kind(
        "the employer's open-source code", "engineers who maintain or contribute to its repositories",
        "software, data, devops and security", "per_company",
        ('site:github.com "{company}" {function}',), False,
        "GitHub's terms forbid using its data for spam or for recruiters: names only, never emails"),
    "portfolio": Kind(
        "design portfolios", "designers and art directors who list the employer",
        "design, UX, advertising, architecture, games", "per_company",
        ('"{company}" {function} (site:dribbble.com OR site:behance.net)',), False,
        "Behance disallows AI crawlers: web search results only, never a fetch"),
    "mentors": Kind(
        "volunteer mentoring platforms", "mentors who give their time, mid to senior",
        "design, product, engineering, data; early career", "per_company",
        ('"{company}" {function} site:adplist.org',), False,
        "they volunteered advice: never ask a mentor for a referral first"),
    "founders": Kind(
        "startup directories", "founders and the early team",
        "startups, product, growth, engineering", "per_company",
        ('"{company}" (site:ycombinator.com/companies OR site:producthunt.com)',), False,
        "search results only"),
    "directory": Kind(
        "official public staff directories and org charts",
        "senior officials, heads of department, boards, school and hospital leaders",
        "public sector, health, local government, education, regulators", "per_company",
        ('"{company}" ("our management" OR "senior leadership" OR "board of directors" '
         'OR organogram OR "executive team")',), False,
        "the plan names the country's own directory; never store pay or contact fields"),
    "registry": Kind(
        "company, charity and regulator registers", "directors, trustees and approved people",
        "small firms, trades, hospitality, charities, regulated finance", "per_company",
        (), False, "the plan names the register and its official API; never addresses"),
    "people_tab": Kind(
        "the employer's People tab, in their own browser", "everyone at the employer in their function",
        "everyone, with a browser linked", "local", (), True, "one page at a time, nothing clicked"),
}

DEFAULT_PLAN = ("connections", "alumni_employer", "alumni_school", "posting", "posts",
                "title_search", "team_page", "roster", "press", "people_tab")

SEARCHES_PER_COMPANY = 4
# Of those, the title searches go first, both of them. Measured: the plain title query
# found 14 people at an employer where the old shapes found 5, and in two real runs at
# one employer (2026-10-18) it was the only kind that named anyone there; posts, team
# pages and press returned job ads, press releases and people elsewhere. A round robin
# had given it one search in four, after the kinds that found nobody.
TITLE_SEARCHES = 2
# The searches that find a named person's LinkedIn profile (linkedin_check), for the
# best name-only people a page named: on top of the four, and capped, where they had
# been uncounted (one run made 13 searches at one employer).
CHECKS_PER_COMPANY = 3
SEARCHES_PER_RUN = 5          # the per_run kinds, together
ALUMNI_EMPLOYER_SEARCHES = 3  # of those: one each for the three employers most recently left
MIN_DECIDED = 5               # replies before a kind is moved by its results


class UnknownKind(ValueError):
    pass


_QUERY: dict[str, str] = {}   # a plan's own query for a kind, filled by plan()


class _Blank(dict):
    """A plan's own query may name a placeholder this file does not fill: it reads as blank."""
    def __missing__(self, key):
        return ""


def plan() -> list:
    """This person's kinds, as (kind, detail), in their order.

    `PEOPLE_SOURCES` in profile/networking.py is (kind, detail) pairs; the detail
    is why the kind pays for them, or the place to look (a roster's URL, the
    directory's address). Without one, DEFAULT_PLAN.
    """
    raw = getattr(_NET, "PEOPLE_SOURCES", None) or DEFAULT_PLAN
    out = []
    for entry in raw:
        entry = (entry,) if isinstance(entry, str) else tuple(entry)
        kind, detail = entry[0], (entry[1] if len(entry) > 1 else "")
        _QUERY[kind] = entry[2] if len(entry) > 2 and entry[2] else _QUERY.get(kind, "")
        if kind not in KINDS:
            raise UnknownKind(f"PEOPLE_SOURCES names {kind!r}; the kinds are {', '.join(KINDS)}")
        if kind == "connections" and CONNECTIONS_EXPORT == "declined" and not _has_export():
            continue
        out.append((kind, detail))
    return out


def _has_export() -> bool:
    return os.path.exists(person.local_state("documents", "linkedin", "Connections.csv"))


def _results(contacts, threads, today=None) -> dict:
    """{kind: (replied, decided)} from what_works' decided first messages."""
    import what_works
    counts: dict[str, list] = {}
    for c in what_works.message_cases(contacts, threads, today):
        if c["attempt"] != "opener" or c["found_via"] == "not recorded":
            continue
        won, total = counts.setdefault(c["found_via"], [0, 0])
        counts[c["found_via"]] = [won + int(c["won"]), total + 1]
    return {k: tuple(v) for k, v in counts.items()}


def ranked(contacts=(), threads=(), today=None) -> list:
    """The plan reordered by replies: (kind, detail, why) best first.

    A kind moves only on MIN_DECIDED decided first messages; until then the
    researched order stands, because three sends say nothing.
    """
    results = _results(list(contacts), list(threads), today) if contacts else {}
    base = plan()

    def key(item):
        i, (kind, _) = item
        won, total = results.get(kind, (0, 0))
        rate = won / total if total >= MIN_DECIDED else None
        return (0 if rate is not None else 1, -(rate or 0), i)

    out = []
    for _, (kind, detail) in sorted(enumerate(base), key=key):
        won, total = results.get(kind, (0, 0))
        why = (f"replied {won} of {total}" if total >= MIN_DECIDED
               else f"{total} decided so far" if total else "no results yet")
        out.append((kind, detail, why))
    return out


def _function() -> str:
    """Their own job title, quoted, as the word a search narrows by."""
    titles = (getattr(_NET, "TITLE_SETS", None) or {}).get("function") or ()
    return f'"{titles[0]}"' if titles else ""


def searches(kind: str, company: str = "", city: str | None = None) -> list:
    """The web searches one kind runs, filled in; [] for a kind with its own tool."""
    if kind not in KINDS:
        raise UnknownKind(kind)
    import discovery
    k = KINDS[kind]
    if kind == "title_search":
        return discovery.queries_for(company, skip=spent_titles(company)) if company else \
            discovery.queries_for(company)
    if kind == "alumni_employer":
        # A turn each: the first search of every past employer before the second of
        # any, so no one employer takes the lot.
        return _round_robin([discovery.queries_for(past, mode="alumni_employer",
                                                   location=city or discovery.HOME_CITY)
                             for past in _alumni_order()], ALUMNI_EMPLOYER_SEARCHES)
    if kind == "alumni_school":
        return [q for school in _schools() for q in
                discovery.queries_for(school, mode="alumni_school", location=city or discovery.HOME_CITY)][:1]
    if not _QUERY:
        plan()
    schools = _schools()
    fill = {"company": discovery.search_name(company) if company else "",
            "function": _function(), "city": city if city is not None else discovery.HOME_CITY,
            "country": person.country(), "school": schools[0] if schools else "",
            "year": str(datetime.date.today().year)}
    templates = (_QUERY[kind],) if _QUERY.get(kind) else k.searches
    if "{school}" in " ".join(templates) and not fill["school"]:
        return []
    out = []
    for t in templates:
        q = " ".join(t.format_map(_Blank(fill)).split())
        if not k.linkedin and "linkedin" not in q:
            q += " -site:linkedin.com"
        out.append(q)
    return out


# What each title search found at each employer: a title that found nobody worth
# writing to there is not searched there again for TITLE_YIELD_DAYS, and the next
# title in its group goes instead (discovery.queries_for, skip=).
TITLE_YIELD_FILE = ("documents", "network", ".title_yield.json")
UNPLACED_PENALTY = 10
TITLE_YIELD_DAYS = 90


def _yields() -> dict:
    import json
    try:
        with open(person.state(*TITLE_YIELD_FILE), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _title_in(query: str) -> str:
    """The person's own title a search ran for, as TITLE_SETS spells it, or ""."""
    import discovery
    q = " ".join(str(query or "").lower().replace('"', " ").split())
    found = [t for g in discovery.TITLE_SETS.values() for t in g
             if " ".join(t.lower().split()) and " ".join(t.lower().split()) in q]
    return max(found, key=len) if found else ""


def record_yield(company: str, query: str, kept: int, placed: int,
                 today: datetime.date | None = None) -> str:
    """Keep what one title search found at one employer. Returns the title, or "" when
    the query names none of the person's titles."""
    import json
    import company_key
    title = _title_in(query)
    key = company_key.key(company)
    if not title or not key:
        return ""
    got = _yields()
    got.setdefault(key, {})[title] = {"kept": int(kept), "placed": int(placed),
                                      "date": (today or datetime.date.today()).isoformat()}
    p = person.state(*TITLE_YIELD_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(got, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return title


def spent_titles(company: str, today: datetime.date | None = None) -> list:
    """The titles that found nobody worth writing to at this employer in TITLE_YIELD_DAYS."""
    import company_key
    today = today or datetime.date.today()
    out = []
    for title, rec in (_yields().get(company_key.key(company)) or {}).items():
        try:
            age = (today - datetime.date.fromisoformat(rec.get("date", ""))).days
        except ValueError:
            continue
        if age <= TITLE_YIELD_DAYS and not rec.get("kept"):
            out.append(title)
    return out


def _round_robin(lists: list, cap: int) -> list:
    """The first of each, then the second of each, up to `cap`: every kind gets a turn."""
    out, depth = [], 0
    while len(out) < cap and any(len(l) > depth for l in lists):
        out += [l[depth] for l in lists if len(l) > depth][:cap - len(out)]
        depth += 1
    return out


def ruled_out(company: str) -> str:
    """Why no search should be spent on this employer, or "".

    The job search's own verdicts, read rather than repeated: a sector or employer
    the person excluded (tools/bar.py), or an entry in job_scraper/do_not_target.json
    saying there is no relevant team there. Two local lookups, no search.
    """
    import bar
    import throttle
    from company_key import key
    verdict, why = bar.verdict(company)
    if verdict == bar.EXCLUDED:
        return why
    return throttle.load_do_not_target().get(key(company), "")


def for_company(company: str, rows=None) -> list:
    """(kind, search) for one employer, best kinds first, at most SEARCHES_PER_COMPANY.

    None at all for an employer the job search has already ruled out."""
    if ruled_out(company):
        return []
    rows = ranked() if rows is None else rows
    kinds = [kind for kind, _, _ in rows if KINDS[kind].scope == "per_company"]
    titles = ([("title_search", q) for q in searches("title_search", company)][:TITLE_SEARCHES]
              if "title_search" in kinds else [])
    return titles + _round_robin([[(kind, q) for q in searches(kind, company)] for kind in kinds
                                  if kind != "title_search"], SEARCHES_PER_COMPANY - len(titles))


def to_check(people: list) -> list:
    """The name-only people worth a profile check (linkedin_check), in the order given
    (best first), at most CHECKS_PER_COMPANY. The rest wait, said so, for a later run."""
    return [p for p in people if p.get("name_only")][:CHECKS_PER_COMPANY]


def for_run(rows=None) -> list:
    """(kind, "search" or "fetch", what) once for the whole run, at most SEARCHES_PER_RUN.

    Everyone these surface is matched to the run's employers (`discovery.alumni_at`
    for the alumni searches, the employer named beside each speaker on a roster).
    """
    import discovery
    rows = ranked() if rows is None else rows
    lists = []
    for kind, detail, _ in rows:
        if KINDS[kind].scope != "per_run":
            continue
        if kind == "roster":
            todo = [(kind, "fetch", url) for _, url, _ in discovery.roster_first()]
            if detail.startswith("http"):
                todo.insert(0, (kind, "fetch", detail))
        else:
            todo = [(kind, "search", q) for q in searches(kind)]
        lists.append(todo)
    return _round_robin(lists, SEARCHES_PER_RUN)


def _past_employers(contacts=None) -> list:
    """The employers they have left: the one whose alumni have replied most first,
    then the most recently left.

    Never the one they work at now: people there are colleagues, not alumni, and
    a job search is often kept from the current employer. A role whose end the
    profile does not date keeps its place after the dated ones. Replies are counted
    from the contact book: alumni contacts whose route names that employer and who
    have answered (throttle.RESPONDED), so a past employer whose people answer is
    searched every run, not every other day.
    """
    import reading
    h = reading.history()
    names = {n[0]: n for n in h["employers"] if n[0] not in h["current"]}
    ended = h["ended"]
    replied = _alumni_replies(names, contacts)
    return sorted(names, key=lambda n: (-replied.get(n, 0), ended.get(n) is None,
                                        -(ended[n].toordinal() if ended.get(n) else 0)))


def _alumni_replies(employers: dict, contacts=None) -> dict:
    """{employer: how many of its alumni in the contact book have replied}."""
    import reading
    import throttle
    if contacts is None:
        try:
            import state
            contacts = state.load_contacts()
        except Exception:  # noqa: BLE001  no book yet: recency alone orders them
            contacts = []
    out: dict[str, int] = {}
    for c in contacts or ():
        if not str(c.get("route") or "").startswith("alumni_employer"):
            continue
        if str(c.get("status") or "") not in throttle.RESPONDED:
            continue
        detail = str(c.get("route_detail") or "")
        for first, aka in employers.items():
            if any(reading._has(a, detail) for a in aka):
                out[first] = out.get(first, 0) + 1
                break
    return out


def _alumni_order(today: datetime.date | None = None, contacts=None) -> list:
    """The employers they have left, in the order a run searches them.

    The one most recently left always goes first. The rest take turns behind it, one
    place a day: an alumni search finds much the same people each time it runs, and
    a run has room for only a few, so the same two searched every run would leave an
    older employer's alumni never searched at all.
    """
    past = _past_employers(contacts)
    if len(past) < 3:
        return past
    rest = past[1:]
    turn = (today or datetime.date.today()).toordinal() % len(rest)
    return [past[0]] + rest[turn:] + rest[:turn]


def _schools() -> list:
    import reading
    return list(reading.history()["schools"])


def linkedin_check(name: str, company: str) -> str:
    """Rung 3, the search that finds a named person's LinkedIn profile: run it with
    allowed_domains=discovery.SEARCH_DOMAINS, read the result, never fetch it, and give
    the results to harvest(..., kind="profile_check", name=<their name>, known=<what the
    page that named them said>), which keeps only them. Plain words with the name
    quoted: the form that found a named person's profile first, titled with their
    employer (2026-10-18). At most CHECKS_PER_COMPANY an employer (to_check)."""
    import discovery
    return f'"{name}" {discovery.search_name(company)}'


def _cli_ladder(argv: list) -> int:
    tools = []
    if "--tools" in argv:
        tools = [t for t in argv[argv.index("--tools") + 1].split(",") if t.strip() not in ("", "none")]
    got = ladder(tools)
    for i, (rung, usable, why) in enumerate(got["rungs"], 1):
        print(f"  {i}. {'yes' if usable else 'no '} {rung.label}: {rung.yields} [{why}]")
    print(f"read: {got['read']}, "
          + ("no browser reads in this chat" if got["read_cap"] == 0
             else f"at most {got['read_cap']} in the browser this run" if got["read_cap"]
             else "in the browser, one page at a time, with no cap of the app's own")
          + (f"; a paste offered for the best {got['hand_top']} at most" if got["hand_top"] else ""))
    if got["say"]:
        print(f"tell them, once, under the list: {got['say']}")
    return 0


def _cli_harvest(argv: list) -> int:
    import json
    path = argv[0]
    opt = {k: argv[argv.index(k) + 1] for k in ("--company", "--kind", "--query", "--out")
           if k in argv}
    with open(path, encoding="utf-8") as fh:
        got = json.load(fh)
    results = got.get("results", got) if isinstance(got, dict) else got
    company = opt.get("--company", "")
    if not company.strip():
        return _print_across(harvest_across(results, opt.get("--kind", "title_search"),
                                            opt.get("--query", "")))
    run = harvest(results, company, opt.get("--kind", "title_search"), opt.get("--query", ""))
    c = run["counts"]
    print(f"{company}: {c['results']} results, {c['people']} people named, {c['kept']} kept "
          f"({c['verified']} with a profile titled with the employer)")
    for i, p in enumerate(run["keep"], 1):
        print(f"  {i}. {p['why']['score']:>3} {p['name']}: {p.get('title') or '(no title in the result)'}"
              f" [{p.get('profile_status')}, {p.get('route')}] {p.get('linkedin_url')}\n"
              f"       why: {p['why']['line']}\n       evidence: {p.get('evidence')}"
              + (f"\n       ask first: {p['maybe_in_book']}" if p.get("maybe_in_book") else ""))
    for p, why in run["dropped"]:
        print(f"  dropped {p.get('name')}: {why}")
    if c.get("in_book"):
        # "Already in your contact book" is not "already written to": a run told a person
        # their best employers were covered when nobody there had had a message.
        print(f"{company}: {c['in_book']} in the contact book already, {c['never_messaged']} of "
              "them never messaged" + (f" (to write to them: python3 tools/network/state.py reopen "
                                       f"--where company=\"{company}\" --where status=dropped "
                                       "--reason ...)" if c["never_messaged"] else ""))
    if "--out" in opt:
        with open(opt["--out"], "w", encoding="utf-8") as fh:
            json.dump({**run, "dropped": [{"person": p, "why": w} for p, w in run["dropped"]]},
                      fh, indent=1, default=str)
    return 0


def _print_across(got: dict) -> int:
    c = got["counts"]
    print(f"a search by title across employers: {c['results']} results, {c['kept']} people kept "
          f"at {c['employers'] - c['ruled_out']} employer(s)"
          + (f", {c['ruled_out']} employer(s) ruled out" if c["ruled_out"] else "")
          + (f", {c['unplaced']} whose result names no employer" if c["unplaced"] else ""))
    for emp, why, run in got["employers"]:
        if why:
            print(f"  {emp}: nothing kept ({why})")
            continue
        print(f"  {emp}: {len(run['keep'])} kept")
        for i, p in enumerate(run["keep"], 1):
            print(f"    {i}. {p['why']['score']:>3} {p['name']}: "
                  f"{p.get('title') or '(no title in the result)'} "
                  f"[{p.get('profile_status')}, {p.get('route')}] {p.get('linkedin_url')}"
                  + (f"\n         ask first: {p['maybe_in_book']}" if p.get("maybe_in_book") else ""))
        for p, why_ in run["dropped"]:
            print(f"    dropped {p.get('name')}: {why_}")
    for p in got["unplaced"]:
        print(f"  no employer named: {p.get('name')}, {p.get('title') or '?'}: a search at an "
              "employer, or a read, places them before a note")
    return 0


COMMANDS = ("ladder", "harvest", "import-connections", "while-you-wait", "people-paste",
            "connections")


def _usage() -> str:
    """The Usage section of this file's docstring."""
    doc = __doc__ or ""
    return doc[doc.find("Usage:"):].rstrip() if "Usage:" in doc else doc.strip()


def _not_an_employer(arg: str) -> bool:
    """Is this argument a flag or a file rather than an employer? `--help`, or a command
    spelled wrong with its file after it, was searched as an employer."""
    a = str(arg or "").strip()
    return a.startswith("-") or bool(re.search(r"\.(?:json|csv|txt|md|zip)$", a, re.I))


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in argv):
        print(_usage())
        return 0
    if argv and argv[0] in COMMANDS and argv[0] not in ("ladder", "while-you-wait") \
            and len(argv) < {"people-paste": 3}.get(argv[0], 2):
        print(f"sources: {argv[0]} needs more than that.\n{_usage()}")
        return 2
    if argv and argv[0] == "harvest" and not os.path.isfile(argv[1]):
        print(f"sources: no file {argv[1]!r}: harvest reads a saved file of search results")
        return 1
    bad = [a for a in argv if _not_an_employer(a)] if argv and argv[0] not in COMMANDS else []
    if bad:
        print(f"sources: {bad[0]!r} is not an employer or a command here.\n{_usage()}")
        return 2
    if argv and argv[0] == "ladder":
        return _cli_ladder(argv[1:])
    if argv and argv[0] == "harvest" and len(argv) > 1:
        return _cli_harvest(argv[1:])
    if argv and argv[0] == "import-connections" and len(argv) == 2:
        try:
            print(import_connections(argv[1]))
        except (OSError, ValueError) as e:
            print(f"sources: nothing saved: {e}")
            return 1
        return 0
    if argv and argv[0] == "while-you-wait":
        print(while_you_wait())
        return 0
    if argv and argv[0] == "people-paste" and len(argv) >= 3:
        degree = argv[3] if len(argv) > 3 else ""
        with open(argv[2], encoding="utf-8") as fh:
            people = from_people_paste(fh.read(), argv[1], degree)
        if not people:
            print(f"sources: nobody in that paste reads as a person at {argv[1]}")
            return 1
        for i, p in enumerate(people, 1):
            how = "message (1st, no request)" if p.get("route") == "connection" else "connection request (2nd)"
            print(f"  {i}. {p['name']}: {p.get('title') or 'title not given'} [{how}]"
                  + (f" {p['linkedin_url']}" if p.get("linkedin_url") else ""))
        return 0
    if argv and argv[0] == "connections" and len(argv) > 1:
        held: list = []
        for p in from_connections(argv[1], held=held):
            print(f"  {p['name']}: {p.get('title')} ({p.get('evidence')}) {p.get('linkedin_url')}"
                  + (f"\n    ask first: {p['maybe_in_book']}" if p.get("maybe_in_book") else "")
                  + "".join(f"\n    {w}" for w in p.get("warn", ())))
        for p, why in held:
            print(f"  not shown, {p.get('name')}: {why}")
        return 0
    import state
    try:
        rows = ranked(state.load_contacts(), state.load_threads())
    except UnknownKind as e:
        print(f"sources: {e}")
        return 1
    if not argv:
        own = bool(getattr(_NET, "PEOPLE_SOURCES", None))
        print(f"where to find people ({'researched for you' if own else 'the default plan'}):")
        for i, (kind, detail, why) in enumerate(rows, 1):
            k = KINDS[kind]
            print(f"  {i}. {k.label}: {k.finds} [{why}]" + (f"\n       {detail}" if detail else ""))
        return 0
    print("once for the run:")
    for kind, how, what in for_run(rows):
        print(f"  {kind} ({how}): {what}{_NAMES_ONLY if not KINDS[kind].linkedin else ''}")
    for company in argv:
        why = ruled_out(company)
        if why:
            print(f"for {company}: nothing searched ({why})")
            continue
        print(f"for {company}:")
        for kind, q in for_company(company, rows):
            print(f"  {kind}: {q}{_NAMES_ONLY if not KINDS[kind].linkedin else ''}")
        print(f"  then at most {CHECKS_PER_COMPANY} profile checks, for the best name-only "
              f"people found (sources.to_check, sources.linkedin_check)")
    return 0


# ------------------------------------------------------------------ the ladder

# How a run finds people and what it reads about them, cheapest and safest first.
# Bulk discovery never depends on reading anyone: rungs 1 to 3 make the list from
# any chat (a phone, the web, a cloud chat with no browser), and reading, rungs 4
# and 5, only enriches a short list of it. A run with no browser still delivers the
# whole ranked list, says in one line what reading would add, and offers a paste
# for at most reading.HAND_TOP people; it never asks for a screenshot of everyone.
# Browser reads have no cap of the app's own (reading.shortlist_cap): the people a run will
# write to, one page at a time.
Rung = namedtuple("Rung", "id label yields cannot needs")
LADDER = (
    Rung("connections", "your own LinkedIn connections export",
         "everyone you already know at the employer, in bulk, each with their profile "
         "address; read only, and it contacts nobody",
         "people you are not connected to", "the export, downloaded by you once"),
    Rung("public_web", "public pages and search results",
         "named people at the employer in bulk: profile results titled with their employer, "
         "team and leadership pages, speaker lists, papers, code and press",
         "what a profile says beyond its title", "web search, in any chat"),
    Rung("exists", "a profile check from search results",
         "whether a named person has a LinkedIn profile at the employer, verified or likely, "
         "from the result's own title; nothing is fetched",
         "anything the profile says", "web search, in any chat"),
    Rung("browser_read", "a read in your own browser",
         "the profile itself, for the short list only: current role, location, shared "
         "history, recent posts, and whether a request is already pending",
         "anyone beyond the short list", "a browser of yours this chat can use, and your yes"),
    Rung("hand", "a paste or screenshots from you",
         "one or two profiles you care most about, read from what you send",
         "a list: it is never how people are found", "you, a few seconds each"),
)


def ladder(tools=(), consent: str | None = None, has_export: bool | None = None) -> dict:
    """What this run can use from the ladder, for the tools this chat has.

    `tools` as reading.route() takes them (browser, chrome, chrome-off, enable).
    Returns {"rungs": [(Rung, usable, why)], "read": route, "read_cap": None for no cap of
    the app's own, 0 where nothing is read in the browser,
    "hand_top": n, "say": the one line for the person, or ""}.
    """
    import reading
    r = reading.route(list(tools or ()), consent)
    # None: no cap of the app's own on browser reads (reading.shortlist_cap); 0: none here.
    cap = reading.shortlist_cap()[0] if r["route"] in ("browser", "enable") else 0
    export = _has_export() if has_export is None else has_export
    declined = CONNECTIONS_EXPORT == "declined"
    reads = r["route"] in ("browser", "enable")
    rungs = []
    for rung in LADDER:
        if rung.id == "connections":
            usable = export
            why = ("on file" if export
                   else "declined for now: asked again when what it offers changes, or after "
                        "a while (the connections-export upgrade)" if declined
                   else "not on file yet: the connections-export upgrade asks")
        elif rung.id == "browser_read":
            usable = reads
            why = (f"{r['browser']}, the people worth writing to, one page at a time"
                   if reads
                   else "no browser of yours in this chat" if reading.PROFILE_READS == "browser"
                   else f"PROFILE_READS is {reading.PROFILE_READS!r}")
        elif rung.id == "hand":
            usable = not reads
            why = f"offered for the best {reading.HAND_TOP} at most" if not reads else "not needed"
        else:
            usable, why = True, "any chat"
        rungs.append((rung, usable, why))
    say = "" if reads else (
        "These were found from search results" + (" and your connections" if export else "")
        + ", without reading anyone's profile. Reading a profile adds their current role, "
        "shared history and recent posts; for the one or two who matter most, send "
        + reading.what_to_send(reading.surface()) + ", and I'll write to them from it.")
    return {"rungs": rungs, "read": r["route"], "read_cap": cap,
            "hand_top": 0 if reads else reading.HAND_TOP, "say": say}


def from_connections(company: str, connections=None, contacts=None, threads=None,
                     held=None) -> list:
    """Rung 1: the person's own connections at one employer, best first, each one
    `surface.check` lets through: nobody in the contact book, nobody written to on any
    channel, nobody at an employer the bar rules out. Nothing searched, nothing fetched,
    nobody contacted. `held`, a list, collects (person, reason) for everyone left out.

    In their function first (discovery.FUNCTION_TITLE), then the hands-on titles that
    reply most (discovery.reply_rank), then the most recently connected. The file has no
    location, so nobody here is placed; a connection made long ago carries the warning
    that their employer and title may have changed since (`needs_read`).
    """
    import discovery
    import state
    import surface
    conns = state.first_degree() if connections is None else connections
    ctx = surface.context(contacts=contacts, threads=threads, connections=conns)
    out = []
    for c in state.connections_at(conns, company):
        # Checked at the employer asked about: the file may name it by a business line
        # ("<Name> Ratings"), and its own name is kept as the other one they go by.
        got = surface.check(dict(c, company=company, also_company=c.get("company")), ctx)
        if not got["show"]:
            if held is not None:
                held.append((c, got["reason"]))
            continue
        asks = [w[len("ask first: "):] for w in got["warn"] if w.startswith("ask first: ")]
        if asks:
            c = {**c, "maybe_in_book": asks[0]}
        old = got["needs_read"]
        out.append({**c, "found_via": "connections", "route": "connection",
                    "route_detail": "in your connections", "first_degree": True,
                    "channel": "message", "profile_status": "verified",
                    "location_unverified": True,
                    **({"reverify": True, "needs_read": True} if old else {}),
                    "warn": [w for w in got["warn"] if not w.startswith("ask first: ")],
                    "evidence": "your connections export"
                                + (f", connected {c['connected_on']}" if c.get("connected_on") else "")})

    import export

    def key(p):
        in_function = bool(discovery.FUNCTION_TITLE.search(p.get("title") or ""))
        rank, _ = discovery.reply_rank({**p, "route": ""})
        when = export.day(p.get("connected_on") or "")
        return (not in_function, rank, -(when.toordinal() if when else 0))
    return sorted(out, key=key)


# LinkedIn's Connections.csv is a few hundred kilobytes for most people; a file far past
# this is not one, and is not read into memory to find out.
CONNECTIONS_MAX_BYTES = 20 * 1024 * 1024


def import_connections(src: str, dest: str | None = None) -> str:
    """Save LinkedIn's Connections.csv into documents/linkedin/, from the file itself, or the
    whole export from the archive or folder it came in, and return what to tell the person.

    Given the archive or its folder, the export is taken whole (`export.take`): every file
    the app reads is saved and the message history imported into the log, in one step.
    Reading Connections.csv alone from it left the person's messages unsaved, and a chat
    read them straight from the download and kept none of it (2026-10-21). Nothing else in
    the archive is opened. The file starts with a few lines of notes above its header,
    which state.first_degree() finds; one with no connection under a "First Name" header is
    refused, and nothing is saved."""
    import zipfile
    import export
    if zipfile.is_zipfile(src) or os.path.isdir(src):
        got = export.read("connections", src)
        if not got["where"]:
            raise ValueError("there is no Connections.csv in that download: it is probably "
                             "the shorter download, which leaves connections out")
        # Counted, and refused, from the download itself: an empty or header-less file was
        # saved over the good one kept, or "saved" while the old one was counted.
        count = sum(1 for r in got["rows"] if str(r.get("First Name") or "").strip()
                    or str(r.get("Last Name") or "").strip())
        if not count:
            raise ValueError("the Connections.csv in that download has no connections in it: "
                             "no row under a \"First Name\" header, which is how LinkedIn "
                             "writes it. Nothing was saved, and the copy kept here is as it was")
        lines = export.take([src])
        return " ".join([f"Saved your {count} connections."] + lines)
    dest = dest or os.path.join(export.home(), "Connections.csv")
    if os.path.getsize(src) > CONNECTIONS_MAX_BYTES:
        raise ValueError("that file is too large to be LinkedIn's Connections.csv")
    with open(src, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8-sig", errors="replace")
    # The one reader of every export file (tools/network/export.py), which state.first_degree
    # reads through too: a header in any case, below its notes.
    got = export.parse(text, "connections")
    count = sum(1 for r in got["rows"]
                if str(r.get("First Name") or "").strip() or str(r.get("Last Name") or "").strip())
    if not count:
        raise ValueError("that file has no connections in it: no row under a \"First Name\" "
                         "header, which is how LinkedIn writes Connections.csv")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return f"Saved your {count} connections."


def while_you_wait(tracker=None) -> str:
    """The quicker route to the people who matter most while the export is on its way,
    offered once with its steps: one employer's 1st-degree people, pasted, starting
    where an interview is running."""
    import csv
    rows = tracker
    if rows is None:
        try:
            with open(person.state("job_search_tracker.csv"), encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            rows = []
    live = next((str(r.get("company") or "").strip() for r in reversed(rows)
                 if str(r.get("status") or "").strip().lower() == "interview"
                 and str(r.get("company") or "").strip()), "")
    where = f"{live}, where you are interviewing" if live else "the employer that matters most to you now"
    return (f"While you wait, the people who matter most can come first, starting with {where}: "
            "paste me its 1st-degree people and I'll draft a message to each, no connection "
            "request needed. Want the steps for that?")


# One person in a paste of LinkedIn's people search: their degree is written beside the
# name ("Name \u2022 1st") or on a line of its own ("\u2022 1st", "1st degree connection").
_DEGREE = re.compile(r"(?:^|[\s\u2022\u00b7])(1st|2nd|3rd\+?)(?:\s+degree(?:\s+connection)?)?\s*$",
                     re.I)
_PROFILE_LINK = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s)>\]\"']+", re.I)
# What a search result's card says that is neither their job nor where they are.
_CARD_NOISE = re.compile(r"^(?:view\b.*\bprofile|message|connect|follow|following|pending|"
                         r"send inmail|status is \w+|.*\bmutual connections?\b|current:|past:|"
                         r"summary:|skills:|open to work|provides services|premium|\d+ followers?|"
                         # The page's own links and buttons: "View full list" was read as a
                         # person on every people-search page (2026-10-19).
                         r"view full list$|(?:see|show|view) all\b|load more$|show more results$|"
                         r"try premium\b|learn more$|dismiss$|next$|previous$|"
                         r"are these results helpful\b)",
                         re.I)
# LinkedIn's own cards on a people-search page, never a person: "Looking to get hired?"
# with its list of jobs and employers, ending "View full list", a Premium offer, an ad.
# A card runs from its first line to its last ("View full list", "See all"), or stops
# before the next person's card (a degree beside a name), and never runs past
# _PROMO_MAX lines: with no end in sight only its first line is dropped, so a real card
# is never swallowed.
_PROMO_START = re.compile(r"^(?:looking to get hired\b.*|are you (?:looking|hiring)\b.*|"
                          r"jobs where you\b.*|try premium\b.*|(?:reactivate|unlock) premium\b.*|"
                          r"get hired faster\b.*|promoted|sponsored|people you may know|"
                          r"people also viewed)$", re.I)
_PROMO_END = re.compile(r"^(?:view full list|(?:see|show|view) all\b.*|see more jobs|"
                        r"try (?:it )?(?:for )?free\b.*|learn more|dismiss)$", re.I)
_PROMO_MAX = 15


def _promo_lines(lines: list) -> set:
    """Indices of `lines` inside LinkedIn's own cards (_PROMO_START to _PROMO_END)."""
    out, i = set(), 0
    while i < len(lines):
        if not _PROMO_START.match(lines[i]):
            i += 1
            continue
        end = i + 1
        for j in range(i + 1, min(len(lines), i + 1 + _PROMO_MAX)):
            if _PROMO_END.match(lines[j]):
                end = j + 1
                break
            m = _DEGREE.search(lines[j])
            if m:
                # A person's card: theirs starts at the name, the line before a degree
                # written on its own line, or this line when it carries both.
                end = j - 1 if not lines[j][:m.start()].strip(" \u2022\u00b7-") else j
                break
        out.update(range(i, max(end, i + 1)))
        i = max(end, i + 1)
    return out


def people_paste(text: str, company: str, degree: str = "") -> list:
    """[{name, title, location, linkedin_url, degree}] from a paste of LinkedIn's people
    search for one employer, or a screenshot of it written out the same way. `degree`
    is for a paste that carries none, such as one filtered to 1st already. LinkedIn's
    own cards on the page (_PROMO_START) are never read as people."""
    import discovery
    lines = [ln.strip() for ln in str(text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    promo = _promo_lines(lines)
    lines = [ln for i, ln in enumerate(lines) if i not in promo]
    out, cur, want = [], None, ""
    for ln in lines:
        link = _PROFILE_LINK.search(ln)
        if link:
            if cur is not None and not cur["linkedin_url"]:
                cur["linkedin_url"] = link.group(0).rstrip(".,")
            continue
        m = _DEGREE.search(ln)
        head = ln[:m.start()].strip(" \u2022\u00b7-") if m else ln
        if (head and discovery._a_person(head, company) and not _CARD_NOISE.match(head)
                and not discovery._ROLE_WORD.search(head) and not discovery._AT.search(head)
                and not discovery._is_place(head)):
            cur = {"name": head, "title": "", "location": "", "linkedin_url": "",
                   "degree": (m.group(1).lower() if m else "") or degree}
            out.append(cur)
            want = "title"
            continue
        if cur is None:
            continue
        if m and not head:
            cur["degree"] = m.group(1).lower()
            continue
        if _CARD_NOISE.match(ln):
            continue
        if want == "title":
            cur["title"], want = ln, "location"
        elif want == "location":
            if discovery._is_place(ln):
                cur["location"] = ln
            want = ""
    for p in out:
        p["degree"] = p["degree"].rstrip("+") if p["degree"] else (degree or "")
    return out


def from_people_paste(text: str, company: str, degree: str = "", contacts=None) -> list:
    """The people a paste of one employer's people search names, ranked: 1st-degree
    connections first, each a message with no connection request (route "connection"),
    as from_connections ranks them; then 2nd-degree, each a connection request. Anyone
    already in the contact book is left out. Needs no browser: the person pastes."""
    import state
    got = [p for p in people_paste(text, company, degree) if p["name"]]
    if contacts is None:
        contacts = state.load_contacts() if os.path.exists(state.CONTACTS_CSV) else []
    first = [dict(p, company=company) for p in got if p["degree"] == "1st"]
    ranked = [dict(p, evidence="your paste of LinkedIn's people search, 1st-degree")
              for p in from_connections(company, connections=first, contacts=contacts)]
    import discovery
    import surface
    ctx = surface.context(contacts=contacts)
    second = []
    for p in got:
        if p["degree"] != "2nd" or not surface.check(dict(p, company=company), ctx)["show"]:
            continue
        rank, _ = discovery.reply_rank({**p, "route": ""})
        second.append((not discovery.FUNCTION_TITLE.search(p["title"] or ""), rank, p))
    second.sort(key=lambda x: (x[0], x[1]))
    ranked += [dict(p, company=company, found_via="people_paste", route="",
                    route_detail="2nd-degree: you share connections", channel="connection",
                    evidence="your paste of LinkedIn's people search, 2nd-degree")
               for _, _, p in second]
    for p in ranked:
        p["found_via"] = "people_paste"
    return ranked


def harvest(results, company: str, kind: str = "title_search", query: str = "",
            today: datetime.date | None = None, connections=None, contacts=None,
            name: str = "", known: dict | None = None, remember: bool = True) -> dict:
    """Rungs 2 and 3 for one employer: search results to a ranked list, nothing fetched.

    The results' own titles say who each person is and where they work
    (discovery.people_from_results); discovery.triage() drops the moved-on, the
    elsewhere-based and the wrong function; anyone already in the contact book is
    dropped; their own connections are marked as a message rather than a request;
    and why.why_them() ranks the rest. Returns {"keep": [...], "dropped": [(p, why)],
    "counts": {...}}; every kept person carries `evidence`, `profile_status` and
    `route`, and nobody is asked for anything.

    `name` is a profile check's: only that person is kept, never the others the same
    results happen to name. `known` is what the page that named them said ({"title",
    "evidence"}, a speaker list's "AVP, Data Platforms"): the title fills in
    where the result gives none, so a named leader no longer ranks with the unknowns.
    """
    import discovery
    import state
    import why
    today = today or datetime.date.today()
    people = discovery.people_from_results(results, company, kind=kind, query=query, today=today)
    if name:
        want = state._match_name(name)
        people = [p for p in people if state._match_name(p["name"]) == want]
        for p in people:
            if known and known.get("title") and not p.get("title"):
                p["title"], p["title_source"] = known["title"], known.get("evidence") or "the page that named them"
            if known and known.get("evidence"):
                p["evidence"] = f"{known['evidence']}; then {p['evidence']}"
    t = discovery.triage(people, today=today, target_company=company)
    if contacts is None:
        contacts = state.load_contacts() if os.path.exists(state.CONTACTS_CSV) else []
    conns = state.first_degree() if connections is None else connections
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    import surface
    ctx = surface.context(contacts=contacts, threads=threads, connections=conns, today=today)
    keep, dropped = [], list(t["dropped"])
    for p in discovery.mark_first_degree(t["keep"], conns):
        # The one check (surface.py): the book, their whole thread, the bar, a hold.
        got = surface.check(dict(p, company=company), ctx)
        if not got["show"]:
            dropped.append((p, got["reason"]))
            continue
        # A nickname, an initial or a typo of somebody already in the book: kept, never
        # dropped on a guess, and never added as a stranger either. The person is asked.
        asks = [w[len("ask first: "):] for w in got["warn"] if w.startswith("ask first: ")]
        if asks:
            p["maybe_in_book"] = asks[0]
        p.setdefault("route", "connection" if p.get("first_degree") else "cold")
        p.setdefault("company", company)
        if query and kind == "title_search" and not p.get("title"):
            # Only a title search looks for a job. A posts, press or name search would
            # put its operators, or the person's own name, where the job goes.
            p["found_for"] = _searched_for(query, company)
        p["why"] = why.why_them(p, today=today, roles=[])
        keep.append(p)
    # Stable: people the scores cannot tell apart keep the search engine's order. Anyone
    # nothing has placed yet gives up UNPLACED_PENALTY points against people placed in
    # the person's market: a deep read spent finding out where somebody is was the
    # commonest waste. A penalty, not a bottom: a hiring manager with no place in their
    # result still outranks a placed name with no job at all.
    keep.sort(key=lambda p: (-(p["why"]["score"] - (UNPLACED_PENALTY if p.get("location_unverified") else 0)),
                             discovery.PROFILE_STATUS.index(p.get("profile_status") or "unconfirmed")))
    if kind == "title_search" and query and not name and remember:
        record_yield(company, query, len(keep),
                     sum(1 for p in keep if not p.get("location_unverified")), today)
    book = state.book_at(contacts, threads, company) if company else {"in_book": 0, "never_messaged": 0}
    return {"keep": keep, "dropped": dropped,
            "counts": {"results": len(results or ()), "people": len(people), "kept": len(keep),
                       "verified": sum(p.get("profile_status") == "verified" for p in keep),
                       "in_book": book["in_book"], "never_messaged": book["never_messaged"]}}


def harvest_across(results, kind: str = "title_search", query: str = "",
                   today: datetime.date | None = None, connections=None, contacts=None) -> dict:
    """One search by title across employers ("<title> <city>", no employer in it) feeding
    every employer it found: the results grouped by the employer each result's own title
    names, each employer checked the way every list of people is (`surface.employer_out`: the
    bar, do_not_target.json, a finding of no relevant team there), and each group harvested
    as a search at that employer would be. A result that names no employer is never filed under one.

    {"employers": [(employer, why ruled out or "", harvest run or None)], "unplaced":
    [people], "counts": {...}}, the employer with most people kept first. A title search
    that found nobody somewhere is not remembered against that employer's titles (it was
    not a search there)."""
    import discovery
    from company_key import key as company_key
    today = today or datetime.date.today()
    groups: dict = {}
    unplaced = []
    for r in results or ():
        got = discovery.people_from_results([r], "", kind=kind, query=query, today=today)
        if not got:
            continue
        emp = str(got[0].get("company") or "").strip()
        if not emp:
            unplaced.append(got[0])
            continue
        name, rows = groups.get(company_key(emp), (emp, []))
        rows.append(r)
        groups[company_key(emp)] = (name, rows)
    import surface
    out = []
    for _k, (emp, rows) in groups.items():
        why = surface.employer_out(emp, today)
        if why:
            out.append((emp, why, None))
            continue
        out.append((emp, "", harvest(rows, emp, kind, query, today=today, connections=connections,
                                     contacts=contacts, remember=False)))
    out.sort(key=lambda g: (g[2] is None, -(len(g[2]["keep"]) if g[2] else 0), g[0].lower()))
    kept = sum(len(run["keep"]) for _e, _w, run in out if run)
    return {"employers": out, "unplaced": unplaced,
            "counts": {"results": len(results or ()), "employers": len(out), "kept": kept,
                       "ruled_out": sum(1 for _e, w, _r in out if w),
                       "unplaced": len(unplaced)}}


def _searched_for(query: str, company: str) -> str:
    """The words a search added to the employer and the city: the job it looked for."""
    import discovery
    q = re.sub(r"\S+:\S+|-\S+|[()\"]|\bOR\b|\bAND\b", " ", query)
    for w in (discovery.search_name(company), company, discovery.HOME_CITY, "hiring"):
        if w:
            q = re.sub(r"(?<!\w)" + re.escape(w) + r"(?!\w)", " ", q, flags=re.I)
    return " ".join(q.split())


# Which kinds can produce someone a request can go to. A LinkedIn result carries
# their profile's address; every other kind (press, team pages, speaker lists)
# names a person, and that name has to be found on LinkedIn before any request:
# sources.linkedin_check, or the person's own search in their browser.
_NAMES_ONLY = "  [names only: find each on LinkedIn before a request]"


def short_batch(found: int, wanted: int, tried: dict, have_connections: bool = False,
                browser: bool = False, named: int = 0) -> str:
    """What to say when the run's searches are spent and the batch is not full.

    Never padded with weaker names. `tried` is {kind: people worth writing to it
    found}. `named` is everyone the run kept, when more than `found` (those it could
    write to now): the rest are named but need a look first, and the count says so
    rather than reading as if nobody else turned up. The ways to more people are the
    person's own: the people they already know (their connections export), the People
    tab of each employer in their own browser, or names they know of.
    """
    if found >= wanted:
        return ""
    parts = ", ".join(f"{KINDS[k].label if k in KINDS else k} {n}" for k, n in tried.items())
    more = []
    if not have_connections:
        # The path itself is dated and sourced in tools/claude_surfaces.json
        # (linkedin-connections), given when they say yes, never pasted unasked.
        more.append("your LinkedIn connections, so I start from people you already know: "
                    "one file from LinkedIn, which takes anything from ten minutes to a day "
                    "to arrive, and I'll walk you through it")
    if browser:
        more.append("each employer's People tab, read in your own browser like a profile")
    more.append("names of anyone you know of there, and I'll read and write to them")
    head = (f"I found {named} people; {found} of the {wanted} this run could write to have "
            f"enough known about them for a note, and the other {named - found} need a look "
            f"first (their results give no job). I stopped rather than pad the list."
            if named > found else
            f"I found {found} of the {wanted} people this run could write to, and stopped "
            f"rather than pad the list.")
    return (f"{head} What I tried: {parts or 'nothing returned'}. To find "
            f"more: " + "; or ".join(more) + ".")


if __name__ == "__main__":
    sys.exit(main())
