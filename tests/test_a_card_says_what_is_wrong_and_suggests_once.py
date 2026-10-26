"""A card on the page says what is wrong or urgent, and suggests at most one thing, once.

UX decisions, "Crucial suggestions without pressing Tweak": level 1 (`alerts`) is something
wrong or urgent, with one action and its cost in plain words, and stays whatever the
Suggestions setting says; level 2 (`suggest`) is one suggestion with its evidence, never
offered again after No thanks, paused for a month after three of a kind, and no more than
three new ones reach the page a day. Everything comes from code the app already runs, with
no model call. Every person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_actions  # noqa: E402
import app_alerts  # noqa: E402
import app_lists  # noqa: E402
import app_model  # noqa: E402
import app_state  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, NOW, Search  # noqa: E402

LARKSPUR = "r9-4"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _job(m, jid):
    return next(r for r in m["jobs"]["rows"] if r["id"] == jid)


def _ready(m, rid):
    return next(r for r in m["ready"] if r["id"] == rid)


def test_every_work_kind_has_a_cost_in_plain_words():
    assert set(app_alerts.WORK_COST) == set(page_db.WORK_KINDS)
    assert all(v in app_alerts.COSTS for v in app_alerts.WORK_COST.values())
    assert not any(re.search(r"token", label, re.I) for label in app_alerts.COSTS.values())


def test_someone_who_replied_is_suggested_before_a_cold_application(search):
    m = search.model()
    assert app_model.check(m) == []
    s = _job(m, LARKSPUR)["suggest"]
    assert s["kind"] == "warm" and s["level"] == 2
    assert s["text"].startswith("Juno at Larkspur Retail replied to you on 2026-09-12")
    assert s["action"]["type"] == "work" and s["action"]["kind"] == "reply"
    assert s["action"]["args"]["contact"] and s["cost"]["label"].startswith("Some Claude")
    assert s["since"] == NOW[:10]
    # A posting where nobody has replied carries none.
    assert _job(m, "r9-1")["suggest"] is None


def test_no_thanks_is_for_good_and_can_be_taken_back(search):
    sid = _job(search.model(), LARKSPUR)["suggest"]["id"]
    aid = search.act("suggest.dismiss", sid, rev=_job(search.model(), LARKSPUR)["suggest"]["rev"])
    got = search.apply()
    assert got["ok"] == [aid], got
    assert _job(search.model(), LARKSPUR)["suggest"] is None
    with open(os.path.join(search.profile, "app.json"), encoding="utf-8") as fh:
        assert json.load(fh)["suggest_no"][sid] == {"on": "2026-10-25", "kind": "warm"}
    search.written_back()
    undo = search.act("undo", undoes=aid)
    assert search.apply()["ok"] == [undo]
    assert _job(search.model(), LARKSPUR)["suggest"]["id"] == sid


def test_a_failed_check_is_an_alert_with_its_fix_and_its_cost(search):
    m = search.model()
    fern = next(r for r in m["ready"] if r["company"] == "Fernhill Freight")
    (a,) = fern["alerts"]
    assert a["level"] == 1 and a["kind"] == "checks" and a["text"].startswith("Not made yet")
    assert a["action"]["label"] == "Make it" and a["action"]["kind"] == "draft"
    assert a["cost"]["label"] == "A lot of Claude, several minutes"
    assert _ready(m, KESTREL)["alerts"] == []


def test_a_link_that_closed_or_is_not_the_employers_own_is_said_on_the_card(search):
    path = os.path.join(search.state, "job_search_tracker.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["company"] == "Kestrel Mutual":
            r["notes"] += (" Link closed: no longer on Kestrel Mutual's own board, checked "
                           "2026-10-24 09:00.")
    app_state._save_csv(path, rows, list(rows[0].keys()))
    item = _ready(search.model(), KESTREL)
    assert item["apply"]["status"] == "closed" and item["apply"]["checked_on"] == "2026-10-24" and item["apply"]["checked_at"] is None
    (a,) = item["alerts"]
    assert a["kind"] == "closed" and a["action"] == {
        "type": "act", "label": "Not applying", "action": "ready.not_applying", "item": KESTREL,
        "value": None, "rev": item["rev"]}             # the card's rev, to send as rev_seen
    assert a["cost"]["label"] == "Free, instant"


def test_a_closing_date_tomorrow_and_an_interview_tomorrow_with_no_prep(search):
    path = os.path.join(search.state, "documents", "rounds", "r9.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    rows[0]["deadline"] = "2026-10-26"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    folder = os.path.join(search.state, "documents", "applications",
                          "thornbury_bank_risk_analyst_thornbury")
    os.remove(os.path.join(folder, "interview_prep.md"))
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [ ] Panel interview (scheduled 2026-10-26, with the head of risk)\n")
    m = search.model()
    (a,) = _job(m, "r9-1")["alerts"]
    assert a["kind"] == "deadline" and a["text"] == "Applications close tomorrow."
    (i,) = [x for x in m["interviews"] if x["company"] == "Thornbury Bank"]
    (b,) = i["alerts"]
    assert b["kind"] == "no_prep" and "tomorrow" in b["text"]
    assert b["action"]["kind"] == "prep" and b["action"]["label"] == "Prepare me"
    assert app_model.check(m) == []


def test_a_note_over_its_limit_is_an_alert_and_a_held_tool_the_resume_leaves_out_a_suggestion(
        search):
    draft = os.path.join(search.state, "documents", "network", "kestrel_mutual_ansgar", "draft.md")
    with open(draft, "w", encoding="utf-8") as fh:
        fh.write("Hi Pell, " + "I build weekly forecasts for operations teams. " * 8 + "\n")
    folder = os.path.join(search.state, "documents", "applications",
                          "kestrel_mutual_claims_forecasting_analyst_kestrel")
    with open(os.path.join(folder, "job_posting.md"), "w", encoding="utf-8") as fh:
        fh.write("# Claims Forecasting Analyst\n\nYou will build Looker dashboards and "
                 "forecasts in Python and SQL.\n")
    os.makedirs(os.path.join(search.state, "cv"), exist_ok=True)
    with open(os.path.join(search.state, "cv", "Morgan_Ellis_CV_Kestrel.tex"), "w",
              encoding="utf-8") as fh:
        fh.write("\\cvitem{Tools}{Python, SQL, Excel}\n")
    m = search.model()
    (msg,) = m["messages"]
    (a,) = msg["alerts"]
    assert a["kind"] == "too_long" and a["action"]["kind"] == "tweak"
    assert str(msg["limit"]) in a["text"]
    s = _ready(m, KESTREL)["suggest"]
    assert s["kind"] == "near" and s["text"].startswith("The posting asks for Looker; you have "
                                                        "Power BI")
    assert s["action"]["kind"] == "tweak" and s["action"]["args"]["target"]["id"] == KESTREL
    assert app_model.check(m) == []


def test_only_urgent_keeps_the_alerts_and_drops_the_suggestions(search):
    item = search.item("setting-suggestions")
    assert item["value"] == "on" and [c[0] for c in item["choices"]] == ["on", "urgent", "off"]
    aid = search.act("setting.set", "setting-suggestions", value={"value": "urgent"})
    assert search.apply()["ok"] == [aid]
    m = search.model()
    assert _job(m, LARKSPUR)["suggest"] is None
    assert next(r for r in m["ready"] if r["company"] == "Fernhill Freight")["alerts"]


def _fake(n):
    """A model with n cards each carrying a warm suggestion."""
    rows = [{"id": f"r1-{i}", "suggest": {"id": f"sg-warm-r1-{i}-x", "kind": "warm",
                                          "since": None}} for i in range(n)]
    return {"jobs": {"rows": rows}, "ready": [], "messages": [], "interviews": []}


def test_no_more_than_three_new_suggestions_reach_the_page_a_day(monkeypatch):
    monkeypatch.setattr(app_alerts, "dismissed", lambda: {})
    monkeypatch.setattr(app_alerts, "setting", lambda: "on")
    day = dt.date(2026, 10, 25)
    m = _fake(5)
    app_alerts.offer(m, day)
    got = [r["suggest"] for r in m["jobs"]["rows"]]
    assert [s["since"] for s in got if s] == ["2026-10-25"] * 3 and got.count(None) == 2
    # Three already showed today: none more today; the three keep their day.
    shown = {f"sg-warm-r1-{i}-x": "2026-10-25" for i in range(3)}
    m = _fake(5)
    app_alerts.offer(m, day, shown)
    assert [r["suggest"] and r["suggest"]["since"] for r in m["jobs"]["rows"]] == [
        "2026-10-25"] * 3 + [None, None]
    # Tomorrow, two more join them.
    m = _fake(5)
    app_alerts.offer(m, day + dt.timedelta(days=1), shown)
    assert [r["suggest"]["since"] for r in m["jobs"]["rows"]] == ["2026-10-25"] * 3 + [
        "2026-10-26"] * 2


def test_three_no_thanks_of_one_kind_pause_it_for_a_month():
    day = dt.date(2026, 10, 25)
    no = {f"sg-warm-{i}": {"on": f"2026-10-{20 + i}", "kind": "warm"} for i in range(3)}
    no["sg-near-1"] = {"on": "2026-10-21", "kind": "near"}
    assert app_alerts.paused(day, no) == {"warm": "2026-11-21"}
    assert app_alerts.paused(dt.date(2026, 11, 22), no) == {}


def test_what_the_page_already_shows_is_read_back_from_its_database(tmp_path):
    dump = str(tmp_path)
    os.makedirs(os.path.join(dump, "view"))
    doc = {"rev": "x", "made_at": NOW, "data": {"rows": [
        {"id": "r1-1", "suggest": {"id": "sg-warm-r1-1-x", "since": "2026-10-24"}},
        {"id": "r1-2", "suggest": None}]}}
    with open(os.path.join(dump, "view", "jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(doc, __version__=3), fh)
    db = page_db.load(dump)
    assert app_alerts.shown_in(db.get("view")) == {"sg-warm-r1-1-x": "2026-10-24"}


# ------------------------------------------------------------------ the page's action names

# An action the page sends that the engine has no writer for yet. Each entry must still be
# missing, so this list only shrinks (due.done left it on 2026-10-25).
NOT_YET: set = set()


def test_every_action_the_page_sends_is_one_the_engine_applies():
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    sent = set(re.findall(r'action: "([a-z_]+\.[a-z_]+)"', js))
    known = set(app_actions.ACTIONS)
    assert sent - known <= NOT_YET, sent - known
    assert all(n not in app_actions.ACTIONS for n in NOT_YET)


def test_the_page_and_the_engine_name_each_action_the_same_way(search):
    """One name each (LEGACY_AUDIT W15): a name from the build is not an action."""
    assert not hasattr(app_actions, "ALIASES")
    old = search.act("message.skip", "msg-kestrel_mutual_ansgar")
    skip = search.act("msg.skip", "msg-kestrel_mutual_ansgar")
    got = search.apply()
    assert got["conflict"] == [old] and got["ok"] == [skip], got
    assert search.receipt(old)["note"] == "The app does not know that action yet."
    assert search.model()["messages"] == []


class _Ctx:
    """Just what app_alerts reads for a message: the contact book, its threads, today."""

    def __init__(self, contacts, threads, today):
        self.contacts, self.threads, self.today, self._got = contacts, threads, today, {}

    def _once(self, key, make):
        if key not in self._got:
            self._got[key] = make()
        return self._got[key]


def test_a_clear_difference_in_what_drew_replies_is_suggested_with_its_counts():
    short, long = "Hi, we were both at Leeds. How is the team set up?", "Hi. " + "x" * 330
    contacts, threads = [], []
    for i in range(60):
        cid = f"c{i}"
        brief = i < 30
        contacts.append({"contact_id": cid, "name": f"Ash Brook{i}", "company": "Kestrel Mutual",
                         "route": "cold"})
        threads.append({"contact_id": cid, "date": "2026-08-01", "direction": "outbound",
                        "channel": "linkedin_message", "full_text": short if brief else long})
        if (brief and i < 15) or (not brief and i == 59):
            threads.append({"contact_id": cid, "date": "2026-08-03", "direction": "inbound",
                            "channel": "linkedin_message", "full_text": "Happy to chat."})
    ctx = _Ctx(contacts, threads, dt.date(2026, 10, 25))
    item = {"id": "msg-c99", "contact": "c99", "first_name": "Kit", "kind": "first_note",
            "text": long, "rev": "r"}
    s = app_alerts._works_suggest(ctx, item)
    assert s and s["kind"] == "works"
    assert s["text"].startswith("Your first notes under 200 characters drew more replies "
                                "(15 of 30, 50%) than ones over 300 characters (1 of 30, 3%)")
    assert s["action"]["kind"] == "tweak"
    assert app_alerts._works_suggest(ctx, dict(item, text=short)) is None   # already the shape


# ------------------------------------------------------------------ lists: live shown, history folds


def _big_book(state, n=3000):
    """A contact book of people found and not written to yet, none of them owed anything."""
    path = os.path.join(state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    cols = list(rows[0].keys())
    for i in range(n):
        rows.append(dict.fromkeys(cols, "") | {
            "contact_id": f"prospect_{i:04d}", "name": f"Rue Upcott{i}", "company": f"Teal Freight {i % 90}",
            "company_key": f"teal freight {i % 90}", "route": "cold", "status": "not_contacted",
            "email": f"rue{i}@example.com"})
    app_state._save_csv(path, rows, cols)


def test_every_live_contact_shows_and_the_rest_fill_a_budget_then_fold_into_the_database(search):
    _big_book(search.state)
    m = search.model()
    assert app_model.check(m) == []
    count, lists = m["people_count"], m["lists"]["people"]
    live = [p for p in m["people"] if p["live"]]
    assert {p["first_name"] for p in live} >= {"Juno"}            # the one who replied
    assert len(live) == count["live"] and count["all"] == lists["total"] > count["shown"]
    assert count["rest"] == count["all"] - count["shown"] > 0
    assert app_lists.size(m["people"]) < app_lists.PEOPLE_BYTES + 5_000
    assert lists["counts"]["status"]["not_contacted"] >= 3000
    assert lists["counts"]["route"]["cold"] >= 3000 and len(lists["counts"]["employer"]) <= 41
    # `app.py view` writes the whole book in parts the database takes, nobody's address in it.
    out = os.path.join(search.dump, "view_out")
    got = json.loads(search.run("view", out, "--now", NOW))
    ids, parts = [], 0
    for b in got["batches"]:
        with open(b, encoding="utf-8") as fh:
            for e in json.load(fh):
                if e["doc_id"].startswith("list~people~"):
                    parts += 1
                    assert os.path.getsize(e["file_path"]) < 256 * 1024
                    with open(e["file_path"], encoding="utf-8") as doc:
                        body = doc.read()
                    assert "@example.com" not in body and "Upcott" not in body
                    ids += [i["id"] for i in json.loads(body)["items"]]
    assert parts == lists["parts"] >= 2
    assert len(ids) == len(set(ids)) == count["all"]


def test_a_closed_application_folds_after_a_month_and_an_open_one_never(search):
    path = os.path.join(search.state, "job_search_tracker.csv")
    rows = app_state._csv_rows(path)
    rows += [{"date": "2026-03-01", "company": "Wren Health", "role": "Old Open Analyst",
              "status": "applied", "applied_on": "2026-03-02", "notes": ""},
             {"date": "2026-03-01", "company": "Sedge Energy", "role": "Old Closed Analyst",
              "status": "rejected", "applied_on": "2026-03-02", "notes": "2026-03-20: rejected"}]
    app_state._save_csv(path, rows, list(rows[0].keys()))
    m = search.model()
    shown = {a["role"] for a in m["done"]["applications"]}
    assert "Old Open Analyst" in shown and "Old Closed Analyst" not in shown
    apps = m["lists"]["applications"]
    assert apps["folded"] == {"count": apps["total"] - apps["shown"], "days": 30}
    assert apps["folded"]["count"] >= 1 and apps["counts"]["status"]["rejected"] >= 1


def test_a_past_interview_stays_two_weeks_then_folds(search):
    folder = os.path.join(search.state, "documents", "applications",
                          "thornbury_bank_risk_analyst_thornbury")
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [x] Panel interview (2026-10-20, with the head of risk)\n")
    path = os.path.join(search.state, "job_search_tracker.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["company"] == "Thornbury Bank":
            r["status"] = "rejected"
    app_state._save_csv(path, rows, list(rows[0].keys()))
    (i,) = [x for x in search.model()["interviews"] if x["company"] == "Thornbury Bank"]
    assert i["past"] is True and i["when"] == "2026-10-20" and i["alerts"] == []
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [x] Panel interview (2026-09-20, with the head of risk)\n")
    m = search.model()
    assert [x for x in m["interviews"] if x["company"] == "Thornbury Bank"] == []
    assert m["lists"]["interviews"]["folded"]["count"] == 1


def test_parts_stay_under_the_database_limit_and_a_shrunk_list_drops_its_old_parts():
    items = [{"id": f"c{i}", "first_name": "Kit", "employer": "Teal Freight " * 4,
              "status": "not_contacted"} for i in range(4000)]
    parts = app_lists.chunks(items)
    assert len(parts) >= 2 and sum(len(p) for p in parts) == 4000
    assert all(app_lists.stored({"items": p}) < 256 * 1024 for p in parts)
    view = {"list~people~1": {}, "list~people~2": {}, "list~people~3": {}, "jobs": {}}
    assert app_lists.stale({"people": items[:10]}, view) == ["list~people~2", "list~people~3"]


# ------------------------------------------------------------------ Done on what is due


def test_done_on_a_dated_action_and_on_a_follow_up_is_applied_and_can_be_taken_back(search):
    path = os.path.join(search.state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    cols = list(rows[0].keys())
    rows.append(dict.fromkeys(cols, "") | {
        "contact_id": "wren_health_orme", "name": "Tam Orme", "company": "Wren Health",
        "company_key": "wren health", "route": "alumni_school", "status": "call_booked",
        "next_action": "Confirm the call time", "next_action_due": "2026-10-24"})
    app_state._save_csv(path, rows, cols)
    tpath = os.path.join(search.state, "job_search_tracker.csv")
    trows = app_state._csv_rows(tpath)
    trows.append({"date": "2026-10-14", "company": "Sedge Energy", "role": "Data Analyst",
                  "status": "applied", "applied_on": "2026-10-15", "notes": "applied online",
                  "confirmed_by": "chat", "confirmed_at": "2026-10-15 09:00",
                  "source": "https://jobs.example/sedge/data"})
    app_state._save_csv(tpath, trows, list(trows[0].keys()))
    due = {d["id"]: d for d in search.model()["due"]}
    act_id = next(i for i, d in due.items() if "wren_health_orme" in i)
    app_id = next(i for i, d in due.items() if "Sedge Energy" in d["title"])
    assert due[act_id]["done"] == {"action": "due.done", "label": "Done"}
    assert due[app_id]["done"] and due["due-reply-larkspur_retail_castellan"]["done"] is None
    a1 = search.act("due.done", act_id, rev=due[act_id]["rev"])
    a2 = search.act("due.done", app_id, rev=due[app_id]["rev"])
    got = search.apply()
    assert got["ok"] == [a1, a2], [search.receipt(a) for a in (a1, a2)]
    now = {d["id"] for d in search.model()["due"]}
    assert act_id not in now and app_id not in now
    assert "followed up 2026-10-25" in search.tracker_row("Sedge Energy")["notes"]
    # Taken back, with no time limit: a week later the inverse still runs.
    search.written_back()
    u1 = search.act("undo", undoes=a1)
    u2 = search.act("undo", undoes=a2)
    later = json.loads(search.run("apply", search.dump, "--chat", "cloud-1",
                                  "--now", "2026-11-01T09:00:00Z"))
    assert later["ok"] == [u1, u2], [search.receipt(u) for u in (u1, u2)]
    assert search.tracker_row("Sedge Energy")["notes"] == "applied online"
    assert act_id in {d["id"] for d in search.model()["due"]}


def test_an_answer_only_a_chat_can_take_back_says_so(search):
    sid = _job(search.model(), LARKSPUR)["suggest"]["id"]
    aid = search.act("suggest.dismiss", sid, rev=_job(search.model(), LARKSPUR)["suggest"]["rev"])
    search.apply()
    assert search.receipt(aid)["undo"]["action"] == "suggest.undismiss"
    assert "undo_note" not in search.receipt(aid)
    m = search.model()
    m2 = [n for n in m["needs_you"] if n["kind"] == "setup"]
    assert m2 == []                                     # a private copy has no outside cards


# ------------------------------------------------------------------ dates, holds and links


def test_an_interview_day_is_a_day_and_times_carry_their_zone(search):
    m = search.model()
    (i,) = m["interviews"]
    assert i["when"] == "2026-10-28" and i["all_day"] is True and i["time"] is None
    assert m["person"]["time_zone"] == "Europe/London"
    assert m["made_at"].endswith("Z")
    for r in m["jobs"]["rows"]:
        assert r["apply"]["checked_at"] is None or r["apply"]["checked_at"].endswith("Z")


def test_a_referral_in_flight_marks_every_job_and_draft_there_and_links_the_contact(search):
    path = os.path.join(search.state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["contact_id"] == "kestrel_mutual_ansgar":
            r["status"] = "referral_in_progress"
            r["next_action"] = "Wait for the recruiter to call"
    app_state._save_csv(path, rows, list(rows[0].keys()))
    m = search.model()
    job = next(r for r in m["jobs"]["rows"] if r["company"] == "Kestrel Mutual")
    draft = _ready(m, KESTREL)
    for card in (job, draft):
        hold = next(a for a in card["alerts"] if a["kind"] == "referral_hold")
        assert hold["contact"] == "kestrel_mutual_ansgar"
        assert hold["action"] == {"type": "go", "label": "Ask Pell first", "to": "people",
                                  "item": "kestrel_mutual_ansgar"}
        assert "Wait for the recruiter to call" in hold["why"] and "Ansgar" not in hold["why"]
        assert card["suggest"] is None
    assert app_model.check(m) == []


def test_a_job_its_draft_its_contact_and_its_interview_link_to_each_other(search):
    m = search.model()
    job = next(r for r in m["jobs"]["rows"] if r["company"] == "Kestrel Mutual")
    draft = _ready(m, KESTREL)
    pell = next(p for p in m["people"] if p["id"] == "kestrel_mutual_ansgar")
    assert job["draft"] == KESTREL and draft["job"] == job["id"]
    assert job["related"]["people"] == ["kestrel_mutual_ansgar"]
    assert pell["related"]["jobs"] == [job["id"]] and pell["related"]["ready"] == [KESTREL]
    assert "people" not in pell["related"]                   # never every colleague
    (i,) = m["interviews"]
    # The interview links to its own application (the record it is a stage of), and nothing
    # else is at that employer.
    assert i["draft"] is None and i["related"] == {"applications": [
        "app-thornbury_bank_risk_analyst"]}
