"""`state.py` leads with what is owed now, says old replies in one line, and puts the employer
pairs that may be one first.

The audit of 2026-11-10 (DW-4) found its OWED list running to about 590 lines, 141 of them
"owed over 45 days", the four current items at lines 80 to 83, and "1249bd" never explained.
The possible employer pairs (JOINS) came at the foot of the dump (PD-23). Every person and
employer is invented.
"""
from __future__ import annotations

import csv
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import schema  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 11, 10)


def _write(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def test_the_current_item_comes_first_and_fifty_old_ones_are_one_line(tmp_path, capsys):
    contacts, threads = [], []
    for i in range(50):
        cid = f"zephyr_dental_{i}"
        contacts.append({"contact_id": cid, "name": f"Old Person{i}", "company": "Zephyr Dental",
                         "status": "replied_needs_response"})
        threads.append({"contact_id": cid, "date": "2023-02-01", "direction": "in",
                        "channel": "message", "summary": "an old reply",
                        "full_text": "Thanks for getting in touch."})
    contacts.append({"contact_id": "quayside_foods_ivo", "name": "Ivo Marsh",
                     "company": "Quayside Foods", "status": "replied_needs_response"})
    threads.append({"contact_id": "quayside_foods_ivo", "date": "2026-11-09", "direction": "in",
                    "channel": "message", "summary": "a reply", "full_text": "Happy to talk."})
    cp, tp, kp = (str(tmp_path / n) for n in ("c.csv", "t.csv", "k.csv"))
    _write(cp, schema.CONTACT_COLUMNS, contacts)
    _write(tp, schema.THREAD_COLUMNS, threads)
    _write(kp, ["date", "company", "role", "status"],
           [{"date": "2026-11-01", "company": "Quayside", "role": "Planner", "status": "applied"}])
    state.main(["--contacts", cp, "--threads", tp, "--tracker", kp, "--today", TODAY.isoformat()])
    out = capsys.readouterr().out
    lines = out.splitlines()
    owed = lines.index("OWED")
    assert "Ivo Marsh" in lines[owed + 1], lines[owed:owed + 3]
    assert "bd " not in out and "working days" in lines[owed + 1], lines[owed + 1]
    block = lines[owed:lines.index("", owed) if "" in lines[owed:] else len(lines)]
    older = [x for x in block if "Old Person" in x]
    assert older == [], older[:3]
    assert any("50 more owed over" in x for x in lines[owed:owed + 4]), lines[owed:owed + 4]
    joins = next(i for i, x in enumerate(lines) if x.startswith("JOINS"))
    assert joins < owed, (joins, owed)
    # Every one, on asking.
    state.main(["--contacts", cp, "--threads", tp, "--today", TODAY.isoformat(), "--all"])
    lines = capsys.readouterr().out.splitlines()
    owed = lines.index("OWED")
    block = lines[owed:lines.index("", owed) if "" in lines[owed:] else len(lines)]
    assert sum("Old Person" in x for x in block) == 50
