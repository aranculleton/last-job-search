# The page's design language

For whoever changes the page (`templates/app/`): a chat or a person. Each rule says which
test holds it, so a change that breaks one fails before it ships. The person reading the
page is tired, often on a phone, and not technical: every screen answers "what do I do
next?" in its first lines, and nothing asks for a decision a default could make.

## Places

- Seven places: **Brief** (the home screen), **To do**, **Jobs** (Found, Drafts, Applied),
  **Contacts** (one list, each person with what to send them), **Coming up** and **Chat**
  together in the side menu, and **Settings** alone at its foot. Five sit in the phone's tab
  bar (Brief, To do, Jobs, Contacts, Chat); To do alone carries a coloured badge, and Chat a
  small grey dot while an answer waits unseen. (layout 6, nav order test; contacts rules test)
- Each screen: its title, one plain summary line, at most three blocks before the first item.
  (layout 1 to 3)
- A long list opens on its first few and folds the rest one tap below ("Show 6 more"): To do
  five today, Drafts five, Contacts who has a message to send and who needs you. Never a
  filter left on. The fold's count is what it still holds: once tapped it goes, and its first
  card takes the focus; "Show 1 more" never stays over what it showed. (layout 2, crowd tests,
  fold test)
- To do's five are what is late or due today first, then the questions; setting-up cards wait
  behind the fold. (tired-person tests)
- To do holds only what there is to do. Someone who has not answered the person's limit of
  messages is never a card there, nor counted. In Contacts they wait below the fold with the
  others who need nothing, their row saying to leave it unless they write back, with Close.
  (contacts rules test)
- Claude's work has one button on every screen, the pill in the header. On a wide screen it
  opens and closes the panel on the right, as the menu's "Icons only" folds, remembered on the
  device (open beside every screen but the Brief until the person chooses); narrower, it opens
  as a panel on the right, and on a phone as a sheet from the bottom. (pill tests)
- In Claude's work, four or more of one kind waiting, or finished, are one card with their
  count and the first few names; Show lists them. Nobody scrolls past fifty cards. (run test)

## Cards and lists

- Every item is its own soft card: a 1px line, rounded corners, no shadow, 8px from the next.
  Only what floats (a sheet, a menu, a toast) has a shadow. Nothing has a line down its side.
  (design test)
- A card reads top down: its top line (a kind or a score, the title, a state pill, the bin),
  one line of facts, at most one block in a soft grey box (a question or a suggestion), then
  its actions: one row of pills (Buttons, below). (layout 7, 8, action-row test)
- A job card's line of facts says when it was posted and the pay where stated; why it scored
  what it did is the first line under More. A drafted role's card in Found opens its draft,
  where "I have applied" is; a closed one offers only setting it aside. (jobs page tests)
- A state is a small tinted pill in words a person uses, never a code word: ok green, info
  blue, warn amber, bad red, held violet, waiting grey. (status audit, colour tests)
- A To do row whose message is already drafted says "Draft ready" and its one button opens
  the draft, never drafts it again; two or more drafted are one card, "N messages ready to
  send", a row a person opening their draft and one button opening Contacts at the drafted
  people. (drafted messages tests)
- Many of one small thing are one checklist card, a row an item: each row has one action of
  its own beside its bin, and the card's own actions keep to the card's anatomy above.
  (layout 8)
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
  the way its work card reads it (Saved, Waiting for Claude, Next, In line, Claude is on it
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
  "Overdue" in the corner only when a follow-up or the message is late; the draft with Copy
  and the pencil in its corner (a subject's Copy an icon at its line's end); then one row of
  pills: one filled (I sent it once copied, or the one owed step), at most two soft ones
  ("They replied"), and More. With a message on the card, "They replied" waits under More.
  Why: five buttons a card read as five jobs, and three dates a card as none.
- More is for what is rare, a handful at most: their profile link, a call booked, they sent
  me a job, the referral, read their profile, Claude's ideas and notes. Never editing (the
  pencil), never the card's facts (its line), and no More on a card with nothing
  rare. Why: More became a drawer of everything, so nothing in it was found.
- The pencil changes the draft in place: the words edited where they are (what Copy copies
  and I sent it logs), and one small field, "or tell Claude what to change", with Shorter,
  Warmer and More formal, each queuing the change with the card's line. Why: a slight edit is
  the commonest change, and it was buried under More.
- A draft that fails a check with a clear fix (too long for the channel, a phrase that reads
  machine-written, asking them for a job, a rule of theirs) is fixed by Claude by itself: the
  engine finds it (`app_model.message_fix`) and the view queues the fix with no tap; the card
  says "Claude is fixing it: <why>" and offers the draft as ready only once it passes. Never a
  Fix it button. Tried twice and still failing, it says so, with the pencil to change it. A
  fact only the person knows is asked through the one rare question. Why: where there is
  clearly a recommended option, the app does it.
- What wakes Claude carries its cost beside it (the gauge: "Draft my reply", "Ask Claude",
  the chips, "Draft the follow-up"); what only the page does (I sent it, an edit in place,
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

## The bin

- One icon puts anything away: the bin, top right of every live card. Never an x.
- One possible answer: done at once, with Undo. Several: a short sheet of buttons, one a
  choice, the one tapped done at once (never a choice and then a second button), and Undo
  putting every part back. (bin tests, design test)
- The choices: a job (not this role, the pay, the place, my field, no more from the employer;
  posted too long ago only where it was, closed only where it has); a draft (the same); a
  message (set it aside, or the person's choices); a person (hide this for a week where it is
  a To do row, let it go where they have not replied, don't contact, not that employer any
  more, in touch another way); an interview
  or an application (they said no, I withdrew, stopped waiting); a reminder in To do (hide it
  for a week, and "1 hidden this week: Show" at the end of To do brings it back, as "1 set
  aside: Show" does in Jobs). "I have applied" is under a job's More and on a draft's face,
  never in the bin as well.
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
  pencil, the bin's choices, or More (rare). A card's budget is one filled pill, two soft
  pills, the pencil, the bin, and the gauge where Claude wakes; more means a step above was
  skipped. Settings gets no new option for it: a default that suits nearly everyone is the
  setting. (the maintainer, 2026-11-05: "we also don't want to clutter the page with buttons
  and options and configurations by doing this, so be very smart about it"; action-row test)
- Underlined text is only a link inside a sentence ("3 more: Show them", a name in a line),
  never a control in a row of actions. Rose is for links inside a sentence. (action-row test)
- More holds only what is genuinely rare for that card: five at most, a short list grouped by
  kind with no long explanations. Never an action people use often, never a pencil or a way to
  edit, never a fact that belongs on the card's line of facts or its "?"; a card with nothing
  rare has no More, and anything nobody uses goes. (the maintainer, 2026-11-05: "shouldn't More
  be for genuine additional features, not just burying EVERYTHING under there"; action-row test)
- Every control that wakes Claude carries the gauge beside it: the same bars, size and place,
  with its minutes shown, and its "?" or a long press says it in one line ("About 3 minutes of
  Claude's time, from your Claude allowance"). A control that only runs code (marking sent, a
  date, the bin, a word changed in place) has none, so what is free can be seen. The minutes
  are the engine's, from this copy's own finished work of that kind and size where it has any,
  and a button that starts several says the time for all of them. (the maintainer,
  2026-11-05: the gauge "is meant to deter someone from spending tokens unnecessarily")
- Text on a pill reads at 4.5:1 and a soft pill's edge at 3:1 against its card, in both looks;
  every control shows its focus ring. (colour tests, layout 14)
- On a phone everything is drawn small with a full-size tap area (44px), and hover styles
  apply only on devices that hover, so nothing needs two taps. (target probe, layout 14)
- Three sizes: Smaller, Standard (the default), Larger.

## Colour, type and space

- Colours are the tokens in `palettes.py`, never a raw value. Light: a near-white page, white
  cards, ink buttons with white text (7.3:1). Dark: the main Rosé Pine. (colour tests)
- Spacing keeps to 0, 2, 4, 8, 12, 16, 20, 24, 32 and 44 pixels; a first screen keeps to
  seven type styles, three weights and three tones. (layout 10, 11)

## Moving parts

- Running work turns a small spinner and sweeps its bar; waiting work breathes; an update is a
  moving line under the header. Reduced motion stills all of it. (motion test)
- Work says where it stands in words: running, Next, In line, Not sent yet, Waking Claude,
  Sent, No answer yet, Waiting for Claude (with when it was asked), in the same chat. "Claude
  is on it" only for work Claude has begun; a step's clock only from a few seconds in, and
  none where the work counts its own progress. The top pill names the one thing running.
  Work waiting its turn behind the big jobs stays "In line" however long it waits, and drafts
  written together show their batch's progress and one Stop. The chat's line under a message
  is the same words as its card. (what-reaches-Claude tests)
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
- Each setting has one home in Settings. Where a setting also has a control elsewhere (the
  Brief's bell, a break from To do), both open the same sheet and can never disagree.
- Every control does something visible (the sweep test taps all of them) and every action
  reaches the engine and is applied (the round-trip tests).

## Before a change ships

Run the browser tests, then look at the screen you changed on a phone and on a laptop, in
light and dark. A rule here that a change needs to break is changed here first, with its test.
