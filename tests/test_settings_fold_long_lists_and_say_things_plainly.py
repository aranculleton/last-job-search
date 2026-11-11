"""Settings, 4.12 (the maintainer's notes): long lists are one row that opens them, each list
shows its first few with Show all, things are said plainly, and the folded Advanced holds only
what can slow things down or use more of the Claude allowance.

- Your rules: every employer turned down was its own full-width row, a wall. Now one row,
  "Employers you've turned down (N)", with what they left out; it opens the names, each with a
  small trash.
- Learned rules were shown twice: in Your rules (210 rows titled "Learned from you") and in
  What you have taught it. One home now, grouped by area, a rule a line; Your rules has one
  row that opens it.
- Something looks wrong opens its box in place, no popup, begun with where and the version;
  Tell the app's makers stays a quiet link under the box.
- What's new says the version on its row; inside, the newest few lines with Show more, and
  Changes made for you in plain words, each change once.
- Text size: Smaller and Larger are drawn in the size they set, the control keeping its
  height.
- Jobs you hid: plain labels ("You cleared these", "Not this employer"), never "at the
  person's request" or "Employer: 1 job".
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample  # noqa: E402

CLOCK = "2026-10-25T09:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _go(run, tmp_path, steps, vp, model=None, name="page"):
    path = os.path.join(str(tmp_path), name + ".html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model or _sample())))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={}, fake={"canSend": "available"}, clock=CLOCK)
    assert not got["errors"], got["errors"]
    return got


def _rule(rid, kind, name, sentence, left=0, **more):
    return dict({"id": rid, "kind": kind, "name": name, "sentence": sentence, "set_on": "2026-09-01", "words": None,
                 "review_on": None, "left_out": left, "edit": None, "drop": None, "still_right": False, "rev": "r-" + rid}, **more)


def _model(declined=30, learned=15):
    m = _sample()
    rows = [_rule("rule~places", "place", "Where", "You search in Leeds", 4, edit={"what": "places"})]
    for i in range(declined):
        who = "Employer %02d" % i
        rows.append(_rule("rule~declined~e%02d" % i, "declined", "No more from " + who, "No more roles from " + who, i % 3,
                          drop={"kind": "declined", "key": "e%02d" % i}))
    areas = ["messages", "documents", "jobs"]
    for i in range(learned):
        rows.append(_rule("rule~learned~%d" % (i + 1), "learned", "Learned from you", "Rule %d" % i, None, drop={"kind": "learned", "n": i + 1}))
    m["rules"] = {"id": "your-rules", "rows": rows, "brief_line": None, "still_right": 0, "rev": "rv"}
    m["learned"] = [{"id": "learned-%d" % (i + 1), "n": i + 1, "area": areas[i % 3], "rule": "A rule about %s number %d, written out at some length so it runs past one line" % (areas[i % 3], i),
                     "say": "A rule about %s number %d, written out at some length so it runs past one line on a phone" % (areas[i % 3], i),
                     "said": "", "on": "2026-10-%02d" % (1 + i), "retired": False, "rev": "l%d" % i} for i in range(learned)]
    return m


SETTINGS_TEXT = "document.getElementById('main').textContent"


def test_employers_turned_down_are_one_row_that_opens_their_names_each_with_a_trash(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": SETTINGS_TEXT, "count": '#main [data-k^="info-sum:rule-rule-declined"]'},
        {"open": "info-sum:rules-declined", "read": '[data-k="det:info:rules-declined"]', "count": '[data-k="det:info:rules-declined"] .dec-row [data-k^="rule-bin:"]'},
        {"open": "few:declined", "count": '[data-k="det:info:rules-declined"] .dec-row'},
    ], WIDE, model=_model())
    first, opened, all_ = got["after"]
    assert first["count"] == 0, "no row a turned-down employer"
    assert "Employers you've turned down (30)" in first["eval"] and "No more from Employer" not in first["eval"]
    # The total they left out lately: 0+1+2 ten times over.
    assert "30 left out lately" in first["eval"], first["eval"][:400]
    assert opened["count"] == 5 and "Show all" in opened["text"], (opened["count"], opened["text"][:300])
    assert all_["count"] == 30


def test_learned_rules_have_one_home_grouped_by_area_and_your_rules_links_to_it(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": SETTINGS_TEXT, "count": '#main [data-k^="info-sum:rule-rule-learned"]'},
        {"click": "Learned from you: 15 rules", "eval": "document.querySelector('[data-k=\"det:info:learned\"]').open",
         "read": '[data-k="det:info:learned"]', "count": '[data-k="det:info:learned"] .l-group'},
        {"eval": "(() => { const s = document.querySelector('[data-k=\"det:info:learned\"] .l-say'); const r = s.getBoundingClientRect();"
                 " return [getComputedStyle(s).whiteSpace, getComputedStyle(s).textOverflow, Math.round(r.height) < 40,"
                 " !!s.parentElement.querySelector('.l-on')]; })()"},
    ], PHONE, model=_model())
    first, opened, line = got["after"]
    assert first["count"] == 0, "no learned rule in Your rules"
    assert "Learned from you: 15 rules" in first["eval"]
    assert opened["eval"] is True and opened["count"] == 3, (opened["eval"], opened["count"])
    for head in ("Messages (5)", "Documents (5)", "Jobs (5)"):
        assert head in opened["text"], opened["text"][:400]
    assert opened["text"].count("Show all") == 3, "each area its first three"
    assert line["eval"] == ["nowrap", "ellipsis", True, True], line["eval"]


def test_something_looks_wrong_opens_its_box_in_place_with_the_makers_link_under_it(run, tmp_path):
    m = _model(declined=0, learned=0)
    got = _go(run, tmp_path, [
        {"hash": "jobs"},
        {"hash": "settings", "click": "Something looks wrong", "exact": False,
         "eval": "(() => { const t = document.querySelector('#main textarea.ct-text'); const a = document.querySelector('#main [data-k=\"report-makers\"]');"
                 " return [t ? t.value : null, a ? a.href : '', !!document.querySelector('dialog[open]'),"
                 " a ? !!(t.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) : false]; })()"},
        {"click": "Cancel the question", "within": "#main .ct-box", "eval": "!!document.querySelector('#main textarea.ct-text')"},
    ], WIDE, model=m)
    value, href, dialog, after = got["after"][1]["eval"]
    assert not dialog, "no popup"
    assert value and value.startswith("On ") and m["app"]["version"] in value, value
    assert "Jobs" in value, "where the person came from"
    assert href.startswith("https://github.com/aranculleton/last-job-search/issues/new?") and after, (href, after)
    assert "Leave out names" in got["after"][1]["text"]
    assert got["after"][2]["eval"] is False


def test_whats_new_says_the_version_on_its_row_and_folds_to_the_newest_few(run, tmp_path):
    m = _model(declined=0, learned=0)
    m["updates"] = {"version": "4.11.0", "changed": [{"version": "4.11.0", "date": "2026-10-20", "lines": ["Line %d" % i for i in range(6)]},
                                                     {"version": "4.10.0", "date": "2026-10-10", "lines": ["Old %d" % i for i in range(6)]}],
                    "done": [{"id": "upg-%d" % i, "line": "A plain change %d." % i, "on": "2026-10-%02d" % (10 + i), "undone": False} for i in range(6)],
                    "mode": "auto", "waiting": None, "changelog": ""}
    m["app"]["update_waiting"] = False
    got = _go(run, tmp_path, [
        {"hash": "settings", "read": '[data-k="info-sum:news"]'},
        {"open": "info-sum:news", "read": '[data-k="det:info:news"]', "count": '[data-k="det:info:news"] .news-line'},
    ], WIDE, model=m)
    assert "4.11.0 · Up to date" in got["after"][0]["text"], got["after"][0]["text"]
    body = got["after"][1]
    assert body["count"] == 3 and body["text"].count("Show more") == 2, (body["count"], body["text"][:500])
    assert "A plain change 5." in body["text"] and "A plain change 0." not in body["text"], "the newest first"


def test_smaller_and_larger_are_drawn_in_the_size_they_set_and_keep_the_controls_height(run, tmp_path):
    read = ("(() => ['smaller', 'standard', 'larger'].map((v) => { const s = document.querySelector('[data-size=\"' + v + '\"]');"
            " return [parseFloat(getComputedStyle(s).fontSize), Math.round(s.closest('label').getBoundingClientRect().height)]; }))()")
    got = _go(run, tmp_path, [{"hash": "settings", "eval": read}], WIDE, model=_model(0, 0))
    (sm, hs), (st, ht), (lg, hl) = got["after"][0]["eval"]
    assert sm < st < lg, (sm, st, lg)
    assert hs == ht == hl, (hs, ht, hl)


def test_advanced_holds_only_what_costs_time_or_allowance_and_the_rest_is_where_it_belongs(run, tmp_path):
    read = ("(() => { const g = (t) => [...document.querySelectorAll('#main .set-group')].find((x) => (x.querySelector('h3, summary') || {}).textContent === t);"
            " const adv = document.querySelector('#main .set-advanced');"
            " return [adv.querySelector('summary').textContent, [...adv.querySelectorAll('.set-name')].map((x) => x.firstChild.textContent.trim()),"
            " !!g('Look').querySelector('#keys-on'), !!g('Look').querySelector('#size-name'), !!g('This device').querySelector('[data-k=\"info-sum:device\"]'),"
            " adv.querySelector('.set-intro').textContent]; })()")
    got = _go(run, tmp_path, [{"hash": "settings", "eval": read}], WIDE, model=_model(0, 0))
    summary, names, keys, size, device, intro = got["after"][0]["eval"]
    assert summary == "Advanced" and names == ["Where Claude works", "Suggestions"], (summary, names)
    assert keys and size and device
    assert "allowance" in intro and "slow" in intro


# ------------------------------------------------------------------ the engine's side


def test_changes_made_for_you_are_plain_words_and_never_a_file_or_a_test():
    import app_setup
    import profile_upgrades
    say = app_setup.plain_change
    assert say("Brought test_a_referral_in_flight_keeps_the_role in line") == app_setup.OWN_TESTS_LINE
    assert say("Updated networking.py with the new reading", "your contacts are read the new way") == "Your contacts are read the new way."
    assert say("set `PROFILE_READS` to browser", "") == "An improvement to your search."
    assert say("your resume's file names now carry your name") == "Your resume's file names now carry your name."
    for u in profile_upgrades.REGISTRY:
        assert not app_setup.CODE_WORD.search(u.gives or ""), (u.id, u.gives)


def test_the_same_change_logged_several_times_shows_once(monkeypatch):
    import app_setup
    same = {"id": "x", "said": "Your search reads the new boards", "reverted": False}
    monkeypatch.setattr(app_setup, "_upgrade_commits", lambda days=60: [
        dict(same, sha="a" * 40, date="2026-10-20"), dict(same, sha="b" * 40, date="2026-10-19"),
        {"id": "y", "said": "Fixed tools/app.py", "reverted": False, "sha": "c" * 40, "date": "2026-10-18"}])
    got = app_setup.updates_section(__import__("datetime").date(2026, 10, 25), {})
    lines = [d["line"] for d in got["done"]]
    assert lines.count("Your search reads the new boards.") == 1 and not any("app.py" in x for x in lines), lines


def test_jobs_you_hid_are_said_in_plain_words():
    import app_model
    say = app_model.hid_label
    assert say("Cleared from the list at the person's request") == "You cleared these"
    assert say("not for me (said on the page)") == "You cleared these"
    assert say("Cleared automatically after a week") == "Cleared automatically after a week"
    assert say("employer") == "Not this employer"
    assert say("closed") == "The job closed"
    assert say("pay") == "The pay" and say("place") == "The place" and say("field") == "Not my field"
    assert say("not this role") == "Not this one" and say("old") == "Posted too long ago"
    assert say("Too senior for the person") == "Too senior for you"


def test_the_interview_and_the_reminder_have_their_new_choices():
    import app_model
    import upcoming
    got = {k: [c[0] for c in ch] for k, _, ch in app_model.SETTINGS}
    assert got["prep_days"][0] == "1" and dict(dict((k, ch) for k, _, ch in app_model.SETTINGS)["prep_days"])["1"] == "From the day before"
    rem = got["calendar_reminder"]
    assert rem.index("60") < rem.index("120") < rem.index("1440")
    assert dict(dict((k, ch) for k, _, ch in app_model.SETTINGS)["calendar_reminder"])["120"] == "Two hours before"
    orig = upcoming.person.get
    try:
        upcoming.person.get = lambda key, default=None: "120" if key == "calendar_reminder" else orig(key, default)
        assert upcoming.reminder_minutes() == 120
    finally:
        upcoming.person.get = orig


def test_a_rule_the_app_now_keeps_is_folded_under_now_part_of_the_app_and_not_counted(run, tmp_path):
    m = _model(declined=0, learned=6)
    m["learned"].append({"id": "learned-99", "n": 99, "area": "documents", "rule": "Name the resume file after me", "say": "Name the resume file after you",
                         "said": "", "on": "2026-09-01", "retired": True, "why": "Now part of the app", "app_does": "Every resume file carries your name.",
                         "retired_on": "2026-10-20", "rev": "l99"})
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:learned", "read": '[data-k="det:info:learned"]', "count": '[data-k="det:info:learned"] .l-group[data-area] .l-item'},
        {"open": "l-part", "read": '[data-k="det:learned-part"]'},
    ], WIDE, model=m)
    assert got["after"][0]["count"] == 6 and "Now part of the app (1)" in got["after"][0]["text"], got["after"][0]["text"][:400]
    assert "Every resume file carries your name." in got["after"][1]["text"]


RULES = r"""(() => {
  const group = (name) => [...document.querySelectorAll('#main .set-group, #main section')].find((g) => { const h = g.querySelector('h3, .group'); return h && h.textContent.trim() === name; });
  const rows = (g) => g ? [...g.querySelectorAll('.set-sum')].filter((r) => r.getClientRects().length).map((r) => [r.querySelector('.set-name').textContent.trim(), (r.querySelector('.set-value') || {}).textContent || '']) : null;
  const yours = group('Your rules'), more = yours && yours.querySelector('.few-more .btn');
  const first = yours && yours.querySelector('.setting-row');
  return {search: rows(group('Your search')), rules: rows(yours), more: more ? more.textContent.trim() : null,
          inset: more && first ? Math.round(more.getBoundingClientRect().left - first.getBoundingClientRect().left) : null,
          rowInset: first ? Math.round(first.querySelector('.set-name').getBoundingClientRect().left - first.getBoundingClientRect().left) : null};
})()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_your_rules_lists_what_left_something_out_and_your_search_carries_its_own(run, tmp_path, vp):
    # "Where" and "Pay" each twice a screen apart, one saying the places and one "2 left out
    # lately", and four rows of "None left out lately" (the screen review, 2026-11-11). What a
    # search row's rule left out is said on that row; Your rules lists the rules that left
    # something out, the rest behind Show all, at the rows' own inset.
    m = _sample()
    with open(os.path.join(ROOT, "tests", "fixtures", "app_model_example.json"), encoding="utf-8") as fh:
        m["rules"] = __import__("json").load(fh)["rules"]
    got = _go(run, tmp_path, [{"hash": "settings", "eval": RULES}], vp, model=m)["after"][0]["eval"]
    where = dict(got["search"])["Where"]
    assert "2 left out lately" in where, got["search"]
    names = [n for n, _ in got["rules"]]
    assert not {"Where", "Pay", "Your field"} & set(names), got["rules"]
    assert not [v for _, v in got["rules"] if "None left out" in v], got["rules"]
    assert "Needs a qualification you do not hold" in names, got["rules"]
    assert got["more"] and got["inset"] is not None and got["inset"] >= got["rowInset"] - 1, got


MONEY = r"""(() => { const t = (s) => (document.querySelector(s) || {}).textContent || ''; return {pay: t('[data-k="info-sum:search-pay"]'), prep: t('dialog.detail')}; })()"""


def test_money_is_written_one_way_everywhere(run, tmp_path):
    # "At least GBP 38,000" in Settings and "Say GBP 44,000" in the prep, against "£44,000" on
    # the job's card: the same money written two ways (the screen review, 2026-11-11).
    got = _go(run, tmp_path, [{"hash": "settings", "eval": MONEY}, {"hash": "interviews/int-larkspur-supply/open", "wait": 200, "eval": MONEY}], WIDE)
    pay, prep = got["after"][0]["eval"]["pay"], got["after"][1]["eval"]["prep"]
    assert "£38,000" in pay and "GBP" not in pay, pay
    assert "£44,000" in prep and "GBP" not in prep, prep[:600]


def test_whats_new_leaves_a_waiting_update_to_the_row_that_offers_it(run, tmp_path):
    # "What's new: 4.0.0 · An update is waiting" repeated the update's own row at the top of
    # Settings, with its Update now (the screen review, 2026-11-11). The version stays.
    got = _go(run, tmp_path, [{"hash": "settings", "eval": "[(document.querySelector('[data-k=\"info-sum:news\"]') || {}).textContent || '', document.querySelectorAll('#main .update-row').length]"}], WIDE)
    news, banner = got["after"][0]["eval"]
    assert banner == 1 and "An update is waiting" not in news and news.startswith("What's new"), (news, banner)


def test_your_profile_says_past_jobs_and_an_empty_list_is_added_to(run, tmp_path):
    # Settings summed the profile as "2 roles", beside Your search's Roles (the roles wanted),
    # and an empty Certificates offered "Change" (the screen review, 2026-11-11).
    got = _go(run, tmp_path, [{"hash": "settings", "read": '[data-k="open-profile"]'},
                              {"hash": "profile", "eval": "(document.querySelector('[data-k=\"you-certs\"]') || {}).textContent"}], PHONE)
    assert "2 past jobs" in got["after"][0]["text"] and "roles" not in got["after"][0]["text"], got["after"][0]["text"]
    assert got["after"][1]["eval"] == "Add", got["after"][1]["eval"]
