"""What one long networking session on the newest release found, each from raw page text.

A person ran discovery, the one-page reads and first notes for an afternoon on their own
computer (2026-10-19). Each case here is the shape of a page or a draft from that
session, written out with invented people and employers: the sent-invitations list
gluing a note onto the next person, every contact missing from the ten loaded cards
of 425 called gone, a nickname and letters after a name that never matched, a
promotional card read as a person, nobody screened by where they work, a sales
executive kept, an industry body taken as the employer, an About cut to its first
sentence, a peer held to a senior reader's length, a rule with no hint, a reason that
said the wrong thing, a SKIP that did not say how to close, and a pack's own comment
read as prose.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import compose  # noqa: E402
import discovery  # noqa: E402
import reading  # noqa: E402
import voice_check  # noqa: E402

TODAY = datetime.date(2026, 10, 19)


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    return tmp_path


# ------------------------------------------------------------ G1. a note under a card

# A request sent with a note: name, headline, "Sent ...", Withdraw, then the note's
# preview and "...show more". Read with the preview in, every later card was named
# after the note above it.
INVITES_WITH_NOTES = """Manage invitations
Received
Sent
People (3)
Rosalind Achterberg
Head of Pricing Analytics at Kestrel Mutual
Sent 2 days ago
Withdraw
Hi Rosalind, we were both at Oakmere Foods and I would like to hear how you found the
...show more
Idris Corrie
Data Analyst at Fenwick Lane Insurance
Sent 1 week ago
Withdraw
Good to meet you at the forecasting meetup last week
Tamsin Oyelaran
Head of Demand Forecasting at Fernhill Freight
Sent 2 weeks ago
Withdraw
Hi Tamsin, your post on cold-chain forecasting from weather feeds was a good read
...show more
"""


def test_a_note_under_a_sent_request_never_becomes_the_next_persons_name():
    cards = reading.invitations(INVITES_WITH_NOTES, TODAY)
    assert [c["name"] for c in cards] == ["Rosalind Achterberg", "Idris Corrie", "Tamsin Oyelaran"]
    assert [c["headline"] for c in cards] == [
        "Head of Pricing Analytics at Kestrel Mutual", "Data Analyst at Fenwick Lane Insurance",
        "Head of Demand Forecasting at Fernhill Freight"]
    assert [c["sent"] for c in cards] == ["2026-10-17", "2026-10-12", "2026-10-05"]
    # The notes are the person's own words to them: never anyone's name or headline.
    assert not any("Hi " in c["name"] + c["headline"] or "meetup" in c["headline"] for c in cards)


# ------------------------------------------------------------ G2. ten loaded of 425

INVITES_FIRST_TEN = """Manage invitations
Sent
People (425)
Rosalind Achterberg
Head of Pricing Analytics at Kestrel Mutual
Sent 2 days ago
Withdraw
Idris Corrie
Data Analyst at Fenwick Lane Insurance
Sent 1 week ago
Withdraw
"""


def _request(cid, date):
    return {"contact_id": cid, "date": date, "direction": "out", "channel": "linkedin",
            "scenario": "connection_request", "summary": "connection request", "full_text": ""}


def _book():
    return [{"contact_id": "kestrel_achterberg", "name": "Rosalind Achterberg",
             "company": "Kestrel Mutual", "status": "awaiting_reply"},
            {"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran",
             "company": "Fernhill Freight", "status": "awaiting_reply"},
            {"contact_id": "oakmere_halloway", "name": "Wren Halloway",
             "company": "Oakmere Foods", "status": "awaiting_reply"}]


def test_only_a_request_newer_than_the_oldest_loaded_card_can_be_called_gone():
    # The list is newest first and loads about ten of its 425. Tamsin's request went after
    # the oldest card loaded and is not on it: accepted or withdrawn. Wren's went weeks
    # before anything loaded, so the page says nothing about it either way.
    cards = reading.invitations(INVITES_FIRST_TEN, TODAY)
    threads = [_request("kestrel_achterberg", "2026-10-17"), _request("fernhill_oyelaran", "2026-10-15"),
               _request("oakmere_halloway", "2026-08-30")]
    got = reading.match_invitations(cards, _book(), threads=threads,
                                    total=reading.invitations_total(INVITES_FIRST_TEN))
    assert [c["contact_id"] for c in got["gone"]] == ["fernhill_oyelaran"]
    assert [c["contact_id"] for c in got["unchecked"]] == ["oakmere_halloway"]
    # The whole list on the page: everyone missing from it is gone.
    whole = INVITES_FIRST_TEN.replace("People (425)", "People (2)")
    got = reading.match_invitations(cards, _book(), threads=threads,
                                    total=reading.invitations_total(whole))
    assert sorted(c["contact_id"] for c in got["gone"]) == ["fernhill_oyelaran", "oakmere_halloway"]
    assert got["unchecked"] == []
    # A page that gave no cards and no count says nothing about anyone.
    nothing = reading.match_invitations([], _book(), threads=threads)
    assert nothing["gone"] == [] and len(nothing["unchecked"]) == 3


def test_the_invitations_command_says_who_it_could_not_check(here, monkeypatch, capsys):
    import state
    today = datetime.date.today()
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: _book())
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [
        _request("kestrel_achterberg", (today - datetime.timedelta(days=2)).isoformat()),
        _request("fernhill_oyelaran", (today - datetime.timedelta(days=4)).isoformat()),
        _request("oakmere_halloway", (today - datetime.timedelta(days=50)).isoformat())])
    monkeypatch.setattr(state, "THREADS_CSV", str(here / "network_threads.csv"))
    (here / "network_threads.csv").write_text("contact_id\n")
    page = here / "invites.txt"
    page.write_text(INVITES_FIRST_TEN, encoding="utf-8")
    assert reading.main(["invitations", str(page)]) == 0
    out = capsys.readouterr().out
    assert "no longer pending: Tamsin Oyelaran" in out
    assert "Wren Halloway" not in out.split("not checked")[0]
    assert "not checked" in out and "2 of 425" in out and "Wren Halloway" in out


# ------------------------------------------------------------ G3. the same person

@pytest.mark.parametrize("card_name,contact_name", [
    ("Tamsin Rhian (Wren) Oyelaran, Ph. D.", "Wren Oyelaran"),      # the nickname in brackets
    ("Tamsin Rhian (Wren) Oyelaran, Ph. D.", "Tamsin Oyelaran"),    # the given name, no middle
    ("Wren Oyelaran", "Tamsin (Wren) Oyelaran"),                    # either side may hold it
    ("Tamsin Oyelaran PhD, MBA", "Tamsin Rhian Oyelaran"),
    ("Tamsin Oyelaran, C.F.A., PMP", "Tamsin Oyelaran"),
    ("Dr. Tamsin Oyelaran (She/Her)", "Tamsin Oyelaran"),
])
def test_a_card_with_a_nickname_letters_and_a_middle_name_is_the_contact(card_name, contact_name):
    card = {"name": card_name, "headline": "Head of Demand Forecasting at Fernhill Freight",
            "sent": "2026-10-12"}
    book = [{"contact_id": "fernhill_oyelaran", "name": contact_name, "company": "Fernhill Freight",
             "status": "not_contacted"}]
    got = reading.match_invitations([card], book, threads=[])
    assert [c["contact_id"] for _, c in got["pending"]] == ["fernhill_oyelaran"], card_name


@pytest.mark.parametrize("card_name,contact_name", [
    ("Tamsin Rhian Oyelaran", "Rhian Oyelaran"),        # a middle name is not who they are
    ("Tamsin Oyelaran", "Tamsin Okafor"),
    ("Tamsin (Wren) Oyelaran", "Idris Oyelaran"),
])
def test_another_person_with_the_surname_is_never_matched(card_name, contact_name):
    assert not reading.same_person(card_name, contact_name)


# ------------------------------------------------------------ G4 and G5. a people page

PEOPLE = """Looking to get hired?
Jobs where you could be a top applicant
Pricing Analyst
Kestrel Mutual
Manchester, England, United Kingdom
Corwin Haldane
View full list
Rosalind Achterberg
2nd
Head of Pricing Analytics at Kestrel Mutual
Manchester, England, United Kingdom
Connect
Rhian Pellow
2nd
Pricing Lead
Manchester, England, United Kingdom
Current: Pricing Lead at Fenwick Lane Insurance
Connect
Idris Corrie
3rd+
Data Analyst
Manchester, England, United Kingdom
Message
Tamsin Oyelaran
2nd
Head of Demand Forecasting @ Fernhill Freight | ex-Kestrel Mutual
Manchester, England, United Kingdom
Connect
"""


def test_a_promotional_card_is_never_a_person():
    people = reading.people_page(PEOPLE, "Kestrel Mutual")
    names = [p["name"] for p in people]
    assert names == ["Rosalind Achterberg", "Rhian Pellow", "Idris Corrie", "Tamsin Oyelaran"]
    import sources
    assert "View full list" not in [p["name"] for p in sources.people_paste(PEOPLE, "Kestrel Mutual")]
    assert "Corwin Haldane" not in [p["name"] for p in sources.people_paste(PEOPLE, "Kestrel Mutual")]


def test_each_card_is_screened_by_where_it_says_they_work():
    by = {p["name"]: p for p in reading.people_page(PEOPLE, "Kestrel Mutual")}
    assert by["Rosalind Achterberg"]["where"] == "at"
    assert (by["Rhian Pellow"]["where"], by["Rhian Pellow"]["employer"]) == (
        "elsewhere", "Fenwick Lane Insurance")
    assert by["Idris Corrie"]["where"] == "unknown"
    # A past employer named in the headline is not where they work.
    assert (by["Tamsin Oyelaran"]["where"], by["Tamsin Oyelaran"]["employer"]) == (
        "elsewhere", "Fernhill Freight")
    assert reading.screen(by["Rosalind Achterberg"], "Kestrel Mutual") == (True, "")
    keep, why = reading.screen(by["Rhian Pellow"], "Kestrel Mutual")
    assert not keep and "Fenwick Lane Insurance" in why and "Kestrel Mutual" in why
    keep, why = reading.screen(by["Idris Corrie"], "Kestrel Mutual")
    assert keep and "does not say where" in why
    # A request already pending is said before where they work: it is recorded as sent.
    keep, why = reading.screen(dict(by["Rhian Pellow"], reach="pending"), "Kestrel Mutual")
    assert not keep and "already pending" in why


def test_an_alias_the_profile_holds_counts_as_the_employer(monkeypatch):
    import company_key
    monkeypatch.setitem(company_key.ALIASES, "kmu", "kestrel mutual")
    page = "Rhian Pellow\n2nd\nPricing Lead | KMU\nManchester, England, United Kingdom\nConnect\n"
    (p,) = reading.people_page(page, "Kestrel Mutual")
    assert p["where"] == "at"


def test_the_people_command_counts_each_kind_apart(here, capsys):
    page = here / "people.txt"
    page.write_text(PEOPLE, encoding="utf-8")
    assert reading.main(["people", str(page), "--company", "Kestrel Mutual"]) == 0
    out = capsys.readouterr().out
    first = out.splitlines()[0]
    assert "4 on the page: 1 at Kestrel Mutual, 2 elsewhere, 1 where the card does not say" in first
    assert "View full list" not in out


# ------------------------------------------------------------ G6 and J1. revenue roles

@pytest.mark.parametrize("title", [
    "Data & AI Sales Executive", "Account Executive, Enterprise", "Senior Account Manager",
    "Business Development Manager, Machine Learning", "Head of Partnerships",
    "Strategic Partnerships Director", "Go-To-Market Lead", "GTM Strategy Manager",
    "Customer Success Manager", "Head of Sales", "VP Sales", "Sales Director, Data Platforms",
    "Head of Industry, Financial Services", "Solutions Architect, Data & AI",
])
def test_a_sales_or_partnerships_title_is_a_revenue_role(title):
    assert discovery.disqualify({"title": title}, "Brannock"), title


@pytest.mark.parametrize("title", [
    "Senior Data Scientist, Go-To-Market", "Analytics Manager, Partnerships",
    "Data Analyst, Customer Success", "Sales Analytics Manager", "Head of Data & Analytics",
    "Pricing Analyst", "Revenue Management Analyst", "GTM Analytics Lead",
    "Business Intelligence Lead, Sales", "Director of Data Science",
])
def test_a_data_or_analytics_title_is_still_kept(title):
    assert discovery.disqualify({"title": title}, "Brannock") is None, title


def test_the_reason_says_what_it_found():
    keep, why = reading.verdict({"headline": "Head of Industry, Financial Services",
                                 "company": "Brannock", "location": ""}, "Brannock")
    assert not keep and "industry head" in why and "Head of Industry" in why
    assert "dressed as technical" not in why
    keep, why = reading.verdict({"headline": "Data & AI Sales Executive", "company": "Brannock",
                                 "location": ""}, "Brannock")
    assert not keep and "a sales role" in why and "Sales Executive" in why
    # A title that reads as technical keeps the person's own reason, which was written for it.
    why = discovery.disqualify({"title": "Solutions Architect, Data & AI"}, "Brannock")
    assert "dressed as technical" in why


# ------------------------------------------------------------ G7. an organisation badge

def _card(*middle, experience=()):
    return "\n".join(["Rosalind Achterberg", "2nd", "Head of Pricing Analytics at Kestrel Mutual",
                      "Manchester, England, United Kingdom", "Contact info", *middle,
                      "500+ connections", "Connect", "Message", "More", "About",
                      "I build pricing models insurers can explain.", *experience]) + "\n"


def test_the_headline_employer_beats_an_organisation_badge_on_the_card():
    r = reading.parse(_card("Northgate Pricing Society", "University of Leeds"),
                      name="Rosalind Achterberg", company="Kestrel Mutual", source="browser",
                      today=TODAY)
    assert r["current"] == "Kestrel Mutual"


def test_a_side_role_listed_first_is_not_the_employer_the_headline_names():
    r = reading.parse(_card("Northgate Pricing Society", experience=(
        "Experience", "Committee Member", "Northgate Pricing Society", "Jan 2025 - Present",
        "Head of Pricing Analytics", "Kestrel Mutual", "Jan 2024 - Present")),
        name="Rosalind Achterberg", company="Kestrel Mutual", source="browser", today=TODAY)
    assert r["current"] == "Kestrel Mutual"
    # With no employer in the headline, the first Experience entry stands.
    plain = _card("Kestrel Mutual", experience=(
        "Experience", "Head of Pricing Analytics", "Kestrel Mutual", "Jan 2024 - Present"))
    plain = plain.replace("Head of Pricing Analytics at Kestrel Mutual", "Head of Pricing Analytics")
    assert reading.parse(plain, name="Rosalind Achterberg", company="Kestrel Mutual",
                         today=TODAY)["current"] == "Kestrel Mutual"


# ------------------------------------------------------------ G8. the whole About

LONG_ABOUT = ("I lead pricing for personal lines at a mutual insurer, and I have done so for six "
              "years. Before that I was an actuarial analyst, which is where I learned to distrust "
              "any model nobody can explain to an underwriter. My team is eleven people across "
              "Manchester and Leeds, and we hire for curiosity before tools. Most of what we do is "
              "unglamorous: cleaning claims history, agreeing definitions with finance, and making "
              "sure a rate change can be traced back to the evidence behind it. Our remit now spans "
              "pricing and revenue intelligence, which means demand elasticity, competitor rate "
              "monitoring and the renewal book, all in one team.")


def test_the_whole_about_is_kept_for_grounding_and_a_short_one_shown():
    page = _card().replace("I build pricing models insurers can explain.", LONG_ABOUT)
    r = reading.parse(page, name="Rosalind Achterberg", company="Kestrel Mutual", today=TODAY)
    assert len(LONG_ABOUT) > reading.ABOUT_CHARS and r["about"] == LONG_ABOUT
    ok, why = reading.grounded("Your team's remit spanning pricing and revenue intelligence, "
                               "with elasticity and competitor monitoring", r)
    assert ok and "about" in why
    about = [h for h in reading.hooks(r, TODAY) if h[1] == "about"]
    assert about and len(about[0][3]) <= 201
    # The verdict reads what it always read: the opening of the About, never more.
    later = dict(r, about=LONG_ABOUT + " I left as head of pricing at my last insurer in 2019.")
    assert reading.verdict(later, "Kestrel Mutual")[0]


# ------------------------------------------------------------ H1. a peer's length

def test_a_peer_with_nothing_shared_gets_the_standard_length():
    found = {"headline": "Science Manager, Demand Forecasting", "about": "", "items": [],
             "shared": {}, "sources": [{"kind": "paste"}]}
    assert compose.shape_for("Science Manager, Demand Forecasting", found) == "shared"
    assert compose.shape_for("Director of Data Science", found) == "brief"
    ground = ("Your work on demand forecasting for regional depots, and how your team runs its "
              "forecast reviews with depot managers")
    note = compose.first_note("Rosalind Achterberg", ground, shape="shared")
    assert compose.BRIEF_CHARS < len(note) <= 300


# ------------------------------------------------------------ H2. a rule with its fix

def test_a_buried_employer_says_what_to_do_and_offers_the_reordering():
    note = ("Hi Wren, hope you're well. Your post on forecasting depot demand from weather feeds "
            "was a good read. I work in supply-chain analytics in Manchester now. I spent four "
            "years at Brindle & Hart Logistics before that. Would you have 15 minutes for a few "
            "questions sometime?")
    found = [v for v in compose.validate(note, "connection", name="Wren Halloway",
                                         employers=["Brindle & Hart Logistics"])
             if v.rule == "employers_buried"]
    assert len(found) == 1
    text = found[0].text
    assert text.startswith("Brindle & Hart Logistics") and "first sentence" in text
    suggested = text.split("for example: ", 1)[1]
    assert compose.employers_early(suggested, ["Brindle & Hart Logistics"]) == []
    assert suggested.startswith("Hi Wren, hope you're well. I spent four years at Brindle")
    assert sorted(suggested.split()) == sorted(note.split())    # the same words, reordered
    # Nothing to move when no sentence names it: the hint alone.
    bare = note.replace("Brindle & Hart Logistics", "a logistics firm")
    (v,) = [v for v in compose.validate(bare, "connection", name="Wren Halloway",
                                        employers=["Brindle & Hart Logistics"])
            if v.rule == "employers_buried"]
    assert "first sentence" in v.text and "for example" not in v.text


# ------------------------------------------------------------ J2. what a SKIP says to run

def test_a_skip_prints_the_command_and_when_to_run_it(here, capsys):
    reading.save("brannock_corrie", {"name": "Idris Corrie", "company": "Brannock",
                                     "headline": "Head of Industry, Financial Services",
                                     "location": "", "sources": [{"kind": "paste"}], "items": []})
    assert reading.main(["verdict", "brannock_corrie"]) == reading.EXIT["skip"]
    out = capsys.readouterr().out
    line = next(x for x in out.splitlines() if "reading.py skip" in x)
    assert "once the person has confirmed nothing else is needed" in line
    cmd = line.split("python3 ", 1)[1].split(" (", 1)[0]
    import shlex
    argv = shlex.split(cmd)
    assert argv[:3] == ["tools/network/reading.py", "skip", "brannock_corrie"]
    assert argv[3] == "--reason" and "Head of Industry" in argv[4]


# ------------------------------------------------------------ J3. the tools' own comments

def test_a_stage_comment_the_tools_write_is_not_prose():
    pack = ("<!-- stages: Recruiter screen; Technical interview -->\n"
            "# Interview prep\n\nI worked on pricing models for three years and enjoyed most of it.\n")
    assert not [f for f in voice_check.check(pack) if f["rule"] == "em-dash"]
    assert voice_check.check("I worked on pricing -- mostly for insurers.")    # prose still read
