---
name: networking
description: >
  The professional outreach layer: finding the right people at target companies,
  composing every outbound message type, managing live conversation threads,
  tracking who is owed what, and preparing for the calls that come out of it.
  Triggers on: network, networking, outreach, connect, connection request,
  InMail, cold email, referral, warm intro, reply to, draft a reply, follow up,
  thread, contact, /network, /reply, /threads, /prep
---

# Networking and Outreach

## What this is

The other half of the job search. `job-application-assistant` answers "which roles
are worth applying to and what documents do they need". This answers "which people
are worth talking to and what should be said to them".

They are one pipeline, not two. The same employer, the same profile, the same
tracker. `tools/company_key.py` is the join: a contact at "Acme Corp" and an application
to "Acme Inc." resolve to the same key (`acme`), so a referral thread and an
application record find each other automatically. An initialism and the full name
(the contact's profile says "ABC", the application says "Acme Bank of Commerce") join
only through the person's `COMPANY_ALIASES` in `profile/employers.py`.

**The highest-value output is judgment, not volume.** Twenty mediocre names is a
failure. Every message spends a scarce platform slot and a piece of the user's
reputation, and both are harder to get back than they are to spend.

## The modules

Deterministic logic lives in `tools/network/`, so it is testable and costs no
model tokens. This skill decides *what* to do; the modules enforce *that it is
done correctly*.

| Module | What it owns |
|---|---|
| `schema.py` | The contract: contact and thread columns, statuses, platform limits |
| `state.py` | The store, the application link, what is owed, platform budget |
| `sources.py` | Where to look: the kinds of public place that name people, this person's plan of them, and the search budget |
| `discovery.py` | Query construction, tier classification, the disqualifier filter |
| `why.py` | Why this person: a score from 0 to 100 and one plain line, by counting |
| `openalex.py` | Researchers who put an employer on a recent paper, when `OPENALEX` is on |
| `tone.py` | Every tone rule as an enforceable check |
| `compose.py` | Message assembly with hard length limits |
| `reply.py` | Scenario classification and reply guidance |
| `reading.py` | What was read about one person before writing: their page, their public work, what a note can rest on |
| `prep.py` | Call prep documents, for a call that came out of a thread |
| `profile_facts.py` | The candidate half of a prep document, read from the profile |
| `export.py` | LinkedIn's data export, read: their connections, their message history into the log, the invitations still waiting. Given a download, `take` it first: saved and imported in one step, never read straight from where it was downloaded |
| `own_profile.py` | Their own LinkedIn profile, checked now and then for red flags only; `due` is silent until a look is worth it |

**Never hand-write a message without running `compose.validate()` on it**, with the
recipient's `name=`: a draft that greets anybody else ("Hi Tamsin," on a note for Riley
Chen, which a shuffled batch produces) is refused as `greeting_wrong_name`, and no
recorded rule lifts that. The tone rules exist because each one was a correction made
in practice; the checker is how they stop being re-learned.

## This skill and its four commands

They are not alternatives, and the names are close enough to pick wrongly.

- **This skill** is the rules: tiers, tone, limits, playbooks. It loads whenever outreach
  comes up.
- **`/network`** runs a discovery against named companies.
- **`/reply`** drafts inside a live thread.
- **`/threads`** shows what is owed.
- **`/prep`** writes call prep for a booked call. **Not `/interview`**, which prepares a
  real interview on a tracked application and takes a company rather than a person.

`/networking` is not a command. See "Commands and skills: what routes where" in
`RUNBOOK.md` for the full map.

## The rules every outreach keeps

Load this skill before any outreach. It is an **extension of this system, not a parallel
one**: the join is `tools/company_key.py` (above), and company findings cache in the
existing `company_research/`. State lives in `network_contacts.csv` and
`network_threads.csv` beside the tracker, saved with the rest (`python3 tools/save_state.py`).
**Status is derived from the messages wherever the log can know it**, so it cannot drift
from the evidence. What the log cannot know (a call booked, a referral in flight, a
conversation gone cold, a close) is stored on the contact row by whoever learns it
(`state.py set`), and wins over the log. `networking/connection_targets.md` is research
notes only. **Not a contact store**: `network_contacts.csv` is, and anyone named in that file
is a row in it.

Every rule below is enforced in code; each section further down has the detail.

- **Nobody is shown as someone to write to without the one check**: `python3
  tools/network/surface.py` (`surface.check()`; `--file` for a list made any other way). It
  reads the contact book, their whole thread on every channel and the bar, and prints NOT
  with the reason for anyone not to show. Never join files or check people by hand.
- The search budget is `tools/network/sources.py`; alumni and referral routes come before
  cold; tier 1 only on a quoted live hiring signal; each person is read before anyone writes
  to them (`reading.py`, `/network` step 5); and someone already contacted is never surfaced.
- **Outreach is for referrals, in three stages never compressed into one:** a first note that
  asks for a conversation (`compose.first_note()`), the conversation, then a referral ask for
  one linked role (`compose.referral_ask()`).
- **Who reads a first note decides what it says** (`compose.READER_TYPES`, each a setting in
  `profile/networking.py`): a recruiter may be told the role wanted and the person's work
  authorization, a decision-maker the role wanted (their work authorization once the
  messages the person approves say it), and a decision-maker gets the open ask ("anything
  coming up"); asking whether they are hiring, or for a referral, is a recruiter's alone; a
  peer is told neither unless that message asks.
- Before a draft is shown, `compose.advise()`: the draft is rewritten on its warnings first,
  and a warning the rewrite leaves standing is shown with the draft for the person to decide,
  never in place of the rewrite.
- Connection notes are the plan's limit, 200 characters on a free LinkedIn plan and 300 on
  Premium (`schema.LIMITS`, from `LINKEDIN_PLAN`), hard: `compose.py` raises, never
  truncates.
- No LinkedIn profile is ever fetched from a session, and LinkedIn's job search **stays
  on**: only the person switches it off, never a session. Profiles are read in the person's
  own browser: by the page itself when it is open in the Claude desktop app, or by a chat on
  their computer.
- **A chat on the person's computer** starts with "On a new computer" below
  (`reading.py new-computer`): LinkedIn signed in, then its download, unprompted.
- Never claim anything not in `profile/01-candidate-profile.md`.
- **A LinkedIn download the person gives is taken first**, before anything is written from
  it: `python3 tools/network/export.py take <the ZIP or its folder>` saves it and imports its
  message history in one step. Never read its files straight from where it was downloaded.
- A resume sent to a contact is logged with its file (`state.py message <id> --attached
  <file>`). One made for them is staged with `stage_picks.py --for-contact <id>`, and
  RECONCILE (`python3 tools/network/state.py`) says where the two disagree, because the chat
  that logs the ask and the chat that drafts the resume are often two chats at once.
- Before drafting anything, `python3 tools/learned.py brief messages` and `python3
  tools/what_works.py brief messages` (RUNBOOK.md, "Learning the person"); what the person
  says back about a draft goes through the same section.

## Discovery

Where to look is the person's own plan, `tools/network/sources.py`: the kinds of public
place where people in their field, level and country are named (`sources.KINDS`: LinkedIn
title searches and hiring posts, team pages, posting contacts, alumni features, speaker
lists, meetups, trade press, code, official directories and more), chosen by `/setup`
(`PEOPLE_SOURCES`) and ranked by what has drawn replies. `/network` step 3 runs it. The
LinkedIn people searches inside it follow the rules below.

**Bulk discovery never depends on reading anyone** (`sources.LADDER`, `/network`, "The
ladder"). A run makes its whole list from rungs any chat has: their own connections export,
then public pages and search results, then a profile check from the results' own titles.
Reading a profile, in their browser or from a paste, enriches a short list of that list:
the best ten in a browser, the best three from a paste, never everyone.

### Searching LinkedIn for people

```
WebSearch(
  query='[COMPANY] [ONE JOB TITLE] [LOCATION]',
  allowed_domains=["linkedin.com", "<country>.linkedin.com"],
)
```

`discovery.queries_for()` builds the query string and `discovery.SEARCH_DOMAINS`
holds the domain list. Pass both. One title per query, in plain words: measured on
2026-10-18, that shape found 14 people named at the employer where the old one, a quoted
literal `"linkedin.com/in"` and four ORed quoted titles, found 5; the ORed titles alone
brought back job listings. Save the results' titles and addresses and run
`sources.py harvest` over them: it turns them into people with evidence and a profile
status, and drops every result that is not the person's own profile or post.

**The `site:` operator does not work for profile searches.** The brief this skill was built from
prescribes `site:linkedin.com/in ...`, and three live runs proved it wrong for
this toolchain: a company search returned Glassdoor and ZipRecruiter
listings, and an alumni search returned nothing but LinkedIn `/jobs/` pages. The
same intent with the domains constrained returned mostly real profiles. Do not
re-introduce `site:` into a profile query; a test asserts its absence. The
hiring-posts search is the deliberate exception: it asks for `site:linkedin.com/posts`, and
its results are read, never fetched.

Even then, roughly two results in ten are LinkedIn's own job-board pages.
**Put every URL through `discovery.resolve_result(url, company)`** before triage: it
rejects `/jobs/` and the aggregators, keeps profiles, and turns a post permalink
(`/posts/...-activity-`, `-share-` or `-ugcPost-`) into the author's profile and the
post's exact date. Those posts are where tier-1 signals live, and `is_person_url()`
alone threw them away.

Public LinkedIn profiles carry JSON-LD, so snippets return job titles, employer
with location, and recent post content. One query returns roughly ten results.
It is the highest-yield call available.

**Never spend a call on:** a company-name search with no domain constraint
(returns job ads), a careers page (JavaScript), a blog's index page (no author
names, stale), or fetching an individual profile URL (login-walled, returns
nothing). Team pages, blog posts, org charts and the other kinds are reached
through the searches `sources.py` prints, and a page is fetched only where its
robots.txt allows.

### Budget

Each employer gets at most `sources.SEARCHES_PER_COMPANY` (four) searches across all
its kinds, every kind taking a turn before any takes a second, and the kinds searched
once for the whole run (alumni, rosters, meetups, awards) share `SEARCHES_PER_RUN`
(five). Inside that, the LinkedIn title searches go first, both of them
(`sources.TITLE_SEARCHES`, two: the one kind measured to name people in bulk);
`discovery.queries_for()` returns at most two, and **never more than three** whatever the
caller passes. On top of the four, at most `sources.CHECKS_PER_COMPANY` (three) searches
check the profile of the best name-only people a page named (`sources.to_check`). Searches
that return nothing at all are
`no_results`, which proves nothing: try a roster, record nothing.
Queries that return people of whom none fits are `no_relevant_presence`: record it
with `discovery.record_presence()`, which holds for `PRESENCE_REVIEW_DAYS`
(`tools/company_research.py`), and move on. That
verdict is a real output, not a failure: it stops the company being re-targeted
next month.

`sources.for_company()`, `sources.for_run()` and `discovery.queries_for()` enforce the
caps. Do not route around them.

### Tiers

These tiers rank people. The job-scraper skill's Tiers 1 to 4 are its scoring stages, a
different thing.

1. **Live hiring intent.** The snippet quotes a post saying they are hiring.
   Converts far better than anything else, because the person has a live need
   and has publicly invited contact. `classify_tier` returns the quoted signal
   so it can be shown as evidence.
2. **Hiring authority in the right location.** Manager through VP, on a team
   matching the user's function, in the target city.
3. **Senior ICs.** Principal, Staff, Lead, Senior. No formal authority, but they
   get asked "know anyone good?", they have referral bonuses, and they are
   pitched far less than managers, so they often answer more.
4. **Anyone else adjacent.** Only when 1 to 3 are empty.

### Routes that beat cold outreach

Cold is the worst channel. Use it last.

- **Shared-employer alumni** is the strongest. Former colleagues from any of
  the candidate's past employers (`profile/01-candidate-profile.md`) who are
  now in the target city. The shared history is real, not manufactured, and
  the response rate reflects that.
- **Referral chains.** When a contact names someone, that person is the highest
  priority target in the system and the message leads with the referrer's name.
- **Shared education.** Alumni of the candidate's university in the target market.
- **Mutual connections**, when a name is available.
- **"Meet the hiring team"** on a live posting: the warmest cold contact there
  is, because they own a req the user matches.

Run alumni modes before cold modes for any company where both are possible.

### Filter ruthlessly

`discovery.disqualify()` holds the rules. The ones that bite most:

- **Revenue roles dressed as technical.** Solutions Architect, Field Engineering,
  Cloud & AI Specialist, Technical Account Manager, Client Partner, Head of
  Industry. They are customer-facing sales and do not hire for technical teams.
  So are sales, account, business development, go-to-market, partnerships and
  customer success roles ("Data & AI Sales Executive"), unless the title's own role
  is in the person's function: "Senior Data Scientist, Go-To-Market" and "Analytics
  Manager, Partnerships" are kept. The skip says what it found ("an industry head, a
  sales and partnerships role").
- **Wrong office function.** Verify the city houses the function before
  searching. Record "no relevant presence" when it does not.
- **Name collisions.** Acme the AI lab is not Acme Health. Verify
  entity, industry and headquarters before including anyone.
- **Staffing spam.** Emoji urgency, no company named, a personal email address,
  bulk unrelated role lists. These harvest resumes.
- **The person has moved.** Watch for "my last day" and "excited to share I've
  joined" in the activity snippet.

### Read each person before writing to them

Finding someone gives a title and a line. That is enough to know they are worth
writing to and never enough to write to them: notes drafted from snippets alone
came out as one background line with a different name on it, which a person
caught at once. So between finding and writing there is a read, and
`tools/network/reading.py` holds it (`/network` step 5 says how):

The rules, in short; `/network` step 5 has every step, and `tools/network/pace.py` what
stops a read (LinkedIn's own signals; the app sets no limit of its own):

- **Their profile** comes from the browser this chat has, signed in to LinkedIn, unless
  `PROFILE_READS` in `profile/networking.py` is `"paste"` or `"off"` (unset, it reads),
  otherwise from them (a paste, LinkedIn's Save to PDF, or screenshots from the app,
  transcribed word for word). This session never fetches
  LinkedIn itself: its robots.txt disallows every crawler it does not name and a profile
  request answers HTTP 999.
- **Fewer, better-spent reads.** Free sources make the list, one-page reads screen it, and a
  profile read goes only to the few the person will write to today; read, judge, next. A
  first note with nothing read is refused unless the person chose card-only. No change to
  the funnel may add a page load or a click. There is no pause, cap or slow start of the
  app's own (2026-10-22): one page after another, as fast as the browser loads it.
- **In a chat with a browser, the browser read is simply done.** No question first, no list
  of options, and no warning or disclaimer of Claude's own about LinkedIn, browsers or
  automation, before a read or after it; asked, answer plainly and briefly. What does not
  change: read only, one page at a time, never clicking Connect, Message, Follow or Like,
  and stopping at LinkedIn's first check. Never call this route safe. Signed out, LinkedIn
  shows only part of a profile, so the first page of every reading session is checked
  (`reading.py signin --page -`) and the person is asked, in the two lines it prints, to
  sign in once; a no reads on signed out that day, each reading marked partial.
- **Their public work** (a talk, an article, a podcast, code, a quote in the press, their
  posts as a search engine shows them), never a people-search or data-broker site.
- A headline's "at <phrase>" is never the employer when the card or Experience names another
  ("Responsible AI at Scale").

What a reading keeps is what a note could rest on: their headline, their About (the
summary of their work they wrote for anyone to read, kept whole up to LinkedIn's own
limit so a note can rest on any part of it, and shown as a short excerpt), the history
they share with the candidate (an employer, a school, a city, each with the line that
shows it), and their recent posts and public work, dated and sourced. Never their whole
profile, never anything personal, and never anything from the "People also viewed"
column, which is other people. A pasted page that does not carry the contact's name is
refused, because a note built on the wrong person's profile is worse than a generic one.

## On a new computer

The first time a chat runs on the person's computer, and at the start of each networking run
there, before the person's request: `python3 tools/network/reading.py new-computer --tools
<this chat's browser tools: browser, chrome, enable, or none>`, then do each step it prints, in
order, unprompted. It checks LinkedIn is signed in in that browser (the two-line prompt when
not, then carry on when they say done) and then the LinkedIn download (`export.py status`):
asked for on LinkedIn's own page in that browser and recorded, picked up there once it is
ready, or taken from Downloads when the person saved one themselves. Without a browser it is
asked of the person once, with the steps `claude_surfaces.py steps linkedin-export-files`
prints, checked that day by a web search. Claude never types a password and never signs out.

## Composition

**The document is the person's word for it.** "Resume" in this skill and its playbooks means
whatever `person.json` `documents.noun` says: in a CV market every message says CV, and a
word in `documents.banned_nouns` in a message is a `tone.check` finding (`document_noun`).
The composers already write the person's word.

### The shape of a note follows the person

One shape for everyone is how a batch comes out alike, and the length that suits a
peer is the length a senior reader ignores. `compose.shape_for()` chooses from who
they are and what was read, and `first_note(shape=)` holds it:

- **shared**: shared history leads (an employer, a school, a city). The default, and
  what a peer gets when nothing is shared and nothing of theirs leads: the standard
  note at the plan's limit, never the senior reader's 220.
- **their_work**: their talk, post, paper or code leads, with no opener before it.
- **brief**: a senior reader. The true line, who you are and the ask; no question,
  under 220 characters.
- **recruiter**: their job is roles, so who you are, what you want and work authorization.
- **connected**: already connected, so a message with room for the question and the ask.
- **pointer**: the kind of team or work named, ending on a question they can answer by
  pointing to the right person ("Would you know the right person to speak to about that?").
  It makes a helpful reply easy without asking for anything: the referral-aware first note.

### Who reads it decides what it says

Three kinds of reader (`compose.READER_TYPES`, from their title, or `reader=`), each with
the person's settings in `profile/networking.py`:

| Reader | Work authorization (`ELIGIBILITY`) | The role wanted (`SAY_THE_ROLE`) | The ask | InMail length (`INMAIL_WORDS`) |
|---|---|---|---|---|
| recruiter | yes | yes | anything coming up that fits | about 170 words |
| decision-maker | once the messages the person approves say it | yes | "Would love to hear if you have anything coming up, or know the right person to speak to." | about 170 words |
| peer | no, unless `work_auth=True` for that message | no | a short call, or a pointer | about 130 words |

The decision-maker's row is the message that drew a reply from a senior reader within
three hours: who the sender is, with the years; one piece of real work with its numbers;
why this person; a plain statement of eligibility, which a draft carries once the person's
approved messages to decision-makers do; the open ask. Asking about openings,
"are you hiring", "refer me" stay a recruiter's alone, at every reader type: a job-ask
finding names the phrase and what to write instead.

Who to write to first is `tools/network/why.py`: a score and one plain line of why
this person, from the route, shared history, a hiring post, a role open at their
employer that the candidate scored well, their function, recent activity and the
reply odds of their kind of title. Where to look is `tools/network/sources.py`: the
person's own plan of places people in their field are named, ranked by what has
drawn replies, inside a fixed search budget.

### What outreach is for: referrals

Every first message exists to start a conversation, and the conversation is
what produces the referral. That is the whole sequence. A contact who answers a
cold note may mention a role that is not posted, name a colleague, make an
introduction or put the candidate's name forward, and none of them is asked for
a job in the first message.

So there are three stages and three messages, and they are never compressed
into one:

| Stage | Message | Composer | Asks for |
|---|---|---|---|
| 1. First note | connection request, 200 chars free / 300 Premium | `compose.first_note()` | 15 minutes; a question about them only when there is a real one |
| 2. Conversation | replies, call prep | `/reply`, `/prep` | whatever the conversation needs |
| 3. Referral ask | message pane, under 90 words | `compose.referral_ask()` | a referral for one named, linked role |

### The first note: `compose.first_note()`

A note that names the job it wants reads as a demand, and the note exists to
lead to a referral. A note in the application shape ("I am an analyst with six
years of forecasting experience and would like to be considered for the Senior
Analyst role on your team. I have the right to work here and need no
sponsorship") draws almost no replies, while a short note that starts from
something real and asks about them gets answered. For example:

> Hi Sasha, hope you're well. Your talk on forecasting stock levels stuck with
> me. I work in data and I'm looking for my next role here. Would you have
> fifteen minutes for a call one week?

That note is 186 characters, so it fits a free account's 200. Adding a question
("How did your team settle on building the forecasts in-house rather than buying
a tool?") takes it to 273, which `first_note()` refuses on a free plan and accepts
on Premium. That is the shape, and `first_note()` assembles it:

    Hi Sasha, hope you're well. <the reason for writing>. <about me>. [<question>?] <ask>.

- **The reason for writing** (required, and true). One or more of, in this order:
  - a **mutual connection** the person confirmed (`mutual=`): `reading.py show` lists the
    ones the page names; ask "mention <name>?" first, and never say how well they know them;
  - **how they were found** (`how_found=`, `compose.how_found_line("team_search",
    company=..., team=...)` and the rest of `HOW_FOUND`): a search of the team, the people
    page, a referral, a speaker list. The honest reason, and the one to use when nothing
    else is real;
  - the **common ground**: a shared employer or school, or the one thing about their work
    that made the candidate write, taken from their reading (`UngroundedNote` when it
    rests on nothing read; their name or employer alone does not count);
  - a **parallel in their path** (`parallel=`): `reading.py show` lists them, marked
    INFERRED, so the note hedges it once ("I imagine you moved into <X> from <Y>,
    which is the move I'm making"). The composers do that themselves
    (`compose.hedge()`): a common ground or parallel whose subject is the reader and which
    their page does not state comes out with one hedge from the person's own (TEMPLATES
    "hedge") or the bank; `hedged=False` leaves it as written. A generic fit ("useful on a
    team like yours") is warned as presumptuous; their own path is the reason instead.

  **Never a pretext.** A note that says the sender read, saw or watched something of theirs
  ("I saw your package on GitHub") raises `UnconfirmedReading` unless `looked=True`, the
  sender's own word that they did: a reading the chat did is not the sender having looked.
  No two notes in a batch say the same thing (`reading.same_ground()`), and none is built
  the same way (`reading.py batch` reports "same shape"). What a batch is judged on is its
  frames, not one phrase: one sentence with the nouns swapped ("<years of X>, which I imagine
  <employer> values"), one opening after the greeting or one close across more than a third
  of the batch, two notes to people at one employer sharing a sentence, or six or more notes
  all in one sentence order ("same sentence order": twenty notes of who-line, one line about
  them and the ask, 2026-10-22), saves none of them (`reading.py draft` and `drafts` check
  every save, exit 11). `compose.first_note` varies its order by contact; `order=` chooses
  one. No close is held to `ASK` word for word. A phrase the person
  reuses for strangers at different employers is theirs; the house style in one message is
  a stock phrase, and the person's own (`OWN_VOICE`, their `OPENER` and `ASK`) is allowed in
  every kind of message.
- **The company limit holds at the draft too.** `reading.PER_EMPLOYER` people at one
  employer (two, or the person's `PEOPLE_PER_EMPLOYER` in `profile/networking.py`) while
  nobody there has answered, counting those waiting on a reply and the notes already queued:
  `reading.employer_full_line()` is the one test, read by the short list, every draft saved
  and `reading.py batch`. When the person wants more at one employer, keep their word for
  it: `reading.py more-at "<Employer>" --said "<their words>" [--up-to <n>]` (kept in
  `profile/more_at.json` and recorded as theirs); every refusal prints that line.
- **About me** defaults to one modest line, `ABOUT_ME` in
  `profile/networking.py`, that also says the candidate is looking, as context
  rather than a demand, in the shape "I work in data science, ex-<Employer> and
  <Employer>, and I'm looking for my next role here". That says who they are
  and what they are looking for, without naming a job. Change it when the common ground already names one of
  those employers. **Drop the looking clause when the common ground is their
  hiring** (a recruiting post, an open req): beside a hiring signal it turns
  the note back into a job ask.
- **Question** (optional): about them, answerable in a line, and only when there
  is a real one: how they got into the field, how the team is set up. Never one
  made up to fill the slot. A person called "How has data science changed
  pricing there?" "so artificial", and the same note read better as the true line
  and a plain ask for a conversation, which is a complete note on its own.
- **Ask**: the person's `TEMPLATES` for this reader first, then their `ASK`, then the
  phrase bank's asks for this reader (`compose.py phrases`), chosen per contact
  (`variant_key=` the contact id) so a batch varies. Pass `ask=None` when the question
  carries it. Never an exit ("if not, no worries"): it invites no reply. An easy no
  belongs only in a later message that asks a favour, as the referral ask's "no problem
  at all if not" does, and never as words that name the pressure ("no pressure either
  way", under "Never name the thing you are disclaiming").

**What a first note never does**, enforced by `AsksForTheJob` and by
`validate(kind="connection")`:

- read their own title back to them ("You lead analytics engineering at
  Acme."). Say what about the work caught the candidate's eye instead. Not
  enforced in code; an audit of drafted notes is what catches it

- name the role the candidate wants, or call any job "the job I want"
- ask whether they or their team is hiring, whether a role is on their team, or
  who hires for it
- say where the candidate wants their next role to be ("Acme is where I want my
  next role")
- state work authorization to a peer. To a recruiter it goes in by default (`ELIGIBILITY`),
  because their reply is about roles; to a decision-maker once most of the messages the person
  approved for one say it (`compose.eligible()`); to a peer only when
  that message passes `work_auth=True`. A brief note to a senior reader leaves it out unless
  asked, for want of room.

Contractions are fine: "I'm" and "I'd" open sentences in natural English, and forcing "I am"
and "I would" made the defaults read like someone who just learned English as a second
language (`CONTRACTIONS` brings the old rule back for a person who wants it).

**To a recruiter, and to anyone: never "any jobs?", never "are you the right person?".**
"Any data roles open in <city>?", "does hiring sit with your team, or someone else?", "do your
searches cover it, or is that another team?" and "or someone better to ask?" read as "any
jobs?" and "are you useful to me?". `validate()` refuses the blunt job ask for every reader
(`asks_for_the_job`) and the gatekeeping question by its shape (`gatekeeping`). A pointer asked
openly ("Would you know the right person to speak to about it?") is neither.

**What they approved is the model.** A message the person approved ("great, both sent",
"almost perfect", "more of this") is kept whole with `learned.py approve`, and
`learned.py brief messages --channel <c> --reader <r>` prints the best matches above the
rules, before any draft of that kind. The hook notes an approval the way it notes a reaction.

### Before it is shown: `compose.advise()`

`validate()` is what must never go: a refused draft is rewritten and never shown.
`advise()` is what may go but reads worse than it should, each warning with its rewrite.
The draft is rewritten on its warnings before it is shown, and a warning the rewrite leaves
standing is shown with the draft for the person to decide, never in place of the rewrite:

- the phrases the person rejected: "sits close to", "is the kind of path", "I would value",
  "high on my list" and any praise of the company that fits any company, "the route I would
  most like to follow", "which teams to look at and how to approach them", "Data scientist
  here" as an opener, a closing question asking how to get hired, a test question in place
  of an honest ask, and a vague ask about how their team works or spends its days, caught
  by its shape ("I'd love to hear what your team spends its days on");
- phrasings that read badly to anyone (`advice.PHRASINGS`): telling them what they do ("You
  recruit for ..."), a detail off their profile read back so it reads as googled ("your
  <model> for <employer>'s <project>"), underselling ("a long way from my background"), a vague
  close ("what you're seeing", "great to hear more"), "swap notes" or "compare notes", "it
  looks like", a reason opening "Since you ...", asking a recruiter how they got into
  recruiting, "<X> is a thread between us: A for you, B for me", "pretty much", "sometime",
  "the <X> side", and "hoping to", which reads as asking for it now;
- a list of three credentials in a row: name the one that matters to this reader. Never the
  person's own who-line (as `ABOUT_ME` sets it, or as it stands in a message they approved),
  and never a list with a place in it ("moved from Leeds to Manchester, ex-<A> and <B>");
- the person's own city, in a draft to an employer that heard another place
  (`company=` the reader's employer; `tools/told.py` keeps what each employer heard);
- hedges: one light hedge per inference ("I imagine", "I'm guessing", "probably", "it
  seems like"), never two in a sentence, never a disclaimer ("I can't know from the
  outside"). A question and an offer on their terms ("if you think it might help, I can
  send ...") hedge no claim and are never counted;
- a claim about the reader written as fact (a fact their headline holds, said in other words,
  is STATED: "you recruit for ML and AI" from "Talent Acquisition, Machine Learning & AI").
  Each claim is STATED (their page says it, so
  say it plainly), INFERRED (from a title, an employer, a path: hedge it once) or a GUESS
  (about their team or what would be useful to them: lightly, or better not at all). A
  fact their reading holds (their employers by name or initials, their title) is STATED,
  and an asking close ("I'd love to join your team, or just hear more") claims nothing.
  An inference has them as its subject ("You moved into pricing", "Your team builds the
  forecasts"); "Your talk stuck with me" says what the sender felt, and is no claim;
- a guess at what they see from their level or title ("you've probably seen a fair few
  of the teams from a Staff role"): ask it, or cut it;
- a credential with no reason in its sentence: tie it to them as a plain link ("the same
  forecasting work your team does"), or cut it. A sentence with a number in it is evidence
  and carries its own point;
- a comparison that never says how ("goes a lot further than", "a step on from", "take my
  work next"): bigger, more complex, more data, more senior;
- their career read back to them ("you did X, then Y, then Z"): the one step that links to
  yours; congratulations followed by a jobs ask in the same note; a metric dump (three
  figures or more in a note, four in an InMail; "from 22% to 14%" counts once);
- a content word said twice in one sentence ("consulting" twice in the line about you),
  or in two sentences side by side ("now" twice running, always). A word the message's own
  subject names (the reason for writing, the question, their team) may come back in the
  next sentence: a message about pricing says "pricing". Names, numbers and the person's
  fixed lines never count;
- the person's own shorthand or contraction written out in full, where their VOICE in
  `profile/networking.py` lists it ("I am" for someone who says "I'm", an employer's full
  name for the short one they use). The composers write their VOICE themselves;
- an exit in a first message ("no worries at all", "totally fine if not"); "I came across
  your profile"; the employer named late (with the reordering); an InMail close
  that asks nothing about their current work or team (`bare_close`); an InMail longer than
  its reader needs (`compose.inmail_words()`: the length the person asked for with
  `learned.py record ... --length inmail=<words>`, else `INMAIL_WORDS`).

The person's own words are never warned about, and a check one of their rules outranks
(`learned.py record --overrides <rule>`) is only mentioned, `advise()`'s own included.

Praise to a stranger is a refusal, not a warning: `validate()` refuses "really interested
me", "fascinating", "impressive", "the kind of work I'd like to do more of" and the like
(`flattery`) in a sentence that reaches them, and the fix is the plain link between their
path and the sender's. A sentence about the sender alone ("I've been fascinated by markdown
pricing") is not praise of them. Every composer, the nudge, referral ask, email and warm
intro included, refuses what `validate()` refuses for its kind, a phrase the person said
never to use (`learned.py record --never-say`) among it.

Each refusal carries the name of the check that made it, and voice_check's are its own
("house-style", "ai-diction", "opener-hope"), so `learned.py record --overrides
house-style` lifts that one check. A note to a hiring manager about an application already
in is `validate(kind="message")`, with no length of its own (`outreach.check_note()` runs
it): saying it was applied for is the point there, and a job ask everywhere else.

**Then read it aloud.** `compose.READ_ALOUD` says how: the most natural spoken version,
every fact, name and number kept, nothing added, their rules kept.
`compose.read_aloud(original, rewrite)` keeps it only if no fact was lost or added and it
still passes `validate()`; show the one kept, never both.

**Their own messages that drew replies come first.** `python3 tools/what_works.py brief
messages` shows them, with their words: match their shape and their wording ahead of every
default here. A message logged without its words cannot be one, which is why every send is
logged with them.

"Hope you're well" and "I'd love to" are allowed in a first note when the person's
`OWN_VOICE` in `profile/networking.py` names them. They were banned on a frequency
count, but frequency was never the problem: the notes that were answered carried both
phrases, and so did the ones that were not. The body was the difference. A person whose
`OWN_VOICE` does not list them gets `ReadsAsGenerated` for them, and they stay flagged in
letters either way.

### The referral ask: `compose.referral_ask()`

Only inside a live thread, after they have replied, spoken to the candidate or
offered help. One role, named and linked, the posting URL on its own line, an
explicit "would you be comfortable referring me for it?", and an easy no. Under
90 words. Asked of a stranger it is the cold application stage 1 was rebuilt
to stop sending, so it is refused in code: `thread=` is their contact_id (or their
message rows), and nothing composes until a reply or a call of theirs is in it, or
their row says they replied before the log began.

If they have already offered to refer the candidate, in whatever words, the ask
is answered: do what they said, then thank them.

**InMail, under 200 words, with a subject.** `compose.inmail()` returns an `InMail`: the
text as before, and `.subject` and `.body` for LinkedIn's two fields. The shape that drew a
reply: "Hi <name>, hope you're well."; who they are, with the years; one piece of real work
with its numbers; why this person, eligibility by reader, the ask; the sign-off. Never a job
ask. Sized to the reader (the table above); the 200 words are a ceiling, not a target. The
**subject** is who the sender is by default, the identity line that drew a reply
(`compose.identity_subject()`: "<title>, ex-<the employers they left>", or `SUBJECT` in
their networking.py), never "Quick question", "Job enquiry" or anything that asks for the
job; `inmail_subject()` refuses those. Where the reason for writing names an employer the
sender left, the subject names it first (`identity_subject(lead=)`). A page that shows only
Message to someone not connected sets their channel to InMail and says how many credits are
left; `state.py sent --channel inmail --subject "..."` spends one. An InMail answered within
90 days gives its credit back (LinkedIn's own help, read through a web search), and the
balance LinkedIn shows wins over the count until the month turns: `state.py inmail-credits
<n>` keeps it. Nobody whose card or page shows a request already Pending gets one: `people`
and `read` record that request as sent.

**No two InMails in a round built alike.** Two went out with one subject, one paragraph
order and one close, and the person asked why the structure was identical when it is meant
to be personal to the company, the role, the level and the person. `inmail(order=)` is one
of `INMAIL_ORDERS`: who you are first (the senior reader's default), why them first (a peer
with common ground), or both together; `inmail(team="the pricing team")` closes on a real
question about their current work. `compose.round_alike(drafts)` finds a subject, a
paragraph order or a close two messages share, and `reading.py batch` (exit 11) and
`reading.py draft` run it.
Credits are scarce; reserve them for tier 1 at top-priority companies, or people
unreachable otherwise. A free LinkedIn account has none: InMail there goes only to an
Open Profile (their profile shows a Message button), and everything else is a connection
request. **The Message button looks the same for an Open Profile and for an InMail that
spends a credit**: which one shows only in their message window
(`claude_surfaces.py steps linkedin-open-profile`). So before an InMail is drafted, run
`reading.py extractor --message-check` on their page (it opens the window, types nothing,
closes it) and keep what it returned with `reading.py message-check <id> <output>` (or the
person's word, `free` or `credits`, with `--by-hand`). A draft is saved only for someone
who will get it: free goes as an Open Profile message (channel `open_profile`, no credit);
one that needs a credit only while the credits left this month cover it beside the InMails
already drafted; and none before the check. 14 InMails were drafted on a guess and 2 went
through (2026-10-24).

**The person's LinkedIn plan sets the limits.** `profile/networking.py` `LINKEDIN_PLAN`,
"free" or "premium" (`tools/network/schema.py`): a free account's connection note is 200
characters and a handful of personalised notes a month, Premium's is 300 with InMail
credits. With no plan recorded the free limits apply, because a note short enough for free
is short enough for Premium. When the month's notes are spent, the request goes with no
note and the drafted note follows as a message once they accept (`platform_budget()` says
so). The app sets no cap on connection requests (2026-10-22): LinkedIn publishes no number
and says itself when its weekly limit is reached, and `state.py`'s BUDGET line counts what
went without printing a number LinkedIn never gave.

**A message to someone already connected** (first degree) is `kind="dm"` in
`compose.validate()`: no subject and no credit, LinkedIn's message limit
(`schema.LIMITS["message_chars"]`), and the first-note rules, since it is a first message.
A nudge in that thread is still `kind="nudge"`, and a later message `kind="reply"`.

**Email, when they give an address.** A strong signal, and it happens often.
Resume attached, a short context paragraph so they do not have to find the
original message. Do not over-trim: a senior person who asked you to email them
expects substance. Repeating what was said on LinkedIn is fine. Which resume: one drafted
for them for a role they named (`stage_picks.py ... --for-contact <id>`), else the
person's current one, never one tailored to a guess; and the message is logged with the
file that went (`state.py message <id> --attached <file>`), so a drafting chat and a
networking chat working at once leave one record and the next interview knows what they hold.

**Warm intro.** The referrer's name goes in the first sentence. This is the
highest-converting message type in the system and burying the referral wastes it.

**Register.** Match the recipient. Same content, different surface. Where work
authorization belongs (a recruiter, a referral ask, a direct question), it is
the senior wording in `profile/networking.py` (`WORK_AUTH`) for a senior
recipient and the peer wording for a peer.

## Replies

The largest surface. `reply.classify()` identifies the scenario; `reply.guidance()`
returns the correct move and a target length. **Match their effort.** Two informal
lines earns two lines back; four detailed paragraphs earns real engagement.

The single most common failure is **restating their own points back to them**.
It reads as machine-generated. `tone.restate_ratio()` measures it. Show you
understood the shape of what they said; do not summarise it at them.

See `02-reply-playbook.md` for the full scenario table.

### A request that is still pending is not a thread

Until a connection request is accepted there is nowhere to write, so it is never
nudged. `state.owed()` lists it as `request_pending` once it has waited
`state.REQUEST_WITHDRAW_DAYS` (21 days): withdraw it, because LinkedIn caps how many
can be outstanding and one nobody accepted in three weeks rarely is. Once the person has,
`state.py withdraw <contact_id>` records it: a `request_withdrawn` row, which the derived
status reads as closed, and the contact closed with the date and why, so nobody writes
to them again. Requests sent from LinkedIn itself, which the log never saw, come from
their export (`export.py pending`, the same three weeks): they withdraw those on LinkedIn,
and `export.py withdrawn` records each one closed. Someone who
accepted a request that carried **no note** has been told nothing, so what is owed is
a first message (`first_message`), written with `compose.first_note()`, never a nudge.
A call or meeting logged in the thread (`channel` call, phone, teams..., or
`scenario` call_held / call_missed) is never a message: a held one counts as a
conversation, and what follows it lives in `next_action`.

A close the person chose is written into the row as "closed on purpose: <their
reason>" (or "do not reopen"), so a later reply does not reopen it on every run. A
close without those words that is followed by a reply is reported as `reopened`,
because a session that closed somebody by mistake is exactly what that catches.

### Accepting is not replying, and it is not nothing either

A connection request has three outcomes, not two, and for a long time this skill
could only see two. Ignored is one. A reply is another. **Accepted and then
silence is the third**, it is recorded as `connected_no_reply`, and it was being
counted as ignored, which is wrong in both directions: it hid the people most
worth a second message inside the bucket of people not worth one.

Treat it as the best non-reply there is. They took an action, and the acceptance
converted a short, character-capped invitation into a permanent 1st-degree DM channel with
no character limit and no InMail credit. That is a materially better position
than the day before, and it deserves a materially better message than the nudge
an ignored invitation would get.

- **Wait the same 5 to 7 business days** from the acceptance, not from the send, or the
  person's own days where `profile/networking.py` sets `FOLLOW_UP_DAYS` (with
  `MAX_UNANSWERED`, how many may go unanswered in a row). `state.follow_up_on` is the one
  clock, and the date is written onto the contact (`state.py follow-ups --write`).
- **Ask one specific question about their work, answerable in a line.** This is
  the whole content of a good nudge to someone who never engaged. News about the
  sender is not a reason to reply: an update about the sender's own situation is
  something a senior stranger who already declined to answer has no reason to
  care about. A question about *their* side does the opposite, because
  answering costs one line and people answer questions about their own work when
  they will not answer an introduction. Never "just following up on my request",
  and never an update about the sender.
- **But only where there is no thread substance to point at.** This rule is for a
  cold introduction that was ignored, and applying it to a live thread produces
  the opposite of what it is for. Where a call has already happened, a resume has
  already gone, or a question has already been answered, the follow-up points at
  *that* and stops. Inventing a question to justify the message is what makes it
  read as generated, and inventing one whose answer is already settled is worse:
  a draft that asks which track interests the candidate, when the track was
  agreed earlier in the thread, reads as not having listened. Three
  sentences pointing at the real thing beat a manufactured opener every time.
- **Make it SHORTER than the message they ignored**, not longer. The free channel
  is room the nudge does not have to use. See below.
- **One only**, same as everywhere else. After that, stop and leave the
  connection, which keeps its value indefinitely.
- **Never re-send a connection note** to someone already connected. It cannot be
  sent and it signals the sender is not looking.

**Log an acceptance as an inbound row with scenario `accepted_no_reply` and no
text.** `state.derive_status` reads that row as `connected_no_reply`, never as a
reply, and the nudge clock runs from its date. Reading the direction alone would
count an acceptance as an answer, make the employer a warm route and refuse the
nudge because "they answered".

**An automatic reply is not a reply either.** An out-of-office or a "no longer with
the company" template logged inbound (scenario `auto_reply`, or recognised from its words
by `state.auto_reply()`, in English and a few other languages) changes nothing: the
thread still waits on them, the employer is not a warm route, no reply is owed, and it
never counts as a message that drew a reply. An away message's return date holds the
nudge until two working days after it (`state.AWAY_GRACE_BUSINESS_DAYS`); a "no longer
with" means closing the contact and finding who holds the role now.

The blind spot that remains: the repo cannot see LinkedIn, so it only knows
someone accepted when the candidate says so. Every `awaiting_reply` row is
potentially a `connected_no_reply` row. When a nudge falls due, the first
question is whether they are now a 1st-degree connection, because the answer
changes the channel, the length and the content of what gets sent.

## Pipeline state

`network_contacts.csv` and `network_threads.csv`, beside the application tracker.
Status is *derived from the messages* wherever the log can know it (who spoke last,
whether a request was accepted), so it cannot drift from the evidence. The statuses a
message log cannot carry are stored on the contact row: `call_booked`,
`in_conversation`, `referral_in_progress`, and the terminal `gone_cold`, `closed` and
`converted_to_application`. A terminal row always wins, and a reply in the log outranks
any other stored status, because a reply is owed whatever the row says
(`state.effective_status()`).

**Never surface someone already contacted, and never by a check of your own.** Every
person shown as someone to write to has passed `surface.check()` (`python3
tools/network/surface.py`): the contact book by id, address or name at either employer,
their whole thread on every channel, the bar, and a hold, with the reason when not. A
chat that checked by hand skipped steps and surfaced people already written to on
another channel and at employers the bar rules out (2026-10-23). If the user asks for a second contact
at a company, pick a different person and change the angle so it does not read as
a sweep. **Check how recently the first one went out.** A second approach at one
employer the day after the first is a sweep whatever the angle; space it a week,
and say in the row why it is held rather than dropping the person.

**A live process at an employer outranks a new approach there.** If someone
inside has the resume, held a call, or is advocating, a cold request to a second
person at that company puts a worse record of the same candidate in front of the
same team. Hold it until the live thread resolves.

### Once they have replied, stop writing to a stranger

The single most repeated correction in this skill's history, and the one that
keeps coming back in new clothes. A thread with a reply in it is a conversation,
and a conversation has a different register from a first approach. Four things
that belong in a cold note and nowhere after it:

- **Dates they lived through.** "The CV I sent last Tuesday", "my message
  from a while back". They were there. A date is a reminder, and a
  reminder says you assume they forgot you.
- **Re-thanking what was already thanked.** "Thanks again for the call last week,
  and for pointing me to your colleague before that" thanks one person twice for
  two things in a single opening clause.
- **Re-introducing the sender.** The who-line earns its place once. After that it
  says the sender has not registered that they are already known.
- **Formal sign-offs in a chat window.** "Kind regards" to someone who opened
  with ":)". A light "hope you're well" is not on this list: between two people
  who have spoken once, that is ordinary politeness, and stripping it produces a
  message that reads as aggressive. The fault is rebuilding *context*, not
  being warm.

The test is simple: **would a person who knows you write this?** If the draft
would read identically to a stranger, it is a first message wearing a thread as
a costume. A long thank-you to an advocate that explains the whole situation
back to them can be cut to two short lines that sound like someone they have
met.

**Never invent a reason for their silence.** "Happy to resend if it got lost",
"in case it got buried", "not sure if you saw", "I know you're busy". Every one
supposes a failure that almost certainly did not happen, and the sender knows it
did not: a sent email is a sent email. The move costs twice. It reads as
desperate, and it hands the reader a ready-made non-answer to reach for instead
of the real one, so the message actively lowers its own chance of a straight
reply. Their silence needs no theory. Ask the question and stop: "any word from
the hiring manager?" is the whole message. The `excusing their silence` rule in
`tone.py` enforces it, and `live_thread` does not relax it, because it is wrong
in every register.

**Aggressive is a failure mode of terse, not the opposite of it.** Cutting
scaffolding is right; cutting the warmth with it is not. "Can you refer me, yes
or no? I need to plan" is short and reads as an ultimatum, because the binary
demands a decision and "I need to plan" says they are one option among several.

**Cut the middle, keep the ends.** This rule exists because a message revised
several times tends to go verbose, then blunt, then curt, and each overcorrection
is its own failure. What gets cut is the middle: context they already hold, dates
they lived through, re-introductions, manufactured questions. What stays is a
greeting with some life in it and a closing beat, because those are what make a
short message read as a person being brief rather than a person being cold. "Any
word from the hiring manager?" is six words and reads as a demand. "Hope things are
good. Any word back from the hiring manager? Still very interested." is fourteen and
reads as a colleague. Fourteen words is not scaffolding.

The overcorrection pattern is the tell. If a draft has just been cut hard, read it
again for coldness before sending it, because the pass that removes the padding
is the pass most likely to remove the warmth with it.

**The cold rules do not all survive the switch to a live thread.** `tone.check(..., live_thread=True)`
drops `COLD_ONLY_RULES`. The no-opening-contraction rule is there because a
character-capped note uses a contraction to save two characters, and that reasoning
dies in a warm reply: answering "That's great, thank you Riley" to someone who
wrote "Hi Sasha - ... :)" is how people speak, and "That is great" is the stilted
version. Everything register-independent still fires.

### "Following up" has to be true

The phrase asserts that something is outstanding. Before writing it, ask what.

`reply.following_up_is_honest(threads, today)` answers it from the message log
rather than from the writer's sense of awkwardness, and returns a reason meant to
be read by a person. It is honest when an unacknowledged thing is genuinely
pending: a resume they asked for, a booked call, an introduction requested. It is
not honest in three cases, each of which needs a different message entirely:

- **They spoke last.** That is an overdue reply, not a follow-up, and opening on
  "following up" hides that the delay was ours. If a contact says yes to a call
  and gives their availability, a draft that opens a week and more later on
  "following up on the call we said we would set up" reframes the
  candidate's silence as their slowness.
- **They committed to something and the clock is theirs.** "Send it over and I
  will see what we have" is a promise with a lead time. Chasing inside it
  reads as not trusting them to do it. The clock starts when they could *act*,
  not when they promised: a promise conditional on a resume that arrives four
  days later has not been running since the day it was made.
- **Nothing was promised.** After a conversation that simply concluded, there is
  no pending item, and "following up on the call" pokes someone who gave you
  their time and owes you nothing. Thank them for what they actually did, say
  where you stand, and ask a status question with an easy out.

**Sweep the whole book when a rule like this lands, not just the draft that
prompted it.** Running every stored draft through `tone.check()` and this
function together finds bad *data* as well as bad writing: a resume row missing
its `send_resume` scenario, or a contact at `in_conversation` with no messages
logged at all. A rule that only reaches the draft in front of you is a rule the
next session gets wrong.

### Never name the thing you are disclaiming

"One question rather than a chase" tells the reader this is a chase. "Sorry to
nag" asks them to hold the nagging in mind while they read. "No pressure either
way" introduces pressure as a topic. Every one of them is the same move: the
writer is uncomfortable about sending the message and hands that discomfort to
the recipient instead of simply asking. The easy no a favour carries ("no problem
at all if not", closing a referral ask) is not this move: it answers the favour
asked and says nothing about the message itself, which is why a later message
may carry it and a first one may not (`advise()` warns an exit only in a first
note or an InMail).

Cut the disclaimer and the awkwardness goes with it, because it was never in the
question, only in the apology for asking. The `naming what you disclaim` rule in
`tone.py` catches the message describing *itself* as a chase, nag, bother, pester
or reminder, and is deliberately narrow enough to leave "I had to chase the
invoice team" and every other ordinary use alone.

The rule exists because a batch of short follow-ups drifts into opening on the
same manufactured line.

### A nudge is shorter than the thing that was ignored

Someone who ignored a short, capped invitation is not going to answer an even
longer one, least of all if they are senior. The failure mode is a long DM
written by hand instead of through the module, which says `sentences=(2, 2)`
under `gone_quiet`.

The asymmetry is the point. A first message is an introduction and earns the full
note limit. A nudge has already been declined once, so every extra word is spent
arguing with someone who has not engaged, and seniority makes that worse rather
than better: the more senior the reader, the more a long second message reads as
someone who cannot take a hint.

`compose.nudge()` enforces it at `schema.LIMITS["nudge_chars"]`: 280 at most, and always
20 below the connection note limit, so 180 on a free account (note 200) and 280 on
Premium (note 300). It is deliberately *below* the note it chases. It raises rather than trims,
and it refuses a nudge with no new reason, because a nudge with no new reason is
a check-in and a check-in is why the first message went unanswered.

**Pass `their=(employer,)` when the reason opens on their employer's name.** The
reason runs on from "Hi Sasha," so its first word is lowered, and a one-word
name nobody vouched for goes with it: without the argument a draft reads "Hi
Sasha, acme's Future Opportunities". A possessive, a day, a place and a two-word
name keep their capital without it; "Acme opened a role" does not.

### A referrer who just delivered gets thanks, not a second ask

When a referral converts, the reflex is to bundle the thank you with the next
request: what is the team like, what should I know, who will I meet. Resist it,
and check which round is actually in front of you first.

A first-round talent-acquisition screen is motivation, salary, notice period and
work authorization. There is almost nothing an insider can tell you that changes
how you handle it, so an ask attached to that round spends a favour on the round
where it is worth least, immediately after the person has already done you one.
The round where their knowledge genuinely moves the needle is the hiring-team
interview, and that is where the ask belongs.

So the note thanks them, reports the outcome, says **nothing is needed from them
now**, and promises an update. That is generous rather than transactional, it
self-selects (a senior person who wants to help will offer), and it builds the
natural reason to come back to them at the round that matters.

**When the candidate closes a thread, close it.** If the candidate decides to let
a thread go and says so, that is recorded once, with the cost
named once, and then never raised again: the row goes to `closed`, the next
action is emptied, and nothing further is drafted. These are the candidate's
relationships. The skill's job is to make the cost visible before the decision,
not to relitigate it after.

**Thank an advocate on the day, not after the outcome.** Someone who puts a name
forward and hears nothing does not do it twice, and that relationship outlasts
any single requisition.

**Length tracks what they do not already know, not how big the news feels.** A
thank-you tends to start long and want cutting to a third, because it keeps
explaining the situation to the one person who set it up. Telling a referrer
"you passed my details on a couple of weeks back", or quoting the requisition
number back at them, is the restating failure this skill already names, wearing a
thank-you as a disguise. Inside a live thread the recipient holds the context:
say the new fact, say thanks, say what happens next, stop. Three lines is not
curt to someone who has been in the conversation all along; it is the only
length that treats them as though they were.

**Do not hedge the attribution either way.** "I suspect that is your doing" is a
guess dressed as gratitude: it is either false modesty, or it quietly asks them
to confirm or correct it. Thank them for the thing you know they did (they said
they passed the details on) and report the thing you know happened (an invite
arrived). Causation needs no claim, and the note is true whichever way it went.

### A referral is capped by its channel, not by its type

`warm_intro()` takes `channel`. The default, `"message"`, allows up to
`INTRO_WORDS` because a message pane has room. **"Please connect with X" does not
mean a message pane.** It means the warm intro *is* the connection request, and
LinkedIn truncates it at the connection note limit (200 free, 300 Premium) exactly like a cold one. Pass
`channel="connection"` and the composer refuses anything longer, because the one
thing that must survive is the referrer's name, and a truncator cuts from the
end. The referrer still has to lead on either channel.

**Print every draft in full, in the reply.** A draft referred to by contact_id,
or described rather than quoted, cannot be sent, cannot be corrected and does not
survive the session. This applies to messages for people already contacted as
much as to new ones: the candidate sends from the chat, not from the CSV.

**Respect the platform.** `state.platform_budget()` returns the InMail credits left and
the connection requests sent. When LinkedIn says its weekly invitation limit is reached,
say so (`state.CAPPED_NOTE`) and keep the rest queued for the next week.

## Judgment

**Answer "what do I owe" from `python3 tools/open_actions.py`, never from memory
or from one state file.** It is derived from all three and it orders employers by
how close they are to an outcome. Answering from the nudge clock alone reports
"one follow-up due" and misses calls agreed but not yet booked, replies owed,
and offers waiting to be taken up. A nudge to someone who has not
replied is the least valuable thing in that list, and it is the only thing the
clock shows.

**There is no best hour to send, and nothing is held for one.** A request waits in their
invitations until they next open LinkedIn, and who is asked and what the note says decide a
reply far more than the hour (the person's question of 2026-10-22). The one exception: a reader
in another time zone gets it in their working day, not their night or weekend, and the
hand-over says so in one line only when it applies.

Say plainly when a company or a person is a dead end, and why. Distinguish a
**skills gap** (bridgeable, name it honestly, a named gap plus genuine strengths
beats an overclaim) from a **categorical blocker** (citizenship, clearance, a
required designation, a seniority tier well above the user) which is a hard no
regardless of framing.

Never write a message claiming something not in `profile/01-candidate-profile.md`. It
fails in the first screening call and costs the relationship. When pushed to
overstate, hold the factual line and find the strongest honest framing. There is
almost always one.

## Commands

- `/network <companies>`, discovery run, ending in ready-to-send drafts
- `/reply <contact>`, classify a live thread and draft the reply
- `/threads`, what is owed, what is due, what has gone cold
- `/prep <contact>`, prep document for a booked call
- `state.py received <id> --text-file <file>` logs their message as it came (`--scenario`,
  `--date`, `--channel`), never written into the log by hand
- `state.py nudge <id> --text-file <file>` logs a nudge that went, with its words;
  `state.py message <id> ...` any other later message (`--texts <file.json>` for several);
  `--attached <file>` on either (and on `sent`) names a file that went with it, and
  `state.py attach <id> <file>` names it on the newest message already logged to them
  (`--date <day>` for an older one);
  a second message to someone on a day one already went is refused unless `--also`
- `state.py no-reply <id> --why "<what they said>"` when their last message needs no
  answer ("I'll get back to you next week"): nothing owed until they write again or the
  day to look again
- `reading.py estimate [N]` says how long N reads take; `reading.py meanwhile` the notes
  that can be written now; `reading.py drafts <file.json>` saves a batch checked together
