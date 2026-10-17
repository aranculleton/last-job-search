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
"""
from __future__ import annotations

import datetime
import os
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
        "everyone, with a browser linked", "local", (), True, "at a person's pace, nothing clicked"),
}

DEFAULT_PLAN = ("connections", "alumni_employer", "alumni_school", "posting", "posts",
                "title_search", "team_page", "roster", "press", "people_tab")

SEARCHES_PER_COMPANY = 4
SEARCHES_PER_RUN = 5          # the per_run kinds, together
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
    return os.path.exists(person.state("documents", "linkedin", "Connections.csv"))


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
        return discovery.queries_for(company)
    if kind == "alumni_employer":
        return [q for past in _past_employers() for q in
                discovery.queries_for(past, mode="alumni_employer", location=city or discovery.HOME_CITY)][:2]
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
    return _round_robin([[(kind, q) for q in searches(kind, company)] for kind, _, _ in rows
                         if KINDS[kind].scope == "per_company"], SEARCHES_PER_COMPANY)


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


def _past_employers() -> list:
    import reading
    return [names[0] for names in reading.history()["employers"]]


def _schools() -> list:
    import reading
    return list(reading.history()["schools"])


def linkedin_check(name: str, company: str) -> str:
    """The search that finds a person's LinkedIn profile: read the result URL, never fetch it."""
    import discovery
    return f'{discovery.SITE} "{name}" "{discovery.search_name(company)}"'


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
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
        print(f"  {kind} ({how}): {what}")
    for company in argv:
        why = ruled_out(company)
        if why:
            print(f"for {company}: nothing searched ({why})")
            continue
        print(f"for {company}:")
        for kind, q in for_company(company, rows):
            print(f"  {kind}: {q}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
