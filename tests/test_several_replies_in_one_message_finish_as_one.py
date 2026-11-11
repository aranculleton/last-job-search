"""One Chat message with several people's replies is finished once, naming every one (#228).

The person pasted three replies in one message ("here are replies from three people, draft
answers"). `reply.py finish` ran for each with the same talk item: the first wrote the item's
finish, the next two were handed that same finish back, and `app.py done` with the real
answer was handed it back too, so the page said only that the first reply was ready. Now each
finish adds its person to the item's one finish, and the answer given at the end replaces the
lines and keeps every button. Made again from the same read, it carries the version the first
was pinned to, so a finish that landed is never sent twice. Every person is invented: the
example search's contacts (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_a_reply_takes_two_commands import (  # noqa: E402,F401
    JUNO, LARKSPUR, ROOT, WREN, batch, put, run, search)
from test_a_tick_on_the_page_is_applied_once import NOW  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
WID = "talk~cloud-c7~m4"
DRAFTS = {
    LARKSPUR: "Thanks Juno, that is kind of you. I have sent my CV to your email.\n",
    JUNO: "Thanks Juno, Wednesday at 2.30pm suits me well. See you then.\n",
    WREN: "Hi Wren, hope the week is going well. Thursday afternoon would suit me for a call.\n",
}


def _finish(s, cid):
    code, out = run(s, "tools/network/reply.py", "finish", cid, "--draft-file", "-",
                    "--work", WID, "--dump", s.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25", given=DRAFTS[cid])
    assert code == 0, out
    return json.loads(out[out.index("{"):])


def _item(s):
    put(s, "work", WID, {"kind": "talk", "title": "Answer: three replies", "to": "cloud",
                         "args": {"thread": "cloud-c7", "message": "m4"},
                         "status": "running", "stage": 1}, 3)
    for cid, v in ((LARKSPUR, 2), (WREN, 4)):
        put(s, "holds", f"contact~{cid}", {"work": WID, "chat": "chat-test"}, v)


def test_three_replies_then_the_real_answer_give_one_finish_naming_all_three(search):  # noqa: F811
    _item(search)
    firsts = []
    for cid in (LARKSPUR, JUNO, WREN):
        got = _finish(search, cid)
        assert not got.get("again"), got
        firsts.append(got["batches"])
    assert firsts[0] == firsts[1] == firsts[2]          # one finish, made again each time
    said, work, *locks = batch(firsts[-1][0])
    text = said["body"]["text"]
    assert "reply to Juno is drafted" in text and "follow-up to Wren is drafted" in text, text
    assert text.count("is drafted") == 3, text
    go = [{"label": "Updated in Contacts", "to": f"page:contacts/{c}"}
          for c in (LARKSPUR, JUNO, WREN)]
    assert said["body"]["go"] == go
    # Pinned to the version read before the first finish, and each hold freed once.
    assert (work["op"], work["if_version"], work["body"]["status"]) == ("update", 3, "done")
    assert work["body"]["result"]["go"] == go
    assert sorted((x["doc_id"], x["if_version"]) for x in locks) == \
        sorted([(f"contact~{LARKSPUR}", 2), (f"contact~{WREN}", 4)])

    answer = ("Three replies drafted: Juno at Larkspur, Juno at Thornbury Bank and Wren. Each "
              "is on their card, ready to copy.")
    code, out = run(search, APP, "done", search.dump, "--work", WID, "--reply-file", "-",
                    "--kind", "cloud", "--now", NOW, given=answer)
    assert code == 0, out
    got = json.loads(out)
    assert not got.get("again") and got["batches"] == firsts[0], got
    said, work, *_ = batch(got["batches"][0])
    assert said["doc_id"] == batch(firsts[0][0])[0]["doc_id"]      # one message, never two
    assert said["body"]["text"] == answer
    assert said["body"]["go"] == go and work["body"]["result"]["go"] == go
    assert work["if_version"] == 3
    assert work["body"]["result"]["summary"] == \
        "Your messages to Juno, Juno and Wren are ready to copy."

    # The same answer again changes nothing: that finish, handed back to send if it never was.
    code, out = run(search, APP, "done", search.dump, "--work", WID, "--reply-file", "-",
                    "--kind", "cloud", "--now", NOW, given=answer)
    assert code == 0 and json.loads(out)["again"] is True, out


def test_a_finish_already_sent_is_never_finished_again(search):  # noqa: F811
    """Read again after the finish landed, the page's own copy says done: the finish is
    handed back, never made a second time."""
    _item(search)
    first = _finish(search, LARKSPUR)
    os.remove(os.path.join(search.dump, ".finished.json"))
    code, out = run(search, "tools/network/reply.py", "finish", WREN, "--draft-file", "-",
                    "--work", WID, "--dump", search.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25", given=DRAFTS[WREN])
    assert code == 2 and "already finished" in out, out
    code, out = run(search, APP, "done", search.dump, "--work", WID, "--reply-file", "-",
                    "--kind", "cloud", "--now", NOW, given="All three are drafted.")
    assert code == 2 and "already finished" in out, out
    assert first["batches"]


def test_made_again_after_it_landed_it_is_pinned_where_the_store_refuses_it(search):  # noqa: F811
    """The first finish landed and the folder read the page again (done, one version on):
    a finish made again still carries the version read before the first, so the store
    refuses it whole, and it names the same message, so the thread never holds two."""
    _item(search)
    first = _finish(search, LARKSPUR)
    said0 = batch(first["batches"][0])[0]
    put(search, "work", WID, {"kind": "talk", "title": "Answer: three replies", "to": "cloud",
                              "args": {"thread": "cloud-c7", "message": "m4"},
                              "status": "done"}, 4)
    got = _finish(search, WREN)
    said, work, *_ = batch(got["batches"][0])
    assert work["if_version"] == 3 and said["doc_id"] == said0["doc_id"], (work, said)
