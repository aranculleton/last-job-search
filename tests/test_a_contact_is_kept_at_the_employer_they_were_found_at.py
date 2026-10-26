"""A contact is kept at the employer they were found at, however their card writes it, and
the number written to at one employer is the person's to raise.

A networking round on 2026-10-24 skipped five people as having moved on because their
headline wrote the employer short ("at <Name>" for "<Name> Asset Management", "<Name> -
<Line>" for "<Name> <Line>"), and one more because "500+" was read as where they work: a
browser's page text puts the count and the word "connections" on two lines. The same round
asked for more people at four employers than the limit of two, and the short list and every
draft refused them with nothing that could say otherwise. Each case below is the shape of
one of those, with invented people and employers.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import discovery  # noqa: E402
import learned  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date.today()
HOME = "Manchester, England, United Kingdom"

@pytest.fixture(autouse=True)
def _today():
    """TODAY is the day each test runs, not the day this file was loaded: a run that
    crossed midnight compared the one with the other (Windows, 2026-10-26)."""
    global TODAY
    TODAY = datetime.date.today()



def _reading(headline, company, current=None, **kw):
    r = {"name": "Rhian Pellow", "company": company, "headline": headline,
         "location": HOME, "items": [], "experience": [], "about": ""}
    r["current"] = reading._headline_employer(headline) if current is None else current
    r.update(kw)
    return r


@pytest.mark.parametrize("headline,company", [
    ("Data Scientist at Northgate", "Northgate Asset Management"),
    ("Quantitative Analyst @ Kestrel | Machine Learning and Research",
     "Kestrel Investment Management"),
    ("Principal Data Scientist at Larkspur - Oakmere", "Larkspur Oakmere"),
    ("Director, Data Science @ Fernhill", "Fernhill Realty"),
    ("Chief Data Scientist at Quayside", "Quayside Credit Corporation"),
])
def test_an_employer_written_short_is_where_they_were_found(headline, company):
    keep, why = reading.verdict(_reading(headline, company), company)
    assert keep and "moved on" not in why


@pytest.mark.parametrize("headline,company", [
    ("Analyst at Capital", "Northgate Capital"),               # a word many employers share
    ("Data Scientist at Northgate Bank", "Northgate Capital"),  # another firm of one name
    ("Data Scientist at Kestrel Mutual", "Fernhill Freight"),
    ("Data Scientist at Asset Management", "Northgate Asset Management"),
])
def test_another_employer_is_still_one_they_moved_to(headline, company):
    keep, why = reading.verdict(_reading(headline, company), company)
    assert not keep and why.startswith("has moved on")


def test_a_short_form_joins_nothing_else():
    """The short form is for the moved-on question alone: a join of two employers'
    records (same_employer) stays strict."""
    assert discovery.written_short("Northgate", "Northgate Asset Management")
    assert not discovery.same_employer("Northgate", "Northgate Asset Management")
    assert not discovery.written_short("Bank", "Northgate Bank")
    assert not discovery.written_short("Northgate Bank", "Northgate Capital")
    # A name of shared words, its "of <place>" left off (the review of 2026-10-24).
    assert discovery.written_short("National Bank", "National Bank of Larkspur")
    assert not discovery.written_short("Bank", "Bank of Larkspur")
    assert not discovery.written_short("National Bank of Leeds", "National Bank of Larkspur")


CARD = ("Rhian Pellow\n· 2nd\nQuant Research, NGQ | Prev. Quant, Fernhill\n"
        "Manchester, England, United Kingdom\nContact info\n{count}\nConnect\nMessage\n")


@pytest.mark.parametrize("count", ["500+\nconnections", "500+ connections",
                                   "1,234 followers\n500+ connections", "500+"])
def test_a_count_on_the_card_is_never_where_they_work(count):
    got = reading.parse(CARD.format(count=count), name="Rhian Pellow",
                        company="Northgate Quant Partners")
    assert got["current"] == ""
    keep, why = reading.verdict(got, "Northgate Quant Partners")
    assert keep and "moved on" not in why


def test_a_reading_saved_with_a_count_for_an_employer_is_kept():
    r = _reading("Quant Research, NGQ | Prev. Quant, Fernhill", "Northgate Quant Partners",
                 current="500+")
    keep, why = reading.verdict(r, "Northgate Quant Partners")
    assert keep and "moved on" not in why
    assert reading.is_count("500+") and reading.is_count("1,234 followers")
    assert not reading.is_count("Northgate 500")


# ------------------------------------------------------------ the number at one employer


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(reading, "_more_at_path", lambda: str(tmp_path / "more_at.json"))
    contacts, threads = str(tmp_path / "contacts.csv"), str(tmp_path / "threads.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", threads)
    real_load_c, real_save_c = state.load_contacts, state.save_contacts
    real_load_t, real_save_t = state.load_threads, state.save_threads
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_load_c(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_save_c(rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real_load_t(path))
    monkeypatch.setattr(state, "save_threads", lambda rows, path=threads: real_save_t(rows, path))
    kept = []
    monkeypatch.setattr(learned, "record", lambda *a, **k: kept.append((a, k)))

    class Book:
        path = tmp_path
        learned = kept

        @staticmethod
        def put(*rows):
            state.save_contacts(state.load_contacts() + [dict(r) for r in rows])

        @staticmethod
        def contacts():
            return state.load_contacts()
    return Book


def _row(cid, name, company, **kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update({"contact_id": cid, "name": name, "company": company, "status": "not_contacted",
                "location": HOME, **kw})
    return row


def _two_waiting_at_kestrel():
    sent = (TODAY - datetime.timedelta(days=8)).isoformat()
    return [_row(f"kestrel_w{i}", n, "Kestrel Mutual", status="awaiting_reply",
                 first_contacted=sent) for i, n in enumerate(("Ana Rook", "Bo Venn"))]


def test_the_number_an_employer_is_the_persons_setting():
    assert reading._people_per_employer(3) == 3
    for bad in (0, -1, "two", None, True):
        assert reading._people_per_employer(bad) == 2


def test_the_limit_is_read_from_the_setting_when_it_is_asked(book, monkeypatch):
    book.put(*_two_waiting_at_kestrel())
    assert reading.employer_full_line("Kestrel Mutual", book.contacts(), today=TODAY)
    monkeypatch.setattr(reading, "PER_EMPLOYER", 3)
    assert reading.employer_full_line("Kestrel Mutual", book.contacts(), today=TODAY) == ""


def test_more_at_one_employer_on_the_persons_word(book, capsys):
    book.put(*_two_waiting_at_kestrel(),
             _row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    full = reading.employer_full_line("Kestrel Mutual", book.contacts(), today=TODAY)
    assert "against 2 a company" in full
    said = "write to two more at Kestrel, they are hiring"
    assert reading.main(["more-at", "Kestrel Mutual Ltd", "--said", said, "--up-to", "4"]) == 0
    assert "up to 4 people" in capsys.readouterr().out
    assert json.load(open(book.path / "more_at.json"))[0]["said"] == said
    (area, kept_said, rule), _ = book.learned[0]
    assert area == "people" and kept_said == said and "Up to 4" in rule
    assert reading.employer_full_line("Kestrel Mutual", book.contacts(), today=TODAY) == ""
    got = reading.shortlist(["kestrel_achterberg"], today=TODAY, contacts=book.contacts(),
                            sends_left=10)
    assert got["ids"] == ["kestrel_achterberg"] and not got["employer_full"]
    # Two more there is the person's number: a fifth is still refused, saying so.
    more = [_row(f"kestrel_n{i}", n, "Kestrel Mutual") for i, n in
            enumerate(("Idris Corrie", "Corwin Haldane"))]
    full = reading.employer_full_line("Kestrel Mutual", book.contacts(), also=more, today=TODAY)
    assert "against the 4 you asked for there" in full


def test_a_draft_is_saved_on_the_persons_word_and_says_so(book, capsys):
    book.put(*_two_waiting_at_kestrel(),
             _row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    f = book.path / "note.txt"
    f.write_text("Hi Rosalind, we both worked at Oakmere Foods. How is the team set up?",
                 encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "against 2 a company" in out and "reading.py more-at \"Kestrel Mutual\"" in out
    reading.set_more_at("Kestrel Mutual", "yes, more at Kestrel")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["ok"]
    assert "on your word" in capsys.readouterr().out
    assert os.path.isfile(reading.draft_path("kestrel_achterberg"))


def test_more_at_needs_their_words_and_can_be_taken_back(book, capsys):
    assert reading.main(["more-at", "Kestrel Mutual"]) == reading.EXIT["error"]
    assert "own words" in capsys.readouterr().out
    reading.set_more_at("Kestrel Mutual", "more there please", up_to=3)
    assert reading.employer_limit("Kestrel Mutual Ltd")[0] == 3
    assert reading.main(["more-at"]) == 0
    assert "Kestrel Mutual: up to 3" in capsys.readouterr().out
    assert reading.main(["more-at", "Kestrel Mutual", "--remove"]) == 0
    assert reading.employer_limit("Kestrel Mutual") == (reading.PER_EMPLOYER, {})


# ------------------------------------------------------------ is a message to them free?


def _not_connected(cid="kestrel_achterberg", channel="inmail"):
    return _row(cid, "Rosalind Achterberg", "Kestrel Mutual", channel=channel)


NOTE = ("Hi Rosalind, we both worked at Oakmere Foods before. I am a data scientist in "
        "Manchester looking at pricing teams. How is the team at Kestrel set up?")


def test_an_inmail_is_not_drafted_before_their_message_window_is_checked(book, capsys):
    """14 InMails were drafted on a guess and 2 went through (2026-10-24): the card shows
    Message whether the note is free or spends a credit."""
    book.put(_not_connected())
    f = book.path / "note.txt"
    f.write_text(NOTE, encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "checked first" in out and "--message-check" in out
    assert not os.path.isfile(reading.draft_path("kestrel_achterberg"))


def test_a_free_message_is_drafted_as_one_and_spends_no_credit(book, capsys):
    book.put(_not_connected())
    snippet = json.dumps({"url": "https://www.linkedin.com/in/example", "kind": "message_check",
                          "answer": "free", "opened": True, "closed": True})
    assert reading.main(["message-check", "kestrel_achterberg", snippet]) == 0
    assert "free" in capsys.readouterr().out
    assert reading.load("kestrel_achterberg")["message_window"]["answer"] == "free"
    assert state.load_contacts()[0]["channel"] == "open_profile"
    f = book.path / "note.txt"
    f.write_text(NOTE, encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["ok"]


def test_an_inmail_that_needs_a_credit_is_drafted_only_while_credits_last(book, monkeypatch,
                                                                         capsys):
    book.put(_not_connected(), _row("fernhill_corrie", "Idris Corrie", "Fernhill Freight",
                                    channel="inmail"))
    for cid in ("kestrel_achterberg", "fernhill_corrie"):
        reading.record_message_check(cid, "needs credits", how="by hand")
    monkeypatch.setattr(state, "platform_budget",
                        lambda *a, **k: {"inmails_left": 1, "inmails_source": "test"})
    f = book.path / "note.txt"
    f.write_text(NOTE, encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["ok"]
    capsys.readouterr()
    g = book.path / "note2.txt"
    g.write_text(NOTE.replace("Rosalind", "Idris").replace("Kestrel", "Fernhill"),
                 encoding="utf-8")
    assert reading.main(["draft", "fernhill_corrie", str(g), "--card-only"]) == \
        reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "1 are left this month with 1 InMail(s) already drafted" in out
    assert not os.path.isfile(reading.draft_path("fernhill_corrie"))


def test_the_check_reads_its_labels_from_the_registry_and_types_nothing():
    import claude_surfaces
    labels = claude_surfaces.entry(reading.MESSAGE_CHECK_ENTRY)["labels"]
    js = reading.message_check_extractor()
    assert "__LABELS__" not in js
    for word in labels["free"] + labels["credits"]:
        assert json.dumps(word) in js
    # It opens the window and closes it: no key typed, no text set, nothing sent.
    for never in (".value", "insertText", "execCommand", "keypress", "\"send\""):
        assert never not in js
    assert reading.message_answer("needs credits") == "credits"
    assert reading.message_answer('{"answer": "free"}') == "free"
    assert reading.message_answer("maybe") == ""


HARNESS = """
let bodyText = "Rhian Pellow\\nHead of Pricing at Kestrel Mutual\\nMessage\\nMore";
let closed = false;
const closeBtn = {innerText: "", textContent: "",
  getAttribute: k => k === "aria-label" ? "Close your conversation with Rhian Pellow" : null,
  click() { closed = true; }};
const msgBtn = {innerText: "Message", textContent: "Message",
  getAttribute: k => k === "aria-label" ? "Message Rhian Pellow" : null,
  click() { bodyText += "\\n" + %s; buttons.push(closeBtn); }};
const buttons = [msgBtn];
const card = {querySelector: () => msgBtn, querySelectorAll: () => [msgBtn], parentElement: null};
const h1 = {closest: () => card, parentElement: card};
const main = {querySelector: s => s === "h1" ? h1 : null, querySelectorAll: () => [msgBtn]};
global.KeyboardEvent = class { constructor(t, o) { this.type = t; } };
global.document = {querySelector: s => s === "main" ? main : s === "h1" ? h1 : null,
  querySelectorAll: s => s === "button" ? buttons.slice() : [],
  body: {get innerText() { return bodyText; }}, dispatchEvent() {}};
global.location = {href: "https://www.linkedin.com/in/example"};
eval(%s).then(r => console.log(JSON.stringify({got: JSON.parse(r), closed})));
"""


@pytest.mark.parametrize("window,answer", [
    ("Free message\\nWrite a message", "free"),
    ("Get more InMail credits\\nTry Premium", "credits"),
    ("Write a message", "unknown"),
])
def test_the_check_opens_the_window_reads_it_and_closes_it(tmp_path, window, answer):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    run = tmp_path / "run.js"
    run.write_text(HARNESS % (json.dumps(window.replace("\\n", "\n")),
                              json.dumps(reading.message_check_extractor())), encoding="utf-8")
    got = json.loads(subprocess.run([node, str(run)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=60).stdout)
    assert got["got"]["answer"] == answer and got["got"]["opened"]
    assert got["closed"] and got["got"]["closed"]
    assert reading.message_answer(json.dumps(got["got"])) == answer


def test_one_employer_written_two_ways_takes_the_later_word(book):
    # Two chats each kept the person's word, one as "Kestrel Mutual", one in lower case:
    # the merge keeps both rows, and the later one stands (the review of 2026-10-24).
    import json
    with open(reading._more_at_path(), "w", encoding="utf-8") as fh:
        json.dump([{"employer": "kestrel mutual", "limit": 5, "said": "five", "date": "2026-10-25"},
                   {"employer": "Kestrel Mutual", "limit": 4, "said": "four", "date": "2026-10-24"}],
                  fh)
    assert reading.employer_limit("Kestrel Mutual")[0] == 5


def test_nothing_is_kept_in_the_example_person(monkeypatch):
    monkeypatch.setattr(reading, "_more_at_path", lambda: os.path.join(
        ROOT, "profile.example", reading.MORE_AT_FILE))
    with pytest.raises(ValueError, match="example person"):
        reading.set_more_at("Kestrel Mutual", "more there")
    assert not os.path.exists(os.path.join(ROOT, "profile.example", reading.MORE_AT_FILE))
