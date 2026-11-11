"""A page update rewrote every part of a section that changed at all (the second audit of
2026-11-10, D6): of six parts of a person's contacts, three held the very same text and went
again for their stamp alone, 1.59 MB in one update when 8 of 395 people had changed, and the
brief's update the same morning rewrote them all with no one changed. A section is now cut
where its own items end (never where a size falls, which moved every later cut), each part
carries what it holds, and only a part that holds something new is written. The whole lists
behind "Show" are cut and written the same way. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_lists  # noqa: E402
import page_db  # noqa: E402


def _people(n=600):
    return [{"id": f"person_{i}", "first_name": f"Morgan{i}", "employer": "Quillon Data",
             "note": "invented " * 120, "status": "not_contacted"} for i in range(n)]


def _texts(docs):
    return {d: b.get("text") for d, b in docs if "text" in b}


def test_one_person_changed_rewrites_one_part_of_the_section(tmp_path):
    people = _people()
    doc = {"rev": "r1", "made_at": "2026-11-10T08:00:00Z", "data": people}
    first = page_db.split("people", doc)
    assert len(first) > 4
    changed = [dict(p) for p in people]
    changed[3]["note"] += " and a longer note than before" * 60     # early: every later cut moved
    second = page_db.split("people", dict(doc, rev="r2", data=changed))
    a, b = _texts(first), _texts(second)
    differ = [d for d in b if a.get(d) != b[d]]
    assert len(differ) == 1, (len(differ), len(b))
    # The parts join to the section, each checked against what the head says it holds,
    # whenever it was written; one holding something else is never read as the section.
    view = {d: {"data": body, "version": 1} for d, body in first}
    view.update({d: {"data": body, "version": 2} for d, body in second if d in differ or
                 d == "people"})
    assert page_db.joined(view, "people") == changed
    view[differ[0]] = {"data": dict(first[[d for d, _ in first].index(differ[0])][1]),
                       "version": 1}
    assert page_db.joined(view, "people") is None


def test_one_person_changed_rewrites_one_part_of_the_whole_list():
    people = _people(1200)
    before = dict(app_lists.docs({"people": people}, "2026-11-10T08:00:00Z", "r1"))
    changed = [dict(p) for p in people]
    changed[5]["note"] += " and a longer note than before" * 60
    after = dict(app_lists.docs({"people": changed}, "2026-11-10T09:00:00Z", "r2"))
    assert len(after) > 2
    differ = [d for d in after if (before.get(d) or {}).get("items") != after[d]["items"]]
    assert differ == ["list~people~1"], differ
    # Each part says what it holds, and every part says what each part holds, so a part left
    # as it was joins with one written later.
    assert all(d["revs"] == [after[f"list~people~{i}"]["rev"] for i in range(1, len(after) + 1)]
               for d in after.values())
    assert after["list~people~2"]["rev"] == before["list~people~2"]["rev"]


def _store_after_view(store: dict, full: dict, made_at: str) -> dict:
    """The store's `view/list~...` documents once `app.py view` has written `full` over
    `store` ({doc id: fields}): a part kept as it was (app_lists.unchanged), the rest written,
    and the parts the list no longer fills taken off (app_lists.stale), as cmd_view does."""
    out = dict(store)
    for doc_id, doc in app_lists.docs(full, made_at, "r-" + made_at):
        if not app_lists.unchanged(out.get(doc_id), doc):
            out[doc_id] = json.loads(json.dumps(doc))
    for doc_id in app_lists.stale(full, out):
        out.pop(doc_id)
    return out


def test_a_list_that_loses_its_last_part_still_shows_whole_on_the_page():
    """A list that lost its last part with the rest as they were: nothing was written, the
    part was taken off, and every part kept said the old count, so the page looked for the
    part just taken off and "Show" was empty until some other part changed (the review of
    2026-11-11: 10 parts to 9)."""
    import page_parts_js
    if not page_parts_js.node():
        pytest.skip("node is not installed")
    people = _people(1500)
    before = app_lists.docs({"people": people}, "2026-11-10T08:00:00Z", "r1")
    parts = [d["items"] for _, d in before]
    assert len(parts) >= 3
    store = _store_after_view({}, {"people": people}, "2026-11-10T08:00:00Z")
    fewer = [p for part in parts[:-1] for p in part]
    store = _store_after_view(store, {"people": fewer}, "2026-11-10T09:00:00Z")
    assert len([d for d in store if d.startswith("list~people~")]) == len(parts) - 1
    shown = page_parts_js.read(store, lists=["people"])["lists"]["people"]
    assert [p["id"] for p in shown] == [p["id"] for p in fewer]
