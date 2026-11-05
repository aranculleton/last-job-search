"""Contacts is one page: each person's card carries the message drafted to them, and a reply
they sent is pasted right under them.

The maintainer, 2026-11-04 (note 10): "Contacts becomes one page. No separate People and
Messages tabs. Each person's card shows their latest drafted message under their name ...
until I tap that I sent it ... People with a message already drafted sort to the top by
default. Fewer, smarter buttons: the main one opens a box under the person where I paste what
they sent; it shows Claude working, and Claude's reply appears under that same person, ready to
copy and send." And: someone talking to many people pastes ten replies one after another, fast;
each card shows its own state, from the work items, across live updates and reloads.

Every person and employer here is invented (the book of
`test_contacts_show_only_what_the_persons_rules_allow`, with a crowd of invented people).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_contacts_show_only_what_the_persons_rules_allow import APP, Book, NOW, PHONE, WIDE, fixed  # noqa: E402

CLOCK = "2026-10-25T18:30:00Z"
SHOTS = os.environ.get("LJS_SHOTS", "")


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    return Book(str(tmp_path_factory.mktemp("contacts1")), crowd=50)


@pytest.fixture(scope="module")
def model(book):
    return book.model()


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


def _drafted(model):
    return {m["contact"] for m in model["messages"] if m.get("contact")}


# ------------------------------------------------------------------ the engine's order

def test_people_with_a_message_drafted_come_first(model):
    """Drafted first, then who needs you, in the engine's own order: the page never sorts them
    again from dates of its own."""
    drafted = _drafted(model)
    ids = [p["id"] for p in model["people"]]
    have = [i for i, cid in enumerate(ids) if cid in drafted]
    assert have, "the book has drafted messages"
    # Every drafted person before anyone without a message.
    first_without = next(i for i, cid in enumerate(ids) if cid not in drafted)
    assert max(have) < first_without, ([ids[i] for i in have], ids[:len(have) + 3])
    # A first note drafted to someone not yet written to is up front too, not behind the
    # people who need you.
    assert model["people_count"]["drafted"] == len(have), model["people_count"]


# ------------------------------------------------------------------ the page

def _card(cid):
    return '#main [data-item="%s"]' % cid


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_contacts_is_one_page_and_each_card_carries_its_draft(run, page, model, vp):
    """No People and Messages switch; Rafe's reply is on his card, open, with Copy and I sent
    it; rare things are under More; the old Messages address opens Contacts on his card."""
    rafe = "kestrel_foods_thorne"
    got = run("engine", html=page, viewport=vp, clock=CLOCK, seed=fixed(model), shots="contacts-" + ("phone" if vp is PHONE else "wide") if SHOTS else None, steps=[
        {"hash": "contacts", "shot": "top"},
        {"hash": "contacts", "read": _card(rafe),
         "eval": "(() => { const c = document.querySelector('%s'); const d = c.querySelector('details.pdraft');"
                 " return {open: !!(d && d.open), face: [...c.querySelectorAll('.card-actions > .btn, .card-actions > a')].map((b) => b.textContent.trim()),"
                 " more: [...c.querySelectorAll('.more-panel:not(.info-panel) button, .more-panel:not(.info-panel) a')].map((b) => b.textContent.trim()),"
                 " first: document.querySelector('#main ul.people > li').dataset.item, pen: !!c.querySelector('.sendbox [data-k=\"pen:msg-kestrel_foods_thorne\"]'),"
                 " tabs: !!document.querySelector('[data-k^=\"contsw\"]') }; })()" % _card(rafe)},
        {"hash": "drafts-messages/msg-" + rafe, "until": "location.hash === '#contacts/%s'" % rafe},
        {"hash": "contacts", "click": "I sent it: the message to Rafe", "read": _card(rafe)},
        # Sent, he needs nothing from you now: below the fold with the others who wait.
        {"open": "fold:contacts", "read": _card(rafe), "shot": "sent"},
    ])
    assert not got["errors"], got["errors"]
    top = got["after"][0]["text"]
    assert "People" not in top.split("\n")[:8] and "Messages" not in top, top[:600]
    card, probe = got["after"][1]["text"], got["after"][1]["eval"]
    assert probe["open"] and not probe["tabs"], probe
    assert "Your reply" in card and "Thanks Rafe." in card and "Copy" in card and "I sent it" in card, card
    # The pencil is on the draft itself, beside Copy; More holds no editing (2026-11-04).
    assert probe["pen"], probe
    assert not any(t.startswith(("Edit", "I sent these words")) for t in probe["more"]), probe["more"]
    # People with a message drafted come first, as the engine orders them.
    assert probe["first"] in _drafted(model), probe["first"]
    # The old address of a message lands on its person in Contacts.
    assert got["after"][2]["hash"] == "#contacts/" + rafe, got["after"][2]["hash"]
    # I sent it: the draft goes from the card at once; he waits for a reply.
    assert got["after"][3]["text"] == "", "a card finished leaves the list at once"
    sent = got["after"][4]["text"]
    assert "Thanks Rafe." not in sent and "Message sent" in sent and "Nothing to do until they write back" in sent, sent
    assert any(a["action"] == "msg.sent" and a["item"] == "msg-" + rafe for a in got["actions"]), got["actions"]


def _waiting(model, n=10):
    out = [p for p in model["people"] if p["id"].startswith("crowd_") and p["status"] == "awaiting_reply"
           and p["group"] in ("follow", "waiting")]
    assert len(out) >= n, [p["id"] for p in out]
    return out[:n]


def test_ten_replies_pasted_in_a_row_each_show_on_their_own_card(run, page, model):
    """Ten pastes in quick succession: none waits for the one before, each card says where its
    own reply stands (from the tap, then its work item, the same after a reload), and each
    reply Claude writes lands on its own card, ready to copy."""
    ten = _waiting(model)
    quick = []
    for p in ten:
        at, first = _card(p["id"]), p["first_name"]
        quick += [{"within": at, "click": "They replied: paste what %s sent" % first},
                  {"within": at, "fill": {"Paste what %s sent" % first: "Thanks %s here, happy to talk next week." % first}},
                  {"within": at, "click": "Draft my reply to %s" % first}]
    states = ("(() => { const out = {}; for (const c of document.querySelectorAll('#main ul.people > li[data-item]')) {"
              " const g = c.querySelector('.going'); if (g) out[c.dataset.item] = {words: g.querySelector('.going-word').textContent,"
              " spin: !!g.querySelector('.spin')}; } return out; })()")
    boxes = "document.querySelectorAll('#main .reply-box').length"
    # Claude, played: every tap applied, the first reply running, the rest waiting their turn.
    work = {}
    for i, p in enumerate(ten):
        work["work/reply~" + p["id"]] = {
            "kind": "reply", "title": "Reply to " + p["first_name"], "to": "either", "args": {"contact": p["id"]},
            "asked_at": "2026-10-25T18:29:%02dZ" % i, "status": "running" if i == 0 else "queued",
            "stages": [{"name": "Reading what they said", "est_s": 30}, {"name": "Drafting your reply", "est_s": 60}],
            "stage": 1 if i == 0 else 0, "stage_at": "2026-10-25T18:29:30Z",
            **({"claimed_by": "cloud-1", "claimed_at": "2026-10-25T18:29:30Z", "lease_until": "2026-10-25T20:00:00Z"} if i == 0 else {})}
    # Three replies written: their work done and their drafts in the page's data.
    written = ten[:3]
    msgs = list(model["messages"]) + [{
        "id": "msg-" + p["id"], "contact": p["id"], "first_name": p["first_name"], "employer": p["employer"],
        "channel": "linkedin_message", "kind": "reply", "type": "reply", "subject": None,
        "body": "Thanks %s, next week works well for me." % p["first_name"],
        "text": "Thanks %s, next week works well for me." % p["first_name"], "warnings": [], "blocked": [],
        "count": {}, "rev": "r-" + p["id"]} for p in written]
    finished = {k: dict(v, status="done", finished_at="2026-10-25T18:31:00Z") for k, v in work.items()
                if any(k.endswith(p["id"]) for p in written)}
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, shots="contacts-ten" if SHOTS else None, steps=[
        {"hash": "contacts", "quick": quick, "eval": states},
        {"eval": boxes},
        {"receipts": True, "write": work, "eval": states, "shot": "working", "full": True},
        {"reload": True, "hash": "contacts", "eval": states},
        {"write": dict(finished, **{"view/messages": {"made_at": "2026-10-25T18:31:00Z", "data": msgs}}), "eval": states, "shot": "written", "full": True},
        {"hash": "contacts", "read": _card(written[0]["id"])},
        {"hash": "contacts", "read": _card(ten[5]["id"])},
    ])
    assert not got["errors"], got["errors"]
    ids = [p["id"] for p in ten]
    # Each paste is its own "They replied", with the words, and none was lost to the next.
    taps = [a for a in got["actions"] if a["action"] == "msg.received"]
    assert sorted(a["item"] for a in taps) == sorted(ids), [a["item"] for a in taps]
    assert all(a["value"].get("draft") is True and "happy to talk" in a["value"]["text"] for a in taps), taps
    # At once, before Claude: every card says its reply is waiting, and no box stays open.
    first = got["after"][0]["eval"]
    assert set(first) >= set(ids), first
    assert {first[c]["words"] for c in ids} <= {"Waiting for Claude", "Next", "Starting", "No answer yet"}, first
    assert got["after"][1]["eval"] == 0, "every box closed once its reply was asked for"
    # Claude working: the running one spins and says so; the others say their place.
    work_now = got["after"][2]["eval"]
    assert work_now[ids[0]] == {"words": "Claude is on it", "spin": True}, work_now[ids[0]]
    assert work_now[ids[1]]["words"] == "Next" and work_now[ids[2]]["words"] == "In line", (work_now[ids[1]], work_now[ids[2]])
    assert not any(work_now[c]["spin"] for c in ids[1:]), work_now
    # A reload keeps each card's own state: it is read from the work items, not this tab.
    assert got["after"][3]["eval"] == work_now, (got["after"][3]["eval"], work_now)
    # Three written: each on its own card, ready to copy; the rest still say where theirs is.
    later = got["after"][4]["eval"]
    assert not any(c in later for c in ids[:3]), later
    assert all(c in later for c in ids[3:]), later
    one = got["after"][5]["text"]
    assert "Your reply" in one and "next week works well for me" in one and "Copy" in one and "I sent it" in one, one
    # With the running one done, the next waits for Claude to look again: said, not guessed.
    assert "Waiting for Claude" in got["after"][6]["text"], got["after"][6]["text"]


def test_a_reply_kept_already_asks_only_what_to_say_back(run, page):
    """Rafe's reply is kept and drafted; Corwin's is pasted in the box under him, and a reply
    already in the log never asks for it again (contacts 1 and 43, now in the box)."""
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "click": "They replied: paste what Corwin sent", "read": _card("teal_retail_nettle"),
         "eval": "document.activeElement && document.activeElement.id"},
        {"hash": "contacts", "click": "Draft a reply to Shirin", "read": _card("kestrel_bank_lowther")},
    ])
    assert not got["errors"], got["errors"]
    corwin = got["after"][0]["text"]
    assert "Paste what Corwin sent" in corwin and "Draft my reply" in corwin, corwin
    assert got["after"][0]["eval"] == "rb-teal_retail_nettle", got["after"][0]["eval"]
    assert not got["after"][0]["dialog"], "the box is on the card, not a sheet"
    shirin = got["after"][1]["text"]
    assert "already kept" in shirin and "Paste what Shirin sent" not in shirin, shirin


# ------------------------------------------------------------------ the latest exchange

def test_the_engine_says_the_latest_exchange_and_how_it_began(model):
    """The card's line is the latest exchange only; when you first wrote and how many each way
    are for its More. Worked out once, in the engine (the maintainer, 2026-11-04)."""
    rafe = next(p for p in model["people"] if p["id"] == "kestrel_foods_thorne")
    ex = rafe["exchange"]
    assert ex == {"last": "them", "last_on": "2026-10-19", "replied": True, "first": "you",
                  "first_on": "2026-10-01", "out": 1, "in": 1}, ex
    never = next(p for p in model["people"] if p["id"] == "sedge_foods_glen")
    assert never["exchange"] is None, never["exchange"]


def test_a_card_says_the_latest_exchange_and_its_more_how_it_began(run, page):  # "?" since round two
    """'They replied 19 Oct' on Rafe's card, 'You wrote 15 Oct' on Ash's; 'First wrote' and the
    counts only under More; a late follow-up says Overdue in its corner, never 'days late'."""
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "read": _card("kestrel_foods_thorne")},
        {"hash": "contacts", "open": "pname:row:kestrel_foods_thorne", "eval": "document.querySelector('dialog [data-k=\"pex:kestrel_foods_thorne\"]').textContent"},
        {"eval": "(document.querySelectorAll('dialog[open]').forEach((d) => d.close()), 1)"},
        {"hash": "contacts", "read": _card("thornbury_bank_brook")},
        {"hash": "contacts", "read": "#main"},
    ])
    assert not got["errors"], got["errors"]
    rafe, _, _, ash, everyone = (x["text"] for x in got["after"])
    more = got["after"][1]["eval"]
    face = rafe.split("More", 1)[0]
    # How it began is on their page, with the conversation: never More, never a "?" on every
    # card (2026-11-04).
    assert "They replied 19 Oct" in face and "First wrote" not in face, face
    assert "First wrote 1 Oct. 1 message from you, 1 from them." in more, more
    assert "You wrote 15 Oct" in ash and "no reply" not in ash, ash
    assert "days late" not in everyone and "day late" not in everyone, everyone
    assert "Overdue" in everyone, everyone[:800]


# ------------------------------------------------------------------ every state of the box's line

CORWIN = "teal_retail_nettle"
LINE = ("(() => { const g = document.querySelector('%s .going'); return g ? g.innerText.replace(/\\s+/g, ' ').trim() : ''; })()"
        % _card(CORWIN))
BOX = ("(() => { const t = document.querySelector('%s .reply-box textarea'); return t ? [document.querySelector('%s .reply-label').textContent, t.value] : null; })()"
       % (_card(CORWIN), _card(CORWIN)))


def _reply_work(status, **more):
    return dict({"kind": "reply", "title": "Reply to Corwin", "to": "either", "args": {"contact": CORWIN},
                 "asked_at": "2026-10-25T18:29:00Z", "status": status,
                 "stages": [{"name": "Reading what they said", "est_s": 30}, {"name": "Drafting your reply", "est_s": 60}],
                 "stage": 1, "stage_at": "2026-10-25T18:29:30Z"}, **more)


def test_the_reply_line_says_each_state_and_can_be_called_off(run, page, model):
    """The inline standard (the maintainer, 2026-11-04): shown at once; Cancel while it waits
    (gone at once, the words back in the box) and while it runs (Stopping, then Stopped);
    Finished but not on the page yet says so and shows the draft the moment it comes; a
    failure says why, with Try again."""
    said = "Thanks Morgan, happy to talk next week."
    # Before Claude has it: saved and shown at once; Cancel takes the tap back and the words
    # are in the box again.
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "click": "They replied: paste what Corwin sent"},
        {"fillMain": {"Paste what Corwin sent": said}, "then": "Draft my reply to Corwin", "eval": LINE},
        {"click": "Cancel the reply to Corwin", "eval": "[%s, %s]" % (LINE, BOX)},
    ])
    assert not got["errors"], got["errors"]
    first = got["after"][1]["eval"]
    assert first.startswith(("Waiting for Claude · Saved", "Next · Saved")) and "Cancel" in first, first
    line, box = got["after"][2]["eval"]
    assert line == "" and box == ["Paste what Corwin sent", said], (line, box)
    assert not [a for a in got["actions"] if a["action"] == "msg.received"], "called off before Claude had it"
    # Waiting its turn: Cancel stops it at once.
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/reply~" + CORWIN: _reply_work("queued", stage=0)}, steps=[
        {"hash": "contacts", "eval": LINE},
        {"click": "Cancel the reply to Corwin", "eval": "[%s, %s]" % (LINE, BOX)},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"].startswith("Waiting for Claude") and "Cancel" in got["after"][0]["eval"], got["after"][0]["eval"]
    line, box = got["after"][1]["eval"]
    assert line.startswith("Stopped · Nothing was drafted") and "Cancel" not in line, line
    assert box and box[0].startswith("Paste what Corwin sent"), box
    assert next(w for w in got["after"][-1]["work"] if w["id"] == "reply~" + CORWIN)["status"] == "stopped"
    # Running: Stopping after this step, then Stopped once its chat stops it.
    running = _reply_work("running", claimed_by="cloud-1", claimed_at="2026-10-25T18:29:30Z", lease_until="2026-10-25T20:00:00Z")
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/reply~" + CORWIN: running}, steps=[
        {"hash": "contacts", "eval": LINE},
        {"click": "Cancel the reply to Corwin", "eval": LINE},
        {"write": {"work/reply~" + CORWIN: dict(running, stop_asked=True, status="stopped", finished_at="2026-10-25T18:30:30Z")}, "eval": LINE},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"].startswith("Claude is on it · Drafting your reply"), got["after"][0]["eval"]
    assert got["after"][1]["eval"].startswith("Stopping"), got["after"][1]["eval"]
    assert got["after"][2]["eval"].startswith("Stopped"), got["after"][2]["eval"]
    # Finished, the draft not on the page yet: said, then the draft itself, with no reload.
    reply = {"id": "msg-" + CORWIN, "contact": CORWIN, "first_name": "Corwin", "employer": "Teal Retail", "channel": "linkedin_message",
             "kind": "reply", "type": "reply", "subject": None, "body": "Thanks Corwin, next week works.", "text": "Thanks Corwin, next week works.",
             "warnings": [], "blocked": [], "count": {}, "rev": "r-c"}
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/reply~" + CORWIN: _reply_work("done", finished_at="2026-10-25T18:30:00Z")}, steps=[
        {"hash": "contacts", "eval": LINE},
        {"write": {"view/messages": {"made_at": "2026-10-25T18:31:00Z", "data": list(model["messages"]) + [reply]}}, "read": _card(CORWIN), "eval": LINE},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"] == "Finished · Putting it on your page.", got["after"][0]["eval"]
    shown = got["after"][1]
    assert shown["eval"] == "" and "Thanks Corwin, next week works." in shown["text"] and "I sent it" in shown["text"], shown
    # A failure says why, in plain words, with Try again, which asks for it once more.
    failed = _reply_work("failed", error="Claude could not read their message.", finished_at="2026-10-25T18:30:00Z")
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/reply~" + CORWIN: failed}, steps=[
        {"hash": "contacts", "eval": LINE},
        {"click": "Try the reply to Corwin again", "eval": LINE},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"] == "Did not finish · Claude could not read their message. Try again", got["after"][0]["eval"]
    assert next(w for w in got["after"][-1]["work"] if w["id"] == "reply~" + CORWIN)["status"] == "queued", got["after"][-1]["work"]
    assert not got["after"][1]["eval"].startswith("Did not finish"), got["after"][1]["eval"]


def test_a_reply_that_cannot_be_written_honestly_asks_one_question_on_the_card(run, page):
    """Rare: the reply's work stops on one question (its `needs`), asked in the card's one soft
    grey box in place of the draft, the words it is about as a small quote, answered with a
    tap that resumes the same work (the maintainer, 2026-11-04)."""
    rafe = "kestrel_foods_thorne"
    needs = {"question": "Which day suits you for the call?", "about": "What would you like to know?",
             "answer": {"kind": "choice", "choices": ["Thursday", "Friday"]}}
    work = dict(_reply_work("needs_you", note="Which day suits you for the call?", needs=needs), args={"contact": rafe}, title="Reply to Rafe")
    box = "(() => { const c = document.querySelector('%s'); return [c.querySelectorAll('.ask-box, .sendtext').length, !!c.querySelector('details.pdraft')]; })()" % _card(rafe)
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/reply~" + rafe: work}, steps=[
        {"hash": "contacts", "read": _card(rafe), "eval": box},
        {"click": "Thursday", "within": _card(rafe), "read": _card(rafe)},
    ])
    assert not got["errors"], got["errors"]
    card = got["after"][0]["text"]
    assert "Which day suits you for the call?" in card and "What would you like to know?" in card, card
    assert "Needs your answer" in card and "Thursday" in card and "Friday" in card, card
    assert got["after"][0]["eval"] == [1, False], ("one soft grey box: the question, in place of the draft", got["after"][0]["eval"])
    w = next(x for x in got["after"][1]["work"] if x["id"] == "reply~" + rafe)
    assert w["status"] == "queued" and "Thursday" in w["args"]["answers"].values(), w
    assert "Which day suits you" not in got["after"][1]["text"], "answered, the question goes"


# ------------------------------------------------------------------ fixed by itself, and the pencil

ZOE = "rook_health_quarry"


def test_a_draft_that_breaks_a_rule_has_its_fix_queued_with_no_tap(book, model, tmp_path):
    """The maintainer, 2026-11-04, over a 328-of-300 note with a Fix it button: "why not fix it
    autonomously?" The engine says what to fix, and the view queues it, asked by nobody."""
    import glob
    import json as _json
    zoe = next(m for m in model["messages"] if m["contact"] == ZOE)
    fix = zoe["fix"]
    assert fix["must"] and "it asks them for a job" in fix["reasons"], fix
    dump, out = tmp_path / "dump", tmp_path / "out"
    dump.mkdir()
    book.run(APP, "view", str(out), "--now", NOW, "--dump", str(dump))
    queued = {}
    for f in glob.glob(str(out / "files" / "work" / "*.json")):
        with open(f, encoding="utf-8") as fh:
            body = _json.load(fh)
        queued[body["args"]["target"]["id"]] = body
    w = queued.get(zoe["id"])
    assert w and w["kind"] == "tweak" and w["status"] == "queued" and w["args"]["auto"] is True, queued.keys()
    assert "it asks them for a job" in w["args"]["text"] and not any("PDF" in s["name"] for s in w["stages"]), w
    # Asked once: the same draft and reasons are never queued again.
    dump2, out2 = tmp_path / "dump2", tmp_path / "out2"
    (dump2 / "work").mkdir(parents=True)
    (dump2 / "work" / (fix["work"] + ".json")).write_text(_json.dumps({"data": dict(w, status="queued"), "version": 1}), encoding="utf-8")
    book.run(APP, "view", str(out2), "--now", NOW, "--dump", str(dump2))
    again = [f for f in glob.glob(str(out2 / "files" / "work" / "*.json")) if ZOE in f]
    assert not again, again


def test_the_card_says_claude_is_fixing_it_and_offers_it_only_once_fixed(run, page, model):
    zoe = next(m for m in model["messages"] if m["contact"] == ZOE)
    wid = zoe["fix"]["work"]
    line = "(() => { const g = document.querySelector('%s .going'); return g ? g.innerText.replace(/\\s+/g, ' ').trim() : ''; })()" % _card(ZOE)
    running = {"kind": "tweak", "title": "Fix the note to Zoe", "to": "either", "status": "running", "claimed_by": "cloud-1",
               "claimed_at": "2026-10-25T18:29:30Z", "lease_until": "2026-10-25T20:00:00Z", "asked_at": "2026-10-25T18:29:00Z",
               "args": {"v": 1, "target": {"id": zoe["id"], "output": "message", "contact": ZOE}, "auto": True, "text": zoe["fix"]["text"]},
               "stages": [{"name": "Changing it", "est_s": 45}], "stage": 0, "stage_at": "2026-10-25T18:29:30Z"}
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed={"work/" + wid: running}, steps=[
        {"hash": "contacts", "read": _card(ZOE), "eval": line}])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"].startswith("Claude is fixing it · It asks them for a job"), got["after"][0]["eval"]
    assert "I sent it" not in got["after"][0]["text"] and "Fix it" not in got["after"][0]["text"], got["after"][0]["text"]
    # Tried as often as it may and still breaking a rule: said, with the pencil to change it.
    tried = {"work/" + wid: dict(running, status="done"), "work/" + wid.rsplit("~", 1)[0] + "~older": dict(running, status="done")}
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=tried, steps=[{"hash": "contacts", "read": _card(ZOE)}])
    card = got["after"][0]["text"]
    assert "Claude could not fix this by itself: it asks them for a job. Change it with the pencil." in card and "I sent it" not in card, card


def test_the_pencil_changes_the_words_in_place_or_asks_claude(run, page, model):
    """The pencil beside Copy (2026-11-04): the words changed in place are what is copied and
    logged as sent; "Shorter" asks Claude, its line on the card."""
    rafe = "kestrel_foods_thorne"
    new = "Thanks Rafe, I'd love to hear how the planning team works."
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=fixed(model), steps=[
        # The pencil asks what to change; its "Edit the words yourself" makes the words a field
        # (the maintainer, 2026-11-05).
        {"hash": "contacts", "open": "pen:msg-" + rafe},
        {"open": "penedit:msg-" + rafe},
        {"eval": "(() => { const t = document.querySelector('[data-k=\"pentext:msg-%s\"]'); t.value = %s; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()" % (rafe, json.dumps(new))},
        {"click": "Copy message to Rafe", "clip": True},
        {"click": "I sent it: the message to Rafe"},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][3]["clip"] == new, got["after"][3]["clip"]
    sent = next(a for a in got["actions"] if a["action"] == "msg.sent")
    assert sent["value"]["text"] == new, sent
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=fixed(model), steps=[
        {"hash": "contacts", "open": "pen:msg-" + rafe, "count": _card(rafe) + " .pen-tell .cost"},
        # A quick choice fills the box; one Ask Claude sends it, with the box's one gauge (the
        # maintainer, 2026-11-05: four gauges in a row were clutter).
        {"click": "Shorter: add it to what Claude changes"},
        {"click": "Ask Claude to change the message to Rafe", "read": _card(rafe)},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["count"] == 1, "one gauge, beside Ask Claude"
    w = [x for x in got["after"][2]["work"] if x.get("kind") == "tweak" and not x["args"].get("auto")]
    assert w and w[0]["args"]["text"] == "Make it shorter." and w[0]["args"]["target"]["contact"] == rafe, w
    assert "Make it shorter" in got["after"][2]["text"] and "Cancel" in got["after"][2]["text"], got["after"][2]["text"]


# ------------------------------------------------------------------ More on a card

MORE = r"""(() => {
  const c = document.querySelector('%s');
  const row = c.querySelector('.card-actions');
  const sum = row.querySelector(':scope > details.more > summary');
  const first = row.querySelector(':scope > .btn, :scope > a');
  const panel = sum && document.getElementById(sum.getAttribute('aria-controls'));
  const top = (e) => Math.round(e.getBoundingClientRect().top);
  return {sum: !!sum, sameLine: !!(sum && first) && Math.abs(top(sum) - top(first)) <= 2, first: first ? first.textContent.trim() : '',
    after: !!panel && row.nextElementSibling === panel, shown: !!panel && !panel.hidden && panel.getClientRects().length > 0,
    rows: panel ? [...panel.querySelectorAll(':scope > .more-acts')].map((r) => [...r.children].filter((b) => b.matches('button, .btn, a')).map((b) => [b.textContent.trim(), top(b)])) : []};
})()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_more_opens_under_its_row_and_its_buttons_are_one_row(run, page, model, vp):
    """The maintainer, 2026-11-05: "the more dropdown was next to i sent it, but when u press it,
    it goes below it", and "those buttons could for sure be one line". Opened, More stays beside
    I sent it and its panel opens under the row; its buttons are one row, wrapping only at the
    panel's width, with Something else last."""
    rafe = "kestrel_foods_thorne"
    got = run("engine", html=page, viewport=vp, clock=CLOCK, seed=fixed(model), steps=[
        {"hash": "contacts", "eval": MORE % _card(rafe)},
        {"more": rafe, "eval": MORE % _card(rafe)},
    ])
    assert not got["errors"], got["errors"]
    shut, opened = got["after"][0]["eval"], got["after"][1]["eval"]
    assert shut["sum"] and shut["sameLine"] and not shut["shown"], shut
    assert opened["first"] == "I sent it" and opened["sameLine"], opened
    assert opened["after"] and opened["shown"], opened
    assert len(opened["rows"]) == 1, opened["rows"]
    labels = [b[0] for b in opened["rows"][0]]
    assert labels[-1] == "Something else", labels
    if vp is WIDE:
        assert len({b[1] for b in opened["rows"][0]}) == 1, opened["rows"]


def test_something_else_asks_under_the_card_and_the_answer_shows_there_never_in_chat(run, page, model):
    """The maintainer, 2026-11-05: "there should be a 'something else' button if i need to feed
    back", then: "it opens a text box UNDER THAT PARTICULAR THING IM QUERYING, which gets sent to
    claude ... (separate from the chat ...) and then the response shows underneath ... the chat is
    being clogged up with everything". The question goes to Claude as work about that card, in
    the card's own thread, and Claude's answer shows under the card; the Chat shows neither."""
    rafe = "kestrel_foods_thorne"
    p = next(x for x in model["people"] if x["id"] == rafe)
    th = "card-person-" + rafe
    card = _card(rafe)
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=fixed(model), steps=[
        {"hash": "contacts", "more": rafe, "click": "Something else about " + p["first_name"],
         "eval": "(() => { const b = document.querySelector('%s .ct-box textarea'); return {box: !!b, focused: document.activeElement === b}; })()" % card},
        # The box is filled, then sent (a step taps before it fills).
        {"fillMain": {"Anything else about": "He moved to the risk team. Is my note still right?"}},
        {"click": "Ask Claude about " + p["first_name"], "read": card, "store": "talk/"},
        # Claude answers in the card's own thread, as `app.py done --reply-file` writes it.
        {"write": {"talk/%s/messages/m-answer" % th: {"from": "claude", "text": "Yes. Say risk team in the second line.", "at": "2026-10-25T18:31:00Z", "_v": 1}},
         "read": card},
        {"hash": "chat", "read": "#main"},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"]["box"], got["after"][0]["eval"]
    talk = [w for w in got["work"] if w.get("kind") == "talk"]
    assert len(talk) == 1, got["work"]
    assert talk[0]["args"]["thread"] == th and talk[0]["args"]["about"]["kind"] == "person" and talk[0]["args"]["about"]["id"] == rafe, talk[0]
    threads = [x for x in got["after"][2]["store"] if x["path"].count("/") == 1]
    assert [x["path"] for x in threads] == ["talk/" + th] and threads[0]["card"]["id"] == rafe, threads
    asked = got["after"][2]["text"]
    assert "He moved to the risk team" in asked and "Something else" in asked, asked
    answered = got["after"][3]["text"]
    assert "Yes. Say risk team in the second line." in answered, answered
    chat = got["after"][4]["text"]
    assert "risk team" not in chat, chat[:800]


def test_a_draft_that_sends_the_resume_carries_the_document(run, model, tmp_path):
    """The maintainer, 2026-11-05: "it would be great if the actual document was linked there".
    A draft whose words send the resume ("CV attached") shows the file under it, ready to save
    and attach; one that only offers it does not."""
    import copy
    import app_model
    from test_the_page_works_in_a_browser import _write
    rafe = "kestrel_foods_thorne"
    assert app_model.sends_of("Thanks Rafe, CV attached.") == "resume"
    assert app_model.sends_of("Here's my resume as promised.") == "resume"
    assert app_model.sends_of("Happy to send my resume if that is useful.") is None
    m2 = copy.deepcopy(model)
    msg = next(x for x in m2["messages"] if x["contact"] == rafe)
    msg["text"] = msg["body"] = "Thanks Rafe, CV attached. Happy to talk whenever suits."
    msg["sends"] = "resume"
    other = next(x for x in m2["messages"] if x["contact"] != rafe and x.get("contact"))
    html = _write(tmp_path, "sends", m2)
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=fixed(m2), steps=[
        {"hash": "contacts", "read": _card(rafe),
         "eval": "[...document.querySelectorAll('%s .sends-line button')].map((b) => b.textContent.trim())" % _card(rafe)},
        {"hash": "contacts", "count": _card(other["contact"]) + " .sends-line"},
    ])
    assert not got["errors"], got["errors"]
    assert "Goes with it" in got["after"][0]["text"], got["after"][0]["text"]
    (label,) = got["after"][0]["eval"]
    assert label.startswith("Your "), label
    assert got["after"][1]["count"] == 0


def test_an_answer_is_done_never_putting_it_on_your_page(run, page, model):
    """An answer is its own result: its work card said "Finished: putting it on your page" for
    three minutes, a long pill that squeezed its title to a word a line (the maintainer,
    2026-11-05)."""
    seed = dict(fixed(model), **{"work/talk~x": {"kind": "talk", "title": "Answer: “About Rafe at Kestrel Foods: did we apply?”", "status": "done",
                                                 "to": "cloud", "asked_at": "2026-10-25T18:20:00Z", "finished_at": "2026-10-25T18:29:00Z",
                                                 "result": {"summary": "Yes, you applied through his link."}, "args": {}, "_v": 2}})
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        {"hash": "contacts", "eval": "[...document.querySelectorAll('[data-work=\"talk~x\"] .state-word')].map((e) => e.textContent.trim())"}])
    assert not got["errors"], got["errors"]
    words = got["after"][0]["eval"]
    assert words and not any("putting it on your page" in w for w in words), words
