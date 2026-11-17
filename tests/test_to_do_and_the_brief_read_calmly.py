"""To do and the Brief read calmly: one next step a card, each thing said once, nothing cut off.

The redesign's second round (2026-11-17), from its three reviews of the first: To do's cards
were walls of equal grey pills with "N min of Claude" wedged between them ("Choose the role ·
15 min of Claude · Done · Open in Contacts" ran three lines on a phone); a thank-you note was
tagged "Interview"; "Not due yet (5)" stood open over its cards with its chevron saying shut;
nothing said "you are done for today"; a screen reader's list of headings skipped every card.
On the Brief, "Waiting on you" said again who Next already had, Next's steps did not look like
something to tap, its way to To do said "To do" under "1 of 4", News and Your progress were
ghost cards, the week strip's today was a ring that read as a key's stuck focus, and three
panels were capped at 300px and cut their rows under a person's own text spacing.
Every person and employer is invented (the sample's own, and the two added here).
"""
from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import app_page  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import _two_waiting  # noqa: E402

T = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


# Each To do card's face: the pills in its row of actions outside More, and where each gauge
# sits against the button it belongs to.
FACES = r"""(() => [...document.querySelectorAll('#main [data-card]')].filter((c) => c.getClientRects().length).map((c) => {
  const row = c.querySelector(':scope > .card-actions');
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const pills = row ? [...row.children].filter((e) => vis(e) && e.matches('.btn:not(.icon-only), a.btn, a.navlink')).map((e) => e.textContent.trim()) : [];
  const glued = row ? [...row.querySelectorAll(':scope > [data-wakes]')].filter(vis).map((b) => {
    const g = b.nextElementSibling; if (!g || !g.matches('.cost')) return null;
    const r = b.getBoundingClientRect(), q = g.getBoundingClientRect(), mid = (q.top + q.bottom) / 2;
    return mid > r.top && mid < r.bottom && q.left >= r.right - 1;
  }).filter((x) => x !== null) : [];
  return {card: c.getAttribute('data-item'), pills, more: !!(row && row.querySelector(':scope > details.more')), glued,
    kind: ((c.querySelector(':scope > .todo-top .kind') || {}).textContent || '').trim(), title: ((c.querySelector('.card-title') || {}).textContent || '').trim()};
}))()"""


def test_a_to_do_card_shows_its_next_step_and_one_more_its_gauge_beside_its_button(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": FACES}], vp, clock=T)
    cards = got["after"][0]["eval"]
    assert len(cards) >= 8, cards
    for c in cards:
        assert len(c["pills"]) <= 2, c
        # The minutes stay with the button that spends them, never alone on the next line.
        assert all(c["glued"]), c
    by = {c["card"]: c for c in cards}
    # The card that had four: its next step, Done, and Open in Contacts under More.
    tamsin = next(c for c in cards if "Tamsin" in c["title"])
    assert "Open in Contacts" not in tamsin["pills"] and tamsin["more"], tamsin
    # An interview: Read your prep alone on its face, Add to calendar first under More.
    iv = by["soon:int-larkspur-supply"]
    assert iv["pills"] == ["Read your prep"] and iv["more"], iv
    # The messages card: Open Contacts, and its time to send under More.
    assert by["grp:send"]["pills"] == ["Open Contacts"] and by["grp:send"]["more"], by["grp:send"]


def test_an_interviews_calendar_leads_its_more_on_to_do(run, tmp_path):
    more = ("[...document.querySelectorAll('#main [data-item=\"soon:int-larkspur-supply\"] .more-panel .btn')]"
            ".filter((b) => b.getClientRects().length).map((b) => b.textContent.trim())")
    got = _go(run, tmp_path, [{"hash": "todo", "more": "soon:int-larkspur-supply", "eval": more}], WIDE, clock=T)
    assert got["after"][0]["eval"][:1] == ["Add to calendar"], got["after"][0]["eval"]


def test_a_thank_you_is_tagged_as_the_message_it_is(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": FACES}], PHONE, clock=T)
    thanks = [c for c in got["after"][0]["eval"] if c["title"].startswith("Thank-you note")]
    assert thanks and all(c["kind"] == "Thank-you" for c in thanks), thanks


HEADS = r"""(() => {
  const out = [];
  for (const t of document.querySelectorAll('#main [data-card] > .card-title')) {
    if (!t.getClientRects().length) continue;
    const band = t.closest('section.band'), emp = t.closest('.todo-group.by-employer');
    const above = emp ? emp.querySelector('.todo-employer') : band ? band.querySelector(':scope > h3') : document.querySelector('#main h2.screen-title');
    out.push({title: t.textContent.trim().slice(0, 40), tag: t.tagName, above: above ? above.tagName : null});
  }
  return out;
})()"""


def test_every_to_do_card_title_is_a_heading_one_level_under_what_holds_it(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": HEADS}], WIDE, clock=T)
    heads = got["after"][0]["eval"]
    assert len(heads) >= 8, heads
    for h in heads:
        assert h["tag"] in ("H3", "H4", "H5") and h["above"], h
        assert int(h["tag"][1]) == int(h["above"][1]) + 1, h


FOLD = r"""(() => { const d = document.querySelector('#main details[data-k="det:todo-soon"]'); if (!d) return null;
  const s = d.querySelector(':scope > summary'), after = getComputedStyle(s, '::after');
  return {words: s.textContent.trim(), ink: getComputedStyle(s).color === getComputedStyle(document.querySelector('#main .card-title')).color,
    weight: getComputedStyle(s).fontWeight, chevron: after.width};
})()"""


def test_not_due_yet_waits_shut_under_its_one_disclosure(run, tmp_path, vp):
    # The page as it first draws To do, with nothing unfolded: the engine's steps open every
    # fold of To do to read what is behind it, so the first look is read on its own.
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(_sample())))
    first = run("paint", html=path, viewport=vp, hash="todo", clock=T, fake={"canSend": "available"})
    assert not first["errors"], first["errors"]
    words = first["bodyText"]
    # Shut: its name is said, the cards under it (Next 7 days, Later) are not.
    assert "Not due yet (" in words and "Second interview with Harbourline Bank" not in words and "Next 7 days" not in words, words[-800:]
    got = _go(run, tmp_path, [{"hash": "todo", "eval": FOLD}], vp, clock=T)
    f = got["after"][0]["eval"]
    # The one disclosure: its words in the ink at 600, with its chevron.
    assert f and f["words"].startswith("Not due yet (") and f["ink"] and f["weight"] == "600" and f["chevron"] == "8px", f


def _nothing_today():
    """Nothing late or due today, and nothing to answer: only what is coming later."""
    m = copy.deepcopy(_sample())
    m["due"] = [d for d in m["due"] if d.get("due") and d["due"] > "2026-10-27" and not d.get("overdue_days")]
    m["needs_you"] = []
    m["messages"] = []
    m["to_send"] = {"n": 0, "ids": []}
    for r in m["ready"]:
        r["alerts"] = []
    for r in m["jobs"]["rows"]:
        r["alerts"] = []
    m["interviews"] = [i for i in m["interviews"] if i.get("when", "") > "2026-10-28"]
    return m


CLEAR = r"""(() => { const c = document.querySelector('#main .all-clear'); if (!c) return null;
  return {head: (c.querySelector('h3, h4') || {}).tagName, words: c.innerText.split('\n').map((x) => x.trim()).filter(Boolean),
    circle: Math.round(c.querySelector('.empty-ic').getBoundingClientRect().width), quiet: [...c.querySelectorAll('.btn')].map((b) => b.className)};
})()"""


def test_nothing_due_today_is_said_as_good_news_on_to_do(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": CLEAR}], vp, model=_nothing_today(), clock=T)
    c = got["after"][0]["eval"]
    assert c, "no all clear on a To do with nothing due today"
    assert c["head"] == "H3" and c["words"][0] == "Nothing left today" and c["circle"] == 64, c
    assert c["words"][-1] == "See what's coming up" and len(c["quiet"]) == 1 and "quiet" in c["quiet"][0], c


PANELS = r"""(() => Object.fromEntries([...document.querySelectorAll('#main .brief-grid > .bpanel')].map((p) => [p.getAttribute('data-k'),
  {text: p.innerText, bg: getComputedStyle(p).backgroundColor, max: getComputedStyle(p).maxHeight}])))()"""


def test_waiting_on_you_names_only_who_today_and_next_leave_out(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": PANELS}], WIDE, clock=T)
    p = got["after"][0]["eval"]
    # Marisol is a row of the messages card in Next: with nobody else waiting, no panel.
    assert "bp:people" not in p and "Messages to send" in p["bp:next"]["text"], list(p)
    got = _go(run, tmp_path, [{"hash": "brief", "eval": PANELS}], WIDE, model=_two_waiting(copy.deepcopy(_sample())), clock=T)
    p = got["after"][0]["eval"]
    people = p["bp:people"]["text"]
    assert "Odette" in people and "Linus" in people and "Marisol" not in people, people


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_brief_panel_is_a_card_and_none_is_capped(run, tmp_path, scheme):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(_sample())))
    for size in ({"width": 860, "height": 900}, WIDE):
        got = run("engine", html=path, viewport=size, scheme=scheme, steps=[{"hash": "brief", "eval": PANELS}], seed={}, fake={"canSend": "available"}, clock=T)
        assert not got["errors"], got["errors"]
        p = got["after"][0]["eval"]
        cards = {k: v["bg"] for k, v in p.items() if k != "bp:today"}
        # News and Your progress as cards like the rest, never the page itself.
        assert len(set(cards.values())) == 1 and "rgba(0, 0, 0, 0)" not in cards.values(), cards
        assert all(v["max"] == "none" for v in p.values()), {k: v["max"] for k, v in p.items()}


WEEK = r"""(() => { const d = document.querySelector('#main .bp-day.is-today'); const n = d.querySelector('.bp-day-n'); const cs = getComputedStyle(d);
  return {ring: cs.boxShadow, outline: cs.outlineStyle, fill: cs.backgroundColor, radius: cs.borderRadius, weight: getComputedStyle(n).fontWeight}; })()"""


def test_today_in_the_week_is_a_soft_fill_never_a_ring(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": WEEK}], WIDE, clock=T)
    w = got["after"][0]["eval"]
    assert w["ring"] == "none" and w["outline"] == "none" and w["fill"] not in ("rgba(0, 0, 0, 0)", "transparent"), w
    assert w["radius"] == "10px" and w["weight"] == "700", w


NEXT = r"""(() => [...document.querySelectorAll('#main .bp-steps > li')].filter((li) => li.getClientRects().length).map((li) => {
  const r = li.getBoundingClientRect(), a = li.querySelector('a.bp-link');
  const hit = document.elementFromPoint(r.right - 6, (r.top + r.bottom) / 2);
  return {chevron: getComputedStyle(li, '::after').borderRightStyle, whole: !!hit && hit.closest('a') === a};
}))()"""


def test_next_steps_are_whole_rows_to_tap_with_a_chevron(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": NEXT}], vp, clock=T)
    rows = got["after"][0]["eval"]
    assert len(rows) == 3 and all(r["chevron"] == "solid" and r["whole"] for r in rows), rows


def test_things_are_called_what_a_person_calls_them(run, tmp_path):
    """The UX review, 2026-11-17: "When it comes", "Add something", "Plan a time" and LinkedIn's
    own "InMail" said less than they could."""
    got = _go(run, tmp_path, [
        {"hash": "brief", "read": "#main .brief-head"},
        {"hash": "brief", "read": '#main [data-k="bp:upcoming"] .bp-foot'},
        {"hash": "settings"},
        {"hash": "todo", "more": "grp:send", "read": '#main [data-item="grp:send"]'},
    ], WIDE, clock=T)
    head, foot, settings, send = (a["text"] for a in got["after"])
    assert "When your brief arrives" in head and "When it comes" not in head, head
    assert "Add a date" in foot and "Add something" not in foot, foot
    assert "When your brief arrives" in settings and "When it comes" not in settings, settings[:600]
    assert "Set a time to send" in send and "Plan a time" not in send and "InMail" not in send, send


HOW = r"""(() => { const d = document.querySelector('#main [data-item="linkedin-export"] details.how-fold'); if (!d) return null;
  return {open: d.open, words: d.querySelector(':scope > summary').textContent.trim(), steps: d.querySelector('ol.steps').checkVisibility(),
    button: [...document.querySelectorAll('#main [data-item="linkedin-export"] .card-actions .btn')].map((b) => b.textContent.trim())}; })()"""


def test_linkedins_steps_wait_one_tap_away(run, tmp_path):
    """The UX review, 2026-11-17: the LinkedIn card printed its three steps inline, eight lines
    on a phone. They wait under "How to get it"; its button opens the page they start on."""
    got = _go(run, tmp_path, [{"hash": "todo", "eval": HOW}], PHONE, clock=T)
    h = got["after"][0]["eval"]
    assert h and h["open"] is False and h["words"] == "How to get it" and h["steps"] is False, h
    assert [b.startswith("Open LinkedIn's download page") for b in h["button"]] == [True], h
