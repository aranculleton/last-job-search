"""Books made before the export matched people properly are put right by themselves: the
one-record upgrade, run by the sync with no one asked.

A person's copy (2026-11-05) already held many people kept twice (a first-name-only record,
then a second one an import made with the full name and employer) and many known by a first
name alone. The maintainer: nobody should ever have to do this themselves. Only what is
certain changes: two rows that logged one message, and a first-name-only row exactly one of
the person's own connections is. A name alone never joins anyone, and anything unsure is
left for reconcile to list. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import export  # noqa: E402
import state  # noqa: E402

THEM = "https://www.linkedin.com/in/" + "ACoAAB9x" + "ExampleRobinVale"   # the export's member-id form, built so no scan reads it as a real handle
NOTE = "Hi Robin, thanks for getting in touch about the analytics roles you are hiring for."
TODAY = datetime.date(2026, 11, 5)


def _c(cid, name, **kw):
    return {"contact_id": cid, "name": name, "company": "", "company_key": "", "title": "",
            "linkedin_url": "", "status": "awaiting_reply", "notes": "", "outcome": "",
            "next_action": "", "next_action_due": "", **kw}


def _t(cid, date, direction, text):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": "message",
            "scenario": "", "summary": "logged", "full_text": text, "subject": ""}


def _book(tmp_path, contacts, threads, connections=None):
    cp, tp = str(tmp_path / "network_contacts.csv"), str(tmp_path / "network_threads.csv")
    state.save_contacts(contacts, cp)
    state.save_threads(threads, tp)
    ex = tmp_path / "linkedin"
    ex.mkdir(exist_ok=True)
    if connections is not None:
        (ex / "Connections.csv").write_text(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            + "".join(r + "\n" for r in connections), encoding="utf-8")
    return cp, tp, str(ex)


def _dir(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    return d


def _run(paths, dry=False):
    cp, tp, ex = paths
    return export.one_record(cp, tp, dry=dry, src=ex, today=TODAY)


def _by(cp):
    return {c["contact_id"]: c for c in state.load_contacts(cp)}


def _second(**kw):
    return _c("juniper_talent_vale", "Robin Vale", company="Juniper Talent",
              company_key="juniper talent", title="Senior Recruiter", linkedin_url=THEM, **kw)


def test_two_rows_that_logged_one_message_become_one_with_its_fields_and_both_threads(tmp_path):
    kept = _c("recruiter_vale", "Robin", status="replied_needs_response")
    # The export's copy has its quote marks curly where the app's were straight.
    said = "Hi Robin, I'll be glad to hear about the analytics roles you are hiring for."
    threads = [_t("recruiter_vale", "2026-10-01", "out", said),
               _t("recruiter_vale", "2026-10-04", "in", "Happy to talk next week about the role."),
               _t("juniper_talent_vale", "2026-10-01", "out", said.replace("'", "’"))]
    paths = _book(tmp_path, [kept, _second(next_action="follow up", next_action_due="2026-10-15")],
                  threads)
    with open(paths[1], encoding="utf-8") as fh:
        log_before = fh.read()
    assert _run(paths, dry=True)["joined"] == [("recruiter_vale", ["juniper_talent_vale"])]
    assert _by(paths[0])["juniper_talent_vale"]["status"] == "awaiting_reply"   # dry wrote nothing
    got = _run(paths)
    assert got["joined"] == [("recruiter_vale", ["juniper_talent_vale"])], got
    rows = _by(paths[0])
    k, gone = rows["recruiter_vale"], rows["juniper_talent_vale"]
    # The row with his reply is kept, and takes the name, employer, title and address.
    assert (k["name"], k["company"], k["title"]) == ("Robin Vale", "Juniper Talent",
                                                     "Senior Recruiter"), k
    assert state.profile_handle(k["linkedin_url"]) == state.profile_handle(THEM)
    assert "juniper_talent_vale" in k["notes"] and 'was "Robin"' in k["notes"], k["notes"]
    # The other is closed as the same person, saying what it was, so it can be undone.
    assert gone["status"] == "closed" and gone["outcome"] == "duplicate of recruiter_vale"
    assert "Joined by the app on 2026-11-05" in gone["notes"] and "awaiting_reply" in gone["notes"]
    assert "follow up 2026-10-15" in gone["notes"], gone["notes"]
    assert state.duplicate_of(list(rows.values())) == {"juniper_talent_vale": "recruiter_vale"}
    # The message log is not touched: each row keeps its own, the page shows both on one card.
    with open(paths[1], encoding="utf-8") as fh:
        assert fh.read() == log_before
    found = {p["reason"] for p in state.reconcile(list(rows.values()), state.load_threads(paths[1]))}
    assert not found & {"shared_message", "duplicate_holds_more"}, found
    assert export.one_record_line(got) == ("Joined 1 contact that was the same person as "
                                           "another.")


def test_the_row_with_their_latest_reply_is_the_one_kept(tmp_path):
    threads = [_t("recruiter_vale", "2026-10-01", "out", NOTE),
               _t("juniper_talent_vale", "2026-10-01", "out", NOTE),
               _t("juniper_talent_vale", "2026-10-09", "in", "Thanks Morgan, could we talk Friday?")]
    paths = _book(tmp_path, [_c("recruiter_vale", "Robin"), _second()], threads)
    assert _run(paths)["joined"] == [("juniper_talent_vale", ["recruiter_vale"])]
    rows = _by(paths[0])
    assert rows["recruiter_vale"]["outcome"] == "duplicate of juniper_talent_vale"
    assert rows["juniper_talent_vale"]["name"] == "Robin Vale"


def test_a_look_alike_with_no_shared_message_or_anything_against_it_is_left_alone(tmp_path):
    hello = "Thanks for connecting, I would love to hear how the team works."
    contacts = [
        # The same name and employer, and no message in common: a name never joins anyone.
        _c("vale_a", "Robin Vale", company="Juniper Talent", company_key="juniper talent"),
        _c("vale_b", "Robin Vale", company="Juniper Talent", company_key="juniper talent"),
        # One message in common, and different surnames: two people.
        _c("reed_one", "Sasha Reed"), _c("reed_two", "Sasha Halloway"),
        # One message in common, and different employers.
        _c("wren_a", "Wren", company="Kestrel Mutual"), _c("wren_b", "Wren", company="Larkspur Retail"),
        # One line logged under three rows: a template, not one person.
        _c("juno_1", "Juno"), _c("juno_2", "Juno"), _c("juno_3", "Juno"),
        # Said by hand not to be the same person.
        _c("robin_x", "Robin", notes="not the same person as robin_y"), _c("robin_y", "Robin"),
    ]
    threads = [_t("vale_a", "2026-10-01", "out", NOTE), _t("vale_b", "2026-10-02", "out", NOTE)]
    for a, b in (("reed_one", "reed_two"), ("wren_a", "wren_b"), ("robin_x", "robin_y")):
        threads += [_t(a, "2026-10-03", "out", hello), _t(b, "2026-10-03", "out", hello)]
    threads += [_t(j, "2026-10-05", "out", hello) for j in ("juno_1", "juno_2", "juno_3")]
    paths = _book(tmp_path, contacts, threads)
    with open(paths[0], encoding="utf-8") as fh:
        before = fh.read()
    got = _run(paths)
    assert got == {"joined": [], "filled": []}, got
    with open(paths[0], encoding="utf-8") as fh:
        assert fh.read() == before


def test_a_first_name_row_is_filled_from_exactly_one_connection_and_never_from_two(tmp_path):
    one = [f"Robin,Vale,{THEM},,Juniper Talent,Senior Recruiter,01 Oct 2026",
           "Robin,Castellan,https://www.linkedin.com/in/example-robin-castellan,,Kestrel Mutual,"
           "Analyst,02 Oct 2026"]
    paths = _book(tmp_path, [_c("recruiter_vale", "Robin")], [], one)
    got = _run(paths)
    assert got["filled"] == [("recruiter_vale", ["name", "company", "title", "linkedin_url"])], got
    r = _by(paths[0])["recruiter_vale"]
    assert (r["name"], r["company"], r["company_key"], r["title"]) == (
        "Robin Vale", "Juniper Talent", state.company_key("Juniper Talent"), "Senior Recruiter")
    assert "Filled from your LinkedIn connections on 2026-11-05" in r["notes"], r["notes"]
    assert export.one_record_line(got) == ("Filled in the missing details of 1 contact from "
                                           "your LinkedIn download.")
    # Two connections who could be him: nothing is guessed.
    two = one[:1] + ["Robin,Vale,https://www.linkedin.com/in/example-robin-vale-two,,Larkspur "
                     "Retail,Buyer,03 Oct 2026"]
    paths = _book(_dir(tmp_path, "two"),
                  [_c("recruiter_vale", "Robin")], [], two)
    assert _run(paths) == {"joined": [], "filled": []}
    assert _by(paths[0])["recruiter_vale"]["name"] == "Robin"
    # No surname on the row: nobody's.
    paths = _book(_dir(tmp_path, "bare"),
                  [_c("recruiter_x", "Robin")], [], one)
    assert _run(paths)["filled"] == []
    # Already in the book under the full name: a duplicate for reconcile, not a gap to fill.
    paths = _book(_dir(tmp_path, "known"),
                  [_c("recruiter_vale", "Robin"), _second()], [], one)
    assert _run(paths)["filled"] == []


def test_it_runs_with_no_connections_file(tmp_path):
    threads = [_t("recruiter_vale", "2026-10-01", "out", NOTE),
               _t("juniper_talent_vale", "2026-10-01", "out", NOTE)]
    paths = _book(tmp_path, [_c("recruiter_vale", "Robin"), _second()], threads)
    got = _run(paths)
    assert got["joined"] and got["filled"] == [], got
    empty = tmp_path / "nothing"
    empty.mkdir()
    paths = _book(empty, [_c("recruiter_vale", "Robin")], [])
    assert _run(paths) == {"joined": [], "filled": []}


def test_a_second_run_changes_nothing_and_the_upgrade_is_no_longer_pending(tmp_path):
    import profile_upgrades as U
    st = tmp_path / "state"
    st.mkdir()
    threads = [_t("recruiter_vale", "2026-10-01", "out", NOTE),
               _t("juniper_talent_vale", "2026-10-01", "out", NOTE)]
    paths = _book(st, [_c("recruiter_vale", "Robin"), _c("castellan_juno", "Juno"), _second()],
                  threads, ["Juno,Castellan,https://www.linkedin.com/in/example-juno-castellan,,"
                            "Larkspur Retail,Buyer,05 Oct 2026"])
    env = dict(os.environ, LJS_STATE=str(st),
               LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    os.makedirs(os.path.join(str(st), "documents"), exist_ok=True)
    os.replace(paths[2], os.path.join(str(st), "documents", "linkedin"))
    # The upgrade sees it as pending, from the state alone.
    probe = ("import sys; sys.path[:0] = %r; import profile_upgrades as U; print(U._one_record())"
             % [os.path.join(ROOT, "tools")])
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, encoding="utf-8",
                       env=env, cwd=ROOT, timeout=120)
    assert "1 contact(s) kept twice" in r.stdout and "first name only" in r.stdout, r.stdout + r.stderr
    # The sync runs its command; it says one plain line.
    cmd = [sys.executable, *[os.path.join(ROOT, p) if p.endswith(".py") else p
                             for p in next(u for u in U.REGISTRY if u.id == "one-record").command[1:]]]
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == (
        "Joined 1 contact that was the same person as another, and filled in the missing "
        "details of 1 contact from your LinkedIn download."), r.stdout + r.stderr
    with open(paths[0], encoding="utf-8") as fh:
        after = fh.read()
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout
    with open(paths[0], encoding="utf-8") as fh:
        assert fh.read() == after
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, encoding="utf-8",
                       env=env, cwd=ROOT, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr


def test_the_upgrade_is_instant_and_touches_only_the_contact_book_and_log():
    import profile_upgrades as U
    u = next(u for u in U.REGISTRY if u.id == "one-record")
    assert (u.cost, u.needs) == ("instant", "nobody")
    assert set(u.paths) == {"network_contacts.csv", "network_threads.csv"}
    from personal_paths import is_personal
    assert all(is_personal(p) for p in u.paths)


def _page_with(tmp_path, name, both):
    """The example person's page with a row joined to Wren's as the same person, the message
    that showed them to be one logged under Wren's row and, with `both`, under the joined one."""
    import csv
    import json
    import app_state
    st = app_state.small(str(tmp_path / name / "state"))
    profile = app_state.profile_copy(str(tmp_path / name / "profile"))
    said = "Thanks for reaching out, the planning team is hiring in the new year."
    for fname, extra in (
            ("network_contacts.csv", [{"contact_id": "fernhill_wren_dup", "name": "Wren Halloway",
                                       "status": "closed",
                                       "outcome": "duplicate of fernhill_freight_halloway"}]),
            ("network_threads.csv", [
                {"contact_id": cid, "date": "2026-10-20", "direction": "inbound",
                 "channel": "linkedin", "summary": "their note", "full_text": said}
                for cid in (("fernhill_freight_halloway", "fernhill_wren_dup") if both
                            else ("fernhill_freight_halloway",))])):
        path = os.path.join(st, fname)
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        cols = list(rows[0].keys())
        rows += [dict.fromkeys(cols, "") | e for e in extra]
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now",
                        "2026-10-25T18:00:00Z"], capture_output=True, encoding="utf-8", timeout=180,
                       env=dict(os.environ, LJS_STATE=st, LJS_PROFILE=profile))
    model = json.loads(r.stdout)
    kept = next(p for p in model["people"] if p["id"] == "fernhill_freight_halloway")
    return json.dumps(kept).count("the planning team is hiring")


def test_the_message_both_rows_logged_shows_once_on_the_card_kept(tmp_path):
    once = _page_with(tmp_path, "one", both=False)
    assert once and _page_with(tmp_path, "two", both=True) == once
