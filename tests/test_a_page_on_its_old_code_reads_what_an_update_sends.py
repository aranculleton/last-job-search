"""A page still on its old code reads what a page update sends it, until it is republished.

An update brings the page's new code to the copy at once, but to the published page only with
its republish, which `app.py view` asks for after its own batches (`page_code_behind`). A page
update now writes each part of a big section or a whole list under a name for what it holds,
joined by what the newest part lists (the second audit, D6), which the page's code before then
cannot join: it joins only parts that carry the head's own rev. For the minutes between the
update and the republish, a fresh load of that page showed big sections and every "Show" list
blank (the review of 2026-11-11). So while the published page's code is from before it joins
parts that way, a page update writes them as that code reads them, and the new code reads both.

The old code below is the page's own joining of parts, word for word as published pages before
it ran it. Every person and employer here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
import build_versions  # noqa: E402
import page_db  # noqa: E402
import page_parts_js  # noqa: E402

# templates/app/app.js's joined() and fullList() as every page published before the page's
# parts were joined by what each holds (app_page.JOINS_BY_HOLD) runs them.
OLD_PAGE_JS = """
  function joined(k, v) {
    const kept = joinedKept.get(k);
    if (kept && kept.rev === v.rev) return kept.data;
    let text = "";
    for (let i = 1; i <= Number(v.in_parts); i++) {
      const p = S.views.get("part~" + k + "~" + i);
      if (!p || p.rev !== v.rev || typeof p.text !== "string") return kept ? kept.data : undefined;
      text += p.text;
    }
    try { const data = JSON.parse(text); joinedKept.set(k, {rev: v.rev, data}); return data; } catch (e) { return kept ? kept.data : undefined; }
  }
  function fullList(name) {
    const docs = [];
    for (const [k, v] of S.views) if (k.indexOf("list~" + name + "~") === 0) docs.push(obj(v));
    if (!docs.length) return [];
    let newest = docs[0];
    for (const d of docs) if (txt(d.made_at) > txt(newest.made_at)) newest = d;
    const parts = Number(newest.parts) || 0;
    if (!parts) return docs.flatMap((d) => arr(d.items).filter(Boolean));
    const byPart = new Map(docs.filter((d) => txt(d.rev) === txt(newest.rev)).map((d) => [Number(d.part), d]));
    const kept = fullKept.get(name);
    for (let i = 1; i <= parts; i++) if (!byPart.has(i)) return kept ? kept.items : [];
    if (kept && kept.rev === txt(newest.rev) && kept.parts === parts) return kept.items;
    const items = [];
    for (let i = 1; i <= parts; i++) for (const it of arr(byPart.get(i).items)) if (it) items.push(it);
    fullKept.set(name, {rev: txt(newest.rev), parts, items});
    return items;
  }
"""


def _since() -> int:
    import app_page
    return next(v[0] for v in build_versions.METHODS["page"]["versions"]
                if app_page.JOINS_BY_HOLD in v[3])


def _copy(tmp_path, page_version: int) -> tuple[str, str]:
    """(state, profile): a big invented search whose page is published, at `page_version`."""
    state = app_state.large(str(tmp_path / "state"), tracker_rows=200, contacts=1200,
                            threads=1500)
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(profile, "app.json"), "w", encoding="utf-8") as fh:
        json.dump({"url": "https://claude.ai/code/artifact/example-old-page"}, fh)
    path = os.path.join(profile, "build_versions.json")
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    rec["page"] = {"date": "2026-11-01", "version": page_version}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return state, profile


def _view(tmp_path, state, profile, name) -> dict:
    """{doc id: fields} of the screens one `app.py view` writes, with no read of the store."""
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY="private")
    env.pop("CLAUDE_CODE_REMOTE", None)
    args = [sys.executable, os.path.join(ROOT, "tools", "app.py"), "view",
            str(tmp_path / name), "--now", app_state.NOW]
    r = subprocess.run(args, env=env, capture_output=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    got = {}
    for b in json.loads(r.stdout)["batches"]:
        with open(b, encoding="utf-8") as fh:
            for e in json.load(fh):
                if e["collection"] == "screen" and e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as fh2:
                        got[e["doc_id"]] = json.load(fh2)
    return got


def test_a_page_still_on_its_old_code_reads_what_an_update_sends_it(tmp_path):
    if not page_parts_js.node():
        pytest.skip("node is not installed")
    state, profile = _copy(tmp_path, _since() - 1)
    sent = _view(tmp_path, state, profile, "v1")
    assert "people" in sent and sent["people"].get("in_parts", 0) >= 2
    lists = sorted({d.split("~")[1] for d in sent if d.startswith("list~")})
    assert "people" in lists and len([d for d in sent if d.startswith("list~people~")]) >= 2
    whole = {d: {"data": b} for d, b in sent.items()}
    section = page_db.joined(whole, "people")
    full = {n: [it for i in range(1, 99) for it in (sent.get(f"list~{n}~{i}") or {})
                .get("items", [])] for n in lists}
    # The page on its old code: every big section and every whole list is there.
    old = page_parts_js.read(sent, sections=["people"], lists=lists, js=OLD_PAGE_JS)
    assert old["sections"]["people"] == section and section, "the old page's People was blank"
    for n in lists:
        assert old["lists"][n] == full[n] and full[n], n
    # The new code reads it too: a republish that lands later finds the store readable.
    new = page_parts_js.read(sent, sections=["people"], lists=lists)
    assert new["sections"]["people"] == section and all(new["lists"][n] == full[n] for n in lists)
    # Republished: the page's code joins by what each part holds, and an update writes that.
    state_rec = os.path.join(profile, "build_versions.json")
    with open(state_rec, encoding="utf-8") as fh:
        rec = json.load(fh)
    rec["page"]["version"] = _since()
    with open(state_rec, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    after = _view(tmp_path, state, profile, "v2")
    assert after["people"].get("part_revs"), "the new shape once the page reads it"
    store = dict(sent, **after)
    new = page_parts_js.read(store, sections=["people"], lists=lists)
    assert new["sections"]["people"] == section


def test_only_one_page_version_says_its_parts_are_joined_by_what_they_hold():
    """The version that tells the page's code apart is found by its own words, so it holds
    when the versions are numbered again."""
    import app_page
    assert len([v for v in build_versions.METHODS["page"]["versions"]
                if app_page.JOINS_BY_HOLD in v[3]]) == 1
