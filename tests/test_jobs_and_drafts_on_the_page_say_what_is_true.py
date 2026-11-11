"""Jobs, Drafts, Applied and the Brief on the page say what is true, once, in plain words.

The 3 November audit drove a real page: no card said when a job was posted or why it scored
what it did; a closed posting offered a referral ask and "I have applied"; "Also at" listed
the note to someone and then them again, and a draft's own role as somewhere else; "Apply
on their site" opened LinkedIn; "[check the tracker row]" sat behind a Copy button; the
resume the person must never send was one tap away; Applied said "66 applied" beside the
Brief's 54 and Drafts' 52, and "with an interview booked" of interviews with no day; a
follow-up two days late said "on Sun 1 Nov"; "usually 0" sat under a week of 51; Progress
said "Applied Applied"; a stage name led a heading in lower case; and news five days old
said only "Gathered". Each test taps the page as the person did. Every person and employer
is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


T = "2026-10-25T09:00:00Z"


def _row(m, rid):
    return next(r for r in m["jobs"]["rows"] if r["id"] == rid)


ROWS = """[...document.querySelectorAll('[data-item="ID"] .info-panel .m-row')].filter((r) => r.getClientRects().length)
  .map((r) => [r.querySelector('.m-label').textContent.trim(), r.querySelector('.m-body').innerText.trim()])"""


def test_a_job_card_says_when_it_was_posted_and_why_it_scored_what_it_did(run, tmp_path):
    """Why it scored what it did is the first row under More, and a watch-out is its own row:
    "Why 100: Matches your skills ... Asks for a graduate degree" read as a contradiction
    (the maintainer, 2026-11-04)."""
    m = _sample()
    _row(m, "r12-1")["reasons"] = {"good": "Matches your skills: SQL, Python.", "watch": "Asks for 5+ years in banking."}
    card = '[data-item="r12-1"]'
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": card + " .facts"},
        # Its details are a fold of their own, from "Why" on its line of facts (2026-11-05).
        {"click": "Why it scored 84: Harbourline Bank, Pricing Analyst", "eval": ROWS.replace("ID", "r12-1")},
    ], PHONE, model=m, clock=T)
    assert "Posted 5 days ago" in got["after"][0]["text"], got["after"][0]["text"]
    rows = got["after"][1]["eval"]
    assert rows[0] == ["Why it scored 84", "Matches your skills: SQL, Python."], rows
    assert rows[1] == ["Watch out", "Asks for 5+ years in banking."], rows


def test_a_jobs_line_of_facts_says_where_when_posted_and_when_found(run, tmp_path):
    """One line: the employer, the town (the engine's short form), when it was posted, when it
    was found and the pay (the maintainer, 2026-11-04 and 2026-11-05: "Calgary, Alberta,
    Canada (Remote)" pushed "Posted 5 days ago" onto a second line, and nothing said when each
    job was found)."""
    m = _sample()
    r = _row(m, "r12-1")
    r.update(place="Calgary, Alberta, Canada (Remote)", place_short="Calgary (Remote)", remote="remote",
             found_days=0, found_on="2026-10-25", deadline=None)
    # A drafted job is its draft's card, with the job's own facts (2026-11-05).
    _row(m, "r12-4").update(found_days=8, found_on="2026-10-17")
    got = _go(run, tmp_path, [{"hash": "jobs", "read": '[data-item="r12-1"] .facts'},
                              {"read": '[data-item="app-ellerwick-insight"] .facts'}], WIDE, model=m, clock=T)
    # Read as words: each dot keeps to the fact after it with a no-break space (the screen
    # review, 2026-11-11).
    line = [a["text"].replace("\u00a0", " ") for a in got["after"][:2]]
    assert line[0] == "Harbourline Bank · Calgary (Remote) · Posted 5 days ago · found today · £46,000 to £52,000 · Why", line[0]
    assert line[1].startswith("Ellerwick Trust · Salford · Found 17 Oct · "), line[1]


def test_each_pencil_stands_beside_its_own_documents_words(run, tmp_path):
    """The CV's pencil beside "CV 1 page" and the letter's beside "letter 1 page", from the
    engine's own words for each: two pencils side by side at the end of the line, one wrapped
    onto a line of its own, said nothing of which was which (the screenshots, 2026-11-05)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import app_model
    m = _sample()
    a = next(x for x in m["ready"] if x["id"] == "app-ellerwick-insight")
    a["checks"] = app_model._checks([{"kind": "resume", "made": True, "pages": 1},
                                     {"kind": "letter", "made": True, "pages": 1}], 1, "CV")
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": """[...document.querySelectorAll(
      '[data-item="app-ellerwick-insight"] .checks button')].map((b) => { const w = b.previousElementSibling;
        const mid = (e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; };
        return [b.textContent.trim(), w ? w.textContent : "", !!w && Math.abs(mid(w) - mid(b)) < 6
          && getComputedStyle(b.parentElement).whiteSpace === "nowrap"]; })"""}],
        PHONE, model=m, clock=T)
    pens = got["after"][0]["eval"]
    assert [w for _, w, _ in pens] == ["CV 1 page", "letter 1 page"], pens
    assert pens[0][0].startswith("Edit the CV") and pens[1][0].startswith("Edit the letter"), pens
    # Each pencil on the line of the words it edits, the two kept from breaking apart: on a phone
    # the letter's pencil wrapped onto a line of its own (the screenshots, 2026-11-05).
    assert all(same for _, _, same in pens), pens


MORE_PLACE = """(() => { const c = document.querySelector('[data-item="ID"]'); const s = c.querySelector('summary.more-btn');
  const row = s.closest('.card-actions'); const first = row.querySelector('.btn, a'); const p = c.querySelector('.more-panel:not(.info-panel)');
  const mid = (e) => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; };
  return {sameLine: Math.abs(mid(s) - mid(first)) < 4, below: p.getBoundingClientRect().top >= row.getBoundingClientRect().bottom - 1,
    shown: p.getClientRects().length > 0}; })()"""
ONE_SIZE = """(() => { const sizes = new Set(); const p = document.querySelector('[data-item="ID"] .info-panel');
  for (const el of p.querySelectorAll('*')) { if (!el.getClientRects().length || el.closest('.sr-only')) continue;
    if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) sizes.add(getComputedStyle(el).fontSize); }
  return [...sizes]; })()"""


# Each card's details fold, opened from its line of facts.
FOLD = {"r12-1": "Why it scored 84: Harbourline Bank, Pricing Analyst", "app-ellerwick-insight": "Why it scored 66: Ellerwick Trust, Research Analyst",
        "app-harbourline-risk": "Details: Harbourline Bank, Credit Risk Analyst"}


@pytest.mark.parametrize("where,item", [("jobs", "r12-1"), ("drafts", "app-ellerwick-insight"), ("applied", "app-harbourline-risk")])
def test_more_stays_in_the_actions_row_and_its_panel_is_one_size(run, tmp_path, where, item):
    """Opened, More left its row and stood alone on a line of its own over a panel of mixed
    sizes, a bullet list larger than the lines around it (the maintainer, 2026-11-04)."""
    seed = {"pref:jobs:tab": "applied"} if where == "applied" else {}
    got = _go(run, tmp_path, ([{"hash": "jobs", "click": "Applied"}] if where == "applied" else [{"hash": where}])
              + [{"more": item, "eval": MORE_PLACE.replace("ID", item)},
                 {"click": FOLD[item], "eval": ONE_SIZE.replace("ID", item)}], WIDE, clock=T, seed=seed)
    place = got["after"][-2]["eval"]
    assert place == {"sameLine": True, "below": True, "shown": True}, place
    assert len(got["after"][-1]["eval"]) == 1, ("one type size in More", got["after"][-1]["eval"])


def test_also_at_is_grouped_by_kind_and_each_link_names_what_it_opens(run, tmp_path):
    """"Also at <employer>: the role: ..., your draft, your draft, the message to ..., <name>,
    <name>": two links the same, nothing saying which role each draft was for, and no
    grouping (the maintainer, 2026-11-04)."""
    import copy
    m = _sample()
    own = _row(m, "r12-4")
    other = copy.deepcopy(own)
    other.update(id="r12-7", title="Data Analyst, Grants", draft="app-ellerwick-grants")
    lead = copy.deepcopy(own)
    lead.update(id="r12-8", title="Analyst, Policy", draft=None, status="new")
    m["jobs"]["rows"] += [other, lead]
    d = copy.deepcopy(next(a for a in m["ready"] if a["id"] == "app-ellerwick-insight"))
    d.update(id="app-ellerwick-grants", role="Data Analyst, Grants", job="r12-7")
    m["ready"].append(d)
    priya = next(p for p in m["people"] if p["id"] == "ellerwick_trust_priya")
    more = []
    for first in ("Rowan", "Sable", "Tovah", "Umber"):
        p = copy.deepcopy(priya)
        p.update(id="ellerwick_trust_" + first.lower(), first_name=first)
        m["people"].append(p)
        more.append(p["id"])
    own["related"] = {"jobs": ["r12-7", "r12-8"], "ready": ["app-ellerwick-insight", "app-ellerwick-grants"],
                      "messages": ["msg-priya-thanks"], "people": ["ellerwick_trust_priya"] + more}
    own["related"] = dict(own["related"])
    d0 = next(a for a in m["ready"] if a["id"] == "app-ellerwick-insight")
    d0["related"] = own["related"]
    got = _go(run, tmp_path, [{"hash": "jobs", "click": "Why it scored 66: Ellerwick Trust, Research Analyst", "eval": """(() => { const r = document.querySelector('[data-item="app-ellerwick-insight"] .related');
      return {links: [...r.querySelectorAll('a')].map((a) => a.textContent.trim()), text: r.innerText}; })()"""}], WIDE, model=m, clock=T)
    links, text = got["after"][0]["eval"]["links"], got["after"][0]["eval"]["text"]
    assert len(links) == len(set(links)), ("a link twice", links)
    assert "Roles: Analyst, Policy" in text, text
    assert "Drafts: your draft for Data Analyst, Grants" in text, "a role with its draft is the draft"
    assert all(x.startswith("your draft for ") for x in links if "draft" in x), links
    assert "Research Analyst" not in text, "the card's own role and draft are not also there"
    assert "People: the message to Marisol, Rowan, Sable and 2 more" in text, "a message stands for its person"


def test_the_warm_route_is_the_cards_one_soft_grey_box(run, tmp_path):
    """"Before you apply: <name> ... ask them first." stood as a rose line on one card while
    the cards above said the same in a soft grey box (the maintainer, 2026-11-05)."""
    m = _sample()
    import copy
    other = copy.deepcopy(_row(m, "r12-1"))
    other.update(id="r12-9", company="Ellerwick Trust", title="Analyst, Policy", related={"people": ["ellerwick_trust_priya"]},
                 warm="Marisol at Ellerwick Trust has replied to you: ask them first.", warm_contact="ellerwick_trust_priya")
    m["jobs"]["rows"].append(other)
    r = _row(m, "r12-1")
    r["suggest"] = {"level": 2, "id": "sg-warm-r12-1-a1", "kind": "warm",
                    "text": "Bea at Harbourline Bank replied to you: ask Bea about this role before applying.",
                    "why": "A reply is what makes a route warm.",
                    "action": {"type": "work", "label": "Write to Bea", "kind": "reply", "id": "reply~harbourline_bank_bea",
                               "title": "Write to Bea at Harbourline Bank", "args": {"contact": "harbourline_bank_bea"}},
                    "cost": {"state": 2, "label": "Some Claude"}, "since": "2026-10-25", "rev": "s9"}
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": """(() => { const w = document.querySelector('[data-item="r12-9"] .warm');
      const s = document.querySelector('[data-item="r12-1"] .suggest'); const bg = (e) => getComputedStyle(e).backgroundColor;
      return {box: bg(w) === bg(s) && bg(w) !== 'rgba(0, 0, 0, 0)', text: w.innerText, main: document.querySelector('#main').innerText.includes('Before you apply')}; })()"""}],
        WIDE, model=m, clock=T)
    said = got["after"][0]["eval"]
    assert said["box"], "the same soft grey box as the suggestion's"
    assert said["text"] == "Marisol at Ellerwick Trust has replied to you: ask them first.", said
    assert not said["main"], "said one way"


def test_each_jobs_card_marks_its_own_next_step_the_same_way(run, tmp_path):
    """The first card's "See the draft" was filled and the next cards' the same button a plain
    grey pill, read as two kinds of button (the maintainer, 2026-11-05): the screen's first next
    step is filled and every other card's is the semibold "next" pill, one a card (Buttons). A
    drafted job is its draft's card, in the job's place."""
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": """[...document.querySelectorAll('#main .card.job, #main .card.app')].map((c) =>
      [c.getAttribute('data-item'), c.querySelectorAll('.card-actions .btn.primary, .card-actions .btn.next').length])"""}], WIDE, clock=T)
    marked = dict(got["after"][0]["eval"])
    assert marked["r12-1"] == 1 and marked["app-ellerwick-insight"] == 1, marked
    assert max(marked.values()) == 1, marked


def test_a_long_title_fills_its_line_before_it_wraps(run, tmp_path):
    """A two-line title was balanced, so it broke at half a wide card's width (2026-11-04)."""
    m = _sample()
    # A drafted role, its state pill beside the title, as in the maintainer's screenshot.
    long = "Analyst/Consultant/Senior Consultant, Credit Risk and Data Analytics, Financial Engineering & Modelling"
    _row(m, "r12-4")["title"] = long
    next(a for a in m["ready"] if a["id"] == "app-ellerwick-insight")["role"] = long
    line = """(() => { const h = document.querySelector('[data-item="app-ellerwick-insight"] h3');
      const r = document.createRange(); r.selectNodeContents(h); const rects = [...r.getClientRects()].filter((b) => b.width > 0);
      const top = Math.min(...rects.map((b) => b.top)); const first = rects.filter((b) => Math.abs(b.top - top) < 4);
      return [new Set(rects.map((b) => Math.round(b.top / 4))).size,
              (Math.max(...first.map((b) => b.right)) - Math.min(...first.map((b) => b.left))) / h.clientWidth]; })()"""
    # Every screen is the whole width (4.10.1), so on a wide one the title fits on one line; a
    # narrower window wraps it, and there it fills its first line before it wraps.
    for vp, wraps in ((WIDE, False), ({"width": 900, "height": 900}, True)):
        got = _go(run, tmp_path, [{"hash": "jobs", "eval": line}], vp, model=m, clock=T)
        lines, filled = got["after"][0]["eval"]
        assert (lines > 1) == wraps, (vp, lines)
        assert lines == 1 or filled > 0.75, (vp, filled)


def test_a_closed_posting_offers_only_setting_it_aside(run, tmp_path):
    """And it waits under the list, "1 closed: Show", as what was set aside does: it is not
    one to look at (2026-11-05)."""
    m = _sample()
    r = _row(m, "r12-5")
    r["warm"] = "Noor at Brackenridge Advisory has replied to you: ask them first."
    r["warm_contact"] = "brackenridge_advisory_noor"
    card = '[data-item="r12-5"]'
    got = _go(run, tmp_path, [{"hash": "jobs", "count": "#main " + card},
                              # Nothing rare to do on it, so no More (2026-11-05).
                              {"click": "Show 1 closed"}, {"read": card, "count": card + " summary.more-btn"}], PHONE, model=m, clock=T)
    assert got["after"][0]["count"] == 0 and "1 closed: Show" in got["after"][0]["text"], got["after"][0]["text"][:400]
    text = got["after"][2]["text"]
    assert got["after"][2]["count"] == 0, "no More on a card with nothing rare"
    assert "Set it aside" in text
    for gone in ("for a referral", "I have applied", "Find people at", "ask them first"):
        assert gone not in text, (gone, text)


def test_also_at_names_each_person_once_and_never_the_cards_own_role(run, tmp_path):
    m = _sample()
    r = _row(m, "r12-5")
    r["apply"] = dict(r["apply"], status="open")
    r["alerts"] = []
    got = _go(run, tmp_path, [{"hash": "jobs", "more": "r12-5", "read": '[data-item="r12-5"] .related'}],
              PHONE, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "the note to Noor" in text and text.count("Noor") == 1, text
    d = _sample()
    a = next(x for x in d["ready"] if x["id"] == "app-ellerwick-insight")
    got = _go(run, tmp_path, [{"hash": "drafts", "more": a["id"], "read": '[data-item="app-ellerwick-insight"]'}],
              PHONE, model=d, clock=T)
    assert "the role: Research Analyst" not in got["after"][0]["text"], "a draft's own role is not elsewhere"


def test_a_draft_says_where_its_apply_link_goes_and_leaves_a_gap_to_the_person(run, tmp_path):
    m = _sample()
    a = next(x for x in m["ready"] if x["id"] == "app-ellerwick-insight")
    a["apply"] = {"url": "https://www.linkedin.com/jobs/view/4000000999/", "status": "not_checked", "kind": "linkedin"}
    a["screening"].append({"q": "How did you hear about this role?", "a": "", "fill": True})
    card = '[data-item="app-ellerwick-insight"]'
    got = _go(run, tmp_path, [
        {"hash": "drafts", "read": card},
        # What to copy is in its details, a fold from its line of facts (2026-11-05).
        {"click": "Why it scored 66: Ellerwick Trust, Research Analyst",
         "eval": "document.querySelector('[data-k=\"det:copy:app-ellerwick-insight\"]').open = true"},
        {"read": card, "count": card + ' [data-k^="copy:qa-"]'},
    ], PHONE, model=m, clock=T)
    assert "Apply on LinkedIn" in got["after"][0]["text"] and "Apply on their site" not in got["after"][0]["text"]
    opened = got["after"][2]
    assert "How did you hear about this role?" in opened["text"]
    assert "Yours to answer" in opened["text"]
    assert opened["count"] == 3, "a Copy for each answer Claude wrote, none for the gap"


def test_the_resume_that_breaks_the_persons_rules_offers_only_a_fresh_one(run, tmp_path):
    m = _sample()
    m["resume"]["breaks"] = ["it has dashes your documents never use"]
    m["resume"]["asset"] = None
    card = '[data-item="resume-current"], [data-item="resume-general"]'
    got = _go(run, tmp_path, [{"hash": "drafts", "read": card}], PHONE, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "Not to send" in text and "Make a fresh one" in text and "dashes your documents never use" in text
    assert "Get it" not in text and "Get this one anyway" not in text


def test_applied_says_what_it_counts_and_flags_a_late_follow_up(run, tmp_path):
    m = _sample()
    for a in m["applications"]:
        if a["id"] == "app-fernhill-ops":
            a["next"] = {"kind": "follow_up", "label": "Follow up", "date": "2026-10-23"}
    for i in m["interviews"]:
        if i["id"] == "int-harbourline-risk":
            i["when"] = None
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Applied", "read": "#main"},
    ], PHONE, model=m, clock=T, seed={"pref:jobs:tab": "applied"})
    text = got["after"][0]["text"]
    assert " still open" in text and " applied," not in text.split("\n")[0], text[:300]
    assert "1 interview with no day yet" in text, text[:300]
    # A follow-up the person set is ready, never late (the UX review of 2026-11-10, U-6, and the
    # review of 2026-11-11): it said "Follow-up due" and "Next: follow up, 2 days late".
    assert "Next: follow up, ready now" in text and "Follow-up ready" in text and "days late" not in text


def test_the_weeks_say_their_average_and_progress_says_applied_once(run, tmp_path):
    m = _sample()
    m["done"]["weeks"] = [{"week": "2026-W%02d" % w, "applied": n, "replies": 0}
                          for w, n in zip(range(36, 44), (10, 0, 0, 0, 0, 51, 3, 0))]
    got = _go(run, tmp_path, [
        {"hash": "brief", "read": '[data-k="spark-cap"]'},
        {"hash2": "progress", "read": "#main"},
    ], PHONE, model=m, clock=T)
    cap = got["after"][0]["text"]
    assert "about 8 a week on average" in cap and "usually" not in cap, cap
    assert "Applied Applied" not in got["after"][1]["text"]


def test_a_stage_name_leads_its_heading_with_a_capital(run, tmp_path):
    m = _sample()
    for i in m["interviews"]:
        if i["id"] == "int-copperleaf-payments":
            i["next_stage"] = "initial round"
    got = _go(run, tmp_path, [{"hash": "interviews", "click": "Interviews", "exact": True, "read": "#main"}],
              WIDE, model=m, clock=T)
    assert "Initial round with Copperleaf Pay" in got["after"][0]["text"]
    assert "initial round with Copperleaf Pay" not in got["after"][0]["text"]


def test_news_from_an_earlier_brief_says_todays_search_found_nothing_newer(run, tmp_path):
    m = _sample()
    m["brief"]["news_date"] = "2026-10-20"
    m["brief"]["news_searched"] = "2026-10-25"
    got = _go(run, tmp_path, [{"hash": "brief", "read": '[data-k="news-asof"]'}], WIDE, model=m, clock=T)
    assert got["after"][0]["text"].startswith("Searched this morning: nothing newer than these, from"), got["after"][0]["text"]


def test_a_job_put_in_the_bin_leaves_and_set_aside_counts_it(run, tmp_path):
    """After "Not this one" the card stayed in place, Found dropped and "set aside" did not
    rise (audit 20)."""
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": "#main"},
        {"click": "Not for me: Harbourline Bank, Pricing Analyst"},
        {"click": "Not this one", "within": "dialog", "read": "#main", "count": '#main [data-item="r12-1"]'},
    ], PHONE, clock=T)
    before, after = got["after"][0]["text"], got["after"][2]
    assert "1 set aside" in before and after["count"] == 0
    assert "2 set aside" in after["text"], after["text"][:400]


def test_one_way_to_each_thing_on_jobs_and_the_brief(run, tmp_path):
    """The audit's "too many buttons": a warm route asked about twice on one card, "Find jobs"
    and "Search again" for one search, and "I have applied" on a drafted role's Found card
    as well as on its draft."""
    m = _sample()
    r = _row(m, "r12-1")
    r["warm"] = "Bea at Harbourline Bank has replied to you: ask them first."
    r["warm_contact"] = "harbourline_bank_bea"
    r["related"] = dict(r.get("related") or {}, people=["harbourline_bank_bea"])
    r["suggest"] = {"level": 2, "id": "sg-warm-r12-1-a1", "kind": "warm",
                    "text": "Bea at Harbourline Bank replied to you: ask Bea about this role before applying.",
                    "why": "A reply is what makes a route warm.",
                    "action": {"type": "work", "label": "Write to Bea", "kind": "reply", "id": "reply~harbourline_bank_bea",
                               "title": "Write to Bea at Harbourline Bank", "args": {"contact": "harbourline_bank_bea"}},
                    "cost": {"state": 2, "label": "Some Claude"}, "since": "2026-10-25", "rev": "s9"}
    got = _go(run, tmp_path, [
        {"hash": "jobs", "more": "r12-1", "read": '[data-item="r12-1"]'},
        {"more": "app-ellerwick-insight", "read": "#main", "count": '#main [data-item="r12-4"]'},
        {"hash": "brief", "read": "#main .bp-jobs"},
    ], WIDE, model=m, clock=T)
    card = got["after"][0]
    assert "Write to Bea" in card["text"] and "for a referral" not in card["text"], card["text"]
    # A drafted job is its draft's card, in the job's place, never a second card: its
    # "I have applied" once (2026-11-05).
    drafted = got["after"][1]
    assert drafted["count"] == 0 and "See the draft" not in drafted["text"], "one card a job"
    assert "I have applied" in drafted["text"]
    assert "Search again" not in got["after"][2]["text"] and "Find jobs" in got["after"][2]["text"]


def test_the_briefs_jobs_tile_leads_with_the_drafts_ready_to_apply(run, tmp_path):
    """"Nothing new to look at." with only Find jobs, over drafts made and never sent (the
    maintainer, 2026-11-05): the tile leads with what is owed, the same count as Drafts, opens
    them, and says nothing only when there is neither a draft to send nor a find."""
    m = _sample()
    for r in m["jobs"]["rows"]:
        r["status"] = "dismissed"
    got = _go(run, tmp_path, [{"hash": "brief", "read": "#main .bp-jobs"},
                              {"hash": "drafts", "read": "#main .summary"}], WIDE, model=m, clock=T)
    tile, drafts = got["after"][0]["text"], got["after"][1]["text"]
    # Counted as Jobs counts them: the draft with a question waits on you (the screen
    # review, 2026-11-11).
    assert "2 drafts ready to apply, 1 waiting on you" in tile and "Nothing new to look at." not in tile, tile
    # One sentence whose total is the tab's since the UX review of 2026-11-10 (U-9).
    # The tab's total first (U-9); what makes it up is test_the_jobs_line_adds_up_to_its_tab's.
    assert drafts.startswith("3 to apply to: "), ("the same count as Jobs' one list", drafts[:120])
    got = _go(run, tmp_path, [{"hash": "brief", "click": "2 drafts ready to apply, 1 waiting on you", "role": "link",
                               "until": "location.hash.startsWith('#drafts')"}], WIDE, model=m, clock=T)
    assert got["after"][0]["hash"].startswith("#drafts"), got["after"][0]["hash"]
    m["ready"] = []
    got = _go(run, tmp_path, [{"hash": "brief", "read": "#main .bp-jobs"}], WIDE, model=m, clock=T)
    assert "Nothing new to look at." in got["after"][0]["text"], got["after"][0]["text"]


def test_a_draft_made_for_someone_links_their_name_and_has_no_pill_to_see_them(run, tmp_path):
    # "See Tamsin" stood as a pill row of its own between two lines that named her (the screen
    # review, 2026-11-11). Her name in "Made for Tamsin" opens her card.
    look = """(() => { const c = [...document.querySelectorAll('#main .card.app')].find((x) => /Made for Tamsin/.test(x.textContent)); if (!c) return null;
      return {pill: [...c.querySelectorAll('button, a.btn')].filter((b) => /^See /.test(b.textContent.trim())).length,
              link: (c.querySelector('.meta a') || {}).textContent || null}; })()"""
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": look}], PHONE, clock=T)
    seen = got["after"][0]["eval"]
    assert seen and seen["pill"] == 0 and seen["link"] == "Tamsin", seen
