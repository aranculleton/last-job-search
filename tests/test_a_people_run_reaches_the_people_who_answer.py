"""A people run reaches the people who answer, and keeps what it chose (2026-11-10).

From a "find 5 people at big employers" run in real use: it filled the
list with engineers and peers although recruiters and founders answer that person far more
often, and where an employer had no recruiter in the city it fell back on peers there rather
than trying the next employer; a head of the function with "Hiring" in the headline was
skipped because an earlier run had closed them; a re-check swapped a chosen person for one
whose headline reads as selling; `reading.py shortlist --remove <id>` emptied the whole
list; every employer was searched kind by kind, many of them empty; and `reading.py batch`
showed a likeness between two notes left over from earlier runs. Now:

- the ranking puts the kind of reader first by the person's own reply rates, then a hiring
  signal in the headline; peers fill only what is left once the hiring side at every
  employer has been tried, and the run says so (`candidates.check`);
- closed means closed by the person: a row an earlier run closed after a read is checked
  again by today's rules, and opened again when chosen (`state.closed_by_a_run`);
- a headline that reads as selling is out, and someone chosen before stays chosen;
- the short list is kept on the person's own day, and a removal takes off that one alone;
- `candidates.py order` puts first the employers with people known in the place and skips
  one an earlier check found empty there, for a while;
- `reading.py batch` says only what involves the run's own notes.

Made-up people only: a remote software engineer, a nurse in Vancouver, and a career changer
in Leeds.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import shutil
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def _own_talked_cache(monkeypatch):
    """reading.talked_with keeps what it read by the shared files' time and size, which these
    tests' own books bypass: a cache of their own, so a later test in the worker never reads
    one of these books' answers for the shared example (a follow-up test failed after them)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "tools", "network"))
    import reading
    monkeypatch.setattr(reading, "_TALKED", {})

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

_DAY = datetime.date.today()
TODAY = _DAY.isoformat()


def _profile(tmp_path, networking="", employers="", search=""):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    for name, extra in (("networking.py", networking), ("employers.py", employers),
                        ("search.py", search)):
        if extra:
            with open(d / name, "a", encoding="utf-8") as fh:
                fh.write("\n\nimport re\n" + extra + "\n")
    (tmp_path / "state").mkdir()
    return d


COLS = ["contact_id", "name", "company", "title", "location", "linkedin_url", "status",
        "first_contacted", "channel", "outcome", "notes"]


def _book(tmp_path, rows):
    with open(tmp_path / "state" / "network_contacts.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def _rows(tmp_path):
    with open(tmp_path / "state" / "network_contacts.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _env(tmp_path):
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "profile"),
               LJS_STATE=str(tmp_path / "state"), LJS_LEDGER=str(tmp_path / "ledger"),
               LJS_TODAY=TODAY, LJS_COPY="private")
    env.pop("CLAUDE_CODE_REMOTE", None)
    return env


def _cli(tmp_path, *args, ok=(0,)):
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network",
                                                       "candidates.py"), *args],
                         env=_env(tmp_path), capture_output=True, encoding="utf-8",
                         timeout=180)
    assert got.returncode in ok, got.stdout + got.stderr
    return got.stdout


def _check(tmp_path, people, *args):
    f = tmp_path / f"people{len(list(tmp_path.glob('people*.json')))}.json"
    f.write_text(json.dumps(people), encoding="utf-8")
    return _cli(tmp_path, "check", str(f), *args)


def _json(tmp_path, people, *args):
    return json.loads(_check(tmp_path, people, "--json", *args))


def _p(name, title, company, location="United Kingdom", slug=""):
    slug = slug or name.lower().replace(" ", "-")
    return {"name": name, "title": title, "company": company, "location": location,
            "linkedin_url": f"https://www.linkedin.com/in/{slug}-example"}


def _names(rows):
    return [r["name"] for r in rows]


# ---------------------------------------------------------------- a remote software engineer

ENG_NET = '''
HOME_CITY = ""
FUNCTION_TITLE = re.compile(r"\\b(software|engineer\\w*|developer|backend|frontend|platform|devops)\\b", re.I)
TITLE_SETS = {"hiring_authority": ["Engineering Manager", "Head of Engineering"],
              "senior_ic": ["Staff Software Engineer", "Principal Engineer"],
              "function": ["Software Engineer", "Backend Engineer"],
              "recruiting": ["Technical Recruiter"]}
REPLY_RATES = {"recruiter": (9, 15), "founder": (5, 7), "peer": (4, 120),
               "senior_peer": (1, 20)}
SKIP_HEADLINES = ["staffing agency"]
'''
ENG_EMP = 'TIER_1 = {"nimbus cloud", "larkspur systems", "thornbury games"}\n'


def test_peers_wait_while_another_employer_could_give_the_hiring_side(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [])
    people = [
        _p("Idris Corrie", "Software Engineer", "Nimbus Cloud"),
        _p("Hal Okonedo", "Backend Engineer", "Nimbus Cloud"),
        _p("Pip Varga", "Engineering Manager", "Nimbus Cloud"),
        _p("Nell Ashby", "Software Engineer", "Larkspur Systems"),
        _p("Odo Fenwick", "Staff Software Engineer", "Larkspur Systems"),
    ]
    got = _json(tmp_path, people, "--want", "4")
    # Only the hiring side is chosen; the peers wait while Thornbury Games is untried.
    assert _names(got["chosen"]) == ["Pip Varga"]
    assert set(got["peers_held"]) == {"Idris Corrie", "Hal Okonedo", "Nell Ashby", "Odo Fenwick"}
    assert [e.lower() for e in got["next_employers"]] == ["thornbury games"]
    assert got["no_hiring_side"] == ["Larkspur Systems"]
    text = _check(tmp_path, people, "--want", "4")
    assert "peers held back: 4" in text and "thornbury games" in text.lower()
    assert "none found at Larkspur Systems" in text and "--peers takes them now" in text
    # Once every employer has been tried, the peers fill what is left, and it says so.
    got = _json(tmp_path, people, "--want", "3", "--peers")
    assert got["chosen"][0]["name"] == "Pip Varga" and got["peers_filled"] == 2
    assert "peers: 2 of the list" in _check(tmp_path, people, "--want", "3", "--peers")


def test_the_kind_that_answers_comes_first_then_a_hiring_signal(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [])
    people = [
        _p("Bea Lowry", "Engineering Manager", "Larkspur Systems"),
        _p("Cal Strand", "Engineering Manager | We're hiring backend engineers",
           "Thornbury Games"),
        _p("Dee Marlow", "Technical Recruiter", "Nimbus Cloud"),
        _p("Eli Tamsett", "Founder", "Thornbury Games"),
    ]
    got = _json(tmp_path, people, "--want", "4")
    # Recruiters and founders answer this person most (REPLY_RATES): first, by kind; then the
    # hiring leader whose headline says they are hiring, before the one whose does not.
    kinds = [r["kind"] for r in got["chosen"]]
    assert kinds[:2] in (["recruiter", "founder"], ["founder", "recruiter"])
    assert _names(got["chosen"])[2:] == ["Cal Strand", "Bea Lowry"]
    assert "says they are hiring" in got["chosen"][2]["why"]


def test_a_headline_that_reads_as_selling_is_out(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [])
    people = [
        _p("Fen Arkwright", "Cloud & Platform in Nordic Retail Banking", "Nimbus Cloud"),
        _p("Gus Penrith", "Client Partner, Platform Engineering", "Nimbus Cloud"),
        _p("Ivo Calder", "Partnerships Lead | Developer Tools", "Larkspur Systems"),
        _p("Jem Rawle", "Helping banks modernise their platforms", "Larkspur Systems"),
        _p("Kit Sowerby", "Senior Software Engineer in Retail Banking", "Nimbus Cloud"),
        _p("Lyn Ottery", "Technical Recruiter, Staffing Agency", "Thornbury Games"),
    ]
    got = _json(tmp_path, people, "--want", "3", "--peers")
    out = {o["name"]: o["why"] for o in got["out"]}
    assert "reads as selling" in out["Fen Arkwright"]
    assert "sales" in out["Gus Penrith"]                  # the search rules already said so
    assert "partnerships" in out["Ivo Calder"].lower()
    assert "reads as selling" in out["Jem Rawle"]
    assert "never to show" in out["Lyn Ottery"]           # their own SKIP_HEADLINES
    assert _names(got["chosen"]) == ["Kit Sowerby"]


def test_a_sales_person_is_never_cut_for_selling():
    import candidates
    assert candidates.sales_reading("Account Executive, Mid-Market", own={"sales"}) == ""
    assert candidates.sales_reading("Sales Analytics Manager", own={"technology"}) == ""
    assert candidates.sales_reading("Software Engineer in Insurance",
                                    own={"technology"}) == ""
    assert candidates.sales_reading("Cloud & Platform in Nordic Insurance",
                                    own={"technology"})


def test_someone_chosen_is_never_swapped_for_someone_new(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [])
    first = [_p("Mae Holroyd", "Technical Recruiter", "Nimbus Cloud")]
    assert "1 chosen" in _check(tmp_path, first, "--want", "1", "--add", "--shortlist")
    # A later check with a new, higher-ranked person: the chosen one stays.
    again = first + [_p("Ned Coldwell", "Founder", "Quillstone Labs")]
    got = _json(tmp_path, again, "--want", "1")
    assert _names(got["chosen"]) == ["Mae Holroyd"] and got["kept"] == ["Mae Holroyd"]
    text = _check(tmp_path, again, "--want", "1")
    assert "kept, chosen before: Mae Holroyd" in text
    # Their headline no longer passing does not take them off either: it says so.
    changed = [_p("Mae Holroyd", "Account Executive", "Nimbus Cloud")]
    got = _json(tmp_path, changed, "--want", "1")
    assert _names(got["chosen"]) == ["Mae Holroyd"]
    assert any("chosen already" in w and "--remove" in w for w in got["chosen"][0]["warn"])


def test_closed_by_an_earlier_run_is_checked_again_closed_by_the_person_is_not(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "nimbus_quarrie", "name": "Ola Quarrie", "company": "Nimbus Cloud",
         "title": "Head of Engineering", "status": "closed",
         "linkedin_url": "https://www.linkedin.com/in/ola-quarrie-example",
         "outcome": "skipped after a read 2026-10-01: two already waiting there"},
        {"contact_id": "nimbus_rudd", "name": "Pia Rudd", "company": "Nimbus Cloud",
         "title": "Technical Recruiter", "status": "closed",
         "linkedin_url": "https://www.linkedin.com/in/pia-rudd-example",
         "outcome": "closed by the person: not for now"},
    ])
    people = [_p("Ola Quarrie", "Head of Engineering | Hiring", "Nimbus Cloud"),
              _p("Pia Rudd", "Technical Recruiter", "Nimbus Cloud")]
    got = _json(tmp_path, people, "--want", "2")
    assert _names(got["chosen"]) == ["Ola Quarrie"]
    assert any("an earlier run closed them on 2026-10-01" in w for w in got["chosen"][0]["warn"])
    assert "closed" in {o["name"]: o["why"] for o in got["out"]}["Pia Rudd"]
    text = _check(tmp_path, people, "--want", "2", "--add")
    assert "opened again: Ola Quarrie" in text
    rows = {r["contact_id"]: r for r in _rows(tmp_path)}
    assert rows["nimbus_quarrie"]["status"] == "not_contacted"
    assert rows["nimbus_rudd"]["status"] == "closed"
    assert len(rows) == 2                                   # never a second row


def test_the_state_helper_names_only_a_runs_own_close():
    import state
    run = {"status": "closed", "outcome": "skipped after a read 2026-10-01: in another city"}
    assert state.closed_by_a_run(run) == ("an earlier run closed them on 2026-10-01 "
                                          "(in another city)")
    assert state.closed_by_a_run(dict(run, notes="closed on purpose")) == ""
    assert state.closed_by_a_run(run, [{"direction": "outbound", "date": "2026-09-01"}]) == ""
    assert state.closed_by_a_run({"status": "closed", "outcome": "not interested"}) == ""


# ---------------------------------------------------------------- the first pass, a nurse

NURSE_NET = '''
HOME_CITY = "Vancouver"
FUNCTION_TITLE = re.compile(r"\\b(nurs\\w*|clinical|patient care|paediatric\\w*|pediatric\\w*)\\b", re.I)
TITLE_SETS = {"hiring_authority": ["Nurse Manager", "Director of Nursing"],
              "senior_ic": ["Clinical Nurse Specialist", "Charge Nurse"],
              "function": ["Registered Nurse", "Paediatric Nurse"],
              "recruiting": ["Nurse Recruiter", "Clinical Recruiter"]}
'''


def test_the_likely_employers_are_searched_first_and_empty_ones_wait(tmp_path):
    _profile(tmp_path, NURSE_NET)
    van = "Vancouver, British Columbia, Canada"
    _book(tmp_path, [
        {"contact_id": "coast_a", "name": "Ama Rhodes", "company": "Coastwell Health",
         "title": "Charge Nurse", "location": van, "status": "not_contacted"},
        {"contact_id": "fern_a", "name": "Bex Torrance", "company": "Fernlea Clinics",
         "title": "Registered Nurse", "location": "Halifax, Nova Scotia, Canada",
         "status": "not_contacted"},
    ])
    net = tmp_path / "state" / "documents" / "network"
    net.mkdir(parents=True)
    (net / ".search_filters.json").write_text(json.dumps(
        {"employers": {"harbourline care": {"name": "Harbourline Care",
                                            "currentCompany": '["12345"]'}}}))
    old = (_DAY - datetime.timedelta(days=40)).isoformat()
    recent = (_DAY - datetime.timedelta(days=5)).isoformat()
    (net / ".people_seen.json").write_text(json.dumps({
        "pinecrest hospital": {"vancouver": {"employer": "Pinecrest Hospital", "date": recent,
                                             "found": 6, "fit": 0}},
        "alder bay health": {"vancouver": {"employer": "Alder Bay Health", "date": old,
                                           "found": 4, "fit": 0}}}))
    names = ["Fernlea Clinics", "Pinecrest Hospital", "Harbourline Care", "Alder Bay Health",
             "Coastwell Health"]
    text = _cli(tmp_path, "order", *names, "--place", "Vancouver")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("next  Coastwell Health: 1 in your contact book there")
    assert lines[1].startswith("next  Harbourline Care: its company number is kept")
    # Nothing known: in the order given. Fernlea's one person is in another city.
    assert [ln.split(":")[0] for ln in lines[2:4]] == ["next  Fernlea Clinics",
                                                       "next  Alder Bay Health"]
    assert lines[4].startswith(f"skip  Pinecrest Hospital: searched {recent}: nobody who fits "
                               "in Vancouver")
    # The search leaves the empty one out and says so; --all searches it anyway.
    out = _cli(tmp_path, "search", "Pinecrest Hospital", "Harbourline Care", "--place",
               "Vancouver", ok=(0, 1))
    assert "Pinecrest Hospital: skipped" in out and "--all" in out
    # A check narrowed to an employer keeps what it found there, for the next run.
    _check(tmp_path, [_p("Cy Wardle", "Software Engineer", "Harbourline Care", van)],
           "--company", "Harbourline Care", "--place", "Vancouver")
    seen = json.loads((net / ".people_seen.json").read_text())
    assert seen["harbourline care"]["vancouver"]["fit"] == 0
    assert seen["harbourline care"]["vancouver"]["date"] == TODAY
    assert "skip  Harbourline Care" in _cli(tmp_path, "order", "Harbourline Care", "--place",
                                            "Vancouver")


# ---------------------------------------------------------------- the short list and the batch

@pytest.fixture
def here(tmp_path, monkeypatch):
    import reading
    import state
    state_dir = tmp_path / "chat_a"
    monkeypatch.setattr(reading.person, "state", lambda *p: str(state_dir.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts = [{"contact_id": f"p{i}", "name": f"Person {i}", "company": f"Firm {i}",
                 "location": "Leeds", "status": "not_contacted"} for i in range(4)]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: contacts)
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    return contacts


def test_removing_one_from_the_short_list_takes_off_that_one_alone(here, monkeypatch, capsys):
    import reading
    # The person's day is not the computer's: late at night in their own zone.
    theirs = datetime.date.today() + datetime.timedelta(days=1)
    monkeypatch.setattr(reading.person, "today", lambda *a, **k: theirs)
    got = reading.shortlist(["p0", "p1", "p2"], today=theirs, contacts=here)
    assert got["ids"] == ["p0", "p1", "p2"]
    assert reading.main(["shortlist", "--remove", "p1"]) == 0
    assert reading._shortlist_file(theirs) == ["p0", "p2"]
    assert "removed: p1" in capsys.readouterr().out
    # Removing someone who is not on it changes nothing at all.
    assert reading.main(["shortlist", "--remove", "p3"]) == 0
    assert reading._shortlist_file(theirs) == ["p0", "p2"]
    assert reading.on_shortlist("p0") and not reading.on_shortlist("p1")


def test_a_batch_is_shown_only_what_involves_its_own_notes(here, monkeypatch, capsys):
    import reading
    here[0]["company"] = here[1]["company"] = "Brackenmoor Freight"
    same = "I plan inbound loads for a regional grocer and keep its forecasts honest."
    reading.write_draft("p0", f"Hi Person, hope you're well. {same} Would love to compare notes.",
                        "Person 0")
    reading.write_draft("p1", f"Hi Person, good to see your team growing. {same} Happy to chat.",
                        "Person 1")
    reading.write_draft("p2", "Hi Person, I read your piece on cold-chain audits. I map supplier "
                        "lead times in Python. How does your team plan for winter?", "Person 2")
    reading.write_draft("p3", "Hi Person, congratulations on the new depot. I work on routing "
                        "for van fleets. What changed most since it opened?", "Person 3")
    # This run's notes are p2 and p3, on today's short list: the older likeness is not theirs.
    reading.shortlist(["p2", "p3"], today=reading.person.today(), contacts=here)
    capsys.readouterr()
    assert reading.main(["batch"]) == 0
    out = capsys.readouterr().out
    assert "2 queued note(s) checked, against 2 older one(s)" in out
    assert "p0" not in out and "p1" not in out
    # Named ids, the same: only what involves them.
    assert reading.main(["batch", "p2", "p3"]) == 0
    # A note of the run's own alike to an older one is still said.
    reading.write_draft("p3", f"Hi Person, congratulations on the new depot. {same} What "
                        "changed most since it opened?", "Person 3")
    here[3]["company"] = "Brackenmoor Freight"
    assert reading.main(["batch", "p2", "p3"]) == reading.EXIT["alike"]
    out = capsys.readouterr().out
    assert "p3" in out


# ---------------------------------------------------------------- every older book, by itself

def test_an_older_book_has_its_cold_conversations_closed_by_an_instant_upgrade(tmp_path):
    import profile_upgrades as U
    import schema
    up = next(u for u in U.REGISTRY if u.id == "threads-gone-cold")
    assert up.cost == "instant" and up.needs == "nobody"
    _profile(tmp_path)
    _book(tmp_path, [{"contact_id": "kestrel_vane", "name": "Rue Vane",
                      "company": "Kestrel Mutual", "status": "awaiting_reply",
                      "first_contacted": "2024-02-01"}])
    with open(tmp_path / "state" / "network_threads.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.THREAD_COLUMNS)
        w.writeheader()
        w.writerow({c: "" for c in schema.THREAD_COLUMNS} | {
            "contact_id": "kestrel_vane", "date": "2024-02-01", "direction": "outbound",
            "channel": "linkedin", "summary": "first note", "full_text": "Hello"})
    got = subprocess.run([sys.executable, os.path.join(ROOT, up.command[1]), *up.command[2:]],
                         env=_env(tmp_path), capture_output=True, encoding="utf-8", timeout=120)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "gone cold: 1 conversation(s)" in got.stdout
    row = _rows(tmp_path)[0]
    assert row["status"] == "gone_cold" and "closed by itself" in row["outcome"]
