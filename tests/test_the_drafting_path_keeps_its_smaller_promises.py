"""The drafting path's smaller promises, each kept: names, research manners, costs, pages.

- A second role at an employer whose title is all filler ("Senior Analyst") got the
  machine-looking "KestrelMutual_Role", and a third crashed staging with a traceback whose
  advice could not apply to /apply.
- `stage` printed `picks.json` as the workflow's args; the args are `draft_args.json`,
  which `tools/draft_pack.py build` writes, and without it every draft was flagged no-pack.
- A bare domain redirecting to www (robots.txt included) was read as a refusal and noted
  refused for a fortnight. A URL from inside the posting was fetched when written with http
  or a tracking query. The crawl delay was not kept between robots.txt and the first page.
  Two runs for one employer at once spent its daily budget twice.
- The costs of two roles at one employer were merged: the agents were labelled by company.
- A sign the font has no glyph for passed the round trip, and the letters were never read
  for a replacement character.
- When a letter overflowed, the trimmer dropped the close's last sentence, the one written
  for this role, and left the right-to-work sentence every letter shares as the closing.

Every employer, posting and site here is invented.
"""
from __future__ import annotations

import copy
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import company_research as CR  # noqa: E402
import docpaths  # noqa: E402
import draft_cost  # noqa: E402
import fit_to_page  # noqa: E402
import stage_picks  # noqa: E402
import untrusted  # noqa: E402
import verify_pdf  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE, labels, run_workflow  # noqa: E402

PAGE = ("<html><title>About</title><body><p>"
        + "We serve 2 million customers across the north of England every year. " * 3
        + "</p></body></html>")


def _row(role, status, abbr):
    return {"company": "Kestrel Mutual", "role": role, "status": status,
            "cv_file": docpaths.resume_rel(abbr), "cover_letter_file": docpaths.letter_rel(abbr)}


# ------------------------------------------------------------------ names

def test_a_filler_only_title_is_named_by_its_own_words_and_never_crashes(tmp_path):
    rows = [_row("Data Analyst", "applied", "KestrelMutual")]
    abbr = stage_picks.choose_abbr("Kestrel Mutual", "Senior Analyst", rows, str(tmp_path))
    assert abbr == "KestrelMutual_SeniorAnalyst"
    rows.append(_row("Senior Analyst", "applied", abbr))
    third = stage_picks.choose_abbr("Kestrel Mutual", "Senior Analyst", rows, str(tmp_path))
    assert third not in (abbr, "KestrelMutual") and third.startswith("KestrelMutual_")
    assert not third.endswith("_Role")


def test_stage_names_the_pack_build_and_the_workflow_args(tmp_path, capsys):
    staged = stage_picks.stage(str(tmp_path), ["1"], rows=[], root=str(tmp_path), shortlist=[{
        "company": "Kestrel Mutual", "title": "Claims Forecasting Analyst", "location": "Manchester",
        "url": "https://jobs.example/1", "portal": "pasted", "desc": FIXTURE["posting"]}])
    stage_picks._report(staged, str(tmp_path))
    out = capsys.readouterr().out
    assert f"python3 tools/draft_pack.py build {tmp_path}" in out
    assert os.path.join(str(tmp_path), "draft_args.json") in out
    assert "args for the draft-applications workflow: " + os.path.join(str(tmp_path), "picks.json") \
        not in out


# ------------------------------------------------------------------ research manners

def _posting(tmp_path, body):
    f = tmp_path / "01_kestrel.md"
    f.write_text("# Kestrel Mutual | Analyst\n\n- location: Manchester, UK\n\n"
                 + untrusted.fence(body) + "\n", encoding="utf-8")
    return str(f)


def test_a_robots_txt_behind_a_redirect_is_read_not_refused(tmp_path):
    seen = []

    def transport(url, headers):
        seen.append(url)
        if url.startswith("https://kestrel.example/"):
            return 301, {"location": url.replace("https://kestrel.example/",
                                                 "https://www.kestrel.example/")}, ""
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, "User-agent: *\nAllow: /\n"
        return 200, {"content-type": "text/html"}, PAGE
    rep = CR.fetch("Kestrel Mutual", urls=["https://kestrel.example/about"], today="2026-10-21",
                   root=str(tmp_path / "root"), transport=transport, sleep=lambda s: None,
                   pages=str(tmp_path / "pages"))
    assert [u["state"] for u in rep["urls"]] == ["ok"]
    note = CR.host_notes(str(tmp_path / "root")).get("kestrel.example") or {}
    assert note.get("status") != "refused"


def test_a_link_from_the_posting_is_never_fetched_however_it_is_written(tmp_path):
    post = _posting(tmp_path, "Apply at https://www.kestrel.example/careers/123 today.")
    calls = []
    rep = CR.fetch("Kestrel Mutual", urls=["http://www.kestrel.example/careers/123",
                                           "https://www.kestrel.example/careers/123?src=li",
                                           "https://kestrel.example/careers/123/"],
                   posting=post, today="2026-10-22", root=str(tmp_path / "root"),
                   transport=lambda u, h: calls.append(u) or (200, {}, PAGE),
                   sleep=lambda s: None, pages=str(tmp_path / "pages"))
    assert [u["state"] for u in rep["urls"]] == ["refused", "refused", "refused"] and calls == []


def test_the_crawl_delay_is_kept_from_robots_txt_to_the_first_page(tmp_path, monkeypatch):
    clock = [1_000_000.0]
    log = []
    monkeypatch.setattr(CR.time, "time", lambda: clock[0])

    def sleep(s):
        clock[0] += s

    def transport(url, headers):
        log.append((clock[0], url))
        clock[0] += 0.2
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, "User-agent: *\nCrawl-delay: 10\nAllow: /\n"
        return 200, {"content-type": "text/html"}, PAGE
    CR.fetch("Kestrel Mutual", urls=["https://www.kestrel.example/about",
                                     "https://www.kestrel.example/news"],
             today="2026-10-21", root=str(tmp_path / "root"), transport=transport, sleep=sleep,
             pages=str(tmp_path / "pages"))
    gaps = [b[0] - a[0] for a, b in zip(log, log[1:])]
    assert len(log) == 3 and all(g >= 10 for g in gaps), log


def test_two_runs_for_one_employer_share_one_budget(tmp_path):
    count = [0]
    lock = threading.Lock()
    # Both runs have started (each has read the day's count) before either goes on: two
    # roles at one employer researched at once.
    started = threading.Barrier(2, timeout=5)
    first = set()

    def transport(url, headers):
        with lock:
            count[0] += 1
            me = threading.get_ident()
            waits = me not in first
            first.add(me)
        if waits:
            try:
                started.wait()
            except threading.BrokenBarrierError:
                pass
        if url.endswith("/robots.txt"):
            return 200, {}, "User-agent: *\nAllow: /\n"
        return 200, {}, PAGE
    urls = [f"https://h{i}.kestrel.example/p" for i in range(12)]
    pages = str(tmp_path / "pages")

    def run(k):
        CR.fetch("Kestrel Mutual", urls=urls[k::2] + urls[(k + 1)::2], today="2026-10-21",
                 root=str(tmp_path / "root"), transport=transport, sleep=lambda s: None,
                 pages=pages)
    ts = [threading.Thread(target=run, args=(k,)) for k in (0, 1)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert count[0] <= CR.FETCH_BUDGET


# ------------------------------------------------------------------ costs

def test_two_roles_at_one_employer_keep_their_own_costs():
    res = [{"pick": {"slug": "acme", "company": "Acme", "role": "Data Analyst", "abbr": "Acme"},
            "cost": [{"stage": "draft", "calls": 1, "approx_prompt_tokens": 100}]},
           {"pick": {"slug": "acme_2", "company": "Acme", "role": "Pricing Analyst",
                     "abbr": "Acme_Pricing"},
            "cost": [{"stage": "draft", "calls": 1, "approx_prompt_tokens": 100}]}]
    usage = [{"label": "draft:acme", "tokens": 1000, "tool_calls": 3, "seconds": 60},
             {"label": "draft:acme_2", "tokens": 9000, "tool_calls": 30, "seconds": 600}]
    rows = draft_cost.per_posting(res, usage)
    assert rows["acme"]["totals"]["tokens"] == 1000 and rows["acme_2"]["totals"]["tokens"] == 9000
    # An older run's company label names two postings here, and is given to neither.
    rows = draft_cost.per_posting(res, [{"label": "draft:Acme", "tokens": 9000}])
    assert rows["acme"]["totals"]["tokens"] is None and rows["acme_2"]["totals"]["tokens"] is None
    # The workflow labels its agents by slug.
    got = run_workflow({"A": "clean", "B": "clean"}, pack="P")
    assert labels(got, "draft") == ["draft:a", "draft:b"]


# ------------------------------------------------------------------ pages

def test_a_sign_the_font_lacks_is_named_by_the_round_trip():
    groups = [("Profile (the summary)", [("summary", "Forecast error at ≥ 95% accuracy")])]
    assert verify_pdf.roundtrip(groups, "Profile Forecast error at � 95% accuracy")
    assert verify_pdf.roundtrip(groups, "Profile Forecast error at ≥ 95% accuracy") == []


def test_trimming_a_long_close_keeps_the_sentence_written_for_this_role():
    a = copy.deepcopy(FIXTURE["draft"])
    last = a["p4"].split(". ", 1)[1]
    for _ in range(3):
        fit_to_page.trim_letter(a, 15, page_over=True)
    assert a["p4"].endswith(last)
    # A close with more sentences loses one that is neither its last nor where the
    # candidate is and their right to work.
    a = copy.deepcopy(FIXTURE["draft"])
    a["p4"] = ("I am based in Manchester. I have full right to work in the UK, so no sponsorship "
               "is needed. I would enjoy the weekly rhythm of a claims team very much. " + last)
    a["claim_map"] = [{"field": "p4", "sentence": "I am based in Manchester.", "cites": ["LOC"]},
                      {"field": "p4", "sentence": "I have full right to work in the UK, so no "
                       "sponsorship is needed.", "cites": ["AUTH"]}]
    fit_to_page.trim_letter(a, 15, page_over=True)
    assert "full right to work" in a["p4"] and a["p4"].endswith(last)
    assert "weekly rhythm" not in a["p4"]



def test_a_close_that_repeats_a_line_can_still_be_cut():
    # The sentences kept are kept by place, not by wording: kept by wording, every sentence
    # worded like the kept one was kept too, and a close repeating one line could not be
    # shortened at all (a person's own test of the trimmer caught it).
    close = " ".join(["Closing sentence offering a conversation."] * 8)
    assert len(fit_to_page.shorten_close(close, 30).split()) <= 30
    kept = fit_to_page.shorten_close(close, 30, keep=["Closing sentence offering a conversation."])
    assert kept.startswith("Closing sentence") and len(kept.split()) <= 30
