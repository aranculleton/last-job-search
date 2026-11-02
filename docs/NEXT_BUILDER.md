# Notes for the next builder

Written at the end of 4.6.0 (2026-11-02) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.6 left.

## Do first, for [Unreleased]: fixed rules 4.6 built in that should come from the person

The maintainer, reading the 4.6 notes (2026-11-02): "i thought that was AN example why do we
have dedicated searches or calculations for this... dont different things affect everyones
situation? why would you hardcode this." They are right. Each item below is a rule the app
decides for everyone where the person's own situation should decide. Fix them before
anything else in the next version, starting with the news.

1. **The brief's news is five fixed kinds of search** (`tools/brief.py`, `queries` and
   `NEWS_GROUPS`): employers in play, the right to work, the local market, the central bank's
   interest rates, target employers. The kinds were older than 4.6; 4.6 made them worse by
   building them in further: a hand-written table of central banks (`CENTRAL_BANK`,
   `BANK_DECISION`, `EURO`), a table of country names (`COUNTRY`, `LANGUAGE`), a regex that
   reads the profile's right-to-work line for "visa", "permit" or "status" (`rights_term`),
   a stock field taken from Target Sectors or the first search title, and a weekly rule for
   the rights and bank searches (`since` in an earlier ISO week). A nurse, a lawyer or a
   student on a visa each has different things that move their search, and an interest rate
   is one example, not a category. **Build instead**: what to watch comes from the person.
   When the profile is made or changes, Claude writes the few things that matter to this
   person's search, in their own terms and each with how often it changes (for example
   "NHS band 5 pay talks, monthly", "Graduate visa rule changes, weekly"), into their profile
   (person.json `brief.watch`), shown and editable on the page in Edit the brief, which today
   offers the five fixed kinds under "Also watch". `queries` then reads that list and the
   employers in play, and nothing else; the tables go. An older profile gets its list from
   a profile upgrade, written once in the background, never asked about. Keep the cost where
   it is (at most six searches a brief).
2. **Coming up's English word lists** (`tools/upcoming.py`): a stage is a test if its label
   has "test", "assessment", "case study" and the like (`_TEST`); a screen or a call is 30
   minutes and anything else an hour (`_SHORT`, `minutes`); a place is read from "teams",
   "zoom", "phone", "office" (`_PLACES`). Someone writing their stages in French or German
   gets none of it. The length and the kind should be written on the stage when it is
   recorded (`/outcome`, `register_process`), which knows the invite, not guessed from words.
3. **Fixed windows**: Coming up looks 60 days ahead (`WINDOW_DAYS`); a closing day shows from
   21 days out (`DEADLINE_DAYS`); Today's interview card is the nearest within 7 days, called
   "the prep window" (`weekIv` in `renderBrief`); calendar reminders are an hour before and
   the afternoon before an all-day item (`vevent`'s `VALARM`). None is the person's choice.
   At least the reminders and the prep window belong in their settings, with these as
   defaults.
4. **A time zone word the app does not know gives no time** (`_zone_word`): a guess that any
   upper-case word ending in T is a zone. The zones should come from a full table (the
   standard library's zone names, or the person's own country's zones), not `_ZONE_WORDS`
   plus a rule of thumb.
5. **The strip's day letters are English** ("Mo", "Tu", `DAY2` in `weekStrip`); every other
   date on the page goes through `Intl` in the person's locale. Use `Intl` here too.
6. **Choices made for the person on the Brief**, each reasonable, none asked for: the Jobs
   count in the menu now means only new postings not in a process (`jobToLook`, it used to
   count drafting and ready ones too); the People panel is "Waiting on you" and leaves out
   anyone a step above names; "people replied" became "contacts replied"; Next three tops up
   from To do but skips connection requests and withdrawals (`DUE_SKIP`) and drops a brief
   step that only says to look at jobs when the Jobs panel shows them; the brief's opening
   sentences show only where `brief_link` finds them about nothing shown (one item per
   sentence, so a sentence about two things is judged by one). Check each with the
   maintainer's page before building on it.
7. **One Outlook**: the work-or-school link was dropped on the reasoning that a job search
   does not belong in the calendar of the job being left. Sound for most, wrong for someone
   whose only calendar is a school or work one; if anyone asks, bring it back as a second
   choice under the first.
8. **The fit's numbers** (`fitBrief`): 64px kept clear for the Chat button, each list's fewest
   and starting counts in `data-fit` ("2,3" for People and Jobs, "1,3" for the questions,
   "2,2" for Coming up). Tuned on the sample at three window sizes, not on real data.

## How to work (the maintainer, 2026-10-30 and 2026-11-02)

- **Decide, never ask.** Every design, tooling and gate question is the builder's to settle
  (MAINTAINING.md, "The builder decides"). Make the call, do it, say it in one line, and have
  a reason for it: the maintainer asked in capitals to "genuinely think about things in
  detail from all perspectives", and twice caught a change made without one.
- **Look at the page as a tired job seeker would before calling it done.** For anything the
  person sees, take the screenshots (the harness's `shots` scenario) at 1280x760, 1440x900, a
  tablet and a phone, look at them, and for anything sizeable send a reviewer the pictures
  and ask what a person would misread. In 4.6 that found the same interview shown three
  times, a prep link on the wrong row and a phone tap landing on the wrong link, none of
  which any test caught.
- **Merge to master when green; release only when the maintainer says**, or at once when a
  fix stops something working for people other than them (MAINTAINING.md, "Releasing").
- **Keep it cheap**: few steps, no polling, the whole suite on GitHub only.
- The push gate's denylist is built by the maintainer's copy's own `tools/build_app.py`,
  cached 12 hours in `/tmp/ljs-push-gate`. The name guard stops on any proper noun the app
  never carried: an invented one or an institution goes in `tools/name_guard_allow.txt` with
  what it is; a real place or person in test data is replaced with an invented one.

## What 4.6 decided, to keep

- **Coming up is built from the records on every run** (`tools/upcoming.py`), never stored.
  The only thing kept is what the person adds (`documents/upcoming.json`, merged by id).
  Follow-ups never appear there: they are To do's.
- **Calendars without an account.** A Google link, one Outlook link (outlook.live.com: a
  job search does not belong in the calendar of the job being left) and an RFC 5545 event.
  The host's downloads refuse `.ics`, so the file is a stored zip holding one; if the host
  ever allows `.ics`, save it directly and drop `zipOne`.
- **The Brief says each thing once, by id** (`renderBrief`: `taken`, `itemKeys`, `dueKeys`,
  `upKeys`), in this order: Today's interview (the nearest within 7 days, the prep window),
  Next three, Coming up, Waiting on you, Jobs; the brief's opening sentences last, and only
  those about something no panel shows (the model gives each sentence an item through
  `brief_link`). Never match by words.
- **No panel across a laptop's full width** (the maintainer disliked stretched bars). The
  grid is 12 columns on a laptop and 2 on a tablet; `fillRows` widens the last panel of a
  short row. `fitBrief` grows a list into a row's spare height and shrinks it, only where
  that saves height, to fit the window less 64px for the Chat button; it is worked out once
  per window size and model rev, so nothing moves while the page is used.
- **One button a row on Coming up**: the title opens the thing (an interview its prep), the
  calendar-with-a-plus adds it; "Prepare me" shows only where there is no prep.
- **Jobs counted one way**: `jobToLook` is both the nav's count and the Brief's list.
- **News is the profile's own**: `brief.queries` takes the country's name and central bank
  from the market tables and its own tables, the field from Target Sectors or the first
  search title, and runs the right-to-work and central-bank searches once a week.

## Left, on purpose, with the reason

- **The Interviews view's cards were not reworked.** A user's-eye review said the bin on a
  card (it records "not going ahead") reads as delete, and that `demotePrimaries` leaves
  "Read your prep" dark on a prepared interview while "Prepare me" on the unprepared ones
  goes grey. Both are older than 4.6 and need their own look; the bin is worth moving into
  More with words.
- **The two-week strip has no legend** for a filled dot (a meeting) against a ring (due by
  the end of the day), and a day's contents are said to a screen reader and a pointer
  (`title`) only, not on a touch tap, where a busy day opens Coming up and a free day opens
  Add something.
- **A tablet (760 to 1099 wide) can leave one panel alone on a row**, drawn at both columns.
  Seven panels in two columns leave one over whichever way they fall.
- **Whether the Brief shows a third Coming up card can depend on load timing**: `fitBrief`
  first runs when the Brief draws, and the header's work pill can arrive after. It is stable
  once worked out; the sweep test counts a row the fit hid as fitted, not broken.
- **Coming up is not in the phone's bottom bar**; it is reached from the Brief's panel and
  the footer. Five tabs is the most the bar holds well.
- **The right-to-work news needs a word for the person's status.** `STATUS_NAME` in
  `networking.py` first; else the profile's "Right to work" or "Work authorization" line is
  read for a visa, permit or status. Setup does not write `STATUS_NAME`.
- **A page-only person gets news only when the brief runs**; the daily upkeep never
  searches, to stay cheap.

## Not tested

- The add-to-calendar links were checked for their shape, not opened in Google Calendar or
  Outlook; the zip's `.ics` was read back and checked for the standard, not imported into
  Apple Calendar on a real phone.
- `fitBrief` on a real Claude app window, whose frame is smaller than a browser's.
- What the Everywhere workflow found on the release PR, not fixed in 4.6:
  - Safari (the runner's WebKit 26.0, build 2215), phone, dark only: `test_8` says the To do
    LinkedIn download card now meets promise 8 ("met now: take these out of KNOWN"). It
    passes locally in WebKit in both themes and fails in Chromium if taken out, so KNOWN
    keeps it; look at whether that card's step buttons draw differently in that build.
  - Firefox: `test_reduced_motion_stops_the_spinner_and_the_bar` read the spinner still
    turning once under load; it passes locally on master and on 4.6. Make the test wait for
    the reduced-motion rule to apply rather than read the first frame.
  - The far time zones caught a 4.6 test assuming the device's zone; fixed before merging.
