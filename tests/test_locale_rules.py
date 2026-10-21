"""One copy of the document-language rules and one voice filter, read by every reader.

The dash, spelling and document-noun rules were written four times (check_claims,
tone, voice_check, audit_letters) and the copies disagreed; the hard-finding filter
was written four times (three in compose, one in outreach); the banned phrases were
two lists. Each test below pins one rule, one disagreement and how it was settled,
or one filter's exemptions as they were before there was one filter. The voice filter's
moved on 2026-10-20: a light "hope" is lifted in every follow-up, and what tone.check()
reports is not reported again, and the outreach check is validate() for a "message".
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import audit_letters  # noqa: E402
import check_claims  # noqa: E402
import compose  # noqa: E402
import locale_rules  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import tone  # noqa: E402
import voice_check  # noqa: E402

EM, EN = chr(0x2014), chr(0x2013)
CANADIAN = locale_rules.for_documents({"spelling": "canadian", "noun": "resume",
                                       "banned_nouns": ["CV"]})
AMERICAN = locale_rules.for_documents({"spelling": "american"})
BRITISH = locale_rules.for_documents({"spelling": "british", "noun": "CV",
                                      "banned_nouns": ["resume"]})
AUSTRALIAN = locale_rules.for_documents({"spelling": "australian"})


def spelt(locale, text, **kw):
    return [m.group(0) for _, m in locale.wrong_spellings(text, **kw)]


def rules(text, **kw):
    return {v.rule for v in tone.check(text, **kw)}


def claims(tex):
    """check_claims' findings on a LaTeX fragment, by rule name."""
    text = check_claims.strip_latex(tex)
    return [name for _, name, pat, _ in check_claims.CHECKS
            for _ in re.finditer(pat, text, re.I | re.S)]


# ------------------------------------------------------------------ dashes

def test_both_dash_characters_and_a_typed_dash_are_found():
    found = [r for r, _ in locale_rules.LOCALE.dashes(
        f"one {EM} two {EN} three -- four---five quality-- the rest")]
    assert found == ["em_dash", "en_dash", "em_dash", "em_dash", "em_dash"]


def test_furniture_and_links_are_not_dashes():
    # tone's handling, kept: a signature delimiter and a flag; and two it lacked,
    # a Markdown table's rule line and a profile id inside a link.
    L = locale_rules.LOCALE
    assert L.dashes("Thanks,\n-- \nMorgan") == []
    assert L.dashes("run it with --today") == []
    assert L.dashes("| Who | Why |\n|---|:--|\n| Tamsin | Leeds |") == []
    assert L.dashes("https://example.com/in/ACoAAB--x9 is the profile") == []
    assert L.dashes("the work -- and the rest") != []


def test_the_profile_decides_which_dashes_are_banned():
    # voice_check banned both whatever the profile said; check_claims only the em.
    only_em = locale_rules.for_documents({"banned_characters": [EM]})
    assert [r for r, _ in only_em.dashes(f"2019 {EN} 2021, and {EM} this")] == ["em_dash"]
    assert locale_rules.for_documents({"banned_characters": []}).dashes(f"a {EM} b -- c") == []
    assert voice_check.RULES[[r[0] for r in voice_check.RULES].index("em-dash")][2].pattern \
        == locale_rules.LOCALE.dash_pattern


def test_documents_catch_the_en_dash_and_latex_dashes():
    # check_claims flagged U+2014 alone, so an en dash, "--", "---" and
    # \textemdash all reached a resume unflagged.
    for tex in (f"Led the work {EN} all of it.", r"Led the work -- all of it.",
                r"Led the work --- all of it.", r"Led the work\textemdash{}all of it.",
                r"Jan 2023--Jan 2025"):
        assert "em-dash" in claims(tex), tex


def test_a_comment_or_a_link_address_in_latex_is_not_prose():
    assert "em-dash" not in claims(r"\item Built the model. % --- note to self")
    assert "em-dash" not in claims(r"\href{https://example.com/a--b}{Portfolio}")
    assert "em-dash" in claims(r"\item Built the model -- twice. 40\% faster")


def test_voice_check_and_tone_agree_on_a_typed_dash():
    for text in ("The Leeds team -- the payments one -- is close.", "Half the work--maybe more."):
        assert "em_dash" in rules(text)
        assert any(f["rule"] == "em-dash" for f in voice_check.check(text))
    for text in ("Thanks,\n-- \nMorgan", "| a | b |\n|---|---|"):
        assert "em_dash" not in rules(text)
        assert not any(f["rule"] == "em-dash" for f in voice_check.check(text))


# ------------------------------------------------------------------ spelling

def test_canadian_flags_british_and_american_forms_alike():
    assert spelt(CANADIAN, "I organised it, analysed it and ran the programme whilst there") \
        == ["organised", "analysed", "programme", "whilst"]
    assert spelt(CANADIAN, "behavior modeling at the center") == ["behavior", "modeling", "center"]
    assert spelt(CANADIAN, "behaviour modelling at the centre, organized and analyzed") == []


def test_analyses_is_a_noun_in_every_variety():
    for locale in (CANADIAN, AMERICAN, BRITISH, AUSTRALIAN):
        assert spelt(locale, "I ran sensitivity analyses") == []
    assert spelt(CANADIAN, "the team analysed the data") == ["analysed"]   # tone had it, check_claims did not


def test_american_flags_the_british_forms():
    assert spelt(AMERICAN, "behaviour and colour, organised, analysing") \
        == ["organised", "analysing", "behaviour", "colour"]
    assert spelt(AMERICAN, "behavior and color, organized") == []


def test_british_messages_are_checked_now():
    # tone checked only Canadian and American spelling, so a British person's
    # messages were never checked for "behavior" or "-ize".
    assert spelt(BRITISH, "I organized the behavior data and analyzed the centers") \
        == ["organized", "behavior", "analyzed", "centers"]
    assert spelt(BRITISH, "I organised the behaviour data and analysed it") == []
    # The -ize list is closed, so a word with only the one spelling never fires.
    assert spelt(BRITISH, "the size of the prize, seized") == []
    assert "american_spelling" in rules("I organized the behavior data.")   # the example is British


def test_australian_takes_the_plurals_british_does():
    # check_claims' Australian pattern had no plurals: "behaviors" and "centers" passed.
    assert spelt(AUSTRALIAN, "behaviors and centers, colors") == ["behaviors", "centers", "colors"]


def test_the_ise_exceptions_hold_and_cover_their_prefixed_forms():
    for word in ("enterprise", "expertise", "comprising", "supervises", "otherwise",
                 "unsupervised", "imprecise", "pairwise", "stepwise", "advertising"):
        assert spelt(CANADIAN, f"the {word} work") == [], word


def test_a_profiles_own_ise_names_are_spared():
    own = locale_rules.for_documents({"spelling": "canadian"}, ["saltmarshise"])
    assert spelt(own, "the Saltmarshise team") == []
    assert spelt(CANADIAN, "the saltmarshise team") == ["saltmarshise"]


def test_a_message_spares_names_and_quotations_a_resume_does_not():
    text = "Hi Tamsin, Xpertise Recruitment said 'behavioral pricing' was the focus."
    assert spelt(CANADIAN, text, theirs=True) == []
    assert spelt(CANADIAN, text) == ["Xpertise", "behavioral"]
    assert spelt(CANADIAN, "Skills: SQL, Data Visualisation", theirs=False) == ["Visualisation"]
    assert spelt(CANADIAN, "Analysed the data. It's behavioral.", theirs=True) \
        == ["Analysed", "behavioral"]


def test_no_spelling_set_means_no_spelling_rule():
    assert spelt(locale_rules.for_documents({}), "organised behavior") == []


# ------------------------------------------------------------------ the document noun

def test_the_banned_noun_in_documents_and_in_messages():
    n = BRITISH.nouns[0]
    for text in ("My resume is attached", "Morgan_Ellis_Resume_Oakmere.pdf", "the résumé"):
        assert n.document.search(text), text
    assert n.message.search("my resume is attached") and n.message.search("x_Resume_y")
    assert not n.message.search("happy to resume the conversation")
    cv = CANADIAN.nouns[0]
    for text in ("my CV", "Morgan_CV_Acme.pdf", "two CVs"):
        assert cv.document.search(text) and cv.message.search(text), text
    assert not cv.document.search("see cv/main.tex")


def test_every_reader_takes_the_noun_from_one_place():
    assert "document_noun" in rules("My resume is attached.")
    assert "the-word-resume" in claims("Please find my resume attached.")
    assert audit_letters.page_flags("I attach my resume.") == ["says resume"]
    assert audit_letters.page_flags(f"Leeds {EN} Manchester") == ["dash"]
    assert audit_letters.page_flags("Kind regards, Morgan") == []


def test_check_claims_keeps_the_names_profiles_place():
    names = [n for _, n, _, _ in check_claims.CHECKS]
    for name in ("em-dash", "the-word-resume", "british-spelling"):
        assert name in names
    assert "british-spelling" in claims("Analyzed the behavior data.")


def test_no_profile_is_the_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv(person.ENV, str(tmp_path / "nobody"))
    person.reset()
    try:
        L = locale_rules._from_profile()
        assert L.banned_characters == (EM, EN) and L.ise is None and L.variant is None
    finally:
        monkeypatch.undo()
        person.reset()


# ------------------------------------------------------------------ the phrases

def test_tone_and_voice_check_read_one_phrase_list():
    assert set(tone.BANNED_PHRASES) <= set(voice_check.PHRASES) | set(tone._MESSAGE_ONLY)
    for text in ("We moved the needle.", "There are synergies here.", "I am leveraging my SQL.",
                 "I am passionate about forecasting.", "A real team player.",
                 "Happy to circle back.", "Your point resonated with me."):
        assert "banned_phrase" in rules(text), text
        assert any(f["rule"] == "cliche" for f in voice_check.check(text)), text


def test_what_only_a_message_does_wrong_stays_in_messages():
    for text in ("Is Oakmere hiring on the data side?", "Leveraging the same tooling."):
        assert "banned_phrase" in rules(text)
        assert not any(f["rule"] == "cliche" for f in voice_check.check(text))
    # "leverage my" is both; the message reports it once.
    assert [v.text for v in tone.check("I would leverage my SQL.") if v.rule == "banned_phrase"] \
        == ["leverage"]


def test_at_scale_is_padding_only_without_a_number_in_both():
    assert any(f["match"] == "at scale" for f in voice_check.check("Built pipelines at scale."))
    assert not any(f["match"] == "at scale"
                   for f in voice_check.check("Built pipelines at scale across 2,400 SKUs."))
    assert "banned_phrase" in rules("Built pipelines at scale.")


# ------------------------------------------------------------------ the voice filter

SAMPLES = (
    "Hi Tamsin, hope you're well. I would love to hear how the Leeds team is set up.",
    "Hi Tamsin, hope the week has been a good one. Would love a chat.",
    "Hope you're well. Any update on the timing?",
    "I hope this message finds you well. I am passionate about data.",
    f"Thanks, that is useful {EM} I will send it over.",
    "Quick one: I'd love to connect and I would welcome the chance to talk.",
    "Your forecasting work came up at Brindle & Hart, where I ran the weekly numbers.",
)


def _old_hard(text):
    return [f for f in voice_check.check(text) if f["severity"] == "hard"]


def _old_lift(found, pattern):
    return [f for f in found if not (f["rule"] == "house-style" and pattern.match(f["match"]))]


# What tone.check() reports under its own names (a banned phrase, a dash, a phrase the
# person said never to use), and what that name is there.
TONE_NAME = {"cliche": "banned_phrase", "em-dash": "em_dash", "person-dislikes": "person_dislikes"}


def _voice_findings_now(text, kind):
    """What validate()'s voice filter returns, as of 2026-10-21: the person's own words
    (OWN_VOICE, and the stock phrases inside their OPENER and ASK) lifted in every kind of
    message, where 2026-10-20 lifted them in a connection note and an InMail only; a light
    "hope" lifted in every follow-up besides; and nothing tone.check() already reports, so no
    finding comes back twice."""
    hard = _old_hard(text)
    if kind:
        hard = [f for f in hard if not (f["rule"] == "house-style"
                                        and compose.own_words().match(f["match"]))]
    if kind in ("reply", "referral_ask", "nudge", "email", "intro", "intro_connection"):
        hard = _old_lift(hard, compose._THREAD_WARMTH)
    return [f for f in hard if f["rule"] not in TONE_NAME]


def _raised(fn, *args):
    try:
        fn(*args)
    except compose.ReadsAsGenerated as e:
        return str(e)
    return None


def test_hard_lifts_only_a_house_style_finding_allow_matches():
    text = "Hi Tamsin, hope you're well. I am passionate about data."
    assert voice_check.hard(text) == _old_hard(text)
    allow = re.compile(r"^(?:hope you'?re well|passionate about)", re.I)
    kept = {f["match"] for f in voice_check.hard(text, allow=allow)}
    assert "hope you're well" not in kept and "passionate about" in kept


@pytest.mark.parametrize("text", SAMPLES)
def test_the_composers_refuse_what_they_refused(text):
    old = _old_hard(text)
    expected = (None if not old else "connection note reads as generated: %s. %s" % (
        "; ".join(sorted({f["match"] for f in old}))[:160], old[0]["fix"]))
    assert _raised(compose._voice, "connection note", text) == expected
    old = _old_lift(_old_hard(text), compose._OWN_VOICE)
    expected = (None if not old else "first note reads as generated: %s. %s" % (
        "; ".join(sorted({f["match"] for f in old}))[:160], old[0]["fix"]))
    assert _raised(compose._first_note_voice, text) == expected


@pytest.mark.parametrize("text", SAMPLES)
@pytest.mark.parametrize("kind", ["connection", "inmail", "reply", "referral_ask", "email",
                                  "nudge", "intro", "message", None])
def test_validate_lifts_what_it_lifted(text, kind):
    assert compose._voice_findings(text, kind) == _voice_findings_now(text, kind)
    # And nothing voice_check finds is lost: tone reports the rest under its own name.
    vk = kind or "connection"
    got = compose.validate(text, vk, _all=True)
    found = {v.rule for v in got} | {compose._check_of(v) for v in got}
    for f in _voice_findings_now(text, vk):
        assert TONE_NAME.get(f["rule"], f["rule"]) in found, (f, found)


def test_the_exemptions_are_the_ones_each_filter_had():
    first = "Hi Tamsin, hope you're well. Would love to hear how it is going."
    assert compose._voice_findings(first, "connection") == []
    # Changed 2026-10-21: "would love to" is the person's own (OWN_VOICE), so it is lifted in
    # every kind of message, an email too; a stock phrase that is not theirs is not.
    assert compose._voice_findings(first, "email") == []
    assert compose._voice_findings("Hi Tamsin, I would welcome the chance to talk.", "email")
    warm = "Hope you're well. Any update on the timing?"
    assert compose._voice_findings(warm, "reply") == []
    assert compose._voice_findings(warm, "connection") == []          # OWN_VOICE has it too
    assert compose._voice_findings("Hope the week went well. Any news?", "reply") == []
    assert compose._voice_findings("Hope the week went well. Any news?", "connection")


@pytest.mark.parametrize("text", SAMPLES)
def test_the_outreach_note_check_is_validate_for_a_message(text):
    # It ran tone.check and voice_check by hand, a subset of validate() (2026-10-20). It is
    # validate(kind="message") now, beside its own three checks, and it loses nothing the
    # old check caught: every tone finding, and every voice_check finding by its own name
    # or by the name tone reports it under.
    def own_checks(note):
        problems = []
        n = len(note.split())
        if n >= outreach.MAX_NOTE_WORDS:
            problems.append(f"{n} words; the most a note may carry is {outreach.MAX_NOTE_WORDS - 1}")
        if not outreach.CREDENTIAL.search(note):
            problems.append("names none of the candidate's employers, so it carries no credential")
        if len(outreach.APPLYING.findall(note)) > 1:
            problems.append("says it has applied more than once")
        return problems
    # Less one check: "Sam" stands in for a reader nobody has named, so a note greeting its
    # real reader ("Hi Tamsin") is not greeting the wrong person. greeting_wrong_name
    # (2026-10-21) is left to a call that knows the reader, and check_note skips it.
    gate = [f"{v.rule}: {v.text}" for v in compose.validate(
        text.replace("[name]", "Sam"), "message", name="Sam", seniority="senior",
        reader="decision_maker") if v.rule != "greeting_wrong_name"]
    got = outreach.check_note(text)
    assert got == own_checks(text) + gate
    rules_ = ({p.split(":", 1)[0] for p in got}
              | {p.split(":", 2)[1].strip() for p in got if p.startswith("reads_as_generated:")})
    assert {v.rule for v in tone.check(text, recipient_seniority="senior", name="Sam")
            if v.rule != "greeting_wrong_name"} <= rules_
    # Less the person's own words, lifted in every kind of message since 2026-10-21.
    for f in _voice_findings_now(text, "message") + [f for f in _old_hard(text)
                                                     if f["rule"] in TONE_NAME]:
        assert TONE_NAME.get(f["rule"], f["rule"]) in rules_, (f, rules_)
