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
   any finding. With --test, also runs the exported tree's own test suite
   against its example person, the way the app's CI will.

The denylist is written only where --tokens-out says (default: a temp file
that is deleted). It is personal data: never commit it, never pass it to the
app. The app's CI gets the same list from an encrypted Actions secret.

ALLOWED_ORGANIZATIONS are companies that may appear in the app even though
the person applied to them, because the app names them as platforms or tools
whatever the person did: an AI vendor whose model runs the app, the portals
it searches, the hosting it uses, a cloud product a skill is named after.
Each is a decision; keep the list short.
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
    caught it. Read through one `git cat-file --batch`, so a long history costs one
    process, not one per version, and each distinct row is kept once: a contact book's
    history held 26,744 rows and 1,156 different ones.
    """
    rows = _csv(path)
    folder = os.path.dirname(path) or "."
    top = subprocess.run(["git", "-C", folder, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        return rows
    root = top.stdout.strip()
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")
    log = subprocess.run(["git", "-C", root, "log", "--format=%H", "--", rel],
                         capture_output=True, text=True)
    revs = log.stdout.split() if log.returncode == 0 else []
    if not revs:
        return rows
    batch = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                           input="".join(f"{r}:{rel}\n" for r in revs).encode(),
                           capture_output=True)
    out, data, at = [], batch.stdout, 0
    seen: set = set()

    def keep(got: list[dict]) -> None:
        for row in got:
            key = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in row.items())
            if key not in seen:
                seen.add(key)
                out.append(row)

    keep(rows)
    # Read by position: cutting the rest of the batch off after each version copied it
    # again every time, a fifth of a second on 19 MB.
    while at < len(data):
        end = data.find(b"\n", at)
        if end < 0:
            break
        parts = data[at:end].split()
        at = end + 1
        if len(parts) < 3 or parts[1] != b"blob":       # "<rev>:<path> missing", a deletion
            continue
        size = int(parts[2])
        blob, at = data[at:at + size], at + size + 1
        try:
            keep(list(csv.DictReader(io.StringIO(blob.decode("utf-8", errors="replace")))))
        except csv.Error:
            continue
    return out


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
    out: list[str] = []
    add = out.append
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
        if not _generic_employer(r["employer"]):
            add("=" + r["employer"])
    for s in _school(getattr(roles, "EDUCATION", "")):
        add(s)
        m = re.search(r" of ([A-Z]\w+)$", s)
        if m:
            add(m.group(1))
    contacts = _csv_ever(person.state("network_contacts.csv"))
    for row in contacts:
        name = (row.get("name") or "").strip()
        if len(name.split()) >= 2:
            out.extend(name_forms(name))
            # A contact also appears by first name in an example message
            # ("Hi Sasha, ..."). The greeting form is precise; the bare first
            # name would fire on every other person who shares it. Every given
            # name gets one, because people go by a middle name too, except the
            # first names the app's own invented people use (INVENTED_FIRST_NAMES).
            out.extend(_greetings(name))
        url = row.get("linkedin_url") or ""
        h = re.search(r"linkedin\.com/in/([^/?#]+)", url)
        if h:
            add(h.group(1))
        if row.get("email"):
            add(row["email"].strip())
    # Threads name their person by contact_id, which is itself a name slug
    # ("firstname_lastname"); the contacts file holds the names.
    ids = {(r.get("contact_id") or "").strip() for r in contacts}
    ids |= {(r.get("contact_id") or "").strip() for r in _csv_ever(person.state("network_threads.csv"))}
    out += sorted(i for i in ids if "_" in i)
    for row in _csv_ever(person.state("job_search_tracker.csv")):
        company = (row.get("company") or "").strip()
        forms = company_forms(company) if company else []
        if forms and not set(forms) & ALLOWED_ORGANIZATIONS:
            for form in forms:
                add("=" + form)
        cp = (row.get("contact_person") or "").strip()
        if len(cp.split()) >= 2:
            out.extend(name_forms(cp))
    # Everybody a discovery run or a prep doc ever named, not only the people who
    # became contacts: the people found and dropped are real too, and a comment
    # that cites "the run dropped <name>" carries them into the app.
    for name in _people():
        add(name)
        out.extend(_greetings(name))
    extra = person.path("leak_tokens.txt")
    if os.path.isfile(extra):
        with open(extra, encoding="utf-8") as fh:
            out += [line.rstrip("\n") for line in fh]
    seen, uniq = set(), []
    for t in out:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--tokens-out", help="keep the denylist here (personal data: never commit it)")
    ap.add_argument("--show", action="store_true", help="print matched text (local use only)")
    ap.add_argument("--test", action="store_true", help="run the exported tree's tests too")
    a = ap.parse_args(argv)

    removed = export(a.out_dir)
    print(f"build_app: exported HEAD to {a.out_dir}, removed {len(removed)} personal path(s)")
    tokens = denylist()
    keep = a.tokens_out
    tmp = None
    if not keep:
        fd, tmp = tempfile.mkstemp(prefix="leak_tokens_")
        os.close(fd)
        keep = tmp
    with open(keep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(tokens) + "\n")
    try:
        cmd = [sys.executable, os.path.join(ROOT, "tools", "leak_scan.py"), a.out_dir, "--tokens", keep]
        if a.show:
            cmd.append("--show")
        env = dict(os.environ, LJS_LEAK_TOKENS="")
        rc = subprocess.run(cmd, env=env).returncode
    finally:
        if tmp:
            os.remove(tmp)
    if rc != 0:
        print("build_app: LEAK SCAN FAILED. Nothing from this tree may be pushed.", file=sys.stderr)
        return 1
    print(f"build_app: leak scan clean ({len(tokens)} denylist entries)")
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
