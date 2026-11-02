# Notes for the next builder

Written at the end of 4.6.0 (2026-11-02) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.6 left.

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
