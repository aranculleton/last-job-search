"""OpenAlex as an optional discovery source: offline, on invented records."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "network"))
import openalex  # noqa: E402

INST = {"results": [
    {"id": "https://openalex.org/I2", "display_name": "Kestrel Mutual Research Trust",
     "type": "nonprofit", "country_code": "GB"},
    {"id": "https://openalex.org/I1", "display_name": "Kestrel Mutual", "type": "company",
     "country_code": "GB"},
    {"id": "https://openalex.org/I9", "display_name": "Kestrel Mutual Inc", "type": "company",
     "country_code": "US"}]}
WORKS = {"results": [
    {"id": "https://openalex.org/W1", "title": "Explaining pricing models to underwriters",
     "publication_date": "2026-05-02", "authorships": [
         {"author": {"display_name": "Rosalind Achterberg", "orcid": ""},
          "institutions": [{"id": "https://openalex.org/I1"}]},
         {"author": {"display_name": "Corwin Haldane"},
          "institutions": [{"id": "https://openalex.org/I77"}]}]},
    {"id": "https://openalex.org/W2", "title": "An older paper", "publication_date": "2025-11-01",
     "authorships": [{"author": {"display_name": "Rosalind Achterberg"},
                      "institutions": [{"id": "https://openalex.org/I1"}]}]}]}


def fake(calls):
    def fetch(path, params):
        calls.append((path, params))
        return INST if path == "institutions" else WORKS
    return fetch


def test_the_employer_in_their_country_and_only_its_own_authors():
    calls = []
    out = openalex.people_at("Kestrel Mutual", "GB", today=datetime.date(2026, 10, 17),
                             fetch=fake(calls))
    assert out["institution"]["id"].endswith("I1")          # the company, in their country
    assert [p["name"] for p in out["people"]] == ["Rosalind Achterberg"]   # once, newest paper
    assert out["people"][0]["text"] == "Explaining pricing models to underwriters"
    assert "authorships.institutions.id:I1,from_publication_date:2024-10-17" in calls[1][1]["filter"]


def test_it_is_off_unless_the_profile_turns_it_on(capsys):
    assert openalex.ENABLED is False                         # the example person's field
    assert openalex.main(["Kestrel Mutual"]) == 0
    assert "off" in capsys.readouterr().out


def test_a_spent_allowance_says_what_would_fix_it(monkeypatch):
    import urllib.error
    import urllib.request

    def refuse(*a, **k):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.delenv(openalex.KEY_ENV, raising=False)
    try:
        openalex.institution("Kestrel Mutual")
    except openalex.OpenAlexError as e:
        assert openalex.KEY_ENV in str(e)
    else:
        raise AssertionError("a 429 must raise")
