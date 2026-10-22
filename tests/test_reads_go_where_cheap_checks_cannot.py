"""Profile reads are the scarcest thing a networking run spends, so cheap checks go first.

From one person's session on their own computer (2026-10-19): ten people were
short-listed for reads, seven were read before the pacing ran the session out of time,
and five of the seven were spent on facts a cheaper check could have caught: a request
already Pending, a city elsewhere, a role outside the function. Around that: a verdict
that said KEEP with nothing read, one exit code meaning three things, a top card read
wrong on today's layout, and two real employees dropped by the result-title reader. Since
2026-10-22 the app sets no reading limit of its own (no pause, cap or ramp): only LinkedIn's
own signals stop a read. Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import discovery  # noqa: E402
import reading  # noqa: E402

TODAY = datetime.date(2026, 10, 19)


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    return tmp_path


# ------------------------------------------------------------ 1. the verdict

def test_a_verdict_with_no_page_read_is_not_read_yet_never_keep(here, capsys):
    cid = "kestrel_achterberg"
    reading.main(["add", cid, "--kind", "talk", "--url", "https://example.org/t/1",
                  "--text", "Explaining pricing models to underwriters", "--name",
                  "Rosalind Achterberg", "--company", "Kestrel Mutual"])
    capsys.readouterr()
    assert reading.main(["verdict", cid]) == reading.EXIT["not_read"]
    out = capsys.readouterr().out
    assert "NOT READ YET" in out and "KEEP" not in out.replace("NOT READ YET", "")


def test_a_public_finding_can_still_rule_someone_out_cheaply(here, capsys):
    cid = "kestrel_achterberg"
    # A public page that shows they have moved on rules them out. Where they sit no longer
    # does (2026-10-21): that is a note, never a skip.
    reading.save(cid, {"name": "Rosalind Achterberg", "company": "Kestrel Mutual",
                       "headline": "", "current": "Fernhill Freight",
                       "location": "San Francisco, California, United States",
                       "sources": [{"kind": "public", "url": "https://example.org/t/1"}],
                       "items": []})
    assert reading.main(["verdict", cid]) == reading.EXIT["skip"]
    out = capsys.readouterr().out
    assert "SKIP: has moved on" in out and f"reading.py skip {cid}" in out


# ------------------------------------------------------------ 2. exit codes

def test_every_exit_code_means_one_thing():
    codes = [v for k, v in reading.EXIT.items()]
    assert len(codes) == len(set(codes)) and 2 not in codes      # 2 is argparse's
    assert {"skip", "wait", "later", "tomorrow", "not_read"} <= set(reading.EXIT)
    for k in reading.EXIT:
        assert f"{reading.EXIT[k]}  " in reading.__doc__ or f"{reading.EXIT[k]} " in reading.__doc__


def _browsed(here, times, gap=60):
    for i, t in enumerate(times):
        reading.save(f"c{i}", {"sources": [{"kind": "browser", "at": t.isoformat(),
                                            "next_gap": gap}]})


def test_a_read_right_after_another_is_saved_with_no_pause_and_nothing_logged(
        here, monkeypatch, capsys):
    """Was "a read too soon is kept, never refused, and still says wait". There is no pause
    of the app's own now (2026-10-22): a page right after another is a read like any, nothing
    is logged against a pace, and the next may load at once."""
    import pace
    import state
    monkeypatch.setenv("LJS_LEDGER", str(here / "ledger"))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    row = {"contact_id": "kestrel_achterberg", "name": "Rosalind Achterberg",
           "company": "Kestrel Mutual", "location": "Manchester", "channel": "connection",
           "status": "not_contacted"}
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [row])
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    now = datetime.datetime.now()
    _browsed(here, [now - datetime.timedelta(seconds=1)], gap=0)
    reading.shortlist(["kestrel_achterberg"], now.date(), contacts=[row], sends_left=10)
    page = here / "p.txt"
    page.write_text(_card("Manchester, England, United Kingdom", "Contact info", "Kestrel Mutual"),
                    encoding="utf-8")
    code = reading.main(["read", "kestrel_achterberg", str(page), "--source", "browser"])
    assert code == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "saved" in out and "pace" not in out and "the next page at" not in out
    assert "breaches" not in pace.load() and pace.friction() == []
    assert reading.main(["gate"]) == reading.EXIT["ok"]


def test_a_full_hour_and_a_full_day_of_pages_still_go_and_a_stop_is_tomorrow(here):
    now = datetime.datetime(2026, 10, 19, 15, 0)
    _browsed(here, [now - datetime.timedelta(seconds=i + 1) for i in range(200)])
    assert reading.gate_state(now, sends_left=None)["kind"] == "go"
    assert reading.gate_state(now.replace(hour=23), sends_left=0)["kind"] == "go"
    reading.stop("LinkedIn showed a check: Let's do a quick security check", now.date())
    g = reading.gate_state(now, sends_left=None)
    assert g["kind"] == "tomorrow" and reading.EXIT[g["kind"]] == 9


def test_gate_wait_never_sleeps(here):
    now = [datetime.datetime(2026, 10, 19, 15, 0)]
    _browsed(here, [now[0] - datetime.timedelta(seconds=1)], gap=600)
    slept = []
    g = reading._wait_gate(300, sleep=slept.append, clock=lambda: now[0])
    assert g["kind"] == "go" and slept == []
    reading.stop("LinkedIn showed a check: verify it's you", now[0].date())
    assert reading._wait_gate(300, sleep=slept.append, clock=lambda: now[0])["kind"] == "tomorrow"
    assert slept == []


# ------------------------------------------------------------ 6. no pace of the app's own

def test_the_reading_text_says_there_is_no_pace_of_the_apps_own():
    import inspect
    import pace
    src = inspect.getsource(reading)
    assert "the app sets no limit of its own on reading" in src
    assert "the app sets no limit of its own" in pace.__doc__
    # The pace it once stated is not claimed any more.
    for gone in ("never under 45 seconds", "GAP_MEDIAN", "BREAK_AFTER", "READS_PER_HOUR"):
        assert gone not in src, gone


def test_a_one_page_read_records_no_pause(here, monkeypatch):
    monkeypatch.setenv("LJS_LEDGER", str(here / "ledger"))
    rec = reading.page_read("people", "https://example.org/p", datetime.datetime(2026, 10, 19, 9))
    assert rec["next_gap"] == 0 and rec["break"] is False


def test_the_short_list_adds_and_never_replaces(here):
    placed = [{"contact_id": f"p{i}", "location": "Manchester"} for i in range(9)]
    got = reading.shortlist(["p0", "p1", "p2"], TODAY, contacts=placed, sends_left=2)
    assert got["ids"] == ["p0", "p1", "p2"]
    # No cap of the app's own: the second call adds everyone it names, behind the first.
    got = reading.shortlist(["p3", "p4", "p5", "p6"], TODAY, contacts=placed, sends_left=2)
    assert got["ids"] == ["p0", "p1", "p2", "p3", "p4", "p5", "p6"] and got["full"] == []


def test_no_more_than_the_unplaced_cap_of_people_nothing_has_placed(here):
    n = reading.UNVERIFIED_ON_SHORTLIST
    contacts = [{"contact_id": f"u{i}", "location": ""} for i in range(n + 2)]
    got = reading.shortlist([c["contact_id"] for c in contacts], TODAY, contacts=contacts)
    assert got["ids"] == [f"u{i}" for i in range(n)]
    assert got["unplaced"] == [f"u{n}", f"u{n + 1}"]
    # A one-page read that placed someone lets them on.
    reading.from_list("u2", {"name": "Idris Corrie", "location": "Salford", "title": "Analyst"},
                      "Kestrel Mutual")
    assert reading.placed("u2", contacts)


def test_reads_left_says_there_is_no_limit_of_the_apps_own(here):
    now = datetime.datetime(2026, 10, 19, 15, 0)
    _browsed(here, [now - datetime.timedelta(minutes=i + 1) for i in range(5)])
    assert reading.reads_left(now, sends_left=None) == (None, reading.NO_LIMITS)


def test_a_signal_yesterday_brings_no_slow_start_today(here, monkeypatch):
    import pace
    monkeypatch.setenv("LJS_LEDGER", str(here / "ledger"))
    now = datetime.datetime(2026, 10, 19, 15, 0)
    _browsed(here, [now - datetime.timedelta(minutes=i + 1) for i in range(3)])
    pace.record_friction("check", "a security check", now - datetime.timedelta(days=1))
    assert reading.reads_left(now, sends_left=None) == (None, reading.NO_LIMITS)
    assert reading.gate_state(now)["kind"] == "go"


# ------------------------------------------------------------ 7. the top card

def _card(*middle, buttons=("Connect", "Message", "More")):
    return "\n".join(["Rosalind Achterberg", "· 2nd", "Head of Pricing Analytics", *middle,
                      "500+ connections", *buttons, "About",
                      "I build pricing models insurers can explain.", "Experience",
                      "Head of Pricing Analytics", "Kestrel Mutual · Full-time",
                      "Jan 2024 - Present · 1 yr 10 mos"]) + "\n"


TODAYS_CARD = ("San Francisco, California, United States", "Contact info",
               "Kestrel Mutual", "University of Leeds")


@pytest.mark.parametrize("card,reach", [
    (_card(*TODAYS_CARD, "Corwin is a mutual connection"), "request"),
    (_card(*TODAYS_CARD), "request"),
    (_card(*TODAYS_CARD, "Corwin is a mutual connection", buttons=("Pending", "Message", "More")),
     "pending"),
    (_card(*TODAYS_CARD, buttons=("Follow", "More")), "request under More"),
])
def test_todays_top_card_reads_headline_place_and_reach(card, reach):
    r = reading.parse(card, name="Rosalind Achterberg", company="Kestrel Mutual",
                      source="browser", today=TODAY)
    assert r["headline"] == "Head of Pricing Analytics"           # never the mutual line
    assert r["location"] == "San Francisco, California, United States"   # never the school
    assert r["reach"] == reach and r["current"] == "Kestrel Mutual"
    keep, why = reading.verdict(r, "Kestrel Mutual")
    # Changed 2026-10-21: where a contact sits is a note, never a skip; a request already
    # pending still is one.
    if reach == "pending":
        assert not keep and "pending" in why
    else:
        assert keep and "based in San Francisco" in why
    assert "University of Leeds" not in why


def test_the_place_and_contact_info_on_one_line():
    r = reading.parse(_card("Manchester, England, United Kingdom · Contact info",
                            "Kestrel Mutual", "University of Leeds"),
                      name="Rosalind Achterberg", company="Kestrel Mutual", source="browser",
                      today=TODAY)
    assert (r["headline"], r["location"]) == ("Head of Pricing Analytics",
                                              "Manchester, England, United Kingdom")


def test_a_card_with_no_contact_info_line_and_a_school_under_the_employer():
    r = reading.parse(_card("Kestrel Mutual", "University of Leeds"),
                      name="Rosalind Achterberg", company="Kestrel Mutual", source="browser",
                      today=TODAY)
    assert r["headline"] == "Head of Pricing Analytics" and r["location"] == ""
    assert reading.verdict(r, "Kestrel Mutual")[0]


# ------------------------------------------------------------ 3 and 8. search results

def test_a_team_after_a_comma_is_not_another_employer():
    got = discovery.parse_result_title("Corwin Haldane - Pricing Director, Claims", "Kestrel Mutual")
    assert got["employer"] == "" and got["employer_unsure"] == "Claims"
    people = discovery.people_from_results(
        [{"title": "Corwin Haldane - Pricing Director, Claims",
          "url": "https://www.linkedin.com/in/example-corwin"}], "Kestrel Mutual", today=TODAY)
    t = discovery.triage(people, today=TODAY, target_company="Kestrel Mutual")
    assert [p["name"] for p in t["keep"]] == ["Corwin Haldane"]
    assert "may be a team" in t["keep"][0]["reverify"]


def test_the_employer_and_its_city_are_the_employer():
    got = discovery.parse_result_title("Idris Corrie - Kestrel Mutual Manchester", "Kestrel Mutual")
    assert (got["employer"], got["location"]) == ("Kestrel Mutual", "Manchester")
    assert discovery.parse_result_title("Idris Corrie - Former Kestrel Mutual Manchester",
                                        "Kestrel Mutual")["employer"] != "Kestrel Mutual"
    assert discovery.parse_result_title("Idris Corrie - Kestrel Mutual Ventures",
                                        "Kestrel Mutual")["employer"] == "Kestrel Mutual Ventures"


def test_the_search_summary_places_people_and_names_their_employer():
    results = [{"title": "Tamsin Oyelaran - Head of Demand Forecasting",
                "url": "https://www.linkedin.com/in/example-tamsin",
                "summary": "Experience: Fernhill Freight · Education: University of Leeds · "
                           "Location: Salford · 500+ connections on LinkedIn."},
               {"title": "Rhian Pellow - Analyst", "url": "https://www.linkedin.com/in/example-rhian",
                "location": "Greater Manchester, England"}]
    people = discovery.people_from_results(results, "Fernhill Freight", today=TODAY)
    by = {p["name"]: p for p in people}
    assert by["Tamsin Oyelaran"]["location"] == "Salford"
    assert by["Tamsin Oyelaran"]["company"] == "Fernhill Freight"
    assert by["Rhian Pellow"]["location"] == "Greater Manchester, England"


def test_a_title_that_found_nobody_at_an_employer_is_not_searched_there_again(here):
    import sources
    titles = discovery.TITLE_SETS["hiring_authority"]
    first = discovery.queries_for("Kestrel Mutual")[0]
    assert titles[0] in first
    sources.record_yield("Kestrel Mutual", first, kept=0, placed=0, today=TODAY)
    assert titles[0] in sources.spent_titles("Kestrel Mutual", TODAY)
    again = sources.searches("title_search", "Kestrel Mutual")
    assert titles[0] not in again[0] and titles[1] in again[0]
    # Another employer is untouched.
    assert titles[0] in sources.searches("title_search", "Fernhill Freight")[0]


# ------------------------------------------------------------ 4. one page, many people

INVITES = """Manage invitations
Received
Sent
People (3)
Rosalind Achterberg
Head of Pricing Analytics at Kestrel Mutual
Sent 2 days ago
Withdraw
Idris Corrie
Data Analyst at Fenwick Lane Insurance
Sent 1 week ago
Withdraw
Tamsin Oyelaran
Head of Demand Forecasting at Fernhill Freight
Sent today
Withdraw
"""


def test_the_sent_invitations_page_is_read_once_for_everyone():
    cards = reading.invitations(INVITES, TODAY)
    assert [c["name"] for c in cards] == ["Rosalind Achterberg", "Idris Corrie", "Tamsin Oyelaran"]
    assert cards[0]["sent"] == "2026-10-17" and cards[2]["sent"] == "2026-10-19"
    contacts = [{"contact_id": "kestrel_achterberg", "name": "Rosalind Achterberg",
                 "company": "Kestrel Mutual", "status": "not_contacted"},
                {"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran",
                 "company": "Fernhill Freight", "status": "awaiting_reply"}]
    got = reading.match_invitations(cards, contacts)
    assert [c["contact_id"] for _, c in got["pending"]] == ["kestrel_achterberg"]
    assert len(got["unknown"]) == 1


def test_a_people_page_screens_a_dozen_people_for_one_load():
    page = """Rosalind Achterberg
· 2nd
Head of Pricing Analytics at Kestrel Mutual
Manchester, England, United Kingdom
Pending
Corwin Haldane
· 2nd
Pricing Lead at Kestrel Mutual
Boston, Massachusetts, United States
Connect
"""
    people = reading.people_page(page, "Kestrel Mutual")
    by = {p["name"]: p for p in people}
    assert by["Rosalind Achterberg"]["reach"] == "pending"
    assert not reading.screen(by["Rosalind Achterberg"], "Kestrel Mutual")[0]
    # Changed 2026-10-21: based elsewhere is a note, never a cut.
    keep, why = reading.screen(by["Corwin Haldane"], "Kestrel Mutual")
    assert keep and "based in Boston" in why


def test_a_one_page_read_holds_nothing_back(here):
    now = datetime.datetime(2026, 10, 19, 15, 0)
    reading.page_read("invitations", "https://www.linkedin.com/mynetwork/", now)
    nxt = now + datetime.timedelta(seconds=1)
    assert reading.gate_state(nxt, sends_left=0)["kind"] == "go"
    assert reading.gate_state(nxt, sends_left=0, profile=False)["kind"] == "go"
    with pytest.raises(ValueError):
        reading.page_read("profile", "", now)


# ------------------------------------------------------------ 11. dates as known

def test_a_finding_dated_by_month_or_not_at_all_is_said_so():
    assert reading.item("podcast", "https://example.org/p", "Pricing in public", "unknown")["date"] == "unknown"
    assert reading.item("article", "https://example.org/a", "Model risk notes", "2026-03")["date"] == "2026-03"
    assert reading.shown_date("2026-03") == "March 2026" and reading.shown_date("unknown") == "date unknown"
    assert reading._item_days("2026-09", TODAY) == 48
    with pytest.raises(ValueError):
        reading.item("post", "https://www.linkedin.com/posts/x", "a post", "unknown")
    with pytest.raises(ValueError):
        reading.item("talk", "https://example.org/t", "a talk", "last spring")


# ------------------------------------------------------------ 13. notes too alike

TAIL = "I work in supply-chain analytics, ex-Oakmere Foods, and I'm looking for my next role."


def _note(hook, ask="Would you be open to a quick chat?"):
    return f"Hi there, hope you're well. {hook} {TAIL} {ask}"


def test_a_batch_ending_on_one_sentence_is_too_alike():
    notes = {f"c{i}": _note(f"Your talk number {i} on cold-chain forecasting stayed with me.")
             for i in range(6)}
    found = reading.alike(notes, ask="Would you have 15 minutes for a few questions sometime?",
                          about_me="", opener="hope you're well")
    kinds = {k for k, _, _ in found}
    assert "shared" in kinds
    # An ask is never held to the person's ASK word for word (2026-10-22: "not your ask" sent
    # every close to the one sentence). The same close in every note is what is caught.
    long_ask = ("Would you be open to connecting and sharing a few thoughts on how your team "
                "approaches forecasting?")
    notes = {f"c{i}": _note(f"Your talk number {i} on cold-chain forecasting stayed with me.",
                            ask=long_ask) for i in range(6)}
    found = reading.alike(notes, ask="Would you have 15 minutes for a few questions sometime?",
                          about_me="", opener="hope you're well")
    assert any(k == "shared" and s == long_ask for k, s, _ in found)
    assert "not your ask" not in {k for k, _, _ in found}


def test_the_persons_own_lines_are_theirs_to_repeat_unless_they_vary_them():
    ask = "Would you have 15 minutes for a few questions sometime?"
    about = TAIL.rstrip(".")
    hooks = ["Your post on demand sensing made me rethink our weekly forecast.",
             "We both spent years at Oakmere Foods in Leeds.",
             "Your talk about depot managers trusting models was spot on.",
             "Your article on cold-chain spoilage and weather feeds was new to me.",
             "Your repository for warehouse slotting is one I have used.",
             "Your panel on hiring analysts into operations teams was refreshing."]
    notes = {f"c{i}": _note(h, ask=ask) for i, h in enumerate(hooks)}
    assert reading.alike(notes, ask=ask, about_me=about, opener="hope you're well") == []
    found = reading.alike(notes, ask=ask, about_me=about, opener="hope you're well",
                          vary_about_me=True)
    assert found and found[0][0] == "shared"


def test_a_page_kept_after_a_stop_still_exits_as_a_stop(here, monkeypatch, capsys):
    # Kept with an ok, a page read after the day was stopped by a check was one the
    # session's loop went past, reading on.
    import state
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    row = {"contact_id": "kestrel_achterberg", "name": "Rosalind Achterberg",
           "company": "Kestrel Mutual", "location": "Manchester", "channel": "connection",
           "status": "not_contacted"}
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [row])
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    now = datetime.datetime.now()
    reading.shortlist(["kestrel_achterberg"], now.date(), contacts=[row], sends_left=10)
    reading.stop("LinkedIn showed a check: Let's do a quick security check")
    page = here / "p.txt"
    page.write_text(_card("Manchester, England, United Kingdom", "Contact info", "Kestrel Mutual"),
                    encoding="utf-8")
    code = reading.main(["read", "kestrel_achterberg", str(page), "--source", "browser"])
    out = capsys.readouterr().out
    assert "saved" in out and "It is kept" in out and "read nothing more today" in out
    assert code == reading.EXIT["tomorrow"]
    assert reading.after_breach(None) == reading.EXIT["ok"]
    assert reading.after_breach({"kind": "tomorrow"}) == reading.EXIT["tomorrow"]
