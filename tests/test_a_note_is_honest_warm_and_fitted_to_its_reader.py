"""A first message is honest, warm and fitted to who reads it.

From one long networking session (2026-10-19 and 20), whose verdict was "this is making
the skill USELESS": a polite indirect template, the same structure in every note, a
false "I saw your package" hook, contractions forced out until the notes read "like
someone who just learned English as a second language", an exit line that invited no
reply, an eligibility line refused for a decision-maker, hedges stacked three deep, and
credentials with no reason in their sentence. Invented people and employers only; the
example person is Morgan Ellis.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import advice  # noqa: E402
import compose  # noqa: E402
import tone  # noqa: E402

FOUND = compose.how_found_line("team_search", company="Larkspur", team="forecasting")


def rules(found):
    return {a.rule for a in found}


# ------------------------------------------------------------ voice: contractions

def test_contractions_are_allowed_by_default_and_a_setting_brings_back_the_old_rule(monkeypatch):
    note = ("Hi Ana, hope you're well. I'm a supply-chain analyst in Manchester. I'd love to "
            "hear how you moved into forecasting. Would you have 15 minutes sometime?")
    assert "sentence_starts_with_contraction" not in {v.rule for v in tone.check(note)}
    monkeypatch.setattr(tone, "CONTRACTIONS", "refuse")
    assert "sentence_starts_with_contraction" in {v.rule for v in tone.check(note)}
    monkeypatch.setattr(tone, "CONTRACTIONS", "warn")
    assert "sentence_starts_with_contraction" in rules(compose.advise(note, "connection"))


# ------------------------------------------------------------ what reads as generated

@pytest.mark.parametrize("phrase", [
    "Larkspur is high on my list.",
    "Your team sits close to what I do.",
    "Yours is the kind of path I'd like to follow.",
    "I would value your view.",
    "It's the route I would most like to follow.",
    "I'd love a steer on which teams to look at and how to approach them.",
    "Data scientist here.",
    "How would someone like me get hired onto your team?",
    "How do you decide an AI workflow is good enough to ship?",
])
def test_each_phrase_the_person_rejected_is_warned_with_a_rewrite(phrase):
    found = [a for a in advice.check(f"Hi Ana, hope you're well. {phrase}", "connection")
             if a.rule == "ai_tell"]
    assert found and found[0].fix


def test_a_list_of_three_credentials_is_warned():
    found = advice.check("I've worked at Oakmere Foods, Saltmarsh Analytics and Brindle & Hart.",
                         "inmail")
    assert "three_credentials" in rules(found)


# ------------------------------------------------------------ hedges, confidently

def test_stacked_hedges_and_disclaimers_are_warned_and_one_light_hedge_is_not():
    over = ("I think your team could probably use forecasting help, though I can't know from "
            "the outside.")
    found = advice.check(over, "connection")
    assert {"stacked_hedge", "disclaimer"} <= rules(found)
    once = "I imagine your team spends a lot of time on depot forecasts."
    assert not {"stacked_hedge", "disclaimer", "unhedged_inference"} & rules(
        advice.check(once, "connection"))


# ------------------------------------------------------------ no exit in a first message

def test_an_exit_that_invites_no_reply_is_warned_in_a_first_message_only():
    text = "Would you have 15 minutes sometime? If not, no worries at all."
    found = [a for a in advice.check(text, "connection") if a.rule == "soft_exit"]
    assert found and "anything coming up" in found[0].fix
    assert "soft_exit" not in rules(advice.check(text, "nudge"))


# ------------------------------------------------------------ eligibility by reader

def test_eligibility_is_said_to_a_decision_maker_and_a_recruiter_and_never_to_a_peer():
    to_head = compose.first_note("Juno Castellan", how_found=FOUND, title="Head of Data",
                                 variant_key="a", shape="shared",
                                 about_me="I work in supply-chain analytics")
    assert compose.work_auth_line("senior") in to_head          # the senior register
    to_peer = compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst",
                                 variant_key="a")
    assert "sponsorship" not in to_peer
    # The person may say it in one message to a peer, and validate agrees.
    told = compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst",
                              work_auth=True, variant_key="a")
    assert "no sponsorship needed" in told
    assert "work_auth_in_first_note" in {v.rule for v in compose.validate(told, "connection",
                                                                          title="Data Analyst")}
    assert compose.validate(told, "connection", title="Data Analyst", work_auth=True) == []


def test_saying_the_role_wanted_is_allowed_to_a_decision_maker_not_asking_for_the_job():
    head = "Hi Juno, the role I want is in forecasting. I'm a supply-chain analyst in Manchester."
    assert not [v for v in compose.validate(head, "connection", title="Head of Data")
                if v.rule == "asks_for_the_job"]
    peer = [v for v in compose.validate(head, "connection", title="Data Analyst")
            if v.rule == "asks_for_the_job"]
    assert peer and "SAY_THE_ROLE" in peer[0].text
    ask = [v for v in compose.validate("Hi Juno, are you hiring?", "connection",
                                       title="Head of Data") if v.rule == "asks_for_the_job"]
    assert ask and "anything coming up" in ask[0].text


def test_a_second_clause_saying_they_are_looking_is_not_a_job_ask():
    text = ("Hi Ana, forecasting at Larkspur is exactly the work I want to be doing, and I am "
            "looking for my next role.")
    assert not compose.first_note_findings(text, reader="peer")


# ------------------------------------------------------------ honest reasons

def test_how_they_were_found_is_a_reason_and_a_claim_to_have_looked_needs_the_senders_word():
    note = compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst", variant_key="b")
    assert "while looking at Larkspur's forecasting team" in note
    with pytest.raises(compose.UnconfirmedReading):
        compose.first_note("Ana Rook", "I saw your package on GitHub for demand curves",
                           title="Data Analyst", how_found=FOUND)
    assert "package" in compose.first_note(
        "Ana Rook", "I saw your package on GitHub for demand curves", title="Data Analyst",
        how_found=FOUND, looked=True)


def test_a_path_parallel_and_a_confirmed_mutual_connection_are_reasons_too():
    note = compose.first_note(
        "Juno Castellan", mutual="Bo Venn", title="Data Analyst",
        parallel="It looks like you moved into Larkspur from logistics, which is the move "
                 "I'm hoping to make")
    assert note.startswith("Hi Juno, hope you're well. We're both connected to Bo Venn.")
    assert "It looks like you moved into Larkspur from logistics" in note


def test_a_note_that_never_reaches_them_names_the_word_to_add():
    with pytest.raises(compose.NoteIsAllAboutTheSender) as e:
        compose.first_note("Ana Rook", "I'm keen on forecasting", title="Data Analyst",
                           their=("Larkspur",), opener="", ask="Up for a quick chat sometime?",
                           about_me="I work in supply-chain analytics in Manchester")
    assert '"your"' in str(e.value) and "Larkspur" in str(e.value)


# ------------------------------------------------------------ where a claim comes from

def test_a_claim_about_them_is_stated_inferred_or_a_guess_and_an_unhedged_one_is_warned():
    r = {"headline": "Head of Data at Larkspur", "about": "I run a small team building "
         "forecasting tools for warehouses and depots.", "items": [], "experience": []}
    assert advice.provenance("Your team builds forecasting tools for warehouses.", r) == "STATED"
    assert advice.provenance("You started in logistics before moving into software.", r) == "INFERRED"
    assert advice.provenance("My work would be useful on a team like yours.", r) == "GUESS"
    assert advice.provenance("I found you on Larkspur's people page.", r) == ""
    found = rules(advice.check("You started in logistics before moving into software.",
                               "connection", reading=r))
    assert "unhedged_inference" in found
    assert "generic_fit" in rules(advice.check(
        "I can imagine my background being useful on a team like yours.", "connection",
        reading=r))


# ------------------------------------------------------------ every credential has a point

def test_a_credential_with_no_reason_in_its_sentence_is_warned():
    found = [a for a in advice.check("I also use SQL and Power BI daily.", "connection")
             if a.rule == "credential_without_purpose"]
    assert found and "why" in found[0].fix
    tied = "I use SQL daily, which is why your depot forecasting work interests me."
    assert "credential_without_purpose" not in rules(advice.check(tied, "connection"))
    evidence = "At Brindle & Hart I cut forecast error from 22% to 14% in SQL."
    assert "credential_without_purpose" not in rules(advice.check(evidence, "inmail"))


# ------------------------------------------------------------ InMail

def test_an_inmail_is_a_subject_and_a_body_in_the_shape_that_drew_a_reply():
    m = compose.inmail("Juno Castellan", how_found="I found you on Larkspur's people page",
                       evidence="At Brindle & Hart I cut forecast error from 22% to 14%",
                       title="Head of Data", variant_key="x")
    assert m.subject == compose.identity_subject() and m["subject"] == m.subject
    paras = m.body.split("\n\n")
    assert paras[0] == "Hi Juno, hope you're well."
    assert paras[2].startswith("At Brindle & Hart")
    assert compose.work_auth_line("senior") in paras[3]          # a decision-maker's register
    assert any(p in paras[3] for p in compose.BANK["ask"]["decision_maker"])
    assert paras[-1] == compose.SIGN_OFF["senior"]
    assert compose.validate(m, "inmail", title="Head of Data") == []


def test_an_inmail_longer_than_its_reader_needs_is_warned_not_refused():
    long = " ".join(["Forecasting at depot level is the work I enjoy most."] * 16)
    found = [a for a in compose.advise(long, "inmail", title="Data Analyst")
             if a.rule == "longer_than_this_reader_needs"]
    assert found and "130" in found[0].fix


# ------------------------------------------------------------ the phrase bank

def test_the_bank_varies_by_contact_and_every_variant_passes_the_checks():
    asks = {compose.phrase("ask", "decision_maker", key) for key in "abcdefghij"}
    assert len(asks) > 1
    assert compose.phrase("ask", "decision_maker", "k") == compose.phrase("ask", "decision_maker", "k")
    for reader, variants in compose.BANK["ask"].items():
        for ask in variants:
            note = compose.first_note("Ana Rook", how_found=FOUND, reader=reader, ask=ask,
                                      work_auth=False)
            assert compose.validate(note, "connection", reader=reader) == [], (reader, ask)
            assert "soft_exit" not in rules(compose.advise(note, "connection", reader=reader))


def test_a_pointer_note_ends_on_a_question_answered_by_naming_someone():
    note = compose.first_note("Ana Rook", "I'm keen to find the team doing depot forecasting "
                              "at Larkspur", how_found=FOUND, shape="pointer", title="Data Analyst",
                              variant_key="p")
    assert any(note.endswith(p) for p in compose.BANK["pointer"]["any"])


# ------------------------------------------------------------ read it aloud

def test_a_spoken_rewrite_keeps_every_fact_or_the_original_stands():
    original = ("Hi Ana, hope you're well. I came across your profile while looking at "
                "Larkspur's forecasting team. I cut forecast error from 22% to 14% at Brindle "
                "& Hart. Would you have 15 minutes sometime?")
    good = ("Hi Ana, hope you're well. I came across your profile while I was looking at "
            "Larkspur's forecasting team. At Brindle & Hart I cut forecast error from 22% to "
            "14%. Would you have 15 minutes sometime?")
    assert compose.read_aloud(original, good)["ok"]
    bad = good.replace("22%", "25%").replace("Brindle & Hart", "Fernhill")
    res = compose.read_aloud(original, bad)
    assert not res["ok"] and "22%" in res["lost"] and "25%" in res["added"]


# ------------------------------------------------------------ a batch alike

def test_notes_built_the_same_way_are_found_as_a_pair():
    a = ("Hi Ana, hope you're well. I came across your profile at Larkspur. I work in "
         "analytics. Would you have 15 minutes?")
    b = ("Hi Bo, hope you're well. I came across your work at Fernhill. I work in "
         "logistics. Would you have a call?")
    c = "Hi Cy, we both worked at Oakmere Foods. How did you find the move? Up for a chat?"
    assert [(x, y) for x, y, _ in compose.alike({"a": a, "b": b, "c": c})] == [("a", "b")]


# ------------------------------------------------------------ a reaction waits

def test_drafting_refuses_while_a_reaction_waits_to_be_recorded(monkeypatch):
    import learned
    monkeypatch.setattr(learned, "pending", lambda: [{"said": "too formal", "at": "x"}])
    with pytest.raises(compose.UnrecordedReaction, match="too formal"):
        compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst")


def test_a_rule_the_person_recorded_outranks_a_check(monkeypatch):
    import learned
    note = "Hi Ana, any openings on your team? I work in forecasting."
    assert "asks_for_the_job" in {v.rule for v in compose.validate(note, "connection")}
    monkeypatch.setattr(learned, "overrides", lambda: {"asks_for_the_job"})
    assert "asks_for_the_job" not in {v.rule for v in compose.validate(note, "connection")}
    assert "your_rule_outranks" in rules(compose.advise(note, "connection"))


# ------------------------------------------------------------ what the audit found

def test_the_check_and_read_aloud_commands_run(tmp_path):
    import subprocess
    note = tmp_path / "note.txt"
    note.write_text("Hi Ana, I came across your profile at Larkspur. Would you have 15 "
                    "minutes for a call?\n", encoding="utf-8")
    for args in (["check", str(note)], ["read-aloud", str(note), str(note)]):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "compose.py"),
                            *args], capture_output=True, text=True, env=os.environ)
        assert "NameError" not in r.stderr and r.returncode in (0, 1), r.stderr


def test_the_apps_own_asks_pass_a_voice_check_that_refuses_would_love_to(monkeypatch):
    import re
    monkeypatch.setattr(compose, "_OWN_VOICE", re.compile(r"(?!x)x"))
    for reader in ("decision_maker", "recruiter"):
        for key in "abcdef":
            ask = compose.phrase("ask", reader, key)
            assert ask and compose._voice_ok(ask), (reader, ask)
            m = compose.inmail("Wren Halloway", how_found=FOUND, evidence="Cut error 12%.",
                               reader=reader, variant_key=key, opener="")
            assert "love to" not in m.body.lower()
    monkeypatch.setattr(advice, "_NET", None)
    assert "love to" not in advice.exit_fix().lower()


def test_a_note_is_checked_for_the_reader_it_was_written_for():
    import copy
    import pickle
    n = compose.first_note("Wren Halloway", how_found=FOUND, title="Director of Analytics",
                           about_me="")
    assert n.reader == "decision_maker"
    assert compose.validate(n, "connection", name="Wren Halloway") == []
    m = compose.inmail("Wren Halloway", how_found=FOUND, evidence="Cut error 12%.",
                       title="Director of Analytics", variant_key="x")
    assert compose.validate(m, "inmail") == []
    for x in (n, m):
        assert pickle.loads(pickle.dumps(x)) == x and copy.deepcopy(x) == x
    assert copy.deepcopy(m).subject == m.subject


def test_the_composers_own_how_found_line_is_never_a_claim_to_have_looked():
    for event in ("Northern Data Talk", "the Forecasting Panel", "Ops Keynote Night"):
        line = compose.how_found_line("event", event=event)
        note = compose.first_note("Wren Halloway", how_found=line, about_me="",
                                  ask="Would you have 15 minutes for a call?")
        assert line.split()[0] in note


def test_a_referrer_keeps_the_capital_of_their_name():
    line = compose.how_found_line("referral", referrer="Ana")
    note = compose.first_note("Wren Halloway", how_found=line, shape="brief",
                              title="Director of Analytics")
    assert "Hi Wren, Ana suggested" in note
    assert compose.first_note("Wren Halloway", how_found=FOUND, their=None)


def test_a_malformed_template_setting_never_breaks_drafting(monkeypatch):
    import types
    monkeypatch.setattr(advice, "_NET", types.SimpleNamespace(TEMPLATES={"any": ["a", "b"]}))
    advice.check("Hi Ana, hope you're well.", "connection")
    monkeypatch.setattr(advice, "_NET", types.SimpleNamespace(TEMPLATES=["a"]))
    advice.check("Hi Ana, hope you're well.", "connection")
    monkeypatch.setattr(compose, "TEMPLATES", {"any": ["a", "b"]})
    assert compose.phrase("ask", "peer", "k", fallback="Up for a call?") == "Up for a call?"


def test_a_pinned_skill_is_its_item_and_a_certificate_is_read_from_its_latex(monkeypatch):
    import types
    monkeypatch.setattr(advice, "_SKILLS", types.SimpleNamespace(PINNED=("bi", "Looker"),
                                                                 ITEMS=()))
    monkeypatch.setattr(advice, "_ROLES", types.SimpleNamespace(CERTIFICATIONS=(
        r"Acme Certified Data Engineer (2026) \textbullet{} A\kern0pt WX Certified ML "
        r"Engineer (2026) \textbullet{} dbt Analytics Engineering (in progress)")))
    assert advice.certification_names() == ["Acme Certified Data Engineer",
                                            "AWX Certified ML Engineer",
                                            "dbt Analytics Engineering"]
    names = [n for n, _rx in advice.credentials()]
    assert "Looker" in names and "bi" not in names
    assert not advice.without_purpose("We run a bi-weekly pricing review.")
    assert advice.without_purpose("I am AWX certified as well.")


def test_a_sentence_ends_after_an_acronym():
    assert tone.sentences("I was at QMX. I imagine that taught you a lot. J. Smith "
                          "agreed.") == ["I was at QMX.", "I imagine that taught you a lot.",
                                         "J. Smith agreed."]


def test_the_persons_own_lines_are_not_a_shared_shape(monkeypatch):
    monkeypatch.setattr(compose, "ABOUT_ME", "I work in supply-chain analytics in Manchester")
    monkeypatch.setattr(compose, "ASK", "Would you have 15 minutes for a few questions sometime")
    a = compose.first_note("Ana Rook", "We both worked at Oakmere Foods", their=("Oakmere",))
    b = compose.first_note("Bo Venn", "We both went to Leeds", their=("Leeds",))
    assert compose.alike({"a": a, "b": b}) == []


def test_a_message_button_with_no_degree_read_spends_no_credit():
    import reading
    assert reading.channel_for({"reach": "message"}) == ""
    assert reading.channel_for({"reach": "message", "degree": "2nd"}) == "inmail"


@pytest.mark.parametrize("text", [
    "I want to understand how your role changed.",
    "I want to hear more. Your role sounds broad.",
    "I'm interested in your move from finance into a product role.",
    "I like to apply statistics to depot planning.",
    "They are slow hiring at the moment.",
])
def test_ordinary_peer_sentences_are_not_job_asks(text):
    assert not compose.JOB_ASK.search(text)


@pytest.mark.parametrize("text", [
    "I want a senior forecasting role.", "I want to move into a product role.",
    "I'd love to apply for it.", "Is Larkspur hiring?", "I'm interested in the analyst role.",
])
def test_the_job_asks_are_still_found(text):
    assert compose.JOB_ASK.search(text)


def test_a_spoken_rewrite_that_lowers_an_opening_word_or_has_an_accent_is_read_right():
    orig = "Hi Éloïse, we both worked at Oakmere. Curious how you found the move?"
    assert compose.read_aloud(orig, orig.replace("Curious", "I'm curious"))["ok"]
    res = compose.read_aloud(orig, orig.replace("Éloïse", "Élodie"))
    assert "Éloïse" in res["lost"] and "Élodie" in res["added"]


def test_settings_written_as_words_or_strings_are_read_as_meant():
    assert compose._per_reader({"peer": "no", "recruiter": "yes"},
                               {"recruiter": False, "decision_maker": True, "peer": True}) == \
        {"recruiter": True, "decision_maker": True, "peer": False}
    assert compose._per_reader({"peer": "130"}, {"peer": 100})["peer"] == 130
    assert compose._as("two hundred", 220) == 220
