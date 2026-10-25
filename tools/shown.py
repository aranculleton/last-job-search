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
import local_path  # noqa: E402
from safe_name import cap_bytes, windows_safe  # noqa: E402

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
# Only a bracket that is an id is dropped: "(Level 2)" and "(L3)" say which job it is, and
# dropping every bracket with a digit in it sent two levels of one role under one name.
_REQ = re.compile(r"\s*[(\[]\s*(?:(?:req(?:uisition)?|job|jr|r|id|ref|no|number|posting)"
                  r"\b\.?[\s#:._-]*)?[a-z]{0,3}[\s#:._-]*\d[\d._-]{2,}[a-z]?\s*[)\]]", re.I)
# What no file name on any computer may hold.
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
# The most a name may run to, in bytes: a disk allows about 255 for a whole name, and a name
# in Japanese or Greek is two or three bytes a letter (tools/safe_name.py).
MAX_NAME_BYTES = 200


def _clean(text, keep_req: bool = False) -> str:
    text = str(text or "") if keep_req else _REQ.sub("", str(text or ""))
    text = re.sub(r"\s+", " ", _BAD.sub(" ", text)).strip(" .-")
    return windows_safe(cap_bytes(text, MAX_NAME_BYTES).strip(" .-"))


def _named(whose, label) -> str:
    """"<whose> <label>", the label never cut: the part that says whose is shortened
    first, so a long role name cannot take the "interview prep" off the end and leave the
    prep, the record and the form answers under one name."""
    label = _clean(label) or "document"
    room = MAX_NAME_BYTES - len(label.encode("utf-8")) - 1
    whose = cap_bytes(_clean(whose, keep_req=True), max(room, 0)).strip(" .-")
    return windows_safe(("%s %s" % (whose, label)).strip())


def _role_shown(company, role, rows) -> str:
    """The role as its name shows it: without its requisition number, unless another row
    at this employer has the same role under another number, when the number is what tells
    the two apart."""
    plain = _REQ.sub("", role).strip()
    if plain == role:
        return role
    import company_key
    k = company_key.key(company)
    twins = {(r.get("role") or "").strip() for r in rows
             if company_key.key(r.get("company") or "") == k
             and _REQ.sub("", (r.get("role") or "")).strip().lower() == plain.lower()}
    return role if len(twins) > 1 else plain


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
    """(company, role) of the tracker row whose folder this is, or ("", ""). The role as
    the name shows it (`_role_shown`)."""
    tracker = os.path.join(root, "job_search_tracker.csv")
    if not os.path.exists(tracker):
        return "", ""
    import outreach
    import csv_store                     # the mark a spreadsheet adds, and its encoding
    rows = csv_store.dict_rows(tracker, refuse=False)
    for r in reversed(rows):
        company, role = (r.get("company") or "").strip(), (r.get("role") or "").strip()
        if company and os.path.basename(outreach.app_folder(company, role)) == folder_name:
            return company, _role_shown(company, role, rows)
    return "", ""


def _contact(contact_id, root) -> tuple:
    """(name, company) of the contact with this id, or ("", ""). Two people of one name at
    one employer each get a third part, their title, or failing that a number in id order,
    so their two call preps are never sent under one name."""
    book = os.path.join(root, "network_contacts.csv")
    if not os.path.exists(book):
        return "", ""
    import state
    book_rows = state.load_contacts(book)
    me = next((c for c in book_rows if (c.get("contact_id") or "").strip() == contact_id), None)
    if me is None:
        return "", ""
    name, company = (me.get("name") or "").strip(), (me.get("company") or "").strip()
    import company_key

    def same(c):
        return ((c.get("name") or "").strip().casefold() == name.casefold()
                and company_key.key(c.get("company") or "") == company_key.key(company))
    twins = sorted((c for c in book_rows if same(c)),
                   key=lambda c: (c.get("contact_id") or "").strip())
    if len(twins) > 1 and name:
        title = (me.get("title") or "").strip()
        titles = [(c.get("title") or "").strip().casefold() for c in twins]
        if title and titles.count(title.casefold()) == 1:
            name = "%s, %s" % (name, title)
        else:
            name = "%s %d" % (name, twins.index(me) + 1)
    return name, company


def name_for(path, root=None) -> str:
    """The name the person sees for this document, without its extension. `root` is the
    person's files (person.state() unless a tool was given another)."""
    root = os.path.abspath(root or person.state())
    rel = local_path.rel(os.path.abspath(path), root).replace(os.sep, "/")
    parts = rel.split("/")
    stem = os.path.splitext(parts[-1])[0]
    label = _label(stem)
    if len(parts) >= 4 and parts[:2] == ["documents", "applications"]:
        company, role = _application(parts[2], root)
        whose = " ".join(x for x in (company, role) if x) or _words(parts[2])
        return _named(whose, label)
    if len(parts) >= 4 and parts[:2] == ["documents", "network"]:
        name, company = _contact(parts[2], root)
        whose = ("%s (%s)" % (name, company) if name and company else name) or _words(parts[2])
        return _named(whose, label)
    # Anywhere else a file already named for what it is keeps that name; a bare one takes
    # its folder's.
    if stem in LABELS and len(parts) > 1:
        return _named(_words(parts[-2]), label)
    return _clean(label) or "document"


# The notes a document keeps for the tools, never for the person: "<!-- stages -->",
# "<!-- quoted -->" and a prep's "<!-- generated answers: {json} -->". They reached the
# person in every copy sent (interview audit, 2026-10-25).
_ALONE = re.compile(r"^[ \t]*<!--.*?-->[ \t]*(?:\n|\Z)", re.S | re.M)
_INLINE = re.compile(r"[ \t]*<!--.*?-->", re.S)
_TEXT_TYPES = (".md", ".txt", ".markdown")


def for_the_person(text: str) -> str:
    """The document as the person reads it: the tools' comments out (a comment on lines of
    its own with its lines), and no run of blank lines where one stood."""
    out = _INLINE.sub("", _ALONE.sub("", str(text or "")))
    return re.sub(r"\n{3,}", "\n\n", out)


def copy(path, root=None) -> str:
    """Copy the document to documents/to_send/ under name_for(); the copy's path, relative
    to the person's files. Made again on every call, so a copy is never older than the
    document it is of. A text document is copied without the tools' comments."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    root = root or person.state()
    out = os.path.join(root, *OUT)
    os.makedirs(out, exist_ok=True)
    ext = os.path.splitext(path)[1]
    dest = os.path.join(out, name_for(path, root) + ext)
    if ext.lower() in _TEXT_TYPES:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        with open(dest, "w", encoding="utf-8", newline="") as fh:
            fh.write(for_the_person(text))
    else:
        shutil.copyfile(path, dest)
    return local_path.rel(dest, root).replace(os.sep, "/")


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
