"""No words are drawn over other words or over a button, and nothing is drawn crushed, cut
off, out of place or too small, on any screen, at a phone's, a tablet's or a laptop's width,
light or dark.

On Coming up, By day, an interview's time read from another zone ("15:00 Toronto time (20:00
here)") ran out of its column under the title, over the row's line of facts and into its pill,
on a laptop in dark (the maintainer, 2026-11-11). The layout checks found only what spilled past
the width. The harness's overlap probe (tests/app_page/harness.js, overlapProbe) now measures
every line of visible text and every drawn control on every screen and each of its views, and
names each pair that meet. It runs over the sample and over the sample at its extremes: a
person whose zone is not the device's, so every time says both; a long employer, a long role
and a long interview title; and an interview tomorrow with a live prep, so the practice day's
pills are drawn. Every person and employer is invented.

The drawing probe (drawnProbe, beside it) found what a real person's page showed and no check
saw (2026-11-11): a work card's "38 messages ready to send." a letter a line, Your rules drawn
2250px wide and cut off, the weekly chart's axis labels piled into one another, a separator
dot starting or ending a line, a Brief panel cutting its last step in half, a raw date in an
interview's title, More alone on a line under the card's other pills, controls under 24px on
a computer, and 13px words at 3.56:1 in the dark. It reads every screen and view, Settings with
its rows open, Claude's work as a sheet or beside the screen, an application's page and an
interview's live prep, on the sample and on its extremes, which now hold each of those cases.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_interview_pack import app  # noqa: E402,F401
from test_the_live_prep_on_the_page import _model as _live_model  # noqa: E402
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

# The day before the interview with the live prep: its practice is on its card's face.
CLOCK = "2026-10-27T09:00:00Z"
SIZES = {"phone": {"width": 390, "height": 844}, "tablet": {"width": 768, "height": 1024},
         "laptop": {"width": 1280, "height": 800}, "desktop": {"width": 1600, "height": 900}}

LONG_EMPLOYER = "Copperleaf Payments and Merchant Services Group"
LONG_ROLE = "Senior Data Analyst, Payments Risk and Merchant Onboarding Analytics"
LONG_STAGE = "Final round: technical case study with the hiring panel"

# Overlaps meant to be there, each with why. A string lets an element pass whole; a pair lets
# only those two meet; `drawn` measures a control as the part of it that is drawn.
ALLOW = [
    # The "?" is a 22px circle drawn inside a 44px target on a phone (DESIGN.md, "Buttons,
    # links and taps": a full-size tap area): the target reaches past its line, the circle
    # does not. Measured as the circle.
    {"sel": ".q, .sum .help-q", "drawn": 23},
    # A draft's heading row is its fold's whole-width toggle, and Copy and the pencil sit at
    # its right end by design (DESIGN.md, "Contacts": "the draft with Copy and the pencil at
    # the right end of its heading line"): the row is drawn under them, its words beside them.
    ["summary.pdraft-sum", ".bubble-copy, .bubble-pen"],
]


# Kinds of drawing let pass where they are meant, each with why: {kind: [selector, ...]}.
DRAWN_ALLOW: dict = {}

# Thirty-eight people with a follow-up drafted and waiting: a run of finished work as long as a
# real week's ("38 follow-ups done", "38 messages ready to send."). Invented first names at the
# sample's own invented employers.
FIRSTS = ["Ada", "Bram", "Cleo", "Dov", "Edie", "Finn", "Gus", "Hana", "Ivo", "Jun", "Kai", "Lior", "Mae",
          "Nils", "Ona", "Pip", "Quin", "Rory", "Sami", "Tove", "Uma", "Vik", "Wyn", "Xan", "Yara", "Zed",
          "Arlo", "Bea", "Cal", "Dot", "Eli", "Fay", "Gil", "Hal", "Ida", "Jem", "Kit", "Lux"]
EMPLOYERS = ["Harbourline Bank", "Larkspur Retail", "Ellerwick Trust", "Kestrel Mutual", "Fernhill Freight",
             "Quayside Foods", "Brackenridge Advisory"]
LONG_RULE = ("When someone offers to chat early in a thread, never answer with a list of times: say yes in "
             "one plain sentence, ask what suits them, and keep the note under three lines, because a long "
             "reply to a short offer reads as keen in the wrong way and nobody answered the long ones")
FAILED = "work/draft~ellerwick"


def _at(seconds):
    t = dt.datetime.fromisoformat(CLOCK.replace("Z", "+00:00")) + dt.timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def extremes():
    """The sample with a live prep, at its extremes, as an engine would write them: the person in
    Toronto on a device in London, so every time says both zones; one employer's name, one role
    and one interview's title at full length, wherever the sample names them; thirty-eight
    follow-ups drafted, rules long enough to need cutting, a week of 400 messages in the chart,
    an interview paused on a day written as a date, and a find whose line of facts is long."""
    m = _live_model()
    m["person"] = dict(m["person"], time_zone="America/Toronto")
    text = json.dumps(m).replace("Copperleaf Pay", LONG_EMPLOYER).replace("Data Analyst, Payments", LONG_ROLE)
    m = json.loads(text)
    for iv in m["interviews"]:
        if iv["id"] == "int-copperleaf-payments":
            iv["next_stage"] = LONG_STAGE
        # Paused, as a stage written with its day: the title says the day in words.
        if iv["id"] == "int-harbourline-risk":
            iv["next_stage"] = iv["stage_title"] = "Paused 2026-10-20"
    for u in m["upcoming"]:
        if u["id"].startswith("up-app-copperleaf-payments"):
            u["title"] = LONG_STAGE + ": " + LONG_EMPLOYER
    for i, first in enumerate(FIRSTS):
        cid = "extreme_%s" % first.lower()
        employer = EMPLOYERS[i % len(EMPLOYERS)]
        m["people"].append({"id": cid, "group": "follow", "late": 0, "first_name": first, "employer": employer,
                            "title": "Senior Recruiter, Talent Acquisition for Data and Analytics (supporting hiring across the region)",
                            "status": "awaiting_reply", "last": "2026-10-12", "next_action": "One nudge if no reply",
                            "due": "2026-10-27", "rev": "p-" + cid, "related": {"messages": ["msg-" + cid]}})
        m["messages"].append({"id": "msg-" + cid, "contact": cid, "first_name": first, "employer": employer,
                              "channel": "linkedin_message", "kind": "follow_up",
                              "text": "Hi %s, a quick follow-up on my note. I would love to hear how the team works." % first,
                              "chars": 80, "limit": 8000, "why": "Your note went unanswered for 2 weeks", "due": "2026-10-27",
                              "rev": "m-" + cid, "alerts": [], "suggest": None, "hold": None, "related": {"people": [cid]}})
    m["to_send"] = {"n": len(m["messages"]), "ids": [x["id"] for x in m["messages"]]}
    # Long rules, and more of one kind than its group shows before "Show all".
    m["learned"] = m["learned"] + [{"id": "learned-long-%d" % i, "area": area, "rule": LONG_RULE, "say": LONG_RULE,
                                    "said": "one thing i dont like is the long replies to short offers", "on": "2026-10-%02d" % (10 + i),
                                    "retired": False, "rev": "ll%d" % i}
                                   for i, area in enumerate(["messages"] * 6 + ["documents", "jobs"])]
    # File names, each choice's example as long as a long employer and role make one.
    m["settings"].append({"id": "setting-file_names", "key": "file_names", "label": "File names", "kind": "choice",
                          "value": "name_employer_document", "rev": "s-file_names", "recommended": "name_employer_document",
                          "choices": [["name_employer_document", "Name, employer, document"], ["name_document", "Name, document"],
                                      ["name_employer_role_document", "Name, employer, role, document"]],
                          "examples": {"name_employer_document": "Morgan_Ellis_Copperleaf_Payments_Merchant_Resume.pdf",
                                       "name_document": "Morgan_Ellis_Resume.pdf",
                                       "name_employer_role_document": "Morgan_Ellis_Copperleaf_Senior_Data_Analyst_Payments_Resume.pdf"}})
    weeks = m["done"]["weeks"]
    for i, w in enumerate(weeks):
        w["sent"] = [12, 30, 55, 80, 120, 160, 240, 400][i % 8]
    # The Brief's next steps as long as a busy week writes them.
    for sec in m["brief"]["sections"]:
        if sec["kind"] == "next":
            for it in sec["items"]:
                it["text"] = it["text"].rstrip(".") + ", then tell Claude what you decided so the rest of the week's plan can be made again around it."
    for r in m["jobs"]["rows"]:
        if r["id"] == "r12-4":
            r.update(company="Ellerwick Trust and Merchant Services Group", place="Newcastle upon Tyne and Gateshead",
                     pay={"text": "GBP 38,000 to 42,000 plus a yearly bonus", "stated": True})
    return m


def seeds():
    """Claude's work as the extremes have it: the thirty-eight follow-ups done a moment ago, and a
    draft that failed; and a chat with a message of the person's."""
    out = {}
    for i, first in enumerate(FIRSTS):
        cid = "extreme_%s" % first.lower()
        out["work/follow_up~" + cid] = {"kind": "follow_up", "title": "Follow up with " + first, "to": "cloud", "args": {"contact": cid},
                                        "asked_at": _at(-600 + i), "status": "done", "claimed_by": "cloud-1", "claimed_at": _at(-500),
                                        "finished_at": _at(-20), "result": {"summary": "Drafted a follow-up to " + first + "."},
                                        "stop_asked": False, "attempt": 1}
    out[FAILED] = {"kind": "draft", "title": "Resume and letter: Ellerwick Trust, Senior Data Scientist II", "to": "cloud",
                   "args": {"job": "r12-4"}, "asked_at": _at(-900), "status": "failed", "claimed_by": "cloud-1", "claimed_at": _at(-880),
                   "finished_at": _at(-480), "error": "It stopped part way. Anything already saved is kept.", "stop_asked": False, "attempt": 1}
    out["talk/cloud-1"] = {"to": "cloud", "conv": "1", "title": "Is Harbourline Bank hiring?", "created_at": _at(-3600)}
    out["talk/cloud-1/messages/m1"] = {"from": "you", "text": "Is Harbourline Bank hiring analysts?", "at": _at(-3590)}
    out["talk/cloud-1/messages/m2"] = {"from": "cloud", "text": "Yes: two analyst roles opened there this week.", "at": _at(-3580)}
    return out


# What opens over a screen or inside it, each read as it stands open: Settings with its rows
# open (Your rules among them), Claude's work as a sheet where it is not beside the screen, an
# application's own page, and the live prep.
OPENED = [
    {"key": "settings/open", "hash": "settings", "eval": "document.querySelectorAll('#main details:not([open])').forEach((d) => { d.open = true; })"},
    {"key": "work", "hash": "todo", "unless": "#rail .work-card", "click": "#pill", "wait": "dialog.work-sheet[open] .work-card", "optional": True},
    {"key": "application", "hash": "jobs/app-fernhill-ops/open", "wait": "dialog.detail[open]"},
    {"key": "interview", "hash": "interviews/int-copperleaf-payments/open", "wait": "dialog.detail[open]"},
]


_PAGES: dict = {}


@pytest.fixture
def pages(app, tmp_path_factory):  # noqa: F811
    if not _PAGES:
        tmp = tmp_path_factory.mktemp("overlaps")
        _PAGES.update(sample=_write(tmp, "sample", _sample()), extremes=_write(tmp, "extremes", extremes()))
    return _PAGES


@pytest.fixture(scope="module")
def run():
    yield from browser()


_RUNS: dict = {}


def _layout(run, pages, model, size, scheme):
    """Every screen, view and opened state of one page at one size in one look, read once for
    both tests."""
    key = (model, size, scheme)
    if key not in _RUNS:
        got = run("layout", html=pages[model], viewport=SIZES[size], scheme=scheme, fake={"canSend": "available"}, clock=CLOCK,
                  overlaps=True, allow=ALLOW, drawn=True, drawnAllow=DRAWN_ALLOW, opened=OPENED,
                  seed=seeds() if model == "extremes" else {})
        assert not got["errors"], got["errors"]
        assert set(got["overlaps"]) >= {"brief", "todo", "jobs", "contacts", "interviews", "progress", "chat", "settings", "profile",
                                        "settings/open", "application", "interview"} | ({"work"} if model == "extremes" else set()), got["overlaps"].keys()
        _RUNS[key] = got
    return _RUNS[key]


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("size", ["phone", "tablet", "laptop", "desktop"])
@pytest.mark.parametrize("model", ["sample", "extremes"])
def test_no_words_are_drawn_over_other_words_or_buttons_on_any_screen(run, pages, model, size, scheme):
    found = {screen: f for screen, f in _layout(run, pages, model, size, scheme)["overlaps"].items() if f}
    assert not found, "\n".join(screen + ": " + o["a"] + " and " + o["b"] + " meet, %(w)sx%(h)spx at %(at)s" % o
                                 for screen, overlaps in found.items() for o in overlaps)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("size", ["phone", "tablet", "laptop", "desktop"])
@pytest.mark.parametrize("model", ["sample", "extremes"])
def test_nothing_is_drawn_crushed_cut_off_out_of_place_or_too_small_on_any_screen(run, pages, model, size, scheme):
    found = {screen: f for screen, f in _layout(run, pages, model, size, scheme)["drawn"].items() if f}
    assert not found, "\n".join("%s: %s %s \"%s\": %s" % (screen, d["kind"], d["el"], d["words"], d["detail"])
                                 for screen, ds in found.items() for d in ds)


def test_the_check_sees_words_drawn_over_words(run, pages):
    """The probe itself: a line of words laid over a row's title is named."""
    got = run("overlap_selftest", html=pages["sample"], viewport=SIZES["desktop"], clock=CLOCK, allow=ALLOW)
    assert not got["errors"], got["errors"]
    assert any("Drawn over the title" in o["a"] + o["b"] for o in got["found"]), got["found"]


# One fault of each kind, laid on a screen as stood, each in a box of its own (`spoil-<kind>`).
SPOIL = """(() => {
  const m = document.querySelector("#main .sec") || document.getElementById("main");
  const add = (html) => { const d = document.createElement("div"); d.innerHTML = html; m.appendChild(d.firstElementChild); };
  add('<p class="spoil-crushed" style="width: 12px">38 messages ready to send.</p>');
  add('<p class="spoil-broken" style="width: 90px; overflow-wrap: anywhere">Copperleafpaymentsresume.pdf</p>');
  add('<div class="spoil-clipped" style="width: 120px; overflow: hidden; white-space: nowrap">When someone offers to chat early in a thread</div>');
  add('<p class="spoil-starts">Interview<br>\u00b7 Supply Chain Analyst</p>');
  add('<p class="spoil-ends">Interview \u00b7<br>Supply Chain Analyst</p>');
  add('<button type="button" class="spoil-small" style="width: 16px; height: 16px; padding: 0; border: 1px solid">?</button>');
  add('<div class="card-actions spoil-alone" style="width: 220px"><button type="button" class="btn secondary small">Practise 3 questions</button><button type="button" class="btn secondary small">Read your prep</button><details class="more"><summary class="more-btn">More</summary></details></div>');
  add('<p class="spoil-faint" style="color: #c8c8c8; background: #ffffff">Words too faint to read</p>');
  add('<svg class="spoil-piled" width="60" height="40" viewBox="0 0 60 40"><text x="10" y="20">300</text><text x="12" y="22">400</text></svg>');
  add('<p class="spoil-date">Paused 2026-10-20 with Harbourline Bank</p>');
})()"""
KINDS = {"crushed": ["spoil-crushed", "spoil-broken"], "clipped": ["spoil-clipped"], "separator": ["spoil-starts", "spoil-ends"],
         "small": ["spoil-small"], "alone": ["spoil-alone"], "faint": ["spoil-faint"], "piled": ["spoil-piled"], "date": ["spoil-date"]}


def test_the_check_sees_each_kind_of_fault(run, pages):
    """The drawing probe itself: each kind of fault laid on a screen is named, where it is."""
    got = run("drawn_selftest", html=pages["sample"], viewport=SIZES["laptop"], clock=CLOCK, spoil=SPOIL)
    assert not got["errors"], got["errors"]
    for kind, boxes in KINDS.items():
        for box in boxes:
            assert any(d["kind"] == kind and box in d["el"] for d in got["found"]), (kind, box, got["found"])
    # And nothing on the screen as it stood.
    assert all("spoil-" in d["el"] for d in got["found"]), got["found"]


# Where the Chat's first words are against the header's foot, once it has settled.
CHAT_HEAD = """(async () => {
  await new Promise((r) => setTimeout(r, 400));
  const foot = document.getElementById("top").getBoundingClientRect().bottom;
  const walk = document.createTreeWalker(document.getElementById("main"), NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const el = n.parentElement;
    if (!n.textContent.trim() || !el.checkVisibility({visibilityProperty: true}) || el.closest(".sr-only")) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const q = [...r.getClientRects()].find((x) => x.width > 1 && x.height > 1);
    if (q) return {foot: Math.round(foot), first: Math.round(q.top), words: n.textContent.trim().slice(0, 40), scrolled: Math.round(window.scrollY)};
  }
  return null;
})()"""


@pytest.mark.parametrize("model", ["sample", "extremes"])
def test_the_chat_opens_with_its_first_words_under_the_header_never_behind_it(run, pages, model):
    """A Chat taller than the window under the header opened at its end with its first words
    slid under the header and its Refresh pill (Firefox in CI, 2026-11-11): its height took the
    header as 56px, and with the line under it (Updated, Refresh) it is 117px on a phone."""
    got = run("engine", html=pages[model], viewport=SIZES["phone"], fake={"canSend": "available"}, clock=CLOCK,
              seed=seeds() if model == "extremes" else {}, steps=[{"hash": "chat", "eval": CHAT_HEAD}])
    assert not got["errors"], got["errors"]
    head = got["after"][0]["eval"]
    assert head and head["first"] >= head["foot"] - 1, head


def test_the_extremes_are_drawn(run, pages):
    """The extremes reach the page: both zones in a time, the long names, the practice day."""
    got = run("engine", html=pages["extremes"], viewport=SIZES["desktop"], fake={"canSend": "available"}, clock=CLOCK,
              hashes=["interviews", "jobs"])
    assert not got["errors"], got["errors"]
    up = got["texts"]["interviews"]
    assert "Toronto time (" in up and " here)" in up, up
    assert LONG_STAGE + ": " + LONG_EMPLOYER in up and "Practise 3 questions" in up, up
    assert LONG_ROLE in got["texts"]["jobs"], got["texts"]["jobs"]
