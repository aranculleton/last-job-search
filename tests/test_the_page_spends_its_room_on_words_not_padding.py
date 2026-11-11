"""The page is dense where it can be: words get the room, never padding, indents or a control
floated into them (templates/app/DESIGN.md).

The maintainer, 2026-11-10: "it needs to be polished and the design needs to be smart and not
super padded eyesore where necessary. inline and things are good." Each check here is one
place that was padded for nothing, measured as drawn, on a phone and on a wide screen.
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _eval(run, tmp_path, hash_, probe, vp, **kw):
    got = _go(run, tmp_path, [{"hash": hash_, "eval": probe}], vp, clock=T, **kw)
    return got["after"][0]["eval"]


# ------------------------------------------------------------------ Contacts: a draft's words

# Every draft open on a person's card: where its words start against the card's own edge, and
# whether its Copy or pencil sits inside the words' box.
DRAFTS = r"""(() => {
  const out = [];
  for (const d of document.querySelectorAll('#main li.person .pdraft[open]')) {
    const card = d.closest('li.person');
    const text = d.querySelector('.sendtext');
    if (!text || !text.getClientRects().length) continue;
    // Against the initial's own left edge, the card's content edge, as drawn.
    const t = text.getBoundingClientRect(), a = card.querySelector('.avatar').getBoundingClientRect();
    const over = [...d.querySelectorAll('.sendbox .bubble-copy, .sendbox .bubble-pen')].filter((b) => {
      const r = b.getBoundingClientRect();
      return r.width && r.bottom > t.top + 1 && r.top < t.bottom - 1 && r.right > t.left && r.left < t.right;
    }).length;
    // An email's subject keeps its Copy beside its words, never at the card's far edge.
    const subj = d.querySelector(':scope > .subject'), sc = subj && subj.querySelector('.btn');
    const words = subj ? (() => { const g = document.createRange(); g.selectNodeContents(subj.children[1]); return g.getBoundingClientRect(); })() : null;
    const far = subj && sc ? Math.round(sc.getBoundingClientRect().left - words.right) : null;
    // What a failure needs to say where to look: how far the buttons reach into the words, and
    // the heights of the heading and the buttons' row (Firefox drew them apart, 2026-11-11).
    const reach = Math.max(0, ...[...d.querySelectorAll('.sendbox .bubble-copy, .sendbox .bubble-pen')].map((b) => Math.round(b.getBoundingClientRect().bottom - t.top)));
    const sum = d.querySelector(':scope > summary'), tools = d.querySelector('.sendbox > .bubble-tools');
    out.push({who: card.dataset.item, indent: Math.round(t.left - a.left), over, far, reach,
              heading: sum ? Math.round(sum.getBoundingClientRect().height) : null, tools: tools ? Math.round(tools.getBoundingClientRect().height) : null});
  }
  return out;
})()"""


def test_a_drafts_words_take_the_whole_bubble_and_on_a_phone_the_whole_card(run, tmp_path, vp):
    got = _eval(run, tmp_path, "contacts", DRAFTS, vp)
    assert len(got) >= 3, got
    # Copy and the pencil sit on the draft's heading line, never in the words: floated into
    # the bubble they bent its first lines round them, three words a line on a phone.
    assert [d for d in got if d["over"]] == [], got
    # On a wide screen an email's subject keeps its Copy beside its words (on a phone a
    # wrapped subject fills the line).
    if vp is WIDE:
        assert any(d["far"] is not None for d in got) and all(d["far"] is None or d["far"] <= 16 for d in got), got
    # On a phone only the name sits beside the initial; the draft starts at the card's edge.
    if vp is PHONE:
        assert {d["indent"] for d in got} == {0}, got


# ------------------------------------------------------------------ Coming up: a row's lines

ROWS = r"""(() => [...document.querySelectorAll('#main [data-k="up-days"] .up-row')].map((r) => {
  const box = (sel) => { const e = r.querySelector(sel); return e && e.getClientRects().length ? e.getBoundingClientRect() : null; };
  const note = box('.up-note'), prep = box('.up-prep'), main = box('.up-main'), cal = box('.up-acts [data-k^="cal:"]');
  const link = r.querySelector('.up-link');
  // A title's box against its words' own: a 44px line of air around one line of words.
  const words = link ? (() => { const g = document.createRange(); g.selectNodeContents(link); return g.getBoundingClientRect().height; })() : 0;
  const fits = note && prep && main ? note.width + prep.width + 8 <= main.width : false;
  // Where the prep wraps to a line of its own, that line never starts with the dot.
  const lead = r.querySelector('.up-prep') ? getComputedStyle(r.querySelector('.up-prep'), '::before').content : 'none';
  return {id: r.dataset.item, lead, oneLine: fits ? Math.abs((note.top + note.bottom) / 2 - (prep.top + prep.bottom) / 2) < 4 : null,
          air: link ? Math.round(link.getBoundingClientRect().height - words) : null, cal: cal ? Math.round(cal.left) : null};
}))()"""


def test_a_coming_up_row_says_what_it_is_on_one_line_and_its_icons_line_up(run, tmp_path, vp):
    rows = _eval(run, tmp_path, "interviews", ROWS, vp)
    assert len(rows) >= 5, rows
    # What it is and whether its prep is ready share the line under the title where they fit.
    # On a phone the prep's pill (Read your prep, Prepare me: the UX review's U-12) is too wide
    # to sit beside what the row is, so there it takes the line under it.
    assert [r for r in rows if r["oneLine"] is False] == [], rows
    if vp is WIDE:
        assert any(r["oneLine"] for r in rows), rows
    assert all(r["lead"] in ("none", "normal") for r in rows), rows
    # The calendar is in the same place on every row, a trash beside it or not.
    assert len({r["cal"] for r in rows if r["cal"] is not None}) == 1, rows
    # A title is drawn its own height, never a 44px line of air round its words on a phone. A
    # line is taller than its letters by the font's own measure: 5px in Windows' type (Liberation
    # Sans, Everywhere 4.15.0), where the air this is about was 20px and more.
    assert all(r["air"] is None or r["air"] <= 8 for r in rows), rows


# ------------------------------------------------------------------ Claude's work: one line less a card

_W = {"to": "cloud", "args": {}, "_v": 2}
WORK = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
        "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:56:00.000Z", "since": "2026-10-24T08:00:00.000Z"},
        "work/search~1": dict(_W, kind="search", title="Finding jobs", status="running", asked_at="2026-10-25T08:55:00.000Z",
                              claimed_at="2026-10-25T08:55:10.000Z", stage_at="2026-10-25T08:57:00.000Z",
                              steps=[{"at": "2026-10-25T08:55:10.000Z", "text": "Searching 4 job sites"}], count={"done": 3, "total": 4})}

STOPS = r"""(() => {
  const mid = (e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; };
  const cards = [...document.querySelectorAll('.work-card')].filter((c) => c.getClientRects().length && c.querySelector('.wc-time') && c.querySelector('.wc-time').textContent.trim());
  const close = document.querySelector('dialog[open] [data-k="work-close"]'), title = document.querySelector('dialog[open] .rail-title');
  return {cards: cards.map((c) => Math.round(Math.abs(mid(c.querySelector('.wc-time')) - mid(c.querySelector('.btn.stop-claude'))))),
          close: close && title ? Math.round(Math.abs(mid(close) - mid(title))) : null};
})()"""


def test_stop_claude_is_on_its_clocks_line_and_the_sheets_close_on_its_titles(run, tmp_path, vp):
    step = dict({"hash": "todo", "eval": STOPS}, **({"open": "pill"} if vp is PHONE else {}))
    got = _go(run, tmp_path, [step], vp, clock=T, seed=WORK)["after"][0]["eval"]
    assert got["cards"] and all(d <= 8 for d in got["cards"]), got
    if vp is PHONE:
        assert got["close"] is not None and got["close"] <= 8, got


# ------------------------------------------------------------------ To do: a checklist row

GROWS = r"""(() => [...document.querySelectorAll('#main .g-row')].filter((r) => r.getClientRects().length && r.querySelector('.g-name + p.small')).map((r) => {
  const mid = (e) => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; };
  const name = r.querySelector('.g-name'), sub = r.querySelector('.g-name + p.small'), btn = r.querySelector('.g-acts .btn:not(.icon-only)');
  return {row: r.dataset.item, oneLine: Math.abs(mid(name) - mid(sub)) < 4, reach: btn ? Math.round(btn.getBoundingClientRect().left - name.getBoundingClientRect().left) : null};
}))()"""


def test_a_checklist_rows_name_and_state_share_a_line_near_its_button_on_a_wide_screen(run, tmp_path):
    rows = _eval(run, tmp_path, "todo", GROWS, WIDE)
    assert len(rows) >= 5, rows
    assert all(r["oneLine"] for r in rows), rows
    # The button is within a reading width of the name it acts on, not across the screen.
    assert all(r["reach"] is not None and r["reach"] < 520 for r in rows), rows


# ------------------------------------------------------------------ To do: later is not the trash

LATER = r"""(() => [...document.querySelectorAll('#main [data-todo] .hide-x')].filter((b) => b.getClientRects().length).map((b) => ({
  card: b.closest('[data-todo]').dataset.todo, label: b.getAttribute('aria-label') || '',
  word: [...b.querySelectorAll('span:not(.sr-only)')].filter((s) => s.getBoundingClientRect().width > 4).map((s) => s.textContent.trim()).join(' '),
  bin: !!b.querySelector('svg path[d^="M4 7h16"]')})))()"""


def test_putting_off_on_to_do_says_later_and_the_trash_is_only_for_what_goes(run, tmp_path, vp):
    got = _eval(run, tmp_path, "todo", LATER, vp)
    later = [g for g in got if g["label"].startswith(("Later", "Hide for a week"))]
    person = [g for g in got if g["label"].startswith("Not ")]
    assert later and person, got
    # A card put off for a while says so in words, with a clock, never the trash.
    assert all(g["word"] == "Later" and not g["bin"] for g in later), later
    # A card about one person keeps the trash: its choices include letting them go.
    assert all(g["bin"] and not g["word"] for g in person), person


# ------------------------------------------------------------------ Jobs: a card's lines

JOBS = r"""(() => {
  const mid = (e) => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; };
  const pens = [...document.querySelectorAll('#main .card.job .facts')].map((f) => {
    const why = f.querySelector('.info-toggle'), pen = f.querySelector('[data-k^="jobpen:"]');
    return why && pen ? Math.round(Math.abs(mid(why) - mid(pen))) : null;
  }).filter((x) => x !== null);
  const gap = (sel) => [...document.querySelectorAll(sel)].map((e) => getComputedStyle(e).rowGap)[0];
  const folds = [...document.querySelectorAll('#main .sec > p.fold')].filter((p) => p.getClientRects().length);
  const apart = folds.slice(1).map((p, i) => Math.round(p.getBoundingClientRect().top - folds[i].getBoundingClientRect().bottom));
  // "Why" never starts a line alone: the fact before it goes with it, its last words where it
  // takes two lines.
  const whys = [...document.querySelectorAll('#main .facts')].map((f) => {
    const why = f.querySelector('.info-toggle'), last = [...f.querySelectorAll('.fact')].pop();
    const end = last ? [...last.getClientRects()].pop() : null;
    return why && end ? Math.round(Math.abs(mid(why) - (end.top + end.bottom) / 2)) : null;
  }).filter((x) => x !== null);
  return {pens, whys, draftGap: gap('#main .card.app .app-main'), cardGap: gap('#main .card.app'), apart};
})()"""


@pytest.mark.parametrize("width", [390, 1440])
def test_a_jobs_lines_keep_together_and_a_draft_is_as_tight_as_a_find(run, tmp_path, width):
    # 390 wide, where "Why" ended one line and its pencil started the next (2026-11-10).
    got = _eval(run, tmp_path, "jobs", JOBS, {"width": width, "height": 844 if width < 760 else 900})
    # The pencil at the end of a job's facts stays beside "Why", never alone on a line.
    assert got["pens"] and all(d <= 4 for d in got["pens"]), got
    assert got["whys"] and all(d <= 4 for d in got["whys"]), got
    # A draft's lines are a card's step apart, not half again more.
    assert got["draftGap"] == got["cardGap"] == "8px", got
    # The folds after the list ("1 closed: Show", "1 set aside: Show") read as one block on
    # a computer; on a phone each Show keeps the room its 44px reach needs.
    assert len(got["apart"]) >= 1 and all(a <= (8 if width > 760 else 12) for a in got["apart"]), got


# ------------------------------------------------------------------ a control on its own is a pill

PILLS = r"""(() => [...document.querySelectorAll('[data-k="bp-tip"], [data-k="tip-seen"], [data-k="cal-all"], [data-k^="up-time:"], [data-k="work-hide"], [data-k="work-close"], [data-k^="you-edit:"], [data-k="you-edu"], [data-k="you-certs"]')]
  .filter((b) => b.getClientRects().length).map((b) => { const s = getComputedStyle(b);
    return {k: b.dataset.k.split(':')[0], pill: s.textDecorationLine === 'none' && parseFloat(s.borderTopLeftRadius) >= 12 && !/rgba\(0, 0, 0, 0\)|transparent/.test(s.backgroundColor)}; }))()"""


def test_a_control_standing_on_its_own_is_a_pill_never_underlined_words(run, tmp_path):
    # Got it, Add all to your calendar, Add the time, the work panel's Hide, the sheet's Close
    # and Your profile's Change: underlined words as controls, against the page's own rule
    # (the review, 2026-11-10).
    seen = []
    for vp, hashes, opener in ((WIDE, ["brief", "interviews", "todo", "profile"], None), (PHONE, ["todo"], "pill")):
        steps = [dict({"hash": h_, "eval": PILLS}, **({"open": opener} if opener else {})) for h_ in hashes]
        got = _go(run, tmp_path, steps, vp, clock=T, seed=WORK)
        seen += [x for a in got["after"] for x in a["eval"]]
    assert {x["k"] for x in seen} >= {"bp-tip", "cal-all", "up-time", "work-hide", "work-close", "you-edit", "you-edu", "you-certs"}, seen
    assert [x for x in seen if not x["pill"]] == [], seen


# ------------------------------------------------------------------ Progress: the weeks

WEEKS = r"""(() => { const c = document.querySelector('#main details.chart'); if (!c) return null;
  const svg = c.querySelector('svg.weeks-svg');
  return {open: c.open, chart: svg && svg.getClientRects().length ? Math.round(svg.getBoundingClientRect().height) : 0,
          chevrons: [...c.querySelectorAll('summary')].map((s) => getComputedStyle(s, '::after').content !== 'none' && getComputedStyle(s, '::after').borderRightStyle === 'solid')}; })()"""


def test_the_weeks_card_on_progress_shows_its_chart_and_says_it_folds(run, tmp_path, vp):
    got = _eval(run, tmp_path, "progress", WEEKS, vp)
    # Folded, "Each week" was a heading over an empty box, nothing saying it opens.
    assert got and got["open"] and got["chart"] > 60, got
    assert got["chevrons"] and all(got["chevrons"]), got


# ------------------------------------------------------------------ the header's dot

DOT = r"""(() => { const d = document.querySelector('#conn .dot'), s = getComputedStyle(d);
  return {state: document.getElementById('conn').getAttribute('data-state'), filled: !/rgba\(0, 0, 0, 0\)|transparent/.test(s.backgroundColor), ring: s.boxShadow !== 'none'}; })()"""
UNHEARD = {"work/search~late": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:30:00Z",
                                "status": "queued", "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None,
                                "claimed_at": None, "stop_asked": False, "attempt": 1},
           "meta/listener": {"chat": "cloud-1", "title": "Job search helper", "kind": "cloud", "answered_at": "2026-10-25T07:30:00Z", "watching": True}}


def test_the_header_dot_says_claude_is_not_listening_by_its_shape_not_its_colour_alone(run, tmp_path):
    live = _go(run, tmp_path, [{"hash": "todo", "eval": DOT}], PHONE, clock=T, seed=WORK)["after"][0]["eval"]
    away = _go(run, tmp_path, [{"hash": "todo", "eval": DOT}], PHONE, clock=T, seed=UNHEARD)["after"][0]["eval"]
    assert live["state"] == "live" and live["filled"] and not live["ring"], live
    # WCAG 1.4.1: the amber of "not listening" was the only difference from the green of live.
    assert away["state"] == "unheard" and not away["filled"] and away["ring"], away


# ------------------------------------------------------------------ the gauge names Claude

GAUGES = r"""(() => [...document.querySelectorAll('#main .cost.has-tip, #top .cost.has-tip')].filter((c) => c.getClientRects().length)
  .map((c) => [...c.querySelectorAll('span[aria-hidden="true"]')].map((s) => s.textContent).join('')))()"""


def test_a_gauges_minutes_say_whose_time_they_are(run, tmp_path):
    seen = []
    for h_ in ("todo", "jobs"):
        seen += _eval(run, tmp_path, h_, GAUGES, WIDE)
    timed = [g for g in seen if "min" in g]
    # "38 min" beside Find jobs read as a wait, not as Claude's time it will take.
    assert timed and all(g.endswith(" min of Claude") for g in timed), seen


# ------------------------------------------------------------------ the Brief's rows wrap as words

BRIEF_ROWS = r"""(() => [...document.querySelectorAll('#main :is(.bp-today, .bp-next) a.bp-text.bp-link')].filter((a) => a.getClientRects().length).map((a) => ({
  text: a.textContent.trim().slice(0, 40), align: getComputedStyle(a).textAlign,
  flows: [...a.childNodes].filter((n) => n.nodeType === 1 || n.textContent.trim()).length})))()"""


def test_a_brief_row_wraps_as_one_line_of_words_from_its_start(run, tmp_path):
    # Today's and Next three's rows are words. On a phone a row's link is a flex row: bare words
    # beside the day's span were two columns, the day squeezing the words at a larger text size,
    # and a wrapped line centred (U-20).
    rows = _eval(run, tmp_path, "brief", BRIEF_ROWS, PHONE)
    assert len(rows) >= 3, rows
    assert all(r["flows"] == 1 for r in rows), rows
    assert all(r["align"] in ("start", "left") for r in rows), rows


# ------------------------------------------------------------------ a phone's own size

SIZE = r"""(() => { const p = document.querySelector('#main .card p, #main p'); const z = parseFloat(document.body.style.zoom) || 1;
  return {zoom: z, body: Math.round(parseFloat(getComputedStyle(document.body).fontSize) * z * 10) / 10,
          small: Math.round(parseFloat(getComputedStyle(document.querySelector('#main .small, #main .muted')).fontSize) * z * 10) / 10}; })()"""


def test_a_phone_draws_the_page_at_its_own_size_by_default(run, tmp_path):
    # Drawn at 85%, a phone's body was 12.8px and its small words 11.2px (the review,
    # 2026-11-10, U-2); density comes from padding, never from shrinking type. A phone's own
    # text is a touch under a computer's 16px (the maintainer, 2026-10-29), never under 15.
    got = _eval(run, tmp_path, "todo", SIZE, PHONE)
    assert got["zoom"] == 1 and got["body"] >= 15 and got["small"] >= 13, got


PROFILE = r"""(() => { const card = document.querySelector('#main .prof-missing'), row = card && card.querySelector('li');
  if (!row) return null; const t = card.querySelector('.prof-h').getBoundingClientRect(), r = row.firstElementChild.getBoundingClientRect();
  return {inset: Math.round(r.left - t.left)}; })()"""


def test_what_is_still_to_fill_in_reads_at_the_cards_own_edge(run, tmp_path, vp):
    # A Settings row's 16px inset put each line a step in from the card's title (2026-11-10).
    got = _eval(run, tmp_path, "profile", PROFILE, vp)
    assert got is not None and abs(got["inset"]) <= 1, got


HEAD = r"""(() => { const s = document.querySelector('#main .summary.with-tool'); if (!s) return null;
  const mid = (e) => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; };
  const words = s.querySelector('.sum, .sum-small'), tool = s.querySelector(':scope > :last-child .btn, :scope > :last-child a, :scope > :last-child button');
  return words && tool ? Math.round(Math.abs(mid(words) - mid(tool))) : null; })()"""


@pytest.mark.parametrize("screen", ["todo", "contacts", "interviews"])
def test_a_headers_pills_sit_on_its_summary_line_on_a_wide_screen(run, tmp_path, screen):
    # Pinned to the top of the line, a 38px pill sat a third of a line below the words it is
    # beside (2026-11-10).
    off = _eval(run, tmp_path, screen, HEAD, WIDE)
    assert off is not None and off <= 3, off


GREET = r"""(() => { const t = document.querySelector('#main .brief-hello .screen-title').getBoundingClientRect(), b = document.querySelector('#main .brief-head [data-k="brief-bell"]').getBoundingClientRect();
  return {beside: b.top < t.bottom && b.left > t.left, titleLines: Math.round(t.height / parseFloat(getComputedStyle(document.querySelector('#main .brief-hello .screen-title')).lineHeight))}; })()"""


def test_the_briefs_bell_and_pencil_sit_beside_the_greeting_on_a_phone(run, tmp_path):
    # Their phone rule sat above the sheet's own and lost to it: at a phone's own size they
    # took a row of their own under the greeting (2026-11-10).
    got = _eval(run, tmp_path, "brief", GREET, PHONE)
    # Beside, and the greeting at most two lines: in the widest common font (DejaVu Sans, on
    # GitHub's runner) "Good afternoon, Morgan" takes its second line beside them, as a long
    # name would in any font (2026-11-11).
    assert got["beside"] and got["titleLines"] <= 2, got


SETROWS = r"""(() => [...document.querySelectorAll('#main .set-rows .set-sum')].filter((r) => r.getClientRects().length && r.textContent.trim().length < 30)
  .map((r) => Math.round(r.getBoundingClientRect().height)))()"""


def test_a_one_line_setting_is_a_44px_row_on_a_phone(run, tmp_path):
    # 52px a row with 16px insets, at a phone's own size the list of settings ran a third
    # longer than its words needed (2026-11-10). 44px is the tap a finger needs.
    rows = _eval(run, tmp_path, "settings", SETROWS, PHONE)
    assert rows and min(rows) >= 43 and sorted(rows)[len(rows) // 2] <= 46, rows


CHIPS = r"""(() => [...document.querySelectorAll('#main .card.todo')].filter((c) => c.getClientRects().length && c.querySelector('.todo-top .chip') && c.querySelector('.todo-top .kind')).map((c) => {
  const k = c.querySelector('.todo-top .kind').getBoundingClientRect(), p = c.querySelector('.todo-top .chip').getBoundingClientRect();
  return {card: c.dataset.item, after: Math.round(p.left - k.right), under: Math.round(Math.abs(p.left - k.left))}; }))()"""


def test_a_to_do_cards_state_pills_follow_its_kind_on_a_phone(run, tmp_path):
    # With its Later or trash in the corner, a card's pills read from its kind, never pushed
    # to the far end or floating mid-line when they wrap (2026-11-10).
    rows = _eval(run, tmp_path, "todo", CHIPS, PHONE)
    assert rows and all(r["after"] <= 16 or r["under"] <= 4 for r in rows), rows


SWITCH = r"""(() => [...document.querySelectorAll('#main .segctl .seg-opt')].filter((o) => o.getClientRects().length).map((o) => {
  const g = document.createRange(); g.selectNodeContents(o);
  return {word: o.textContent.trim(), lines: new Set([...g.getClientRects()].map((r) => Math.round(r.top))).size}; }))()"""


def test_a_switchs_words_are_never_broken_at_the_pages_own_size(run, tmp_path, vp):
    # A lone switch wraps its words at double text (layout 14), but its options shared its
    # width equally, so "Interviews" broke into "Intervie / ws" at every size (the screen
    # review, 2026-11-11). Each option is its own words' width, one line, at the page's size.
    opts = _eval(run, tmp_path, "interviews", SWITCH, vp)
    assert opts and all(o["lines"] == 1 for o in opts), opts


# One search running and one draft waiting its turn: the header's pill at its longest.
BUSY = dict(WORK, **{"work/draft~r12-2": dict(_W, kind="draft", title="CV and letter: Larkspur Retail, Senior Supply Chain Analyst",
                                              status="queued", asked_at="2026-10-25T08:59:20.000Z")})
TITLE = r"""(() => { const s = document.getElementById('screen'), p = document.getElementById('pill');
  return {title: s.textContent, cut: s.scrollWidth > s.clientWidth + 1, pill: p ? p.innerText.trim() : null,
          said: p ? p.textContent.replace(/\s+/g, ' ').trim() : null}; })()"""


@pytest.mark.parametrize("screen", ["brief", "interviews", "profile"])
def test_a_phones_header_never_cuts_the_screens_name(run, tmp_path, screen):
    # "Coming…" and "Your pr…": the screen's only visible name on a phone gave way to "1
    # running · 1 waiting" (the screen review, 2026-11-11). Where both do not fit, the pill
    # says its count, and its words stay for a screen reader.
    got = _go(run, tmp_path, [{"hash": screen, "eval": TITLE}], PHONE, clock=T, seed=BUSY)["after"][0]["eval"]
    assert not got["cut"], got
    assert got["pill"] and "1 waiting" in got["said"], got
    if screen == "brief":
        # A short name leaves the pill its words.
        assert "waiting" in got["pill"], got


CORNER = r"""(() => [...document.querySelectorAll('#main .card.todo')].filter((c) => c.getClientRects().length && c.querySelector(':scope > .todo-top > [data-bin], :scope > .todo-top > .hide-x')).map((c) => {
  const top = c.querySelector(':scope > .todo-top'), end = top.querySelector(':scope > [data-bin], :scope > .hide-x'), pill = top.querySelector('.state-word, .chip');
  const cr = c.getBoundingClientRect(), er = end.getBoundingClientRect(), pr = pill ? pill.getBoundingClientRect() : null;
  const cs = getComputedStyle(c);
  return {card: c.dataset.item, corner: Math.round(cr.right - er.right), edge: Math.round(parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth)),
          gap: pr ? Math.round(er.left - pr.right) : null, kindGap: pr ? Math.round(pr.left - top.firstElementChild.getBoundingClientRect().right) : null};
}))()"""


def test_a_to_do_cards_trash_is_in_its_corner_and_its_pill_never_floats(run, tmp_path, vp):
    # An interview's card in To do drew its trash right after "In 3 days" on a phone, and its
    # pill mid-row on a wide screen, unlike every other card (the screen review, 2026-11-11).
    rows = _eval(run, tmp_path, "todo", CORNER, vp)
    ivs = [r for r in rows if r["card"].startswith("soon:")]
    assert ivs, rows
    # In its corner: no further in than the card's own padding and border (Safari drew the 1px
    # border Chrome's rounding hid, 4.15.0's run).
    assert all(r["corner"] <= r["edge"] + 1 for r in rows), rows
    if vp is PHONE:
        assert all(r["kindGap"] is None or r["kindGap"] <= 16 for r in ivs), ivs
    else:
        assert all(r["gap"] is None or r["gap"] <= 24 for r in ivs), ivs


SENDROWS = r"""(() => { const card = document.querySelector('#main .send-card'); if (!card) return null;
  const cr = card.getBoundingClientRect(), pad = parseFloat(getComputedStyle(card).paddingRight), edge = pad + parseFloat(getComputedStyle(card).borderRightWidth);
  const lines = (e) => { const g = document.createRange(); g.selectNodeContents(e); return new Set([...g.getClientRects()].map((r) => Math.round(r.top))).size; };
  return [...card.querySelectorAll('.g-row')].filter((r) => r.getClientRects().length).map((r) => {
    const pill = r.querySelector('.g-acts .btn:not(.icon-only)'), bin = r.querySelector('.g-acts [data-bin]'), link = r.querySelector('.g-name .name-link'), at = r.querySelector('.g-at');
    return {pill: pill ? Math.round(pill.getBoundingClientRect().left) : null, bin: bin ? Math.round(cr.right - pad - bin.getBoundingClientRect().right) : null,
            line: Math.round(r.getBoundingClientRect().right - cr.left), card: Math.round(cr.width), edge: Math.round(edge), nameLines: link ? lines(link) : null,
            atBelow: link && at ? (() => { const g = document.createRange(); g.selectNodeContents(link); const a = document.createRange(); a.selectNodeContents(at);
              return a.getClientRects()[0].top >= g.getClientRects()[0].bottom - 1; })() : null};
  }); })()"""


def test_messages_to_send_rows_span_the_card_with_their_trash_at_its_edge(run, tmp_path, vp):
    # Wide, the rows stopped about 300px short of the card's edge, their pills and trash a
    # column in mid-card; on a phone a name wrapped to three underlined lines beside its pill
    # ("Noor at / Brackenridge / Advisory") (the screen review, 2026-11-11). The row spans the
    # card, its trash at the card's edge, its pill in a column near the names; a phone puts
    # the name on its line and where they work under it.
    rows = _eval(run, tmp_path, "todo", SENDROWS, vp)
    assert rows and len(rows) >= 5, rows
    assert all(r["bin"] is not None and r["bin"] <= 8 for r in rows), rows
    # To the card's content edge, its padding and its border (Safari counted the 1px border
    # Chrome's rounding hid, 4.15.0's run).
    assert all(r["line"] >= r["card"] - r["edge"] - 1 for r in rows), rows
    if vp is WIDE:
        assert len({r["pill"] for r in rows}) <= 2 and max(r["pill"] for r in rows) - min(r["pill"] for r in rows) <= 2, rows
    else:
        assert all(r["nameLines"] == 1 for r in rows if r["nameLines"] is not None), rows
        assert [r for r in rows if r["atBelow"] is not None] and all(r["atBelow"] for r in rows if r["atBelow"] is not None), rows


# Every "·" in a line of facts, and whether it sits on the line of what follows it.
DOTS = r"""((sel) => { const out = [];
  for (const box of document.querySelectorAll(sel)) {
    if (!box.getClientRects().length) continue;
    const walk = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const i = n.data.indexOf('·'); if (i < 0) continue;
      const g = document.createRange(); g.setStart(n, i); g.setEnd(n, i + 1); const dot = g.getClientRects()[0]; if (!dot) continue;
      let next = n.nextSibling; while (next && next.nodeType === 3 && !next.data.trim()) next = next.nextSibling;
      // The first letter after the dot, in its own words or in what follows them.
      const j = n.data.slice(i + 1).search(/[^\s\u00a0\u2060]/);
      // A button's own words, never its box, which is taller than the line on a phone.
      const words = (e) => { const r = document.createRange(); r.selectNodeContents(e); return r.getClientRects()[0]; };
      const after = j >= 0 ? (() => { const r = document.createRange(); r.setStart(n, i + 1 + j); r.setEnd(n, i + 2 + j); return r.getClientRects()[0]; })() : next && next.nodeType === 1 ? words(next) : null;
      if (after) out.push({text: n.data, alone: Math.abs(after.top - dot.top) > 4});
    }
  }
  return out; })"""


@pytest.mark.parametrize("screen,sel", [("jobs", "#main .card.job .facts"), ("interviews", "#main .up-row .up-main")])
def test_a_facts_separator_never_ends_a_line(run, tmp_path, screen, sel):
    # "Copperleaf Pay · Manchester ·" and "Interview · Supply Chain Analyst ·" ended lines on a
    # phone, the next fact under them (the screen review, 2026-11-11). A dot goes with what
    # follows it.
    dots = _eval(run, tmp_path, screen, DOTS + "(" + repr(sel) + ")", PHONE)
    assert dots, dots
    assert [d for d in dots if d["alone"]] == [], dots
    if screen == "interviews":
        # The dot between what a row is and its prep is drawn, not written: on a phone, where
        # the prep's pill takes the next line, there is none to end the line before.
        left = _eval(run, tmp_path, screen, "[...document.querySelectorAll('#main .up-row .up-note')].filter((n) => n.nextElementSibling && n.nextElementSibling.matches('.up-prep'))"
                     ".map((n) => [getComputedStyle(n, '::after').content, getComputedStyle(n.nextElementSibling, '::before').content])", PHONE)
        assert left and all(a in ("none", "normal") and b in ("none", "normal") for a, b in left), left


IVTOP = r"""(() => [...document.querySelectorAll('#main .card.interview')].filter((c) => c.getClientRects().length).map((c) => {
  const t = c.querySelector('.job-top h3').getBoundingClientRect(), bin = c.querySelector('.job-top [data-bin]'), pill = c.querySelector('.state-word'), when = c.querySelector('.when');
  return {card: c.dataset.item, binBeside: bin ? bin.getBoundingClientRect().top < t.bottom : null,
          pillOnWhen: pill && when ? Math.abs((pill.getBoundingClientRect().top + pill.getBoundingClientRect().bottom) / 2 - (when.getBoundingClientRect().top + Math.min(when.getBoundingClientRect().height, 24) / 2)) < 8 : null};
}))()"""


def test_an_interviews_card_on_a_phone_keeps_its_pill_on_the_when_line_and_its_trash_beside_the_title(run, tmp_path):
    # "In 3 days" and the trash took a row of their own under the title on a phone (the
    # screen review, 2026-11-11).
    got = _go(run, tmp_path, [{"hash": "interviews", "open": "up-view:interviews", "eval": IVTOP}], PHONE, clock=T)
    cards = [c for c in got["after"][0]["eval"] if c["pillOnWhen"] is not None]
    assert cards and all(c["pillOnWhen"] for c in cards), cards
    assert all(c["binBeside"] in (True, None) for c in cards), cards


SUBJECT = ("[...document.querySelectorAll('#main .pdraft > .subject')].filter((p) => p.getClientRects().length).map((p) => {"
           " const g = document.createRange(); g.selectNodeContents(p.children[1]); const line = g.getClientRects()[0];"
           " const b = p.querySelector('.btn').getBoundingClientRect();"
           " return {words: p.children[1].textContent, off: Math.round(((b.top + b.bottom) / 2 - (line.top + line.bottom) / 2) * 10) / 10}; })")


def test_an_email_subjects_copy_sits_on_its_line(run, tmp_path, vp):
    # The README picture of 4.15.0: the subject's Copy sat 7px below "Subject: Thank you for
    # Thursday", its top lined up with the words' top and its height hanging under them.
    got = _eval(run, tmp_path, "contacts", SUBJECT, vp)
    assert got, "an email draft with a subject on Contacts"
    assert all(abs(s["off"]) <= 2 for s in got), got


NARROW_WHY = r"""(() => Array.from({length: 161}, (_, i) => 140 + i).flatMap((w) => [...document.querySelectorAll('#main .card.job .facts')].map((f) => {
  f.style.maxWidth = w + 'px';
  const why = f.querySelector('.info-toggle'), last = [...f.querySelectorAll('.fact')].pop();
  const end = last ? [...last.getClientRects()].pop() : null, b = why ? why.getBoundingClientRect() : null;
  const out = why && end ? Math.round(Math.abs((b.top + b.bottom) / 2 - (end.top + end.bottom) / 2)) : null;
  f.style.maxWidth = '';
  return out;
})).filter((x) => x !== null))()"""


def test_why_keeps_to_the_last_facts_words_at_any_width(run, tmp_path):
    # GitHub's runner drew one card's "Why" alone on the line under its last fact at 390 wide
    # (4.15.0's run): a plain space before "· Why" let the line break there when the last fact
    # and Why did not fit together. Any width, from 140px to 300px, keeps them together.
    got = _eval(run, tmp_path, "jobs", NARROW_WHY, PHONE)
    assert got and all(d <= 4 for d in got), got
