"""Every other JSON state file two chats can both change merges by its writer's own rules.

Each case is a person's copy in a real git repo: a common start, then two chats on two
branches, each changing the file with that file's own writer, merged by real git through
tools/merge_state.py. Where a writer can save what it reads, the merged file is saved again
through it and must not change by a byte: the merge writes it as its writer does. Git stops
only where nothing says which change is later.

Every person, employer, page and link here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import merge_state as M  # noqa: E402
import person  # noqa: E402
from test_two_chats_writing_the_page_files_merge_key_by_key import Repo  # noqa: E402

D1, D2, D3 = "2026-10-21", "2026-10-23", "2026-10-25"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy whose profile is the example person's, without the state files the tests
    write, so each starts where a test says."""
    import shutil
    import app_state
    r = Repo(tmp_path, monkeypatch)
    shutil.rmtree(r.profile)
    app_state.profile_copy(r.profile)
    for name in ("build_versions.json", "asked.json", "place.json", "routines.json"):
        os.remove(os.path.join(r.profile, name))
    person.reset()
    yield r
    person.reset()


def two_chats(repo, base, theirs, ours, theirs_at="2026-10-25T15:00:00Z",
              ours_at="2026-10-25T11:00:00Z"):
    """Run `base` and commit; `theirs` on a branch; `ours` on master; merge theirs in."""
    with open(os.path.join(repo.root, "README"), "w", encoding="utf-8") as fh:
        fh.write("a copy\n")
    if base:
        base()
    repo.commit("base")
    repo.side("other", new=True)
    theirs()
    repo.commit("theirs", when=theirs_at)
    repo.side("master")
    ours()
    repo.commit("ours", when=ours_at)
    r = repo.merge()
    return r, r.stdout + r.stderr


def unchanged(repo):
    """Saved again through its writer, the merged file reads as git committed it."""
    assert repo.git("status", "--porcelain").stdout == "", repo.git("diff").stdout


def written_as(repo, rel, **how):
    """The merged file is, byte for byte, what its writer's own json.dump call makes of it:
    for a writer that only ever adds, so cannot save what it read unchanged. `newline`
    False for a writer that ends the file without one."""
    newline = how.pop("newline", True)
    with open(os.path.join(repo.root, rel), encoding="utf-8") as fh:
        text = fh.read()
    assert text == json.dumps(json.loads(text), **how) + ("\n" if newline else "")


def read(repo, *parts):
    with open(os.path.join(repo.root, *parts), encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ the profile


def test_build_versions_keep_the_higher_version_and_tell_nobody(repo, monkeypatch):
    import build_versions as B
    versions = {"drafts": 50, "boards": 22}
    monkeypatch.setattr(B, "current", lambda name: versions[name])
    r, said = two_chats(
        repo, lambda: B.record(["drafts"], today=D1),
        lambda: (versions.update(drafts=51), B.record(["drafts"], today=D2)),
        lambda: (versions.update(drafts=50), B.record(["boards"], today=D3)))
    assert r.returncode == 0, said
    got = read(repo, "profile", "build_versions.json")
    assert got == {"boards": {"version": 22, "date": D3}, "drafts": {"version": 51, "date": D2}}
    B.record([], today=D3)
    unchanged(repo)
    # Both changed one part: the higher version stands, said, and not for the person.
    repo.side("other")
    versions.update(drafts=52)
    B.record(["drafts"], today=D1)
    repo.commit("an older chat, a newer version", when="2026-10-25T09:00:00Z")
    repo.side("master")
    versions.update(drafts=51)
    B.record(["drafts"], today=D3)
    repo.commit("a newer chat, an older version", when="2026-10-25T19:00:00Z")
    r = repo.merge()
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    assert read(repo, "profile", "build_versions.json")["drafts"]["version"] == 52
    assert "version 52 against 51" in said and "nothing to tell the person" in said
    assert "Claude: tell the person" not in said


def test_employers_judged_on_two_chats_are_both_kept_and_a_rejudgement_takes_the_later(repo):
    import bar
    bar._judged_cache.clear()
    r, said = two_chats(
        repo, lambda: bar.judge("Oakmere Foods", "pay", "pays at the top of the band", today=D1),
        lambda: (bar.judge("Fernhill Freight", "signal", "a name planners know", today=D2),
                 bar.judge("Oakmere Foods", "prestige", "the best known grocer", today=D2)),
        lambda: (bar.judge("Larkspur Retail", "none", "nothing to say for it", today=D3),
                 bar.judge("Oakmere Foods", "none", "pay cut this year", today=D3)))
    assert r.returncode == 0, said
    got = read(repo, "profile", "employers_judged.json")
    assert set(got) == {"fernhill freight", "larkspur retail", "oakmere foods"}
    assert got["oakmere foods"]["verdict"] == "none" and got["oakmere foods"]["date"] == D3
    bar._judged_cache.clear()
    bar.judge("Oakmere Foods", "none", "pay cut this year", today=D3)
    unchanged(repo)
    bar._judged_cache.clear()


def test_a_no_on_two_chats_is_kept_and_the_later_no_stands(repo):
    import profile_upgrades as P
    a, b = P.REGISTRY[0].id, P.REGISTRY[1].id
    r, said = two_chats(
        repo, lambda: P.record_no(a, dt.date.fromisoformat(D1)),
        lambda: P.record_no(b, dt.date.fromisoformat(D2)),
        lambda: P.record_no(a, dt.date.fromisoformat(D3)))
    assert r.returncode == 0, said
    got = read(repo, "profile", "asked.json")
    assert got[a]["no"] == D3 and got[b]["no"] == D2
    P.record_no(a, dt.date.fromisoformat(D3))
    unchanged(repo)


def test_where_they_work_takes_the_later_answer_and_setup_stays_with_whoever_started_first(
        repo, monkeypatch):
    import place
    monkeypatch.setattr(place, "this_chat", lambda env=None: "chat-cloud")
    r, said = two_chats(
        repo, lambda: place.record("phone", dt.date.fromisoformat(D1)),
        lambda: (place.record("both", dt.date.fromisoformat(D2)),
                 place.mark_setup("started", dt.date.fromisoformat(D1))),
        lambda: (monkeypatch.setattr(place, "this_chat", lambda env=None: "chat-computer"),
                 place.record("computer", dt.date.fromisoformat(D3)),
                 place.mark_setup("started", dt.date.fromisoformat(D2))))
    assert r.returncode == 0, said
    got = read(repo, "profile", "place.json")
    assert got["works_on"] == "computer" and got["asked"] == D3
    assert got["setup"] == {"started": D1, "chat": "chat-cloud"}
    place.record("computer", dt.date.fromisoformat(D3))
    unchanged(repo)


def test_scheduled_tasks_recorded_on_two_chats_keep_every_task(repo):
    import routines
    path = os.path.join(repo.profile, "routines.json")

    def a_round():
        reg = routines.load(path)
        reg["routines"].append({"key": "job_round", "name": "Job search: shortlist",
                                "trigger_id": "trig_ROUND", "cron": "0 7 * * 1"})
        with open(path, "w", encoding="utf-8") as fh:      # as Claude adds one, by hand
            json.dump(reg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    r, said = two_chats(
        repo, lambda: routines.record("session_A", "trig_A", path=path),
        a_round,
        lambda: routines.record("session_B", "trig_B", path=path),
        theirs_at="2026-10-25T09:00:00Z", ours_at="2026-10-25T10:00:00Z")
    assert r.returncode == 0, said
    got = routines.load(path)
    assert [t["key"] for t in got["routines"]] == ["morning_brief", "job_round"]
    assert got["routines"][0]["trigger_id"] == "trig_B"
    routines.record("session_B", "trig_B", path=path)
    unchanged(repo)


def test_findings_kept_on_two_chats_are_all_kept(repo, monkeypatch):
    import profile_consistency as C

    def finding(n):
        return {"file": "01-candidate-profile.md", "line": n, "fact": "a date",
                "said": f"20{n:02d}", "sentence": f"Joined in 20{n:02d}."}
    shown = [finding(1), finding(2), finding(3)]
    monkeypatch.setattr(C, "findings", lambda: shown)
    r, said = two_chats(
        repo, lambda: C.keep(["01-candidate-profile.md:1"], today=D1),
        lambda: C.keep(["01-candidate-profile.md:2"], today=D2),
        lambda: C.keep(["01-candidate-profile.md:3"], today=D3))
    assert r.returncode == 0, said
    assert [f["said"] for f in C.reviewed()] == ["2001", "2003", "2002"]
    written_as(repo, "profile/consistency_reviewed.json", indent=1)


def test_a_scoring_baseline_recorded_on_two_chats_keeps_each_posting(repo, monkeypatch):
    import score_eval as S
    corpus = os.path.join(repo.root, "corpus")
    os.makedirs(corpus)
    monkeypatch.setattr(S, "CORPUS", corpus)
    monkeypatch.setattr(S, "BASELINE", os.path.join(repo.profile, "tests", "fixtures",
                                                    "score_baseline.json"))
    os.makedirs(os.path.dirname(S.BASELINE), exist_ok=True)
    stems = {"stems": ["pass__planner"]}
    monkeypatch.setattr(S, "cases", lambda: [{"stem": s} for s in stems["stems"]])
    monkeypatch.setattr(S, "evaluate", lambda c: {"stem": c["stem"], "fit": 70})
    monkeypatch.setattr(sys, "argv", ["score_eval.py", "--update"])

    def update(*new):
        stems["stems"] = ["pass__planner", *new]
        os.makedirs(os.path.dirname(S.BASELINE), exist_ok=True)
        assert S.main() == 0
    r, said = two_chats(repo, update, lambda: update("cut__night_shift"),
                        lambda: update("pass__analyst"))
    assert r.returncode == 0, said
    assert set(json.load(open(S.BASELINE, encoding="utf-8"))) == {
        "pass__planner", "cut__night_shift", "pass__analyst"}
    stems["stems"] = ["pass__planner", "cut__night_shift", "pass__analyst"]
    assert S.main() == 0
    unchanged(repo)


# ------------------------------------------------------------------ the search


@pytest.mark.parametrize("how", [{}, {"indent": 2}], ids=["one line", "indented"])
def test_employers_ruled_out_on_two_chats_are_both_kept_in_the_files_own_format(repo, how):
    """Claude writes this file by hand; the merge keeps whatever shape it was written in."""
    path = os.path.join(repo.root, "job_scraper", "do_not_target.json")

    def write(data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, **how)

    def entry(day, until):
        return {"reason": "the office there is sales only", "scope": "all",
                "established_by": "careers page", "recorded": day, "review_after": until}
    start = {"_README": "Employers with no relevant presence.",
             "companies": {"Quayside Foods": entry(D1, "2027-01-01")}}
    r, said = two_chats(
        repo, lambda: write(start),
        lambda: write({**start, "companies": {**start["companies"],
                                              "Lanternfish": entry(D2, "2027-02-01")}}),
        lambda: write({**start, "companies": {"Quayside Foods": entry(D3, "2027-04-01"),
                                              "Larkspur Retail": entry(D3, "2027-03-01")}}))
    assert r.returncode == 0, said
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    got = json.loads(text)
    assert set(got["companies"]) == {"Quayside Foods", "Lanternfish", "Larkspur Retail"}
    assert got["companies"]["Quayside Foods"]["review_after"] == "2027-04-01"
    assert text == json.dumps(got, **how), "kept in the shape it was written in"


def test_jobs_brought_back_into_one_round_on_two_chats_are_all_on_its_shortlist(repo):
    import filtered
    import run_round
    rounds = os.path.join(repo.root, "documents", "rounds")
    seen = os.path.join(repo.root, "job_scraper", "seen_jobs.json")

    def gone(n, company):
        return {"url": f"https://jobs.example.com/{n}", "title": "Demand Planner",
                "company": company, "location": "Leeds", "stage": "text screen",
                "rule": "years", "reason": "asks for 8 years"}

    def base():
        os.makedirs(os.path.join(repo.root, "rN"))
        short = os.path.join(repo.root, "rN", "06_shortlist.json")
        with open(short, "w", encoding="utf-8") as fh:
            json.dump([{"url": "https://jobs.example.com/0", "title": "Planner",
                        "company": "Quayside Foods", "priority": 80, "fit": 78}], fh)
        run_round.write_summary(short, rounds, "r7")
        os.makedirs(os.path.join(rounds, "filtered"))
        with open(filtered.path_for(rounds, "r7"), "w", encoding="utf-8") as fh:
            json.dump({"round": "r7", "counts": {"years": 2},
                       "filtered": [gone(1, "Lanternfish"), gone(2, "Larkspur Retail")]}, fh)
        os.makedirs(os.path.dirname(seen), exist_ok=True)
        with open(seen, "w", encoding="utf-8") as fh:
            json.dump({"seen": {}}, fh, indent=2)
        import shutil
        shutil.rmtree(os.path.join(repo.root, "rN"))

    def bring(n):
        return lambda: filtered.back("r7", [f"https://jobs.example.com/{n}"], why="worth a look",
                                     summary_dir=rounds, today=D3, seen_path=seen)
    r, said = two_chats(repo, base, bring(1), bring(2))
    assert r.returncode == 0, said
    rows = read(repo, "documents", "rounds", "r7.json")
    assert [x["url"][-1] for x in rows] == ["0", "2", "1"]
    written_as(repo, "documents/rounds/r7.json", indent=1, ensure_ascii=False)


def test_the_slow_boards_cursor_takes_the_further_along(repo, monkeypatch):
    import scrape_wide as W
    monkeypatch.setattr(W, "SWEEP_STATE", None)

    def sweep(sent, day, skill="jobsite-a"):
        monkeypatch.setattr(W, "PLAN", {skill: ("rotate", 2, 10, 0)})
        W.save_cursor({skill: sent}, day)
    r, said = two_chats(repo, lambda: sweep(4, D1), lambda: sweep(9, D2),
                        lambda: (sweep(5, D3), sweep(3, D3, "jobsite-b")))
    assert r.returncode == 0, said
    got = read(repo, "documents", "rounds", ".sweep", "cursor.json")
    assert got["jobsite-a"]["date"] == D3 and got["jobsite-a"]["sent"] == 5
    assert set(got) == {"jobsite-a", "jobsite-b"}
    assert "the later round" in said and "nothing to tell the person" in said
    W._write_cursor(W._cursor())
    unchanged(repo)


# ------------------------------------------------------------------ networking


def test_the_own_profile_look_keeps_both_answers_and_every_dismissal(repo):
    import own_profile as O
    r, said = two_chats(
        repo, lambda: O.answer("photo", "no", today=D1),
        lambda: (O.answer("photo", "yes", today=D2),
                 O.dismiss("headline-length", "I like it long", today=D2)),
        lambda: (O.answer("open-to-work", "no", today=D3),
                 O.dismiss("no-banner", "a banner is not for me", today=D3)))
    assert r.returncode == 0, said
    got = O.load_review()
    assert got["answers"]["photo"]["answer"] == "yes"
    assert got["answers"]["open-to-work"]["answer"] == "no"
    assert {d["id"] for d in got["dismissed"]} == {"headline-length", "no-banner"}
    O.save_review(O.load_review())
    assert repo.git("status", "--porcelain", "--", "documents").stdout == ""


def test_what_a_computer_could_not_keep_in_its_own_ledger_merges(repo, monkeypatch):
    import pace
    import reading as R
    monkeypatch.setattr(pace, "put", lambda *a, **k: False)
    monkeypatch.setattr(pace, "update", lambda *a, **k: False)
    monkeypatch.setattr(R, "note_load", lambda *a, **k: None)
    t = dt.datetime.fromisoformat

    def chat(at, ids, page):
        R.mark_signed_in(t(at))
        R.page_read("people", f"https://www.linkedin.com/search/results/people/?p={page}",
                    t(at), people=10)
        R._save_shortlist(ids, t(at).date())
    r, said = two_chats(repo, lambda: chat("2026-10-25T08:00:00", ["juno_castellan"], 1),
                        lambda: chat("2026-10-25T10:00:00", ["juno_castellan", "ana_rook"], 2),
                        lambda: chat("2026-10-25T09:00:00", ["corwin_haldane"], 3))
    assert r.returncode == 0, said
    net = ("documents", "network")
    assert read(repo, *net, ".signed_in.json")["at"] == "2026-10-25T10:00:00"
    assert [x["url"][-1] for x in read(repo, *net, ".page_reads.json")["reads"]] == ["1", "3", "2"]
    # One day's short lists are one list, as the reader takes them.
    assert read(repo, *net, ".shortlist.json")["ids"] == ["corwin_haldane", "juno_castellan",
                                                          "ana_rook"]
    R.mark_signed_in(t("2026-10-25T10:00:00"))
    R._save_shortlist(["corwin_haldane", "juno_castellan", "ana_rook"], t(D3).date())
    unchanged(repo)
    written_as(repo, "documents/network/.page_reads.json", indent=1, newline=False)


def test_a_stop_and_a_lift_on_two_chats_keep_the_newer_snapshot_whole(repo, monkeypatch):
    import pace
    import reading as R
    monkeypatch.setattr(pace, "put", lambda *a, **k: False)
    t = dt.datetime.fromisoformat
    r, said = two_chats(
        repo, lambda: R._write_stop("security check", now=t("2026-10-25T08:00:00")),
        lambda: R._write_stop("signed out twice", now=t("2026-10-25T12:00:00")),
        lambda: R._write_stop("a CAPTCHA", now=t("2026-10-25T09:00:00")))
    assert r.returncode == 0, said
    got = read(repo, "documents", "network", ".reads_stopped.json")
    assert got["reason"] == "signed out twice" and got["at"] == "2026-10-25T12:00:00"
    written_as(repo, "documents/network/.reads_stopped.json", indent=1, newline=False)


def test_search_filters_balance_and_title_yields_merge(repo, monkeypatch):
    import reading as R
    import sources
    import state
    monkeypatch.setattr(sources, "_title_in", lambda q: q.split(" at ")[0])
    people = "https://www.linkedin.com/search/results/people/?currentCompany=%5B%22{}%22%5D"

    def chat(company, n, balance, day, title):
        R.learn_search(people.format(n), company)
        state.record_inmails(balance, [], [], dt.date.fromisoformat(day))
        sources.record_yield(company, f"{title} at {company}", 3, 1,
                             dt.date.fromisoformat(day))
    r, said = two_chats(repo, lambda: chat("Quayside Foods", 1, 5, D1, "planner"),
                        lambda: chat("Lanternfish", 2, 4, D2, "analyst"),
                        lambda: chat("Larkspur Retail", 3, 3, D3, "planner"))
    assert r.returncode == 0, said
    net = ("documents", "network")
    assert set(read(repo, *net, ".search_filters.json")["employers"]) == {
        "quayside", "lanternfish", "larkspur"} or len(
        read(repo, *net, ".search_filters.json")["employers"]) == 3
    assert read(repo, *net, ".inmail_credits.json")["balance"] == 3
    assert len(read(repo, *net, ".title_yield.json")) == 3
    chat("Larkspur Retail", 3, 3, D3, "planner")              # each writer again: no change
    unchanged(repo)


def test_one_person_read_on_two_chats_keeps_every_source_and_the_newer_page(repo):
    import reading as R
    cid = "juno_castellan"

    def read_on(day, headline, item):
        R.save(cid, R.merge(R.load(cid), {
            "name": "Juno Castellan", "company": "Quayside Foods", "read_on": day,
            "sources": [{"kind": "profile_page", "url": "https://www.linkedin.com/in/example-x",
                         "date": day}],
            "headline": headline, "location": "Leeds", "about": "", "current": "Quayside Foods",
            "degree": "2nd", "reach": "", "connect": "", "shared": {},
            "items": [{"kind": "post", "date": day, "url": "", "text": item}],
            "experience": [], "mutuals": []}))
    r, said = two_chats(repo, lambda: read_on(D1, "Planner", "a post on forecasting"),
                        lambda: read_on(D3, "Head of Planning", "a post on hiring"),
                        lambda: read_on(D2, "Senior Planner", "a post on promotions"))
    assert r.returncode == 0, said
    got = R.load(cid)
    assert got["headline"] == "Head of Planning" and got["read_on"] == D3
    assert [s["date"] for s in got["sources"]] == [D1, D2, D3]
    assert [i["text"] for i in got["items"]] == ["a post on forecasting", "a post on promotions",
                                                 "a post on hiring"]
    R.save(cid, R.load(cid))
    unchanged(repo)


def test_what_a_note_may_name_kept_on_two_chats_is_all_kept(repo):
    import reading as R
    cid = "ana_rook"
    r, said = two_chats(
        repo, lambda: R.keep_own_facts(cid, [("forecasting", "her talk")], "she wrote it", D1),
        lambda: R.keep_own_facts(cid, [("the 2025 report", "her team")], "her team's", D2),
        lambda: R.keep_own_facts(cid, [("demand sensing", "her post")], "her own post", D3))
    assert r.returncode == 0, said
    assert R.own_facts(cid) == {"forecasting", "the 2025 report", "demand sensing"}
    R.keep_own_facts(cid, [("forecasting", "her talk")], "she wrote it", D1)
    unchanged(repo)


def test_a_notes_parts_saved_two_ways_take_the_later_save_else_stop(repo):
    import parts
    cid = "corwin_haldane"

    def save(sha):
        return lambda: parts.save(cid, {"kind": "first_note", "args": {"opener": sha},
                                        "text_sha": sha})
    r, said = two_chats(repo, save("a" * 16), save("b" * 16), save("c" * 16),
                        theirs_at="2026-10-25T15:00:00Z", ours_at="2026-10-25T11:00:00Z")
    assert r.returncode == 0, said
    got = read(repo, "documents", "network", cid, "draft.parts.json")
    assert got["text_sha"] == "b" * 16 and got["args"] == {"opener": "b" * 16}
    parts.save(cid, got)
    unchanged(repo)


def test_a_composed_note_leaves_nothing_in_the_copy_until_its_draft_takes_it(repo):
    """A note's parts wait in this computer's ledger, never among the person's files: kept in
    the copy, every note composed and not written was a file left behind that stopped the
    next update (2026-10-26). Beside a draft they are the person's, and merge as one."""
    import parts
    parts.remember("first_note", {"opener": "Hello", "ask": "a call"}, "Hi Ana, a short note.")
    status = repo.git("status", "--porcelain", "--untracked-files=all").stdout
    assert "documents/" not in status, status
    assert parts.adopt("corwin_haldane", "Hi Ana, a short note.")
    assert os.path.isfile(os.path.join(repo.root, "documents", "network", "corwin_haldane",
                                       parts.PARTS))


def test_a_notes_parts_saved_two_ways_at_one_moment_stop_the_merge(repo):
    import parts
    cid = "corwin_haldane"

    def save(sha):
        return lambda: parts.save(cid, {"kind": "first_note", "args": {"opener": sha},
                                        "text_sha": sha})
    r, said = two_chats(repo, save("a" * 16), save("b" * 16), save("c" * 16),
                        theirs_at="2026-10-25T15:00:00Z", ours_at="2026-10-25T15:00:00Z")
    assert r.returncode != 0, said
    assert repo.unmerged() == [f"documents/network/{cid}/draft.parts.json"]


# ------------------------------------------------------------------ one application


def test_a_campaign_answer_and_the_packs_built_record_keep_the_newer_snapshot(
        repo, monkeypatch):
    import interview_pack as I
    company, role = "Quayside Foods", "Demand Planner"

    def campaign(**kw):
        return lambda: I.record_campaign(company, role, **kw)

    def built(stage):
        folder = I.docpaths.app_folder(company, role)
        monkeypatch.setattr(I, "_rebuild", lambda ctx, never_say=None: (
            f"# Prep\n{stage}\n", [], f"# Prep\n{stage}\n"))
        I.write_pack({"folder": folder, "stage": stage, "map": {"Why us?": "the move"}})
    r, said = two_chats(
        repo, lambda: (campaign(chat="", declined=True, today=D1)(), built("screen")),
        lambda: (campaign(chat="session_A", today=D2)(), built("first interview")),
        lambda: (campaign(chat="session_B", today=D3)(), built("second interview")),
        theirs_at="2026-10-25T15:00:00Z", ours_at="2026-10-25T11:00:00Z")
    folder = I.docpaths.app_folder(company, role)
    # The prep document itself is markdown, merged as lines: both chats rebuilt one line.
    assert repo.unmerged() == [os.path.relpath(I.living_path({"folder": folder}),
                                               repo.root).replace(os.sep, "/")], said
    with open(os.path.join(folder, "campaign.json"), encoding="utf-8") as fh:
        assert json.load(fh) == {"chat": "session_B", "started": D3}
    with open(I.built_path(folder), encoding="utf-8") as fh:
        assert json.load(fh)["stage"] == "first interview"      # the later commit's
    rel = os.path.relpath(folder, repo.root).replace(os.sep, "/")
    written_as(repo, rel + "/campaign.json", indent=1)
    written_as(repo, rel + "/.interview_prep.built.json", indent=1, ensure_ascii=False)


def test_a_kept_draft_and_its_cost_take_the_later_save(repo):
    import docpaths
    import draft_cost
    import fit_to_page
    company, role = "Lanternfish", "Supply Analyst"

    def draft(summary, calls):
        def go():
            folder = docpaths.app_folder(company, role, "LF")
            os.makedirs(folder, exist_ok=True)
            fit_to_page.save(os.path.join(folder, "draft.json"),
                             [{"company": company, "role": role, "summary": summary}], set())
            draft_cost.write(os.path.join(repo.root, "scratch"), [
                {"pick": {"slug": "lanternfish", "company": company, "role": role,
                          "abbr": "LF"},
                 "cost": [{"stage": "draft", "calls": calls, "approx_prompt_tokens": 900}]}])
        return go
    os.makedirs(os.path.join(repo.root, "scratch"))
    with open(os.path.join(repo.root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("scratch/\n")
    r, said = two_chats(repo, draft("Planner of four years.", 1),
                        draft("Planner who cut stock by a fifth.", 2),
                        draft("Planner, plainer.", 3))
    assert r.returncode == 0, said
    folder = docpaths.app_folder(company, role, "LF")
    got = json.load(open(os.path.join(folder, "draft.json"), encoding="utf-8"))
    assert got[0]["summary"] == "Planner who cut stock by a fifth."
    assert json.load(open(os.path.join(folder, "cost.json"), encoding="utf-8"))[
        "totals"]["calls"] == 2
    fit_to_page.save(os.path.join(folder, "draft.json"), got, set())
    unchanged(repo)


# ------------------------------------------------------------------ research


def test_two_chats_researching_one_employer_keep_every_fact_and_the_later_check(
        repo, tmp_path):
    import company_research as CR
    pages = str(tmp_path / "pages")
    url = "https://www.example.com/about"
    text = ("Quayside Foods runs forty stores across the north of England. "
            "It opened a new distribution centre in Leeds last spring. "
            "Its planning team moved to weekly forecasting this year.")
    CR._store_page(url, "About", text, "page", pages)

    def fact(sentence):
        return {"claim": sentence, "quote": sentence, "url": url}
    one = fact("Quayside Foods runs forty stores across the north of England.")
    two = fact("It opened a new distribution centre in Leeds last spring.")
    three = fact("Its planning team moved to weekly forecasting this year.")

    def save(facts, day, host_status):
        def go():
            CR.save("Quayside Foods", {"facts": facts, "fetched_date": day}, today=day,
                    pages=pages)
            CR.note_host("www.example.com", {"status": host_status, "last_checked": day})
        return go
    r, said = two_chats(repo, save([one], D1, "ok"), save([one, two], D2, "challenged"),
                        save([one, three], D3, "ok"))
    assert r.returncode == 0, said
    got = CR.load("Quayside Foods", today=D3)[0]
    assert [f["claim"][:12] for f in got["facts"]] == ["Quayside Foo", "Its planning", "It opened a "]
    assert got["facts"][0]["quote_checked"] == D3 and got["fetched_date"] == D3
    hosts = read(repo, "company_research", "_hosts.json")["hosts"]
    assert hosts["www.example.com"] == {"status": "ok", "last_checked": D3}
    assert "written later" in said and "'challenged'" in said
    CR.save("Quayside Foods", {}, today=D3, pages=pages)
    CR.note_host("www.example.com", {"status": "ok", "last_checked": D3})
    unchanged(repo)


def test_a_fact_one_chat_took_out_by_hand_is_never_dropped():
    base = {"facts": [{"claim": "A", "url": "https://x.example/a"},
                      {"claim": "B", "url": "https://x.example/b"}]}
    ours = {"facts": [{"claim": "A", "url": "https://x.example/a"}]}
    theirs = {"facts": base["facts"] + [{"claim": "C", "url": "https://x.example/c/"}]}
    text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                             "company_research/quayside_foods.json")
    assert not problems
    assert [f["claim"] for f in json.loads(text)["facts"]] == ["A", "B", "C"]


def test_a_facts_identity_is_the_research_tools_own():
    import company_research as CR
    for f in ({"claim": "x", "url": "HTTPS://Example.com/About/"},
              {"quote": "  It’s   a — Fact ", "source_url": "https://e.example/p?q=1"},
              "a bare fact"):
        assert M.fact_id(f) == CR._fact_id(f)


def test_the_files_wired_before_keep_their_writers_format_too(repo):
    """Tips and the LinkedIn download's record were written back with the merge's default
    shape, not their writers': every merge rewrote their lines."""
    import tips
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import export
    def shown(**more):
        got = tips.load()
        got.setdefault("shown", {}).update(more)
        tips.save(got)
    r, said = two_chats(repo, lambda: shown(search=D1), lambda: shown(apply=D2),
                        lambda: shown(networking=D3))
    assert r.returncode == 0, said
    assert tips.load()["shown"] == {"search": D1, "apply": D2, "networking": D3}
    tips.save(tips.load())
    unchanged(repo)
    assert export.record_path().endswith("linkedin_export.json")
    assert M.json_rules("documents/network/linkedin_export.json")["sort"] == "all"
