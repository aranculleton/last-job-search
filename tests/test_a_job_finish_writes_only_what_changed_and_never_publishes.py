"""A job's finish writes only what the job changed, and never publishes the page (issue 254).

A chat on the person's computer finished a "Find people" job, eight notes drafted and checked,
and the notes reached the page some twenty minutes later. Two things took the time.

The page update after the job (`app.py view --work`) rewrote most of a long People section for
eight new people. Each item carries its links to everything else at its employer (`related`,
app_lists.link), so a new note at an employer changed the record of every colleague there, and
those colleagues sit all through the section. On an invented search of 1,500 contacts, eight
new people rewrote all 34 parts of People and 48 records in all, 3.2 MB in six batches. The
links are now kept apart from the items, in records cut by employer (`view/links~<n>`,
app_lists.links_docs), and the page puts them back on the items it reads (templates/app/app.js
withLinks); a part is cut where its own item says, never after a minimum that moved every later
cut; and the addresses are kept in records whose count holds. The same finish is now 18
records, 0.5 MB, in one batch.

And the same update told the chat on the computer to republish the page: every `view` whose
copy recorded the page as a version behind its code said "republish it now" (page_code_behind),
a job's finish too, and a copy's record lags whenever the chat that answers the page published
from a copy this one has not taken yet. From the Mac the publish, after a read of the page
itself, ran for over twenty minutes, the notes waiting behind it. The page's own record
(`meta/now` `page`, never lowered) now counts as well, and a job's finish never publishes: where
the page's code really is behind, it asks the chat that answers the page, in one small batch.

The page's database is the folder test_one_chat_answers_the_page.py keeps with the real one's
rules. Every person, employer and chat here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
import build_versions  # noqa: E402
import test_one_chat_answers_the_page as one  # noqa: E402
from test_a_page_from_4_2_moves_to_its_new_names import read  # noqa: E402

BEFORE = "2026-10-25T17:00:00Z"
NOW = "2026-10-25T18:00:00Z"
LISTENER = "cloud-juno"
MAC = "mac-job-1"
JOB = "network~people~1"
PAGE_READS = ("screen", "meta", "addr", "work", "holds", "beats")
FIRMS = [f"{a.title()} {b.title()}" for a in app_state.FIRM for b in app_state.KIND]


@pytest.fixture
def search(tmp_path):
    """A big invented search whose page the chat that answers it has drawn, and a network job
    a chat on the computer is running."""
    c = one.Copy(tmp_path)
    c.page(current=True)
    app_state.large(c.state, tracker_rows=60, contacts=400, threads=800)
    _put(c, "work", JOB, {"kind": "network", "status": "running", "to": "computer",
                          "title": "Find people", "args": {"count": 8},
                          "asked_at": BEFORE, "claimed_by": MAC, "claimed_at": BEFORE,
                          "run_by": MAC, "lease_until": "2026-10-25T19:00:00Z"}, 2)
    out = _view(c, "first", LISTENER, at=BEFORE)
    assert c.send("\n".join(out["batches"])), "the first drawing was refused"
    yield c
    sys.path.remove(c.root)


def _put(c, coll, doc_id, fields, version):
    os.makedirs(os.path.join(c.db, coll), exist_ok=True)
    with open(os.path.join(c.db, coll, doc_id + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"data": dict(fields, _v=version), "version": version}, fh)


def _view(c, name, chat, *more, at=NOW):
    d = read(c, os.path.join(c.root, name + "-read"), PAGE_READS)
    return json.loads(c.run("view", os.path.join(c.root, name + "-out"), "--dump", d,
                            "--now", at, "--chat", chat, *more))


def _store(c):
    """{collection/doc id: (version, the record's text)} for the whole page's database."""
    out = {}
    for coll in os.listdir(c.db):
        folder = os.path.join(c.db, coll)
        if coll.startswith(".") or not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                doc = json.load(fh)
            out[f"{coll}/{name[:-5]}"] = (doc["version"], json.dumps(doc["data"]))
    return out


def _new_people(c, n=8):
    """The job's people: `n` invented contacts, each at an employer the search already holds
    people at, each with a first note drafted. Their ids."""
    path = os.path.join(c.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    cols = list(rows[0].keys())
    ids = []
    for i in range(n):
        firm = FIRMS[i * 9 % len(FIRMS)]
        cid = f"found_{i}_{firm.lower().replace(' ', '_')}"
        ids.append(cid)
        rows.append(dict.fromkeys(cols, "") | {
            "contact_id": cid, "name": f"Wren Vane{i}", "title": "Head of Data",
            "company": firm, "company_key": firm.lower(),
            "linkedin_url": f"https://www.linkedin.com/in/example-found-{i}", "tier": "2",
            "route": "cold", "status": "not_contacted", "next_action": "Send the note",
            "notes": "example contact"})
        folder = os.path.join(c.state, "documents", "network", cid)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "draft.md"), "w", encoding="utf-8") as fh:
            fh.write(f"Hi Wren, hope you're well. I work in demand forecasting in Manchester. "
                     f"I'd love to hear how the analytics team at {firm} works.\n")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return ids


def test_finishing_a_network_job_writes_only_its_people_their_notes_and_the_counts(search):
    c = search
    ids = _new_people(c)
    before = _store(c)
    # The job's own finish, then the page brought up to date from this copy (job_steps).
    done = json.loads(c.run("done", read(c, os.path.join(c.root, "done-read"), PAGE_READS),
                            "--work", JOB, "--chat", MAC, "--kind", "computer",
                            "--summary", "Eight people found, each with a note.", "--drafted", str(len(ids)),
                            "--now", NOW))
    assert c.send("\n".join(done["batches"]))
    out = _view(c, "finish", MAC, "--work", JOB)
    assert len(out["batches"]) == 1, "the finish fits in one batch"
    assert c.send("\n".join(out["batches"]))
    after = _store(c)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    # Every record written holds one of the job's people or their notes, or is a count, the
    # job's own item, or the line saying the computer was at work (Settings, `where`).
    counts = {"screen/people", "screen/messages", "screen/lists", "screen/people_count",
              "screen/message_budget", "screen/where", "meta/now", f"work/{JOB}"}
    unrelated = [k for k in changed if k not in counts and k in after
                 and not any(cid in after[k][1] for cid in ids)]
    assert unrelated == [], f"{len(unrelated)} of {len(changed)} records written hold none of " \
                            f"the job's people: {unrelated}"
    assert not [k for k in changed if k not in after], "nothing taken off"
    # The parts of the long People section that hold none of them were left as they were.
    parts = [k for k in after if k.startswith("screen/part~people~")]
    assert len(parts) > 4 and len([k for k in changed if k in parts]) <= 3, changed


def test_the_page_puts_back_each_items_links_as_the_engine_made_them(search):
    """The links kept apart are the engine's own: the page, reading the store, draws on each
    item exactly the `related` (and `people_more`) the model gave it."""
    import page_parts_js
    if not page_parts_js.node():
        pytest.skip("node is not installed")
    c = search
    _new_people(c)
    out = _view(c, "second", LISTENER)
    assert c.send("\n".join(out["batches"]))
    views = {k[len("screen/"):]: json.loads(text) for k, (_, text) in _store(c).items()
             if k.startswith("screen/")}
    assert any(k.startswith("links~") for k in views), "the links are kept apart"
    assert not any('"related"' in json.dumps(v) for k, v in views.items()
                   if k.startswith("part~people~")), "and out of the people's own records"
    names = ("jobs", "ready", "messages", "people", "interviews", "applications", "referrals",
             "due")
    got = page_parts_js.read(views, sections=names, linked=True)["sections"]
    model = json.loads(c.run("model", "--now", NOW))

    def items(section, value):
        return (value or {}).get("rows") or [] if section == "jobs" else value or []
    linked = 0
    for name in names:
        want = {it["id"]: (it.get("related"), it.get("people_more"))
                for it in items(name, model.get(name))}
        drawn = {it["id"]: (it.get("related"), it.get("people_more"))
                 for it in items(name, got[name])}
        assert drawn == want, name
        linked += sum(1 for rel, _more in want.values() if rel)
    assert linked > 100, "the search has links to draw"


def test_a_jobs_finish_never_publishes_the_page_when_its_build_is_unchanged(search):
    """The chat that answers the page published this version from a copy this one has not
    taken yet: the page's own record says so, and the finish publishes nothing."""
    c = search
    _new_people(c)
    current = build_versions.current("page")
    _page_at(c, current - 1, held=current)
    out = _view(c, "finish", MAC, "--work", JOB)
    said = "\n".join(out.get("for_claude") or [])
    assert "app.py page" not in said and "republish" not in said.lower(), said
    assert not [p for p in out["batches"] if os.path.basename(p).startswith("republish")]
    assert c.send("\n".join(out["batches"]))
    # The page's own record of its version is never taken back by a copy behind it.
    with open(os.path.join(c.db, "meta", "now.json"), encoding="utf-8") as fh:
        assert json.load(fh)["data"]["page"] == current


def _page_at(c, recorded, held):
    """This copy records the page published at version `recorded`; the page's own record
    (meta/now `page`) says `held`."""
    path = os.path.join(c.profile, "build_versions.json")
    with open(path, encoding="utf-8") as fh:
        got = json.load(fh)
    got["page"] = {"version": recorded, "date": "2026-10-24"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(got, fh)
    path = os.path.join(c.db, "meta", "now.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["data"]["page"] = held
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def test_a_jobs_finish_asks_the_chat_that_answers_the_page_when_its_code_is_behind(search):
    """The page's code really is behind this copy's: the finish still writes its records and
    publishes nothing itself. One small batch asks the chat that answers the page, which
    publishes it from the cloud."""
    c = search
    _new_people(c)
    behind = build_versions.current("page") - 1
    _page_at(c, behind, held=behind)
    out = _view(c, "finish", MAC, "--work", JOB)
    said = "\n".join(out.get("for_claude") or [])
    assert "app.py page" not in said and "Artifact" not in said, said
    asked = [p for p in out["batches"] if os.path.basename(p).startswith("republish")]
    assert asked and out["batches"][-1] == asked[0], out["batches"]
    assert c.send("\n".join(out["batches"]))
    wid = f"republish~v{build_versions.current('page')}"
    assert os.path.exists(os.path.join(c.db, "work", wid + ".json"))
    # The chat that answers the page, with no job of its own to finish, still publishes it.
    out = _view(c, "listener", LISTENER)
    assert "app.py page" in "\n".join(out.get("for_claude") or [])
