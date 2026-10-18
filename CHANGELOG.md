# Changelog

> **Claude, if a sync just printed this line and nothing about profile upgrades:** this repo's
> `tools/sync_app.py` was older than the one it brought in, so it could not apply the app's
> improvements itself. Run
> `python3 tools/profile_upgrades.py --after-sync` now and do what it prints. From the next
> sync on, the sync does this by itself.

The app's history starts here. It began as a fork of
[MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) at v1.7.0; that
project's history is archived, unmaintained, in [CHANGELOG-upstream.md](CHANGELOG-upstream.md).
Version numbers here are this app's own and do not track upstream's.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). An entry says what
changed and, where it matters, the failure that caused the change, because that is the part a
future session needs. `tools/sync_app.py` prints the lines a sync brings in, so write each one to
make sense to somebody whose repo just received it.

---

## [Unreleased]

### Added

- **Networking finds people in bulk from any chat, and reads only the best few.** A run makes
  its whole list from the rungs every chat has: your own connections export, search results
  whose own titles name the person and the employer, and a profile check from those titles,
  marked verified, likely or unconfirmed and never more than that. Nothing is fetched from
  LinkedIn, nothing is sent and nothing is asked per person. Reading enriches a short list:
  the best ten in your browser where the chat has one, paced as before, or a paste of the one
  or two who matter most where it has not, never screenshots of everyone. People searches are
  plain words, one title at a time: measured on two employers, that found 14 people at the
  employer where the old searches found 5. Profile upgrade: connections-first (asked once,
  only if you declined the connections export before).
- **A chat says once when it is the wrong place for your settings, and where to go.** If you
  chose to have profiles read in your own browser and a chat cannot reach one, it says once,
  at the end of its reply, that finding people works there, and where reading does: a chat on
  your computer, or that chat from your phone. It decides by what the chat can do, never by
  where it was started, so a phone chat linked to your computer is left alone. A chat on your
  computer lists anything missing, one command each, marked where it asks for your password.
  It offers the choice and never makes it, holds back no work, and changes no setting. It
  runs with every sync, so it reaches chats already open.
- **What the app says about the Claude app is kept in one place, dated and sourced.** Every
  path a message or a doc gives you comes from `tools/claude_surfaces.json`, with the official
  page beside it and the day it was checked, written as where to go "at the time of writing",
  never as a key to press or a button to click. An entry older than 60 days says so before it
  is used, and a weekly check in the app compares each one with its page and with Claude
  Code's release notes.
- **Setting up asks where you will mostly work**, a computer or a phone or the web, with the
  trade-off in two sentences and a recommendation, and gives the exact next step. Profile
  upgrade: work-place (asked once, with the session's other questions).

### Fixed

- **The app runs on the Python a Mac already has.** A Mac's own `python3` is 3.9.6, and
  five places used a keyword that arrived in 3.10. On a Mac that crashed the merge driver,
  so a merge touching the contact book or the message log stopped with one side's copy in
  the file, and it crashed the message checks and the text screen, so some hard cuts were
  not applied. The app now runs on 3.9 and newer, and CI's second leg runs the whole suite
  on 3.9, so this cannot return unseen. On an older Python every tool stops with one
  sentence saying what to install. No profile upgrade: nothing to do in anyone's repo.
- **A merge can no longer leave a state file holding only one side.** When the row-by-row
  merge cannot run (an old Python, a crash, no `python3`), git's own line merge now runs
  instead and marks the conflict in the file. The new driver line reaches every repo on
  its next sync. No profile upgrade.
- **`env_check.py` checks the Python version, pytest and PyYAML**, with the install line
  for each (`pip3 install --user`, no password needed).
- **A new contact-book column goes on the end.** The first save after an update put
  `found_via` in the middle of the header, which rewrote all of a contact book's rows and
  made two chats saving that day collide on every line. Now a new column is added at the
  end, once, with a line saying so. No profile upgrade.
- **A pension plan's full name and its short name are one employer** ("<Name> Teachers'
  Pension Plan" and "<Name> Teachers'"), so the target list and the contact book agree.
- **LinkedIn's first sign-in in the browser pane is a wait, not a stop.** A profile that
  opened on LinkedIn's sign-in or join page used to read as a failed profile. Now Claude
  opens LinkedIn's sign-in page in the pane, says one sentence, and waits, looking only at
  the pane's address, for five minutes before asking once more; nothing is counted against
  the day's reads and nothing is stopped. The pane keeps the sign-in after that. A security
  check, or the sign-in page again after signing in that day, still stops reads for the day.
  `reading.py route` now says which browser it will use and whether it can be used now
  (Claude in Chrome with no Chrome window connected cannot). No profile upgrade.
- **A profile read keeps the headline and the employer on the top card.** The headline was
  taken from the wrong line, and when LinkedIn had not loaded Experience the read had no
  current employer at all. The headline and current role now ground a note, an About is
  clipped like the rest, and a press item older than the posts window no longer does.
  Grounding ignored words that started with a capital letter; it no longer does. Existing
  readings are not re-read. No profile upgrade.
- **A read skips someone your location rules rule out**, and says to check where they work
  when they are somewhere your search does not name, rather than skipping them.
- **`reading.py stop --reason "<words>"` works**, as well as `stop "<words>"`.
- **"Set up my brief" from your computer works.** Claude was told to start the brief's cloud
  chat with `claude --cloud` from its own shell, which that command refuses: it needs an
  interactive terminal. Now it makes the brief itself where its chat has the tool for routines,
  and otherwise asks you once, in the registry's words, to make it in the cloud.
- **"Set up my brief" never makes a second brief.** An existing one is found by your registry
  or by its own stored prompt, never its title, so a brief called "Job search: brief (Mon and
  Thu)" is found as surely as one called "morning brief" (`routines.py brief`). From your
  computer it says the brief runs in the cloud and needs nothing there, and it never makes a
  desktop task, which would run only while the app is open. `claude --cloud` is used only
  where the terminal version is installed: the desktop app alone may not provide it.
- **Work done on your own computer reaches GitHub.** A chat there has no GitHub tools, so it
  works on a branch, merges master in first (so the tracker and contact book merge row by row
  on your computer), and lands it with `gh pr create` and `gh pr merge`. The setup check
  lists `gh` and its sign-in when they are missing.
- **Someone found by name only is marked.** Team pages, press and rosters name people without
  a LinkedIn link; they are now marked `name_only` and ranked down until a profile is found,
  and a name on a page more than a year old is marked to re-check. Why-them uses the headline
  read from their page over an older title in the contact book.
- **A run that cannot fill its batch says so** (`sources.short_batch`): how many it found,
  what each kind of search returned, and the ways to more people, never weaker names.
- **Alumni searches go in the order your alumni have replied**, then by how recently you
  left. The plan's alumni description named the employer people work at now, which is never
  searched. Profile upgrade: alumni-text (Claude rewrites that one description in the
  background).

### Changed

- **Browser reads are paced like a person writing to a few people.** The defaults are 8
  profiles an hour and 15 a day (from 30 and 80), and a day never reads more than the
  connection requests it can still send that day, plus three for people a read rules out.
  The gap between profiles varies around a minute and a half, a longer break comes after a
  varying three to seven, and each page is scrolled to its end at reading pace before it is
  read. A profile that sets its own numbers keeps them. This lowers the risk of a
  restriction on the account; it does not remove it, and LinkedIn's terms forbid automated
  access at any pace.

## [3.2.5] - 2026-10-18

### Fixed

- **Alumni searches reach every employer you have left.** They took the first employer in
  your history twice and nothing else, and the first was usually the one you work at now:
  colleagues rather than alumni, and the people a confidential search should not reach.
  Now every employer you have left gets one search before any gets a second: the one most
  recently left leads, the others take turns behind it a day at a time, and the current one
  (a role whose dates run to "Present", in any language) gets none. No profile upgrade: it reads the role dates already there.
- **Changing one rule puts back only the postings ruled out by that rule.** One number on
  the pay blocker used to lapse every ruling, language and eligibility included, so they
  were all screened again. A ruling now records the part of your rules it rests on (one
  blocker row, the evaluation framework, or one gate setting), named by the reason itself
  ("blocker 4", or the screen's own wording) or with `--rests-on`, and lapses only when that
  part changes. After a change, `exclude.py lapsed` lists what lapsed and what changed, and
  `restamp` keeps the ones that still hold. On a real copy, moving the pay threshold lapsed
  166 of 318 rulings rather than all 318, 58 of them the pay rulings themselves.
  Profile upgrade: ruling-parts (Claude names the part for your older rulings in the
  background).
- **A ruling rewrites only its own lines in `seen_jobs.json`.** `exclude.py` wrote the file
  at a different indent from everything else that writes it, so one stamp rewrote the whole
  file and two chats then had to merge all of it. `--url` picks one of several rulings whose
  reasons are word for word the same, and `review --full` lists their addresses.
- **The suite never reads a checkout nested inside the repo.** A background `/upgrade`
  agent's worktree in `.claude/worktrees/` failed a test over its own copy of the
  CHANGELOG. Every recursive glob in `tests/` now goes through `tests/repo_files.py`, a test
  keeps it that way, and `.claude/worktrees/` is ignored so it is never committed.

### Changed

- **The model check comes with the day's sync.** A script cannot see which model a chat runs
  on, and the line asking for the check was skipped, so `sync_app.py --on "<model>"` ends
  the day's sync with what this model suits and what wants another, and a sync without
  `--on` says to add it. The guide knows Fable: more than any of this needs, with Opus and
  Sonnet named for the work each covers, for less of your allowance. No profile upgrade.
- **The question about reading profiles in your browser says where that works:** a chat on
  your computer in the Claude desktop app. No reminder is added for anyone who already
  chose pasting: that choice was about the risk to their account, and it stands. No
  profile upgrade.

## [3.2.0] - 2026-10-17

### Changed

- **What is ruled out follows your rules, as they are now.** Exclusions used to last for
  ever, whatever had changed since. Every ruling now records what it rests on
  (`tools/exclude.py`):
  - **Ruled out by your screening rules** (the triage blockers, the evaluation
    framework, the gate settings in `search.py`): the ruling lapses when those rules
    change, and the posting is screened again the next time a round finds it. Nothing
    is fetched before then, and editing what to search for never lifts a ruling.
  - **Ruled out in your own words** ("not this kind of company"): it holds until you
    change your mind, and then Claude lifts it in the same turn.
  - **Employer-level rulings** (excluded sectors, declined employers, "no relevant team
    here") were already read fresh every round, and still are.
  - **Older rulings** say nothing about what they rest on, and some are wrong by the
    current rules: a salary below the floor, "7+ years against 4" or a missing
    Master's is now ranked down, never cut. They are reviewed once, in groups, against
    the four hard cuts and your own deal-breakers: what still holds is stamped, the
    rest is lifted, and your own calls are listed for you to check.

  Profile upgrade: rulings-review (Claude reviews your older rulings in the background).
- **Your results feed the rankings.** A networking route whose reply rate clearly
  differs from the rest (enough notes, and a gap unlikely to be chance) moves the
  people on it up or down. An employer that has interviewed you before gives its next
  role a small lift. A skill the score docks a posting for is also treated as a gap
  when the resume and letter are written, so neither claims it. No profile upgrade:
  it reads the state files already there.
- **One definition where there were several.** Parts of the app that answer the same
  question now share one answer, so a fix to one reaches the others:
  - **What counts as a preference** ("preferred", "a plus", "would be a bonus") is
    defined once, and the job score and the skill-gap reader both use it. They used to
    read "a bonus-eligible role requires Python" as if Python were optional.
  - **"Or equivalent experience"** is recognised in every form, everywhere a degree bar is read.
  - **The years-of-experience bar** in the opportunity score is now the entry bar the
    fit score already used, not the highest number in the posting.
  - **Resumes and letters** are checked for a status the profile does not hold (a
    citizenship, say), as every message already was, and an American-spelling profile
    no longer has "analyses", the plural noun, flagged as British.
  - **Networking:** an employer the job search ruled out (an excluded sector, a declined
    employer, a "no relevant team here" entry) gets no searches. A past employer is
    recognised on a profile without its legal suffix ("Oakmere Foods" for "Oakmere
    Foods Ltd"). The careful recruiter test is used when ranking people, so a manager
    "recruiting data scientists" is not ranked as a recruiter. A contact at an employer
    you applied to says so. A call-prep document flags company research more than 30
    days old.

  Measured on a real person's 13 postings and 114 resumes and letters: no score and no
  finding changed. No profile upgrade: nothing to set.
- **Networking finds people where your field names them, says why each one, and writes
  to each in the shape that suits them.**
  - **Where to look is yours.** A LinkedIn title search finds executives and misses most
    of the people who reply. `tools/network/sources.py` holds 26 kinds of public place
    that name people at an employer (team pages, posting contacts for informal
    enquiries, graduate recruiters, alumni features, meetups and professional-body
    committees, speaker lists, trade press and appointments, award shortlists, blogs,
    code, portfolios, papers, patents, official staff directories and registers), each
    checked against its robots.txt and terms. Your own plan picks the ones that pay for
    your field, level and country (`PEOPLE_SOURCES`), and a run works down it inside a
    fixed budget: a few searches per employer, the shared ones once per run, and it
    stops when the batch is full. Everyone found is checked for a LinkedIn profile by
    search, never by opening LinkedIn.
  - **It learns which places pay.** Each contact records where they were found
    (`found_via`, a new column filled in as people are added), and once a source has
    five answered or unanswered first notes, the plan reorders by reply rate.
  - **Why them, in plain words.** `tools/network/why.py` scores each person from 0 to
    100 with one line: a shared employer or school, a hiring post, a role open at their
    employer that you scored well, their function, recent activity, whether you are
    already connected. Plain code, no model call. The batch is read and written in that
    order, and the line sits beside each draft.
  - **A note shaped to the person.** Shared history leads where there is some; their
    talk, post, paper or code leads where there is not; a senior reader gets a shorter
    note with no question; a recruiter gets what they need; someone already connected
    gets a message. The default shape is unchanged, word for word.

  Profile upgrade: people-sources (Claude researches your plan in the background).
  Profile upgrade: connections-export (asked once: your LinkedIn connections, so runs
  start from people you know).
- **Networking limits that let it do real work.** The connection-request budget was 20 a
  week, which one evening used up. It is now 50 a week, half of the roughly 100 LinkedIn
  is reported to allow, and at most 25 sent in a day, because a week's requests in one day
  is a burst. A long run drafts the whole week's budget and says how many can go today; the
  rest stay queued. Drafts are shown five at a time as they are ready. Profile reads go up to
  30 an hour and 80 a day, about one every two minutes, which is enough to prepare a whole
  week's requests in one go. Set your own in `profile/networking.py` (`LINKEDIN_LIMITS`,
  `PROFILE_READS_PER_HOUR`, `PROFILE_READS_PER_DAY`); a setting you already made is
  kept. No profile upgrade: the new numbers are defaults.
- **Research papers as an optional source.** For fields where the people worth meeting
  publish (research science, pharma, academia, quantitative finance), `OPENALEX = True` in
  `profile/networking.py` lets `/network` find who at an employer has put it on a recent
  paper (`tools/network/openalex.py`). Off by default; it needs a free OpenAlex key in
  `OPENALEX_API_KEY` in a cloud session. No profile upgrade: off is the safe default, and
  `/setup` turns it on for a field like that.
- **It runs on your own computer too.** START_HERE.md has the steps: the desktop app's Code
  tab or the `claude` terminal command, your copy cloned to your disk, and "set me up". The
  environment check now says where it runs and gives the install for that machine (Homebrew
  and MacTeX on a Mac, MiKTeX on Windows), and `setup_env.sh` installs Poppler through
  Homebrew by itself. The brief still runs in the cloud: a local session starts a cloud chat
  to set it up. Nothing changes for a repo already running in the cloud. No profile upgrade:
  it is a new place to run the same app.
- **Profiles read on a phone and in a web session too.** Screenshots of someone's profile
  from the LinkedIn app, attached to the chat, are transcribed word for word and read like a
  paste (`reading.py read <id> <file> --source screenshot`): shared history, posts and the
  fit check, with nothing of the person's at risk. It is the route that works wherever a
  session runs. The browser read needs the desktop app on a computer, and a cloud container
  is never given a LinkedIn login. `reading.py route` picks the route by itself:
  - **A browser is there:** read in it.
  - **It can be switched on:** switch it on first.
  - **Neither:** ask once for screenshots on a phone or a paste on a computer.

  The person is never told to press a key or find a setting. No profile upgrade: it is a
  new way to answer the same ask.
- **Networking reads as many people as a batch needs, and moves on from the ones who no
  longer fit.**
  - **No fixed number.** `/network` reads the people a run surfaced, best first, until it
    has as many worth writing to as the run can send, the way a round runs until its yield
    target.
  - **Skip and read on.** After each read, `reading.py verdict` skips someone the page shows
    has moved on, is based elsewhere or holds a role the search filters out. The skip is
    recorded as closed with the reason, and the next person is read instead.
  - **Paced like a person prospecting.** `reading.py gate` holds a varied gap of 25 to 75
    seconds between profiles and a break of two to five minutes every fifth, and caps
    browser reads at 30 an hour and 80 a day (`PROFILE_READS_PER_HOUR`,
    `PROFILE_READS_PER_DAY` set your own; raising them raises the risk to your account).
    `reading.py stop` halts reads for the day on any LinkedIn warning, check or wall.
    A profile is opened once: a fresh reading is never read again in the browser.
  - **Public sources before LinkedIn.** Each person's talks, articles and posts are
    searched first, and someone they show has moved on is skipped without a LinkedIn
    visit. The one browser read keeps the connection degree and whether Connect, Message
    or Pending shows, so a pending request is skipped and a 1st-degree contact gets a
    message rather than a request.
  - **Rosters every run.** Conference speaker lists and the employers' own team pages are
    read alongside the title queries, not only when search runs dry. Measured over five
    employers in one city, title queries found mostly individual contributors and
    managers, the rosters mostly directors and above; neither alone filled every batch.
  - **Cloud sessions.** A cloud session reads profiles in the Claude desktop app's
    built-in browser while it is linked to your computer.

  No profile upgrade: both caps have safe defaults, and the browser question is the
  existing `profile-reads`.
- **Every note is written from what was read about the person, not from a search
  snippet.** Notes drafted from snippets came out alike: one background line with a
  different name on it. `/network` now reads each person before writing to them
  (`tools/network/reading.py`):
  - **Their LinkedIn profile:** read in your own signed-in browser if you say yes
    (`PROFILE_READS = "browser"`), or pasted by you when you open it to send the request
    (select all and copy, or LinkedIn's Save to PDF).
  - **Their public work:** talks, articles, podcasts, code, and their posts as a search
    engine shows them.
  - **What is kept:** only what a note could rest on (shared employers, schools and cities,
    recent posts, public work), each with its source and date.
  - **Checks on every note:** `compose.first_note(reading=)` refuses a common ground nothing
    read supports, and their name or employer alone does not count. `reading.same_ground()`
    catches two notes that say the same thing.
  - **Prep documents** now say what was read.
  - **Notes waiting to be sent are rewritten** this way by `/upgrade` (method
    `network-notes`).
  - A session still never fetches LinkedIn itself: its robots.txt disallows every crawler it
    does not name and a profile request returns HTTP 999.

  Profile upgrade: profile-reads (it asks once whether Claude may read profiles in your
  browser, because LinkedIn's terms forbid automated access and the risk is to your account).
- **Releases, not every merge.** A person's repo now follows the app's newest `vX.Y.Z`
  release, and the maintainer's own repo follows master, so a change runs in the
  maintainer's copy before it reaches anyone else. A repo whose GitHub owner is the app's is
  the maintainer's; `"app_channel": "master"` or `"stable"` in `profile/person.json` overrides
  it. A first sync still takes master, and stable never goes backwards. MAINTAINING.md,
  "Releasing", says when and how to cut one. No profile upgrade: the sync chooses the channel
  by itself.
- **One scheduled task by default: a brief, twice a week, that is about this person's search.**
  A daily brief plus a twice-weekly round was two messages on round days and a message every
  morning. The brief (`automation/prompts/morning_brief.md`) now covers everything since the
  last one, and leads with where the search is: an interview to prep, replies owed,
  applications waiting, or too little going out. Then come what is owed with the drafts, the
  counts since the last brief, three things to do before the next one, and the news that
  matters. It never searches; "find me jobs" in any chat does. Every scheduled run now takes
  the app's updates first (`_common.md` step 2, `sync_app.py --if-stale`), so a copy stays
  current when no chat is opened. The scheduled round stays in the app, optional and off by
  default. No profile upgrade: a task keeps the schedule its person set, and the new brief
  works on any schedule; to move to twice a week, ask any chat to change the brief's days.

### Fixed

- **A slow job board now reaches all its searches over a few rounds.** A board that paces its
  requests used to stop at its 20-minute budget with most of its searches unsent: 312 of 368
  on one, and always the same ones, so its named employers never ran. Three changes, for a
  person's own boards only (LinkedIn and freehire send exactly what they did):
  - **No duplicate employer searches:** an employer already read from its own hiring system
    (`profile/boards.py`) is not searched for again on the board.
  - **No narrower duplicates:** a search a broader one covers is not sent ("senior data
    scientist" when "data scientist" is already there).
  - **Resume where it stopped:** each round picks up where the last one stopped
    (`documents/rounds/.sweep.json`, committed with the round summaries). A board too slow
    even for its first pass rotates through everything, so successive rounds reach every
    search.

  On one real profile this took Job Bank from 368 planned requests to 243. No profile
  upgrade: the next round does it by itself.
- **Reading people: the gaps a first real run found.**
  - **New candidates:** `reading.py add`, `show` and `verdict` now work for a candidate not
    yet in the contact book (`--name`, `--company`); before, only `read` did.
  - **Post dates in words:** a post dated "3 weeks ago" is kept, and so is a post with no
    "posted this" line above it, as screenshots show them. A phrase such as "my 5 years" is
    not read as an age.
  - **Current employer:** found when a role has no employment type ("Title / Company /
    dates").
  - **Cut text:** the About excerpt is cut at a word, not mid-word.
  - **Dates on public finds:** a reading made only from public finds carries the date they
    were found, so prep documents no longer say "read undated".
  - **When people search runs dry or the search tool declines:** `/network` goes to the
    person's connections export, then rosters, then LinkedIn's People tab in their browser,
    and never rephrases a declined query.
  - **Read-only rule:** a test now fails if any flow that names a browser tool lacks it.
- **A chat kept open for days now gets the updates.** The sync ran only at the start of a
  session, and most people never start a new one: a chat carried on for days pulled neither
  master nor the app's updates after its first hour. `tools/sync_app.py --if-stale` does a
  session's first two steps (master, then the app) once a day and is a no-op after that, and
  CLAUDE.md asks for it before each piece of work. `run_round.py` and `stage_picks.py` print a
  reminder when it has not run today, so even a chat whose instructions predate this is told.
  No profile upgrade: nothing to do, the sync that brings this in is the last one a long chat
  has to be asked for.
- **The reminder reaches a day with no search in it, and new rules reach an open chat.**
  `open_actions.py`, `followups.py` and `network/state.py` print the same once-a-day reminder
  as a round, so someone who only networks or asks what they owe is told too. When a sync
  changes CLAUDE.md or AGENTS.md, it says so and asks the chat to read it again: commands and
  skills are read fresh each time, but those two are read once, when a chat starts.
- **Workday boards that leave the location out of their listing.** Every posting came back
  with a blank location, which the place filter reads as nowhere, so a large board narrowed to
  one country returned 154 postings and kept none. The location is now read from each
  posting's path (`/job/<place>/...`), in `ats_boards.py` and the vendored openroles (0.1.2).
  The `boards` method is at version 7 with `rerun`, so every older repo re-checks its boards
  once: a board probed as "0 in range" for this reason now counts. No profile upgrade: a
  method version is redone by `/upgrade` in the background, with nobody asked.
- **The documentation says what the code does**, from the search budget and the rulings to the connectors, the brief's set-up and the local install, where `./tools/setup_env.sh` now installs Bun too.

## [3.1.0] - 2026-10-15

### Changed

- **Other agent tools have a way in.** `AGENTS.md` now says how to run each part in Codex,
  Gemini CLI, Cursor or Antigravity: which files to read, the slash commands as procedures,
  the subagents and the drafting workflow done by hand, and the scheduled brief run yourself.
  A new `GEMINI.md` points Gemini CLI to it. The README and START_HERE say plainly that the
  requirement is Claude Code, which has no free tier, and point anyone on another tool to
  `AGENTS.md`.
- **CONTRIBUTING.md is for visitors now.** It says what to send (issues with a bug or an idea,
  fixes as a diff in an issue, links to ports for other agent tools) and why outside pull
  requests are not merged. The maintainer's guide that used to be there is `MAINTAINING.md`,
  unchanged, and CLAUDE.md points to it. The issue form no longer calls the tracker private or
  sends people to the upstream project.
- **Finding an employer's board, and Lever's full postings.**
  - `python3 tools/ats_boards.py --find "<Employer>"` (or its careers page URL) finds an
    employer's Greenhouse, Lever or Ashby board and counts what a round would get from it.
    The finding is [openroles](https://github.com/aranculleton/openroles), the open-source
    library this reader grew into, vendored in `tools/openroles/`, so nothing new needs
    installing. A round still reads boards with `ats_boards.py` itself.
  - Lever postings now include their requirement lists. Before, only the intro was read, so
    a Lever role was scored without its requirements.

### Fixed

- **The docs now say what the build does, and newcomers get a plain-English start.**
  - *README and START_HERE* are rewritten for someone who has never met the maintainer:
    what you need, three steps, what to say to it, and which model suits what.
  - *Person-facing guides* (SETUP, RUNBOOK, SECURITY, ARCHITECTURE, CONTRIBUTING,
    documents/README, automation/README) are corrected where they disagreed with the
    code. Fixes include:
    - installing from `requirements.txt`;
    - what a round keeps, and that `--from-scraped` needs `--keep-intermediates`;
    - `CV` filenames, the chase rule, what `/notion-sync` sends, and where portals are
      switched;
    - note limits by LinkedIn plan, and the full cut list;
    - an automation set-up with no schedule to type. Personal changes to a routine now
      go in `profile/CLAUDE.md`, because a sync puts the app's prompt files back.
  - *Commands:*
    - `/add-template` keeps templates under `profile/`;
    - `/reply` logs only what went and sets the statuses the log cannot know;
    - `/outcome` uses `followups.py`'s clock;
    - `/rank`, `/notion-sync` and `/apply` read scores from `documents/rounds/`;
    - every command that writes reads the learned brief first;
    - `/apply` and `/interview` use the research and grounding agents by name;
    - `/html-report` sends the file;
    - `/network` records a sent note;
    - a lost "/setup Path A" hand-off is gone.
  - *Skills:*
    - connection-note limits (200 free, 300 Premium);
    - the cut list and the salary flag on the top of the range;
    - suppression by sent rows only;
    - years bands measured against years held;
    - consistent summary, bullet and letter rules;
    - real-search examples replaced with invented ones.

### Changed

- **Every session starts lighter, and says which model suits the work.**
  - *CLAUDE.md is about half its old length* (from roughly 9,800 words to 5,400). Every
    session and every compaction loads it. Sections only one kind of work needs moved, word
    for word, to the files that work reads:
    - the verification checklist to
      `.claude/skills/job-application-assistant/verification-checklist.md`;
    - the developer rules and private-repo CI to `CONTRIBUTING.md`;
    - the tools table and "documents for someone else" to `RUNBOOK.md`;
    - the full search rules to the job-scraper skill.

    CLAUDE.md keeps a short summary of each, and says when to read the full version.
  - *Which model:* `python3 tools/model_guide.py <work> --on <model>` says in one line when
    the session's model is more than a piece of work needs, or less. It says nothing when
    the model fits. `--all` prints the table. It names tiers, not versions, so a new version
    changes nothing. It never guesses at a model family it does not know.

### Fixed

- **Several chats open on one repo no longer trip over each other.**
  - *Updates:* when an update brought upgrades in, every open chat started the same
    background /upgrade and asked the same questions. Now only the chat whose own sync
    brought it in does. The others say "being applied by the chat that brought this update
    in" and stay quiet, and take over after two hours if anything is still pending.
  - *State files:* two chats that each logged a message, added a tracker row or ruled out
    a posting met as a merge conflict. The tracker, contact book, message log and
    `seen_jobs.json` now merge row by row (`tools/merge_state.py`, which every sync wires
    into git). Rows and notes from both sides are kept. Git stops only where both changed
    the same field of the same row two ways.

- **What a line-by-line audit of a real repo found, fixed.** Each was reproduced on real
  input first.
  - *Search:*
    - "<City>, ON, CA", the way Dayforce, SmartRecruiters and Workday write a Canadian
      location, was failed as "US on-site" ("CA" read as California). A country code beside
      a home region or city is now the country.
    - The home region written twice ("<Region>, <code>, <Country>") passes as home.
    - A list naming home and another country is flagged for the posting body to decide.
    - US-remote rows from a remote search are marked remote, so they are no longer failed
      as on-site.
  - *Old exclusions:* those citing a years bar, or only the name of the stage that wrote
    them, stopped blocking roles the current rules merely rank lower. A stated range or a
    required degree the person's own triage card knocks out still stands.
  - *Eligibility:* the gate now cuts "not open to work permit holders", "unable to sponsor
    a work visa", a requirement in a sentence that mentions "private equity", and a
    requirement to live in another country ("must be based in the US or Spain"). A list
    that includes your country passes.
  - *Reading postings:*
    - "asset" and "bonus" count as preference only as "is an asset" or "would be a bonus",
      so "required for our asset management team" is read as written.
    - A loan size or portfolio value is no longer read as the pay band.
    - "Long Name (LN)" joins "LN".
    - A preferred degree is never "do not apply".
  - *Employers and relisted roles:*
    - An employer where you are mid-interview keeps holding off new roles there, however
      long the process runs.
    - A role already applied to does not come back once its application closes.
    - Greenhouse rows are dated by first publication, not last edit, and Lever rows now
      carry a date.
    - A live contact softens the gap penalty in a round, as documented.
    - On a slow board, the named-employer searches run before the outlying places.
  - *Documents:*
    - One refused outreach note no longer stops the batch or leaves a half-written file;
      its `outreach.md` says it is not ready.
    - "8+ years" and "9 per cent" are checked against the profile.
    - A draft with no posting text says so instead of rendering untailored, and a kept
      draft renders through the same loader everywhere.
    - The deadline reaches the tracker.
    - The spelling check catches "-ises", "-isations" and plural American forms.
    - A rejected draft is never rendered.
    - A third letter paragraph the template cannot place is refused rather than silently
      dropped.
    - A letter that already fits the page keeps its opening paragraph whole.
    - The bullet split no longer swings on a fraction of a point, and filenames no longer
      end on "of".
  - *Networking and learning:*
    - "No action unless they reply" now does what it says.
    - A thread closed after the last reply (a dated close in `outcome`) is not reported as
      reopened.
    - A catch-up message is not counted as a connection request.
    - A hiring manager whose snippet says "recruiting" is not a recruiter, and plain job
      asks ("I'd love to apply", "consider me") are caught in a first note.
    - An interview stays an interview after a later rejection, a draft is credited only to
      its own role, and `/outcome`'s audit line reports the row it recorded.

- **Networking: nothing it suggests sending is something that cannot be sent.** From an
  audit of a real contact book:
  - A connection request nobody has accepted is no longer listed as a nudge: there is
    nowhere to write. After 21 days it is listed as one to withdraw.
  - Someone who accepted a request that carried no note is owed a first message, not a
    nudge on a note that was never sent.
  - A call or meeting in the log is not a message. A held one counts as a conversation, so
    the thread no longer "goes silent" the day after you spoke.
  - A nudge opening on a one-word name keeps its capital ("Hi Robin, Larkspur opened...",
    not "larkspur"). The check knows your employers, skills and every company in your
    contact book and tracker, and `validate()` flags a name it lowercased.
  - `validate()` refuses check-ins ("just checking in", "bumping this", "did you get a
    chance"). "Any update on the timing?" in a reply is still fine.
  - Tier 1 means a hiring post about your own work. "Our marketing team is hiring a
    content writer" from a data director no longer counts.
  - The question at the end of a first note is optional. A true line and a plain ask for
    a conversation make a complete note; a question made up to fill the slot is what
    read as artificial. A test of your own that requires the question needs updating to
    match.
  - Saving the contact book or the message log keeps the file's own line endings. A file
    saved from a spreadsheet used to be rewritten in full on every save, which is how
    two chats each logging a message collided on every line.
  - Greetings: "J. Smith" is "Hi J. Smith," and "Dr Smith" is "Hi Dr Smith,". A
    credential is never read as a first name.
  - A close you chose, written "closed on purpose: <reason>", is no longer reported as
    reopened on every run. A close without those words that is followed by a reply still
    is, because that catches a chat that closed someone by mistake.
  - `tools/network/state.py` lists employer names that are probably one employer and do
    not join ("Fernhill" and "Fernhill Freight"), never merging them, so you can add the pair
    to `COMPANY_ALIASES`.
  - `tone.DATA_DRIVEN_RULES` names the rules that fire only on your own data, so a test
    of your own that gives every rule a case can leave them out.

- **"Draft 1 and 3" works after every round, and in a later session too.** Each round's
  clean-up deleted the shortlist file drafting is staged from, so picking from a shortlist
  that had just been sent failed. The round now keeps it (the top 60, in the gitignored round
  folder), and in a later session, when that folder is gone, staging reads the committed
  `documents/rounds/<round>.json` and fetches each pick's posting from its board.
- **A single /apply now goes through the same pipeline as a batch.** It wrote the resume and
  letter by hand, so it skipped the bullet allocator, the layout the renderer enforces,
  `verify_batch.sh` and the kept `draft.json` (which is also what lets a result teach the
  next draft). It now stages the one posting (`tools/stage_picks.py single`), drafts with the
  same research, draft and grounding-audit stages, renders with `fit_to_page.py` and records
  the row with `record_drafts.py`. Its plan also asks whether you have already applied. Hand
  drafting remains only for a custom template from /add-template.
- **One folder per application.** The commands looked for `<company>_<role>/` while the
  tools wrote `<company>_<role>_<abbr>/`, so /outcome and /interview could start a second
  folder beside the real one. Every command now asks `tools/outreach.py --folder`, which
  finds the folder already on disk under either name.
- **The drafting workflow works in your repo, wherever it sits.** It sent every agent to a
  fixed path that only existed in the app's own container.
- `tools/fleet.py` counted only squash-merged pull requests, so a repo that merges the usual
  way was told nothing had come through a pull request.
- `/reset` now removes everything that is yours: each contact's folder under
  `documents/network/`, `documents/others/`, your own job boards, `networking/`,
  `gmail_sync/`, and the Notion sync record.
- The end-of-session commit now includes `profile/` (what you have taught it, and facts
  written back) and `company_research/`.
- No em dashes left in the skill documents, including the report /upskill writes, and two
  examples left over from the original project's own search are replaced with invented ones.

### Added

- **It learns what works from your results, with nobody having to say so.** Which messages
  drew a reply and which applications reached an interview were already on record, and
  nothing read them back. `tools/what_works.py` now does, by counting: no model call, and no
  file of its own to fall out of step. Before a message is drafted, it shows the ones that
  got answers, closest first, and drafting matches their shape (length, opening move, the
  question asked), never their words. Before /apply drafts, it shows the applications that
  reached an interview, with the summary and bullets their resume used, and those bullets get
  a small, capped lift in the allocator so the next resume for a similar role leans the same
  way. When a result arrives (/outcome, or /reply logging their reply) a one-line audit says
  what that result had and what the rate is now. A difference (alumni against cold, short
  against long) is reported only when both groups are big enough and the gap is unlikely to be
  chance; until then you see the examples alone. Messages are now logged with their full
  text, because one logged without it can never become an example. No profile upgrade: it
  reads what is already there.
- **It learns you, and keeps what it learns.** The defaults (the voice of a first note, the
  interview questions, who is worth contacting, how roles rank) are still where you start.
  Now every reaction you give outranks them and is kept for good in `profile/learned.json`
  (`tools/learned.py`). That covers "too formal", "not this kind of company", "stop
  suggesting recruiters", or an edit you make to a draft. Each reaction is applied at once,
  written into the setting it governs, and read before anything is drafted. Phrases you
  never want are flagged in every message and document. After drafts, messages, shortlists
  and questions, you are asked in one line whether you'd like anything different. No sync
  touches `learned.json`, and no upgrade changes a setting it records. When the app
  improves something you have shaped, you are offered the new way once (keep yours, or
  switch), never switched over. The greeting and the referral-ask wording are now settings
  (`GREETING`, `REFERRAL_LINE`, `REFERRAL_CLOSE` in `networking.py`), defaulting to today's
  words. Profile upgrade: learned-choices.
- **Every output is shown in the reply.** Messages, drafts, notes, interview packs and prep
  documents are pasted ready to use, and resumes and letters are sent into the
  conversation as files. A path in the repo is the record, never the answer.
- **Every improvement to the app reaches what you already have, by itself.** A sync always
  brought the app's new code, but not what the old code had already made: the profile your
  `/setup` wrote, the job boards it built, your call-prep documents, drafts not yet sent,
  postings ruled out under older rules. Those stayed as they were, and nothing told you the
  app now did them better. Every part of the app that leaves something in your repo is now
  versioned, and your repo records which version made what it has
  (`profile/build_versions.json`). When a part gets better in a way worth redoing, it is
  redone with no one asking: `/upgrade` in the background for a part of setup, the boards,
  drafts, interview packs, research, contacts or upskilling plans; the sync itself for
  prep documents; every round for postings ruled out by an older screen. A profile with no
  record is dated from when it was made, so one set up on the first release redoes every
  part of setup improved since, starting with your job boards. A redo adds and corrects but
  never removes: a value it would change goes beside yours as a question. Anything that
  needs your consent (your scheduled tasks) is asked, a few at a time. Changing how any part
  is done, or adding any file to the app, now fails the app's CI until that decision is made.
  No profile upgrade: this is what lists them.
- **Profile upgrades apply themselves.** Listing what a profile was missing and waiting for a
  yes meant nothing happened: nobody knows which of nineteen upgrades matter, so nobody asked.
  Now, when the sync lists any, Claude starts `/upgrade` in a background agent and gets on with
  what you asked; it researches and builds your job boards, writes the settings your field needs
  and the rest, from your profile, one commit each. At the end of its reply it tells you what
  changed and how to undo each (`git revert`). Only what needs you is asked, at most three
  questions at the end of a session: whether to read your LinkedIn job alerts, and every fact
  in your profile still marked `[CONFIRM: ...]`, which is now asked until it is answered instead
  of waiting for someone to run `/setup` again. The twice-weekly shortlist takes the app's
  updates and applies the upgrades before its round, so a board it builds is searched that
  round. The morning brief is unchanged.
  No profile upgrade: this is what applies them.
- **Profile upgrades: what the app added since you set up, and what it needs from you.** `/setup`
  runs once, so a part of the app that needs something on your side (your job boards researched,
  a setting with no safe default, a portal rebuilt) never reached a profile written before it.
  `tools/profile_upgrades.py` checks your repo for each one, and every sync now ends by listing
  what is pending, with what runs it and how long it takes; the twice-weekly shortlist carries
  the same line. **If you set up before 15 October 2026,** your next sync lists the upgrades
  waiting for you. This sync is the old copy of the sync and cannot, so the session runs
  `python3 tools/profile_upgrades.py` once to see them now. Nothing runs without a yes
  (superseded: upgrades Claude can do alone now apply themselves; see the later entry).
  No profile upgrade: this is what lists them.
- **Your LinkedIn job alerts can feed every round.** LinkedIn's alert emails are its own match
  for you, and they carry roles a keyword search ranks out of reach. Set `JOB_ALERT_QUERY` in
  `profile/search.py` (off unless you set it, because it reads your inbox) and the job round
  searches Gmail for those emails only, `tools/job_alerts.py` takes the job ids from them and
  fills each posting from LinkedIn's own page, and `run_round.py --alerts` screens and scores
  them with everything else. Built and tested on invented alert emails; the LinkedIn fetch was
  checked live. If your first real alerts yield nothing, say so: the id pattern is the one
  thing a real email could prove wrong.
  Profile upgrade: `job-alerts`.
- **Every round searches the job boards built for you.** A portal made by `/add-portal` for
  your country, field or level used to run only when you typed `/scrape`; `tools/scrape_wide.py`
  called LinkedIn and freehire by name and nothing else. Now any portal that is on and follows
  the portal contract is searched, health-checked and hydrated in every round, scheduled ones
  included, each kept to the `crawl-delay` its `SKILL.md` declares (one request a second when
  it declares none), on its own thread so LinkedIn and freehire send exactly the requests they
  did. A portal is called only when its `SKILL.md` says `contract: 1` (`/add-portal` writes it
  once the CLI takes the round's flags). A board that fails three requests in a row, or runs
  past 20 minutes, is stopped and the round goes on; its detail fetches get 15. `PORTAL_LOCATIONS`
  in `profile/search.py` gives a board its places as it writes them.
- **`/setup` researches and builds your boards.** It finds the boards that serve your country,
  city, field and level, checks each one's robots.txt, builds the best one or two with
  `/add-portal`, and records every board it looked at, built or not, with its source, in
  `profile/search.py` `PORTAL_RESEARCH`. `python3 tools/portals.py` lists the ones with no
  portal, and a round that misses its yield target names them.
- **`START_HERE.md`**, the five steps from this page to a working search, in plain words:
  make a private copy with "Use this template", let Claude see it, set up the cloud
  environment (the setup line and the job-board domains), say "set me up", and use it.
  Linked from the top of the README.

### Changed

- **The app ships no country's job boards.** The four Danish portals (`jobindex-search`,
  `jobnet-search`, `jobdanmark-search`, `jobbank-search`) are deleted: the app is for anyone,
  anywhere, and a board for one market belongs to the people in it. The app keeps
  `linkedin-search` and `freehire-search`, which work in any country. Every other folder in
  `.agents/skills/` is now yours (`tools/personal_paths.py`): a sync never touches it or calls
  it drift, and the app's leak scan fails if one reaches the app. **If you search Denmark and
  had one of the four on,** this sync deletes it. Build it again with `/add-portal`, which makes
  it a portal every round searches. Putting the old one back (`git checkout <this sync's
  commit>^1 -- .agents/skills/<name>`) gives one `/scrape` can run by hand only: it predates
  the portal contract, so rounds skip it.
  had one of the four on,** this sync deletes it; put it back as your own with
  `git checkout <this sync's commit>^1 -- .agents/skills/<name>` and commit, or build it
  fresh with `/add-portal`.
  Profile upgrade: `missing-portal`.
- **The screen's job-family flags and two networking reasons are your profile's.**
  `tools/score_posting.py`'s wrong-family and homonym flags ("reporting and dashboard building
  is the whole job", "'modelling' here is valuation") were an analyst's, and the networking
  revenue-role reason said "dressed as technical" to everybody. They are now `SCREEN_WRONG_FAMILY`
  and `SCREEN_HOMONYMS` in `search.py` and `NOT_HIRING_REASON` in `networking.py`, with neutral
  defaults; `SPAM_BULK_ROLES` in `networking.py` can take your own job off the staffing-spam
  list. **If you are an analyst and want the old flags**, copy the example's
  `SCREEN_WRONG_FAMILY`, `SCREEN_HOMONYMS` (`profile.example/search.py`) and
  `NOT_HIRING_REASON` (`profile.example/networking.py`) into your profile.
  Profile upgrade: `screen-flags`.
- **`person.json`'s keys are listed with everything else.** `python3 tools/profile_names.py
  person` shows every key a tool reads, whether it is needed or optional, whether the example
  sets it, and where it is read.
- **The evaluation template is written for any work status.** `04-job-evaluation.md` assumed a
  permit holder; a citizen now writes one line, and a free-movement row covers EU/EEA and
  Swiss, Common Travel Area and Trans-Tasman citizens. **If your profile is a citizen's and
  was written from the old template**, nothing breaks; `/setup --section market` rewrites it.
  No profile upgrade: nothing breaks, and the rewrite only tidies a citizen's eligibility gate.
- **Scheduled briefings have two set-ups that work, written out step by step.**
  `automation/README.md` now walks through **(a)** one chat per task ("Job search: morning
  brief", and "Job search: shortlist" for the twice-weekly round, whose key and prompt file
  stay `job_round`), created with your private repo and each task bound to its own chat,
  whose reply is the briefing; or **(b)** each task made in the
  Claude app's Routines screen with the repo ticked and notifications on, for a push. It
  gives the exact prompt each task stores (`python3 tools/routines.py stub <key>` prints
  yours) and how to test without `fire_trigger`. `_common.md` makes the final reply the
  message and depends on no relay. **If your registry has an `ops_session` and a relay**,
  nothing changes for you: that older set-up is still recognised and still relays, and
  the README says why never to rebuild that chat (a chat made now is refused the hand-off).
  `python3 tools/routines.py check` validates `profile/routines.json` (prompt files exist,
  ids well formed and unique, every cron carries `CRON_TZ`), and `ci_local.sh` runs it.
  A long-lived scheduled chat is capped with `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000` on a
  cloud environment only those chats use; the app's `.claude/settings.json` is synced to
  everyone, so a per-model cap there would squeeze every chat on that model.
  No profile upgrade: scheduled briefings are optional, set up from `automation/README.md`.
- **A profile without employer tiers can meet the yield target.** `tools/fit.py` divided
  opportunity by a fixed 130 before multiplying it into priority, a number calibrated on a
  profile with tiers, leverage and core capabilities. Without them opportunity tops out at
  58, so no posting ranked above about 45 and every round reported MISSED after three
  expansions. The divisor is now 130 or the most your profile can score, whichever is lower
  (`opportunity.SCALE`; `OPP_SCALE` in `search.py` pins it). **A profile that can score 130
  ranks exactly as before**; one that cannot sees every priority rise in proportion, in the
  same order.
- **Networking looks for your colleagues, not a data team's.** `/network` searched every
  employer for data scientists, counted only data titles as "in function" (so a nurse's run
  would write every employer off as having no relevant presence), and read "I'm in
  marketing" in a reply as a mismatch for everybody. `profile/networking.py` now holds
  `TITLE_SETS`, `FUNCTION_TITLE`, `HANDS_ON_TITLE`, `HIRING_ROLE_NOUNS`,
  `HIRING_HEADLINE_NOUNS`, `OTHER_FUNCTIONS`, `OTHER_FUNCTIONS_MOVED`, `OWN_FUNCTION_WORDS`
  and optionally `NOT_HIRING_TITLES` (`None` for someone in sales).
  **After this sync, add them to your `networking.py`**: `/network` refuses to search
  without `TITLE_SETS`, and without `FUNCTION_TITLE` every in-market manager counts as in
  your function. `profile.example/networking.py` shows the shape (a data team's values).

Found by a sweep of the whole app for anything that assumed a data analyst a few years in,
in North America. **Nothing to do unless a default below is wrong for you**; each is a
setting now, and `python3 tools/profile_names.py` lists every one.

- **Experience thresholds are measured from your own `YEARS_HELD`.** They were fixed at 7, 9,
  11 and 13 years in `tools/fit.py` (6, 8 and 10 in `tools/opportunity.py`, and the screens'
  flags likewise), which is right for someone with four years: twenty years' experience lost
  points on "10+ years", and a new graduate lost nothing on "6+". If your scores move after
  this sync, this is why, and it is the fix.
  No profile upgrade: every profile already sets `YEARS_HELD`.
- **`/interview` uses your own STAR examples** (`profile/07-interview-prep.md`). It read the
  app's guide, whose examples belong to the fictional example person. And `/apply` drafts your
  summary from the profile statement templates in your `profile/CLAUDE.md`, never from the
  example person's in `05-cv-templates.md`. If your `profile/CLAUDE.md` has none, add 2-3.
  Profile upgrade: `interview-prep`.
- **Your resume's page count and section order** are `documents.resume_pages` (default 1)
  and `documents.section_order` (default summary, experience, skills, education,
  certifications) in `person.json`; `fit_to_page.py` and `verify_batch.sh` follow them. A
  recent graduate can lead with education; a long career can take two pages.
- **The letter's "Dear" and "Page"** are `documents.salutation_prefix` and
  `documents.page_label`, for a letter in another language.
- **Your weekend** (`search.py` `WEEKEND`, default Saturday and Sunday) sets every
  business-day follow-up date. **Contract work** is docked 6 unless `OPP_CONTRACT = None`.
  `MANAGES_PEOPLE = True` stops the screen flagging roles with direct reports. The portal
  health probe's word is `CANARY_QUERY` (default "data").
  Profile upgrade: `market-week`.

Found by the first person set up outside data analysis. **If your profile was written before
this, three things to do after this sync**, all in `profile/`:

- **Your resume's Skills headings are yours now, and a resume will not render without them.**
  They were hard-coded as a data analyst's ("Languages and modelling", "Data engineering and
  cloud", "BI, tooling and delivery") and printed on everybody's resume. Set `LABELS` in
  `skills.py`: one `(line, heading)` per line, in your own words; `MERGE` and `MAX_PER_LINE`
  are optional (`profile.example/skills.py` shows the shape). Rendering stops with
  `NoHeadings` until you do.
- **No title is docked for its level unless your profile says so.** `tools/fit.py` docked
  every junior, graduate, intern or trainee title 25 points, and `tools/opportunity.py` docked
  those 25 and director, head-of and principal titles 12, for everybody. They now read
  `FIT_BELOW_LEVEL`, `OPP_BELOW_LEVEL` and `OPP_ABOVE_LEVEL` from `search.py`. If you are
  mid-career and want the old behaviour, copy the three patterns from
  `profile.example/search.py`. **If you cancelled the junior penalty in your profile** (a
  bonus for junior titles, say), take the cancellation out, or junior roles now score high
  twice over.
  Profile upgrade: `level`.
- **Your bullets' themes can be your own.** `tools/allocate.py` matched postings only against
  a data analyst's theme words, so a theme outside them scored nothing and bullets were picked
  on weight alone. Add `THEME_CUES` (theme -> the words postings use for it) to `bullets.py`;
  `python3 tools/allocate.py` names every theme no cue matches.

- **Every portal has a switch that works, and it is the person's.** The `enabled:` flag in
  a portal's `SKILL.md` used to switch off nothing a round did, because
  `tools/scrape_wide.py` called LinkedIn and freehire by name. It, `tools/hydrate.py` and
  `/scrape` now ask **`tools/portals.py`**: the `SKILL.md` default, then the person's
  `PORTALS` in `profile/search.py` (`{"linkedin-search": False}` turns LinkedIn off). A
  portal that is off is sent no search, probe or detail request. **`linkedin-search` and
  `freehire-search` are on by default**; `/setup` tells the person that LinkedIn's
  robots.txt disallows the guest endpoints the search uses, and the choice is theirs.
  `python3 tools/portals.py` prints what the next round searches and why.
- **A4 or US Letter follows the country.** `person.paper()` prints on US Letter across most
  of the Americas and A4 everywhere else, from `identity.country` in `person.json` (or
  `search.py` `PORTAL_COUNTRY`). `documents.paper` and `documents.letter_paper` still win
  where set, so **if your profile sets them only because the app once needed it, remove
  them** and let the country decide.
  Profile upgrade: `country`.
- **The guides no longer steer towards data work.** The networking skill and discovery
  playbook, the writing style's role-type language, `/expand`'s competency taxonomy and the
  upskill skill use field-neutral wording, with examples from several fields.
- **`/setup` writes `profile/` and nothing else.** It refuses the app itself and any public
  repo before a word is written, asks the person only plain questions about themselves,
  researches their market (boards, employer ATS, eligibility wording, pay, document
  conventions, place names) and writes every profile file in the shape of
  `profile.example/`, plus empty state files. It used to edit the app's own skill files,
  CLAUDE.md and the example CV, which the next sync would undo.
- **`/reset` has a `state` scope** and removes `profile/` whole rather than blanking files.
  It never deletes the app's templates and fonts.
- SECURITY.md, SETUP.md and the README describe the app as public and a person's copy as
  private.

### Fixed

- **Regressions from the networking rework, caught by a person's own profile tests.**
  - A first note or InMail with no opener read "Hi Robin, Saw the post": the clause after the
    greeting comma is lowercase again.
  - "Hiring in <City>, <Other City> or remote" read "remote" first and lost tier 1; the named
    city is read first.
  - "After 6 years at <Employer>, on to the next thing." is a departure again; the list of
    leaving phrases is wider.
  - "We are not hiring on my team right now." is a no again ("my team" had excused it), so
    the stop-after-two-nos rule fires. A no is excused only by an offer to talk, a booking
    link or an address to write to.
  - "<City>, ON", the ordinary Canadian form, read as another country and ranked the person
    last. A location is abroad now only when it names a country the profile lists as not
    home, so postal abbreviations need no place in `REGION_WORDS`; a short word there ("on",
    "in") is no longer matched as a word in posts. Remove any abbreviation added to
    `REGION_WORDS` as a stopgap.
  - Triage's working fields can no longer become columns in `network_contacts.csv`; columns
    added by hand in the file are still kept.
  - `/network` shows each person with their message, ready to paste, in the same reply.
- **Postings blocked for good by a skip that was never a verdict, and internal postings
  surfaced.** `seen_jobs.json` skips the throttle derives afresh every run blocked their
  postings permanently: a referral hold kept 59 postings at one employer out for a month
  after the referral had converted, and a do-not-target entry's skips outlived its review
  date. A referral hold, do-not-target, the company throttle, a same-employer duplicate
  and the candidate's bar no longer block from the record (the live hold is applied at the
  prefilter instead, so they still cost no fetch while it lasts), and neither do older
  rounds' queue decisions ("not scored this round", "never read by a model"); an
  `excluded` entry citing any of them is treated the same. A posting on a Workday
  internal site (`/Privileged/`), which an outside applicant cannot use, is dropped at the
  prefilter with the reason `eligibility: internal Workday site`; a profile can name its
  employers' other internal sites in `search.py` `WORKDAY_INTERNAL_SITES`. No profile
  upgrade: both take effect on the next round.
- **Finding people: the same person twice, the wrong people as tier 1, employers written off
  on nothing.**
  - "Already contacted" matched on names alone. A name in another script reduced to
    nothing and matched the first person at that employer; "Søren Møller" and "Łukasz"
    lost letters; the profile URL every result carries was never compared. It now
    matches on the URL first, keeps every script's letters, and folds ø, ł, ß and the rest.
    Employers key alike written with "&" or "and", with accents or without.
  - Tier 1 is a live hiring post about your own work: another job seeker's "I'm looking
    for my next opportunity", a marketing director's "we're hiring", a remote role in
    another country and an undated headline no longer count. Post permalinks, where those
    posts live, are kept with their exact date instead of being filtered out.
  - A result with no location is kept as unverified, not read as somebody elsewhere; an
    empty search records nothing; "no relevant presence" holds for 90 days, not for ever.
  - Places match on whole words: Aylesbury is not Bury, Manchester, New Hampshire is not
    Manchester, and a home city of two words gets its metro.
  - A hiring post with a few emoji and an in-house recruiter are no longer dropped as
    spam, and "after 8 years at Acme I lead data" is tenure, not a departure.
  - Searches use the employer's everyday name, alumni are searched once per run, drafts
    are kept in `documents/network/<id>/draft.md`, and LinkedIn's connections export in
    `documents/linkedin/Connections.csv`, if you add it, puts the people you already know
    first. No profile upgrade: the new title settings default to the English ones.
- **Networking messages you could not send, and replies read the wrong way round.**
  - Connection notes were capped at 300 characters and InMail drafted for everyone, which is
    a Premium account's limits: a free account (a 200-character note, a handful of
    personalised notes a month, no InMail except to an Open Profile) was handed drafts it
    could not send. The limits now follow your LinkedIn plan (`profile/networking.py`
    `LINKEDIN_PLAN`), the free ones until you say, and the weekly budget counts drafts
    already queued. Profile upgrade: linkedin-plan.
  - An InMail had no subject line and none of the first note's rules. It now has a
    subject of a few words naming the common ground (never "Quick question" or a job),
    the first note's shape and one paragraph of evidence.
  - "Not interested, thanks." and "Please stop messaging me." read as friendly short
    replies and drew a call invitation; "not hiring, but happy to chat" read as a no, so
    two of them closed a booked call. Both now read right, "talk to <a colleague>" reads as
    a referral, and a thread at `call_booked` or `referral_in_progress` is never stopped.
  - An empty `/reply` on a thread we had already answered re-read their old message and
    drafted a CV already sent; it is now a quiet thread, and `/reply` drafts no second
    nudge.
  - "Do you have any openings on your team?", "could you refer me" and five other plain
    job asks passed the first-note check; a note whose common ground is their hiring
    drops the "looking for my next role" clause; a question ends in a question mark.
  - The per-application outreach note is checked by the same tone rules, says its
    character count, comes with a version that fits a connection request, and no longer
    tells you to ask someone who never replied for a referral. `/apply` now checks who is
    already talking to the employer before drafting, and writes the note.
- **A job board built for you searched your home city and nothing else.** A round sent a
  person's own board one place, the first in `SCRAPE_LOCATIONS`, unless someone had listed
  its places by hand, so the towns around it, the region and the country went unsearched
  while LinkedIn searched all of them; and it never asked any board for remote roles. Every
  board now searches every place in `SCRAPE_LOCATIONS`, home deep and the rest two pages, and
  remote roles where it can filter for them (`remote: true`, `--remote`). `/add-portal` builds
  CLIs that read places as LinkedIn writes them, cover a commute's radius around each, and
  take `--remote`; `/setup` writes the whole metro area and the country as places, and the
  wider regions an employer abroad files remote roles under. Boards you already have are
  rebuilt this way in the background (boards version 3), and your places widened (market
  version 3). No profile upgrade: build_versions carries it.
- **A portal that went quiet is reported again.** `run_round.py` read the health probe's file
  after pruning had deleted it, so a portal returning nothing was never named and a MISSED
  round blamed the market. It is read first now, and a DOWN portal is named on every round,
  met or missed.
- **`ci_local.sh` is green again in a person's repo.** The check that no real scheduled-task or
  chat id is committed to the app read every tracked file, so after a sync it failed on
  `profile/routines.json` and `handoff/`, the person's own files and exactly where their ids
  belong. It now skips what `tools/personal_paths.py` calls personal.
- **A vacancy open only to the employer's own staff is cut.** A test of the scheduled
  shortlist ranked an "Internal Mobility" posting eighth; nothing screened for it. A title
  saying "internal mobility", "internal only" or "internal applicants only", or a sentence
  restricting the role to current or existing staff, is now a cut with the quote. "Internal
  candidates will be prioritised" and "Internal Audit" are not. Postings in another language
  use `INTERNAL_ONLY_TITLE` and `INTERNAL_ONLY` in `search.py`.
- **The shortlist message reads well on a phone.** One role per block (role, employer and
  score first, location, posting date and one reason on the next line, the link on its own
  line), warm-route notes under their role, and a failure line only when a step failed.

- **A junior role no longer scores mentoring bullets up.** `tools/allocate.py` counted the
  bare word "junior" as a mentoring cue, so every posting for a junior role pulled your
  mentoring bullets forward. It now counts "junior" only as the object of the work
  ("develop junior", "train junior", "support junior"), plus "upskill".
- **`/setup`'s environment check is `python3 tools/env_check.py`.** The old inline check read
  any HTTP status as success, so a host your network policy refused still "answered", and it
  never looked at Ashby, Workday, pypdf or bun. It now names a policy refusal as one, catches
  a pypdf that is installed but panics (the `cffi` case), checks bun, and probes LinkedIn,
  freehire, Greenhouse, Lever, Ashby and your first Workday board.

- **Messages say your word for the document.** The email composer wrote "My resume is
  attached", the referral ask "Happy to send my resume", one outreach-note close "does not
  fit on a resume", and the reply guidance "Do not attach a file named CV; the attachment
  says resume", whatever `person.json` `documents.noun` said. All of them now use your noun,
  the guidance names your banned word, and `tone.check` reports any word in
  `documents.banned_nouns` in a message (`document_noun`; "CV" keeps its old rule), so
  "my resume" no longer passes in a CV market. "Resume" as a verb is not flagged.

- **A credential stated as "essential", "mandatory" or "must be registered" is a credential
  gate.** "A recognised accounting qualification (ACA, ACCA or CIMA) is essential" passed,
  so a full application could be drafted for a job you cannot hold. The sentence must still
  name one of your profile's `DESIGNATION` credentials, and "desirable" still wins.
- **A short posting is still read for its bars.** A body under 400 characters skipped every
  gate; "Active SC clearance required" or "Fluency in Welsh is essential" in a snippet went
  through. Every gate now reads what there is, and the row is still marked `thin`.
- **Pay is read however the posting writes it.** "EUR 35,000", "45 000 €", "GBP 45,000 to
  52,000", "€45-55k", "£45k-50k pa" and "₹12,50,000" (and lakh, crore and LPA) were read as
  no salary stated, so a range under your floor was never flagged and a high one never
  earned its points. The market's symbol or `CURRENCY_CODE` may sit before or after the
  figure, a range's bare end takes the other end's currency, and "per annum", "p.a.",
  "DOE", "package" and "CTC" are pay cues. A single figure counts only right after a pay
  label ("Salary: €38,000"; "up to" is a top, "from" is a minimum and is not scored as one).
  `tools/opportunity.py` now reads the screen's range rather than its own pattern, so the two
  cannot disagree. **Scores move after this sync** where postings state pay in a form the
  old pattern missed (a "k" figure, a code, a space separator); that is the fix.

- **`verify_batch.sh` no longer fails letters written the way the style guide asks.**
  `audit_letters.py` required the opening to name the role, which pushed every letter back
  to the "I am applying for the <role> role" opener `03-writing-style.md` bans; it now flags
  that opener instead, and asks for the role only when the batch holds two roles at one
  employer. The opening must still name one of your employers, but as people write it: "at
  Brindle & Hart" names Brindle & Hart Logistics. **If you call an employer something
  `roles.py` does not hold** ("Oakmere" for Oakmere Foods), add `known_as="Oakmere"` to that
  role; the outreach note's hook uses the same matcher.
  No profile upgrade: the audit names the employer when a short name needs `known_as`.
- **A date running into a capitalised word is no longer a claim.** `check_numbers.py` read
  "2024 Weekend" as "2024 week" (and "12 monthly", "3 hourly", "2023 Daytime" likewise), an
  ungrounded number that failed the batch.
- **Ireland's DAC, CLG, UC and Teoranta, Canada's ULC, and "Pvt Ltd", "Pte Ltd", "Pty Ltd" and
  "Co., Ltd."** come off the salutation, the outreach note, the document file name and the
  company key, so the throttle sees "Acme DAC" and "Acme" as one employer. "Acme Pty Ltd"
  used to become "Acme Pty". A draft re-rendered after this sync for an employer with one of
  these forms is written under the shorter name.
- **A draft's file name is settled before it is rendered.** `fit_to_page.py` read a
  hand-written `abbr` ("FF") before the renderer replaced it with the derived one, so the
  last compile looked for a file never written; a draft with no `abbr` was a bare
  `KeyError` there, in `outreach.py` and in `record_drafts.py`. A shortlist row with none
  now says so and names the employer.
- **The leak scan no longer treats a placeholder as a person.** An employer entry such as
  "Projects", "Freelance" or "Career break" became a denylist entry, matched the app's own
  headings, and forced a rename on the person's resume. Placeholders are skipped; a real
  employer with such a word in its name ("Acme Projects") is still an entry.
- `/setup` checks for LaTeX and the job-board hosts first, and gives the environment settings
  then, so they can be changed before the session that needs them rather than after.
- The prefilter's title reason no longer says "analytics, data, modelling, risk or pricing";
  it names the profile's `POSITIVE` list.
- `tools/build_app.py` no longer writes a phone number out as an example: the one it had was
  a test person's own, and their leak scan failed on the app's file.

Found by the first end-to-end setup of a fictional person in a new market, from a fresh
template copy:

- **The leak scan failed for anyone without a North American phone number.** A non-North
  American number now yields its national grouping (with and without the trunk 0) instead of
  a three-digit slice that matched everywhere, and the reserved `example.*` domains the app's
  templates use are never entries (`build_app.phone_forms()`).
- **An app test read the person's own tracker**, and failed after a new repo's first `/apply`.
  It reads the example person's temporary state, as every app test does.
- **Scoring crashed on a profile shaped like the example.** The example's `FIT_MISSING` held
  pairs where `tools/fit.py` reads triples; a new test scores a posting against the example.
- **`tools/profile_names.py`** lists every name the tools read from a profile, whether a tool
  needs it, whether the example sets it, and where it is read; `/setup` uses it, and a test
  checks the example sets every name a tool cannot do without.
- `/setup` writes `seen_jobs.json` as `{"seen": {}}` (the tools read that key), commits before
  the checks that read the commit, states the role-heading shape, and says a Workday board
  cannot be guessed.
- The commit recipe in CLAUDE.md adds one existing path at a time: one `git add` with a path a
  new repo does not have yet staged nothing at all.
- The cover letter is printed on the profile's paper (`documents.letter_paper`, defaulting to
  `documents.paper`), no longer always US Letter.
- "Pty" is a company suffix; the duplicated-word check no longer fires on a phone number's
  repeated digit groups; the example's role headings use the shape the prep tools read;
  `/apply`'s rule on gaps now matches rule 8 of the writing style.

## [3.0.0] - 2026-10-14

The first release as a template: one app, any number of people, each in their own private repo.

### Added

- **Everything about a person lives in `profile/`.** Identity, history, bullets, skills, market,
  preferences and voice, read by every tool through `tools/person.py`. No tool names a person, an
  employer, a city or a currency of its own; a repo with no `profile/` starts with `/setup`.
- **`tools/personal_paths.py`, the one list of what belongs to a person**: the profile and the
  search's state (tracker, contact book, threads, documents, research). Everything else is the
  app's.
- **An example person, `profile.example/`.** Fictional, complete, and what the app's own tests run
  against, so the suite gives the same answer in the app and in a person's repo. A person's own
  tests live in `profile/tests/` and run in a separate process.
- **`tools/sync_app.py`.** A person's repo pulls the app's updates and never sends anything back.
  The first sync of a template-made repo merges unrelated histories; an app-owned file edited in a
  person's repo is put back and named; personal paths are never touched; `--check` reports how far
  behind and any drift.
- **`tools/build_app.py` and `tools/leak_scan.py`.** The app is built from a person's repo by
  removing every personal path, then scanned for anything of theirs that is left: contact details
  by shape, and every name and fact the person's own data holds, in every form it is written in.
  `tools/ci_local.sh` runs it on every check in a person's repo, and the app's CI runs it on every
  push.

### Changed

- **Private repos spend no Actions minutes by default.** Every CI job runs on a public repo or a
  manual dispatch; `./tools/ci_local.sh` runs the same checks locally, Python 3.10 leg included.
