"""tools/markets.py and tools/markets/: the market tables /setup reads before it researches.

Setup used to research every person's market from nothing, most of what a setup cost. The
app now ships the public part (national, field, level, regional and remote boards, the
eligibility wording, document conventions, where pay is published, the big metros' names)
and setup researches only what is missing. These tests hold the tables to what makes them
safe to rely on: every fact names the page it came from and the day, setup is given only
what code found on that page in the last year, a robots.txt verdict is code's and never
hand-written, and no country is covered in more detail than the others.

Nothing here reaches the network: robots.txt and pages are faked, and the shipped tables
are read on the day they were checked.
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import markets  # noqa: E402

CHECKED = dt.date(2026, 10, 25)          # the day the shipped tables were read


def _fact(**kw):
    out = {"source": "https://stats.example.org/page", "quote": "a sentence of six words or more",
           "checked": "2026-10-20", "verified": True}
    out.update(kw)
    return out


def _board(name, url, **kw):
    b = {"name": name, "url": url, "kind": "general"}
    b.update(_fact(source=url + "/about"))
    b.update({"search": url + "/jobs?q=x", "paths": {"search": "/jobs?q=x", "posting": "/job/"},
              "robots": {"status": "allowed", "search": True, "posting": True,
                         "crawl_delay": None, "ai_input": None, "why": "",
                         "checked": "2026-10-20"},
              "public_search": {"status": "open", "http": 200, "checked": "2026-10-20"}})
    b.update(kw)
    return b


def _country(cc="zz", **kw):
    t = {"country": cc, "name": "Zedland", "aka": ["ZL", "Zed"], "languages": ["en"],
         "currency": "ZZD",
         "boards": [_board("Zedjobs", "https://www.zedjobs.example"),
                    _board("Zedwork", "https://www.zedwork.example"),
                    _board("Unread Board", "https://unread.example", verified=False,
                           why="the source could not be read")],
         "eligibility": [_fact(phrase="Zedland citizen", lang="en", means="citizenship"),
                         _fact(phrase="work permit", lang="en", means="work_right"),
                         _fact(phrase="clearance", lang="en", means="clearance", verified=False,
                               why="the quote is not on the page")],
         "documents": [_fact(topic=t, value="v") for t in markets.TOPICS],
         "pay": [_fact(name="Zed statistics", url="https://stats.example.org", what="pay"),
                 _fact(name="Zed survey", url="https://survey.example.org", what="pay")],
         "places": [_fact(metro=m, written=[m, m + " North"]) for m in ("Alpha", "Beta", "Gamma")]}
    t.update(kw)
    return t


def _root(tmp_path, country=None, field=None, level=None, region=None, remote=None):
    root = tmp_path / "markets"
    root.mkdir()
    markets.dump(str(root / "zz.json"), country or _country())
    for sub, name, table in (("fields", "widgets", field), ("levels", "graduate", level),
                             ("regions", "zz", region)):
        if table is not None:
            (root / sub).mkdir()
            markets.dump(str(root / sub / f"{name}.json"), table)
    if remote is not None:
        markets.dump(str(root / "remote.json"), remote)
    return str(root)


# ------------------------------------------------------------------ the shipped tables

def test_every_shipped_table_passes_its_own_check():
    assert markets.check() == []


def test_twenty_countries_and_every_dimension_are_covered():
    c = markets.counts()
    assert len(c["countries"]) >= 20
    assert len(c["fields"]) >= 15
    assert set(c["levels"]) == set(markets.LEVELS)
    assert c["remote"]["boards"][1] >= 5
    assert len(c["regions"]) >= 3


def test_no_country_lists_more_than_the_others():
    """Evenly covered, so no one market stands out: each country lists the same kinds of
    fact within the same narrow range, whatever could be verified."""
    for cc, t in markets.countries().items():
        for kind, (lo, hi) in markets.EVEN.items():
            assert lo <= len(t[kind]) <= hi, (cc, kind)
        assert sorted(d["topic"] for d in t["documents"]) == sorted(markets.TOPICS), cc


def test_a_country_is_found_by_its_code_its_name_or_what_people_call_it():
    assert markets.country_code("UK") == "gb"
    assert markets.country_code("United Kingdom") == "gb"
    assert markets.country_code("deutschland") == "de"
    assert markets.country_code("Atlantis") is None
    assert markets.field_code("nursing") == "healthcare-nursing"
    assert markets.level_code("new grad") == "graduate"


def test_every_board_opens_on_its_name_then_its_own_address():
    # The leak scan reads a board's name beside its address (leak_scan.market_allowance).
    for path in markets._files():
        with open(path, encoding="utf-8") as fh:
            table = json.load(fh)
        for b in markets._all_boards(table):
            assert list(b)[:2] == ["name", "url"], (path, b["name"])


def test_every_verified_quote_is_long_enough_to_prove_something():
    for path in markets._files():
        with open(path, encoding="utf-8") as fh:
            table = json.load(fh)
        for f in markets._all_facts(table):
            if f["verified"]:
                assert markets._size(f["quote"]) >= markets.MIN_QUOTE_WORDS, (path, f["quote"])
            else:
                assert f.get("why"), path


def test_a_fields_tools_are_in_the_shape_a_profile_extends_its_families_with():
    for fc in markets.fields():
        for fam in markets.families(fc, today=CHECKED):
            name, *members = fam
            assert isinstance(name, str) and len(members) >= 2
            for tool, pattern in members:
                assert re.search(pattern, tool, re.I), (fc, tool)


def test_the_brief_gives_boards_with_their_robots_and_says_what_is_left():
    text = markets.brief("de", field="engineering", level="graduate", city="Hamburg",
                         employers=2, today=CHECKED)
    assert "robots" in text and "Still to research:" in text
    assert "ats_boards.py --find" in text
    assert "Hamburg" not in text.split("Still to research:")[1]      # a metro the table holds


# ------------------------------------------------------------------ what setup is given

def test_setup_is_given_only_what_code_found_on_a_page(tmp_path):
    root = _root(tmp_path)
    m = markets.load("Zed", root=root, today=dt.date(2026, 10, 21))
    assert [b["name"] for b in m["boards"]] == ["Zedjobs", "Zedwork"]
    assert [e["means"] for e in m["eligibility"]] == ["citizenship", "work_right"]
    every = markets.load("zz", unverified=True, root=root, today=dt.date(2026, 10, 21))
    assert len(every["boards"]) == 3 and len(every["eligibility"]) == 3


def test_a_fact_read_more_than_a_year_ago_is_a_lead_not_a_fact(tmp_path):
    root = _root(tmp_path)
    later = dt.date(2026, 10, 20) + dt.timedelta(days=markets.STALE_DAYS + 1)
    m = markets.load("zz", root=root, today=later)
    assert m["boards"] == [] and m["eligibility"] == [] and m["documents"] == []
    gaps = markets.gaps("zz", city="Alpha", root=root, today=later)
    assert any("how a resume is written" in g for g in gaps)
    assert any("eligibility wording" in g for g in gaps)


def test_country_field_level_region_and_remote_merge_and_each_board_comes_once(tmp_path):
    field = {"field": "widgets", "name": "Widget making", "aka": ["widgets"],
             "boards": {"*": [_board("Widgetjobs", "https://widgetjobs.example")],
                        "zz": [_board("Zed Widgets", "https://zedwidgets.example")],
                        "yy": [_board("Elsewhere", "https://elsewhere.example")]},
             "documents": {"*": [_fact(topic="portfolio", value="a link")]},
             "licences": {"zz": [_fact(value="a Zed licence")]},
             "pay": {"*": [_fact(name="Widget pay", url="https://pay.example", what="pay")]},
             "titles": [_fact(value=["Widget Maker", "Widget Lead"])],
             "families": [_fact(family="lathe", members=[["Alpha Lathe", r"\balpha lathe\b"],
                                                         ["Beta Lathe", r"\bbeta lathe\b"]])]}
    level = {"level": "graduate", "name": "Graduate", "aka": ["new grad"],
             "boards": {"zz": [_board("Zed Grads", "https://zedgrads.example")]},
             "norms": {"*": [_fact(value="graduates are hired in spring")]}}
    region = {"country": "zz", "regions": {"no": {"name": "Northern Zed", "aka": ["NZD"],
              "boards": [_board("North Jobs", "https://northjobs.example"),
                         _board("Zedjobs again", "https://www.zedjobs.example")]}}}
    remote = {"boards": [_board("Anywhere", "https://anywhere.example")]}
    root = _root(tmp_path, field=field, level=level, region=region, remote=remote)
    m = markets.load("zz", field="widgets", level="new grad", region="Northern Zed",
                     root=root, today=dt.date(2026, 10, 21))
    scopes = [(b["name"], b["scope"]) for b in m["boards"]]
    assert scopes == [("Zedjobs", "country"), ("Zedwork", "country"), ("Widgetjobs", "field"),
                      ("Zed Widgets", "field"), ("Zed Grads", "level"),
                      ("North Jobs", "region"), ("Anywhere", "remote")]
    assert [d["topic"] for d in m["documents"] if d["scope"] == "field"] == ["portfolio"]
    assert m["licences"][0]["value"] == "a Zed licence"
    assert m["norms"][0]["value"] == "graduates are hired in spring"
    assert markets.families("widgets", root=root, today=dt.date(2026, 10, 21)) == [
        ("lathe", ("Alpha Lathe", r"\balpha lathe\b"), ("Beta Lathe", r"\bbeta lathe\b"))]


def test_gaps_name_what_the_one_research_agent_is_sent_for(tmp_path):
    root = _root(tmp_path)
    assert markets.gaps("Atlantis", root=root)[0].startswith("everything about Atlantis")
    got = markets.gaps("zz", field="knitting", city="Delta", employers=3, root=root,
                       today=dt.date(2026, 10, 21))
    assert any("place names around Delta" in g for g in got)
    assert any("knitting" in g for g in got)
    assert any("3 target employers" in g and "ats_boards.py --find" in g for g in got)
    assert not any("place names around" in g for g in
                   markets.gaps("zz", city="beta north", root=root, today=dt.date(2026, 10, 21)))


# ------------------------------------------------------------------ verdicts made by code

def _policy(body, status=200):
    def fetch(url, ua):
        assert url.endswith("/robots.txt")
        if isinstance(body, Exception):
            raise body
        return body, status
    return fetch


def test_a_robots_verdict_is_made_by_code_for_the_search_and_posting_paths():
    paths = {"search": "/jobs?q=x", "posting": "/job/1"}
    v = markets.robots_verdict("https://a.example", paths, _policy("", 404))
    assert (v["status"], v["search"], v["posting"]) == ("no_policy", True, True)
    v = markets.robots_verdict("https://a.example", paths,
                               _policy("User-agent: *\nDisallow: /job/\nCrawl-delay: 5\n"))
    assert (v["status"], v["search"], v["posting"], v["crawl_delay"]) == ("partial", True, False, 5.0)
    v = markets.robots_verdict("https://a.example", paths,
                               _policy("User-agent: Claude-User\nDisallow: /\n"))
    assert v["status"] == "disallowed"
    v = markets.robots_verdict("https://a.example", paths,
                               _policy("User-agent: *\nContent-Signal: ai-input=no\nAllow: /\n"))
    assert (v["status"], v["ai_input"]) == ("allowed", "no")
    v = markets.robots_verdict("https://a.example", paths, _policy(RuntimeError("curl exit 28")))
    assert v["status"] == "unconfirmed" and v["search"] is None


def test_a_search_is_never_fetched_where_robots_disallows_it():
    calls = []

    def transport(url, headers):
        calls.append(url)
        return 200, {}, "<html><body>" + "results " * 400 + "</body></html>"

    b = _board("Zedjobs", "https://www.zedjobs.example")
    b["robots"]["search"] = False
    assert markets.search_check(b, transport)["status"] == "not_tried" and calls == []
    b["robots"]["search"] = True
    assert markets.search_check(b, transport) == {"status": "open", "http": 200}
    blocked = markets.search_check(b, lambda u, h: (403, {}, "Forbidden"))
    assert blocked["status"] == "blocked"


def test_check_refuses_a_table_that_was_written_by_hand_wrongly(tmp_path):
    bad = _country()
    bad["boards"][0]["robots"]["search"] = False                 # status says allowed
    bad["boards"][1]["url"] = "http://www.zedwork.example"        # not https
    bad["boards"][1]["kind"] = "favourite"
    bad["eligibility"][0]["checked"] = "2099-01-01"               # in the future
    bad["eligibility"][1]["means"] = "vibes"
    bad["places"] = bad["places"][:1]                             # fewer than every other
    bad["boards"].append({"url": "https://x.example", "name": "Backwards"})
    problems = "\n".join(markets.check(_root(tmp_path, country=bad), today=CHECKED))
    for words in ("does not follow from its verdicts", "url is not an https address",
                  "kind 'favourite'", "checked is not a date", "means is not one of",
                  "1 places, where every country lists", "starts with its name, then its url"):
        assert words in problems, words


def test_a_fact_is_verified_only_when_its_quote_and_every_name_are_on_the_page():
    page = "Zedjobs lists every job in Zedland, from Alpha to Beta North."
    f = _fact(quote="Zedjobs lists every job in Zedland", on_page=["Alpha", "Beta North"])
    assert markets.verify_fact(f, page)["verified"] is True
    assert markets.verify_fact(dict(f, on_page=["Gamma"]), page)["why"] == "not on the page: Gamma"
    assert markets.verify_fact(dict(f, quote="Zedjobs lists nothing at all here"), page)[
        "why"] == "the quote is not on the page"
    assert markets.verify_fact(dict(f, quote="Zedjobs lists"), page)["verified"] is False
    gone = markets.verify_fact(f, None, "HTTP 404")
    assert gone["verified"] is False and "HTTP 404" in gone["why"]
    # Japanese writes no spaces: two characters count as a word.
    assert markets._size("社会人の転職者・中途採用者向けの就職サイト") >= markets.MIN_QUOTE_WORDS


def test_verify_writes_what_it_found_back_into_the_table(tmp_path):
    root = _root(tmp_path)

    def transport(url, headers):
        if "unread" in url:
            return 404, {}, ""
        return 200, {}, "<html><body><p>a sentence of six words or more</p>" \
                        "<p>Alpha Alpha North Beta Beta North Gamma Gamma North</p></body></html>"

    lines = markets.verify([os.path.join(root, "zz.json")], write=True, root=root,
                           today=CHECKED, transport=transport)
    assert any("Unread Board" in line for line in lines)
    with open(os.path.join(root, "zz.json"), encoding="utf-8") as fh:
        table = json.load(fh)
    assert table["boards"][0]["verified"] is True and table["boards"][0]["checked"] == "2026-10-25"
    assert table["boards"][2]["verified"] is False
    assert table["eligibility"][2]["verified"] is True        # its quote is on the page now


def test_robots_writes_the_verdict_code_made(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(markets, "_robots_child", lambda base, paths, timeout=60: {
        "status": "disallowed", "search": False, "posting": False, "crawl_delay": None,
        "ai_input": None, "why": ""})
    markets.robots([os.path.join(root, "zz.json")], write=True, today=CHECKED, root=root)
    with open(os.path.join(root, "zz.json"), encoding="utf-8") as fh:
        b = json.load(fh)["boards"][0]
    assert b["robots"]["status"] == "disallowed" and b["robots"]["checked"] == "2026-10-25"
    assert b["public_search"]["status"] == "not_tried"         # never fetched when disallowed
    assert markets.check(root, today=CHECKED) == []


# ------------------------------------------------------------------ setup reads them first

def test_setup_reads_the_tables_first_and_sends_one_agent_for_the_rest():
    with open(os.path.join(ROOT, ".claude", "commands", "setup.md"), encoding="utf-8") as fh:
        setup = fh.read()
    with open(os.path.join(ROOT, ".claude", "skills", "job-application-assistant",
                           "setup-sections.md"), encoding="utf-8") as fh:
        sections = fh.read()
    assert "python3 tools/markets.py brief" in setup and "Still to research" in setup
    assert "**one** background agent" in setup
    assert "/add-portal" in setup.split("python3 tools/markets.py brief")[1].split("4. **Ask")[0]
    assert "python3 tools/markets.py brief" in sections
