"""What a first note was made from, kept beside it, so a tweak on the page is code only.

`compose.first_note()` builds a note from parts (the reason for writing, the question,
the ask, the opener, the order, who reads it, whether work authorization is said) and
threw them away: a page that offered "another opening" or "question first" could only
have a model write the note again. Now the composer remembers its arguments under the
note's own text (`remember`), the draft writer keeps them beside `draft.md` as
`draft.parts.json` when the note it writes is that text (`adopt`), and `replay` builds
the same note again with one part changed, through the same composer and its gates.

Nothing here decides what a note says. A part the note was not made from (a hand-written
note, or one edited after it was composed) has no parts record, and a tweak on it is a
redraft, never a guess.
"""
from __future__ import annotations

import hashlib
import json
import os

PARTS = "draft.parts.json"
PENDING = ".composed"            # documents/network/.composed/<text sha>.json, until adopted
KINDS = ("first_note",)
_DEFAULT = "__default__"


def sha(text: str) -> str:
    return hashlib.sha256(" ".join(str(text or "").split()).encode("utf-8")).hexdigest()[:16]


def _dir(*parts: str) -> str | None:
    try:
        import person
        return person.state("documents", "network", *parts)
    except Exception:  # noqa: BLE001  no profile: nothing is remembered
        return None


def _plain(v):
    if isinstance(v, (str, bool, int, float)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [x for x in (_plain(y) for y in v) if isinstance(x, (str, int, float, bool))]
    return _DEFAULT


def remember(kind: str, args: dict, text: str, default=None) -> str | None:
    """Keep the arguments a composer was called with, under the text it made. The saved
    reading is named, never copied: it is read again from reading.json on a replay."""
    d = _dir(PENDING)
    if not d or kind not in KINDS:
        return None
    keep = {}
    for k, v in args.items():
        if k == "reading":
            keep[k] = "saved" if v is not default and v is not None else None
        elif v is default:
            keep[k] = _DEFAULT
        else:
            got = _plain(v)
            if got is not _DEFAULT:
                keep[k] = got
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sha(text) + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"kind": kind, "args": keep, "text_sha": sha(text)}, fh,
                      ensure_ascii=False, indent=1, sort_keys=True)
        return path
    except OSError:
        return None


def path(contact_id: str) -> str | None:
    d = _dir(contact_id)
    return os.path.join(d, PARTS) if d else None


def adopt(contact_id: str, text: str) -> str | None:
    """Beside a draft just written: its parts when the composer made exactly this text,
    else none (a parts record for other words would replay a note nobody wrote)."""
    target = path(contact_id)
    if not target:
        return None
    pending = _dir(PENDING, sha(text) + ".json")
    if pending and os.path.isfile(pending):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.replace(pending, target)
        return target
    if os.path.isfile(target):
        try:
            os.remove(target)
        except OSError:
            pass
    return None


def load(contact_id: str, text: str | None = None) -> dict | None:
    """The parts record of this contact's draft, or None; with `text`, only when the record
    was made for exactly that text."""
    p = path(contact_id)
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(got, dict) or got.get("kind") not in KINDS:
        return None
    if text is not None and got.get("text_sha") != sha(text):
        return None
    return got


def replay(contact_id: str, overrides: dict, record: dict | None = None):
    """The note again from its parts with `overrides` applied, through the composer and its
    gates (a part that would make the note ask for the job, run over its limit or miss the
    reader is refused exactly as when it was first written). Returns (note, parts used)."""
    record = record or load(contact_id)
    if not record:
        raise LookupError("this note has no parts record: changing it means writing it again")
    import compose
    args = {k: v for k, v in record["args"].items() if v != _DEFAULT}
    if args.get("reading") == "saved":
        import reading as _reading
        args["reading"] = _reading.load(contact_id)
    else:
        args.pop("reading", None)
    for k in ("their",):
        if isinstance(args.get(k), list):
            args[k] = tuple(args[k])
    args.update(overrides)
    note = compose.first_note(**args)
    level = record.get("formality") or "standard"
    if level != "standard":
        # The register (Tweak M2) is applied over the composer's words, and kept with the
        # parts, so the next replay keeps it too.
        import advice
        note = advice.formality(str(note), level)
    used = dict(record, args=dict(record["args"], **{k: _plain(v) for k, v in overrides.items()}),
                text_sha=sha(str(note)))
    remember_record(used, str(note))
    return note, used


def remember_record(record: dict, text: str) -> str | None:
    """A parts record kept under the very text it made, for the draft writer to adopt."""
    d = _dir(PENDING)
    if not d:
        return None
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sha(text) + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict(record, text_sha=sha(text)), fh, ensure_ascii=False, indent=1,
                      sort_keys=True)
        return path
    except OSError:
        return None


def save(contact_id: str, record: dict) -> str | None:
    p = path(contact_id)
    if not p:
        return None
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return p
