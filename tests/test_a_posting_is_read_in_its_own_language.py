"""A posting is read in the language it is written in, for any person, in any market.

Three findings with one cause: the screen read postings with English words only, and only
the languages one person's market raised.

- A language the person does not hold, stated as a requirement, is a hard cut. The built-in
  list left out French and about fifteen others, so "Fluent French required" reached an
  English speaker's shortlist at a score of 74, and a posting written in French with "Français
  courant exigé" was ranked tenth. A title written in a language the person does not hold
  was cut only where the profile set TITLE_LANGUAGE, which setup never wrote.
- Pay, years, the terms and a required language written in German, French, Spanish,
  Portuguese, Italian, Dutch, Polish or Swedish were read as stating nothing: no pay cut, no
  pay points, no years flag, and no fixed-term question before drafting.
- Pay stated by the month was read as a year's, so "R$ 4.500 - 5.500 per month" was hard-cut
  as "a different job level" and the ruling kept for good. A month is now read as one, and a
  pay ruling the screen made on a monthly band is released on the next round by itself.

A row already shortlisted under the older screen is caught where it matters: staging reads
its body with today's screen and asks before anything is drafted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import posting_profile  # noqa: E402
import text_screen as T  # noqa: E402

BODY = " You will plan campaigns and report their results to the marketing lead." * 8


def cut(sentence):
    m = T.other_language_cut(sentence)
    return m.group(0) if m else None


# ------------------------------------------------------------------ languages (X-16)

@pytest.mark.parametrize("sentence", [
    "Fluent French required.", "French is required for this role.",
    "Fluency in Swedish is required.", "Native-level Danish required.",
    "Fluent Norwegian required.", "Fluent Finnish required.", "Fluent Greek required.",
    "Fluent Thai required.", "Fluent Malay required.", "Fluent Tamil required.",
    "Fluent Bengali required.", "Fluent Irish required.",
    "Fluent Czech required.", "Fluent Hungarian required.", "Fluent Romanian required.",
    "Fluent Afrikaans required.", "Fluent Indonesian required.",
])
def test_every_language_the_person_does_not_hold_is_a_cut(sentence):
    assert cut(sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Fließende Französischkenntnisse erforderlich.",
    "Français courant exigé.",
    "Spanischkenntnisse zwingend erforderlich.",
    "Se requiere francés fluido.",
    "Inglês e francês fluentes obrigatórios.",
    "Conoscenza fluente del francese richiesta.",
    "Vloeiend Frans is vereist.",
])
def test_a_requirement_in_the_postings_own_language_is_a_cut(sentence):
    assert cut(sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Experience with French markets is required.",
    "Französischkenntnisse von Vorteil.",
    "La maîtrise de l'espagnol est un atout.",
    "Bilingual French is a plus.",
    "Wohnsitz in Deutschland erforderlich.",
    "Fluent English required.",
    "Englischkenntnisse erforderlich.",
])
def test_a_market_a_plus_or_a_held_language_is_not(sentence):
    assert cut(sentence) is None, sentence


@pytest.mark.parametrize("title,language", [
    ("Responsable marketing CRM", "French"), ("Chargée de communication", "French"),
    ("Leiterin Strategischer Einkauf", "German"), ("Sachbearbeiter Buchhaltung", "German"),
    ("Analista de Marketing", "Spanish"), ("Desenvolvedor Backend", "Portuguese"),
    ("Medewerker Klantenservice", "Dutch"), ("Projektledare IT", "Swedish"),
])
def test_a_title_in_a_language_the_person_does_not_hold_is_cut(title, language):
    got = T.screen({"title": title, "desc": BODY, "company": "Kestrel Mutual"})
    assert any(c.startswith(f"job title is in {language}:") for c in got["cuts"]), got["cuts"]


@pytest.mark.parametrize("title", [
    "Email Marketing Manager", "Chef de Partie", "Sous Chef", "Data Analyst (m/w/d)",
    "Marketing Director", "Assistant Store Manager", "Barista", "Charge Nurse",
    "Commercial Analyst", "Employee Relations Advisor", "Technical Consultant",
])
def test_an_english_title_is_not(title):
    got = T.screen({"title": title, "desc": BODY, "company": "Larkspur Retail"})
    assert not any(c.startswith("job title is in") for c in got["cuts"]), got["cuts"]


def test_the_whole_posting_in_french_is_cut_once_for_its_language():
    job = {"title": "Responsable marketing CRM", "company": "Kestrel Mutual",
           "desc": "Nous recherchons un responsable marketing CRM. Français courant exigé." + BODY}
    got = T.screen(job)
    assert got["text_screen"] == "cut"
    assert sum("stated as a requirement" in c for c in got["cuts"]) == 1


# ------------------------------------------------------------------ pay, years, terms (X-17)

@pytest.fixture
def euro(monkeypatch):
    values, labelled = T.money_parser("€", "EUR")
    monkeypatch.setattr(T, "money_values", values)
    monkeypatch.setattr(T, "labelled_value", labelled)
    monkeypatch.setattr(T, "_BOUNDS", (15_000, 300_000))
    monkeypatch.setattr(T, "FOREIGN_CURRENCY", re.compile(r"\b(usd|gbp)\b", re.I))
    monkeypatch.setattr(T, "CUR", "€")
    monkeypatch.setattr(T, "ABSURD_SALARY", 80_000)
    monkeypatch.setattr(T, "SALARY_FLOOR", 90_000)


@pytest.mark.parametrize("text,band", [
    ("Gehalt: 60.000 - 75.000 € brutto/Jahr", (60_000, 75_000)),
    ("Gehalt: 60.000 € - 75.000 €", (60_000, 75_000)),
    ("Wir bieten ein Gehalt von 45.000 € bis 52.000 €.", (45_000, 52_000)),
    ("Salaire : entre 45 000 € et 55 000 € bruts annuels.", (45_000, 55_000)),
    ("Salario: 40.000 - 50.000 € brutos anuales.", (40_000, 50_000)),
    ("Salaris tussen €55.000 en €65.000 per jaar.", (55_000, 65_000)),
    ("Retribuzione annua lorda da 40.000 a 50.000 euro.", (40_000, 50_000)),
    ("Salary range: 70,000 - 85,000 EUR", (70_000, 85_000)),
])
def test_pay_in_the_postings_own_language_is_read(euro, text, band):
    assert T.salary_range(text)[:2] == band


def test_a_german_posting_under_the_cut_line_is_cut(euro):
    text = ("Leitung Einkauf. Wir bieten: ein Jahresgehalt von 50.000 - 60.000 € brutto. "
            "Sehr gute Französischkenntnisse zwingend erforderlich." + BODY)
    got = T.screen({"title": "Leitung Einkauf", "desc": text, "company": "Brennwerk"})
    assert any(c.startswith("stated range tops out at €60,000") for c in got["cuts"]), got
    assert any("stated as a requirement" in c for c in got["cuts"]), got


@pytest.mark.parametrize("text,years", [
    ("Mindestens 8 Jahre Berufserfahrung im CRM-Marketing.", 8),
    ("Sie bringen mindestens 5 Jahre Erfahrung im Einkauf mit.", 5),
    ("Vous justifiez d'au moins 5 ans d'expérience en marketing.", 5),
    ("Al menos 5 años de experiencia en marketing digital.", 5),
    ("Pelo menos 3 anos de experiência com CRM.", 3),
    ("Almeno 4 anni di esperienza nel ruolo.", 4),
    ("Minimaal 6 jaar ervaring als inkoper.", 6),
])
def test_a_years_bar_in_the_postings_own_language_is_read(text, years):
    assert T.stated_years(text)[0] == years


def test_a_german_posting_states_its_terms_pay_years_and_degree(euro):
    text = ("Die Stelle ist befristet auf 12 Monate. Mindestens 5 Jahre Berufserfahrung im "
            "Einkauf. Abgeschlossenes Masterstudium erforderlich. Gehalt: 55.000 - 65.000 € "
            "brutto/Jahr.")
    prof = posting_profile.read({"title": "Leitung Einkauf", "company": "Brennwerk"}, text)
    assert prof["terms"]["kind"] == "fixed-term" and prof["terms"]["months"] == 12
    assert (prof["pay"]["low"], prof["pay"]["high"]) == (55_000, 65_000)
    assert prof["years"]["asks"] == 5
    assert prof["degree"]["level"] == "a master's degree"
    assert any(q["id"] == "contract" for q in posting_profile.questions(prof, {}))


@pytest.mark.parametrize("text,kind", [
    ("Wir bieten eine unbefristete Festanstellung.", "permanent"),
    ("CDD de 6 mois, à pourvoir dès que possible.", "fixed-term"),
    ("Contrato indefinido a jornada completa.", "permanent"),
    ("Contratto a tempo determinato di 12 mesi.", "fixed-term"),
])
def test_the_terms_in_other_languages(text, kind):
    assert posting_profile.terms(text)["kind"] == kind


# ------------------------------------------------------------------ pay by the month (X-19)

@pytest.fixture
def reais(monkeypatch):
    values, labelled = T.money_parser("R$", "BRL")
    monkeypatch.setattr(T, "money_values", values)
    monkeypatch.setattr(T, "labelled_value", labelled)
    monkeypatch.setattr(T, "_BOUNDS", (1_000, 1_000_000))
    monkeypatch.setattr(T, "FOREIGN_CURRENCY", re.compile(r"\b(usd)\b", re.I))
    monkeypatch.setattr(T, "CUR", "R$")
    monkeypatch.setattr(T, "ABSURD_SALARY", 30_000)
    monkeypatch.setattr(T, "SALARY_FLOOR", 42_000)


@pytest.mark.parametrize("text,band", [
    ("Salary: R$ 4.500 - 5.500 per month, plus benefits.", (54_000, 66_000)),
    ("Salário: R$ 4.500 a R$ 5.500 por mês.", (54_000, 66_000)),
    ("Monthly salary: BRL 11,000 to 15,000.", (132_000, 180_000)),
    ("Salary: R$ 4.500/month", (54_000, 54_000)),
    ("Salary: R$ 60.000 - 72.000 per year.", (60_000, 72_000)),
])
def test_a_monthly_band_is_read_as_a_years_pay(reais, text, band):
    got = T.salary_range(text)[:2]
    assert got == band if band[0] != band[1] else got[1] == band[1]


def test_a_monthly_band_is_never_cut_as_a_different_job_level(reais):
    job = {"title": "Staff Nurse", "company": "Kestrel Mutual", "location": "Recife",
           "desc": "Staff Nurse (ICU), Recife. Salary: R$ 4.500 - 5.500 per month, plus benefits."
                   + BODY}
    assert not any(c.startswith("stated range tops out") for c in T.screen(job)["cuts"])


def test_a_pay_ruling_made_on_a_monthly_band_is_released_by_itself(reais):
    monthly = ('stated range tops out at R$5,500, below R$30,000: a different job level, not a '
               'negotiation: "Salary: R$ 4.500 - 5.500 per month, plus benefits."')
    yearly = ('stated range tops out at R$25,000, below R$30,000: a different job level, not a '
              'negotiation: "Salary: R$ 20.000 - 25.000 per year."')
    assert T.ruling_refused(monthly)
    assert not T.ruling_refused(yearly)


# ------------------------------------------------------------------ a row already listed

def test_staging_asks_before_drafting_what_todays_screen_cuts():
    text = "Email Marketing Manager. Fluent French required to manage our Quebec campaigns." + BODY
    row = {"title": "Email Marketing Manager", "company": "Larkspur Retail"}
    prof = posting_profile.read(row, text)
    asks = [q for q in posting_profile.questions(prof, row) if q["id"] == "screen"]
    assert asks and "French" in asks[0]["question"]
    plain = posting_profile.read(row, "Email Marketing Manager." + BODY)
    assert not [q for q in posting_profile.questions(plain, row) if q["id"] == "screen"]


# ------------------------------------------------------------------ a person who holds German

def test_a_german_speaker_is_cut_for_french_never_for_german(tmp_path):
    profile = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), profile)
    search = profile / "search.py"
    search.write_text(search.read_text(encoding="utf-8")
                      + '\nLANGUAGES_HELD = ("german", "english")\n', encoding="utf-8")
    code = (
        "import json, sys; sys.path.insert(0, 'tools'); import text_screen as T\n"
        "s = ['Deutschkenntnisse erforderlich.', 'Fluent German required.',"
        " 'Französischkenntnisse zwingend erforderlich.', 'Fluent English required.']\n"
        "t = ['Leiter Einkauf', 'Responsable achats']\n"
        "body = ' Sie planen den Einkauf und berichten an die Leitung.' * 8\n"
        "print(json.dumps([bool(T.other_language_cut(x)) for x in s]"
        " + [bool([c for c in T.screen({'title': x, 'desc': body})['cuts']"
        " if c.startswith('job title is in')]) for x in t]))\n")
    env = dict(os.environ, LJS_PROFILE=str(profile))
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [False, False, True, False, False, True]
