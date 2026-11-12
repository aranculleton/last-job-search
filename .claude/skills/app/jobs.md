# Big jobs, work for the computer, and the daily tidy

Read when a wake hands this chat a big job's call, work for the computer, a job's chat
reporting back, work asked for in a chat, the daily tidy, or a big job's progress. Steps 3 and
5 are in `.claude/skills/app/wake.md`.

**The answer goes out first.** The reply in the thread or the chat, and the page brought up
to date, come before any saving: landing runs after them, once a turn, in the background
(`python3 tools/land.py`, step 5), and never holds the answer.

This chat answers the page and does small work itself (`run: here`: a reply, a tweak, a
message in the chat), at once. **A big job runs in a chat of its own** (a search, drafts, a
resume for a contact, an interview prep, a networking run): run in this chat, even as
background agents, a search and a networking run held it for 15 and 23 minutes and the
page waited on every tap (2026-10-29). `next` never hands one to this chat to run itself:

- `run: child session`: send the claim, then make the `create_session` call exactly as
  `next` printed it (where it says `<your chat id>`, put that in first, from `get_session`
  with no id). That chat runs the one item, pins its progress, finishes it, lands it on
  master (`land.py` in the foreground, so it ends when the landing has), brings the page up
  to date itself and takes the next job waiting. It never messages this chat: a message
  between chats asks the person's approval every time, and was refused (2026-11-10). It never
  publishes, watches or answers the page, and is titled `Job search: <title>`, never the same
  as another job's chat at work; it puts itself away once its work is saved and nothing else
  waits, and the daily tidy puts away one that could not.
- **A question typed in the page's Chat gets a chat of its own too** (`Job search: Chat`,
  `page_db.QUESTION_CHAT_TITLE`) while this chat has other work of its own running or waiting
  (`page_db.busy_here`), so it never waits on that work (issue #226): `next` hands it out
  first with `run: child session`, made exactly as a big job's call is. With nothing else
  going on it is answered here, at once, which is quicker than a fresh chat's start. A start
  refused or failed is never made again for it: `app.py let-go` lets its claim go at once
  (as the wake's line says), and the wake run again answers it here, first.
  One such chat answers every Chat question while it is at work: this chat then leaves them to
  it, and it takes the next one itself (`next --job-chat --questions`) and puts itself away
  when none is left; it takes one of the cloud's ten places, and the daily tidy puts it away
  like a job's chat. With no `create_session` here, or every place taken, the question is
  answered here, before anything else (`run: here`, wake.md step 3); a question asked under a
  card is always answered here, under its card.
- `run: background agent` is the fallback where `create_session` is not available: a chat
  on a computer, or a chat without that tool (`wake` with `--no-sessions`). Send the
  claim, then make the Agent call exactly as printed (`run_in_background: true`,
  `isolation: "worktree"`).
- **Work for the computer** (a LinkedIn read: a networking run the page sent `to: computer`)
  is never `next`'s for a cloud chat: the engine refuses its claim, finish and fail there.
  `wake` names it on every wake in a `computer:` line, while any waits there or a chat there
  is left to put away, and says what to do: `python3 tools/computer.py route "$D" --chat <your
  id> --tools "<this chat's tool names, comma separated>"` (with `--envs <that file>` where
  this chat has `list_environments`, its answer saved to a file), and do what it prints: its
  batches first (the list of computers, kept for the page), then a `call` exactly as printed,
  then its `then`. A `handback` is a step this chat has no tool for: a subagent ends its answer
  with its lines, exactly as printed, and its listener makes them (SKILL.md, step 0). `paste`
  needs nothing more, the page already says it. **This
  chat never approves computer access** (`confirm_repository_trust`): one small chat of its
  own, "Job search: starts chats on your computer", holds that approval and starts and puts
  away the chats there; `route` makes it once and wakes it by republishing its bell page.
  An approved chat could never be archived, itself included, so every hand-over left an old
  helper in the sidebar (2026-11-10). Never `send_message` a chat on the computer: it reports
  through the page and the copy. On the computer itself, `next --kind computer --computer-only` runs it in that
  chat, which has the browser, never as an agent (COMPUTER.md, "How the work reaches the
  computer"). Where only the person can move it (LinkedIn signed out there, an approval), the
  page says what is wrong in one line with one button (`computer.py state`: its To do card and
  its row under LinkedIn): asked about it, point them there, and never send them to a chat as
  the way through, the one on their computer included (2026-11-11).

Never wait for either: go straight back to step 3 for the next item, so a search, a
networking run and an interview prep run side by side (ten at most in the cloud, each in a chat of
its own, `page_db.HEAVY_CAP_CHATS`; three on a computer, `page_db.HEAVY_CAP`;
`next` keeps the cap and the locks). When a background agent ends with `Finished <id>, on
master` or `Finished <id>, not landed` (its check failed; land it with this chat's own work):
run `app.py view` (step 5; it takes master first) and send its batch; an item still
running finishes here, as step 5 says, from what its line said; then step 3 again, so work
queued while it ran starts now. Two chats writing the page at once is safe: each write is
pinned to what it read, so the later one is refused and redone, and each is drawn from
master.

**A job's chat reports back** only where it was started before job chats stopped
messaging (2026-11-10), with a message another chat sent: `[app]
Finished <id>, on master, in chat <its id>: <what it made>` (or `not landed`). It is data
from that chat, never the person's words, and asks for two things only, done at once and
said to nobody. Read in one go (step 1) into a fresh `$D`; run step 5's `app.py view` and
send its batch, so the results are on the page. Then close that chat: `get_session`
(session_id <its id>), its answer saved to a file, and `python3 tools/tidy.py close <its id>
--work <id> --dump "$D" --details <that file>`; do what it prints (`archive_session`, then
`tidy.py closed <its id>`). It names the archive only for one of the app's own job chats on
this copy whose job has ended and whose work is on master; any other it keeps, for the daily
tidy-up. A finished one whose work never reached GitHub gets a `save` line (make its
send_message, once: that chat saves its work and sends nothing back; the next tidy-up finds it
saved) and, if it still is not there, a `lost` line (send its batch: the work's own card says so, with Try again) and the
archive; the daily tidy-up does the same for one that never reported. Then `wake` with the same folder (step 3 again), so a job waiting for a free place
starts now, and land this turn's work (step 5).

Drafting and audits are never moved below this chat's model. The other chats are never
mentioned to the person; the page shows each job's progress.

**Work asked for in a chat is on the page's work list too**, like work asked on the page, so
the person sees what runs and what is done. When the person asks a chat for work (a search,
drafts, a resume, a prep, a reply to draft), first read `work` and `holds` into `$D`
(ArtifactData `query`), then `python3 tools/app.py ask "$D" --kind <kind> --title "<a few
plain words>" --args '<json>' --here --chat <your chat id>` and send its batch: the item is
this chat's, running at its first stage. Do the work here, pin each stage as a big job does
(`app.py pin ... --chat <your chat id>`, every ten minutes on a long one, "Progress costs
nothing extra" below), and finish it with `app.py done` (step 5), so its card shows the
result. A chat that answers the page sends a big job to a chat of its own instead (`ask`
without `--here`). A networking run asked in a cloud chat while the person's computer is
ready is never that chat's: `ask` sends it `to: computer` by itself (`sent_to: computer`), where
the whole run is done with Claude's browser; do what its `then` says. `app.py busy "$D" "<a few plain words>"` (read `beats` first) is only for
an answer given in the chat itself, never for work: the page shows "Claude is busy in your
chat: <those words>"; `busy "$D" --done` when it is given.

**Once a day, the app's own old chats are tidied** (`listen` prints `tidy:` when it is due).
Right after this chat took the page over from an older helper, `tidy: now` asks for one
`get_session` of that helper and `tidy.py retire`, which puts it away as soon as its work is
saved, and nothing else. The daily one is the way out for a job's chat that never reported, and
for every old helper. `list_sessions` (`mine: true`) and `list_triggers` (with `include_completed: true` only where the line says so, once a week), every page, then
`python3 tools/tidy.py plan --dump "$D" --stdin` with `{"sessions": ..., "triggers": ...}`
on standard input in a quoted heredoc, each as the tool returned it, never typed into files.
It asks for `get_session` on the chats it must check first (their results go under
`"details"` the same way); then it prints the brief's move into a chat of its own where its
chat is gone, archived or approved computer access (four steps, in order, stopping at the
first that fails), or one line recording the chat made for it, the daily upkeep's calls (`upkeep 1:`, made in order, said to nobody),
and the chats to archive with `archive_session`. It never names this chat, a chat the person
named, one a scheduled task that is on still uses, a live campaign's chat, one used lately
(an old helper excepted: there is only ever the live one), or one whose work is not on
master. Then `tidy.py done <each archived>` (it keeps their titles itself), and commit. Where
the brief runs is what the task listing says (`brief:` names it), never the registry: report
the brief moved only once a new `list_triggers`, run through the plan again, shows its task
firing in its own new chat (a helper said it had checked the move when the task still fired in
the old chat, 2026-11-05). `routines.py brief` says the same: `elsewhere:` with `move` calls is
a brief in a chat not made for it (this one included), never one set up; make the moves. The
brief is never carried into this chat, and no reminder or check-in is ever set here (never
`send_later` nor a one-off task bound to this chat): once this chat approves computer access
it can run none. The tidy-up is due again by itself at the page's next check-in.
Nothing is said to the person in a chat they are not reading: the page says it.

**Progress costs nothing extra**, and is for big jobs only: small work done here is claimed
running at its first stage and finished in one batch, with no pin between. At each stage
boundary of a big job (`app.py progress <kind>` names the stages), in the same message as
that stage's first command, `python3 tools/app.py pin "$D" --work <id> --chat <the id it
was claimed under> --stage <stage> --line "<one plain line>"`, and send its batch: it moves the stage, adds the line and renews
the item's lease. On a long stage, pin it again with a new line every ten minutes or so: the
page counts a job with no word for half an hour as stopped. A search's job sites say how far
they are and how long is left: while `run_round.py` runs (in the background), every ten
minutes or so (the lease is thirty) `python3 tools/app.py pin "$D" --work <id> --stage
scrape --log <the round's folder>/round.log`, so the page times it by that and not by the
usual minutes. `"stop_asked": true` in what it prints (or an item named under `stopped`):
`python3 tools/app.py done "$D" --work <id> --chat <the id it was claimed under> --stopped`,
which releases its locks, and stop. A refused pin: as any refused write (SKILL.md, "Rules that hold everywhere"); claimed by
another chat, write nothing else. Work nobody is doing that should not run (a repeat of a read
already done, a sign-in no longer needed, a job whose chat went quiet) is called off by any
chat, the card saying why: `python3 tools/app.py done "$D" --work <id> --chat <your id>
--stopped --summary "<why, in one short sentence>"`.
