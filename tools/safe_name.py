"""A name a file can carry on every computer the person might use.

The person's files are checked out on Windows as well as on a Mac, Linux and the cloud,
and Windows refuses some names outright: CON, PRN, AUX, NUL, COM1 to COM9 and LPT1 to
LPT9, in any case, with or without an extension, and any name ending in a dot or a
space. A contact called "Wren Con" with no employer got the id `con`, and a research
file for an employer whose key was "prn" was `prn.json`: a repo holding either cannot
be checked out on Windows at all. A name made only of letters outside a-z (an employer
written in Chinese or Arabic) slugged to nothing, and every such employer shared one
file called `.json`.

Names are also capped in bytes, not characters: a disk allows about 255 bytes for a
name, and a Japanese or Greek title is three or two bytes a letter.
"""
from __future__ import annotations

import hashlib

RESERVED = frozenset({"con", "prn", "aux", "nul", "conin$", "conout$"}
                     | {f"com{i}" for i in "123456789¹²³"}
                     | {f"lpt{i}" for i in "123456789¹²³"})
# Below the 255 a disk allows, leaving room for an extension and a numbered twin.
MAX_BYTES = 200


def reserved(stem: str) -> bool:
    """True when Windows refuses a file whose name starts with this stem."""
    base = str(stem or "").split(".")[0].rstrip(" ").lower()
    return base in RESERVED


def windows_safe(stem: str, mark: str = "_") -> str:
    """The stem, with `mark` added where Windows would refuse it as it is.

    A trailing dot or space is dropped first (Windows drops them silently, so two names
    that differ only there are one file). A name Windows reserves gets the mark after
    its first part, so `con` is `con_` and `aux.notes` is `aux_.notes`.
    """
    s = str(stem or "").rstrip(" .")
    if reserved(s):
        head, dot, rest = s.partition(".")
        s = head + mark + dot + rest
    return s


def cap_bytes(text: str, limit: int = MAX_BYTES) -> str:
    """The text cut to at most `limit` bytes of UTF-8, never through a character."""
    raw = str(text or "").encode("utf-8")
    if len(raw) <= limit:
        return str(text or "")
    return raw[:limit].decode("utf-8", "ignore").rstrip()


def short_hash(text: str, n: int = 8) -> str:
    """A stable few characters standing for the text, for a name with no letters left."""
    return hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:n]
