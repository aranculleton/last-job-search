"""Employer research fetches politely, within a budget, and remembers what each host did.

Measured on one real batch (2026-10-21): research agents spent 32 to 62 tool calls and
six to ten minutes each, and most of it went on retrying sites that block automated
readers. Several agents found the same bot check independently and read the same posts
through the same feed; nothing told the next agent, or the next round, what the last
one had learned about a host. Research already cached was fetched again, and one
agent's save replaced the facts another had saved.

`tools/company_research.py fetch` is now the one way in: robots.txt first, the site's
crawl delay kept, a feed or a sitemap when a page is behind a bot check, a note per host
that every later run reads first, a budget per employer, fresh facts never fetched
again, and quotes checked against the page as fetched. Every employer, host and page
here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import company_research as C  # noqa: E402

TODAY = dt.date(2026, 10, 21)
CHALLENGE = ("<html><head><title>Just a moment...</title></head><body>"
             "<script src='/cdn-cgi/challenge-platform/h/b/orchestrate'></script></body></html>")
ABOUT = ("<html><head><title>About Oakmere Foods</title></head><body><nav>Home | About</nav>"
         "<p>Oakmere Foods opened its second bakery site in Bolton in March 2026, and it now "
         "supplies 240 independent shops across the North West.</p>"
         "<p>We use cookies to improve your experience.</p></body></html>")
FEED = ("<?xml version='1.0'?><rss version='2.0'><channel><title>Oakmere careers</title>"
        "<item><title>Meet the demand planning team</title>"
        "<link>https://careers.oakmere.example/stories/demand-planning</link>"
        "<description>Our demand planning team rebuilt the weekly bakery forecast in 2026 "
        "and cut waste across 240 shops.</description><pubDate>Mon, 05 Oct 2026</pubDate>"
        "</item></channel></rss>")
ALLOW = "User-agent: *\nAllow: /\n"


class Web:
    """Canned answers by URL, every request recorded."""

    def __init__(self, routes):
        self.routes, self.calls, self.sleeps = routes, [], []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        got = self.routes.get(url)
        if got is None:
            return 404, {}, "not here"
        if callable(got):
            return got(url, headers)
        return got

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def got(self, url):
        return [u for u, _ in self.calls if u == url]


def _fetch(web, tmp_path, *urls, **kw):
    kw.setdefault("today", TODAY)
    return C.fetch("Oakmere Foods", urls, root=str(tmp_path), transport=web, sleep=web.sleep,
                   pages=str(tmp_path / "pages"), **kw)


def test_a_bot_check_is_noted_and_the_next_run_goes_straight_to_the_feed(tmp_path):
    web = Web({
        "https://careers.oakmere.example/robots.txt": (200, {}, ALLOW),
        "https://careers.oakmere.example/teams": (403, {}, CHALLENGE),
        "https://careers.oakmere.example/feed": (200, {}, FEED),
    })
    first = _fetch(web, tmp_path, "https://careers.oakmere.example/teams")
    states = [u["state"] for u in first["urls"]]
    assert states[0] == "challenged" and "feed" in states
    assert any("demand planning team rebuilt" in c["quote"] for c in first["candidates"])
    note = C.host_notes(str(tmp_path))["careers.oakmere.example"]
    assert note["status"] == "challenged" and note["feed"].endswith("/feed")
    first_requests = len(web.calls)

    # The next agent, or the next round, reads the note: no request to the page behind
    # the bot check, and the feed is the first thing tried.
    web.calls.clear()
    second = C.fetch("Oakmere Foods", ["https://careers.oakmere.example/teams"],
                     root=str(tmp_path), transport=web, sleep=web.sleep,
                     pages=str(tmp_path / "pages2"), today=TODAY + dt.timedelta(days=1))
    assert not web.got("https://careers.oakmere.example/teams")
    assert second["urls"][0]["state"] == "skipped"
    assert [u for u, _ in web.calls if not u.endswith("robots.txt")] == [
        "https://careers.oakmere.example/feed"]
    assert len(web.calls) < first_requests
    # After the recheck window, the page is tried again with one request.
    later = TODAY + dt.timedelta(days=C.HOST_RECHECK_DAYS)
    assert C.skip_host(note, later) == ""


def test_a_site_that_says_no_is_never_fetched_nor_read_another_way(tmp_path):
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, "User-agent: *\nDisallow: /\n")})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert [u for u, _ in web.calls] == ["https://www.oakmere.example/robots.txt"]
    assert rep["urls"][0]["state"] == "disallowed"
    assert not rep["candidates"]


def test_robots_it_cannot_read_leaves_permission_unconfirmed(tmp_path):
    web = Web({"https://www.oakmere.example/robots.txt": (403, {}, "denied")})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert not web.got("https://www.oakmere.example/about")
    assert "unconfirmed" in rep["urls"][0]["detail"]


def test_the_crawl_delay_is_kept_and_browser_headers_carry_no_credentials(tmp_path):
    web = Web({
        "https://www.oakmere.example/robots.txt": (200, {}, "User-agent: *\nCrawl-delay: 7\n"),
        "https://www.oakmere.example/about": (200, {}, ABOUT),
        "https://www.oakmere.example/news": (200, {}, ABOUT.replace("Bolton", "Wigan")),
    })
    _fetch(web, tmp_path, "https://www.oakmere.example/about", "https://www.oakmere.example/news")
    assert web.sleeps and max(web.sleeps) >= 6.5
    for url, headers in web.calls:
        assert not {"Cookie", "Authorization"} & set(headers)
        if not url.endswith("robots.txt"):
            assert headers["User-Agent"].startswith("Mozilla/5.0")


def test_a_429_is_waited_out_once_then_left_for_the_day(tmp_path):
    answers = iter([(429, {"retry-after": "3"}, "slow down"), (200, {}, ABOUT)])
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://www.oakmere.example/about": lambda u, h: next(answers)})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert 3 in web.sleeps and rep["urls"][0]["state"] == "ok"
    web2 = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW),
                "https://www.oakmere.example/about": (429, {"retry-after": "3600"}, "no")})
    rep2 = C.fetch("Saltmarsh Analytics", ["https://www.oakmere.example/about"],
                   root=str(tmp_path / "other"), transport=web2, sleep=web2.sleep,
                   pages=str(tmp_path / "pages3"), today=TODAY)
    assert 3600 not in web2.sleeps and rep2["urls"][0]["state"] == "rate_limited"


def test_linkedin_and_links_inside_the_posting_are_never_fetched(tmp_path):
    pick = tmp_path / "01_oakmere.md"
    import untrusted
    pick.write_text("# Oakmere Foods | Planner\n\n- location: Manchester\n\n" + untrusted.fence(
        "Apply now. Read about us at https://www.oakmere.example/culture."), encoding="utf-8")
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW)})
    rep = _fetch(web, tmp_path, "https://www.linkedin.com/company/oakmere",
                 "https://www.oakmere.example/culture", posting=str(pick))
    assert not [u for u, _ in web.calls if "linkedin" in u or u.endswith("/culture")]
    assert [u["state"] for u in rep["urls"]] == ["refused", "refused"]


def test_the_budget_caps_requests_for_one_employer_across_runs(tmp_path):
    routes = {"https://www.oakmere.example/robots.txt": (200, {}, ALLOW)}
    urls = ["https://www.oakmere.example/p%d" % i for i in range(20)]
    for u in urls:
        routes[u] = (200, {}, ABOUT)
    web = Web(routes)
    _fetch(web, tmp_path, *urls[:10])
    _fetch(web, tmp_path, *urls[10:])
    assert len(web.calls) == C.FETCH_BUDGET


def test_a_fresh_cached_fact_that_was_checked_is_never_fetched_again(tmp_path):
    fact = {"claim": "Second bakery site in Bolton", "url": "https://www.oakmere.example/about",
            "quote": "Oakmere Foods opened its second bakery site in Bolton in March 2026",
            "date_seen": (TODAY - dt.timedelta(days=3)).isoformat(),
            "quote_checked": (TODAY - dt.timedelta(days=3)).isoformat()}
    C.save("Oakmere Foods", {"facts": [fact]}, root=str(tmp_path), pages=str(tmp_path / "p"))
    web = Web({})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert web.calls == [] and rep["kept"][0]["claim"] == fact["claim"]
    old = dict(fact, date_seen=(TODAY - dt.timedelta(days=C.RESEARCH_FRESH_DAYS + 1)).isoformat())
    assert not C.fact_fresh(old, {}, TODAY) and C.fact_fresh(fact, {}, TODAY)


def test_a_fresh_fact_no_kept_page_can_check_is_fetched_again(tmp_path):
    # The facts are in the repo and the pages on the computer: a new session had fresh facts
    # with no page, each refused as unchecked, and its page skipped as fresh for 30 days
    # (2026-10-23).
    fact = {"claim": "Second bakery site in Bolton", "url": "https://www.oakmere.example/about",
            "quote": "Oakmere Foods opened its second bakery site in Bolton in March 2026",
            "date_seen": (TODAY - dt.timedelta(days=3)).isoformat()}
    C.save("Oakmere Foods", {"facts": [fact]}, root=str(tmp_path), pages=str(tmp_path / "p"))
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://www.oakmere.example/about": (200, {}, ABOUT)})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert web.got("https://www.oakmere.example/about")
    assert [u["url"] for u in rep["urls"] if u["state"] == "again"] == [
        "https://www.oakmere.example/about"]
    assert C.quote_problem(fact, str(tmp_path / "pages")) == ""      # checkable now


def test_a_quote_is_checked_against_the_page_as_fetched(tmp_path):
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://www.oakmere.example/about": (200, {}, ABOUT)})
    pages = str(tmp_path / "pages")
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/about")
    quote = rep["candidates"][0]["quote"]
    good = {"claim": "Opened a second bakery in Bolton", "quote": quote,
            "url": "https://www.oakmere.example/about"}
    written = C.save("Oakmere Foods", {"facts": [good]}, root=str(tmp_path), pages=pages,
                     today=TODAY)
    saved = json.loads(Path(written).read_text(encoding="utf-8"))["facts"]
    assert saved[0]["quote_checked"] == TODAY.isoformat()
    reworded = dict(good, quote="Oakmere Foods recently opened the largest bakery in Bolton.")
    with pytest.raises(C.QuoteNotFound):
        C.save("Oakmere Foods", {"facts": [reworded]}, root=str(tmp_path), pages=pages)
    assert json.loads(Path(written).read_text(encoding="utf-8"))["facts"] == saved


FACT_A = {"claim": "Bolton site", "quote": "A second site in Bolton.", "url": "https://a.example/1"}
FACT_B = {"claim": "Wigan depot", "quote": "A new depot in Wigan.", "url": "https://a.example/2"}


def test_a_save_appends_and_never_drops_another_writers_facts(tmp_path):
    C.save("Oakmere Foods", {"facts": [FACT_A], "do_not_claim": ["not the largest"]},
           root=str(tmp_path))
    C.save("Oakmere Foods", {"facts": [FACT_B], "do_not_claim": ["not national"]},
           root=str(tmp_path))
    data, _, _ = C.load("Oakmere Foods", root=str(tmp_path))
    assert [f["claim"] for f in data["facts"]] == ["Bolton site", "Wigan depot"]
    assert data["do_not_claim"] == ["not the largest", "not national"]
    # The same fact saved again is updated in place, not doubled.
    C.save("Oakmere Foods", {"facts": [dict(FACT_A, date_seen="2026-10-21")]}, root=str(tmp_path))
    data, _, _ = C.load("Oakmere Foods", root=str(tmp_path))
    assert len(data["facts"]) == 2 and data["facts"][0]["date_seen"] == "2026-10-21"


def test_writers_at_the_same_moment_all_land(tmp_path):
    facts = [{"claim": "fact %d" % i, "quote": "Quote %d." % i, "url": "https://a.example/%d" % i}
             for i in range(8)]
    threads = [threading.Thread(target=C.save, args=("Oakmere Foods", {"facts": [f]}),
                                kwargs={"root": str(tmp_path)}) for f in facts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data, _, _ = C.load("Oakmere Foods", root=str(tmp_path))
    assert sorted(f["claim"] for f in data["facts"]) == sorted(f["claim"] for f in facts)
    assert not [n for n in os.listdir(tmp_path / C.DIR) if n.endswith(".tmp")]


def test_two_roles_at_one_employer_keep_their_teams_apart(tmp_path):
    seen = dt.date.today().isoformat()
    C.save("Oakmere Foods", {"facts": [FACT_A], "team_context": "Demand planning, six people",
                             "fetched_date": seen}, root=str(tmp_path), role="Demand Planner")
    C.save("Oakmere Foods", {"facts": [FACT_B], "team_context": "Pricing, two people"},
           root=str(tmp_path), role="Pricing Analyst")
    data, _, _ = C.load("Oakmere Foods", root=str(tmp_path))
    assert data["role_context"] == {"Demand Planner": "Demand planning, six people",
                                    "Pricing Analyst": "Pricing, two people"}
    rep = _fetch(Web({}), tmp_path, role="Pricing Analyst",
                 today=dt.date.today())
    assert [f["claim"] for f in rep["kept"]] == ["Wigan depot"]
    assert [f["claim"] for f in rep["other_roles"]] == ["Bolton site"]


def test_the_cli_fetch_subcommand_is_there_and_the_lookup_still_works(tmp_path, capsys):
    assert C.main(["Oakmere Foods", "--root", str(tmp_path)]) == 0
    assert "not cached" in capsys.readouterr().out
    # No URLs: nothing is fetched, and it says where the research goes.
    assert C.main(["fetch", "Oakmere Foods", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "research goes in company_research/oakmere-foods.json" in out
    assert "REQUESTS: 0 this run" in out


def test_a_host_with_no_feed_is_not_searched_again_inside_the_window(tmp_path):
    web = Web({"https://investors.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://investors.oakmere.example/results": (403, {}, "Forbidden")})
    _fetch(web, tmp_path, "https://investors.oakmere.example/results")
    tried = [u for u, _ in web.calls if not u.endswith("robots.txt")]
    assert tried[0].endswith("/results") and len(tried) <= 1 + C.MAX_FEED_TRIES + 1
    note = C.host_notes(str(tmp_path))["investors.oakmere.example"]
    assert note["no_feed"] == TODAY.isoformat() and note["sitemap_checked"] == TODAY.isoformat()
    web.calls.clear()
    C.fetch("Oakmere Foods", ["https://investors.oakmere.example/results"], root=str(tmp_path),
            transport=web, sleep=web.sleep, pages=str(tmp_path / "pages2"),
            today=TODAY + dt.timedelta(days=1))
    assert web.calls == []


def test_a_feed_the_host_refuses_too_stops_the_feed_search(tmp_path):
    web = Web({"https://careers.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://careers.oakmere.example/teams": (403, {}, CHALLENGE),
               "https://careers.oakmere.example/feed": (403, {}, CHALLENGE)})
    _fetch(web, tmp_path, "https://careers.oakmere.example/teams")
    assert not web.got("https://careers.oakmere.example/rss")


def test_a_path_robots_disallows_does_not_shut_the_rest_of_the_host(tmp_path):
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, "User-agent: *\nDisallow: /careers/\n"),
               "https://www.oakmere.example/about": (200, {}, ABOUT)})
    rep = _fetch(web, tmp_path, "https://www.oakmere.example/careers/teams",
                 "https://www.oakmere.example/about")
    assert [u["state"] for u in rep["urls"]][:2] == ["disallowed", "ok"]
    assert C.host_notes(str(tmp_path))["www.oakmere.example"]["status"] == "ok"


def test_a_host_known_to_refuse_is_not_tried_nor_read_another_way(tmp_path):
    web = Web({})
    rep = _fetch(web, tmp_path, "https://www.sec.gov/cgi-bin/browse-edgar?company=oakmere")
    assert web.calls == [] and rep["urls"][0]["state"] == "skipped"
    assert "investor pages" in rep["urls"][0]["detail"]


def test_a_host_asking_to_slow_down_is_not_read_another_way(tmp_path):
    web = Web({"https://www.oakmere.example/robots.txt": (200, {}, ALLOW),
               "https://www.oakmere.example/about": (429, {}, "slow down")})
    _fetch(web, tmp_path, "https://www.oakmere.example/about")
    assert not web.got("https://www.oakmere.example/feed")
