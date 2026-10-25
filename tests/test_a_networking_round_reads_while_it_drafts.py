"""A networking round of about twenty people, on 3.9.0 (2026-10-21), and what it showed.

Reads took 30 to 40 minutes with nobody told, one page at a time while the session waited; a
short paste of a page that had loaded was called "did not render"; a headline idiom was read
as an employer and a bank's director skipped; a recruiter working nationally was skipped for
where she sits; twenty first notes from one template were saved with nothing read and passed
one by one; a follow-up could not be logged by command; a direct message to a connection had
no kind; the person's own opener was refused in a nudge; the weekly cap read as LinkedIn's;
and a title search across employers printed "0 at ,". Each case below is the shape of one of
those, with invented people and employers.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import advice  # noqa: E402
import compose  # noqa: E402
import pace  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 21)


def rules(found):
    return ({getattr(a, "rule", None) for a in found}
            | {compose._check_of(a) for a in found if hasattr(a, "text")}) - {""}


@pytest.fixture
def book(tmp_path, monkeypatch):
    """A contact book and a message log in files, the reading files beside them."""
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts, threads = str(tmp_path / "contacts.csv"), str(tmp_path / "threads.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", threads)
    real_load_c, real_save_c = state.load_contacts, state.save_contacts
    real_load_t, real_save_t = state.load_threads, state.save_threads
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_load_c(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_save_c(rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real_load_t(path))
    monkeypatch.setattr(state, "save_threads", lambda rows, path=threads: real_save_t(rows, path))

    class Book:
        path = tmp_path

        @staticmethod
        def put(*rows):
            state.save_contacts(state.load_contacts() + [dict(r) for r in rows])

        @staticmethod
        def contacts():
            return state.load_contacts()

        @staticmethod
        def threads():
            return state.load_threads()
    return Book


def _row(cid, name, company, **kw):
    return {"contact_id": cid, "name": name, "company": company, "status": "not_contacted",
            "location": "Manchester, England, United Kingdom", **kw}


# ------------------------------------------------------------ 1. a round, in plain time

def test_the_round_says_how_long_its_reads_take_before_they_start(book):
    got = reading.estimate(20, sends_left=5)
    # Every one of them today, whatever is left to send: no cap of the app's own, and the
    # time is the browser's own speed, with no pause added (2026-10-22).
    assert got["today"] == 20 and got["later"] == 0
    assert got["seconds"] == 20 * reading.SECONDS_A_READ
    assert got["line"].startswith("Reading these 20 takes about ")
    assert "no waiting of the app's own" in got["line"]
    # Stopped by LinkedIn, none can be read today, and the cards are offered instead.
    reading.stop("a security check appeared")
    held = reading.estimate(20)
    assert held["today"] == 0 and "cannot start today" in held["line"]
    assert "card-only" in held["line"]


def test_reading_waits_are_spent_on_notes_that_can_be_written_now(book):
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    reading.shortlist(["kestrel_achterberg"], contacts=book.contacts(), sends_left=10)
    reading.save("kestrel_achterberg", {
        "name": "Rosalind Achterberg", "company": "Kestrel Mutual",
        "read_on": datetime.date.today().isoformat(), "headline": "Head of Pricing",
        "sources": [{"kind": "browser", "date": datetime.date.today().isoformat(),
                     "at": datetime.datetime.now().isoformat(timespec="seconds")}]})
    got = reading.meanwhile(contacts=book.contacts())
    assert [c for c, _w in got] == ["kestrel_achterberg"]
    assert "write their note from the reading" in got[0][1]


RECRUITER = {"name": "Idris Corrie", "company": "Kestrel Mutual", "read_on": "",
             "headline": "Technical Recruiter at Kestrel Mutual",
             "location": "Manchester, England, United Kingdom", "reach": "request",
             "sources": [{"kind": "list", "url": "", "date": "2026-10-21"}], "items": []}


def test_a_recruiters_card_says_enough_and_is_drafted_card_only_with_no_read(book, capsys):
    book.put(_row("kestrel_corrie", "Idris Corrie", "Kestrel Mutual", title=RECRUITER["headline"]))
    reading.save("kestrel_corrie", dict(RECRUITER))
    assert reading.card_enough(reading.load("kestrel_corrie"))
    # A peer's card never does: their note rests on their reading.
    peer = dict(RECRUITER, headline="Data Scientist at Kestrel Mutual")
    assert not reading.card_enough(peer)
    # Not put on the day's read list: no read is spent on what the card already says.
    got = reading.shortlist(["kestrel_corrie"], contacts=book.contacts(), sends_left=10)
    assert got["card_enough"] == ["kestrel_corrie"] and got["ids"] == []
    note = book.path / "note.txt"
    note.write_text("Hi Idris, I'm a supply-chain analyst in Manchester looking for my next "
                    "role. If anything you're working on fits, it'd be great to hear.",
                    encoding="utf-8")
    assert reading.main(["draft", "kestrel_corrie", str(note)]) == reading.EXIT["ok"]
    assert "CARD ONLY" in capsys.readouterr().out
    assert reading.card_only_draft("kestrel_corrie")
    # Nothing waits on a read for them, and the note sent is the note, never the marker.
    assert "kestrel_corrie" not in [c["contact_id"] for c in reading.queue(book.contacts())]
    assert reading.queued_notes(book.contacts())["kestrel_corrie"].startswith("Hi Idris")


# ------------------------------------------------------------ 2. a page that loaded

STRUCTURED = """Name: Tamsin Oyelaran
Headline: Head of Demand Forecasting at Fernhill Freight
Location: Leeds, England, United Kingdom
About: I run forecasting for a chilled-freight network.
Experience: Head of Demand Forecasting | Fernhill Freight | Jan 2023 - Present | Leeds, England
Experience: Senior Analyst at Oakmere Foods, 2018 - 2022
"""


def test_a_short_structured_paste_of_a_loaded_page_is_a_page_not_a_render_failure():
    assert len(STRUCTURED) < reading.NOT_RENDERED_CHARS * 2
    assert reading.rendered(STRUCTURED, "Tamsin Oyelaran")
    r = reading.parse(STRUCTURED, name="Tamsin Oyelaran", company="Fernhill Freight",
                      source="browser", today=TODAY)
    assert r["headline"] == "Head of Demand Forecasting at Fernhill Freight"
    assert r["location"] == "Leeds, England, United Kingdom"
    assert r["current"] == "Fernhill Freight"
    assert [e["employer"] for e in r["experience"]] == ["Fernhill Freight", "Oakmere Foods"]
    assert [s["name"] for s in r["shared"]["employers"]] == ["Oakmere Foods"]
    # A blank page, or LinkedIn's chrome alone, still did not render.
    assert not reading.rendered("", "Tamsin Oyelaran")
    assert not reading.rendered("Loading\nHome\nMy Network", "Tamsin Oyelaran")


def _browser(monkeypatch, book, row):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    book.put(row)
    reading.shortlist([row["contact_id"]], contacts=book.contacts(), sends_left=10)


SHORT = ("Name: Tamsin Oyelaran\nHeadline: Head of Demand Forecasting at Fernhill Freight\n"
         "Location: Leeds\nExperience: Head of Demand Forecasting | Fernhill Freight | 2023 - "
         "Present\n")


def test_a_short_paste_read_in_the_browser_is_saved_and_signals_nothing(book, monkeypatch,
                                                                      capsys):
    # A page that had loaded, pasted in a little over two hundred characters, was called "did
    # not render", which doubled the pause and warned that one more would stop the day.
    assert len(SHORT) < reading.NOT_RENDERED_CHARS
    _browser(monkeypatch, book, _row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight"))
    page = book.path / "page.txt"
    page.write_text(SHORT, encoding="utf-8")
    assert reading.main(["read", "fernhill_oyelaran", str(page), "--source", "browser"]) == 0
    out = capsys.readouterr().out
    assert "did not render" not in out and "verdict: KEEP" in out
    assert not [x for x in pace.friction() if x["kind"] == "not_rendering"]
    assert reading.load("fernhill_oyelaran")["current"] == "Fernhill Freight"


def test_a_profile_read_before_the_page_was_scrolled_to_the_end_is_read_again(
        book, monkeypatch, capsys):
    """Experience appears only once the page is scrolled to the bottom: read before that, a
    real profile looked empty. It is no render failure and nothing is kept: the same page,
    scrolled, is read again."""
    _browser(monkeypatch, book, _row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight"))
    page = book.path / "page.txt"
    page.write_text("Tamsin Oyelaran\nHead of Demand Forecasting at Fernhill Freight\n"
                    "Leeds, England, United Kingdom\nContact info\nConnect\nActivity\n"
                    "Tamsin reposted this\n", encoding="utf-8")
    code = reading.main(["read", "fernhill_oyelaran", str(page), "--source", "browser"])
    assert code == reading.EXIT["scroll"]
    out = capsys.readouterr().out
    assert "very bottom" in out and "did not render" not in out
    assert reading.load("fernhill_oyelaran") is None and not pace.friction()
    # A page with no Experience even at the end is read as it is, when the session says so.
    assert reading.main(["read", "fernhill_oyelaran", str(page), "--source", "browser",
                         "--no-experience"]) == 0
    assert reading.load("fernhill_oyelaran")["headline"].startswith("Head of Demand")


def test_the_extractor_finds_the_sections_whatever_order_the_page_puts_them_in(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    text = "\n".join(["Tamsin Oyelaran", "Head of Demand Forecasting at Fernhill Freight",
                      "Leeds, England", "Contact info", "Activity", "Tamsin reposted this",
                      "A repost about something else", "About",
                      "I run forecasting for a chilled-freight network.", "Experience",
                      "Head of Demand Forecasting", "Fernhill Freight", "Jan 2023 - Present",
                      "Skills", "Python", "Education", "University of Leeds", "2014 - 2017",
                      "People also viewed", "Juno Castellan"])
    harness = tmp_path / "run.js"
    harness.write_text(
        "const main = {innerText: %s, querySelector: () => null, querySelectorAll: () => []};\n"
        "global.document = {querySelector: s => s === 'main' ? main : null,\n"
        "  getElementById: () => null, body: main, title: 't'};\n"
        "global.location = {href: 'https://www.linkedin.com/in/example'};\n"
        "console.log(eval(%s));\n" % (json.dumps(text), json.dumps(reading.EXTRACTOR)),
        encoding="utf-8")
    raw = subprocess.run([node, str(harness)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
    got = json.loads(raw)
    assert [s["heading"] for s in got["sections"]] == ["About", "Experience", "Education"]
    assert "Activity" not in got["top"] and "reposted" not in raw
    r = reading.parse(reading.from_extract(raw), name="Tamsin Oyelaran",
                      company="Fernhill Freight", source="browser", today=TODAY)
    assert r["current"] == "Fernhill Freight" and r["about"].startswith("I run forecasting")


# ------------------------------------------------------------ 6. a headline's idiom

def _card(headline, org, experience=()):
    return "\n".join(["Rosalind Achterberg", "2nd", headline,
                      "Manchester, England, United Kingdom", "Contact info", org,
                      "University of Leeds", "500+ connections", "Connect", "Message", "More",
                      "About", "I lead model governance.", *experience]) + "\n"


def test_a_headline_idiom_is_never_the_employer_and_a_skip_rests_on_the_real_one():
    r = reading.parse(_card("Director, Responsible AI at Scale", "Kestrel Mutual"),
                      name="Rosalind Achterberg", company="Kestrel Mutual", source="browser",
                      today=TODAY)
    assert r["current"] == "Kestrel Mutual"
    assert reading.verdict(r, "Kestrel Mutual")[0]
    # A phrase that is no idiom, inside a role's title in Experience, is not an employer.
    exp = ("Experience", "Director, AI Governance at Enterprise Scale", "Kestrel Mutual",
           "Jan 2022 - Present")
    r = reading.parse(_card("Director, AI Governance at Enterprise Scale", "Kestrel Mutual", exp),
                      name="Rosalind Achterberg", company="Kestrel Mutual", today=TODAY)
    assert r["current"] == "Kestrel Mutual" and reading.verdict(r, "Kestrel Mutual")[0]
    # Found somewhere else, the SKIP names where they really work.
    keep, why = reading.verdict(r, "Fernhill Freight")
    assert not keep and "Kestrel Mutual" in why and "Scale" not in why


# ------------------------------------------------------------ 20. where a contact sits

def test_a_recruiter_or_a_remote_role_is_never_skipped_for_where_they_sit():
    base = {"company": "Kestrel Mutual", "current": "Kestrel Mutual", "items": [], "about": "",
            "location": "Ottawa, Ontario, Canada"}
    keep, why = reading.verdict(dict(base, headline="Talent Acquisition Partner at Kestrel Mutual"),
                                "Kestrel Mutual")
    assert keep and why == ""
    remote = dict(base, headline="Senior Data Scientist",
                  experience=[{"employer": "Kestrel Mutual", "title": "Senior Data Scientist",
                               "dates": "Jan 2024 - Present", "place": "Ottawa", "mode": "remote"}])
    assert reading.verdict(remote, "Kestrel Mutual") == (True, "")
    # Anyone else is kept too, with where they are said for the person to weigh.
    keep, why = reading.verdict(dict(base, headline="Senior Data Scientist"), "Kestrel Mutual")
    assert keep and why.startswith("caution: based in Ottawa")


def test_a_remote_place_on_the_role_is_kept_when_the_page_is_read():
    page = _card("Talent Partner", "Kestrel Mutual", (
        "Experience", "Talent Partner", "Kestrel Mutual · Full-time", "Jan 2024 - Present",
        "Ottawa, Ontario, Canada · Remote"))
    r = reading.parse(page, name="Rosalind Achterberg", company="Kestrel Mutual", today=TODAY)
    assert r["experience"][0]["mode"] == "remote"


# ------------------------------------------------------------ 9. one search, many employers

ACROSS = """Rosalind Achterberg • 2nd
Data Scientist at Kestrel Mutual
Manchester, England, United Kingdom
Connect
Idris Corrie • 2nd
Senior Data Scientist at Fernhill Freight
Leeds, England, United Kingdom
Message
Tamsin Oyelaran • 3rd+
Data Scientist | Machine learning
Manchester, England, United Kingdom
Connect
Corwin Haldane • 2nd
Data Scientist at Larkspur
Manchester, England, United Kingdom
Connect
"""


def test_a_title_search_across_employers_is_grouped_by_employer_and_never_prints_none(
        book, monkeypatch, capsys):
    import throttle
    from company_key import key
    monkeypatch.setattr(throttle, "load_do_not_target",
                        lambda *a, **k: {key("Larkspur"): "no analytics team in Manchester"})
    groups = reading.by_employer(reading.people_page(ACROSS, ""))
    assert [(g[0], len(g[2])) for g in groups] == [("Fernhill Freight", 1), ("Kestrel Mutual", 1),
                                                   ("Larkspur", 1), ("", 1)]
    assert dict((g[0], g[1]) for g in groups)["Larkspur"] == "no analytics team in Manchester"
    page = book.path / "page.txt"
    page.write_text(ACROSS, encoding="utf-8")
    assert reading.main(["people", str(page)]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert " at ," not in out and "across 3 employer(s)" in out
    assert "Larkspur: out, 1 (no analytics team in Manchester)" in out
    assert "where the card names no employer: 1" in out


def test_one_title_search_in_results_feeds_every_employer_it_found(book, monkeypatch, judged):
    judged("Kestrel Mutual", "Fernhill Freight")   # nobody is shown at an employer nobody has judged
    import throttle
    from company_key import key
    monkeypatch.setattr(throttle, "load_do_not_target",
                        lambda *a, **k: {key("Larkspur"): "no analytics team in Manchester"})
    results = [
        {"title": "Rosalind Achterberg - Data Scientist - Kestrel Mutual | LinkedIn",
         "url": "https://uk.linkedin.com/in/rosalind-achterberg-example",
         "summary": "Experience: Kestrel Mutual · Location: Manchester"},
        {"title": "Idris Corrie - Data Scientist - Fernhill Freight | LinkedIn",
         "url": "https://uk.linkedin.com/in/idris-corrie-example",
         "summary": "Experience: Fernhill Freight · Location: Manchester"},
        {"title": "Corwin Haldane - Data Scientist - Larkspur | LinkedIn",
         "url": "https://uk.linkedin.com/in/corwin-haldane-example"},
        {"title": "Tamsin Oyelaran - Data Scientist | LinkedIn",
         "url": "https://uk.linkedin.com/in/tamsin-oyelaran-example"}]
    got = sources.harvest_across(results, query="data scientist Manchester", contacts=[],
                                 connections=[])
    by = {e: (w, run) for e, w, run in got["employers"]}
    assert set(by) == {"Kestrel Mutual", "Fernhill Freight", "Larkspur"}
    assert by["Larkspur"] == ("no analytics team in Manchester", None)
    assert [p["name"] for p in by["Kestrel Mutual"][1]["keep"]] == ["Rosalind Achterberg"]
    assert [p["name"] for p in got["unplaced"]] == ["Tamsin Oyelaran"]


# ------------------------------------------------------------ 4. a follow-up, logged

def _sent_and_accepted(book):
    book.put(_row("fernhill_halloway", "Wren Halloway", "Fernhill Freight", status="awaiting_reply",
                  first_contacted="2026-10-01", channel="connection"))
    state.save_threads([
        {"contact_id": "fernhill_halloway", "date": "2026-10-01", "direction": "out",
         "channel": "connection", "scenario": "connection_note", "summary": "First note sent",
         "full_text": "Hi Wren, we both worked at Oakmere Foods."},
        {"contact_id": "fernhill_halloway", "date": "2026-10-02", "direction": "in",
         "channel": "connection", "scenario": "connection_accepted", "summary": "accepted",
         "full_text": ""}])


def test_a_nudge_is_logged_by_command_with_its_words(book, capsys):
    _sent_and_accepted(book)
    words = book.path / "nudge.txt"
    words.write_text("Hi Wren, how do your depot forecasts handle bank holidays?",
                     encoding="utf-8")
    # A first-message command says where a later one goes, never only that it refuses.
    assert state.main(["sent", "fernhill_halloway", "--text-file", str(words),
                       "--today", "2026-10-21"]) == 1
    assert "state.py nudge fernhill_halloway" in capsys.readouterr().out
    assert state.main(["nudge", "fernhill_halloway", "--text-file", str(words),
                       "--today", "2026-10-21"]) == 0
    row = book.threads()[-1]
    assert (row["scenario"], row["channel"], row["full_text"]) == (
        "nudge", "message", "Hi Wren, how do your depot forecasts handle bank holidays?")
    c = book.contacts()[0]
    assert c["next_action_due"] and "gone_cold" in c["next_action"]
    # The same words to the same person on the same day: never logged twice.
    assert state.main(["nudge", "fernhill_halloway", "--text-file", str(words),
                       "--today", "2026-10-21"]) == 1
    assert "already logged" in capsys.readouterr().out
    assert len(book.threads()) == 3
    # One nudge, then nothing more is owed but closing it out.
    assert [i["kind"] for i in state.owed(book.contacts(), book.threads(), "2026-11-20")] == \
        ["action_due"]


def test_several_later_messages_go_in_one_command_and_a_reply_is_a_reply(book, capsys):
    _sent_and_accepted(book)
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual",
                  status="replied_needs_response", first_contacted="2026-10-05",
                  channel="connection"))
    state.save_threads(book.threads() + [
        {"contact_id": "kestrel_achterberg", "date": "2026-10-05", "direction": "out",
         "channel": "connection", "scenario": "connection_note", "summary": "First note",
         "full_text": "Hi Rosalind, a note."},
        {"contact_id": "kestrel_achterberg", "date": "2026-10-06", "direction": "in",
         "channel": "message", "scenario": "", "summary": "Happy to chat",
         "full_text": "Happy to chat, what would you like to know?"}])
    texts = book.path / "texts.json"
    texts.write_text(json.dumps({
        "fernhill_halloway": "Hi Wren, one more thought on the depot forecasts.",
        "kestrel_achterberg": "Thanks Rosalind, how is the pricing team set up?"}), encoding="utf-8")
    assert state.main(["message", "fernhill_halloway", "kestrel_achterberg", "--texts",
                       str(texts), "--today", "2026-10-21"]) == 0
    assert "message: 2 recorded" in capsys.readouterr().out
    by = {r["contact_id"]: r for r in book.threads() if r["date"] == "2026-10-21"}
    assert by["kestrel_achterberg"]["scenario"] == "reply"
    assert by["fernhill_halloway"]["scenario"] == "nudge"
    # A nudge where they wrote last is refused: a reply is owed.
    words = book.path / "w.txt"
    words.write_text("Hi Rosalind, any thoughts?", encoding="utf-8")
    state.save_threads(book.threads() + [
        {"contact_id": "kestrel_achterberg", "date": "2026-10-22", "direction": "in",
         "channel": "message", "summary": "Sure", "full_text": "Sure, let's talk Friday."}])
    with pytest.raises(ValueError, match="a reply is owed, not a nudge"):
        state.followed_up(book.contacts(), book.threads(), "kestrel_achterberg", "2026-10-23",
                          text="Hi Rosalind, any thoughts?", kind="nudge")


# ------------------------------------------------------------ 5. kinds and their rules

def test_a_message_to_a_connection_has_a_kind_with_no_subject_and_the_first_note_rules():
    text = ("Hi Wren, we both worked at Oakmere Foods. How is the forecasting team set up "
            "these days? Would you have 15 minutes for a few questions sometime?")
    assert compose.validate(text, "dm", name="Wren Halloway") == []
    assert "no_subject" in rules(compose.validate(text, "inmail", name="Wren Halloway"))
    assert "asks_for_the_job" in rules(compose.validate(
        "Hi Wren, we both worked at Oakmere Foods. Is your team hiring?", "dm",
        name="Wren Halloway"))
    long_ = "Hi Wren, " + "we both worked at Oakmere Foods. " * 300
    assert "too_long" in rules(compose.validate(long_, "dm", name="Wren Halloway"))
    assert schema.LIMITS["message_chars"] > schema.LIMITS["connection_note_chars"]


def test_the_persons_own_words_are_theirs_in_every_kind_of_message():
    # Their OPENER is "hope you're well" and their OWN_VOICE has "would love to": a nudge, a
    # reply and a message to a connection may carry both, as a first note does.
    text = ("Hi Wren, hope you're well. Any word back on the forecasting role? I'd love to "
            "hear how it went.")
    for kind in ("connection", "nudge", "reply", "dm", "message"):
        assert "house-style" not in rules(compose.validate(text, kind, name="Wren Halloway")), kind
    # A stock phrase that is not theirs is still refused, and says what to do about it.
    found = compose.validate("Hi Wren, I would welcome a conversation about forecasting.",
                             "nudge", name="Wren Halloway")
    assert "house-style" in rules(found)
    assert "OWN_VOICE" in next(v.text for v in found if compose._check_of(v) == "house-style")


def test_a_batch_that_is_one_frame_with_the_nouns_swapped_is_flagged():
    employers = ["Kestrel Mutual", "Fernhill Freight", "Larkspur", "Oakmere Foods", "Brindle",
                 "Saltmarsh Analytics", "Northgate", "Halloway Ltd"]
    years = ["Six years of demand planning", "Four years of SQL reporting",
             "Two years of pricing models", "Five years of forecasting",
             "Three years of route planning", "Nine years of supplier analytics",
             "Seven years of stock control", "Eight years of reporting"]
    questions = ["How is the team set up?", "What are you working on?",
                 "Is the pricing work growing?", "What tools does the team lean on?",
                 "How did you get into it?", "What does a good week look like?",
                 "Where is the work heading?", "What surprised you most there?"]
    notes = {f"t{i}": f"Hi Ana, hope you're well. {years[i]}, which I imagine {employers[i]} "
                      f"values. {questions[i]}" for i in range(8)}
    found = reading.alike(notes, employers={f"t{i}": employers[i] for i in range(8)})
    frames = [f for f in found if f[0] == "same frame"]
    assert frames and len(frames[0][2]) == 8 and "which i imagine" in frames[0][1]


def test_within_one_employer_two_notes_sharing_a_sentence_are_too_alike():
    shared = "Your post on cold-chain forecasting from weather feeds stayed with me."
    notes = {"a": f"Hi Ana, hope you're well. {shared} How is the team set up?",
             "b": f"Hi Bo, hope you're well. {shared} What are you working on?",
             "c": "Hi Cy, hope you're well. We both spent years at Oakmere Foods. How was the move?"}
    same_employer = {"a": "Kestrel Mutual", "b": "Kestrel Mutual", "c": "Larkspur"}
    found = reading.alike(notes, employers=same_employer)
    assert ("shared at one employer", shared, ["a", "b"]) in found
    apart = {"a": "Kestrel Mutual", "b": "Fernhill Freight", "c": "Larkspur"}
    assert not [f for f in reading.alike(notes, employers=apart) if f[0].startswith("shared")]


# ------------------------------------------------------------ 12, 13, 18. what draft saves

def test_a_first_note_with_nothing_read_is_refused_unless_it_is_card_only(book, capsys):
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    text = "Hi Rosalind, we both worked at Oakmere Foods. How is the pricing team set up?"
    assert "no_reading" in rules(compose.validate(text, "connection", name="Rosalind Achterberg",
                                                  contact="kestrel_achterberg"))
    assert "no_reading" not in rules(compose.validate(
        text, "connection", name="Rosalind Achterberg", contact="kestrel_achterberg",
        card_only=True))
    # The composer knows when it was told nothing was read, and the Note says so.
    note = compose.first_note("Rosalind Achterberg", common_ground="We both worked at Oakmere Foods",
                              reading=None)
    assert note.read is False and "no_reading" in rules(compose.validate(note, "connection"))
    marked = compose.first_note("Rosalind Achterberg", common_ground="We both worked at Oakmere "
                                "Foods", reading=None, card_only=True)
    assert "no_reading" not in rules(compose.validate(marked, "connection"))
    f = book.path / "note.txt"
    f.write_text(text, encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f)]) == reading.EXIT["error"]
    assert "Nothing was read about Rosalind Achterberg" in capsys.readouterr().out
    assert not os.path.isfile(reading.draft_path("kestrel_achterberg"))
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == 0
    assert "CARD ONLY" in capsys.readouterr().out and reading.card_only_draft("kestrel_achterberg")


def test_a_placeholder_note_waits_on_a_read_and_is_never_ready_to_send(book, capsys, judged):
    judged("Kestrel Mutual")   # nobody is shown at an employer nobody has judged
    # The networking upgrade writes notes before anyone is read: saved only as placeholders,
    # under WAITS ON A READ, which validate() still refuses to send.
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    f = book.path / "note.txt"
    f.write_text("Hi Rosalind, we both worked at Oakmere Foods.", encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--wait-for-read"]) == 0
    assert reading.waits_on_read("kestrel_achterberg")
    assert "kestrel_achterberg" in [c["contact_id"] for c in reading.queue(book.contacts())]
    assert "no_reading" in rules(compose.validate(
        reading.queued_notes(book.contacts())["kestrel_achterberg"], "connection",
        contact="kestrel_achterberg"))


def test_a_batch_of_drafts_too_alike_saves_none_of_them(book, capsys):
    names = ["Ana Rook", "Bo Venn", "Juno Castellan", "Pell Ansgar", "Quillon Varga",
             "Hal Okonedo"]
    employers = ["Kestrel Mutual", "Fernhill Freight", "Larkspur", "Oakmere Foods", "Brindle",
                 "Saltmarsh Analytics"]
    book.put(*[_row(f"c{i}", names[i], employers[i]) for i in range(6)])
    creds = ["Six years of demand planning", "Four years of SQL reporting",
             "Two years of pricing models", "Five years of forecasting",
             "Three years of route planning", "Nine years of supplier analytics"]
    batch = {f"c{i}": {"note": f"Hi {names[i].split()[0]}, hope you're well. {creds[i]}, which I "
                               f"imagine {employers[i]} values. What is the team working on?",
                       "card_only": True} for i in range(6)}
    f = book.path / "batch.json"
    f.write_text(json.dumps(batch), encoding="utf-8")
    assert reading.main(["drafts", str(f)]) == reading.EXIT["alike"]
    out = capsys.readouterr().out
    assert "same frame" in out and "too alike" in out
    assert not any(os.path.isfile(reading.draft_path(f"c{i}")) for i in range(6))


def test_a_draft_is_held_to_the_same_company_limit_as_the_read_list(book, capsys):
    # `draft` reads the calendar, so the two notes went a week before today: dated in
    # October 2026 they stopped holding the employer (WAITING_DAYS) six weeks on.
    today = datetime.date.today()
    waiting = [_row(f"kestrel_w{i}", n, "Kestrel Mutual", status="awaiting_reply",
                    first_contacted=(today - datetime.timedelta(days=8)).isoformat())
               for i, n in enumerate(["Ana Rook", "Bo Venn"])]
    book.put(*waiting, _row("kestrel_achterberg", "Rosalind Achterberg", "Kestrel Mutual"))
    full = reading.employer_full_line("Kestrel Mutual", book.contacts(), today=today)
    assert full.startswith("Kestrel Mutual has 2 waiting on a reply")
    assert reading.shortlist(["kestrel_achterberg"], today=today, contacts=book.contacts(),
                             sends_left=10)["employer_full"]["kestrel_achterberg"] == full
    f = book.path / "note.txt"
    f.write_text("Hi Rosalind, we both worked at Oakmere Foods. How is the team set up?",
                 encoding="utf-8")
    assert reading.main(["draft", "kestrel_achterberg", str(f), "--card-only"]) == \
        reading.EXIT["error"]
    assert "against 2 a company" in capsys.readouterr().out
    assert not os.path.isfile(reading.draft_path("kestrel_achterberg"))


# ------------------------------------------------------------ 15. recruiters and gatekeepers

def test_a_recruiter_is_never_asked_any_jobs_or_whether_they_are_the_right_person():
    who = "Hi Idris, I'm a supply-chain analyst in Manchester. "
    for ask, rule in (("Any data roles open in Manchester?", "asks_for_the_job"),
                      ("Does data science hiring at Kestrel sit with your team, or someone else?",
                       "gatekeeping"),
                      ("Do your searches at Kestrel cover data science, or is that another team?",
                       "gatekeeping"),
                      ("Would you be up for a short call, or someone better to ask?",
                       "gatekeeping")):
        assert rule in rules(compose.validate(who + ask, "connection", name="Idris Corrie",
                                              reader="recruiter")), ask
    # The asks the app offers a recruiter, and a pointer asked openly, still pass.
    for ask in compose.options("ask", "recruiter") + compose.options("pointer", "peer"):
        assert not {"asks_for_the_job", "gatekeeping"} & rules(compose.validate(
            who + ask, "connection", name="Idris Corrie", reader="recruiter")), ask


# ------------------------------------------------------------ 16. warnings that fit

def test_a_who_line_with_a_place_in_it_is_not_three_credentials():
    found = advice.check("Hi Ana, I just moved from Leeds to Manchester, ex-Oakmere Foods and "
                         "Brindle & Hart.", "connection")
    assert "three_credentials" not in rules(found)
    assert "three_credentials" in rules(advice.check(
        "I've worked at Oakmere Foods, Saltmarsh Analytics and Brindle & Hart.", "inmail"))


def test_a_fact_from_their_headline_is_not_an_inference():
    r = {"headline": "Talent Acquisition | Machine Learning & Artificial Intelligence",
         "company": "KMB", "about": "", "items": [], "experience": []}
    s = "You recruit for ML and AI at KMB."
    assert advice.provenance(s, r) == advice.STATED
    assert "unhedged_inference" not in rules(advice.check("Hi Ana, " + s, "connection", reading=r))
    # A claim the page does not hold is still an inference.
    assert advice.provenance("You started in logistics before moving into software.", r) == \
        advice.INFERRED


def test_a_vague_ask_about_how_the_team_spends_its_time_is_caught_by_its_shape():
    for ask in ("I'd love to hear what your team spends its days on.",
                "Would love to hear what the forecasting team is busy with.",
                "I'd love to hear how your team works."):
        assert "ai_tell" in rules(advice.check("Hi Ana, " + ask, "connection")), ask
    assert "ai_tell" not in rules(advice.check(
        "Hi Ana, what is the forecasting team working on at the moment?", "connection"))


# ------------------------------------------------------------ 8. no cap, said plainly

def test_the_budget_line_counts_what_went_and_gives_no_cap_of_its_own():
    b = state.platform_budget([], [], "2026-10-21")
    line = state.budget_line(b)
    assert "sent: 0 this week, 0 today" in line and "no cap of the app's own" in line
    # No number LinkedIn never gave: "50 left" misled a person into reading it as LinkedIn's.
    assert " left this week" not in line and "connections_left" not in b


def test_a_connection_cap_written_in_the_profile_holds_nothing(monkeypatch):
    import importlib
    import person

    class Mine:
        CONNECTIONS_PER_WEEK = 80
        LINKEDIN_PLAN = "premium"
        LINKEDIN_LIMITS = {"connections_per_week": 10000, "connections_per_day": 1000,
                           "inmail_credits_per_month": 30}
    real = person.module
    monkeypatch.setattr(person, "module", lambda name: Mine if name == "networking" else real(name))
    try:
        importlib.reload(schema)
        assert "connections_per_week" not in schema.LIMITS
        assert "connections_per_day" not in schema.LIMITS
        assert schema.LIMITS["inmail_credits_per_month"] == 30    # their plan's limit stands
    finally:
        monkeypatch.undo()
        importlib.reload(schema)


# ------------------------------------------------------------ 17. what the friction was

def test_friction_is_said_as_what_happened(book):
    day = datetime.datetime.combine(TODAY - datetime.timedelta(days=1), datetime.time(10))
    assert pace.said({"kind": "not_rendering", "at": day.isoformat()}) == \
        "a page that came back nearly empty on 20 Oct"
    assert pace.said({"kind": "signed_out", "at": day.isoformat()}) == "a sign-in page on 20 Oct"


# ------------------------------------------------------------ 14. what they approved

@pytest.fixture
def own_profile(tmp_path, monkeypatch):
    import learned
    import person
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    yield learned
    person._modules.clear()
    person._data.clear()


def test_a_message_the_person_approved_is_shown_first_to_the_next_draft(own_profile):
    learned = own_profile
    inmail = ("Hi Ana, you moved from depot planning into forecasting, which is the move I made "
              "too. How did you find the jump?")
    learned.approve("almost perfect, more of this", inmail, channel="inmail", reader="peer")
    learned.approve("great, both sent", "Hi Bo, a note for a recruiter.", channel="connection",
                    reader="recruiter")
    learned.record("messages", "too formal", "plain and direct")
    brief = learned.brief("messages", channel="inmail", reader="peer")
    first = brief.index("Messages you approved")
    assert first < brief.index("plain and direct")
    assert brief.index("you moved from depot planning") < brief.index("a note for a recruiter")
    # Kept whole, and once.
    again = learned.approve("perfect", inmail, channel="inmail", reader="peer")
    assert again.get("already") and len(learned.approved()) == 2


def test_an_approval_is_noted_like_a_reaction_and_answered_by_keeping_it(own_profile):
    learned = own_profile
    assert learned.approval("Great, both sent!") and learned.approval("almost perfect")
    assert not learned.approval("I don't like this one")         # a reaction, not an approval
    out = learned.hook({"hook_event_name": "UserPromptSubmit", "prompt": "almost perfect, both sent"})
    assert "learned.py approve" in out["hookSpecificOutput"]["additionalContext"]
    assert learned.pending()
    learned.approve("almost perfect, both sent", "Hi Ana, a note.", channel="connection")
    assert not learned.pending()

