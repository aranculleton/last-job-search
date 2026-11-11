"""A message someone sent is answered in two commands, and the page is finished by code.

Each step of a chat reads its whole history again, so steps are the cost. A reply pasted
into a chat took about fifteen steps before the person saw the draft, five of them looking
for how a received message is logged (2026-11-03). Now `reply.py prepare` is everything
before the draft: who wrote (by name, saying when it is not sure), their message logged by
state.py received's own path, what it is, whether a reply is owed, the guidance, the
thread, an interview's time saved, and the person's own rules. `reply.py finish` is
everything after: the draft check, refused while it finds anything, the draft put where
the page shows it, and with the page's work its finishing batch. `app.py done` writes that
batch for any other work, and `app.py ask` queues work the way the page does. Every person
and employer is invented: tests/app_state.py's search, with one more Juno Castellan at
Thornbury Bank, where a panel interview is booked for 2026-10-28 with no time.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
from company_key import key as company_key  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402

JUNO = "thornbury_bank_castellan"         # a second Juno Castellan: the example has one
LARKSPUR = "larkspur_retail_castellan"
WREN = "fernhill_freight_halloway"
INVITE = ("Hi Morgan, thanks for your patience. Confirming your panel interview on Wednesday "
          "28 October at 2.30pm with the head of risk. Could you let me know it suits?\n\n"
          "Best,\nJuno")


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    path = os.path.join(s.state, "network_contacts.csv")
    with open(path, encoding="utf-8") as fh:
        head = next(csv.reader(fh))
    with open(path, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=head, extrasaction="ignore").writerow(dict.fromkeys(head, "") | {
            "contact_id": JUNO, "name": "Juno Castellan", "title": "Talent Partner",
            "company": "Thornbury Bank", "company_key": company_key("Thornbury Bank"),
            "tier": "2", "route": "hiring_team", "first_contacted": "2026-10-10",
            "channel": "email", "status": "awaiting_reply"})
    s.tmp = tmp_path
    return s


def run(search, *args, given=None):
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private", LJS_CHAT="chat-test")
    env.pop("LJS_TODAY", None)
    env.pop("CLAUDE_CODE_REMOTE", None)
    r = subprocess.run([sys.executable, *args], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120, cwd=ROOT, input=given)
    return r.returncode, r.stdout + r.stderr


def write(search, name, text):
    path = search.tmp / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def rows_for(search, cid):
    with open(os.path.join(search.state, "network_threads.csv"), encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["contact_id"] == cid]


def put(search, collection, doc_id, data, version):
    d = os.path.join(search.dump, collection)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, doc_id.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
        json.dump(dict(data, _v=version), fh)


def batch(path):
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    out = []
    for e in entries:
        body = None
        if e.get("file_path"):
            with open(e["file_path"], encoding="utf-8") as fh:
                body = json.load(fh)
        out.append(dict(e, body=body))
    return out


# ------------------------------------------------------------------ before the draft


def test_prepare_logs_their_message_and_brings_everything_the_draft_needs(search):
    msg = write(search, "invite.txt", INVITE)
    # Two people share the name: nothing is logged to a guess, and both are named.
    code, out = run(search, "tools/network/reply.py", "prepare", "Juno Castellan",
                    "--text-file", msg, "--date", "2026-10-25", "--today", "2026-10-25")
    assert code == 2 and "not sure who 'Juno Castellan' is" in out, out
    assert JUNO in out and LARKSPUR in out and "nothing was logged" in out
    assert rows_for(search, JUNO) == []

    code, out = run(search, "tools/network/reply.py", "prepare", "Juno Castellan",
                    "--company", "Thornbury Bank", "--text-file", msg, "--date", "2026-10-25",
                    "--channel", "email", "--today", "2026-10-25")
    assert code == 0, out
    (row,) = rows_for(search, JUNO)
    assert (row["direction"], row["channel"], row["date"]) == ("in", "email", "2026-10-25")
    assert row["full_text"].startswith("Hi Morgan, thanks for your patience.")
    for said in ("found by name", "received: They replied (email) on 2026-10-25",
                 # The time it gives goes on the interview, by logging's own path.
                 "Saved on the interview: Panel interview with Thornbury Bank on 2026-10-28 at "
                 "14:30.",
                 "scenario: ", "reply owed: yes, they wrote last.", "move: ", "length: ",
                 "the thread, oldest first", "them (email): Hi Morgan, thanks for your patience",
                 "before drafting, what the person has taught it",
                 f"reply.py finish {JUNO} --draft-file - with the reply on its input"):
        assert said in out, (said, out)

    # Run again (another chat, or a second look): logged once, and the person's own rules
    # are read before the draft.
    code, rec = run(search, "tools/learned.py", "record", "--area", "messages",
                    "--said", "keep replies to recruiters to two lines",
                    "--rule", "Replies to recruiters run two lines at most.")
    assert code == 0, rec
    code, out = run(search, "tools/network/reply.py", "prepare", JUNO, "--text-file", msg,
                    "--date", "2026-10-25", "--channel", "email", "--today", "2026-10-25")
    assert code == 0, out
    assert "nothing logged twice" in out and len(rows_for(search, JUNO)) == 1
    assert "Replies to recruiters run two lines at most." in out


def test_with_no_message_given_their_newest_logged_one_is_read_and_nothing_is_logged(search):
    # The page's Reply: their message is in the log already.
    code, out = run(search, "tools/network/reply.py", "prepare", LARKSPUR, "--today",
                    "2026-10-25")
    assert code == 0, out
    assert "received:" not in out and len(rows_for(search, LARKSPUR)) == 2
    assert "scenario: " in out and "reply owed: yes, they wrote last." in out
    code, out = run(search, "tools/network/reply.py", "prepare", WREN, "--today", "2026-10-25")
    assert code == 0 and "nothing of theirs is waiting" in out, out
    assert f"followup_drafts.py --contact {WREN}" in out


def test_a_first_name_alone_is_not_enough_to_log_it(search):
    msg = write(search, "m.txt", "Thanks for connecting! Happy to chat next week.")
    code, out = run(search, "tools/network/reply.py", "prepare", "Wren", "--text-file", msg)
    assert code == 2 and "not sure who 'Wren' is" in out, out
    assert f"{WREN}: Wren Halloway" in out and "(one name only)" in out
    code, out = run(search, "tools/network/reply.py", "prepare", "Nobody Here", "--text-file", msg)
    assert code == 2 and "nobody called 'Nobody Here' is in the contact book" in out, out
    assert len(rows_for(search, WREN)) == 1          # only the first note


def test_an_out_of_office_and_a_promise_to_come_back_owe_no_reply(search):
    away = write(search, "away.txt", "I am out of the office until 9 November with limited "
                                     "access to email.")
    code, out = run(search, "tools/network/reply.py", "prepare", "Wren Halloway",
                    "--text-file", away, "--today", "2026-11-03")
    assert code == 0, out
    assert "reply owed: no, it is an automatic reply" in out and "Nothing to draft." in out
    # Their words on the command's input: one step, with no file written first.
    code, out = run(search, "tools/network/reply.py", "prepare", WREN, "--text-file", "-",
                    "--today", "2026-11-04", given="Thanks Morgan, I'll get back to you next "
                                                  "week once I've spoken to the team.")
    assert code == 0, out
    assert "reply owed: probably not" in out and f"state.py no-reply {WREN}" in out


# ------------------------------------------------------------------ after the draft


def test_finish_refuses_a_draft_the_check_refuses_and_while_a_reaction_waits(search):
    bad = write(search, "bad.txt", "Thanks Juno — I can leverage my synergies.")
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", bad)
    assert code == 1 and "REFUSED, nothing saved" in out and "fix: em_dash" in out, out
    draft_md = os.path.join(search.state, "documents", "network", LARKSPUR, "draft.md")
    assert not os.path.exists(draft_md)
    with open(os.path.join(search.state, ".reactions.json"), "w", encoding="utf-8") as fh:
        json.dump([{"said": "too formal, all of them", "cue": "too formal",
                    "at": "2026-11-03T10:00:00"}], fh)
    good = write(search, "good.txt", "Thanks Juno, that is kind of you. I have sent my CV to "
                                     "your email.")
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", good)
    assert code == 1 and "not recorded yet" in out, out
    assert not os.path.exists(draft_md)


def test_finish_saves_the_draft_for_the_page_and_writes_the_finishing_batch(search):
    wid = "talk~cloud-c1~m1"
    put(search, "work", wid, {"kind": "talk", "title": "Answer: Juno wrote", "to": "cloud",
                              "args": {"thread": "cloud-c1", "message": "m1"},
                              "status": "running", "stage": 1}, 3)
    put(search, "holds", f"contact~{LARKSPUR}", {"work": wid, "chat": "chat-test"}, 2)
    put(search, "holds", "search", {"work": "search~other", "chat": "chat-test"}, 5)
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", "-",
                    "--work", wid, "--dump", search.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25",
                    given="Thanks Juno, that is kind of you. I have sent my CV to your email.\n")
    assert code == 0, out
    assert "check: passed" in out and "Nothing is sent" in out
    # The page's Messages shows it, with Copy and "I sent it"; nothing is logged as sent.
    with open(os.path.join(search.state, "documents", "network", LARKSPUR, "draft.md"),
              encoding="utf-8") as fh:
        assert fh.read() == "Thanks Juno, that is kind of you. I have sent my CV to your email.\n"
    assert [r["direction"] for r in rows_for(search, LARKSPUR)] == ["outbound", "inbound"]
    got = json.loads(out[out.index("{"):])
    (said, work, lock) = batch(got["batches"][0])
    assert (said["op"], said["collection"]) == ("set", "talk/cloud-c1/messages")
    assert said["body"]["from"] == "cloud" and said["body"]["work"] == wid
    # The thread says where the draft is, with the button to their card, never the draft
    # itself (the maintainer, 2026-11-10): it is on Juno's card with its Copy.
    assert "Thanks Juno, that is kind of you." not in said["body"]["text"], said["body"]["text"]
    go = [{"label": "Updated in Contacts", "to": f"page:contacts/{LARKSPUR}"}]
    assert said["body"]["go"] == go
    assert (work["op"], work["if_version"]) == ("update", 3)
    assert work["body"]["status"] == "done"
    assert work["body"]["result"] == {"summary": "Your reply to Juno is ready to copy.",
                                      "links": [], "go": go}
    assert (lock["op"], lock["collection"], lock["doc_id"], lock["if_version"]) == \
        ("delete", "holds", f"contact~{LARKSPUR}", 2)      # the other job's lock stays


THREAD = """Oct 20
Morgan Ellis   9:14 AM
Hi Juno, thanks again for passing my CV on. Anything else I can send, my email is morgan.ellis@example.com
View Juno’s profile
Juno Castellan   4:02 PM
Thanks Morgan, the team are reviewing it this week.
Today
Morgan Ellis   8:30 AM
Hi Juno, hope the week is going well. My email again in case it is easier: morgan.ellis@example.com
Juno Castellan   10:42 AM
Hi Morgan, all good here. The hiring manager would like a quick call on Thursday at 2pm, does that suit?
"""


def test_a_conversation_pasted_whole_logs_only_their_messages_on_their_own_days(search):
    """A LinkedIn thread pasted whole, the person's own messages in it, was logged as two
    rows of theirs on one day holding the person's words, and the person's own address in
    it read as a request for the resume at 0.97 (2026-11-05)."""
    code, out = run(search, "tools/network/reply.py", "prepare", LARKSPUR, "--text-file", "-",
                    "--today", "2026-10-25", given=THREAD)
    assert code == 0, out
    ins = [r for r in rows_for(search, LARKSPUR) if r["direction"] in ("in", "inbound")]
    new = [r for r in ins if r["date"] >= "2026-10-01"]
    assert [r["date"] for r in new] == ["2026-10-20", "2026-10-25"], new
    assert new[0]["full_text"] == "Thanks Morgan, the team are reviewing it this week."
    assert new[1]["full_text"].startswith("Hi Morgan, all good here.")
    assert not any("morgan.ellis@example.com" in r["full_text"] or "Hi Juno" in r["full_text"]
                   for r in new)
    assert "scenario: send_resume" not in out, out
    assert "2 from Juno read as theirs, 2 of yours left out" in out, out
    # Pasted again: nothing is logged twice.
    code, out = run(search, "tools/network/reply.py", "prepare", LARKSPUR, "--text-file", "-",
                    "--today", "2026-10-25", given=THREAD)
    assert code == 0 and "nothing logged twice" in out, out
    assert len([r for r in rows_for(search, LARKSPUR) if r["direction"] in ("in", "inbound")]) \
        == len(ins)


def test_the_persons_own_address_never_reads_as_one_they_were_given(search):
    said = "Thanks, I will pass it to the team.\n\nMorgan Ellis\nmorgan.ellis@example.com"
    code, out = run(search, "tools/network/reply.py", said)
    assert code == 0 and "scenario: send_resume" not in out, out
    code, out = run(search, "tools/network/reply.py",
                    "Thanks, could you send your CV to juno.c@example.org?")
    assert "scenario: send_resume" in out, out


def test_what_worked_is_said_to_claude_and_never_in_the_reply_on_the_page(search):
    """"35 of 627 (6%) answered" ended up in the reply the person read on the page
    (2026-11-05): the counts are Claude's, said apart, and the page gets the reply alone."""
    wid = "talk~cloud-c2~m1"
    put(search, "work", wid, {"kind": "talk", "title": "Answer: Juno wrote", "to": "cloud",
                              "args": {"thread": "cloud-c2", "message": "m1"},
                              "status": "running", "stage": 1}, 3)
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", "-",
                    "--work", wid, "--dump", search.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25",
                    given="Thanks Juno, that is kind of you. I have sent my CV to your email.\n")
    assert code == 0, out
    assert "what worked (for you, not for the reply): " in out and "answered" in out, out
    got = json.loads(out[out.index("{"):])
    said = batch(got["batches"][0])[0]
    assert said["collection"] == "talk/cloud-c2/messages"
    assert "answered" not in said["body"]["text"] and "route" not in said["body"]["text"], \
        said["body"]["text"]


# ------------------------------------------------------------------ any other work


def test_done_finishes_any_work_in_one_batch_and_holds_the_summary_to_one_sentence(search):
    wid = "draft~20261025T1700-ab12"
    put(search, "work", wid, {"kind": "draft", "title": "CV and letter: Kestrel Mutual",
                              "to": "cloud", "args": {"company": "Kestrel Mutual"},
                              "status": "running", "stage": 4}, 7)
    put(search, "holds", "emp~kestrel_mutual", {"work": wid, "chat": "chat-test"}, 1)
    app = os.path.join(ROOT, "tools", "app.py")
    for summary, why in (
            ("Your Kestrel Mutual CV and letter are ready, checked twice for every fact and "
             "number, and waiting in Drafts.", "15 words at most"),
            ("Your CV is ready. The letter too.", "one sentence")):
        code, out = run(search, app, "done", search.dump, "--work", wid, "--summary", summary,
                        "--now", NOW)
        assert code == 2 and why in out, out
    code, out = run(search, app, "done", search.dump, "--work", wid, "--summary",
                    "Your Kestrel Mutual CV and letter are ready.", "--link",
                    "Your CV=cv/Morgan_Ellis_CV_Kestrel.pdf", "--now", NOW)
    assert code == 0, out
    work, lock = batch(json.loads(out)["batches"][0])
    assert (work["if_version"], work["body"]["status"]) == (7, "done")
    assert work["body"]["result"]["links"] == [{"label": "Your CV",
                                                "url": "cv/Morgan_Ellis_CV_Kestrel.pdf"}]
    assert (lock["op"], lock["if_version"]) == ("delete", 1)
    # Finished is finished: the dump says so, and a second finish writes nothing new. It gives
    # back the finish this folder made, the same batch, so one never sent is never lost (two
    # finishes in a row, 2026-11-09).
    first = json.loads(out)["batches"]
    code, out = run(search, app, "done", search.dump, "--work", wid, "--summary", "Done.",
                    "--now", NOW)
    assert code == 0 and json.loads(out)["again"] is True, out
    assert json.loads(out)["batches"] == first[:1]      # the finish (its files went apart)
    work, _lock = batch(first[0])
    assert work["body"]["result"]["summary"] == "Your Kestrel Mutual CV and letter are ready."

    talk = "talk~cloud-c2~m9"
    put(search, "work", talk, {"kind": "talk", "title": "Answer: what next?", "to": "cloud",
                               "args": {"thread": "cloud-c2", "message": "m9"},
                               "status": "running"}, 2)
    answer = write(search, "answer.txt", "Next is the panel on Wednesday; your pack is ready.")
    code, out = run(search, app, "done", search.dump, "--work", talk, "--summary",
                    "Answered in your chat.", "--reply-file", answer, "--kind", "computer",
                    "--now", NOW)
    assert code == 0, out
    said, work = batch(json.loads(out)["batches"][0])
    assert said["collection"] == "talk/cloud-c2/messages" and said["body"]["from"] == "computer"
    assert said["body"]["text"] == "Next is the panel on Wednesday; your pack is ready."
    failed = "evaluate~20261025T1700-zz99"
    put(search, "work", failed, {"kind": "evaluate", "title": "A job from a link",
                                 "status": "running"}, 1)
    code, out = run(search, app, "done", search.dump, "--work", failed, "--failed",
                    "The posting was taken down before it could be read.", "--now", NOW)
    assert code == 0, out
    (work,) = batch(json.loads(out)["batches"][0])
    assert work["body"]["status"] == "failed"
    assert work["body"]["error"] == "The posting was taken down before it could be read."


def _page_work_fields() -> set:
    """The fields the page's own createWork writes on a new item (templates/app/app.js)."""
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    start = js.index("const doc = {kind: s.kind")
    body = js[start + len("const doc = {"):js.index("};", start)]
    body = re.sub(r"\{[^{}]*\}", "{}", body)          # a nested object's own keys are not its
    return set(re.findall(r"(?:^|, |\n\s+)([a-z_]+):", body))


def test_ask_queues_work_as_the_page_does_and_next_takes_it(search):
    app = os.path.join(ROOT, "tools", "app.py")
    code, out = run(search, app, "ask", search.dump, "--kind", "reply", "--title",
                    "Reply to Juno", "--args", json.dumps({"contact": LARKSPUR}), "--now", NOW)
    assert code == 0, out
    got = json.loads(out)
    (new,) = batch(got["batches"][0])
    assert (new["op"], new["collection"], new["doc_id"]) == ("set", "work", got["work"])
    assert re.fullmatch(r"reply~\d{8}T\d{4}-[a-z0-9]{4}", got["work"])
    assert _page_work_fields() <= set(new["body"]), _page_work_fields() - set(new["body"])
    assert new["body"]["status"] == "queued" and new["body"]["args"] == {"contact": LARKSPUR}
    assert [s["key"] for s in new["body"]["stages"]] == \
        [s["key"] for s in page_db.progress("reply")["stages"]]
    # The dump holds it now, so this chat takes it the way it takes the page's own.
    code, out = run(search, app, "next", search.dump, "--chat", "chat-test", "--kind", "cloud",
                    "--now", NOW)
    assert code == 0 and json.loads(out)["work"] == got["work"], out

    code, out = run(search, app, "ask", search.dump, "--kind", "search", "--title",
                    "Find me jobs", "--now", NOW)
    assert code == 0, out
    code, out = run(search, app, "ask", search.dump, "--kind", "search", "--title",
                    "Find me more jobs", "--now", NOW)
    assert code == 2 and "one at a time" in out, out
    code, out = run(search, app, "ask", search.dump, "--kind", "lunch", "--title", "Lunch",
                    "--now", NOW)
    assert code == 2 and "there is no kind of work 'lunch'" in out, out


def test_the_instructions_name_the_commands():
    def said(rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return " ".join(fh.read().split())
    import app_skill
    app, reply, net = (" ".join(app_skill.text().split()), said(".claude/commands/reply.md"),
                       said(".claude/skills/networking/SKILL.md"))
    for text in (app, reply, net):
        assert "reply.py prepare" in text and "reply.py finish" in text
    assert "app.py done" in app and "app.py ask" in app
    # Every rule /reply keeps is still there.
    for rule in ("learned.py brief", "learned.py record", "Nothing is ever sent", "state.py received"):
        assert rule in reply, rule
