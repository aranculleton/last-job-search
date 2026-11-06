"""TEMPORARY: measurements from Safari's and Firefox's engines, run by hand on GitHub. Removed
before merging. Every person and employer is invented (the sample's own)."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, _go, _sample  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import _full, T, PERSON_ZONE  # noqa: E402
from test_the_chat_opens_on_its_latest import _talk  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


R = "(e) => { if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; }"

BRIEF = r"""(() => { const R = %s;
  const g = document.querySelector('#main .brief-grid');
  const ps = [...g.children].filter((p) => p.getClientRects().length).map((p) => [p.getAttribute('data-k'), R(p), p.scrollHeight, p.clientHeight,
     [...p.querySelectorAll('[data-fit]')].map((l) => [...l.children].filter((x) => !x.hidden).length + '/' + l.children.length).join(',')]);
  const m = (f) => { const s = document.createElement('span'); s.style.font = f; s.textContent = 'The quick brown fox jumps over the lazy dog'; document.body.appendChild(s); const w = s.getBoundingClientRect().width; s.remove(); return Math.round(w * 10) / 10; };
  const cs = getComputedStyle(document.body);
  const shell = document.getElementById('shell');
  return {ih: innerHeight, sh: document.documentElement.scrollHeight, gh: g.style.height, filled: g.classList.contains('is-filled'),
    cols: getComputedStyle(g).gridTemplateColumns.split(' ').length, rows: getComputedStyle(g).gridTemplateRows,
    grid: R(g), shell: R(shell), main: R(document.querySelector('#main')), foot: [...document.querySelectorAll('.foot-line, .bp-tip, #main > .sec > *:last-child')].filter((e) => e.getClientRects().length).map((e) => [e.className, R(e)]),
    font: cs.fontFamily.slice(0, 60), fs: cs.fontSize, lh: cs.lineHeight, w16: m('16px ' + cs.fontFamily), w14: m('14px ' + cs.fontFamily), zoom: document.body.style.zoom,
    greet: R(document.querySelector('#main .sec-head')), panels: ps};
})()""" % R


@pytest.mark.parametrize("size", [{"width": 1000, "height": 560}, {"width": 1280, "height": 720}, {"width": 1440, "height": 900}], ids=["1000", "1280", "1440"])
def test_probe_brief(run, tmp_path, size):
    got = _go(run, tmp_path, [{"hash": "brief", "wait": 400, "eval": BRIEF}], size, model=_full(), clock=T, zone=PERSON_ZONE)
    assert False, "PROBE " + json.dumps(got["after"][0]["eval"], separators=(",", ":"))


CHAT = r"""(() => { const R = %s;
  const se = document.scrollingElement; const f = document.querySelector('#main .talk-form'); const j = document.querySelector('[data-k="talk-jump"]');
  const t = document.querySelector('.tabs'); const sec = f && f.closest('section');
  return {se: se && se.tagName, st: se && se.scrollTop, sy: scrollY, ih: innerHeight, vv: visualViewport && Math.round(visualViewport.height), sh: se && se.scrollHeight, ch: se && se.clientHeight,
    form: R(f), pos: f && getComputedStyle(f).position, bot: f && getComputedStyle(f).bottom, sec: R(sec), body: R(f && f.parentElement),
    jump: j && [j.hidden, R(j), getComputedStyle(j).display], tabs: t && [getComputedStyle(t).position, R(t), t.hidden],
    tabsh: getComputedStyle(document.documentElement).getPropertyValue('--tabs-h'), dvh: (() => { const d = document.createElement('div'); d.style.height = '100dvh'; document.body.appendChild(d); const h = d.getBoundingClientRect().height; d.remove(); return h; })(),
    secMin: sec && getComputedStyle(sec).minHeight, html: [getComputedStyle(document.documentElement).overflow, getComputedStyle(document.body).overflow]};
})()""" % R


def test_probe_chat_phone(run, tmp_path):
    html = _write(tmp_path, "talkphone", _sample())
    got = run("engine", html=html, viewport={"width": 390, "height": 760}, clock="2026-10-25T18:30:00Z", seed=_talk(), steps=[
        {"hash": "chat", "wait": 300, "eval": CHAT},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)"},
        {"wait": 300, "eval": CHAT},
        {"click": "Go to the latest message", "wait": 400, "eval": CHAT},
    ])
    a = got["after"]
    assert False, "PROBE " + json.dumps({"errors": got["errors"], "open": a[0]["eval"], "top": a[2]["eval"], "latest": a[3]["eval"]}, separators=(",", ":"))


CHIP = r"""(() => { const R = %s;
  const c = document.querySelector('[data-k="set-file_names-2"]').closest('.choice');
  const row = c.parentElement;
  return {iw: innerWidth, sw: document.documentElement.scrollWidth, chip: R(c), row: R(row), rowcs: getComputedStyle(row).display + ' ' + getComputedStyle(row).flexWrap,
    kids: [...row.children].map((k) => [R(k), k.scrollWidth, getComputedStyle(k).flex, getComputedStyle(k).minWidth, getComputedStyle(k).maxWidth]),
    label: [...c.querySelectorAll('label, label > span')].map((k) => [k.className, R(k), k.scrollWidth, getComputedStyle(k).whiteSpace, getComputedStyle(k).overflowWrap, getComputedStyle(k).minWidth]),
    up: (() => { const out = []; let e = row; for (let i = 0; i < 8 && e; i++, e = e.parentElement) out.push([e.className.slice(0, 30), R(e), e.scrollWidth]); return out; })()};
})()""" % R


def test_probe_chip_phone(run, tmp_path):
    import app_page
    from test_file_names_are_the_persons_choice import _setting
    model = _sample()
    model["settings"] = [s for s in model["settings"] if s.get("key") != "file_names"] + [_setting()]
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=PHONE, clock="2026-11-06T09:00:00Z", fake={"canSend": "available"}, steps=[
        {"hash": "settings"}, {"open": "set-sum:file_names", "wait": 300, "eval": CHIP},
        {"eval": "(document.querySelector('[data-k=\"set-file_names-2\"]').click(), 1)"}, {"wait": 1200, "eval": CHIP}])
    a = got["after"]
    assert False, "PROBE " + json.dumps({"errors": got["errors"], "open": a[1]["eval"], "after": a[3]["eval"]}, separators=(",", ":"))


JOBS = r"""(() => { const R = %s;
  return [...document.querySelectorAll('#main .card')].filter((c) => c.querySelector('.facts')).slice(0, 3).map((c) => { const f = c.querySelector('.job-main > .facts, .app-main > .facts, .facts');
    const rg = document.createRange(); if (f) rg.selectNodeContents(f); const tops = f ? [...rg.getClientRects()].filter((b) => b.width > 0).map((b) => [Math.round(b.left), Math.round(b.top), Math.round(b.width)]) : [];
    return {k: c.getAttribute('data-k'), card: R(c), tops, facts: f && [f.className, R(f), f.scrollWidth, getComputedStyle(f).lineHeight, f.textContent.slice(0, 160),
      [...f.children].map((x) => [x.tagName + '.' + x.className.slice(0, 20), R(x), getComputedStyle(x).whiteSpace])]}; });
})()""" % R


def test_probe_jobs_wide(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "jobs", "wait": 300, "eval": JOBS}], {"width": 1400, "height": 900})
    assert False, "PROBE " + json.dumps(got["after"][0]["eval"], separators=(",", ":"))
