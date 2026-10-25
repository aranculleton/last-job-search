# The brief (twice a week; schedule: `profile/routines.json`)

One message, twice a week, built around where this person's search is right now. It does
not search for jobs: a fresh shortlist is one "find me jobs" away whenever they want one.
`_common.md` first, which has already brought in the app's updates.

## Read first

- **The last brief**, the newest `documents/briefs/*.md`. Everything below covers **since
  then**, or the last 7 days when there is none, so nothing already sent is repeated.
- **What this person wants from it**: `profile/CLAUDE.md`, section "This search's
  automation", and `python3 tools/learned.py brief messages` for how they like things
  written. Both outrank this file.
- **The state**: `python3 tools/open_actions.py` (employers first, applications and
  contacts together) and `python3 tools/open_actions.py --due` (what is owed today). Holds,
  freezes, "DO NOT CHASE" notes, live interview processes and referral holds are already
  applied by the tool; never argue them back into the message.

## Lead with where the search is

Decide which of these is true, from the tracker and the contact book, and put that first.
It is what makes the brief this person's rather than a template:

- **An interview or offer is live**: that leads. Name each process, its next step and date
  where the tracker has one, and offer `/interview <company>` for the next one. A process
  with a chat of its own (`open_actions.py` says "handled by its campaign chat") gets one
  line naming that chat and nothing else: its prep, drafts and drills live there, and two
  chats preparing the same call contradict each other.
- **Replies owed to people**: these go cold fastest, so they lead when nothing above does.
- **Applications out and waiting**: what is due a nudge, and for each live application
  whether anyone at that employer is in the contact book who could get it read.
- **Little going out** (no application in the last 14 days, or none at all): say so plainly,
  name the warm routes already in the contact book, and say a shortlist is one "find me
  jobs" away. Never run a search here.

## 1. Owed

1. From `open_actions.py --due`: replies owed first, then nudges, then first notes queued.
   Requests to withdraw and what it sets aside (owed over 45 days with nothing done, most
   often old LinkedIn history) are counts: say each in one line, and draft nothing for them.
2. Read the most recent `documents/network/followup_pack_*.md`, reuse any draft still right
   for an item still due, and draft only what is new. Networking messages follow
   `.claude/skills/networking` (read the contact's whole thread in `network_threads.csv`
   first) and every one must pass `compose.validate()` and keep the person's follow-up rule
   (`schema.follow_up_rule()`; unset, one nudge only, 5 to 7 business days),
   stop after two nos, the candidate's exclusions (`profile/CLAUDE.md`), nothing to anyone at
   `awaiting_reply` before their window opens. Application follow-ups are a separate clock,
   two follow-ups 7 days apart: use the text, recipient and schedule the tool prints
   (RUNBOOK.md step 5), and one with no recipient gets only the line saying who to find. First notes: draft for the contacts already in the book (no discovery runs here),
   highest tier and employer value first. The app sets no cap on how many; when LinkedIn
   has said its weekly invitation limit is reached, say so and keep the rest for next week.
3. Write `documents/network/followup_pack_<today>.md` in the previous pack's layout. If
   nothing is due, write no pack. Beside each networking draft, the time where its reader is
   (`python3 tools/network/reading.py send-time <contact_id>`), said only, never a reason to
   hold one back.
4. **Keep the call preps current**: `python3 tools/network/prep.py --stale-only` rebuilds
   every prep written before its contact's status, next action or thread changed (answers
   already rewritten to be said are kept). Say in one line how many it rebuilt, and when
   one is for a call in the next two days, put it in the three things below. A prep that
   prints `RESEARCH NEXT` is listed there too, as research to run, and the prep is shown
   as it is meanwhile, marked as not researched yet.

## 2. Since the last brief

- Applications sent, replies received, interviews, offers and rejections, counted from the
  tracker and `network_threads.csv` between the last brief's date and today.
- Applications drafted but not marked sent for more than 7 days: ask whether they went, and
  record the answer with `python3 tools/confirm.py` (applied, not-applied, skip or closed),
  never by editing the tracker.
- Applications gone quiet: `python3 tools/followups.py --close-quiet` closes each one past the
  chase (45 days, or a week after a second follow-up) as no_response, with a dated note,
  recorded as the search's call, and leaves alone any with an interview, a referral or a "DO
  NOT CHASE" at that employer. Say it in one line as "closing as no reply" with what it
  closed, and that they can keep any open (it prints the `confirm.py applied` line that
  does) or record a late reply with `/outcome`.
- Results to record: anything the person mentioned elsewhere that the tracker does not have
  yet, and a line asking for outcomes with `/outcome`.
- `python3 tools/what_works.py brief search`: one line, only when it reports a clear
  difference.
- `python3 tools/network/own_profile.py due`: when, and only when, it prints a line, its
  question goes in as one of the three things below. It costs nothing when silent.
- `python3 tools/network/export.py due`: when, and only when, it prints a line (their
  LinkedIn download is a fortnight old, or older than their `EXPORT_EVERY_DAYS`), asking
  for a new one is one of the three things below, with the steps `python3
  tools/claude_surfaces.py steps linkedin-export-files` prints, checked against LinkedIn's
  help page that day (CLAUDE.md, "A step on another company's site is checked before it is
  given"). The chat it is given to runs `export.py take`, which says what changed since the
  last one (new connections, requests accepted, replies, requests still waiting) and writes
  each contact's follow-up date.

## 3. News that matters

A homepage, not a newsletter: **up to five bullets**, each one line, each with a link, each
ending in what it means for the candidate. Fewer is fine. **None is fine**: a quiet stretch
says "Quiet week" and stops.

Gather with a cheaper model: one `Agent` call with `model: "sonnet"` (or the
`employer-researcher` subagent for a single employer), given the list below and told to
return items with URL, publisher, publication date and the sentence each rests on. At most
about ten searches in total. You then choose, verify and write.

What counts, in this order. The places, the market and the status to watch are this
search's own: `profile/CLAUDE.md`, "This search's automation", names them.

1. **Employers the candidate is in process with or has a live thread at**: layoffs, hiring
   freezes, a reorg of the team they would join, earnings, a new office in their city, a
   leadership change.
2. **Their target employers** (`profile/CLAUDE.md` "Target Sectors"): the same kinds of
   news, in their market only.
3. **Their market for the roles they want**: hiring or layoff waves, a central-bank
   decision, sector earnings, a big funding round at a local company in their field.
4. **Their work authorization**: any change to the programme or status it rests on. Rare,
   but the one item that outranks everything above.

Rules for an item to go in:

- Published since the last brief (at most 7 days ago), the date checked on the page itself.
- From the publisher's own page, opened and read. A search snippet is a lead, not a source.
- No paywalled guesswork, no rumour, no "sources say" about a specific employer's hiring.
- One line: `<what happened> (<publisher>, <link>). <so what for the candidate>.`
- If an item changes a live application (a freeze or layoffs at that employer), append a
  dated line to that row's `notes` in `job_search_tracker.csv` too.

## 4. Three things before the next brief

Exactly three, most valuable first, each one line, each something the candidate can do in
under half an hour, drawn from the sections above: a reply to send, a nudge, an interview to
prep, a warm route to open, a result to record. Never "keep going" or "stay positive".

## Write, land and deliver

Write `documents/briefs/<today>.md`: the date, the lead, the owed list, the counts since the
last brief, the three things, then the news with links. Same layout every time, so the
briefs read as one record. Commit it, the pack if one was written, and the tracker if a note
was added, and land them per `_common.md`.

The message, under 200 words, written for a phone:

```
<Weekday> brief: <n> owed · <n> applications live · <n> interviews
<the lead, in one sentence>

Owed
- <at most four lines, replies first: Name (Company): the ask>
(or: Nothing owed)

Since <last brief's date>: <n> sent, <n> replies, <n> interviews

Next three
1. <action>
2. <action>
3. <action>

News
- <at most three bullets, one line each, no links in the notification>
(or: Quiet week)

Full brief: <the brief's own page on GitHub, documents/briefs/<today>.md on master>
```
