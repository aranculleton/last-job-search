#!/usr/bin/env python3
"""A document sent to the person, under a name that says whose it is.

Every prep document is kept under a fixed name in a folder of its own
(documents/applications/<employer>_<role>/interview_prep.md, documents/network/<contact>/prep.md),
which every tool, and every employer chat's stored prompt, reads by that name. Sent as it
is, each one arrived as "interview_prep.md" or "prep.md", and two employers' documents
looked the same in the chat (a person's report, 2026-10-22). So what is sent is a copy
named for the person: "Fernhill Freight Demand Planner interview prep.md", "Wren Allard
(Fernhill Freight) call prep.md". The copy goes in documents/to_send/, which git ignores
and every send writes again: the kept file stays the record.

    python3 tools/shown.py <document>...    # prints each copy's path: send that file
"""
from __future__ import annotations

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "network")]

import person  # noqa: E402

OUT = ("documents", "to_send")

# A file name the tools write, by what it is to the person.
LABELS = {
    "interview_prep": "interview prep",
    "prep": "call prep",
    "outcome": "interview record",
    "screening_answers": "form answers",
    "outreach": "outreach note",
    "job_posting": "posting",
}
# A requisition number is the employer's filing, not a name: "Data Scientist II (R_1506034)".
_REQ = re.compile(r"\s*[(\[][^)\]]*\d[^)\]]*[)\]]")
# What no file name on any computer may hold.
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _clean(text) -> str:
    text = _BAD.sub(" ", _REQ.sub("", str(text or "")))
    return re.sub(r"\s+", " ", text).strip(" .-")[:120].strip()


def _words(stem) -> str:
    return re.sub(r"[_\s]+", " ", stem).strip()


def _label(stem) -> str:
    if stem in LABELS:
        return LABELS[stem]
    m = re.match(r"interview_prep_(.+)$", stem)
    if m:
        return "%s interview prep" % _words(m.group(1))
    return _words(stem)


def _application(folder_name, root) -> tuple:
    """(company, role) of the tracker row whose folder this is, or ("", "")."""
    tracker = os.path.join(root, "job_search_tracker.csv")
    if not os.path.exists(tracker):
        return "", ""
    import csv

    import outreach
    with open(tracker, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in reversed(rows):
        company, role = (r.get("company") or "").strip(), (r.get("role") or "").strip()
        if company and os.path.basename(outreach.app_folder(company, role)) == folder_name:
            return company, role
    return "", ""


def _contact(contact_id, root) -> tuple:
    """(name, company) of the contact with this id, or ("", "")."""
    book = os.path.join(root, "network_contacts.csv")
    if not os.path.exists(book):
        return "", ""
    import state
    for c in state.load_contacts(book):
        if (c.get("contact_id") or "").strip() == contact_id:
            return (c.get("name") or "").strip(), (c.get("company") or "").strip()
    return "", ""


def name_for(path, root=None) -> str:
    """The name the person sees for this document, without its extension. `root` is the
    person's files (person.state() unless a tool was given another)."""
    root = os.path.abspath(root or person.state())
    rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
    parts = rel.split("/")
    stem = os.path.splitext(parts[-1])[0]
    label = _label(stem)
    if len(parts) >= 4 and parts[:2] == ["documents", "applications"]:
        company, role = _application(parts[2], root)
        whose = " ".join(x for x in (company, role) if x) or _words(parts[2])
        return _clean("%s %s" % (whose, label))
    if len(parts) >= 4 and parts[:2] == ["documents", "network"]:
        name, company = _contact(parts[2], root)
        whose = ("%s (%s)" % (name, company) if name and company else name) or _words(parts[2])
        return _clean("%s %s" % (whose, label))
    # Anywhere else a file already named for what it is keeps that name; a bare one takes
    # its folder's.
    if stem in LABELS and len(parts) > 1:
        return _clean("%s %s" % (_words(parts[-2]), label))
    return _clean(label) or "document"


def copy(path, root=None) -> str:
    """Copy the document to documents/to_send/ under name_for(); the copy's path, relative
    to the person's files."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    root = root or person.state()
    out = os.path.join(root, *OUT)
    os.makedirs(out, exist_ok=True)
    dest = os.path.join(out, name_for(path, root) + os.path.splitext(path)[1])
    shutil.copyfile(path, dest)
    return os.path.relpath(dest, root).replace(os.sep, "/")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    bad = 0
    for p in args:
        try:
            print(copy(p))
        except FileNotFoundError:
            print("shown: no such file: %s" % p, file=sys.stderr)
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main())
