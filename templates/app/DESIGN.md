# The page's design language

For whoever changes the page (`templates/app/`): a chat or a person. Each rule says which
test holds it, so a change that breaks one fails before it ships. The person reading the
page is tired, often on a phone, and not technical: every screen answers "what do I do
next?" in its first lines, and nothing asks for a decision a default could make.

## Places

- Seven places: **Brief** (the home screen), **To do**, **Jobs** (To apply, Applied),
  **Contacts** (one list, each person with what to send them), **Coming up** and **Chat**
  together in the side menu, and **Settings** alone at its foot. Five sit in the phone's tab
  bar (Brief, To do, Jobs, Contacts, Chat); To do alone carries a coloured badge, and Chat a
  small grey dot while an answer waits unseen. (layout 6, nav order test; contacts rules test)
- Each screen: its title, one plain summary line, at most three blocks before the first item.
  A way to somewhere else (the new jobs, Start again, Paste a message) is a soft pill beside
  the summary, never an underlined line under it; what Claude is doing is the header's work
  pill and each card's own line, never a line of the header. (layout 1 to 3, one-card tests)
- A long list opens on its first few and folds the rest one tap below ("Show 6 more"): To do
  five today, Drafts five, Contacts who has a message to send and who needs you. Never a
  filter left on. The fold's count is what it still holds: once tapped it goes, and its first
  card takes the focus; "Show 1 more" never stays over what it showed. (layout 2, crowd tests,
  fold test)
- To do's five are what is late or due today first, then the questions; setting-up cards wait
  behind the fold. The small questions (a yes or a no, a choice of a few) are one card, "4 quick
  answers", always among the five: one question at a time in its grey box with "1 of 4", each
  answered with its own control (answerBox), the next there the moment it is answered.
  (tired-person tests, quick answers test)
- What helps Claude do more (your profile, reading profiles, the LinkedIn download) is never
  counted among today's things: it is one soft card right after them, above "Not due yet", in
  To do's own style: its title "Help Claude do more", the first one's one plain line saying
  what it gives ("Your profile: every resume and letter is built from it"), and its one pill
  to start it, which puts that one's own card in its place; the rest fold under "and N more".
  With nothing due today, its first card shows at once under its own heading. Why: at the foot
  of To do, among the folds, it was not found (the maintainer, 2026-11-07), and as one faint
  line after today's things it was "so hidden" (2026-11-10). (help test)
- One card an act and one card a person. A person is never on three cards: their follow-up,
  what they asked for and a job's "ask them before you apply" are one card for them, led by
  what they asked, the referral its grey box, its Done finishing all of it. A referral with no
  row about them, a closed posting, and a draft Claude is fixing are never To do cards: they
  are notes on their own cards (the job's, the draft's). A closed posting is set aside by
  itself, with Bring back under Set aside. (one-card tests)
- To do never offers a fix: a draft or a message that fails a check with a clear fix is fixed
  by Claude by itself, queued by the engine (`app_model.message_fix`, `tools/app.py`
  `self_fixes`), its own card saying so. One Claude tried and could not fix is said on To do
  with no button, its own card offering it again. Only a fact only the person knows is asked,
  as that work's one question. (one-card tests)
- An item's actions are defined once, for every card that shows it (`ivActs` for an
  interview, `canSayReplied` and `theyRepliedBtn` for a person): To do offers what Coming up
  and Contacts offer for the same item, with the same names ("Read your prep" everywhere). An
  interview's card: its next step and Add to calendar; Practise with Claude, Update my prep and
  a new day under More; they said no and I withdrew in its trash.
  (one-card tests)
- To do holds only what there is to do. Someone who has not answered the person's limit of
  messages is never a card there, nor counted. In Contacts they wait below the fold with the
  others who need nothing, their row saying to leave it unless they write back, with Close.
  (contacts rules test)
- Every screen is the whole width, as the Brief is: its column fills the space between the
  side menu and Claude's work and narrows only as they take room (the menu's names shown, the
  work panel open) or the window does. No screen sits in a narrow column of its own; card text
  keeps its own measure. The side menu opens on "Icons only", its own section above the
  screens under one rule, as Settings is below them. (layout and menu tests)
- Claude's work has one button on every screen, the pill in the header. On a wide screen it
  opens and closes the panel on the right, as the menu's "Icons only" folds, remembered on the
  device (open beside every screen but the Brief until the person chooses); narrower, it opens
  as a panel on the right, and on a phone as a sheet from the bottom. (pill tests)
- The Chat button and its panel sit at the right, or at the left where the person chose it (Settings >
  Look, Chat button, or the panel's own arrow; the same choice, kept on the device), small or big.
  The panel's controls are the page's own soft pills (Open in Chat, Close), never underlined words.
  The conversation opens on its last day; earlier messages come only by its Show, never by
  scrolling up (the maintainer, 2026-11-06). (chat panel tests)
- In Claude's work, four or more of one kind waiting, or finished, are one card with their
  count and the first few names; Show lists them. Nobody scrolls past fifty cards. (run test)
- Claude's work says its count once, in the header's pill: no line under its title repeats
  it, and "Nothing is sent." is not said over the cards. Each running or waiting card has its
  title, one short state with its clock ("Waking Claude · 1m 4s", never a chip and a line
  both saying it), its bar, and Stop Claude. A finished one is a compact row under
  "finished": its title and one-line result, the time small at its end, the whole row opening
  where its record lives (a person's work in Contacts on that person, a job's in Jobs, a
  draft's in its draft), its trash shown on hover or focus; no Done chip, no Open button.
  (the maintainer, 2026-11-05; Stop Claude tests, compact row test)
- **A laptop's Brief is one screen.** From 960px wide the Brief's panels are two rows (Today,
  Coming up and Next; Waiting on you, Jobs, News and the numbers) that share the window's
  height, with the privacy line and the tip on one last row beside the Chat button, so the
  page does not scroll at 1000 by 560, 1280 by 720 or 1440 by 900. Each list shows as many as
  its room holds and gives way below to one, its panel's own "All ..." opening the rest; News,
  with no screen of its own, says "2 more" and opens them in place. On a short window (660px
  or less) the numbers are one line under the greeting, opening Progress with its chart. A
  phone scrolls. (the maintainer, 2026-11-05; fit tests)
- **A panel uses the room its row gives it**, never content packed at the top over a hole
  before its pills. Worked out from what is drawn (`fitAir`), never a height tuned to one
  window, and only room the panel already has: a list's own small heading where it fits
  (Jobs' "New, best fit first" under its drafts' line), a short list's rows each in a soft box
  as Coming up's are, the rows a step of the spacing scale further apart up to 24px, and past
  that the pills a step under what they open, the spare room at the panel's foot. Your
  progress's chart grows into its room, up to 160px. (the maintainer, 2026-11-07: "u see how
  its bunched at the top? be smart about this"; room tests)
- **Your progress is jobs and people, chosen for the person.** At most four numbers, picked by
  the engine (`app_model._glance`) from what is true now: applied, interviews, offers;
  messages sent, accepted, replies, calls, referrals; and interviews or referrals through
  people. What moved furthest first, both sides where both moved, and never a nought beside
  real work: a month of notes and no applications shows the notes. Under them one line on
  what is working, only when the person's own numbers carry it (two groups of five or more),
  said as counts, never a cause. The weeks are applications and messages sent, the two chart
  colours, each named by a swatch in the line under them; one series where the person only
  does one. Progress says the same. (the maintainer, 2026-11-10: "not make it look like im
  doing nothing"; progress glance tests)

## Cards and lists

- Every item is its own soft card: a 1px line, rounded corners, no shadow, 8px from the next.
  Only what floats (a sheet, a menu, a toast) has a shadow. Nothing has a line down its side.
  (design test)
- A card reads top down: its top line (a kind or a score, the title, a state pill, the trash),
  one line of facts, at most one block in a soft grey box (a question or a suggestion), then
  its actions: one row of pills (Buttons, below). (layout 7, 8, action-row test)
- Jobs is one list of the jobs you might apply to, each once at its own stage, and Applied beside
  it. A drafted job stood in Found and again in Drafts, and acting on it meant flipping tabs: now a
  drafted job is its draft's card, carrying the job's fit and reasons, a job being drafted shows
  its progress, and a find offers Draft this; drafts first, then finds by fit; the tab, the
  summary, the menu and the Brief count the same two things, drafts to send and jobs to look at.
  A posting that has closed waits under the list ("1 closed: Show"). (jobs page tests)
- On a phone, Jobs' search takes its own row under the To apply / Applied switch once the list
  is long: beside it the switch was squeezed unreadable (the review, 2026-11-05). Every other
  control row stays one row.
- Jobs' header is the same on both tabs: its title, its one short line and when it searched, with
  Find jobs and then "Add a job" and your resume as soft pills beside it, as Contacts'. What
  Claude is doing is the header's work pill and each card's own line, never a line here.
  (going-on tests)
- A Jobs card says its facts on one line (the employer, the town, never its region and country,
  when it was posted and found, the pay where stated) ending with its details fold: "Why"
  where it has a score, else "Details", short labelled rows in one size and one tone (why it
  scored, a watch-out apart, worth knowing, skills, the posting, "Also at" the employer by kind,
  each link naming what it opens). More holds only the rare actions; a card with none has no More.
  (jobs page tests, layout 16)
- A Jobs card's actions are the one row of pills of Buttons, below: one filled next step, two soft
  pills at most, then More. A pencil beside the resume's words and one beside the letter's ("CV 1
  page ✎ letter 1 page ✎", the engine's own parts, kept on one line each) open the Tweak panel; the
  pencil at the end of a job's facts corrects its title, pay or place, code only. What Claude can
  do by itself is never a button: a draft's remake after a check with its fix in hand, and its
  files, are queued by the view, and the card says what Claude is doing. Every control that wakes
  Claude carries the gauge; the sweep tags each control Claude-waking or code-only. A warm route
  is said one way, in the card's soft grey box. (layout 7, 8; sweep test; jobs page tests)
- A form's own questions, and changes to a resume or letter, go in the one box under a draft's
  or an application's More ("Questions on the form"); the answers come back on that card, each
  with its Copy. Work a card asked for is said on that card in the words of its card in
  Claude's work, with Cancel while it waits or runs, why it failed with Try again, and Done only
  once its result is on the card. (form questions tests)
- A state is a small tinted pill in words a person uses, never a code word: ok green, info
  blue, warn amber, bad red, held violet, waiting grey. (status audit, colour tests)
- A booked round or call asked for and not confirmed by them yet says "Not confirmed yet",
  a grey pill on its row in Coming up and on the Brief; the box of the same words is there
  wherever its day is given, and booked again without it, it is confirmed. Why: a day only
  asked for read as fixed (the maintainer, 2026-11-05). (not-confirmed tests)
- Every message drafted and waiting is one card, "Messages to send (N)": the drafted
  replies and follow-ups, the week's first notes and the ones to check first together, a row a
  person, each opening their draft in Contacts, and one button opening Contacts. A row Claude
  is fixing says so; one only the person can settle says "Check first". N is the engine's one
  count (`app_model.to_send`), the same as Contacts' "N to send". Why: three cards (drafted,
  first notes, to check) said one thing, and their counts disagreed with Contacts. (drafted
  messages tests)
- A note waiting for its person's profile is not ready to send, so it is not on that card:
  everyone waiting on a read is one card (`app_model.to_read` with the reading list), however
  many, saying when the reading happens. Where the page cannot read (a phone, the web) its
  title says where to open it ("Open your page in the Claude app on your computer to read 3
  profiles"); where it can, it reads by itself and the card says so ("Claude reads 3 profiles
  by itself", "Claude is reading 3 profiles" with its spinner), with Read them only to open its
  tab the first time or to try again after trouble. Why: "when exactly is this waiting for
  claude thing going to happen?" (the maintainer, 2026-11-07). (waiting-note tests)
- **An interview's live prep reads full screen, in the order the interview runs**, on every
  screen. Its head says the round and how long, then search, one Simple|Detailed switch for
  every answer, Open all and Practise, chips to each part and one line of timing. Each part:
  its "Say first" in a soft grey box, a "Likely to prompt" pill under a line taking the person
  to that answer and marking it; each question a soft card with who asks it, the other ways it
  is put and its answer in a soft grey box with its own switch, its follow-ups folds by who
  asks; then the stories, the words A to Z and the notes just for them. A term is a dotted
  word inside its sentence, never a pill: it opens a panel at the side on a wide screen and a
  sheet from the bottom on a phone, with Back through a term inside a term, and Close. Practise
  hides each answer behind Start, with a small timer. Nothing in it is a filled pill: the
  screen's one is Practise with Claude above it. The words, the order and the timing are the
  engine's (`interview_live`). (live prep tests)
- Many of one small thing are one checklist card, a row an item: each row has its own next
  step and Done beside its trash, the trash keeping the rest (They replied, Tomorrow, Next week,
  the person's choices), and the card's own actions keep to the card's anatomy above.
  (layout 8, one-card tests)
- One "?" a card at most, after the last word of its line, and no more than three on a first
  screen. (design test, budget test)

## Contacts

One page, one card a person: what to send them and where they stand, together. (contacts page
tests, `tests/test_contacts_is_one_page_with_each_persons_draft.py`)

- No People and Messages tabs: each card shows the message drafted to them under their name,
  open, and folded by a tap on its heading. Why: the person and what to send them were two
  tabs apart, so one reply meant finding the same name twice.
- "I sent it" takes the message off the card at once; the person then waits for their reply,
  or for the follow-up when one is due. Why: a sent message is done, and the card says what
  happens next instead.
- People with a message drafted come first, then who needs you, in the engine's order
  (`app_model._people`). A message with nobody on the list (an application's follow-up) is a
  card of its own among them. Why: what is already written is the quickest thing to finish.
- Someone you have written to has one main button, "They replied". It opens a labelled box
  right under them, "Paste what Juno sent", with one filled "Draft my reply" (the screen's one
  filled button while it is open). A reply already kept opens the same box, asking only what
  to say back. Why: the paste is the one step the person must do; it cannot be tucked away.
- Draft my reply queues the reply for that person (a "They replied" action, which queues the
  reply work) and frees the box at once, so ten replies go in one after another without
  waiting for any. Why: someone talking to many people pastes several in a row.
- From then the card says where its reply stands, in one line in Claude's work words, read
  the way its work card reads it (Saved, Waiting for Claude, Next, Waiting its turn, Claude is on it
  with the spinner and, after a few seconds, its clock). Read from the tap and its work item,
  never from this tab's memory, so it is the same after a reload or a live update. Claude's
  draft lands in that same card, ready to Copy and "I sent it". Why: with ten queued, each
  card shows which are waiting, which is running and which are done.
- The line has one quiet control. Cancel, while it waits or runs: a tap Claude has not taken
  goes at once with the pasted words back in the box; waiting work stops at once; running
  work says "Stopping after this step", then "Stopped". A reply finished but not on the page
  yet says "Finished · Putting it on your page" and the draft replaces it when it comes, never
  "Done" over nothing. One that failed says why, with Try again. Why: nobody is left
  wondering, and nothing they pasted is lost.
- On the card's face only what is done every time: the name, its state, the trash; one line
  of facts, the latest exchange only ("You wrote 2 Nov", "They replied 3 Nov"; when you
  first wrote and how many messages each way, the engine's `exchange`, are on their page), with
  "Overdue" in the corner only when something owed to them is late, by the engine's one late
  (standing's `late`, as To do's); the draft with Copy
  and the pencil in its corner (a subject's Copy an icon at its line's end); then one row of
  pills: one filled (I sent it once copied, or the one owed step), at most two soft ones
  ("They replied"), and More. With a message on the card, "They replied" waits under More.
  Why: five buttons a card read as five jobs, and three dates a card as none.
- More is for what is rare, a handful at most: their profile link, a call booked, they sent
  me a job, the referral, read their profile, Claude's ideas and notes. Never editing (the
  pencil), never the card's facts (its line), and no More on a card with nothing
  rare. Why: More became a drawer of everything, so nothing in it was found.
- The pencil opens a box under the draft, "What would you like changed?", as Something else
  does: room for a pasted message that grows with it, Shorter, Warmer and More formal filling
  it, one filled Ask Claude (Cmd or Ctrl+Enter) with the box's one gauge, and "Edit the words
  yourself", which makes the draft's own words the field (what Copy copies and I sent it logs).
  Why: a slight edit is the commonest change, and it was buried under More; then the pencil
  opened the words as a field with a one-line box under it, too short to paste into and with
  a gauge on every chip (the maintainer, 2026-11-05).
- A draft that fails a check with a clear fix (too long for the channel, a phrase that reads
  machine-written, asking them for a job, a rule of theirs) is fixed by Claude by itself: the
  engine finds it (`app_model.message_fix`) and the view queues the fix with no tap; the card
  says "Claude is fixing it: <why>" and offers the draft as ready only once it passes. Never a
  Fix it button. Tried twice and still failing, it says so, with the pencil to change it. A
  fact only the person knows is asked through the one rare question. Why: where there is
  clearly a recommended option, the app does it.
- A first note written before their profile was read has no Copy: one line under it says why
  and when, in the engine's words for where reading stands where the page is open
  (`linkedin.reading.hold`): "Claude reads it next time this page is open in the Claude app on
  your computer" on a phone or the web, "Waiting its turn", then "Reading their profile…" with
  the spinner in the app. Never a second line or an alert saying it again. "Paste <name>'s
  profile" is the soft pill beside it where the page cannot read now, its gauge one note's
  rewrite (`app_alerts.paste_profile`), never a networking run's. Why: the line and an alert
  said the same twice, and the paste read as "a lot of your allowance" (the maintainer,
  2026-11-07). (waiting-note tests)
- What wakes Claude carries its cost beside it (the gauge: "Draft my reply", "Ask Claude",
  "Draft the follow-up"; the pencil box's chips only fill it); what only the page does (I sent it, an edit in place,
  the trash) carries none, and wakes nothing. (`data-wakes` marks the first kind.)
- The header is its title and one short line, "4 to send · 8 need you", with Find people and
  "Paste a message" (a message from someone not on the list) as soft pills beside it. What
  Claude is doing is the header's work pill and each card's own line, never a third line.
- Rarely, Claude cannot write a reply honestly without asking (their message is unclear, a
  claim it cannot ground). Then the card asks one question in its one soft grey box, in place
  of the draft until answered: the words it is about as a small quote, the question, and a tap
  to answer where one fits (yes or no, a choice), the work's own `needs`, drawn by the page's
  one shared renderer. The answer resumes that same reply, its line showing it. Why: asked
  where the reply is, never a thread of bubbles somewhere else.
- The trash keeps one place for putting anyone or anything away: the person's choices, and
  for an unsent first note "set this note aside" as well.

## The trash

- The word is trash, never bin, in everything a person reads: its label, its tips and
  its help. (the maintainer, 2026-11-05; the no-bin words test)

- One icon puts anything away: the trash, top right of every live card. Never an x.
- One possible answer: done at once, with Undo. Several: a short sheet of buttons, one a
  choice, the one tapped done at once (never a choice and then a second button), and Undo
  putting every part back. (trash tests, design test)
- The choices: a job (not this role, the pay, the place, my field, no more from the employer;
  posted too long ago only where it was, closed only where it has); a draft (the same); a
  message (set it aside, or the person's choices); a person (hide this for a week where it is
  a To do row, let it go where they have not replied, don't contact, not that employer any
  more, in touch another way); an interview
  or an application (they said no, I withdrew, stopped waiting); a reminder in To do (hide it
  for a week, and "1 hidden this week: Show" at the end of To do brings it back, as "1 set
  aside: Show" does in Jobs); a booked call on Coming up (the call is off, one answer, its
  row gone at once). "I have applied" is under a job's More and on a draft's face,
  never in the trash as well.
- A trash sheet whose card has a box (a person, a message, a job, a draft, an interview) ends
  with **Something else**: the sheet closes and that card's box opens under it, its field
  focused, as Something else under More does; a person's trash in To do opens their box
  under that To do card, never a jump to Contacts (the maintainer, 2026-11-06). Why: none of the reasons fitted what was going on, and there was no
  way to say it in words (the maintainer, 2026-11-05). (trash something-else test)
- Tomorrow and Next week put a dated row off to that day in the engine: put off is never done.
  It leaves To do with "1 put off: Show" at its end, never under Done today nor in "x of N
  done", and its person's card in Contacts says "Put off until <day>" with nothing owed on its
  face. (reviewer's walk test)
- A reason that changes something says so when it is given ("Set aside. Fewer jobs outside
  your field from now on.").
- A card or a row the person has finished (binned, sent, answered, done, closed, no more
  messages) leaves its list at once, before Claude has caught up. Its Undo is in the toast
  while the toast is up, and on its own line only after ("11 closed: Show"): never both.

## Buttons, links and taps

- A card's actions are one row of pills, all one height, radius and padding, the same gap
  between them. The one next step (Draft this, See the draft, Copy, Send) is the filled pill:
  the accent fill with its own ink, semibold, once a screen (its first); every other card's
  next step is the soft pill in the semibold weight. Every other action beside it is the soft
  grey pill (the raised fill with its 3:1 edge, regular weight), and More is a soft pill too. At
  most three before More: the next step and one or two others; rarer actions go under More,
  and a duplicate or a dead button goes. Why: text buttons beside pills read as clutter and
  as less tappable (the maintainer, 2026-11-05: "some things are just text buttons which
  makes it look quite cluttered"), and one filled pill a screen, with each card's next step
  in the semibold weight, says at a glance what to do.
  (action-row test, layout 7)
- Before any action goes on a card, in this order: is it needed at all (if not, it goes)? Can
  the app do it by itself (then it does, and says so)? Can it merge with another (one
  control)? Only then, where it lives: the card (the next step and at most two others), the
  pencil, the trash's choices, or More (rare). A card's budget is one filled pill, two soft
  pills, the pencil, the trash, and the gauge where Claude wakes, its grey box's pills counted
  among them: past it, the row's others go under More; more means a step above was
  skipped. Settings gets no new option for it: a default that suits nearly everyone is the
  setting. (the maintainer, 2026-11-05: "we also don't want to clutter the page with buttons
  and options and configurations by doing this, so be very smart about it"; action-row test)
- **Stop Claude** is the one control that calls off Claude's work, wherever it shows: a card in
  Claude's work, a card's own work line, a reply or a change being written, a card's question,
  a group's line, the Chat's quick answer. A quiet pill, faintly red, labelled "Stop Claude"
  ("Stop Claude's work on <what>" to a screen reader), so it never reads as putting the job or
  the message away. A Cancel that only closes a box before anything is sent stays Cancel.
  (the maintainer, 2026-11-05: "Don't do it" and "Cancel" were ambiguous; Stop Claude test)
- A suggestion's way to say no is **Dismiss** ("Dismiss this suggestion"), never "No thanks",
  which read as calling something off. (the maintainer, 2026-11-05)
- Underlined text is only a link inside a sentence ("3 more: Show them", a name in a line),
  never a control in a row of actions. Rose is for links inside a sentence. (action-row test)
- More holds only what is genuinely rare for that card: five at most, a short list grouped by
  kind with no long explanations. Never an action people use often, never a pencil or a way to
  edit, never a fact that belongs on the card's line of facts or its "?"; a card with nothing
  rare has no More, and anything nobody uses goes. (the maintainer, 2026-11-05: "shouldn't More
  be for genuine additional features, not just burying EVERYTHING under there"; action-row test)
- More's toggle stays in its row beside the card's other pills, open or shut, and its panel
  opens under the row, on every card. Its buttons are one row of pills that wraps only at the
  panel's width, never a line a kind; a note or a link in a sentence follows them. Why: opened
  inside the row it took the whole width and dropped below "I sent it", and a row a kind left
  one button alone on a line (the maintainer, 2026-11-05). (More test)
- The last thing under every live card's More is **Something else**: it opens a box right
  under that card ("Anything else about Juno at Lark?", Ask Claude, Cancel), and what is sent
  goes to Claude as work about that card, in the card's own thread (`talk/card-<kind>-<id>`,
  `args.about`), never in the Chat. The question and Claude's answer show under the card, the
  work line between (Saved, Waiting its turn, Claude is on it, Cancel); a finished exchange stays two days
  with Ask more and Hide, then folds away. It is the way to ask or tell Claude anything the
  card's buttons do not cover, so it is not counted in More's five and carries no gauge: the
  box's Ask Claude does. Under the answer, the one or two next steps it made, read from the
  records and never from its words (a draft it wrote or changed, with that draft's own Copy
  and I sent it, which says "Sent" once sent), none for an answer that only explained; the
  names of the card's people in the answer open them. A long exchange shows its latest,
  "Earlier (N)" opening the rest in place in a box that scrolls inside itself; a long answer
  is clipped with Show all, a day-old one to its first line; a hidden or folded exchange
  leaves "Claude answered 5 Nov · Show". The box keeps its own hairline, so it stays apart
  from a hovered card. A change asked with the pencil is one block under the draft: "You
  asked" and the words, two lines with Show all, then its state and Stop Claude; "New
  version" only once the new words are on the card. Why: everything opening the Chat clogged it with tasks, and an answer
  belongs where its question was asked (the maintainer, 2026-11-05: "it opens a text box UNDER
  THAT PARTICULAR THING IM QUERYING ... and then the response shows underneath"; More test)
- The same box serves an ask that belongs to a place rather than a card (`PLACES`): Paste a
  message under Contacts' header, an interview not on the list under Coming up's, Something looks wrong
  under Settings (no popup first; the makers' link quiet under its box), Tidy these up under Your rules, Bring them back on
  its own row. The Chat keeps only what is a conversation or needs pictures: setting up, a
  practice interview, screenshots, and how the page works. (the maintainer, 2026-11-05: "quite
  a few places in the app which unecessarily go to chat and could be done inline")
- A draft whose words send the resume ("resume attached", "here's my resume") carries the
  file under it, "Goes with it: Your resume (PDF)", saved in a tap to attach; the engine's
  `sends` says which (the maintainer, 2026-11-05: "it would be great if the actual document
  was linked there").
- Every control that wakes Claude carries the gauge beside it: the same bars, size and place,
  with its minutes shown, and its "?" or a long press says it in one line ("About 3 minutes of
  Claude's time, from your Claude allowance"). A control that only runs code (marking sent, a
  date, the trash, a word changed in place) has none, so what is free can be seen. The minutes
  are the engine's, from this copy's own finished work of that kind and size where it has any,
  and a button that starts several says the time for all of them. (the maintainer,
  2026-11-05: the gauge "is meant to deter someone from spending tokens unnecessarily")
- Text on a pill reads at 4.5:1 and a soft pill's edge at 3:1 against its card, in both looks;
  every control shows its focus ring. (colour tests, layout 14)
- On a phone everything is drawn small with a full-size tap area (44px), and hover styles
  apply only on devices that hover, so nothing needs two taps. A switch or a checkbox is reached
  through its whole row, its label. (target probe, layout 14)
- Three sizes: Smaller, Standard (the default), Larger, Smaller and Larger each drawn in the
  size it sets, the control keeping its height and targets. (the maintainer, 4.12; settings
  fold test)

## Colour, type and space

- Colours are the tokens in `palettes.py`, never a raw value. Light: a near-white page, white
  cards, ink buttons with white text (7.3:1). Dark: the main Rosé Pine. (colour tests)
- A character count is the quiet grey while within its limit and red over it; amber only while
  the words are being changed and are in the last twentieth of the limit, where an edit could
  take them over (`app_model.count_of`, `near_at`). One rule for every count of a message: a
  draft, a reply, the pencil's field and "I changed it first". Why: 291 of 300 in amber read as
  a warning about a note that was fine (the maintainer, 2026-11-07). (waiting-note tests)
- Spacing keeps to 0, 2, 4, 8, 12, 16, 20, 24, 32 and 44 pixels; a first screen keeps to
  seven type styles, three weights and three tones. (layout 10, 11)

## Moving parts

- Running work turns a small spinner and sweeps its bar; waiting work breathes; an update is a
  moving line under the header. Reduced motion stills all of it. (motion test)
- Work says where it stands in words: running, Next, Waiting its turn, Not sent yet, Waking Claude,
  Sent, No answer yet, Waiting for Claude (with when it was asked), in the same chat. "Claude
  is on it" only for work Claude has begun; a step's clock only from a few seconds in, and
  none where the work counts its own progress. The top pill names the one thing running.
  Work waiting its turn behind the big jobs stays "Waiting its turn" however long it waits ("In line" left people asking what it meant, the maintainer, 2026-11-06), and drafts
  written together show their batch's progress and one Stop. The chat's line under a message
  is the same words as its card. (what-reaches-Claude tests)
- A tap's write has the Chat's own limit, 20 seconds: past a few seconds its card says
  "Saving…", and one not saved is undone on its card at once, said in its toast while it is
  up and then on its card, in words that name what to tap ("Not saved. Tap I sent it again.")
  with Try again. Why: a store that never answered left "I sent it" gone from its card with
  nothing said (the maintainer, 2026-11-05). (send-tap test)
- A tap is "Saved" once written and "Done" once Claude's receipt says so. Saved says what it
  waits for and where it shows: "Claude makes the change next, and this line says Done when it
  has", what it waits behind ("after “Reply to Juno”", light work running in the chat that
  answers the page), or that Claude's helper is not answering. A tap that is work for Claude
  (the LinkedIn download) links to its card in Claude's work, which says the same ("Next,
  after ..."). One Claude could not do says why in Claude's own words ("changed since you saw
  it" only when it did), with the field to give what it needs, on its card and as a To do
  card. (what-reaches-Claude tests, spaces-its-settings test)
- A live update redraws only the card, panel or row that changed: the rest stays as it was
  drawn, so a phone scrolling fast never meets a blank page. (spaces-its-settings test)
- A control on a card that starts work (an answer, a date, Send) never leaves the person
  wondering, and every page helper uses the one work-state drawing (Claude's work cards),
  never a second one: (1) the tap shows at once on that card ("Saved: in line, after ...",
  "Waking Claude", "Claude is on it: <step>" with the spinner, a clock only after a few
  seconds); (2) "Done" only once the result is on that card in the same redraw, and
  "Finished: putting it on your page" while it is not yet, without a reload; (3) one quiet
  Cancel on whatever is queued or running: queued goes at once, running says "Stopping" then
  "Stopped", and what the person gave is kept; (4) only that card redraws, nothing jumps,
  reduced motion is respected, and it reads the same after a reload; (5) a failure says why,
  with Try again. (answers test, what-reaches-Claude tests)

## Asking the person

- Work asks the person something mid-way only when it cannot be finished honestly without
  them: an unclear or ungrounded claim, a missing fact, two readings of their message. Never
  for a preference a default answers. One question a card at a time, never a thread of
  bubbles. (the maintainer, 2026-11-05: "only if it's absolutely necessary"; answers test)
- The one shape, wherever it is asked: `needs: {question, about, work, answer: {kind,
  choices, min, max, key, label, time}}`. `question` is one plain sentence; `about` the exact
  words of the draft or of their message it concerns, shown quoted in a small block;
  `work` the id of the work it resumes; `answer.kind` one of `yesno`, `choice`, `date`,
  `time`, `number`, `scale` or `text`; `choices` two to six `{value, label}` for a choice;
  `min` and `max` for a number or a scale; `time`, on a date, the key its time goes under
  where one is needed. Text only when nothing else fits. A work item stopped for the person
  carries it (`app.py done --question ... --about ... --answer <kind>`), and so may any item
  a card draws; a tap the engine refused carries the same kinds as its receipt's `ask`
  `{key, label, kind, choices, time}`.
- The card shows it in its one soft grey box: the quote, the question, and the control that
  fits (a row of chips for a few choices, Yes and No, a date picker with the time beside it
  where one is needed, a slider for a scale, a number field, a line of text only when nothing
  else fits). The answer goes straight to the engine and resumes that same work, which shows
  its progress as above. Never "Say it in Chat" for something a control can answer; Chat is
  for conversation. (answers test)

## Words and settings

- Plain words: no git, branch, command or config, no file names, no ids.
- One date a card, said one way: a day gone by as "12 Sept", a day ahead with its weekday. A
  card about someone shows the day they wrote (or you did); its corner says only "Overdue".
  What someone asked for leads the card, and its button does it ("Make a CV for Juno").
- Where a person stands, what is owed, who the person's own rules keep back and every count
  of them are the engine's one answer (`app_model.standing`): the page renders them and never
  works them out again. A message that breaks the person's rules is never offered as ready.
- Counts agree: a tab, a summary and a badge count the same things, and they count cards:
  To do's badge is its late or due-today cards, a checklist card is one with its own "2 of 8
  done", and a button that starts several says the time for all of them. Counting a checklist
  of 25 people as 25 made a calm screen read as an emergency (the UX review, 2026-11-05).
  To do says how far today has gone ("3 of 9 done today") and, once nothing is left, that it
  is all done and what comes next.
- Nothing asks what a default answers. A choice becomes a setting only where people really
  differ, and work goes where it can run without anyone choosing (one chat answers the page;
  only the brief needs the cloud). (place and routing tests)
- An opened setting reads across a wide panel: its words on the left, its buttons at the right
  edge under the row's own value, and a tap's line under both with its Undo at the right; on a
  phone the buttons follow the words. One way to do each thing in it. A short single choice is
  a row of chips, still a radio group, that wraps on a phone. (spaces-its-settings test)
- File names (Settings > You) is the one place a file name is shown: its value is an example
  from the person's own name and latest employer, and each chip shows its own, the one
  recommended for their country marked. It names only the copies they download and send; the
  files Claude keeps keep theirs. Default: the person, the employer, then the document, the
  word by their market (docpaths.FILE_NAME_PRESETS). (file names test)
- Many of one kind in Settings are one row that opens them, never a row each: "Employers
  you've turned down (N)" with what they left out, each name with its small trash; what Claude
  learned has one home, "What you have taught it", grouped by area, a rule a line with its day
  small at the end; Your rules links to it. A long section (Your rules, Jobs you hid, each area
  of what it learned, What's new) shows its first few with "Show all" or "Show more". Advanced,
  folded, holds only what can slow things down or use more of the Claude allowance, and says so
  in one line; everything harmless lives where it belongs (Look, This device). A reason is said
  in the person's voice ("You cleared these"), never the engine's. (the maintainer, 4.12;
  settings fold test)
- Each setting has one home in Settings. Where a setting also has a control elsewhere (the
  Brief's bell, a break from To do), both open the same sheet and can never disagree.
- Every control does something visible (the sweep test taps all of them) and every action
  reaches the engine and is applied (the round-trip tests).

## Before a change ships

Run the browser tests, then look at the screen you changed on a phone and on a laptop, in
light and dark. A rule here that a change needs to break is changed here first, with its test.
