"""What one real networking round on 3.8.0 found in the tools, each case from its shape.

People read and never written to the book, so their sends could not be logged; a short
list that took ids naming nobody; a page refused for its pace after it was already open;
InMail credits that never came back; requests already Pending that nothing saw; a profile
with no Connect button taken for one a note could go to; an employer with no stored filter;
research titles ranked as the person's function; a fourth note at an employer where three
sat unanswered; and drafts handed over with no word of the time where they would land.
Invented people and employers only, against the example profile (Manchester).
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import discovery  # noqa: E402
import pace  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date.today()

@pytest.fixture(autouse=True)
def _today():
    """TODAY is the day each test runs, not the day this file was loaded: a run that
    crossed midnight compared the one with the other (Windows, 2026-10-26)."""
    global TODAY
    TODAY = datetime.date.today()



def _row(cid, name, company, **kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update({"contact_id": cid, "name": name, "company": company, "status": "not_contacted",
                **kw})
    return row


@pytest.fixture
def book(tmp_path, monkeypatch):
    """A contact book and a message log of the test's own, in files, and every reading,
    draft and ledger under tmp_path: nothing reaches the shared example state."""
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    cpath, tpath = tmp_path / "contacts.csv", tmp_path / "threads.csv"
    state._write_csv(str(cpath), [], schema.CONTACT_COLUMNS)
    state._write_csv(str(tpath), [], schema.THREAD_COLUMNS)
    monkeypatch.setattr(state, "load_contacts",
                        lambda path=None: state._read_csv(str(cpath), schema.CONTACT_COLUMNS))
    monkeypatch.setattr(state, "save_contacts",
                        lambda rows, path=None: state._write_csv(str(cpath), rows,
                                                                 schema.CONTACT_COLUMNS))
    monkeypatch.setattr(state, "load_threads",
                        lambda path=None: state._read_csv(str(tpath), schema.THREAD_COLUMNS))
    monkeypatch.setattr(state, "save_threads",
                        lambda rows, path=None: state._write_csv(str(tpath), rows,
                                                                 schema.THREAD_COLUMNS))

    class Book:
        path = tmp_path

        @staticmethod
        def put(*rows):
            state._write_csv(str(cpath), list(rows), schema.CONTACT_COLUMNS)

        @staticmethod
        def contacts():
            return state.load_contacts()

        @staticmethod
        def threads():
            return state.load_threads()

    return Book


# A profile page as a browser read gives it, invented.
def _page(name="Tamsin Oyelaran", headline="Head of Demand Forecasting at Fernhill Freight",
          place="Manchester, England, United Kingdom", degree="2nd",
          buttons=("Connect", "Message", "More"), employer="Fernhill Freight"):
    return "\n".join([name, f"· {degree}", headline, place, "Contact info", "500+ connections",
                      *buttons, "About", "I build forecasts that depot teams actually use, and "
                      "I like explaining them to the people who plan around them every week.",
                      "Experience", headline.split(" at ")[0], f"{employer} · Full-time",
                      "Jan 2024 - Present · 1 yr 10 mos", place]) + "\n"


def _read_about(cid, name="Tamsin Oyelaran", company="Fernhill Freight",
                url="https://www.linkedin.com/in/tamsin-oyelaran-example", **kw):
    got = reading.parse(_page(name=name, **kw), name=name, company=company, source="paste",
                        url=url)
    reading.save(cid, got)
    return got


# ------------------------------------------------------------ 12. read, never in the book

def test_a_send_to_someone_read_but_never_written_to_the_book_is_logged(book):
    _read_about("fernhill_oyelaran")
    contacts, threads = [], []
    row = state.sent(contacts, threads, "fernhill_oyelaran", TODAY, channel="inmail",
                     text="Hi Tamsin, a note.", subject="Demand forecasting")
    assert row["contact_id"] == "fernhill_oyelaran" and len(threads) == 1
    (c,) = contacts
    assert (c["name"], c["company"], c["status"]) == ("Tamsin Oyelaran", "Fernhill Freight",
                                                      "awaiting_reply")
    assert c["linkedin_url"].endswith("/in/tamsin-oyelaran-example")
    assert c["company_key"] == state.company_key("Fernhill Freight")


def test_the_same_person_under_another_id_is_never_a_second_row(book):
    _read_about("fernhill_tamsin")
    known = _row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight",
                 linkedin_url="https://www.linkedin.com/in/tamsin-oyelaran-example/")
    contacts, threads = [known], []
    row = state.sent(contacts, threads, "fernhill_tamsin", TODAY, text="Hi Tamsin, a note.")
    assert row["contact_id"] == "fernhill_oyelaran" and len(contacts) == 1
    assert contacts[0]["status"] == "awaiting_reply"
    # Nothing read and nothing in the book: refused, and it says how.
    with pytest.raises(ValueError, match="nothing read about them"):
        state.sent(contacts, threads, "kestrel_nobody", TODAY, text="Hi.")
    # A send refused for its words adds no row.
    _read_about("oakmere_corrie", name="Idris Corrie", company="Oakmere Foods",
                url="https://www.linkedin.com/in/idris-corrie-example",
                headline="Data Analyst at Oakmere Foods", employer="Oakmere Foods")
    with pytest.raises(ValueError, match="words that went are needed"):
        state.sent(contacts, threads, "oakmere_corrie", TODAY)
    assert len(contacts) == 1


def test_the_sent_command_logs_three_inmails_to_people_only_read(book, capsys):
    note = book.path / "note.txt"
    note.write_text("Hi, a note.", encoding="utf-8")
    for cid, name in (("fernhill_oyelaran", "Tamsin Oyelaran"), ("fernhill_corrie", "Idris Corrie"),
                      ("fernhill_allard", "Wren Allard")):
        _read_about(cid, name=name, url=f"https://www.linkedin.com/in/{cid}-example")
        assert state.main(["sent", cid, "--channel", "inmail", "--subject", "Forecasting",
                           "--text-file", str(note)]) == 0
    out = capsys.readouterr().out
    assert out.count("added from what was read about them") == 3
    assert "not recorded" not in out
    assert [c["contact_id"] for c in book.contacts()] == ["fernhill_oyelaran", "fernhill_corrie",
                                                         "fernhill_allard"]
    assert len(book.threads()) == 3


def test_a_draft_for_someone_only_read_puts_them_in_the_book(book, capsys):
    _read_about("fernhill_oyelaran")
    note = book.path / "note.txt"
    note.write_text("Hi Tamsin, your weather-feed forecasts for depots caught my eye.",
                    encoding="utf-8")
    assert reading.main(["draft", "fernhill_oyelaran", str(note)]) == 0
    assert "added at not_contacted" in capsys.readouterr().out
    (c,) = book.contacts()
    assert c["contact_id"] == "fernhill_oyelaran" and c["status"] == "not_contacted"
    assert "fernhill_oyelaran" in reading.queued_notes(book.contacts())
    # Already in the book under another id: refused, naming that id.
    _read_about("fernhill_tamsin")
    assert reading.main(["draft", "fernhill_tamsin", str(note)]) == reading.EXIT["error"]
    assert "already in the contact book as fernhill_oyelaran" in capsys.readouterr().out
    assert len(book.contacts()) == 1


# ------------------------------------------------------------ 13. an id that names nobody

def test_the_short_list_refuses_an_id_that_names_nobody(book, capsys):
    got = reading.shortlist(["kestrel_ghost"], TODAY, contacts=[], sends_left=10)
    assert got["unknown"] == ["kestrel_ghost"] and got["ids"] == []
    assert reading.main(["shortlist", "kestrel_ghost"]) == reading.EXIT["ok"]
    assert "nobody by these ids is in the contact book or read about yet" in capsys.readouterr().out
    # Someone read about (a name and an employer) is on it, and `next` says who and where.
    _read_about("fernhill_oyelaran")
    got = reading.shortlist(["fernhill_oyelaran"], TODAY, contacts=[], sends_left=10)
    assert got["added"] == ["fernhill_oyelaran"]


def test_next_names_someone_read_but_not_in_the_book(book):
    reading.save("fernhill_oyelaran", {"name": "Tamsin Oyelaran", "company": "Fernhill Freight",
                                       "sources": [{"kind": "public", "url":
                                                    "https://www.linkedin.com/in/tamsin-example"}],
                                       "location": "Manchester", "items": []})
    reading.shortlist(["fernhill_oyelaran"], TODAY, contacts=[], sends_left=10)
    nxt = reading.next_up(TODAY, contacts=[])
    assert nxt["name"] == "Tamsin Oyelaran" and nxt["linkedin_url"].endswith("tamsin-example")


# ------------------------------------------------------------ 14. a page already loaded

def _loaded(when, gap=0):
    pace.add_load("profile", when.isoformat(timespec="seconds"), gap, False, "earlier")


def test_a_list_page_right_after_another_is_read_with_nothing_held_back(book, monkeypatch,
                                                                         capsys):
    # No pause of the app's own since 2026-10-22: a page ten seconds after the last is read
    # as any other, and nothing is logged about it.
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    now = datetime.datetime.now()
    _loaded(now - datetime.timedelta(seconds=10))
    page = book.path / "people.txt"
    page.write_text("Juno Castellan • 2nd\nSenior Data Scientist at Larkspur\n"
                    "Manchester, England, United Kingdom\nConnect\n", encoding="utf-8")
    assert reading.main(["people", str(page), "--company", "Larkspur"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "Juno Castellan" in out and "not read." not in out
    assert "pace" not in out and "the next page at" not in out
    assert pace.friction() == [] and "breaches" not in pace.load()


def test_a_list_page_loaded_after_a_stop_is_kept_and_stops_the_run(book, monkeypatch, capsys):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    reading.stop("a security check appeared")
    page = book.path / "people.txt"
    page.write_text("Juno Castellan • 2nd\nSenior Data Scientist at Larkspur\nConnect\n",
                    encoding="utf-8")
    assert reading.main(["people", str(page), "--company", "Larkspur"]) == reading.EXIT["tomorrow"]
    out = capsys.readouterr().out
    assert "Juno Castellan" in out and "read nothing more today" in out


# ------------------------------------------------------------ 15. InMail credits

def _inmail(cid, day, direction="out", channel="inmail", scenario="first_message"):
    return {"contact_id": cid, "date": day.isoformat(), "direction": direction, "channel": channel,
            "scenario": scenario, "summary": "", "full_text": "words", "subject": ""}


MID = datetime.date(2026, 10, 20)


def test_a_reply_within_ninety_days_gives_the_credit_back(book):
    sent = [_inmail(f"c{i}", MID - datetime.timedelta(days=i + 1)) for i in range(5)]
    replies = [_inmail("c0", MID, direction="in", scenario="reply"),
               _inmail("c1", MID, direction="in", channel="linkedin", scenario="reply")]
    b = state.platform_budget([], sent, MID, inmail_balance={})
    assert (b["inmails_sent"], b["inmails_left"]) == (5, 0)
    b = state.platform_budget([], sent + replies, MID, inmail_balance={})
    assert (b["inmails_refunded"], b["inmails_left"]) == (2, 2)
    assert "credited back for a reply within 90 days" in b["inmails_source"]


def test_what_does_not_give_a_credit_back(book):
    old = MID - datetime.timedelta(days=95)
    threads = [_inmail("late", old), _inmail("late", MID, direction="in", scenario="reply"),
               _inmail("mail", MID - datetime.timedelta(days=2)),
               _inmail("mail", MID, direction="in", channel="email", scenario="reply"),
               _inmail("acc", MID - datetime.timedelta(days=2)),
               _inmail("acc", MID, direction="in", channel="connection",
                       scenario="connection_accepted")]
    assert state.inmail_refunds(threads) == []


def test_the_balance_linkedin_shows_wins_until_the_month_turns(book, capsys):
    sent = [_inmail(f"c{i}", MID - datetime.timedelta(days=i + 1)) for i in range(5)]
    state.record_inmails(3, [], sent, MID)
    b = state.platform_budget([], sent, MID)
    assert b["inmails_left"] == 3 and "the 3 LinkedIn showed on 2026-10-20" in b["inmails_source"]
    later = sent + [_inmail("c9", MID)]
    assert state.platform_budget([], later, MID)["inmails_left"] == 2
    back = later + [_inmail("c9", MID + datetime.timedelta(days=1), direction="in",
                            scenario="reply")]
    assert state.platform_budget([], back, MID + datetime.timedelta(days=1))["inmails_left"] == 3
    # A new month: the count from the log takes over again.
    nov = datetime.date(2026, 11, 2)
    b = state.platform_budget([], back, nov)
    assert b["inmails_left"] == b["inmails_limit"] and "counted from the log" in b["inmails_source"]
    assert state.main(["inmail-credits", "4", "--today", MID.isoformat()]) == 0
    assert "kept 4 as LinkedIn shows it" in capsys.readouterr().out


# ------------------------------------------------------------ 16. a request already Pending

LONG_PENDING = "Pending, click to withdraw invitation sent to Ana Rook"


def test_the_long_pending_label_is_read_on_a_card_and_a_profile():
    page = ("Ana Rook • 2nd\nSoftware Engineer at Larkspur\nManchester, England, United Kingdom\n"
            f"{LONG_PENDING}\nBo Venn • 2nd\nData Analyst at Larkspur\nManchester\nConnect\n")
    by = {p["name"]: p for p in reading.people_page(page, "Larkspur")}
    assert by["Ana Rook"]["reach"] == "pending" and by["Bo Venn"]["reach"] == "request"
    r = reading.parse(_page(name="Ana Rook", headline="Software Engineer at Larkspur",
                            buttons=(LONG_PENDING, "Message", "More"), employer="Larkspur"),
                      name="Ana Rook", company="Larkspur")
    assert r["reach"] == "pending"


def test_a_pending_card_is_recorded_as_sent_and_leaves_every_list(book, capsys):
    book.put(_row("larkspur_rook", "Ana Rook", "Larkspur", channel="connection",
                  linkedin_url="https://www.linkedin.com/in/example-ana"))
    page = book.path / "people.txt"
    page.write_text("Ana Rook • 2nd\nSoftware Engineer at Larkspur\n"
                    f"Manchester, England, United Kingdom\n{LONG_PENDING}\n"
                    "Bo Venn • 2nd\nData Analyst at Larkspur\nManchester\n"
                    "Pending\nhttps://www.linkedin.com/in/example-bo\n", encoding="utf-8")
    assert reading.main(["people", str(page), "--company", "Larkspur"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "pending: a request to larkspur_rook already went from LinkedIn itself" in out
    assert "1 not in the book already have a request Pending (Bo Venn)" in out and "--record" in out
    (ana,) = book.contacts()
    assert ana["status"] == "awaiting_reply"
    assert book.threads()[0]["scenario"] == state.OUTSIDE_SCENARIO
    assert reading.queue(book.contacts()) == []
    # With --record, the one not in the book is added, as sent: never a new note or InMail.
    assert reading.main(["people", str(page), "--company", "Larkspur", "--record"]) == 0
    capsys.readouterr()
    bo = next(c for c in book.contacts() if c["name"] == "Bo Venn")
    assert bo["status"] == "awaiting_reply" and bo["linkedin_url"].endswith("example-bo")
    assert len(book.contacts()) == 2


def test_a_profile_showing_pending_is_recorded_when_read(book, capsys):
    book.put(_row("larkspur_rook", "Ana Rook", "Larkspur", channel="connection"))
    page = book.path / "ana.txt"
    page.write_text(_page(name="Ana Rook", headline="Software Engineer at Larkspur",
                          buttons=("Pending", "Message", "More"), employer="Larkspur"),
                    encoding="utf-8")
    assert reading.main(["read", "larkspur_rook", str(page)]) == reading.EXIT["ok"]
    assert "recorded as sent" in capsys.readouterr().out
    assert book.contacts()[0]["status"] == "awaiting_reply"


# ------------------------------------------------------------ 17. no Connect button

def test_a_profile_with_no_connect_button_says_so_before_a_connection_note(book, capsys):
    book.put(_row("larkspur_venn", "Bo Venn", "Larkspur", channel="connection"))
    page = book.path / "bo.txt"
    page.write_text(_page(name="Bo Venn", headline="Data Scientist at Larkspur", degree="3rd",
                          buttons=("Message", "Follow", "More"), employer="Larkspur"),
                    encoding="utf-8")
    assert reading.main(["read", "larkspur_venn", str(page)]) == reading.EXIT["ok"]
    assert "shows no Connect button" in capsys.readouterr().out
    assert reading.load("larkspur_venn")["connect"] == "missing"
    note = book.path / "note.txt"
    note.write_text("Hi Bo, your churn models caught my eye.", encoding="utf-8")
    assert reading.main(["draft", "larkspur_venn", str(note)]) == reading.EXIT["ok"]
    assert "warning, before this connection note" in capsys.readouterr().out
    # Connect on the page: no warning.
    shown = reading.parse(_page(name="Bo Venn", headline="Data Scientist at Larkspur",
                                employer="Larkspur"), name="Bo Venn", company="Larkspur")
    assert shown["connect"] == "shown"


# ------------------------------------------------------------ 19. company numbers

def test_several_company_numbers_are_kept_at_once_unconfirmed(book, capsys):
    assert reading.main(["company-ids", "Kestrel Mutual=1234", "Fernhill Freight=5678"]) == 0
    out = capsys.readouterr().out
    assert "2 of 2 kept" in out
    assert reading._employer_filter("Kestrel Mutual") == {
        "name": "Kestrel Mutual", "currentCompany": '["1234"]', "unconfirmed": True}
    assert reading._employer_filter("Fernhill Freight")["unconfirmed"]
    assert "currentCompany=%5B%225678%22%5D" in reading.search_url("Fernhill Freight")
    assert reading.main(["company-ids", "Oakmere Foods", "Larkspur=abc"]) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not kept" in out and "0 of 2 kept" in out


def test_no_filter_says_a_keyword_search_finds_people_elsewhere_and_how_to_get_the_number(book,
                                                                                         capsys):
    assert reading.main(["search-url", "--company", "Oakmere Foods", "--function"]) == 1
    out = capsys.readouterr().out
    assert "returns people who do not work at Oakmere Foods" in out
    assert "--company-id" in out and "company-ids" in out and "currentCompany=" in out
    assert "search/results/people" not in out           # no keyword search was built


# ------------------------------------------------------------ 20. research titles

def test_research_titles_rank_below_the_function_and_are_never_cut():
    for title in ("Research Scientist", "Senior Research Scientist", "ML Researcher",
                  "Machine learning researcher", "Research Engineer"):
        rank, why = reading.title_fit(title)
        assert rank == 1 and "research title" in why, title
    assert reading.title_fit("Data Scientist")[0] == 3
    assert reading.title_fit("Operations Research Scientist")[0] == 2
    keep, _ = reading.screen({"name": "Juno Castellan", "title": "Research Scientist",
                              "location": "Manchester", "where": "at"}, "Larkspur")
    assert keep


def test_research_is_not_demoted_for_someone_whose_function_it_is(monkeypatch):
    monkeypatch.setitem(discovery.TITLE_SETS, "function", ["Research Scientist"])
    assert reading.research_title("ML Researcher") == ""
    assert reading.title_fit("ML Researcher")[0] != 1 or "research title" not in \
        reading.title_fit("ML Researcher")[1]


RESEARCH_PAGE = ("Juno Castellan • 2nd\nResearch Scientist at Larkspur\n"
                 "Manchester, England, United Kingdom\nConnect\n"
                 "Dee Hollis • 2nd\nMachine learning researcher at Larkspur\n"
                 "Manchester, England, United Kingdom\nConnect\n"
                 "Cy Marlow • 2nd\nData Scientist at Larkspur\nConnect\n")


def test_a_first_page_with_nobody_in_the_function_here_is_said_once(book, capsys, judged):
    judged("Larkspur")   # nobody is shown at an employer nobody has judged
    page = book.path / "people.txt"
    page.write_text(RESEARCH_PAGE, encoding="utf-8")
    assert reading.main(["people", str(page), "--company", "Larkspur"]) == 0
    out = capsys.readouterr().out
    assert out.count("nobody on this first page is in your function in Manchester") == 1
    assert "2 of the 3 hold research titles" in out
    lines = [ln for ln in out.splitlines() if ln.startswith("  deep read")]
    assert lines[0].startswith("  deep read: Cy Marlow")          # their function first
    # A later page says nothing; a page with someone in the function here says nothing.
    assert reading.no_function_here(reading.people_page(RESEARCH_PAGE, "Larkspur"), "Larkspur",
                                    "https://www.linkedin.com/search/results/people/?page=2") == ""
    here = RESEARCH_PAGE.replace("Data Scientist at Larkspur\n",
                                 "Data Scientist at Larkspur\nSalford, England, United Kingdom\n")
    assert reading.no_function_here(reading.people_page(here, "Larkspur"), "Larkspur") == ""


# ------------------------------------------------------------ 21. two a company

def test_people_waiting_on_a_reply_count_against_two_a_company(book, capsys):
    waiting = [_row(f"kestrel_{i}", n, "Kestrel Mutual Ltd", status="awaiting_reply",
                    location="Manchester")
               for i, n in enumerate(("Rosalind Achterberg", "Corwin Haldane", "Idris Corrie"))]
    new = [_row("kestrel_allard", "Wren Allard", "Kestrel Mutual", location="Manchester"),
           _row("fernhill_a", "Juno Castellan", "Fernhill Freight", location="Manchester"),
           _row("fernhill_b", "Dee Hollis", "Fernhill Freight", location="Manchester"),
           _row("fernhill_c", "Cy Marlow", "Fernhill Freight", location="Manchester")]
    contacts = waiting + new
    got = reading.shortlist(["kestrel_allard", "fernhill_a", "fernhill_b", "fernhill_c"], TODAY,
                            contacts=contacts, sends_left=10)
    assert got["ids"] == ["fernhill_a", "fernhill_b"]
    assert "3 waiting on a reply (Rosalind Achterberg" in got["employer_full"]["kestrel_allard"]
    assert "2 on today's list" in got["employer_full"]["fernhill_c"]
    book.put(*contacts)
    assert reading.main(["shortlist", "kestrel_allard"]) == 0
    assert "against 2 a company" in capsys.readouterr().out


def test_a_note_unanswered_for_months_no_longer_holds_the_employer():
    old = (TODAY - datetime.timedelta(days=reading.WAITING_DAYS + 15)).isoformat()
    waiting = [dict(_row(f"kestrel_{i}", n, "Kestrel Mutual", status="awaiting_reply",
                         location="Manchester"), first_contacted=old)
               for i, n in enumerate(("Rosalind Achterberg", "Corwin Haldane"))]
    new = _row("kestrel_allard", "Wren Allard", "Kestrel Mutual", location="Manchester")
    got = reading.shortlist(["kestrel_allard"], TODAY, contacts=waiting + [new], sends_left=10)
    assert got["ids"] == ["kestrel_allard"]


# ------------------------------------------------------------ 24. their time

NOW = datetime.datetime(2026, 10, 20, 10, 30, tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("place,zone", [
    ("Toronto, Ontario, Canada", "America/Toronto"),
    ("London, Ontario, Canada", "America/Toronto"),
    ("Mississauga, Ontario, Canada", "America/Toronto"),
    ("Vancouver, Canada", "America/Vancouver"),
    ("Manchester, England, United Kingdom", "Europe/London"),
    ("Greater Toronto Area", "America/Toronto"),
    ("Manchester, New Hampshire, United States", ""),
    ("Remote", ""),
])
def test_a_place_maps_to_its_time_zone_only_when_it_is_certain(place, zone):
    assert reading.zone_for(place) == zone


def test_their_time_is_said_and_the_persons_own_is_the_default():
    assert reading.home_zone() == "Europe/London"        # the example profile's TIMEZONE
    assert reading.their_time("Toronto, Ontario, Canada", NOW) == \
        "their time now: Tue 06:30 in Toronto (America/Toronto)"
    assert reading.their_time("", NOW) == "their time now: Tue 11:30 in Manchester (Europe/London)"
    odd = reading.their_time("Manchester, New Hampshire, United States", NOW)
    assert odd.startswith("time now: Tue 11:30 in Manchester (Europe/London), your own")
    assert "their time is not known" in odd


def test_every_hand_over_of_a_draft_says_the_time_there(book, capsys, judged):
    judged("Kestrel Mutual")   # nobody is shown at an employer nobody has judged
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual",
                  location="Toronto, Ontario, Canada", channel="connection"))
    note = book.path / "note.txt"
    note.write_text("Hi Rosalind, a note.", encoding="utf-8")
    # Nothing read about her: saved only as a card-only note now (2026-10-21), and the time
    # there is said all the same.
    assert reading.main(["draft", "kestrel_achterberg", str(note), "--card-only"]) == 0
    assert "their time now:" in capsys.readouterr().out and "(America/Toronto)" in \
        reading.time_for("kestrel_achterberg")
    assert reading.main(["queue"]) == 0
    assert "(America/Toronto)" in capsys.readouterr().out
    assert reading.main(["send-time", "kestrel_achterberg"]) == 0
    out = capsys.readouterr().out
    assert "Rosalind Achterberg [kestrel_achterberg]: their time now:" in out


def test_nothing_is_held_back_for_the_hour(book, capsys, monkeypatch):
    """The time is said, never used to stop a draft: a draft written at any hour is saved."""
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual",
                  location="Toronto, Ontario, Canada"))
    monkeypatch.setattr(reading, "their_time",
                        lambda *a, **k: "their time now: Tue 03:00 in Toronto (America/Toronto)")
    note = book.path / "note.txt"
    note.write_text("Hi Rosalind, a note.", encoding="utf-8")
    # Card-only: nothing read about her, and since 2026-10-21 such a note is saved only so.
    assert reading.main(["draft", "kestrel_achterberg", str(note), "--card-only"]) == 0
    assert os.path.isfile(reading.draft_path("kestrel_achterberg"))
