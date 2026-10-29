"""The page takes a LinkedIn download and reads LinkedIn pages, and the repo records both once.

The coordinator's two flows (2026-10-25), engine half. A: the model says where the download
stands (none yet, asked for, fresh, due by the fortnightly rule), its dated steps and the
only files the page lets the person add; "asked for" is recorded with its day; the files
added on the page are fetched by the chat and taken exactly as `export.py take` takes a ZIP,
once, however many times or chats take them; the brief says once that a download asked for
a day ago is still not taken. B: after "Check it works" the page counts as a browser that
can read, so place.py says nothing about reading and reading.py queues profiles for the
page; a profile the page read is logged as `reading.py read` logs one. No session fetches
linkedin.com. Every name, address and message here is invented
(tests/fixtures/linkedin_export/README.md, tests/app_state.py).
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import APP, NOW, Search  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "linkedin_export")
FILES = {"a1" * 16: "messages.csv", "b2" * 16: "Connections.csv", "c3" * 16: "Invitations.csv"}
PELL = "kestrel_mutual_ansgar"


class Page(Search):
    def __init__(self, root):
        super().__init__(root)
        for name, dest in (("book_contacts.csv", "network_contacts.csv"),
                           ("book_threads.csv", "network_threads.csv")):
            shutil.copyfile(os.path.join(FIX, name), os.path.join(self.state, dest))
        self.assets = os.path.join(root, "assets")
        # Their profiles are read in a browser (the example person pastes them instead).
        net = os.path.join(self.profile, "networking.py")
        with open(net, encoding="utf-8") as fh:
            text = fh.read().replace('PROFILE_READS = "paste"', 'PROFILE_READS = "browser"')
        with open(net, "w", encoding="utf-8") as fh:
            fh.write(text)

    def env(self):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state, LJS_COPY="private")
        env.pop("LJS_TODAY", None)
        return env

    def root_assets(self):
        os.makedirs(self.assets, exist_ok=True)
        return self.assets

    def fetched(self):
        """The page's assets as a chat's Artifact read saves them: <asset id>.<ext>."""
        os.makedirs(self.assets, exist_ok=True)
        for aid, name in FILES.items():
            shutil.copyfile(os.path.join(FIX, name), os.path.join(self.assets, aid + ".csv"))

    def take(self, aid="act-take"):
        self.put("actions", aid, {"action": "export.take", "item": "linkedin-export",
                                  "value": {"assets": [{"id": k, "name": v}
                                                       for k, v in FILES.items()]},
                                  "at": "2026-10-25T17:10:00Z", "rev_seen": "", "tab": "t1"},
                 version=1)
        return aid

    def apply_assets(self, dump=None, chat="cloud-1"):
        return json.loads(self.run("apply", dump or self.dump, "--chat", chat, "--now", NOW,
                                   "--assets", self.assets))

    def py(self, code):
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = ['tools', "
                            "'tools/network']\n" + code], env=self.env(), capture_output=True,
                           encoding="utf-8", cwd=ROOT, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout


@pytest.fixture
def page(tmp_path):
    return Page(str(tmp_path))


def _rows(page):
    with open(os.path.join(page.state, "network_threads.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ A: the download


def test_the_model_says_where_the_download_stands_and_what_to_add(page):
    ex = page.model()["linkedin"]["export"]
    assert (ex["state"], ex["due"], ex["taken_on"]) == ("missing", True, None)
    assert ex["steps"]["lines"][0].startswith("To ")
    assert ex["steps"]["link"].startswith("https://www.linkedin.com/help/")
    assert ex["steps"]["checked"]
    names = {f["name"] for f in ex["files"]}
    assert {"messages.csv", "Invitations.csv", "Connections.csv"} <= names
    assert next(f for f in ex["files"] if f["name"] == "messages.csv")["needed"] == [
        "FROM", "DATE", "CONTENT"]


def test_asked_for_is_recorded_with_its_day_and_can_be_taken_back(page):
    aid = page.act("export.requested", "linkedin-export", rev="")
    assert page.apply()["ok"] == [aid], page.receipt(aid)
    ex = page.model()["linkedin"]["export"]
    assert (ex["state"], ex["requested_at"]) == ("requested", "2026-10-25")
    page.written_back()
    back = page.act("undo", None, value={"undoes": aid})
    assert page.apply()["ok"] == [back]
    assert page.model()["linkedin"]["export"]["requested_at"] is None


def test_the_files_added_on_the_page_are_fetched_then_taken_once(page):
    before = len(_rows(page))
    aid = page.take()
    first = json.loads(page.run("apply", page.dump, "--chat", "cloud-1", "--now", NOW))
    # Not fetched yet: no receipt, and the assets to fetch are named.
    assert first["ok"] == [] and first["fetch"] == [{"action": aid, "assets": list(FILES)}]
    page.fetched()
    got = page.apply_assets()
    assert got["ok"] == [aid], page.receipt(aid)
    r = page.receipt(aid)
    assert r["remove_assets"] == list(FILES)
    assert r["counts"]["messages"] > 0 and r["counts"]["connections"] > 0
    assert r["note"].startswith("Taken: ")
    after = len(_rows(page))
    assert after > before
    ex = page.model()["linkedin"]["export"]
    assert ex["state"] == "fresh" and ex["taken_on"] and ex["counts"]["messages"] > 0
    # The same download again, from another tap: nothing changes.
    page.written_back()
    again = page.take("act-again")
    assert page.apply_assets()["ok"] == [again]
    assert page.receipt(again)["note"].startswith("Already taken")
    assert len(_rows(page)) == after


def test_two_chats_taking_the_same_download_at_once_import_it_once(page):
    page.fetched()
    before = len(_rows(page))
    dumps = []
    for n in (1, 2):
        d = page.dump + f"_{n}"
        page.dump, keep = d, page.dump
        page.take()
        page.dump = keep
        dumps.append(d)
    runs = [subprocess.Popen([sys.executable, APP, "apply", d, "--chat", f"chat-{n}", "--now",
                              NOW, "--assets", page.assets], env=page.env(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            for n, d in enumerate(dumps, 1)]
    outs = [json.loads(r.communicate(timeout=300)[0]) for r in runs]
    assert all(len(o["ok"]) == 1 for o in outs), outs
    once = len(_rows(page))
    assert once > before
    rec = json.load(open(os.path.join(page.state, "documents", "network",
                                      "linkedin_export.json"), encoding="utf-8"))
    assert len(rec["taken_hashes"]) == 1
    # A take run alone afterwards adds nothing either.
    page.py("import export; export.take([export.home()])")
    assert len(_rows(page)) == once


def test_a_download_asked_for_a_day_ago_and_not_taken_is_said_once(page):
    page.py("import export; export.requested('2026-10-23')")
    line = page.py("import export; print(export.waiting_line('2026-10-25'))").strip()
    assert line.startswith("Your LinkedIn download was asked for on 2026-10-23")
    assert page.py("import export; print(export.waiting_line('2026-10-23'))").strip() == ""
    told = page.py("import export; print(repr(export.waiting_line('2026-10-26', "
                   f"[{line!r}])))").strip()
    assert told == "''"


# ------------------------------------------------------------------ B: the page reads LinkedIn

# The tap that says the page read LinkedIn is dated NOW, and the page counts as reading for
# place.PAGE_READS_DAYS after it: route() and place.check() are asked on that same day (the
# `today` place.page_reads takes), as the page's model is (`--now NOW`), not on the
# computer's own calendar.
ON_THE_DAY = ("import datetime, functools, place\n"
              "place.page_reads = functools.partial(place.page_reads, "
              f"today=datetime.date.fromisoformat({NOW[:10]!r}))\n")


def test_after_check_it_works_the_page_is_a_browser_that_reads(page):
    m = page.model()
    assert m["linkedin"]["reading"]["page_reads"] is False
    assert m["where"]["reading"]["state"] == "open_in_app"
    # The page is the reader before it has read anything too (4.3): queued, and the person
    # told once where it reads.
    route = json.loads(page.py(ON_THE_DAY + "import reading, json; "
                               "print(json.dumps(reading.route(())))"))
    assert route["route"] == "page" and "Claude app on your computer" in route["say"]
    aid = page.act("reader.checked", "linkedin-reader", value={"ok": True}, rev="")
    assert page.apply()["ok"] == [aid], page.receipt(aid)
    m = page.model()
    rd = m["linkedin"]["reading"]
    assert rd["page_reads"] is True and rd["ok"] is True and rd["checked_at"]
    assert m["where"]["reading"]["state"] == "ready"
    route = json.loads(page.py(ON_THE_DAY + "import reading, json; "
                               "print(json.dumps(reading.route(())))"))
    assert route["route"] == "page" and route["usable"] and "queue-page" in route["do"]
    assert route["say"] == ""
    told = page.py(ON_THE_DAY + "print(place.check('desktop-cloud', 'browser', []))").strip()
    assert told == "[]"


def test_a_profile_the_page_read_is_logged_as_a_computer_chats_read_is(page):
    page.act("reader.checked", "linkedin-reader", value={"ok": True}, rev="")
    page.apply()
    page.written_back()
    cid = "kestrel_mutual_varga"             # not written to yet: one a run would read
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                          "queue-page", cid], env=page.env(), capture_output=True,
                         encoding="utf-8", cwd=ROOT)
    assert out.returncode == 0 and "queued for the page" in out.stdout
    (q,) = page.model()["linkedin"]["reading"]["queue"]
    assert q["contact"] == cid and q["reach"] == f"reach/{cid}"
    text = ("Tamsin Varga\nPricing Analytics Lead at Kestrel Mutual\nManchester\n"
            "About\nI lead the pricing analytics team.\nExperience\n"
            "Pricing Analytics Lead\nKestrel Mutual\n2022 - Present\n")
    aid = page.act("reading.done", q["id"], value={"text": text, "mode": "card"}, rev=q["rev"])
    got = page.apply()
    assert got["ok"] == [aid], page.receipt(aid)["note"]
    saved = page.py(f"import reading; print(reading.load({cid!r}) is not None)").strip()
    assert saved == "True"
    assert page.model()["linkedin"]["reading"]["queue"] == []
    batch = json.load(open(got["batches"][0], encoding="utf-8"))
    wipe = next(e for e in batch if e["collection"] == "actions" and e["doc_id"] == aid)
    assert json.load(open(wipe["file_path"], encoding="utf-8")) == {
        "value": {"text": {"__delete__": True}}, "_v": wipe["if_version"] + 1}


def test_nothing_here_fetches_linkedin():
    for rel in ("tools/app_actions.py", "tools/app_model.py", "tools/network/export.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            src = fh.read()
        assert "urlopen" not in src and "requests.get" not in src, rel
    _ = PELL


# A message with a line break of its own: a cut inside its quotes would split it in two.
EXTRA = ('conv-juno,,Juno Castellan,https://ca.linkedin.com/in/example-juno-castellan,'
         'Morgan Ellis,https://www.linkedin.com/in/morgan-ellis-example,'
         '2026-09-12 09:00:00 UTC,,"Thanks Morgan.\nHappy to talk next week.",INBOX,\n')


def _split_on_the_page(text, max_chars):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    fn = js[js.index("  function splitCsv(text, max) {"):]
    fn = fn[:fn.index("\n  }\n") + 4]
    out = subprocess.run([node, "-e", fn + "\nprocess.stdout.write(JSON.stringify(splitCsv("
                          "require('fs').readFileSync(0, 'utf8'), " + str(max_chars) + ")));"],
                         input=text.encode("utf-8"), capture_output=True, timeout=60)
    # Bytes both ways: a text pipe on Windows writes every "\n" as "\r\n", so the splitter
    # saw "\r\r\n" where the page itself reads the file as it is (CI, 2026-10-29).
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return json.loads(out.stdout.decode("utf-8"))


def _take_messages(page, aid, messages_assets):
    os.makedirs(page.assets, exist_ok=True)
    assets = list(messages_assets)
    for asset, name in FILES.items():
        if name != "messages.csv":
            shutil.copyfile(os.path.join(FIX, name), os.path.join(page.assets, asset + ".csv"))
            assets.append({"id": asset, "name": name})
    page.put("actions", aid, {"action": "export.take", "item": "linkedin-export",
                              "value": {"assets": assets}, "at": "2026-10-25T17:10:00Z",
                              "rev_seen": "", "tab": "t1"}, version=1)
    got = page.apply_assets()
    assert got["ok"] == [aid], page.receipt(aid)
    return page.receipt(aid)["counts"]


def test_a_file_over_the_pages_limit_comes_in_parts_and_is_joined_whole(tmp_path):
    """A busy inbox's messages run to tens of megabytes, over the page store's 20 MiB. It was
    refused with "ask in Chat", which led nowhere (2026-10-29). Now the page sends it in parts
    of whole records, each under the file's first line, and the engine joins them again."""
    with open(os.path.join(FIX, "messages.csv"), encoding="utf-8", newline="") as fh:
        src = fh.read()
    src = src + ("" if src.endswith("\n") else "\n") + EXTRA
    parts = _split_on_the_page(src, 300)
    head = src.split("\n", 1)[0] + "\n"
    assert len(parts) > 2 and all(p.startswith(head) for p in parts)
    assert parts[0] + "".join(p[len(head):] for p in parts[1:]) == src
    assert all(p.count('"') % 2 == 0 for p in parts)          # whole records in every part
    assert any("Thanks Morgan.\nHappy to talk" in p for p in parts)
    whole = Page(str(tmp_path / "whole"))
    with open(os.path.join(whole.root_assets(), "a1" * 16 + ".csv"), "w", encoding="utf-8",
              newline="") as fh:
        fh.write(src)
    want = _take_messages(whole, "act-whole", [{"id": "a1" * 16, "name": "messages.csv"}])
    split = Page(str(tmp_path / "split"))
    given = []
    for k, text in enumerate(parts, 1):
        asset = f"{k:02x}" * 16
        with open(os.path.join(split.root_assets(), asset + ".csv"), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write(text)
        given.append({"id": asset, "name": "messages.csv", "part": k})
    got = _take_messages(split, "act-parts", given)
    assert got == want and got["messages"] > 0
