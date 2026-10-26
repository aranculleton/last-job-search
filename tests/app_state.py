"""Invented state for the page engine's tests (tools/app.py): a small search and a large one.

Every person, employer and message here is invented. The small state is the example
person's own (profile.example/state) plus a round, its filtered list, two drafted
applications with their documents, an interview and a few drafts waiting to be sent. The
large one is built from short word lists at run time, so no name in it is written here.
"""
from __future__ import annotations

import csv
import json
import os
import random
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "profile.example")

TODAY = "2026-10-25"
NOW = "2026-10-25T18:00:00Z"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _json(path: str, data) -> None:
    _write(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def _pdf(path: str, pages: int) -> None:
    """A real PDF of `pages` blank pages, written by hand: any reader counts its pages."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [%s] /Count %d >>"
            % (" ".join(f"{n + 3} 0 R" for n in range(pages)), pages)]
    objs += ["<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"] * pages
    out, offsets = "%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj {body} endobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(out.encode("ascii"))


def _csv_rows(path: str):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _save_csv(path: str, rows, columns) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


TRACKER_COLUMNS = ["date", "company", "sector", "role", "role_type", "channel", "status",
                   "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
                   "source", "deadline", "applied_on", "confirmed_by", "confirmed_at"]


def profile_copy(dest: str) -> str:
    """A copy of the example person's profile a test may write to (settings, learned)."""
    shutil.copytree(EXAMPLE, dest, ignore=shutil.ignore_patterns("state", "tests",
                                                                  "__pycache__"))
    return dest


def small(state: str) -> str:
    """The example person's state plus everything the page shows, in `state`."""
    shutil.copytree(os.path.join(EXAMPLE, "state"), state, dirs_exist_ok=True)
    tracker = os.path.join(state, "job_search_tracker.csv")
    rows = _csv_rows(tracker)
    rows.append({"date": "2026-10-22", "company": "Kestrel Mutual", "sector": "Insurance",
                 "role": "Claims Forecasting Analyst", "role_type": "data",
                 "channel": "company site", "status": "drafted", "fit_rating": "81",
                 "notes": "r9. drafted from the round",
                 "cv_file": "cv/Morgan_Ellis_CV_Kestrel.tex",
                 "cover_letter_file": "cover_letters/Morgan_Ellis_Cover_Letter_Kestrel.tex",
                 "source": "https://jobs.example/kestrel/claims-forecasting"})
    rows.append({"date": "2026-10-19", "company": "Dovecote Freight", "sector": "Logistics",
                 "role": "Inventory Analyst", "role_type": "data", "channel": "company site",
                 "status": "drafted", "fit_rating": "66",
                 "notes": "2026-10-21: said applied via the portal",
                 "source": "https://jobs.example/dovecote/inventory"})
    rows.append({"date": "2026-10-01", "company": "Thornbury Bank", "sector": "Banking",
                 "role": "Risk Analyst", "role_type": "data", "channel": "company site",
                 "status": "interview", "fit_rating": "77",
                 "notes": "2026-10-20: phone screen went well",
                 "cv_file": "cv/Morgan_Ellis_CV_Thornbury.tex",
                 "cover_letter_file": "cover_letters/Morgan_Ellis_Cover_Letter_Thornbury.tex",
                 "source": "https://jobs.example/thornbury/risk", "applied_on": "2026-10-02",
                 "confirmed_by": "chat", "confirmed_at": "2026-10-02 09:00"})
    _save_csv(tracker, rows, TRACKER_COLUMNS)

    apps = os.path.join(state, "documents", "applications")
    kestrel = os.path.join(apps, "kestrel_mutual_claims_forecasting_analyst_kestrel")
    _json(os.path.join(kestrel, "draft.json"), [{
        "company": "Kestrel Mutual", "role": "Claims Forecasting Analyst", "abbr": "Kestrel",
        "location": "Manchester", "salary": "GBP 42,000 to 48,000",
        "url": "https://jobs.example/kestrel/claims-forecasting"}])
    _write(os.path.join(kestrel, "outreach.md"),
           "# Outreach note - Kestrel Mutual, Claims Forecasting Analyst\n\n"
           "Send to the hiring manager or the recruiter named on the posting, the same day as "
           "the application. Replace [name]. Do not attach anything.\n\n---\n\n"
           "Hi [name], I have applied for the Claims Forecasting Analyst role. I build weekly "
           "forecasts in Python and SQL for operations teams in Manchester.\n\n---\n\n"
           "Words: 24. Characters: 160.\n")
    _write(os.path.join(kestrel, "screening_answers.md"),
           "# Screening answers: Claims Forecasting Analyst at Kestrel Mutual\n\n"
           "### Do you have the right to work in the UK?\n\n**Yes**\n\nA note.\n\n"
           "### Will you now or in future need sponsorship?\n\n**No**\n\nA note.\n\n---\n")
    _pdf(os.path.join(state, "cv", "Morgan_Ellis_CV_Kestrel.pdf"), 1)
    _pdf(os.path.join(state, "cover_letters", "Morgan_Ellis_Cover_Letter_Kestrel.pdf"), 1)

    thornbury = os.path.join(apps, "thornbury_bank_risk_analyst_thornbury")
    _write(os.path.join(thornbury, "outcome.md"),
           "# Outcome\n\n## Interview stages reached\n\n"
           "- [x] Phone screen (2026-10-15, with the recruiter)\n"
           "- [ ] Panel interview (scheduled 2026-10-28, with the head of risk)\n")
    _write(os.path.join(thornbury, "interview_prep.md"),
           "# Interview prep\n\n<!-- stages: Panel interview -->\n\n"
           "- **Q.** Tell me about a forecast you built (screen; source: posting)\n"
           "- **Q.** How do you check your data (screen; source: posting)\n")

    rounds = os.path.join(state, "documents", "rounds")
    _json(os.path.join(rounds, "r9.json"), [
        {"priority": 88, "fit": 84, "title": "Demand Planning Analyst",
         "company": "Brindle Hart Logistics", "location": "Manchester (hybrid)",
         "url": "https://jobs.example/brindle/demand", "portal": "linkedin", "bar": "pay"},
        {"priority": 80, "fit": 81, "title": "Claims Forecasting Analyst",
         "company": "Kestrel Mutual", "location": "Manchester",
         "url": "https://jobs.example/kestrel/claims-forecasting", "portal": "employer"},
        {"priority": 70, "fit": 66, "title": "Inventory Analyst", "company": "Dovecote Freight",
         "location": "Remote, UK", "url": "https://jobs.example/dovecote/inventory",
         "portal": "freehire", "warm_route_note": "DO NOT APPLY COLD: someone you know"},
        {"priority": 61, "fit": 62, "title": "Supply Analyst", "company": "Larkspur Retail",
         "location": "Leeds", "url": "https://jobs.example/larkspur/supply",
         "portal": "linkedin"},
    ])
    _write(os.path.join(rounds, "filtered", "r9.json"),
           json.dumps({"round": "r9", "counts": {"location": 2, "screen": 1}})[:-1]
           + ', "filtered": [\n'
           + ",\n".join(json.dumps(e) for e in (
               {"title": "Data Analyst", "company": "Quayside Foods", "location": "London",
                "url": "https://jobs.example/quayside/1", "stage": "search", "rule": "location",
                "reason": "location: on-site outside Greater Manchester (london)"},
               {"title": "Planner", "company": "Quayside Foods", "location": "Bristol",
                "url": "https://jobs.example/quayside/2", "stage": "search", "rule": "location",
                "reason": "location: on-site outside Greater Manchester (bristol)"},
               {"title": "Inventory Lead", "company": "Dovecote Freight",
                "url": "https://jobs.example/dovecote/lead", "stage": "screen",
                "rule": "screen", "reason": "professional designation stated as a requirement"},
           )) + "\n]}\n")

    # A first note waiting to be sent, to someone the book holds with an email and a phone:
    # the page may show the note, never the address or the number.
    contacts = os.path.join(state, "network_contacts.csv")
    crows = _csv_rows(contacts)
    columns = list(crows[0].keys())
    crows.append(dict.fromkeys(columns, "") | {
        "contact_id": "kestrel_mutual_ansgar", "name": "Pell Ansgar",
        "title": "Claims Analytics Lead", "company": "Kestrel Mutual",
        "company_key": "kestrel mutual", "location": "Manchester",
        "linkedin_url": "https://www.linkedin.com/in/example-pell-ansgar",
        "email": "pell.ansgar@example.co.uk", "tier": "2", "route": "alumni_school",
        "route_detail": "University of Leeds alumni", "status": "not_contacted",
        "next_action": "Send the first note; call 07700 900461 if needed",
        "notes": "example contact; phone +44 7700 900461"})
    _save_csv(contacts, crows, columns)
    _write(os.path.join(state, "documents", "network", "kestrel_mutual_ansgar", "draft.md"),
           "Hi Pell, hope you're well. We were both at Leeds. I build forecasts for "
           "operations teams in Manchester. How is the claims analytics team set up?\n")
    _write(os.path.join(state, "documents", "briefs", "2026-10-23.md"),
           "# Brief, 2026-10-23\n\n- 2 replies owed\n- Kestrel Mutual is hiring analysts\n")
    return state


FIRST = ("ash", "brin", "cal", "dara", "eli", "fen", "gale", "hollis", "ines", "jory", "kit",
         "lark", "mira", "noor", "oren", "pia", "quill", "rue", "sable", "tam")
LAST = ("brook", "caddel", "dunmore", "elsworth", "farrow", "glen", "hatherly", "ivers",
        "jessop", "kellam", "lowther", "marden", "nettle", "orme", "pellow", "quarry",
        "rendle", "stannard", "thorne", "upcott")
FIRM = ("harrow", "kestrel", "lark", "moss", "quay", "rook", "sedge", "teal", "vale", "wren")
KIND = ("freight", "mutual", "retail", "foods", "bank", "logistics", "health", "energy")


def large(state: str, tracker_rows: int = 500, contacts: int = 2000,
          threads: int = 5000, seed: int = 7) -> str:
    """A big invented search: the sizes the budget test names."""
    rnd = random.Random(seed)
    small(state)
    firms = [f"{a.title()} {b.title()}" for a in FIRM for b in KIND]
    rows = []
    statuses = ("drafted", "applied", "applied", "applied", "rejected", "no_response",
                "interview", "withdrawn")
    for i in range(tracker_rows):
        day = f"2026-{rnd.randint(6, 10):02d}-{rnd.randint(1, 28):02d}"
        st = statuses[i % len(statuses)]
        rows.append({"date": day, "company": rnd.choice(firms),
                     "role": f"Analyst {i}", "status": st, "fit_rating": str(rnd.randint(50, 95)),
                     "notes": "invented row", "source": f"https://jobs.example/big/{i}",
                     "applied_on": day if st != "drafted" else "",
                     "confirmed_by": "chat" if st != "drafted" else ""})
    _save_csv(os.path.join(state, "job_search_tracker.csv"), rows, TRACKER_COLUMNS)
    crows = []
    cstat = ("not_contacted", "awaiting_reply", "in_conversation", "replied_needs_response",
             "gone_cold", "connected_no_reply")
    for i in range(contacts):
        first, last = rnd.choice(FIRST).title(), rnd.choice(LAST).title()
        firm = rnd.choice(firms)
        cid = f"{firm.lower().replace(' ', '_')}_{last.lower()}_{i}"
        crows.append({"contact_id": cid, "name": f"{first} {last}", "title": "Analyst",
                      "company": firm, "company_key": firm.lower(),
                      "linkedin_url": "https://www.linkedin.com/in/example-person-" + str(i),
                      "email": f"{first.lower()}.{last.lower()}{i}@example.com",
                      "tier": "3", "route": rnd.choice(("cold", "alumni_school", "referral")),
                      "status": cstat[i % len(cstat)],
                      "next_action": f"Reply to {first} {last}, phone 0161 496 {i % 10000:04d}",
                      "next_action_due": f"2026-10-{rnd.randint(1, 28):02d}",
                      "notes": f"mail {first.lower()}@example.com"})
    columns = list(_csv_rows(os.path.join(EXAMPLE, "state", "network_contacts.csv"))[0].keys())
    _save_csv(os.path.join(state, "network_contacts.csv"), crows, columns)
    trows = []
    for _ in range(threads):
        c = crows[rnd.randrange(len(crows))]
        out = rnd.random() < 0.6
        trows.append({"contact_id": c["contact_id"],
                      "date": f"2026-{rnd.randint(8, 10):02d}-{rnd.randint(1, 28):02d}",
                      "direction": "outbound" if out else "inbound", "channel": "linkedin",
                      "scenario": "first_note" if out else "detailed_generous",
                      "summary": "a message",
                      "full_text": "Hello, write to me at someone@example.com or 0161 496 0000"})
    _save_csv(os.path.join(state, "network_threads.csv"), trows,
              ["contact_id", "date", "direction", "channel", "scenario", "summary", "full_text"])
    return state


if __name__ == "__main__":
    # The fixture the page's own tests and its builder read: the model of the small state,
    # on the fixed clock. Run from the repo root: python3 tests/app_state.py fixture
    import subprocess
    import sys
    import tempfile
    if sys.argv[1:] != ["fixture"]:
        sys.exit("usage: python3 tests/app_state.py fixture")
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, LJS_PROFILE=EXAMPLE, LJS_STATE=small(os.path.join(tmp, "s")),
                   LJS_COPY="private")
        out = os.path.join(ROOT, "tests", "fixtures", "app_model_example.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model",
                        "--now", NOW, "--out", out], env=env, check=True)
