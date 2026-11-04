"""Nobody at their limit of unanswered messages, closed or gone cold is given a date, and
leaving someone alone is never a To do.

The maintainer, 4 November 2026: "you'd already cleared those six 'leave it' cards from the
page earlier today, and they came back after the update gave every contact a follow-up date.
A contact at its message limit shouldn't get a date, and a card that says 'do nothing'
shouldn't be in To do at all." The update ran `state.py follow-ups --write`
(state.write_follow_ups), which put a day to close the thread on every row at its limit; on
that day the row was owed again, and To do listed it as a card to close.

Every person and employer here is invented.
"""
from __future__ import annotations

import ast
import csv
import os
import sys

import pytest

from tests import repo_files  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_contacts_show_only_what_the_persons_rules_allow import (  # noqa: E402
    CONTACT_COLUMNS, NOTE, NUDGE, THREAD_COLUMNS, TODAY, Book, _save, out, person)

STATE_PY = os.path.join(ROOT, "tools", "network", "state.py")
OLD_LINE = ("Nudged: nothing more unless they reply. If still silent by the date, close it: "
            "state.py set {cid} --status gone_cold")


def _rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class Search(Book):
    """The rules book, and four more: two at their limit (one undated, one with the day the
    app used to write), one closed on the page, and one with a follow-up still to come."""

    def __init__(self, root):
        super().__init__(root)
        cp = os.path.join(self.state, "network_contacts.csv")
        tp = os.path.join(self.state, "network_threads.csv")
        c, t = _rows(cp), _rows(tp)
        for cid, name in (("ashby_mills_haldane", "Corwin Haldane"),
                          ("ashby_mills_oyelaran", "Tamsin Oyelaran"),
                          ("brindle_co_quarrie", "Fenella Quarrie")):
            t += [out(cid, "2026-09-10", NOTE.format(n=name.split()[0])),
                  out(cid, "2026-09-24", NUDGE.format(n=name.split()[0]), "follow_up")]
        c += [person("ashby_mills_haldane", "Corwin Haldane", "Ashby Mills", "awaiting_reply"),
              person("ashby_mills_oyelaran", "Tamsin Oyelaran", "Ashby Mills", "awaiting_reply",
                     action=OLD_LINE.format(cid="ashby_mills_oyelaran"), due="2026-10-02"),
              # Closed on the page: Close sets gone_cold and clears the step and its day.
              person("brindle_co_quarrie", "Fenella Quarrie", "Brindle Co", "gone_cold"),
              person("brindle_co_pellow", "Rhian Pellow", "Brindle Co", "awaiting_reply")]
        t.append(out("brindle_co_pellow", "2026-10-21", NOTE.format(n="Rhian")))
        _save(cp, c, CONTACT_COLUMNS)
        _save(tp, t, THREAD_COLUMNS)

    def state_py(self, *args):
        return self.run(STATE_PY, *args, "--today", TODAY)

    def contact(self, cid):
        return next(r for r in _rows(os.path.join(self.state, "network_contacts.csv"))
                    if r["contact_id"] == cid)

    def set_row(self, cid, **fields):
        """Change a row as a merge of two copies can: no command, no gate."""
        path = os.path.join(self.state, "network_contacts.csv")
        rows = _rows(path)
        for r in rows:
            if r["contact_id"] == cid:
                r.update(fields)
        _save(path, rows, list(rows[0]))


@pytest.fixture(scope="module")
def search(tmp_path_factory):
    return Search(str(tmp_path_factory.mktemp("leave")))


@pytest.fixture(scope="module")
def updated(search):
    """The book after the update's follow-up run, and the page's model of it."""
    said = search.state_py("follow-ups", "--write")
    return said, search.model()


def _due_of(m, cid):
    return [d for d in m["due"] if cid in d["id"] or d.get("item") == cid]


def _p(m, cid):
    return next(p for p in m["people"] if p["id"] == cid)


# ------------------------------------------------------------------ 1. no date at the limit

def test_the_updates_follow_up_run_dates_nobody_at_their_limit_or_closed(search, updated):
    said, _ = updated
    for cid in ("ashby_mills_haldane", "ashby_mills_oyelaran"):
        row = search.contact(cid)
        assert row["next_action"] == "Nudged: nothing more unless they reply", row
        assert row["next_action_due"] == "", (cid, row["next_action_due"], said)
    assert search.contact("brindle_co_quarrie")["next_action_due"] == ""
    assert search.contact("brindle_co_quarrie")["status"] == "gone_cold"
    # A follow-up still to come is dated as ever.
    assert search.contact("brindle_co_pellow")["next_action_due"] > TODAY
    assert "close it on" not in said


def test_no_date_goes_on_by_hand_either_and_the_command_says_why(search, updated):
    got = search.state_py("set", "ashby_mills_haldane", "--due", "2026-11-01")
    assert "no date: they have not answered your limit of messages" in got, got
    assert search.contact("ashby_mills_haldane")["next_action_due"] == ""
    got = search.state_py("set", "brindle_co_quarrie", "--due", "2026-11-01")
    assert "no date: the conversation is closed" in got, got
    assert search.contact("brindle_co_quarrie")["next_action_due"] == ""
    # A follow-up still to come takes the day the person gives it.
    search.state_py("set", "brindle_co_pellow", "--due", "2026-11-09")
    assert search.contact("brindle_co_pellow")["next_action_due"] == "2026-11-09"


def test_every_date_on_a_contact_is_written_through_the_one_gate():
    """state.put_next is the one place a contact's next_action_due is written: a writer that
    set it itself could date someone at their limit or closed again."""
    found = []
    for path in map(str, repo_files.files("tools/**/*.py", root=ROOT)):
        if os.sep + "openroles" + os.sep in path:
            continue
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)

        name = os.path.relpath(path, ROOT).replace(os.sep, "/")

        def visit(node, fn="<module>", name=name):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node.name
            targets = (node.targets if isinstance(node, ast.Assign) else
                       [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
            for t in targets:
                for one in (t.elts if isinstance(t, ast.Tuple) else [t]):
                    if (isinstance(one, ast.Subscript) and isinstance(one.slice, ast.Constant)
                            and one.slice.value == "next_action_due"):
                        found.append((name, fn, ast.unparse(one.value)))
            for child in ast.iter_child_nodes(node):
                visit(child, fn, name)
        visit(tree)
    found = sorted(set(found))
    # The gate itself, and an owed item (not a contact row) that carries the row's day.
    assert found == [("tools/network/state.py", "owed", "base"),
                     ("tools/network/state.py", "put_next", "contact")], found


# ------------------------------------------------------------------ 2. never a To do

def test_someone_at_their_limit_is_left_alone_in_contacts_never_in_to_do(updated):
    _, m = updated
    for cid in ("ashby_mills_haldane", "ashby_mills_oyelaran"):
        assert not _due_of(m, cid), _due_of(m, cid)
        p = _p(m, cid)
        assert p["group"] == "leave" and "leave it unless they write back" in p["next"], p
        assert p["owed"]["kind"] == "close" and p["owed"]["action"] == "person.status", p
    assert not any("No reply to" in d["title"] for d in m["due"]), [d["title"] for d in m["due"]]
    assert not any(d.get("leave") for d in m["due"])
    # Counted nowhere in To do: its quiet line names no one left alone.
    hidden = [d["title"] for d in m["due"] if d["kind"] == "hidden"]
    assert not any("messages" in h for h in hidden), hidden


def test_a_row_at_the_limit_dated_before_is_still_never_a_to_do(search, updated):
    """A day the app put there before, or a "Not today" on the old card, left on the row."""
    search.set_row("ashby_mills_oyelaran", next_action_due="2026-10-02")
    m = search.model()
    assert not _due_of(m, "ashby_mills_oyelaran"), _due_of(m, "ashby_mills_oyelaran")
    assert _p(m, "ashby_mills_oyelaran")["group"] == "leave"
    search.set_row("ashby_mills_oyelaran", next_action_due="")


# ------------------------------------------------------------------ 3. closed stays closed

def test_someone_closed_on_the_page_stays_closed_whatever_date_a_merge_puts_back(search, updated):
    search.set_row("brindle_co_quarrie", next_action=OLD_LINE.format(cid="brindle_co_quarrie"),
                   next_action_due="2026-10-02")
    m = search.model()
    assert not _due_of(m, "brindle_co_quarrie"), _due_of(m, "brindle_co_quarrie")
    p = _p(m, "brindle_co_quarrie")
    assert p["group"] == "done" and p["owed"] is None, p
    # And the next follow-up run takes nothing back: it never touches a closed thread.
    search.state_py("follow-ups", "--write")
    assert search.contact("brindle_co_quarrie")["status"] == "gone_cold"
    search.set_row("brindle_co_quarrie", next_action="", next_action_due="")
