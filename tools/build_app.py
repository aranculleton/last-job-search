#!/usr/bin/env python3
"""Build the public app from a person's repo: everything app-owned, nothing personal.

    python3 tools/build_app.py <out_dir> [--tokens-out FILE] [--show] [--test]

1. Exports the COMMITTED tree (`git archive HEAD`, so uncommitted edits never
   ship) and deletes every path tools/personal_paths.py calls personal.
2. Builds the denylist from this repo's profile and state, which only a
   person's repo has: the person's name, contact details, LinkedIn handle,
   file prefix, every employer and school in their history, every person in
   network_contacts.csv and network_threads.csv, every company in the
   tracker, and any extra lines in profile/leak_tokens.txt (people or facts
   that appear nowhere else, a partner's name for instance).
3. Runs tools/leak_scan.py over the exported tree with that list. Exit 1 on
   any finding. An entry the app's master already carried before this repo
   recorded it is set aside, and said so (set_aside()). With --test, also
   runs the exported tree's own test suite against its example person, the
   way the app's CI will.

The denylist is written only where --tokens-out says, without the entries set
aside, and nowhere by default. It is personal data: never commit it, never
pass it to the app. The app's CI gets the same list from an encrypted Actions
secret.

ALLOWED_ORGANIZATIONS are companies that may appear in the app even though
the person applied to them, because the app names them as platforms or tools
whatever the person did: an AI vendor whose model runs the app, the portals
it searches, the hosting it uses, a cloud product a skill is named after.
The list is closed (2026-10-24). A tracker employer whose name the app's own
text already used is set aside by set_aside(), with no name written down; the
list stays only for the person's own employers, which carry no date to go by,
and for a repo with no copy of the app's master.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from personal_paths import is_personal  # noqa: E402

ROOT = person.ROOT

ALLOWED_ORGANIZATIONS = {
    # The app runs on Claude; Claude Code, claude.ai and the commit trailers
    # name the vendor in every copy.
    "Anthropic",
    # Platforms the app is built on or searches.
    "LinkedIn", "GitHub",
    # A brand spelt with a lower-case first letter, which tone.py lists so a
    # sentence opening on it is not "corrected". Naming it says nothing about
    # whether anyone applied there.
    "eBay",
    # Software the app names as a skill a posting asks for.
    "Docker",
    # Employers the app's own prose names for their products and tools, never as where
    # anyone applied: Google (Gemini CLI, Antigravity, Scholar), Microsoft (a Power BI
    # certificate), Apple (a Mac's own Python), IBM and Oracle (spelling and ATS
    # examples). Before set_aside() each failed the checks of anyone whose tracker named
    # it, on the app's own prose (2026-10-23). A name goes here only when the
    # app's text outside tools/bridges.py, whose skill entries the scan already sets
    # aside, uses it this way; a test checks each one is in the app's text.
    "Google", "Microsoft", "Apple", "IBM", "Oracle",
}

# The first names the app's invented people are greeted by in its examples and tests
# ("Hi Ana, ..."). A contact's first name goes on the denylist only as a greeting, to
# catch a real message copied into an example; a greeting with one of these names is the
# app's own cast, so a contact who happens to share it is still caught by full name,
# profile address, email and contact id, and never by the greeting. Before, one contact
# named like an example blocked every merge in the maintainer's repo (2026-10-22: "Hi Ana",
# the app's invented Ana Rook since 2026-10-19). A greeting in the app with a first name
# not listed here fails tests/test_an_invented_name_is_not_a_leak.py, so a name is added
# on purpose, as tools/name_guard_allow.txt is.
INVENTED_FIRST_NAMES = frozenset({
    "Ana", "Bo", "Bob", "Corwin", "Cy", "Halloway", "Idris", "Ivo", "Jane", "Jean", "Juno",
    "Morgan", "Pell", "Quillon", "Quinn", "Raj", "Rhian", "Riley", "Robin", "Rosalind",
    "Sally", "Sasha", "Shirin", "Tamsin", "Taylor", "Thad", "Wren", "Wrenfield", "Xiu",
    "Zo", "Zoe",
})


def _fold(word: str) -> str:
    """A word without its accents: the leak scan matches accent-blind, so "Zoë" is "Zoe"."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))


def _greetings(name: str) -> list[str]:
    """The greeting forms of a person's given names, leaving out the app's own cast."""
    out = []
    for first in given_names(name):
        if _fold(first) not in INVENTED_FIRST_NAMES:
            out += [f"=Hi {first}", f"=Dear {first}"]
    return out


def export(out_dir: str) -> list[str]:
    """`git archive HEAD` into out_dir, minus personal paths. Returns what was removed."""
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise SystemExit(f"build_app: {out_dir} exists and is not empty")
    os.makedirs(out_dir, exist_ok=True)
    arc = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", "HEAD"],
                         capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", out_dir], input=arc, check=True)
    removed = []
    for dp, _dns, fns in os.walk(out_dir, topdown=False):
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, out_dir).replace(os.sep, "/")
            if is_personal(rel):
                os.remove(full)
                removed.append(rel)
        if dp != out_dir and not os.listdir(dp):
            os.rmdir(dp)
    return removed


def _csv(path: str) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _csv_ever(path: str) -> list[dict]:
    """Every row the file holds now and every row any committed version of it held.

    A row taken out of the tracker (a draft never sent, scrubbed on 2026-10-15) still
    names a real employer and is still in this repo's history; a denylist built from
    today's file alone had forgotten it, and only an older copy kept by hand still
    caught it.
    """
    return [row for row, _ in _csv_dated(path)]


def _csv_dated(path: str) -> list[tuple[dict, float | None]]:
    """_csv_ever's rows, each with when this repo first recorded it: the time of the
    oldest commit that holds the row. Every doubt resolves to the earlier time, since a
    date too late reads the app as it stood later than it should, after a leak perhaps:
    a commit's author date where a cherry-pick or rebase reset its commit date; for a row
    only the working copy has, the file's newest commit, which did not yet hold it; and
    None, no date at all, for a row a shallow clone first shows at its oldest commit, or
    one in a file with no history.

    Read through one `git cat-file --batch`, so a long history costs one process, not
    one per version, and each distinct row is kept once: a contact book's history held
    26,744 rows and 1,156 different ones.
    """
    pending = float("inf")
    rows = _csv(path)
    out: list[list] = []
    index: dict = {}

    def keep(got: list[dict], when: float | None) -> None:
        for row in got:
            key = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in row.items())
            i = index.get(key)
            if i is None:
                index[key] = len(out)
                out.append([row, when])
            else:
                out[i][1] = _earlier(when, out[i][1])

    def dated(newest: float | None) -> list[tuple[dict, float | None]]:
        return [(r, newest if w == pending else w) for r, w in out]

    keep(rows, pending)
    folder = os.path.dirname(path) or "."
    top = subprocess.run(["git", "-C", folder, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if top.returncode != 0:
        return dated(None)
    root = top.stdout.strip()
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")
    log = subprocess.run(["git", "-C", root, "log", "--format=%H %at %ct", "--", rel],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    revs = [(p[0], float(min(int(p[1]), int(p[2]))))
            for p in (ln.split() for ln in log.stdout.splitlines()) if len(p) == 3] \
        if log.returncode == 0 else []
    if not revs:
        return dated(None)
    cut = subprocess.run(["git", "-C", root, "rev-parse", "--git-path", "shallow"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout.strip()
    try:
        with open(cut if os.path.isabs(cut) else os.path.join(root, cut), encoding="utf-8") as fh:
            shallow = set(fh.read().split())
    except OSError:
        shallow = set()
    batch = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                           input="".join(f"{r}:{rel}\n" for r, _ in revs).encode(),
                           capture_output=True)
    data, at, k = batch.stdout, 0, -1
    # Read by position: cutting the rest of the batch off after each version copied it
    # again every time, a fifth of a second on 19 MB. One header per version asked for,
    # in the order asked, so the k-th header is the k-th commit's copy.
    while at < len(data):
        end = data.find(b"\n", at)
        if end < 0:
            break
        parts = data[at:end].split()
        at = end + 1
        k += 1
        if len(parts) < 3 or parts[1] != b"blob":       # "<rev>:<path> missing", a deletion
            continue
        size = int(parts[2])
        blob, at = data[at:at + size], at + size + 1
        try:
            keep(list(csv.DictReader(io.StringIO(blob.decode("utf-8", errors="replace")))),
                 None if k >= len(revs) or revs[k][0] in shallow else revs[k][1])
        except csv.Error:
            continue
    # A row the newest copy did not hold was added after it, a shallow clone or not.
    return dated(revs[0][1])


def _earlier(a: float | None, b: float | None) -> float | None:
    """The earlier of two record times; None, no date to go by, outranks any date."""
    return None if a is None or b is None else min(a, b)


def _school(education_tex: str) -> list[str]:
    """The institution named in the profile's Education line."""
    plain = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", education_tex)
    return [m.strip() for m in re.findall(r"(?:University|College|School|Institute) of [A-Z][\w ]+?(?=[,(.]|$)"
                                          r"|[A-Z][\w ]+ (?:University|College)", plain)]


def _looks_like_a_name(v: str) -> bool:
    """Two to four capitalised words of letters (any script), as "Zoë Varga" or "Tomasz K."."""
    words = v.split()
    return 2 <= len(words) <= 4 and all(
        w[0].isupper() and all(c.isalpha() or c in "'-." for c in w) for w in words)


_PERSON_KEYS = {"linkedin_url", "headline", "title", "email", "why_not_now", "location"}
_PREP_HEADING = re.compile(r"^# Prep - ([^,\n]+),", re.M)


_CREDENTIAL = re.compile(r"^(?:[A-Z]{2,5}|Ph\.?D\.?|P\.Eng\.?|M\.?Sc\.?|B\.?Sc\.?)$")


# A bracket that is not a nickname: a role or a note written beside a name, as a tracker's
# contact_person holds "<name> (Talent Acquisition Partner, <employer>)". Read as part of
# the name, its last words became a "name" ("Acquisition Partner") that matched the app's
# own files, and the leak scan failed on them (2026-10-22).
_NICKNAME = re.compile(r"[A-Z][\w'.-]*")


def _without_roles(name: str) -> str:
    """The name with every bracket that is not a one-word nickname taken out, an unclosed
    one included."""
    name = re.sub(r"\(([^)]*)\)",
                  lambda m: m.group(0) if _NICKNAME.fullmatch(m.group(1).strip()) else " ",
                  str(name or ""))
    cut = name.rfind("(")
    if cut >= 0 and ")" not in name[cut:]:
        name = name[:cut]
    return " ".join(name.split())


def name_forms(name: str) -> list[str]:
    """Every form a recorded name is written in elsewhere.

    The contact book records "Xiu Mei (Sally) Ho, PhD"; a comment writes
    "Xiu Mei (Sally) Ho", "Xiu Mei Ho" or "Sally Ho". An entry matches
    only the form it holds, so each form is its own entry.
    """
    base = _without_roles(name).split(",")[0].split()
    while len(base) > 2 and _CREDENTIAL.match(base[-1]):
        base.pop()
    base = " ".join(base)
    forms = [base]
    bare = " ".join(re.sub(r"\([^)]*\)", " ", base).split())
    nick = re.search(r"\(([^)]+)\)", base)
    if nick:
        forms += [bare, nick.group(1).strip() + " " + bare.split()[-1]]
    # "Juno Maeve Castellan" may go by Maeve: every given name with the surname.
    words = bare.split()
    if len(words) >= 3:
        forms += [f"{w} {words[-1]}" for w in given_names(bare)]
    seen: set[str] = set()
    return [f for f in forms if len(f.split()) >= 2 and not (f in seen or seen.add(f))]


def given_names(name: str) -> list[str]:
    """Each name a person might be greeted by: every capitalised word but the last."""
    name = _without_roles(name)
    words = " ".join(re.sub(r"\([^)]*\)", " ", name.split(",")[0]).split()).split()
    while len(words) > 2 and _CREDENTIAL.match(words[-1]):
        words.pop()
    nick = re.findall(r"\(([^)]+)\)", name)
    return [w.strip(".,") for w in words[:-1] + nick
            if len(w.strip(".,")) > 2 and w[0].isupper() and not _CREDENTIAL.match(w)]


_COMPANY_SUFFIX = re.compile(
    r"[,.]?\s+(?:inc|ltd|limited|llc|llp|plc|corp|corporation|company|co|group|holdings"
    r"|beverage company|technologies|services)\.?$", re.I)


# What a resume puts where an employer goes when there is no employer: a run of
# projects, freelance work, a career break. Nobody is identified by them, and
# as entries they matched the app's own headings, so the first person set up
# with a projects entry had to rename it on their resume to pass the scan.
GENERIC_EMPLOYERS = re.compile(
    r"(?:(?:selected|personal|independent|freelance|portfolio|creative|academic|"
    r"university|student|side|other|various|key)\s+)?"
    r"(?:projects?|freelance|freelancer|self[- ]employed|independent|contract(?:ing|or)?|"
    r"consulting|consultancy|various|volunteer(?:ing)?|career break|sabbatical|"
    r"portfolio|personal|travel(?:ling)?)", re.I)


def _generic_employer(name: str) -> bool:
    core = re.split(r"\s*[,(]", name.strip(), maxsplit=1)[0]
    return bool(GENERIC_EMPLOYERS.fullmatch(core))


def company_forms(company: str) -> list[str]:
    """The company as recorded and as people write it: "Acme Foods Company Inc."
    is "Acme Foods" in a comment, and only the recorded form was an entry."""
    core = " ".join(re.sub(r"\([^)]*\)", " ", company).split())
    prev = None
    while prev != core:
        prev, core = core, _COMPANY_SUFFIX.sub("", core).strip()
    return [company] + ([core] if core != company and len(core) > 3 else [])


def _people() -> list[str]:
    """Every person named in the profile's and the state's JSON and prep docs."""
    found: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            v = o.get("name")
            if isinstance(v, str) and _looks_like_a_name(v.strip()) and _PERSON_KEYS & set(o):
                found.add(v.strip())
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    roots = [person.path(), person.state("documents"), person.state("company_research")]
    for root in roots:
        for dp, _, fns in os.walk(root):
            for f in fns:
                full = os.path.join(dp, f)
                try:
                    if f.endswith(".json"):
                        with open(full, encoding="utf-8") as fh:
                            walk(json.load(fh))
                    elif f == "prep.md":
                        with open(full, encoding="utf-8") as fh:
                            found.update(m.strip() for m in _PREP_HEADING.findall(fh.read()))
                except (OSError, ValueError):
                    continue
    return sorted({f for n in found for f in name_forms(n) if len(f.replace(".", "")) > 4})


def phone_forms(written: str) -> list[str]:
    """The entries a phone number needs, in the forms it gets written.

    A North American number: the area code, the line number in its two usual
    groupings and its last four digits, any of which finds the rest. Anywhere
    else: the number as grouped after the country code, and with the trunk 0 it
    is dialled with nationally. Matching ignores separators, so the grouped form
    also finds the digits run together. Short groups alone would match
    everywhere, so they are never entries: the first version took a North
    American slice of an Australian mobile and blocked every "140" in the app.

    No number is written out in this file. An example in an app file is in
    every person's repo, and the one written here once was a test person's own
    number, which their leak scan rightly failed.
    """
    phone = re.sub(r"\D", "", written)
    groups = re.findall(r"\d+", written)
    plus = written.strip().startswith("+")
    if plus and groups:
        groups = groups[1:]                         # drop the country code
    nanp = (len(phone) == 11 and written.strip().startswith("+1")
            or len(phone) == 10 and not plus and phone[0] in "23456789")
    if nanp:
        return [phone[-10:-7], phone[-7:-4] + " " + phone[-4:], phone[-7:], phone[-4:]]
    national = " ".join(groups)
    if len(national.replace(" ", "")) < 8:
        return []
    return [national] + ([] if national.startswith("0") else ["0" + national])


def denylist() -> list[str]:
    """One token per line, in leak_scan.py's format. "=" marks case-sensitive."""
    return list(recorded())


def recorded() -> dict[str, float | None]:
    """The denylist, each entry once and in order, with when this repo first recorded it.

    The time is the earliest commit of the state file row it came from (_csv_dated()
    says how a doubt is settled). None is an entry with no date to go by, and it is never
    set aside: the person's own name and contact details, their employers and schools,
    everyone a discovery run or a prep document named, and profile/leak_tokens.txt.
    """
    out: dict[str, float | None] = {}
    for t, when in _entries():
        t = (t or "").strip()
        if not t:
            continue
        out[t] = _earlier(when, out[t]) if t in out else when
    return out


def _entries() -> list[tuple[str, float | None]]:
    out: list[tuple[str, float | None]] = []

    def add(t: str, when: float | None = None) -> None:
        out.append((t, when))

    ident = person.get("identity")
    for k in ("name", "first", "last"):
        if ident.get(k) and len(ident[k]) > 2:
            add(ident[k])
    add(ident.get("file_prefix", ""))
    email = ident.get("email", "")
    if email:
        add(email)
        add(email.split("@")[0])
        dom = email.split("@")[1]
        # A shared mail provider's domain is everybody's, and the reserved
        # example domains are what the app's own templates use.
        shared = ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com")
        if dom.count(".") == 1 and dom not in shared and not dom.startswith("example."):
            add(dom)
    for form in phone_forms(ident.get("phone", "")):
        add(form)
    handle = re.search(r"linkedin\.com/in/([^/?#]+)", ident.get("linkedin", ""))
    if handle:
        add(handle.group(1))
    roles = person.module("roles")
    for r in roles.ROLES:
        # An employer the app's own prose names for its products is allowed here too, the
        # same as in the tracker: a maintainer who worked there failed every check on it.
        if not _generic_employer(r["employer"]) and not (
                set(company_forms(r["employer"])) & ALLOWED_ORGANIZATIONS):
            add("=" + r["employer"])
    for s in _school(getattr(roles, "EDUCATION", "")):
        add(s)
        m = re.search(r" of ([A-Z]\w+)$", s)
        if m:
            add(m.group(1))
    contacts = _csv_dated(person.state("network_contacts.csv"))
    for row, when in contacts:
        name = (row.get("name") or "").strip()
        if len(name.split()) >= 2:
            for form in name_forms(name):
                add(form, when)
            # A contact also appears by first name in an example message
            # ("Hi Sasha, ..."). The greeting form is precise; the bare first
            # name would fire on every other person who shares it. Every given
            # name gets one, because people go by a middle name too, except the
            # first names the app's own invented people use (INVENTED_FIRST_NAMES).
            for form in _greetings(name):
                add(form, when)
        url = row.get("linkedin_url") or ""
        h = re.search(r"linkedin\.com/in/([^/?#]+)", url)
        if h:
            add(h.group(1), when)
        if row.get("email"):
            add(row["email"].strip(), when)
    # Threads name their person by contact_id, which is itself a name slug
    # ("firstname_lastname"); the contacts file holds the names.
    ids: dict[str, float | None] = {}
    for row, when in contacts + _csv_dated(person.state("network_threads.csv")):
        i = (row.get("contact_id") or "").strip()
        if "_" in i:
            ids[i] = _earlier(when, ids[i]) if i in ids else when
    for i in sorted(ids):
        add(i, ids[i])
    for row, when in _csv_dated(person.state("job_search_tracker.csv")):
        company = (row.get("company") or "").strip()
        forms = company_forms(company) if company else []
        if forms and not set(forms) & ALLOWED_ORGANIZATIONS:
            for form in forms:
                add("=" + form, when)
        cp = (row.get("contact_person") or "").strip()
        if len(cp.split()) >= 2:
            for form in name_forms(cp):
                add(form, when)
    # Everybody a discovery run or a prep doc ever named, not only the people who
    # became contacts: the people found and dropped are real too, and a comment
    # that cites "the run dropped <name>" carries them into the app.
    for name in _people():
        add(name)
        for form in _greetings(name):
            add(form)
    extra = person.path("leak_tokens.txt")
    if os.path.isfile(extra):
        with open(extra, encoding="utf-8") as fh:
            for line in fh:
                add(line.rstrip("\n"))
    return out


# The app as this repo takes it: the app's master, which the sync fetches here
# (sync_app.MASTER).
RELEASED = "refs/remotes/app/master"
_FOUND = re.compile(r"denylist entry (\d+)")


def set_aside(found, when: dict, ref: str = RELEASED, root: str = ROOT) -> dict[str, str]:
    """{entry: app commit} for each entry in `found` that the app at `ref` already carried
    before this repo first recorded it (`when`, from recorded()).

    A tracker employer whose name is an ordinary word in the app's own text failed every
    check, and the cure was to add each one by hand to ALLOWED_ORGANIZATIONS (2026-10-24).
    A word the app used before the person ever wrote it down cannot have come from them,
    so it cannot identify them. The app's copy is read as it stood before the entry was
    recorded, never as it stands now: what reached the app after the person recorded it
    may be the leak itself, and a list made from the app's current text would let a leak
    excuse itself, the way a secret scanner's baseline can hide a live secret.
    """
    # The app's master in the order it grew, each commit at the later of its two dates.
    # It is walked, never searched by date: one commit dated out of order (a rebase that
    # kept author dates, a container with its clock wrong) would otherwise name a copy
    # from after the leak as one from before it.
    log = subprocess.run(["git", "-C", root, "log", "--first-parent", "--reverse",
                          "--format=%H %at %ct", ref, "--"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    chain = [(p[0], max(int(p[1]), int(p[2])))
             for p in (ln.split() for ln in log.stdout.splitlines()) if len(p) == 3] \
        if log.returncode == 0 else []
    groups: dict[str, list[str]] = {}
    for e in dict.fromkeys(found):
        t = when.get(e)
        if t is None:
            continue
        sha = ""
        for c, ct in chain:
            if ct >= t:
                break
            sha = c
        if sha:
            groups.setdefault(sha, []).append(e)
    aside: dict[str, str] = {}
    for sha, entries in groups.items():
        for e in _carried(sha, entries, root):
            aside[e] = sha[:12]
    return aside


def _carried(sha: str, entries: list[str], root: str = ROOT) -> list[str]:
    """The entries the app's tree at this commit holds, matched the way leak_scan matches
    them: only the files `git grep` finds a word of an entry in are read, so a look costs
    a fraction of a second."""
    import leak_scan
    words = set()
    for e in entries:
        body = e[1:] if e.startswith("=") else e
        for form in (body, leak_scan.plain(body)):
            w = max(re.findall(r"\w+", form), key=len, default="")
            if w:
                words.add(w)
    if not words:
        return []
    args = ["git", "-C", root, "grep", "-l", "-z", "-I", "-i", "-F"]
    for w in sorted(words):
        args += ["-e", w]
    got = subprocess.run(args + [sha, "--"], capture_output=True)
    paths = [p.decode("utf-8", "replace").split(":", 1)[1]
             for p in got.stdout.split(b"\0") if b":" in p]
    if not paths:
        return []
    with tempfile.TemporaryDirectory(prefix="app_then_") as d:
        cat = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                             input="".join(f"{sha}:{p}\n" for p in paths).encode(),
                             capture_output=True).stdout
        for p in paths:
            head, _, cat = cat.partition(b"\n")
            size = int(head.split()[2]) if len(head.split()) == 3 else 0
            data, cat = cat[:size], cat[size + 1:]
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(data)
        found = leak_scan.scan(d, leak_scan.tokens_from(entries), leak_scan.load_allow(None),
                               export=True)
    hit = {int(m.group(1)) for f in found for m in [_FOUND.search(f)] if m}
    return [e for n, e in enumerate(entries, 1) if n in hit]


def check(tree: str, when: dict, show: bool = False, ref: str = RELEASED,
          root: str = ROOT) -> tuple[list[str], dict[str, str]]:
    """leak_scan over `tree` with the denylist `when` holds: (findings, {entry: app commit}
    for each entry set aside). A finding on a set-aside entry is not one."""
    import leak_scan
    entries = list(when)
    # The tree is an export of what is committed: a committed venv/ or node_modules/ is
    # read too, as CI's --git scan reads it.
    findings = leak_scan.scan(tree, leak_scan.tokens_from(entries), leak_scan.load_allow(None),
                              show=show, export=True)
    return without_aside(findings, entries, when, ref, root)


def without_aside(findings: list[str], entries: list[str], when: dict, ref: str = RELEASED,
                  root: str = ROOT) -> tuple[list[str], dict[str, str]]:
    """(the findings left, {entry: app commit} set aside): `entries` is the list the scan
    numbered its "denylist entry N" by, and `when` says when each was recorded."""
    def entry(f: str) -> str:
        m = _FOUND.search(f)
        n = int(m.group(1)) if m else 0
        return entries[n - 1] if 0 < n <= len(entries) else ""

    found = {entry(f) for f in findings} - {""}
    aside = set_aside(found, when, ref, root) if found else {}
    return [f for f in findings if entry(f) not in aside], aside


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--tokens-out", help="keep the denylist here (personal data: never commit it)")
    ap.add_argument("--show", action="store_true", help="print matched text (local use only)")
    ap.add_argument("--test", action="store_true", help="run the exported tree's tests too")
    a = ap.parse_args(argv)

    removed = export(a.out_dir)
    print(f"build_app: exported HEAD to {a.out_dir}, removed {len(removed)} personal path(s)")
    when = recorded()
    findings, aside = check(a.out_dir, when, show=a.show, ref=RELEASED, root=ROOT)
    for f in findings:
        print(f)
    print(f"leak_scan: {len(findings)} finding(s); {len(when)} denylist entries checked",
          file=sys.stderr)
    if aside:
        print(f"build_app: set aside {len(aside)} entr{'y' if len(aside) == 1 else 'ies'} the "
              "app already carried before this repo recorded them: "
              + ", ".join(f"{e.lstrip('=')!r} (app {sha})" for e, sha in aside.items()))
    elif any(_FOUND.search(f) for f in findings) and subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--verify", "--quiet", RELEASED],
            capture_output=True).returncode != 0:
        print("build_app: no copy of the app's master here to compare with, so nothing was "
              "set aside (python3 tools/sync_app.py fetches it)")
    if a.tokens_out:
        with open(a.tokens_out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(t for t in when if t not in aside) + "\n")
    if findings:
        print("build_app: LEAK SCAN FAILED. Nothing from this tree may be pushed.", file=sys.stderr)
        return 1
    print(f"build_app: leak scan clean ({len(when) - len(aside)} denylist entries)")
    if a.test:
        env = {k: v for k, v in os.environ.items() if k not in ("LJS_PROFILE", "LJS_STATE")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # The tests run in a throwaway copy, so the export stays exactly the tree
        # that was scanned: no .git, no bytecode, nothing a test wrote. The copy
        # becomes a one-commit repository because some tests ask git what is
        # tracked, as they would in a fresh copy of the app.
        work = tempfile.mkdtemp(prefix="app_test_")
        try:
            shutil.copytree(a.out_dir, work, dirs_exist_ok=True)
            for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                        ["git", "-c", "user.name=build_app", "-c", "user.email=build_app@example.com",
                         "commit", "-q", "-m", "app tree"]):
                subprocess.run(cmd, cwd=work, check=True, capture_output=True)
            t = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                               cwd=work, env=env)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if t.returncode != 0:
            print("build_app: the app tree's own tests failed", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
