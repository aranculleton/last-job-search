"""Contacts, To do, Messages and the brief show only what the person's own rules allow, and
say it once: where each person stands is worked out in the engine, never again on the page.

From the 3 November 2026 audit of a real search (716 people, 150 owed), every case rebuilt
here with invented people at an invented scale:

- a third and a fourth unanswered message drafted and offered with Copy and "I sent it", and
  To do listing people past the limit of two as follow-ups to send;
- follow-ups and replies offered at employers the person's bar turns down, and follow-ups
  to people whose connection request nobody accepted;
- a booked call shown as "Replied: your turn" because the invitation was the last message;
- a thumbs-up from fourteen months ago reopening a thread gone quiet;
- "Next: None", job numbers, links and notes to Claude in Next lines; closed people still
  told what to send;
- the Contacts header, its filters and To do each counting follow-ups and "needs you" their
  own way, and a filter showing nothing because its people sat behind the fold;
- a first note that breaks the person's own rules offered as ready to send.

Every person and employer here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_state  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW              # 2026-10-25T18:00:00Z
TODAY = app_state.TODAY
PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1440, "height": 900}

CONTACT_COLUMNS = ["contact_id", "name", "title", "company", "company_key", "location",
                   "linkedin_url", "email", "tier", "route", "route_detail", "referred_by",
                   "signal", "signal_date", "first_contacted", "channel", "status",
                   "next_action", "next_action_due", "outcome", "linked_application", "notes"]
THREAD_COLUMNS = ["contact_id", "date", "direction", "channel", "scenario", "summary", "full_text"]
HOME = "Manchester, England, United Kingdom"


def person(cid, name, company, status, title="Data Lead", location=HOME, action="", due="",
           **more):
    return dict(dict.fromkeys(CONTACT_COLUMNS, ""), contact_id=cid, name=name, title=title,
                company=company, company_key=company.lower(), location=location,
                linkedin_url="https://www.linkedin.com/in/" + cid.replace("_", "-") + "-example",
                tier="2", route="cold", channel="linkedin", status=status, next_action=action,
                next_action_due=due, notes="invented", **more)


def out(cid, day, text, scenario="first_note", channel="linkedin"):
    return {"contact_id": cid, "date": day, "direction": "outbound", "channel": channel,
            "scenario": scenario, "summary": "message", "full_text": text}


def inn(cid, day, text, scenario="detailed_generous"):
    return {"contact_id": cid, "date": day, "direction": "inbound", "channel": "linkedin",
            "scenario": scenario, "summary": "replied", "full_text": text}


NOTE = "Hi {n}, hope you're well. I build demand forecasts in Manchester. How is your team set up?"
NUDGE = "Hi {n}, following up on my note about the planning team. Would be good to hear how it works."


def the_cases():
    """(contacts, threads, drafts): one of each case the audit found, invented."""
    c, t, d = [], [], {}
    # Their limit of two reached, and a draft for a third: never offered, Close instead.
    c.append(person("harrow_freight_brook", "Juno Brook", "Harrow Freight", "awaiting_reply",
                    action="Send the short nudge (draft in notes)", due="2026-10-20"))
    t += [out("harrow_freight_brook", "2026-09-20", NOTE.format(n="Juno")),
          out("harrow_freight_brook", "2026-10-02", NUDGE.format(n="Juno"), "follow_up")]
    d["harrow_freight_brook"] = "Hi Juno, one more nudge: is the planning team hiring at all?"
    # Three unanswered in a conversation: a fourth is never drafted or listed.
    c.append(person("lark_retail_caddel", "Wren Caddel", "Lark Retail", "in_conversation",
                    action="Follow up on the planning role", due="2026-10-21"))
    t += [out("lark_retail_caddel", "2026-08-01", NOTE.format(n="Wren")),
          inn("lark_retail_caddel", "2026-08-03", "Happy to chat, Morgan."),
          out("lark_retail_caddel", "2026-08-10", "Thanks Wren, how about Tuesday?", "reply"),
          out("lark_retail_caddel", "2026-09-01", "Hi Wren, still keen to talk.", "follow_up"),
          out("lark_retail_caddel", "2026-10-01", "Hi Wren, checking once more.", "follow_up")]
    d["lark_retail_caddel"] = "Hi Wren, a last nudge about the planning role."
    # An employer the bar turns down (the example profile excludes betting): nothing, even a reply.
    c.append(person("rook_betting_dunmore", "Tamsin Dunmore", "Rook Betting", "awaiting_reply",
                    action="One nudge if no reply", due="2026-10-10"))
    t.append(out("rook_betting_dunmore", "2026-10-01", NOTE.format(n="Tamsin")))
    c.append(person("rook_betting_elsworth", "Ivo Elsworth", "Rook Betting",
                    "replied_needs_response"))
    t += [out("rook_betting_elsworth", "2026-10-01", NOTE.format(n="Ivo")),
          inn("rook_betting_elsworth", "2026-10-20", "Thanks Morgan, we are hiring analysts.")]
    # Outside where they look (the example person is in the UK).
    c.append(person("teal_energy_farrow", "Sasha Farrow", "Teal Energy", "awaiting_reply",
                    location="Toronto, Ontario, Canada", action="One nudge if no reply",
                    due="2026-10-12"))
    t.append(out("teal_energy_farrow", "2026-10-02", NOTE.format(n="Sasha")))
    # A request nobody accepted: there is nobody to message yet.
    c.append(person("moss_foods_glen", "Rhian Glen", "Moss Foods", "awaiting_reply",
                    action="Once they accept: one nudge if no reply", due="2026-10-15"))
    t.append(out("moss_foods_glen", "2026-10-05", NOTE.format(n="Rhian"), "connection_request",
                 "connection"))
    # A call booked by their invitation, the last message, for a day ahead.
    c.append(person("vale_health_hatherly", "Riley Hatherly", "Vale Health", "call_booked",
                    action="Call Tue 27 Oct, 2pm UK", due="2026-10-27"))
    t += [out("vale_health_hatherly", "2026-10-10", NOTE.format(n="Riley")),
          inn("vale_health_hatherly", "2026-10-22", "Could you do a screen on Tuesday 27th at 2pm?",
              "interview_invite")]
    # A call booked for a day gone by: how did it go, and the thank-you.
    c.append(person("wren_logistics_ivers", "Robin Ivers", "Wren Logistics", "call_booked",
                    action="Call Thursday 22 Oct, 2pm UK", due="2026-10-22"))
    t += [out("wren_logistics_ivers", "2026-10-05", NOTE.format(n="Robin")),
          inn("wren_logistics_ivers", "2026-10-08", "Thursday the 22nd at 2pm works.")]
    # Gone quiet, then a thumbs-up long ago: still gone quiet.
    c.append(person("quay_bank_jessop", "Quinn Jessop", "Quay Bank", "gone_cold",
                    title="Recruiter", action="None."))
    t += [out("quay_bank_jessop", "2025-08-20", NOTE.format(n="Quinn")),
          inn("quay_bank_jessop", "2025-08-25", "\U0001F44D")]
    # Closed, with a step and a date still on the row: told nothing to send.
    c.append(person("sedge_mutual_kellam", "Rosalind Kellam", "Sedge Mutual", "closed",
                    action="Send now: connection note", due="2026-10-08"))
    # A reply owed, with notes to Claude, a job number and a link on the row.
    c.append(person("kestrel_bank_lowther", "Shirin Lowther", "Kestrel Bank",
                    "replied_needs_response",
                    action="Apply to Demand Analyst (4481616253) through her referral link "
                           "https://jobs.example/kestrel/ref/abc", due="2026-10-18"))
    t += [out("kestrel_bank_lowther", "2026-10-01", NOTE.format(n="Shirin")),
          inn("kestrel_bank_lowther", "2026-10-17", "Here is my referral link for the Demand "
              "Analyst role, Morgan: apply through it and I will flag you.")]
    # We wrote last in a conversation, nothing owed: never "Draft a reply".
    c.append(person("harrow_foods_marden", "Thad Marden", "Harrow Foods", "in_conversation",
                    action="Follow-up drafted 2026-10-23 (batch 6), waiting for him to send",
                    due="2026-10-30"))
    t += [out("harrow_foods_marden", "2026-10-01", NOTE.format(n="Thad")),
          inn("harrow_foods_marden", "2026-10-03", "Sure, happy to talk."),
          out("harrow_foods_marden", "2026-10-20", "Great, does Thursday suit?", "reply")]
    # A follow-up allowed and due: the one "follow" person To do and Contacts both count.
    c.append(person("teal_retail_nettle", "Corwin Nettle", "Teal Retail", "awaiting_reply",
                    action="One nudge if no reply", due="2026-10-19"))
    t.append(out("teal_retail_nettle", "2026-10-09", NOTE.format(n="Corwin")))
    # A dated step of the person's own that is only to wait.
    c.append(person("moss_energy_orme", "Idris Orme", "Moss Energy", "in_conversation",
                    action="Wait for them to book a call next week", due="2026-10-24"))
    t += [out("moss_energy_orme", "2026-10-01", NOTE.format(n="Idris")),
          inn("moss_energy_orme", "2026-10-05", "Let me find a time next week."),
          out("moss_energy_orme", "2026-10-06", "Thanks Idris, any day suits.", "reply")]
    # A dated step that is a message: its button drafts that message.
    c.append(person("vale_freight_pellow", "Taylor Pellow", "Vale Freight", "in_conversation",
                    action="Send the referral ask for the Planning Analyst role",
                    due="2026-10-23"))
    t += [out("vale_freight_pellow", "2026-10-01", NOTE.format(n="Taylor")),
          inn("vale_freight_pellow", "2026-10-04", "No roles in my team now, but ask any time."),
          out("vale_freight_pellow", "2026-10-06", "Thanks Taylor, I will.", "reply")]
    # A first note that breaks the person's own rules: it asks for a job and is over the limit.
    c.append(person("rook_health_quarry", "Zoe Quarry", "Rook Health", "not_contacted",
                    action="Send the first note", due="2026-10-26"))
    d["rook_health_quarry"] = (
        "Hi Zoe, hope you're well. I build demand forecasts in Manchester for retailers and "
        "freight firms, with weekly models in Python and SQL that planners use every Monday. "
        "Are you hiring at the moment? I would love a job on your team, and I can start "
        "straight away if there is anything open now or coming up soon in planning or data.")
    # A note past its day with nothing logged: asked whether it went, never "send now".
    c.append(person("lark_health_upcott", "Ines Upcott", "Lark Health", "not_contacted",
                    action="Send now: connection note", due="2026-10-17"))
    # A reply drafted and waiting, overdue: replies lead Messages and its corner says Overdue.
    c.append(person("kestrel_foods_thorne", "Rafe Thorne", "Kestrel Foods",
                    "replied_needs_response", due="2026-10-20"))
    t += [out("kestrel_foods_thorne", "2026-10-01", NOTE.format(n="Rafe")),
          inn("kestrel_foods_thorne", "2026-10-19", "Happy to talk, Morgan. What would you like to know?")]
    d["kestrel_foods_thorne"] = ("Thanks Rafe. I'd love to hear how the planning team works "
                                 "and what a good first year looks like there.")
    # A referral asked for: the row says so.
    c.append(person("quay_retail_kellam", "Ana Kellam", "Quay Retail", "in_conversation"))
    t += [out("quay_retail_kellam", "2026-10-01", NOTE.format(n="Ana")),
          inn("quay_retail_kellam", "2026-10-03", "Glad to help, Morgan."),
          out("quay_retail_kellam", "2026-10-10", "Would you refer me for the Planning Analyst role?",
              "referral_ask")]
    # Someone at an employer with an interview going: the link says which.
    c.append(person("thornbury_bank_brook", "Ash Brook", "Thornbury Bank", "awaiting_reply"))
    t.append(out("thornbury_bank_brook", "2026-10-15", NOTE.format(n="Ash")))
    # A first note written before their profile was read: its alert says what it costs in words.
    c.append(person("sedge_foods_glen", "Kit Glen", "Sedge Foods", "not_contacted"))
    d["sedge_foods_glen"] = ("WAITS ON A READ\n\nHi Kit, hope you're well. I build demand "
                             "forecasts in Manchester. How is the planning team set up?")
    # Two people with the same first name and no employer: told apart.
    for i, last in enumerate(("Rendle", "Stannard")):
        c.append(person(f"zo_{last.lower()}", f"Zo {last}", "", "awaiting_reply",
                        title="Talent Partner" if i else "Recruiter (UK)", location=""))
        t.append(out(f"zo_{last.lower()}", "2026-10-18", NOTE.format(n="Zo")))
    return c, t, d


class Book:
    """The example person's search with the cases above, and as many more people as asked."""

    def __init__(self, root, crowd=0):
        self.state = app_state.small(os.path.join(root, "state"))
        self.profile = app_state.profile_copy(os.path.join(root, "profile"))
        self.root = root
        self.env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                        LJS_COPY="private")
        self.env.pop("LJS_TODAY", None)
        c, t, d = the_cases()
        base_c = app_state._csv_rows(os.path.join(self.state, "network_contacts.csv"))
        base_t = app_state._csv_rows(os.path.join(self.state, "network_threads.csv"))
        for i in range(crowd):
            first = app_state.FIRST[i % len(app_state.FIRST)].title()
            last = app_state.LAST[(i // len(app_state.FIRST)) % len(app_state.LAST)].title()
            firm = (app_state.FIRM[i % len(app_state.FIRM)].title() + " "
                    + app_state.KIND[(i // 3) % len(app_state.KIND)].title())
            cid = f"crowd_{i}"
            kind = i % 5
            if kind == 0:     # owed a reply
                c.append(person(cid, f"{first} {last}", firm, "replied_needs_response"))
                t += [out(cid, "2026-10-01", NOTE.format(n=first)),
                      inn(cid, f"2026-10-{10 + i % 12:02d}", "Thanks, happy to talk.")]
            elif kind == 1:   # one note out, a nudge due
                c.append(person(cid, f"{first} {last}", firm, "awaiting_reply",
                                action="One nudge if no reply", due="2026-10-20"))
                t.append(out(cid, "2026-10-08", NOTE.format(n=first)))
            elif kind == 2:   # two out, the limit reached
                c.append(person(cid, f"{first} {last}", firm, "awaiting_reply"))
                t += [out(cid, "2026-09-01", NOTE.format(n=first)),
                      out(cid, "2026-09-20", NUDGE.format(n=first), "follow_up")]
            elif kind == 3:   # never written to
                c.append(person(cid, f"{first} {last}", firm, "not_contacted"))
            else:             # quiet long ago
                c.append(person(cid, f"{first} {last}", firm, "gone_cold"))
                t.append(out(cid, "2026-03-01", NOTE.format(n=first)))
        rows = base_c + c
        _save(os.path.join(self.state, "network_contacts.csv"), rows, CONTACT_COLUMNS)
        _save(os.path.join(self.state, "network_threads.csv"), base_t + t, THREAD_COLUMNS)
        prep = os.path.join(self.state, "documents", "network", "moss_energy_orme", "prep.md")
        os.makedirs(os.path.dirname(prep), exist_ok=True)
        with open(prep, "w", encoding="utf-8") as fh:
            fh.write("# Call prep: Idris\n\n## What to ask\n\nHow the planning team works "
                     "with the stores, and what a good first year looks like.\n")
        for cid, text in d.items():
            path = os.path.join(self.state, "documents", "network", cid, "draft.md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")

    def run(self, *args, ok=(0,)):
        r = subprocess.run([sys.executable, *args], env=self.env, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=300)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout + r.stderr

    def model(self):
        return json.loads(self.run(APP, "model", "--now", NOW))


def _save(path, rows, columns):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in columns})


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    return Book(str(tmp_path_factory.mktemp("rules")))


@pytest.fixture(scope="module")
def model(book):
    return book.model()


def _p(m, cid):
    return next(p for p in m["people"] if p["id"] == cid)


def _due_of(m, cid):
    return [d for d in m["due"] if cid in d["id"] or d.get("item") == cid]


# ------------------------------------------------------------------ the engine's one answer

def test_past_their_limit_nobody_is_drafted_listed_or_offered_a_follow_up(model):
    """contacts 6 and 20, contacts_chat_2 3: a third and a fourth message. And nothing to
    do is not a To do (the maintainer, 2026-11-04): they are left alone, in Contacts with
    Close, never a To do row to close, nor counted there."""
    msgs = {x["contact"] for x in model["messages"]}
    for cid in ("harrow_freight_brook", "lark_retail_caddel"):
        p = _p(model, cid)
        assert p["group"] == "leave" and p["owed"]["kind"] == "close", p
        assert p["owed"]["action"] == "person.status" and p["owed"]["due"] is None, p["owed"]
        assert p["owed"]["value"]["status"] == "gone_cold", p["owed"]
        assert p["next"].startswith("No reply to ") and "leave it" in p["next"], p["next"]
        assert cid not in msgs, "a draft past the limit is never offered"
        assert not _due_of(model, cid), _due_of(model, cid)
    hidden = next(d for d in model["due"] if d["kind"] == "hidden")
    assert "limit" not in hidden["title"] and "messages" not in hidden["title"], hidden["title"]


def test_a_turned_down_employer_and_a_place_outside_the_search_are_never_offered(model):
    """contacts 45, contacts_chat_2 4 and 13: the bar and where they live, in every screen."""
    for cid in ("rook_betting_dunmore", "rook_betting_elsworth"):
        p = _p(model, cid)
        assert p["group"] == "held" and p["owed"] is None and "turned down" in p["hold"], p
        assert not _due_of(model, cid)
    sasha = _p(model, "teal_energy_farrow")
    assert sasha["group"] == "held" and "Canada" in sasha["hold"] and sasha["owed"] is None
    assert not _due_of(model, "teal_energy_farrow")
    hidden = next(d for d in model["due"] if d["kind"] == "hidden")
    assert "at employers you turned down" in hidden["title"] and "outside where you look" in hidden["title"]


def test_a_request_nobody_accepted_offers_no_follow_up(model):
    """contacts 7."""
    p = _p(model, "moss_foods_glen")
    assert p["owed"] is None and p["group"] == "held"
    assert p["hold"] == "Your connection request has not been accepted yet"
    assert not [d for d in _due_of(model, "moss_foods_glen") if d["kind"] != "withdraw"]


def test_a_booked_call_stays_booked_and_one_gone_by_asks_how_it_went(model):
    """contacts 9 and 10, contacts_chat_2 8."""
    riley = _p(model, "vale_health_hatherly")
    assert riley["status"] == "call_booked" and riley["status_word"] == "Call booked", riley
    assert riley["owed"]["kind"] == "prep" and riley["call"]["day"] == "2026-10-27"
    assert not [d for d in _due_of(model, "vale_health_hatherly") if d["kind"] == "reply"]
    robin = _p(model, "wren_logistics_ivers")
    assert robin["status"] == "call_booked" and robin["owed"]["kind"] == "thanks"
    assert robin["next"].startswith("How did it go?")


def test_a_thumbs_up_long_ago_does_not_reopen_a_thread_and_none_is_not_a_step(book, model):
    """contacts 11 and 12."""
    quinn = next(p for p in model["people"] + _whole(book, model) if p["id"] == "quay_bank_jessop")
    assert quinn["status"] == "gone_cold" and quinn.get("group") == "done"
    assert quinn.get("next_action", "") == "" and quinn.get("owed") is None


def test_closed_people_are_told_nothing_to_send(book, model):
    """contacts 13."""
    rosalind = next(p for p in model["people"] + _whole(book, model) if p["id"] == "sedge_mutual_kellam")
    assert rosalind["group"] == "done" and not rosalind.get("owed") and not rosalind.get("live")


def test_a_next_step_carries_no_id_link_or_note_to_claude(model):
    """contacts 23, contacts_chat_2 9 and 11."""
    shirin = _p(model, "kestrel_bank_lowther")
    assert "4481616253" not in shirin["next_action"] and "http" not in shirin["next_action"]
    assert shirin["link"] == "https://jobs.example/kestrel/ref/abc"
    assert shirin["owed"]["kind"] == "reply" and shirin["owed"]["logged"] is True
    thad = _p(model, "harrow_foods_marden")
    assert thad["next_action"] == "", thad["next_action"]       # a note to Claude says nothing
    blob = json.dumps(model["people"])
    for leak in ("batch 6", "(draft in notes)", "waiting for him"):
        assert leak not in blob, leak


def test_we_wrote_last_so_nothing_is_a_reply_and_a_wait_is_not_needed(model):
    """contacts 14, contacts_chat_2 2 and 6."""
    thad = _p(model, "harrow_foods_marden")
    assert thad["owed"] is None or thad["owed"]["kind"] != "reply", thad["owed"]
    # A wait whose day has gone is a follow-up, and the line says so with its button: never
    # "Wait for ..." above "Draft the follow-up" (contacts 15).
    idris = _p(model, "moss_energy_orme")
    assert idris["group"] == "follow" and idris["owed"]["kind"] == "follow_up", idris
    assert idris["next"] == "Follow up", idris["next"]
    assert "first year" in idris["call"]["prep"]["text"], "their call prep is readable on their page"


def test_a_dated_message_step_is_its_own_button(model):
    """contacts 15 and 38."""
    taylor = _p(model, "vale_freight_pellow")
    assert taylor["group"] == "now" and taylor["owed"]["label"] == "Draft it"
    assert taylor["owed"]["args"]["step"].startswith("Send the referral ask")


def test_counts_are_one_number_each_agreeing_with_to_do(model):
    """contacts 16, contacts_chat_2 15: the header, the filters and To do count the same."""
    pc = model["people_count"]
    follow_rows = {d["item"] for d in model["due"] if d["kind"] == "nudge"
                   or (d.get("step") or "").startswith("Follow up")}
    follow_people = {p["id"] for p in model["people"] if p["group"] == "follow"}
    assert follow_people == follow_rows and pc["follow"] == len(follow_people), (follow_people, follow_rows)
    reply_rows = {d["item"] for d in model["due"] if d["kind"] == "reply"}
    replies = {p["id"] for p in model["people"] if (p["owed"] or {}).get("reply")}
    assert replies == reply_rows and pc["replies"] == len(replies)
    # Who needs you is one meaning everywhere (app_model.NEEDS_YOU): a reply, a thank-you or a
    # call owed; the follow-ups are counted apart (the maintainer, 2026-11-04).
    assert pc["need"] == sum(1 for p in model["people"] if p["group"] == "now")


def test_one_word_for_each_status_in_the_engine_and_on_the_page():
    """contacts 17, contacts_chat_2 10."""
    import re
    import app_model
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    block = js.split("const PERSON_STATUS = {", 1)[1].split("};", 1)[0]
    page = dict(re.findall(r'(\w+): \["([^"]+)"', block))
    for status, word in app_model.STATUS_WORDS.items():
        assert page.get(status) == word, (status, page.get(status), word)


def test_a_first_note_that_breaks_the_persons_rules_is_not_ready(model):
    """contacts 5 and 34, contacts_chat_2 19 and 20."""
    zoe = next(x for x in model["messages"] if x["contact"] == "rook_health_quarry")
    rules = {b["rule"] for b in zoe["blocked"]}
    assert "asks_for_the_job" in rules and "too_long" in rules, zoe["blocked"]
    assert zoe.get("wave") is None, "a note that breaks a rule is never one of a wave to send"


def test_replies_come_first_in_messages_and_a_reply_is_never_told_to_read_a_profile(model):
    """contacts 35 and 37, contacts_chat_2 18."""
    types = [x["type"] for x in model["messages"] if x["contact"]]
    assert types == sorted(types, key=lambda t: {"reply": 0, "thank_you": 0, "follow_up": 2}.get(t, 3))
    for x in model["messages"]:
        if x["type"] != "first_note":
            assert x["hold"] is None and x["paste"] is None, x


def test_two_people_with_one_first_name_and_no_employer_are_told_apart(book, model):
    """contacts 28, contacts_chat_2 12."""
    zos = [p for p in model["people"] + _whole(book, model) if p["id"].startswith("zo_")]
    assert {p.get("initial") for p in zos} == {"R", "S"}
    assert {p.get("title") for p in zos} >= {"Recruiter (UK)", "Talent Partner"}


def _whole(book, model):
    """The light records the page's database holds for everyone past the first screen."""
    path = os.path.join(book.root, "view")
    if not os.path.isdir(path):
        book.run(APP, "view", path, "--now", NOW)
    out = []
    for dp, _dn, fns in os.walk(path):
        for fn in sorted(fns):
            if fn.startswith("list@people@"):
                with open(os.path.join(dp, fn), encoding="utf-8") as fh:
                    out += json.load(fh).get("items") or []
    return out


# ------------------------------------------------------------------ the page renders that answer

@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


@pytest.fixture(scope="module")
def page(book):
    import app_page
    out = os.path.join(book.root, "page.artifact.html")
    book.run(APP, "page", "--now", NOW, "--out", out)
    path = os.path.join(book.root, "page.html")
    with open(out, encoding="utf-8") as fh, open(path, "w", encoding="utf-8") as w:
        w.write(app_page.standalone(fh.read()))
    return path


CLOCK = "2026-10-25T18:30:00Z"


def _row(text, who):
    """One person's row in the Contacts text: from their name to the next "More"."""
    return text.split(who, 1)[1].split("More", 1)[0] if who in text else ""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_contacts_shows_each_person_as_the_engine_says(run, page, model, vp):
    """contacts 6, 7, 9, 10, 12, 13, 14, 15, 16, 19, 20, 21, 23, 28, 45, 46;
    contacts_chat_2 2, 3, 4, 6, 7, 8, 11, 12, 15, 16."""
    got = run("engine", html=page, viewport=vp, clock=CLOCK, steps=[
        {"hash": "contacts"},
        {"hash": "contacts", "open": "fold:contacts"},
        {"hash": "contacts", "eval": "[...document.querySelectorAll('#main .btn.primary')].map((b) => b.closest('[data-item]') && b.closest('[data-item]').dataset.item)"}])
    assert not got["errors"], got["errors"]
    top, all_ = got["after"][0]["text"], got["after"][1]["text"]
    pc = model["people_count"]
    head = "\n".join(top.split("\n")[:6])
    # One short line: what is written to send, and who needs you (2026-11-04); the follow-ups
    # and replies among them are on their cards.
    # "To send" is the engine's one count (to_send), To do's the same: a note waiting for their
    # profile is drafted but not ready, so not counted (2026-11-07).
    assert f"{model['to_send']['n']} to send · {pc['need']} need you" in head, head
    held = [x for x in model["messages"] if x.get("hold")]
    assert held and model["to_send"]["n"] == pc["drafted"] - len(held), (model["to_send"], pc, held)
    assert "waiting to hear back" not in top
    # Past the limit: they need nothing from the person, so behind the fold (the maintainer,
    # 2026-11-04); their row says to leave it, with Close, never a follow-up of any kind.
    assert "Harrow Freight" not in top and "Lark Retail" not in top, top
    juno = _row(all_, "Juno at Harrow Freight")
    assert "Close" in juno and "No reply to 2 messages: leave it unless they write back." in juno, juno
    for word in ("Draft the follow-up", "Follow up anyway", "See the draft", "Let it go"):
        assert word not in juno, (word, juno)
    # Held by the person's rules: behind the fold, saying why, with nothing to press.
    assert "Rook Betting" not in top
    tam = _row(all_, "Tamsin at Rook Betting")
    assert "Nothing to send: Rook Betting is an employer you turned down." in tam, tam
    assert "Draft" not in tam
    rhian = _row(all_, "Rhian at Moss Foods")
    assert "Your connection request has not been accepted yet." in rhian and "Draft" not in rhian, rhian
    # A booked call stays booked; one gone by asks how it went.
    riley = _row(top, "Riley at Vale Health")
    assert "Call booked" in riley and "Prepare for the call" in riley and "Replied" not in riley, riley
    robin = _row(top, "Robin at Wren Logistics")
    assert "How did it go?" in robin and "Draft the thank-you" in robin, robin
    # The step the person set is the button's own; no note to Claude, id or "None".
    taylor = _row(top, "Taylor at Vale Freight")
    assert "Next: Send the referral ask for the Planning Analyst role" in taylor and "Draft it" in taylor, taylor
    assert "Draft a reply" not in _row(all_, "Thad at Harrow Foods")
    for leak in ("Next: None", "4481616253", "batch 6", "waiting for him", "Next: taylor", "Next: juno"):
        assert leak not in all_, leak
    # Two people with one first name and no employer, told apart.
    assert "Zo R." in all_ and "Zo S." in all_ and "Recruiter (UK)" in all_
    # The one filled button on the screen is on the most overdue reply.
    firsts = [x for x in got["after"][2]["eval"] if x]
    assert firsts and model["people"][0]["id"] == firsts[0], (firsts[:3], model["people"][0]["id"])


def test_a_filter_shows_its_people_and_a_search_is_not_a_filter(run, page, model):
    """contacts 4, 29 and 30, contacts_chat_2 14."""
    # The filter's choices are the few that matter since 2026-11-05 ("less info overload"):
    # Waiting on them shows everyone a message has gone to and who has not answered.
    follow = [p for p in model["people"] if p["group"] == "waiting"]
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, steps=[
        {"hash": "contacts", "open": "filter:contacts", "read": "dialog"},
        {"click": "Waiting on them"},
        {"hash": "contacts", "eval": "document.querySelectorAll('#main [data-list=contacts] li.person').length"}])
    assert not got["errors"], got["errors"]
    assert got["after"][2]["eval"] >= len(follow) > 0, got["after"][2]["text"][:400]
    assert "nothing to do for them now" not in got["after"][2]["text"]


def test_messages_never_offer_a_draft_that_breaks_a_rule(run, page):
    """contacts 5, 34 and 37, contacts_chat_2 19, 20 and 22. The note is on Zoe's own card in
    Contacts (one page since 2026-11-04)."""
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "read": "#main [data-item=\"rook_health_quarry\"]"}])
    assert not got["errors"], got["errors"]
    zoe = got["after"][0]["text"]
    # Claude fixes it by itself, with no tap (2026-11-04): never offered as ready, never a Fix it.
    assert "It fixes this by itself: it asks them for a job." in zoe, zoe
    assert "Fix it" not in zoe and "I sent it" not in zoe and "Copy" not in zoe, zoe
    assert "Due " not in zoe


def test_their_reply_logged_turns_the_row_at_once_and_let_it_go_is_in_the_bin(run, page):
    """contacts 19, contacts_chat_2 5."""
    # Pasted in the box under him (Contacts, 2026-11-04), never a sheet: his reply is drafted.
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, steps=[
        {"hash": "contacts", "click": "They replied: paste what Corwin sent"},
        {"fillMain": {"Paste what Corwin sent": "Thanks Morgan, happy to talk next week."}, "then": "Draft my reply to Corwin"},
        {"hash": "contacts", "read": "#main [data-item=\"teal_retail_nettle\"]"},
        {"hash": "contacts", "open": "fold:contacts", "click": "Not Zo R.?"},
        {"click": "Let it go: they have not replied"},
        {"hash": "contacts", "read": "#main [data-item=\"zo_rendle\"]"}])
    assert not got["errors"], got["errors"]
    corwin = got["after"][2]["text"]
    # His turn became yours at once, and his reply is asked for: the state says so, never
    # "Replied: your turn" over a reply Claude has in hand (the review, 2026-11-05).
    assert "Reply asked for" in corwin and "Replied: your turn" not in corwin and "Waiting for Claude" in corwin, corwin
    assert "Draft the follow-up" not in corwin and "They replied\n" not in corwin, corwin
    acts = {a["action"] for a in got["actions"]}
    assert {"msg.received", "person.status"} <= acts, acts


def test_a_persons_page_has_their_link_and_a_late_step_reads_late(run, page):
    """contacts 18, 24, 42 and 44, contacts_chat_2 9."""
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "open": "pname:row:kestrel_bank_lowther", "read": "dialog"},
        {"hash": "contacts", "more": "kestrel_bank_lowther", "read": "#main [data-item=\"kestrel_bank_lowther\"]"}])
    assert not got["errors"], got["errors"]
    page_text = got["after"][0]["dialog"]
    assert "Open the link" in page_text and "4481616253" not in page_text and "http" not in page_text
    assert "Don't contact again" in page_text
    more = got["after"][1]["text"]
    assert "conversation" not in more.split("More", 1)[-1].lower(), "the name opens their page"


def test_a_draft_a_reply_on_a_kept_reply_never_asks_for_their_words(run, page):
    """contacts 1 and 43, contacts_chat_2 1 and 2 (already fixed on 3 November: the engine
    writes the thread); re-run on the exact steps."""
    buttons = "[...document.querySelectorAll('#main [data-item=\"kestrel_bank_lowther\"] .card-actions > .btn')].map((b) => b.textContent.trim())"
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "read": "#main [data-item=\"kestrel_bank_lowther\"]", "eval": buttons},
        # The box under her, as every reply is drafted on Contacts (2026-11-04).
        {"hash": "contacts", "click": "Draft a reply to Shirin", "read": "#main [data-item=\"kestrel_bank_lowther\"]"}])
    assert not got["errors"], got["errors"]
    face, box = got["after"][0]["eval"], got["after"][1]["text"]
    assert "They replied" not in face, face
    assert "already kept" in box and "Paste what Shirin sent" not in box, box


def fixed(model, cid="kestrel_foods_thorne"):
    """A seed where Claude has already made its one fix of a draft that only reads better
    changed: the draft is then offered as it is (app_model.FIX_TRIES)."""
    m = next(x for x in model["messages"] if x["contact"] == cid)
    if not m.get("fix"):
        return {}
    return {"work/" + m["fix"]["work"]: {"kind": "tweak", "title": "Fix the message", "status": "done", "to": "either",
                                         "args": {"v": 1, "target": {"id": m["id"], "output": "message", "contact": cid}, "auto": True},
                                         "asked_at": "2026-10-25T17:00:00Z", "finished_at": "2026-10-25T17:01:00Z"}}


def test_small_things_each_say_what_they_are(run, page, model):
    """contacts 24, 25, 26, 27, 31, 36, 37, 38, 39, 40, 41, 42, 44, 47, 48, 51;
    contacts_chat_2 22."""
    aria = ("[...document.querySelectorAll('#main [aria-label]')].map((e) => e.getAttribute('aria-label'))"
            ".filter((a) => / at\\??$| at:|^More: \\w+ at$/.test(a))")
    reach = ("(() => { const a = document.querySelector('[data-k=\"pname:row:zo_rendle\"]') || document.querySelector('a.name-link');"
             " const r = a.getBoundingClientRect(); const s = getComputedStyle(a, '::after');"
             " return r.width + Math.max(0, -parseFloat(s.left || 0)) + Math.max(0, -parseFloat(s.right || 0)); })()")
    close = "(document.querySelectorAll('dialog[open]').forEach((d) => d.close()), 1)"
    steps = {
        "aria": {"hash": "contacts", "open": "fold:contacts", "eval": aria},
        "reach": {"hash": "contacts", "eval": reach},
        "ines": {"hash": "contacts", "more": "lark_health_upcott", "read": "#main [data-item=\"lark_health_upcott\"]"},
        "taylor": {"hash": "contacts", "more": "vale_freight_pellow", "read": "#main [data-item=\"vale_freight_pellow\"]"},
        "ash": {"hash": "contacts", "more": "thornbury_bank_brook", "read": "#main [data-item=\"thornbury_bank_brook\"]"},
        "ana": {"hash": "contacts", "read": "#main [data-item=\"quay_retail_kellam\"]"},
        "idris": {"hash": "contacts", "more": "moss_energy_orme", "read": "#main [data-item=\"moss_energy_orme\"]"},
        "idris_page": {"hash": "contacts", "open": "pname:row:moss_energy_orme", "read": "dialog"},
        "close1": {"eval": close},
        "shirin_page": {"hash": "contacts", "open": "pname:row:kestrel_bank_lowther", "read": "dialog"},
        "stop": {"click": "Don't contact again", "eval": "[...document.querySelectorAll('dialog[open]')].map((d) => d.textContent).join(' | ')"},
        "close2": {"eval": close},
        # Each message is on its person's card in Contacts (2026-11-04); the buttons counted are
        # the ones on its face, More's left folded.
        "rafe": {"hash": "contacts", "read": "#main [data-item=\"kestrel_foods_thorne\"]",
                 "count": "#main [data-item=\"kestrel_foods_thorne\"] button:not(details.more:not([open]) button)"},
        "kit": {"hash": "contacts", "read": "#main [data-item=\"sedge_foods_glen\"]"},
        # The pencil in the bubble's corner (2026-11-04): the words changed in place, or Claude
        # asked to change them.
        "panel": {"hash": "contacts", "open": "pen:msg-kestrel_foods_thorne", "eval": "(document.querySelector('[data-item=\"kestrel_foods_thorne\"] .pen-tell') || {}).innerText || ''"},
        "close3": {"open": "pen:msg-kestrel_foods_thorne"},
        # What the live region says is set a moment after the tap (announce): waited for, never
        # read after a set time (CI, 2026-11-04: read before it was said).
        "copy": {"hash": "contacts", "click": "Copy message to Rafe", "ready": "/copied/.test(document.getElementById('live').textContent)",
                 "eval": "document.getElementById('live').textContent"},
        "toast": {"hash": "contacts", "click": "Draft it: Taylor at Vale Freight", "ready": "/^Asked/.test(document.getElementById('live').textContent)",
                  "eval": "document.getElementById('live').textContent"},
    }
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=fixed(model), steps=list(steps.values()))
    assert not got["errors"], got["errors"]
    a = dict(zip(steps, got["after"]))
    assert a["aria"]["eval"] == [], a["aria"]["eval"]                          # 27, 48
    assert a["reach"]["eval"] >= 43.5, a["reach"]["eval"]                        # 47
    ines = a["ines"]["text"]                                                    # 25, 26
    assert "Did it go?" in ines and "They replied" not in ines and "Send now" not in ines, ines
    taylor = a["taylor"]["text"]                                                # 38
    assert "Draft it" in taylor and "Done" not in taylor.split("More", 1)[-1], taylor
    assert "your interview for Risk Analyst" in a["ash"]["text"], a["ash"]["text"]    # 51
    assert "You asked for a referral" in a["ana"]["text"], a["ana"]["text"]           # 41
    assert "Read your call prep" in a["idris"]["text"], a["idris"]["text"]           # 44
    assert "Your call prep" in a["idris_page"]["dialog"], a["idris_page"]["dialog"]
    assert "was due" in a["shirin_page"]["dialog"], a["shirin_page"]["dialog"]        # 24
    assert "Don't contact Shirin" in a["stop"]["eval"], a["stop"]["eval"]              # 42
    rafe = a["rafe"]["text"]                                                    # 37
    # Ready, never "Overdue", for a day he set himself (the UX review of 2026-11-10, U-6).
    assert "Ready to send" in rafe and "Overdue" not in rafe and "Due " not in rafe and "Paste" not in rafe, rafe
    assert a["rafe"]["count"] <= 8, a["rafe"]["count"]                          # chat_2 22
    # A note waiting for their profile says so once, with Paste and its gauge beside it: one
    # note's rewrite in minutes (the engine's), never "a lot of your allowance", a networking
    # run's gauge (the maintainer, 2026-11-07).
    kit = a["kit"]["text"]                                                      # 36
    assert kit.count("Waiting for their profile") == 1 and "Paste Kit's profile" in kit, kit
    assert re.search(r"\b\d+ min\b", kit) and "a lot of your allowance" not in kit, kit
    panel = a["panel"]["eval"]                                                  # 31
    assert "Shorter" in panel and "Warmer" in panel and "More formal" in panel and "InMail" not in panel, panel
    assert "Message to Rafe copied." in a["copy"]["eval"], a["copy"]["eval"]    # 40
    said = a["toast"]["eval"]                                                  # 39
    assert said.startswith("Asked: ") and len(said) <= 80, said


def test_a_messages_own_change_never_says_it_makes_a_pdf(run, page, model):
    """contacts 32, through the pencil since 2026-11-04."""
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=fixed(model), steps=[
        {"hash": "contacts", "open": "pen:msg-kestrel_foods_thorne"},
        {"eval": "(() => { document.querySelector('[data-k=\"penask:msg-kestrel_foods_thorne\"]').value = 'Shorter, please'; return 1; })()"},
        {"open": "pengo:msg-kestrel_foods_thorne"}])
    assert not got["errors"], got["errors"]
    tweak = [w for w in got["work"] if w.get("kind") == "tweak"]
    assert tweak, got["work"]
    assert not any("PDF" in str(s.get("name")) for w in tweak for s in w.get("stages") or []), tweak


def test_contacts_says_claude_is_finding_people_and_not_an_unrelated_chat(run, page):
    """contacts 52, contacts_chat_2 17."""
    seed = {"work/network~x": {"kind": "network", "title": "Find people at Teal Retail", "status": "running",
                               "asked_at": "2026-10-25T18:20:00Z", "claimed_at": "2026-10-25T18:21:00Z",
                               "stages": [{"name": "Finding people", "est_s": 900}], "stage": 0,
                               "stage_at": "2026-10-25T18:21:00Z", "_v": 2},
            "work/talk~y": {"kind": "talk", "title": "Answer: scratch the job drafts", "status": "queued",
                            "asked_at": "2026-10-25T16:00:00Z", "_v": 1}}
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        {"hash": "contacts", "read": "#main .sec-head"}])
    assert not got["errors"], got["errors"]
    # The header's own Find people says it is going; no line of its own for Claude's work
    # (2026-11-04), and never an unrelated chat.
    said = got["after"][0]["text"]
    assert "Finding people" in said and "scratch the job drafts" not in said, said


def test_settings_says_ready_once(run, model, tmp_path):
    """contacts 50."""
    import app_page
    m = json.loads(json.dumps(model))
    m.setdefault("linkedin", {})["reading"] = {"ok": True, "page_reads": True, "setting": "browser"}
    path = os.path.join(str(tmp_path), "ready.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(m)))
    got = run("engine", html=path, viewport=WIDE, clock=CLOCK, steps=[{"hash": "settings"}])
    assert not got["errors"], got["errors"]
    assert "Open this page in the Claude app on your computer to check it" not in got["after"][0]["text"]


# The box on screen and the newest message on screen just above it, not behind it, measured as
# drawn (__drawnRect): the page is zoomed on a phone, and Safari's engine (Playwright 1.56's)
# measured the scrolled box well below the screen while it was on it (CI, 2026-11-04). The box
# sticks to the foot of the screen, so it alone says nothing about where the conversation stands.
PLACED = ("(() => { const f = document.querySelector('.talk-form'), l = document.querySelector('.talk-list');"
          " const m = l && l.lastElementChild; if (!f || !m) return false; const b = f.__drawnRect(), r = m.__drawnRect();"
          " return b.top >= 0 && b.bottom <= window.innerHeight + 2 && r.bottom > 0 && r.bottom <= b.top + 2; })()")


def test_chat_opens_on_its_newest_answers_unanswered_ones_and_dots_a_new_one(run, page):
    """contacts_chat_2 26, 27 and 29."""
    msgs = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Earlier", "created_at": "2026-10-20T09:00:00Z", "_v": 1}}
    for n in range(14):
        msgs[f"talk/cloud-1/messages/m{n:02d}"] = {"from": "you" if n % 2 == 0 else "claude",
                                                   "text": f"Line {n} " + "of a long conversation " * 6,
                                                   "at": f"2026-10-2{n // 7}T{9 + n % 7:02d}:00:00Z", "_v": 1}
    msgs["talk/cloud-1/messages/m20"] = {"from": "you", "text": "Can you tidy the old drafts?", "at": "2026-10-23T09:00:00Z", "_v": 1}
    msgs["talk/cloud-1/messages/m21"] = {"from": "you", "text": "Can you tidy the old drafts please?", "at": "2026-10-24T09:00:00Z", "_v": 1}
    msgs["talk/cloud-1/messages/m22"] = {"from": "claude", "text": "Done: the old drafts are set aside.", "at": "2026-10-25T18:10:00Z", "_v": 1}
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=msgs, steps=[
        {"hash": "contacts", "eval": "!!document.querySelector('.tab .navdot')"},
        # Waited for, with a time limit, never read after a set time.
        {"hash": "chat", "ready": PLACED, "eval": PLACED},
        {"hash": "chat", "read": "#main .talk-list"},
        {"hash": "contacts", "eval": "!!document.querySelector('.tab .navdot')"}])
    assert not got["errors"], got["errors"]
    a = got["after"]
    assert a[0]["eval"] is True, "a new answer not seen yet dots the Chat tab"
    assert a[1]["eval"] is True, "Chat opens on its newest message and the box"
    assert a[2]["text"].count("No answer to this one") == 1, a[2]["text"]
    assert a[3]["eval"] is False, "seen, the dot goes"


# ------------------------------------------------------------------ at the audit's scale

@pytest.fixture(scope="module")
def crowd(tmp_path_factory):
    """726 people, 142 owed a reply, 144 follow-ups due, 142 at their limit, and nine replies
    drafted: the size of the audited search, invented."""
    b = Book(str(tmp_path_factory.mktemp("crowd")), crowd=700)
    for i in range(0, 45, 5):
        path = os.path.join(b.state, "documents", "network", f"crowd_{i}", "draft.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("Thanks, that would be great. Does Thursday at ten work for a call?\n")
    return b


def test_at_scale_to_do_and_contacts_count_who_needs_you_the_same(crowd):
    """To do said "1284 more people who need you are in Contacts" counting every row it left
    off, a follow-up among them, while Contacts said "1279 need you" counting replies alone
    (the review, 2026-11-05): both count who needs you one way (app_model.NEEDS_YOU), so the
    people To do lists and the ones it says are in Contacts add up to Contacts' number, and the
    follow-ups it left off are said apart, as Contacts says them."""
    import re
    m = crowd.model()
    pc = m["people_count"]
    need = {p["id"] for p in m["people"] if p["group"] == "now"}
    could = {p["id"] for p in m["people"] if p["group"] == "follow"}
    assert pc["need"] == len(need) >= 140 and len(could) >= 100, (pc, len(need), len(could))
    hidden = next(d for d in m["due"] if d["kind"] == "hidden")
    said = re.search(r"(\d+) more (?:person who needs|people who need) you", hidden["title"])
    ups = re.search(r"(\d+) (?:more )?follow-ups? you could send", hidden["title"])
    assert said and ups, hidden["title"]
    # On To do: a row of their own, or their message on its "Messages to send" card.
    listed = {p["id"] for p in m["people"] for d in m["due"]
              if d["kind"] not in ("hidden", "withdraw") and (d.get("contact") == p["id"] or d.get("item") == p["id"])}
    listed |= {x["contact"] for x in m["messages"] if x["id"] in m["to_send"]["ids"]}
    assert int(said.group(1)) == len(need - listed), (hidden["title"], len(need), len(need & listed))
    assert int(ups.group(1)) == len(could - listed), (hidden["title"], len(could), len(could & listed))


def test_at_scale_the_counts_are_the_engines_and_a_message_past_five_opens(run, crowd):
    """contacts 3 and 16, contacts_chat_2 14, 15 and 30."""
    import app_page
    m = crowd.model()
    pc = m["people_count"]
    owed = sum(1 for p in m["people"] if (p["owed"] or {}).get("kind") in ("reply", "draft")
               and p["group"] == "now")
    assert pc["need"] >= owed >= 140, (pc, owed)
    out = os.path.join(crowd.root, "page.artifact.html")
    crowd.run(APP, "page", "--now", NOW, "--out", out)
    path = os.path.join(crowd.root, "page.html")
    with open(out, encoding="utf-8") as fh, open(path, "w", encoding="utf-8") as w:
        w.write(app_page.standalone(fh.read()))
    msgs = [x for x in m["messages"] if x["type"] == "reply"]
    # A message's old address opens its person's card in Contacts (one page since 2026-11-04).
    last, whose = msgs[-1]["id"], msgs[-1]["contact"]
    got = run("engine", html=path, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts"},
        {"hash": "drafts-messages/" + last, "until": "!!document.querySelector('[data-item=\"%s\"] details.pdraft[open]')" % whose,
         "eval": "!!document.querySelector('[data-item=\"%s\"] details.pdraft[open]')" % whose}])
    assert not got["errors"], got["errors"]
    head = "\n".join(got["after"][0]["text"].split("\n")[:6])
    assert f"{pc['need']} need you" in head, head
    assert got["after"][1]["eval"] is True, "a draft past the first five is shown when opened"
    light = [x for x in _whole(crowd, m) if x["id"] not in {p["id"] for p in m["people"]}]
    assert light, "the crowd reaches past the page's own list"
    who = light[0]
    # The page's database holds the rest of the book (app.py view writes it): seeded as it is.
    seed = {}
    for dp, _dn, fns in os.walk(os.path.join(crowd.root, "view")):
        for fn in fns:
            if fn.startswith("list@people@"):
                with open(os.path.join(dp, fn), encoding="utf-8") as fh:
                    seed["screen/" + fn[:-5].replace("@", "~")] = json.load(fh)
    got = run("talk", html=path, seed=seed, question="Is " + who["first_name"] + " in my contacts?",
              sample={"toolCalls": [{"name": "find", "input": {"text": who["employer"]}}], "reply": "Yes."})
    found = dict(got["tools"]).get("find", "")
    assert who["employer"] in found, (who, found[:300])


# ------------------------------------------------------------------ the brief and the engine's words

def test_the_brief_links_a_line_to_the_person_it_names_and_says_drafted_only_when_it_is(book):
    """contacts 8."""
    code = ("import sys, json; sys.path[:0] = [%r, %r]; import app_model, brief, datetime as dt\n"
            "ctx = app_model.Ctx(dt.date(2026, 10, 25), dt.datetime(2026, 10, 25, 18))\n"
            "print(json.dumps([app_model.brief_link(ctx, 'Send your reply to Rafe Thorne (Kestrel Foodstuffs): it is drafted for you.'),"
            " brief._on_page({'contact_id': 'kestrel_foods_thorne'}), brief._on_page({'contact_id': 'kestrel_bank_lowther'})]))"
            % (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")))
    got = json.loads(book.run("-c", code).strip().splitlines()[-1])
    assert got[0]["item"] == "kestrel_foods_thorne", got[0]
    assert got[1] is True and got[2] is False


def test_the_linkedin_download_card_names_no_tool(book):
    """contacts 49."""
    path = os.path.join(book.state, "documents", "network", "linkedin_export.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"taken_on": "2026-10-01", "changed": [
            "Since your last download (2026-09-15): 3 new connections, 1 accepted your request, "
            "0 replied, and 4 requests sent over 21 days ago still wait (export.py pending lists them)."]}, fh)
    try:
        blob = json.dumps(book.model()["linkedin"])
    finally:
        os.remove(path)
    assert "still wait" in blob and ".py" not in blob, blob[:400]


def test_a_length_suggestion_counts_only_notes_written_since_the_persons_own_rule(tmp_path):
    """contacts 33, contacts_chat_2 23: 50 notes from before the person's recipe argued
    against every note written to it."""
    b = Book(str(tmp_path))
    contacts = app_state._csv_rows(os.path.join(b.state, "network_contacts.csv"))
    threads = app_state._csv_rows(os.path.join(b.state, "network_threads.csv"))
    for i in range(50):
        cid = f"old_{i}"
        short_note = i % 2 == 0
        text = ("Hi, how is your team set up?" if short_note else
                "Hi, I build demand forecasts in Manchester for retailers and freight firms, "
                "with weekly models in Python and SQL that planners use. I'd love to hear how "
                "your planning team is set up and what it works on this year, if you have time.")
        contacts.append(person(cid, f"Old Note{i}", f"Firm {i}", "gone_cold"))
        threads.append(out(cid, f"2026-08-{1 + i % 28:02d}", text))
        if short_note:
            threads.append(inn(cid, f"2026-08-{2 + i % 27:02d}", "Thanks, happy to talk."))
    contacts.append(person("teal_bank_orme", "Quill Orme", "Teal Bank", "not_contacted"))
    _save(os.path.join(b.state, "network_contacts.csv"), contacts, CONTACT_COLUMNS)
    _save(os.path.join(b.state, "network_threads.csv"), threads, THREAD_COLUMNS)
    note = os.path.join(b.state, "documents", "network", "teal_bank_orme", "draft.md")
    os.makedirs(os.path.dirname(note), exist_ok=True)
    with open(note, "w", encoding="utf-8") as fh:
        fh.write("Hi Quill, hope you're well. I build demand forecasts in Manchester for retailers "
                 "and freight firms, which I imagine is similar to some of the planning work at Teal "
                 "Bank. I'd love to hear what you're working on this year.\n")
    def suggest():
        msg = next(x for x in b.model()["messages"] if x["contact"] == "teal_bank_orme")
        return msg.get("suggest")
    assert suggest() is not None, "the old notes alone do make the suggestion"
    with open(os.path.join(b.profile, "learned.json"), "w", encoding="utf-8") as fh:
        json.dump({"entries": [{"date": "2026-10-22", "area": "messages", "status": "active",
                                "said": "remember this one for future connections",
                                "rule": "Write first notes to the recipe the person approved"}]}, fh)
    assert suggest() is None, "notes from before the person's own rule say nothing about notes written to it"


def test_a_reply_logged_with_no_words_still_reopens_a_closed_thread():
    """Only a reaction (an emoji, "Liked your message") leaves a closed thread closed: a reply
    logged with no words kept was read as a reaction, so a closed thread that got one stayed
    closed (a person's own test, the 4.9.0 rehearsal, 2026-11-04)."""
    import schema
    import state
    row = {c: "" for c in schema.CONTACT_COLUMNS}
    row.update(name="Ada Example", company="Quay Bank", tier="2", channel="connection",
               status="closed")
    row["contact_id"] = state.contact_id(row["name"], row["company"])

    def said(day, way, text=""):
        r = {c: "" for c in schema.THREAD_COLUMNS}
        r.update(contact_id=row["contact_id"], date=day, direction=way, channel="connection",
                 full_text=text)
        return r
    out = said("2026-10-26T07:00", "out")
    assert [p["reason"] for p in state.reconcile([row], [out, said("2026-10-27T15:00", "in")])] \
        == ["reopened"]
    assert state.reconcile([row], [out, said("2026-10-27T15:00", "in", "\U0001F44D")]) == []
