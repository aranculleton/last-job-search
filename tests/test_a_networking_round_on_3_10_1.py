"""A networking round on 3.10.1 (2026-10-22), and what it showed.

A people search narrowed to an employer could not be built from a company number a profile
read had already shown; LinkedIn's page footer was kept as somebody's About, and a
third-degree profile that shows no Experience to strangers exited "scroll" for good;
several roles grouped under one employer read as the person having moved on; two
`--remove` flags removed one person; a recruiter whose card said enough stayed on the read
list; the extractor's output needed a flag and re-typing to reach `read`; a batch opening
on the person's own line passed; a decision-maker was told the person's work authorization
by default; notes nobody would say aloud were saved; and a never-say "Love to hear" refused
"I'd love to hear". Each case below is the shape of one of those, with invented people and
employers.
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

import compose  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 22)


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
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [])

    class Book:
        path = tmp_path

        @staticmethod
        def put(*rows):
            state.save_contacts(state.load_contacts() + [dict(r) for r in rows])

        @staticmethod
        def contacts():
            return state.load_contacts()
    return Book


def _row(cid, name, company, **kw):
    return {"contact_id": cid, "name": name, "company": company, "status": "not_contacted",
            "location": "Manchester, England, United Kingdom", **kw}


def _extract(top, sections=(), companies=()):
    return json.dumps({"url": "https://www.linkedin.com/in/example", "title": "t", "top": top,
                       "sections": [{"heading": h, "text": t} for h, t in sections],
                       "companies": [{"name": n, "id": i} for n, i in companies]})


def _node(tmp_path, script, text, anchors=()):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    harness = tmp_path / "run.js"
    harness.write_text(
        "const anchors = %s.map(([href, text]) => ({getAttribute: () => href, innerText: text,\n"
        "  querySelector: () => null}));\n"
        "const main = {innerText: %s, querySelector: () => null,\n"
        "  querySelectorAll: s => s.includes('/company/') ? anchors : []};\n"
        "global.document = {querySelector: s => s === 'main' ? main : null,\n"
        "  getElementById: () => null, body: main, title: 't'};\n"
        "global.location = {href: 'https://www.linkedin.com/in/example'};\n"
        "console.log(eval(%s));\n" % (json.dumps([list(a) for a in anchors]), json.dumps(text),
                                      json.dumps(script)), encoding="utf-8")
    return subprocess.run([node, str(harness)], capture_output=True, text=True,
                          timeout=60).stdout


# ------------------------------------------------------------ 5. the employer's number

def test_search_url_takes_the_employer_first_and_its_number_from_a_profile_read(book, capsys):
    book.put(_row("fernhill_venn", "Bo Venn", "Fernhill Freight"))
    page = book.path / "extract.json"
    page.write_text(_extract("Bo Venn\nHead of Pricing at Fernhill Freight\nManchester",
                             [("Experience", "Experience\nHead of Pricing\nFernhill Freight\n"
                                             "Jan 2023 - Present")],
                             [("Fernhill Freight", "4410021")]), encoding="utf-8")
    assert reading.main(["read", "fernhill_venn", str(page), "--source", "paste",
                         "--json"]) == reading.EXIT["ok"]
    capsys.readouterr()
    assert reading.known_company_id("Fernhill Freight") == ("4410021", "fernhill_venn")
    # The employer named first, as the command's own help reads it, and no page loaded.
    assert reading.main(["search-url", "Fernhill Freight", "--function"]) == 0
    out = capsys.readouterr().out
    assert "4410021" in out and "from fernhill_venn's profile" in out
    assert reading.main(["search-url", "Fernhill Freight", "--company", "Larkspur"]) == 1


# ------------------------------------------------------------ 6. the footer and a third degree

FOOTER = ["About", "Accessibility", "Talent Solutions",
          "Careers", "Marketing Solutions", "Privacy & Terms"]


def test_the_page_footer_is_never_their_about(book, tmp_path):
    text = "\n".join(["Juno Castellan", "2nd", "Head of Forecasting at Larkspur",
                      "Manchester, England, United Kingdom", "Contact info", "Larkspur",
                      "Experience", "Head of Forecasting", "Larkspur", "Jan 2022 - Present",
                      *FOOTER])
    r = reading.parse(text, name="Juno Castellan", company="Larkspur", today=TODAY)
    assert r["about"] == ""
    # The extractor, on the same page: About is only ever a section above Experience.
    raw = _node(tmp_path, reading.EXTRACTOR, text)
    assert "about" not in [s["heading"].lower() for s in json.loads(raw)["sections"]]
    assert "Talent Solutions" not in reading.from_extract(raw)


def test_a_third_degree_profile_with_no_experience_shown_is_read_as_it_is(book, capsys,
                                                                          monkeypatch):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    book.put(_row("larkspur_pell", "Corwin Pell", "Larkspur"))
    reading.shortlist(["larkspur_pell"], contacts=book.contacts(), sends_left=10)
    page = book.path / "page.txt"
    page.write_text("Corwin Pell\n3rd\nHead of Pricing at Larkspur\n"
                    "Manchester, England, United Kingdom\nContact info\nLarkspur\nFollow\n"
                    "More\n", encoding="utf-8")
    code = reading.main(["read", "larkspur_pell", str(page), "--source", "browser"])
    assert code != reading.EXIT["scroll"]
    assert "third-degree" in capsys.readouterr().out
    assert reading.load("larkspur_pell")["headline"].startswith("Head of Pricing")


# ------------------------------------------------------------ 7. roles grouped under one employer

GROUPED = {
    "a comma in the time there": ["Oakmere Foods", "5 yrs, 6 mos"],
    "the time written in full": ["Oakmere Foods", "5 years 6 months"],
    "a logo line and the name twice": ["Oakmere Foods logo", "Oakmere Foods", "Oakmere Foods",
                                       "5 yrs 6 mos"],
    "the kind of job before the time": ["Oakmere Foods", "Full-time \u00b7 5 yrs 6 mos"],
}


@pytest.mark.parametrize("group", sorted(GROUPED))
def test_roles_grouped_under_one_employer_are_all_at_that_employer(group):
    text = "\n".join(["Sasha Reed", "2nd", "Head of Forecasting",
                      "Manchester, England, United Kingdom", "Contact info", "Experience",
                      *GROUPED[group], "Head of Forecasting", "Jan 2023 - Present",
                      "Senior Analyst, Forecasting", "Apr 2019 - Dec 2022"])
    r = reading.parse(text, name="Sasha Reed", company="Oakmere Foods", today=TODAY)
    assert r["current"] == "Oakmere Foods"
    keep, why = reading.verdict(r, "Oakmere Foods")
    assert keep and why == "", why                 # no "has moved on", no "role is in"


# ------------------------------------------------------------ 8. --remove twice

def test_every_id_given_to_remove_is_removed(book, capsys, monkeypatch):
    monkeypatch.setattr(reading, "shortlist_cap", lambda *a, **k: (10, "the test's cap"))
    book.put(*[_row(f"larkspur_{n}", n.title(), f"Larkspur {n}") for n in ("rook", "venn", "mire")])
    reading.shortlist(["larkspur_rook", "larkspur_venn", "larkspur_mire"],
                      contacts=book.contacts(), sends_left=10)
    assert reading.main(["shortlist", "--remove", "larkspur_rook", "--remove",
                         "larkspur_venn"]) == 0
    assert reading._shortlist_file(datetime.date.today()) == ["larkspur_mire"]


# ------------------------------------------------------------ 9. a recruiter's card

RECRUITER = {"name": "Idris Corrie", "company": "Kestrel Mutual", "read_on": "",
             "headline": "Technical Recruiter at Kestrel Mutual",
             "location": "Manchester, England, United Kingdom", "reach": "request",
             "sources": [{"kind": "list", "url": "", "date": "2026-10-22"}], "items": []}


def test_a_recruiter_whose_card_says_enough_leaves_the_read_list(book, capsys):
    book.put(_row("kestrel_corrie", "Idris Corrie", "Kestrel Mutual"))
    # On the list before their card was read; the card then says enough.
    assert reading.shortlist(["kestrel_corrie"], contacts=book.contacts(),
                             sends_left=10)["ids"] == ["kestrel_corrie"]
    reading.save("kestrel_corrie", dict(RECRUITER))
    assert reading.next_up(contacts=book.contacts()) is None
    got = reading.shortlist([], contacts=book.contacts(), sends_left=10)
    assert got["ids"] == [] and "card says enough" in got["pruned"]["kestrel_corrie"]


# ------------------------------------------------------------ 10. the extractor straight to read

@pytest.mark.parametrize("wrap", [lambda j: j, lambda j: json.dumps(j),
                                  lambda j: "```json\n" + j + "\n```",
                                  lambda j: "Result: " + json.dumps(j)])
def test_the_extractors_output_reaches_read_as_it_came(book, wrap):
    book.put(_row("oakmere_rook", "Ana Rook", "Oakmere Foods"))
    raw = _extract("Ana Rook\nForecasting Lead at Oakmere Foods\nManchester",
                   [("About", "About\nI run demand forecasting for a grocer."),
                    ("Experience", "Experience\nForecasting Lead\nOakmere Foods\n"
                                   "Mar 2021 - Present")])
    page = book.path / "out.txt"
    page.write_text(wrap(raw), encoding="utf-8")
    assert reading.main(["read", "oakmere_rook", str(page), "--source", "paste"]) == 0
    got = reading.load("oakmere_rook")
    assert got["about"].startswith("I run demand forecasting") and got["current"] == "Oakmere Foods"


def test_network_step_five_puts_the_extractor_first():
    with open(os.path.join(ROOT, ".claude", "commands", "network.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "the extractor is the way" in text and "finds the snippet's JSON by itself" in text
    assert text.index("the extractor is the way") < text.index("read the whole page text once")


# ------------------------------------------------------------ 11. the opening slot

def test_most_notes_opening_on_the_persons_own_line_is_a_template():
    names = {"a1": "Ana", "a2": "Bo", "a3": "Juno", "a4": "Wren", "a5": "Sasha"}
    reasons = {"a1": "I found you while looking at Larkspur's pricing team.",
               "a2": "We both worked at Oakmere Foods.",
               "a3": "I saw your name on the depot summit's speaker list.",
               "a4": "I found you on Fernhill's people page.",
               "a5": "Your talk on stock levels stuck with me."}
    about = compose.ABOUT_ME + "."
    first = {k: f"Hi {n}, hope you're well. {about} {reasons[k]} {compose.ASK}?"
             for k, n in names.items()}
    found = [f for f in reading.alike(first) if f[0].startswith("same first sentence")]
    assert found and sorted(found[0][2]) == sorted(names)
    # The same line, after a reason of their own, is theirs to repeat.
    later = {k: f"Hi {n}, hope you're well. {reasons[k]} {about} {compose.ASK}?"
             for k, n in names.items()}
    assert not [f for f in reading.alike(later) if f[0].startswith("same first sentence")]
    # Two of five opening on it is not most of them.
    mixed = dict(later, a1=first["a1"], a2=first["a2"])
    assert not [f for f in reading.alike(mixed) if f[0].startswith("same first sentence")]


# ------------------------------------------------------------ 13. read aloud

UNSPOKEN = ("Hi Juno, new to Manchester from Leeds and keen to meet people in forecasting.",
            "Love to hear what's coming up.",
            "I build pricing models with Airflow underneath.",
            "I'd like to hear about the platform clients model on.",
            "It sounds a lot like your Larkspur days.")


def test_a_note_nobody_would_say_aloud_is_flagged():
    for text in UNSPOKEN:
        assert compose.unspoken(text), text
    for text in ("Would love to hear if anything's coming up.", "I'd love to hear what's coming up.",
                 "Based in Leeds, I work on forecasting.", "I'm new to Manchester from Leeds.",
                 "It's the tool most teams rely on."):
        assert compose.unspoken(text) == [], text


def test_the_apps_own_lines_and_notes_all_read_aloud():
    lines = [v for by in compose.BANK.values() for vs in by.values() for v in vs]
    lines += [v for by in compose.BANK_PLAIN.values() for vs in by.values() for v in vs]
    lines += [compose.OPENER, compose.ABOUT_ME, compose.ASK]
    lines += [compose.how_found_line(k, company="Larkspur", team="pricing", referrer="Ana Rook",
                                     event="the depot summit", shared="Oakmere Foods")
              for k in compose.HOW_FOUND]
    with open(os.path.join(ROOT, ".claude", "skills", "networking", "SKILL.md"),
              encoding="utf-8") as fh:
        skill = fh.read()
    at = skill.index("> Hi Sasha")
    lines.append(" ".join(x.lstrip("> ") for x in skill[at:skill.index("\n\n", at)].splitlines()))
    for reader, title in (("peer", "Data Analyst"), ("decision_maker", "Head of Data"),
                          ("recruiter", "Talent Partner")):
        lines.append(compose.first_note("Ana Rook", how_found=compose.how_found_line(
            "team_search", company="Larkspur", team="pricing"), title=title, variant_key=reader))
        lines.append(compose.inmail("Ana Rook", how_found="I found you on Larkspur's people page",
                                    evidence="At Brindle & Hart I cut forecast error from 22% to "
                                             "14%", title=title, variant_key=reader).body)
    for line in lines:
        assert compose.unspoken(str(line)) == [], line


def test_a_draft_that_does_not_read_aloud_is_not_saved(book, capsys):
    book.put(_row("kestrel_corrie", "Idris Corrie", "Kestrel Mutual",
                  title=RECRUITER["headline"]))
    reading.save("kestrel_corrie", dict(RECRUITER))
    note = book.path / "note.txt"
    note.write_text("Hi Idris, I'm a supply-chain analyst in Manchester looking for my next "
                    "role. Love to hear what's coming up.", encoding="utf-8")
    assert reading.main(["draft", "kestrel_corrie", str(note)]) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not saved" in out and "dropped subject" in out and "Read this note aloud" in out
    assert not os.path.isfile(reading.draft_path("kestrel_corrie"))
    note.write_text("Hi Idris, I'm a supply-chain analyst in Manchester looking for my next "
                    "role. I'd love to hear what's coming up.", encoding="utf-8")
    assert reading.main(["draft", "kestrel_corrie", str(note)]) == reading.EXIT["ok"]


# ------------------------------------------------------------ 14. never say, as a sentence opens

@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def test_a_never_say_written_as_a_sentence_opens_bans_only_that(profile):
    learned.record("voice", "too clipped", "say who", never_say=["Love to hear"],
                   today="2026-10-22")
    for text in ("Love to hear more.", "Thanks. Love to hear more.", "Hi Bo, love to hear more."):
        assert learned.dislikes(text), text
    assert learned.dislikes("I'd love to hear more.") == []
    assert learned.dislikes("I would love to hear more.") == []
    # Written in lower case, it is banned anywhere, as before.
    learned.record("voice", "not that either", "never it", never_say=["reach out"],
                   today="2026-10-22")
    assert learned.dislikes("I'd like to Reach out soon.")


def test_a_never_say_that_refuses_the_persons_own_words_is_said_at_once(profile, capsys):
    e = learned.record("voice", "stop saying it", "never it", never_say=["you're well"],
                       today="2026-10-22")
    assert [(p, s) for p, s, _l in e["own_overlaps"]] == [("you're well", "OPENER")]
    learned.main(["record", "--area", "voice", "--said", "and this", "--rule", "never it",
                  "--never-say", "15 minutes"])
    assert "WARNING" in capsys.readouterr().out


# ============================================================ the same round, second pass

import advice  # noqa: E402


def _recruiter(book, cid="kestrel_corrie"):
    book.put(_row(cid, "Idris Corrie", "Kestrel Mutual", title=RECRUITER["headline"]))
    reading.save(cid, dict(RECRUITER))


# ------------------------------------------------------------ 1. a note past the plan's limit

def test_a_note_past_the_plans_limit_is_not_saved(book, capsys, monkeypatch):
    monkeypatch.setitem(compose.KIND_LIMITS, "connection", {"chars": 300})
    _recruiter(book)
    head = ("Hi Idris, I'm a supply-chain analyst in Manchester looking for my next role. "
            "I've spent four years forecasting depot demand and cutting waste across stores. ")
    tail = "If anything you're working on fits, it'd be great to hear."
    long_ = head + "I'd like to keep doing that work in a team that ships it. " + tail
    note = book.path / "note.txt"
    note.write_text(long_ + "x" * (301 - len(long_) - 1) + ".", encoding="utf-8")
    assert len(note.read_text()) == 301
    assert reading.main(["draft", "kestrel_corrie", str(note)]) == reading.EXIT["error"]
    assert "too long (301 characters, limit 300)" in capsys.readouterr().out
    note.write_text(head + tail, encoding="utf-8")
    assert reading.main(["draft", "kestrel_corrie", str(note)]) == reading.EXIT["ok"]


# ------------------------------------------------------------ 2. a short request for a chat

def test_a_short_request_for_a_chat_or_a_call_is_always_an_allowed_close():
    notes = {"a1": "Hi Ana, I found you on Larkspur's people page. Would you have time for a "
                   "quick chat next week?",
             "a2": "Hi Bo, we both worked at Oakmere Foods. Would you be up for a quick call "
                   "next week?"}
    assert not [f for f in reading.alike(notes) if f[0] == "not your ask"]


# ------------------------------------------------------------ 3. phrasings that read badly

PHRASED = {
    "tells_them_their_job": "You recruit for the data teams at Larkspur.",
    "reads_as_googled": "I saw your propensity model for Larkspur's trial outreach.",
    "undersells": "Freight forecasting is a long way from my background.",
    "vague_close": "Would be great to hear more.",
    "swap_notes": "Would love to swap notes on forecasting.",
    "it_looks_like": "It looks like you moved into pricing.",
    "since_you": "Since you moved into pricing, I wanted to ask about it.",
    "how_they_got_into_recruiting": "How did you get into recruiting?",
    "thread_between_us": "Freight is a thread between us: logistics for you, stores for me.",
    "pretty_much": "It's pretty much the same work.",
    "sometime": "Would you have time for a call sometime?",
    "the_x_side": "I worked on the hardware side at Oakmere Foods.",
    "hoping_to": "I'm hoping to move into pricing.",
}


def test_phrasings_that_read_badly_are_warned_for_everyone():
    for rule, text in PHRASED.items():
        assert rule in {a.rule for a in advice.check(text, "connection")}, rule
    ours = {r for r, _rx, _fix in advice.PHRASINGS}
    for text in ("Sometimes the data is late.", "Who do you hire for?", "on the other side",
                 "side by side", "I'd like to hear more about the team.",
                 "What are you seeing in the market?", "We compared the notes afterwards."):
        assert not ours & {a.rule for a in advice.check(text, "connection")}, text
    # The app's own lines carry none of them, and "it looks like" left the hedge bank.
    lines = [v for by in compose.BANK.values() for vs in by.values() for v in vs]
    for line in lines:
        assert not ours & {a.rule for a in advice.check(str(line), "connection")}, line
    assert not [h for h in advice.HEDGES if "looks like" in h.lower()]


# ------------------------------------------------------------ 4. a batch logged as sent

def test_a_batch_is_logged_from_the_sent_list_not_from_memory(book, capsys):
    for cid, name in (("larkspur_rook", "Ana Rook"), ("larkspur_venn", "Bo Venn")):
        book.put(_row(cid, name, "Larkspur"))
        reading.write_draft(cid, f"Hi {name.split()[0]}, I found you on Larkspur's people page. "
                                 "Would you have time for a quick chat next week?", name)
    args = ["sent", "larkspur_rook", "larkspur_venn", "--draft", "--contacts",
            state.CONTACTS_CSV, "--threads", state.THREADS_CSV]
    assert state.main(args) == 1
    assert "invitations <the page> --record" in capsys.readouterr().out
    assert state.load_threads() == []
    assert state.main(args + ["--each-went"]) == 0
    assert len(state.load_threads()) == 2


# ------------------------------------------------------------ 5 and 6. the sent list

def test_the_sent_list_logs_the_whole_note_and_says_how_far_back_it_reached(book, capsys):
    book.put(_row("kestrel_rook", "Ana Rook", "Kestrel Mutual"))
    whole = ("Hi Ana, I'm a data analyst in Leeds and I've spent four years forecasting depot "
             "demand. Would you have time for a quick chat next week?")
    reading.write_draft("kestrel_rook", whole, "Ana Rook")
    page = book.path / "invites.txt"
    page.write_text("\n".join(["Sent", "People (461)", "Ana Rook",
                               "Head of Pricing at Kestrel Mutual", "Sent 3 days ago", "Withdraw",
                               "Hi Ana, I'm a data analyst in Leeds and I've spe",
                               "...show more"]), encoding="utf-8")
    assert reading.main(["invitations", str(page), "--record"]) == 0
    out = capsys.readouterr().out
    assert "1 of 461 loaded" in out and "reaches back to requests sent about" in out
    row = state.load_threads()[0]
    assert row["full_text"] == whole and "cut where the page folds" not in row["summary"]


# ------------------------------------------------------------ 7. a free Open Profile message

def test_a_free_open_profile_message_spends_no_inmail_credit(book, capsys):
    book.put(_row("fernhill_venn", "Bo Venn", "Fernhill Freight"),
             _row("fernhill_mire", "Sasha Reed", "Fernhill Freight"))
    before = state.platform_budget(book.contacts(), [], TODAY.isoformat())["inmails_left"]
    words = book.path / "words.txt"
    words.write_text("Hi Bo, we both worked at Oakmere Foods.", encoding="utf-8")
    assert state.main(["sent", "fernhill_venn", "--channel", "open_profile", "--text-file",
                       str(words), "--contacts", state.CONTACTS_CSV, "--threads",
                       state.THREADS_CSV, "--today", TODAY.isoformat()]) == 0
    assert "no InMail credit" in capsys.readouterr().out
    contacts, threads = book.contacts(), state.load_threads()
    assert state.platform_budget(contacts, threads, TODAY.isoformat())["inmails_left"] == before
    state.sent(contacts, threads, "fernhill_mire", TODAY, channel="inmail", subject="Forecasting",
               text="Hi Sasha, we both worked at Oakmere Foods.")
    assert state.platform_budget(contacts, threads, TODAY.isoformat())["inmails_left"] < before


# ------------------------------------------------------------ 8. no Connect button

def test_a_second_degree_page_keeps_connect_under_more():
    page = "\n".join(["Bo Venn", "2nd", "Head of Pricing at Larkspur", "Manchester",
                      "Follow", "Message", "More", "Experience", "Head of Pricing", "Larkspur",
                      "Jan 2022 - Present"])
    r = reading.parse(page, name="Bo Venn", company="Larkspur", today=TODAY)
    assert r["connect"] == "missing" and "under More" in reading.no_connect_line(r)
    r3 = reading.parse(page.replace("2nd", "3rd"), name="Bo Venn", company="Larkspur",
                       today=TODAY)
    assert "no request from you" in reading.no_connect_line(r3)


# ------------------------------------------------------------ 9. a paragraph by its subject

def test_a_paragraph_about_the_readers_path_is_about_them_whatever_i_comes_later():
    assert compose.paragraph_role(
        "Going from astrophysics research to running data science at a pension fund is quite "
        "a route, and since I moved from economics into pricing, I had to say hi.") == "them"
    assert compose.paragraph_role("From logistics to forecasting is the move I'm making.") == "me"
    assert compose.paragraph_role("Moving from logistics into forecasting, I found the maths "
                                  "the easy part.") == "me"


def test_a_note_queued_before_the_length_check_is_caught_by_the_batch_check(book, capsys,
                                                                           monkeypatch):
    monkeypatch.setitem(compose.KIND_LIMITS, "connection", {"chars": 300})
    book.put(_row("larkspur_rook", "Ana Rook", "Larkspur"))
    reading.write_draft("larkspur_rook", "Hi Ana, " + "I forecast depot demand. " * 13, "Ana Rook")
    assert reading.main(["batch"]) == reading.EXIT["alike"]
    assert "too long" in capsys.readouterr().out
