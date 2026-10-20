"""Finding people never waits on reading them: the discovery ladder.

A person complained, rightly, that if the only way to read someone was to screenshot or
paste their profile by hand, LinkedIn itself was faster and the app was pointless. So a
run makes its whole list from rungs every chat has (their own connections export, search
results whose own titles name the person and the employer, a profile check from those
titles), and reads only a short list of it: the best ten in a browser of theirs, the best
three from a paste, never everyone. Measured from a cloud chat with no browser on
2026-10-18: two plain searches named 17 people at one employer, every one with a profile
titled with that employer, nothing fetched and nothing asked. The people here are invented.
"""
import datetime
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))
import discovery  # noqa: E402
import reading  # noqa: E402
import sources  # noqa: E402

TODAY = datetime.date(2026, 10, 18)
RESULTS = [
    {"title": "Rosalind Achterberg - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-rosalind/"},
    {"title": "Corwin Haldane - Pricing Lead - Kestrel Mutual", "url": "https://uk.linkedin.com/in/example-corwin"},
    {"title": "Tamsin Oyelaran - Data Science Manager at Kestrel Mutual",
     "url": "https://www.linkedin.com/in/example-tamsin"},
    {"title": "Rhian Pellow - Fenwick Lane Insurance", "url": "https://www.linkedin.com/in/example-rhian"},
    {"title": "Idris Corrie - Greater Manchester, England", "url": "https://www.linkedin.com/in/example-idris"},
    {"title": "42 Data jobs in Manchester (3 new)", "url": "https://uk.linkedin.com/jobs/data-jobs-manchester"},
    {"title": "Kestrel Mutual hiring Data Analyst in Manchester",
     "url": "https://uk.linkedin.com/jobs/view/data-analyst-at-kestrel-mutual-3802692326"},
    {"title": "hk.linkedin.com", "url": "https://hk.linkedin.com/in/example-blank"},
]


def test_a_chat_with_no_browser_still_gets_the_whole_list_and_is_asked_for_nothing_per_person():
    got = sources.ladder([])
    usable = {r.id: ok for r, ok, _ in got["rungs"]}
    assert usable["public_web"] and usable["exists"] and not usable["browser_read"]
    assert got["read"] == "hand" and got["read_cap"] == 0 and got["hand_top"] == reading.HAND_TOP == 3
    assert "without reading anyone's profile" in got["say"]
    assert "the one or two who matter most" in got["say"]
    assert not re.search(r"(?:each|every) (?:person|profile)|everyone", got["say"])


@pytest.mark.parametrize("tools,route", [(["browser"], "browser"), (["enable"], "enable"),
                                         (["chrome"], "browser"), (["chrome-off"], "hand"),
                                         ([], "hand")])
def test_a_chat_with_a_browser_reads_the_best_few_and_one_without_offers_a_paste(tools, route, monkeypatch):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    got = sources.ladder(tools)
    assert got["read"] == route
    reads = route in ("browser", "enable")
    # Deep reads are for the few written to that day; one-page reads screen the rest.
    assert got["read_cap"] == (reading.READS_PER_RUN if reads else 0) and reading.READS_PER_RUN == 5
    assert (got["say"] == "") == reads


def test_search_results_become_people_with_evidence_and_a_profile_status_nothing_fetched():
    got = sources.harvest(RESULTS, "Kestrel Mutual", query="Kestrel Mutual Head of Data Manchester",
                          today=TODAY, connections=[], contacts=[])
    names = [p["name"] for p in got["keep"]]
    # Kept: the hiring manager by title, and the two whose results name only the employer,
    # whose job is unknown rather than adjacent. Dropped: a known title outside the function.
    assert names[0] == "Tamsin Oyelaran"
    assert set(names[1:]) == {"Rosalind Achterberg", "Idris Corrie"}
    assert all(p.get("title_unknown") for p in got["keep"][1:])
    assert any(p["name"] == "Corwin Haldane" and w.startswith("tier 4 adjacent")
               for p, w in got["dropped"])
    by = {p["name"]: p for p in got["keep"]}
    assert by["Rosalind Achterberg"]["profile_status"] == "verified"
    assert by["Tamsin Oyelaran"]["profile_status"] == "verified"         # "... at Kestrel Mutual"
    assert by["Idris Corrie"]["profile_status"] == "likely"              # a place, no employer
    assert not any("location unknown" in w for _, w in got["dropped"])
    for p in got["keep"]:
        assert p["linkedin_url"].startswith("https://") and p["route"] == "cold"
        assert p["evidence"].startswith("search result 2026-10-18: ")
        assert p["why"]["line"]
    # Someone whose own title names another employer works there, not here.
    assert any(p["name"] == "Rhian Pellow" and "works at Fenwick Lane" in w
               for p, w in got["dropped"])
    assert got["counts"] == {"results": 8, "people": 5, "kept": 3, "verified": 2,
                             "in_book": 0, "never_messaged": 0}
    # The searched-for job is a reason to look, never a claim about their role.
    assert any("came up in a search for Head of Data there, which is not their title" in w
               for _, w in by["Rosalind Achterberg"]["why"]["reasons"])


def test_only_a_persons_own_result_makes_a_candidate():
    # A listing, a page with no name and a company's own post are never a person; a name
    # in a search summary or a "people also viewed" list is not a result at all.
    people = discovery.people_from_results(RESULTS, "Kestrel Mutual", today=TODAY)
    assert all(discovery.is_person_url(p["linkedin_url"]) for p in people)
    assert "hk.linkedin.com" not in [p["name"] for p in people]


def test_a_profile_check_says_verified_likely_or_unconfirmed_and_never_more():
    url = "https://www.linkedin.com/in/example-rosalind/"
    t = discovery.parse_result_title
    assert discovery.profile_status(t("Rosalind Achterberg - Kestrel Mutual"), url, "Kestrel Mutual",
                                    "Rosalind Achterberg") == "verified"
    assert discovery.profile_status(t("Rosalind Achterberg - Manchester, England"), url,
                                    "Kestrel Mutual", "Rosalind Achterberg") == "likely"
    assert discovery.profile_status(t("Rosalind Achterberg - Fenwick Lane Insurance"), url,
                                    "Kestrel Mutual", "Rosalind Achterberg") == "unconfirmed"
    assert discovery.profile_status(t("Corwin Haldane - Kestrel Mutual"), url, "Kestrel Mutual",
                                    "Rosalind Achterberg") == "unconfirmed"   # someone else
    assert discovery.profile_status(t("Rosalind Achterberg - Kestrel Mutual"),
                                    "https://uk.linkedin.com/jobs/view/1", "Kestrel Mutual") == "unconfirmed"
    # The check is a search, run with the domain filter: the person's name quoted, nothing else.
    assert sources.linkedin_check("Rosalind Achterberg", "Kestrel Mutual Ltd") == \
        '"Rosalind Achterberg" Kestrel Mutual'


@pytest.mark.parametrize("title,want", [
    ("Rosalind Achterberg - Kestrel Mutual", ("Rosalind Achterberg", "", "Kestrel Mutual", "")),
    ("Corwin Haldane, PhD - Pricing Lead - Kestrel Mutual",
     ("Corwin Haldane", "Pricing Lead", "Kestrel Mutual", "")),
    ("Tamsin Oyelaran MBA (She/Her) - Head of Data at Harrow Point Media ...",
     ("Tamsin Oyelaran", "Head of Data at Harrow Point Media", "Harrow Point Media", "")),
    ("Idris Corrie - Greater Manchester, England", ("Idris Corrie", "", "", "Greater Manchester, England")),
    ("Rhian Pellow - Data and Analytics Leader", ("Rhian Pellow", "Data and Analytics Leader", "", "")),
    ("12 Data jobs in Manchester", ("", "", "", "")),
])
def test_a_result_title_says_who_and_where(title, want):
    got = discovery.parse_result_title(title)
    assert (got["name"], got["headline"], got["employer"], got["location"]) == want


def test_their_connections_come_first_ranked_and_never_twice():
    conns = [
        {"name": "Corwin Haldane", "company": "Kestrel Mutual Ltd", "title": "Head of Finance",
         "linkedin_url": "https://www.linkedin.com/in/example-corwin", "connected_on": "03 Jan 2024"},
        {"name": "Tamsin Oyelaran", "company": "Kestrel Mutual", "title": "Senior Data Scientist",
         "linkedin_url": "https://www.linkedin.com/in/example-tamsin", "connected_on": "12 May 2022"},
        {"name": "Rhian Pellow", "company": "Fenwick Lane Insurance", "title": "Data Analyst",
         "linkedin_url": "https://www.linkedin.com/in/example-rhian", "connected_on": ""},
        {"name": "Idris Corrie", "company": "Kestrel Mutual", "title": "Analytics Engineer",
         "linkedin_url": "https://www.linkedin.com/in/example-idris", "connected_on": ""},
    ]
    book = [{"contact_id": "c1", "name": "Idris Corrie", "company": "Kestrel Mutual",
             "linkedin_url": "https://www.linkedin.com/in/example-idris"}]
    got = sources.from_connections("Kestrel Mutual", conns, book)
    assert [p["name"] for p in got] == ["Tamsin Oyelaran", "Corwin Haldane"]   # function first
    assert all(p["route"] == "connection" and p["channel"] == "message" for p in got)
    assert all(p["evidence"].startswith("your connections export") for p in got)
    # Through the harvest, someone they know is marked a message and ranked warm.
    run = sources.harvest(RESULTS, "Kestrel Mutual", today=TODAY, connections=conns, contacts=book)
    tamsin = next(p for p in run["keep"] if p["name"] == "Tamsin Oyelaran")
    assert tamsin["first_degree"] and tamsin["route"] == "connection"
    assert run["keep"][0]["name"] == "Tamsin Oyelaran"
    assert any(p.get("name") == "Idris Corrie" and w == "already in your contact book"
               for p, w in run["dropped"])


def test_a_people_search_is_plain_words_one_title_at_a_time():
    qs = discovery.queries_for("Kestrel Mutual Ltd")
    assert qs == ["Kestrel Mutual Head of Data Manchester",
                  "Kestrel Mutual Staff Data Scientist Manchester"]
    assert all(" OR " not in q and "linkedin.com" not in q and '"' not in q for q in qs)
    assert discovery.queries_for("Kestrel Mutual", titles=["Pricing Lead", "Actuary", "Third"]) \
        == ["Kestrel Mutual Pricing Lead Manchester", "Kestrel Mutual Actuary Manchester"]
    # An alumni anchor is history and stays quoted, so one word cannot match everyone.
    assert discovery.queries_for("Oakmere Foods", mode="alumni_employer")[0].startswith('"Oakmere Foods" ')


def test_a_browser_read_is_for_the_short_list_only(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    monkeypatch.setattr(reading, "browser_gate", lambda *a, **k: "")
    import state
    # In the contact book: a short list refuses an id that names nobody (it used to take any).
    rosalind = {"contact_id": "kestrel_rosalind", "name": "Rosalind Achterberg",
                "company": "Kestrel Mutual", "location": "Manchester", "channel": "connection",
                "status": "not_contacted"}
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [rosalind])
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    page = tmp_path / "page.txt"
    page.write_text("Rosalind Achterberg\nHead of Pricing\nManchester\nContact info\n· 2nd\n"
                    "Connect\nMessage\nMore\nAbout\nPricing work.\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not on today's short list"):
        reading.main(["read", "kestrel_rosalind", str(page), "--source", "browser",
                      "--name", "Rosalind Achterberg", "--company", "Kestrel Mutual"])
    assert not (tmp_path / "documents" / "network" / "kestrel_rosalind").exists()
    got = reading.shortlist(["kestrel_rosalind"])
    assert got["added"] == ["kestrel_rosalind"] and reading.on_shortlist("kestrel_rosalind")
    assert reading.main(["read", "kestrel_rosalind", str(page), "--source", "browser",
                         "--name", "Rosalind Achterberg", "--company", "Kestrel Mutual"]) == 0


def test_the_paste_queue_offers_the_best_three_never_everyone(tmp_path, monkeypatch, capsys):
    import state
    import why
    contacts = [{"contact_id": f"c{i}", "name": f"Person {i}", "company": "Kestrel Mutual",
                 "status": "not_contacted"} for i in range(7)]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: contacts)
    monkeypatch.setattr(reading, "queue", lambda cs, today=None: list(cs))
    monkeypatch.setattr(why, "ranked", lambda cs, **k: list(cs))
    assert reading.main(["queue"]) == 0
    out = capsys.readouterr().out
    assert "7 draft(s) waiting" in out and "offer a paste for these 3 only" in out
    assert len(re.findall(r"^\s+\d+\. ", out, re.M)) == 3


def test_the_networking_tools_never_fetch_linkedin():
    # Every LinkedIn address the people side handles is a search result, read and never
    # opened. A fetch of linkedin.com from a session is refused by its robots.txt and
    # answered with HTTP 999; the person's own browser is the only reader.
    fetch = re.compile(r"urlopen|requests\.(?:get|post)|http\.client|curl |WebFetch\(|wget ")
    bad = []
    for p in sorted((ROOT / "tools" / "network").glob("*.py")) + [ROOT / "tools" / "place.py"]:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "linkedin" in line.lower() and fetch.search(line):
                bad.append(f"{p.relative_to(ROOT)}:{n}")
    assert bad == []
    # And the commands that drive a browser say it reads, never clicks.
    net = (ROOT / ".claude" / "commands" / "network.md").read_text(encoding="utf-8")
    assert "never a fetch of\n      linkedin.com from this session" in net or "LinkedIn is never fetched from a session" in net
    assert "Nothing is sent, clicked, connected or submitted by any rung" in net


# The shapes a real run at one employer brought back on 2026-10-18, names invented.
REAL_SHAPES = [
    {"title": "Ottoline Barraclough - Chief Data Officer - Kestrel Mutual",
     "url": "https://www.linkedin.com/in/example-ottoline"},
    {"title": "Fenella Quarrie - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-fenella"},
    {"title": "Bastian Merriweather - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-bastian"},
    {"title": "M. Ilyas Tremayne - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-ilyas"},
    {"title": "Gideon Ashworth - Former President and CEO, Kestrel Mutual",
     "url": "https://www.linkedin.com/in/example-gideon"},
    {"title": "Perpetua Lindqvist on LinkedIn: Data Engineer - Willowmere",
     "url": "https://www.linkedin.com/posts/example-perpetua_data-engineer-activity-7380000000000000000-AbCd"},
]


def test_a_real_runs_shapes_rank_the_known_leader_first_and_keep_nobody_wrong():
    # A real run ranked a Chief Data Officer last, below eight people whose job nobody
    # knew and a former CEO; took a surname off; and kept a post about another company.
    got = sources.harvest(REAL_SHAPES, "Kestrel Mutual", query="Kestrel Mutual Head of Data Manchester",
                          today=TODAY, connections=[], contacts=[])
    names = [p["name"] for p in got["keep"]]
    assert names[0] == "Ottoline Barraclough", names
    assert "M. Ilyas Tremayne" in names                       # the whole name
    assert "Gideon Ashworth" not in names and any(
        p["name"] == "Gideon Ashworth" and w.startswith("has moved on") for p, w in got["dropped"])
    everyone = [p["name"] for p in discovery.people_from_results(REAL_SHAPES, "Kestrel Mutual",
                                                                 today=TODAY)]
    assert "Perpetua Lindqvist" not in everyone               # a post about Willowmere
    unknown = [p for p in got["keep"] if not p.get("title")]
    assert unknown and all(any("title is not in the search result" in w
                                for _, w in p["why"]["reasons"]) for p in unknown)


def test_letters_after_a_name_come_off_and_a_short_surname_stays():
    for title, name in (("Mary Ann Smith - Kestrel Mutual", "Mary Ann Smith"),
                        ("M. Ilyas Tremayne - Kestrel Mutual", "M. Ilyas Tremayne"),
                        ("Tamsin Oyelaran CFA - Kestrel Mutual", "Tamsin Oyelaran"),
                        ("Corwin Haldane P.Eng. - Kestrel Mutual", "Corwin Haldane"),
                        ("Rhian Pellow PhD - Kestrel Mutual", "Rhian Pellow")):
        assert discovery.parse_result_title(title)["name"] == name, title
    got = discovery.parse_result_title("Gideon Ashworth - Former President and CEO, Kestrel Mutual")
    assert got["headline"] == "Former President and CEO" and got["employer"] == "Kestrel Mutual"
    assert discovery.parse_result_title("Idris Corrie - Manchester, England, United Kingdom")["location"]
    got = discovery.parse_result_title("Anna Lee - Head of Data, Greater Manchester")
    assert (got["headline"], got["location"]) == ("Head of Data", "Greater Manchester")
    left = {"company": "Kestrel Mutual"}
    assert discovery.disqualify({**left, "title": "Former President and CEO"}, "Kestrel Mutual")
    for still_here in ("Former teacher turned data scientist at Kestrel Mutual",
                       "Ex-Googler, Data Lead", "Previously at Fenwick Lane, now Head of Data"):
        assert not discovery.disqualify({**left, "title": still_here}, "Kestrel Mutual"), still_here


def test_only_a_title_search_says_what_job_it_looked_for():
    # A posts search put its operators where the job goes ("( we're OR join my team ...)
    # site:linkedin.com/posts"), and a name check put the person's own name there.
    one = [{"title": "Fenella Quarrie - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-fenella"}]
    for kind, query in (("posts", '"Kestrel Mutual" ("we\'re hiring" OR "join my team") Data '
                                  'Scientist site:linkedin.com/posts'),
                        ("profile_check", '"Shirin Example" Kestrel Mutual')):
        got = sources.harvest(one, "Kestrel Mutual", kind=kind, query=query, today=TODAY,
                              connections=[], contacts=[])
        assert not got["keep"][0].get("found_for"), kind
        assert not any("came up in a search" in w for _, w in got["keep"][0]["why"]["reasons"])
    assert sources._searched_for('"Kestrel Mutual" ("Head of Data" OR Lead) -site:x.com Manchester',
                                 "Kestrel Mutual") == "Head of Data Lead"


def _post_url(handle: str, day: datetime.date) -> str:
    ms = int(datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
             .timestamp() * 1000)
    return f"https://www.linkedin.com/posts/{handle}_data-team-activity-{ms << 22}-AbCd"


def test_a_post_is_dated_so_an_old_one_no_longer_passes_for_someone_there_now():
    # A 2023 post naming the employer was kept as "likely": its date was read and stored
    # where no check looked.
    results = [
        {"title": "Perpetua Lindqvist on LinkedIn: Kestrel Mutual's data team in 2023",
         "url": _post_url("example-perpetua", datetime.date(2023, 3, 1))},
        {"title": "Hal Okonedo on LinkedIn: Kestrel Mutual is growing its data team",
         "url": _post_url("example-hal", datetime.date(2026, 10, 1))},
    ]
    got = sources.harvest(results, "Kestrel Mutual", kind="posts", today=TODAY,
                          connections=[], contacts=[])
    assert [p["name"] for p in got["keep"]] == ["Hal Okonedo"]
    assert any(p["name"] == "Perpetua Lindqvist" and w.startswith("stale")
               for p, w in got["dropped"])
    assert got["keep"][0]["signal_date"] == "2026-10-01"


def test_a_name_check_keeps_only_that_person_with_the_job_the_page_gave_them():
    # Fed the results of a search for one speaker, harvest kept four other people the
    # same results named, credited to that search; and the speaker page's title was lost,
    # so an AVP ranked with the unknowns.
    results = [
        {"title": "Shirin Example - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-shirin"},
        {"title": "Fenella Quarrie - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-fenella"},
        {"title": "Bastian Merriweather - Kestrel Mutual", "url": "https://www.linkedin.com/in/example-bastian"},
    ]
    page = {"title": "AVP, Data Platforms",
            "evidence": "speaker at an invented summit 2026 (https://example.com/speakers)"}
    got = sources.harvest(results, "Kestrel Mutual", kind="profile_check", today=TODAY,
                          connections=[], contacts=[], name="Shirin Example", known=page)
    assert [p["name"] for p in got["keep"]] == ["Shirin Example"]
    p = got["keep"][0]
    assert p["title"] == "AVP, Data Platforms" and p["title_source"] == page["evidence"]
    assert p["evidence"].startswith(page["evidence"] + "; then search result")
    assert not any("title is not in the search result" in w for _, w in p["why"]["reasons"])
    import why
    assert why.seniority(p["title"]) == "senior"            # AVP, SVP and EVP are senior
    assert why.seniority("SVP, Data") == why.seniority("EVP Operations") == "senior"


def test_name_checks_are_capped_and_the_plan_says_so():
    people = [{"name": f"Person {i}", "name_only": True} for i in range(6)] + [{"name": "Known"}]
    assert [p["name"] for p in sources.to_check(people)] == ["Person 0", "Person 1", "Person 2"]
    assert sources.CHECKS_PER_COMPANY == 3


def test_a_short_batch_counts_everyone_found_not_only_those_it_can_write_to():
    line = sources.short_batch(2, 25, {"title_search": 12}, have_connections=True, named=12)
    assert line.startswith("I found 12 people; 2 of the 25 this run could write to")
    assert "the other 10 need a look first" in line
    assert sources.short_batch(2, 25, {}, have_connections=True).startswith("I found 2 of the 25")
