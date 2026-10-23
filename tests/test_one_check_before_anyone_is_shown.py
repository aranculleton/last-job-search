"""One check before anyone is shown as someone to write to (tools/network/surface.py).

From a person's repo on 2026-10-23: each step made its own check, and the steps a chat
skipped let through people already written to on another channel and people at an
employer the profile rules out. Joining the connections file to the contact book by
profile address alone, about 120 people looked absent from the book when they were in it:
the two files write one address in different forms, and a name at the employer the file
has, which can be years old, was never tried. And the connections file's employer and
title are not kept current and it has no location, so an old connection is read before
anyone writes to them.
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import sources  # noqa: E402
import state  # noqa: E402
import surface  # noqa: E402

TODAY = datetime.date(2026, 10, 23)


def _row(cid, name, company, url="", status="not_contacted", **kw):
    row = {k: "" for k in state.schema.CONTACT_COLUMNS}
    row.update(contact_id=cid, name=name, company=company, linkedin_url=url, status=status, **kw)
    return row


def _msg(cid, date, direction, channel, text="Hello"):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": channel,
            "scenario": "", "summary": text, "full_text": text}


def _ctx(contacts, threads=(), connections=()):
    return surface.context(contacts=contacts, threads=list(threads),
                           connections=list(connections), today=TODAY)


# ------------------------------------------------------------ one address, many forms

def test_every_form_of_one_address_is_one_person():
    one = state.profile_handle("https://www.linkedin.com/in/example-ren%C3%A9e-abc")
    for form in ("https://ca.linkedin.com/in/example-renée-abc/",
                 "http://linkedin.com/in/Example-Ren%c3%a9e-abc?trk=public_profile",
                 "https://www.linkedin.com/mwlite/in/example-renée-abc",
                 "https://linkedin.com/m/in/example-renée-abc/",
                 "https://www.linkedin.com/in/example-renée-abc"):   # é written apart
        assert state.profile_handle(form) == one, form
    assert state.profile_handle("https://www.linkedin.com/in/example-renee-abc") != one


def test_a_connection_whose_file_has_an_older_employer_is_found_in_the_book():
    # The book has them at their new employer, with no address; the connections file has
    # the employer they were at when they connected.
    book = [_row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight")]
    conn = {"name": "Tamsin Oyelaran", "company": "Kestrel Mutual", "title": "Data Analyst",
            "linkedin_url": "https://www.linkedin.com/in/example-tamsin", "connected_on": "03 Jan 2026"}
    rows, how = surface.in_book(book, conn["name"], "Fernhill Freight",
                                conn["linkedin_url"], also=(conn["company"],))
    assert [r["contact_id"] for r in rows] == ["fernhill_oyelaran"] and how == "name and employer"
    # A different address is a different person, whatever the name.
    book[0]["linkedin_url"] = "https://www.linkedin.com/in/example-tamsin-other"
    assert surface.in_book(book, conn["name"], "Fernhill Freight", conn["linkedin_url"]) == ([], "")


def test_the_same_name_elsewhere_is_shown_with_a_question_never_as_a_stranger(judged):
    judged("Kestrel Mutual")
    book = [_row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight")]
    got = surface.check({"name": "Tamsin Oyelaran", "company": "Kestrel Mutual",
                         "linkedin_url": "https://www.linkedin.com/in/example-tamsin"}, _ctx(book))
    assert got["show"]
    assert any(w.startswith("ask first:") and "fernhill_oyelaran" in w for w in got["warn"])


# ------------------------------------------------------------ the whole thread

def test_someone_written_to_on_any_channel_is_never_shown_as_someone_new(judged):
    judged("Kestrel Mutual")
    url = "https://www.linkedin.com/in/example-corwin"
    for channel in ("connection", "inmail", "email", "message", "intro"):
        book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual", url)]
        log = [_msg("kestrel_haldane", "2026-10-01", "out", channel)]
        got = surface.check({"name": "Corwin Haldane", "company": "Kestrel Mutual",
                             "linkedin_url": url}, _ctx(book, log), queued=True)
        assert not got["show"] and got["reason"].startswith("already written to as kestrel_haldane")
        assert channel in got["reason"] or channel == "message"


def test_a_message_logged_under_their_other_row_counts(judged):
    # Two rows for one person, one address: the thread hangs off the second.
    judged("Kestrel Mutual")
    url = "https://www.linkedin.com/in/example-corwin"
    book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual", url),
            _row("kestrel_haldane2", "Corwin Haldane", "Kestrel Mutual", url + "/")]
    log = [_msg("kestrel_haldane2", "2026-10-01", "out", "inmail")]
    got = surface.check({"contact_id": "kestrel_haldane"}, _ctx(book, log), queued=True)
    assert not got["show"] and "1 sent" in got["reason"]


def test_a_queued_row_whose_log_has_messages_leaves_the_queue(judged):
    # The row still says not_contacted; the export's import put the messages in the log.
    judged("Kestrel Mutual")
    import why
    book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual")]
    log = [_msg("kestrel_haldane", "2026-09-16", "out", "connection", "Hi Corwin"),
           _msg("kestrel_haldane", "2026-10-21", "out", "message", "Following up")]
    assert why.not_writable(book[0], log, TODAY).startswith("already written to")
    assert why.not_writable(book[0], (), TODAY) == ""


def test_someone_in_the_book_and_never_written_to_is_queued_not_new(judged):
    judged("Kestrel Mutual")
    book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual")]
    p = {"name": "Corwin Haldane", "company": "Kestrel Mutual"}
    assert surface.check(p, _ctx(book), queued=True)["show"]
    got = surface.check(p, _ctx(book))
    assert not got["show"] and "in the queue, not someone new" in got["reason"]


# ------------------------------------------------------------ the employer

def test_the_bar_decides_who_is_shown(judged):
    p = {"name": "Idris Corrie", "company": "Saltmarsh Casino"}
    got = surface.check(p, _ctx([]))
    assert not got["show"] and got["reason"].startswith("Saltmarsh Casino: a sector the candidate")
    p = {"name": "Idris Corrie", "company": "Quayside Foods"}
    got = surface.check(p, _ctx([]))
    assert not got["show"] and "not judged against your bar yet" in got["reason"] \
        and 'bar.py judge "Quayside Foods"' in got["reason"]
    judged("Quayside Foods", verdict="none")
    got = surface.check(p, _ctx([]))
    assert not got["show"] and "clears none of pay, prestige or signal" in got["reason"]
    judged("Quayside Foods", verdict="signal")
    assert surface.check(p, _ctx([]))["show"]


def test_yourself_is_never_shown(judged):
    judged("Kestrel Mutual")
    me = {"name": "Morgan Ellis", "company": "Kestrel Mutual",
          "linkedin_url": "https://ca.linkedin.com/in/morgan-ellis-example/"}
    assert surface.check(me, _ctx([])) == {**surface.check(me, _ctx([])), "show": False,
                                           "reason": "that is you"}


# ------------------------------------------------------------ old connections

def test_an_old_connection_is_read_before_anyone_writes_to_them(judged):
    judged("Kestrel Mutual")
    conns = [{"name": "Rhian Pellow", "company": "Kestrel Mutual", "title": "Data Analyst",
              "linkedin_url": "https://www.linkedin.com/in/example-rhian", "connected_on": "12 May 2022"},
             {"name": "Idris Corrie", "company": "Kestrel Mutual", "title": "Analytics Engineer",
              "linkedin_url": "https://www.linkedin.com/in/example-idris", "connected_on": "01 Oct 2026"}]
    ctx = _ctx([], connections=conns)
    old = surface.check(conns[0], ctx)
    assert old["show"] and old["needs_read"]
    assert any("connections file (connected 2022-05-12)" in w and "no location" in w
               for w in old["warn"])
    new = surface.check(conns[1], ctx)
    assert new["show"] and not new["needs_read"]
    got = {p["name"]: p for p in sources.from_connections("Kestrel Mutual", connections=conns,
                                                          contacts=[], threads=[])}
    assert got["Rhian Pellow"]["needs_read"] and got["Rhian Pellow"]["location_unverified"]
    assert not got["Idris Corrie"].get("needs_read") and got["Idris Corrie"]["location_unverified"]


def test_the_connections_rung_says_who_it_left_out_and_why(judged):
    judged("Kestrel Mutual")
    url = "https://www.linkedin.com/in/example-corwin"
    conns = [{"name": "Corwin Haldane", "company": "Kestrel Mutual", "title": "Data Lead",
              "linkedin_url": url, "connected_on": "01 Oct 2026"}]
    book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual", url + "/")]
    log = [_msg("kestrel_haldane", "2026-10-02", "out", "linkedin")]
    held = []
    assert sources.from_connections("Kestrel Mutual", connections=conns, contacts=book,
                                    threads=log, held=held) == []
    assert [(p["name"], why.split(":")[0]) for p, why in held] == \
        [("Corwin Haldane", "already written to as kestrel_haldane")]


def test_the_command_says_show_or_not_for_a_list(judged, tmp_path, capsys, monkeypatch):
    judged("Kestrel Mutual")
    import json
    f = tmp_path / "people.json"
    f.write_text(json.dumps([{"name": "Rhian Pellow", "company": "Kestrel Mutual"},
                             {"name": "Idris Corrie", "company": "Saltmarsh Casino"}]),
                 encoding="utf-8")
    monkeypatch.setattr(state, "first_degree", lambda *a, **k: [])
    assert surface.main(["--file", str(f)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("SHOW  Rhian Pellow (Kestrel Mutual)")
    assert out[1].startswith("NOT   Idris Corrie (Saltmarsh Casino): Saltmarsh Casino: a sector")
    assert out[-1] == "1 of 2 to show"


# ------------------------------------------------------------ found by a review (2026-10-23)

def test_every_row_that_is_them_is_read_whatever_comes_first(judged):
    judged("Kestrel Mutual")
    url = "https://www.linkedin.com/in/example-corwin"
    for book in ([_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual", url),
                  _row("kestrel_haldane2", "Corwin Haldane", "Kestrel Mutual", url, status="closed",
                       outcome="asked not to be contacted")],):
        for order in (book, list(reversed(book))):
            got = surface.check({"contact_id": "kestrel_haldane"}, _ctx(order), queued=True)
            assert not got["show"] and got["reason"].startswith("closed"), got
    # Their address on one row, their InMail under another row with their name and no address.
    book = [_row("kestrel_haldane", "Corwin Haldane", "Kestrel Mutual", url),
            _row("kestrel_corwin", "Corwin Haldane", "Kestrel Mutual")]
    log = [_msg("kestrel_corwin", "2026-10-01", "out", "inmail")]
    for p in ({"contact_id": "kestrel_haldane"},
              {"name": "Corwin Haldane", "company": "Kestrel Mutual", "linkedin_url": url}):
        got = surface.check(p, _ctx(book, log), queued=True)
        assert not got["show"] and "inmail" in got["reason"], (p, got)


def test_a_card_with_no_employer_is_never_merged_through_the_connections_file(judged):
    judged("Fernhill Freight")
    conns = [{"name": "Tamsin Oyelaran", "company": "Fernhill Freight", "title": "Analyst",
              "linkedin_url": "https://www.linkedin.com/in/example-tamsin", "connected_on": ""}]
    book = [_row("fernhill_oyelaran", "Tamsin Oyelaran", "Fernhill Freight")]
    log = [_msg("fernhill_oyelaran", "2026-10-01", "out", "message")]
    got = surface.check({"name": "Tamsin Oyelaran"}, _ctx(book, log, conns))
    assert got["how"] != "name and employer"
    assert any(w.startswith("ask first:") for w in got["warn"]), got


def test_nothing_to_check_and_an_unknown_id_are_said_never_a_crash(capsys):
    assert surface.check({}, _ctx([]))["reason"].startswith("nothing to check")
    got = surface.check({"contact_id": "nobody_here"}, _ctx([]))
    assert not got["show"] and got["reason"] == "nobody_here is not in your contact book"
    assert surface.main(["--id", "nobody_here"]) == 0
    assert "nobody_here is not in your contact book" in capsys.readouterr().out


def test_connections_are_checked_at_the_employer_asked_about(judged):
    judged("Kestrel Mutual")
    conns = [{"name": "Rhian Pellow", "company": "Kestrel Mutual Ratings", "title": "Data Analyst",
              "linkedin_url": "https://www.linkedin.com/in/example-rhian", "connected_on": ""}]
    got = sources.from_connections("Kestrel Mutual", connections=conns, contacts=[], threads=[])
    assert [p["name"] for p in got] == ["Rhian Pellow"]


def test_the_newest_connection_comes_first_among_equals(judged):
    judged("Kestrel Mutual")
    conns = [{"name": n, "company": "Kestrel Mutual", "title": "Data Analyst",
              "linkedin_url": url, "connected_on": d}
             for n, url, d in (
                 ("Idris Corrie", "https://www.linkedin.com/in/example-idris", "02 Jan 2026"),
                 ("Hal Okonedo", "https://www.linkedin.com/in/example-hal", "15 Mar 2026"),
                 ("Rhian Pellow", "https://www.linkedin.com/in/example-rhian", "09 Feb 2026"))]
    got = sources.from_connections("Kestrel Mutual", connections=conns, contacts=[], threads=[])
    assert [p["name"] for p in got] == ["Hal Okonedo", "Rhian Pellow", "Idris Corrie"]
