"""A prep document says which prep wrote it, so only an out-of-date one is rewritten.

`prep.py --all` rewrote every document whenever the generator changed (hundreds of
files in one contact book, a diff on every one for a changed date line) and wrote
one for every contact in the book, called or not, so run as a check it left a pile
of untracked files behind. Each document now ends on a stamp naming the prep that
wrote it; `--stale-only` rewrites only one an older prep wrote, never creates one,
and `--dry-run` lists what would be written and writes nothing. `--all` stays the
explicit full rewrite. The people are invented, against the example profile.
"""
from __future__ import annotations

import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import prep  # noqa: E402
import schema  # noqa: E402

TODAY = "2026-10-15"
CONTACTS = [
    {"contact_id": "oakmere_castellan", "name": "Juno Castellan", "company": "Oakmere Foods",
     "title": "Data Analyst", "status": "call_booked"},
    {"contact_id": "kestrel_haldane", "name": "Corwin Haldane", "company": "Kestrel Mutual",
     "title": "Head of Data", "status": "in_conversation"},
    {"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran", "company": "Fernhill Freight",
     "title": "Head of Demand Forecasting", "status": "awaiting_reply"},
]


def _book(tmp_path):
    contacts, threads = tmp_path / "c.csv", tmp_path / "t.csv"
    for path, rows, cols in ((contacts, CONTACTS, schema.CONTACT_COLUMNS),
                             (threads, [], schema.THREAD_COLUMNS)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows({c: r.get(c, "") for c in cols} for r in rows)
    return ["--contacts", str(contacts), "--threads", str(threads),
            "--tracker", str(tmp_path / "none.csv"), "--root", str(tmp_path), "--today", TODAY]


def _doc(tmp_path, cid):
    return tmp_path / "documents" / "network" / cid / "prep.md"


def test_a_document_ends_on_the_version_of_prep_that_wrote_it(tmp_path):
    path = prep.write_prep(CONTACTS[0], today=TODAY, root=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    assert text.startswith("# Prep - Juno Castellan, Oakmere Foods")
    # The stamp also says what it was written from (the contact's row and thread), so a
    # change to either makes it stale.
    assert re.fullmatch(r"<!-- prep v%d: tools/network/prep\.py; as of [0-9a-f]{12} -->"
                        % prep.generator_version(), text.rstrip().splitlines()[-1])
    assert prep.stamp_of(text) == prep.generator_version()
    # What is shown is the document; the stamp rides only in the file.
    assert "<!--" not in prep.prep_markdown(CONTACTS[0], today=TODAY)
    assert not prep.stale(path)


def test_only_a_document_an_older_prep_wrote_is_stale():
    assert prep.redo_from() <= prep.generator_version()
    import build_versions
    redo = [v[0] for v in build_versions.METHODS["prep-docs"]["versions"] if v[2]]
    assert prep.redo_from() == max(redo)


def test_stale_only_rewrites_the_old_ones_and_never_writes_a_new_one(tmp_path, capsys):
    args = _book(tmp_path)
    current = prep.write_prep(CONTACTS[0], today="2026-10-01", root=str(tmp_path))
    old = _doc(tmp_path, "kestrel_haldane")
    old.parent.mkdir(parents=True)
    old.write_text("# Prep - Corwin Haldane, Kestrel Mutual\n\nWritten 2026-09-01.\n", encoding="utf-8")
    before = open(current, encoding="utf-8").read()
    assert prep.stale(str(old)) and not prep.stale(current)
    assert not prep.stale(str(_doc(tmp_path, "fernhill_oyelaran")))     # no document at all

    # A check writes nothing and says what would change.
    assert prep.main(["--stale-only", "--dry-run", *args]) == 0
    out = capsys.readouterr().out
    assert "would rewrite documents/network/kestrel_haldane/prep.md" in out
    assert "oakmere_castellan" not in out and "fernhill_oyelaran" not in out
    assert "1 prep documents would be written" in out and "nothing written" in out
    assert "Written 2026-09-01." in old.read_text(encoding="utf-8")

    assert prep.main(["--stale-only", *args]) == 0
    assert "1 prep documents written" in capsys.readouterr().out
    rewritten = old.read_text(encoding="utf-8")
    assert "Written 2026-10-15." in rewritten and prep.stamp_of(rewritten) == prep.generator_version()
    assert open(current, encoding="utf-8").read() == before                # left alone
    assert not _doc(tmp_path, "fernhill_oyelaran").exists()                # never created

    # Run again, nothing is stale and nothing is written.
    assert prep.main(["--stale-only", *args]) == 0
    assert "0 prep documents written" in capsys.readouterr().out


def test_all_is_still_the_full_rewrite_and_its_dry_run_writes_nothing(tmp_path, capsys):
    args = _book(tmp_path)
    assert prep.main(["--all", "--dry-run", *args]) == 0
    out = capsys.readouterr().out
    assert out.count("would write ") == 3 and "3 prep documents would be written" in out
    assert not (tmp_path / "documents").exists()
    assert prep.main(["--all", *args]) == 0
    assert "3 prep documents written" in capsys.readouterr().out
    assert all(_doc(tmp_path, c["contact_id"]).exists() for c in CONTACTS)


def test_a_rewrite_that_would_change_only_the_date_leaves_the_document_alone(tmp_path, capsys):
    # Two chats that each rewrote every prep wrote the same documents a day apart, and every
    # one of them conflicted when the two met.
    args = _book(tmp_path)
    assert prep.main(["--all", *args]) == 0
    capsys.readouterr()
    first = {c["contact_id"]: _doc(tmp_path, c["contact_id"]).read_text(encoding="utf-8")
             for c in CONTACTS}
    later = [a if a != TODAY else "2026-10-16" for a in args]
    assert prep.main(["--all", *later]) == 0
    out = capsys.readouterr().out
    assert all(_doc(tmp_path, cid).read_text(encoding="utf-8") == text
               for cid, text in first.items())
    assert "0 prep documents written" in out and "3 already current" in out
    # A real change to one contact still rewrites that one, with the new date, and a prep
    # asked for one contact is written, date and all.
    path = prep.write_prep(dict(CONTACTS[2], status="in_conversation"), today="2026-10-16",
                           root=str(tmp_path), keep_if_same=True)
    assert "Written 2026-10-16." in open(path, encoding="utf-8").read()
    one = prep.write_prep(CONTACTS[0], today="2026-10-17", root=str(tmp_path))
    assert "Written 2026-10-17." in open(one, encoding="utf-8").read()
