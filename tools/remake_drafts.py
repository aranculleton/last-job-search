#!/usr/bin/env python3
"""Every application not yet sent made again by the current build, and each that fails its
checks given its own way forward, by code.

The `drafts` method (tools/build_versions.py) used to be a sentence for a background agent:
render each unsent draft again, check them, record the method. One night it made 17 again,
3 cover letters still failed for copying the posting word for word, and the method was
recorded done anyway, with no redraft and no To do card for the three: they sat failing
until someone noticed (the maintainer, 2026-11-05). So this does all of it:

- An application counts as made by a version only once it has passed its checks at it: its
  own verify.json (written by tools/verify_batch.py on every check, with the drafts version
  it ran under) says so. One made by a version since the last that asks for a rerun is left
  alone; nothing is made twice.
- Each that fails is handed its way forward, recorded beside it in remake.json:
    redraft  every failing part is a part of the letter or the summary that copies the
             posting: a tweak is queued for just those parts ("Redo only" the opening, the
             close..., "Summary words"), the path the page's own Tweak box takes, with both
             audits after. tools/app.py view puts it on the page's work list by itself.
    todo     anything else, which only the person can settle (a page too long, a claim the
             profile does not hold): one To do card naming it, with "Make it again".
- The drafts version is recorded for the repo only when every unsent application has
  passed at it. Until then the upgrade is not listed again for the ones already handed
  their way forward; once their redraft passes, the next run records it.
- A tracker row an earlier version wrote naming a cover letter for a draft with none is put
  right on the same run.
- It prints one plain line for the person, at most, and that only when something did not
  pass.

    python3 tools/remake_drafts.py            # make them again, hand off what fails, record
    python3 tools/remake_drafts.py --json     # the same, with what happened as JSON
    python3 tools/remake_drafts.py --pending  # exit 1 while there is something to do
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METHOD = "drafts"
VERIFY = "verify.json"
REMAKE = "remake.json"
# The parts a redraft can rewrite alone (tools/tweak.py: L4 "Redo only", R8 the summary).
REDO_ONLY = ("p1", "p2", "cl_bullets", "p4")
# audit_letters.posting_copies names each part as a reader would: back to the field.
_WHERE = {"the resume summary": "summary", "the opening": "p1", "the company paragraph": "p2",
          "the line before the bullets": "lead", "the close": "p4"}
_COPIES = re.compile(r"copies the posting word for word")


# ------------------------------------------------------------------ what there is

def rerun_version() -> int:
    """The newest drafts version that asks for what an older one made to be made again."""
    import build_versions as B
    return max([v[0] for v in B.METHODS[METHOD]["versions"] if v[2]] or [1])


def _json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _tracker_path() -> str:
    return person.state("job_search_tracker.csv")


def unsent() -> list[dict]:
    """[{"id", "row", "folder", "draft"}]: each tracker row not yet sent that has a kept
    draft.json, with the id the page knows it by (app_model.tracker_ids)."""
    import app_model
    import csv_store
    import outreach
    import throttle
    rows = csv_store.read_rows(_tracker_path())
    out = []
    for row, rid in zip(rows, app_model.tracker_ids(rows)):
        if app_model._status(row) not in throttle.UNSENT:
            continue
        folder = outreach.app_folder(row.get("company"), row.get("role") or "")
        draft = os.path.join(folder, "draft.json")
        if os.path.isfile(draft):
            out.append({"id": rid, "row": row, "folder": folder, "draft": draft})
    return out


def made_at(folder: str) -> tuple[int, bool]:
    """(the drafts version this application was last checked under, whether it passed).
    A verify.json from before the version was kept on it reads as 0: never checked by this
    method."""
    got = _json(os.path.join(folder, VERIFY), {}) or {}
    try:
        version = int(got.get(METHOD) or 0)
    except (TypeError, ValueError):
        version = 0
    return version, bool(got.get("passed", not got.get("flags"))) if version else False


def handed(folder: str) -> dict:
    """The way forward a run gave this application (remake.json), or {}."""
    got = _json(os.path.join(folder, REMAKE), {}) or {}
    return got if isinstance(got, dict) else {}


def due(apps=None) -> list[dict]:
    """The unsent applications this run makes again: not checked and passed under the newest
    rerun version, and not already handed their way forward for it."""
    want = rerun_version()
    out = []
    for a in unsent() if apps is None else apps:
        version, passed = made_at(a["folder"])
        if version >= want and passed:
            continue
        if int(handed(a["folder"]).get("version") or 0) >= want:
            continue
        out.append(a)
    return out


def all_passed(apps=None) -> bool:
    want = rerun_version()
    return all(made_at(a["folder"])[0] >= want and made_at(a["folder"])[1]
               for a in (unsent() if apps is None else apps))


def pending() -> str:
    """Why the drafts method still has work in this repo, or "": something to make again,
    or every application passed and the version not yet recorded."""
    import build_versions as B
    if not B.behind(METHOD):
        return ""
    apps = unsent()
    if due(apps):
        return "due"
    return "record" if all_passed(apps) else ""


# ------------------------------------------------------------------ making and checking

def _tool(*args) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def has_latex() -> bool:
    """A LaTeX engine on this computer, as tools/app_setup.py asks."""
    import shutil
    return bool(shutil.which("lualatex") or shutil.which("xelatex"))


def render(draft_path: str) -> tuple[int, str]:
    """The application made again from its kept draft.json, as the person's own remake is.
    3 on a computer with no LaTeX: nothing could be made, which is neither a pass nor a
    finding to hand on, so it is tried again on the next run (on a computer that has it)."""
    if not has_latex():
        return 3, "no LaTeX on this computer"
    return _tool(os.path.join(ROOT, "tools", "fit_to_page.py"), draft_path)


def check(draft_path: str) -> tuple[int, str]:
    """Every check an application gets (tools/verify_batch.py), which writes its verify.json:
    0 passed, 1 a finding, 3 a check could not run (which is not a pass)."""
    return _tool(os.path.join(ROOT, "tools", "verify_batch.py"), draft_path)


def _kept(draft_path: str) -> dict:
    """The kept draft object, as draft.json holds it (one object in a list)."""
    got = _json(draft_path, [])
    got = got[0] if isinstance(got, list) and got else got
    return got if isinstance(got, dict) else {}


def _loaded(draft_path: str) -> dict:
    import fit_to_page
    apps, _read_in = fit_to_page.load(draft_path)
    return apps[0] if apps and isinstance(apps[0], dict) else {}


def copied_parts(d: dict) -> list[str]:
    """The fields of the summary and the letter that copy the posting word for word."""
    import audit_letters
    import docpaths
    out = []
    for where, _run in audit_letters.posting_copies(d):
        field = _WHERE.get(where) or ("cl_bullets" if where.endswith("bullet") else "")
        if field and (field == "summary" or docpaths.writes_letter(d)):
            out.append(field)
    return list(dict.fromkeys(out))


def letter_flags(d: dict, batch=None) -> list[str]:
    """What the letters check finds on this application's letter, as verify_batch's run of
    it does (tools/audit_letters.py): [] for a resume alone."""
    import audit_letters
    import docpaths
    if not docpaths.writes_letter(d):
        return []
    try:
        flags, words = audit_letters.audit(d, batch or [d])
    except FileNotFoundError:
        # No compiled letter to read the page's own flags off: the draft's, which hold every
        # part that copies the posting.
        import fit_to_page
        flags, words = audit_letters.draft_flags(d, batch or [d]), fit_to_page.body_words(d)
    if words > audit_letters.MAX_BODY_WORDS:
        flags.append(f"{words} body words, over the {audit_letters.MAX_BODY_WORDS} cap")
    return flags


def way_forward(d: dict, folder: str) -> dict:
    """{"way": "redraft", "changes": [...]} when every failing part is one a redraft of that
    part alone puts right, else {"way": "todo"}; with "why" in plain words either way."""
    import app_model
    verify = app_model.verify_items(folder) or {}
    other = [i["said"] for i in verify.get("items") or [] if not i.get("ok")]
    flags = letter_flags(d)
    copies = copied_parts(d)
    beyond = [f for f in flags if not _COPIES.search(f)]
    names = {"summary": "the summary", "p1": "the opening", "p2": "the company paragraph",
             "cl_bullets": "the bullets", "p4": "the close", "lead": "the line before the bullets"}
    redo = [f for f in copies if f in REDO_ONLY]
    if copies and not beyond and not _beyond_letters(other) and \
            all(f in REDO_ONLY or f == "summary" for f in copies):
        # One tweak per document: the letter's parts (L4), the resume's summary (R8).
        tweaks = ([{"output": "letter", "changes": [{"p": "L4", "v": redo}]}] if redo else []) + \
            ([{"output": "resume", "changes": [{"p": "R8", "v": "plainer"}]}]
             if "summary" in copies else [])
        parts = " and ".join(names[f] for f in copies)
        return {"way": "redraft", "tweaks": tweaks,
                "why": f"{parts} copied the posting word for word"}
    said = other + [f.split(":")[0] for f in beyond] + \
        [f"{names.get(f, f)} copies the posting word for word" for f in copies]
    return {"way": "todo", "why": "; ".join(dict.fromkeys(said)) or "a check did not pass"}


def _beyond_letters(said: list) -> bool:
    """A finding on the page's record other than the letters check's own."""
    import app_model
    letters = app_model.VERIFY_WORDS.get("LETTERS")
    return any(s != letters for s in said)


def work_id(app_id: str, output: str, version: int) -> str:
    """A redraft's work item id: one per application, document and version, so each is
    queued once however often the page is brought up to date."""
    import page_db
    return page_db.safe_id(f"tweak~remade-{app_id}-{output}-v{version}")


def queued_work(app: dict, way: dict, version: int) -> list[dict]:
    """The tweak work items for a redraft, as the page's own Tweak box writes them: target
    the application's card, the document, and the changes (tools/tweak.py)."""
    company = str(app["row"].get("company") or "")
    return [{"id": work_id(app["id"], t["output"], version), "kind": "tweak",
             "title": f"Rewrite what copies the posting: {company}"[:140],
             "args": {"target": {"id": app["id"], "output": t["output"], "rev": ""},
                      "changes": t["changes"], "text": "", "remade": version}}
            for t in way.get("tweaks") or []]


# ------------------------------------------------------------------ the tracker

def letters_put_right(apps=None) -> list[str]:
    """Clear `cover_letter_file` on each unsent row whose kept draft writes no letter (a
    resume alone, a letterless draft an earlier version still named one for). Returns
    "<employer> | <role>" for each row changed."""
    import csv_store
    import docpaths
    path = _tracker_path()
    if not os.path.isfile(path):
        return []
    bare = {(a["row"].get("date"), a["row"].get("company"), a["row"].get("role"))
            for a in (unsent() if apps is None else apps)
            if not docpaths.writes_letter(_kept(a["draft"]))}
    rows = csv_store.read_rows(path)
    changed = []
    for r in rows:
        if (r.get("date"), r.get("company"), r.get("role")) in bare and \
                str(r.get("cover_letter_file") or "").strip():
            r["cover_letter_file"] = ""
            changed.append(f"{r.get('company')} | {r.get('role')}")
    if changed:
        import record_drafts
        csv_store.write_rows(path, rows, record_drafts.HEADER)
    return changed


# ------------------------------------------------------------------ the run

def run(today: str | None = None) -> dict:
    """Make every due application again, hand each that fails its way forward, put the
    tracker right, and record the version when everything passed."""
    import build_versions as B
    version = B.current(METHOD)
    apps = unsent()
    out = {"made": [], "passed": [], "redraft": [], "todo": [], "unchecked": [],
           "tracker": letters_put_right(apps), "recorded": False, "say": ""}
    for a in due(apps):
        name = f"{a['row'].get('company')} | {a['row'].get('role')}"
        rc, _said = render(a["draft"])
        if rc != 3:
            out["made"].append(name)
        if rc == 0:
            rc, _said = check(a["draft"])
        if rc == 3:
            # A check that could not run (or no LaTeX to make it with) is not a pass, nor a
            # fault to hand on: tried again on the next run, where it can.
            out["unchecked"].append(name)
            continue
        if rc == 0:
            out["passed"].append(name)
            try:
                os.remove(os.path.join(a["folder"], REMAKE))
            except OSError:
                pass
            continue
        way = way_forward(_loaded(a["draft"]), a["folder"])
        record = {"version": version, "date": today or dt.date.today().isoformat(), **way}
        if way["way"] == "redraft":
            record["work"] = queued_work(a, way, version)
            out["redraft"].append(name)
        else:
            out["todo"].append(name)
        with open(os.path.join(a["folder"], REMAKE), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(record, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    if all_passed(apps):
        B.record([METHOD], today=today)
        out["recorded"] = True
    out["say"] = say(out)
    return out


def say(out: dict) -> str:
    """The one line the person hears, or "" when everything passed."""
    if not (out["redraft"] or out["todo"]):
        return ""
    n = len(out["made"])
    bits = []
    if out["redraft"]:
        k = len(out["redraft"])
        bits.append(f"{k} {'is' if k == 1 else 'are'} being rewritten where "
                    f"{'it' if k == 1 else 'they'} copied the posting")
    if out["todo"]:
        k = len(out["todo"])
        bits.append(f"{k} {'needs' if k == 1 else 'need'} you, in To do")
    return (f"Made {n} unsent application{'' if n == 1 else 's'} again with the newest checks: "
            + " and ".join(bits) + ".")


# ------------------------------------------------------------------ for the page

def page_work(db: dict | None = None) -> list[dict]:
    """The redrafts runs handed out that are not on the page's work list yet and still
    fail: what tools/app.py view queues, each once (its id is fixed)."""
    have = set(((db or {}).get("work") or {}))
    out = []
    for a in unsent():
        rec = handed(a["folder"])
        if rec.get("way") != "redraft":
            continue
        version, passed = made_at(a["folder"])
        if passed and version >= int(rec.get("version") or 0):
            continue
        out += [w for w in rec.get("work") or [] if isinstance(w, dict) and w.get("id")
                and w["id"] not in have]
    return out


def page_writes(db: dict | None, out_dir: str, now: dt.datetime) -> list[str]:
    """The batch that queues each redraft page_work lists, as creates of their own (the
    store refuses a create for an id it holds, so nothing is queued twice), or []. What
    tools/app.py view sends beside the screens."""
    import page_db
    jobs = page_work(db)
    if not jobs:
        return []
    w = page_db.Writes(out_dir)
    for job in jobs:
        w.add("set", "work", job["id"], page_db.queued(job["kind"], job["title"], job["args"],
                                                       now), if_version=None)
    return w.save("remade")


def todo_cards() -> list[dict]:
    """[{"id", "app", "company", "role", "why", "version"}] for each unsent application a
    run handed to the person (remake.json way "todo") that has not passed since."""
    out = []
    for a in unsent():
        rec = handed(a["folder"])
        if rec.get("way") != "todo":
            continue
        version, passed = made_at(a["folder"])
        if passed and version >= int(rec.get("version") or 0):
            continue
        out.append({"id": f"q-remade-{a['id']}", "app": a["id"],
                    "company": str(a["row"].get("company") or ""),
                    "role": str(a["row"].get("role") or ""), "why": str(rec.get("why") or ""),
                    "version": int(rec.get("version") or 0)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    if a.pending:
        why = pending()
        print(why or "nothing to do")
        return 1 if why else 0
    got = run(a.today)
    if a.json:
        print(json.dumps(got, indent=1, ensure_ascii=False))
    elif got["say"]:
        print(got["say"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
