# How it works

For someone who wants the detail. The [README](README.md) is the summary; this is the
level below it.

Three parts. Finding the work is deterministic Python that costs nothing to run. Writing
the application spends model tokens, and it only starts once a person has chosen what to
write about. Reaching people runs beside both on its own clock, and feeds back into the
first: whether anybody at an employer has replied decides whether an application there
goes out cold.

The split at the shortlist is still the one that matters. Nothing is drafted until a
person has picked a posting, and no model spend starts before that.

---

## Part one: finding the work

Seven stages. `tools/run_round.py` runs all of them in order and stops at the shortlist.

| Stage | File | What it decides |
|---|---|---|
| scrape | `scrape_wide.py` | every enabled job board, paginated, across the configured locations and title variants, plus employer career boards read straight from the ATS: Greenhouse, Lever, Ashby and Workday sites (`tools/ats_boards.py`, for the employers `profile/boards.py` names) |
| filter | `prefilter.py` | age, location, title band, and anything already ruled out |
| fetch | `hydrate.py` | the full posting text, one HTTP call each |
| screen | `text_screen.py` | knockouts that a quoted sentence settles |
| score | `opportunity.py` | is this job worth having |
| rank | `fit.py` | would they call back |
| throttle | `throttle.py` | employers you are already talking to or applying at |

### Why the order is what it is

Each stage is more expensive than the one before it, so each one only sees what survived
the last. The filter is regex over a title and a location. Fetching costs an HTTP call
per posting. Screening reads the whole body. Scoring reads it again with judgement.

This ordering was not free to get right. Fetching used to happen before the cross-run
check for postings already ruled out, which meant every round re-downloaded and re-scored
everything it had rejected the week before. A large share of everything reaching the
fetch stage was in that state.

### Employer boards

A portal is a keyword search. `tools/ats_boards.py` is the other half of the scrape: it
asks named employers for everything they have open, from the board their own careers page
reads, as JSON with no key. The employers are the profile's (`profile/boards.py`), read
across four applicant tracking systems:

| ATS | What one board costs |
|---|---|
| Greenhouse | one request, bodies included |
| Lever | one request, bodies included |
| Ashby | one request, bodies and any posted pay included |
| Workday | a paged listing, then one request per body |

Workday is where many large employers live. Until it is read they are visible only
through LinkedIn, so a posting LinkedIn ranked low or never indexed does not exist for
the search.

Four rules shape it.

**robots.txt decides what is read, on every run.** It is parsed with `robots_check.py`,
the same rules the browser-header retry uses. Two employers on the original list
disallow their own careers site and never name the API path; that is read as a no,
because it is the same board through a different URL. SmartRecruiters closes its whole
posting API to every crawler but LinkedIn's, so there is no reader for it. The refusals
are recorded in the module and `--probe` re-checks them.

**A body is fetched only where the free gates could keep the posting.** A Workday body
costs a request, so the listing goes through prefilter's own title and location gates
first. A posting that fails one is still emitted, without a body, so prefilter drops it
with its reason and the funnel stays readable.

**A multi-site posting is judged by the site the candidate could work from.** Prefilter
reads one location string, and a string naming two places reads as the worse of them:
`<City>` and a second city the profile ranks lower is flagged as the second city,
and `<City>` beside a place the profile cannot work from fails on the location gate.
Each site is judged alone and only the best ones are kept.

**Two requests in flight per host.** Every Greenhouse board is one host, so that includes
them. A board that answers 429 is left alone for the rest of the run, and a big board is
searched by title variant instead of paged whole.

An employer's own board is a live board: a posting still listed is still open, so the
age limit (14 days by default), which exists for aggregator listings nobody took down, does
not apply.

### The filter is deliberately timid

A filter that costs nothing but silently discards real opportunities is the most
expensive thing in the pipeline, because the loss is invisible. An early version dropped
a "Manager, Demand Planning Analytics" role on the bare word *Manager*, which the
knockout card explicitly says is not a knockout without direct reports.

So the filter only drops what a title or a location settles on its own. Anything needing
judgement goes through to a stage that reads the actual requirements. A false negative
there costs one cheap pass. A false positive is permanent and nobody sees it.

### The screen cuts on quoted facts only

`text_screen.py` cuts when the posting says something that settles it: a licensing
requirement, a language requirement, a citizenship or residence bar, a vacancy open to
existing staff only, or a stated pay range whose top is below the person's cut line.
Every cut carries the sentence it cut on, so the decision is checkable afterwards.

Salary and degree minimums are flags, not cuts. A posted range below target is
information for the person choosing, not grounds for removal.

`profile/tests/fixtures/screened_postings/`, in a person's own repo, holds postings named
for what must happen to them (the app has none: a real posting is part of somebody's
search, and `tools/score_eval.py` reads the person's). A `pass__*` file is a role that was wrongly cut at some point and must keep
passing. A `cut__*` file must keep being cut. The screen is the one place where a
regression is silent, so the corpus is the regression test.

### What a round leaves behind

About 55MB of intermediate files, all of it derived and thick with third-party posting
text. The round deletes them and keeps the top of the shortlist without the posting
bodies, roughly 30KB, in `documents/rounds/<round>.json`.

A round that **missed** its yield target keeps three files it otherwise deletes, with the
bodies stripped: what the gates removed, what the screen removed, and what the throttle
removed. Those are the three places a posting can vanish, and they are what the failure
message tells you to read.

---

## Part two: writing the application

### Choosing bullets

`tools/bullet_library.py` holds every bullet the candidate could truthfully claim,
tagged by theme, with conflict sets so two bullets carrying the same figure never both
appear.

`tools/allocate.py` decides how many bullets each employer gets and which ones:

- **Tenure.** Two years somewhere is more of a career than one year. Entered as a square
  root so it matters without dominating.
- **Recency.** Recent work is better evidence of current ability. A mild factor.
- **Relevance.** Each posting is scanned for theme cues, and an employer's relevance is
  the strength of its best bullets against this posting.

This is what makes a logistics posting surface a route-cost model, and an inventory
posting surface a stock-out forecast, from the same profile.

**When an employer gets exactly one bullet, that line is also its job description.** With
several bullets, relevance and representativeness pull in the same direction. With one
they can disagree, and relevance can win on a margin of half a point, which lets a minor
line stand for an employer's whole job. Relevance has to win by a full theme match to take
an employer's only line.

### Fitting the page

`tools/fit_to_page.py` renders, compiles, and measures. Too long, and it removes the
weakest bullet for *this* posting and recompiles. Once it fits, it tries to add back the
strongest bullet that is still absent.

The generator enforces what a person forgets: reverse-chronological order, a fixed
section order, a short skills block under the person's own headings, no repeated figures. Each of those is a defect
that reaches an application when nobody is checking, which is why it is a rule.

### Checking the result

`tools/verify_batch.sh` runs over a whole batch and exits non-zero on any finding:

- page count, section order, chronology, bullets per employer
- contact details present as literal text in the PDF's text layer
- no duplicated phrasing across bullets
- no em or en dashes, and none of the document nouns the profile bans (no "CV" where the
  market says resume)
- a clean text layer, with no `(cid:)` markers or replacement characters

Then `check_claims.py` over every factual assertion and `audit_letters.py` over every
letter.

**The text layer is checked separately from the page** because an ATS reads the embedded
text and not the rendering. LaTeX can produce a PDF that looks perfect and extracts as
garbage: icon glyphs landing in front of the phone number, or a name and a city running
together because the name has no descenders.

---

## Part three: reaching the people

`tools/network/` is the other half of the search, and it keeps its own clock: a message
sent in March is what decides, in May, whether an application goes out cold. Four
commands sit on it. `/network` finds people at a target employer, `/reply` works out what
an inbound message needs, `/threads` says what is owed and to whom, and `/prep` writes
the document for a call that came out of a thread.

The division of labour is the one from part one. The code holds what can be tested and
the model does the judging. `discovery.py` builds the queries and triages the results
while the searches themselves happen in the skill layer, and `reply.py` classifies an
inbound message and prescribes what the reply has to do without ever writing one.

### Finding people

Where to look is the person's own plan in `sources.py`: of the kinds of public place that
name people at an employer (team pages, posting contacts, alumni features, speaker lists,
trade press, code, official directories and more), the ones that pay for their field, level
and country, reordered by reply rate once a kind has five decided first notes. Each employer
gets at most four searches across its kinds, the kinds that serve every employer at once
(alumni, rosters, meetups) share five for the whole run, and the LinkedIn title search
inside that is two queries, never more than three, in `queries_for()`. An employer where
people came back and none fits is recorded as having no relevant presence and skipped for
90 days (`company_research.py` `PRESENCE_REVIEW_DAYS`).

Alumni modes run before cold modes wherever both are possible: former
colleagues of a past employer answer far more often than cold contacts. Those queries
never name the target company, because naming it collapses an alumni
search back into a cold one with extra words in it.

`why.py` ranks everyone found: a score from 0 to 100 and one plain line saying why this
person (a shared employer, a hiring post, a role open there that scored well), counted
with no model call, so the batch is read and written best first.

Tier 1 is live hiring intent, and it is the only tier that needs evidence rather than a
title, so the evidence is the quoted sentence and it travels through to the message. It
reads the post and not the poster: a manager in `<City>` writing "we are hiring 3 data
scientists in Austin" must not score tier 1 on the city they sit in, because the quote
offered as proof is about Austin.

Nobody already in the book is surfaced again. `already_contacted()` matches through
`company_key`, and it folds accents before comparing, because LinkedIn can return one
person as "Juno Castellan" in one snippet and "Juno Castellán" in the next. Without
folding, the second harvest looks like a new person, and a second cold message goes to
somebody who was written to that week.

### Composing

Each message type has its own composer (the first note, an InMail, an email, a warm intro,
a nudge, the referral ask), and the first note takes one of five shapes chosen from who
the reader is and what was read about them: shared history first, their own work first,
brief for a senior reader, a recruiter's, or a message to someone already connected
(`compose.shape_for()`). The limits the platform enforces are enforced here. A connection note is 200 characters on a free LinkedIn plan and 300 on Premium
(`tools/network/schema.py` `LIMITS`, set by `LINKEDIN_PLAN`), and `compose.py` raises with the count rather
than truncating, because what to cut is a judgement about which detail matters least and
a truncator always takes the close. A warm intro that does not name the referrer in its
first sentence is refused outright: being recognised before the reader decides whether to
keep reading is the whole reason that message converts.

The channel carries as much as the length does. A 135-word warm intro for somebody a
contact said to connect with is wrong where the message is the connection request, which
LinkedIn cuts at the plan's note limit like any other. Sent that way, it spends the strongest
asset in the book on half a sentence.

Nothing composed here may claim a status the profile does not hold, citizenship or
permanent residency among them. No phrasing fixes that, and the check refuses the draft
rather than rewording it.

### Keeping the thread

Follow up after 5 to 7 business days, counted in business days because six calendar days
from a Wednesday is the following Tuesday while six business days is the Thursday after
that, and counting the calendar way reads as impatience. One nudge, not a series. After
two explicit declines the thread stops, counted from the messages rather than from a
status, because the status is edited by hand and the messages are the evidence.

Scenario precedence is an ordered ladder rather than a score. An email address inside
four generous paragraphs is still `send_resume`, because the substance can be engaged
with in the reply while the address is the thing that stops being actionable if it is
missed. A blend would pick whichever pattern was written more generously that day.

### Preparing for the call

Every fact in a prep document prints with its source or it does not print. `prep.py`
raises on a value that arrives with no attribution, and it cannot produce a compensation
band at all: with nothing researched and passed in, it prints "not researched" rather
than a number. The failure it prevents is a band or a headcount that sounded right, got
written down, and then got said out loud to somebody who knows the real figure. Company
research older than 30 days (`company_research.py` `RESEARCH_FRESH_DAYS`) is flagged as a
lead to re-confirm, not a fact to repeat.

### Where it meets the shortlist

`tools/company_key.py` makes a contact at "ABC" and an application to "Acme Bank of
Commerce" the same employer, so the throttle stage in part one reads the contact book.
What it does with a posting there turns on whether anybody replied.

- **Somebody replied.** The posting surfaces carrying "DO NOT APPLY COLD" and the name.
  It is never hidden, because a warm route makes a job more worth having, not less.
- **Sent, nothing back.** Applying is unaffected and always was. What changes is that a
  second message must not go out, so that rides along as its own note.
- **A referral in flight.** The one state that suppresses the posting outright. Somebody
  inside has put the name forward, and a cold application arrives as a second, worse
  record of the same person.

Counting the unanswered as warm is a defect this had. "DO NOT APPLY COLD" printed over
employers where nobody had said a word back, the referral bonus went onto the fit score,
and the role was exempted from the fit floor, all on the strength of an unanswered
InMail.

---

## Cost

Optimise the whole lifecycle, not any single prompt. A cheap shortlist that surfaces the
wrong roles costs more than it saves, because the expensive stages then run on a bad
target.

| Stage | Model cost | Model |
|---|---|---|
| Scrape, filter, screen | none | it is Python |
| Knockout triage | ~3-5k | small |
| Fact extraction | ~1k | small, batched |
| Full weighted scoring | ~19k | mid |
| Adversarial verification | ~40k | mid, only on 70+ |
| Grounding audit | ~110k | strongest, never downgraded |

**A cheap model may extract, and may reject on a quoted fact. It may not judge.** Two
attempts to move fit scoring onto cheap machinery were measured against a capable model
and came out 18 and 21 points off. Fit turns on whether adjacent-sounding work is
actually adjacent, and that is a judgement. The saving comes from sending fewer postings
to it.

**Anything that could put a false claim in front of an employer runs on the strongest
model available.** Cheapness is never a reason to risk a fabrication.

Full detail in
[`11-cost-model.md`](.claude/skills/job-application-assistant/11-cost-model.md).

---

## State

Sessions run in containers that are destroyed when they end. Anything not committed did
not happen, so state is written at the moment it changes.

The three state files, and two more that hold what has been decided:

| File | Holds |
|---|---|
| `job_search_tracker.csv` | every application, including ones made outside this repo |
| `network_contacts.csv` | who, where, and what state the relationship is in |
| `network_threads.csv` | one row per message, in or out |
| `job_scraper/seen_jobs.json` | every posting seen, and every ruling with its reason and what it rests on: the person's screening rules (it lapses when they change) or their own words (it holds until lifted, `tools/exclude.py`) |
| `profile/learned.json` | what the person has said they want different, kept for good and read before anything is drafted (`tools/learned.py`) |

**Thread status is derived from the message log, never stored.** A stored status drifts
the moment somebody replies and the row is not edited, and the row is edited by hand.
`reconcile()` reports every place the two disagree, and it separates the findings that
need a person from the ones that are only history: a flat list buries the few that matter
among many, and an orphaned thread sits unnoticed until something goes looking for it.

Part three has the rules that decide what gets written into the two networking files.
This section is only where it is kept.

`tools/company_key.py` is the join. "ABC" and "Acme Bank of Commerce" resolve to one key,
so a contact and an application at the same employer link without anyone maintaining a
mapping.

`python3 tools/open_actions.py` renders the three state files as one view, employers first. It is
derived on every run and never stored, so it cannot go stale. If something is missing
there, the state file is wrong, not the view.

---

## Layout

```
tools/            the seven search stages, the document generator, the verifiers
tools/network/    discovery, message composition, thread state, call prep
templates/        resume_gen.py, the LaTeX every document is filled into
.claude/skills/   the rules: scoring, writing style, cost model, playbooks
.claude/commands/ one file per slash command
.agents/skills/   one CLI per job board, each behind an enabled: flag
cv/               rendered resumes, one per application
cover_letters/    rendered cover letters, same
documents/        source material in, application records out, see documents/README.md
tests/            the app's suite, over 80 files and 1,200 tests, run against profile.example/
profile/tests/    a person's own tests, against their profile (not in the app)
```

## Conventions

Changing anything here: [MAINTAINING.md](MAINTAINING.md). The short version is that
almost every rule in `tools/` carries a comment naming the application it shipped as a
defect on, and removing one needs an argument about that original failure.
