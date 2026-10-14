# Morning brief (schedule: `profile/routines.json`)

One message a morning, in two halves: what the candidate owes people, then a short read on
the market. `_common.md` first.

## Half 1: what is owed

1. `python3 tools/open_actions.py --due`. Its first line counts everything. Holds, freezes,
   "DO NOT CHASE" notes, live interview processes and referral holds are already applied by
   the tool; do not second-guess them into a message.
2. **Weekdays only:** read the most recent `documents/network/followup_pack_*.md`, reuse any
   draft in it that is still right for an item still due, and draft only what is new.
   Networking messages follow `.claude/skills/networking` (read the contact's whole thread in
   `network_threads.csv` first) and every one must pass `compose.validate()`. Application
   follow-ups use the text and recipient the tool prints; one with no recipient gets only
   the line saying who to find. Respect what the tool cannot see: one nudge only, 5 to 7
   business days, stop after two nos, the candidate's exclusions (`profile/CLAUDE.md`), nothing to anyone
   at `awaiting_reply` before their window opens. First messages are limited by
   `state.platform_budget()`: draft only as many as there are connection requests left this
   week, highest tier and employer value first. Write
   `documents/network/followup_pack_<today>.md` in the previous pack's layout. If nothing is
   due, write no pack.
3. **Fridays** also add a weekly scoreboard to the pack: applications sent this week,
   replies, interviews, drafted-but-unsent applications older than 7 days, and a request for
   outcomes to record with `/outcome`.
4. **Weekends:** no pack. Count what is owed and name the replies owed, nothing more.

## Half 2: the TLDR

A homepage, not a newsletter: **three to six bullets**, each one line, each with a link,
each ending in what it means for the candidate. Fewer is fine. **None is fine.** Filler is worse than
nothing, so a quiet day says "Quiet morning" and stops.

Gather with a cheaper model: one `Agent` call with `model: "sonnet"` (or the
`employer-researcher` subagent for a single employer), given the list below and told to
return items with URL, publisher, publication date and the sentence each rests on. At most
about ten searches in total. You then choose, verify and write.

What counts, in this order. The places, the market and the status to watch are this
search's own: `profile/CLAUDE.md`, "This search's automation", names them.

1. **Employers the candidate is in process with or has a live thread at.** Take them from
   `python3 tools/open_actions.py` (employers first). Layoffs, hiring freezes, a reorg of the
   team they would join, earnings, a new office in their city, a leadership change. These
   are the items that change what they do today.
2. **Their target employers** (`profile/CLAUDE.md` "Target Sectors"): the same kinds of
   news, in their market only.
3. **Their market for the roles they want**: hiring or layoff waves, a central-bank
   decision, sector earnings, a big funding round at a local company in their field (a new
   budget is a new team).
4. **Their work authorization**: any change to the programme or status it rests on. Rare,
   but the one item that outranks everything above.

Rules for an item to go in:

- Published in the last 48 hours (72 on a Monday), and the date checked on the page itself.
- From the publisher's own page, opened and read. A search snippet is a lead, not a source.
- No paywalled guesswork, no rumour, no "sources say" about a specific employer's hiring.
- One line: `<what happened> (<publisher>, <link>). <so what for the candidate>.`
- If an item changes a live application (a freeze or layoffs at that employer), append a
  dated line to that row's `notes` in `job_search_tracker.csv` too.

Write `documents/briefs/<today>.md`: the date, the owed counts and today's top three actions
from half 1, then the TLDR with links. Same file every day, same layout, so it reads as a
homepage.

## Land and deliver

Commit `documents/briefs/<today>.md`, the pack if one was written, and the tracker if a note
was added. Land it per `_common.md`.

The message, under 150 words:

```
<n> replies owed, <n> nudges, <n> intros queued        (or: Nothing due today)
<at most three lines, replies owed first: Name (Company): the ask>

TLDR
- <at most four bullets, one line each, no links in the notification>
(or: Quiet morning)

Full brief and drafts: <PR link>
```
