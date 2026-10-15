"""A portal a person builds for their own market is searched by every round.

The app used to ship four Danish boards and call none of them: scrape_wide.py
had adapters for LinkedIn and freehire only, and any other portal ran only when
somebody typed /scrape. A person in Toronto or Lagos who built a portal for
their national board with /add-portal got nothing from it in a scheduled round.

Now any portal that is on and follows the portal contract is searched,
paced by the crawl-delay its SKILL.md declares, and hydrated the same way,
and the app's two portals send exactly the requests they always did.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import env_check  # noqa: E402
import hydrate  # noqa: E402
import personal_paths  # noqa: E402
import portals  # noqa: E402
import scrape_wide  # noqa: E402

APP = {"linkedin-search": True, "freehire-search": True}


def _portal(root, name, front):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    lines = "\n".join(f"{k}: {v}" for k, v in front.items())
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: >\n  A board.\n  "
                                f"Two lines.\n{lines}\n---\n\n# {name}\n")


@pytest.fixture
def skills(tmp_path, monkeypatch):
    for name in APP:
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n---\n")
    _portal(tmp_path, "cityboard-search", {"enabled": "true", "contract": "1",
                                           "url": "https://board.example",
                                           "crawl-delay": "5", "pages": "3",
                                           "canary-query": "nurse"})
    _portal(tmp_path, "nationalboard-search", {"enabled": "true", "contract": "1",
                                               "location": "none", "detail": '"false"'})
    # Restored from before the contract: on, with a CLI, and no `contract: 1`.
    _portal(tmp_path, "oldboard-search", {"enabled": "true"})
    monkeypatch.setattr(portals, "SKILLS", str(tmp_path))
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {"cityboard-search": ["Townsville, QX"]})
    portals.cli.cache_clear()
    yield tmp_path
    portals.cli.cache_clear()


def test_a_portal_says_how_it_may_be_called(skills):
    assert portals.crawl_delay("cityboard-search") == 5
    assert portals.pages("cityboard-search") == 3
    assert portals.takes_location("cityboard-search")
    assert portals.url("cityboard-search") == "https://board.example"
    assert not portals.takes_location("nationalboard-search")
    assert not portals.has_detail("nationalboard-search")
    # A board that says nothing gets one request a second, never a flood.
    assert portals.crawl_delay("nationalboard-search") == portals.DEFAULT_DELAY
    assert portals.crawl_delay("linkedin-search") == 0
    assert portals.skill_of("cityboard") == "cityboard-search"


def test_every_portal_that_is_on_is_searched(skills):
    on = portals.enabled({})
    tasks = scrape_wide.build_tasks(on, 5)
    kinds = {t[0] for t in tasks}
    assert {"cityboard-search", "nationalboard-search"} <= kinds
    city = [t for t in tasks if t[0] == "cityboard-search"]
    assert {t[2] for t in city} == {"Townsville, QX"}          # its places, as the board writes them
    assert max(t[3] for t in city) == 3                         # as deep as it says, not --pages
    assert {t[2] for t in tasks if t[0] == "nationalboard-search"} == {None}


def test_the_apps_portals_send_exactly_what_they_did(skills):
    """A person's portal adds requests after the app's; it changes none of them."""
    alone = scrape_wide.build_tasks(APP, 5)
    with_mine = scrape_wide.build_tasks(portals.enabled({}), 5)
    assert with_mine[:len(alone)] == alone
    assert all(t[0] not in ("li", "lir", "fh") for t in with_mine[len(alone):])


def test_a_portal_that_is_off_is_sent_nothing(skills):
    on = portals.enabled({"cityboard-search": False})
    assert "cityboard-search" not in {t[0] for t in scrape_wide.build_tasks(on, 5)}


def test_a_search_sends_the_contract_and_keeps_the_teaser_out_of_the_body(skills, monkeypatch):
    sent = []

    def fake_run(cmd, timeout=90):
        sent.append(cmd)
        return {"results": [{"id": 7, "title": "Planner", "company": "Acme",
                             "url": "https://board.example/7", "location": "Townsville",
                             "date": "2026-10-10T00:00:00", "description": "A teaser."}]}, None
    monkeypatch.setattr(scrape_wide, "run", fake_run)
    rows, err = scrape_wide.contract("cityboard-search", "planner", "Townsville, QX", 2, 14)
    assert err is None
    assert sent[0][3:] == ["search", "-q", "planner", "-l", "Townsville, QX", "--jobage", "14",
                           "--page", "2", "--format", "json"]
    r = rows[0]
    assert (r["id"], r["portal"], r["date"]) == ("7", "cityboard", "2026-10-10")
    assert r["desc"] is None and r["snippet"] == "A teaser."   # hydrate fetches the real body

    rows, _ = scrape_wide.contract("nationalboard-search", "planner", None, 1, 14)
    assert "-l" not in sent[1]
    assert rows[0]["desc"] == "A teaser."                      # no detail allowed: the search text is it


def test_a_sweep_waits_the_crawl_delay_between_requests(skills, monkeypatch):
    monkeypatch.setattr(scrape_wide, "contract",
                        lambda *a: ([{"url": f"u{a[3]}"}], None if a[3] != 2 else "exit 1: 503"))
    waits = []
    tasks = [("cityboard-search", "q", "Townsville, QX", p) for p in (1, 2, 3)]
    rows, n, failed = scrape_wide.sweep("cityboard-search", tasks, 14, sleep=waits.append)
    assert waits == [5, 5, 5]                                   # the probe went just before
    assert n == 3 and failed == ["exit 1: 503"] and len(rows) == 3


def test_the_canary_probes_a_persons_portal_too(skills, monkeypatch):
    monkeypatch.setattr(scrape_wide, "linkedin", lambda *a, **k: ([{"url": "u"}], None))
    monkeypatch.setattr(scrape_wide, "freehire", lambda *a, **k: ([{"url": "u"}], None))
    monkeypatch.setattr(scrape_wide, "contract",
                        lambda skill, *a: ([], None) if skill == "cityboard-search"
                        else ([{"url": "u"}], None))
    health = scrape_wide.canary(30, portals.enabled({}))
    assert health["cityboard"][0] is False                     # silent: broken, not a thin market
    assert health["nationalboard"][0] is True


def _detail_ok(cmd, stdout, **kw):
    stdout.write(json.dumps({"description": "The whole posting. Requirements: SQL."}))

    class P:
        returncode, stderr = 0, ""
    return P()


def test_a_persons_portal_is_hydrated_through_its_own_detail(skills, monkeypatch):
    monkeypatch.setattr(hydrate, "pace", lambda skill: True)
    monkeypatch.setattr(hydrate.subprocess, "run", _detail_ok)
    got = hydrate.fetch({"portal": "cityboard", "id": "7", "url": "u", "snippet": "A teaser."})
    assert got["desc"].startswith("The whole posting")


def test_when_the_detail_fails_the_snippet_stands_in_and_says_so(skills, monkeypatch):
    class Fail:
        returncode, stderr = 1, '{"error": "blocked"}'
    monkeypatch.setattr(hydrate, "pace", lambda skill: True)
    monkeypatch.setattr(hydrate.subprocess, "run", lambda *a, **k: Fail())
    got = hydrate.fetch({"portal": "cityboard", "id": "7", "url": "u", "snippet": "A teaser."})
    assert got["desc"] == "A teaser." and "detail exit 1" in got["hydrate_error"]


def test_a_board_whose_postings_may_not_be_fetched_is_never_asked(skills, monkeypatch):
    monkeypatch.setattr(hydrate.subprocess, "run",
                        lambda *a, **k: pytest.fail("a detail request was sent"))
    got = hydrate.fetch({"portal": "nationalboard", "id": "1", "url": "u"})
    assert "detail: false" in got["hydrate_error"]


def test_detail_fetches_keep_the_crawl_delay_across_workers(skills):
    now, waits = [100.0], []

    def sleep(s):
        waits.append(s)
        now[0] += s
    hydrate._PACE.clear()
    hydrate.pace("cityboard-search", sleep=sleep, clock=lambda: now[0])
    now[0] += 1
    hydrate.pace("cityboard-search", sleep=sleep, clock=lambda: now[0])
    assert waits == [4.0]
    hydrate.pace("linkedin-search", sleep=sleep, clock=lambda: now[0])
    assert waits == [4.0]                                       # the app's portals are not paced here


def test_the_environment_check_probes_a_persons_board(skills):
    assert ("cityboard-search", "https://board.example") in env_check.hosts()


def test_a_persons_portal_is_theirs_and_the_apps_are_the_apps():
    assert personal_paths.is_personal(".agents/skills/cityboard-search/cli/src/cli.ts")
    assert not personal_paths.is_personal(".agents/skills/linkedin-search/SKILL.md")
    assert not personal_paths.is_personal(".agents/skills/freehire-search/cli/dist/cli.mjs")


def test_a_board_researched_and_not_built_is_named_when_a_round_misses(skills, monkeypatch):
    import run_round
    monkeypatch.setattr(portals, "research", lambda: [
        {"board": "City Board", "portal": "cityboard-search", "status": "built"},
        {"board": "Guild Jobs", "portal": "guildjobs-search", "status": "not built yet"},
        {"board": "Walled Garden", "status": "needs a login, so no portal can read it"},
    ])
    assert [r["board"] for r in portals.not_built()] == ["Guild Jobs", "Walled Garden"]
    assert run_round._boards_not_built() == [
        "Guild Jobs (not built yet)", "Walled Garden (needs a login, so no portal can read it)"]


def test_a_quoted_value_means_what_it_says(skills):
    """`detail: "false"` is valid YAML for false; read raw it was a truthy string,
    and a round fetched posting pages the board's robots.txt disallows."""
    assert not portals.has_detail("nationalboard-search")


def test_a_portal_built_before_the_contract_is_not_called(skills):
    on = portals.enabled({})
    assert "oldboard-search" not in scrape_wide.contract_portals(on)
    assert "oldboard-search" not in {t[0] for t in scrape_wide.build_tasks(on, 5)}


def test_a_failing_board_is_stopped_not_waited_out(skills, monkeypatch):
    monkeypatch.setattr(scrape_wide, "contract", lambda *a: ([], "timeout after 90s"))
    tasks = [("cityboard-search", "q", "Townsville, QX", p) for p in range(1, 41)]
    rows, n, failed = scrape_wide.sweep("cityboard-search", tasks, 14, sleep=lambda s: None)
    assert n == scrape_wide.SWEEP_MAX_FAILS
    assert "stopped after 3 failures in a row; 37 requests not sent" in failed[-1]


def test_a_slow_board_stops_at_its_budget(skills, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(scrape_wide, "contract", lambda *a: ([{"url": "u"}], None))

    def sleep(s):
        now[0] += s * 100                       # every wait costs 500 seconds
    tasks = [("cityboard-search", "q", "Townsville, QX", p) for p in range(1, 41)]
    rows, n, failed = scrape_wide.sweep("cityboard-search", tasks, 14, sleep=sleep,
                                        clock=lambda: now[0])
    assert n < 40 and not failed


def test_paced_detail_fetches_stop_at_their_budget(skills):
    now = [100.0]
    hydrate._PACE.clear()
    assert hydrate.pace("cityboard-search", sleep=lambda s: None, clock=lambda: now[0])
    now[0] += hydrate.PACE_BUDGET + 1
    assert not hydrate.pace("cityboard-search", sleep=lambda s: None, clock=lambda: now[0])
    hydrate._PACE.clear()


def test_a_board_past_its_budget_keeps_its_snippet(skills, monkeypatch):
    monkeypatch.setattr(hydrate, "pace", lambda skill: False)
    monkeypatch.setattr(hydrate.subprocess, "run",
                        lambda *a, **k: pytest.fail("fetched past the budget"))
    got = hydrate.fetch({"portal": "cityboard", "id": "7", "url": "u", "snippet": "A teaser."})
    assert got["desc"] == "A teaser." and "budget" in got["hydrate_error"]


def test_a_persons_board_is_probed_with_its_own_word_over_a_month(skills, monkeypatch):
    calls = []
    monkeypatch.setattr(scrape_wide, "linkedin", lambda *a, **k: ([{"url": "u"}], None))
    monkeypatch.setattr(scrape_wide, "freehire", lambda *a, **k: ([{"url": "u"}], None))
    monkeypatch.setattr(scrape_wide, "contract",
                        lambda skill, q, loc, page, jobage: calls.append((skill, q, jobage))
                        or ([{"url": "u"}], None))
    scrape_wide.canary(7, portals.enabled({}))
    assert ("cityboard-search", "nurse", scrape_wide.CANARY_JOBAGE) in calls


def test_a_portal_with_no_places_of_its_own_searches_every_place(skills, monkeypatch):
    """It searched the first of SCRAPE_LOCATIONS alone: the home city, and none of
    the towns around it, the region or the country, which LinkedIn searched."""
    monkeypatch.setattr(scrape_wide, "LOCATIONS", ["Home City, R, C", "Next Town, R, C", "C"])
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {})
    city = [t for t in scrape_wide.build_tasks(portals.enabled({}), 5)
            if t[0] == "cityboard-search"]
    assert [t[2] for t in city if t[3] == 1][:1] == ["Home City, R, C"]
    assert {t[2] for t in city} == {"Home City, R, C", "Next Town, R, C", "C"}
    deep = max(t[3] for t in city if t[2] == "Home City, R, C")
    wide = max(t[3] for t in city if t[2] == "C")
    assert (deep, wide) == (3, 2)                               # home deep, the rest two pages


def test_a_board_that_filters_remote_is_searched_for_remote_roles(skills, monkeypatch):
    remote = [t for t in scrape_wide.build_tasks(portals.enabled({}), 5) if len(t) > 4]
    assert remote == []                                         # nobody said remote: true
    _portal(skills, "remoteboard-search", {"enabled": "true", "contract": "1", "remote": "true"})
    tasks = [t for t in scrape_wide.build_tasks(portals.enabled({}), 5)
             if t[0] == "remoteboard-search"]
    remote = [t for t in tasks if len(t) > 4]
    assert remote and all(t[2] is None and t[4] is True for t in remote)
    first_town = next(i for i, t in enumerate(tasks) if len(t) == 4 and t[2] != tasks[0][2])
    assert tasks.index(remote[0]) < first_town                  # a budget cut drops a town first

    sent = []
    monkeypatch.setattr(scrape_wide, "run", lambda cmd, timeout=90: (sent.append(cmd), ({}, None))[1])
    monkeypatch.setattr(scrape_wide, "contract",
                        lambda *a, **k: (sent.append((a, k)), ([], None))[1])
    scrape_wide.sweep("remoteboard-search", remote[:1] + tasks[:1], 14, sleep=lambda s: None)
    assert sent[0][1] == {"remote": True} and sent[1][1] == {}


def test_a_remote_search_sends_the_flag(skills, monkeypatch):
    sent = []
    monkeypatch.setattr(scrape_wide, "run", lambda cmd, timeout=90: (sent.append(cmd), ({}, None))[1])
    scrape_wide.contract("cityboard-search", "planner", None, 1, 14, remote=True)
    assert "--remote" in sent[0] and "-l" not in sent[0]
