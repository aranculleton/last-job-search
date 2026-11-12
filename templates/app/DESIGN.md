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
  the summary, centred on its line, never an underlined line under it; what Claude is doing is the header's work
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
  To do's own style, under its own small heading, "When you have a minute" (under "Needs your
  answer" it read as one more question, the screen review, 2026-11-11): its title "Help Claude
  do more", the first one's one plain line saying what it gives ("Your profile: every resume
  and letter is built from it"), and its one pill to start it, which puts that one's own card
  in its place; the rest fold under "N more ways to help Claude".
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
  a new day under More; they said no and I withdrew in its trash. Two days before and the day
  before, practice is on its face instead of the calendar: "Practise 3 questions" (its prep
  opened with the answers hidden, at the first likely question) beside Read your prep, with
  a line saying so ("Today: practise 3 questions, about 10 minutes"), or Practise with Claude
  where there is no live prep (the UX review, 2026-11-10, U-4). Coming up's row leads with the
  same step on those days (`ivPractiseDay`, one answer for every place). On those days Add to
  calendar waits under More after the three, then Something else, and nothing else is in it:
  when the prep was made is on the card's line of facts ("Prep ready, updated 29 min ago"),
  with the pencil that changes it beside it, and "Also at" is on the application's own page.
  Why: More opened eleven lines deep, the prep's time, "Also at", a tip about the pencil and
  "Edit the prep" among its buttons (the maintainer, 2026-11-11). (one-card tests, More test)
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
  scrolling up (the maintainer, 2026-11-06). (chat panel tests) On a phone the Chat is as tall
  as the room under the header as it is drawn, so it opens with its first words in sight,
  never behind the header (taken as 56px, its first words slid under the Refresh pill,
  2026-11-11). (overlap test: chat opens)
  With no messages yet the starters and the box sit under the header, with no subtitle; once
  there are messages the box keeps to the foot. Why: an empty Chat stood its starters at the
  foot of a blank screen and said "Ask anything" three ways (the screen review, 2026-11-11).
  (empty chat tests)
- In Claude's work, four or more of one kind waiting, or finished, are one card with their
  count and the first few names; Show lists them. Nobody scrolls past fifty cards. (run test)
- Over Claude's work, with two or more things going, one short strip says what runs now and
  what waits, in the order Claude takes it, a big job said as running in a chat of its own, and
  a big job's card says it does not wait for other work. Why: with several things asked for in
  a row nobody could tell what was queued, in what order, or why a resume seemed to sit behind
  small changes (issue #238). Making a resume downloadable is a stage of the resume's own card,
  "On its way", never a card of its own (#237). (queue test)
- Claude's work says its count once, in the header's pill: no line under its title repeats
  it, and "Nothing is sent." is not said over the cards. Each running or waiting card has its
  title, one short state with its clock ("Waking Claude · 1m 4s", never a chip and a line
  both saying it), its bar (none once it runs past its estimate: its time so far says how long,
  never a bar stuck at its end, #238), and Stop Claude at the end of the clock's line, never on a line
  of its own; in a narrow panel the state goes under the title rather than squeeze it. The
  sheet's Close and the panel's Hide are soft pills on the title's own line (2026-11-10). Its
  actions share the clock's line only while both fit, the words keeping a short line's width,
  else they take the line under it; a finished run's trash is in its corner on its title's
  line. Why: in a column of their own beside the words, three pills drew "38 messages ready to
  send." a letter a line (the screen review, 2026-11-11). (overlap test: crushed) A finished one is a compact row under
  "finished": its title and one-line result, the time small at its end, the whole row opening
  where its record lives (a person's work in Contacts on that person, a job's in Jobs, a
  draft's in its draft), its trash shown on hover or focus; no Done chip, no Open button.
  (the maintainer, 2026-11-05; Stop Claude tests, compact row test)
- **A laptop's Brief is one screen.** From 960px wide the Brief's panels are two rows (Today,
  Coming up and Next; Waiting on you, Jobs, News and the numbers) that share the window's
  height, with the privacy line and the tip on one last row beside the Chat button, so the
  page does not scroll at 1000 by 560, 1280 by 720 or 1440 by 900. Each list shows as many as
  its room holds and gives way below to one, its panel's own "All ..." opening the rest, at
  every width, two columns too: nothing is cut off inside a panel (Next three cut its third step
  in half at a tablet's width, the screen review, 2026-11-11); News,
  with no screen of its own, says "2 more" and opens them in place. On a short window (660px
  or less) the numbers are one line under the greeting, opening Progress with its chart. A
  phone scrolls. (the maintainer, 2026-11-05; fit tests)
- A Brief row is a line of words: what it is with its day inside it ("Read the prep for the
  phone screen · Wed 28 Oct, 13:00"), wrapping from its start, never centred and never the day
  a column of its own squeezing the words (the review, 2026-11-10, at the Larger size). (room
  test)
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
  does one. Its axis steps by 1, 2 or 5 times a power of ten, five lines at most, whatever a week
  holds (a week of 400 drew 42 numbers on top of each other, 2026-11-11). Progress says the same, its "Each week" card open on its chart, every fold in it
  with the chevron Settings' rows use (folded, it read as a heading over an empty box, the
  review, 2026-11-10). (the maintainer, 2026-11-10: "not make it look like im
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
  Claude is doing is the header's work pill and each card's own line, never a line here. While
  a search runs, Find jobs is the soft pill of it, "Finding jobs · about 5 min left" in its
  card's own words, with no gauge: "38 min of Claude" beside it read as the wait (the screen
  review, 2026-11-11). (going-on tests)
- A Jobs card says its facts on one line (the employer, the town, never its region and country,
  when it was posted and found, the pay where stated) ending with its details fold: "Why"
  where it has a score, else "Details", short labelled rows in one size and one tone (why it
  scored, a watch-out apart, worth knowing, skills, the posting, "Also at" the employer by kind,
  each link naming what it opens). More holds only the rare actions; a card with none has no More.
  The last fact, "Why" and the pencil keep together at the line's end, never "Why" or the
  pencil alone on a line, and a
  draft's lines are a card's 8px apart, as a find's are (2026-11-10). (jobs page tests, layout
  16, room test)
- A dot between facts never starts or ends a line, and a day said in words ("Sun 20 Sept") is
  never broken over two: a dot is held to the word after it, and one a line would still start
  or end with goes out of sight (app.js `wordsAdd`, `sepFit`). A file's name or the page's
  address wraps only after an underscore, a slash or a dot, never inside a word. Why: "·
  Applied 3 Nov" with nothing before it, "Interview · Supply Chain Analyst ·" over a pill, a
  row's "· Recruiter" under its name, and a name broken after its 41st letter (the screen
  review, 2026-11-11). (overlap test: separator, crushed)
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
- A Coming up row is its time, its title, and one line under it saying what it is and
  whether its prep is ready ("Interview · Supply Chain Analyst · Prep ready"); its icons keep
  their own places, the pencil, the calendar, then the trash, so they line up down the list.
  On a phone the title is drawn its own height and reaches its tap down into that line, whose
  own link is drawn over the reach. Why: a line each, each its own 44px, made a row of three
  short lines 190px tall, and the calendar moved a place on every row with a trash (the
  maintainer, 2026-11-10: "inline and things are good"). (room test)
  A time from another zone ("15:00 Toronto time (20:00 here)") wraps inside its own column,
  the time here kept whole under the person's clock, and the column is wider on every row of
  the list alike, so the rows still line up. Why: held to one line it ran under the title, over
  the row's line of facts and into its pill on a laptop (the maintainer, 2026-11-11).
  (overlap test)
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
- **An interview's live prep reads full screen, one interview in the order it runs**, laid out
  as the maintainer's call-prep page (2026-11-10: "this is what i want ... more tailored to
  interviews"), on every screen, and kept open beside the call. **Nothing needs opening before
  it can be read** (the maintainer, 2026-11-11): there is no fold, switch or "Show" in it. The
  head: the day and the drafts the person asked for in one quiet line under the title (in large
  type over lines of their own, At a glance began past a phone's first screen where the words
  drew longer, the German run, 2026-11-12), then one pill, Practise with Claude (Update my prep
  and the calendar stay on its card in Coming up). Then the bar, the one
  thing that stays at the top while the prep scrolls, one solid ground flush with the header
  down to under its chips: find ("They asked..."; "/" goes to it, Esc clears it) with "Points
  first" or "Script first" beside it, never after the chips, and under them a chip to every
  part, then Stories and Your notes, one row on a phone that scrolls sideways inside itself, its
  far end fading. One chip is filled, the part whose heading was last scrolled up to the bar
  (the first part from the top of the prep until the next heading gets there; at the end of the
  prep, where the last parts cannot get there, the one tapped, else the last in view), marked as the
  prep scrolls (the one thing that changes by itself) and kept in view in its row as the mark
  moves, a row moved sideways by hand left where it was put until then; nothing else
  looks filled, a chip under the mouse underlined instead of shaded; a part with a known
  question wears a gold dot, the chip's name and hover saying why. A jump on a phone lands under
  the bar as it will be once there, the bar one row before the scroll starts and holding its
  shape until it ends (Safari stops a smooth scroll where the page changes shape under it). On a
  phone, once the prep is read under the bar, find, the order and the chips are one row, the bar
  keeping its room in the flow so nothing under it moves, whole again near the top and while find
  is in use. The bar's name for a screen reader is the timing in a line ("60 minutes in 5 parts,
  the last 7 minutes for your questions", a day of interviews in hours). Then At a glance, in a plain box:
  what they are known to ask (else the first likely question) with the part it is in and its
  gold dot, and two questions to ask them, each a plain line in the ink, never drawn as a link,
  and a tap to its place, and a guessed kind of interview said there with "Not this kind of
  interview?" one tap from the right one. **The opening is on the screen once** (the
  maintainer, 2026-11-12: At a glance, Say first and Tell me about yourself each said it): it is
  Part 1's Say first, never At a glance as well, and an answer whose first sentences say what
  its part's Say first says starts at "Start with your lines above, then:", a tap back to them.
  A test taken alone has nothing to say first: its parts keep in mind how it works. **The
  reading column uses the width** (up to 1200px, 1080 drawn on a 1440 screen; a narrow column
  between wide empty margins, the maintainer, 2026-11-12), and from 1180px a part's Say first
  and its questions sit side by side, Say first staying beside them under the bar as they
  scroll by wherever it fits between the bar and the lifelines. Each part: a small-capitals
  line (its number and minutes) and its title over a rule; "Say first" in a plain box, each
  line a bullet, the line to end on in italics, and under them all one quiet line, "They may
  follow with:" and the questions those lines may bring, a gold dot on one they are known to
  ask, each a tap going to its answer and marking it until a moment after it arrives, never a
  pill between the lines being read aloud (the maintainer, 2026-11-12); then its questions as
  cards, the question first and who asks after it, small, a gold dot on one they are known to
  ask. **What is read aloud is the large type**: the lines said first, the line to end on and
  the script, a quarter larger than the words round them (a step less on a phone), with room
  between the lines and never more than about 95 characters a line; the labels, who asks and
  the notes under an answer are small and quiet. **Every answer shows both ways at once**: the
  script to read aloud (full ink) and the same answer as points (the first one bold and
  larger), in the order the person picked, the second under a thin rule; nothing redraws when
  they flip it. **Follow-ups are choices, never folds of the answer**: under an answer, "They
  may ask next" and a row a follow-up; the one tapped opens both ways of its answer in place,
  under its own row, with its own follow-ups as rows under that, three deep, the other rows
  staying where they are; the rows on the open path are filled, a tap on one closes it, and
  each open answer ends with the way back up ("Back to “...”", or "Close this answer"), the
  row tapped keeping the focus (the maintainer, 2026-11-12: "more dynamic"). The follow-ups after any story are said
  once, at the part's foot ("After any story here, they may ask"), never under each question.
  The questions to ask them sit in the last part, each with what to ask next to each likely
  answer as a plain line ("If they say ... → ask: ..."). Find looks through what to say, both
  ways of every answer and every follow-up at any depth, and a follow-up it finds is picked so
  its answer is in view. Then the stories, each once with the questions it answers, and the
  notes that are the person's alone, pay and notice among them, with the answers to avoid as a
  plain list, last in a gold box; the last line says Claude does not join, listen or record. A
  term is a dotted word inside its sentence, never a pill: it opens a small box (at most 272px
  wide) under the line after its own, or over its own line where that would not fit, never
  covering the line being read or the next one, between the bar and the lifelines, and never a
  panel or a dimmed page, saying what it means, what it means here and what it is like, with
  More for an example and the technical answer. A mouse moved onto the word and kept there 700ms
  opens it, never a word the text scrolled under a mouse left resting; leaving the word and the
  box closes it; focus opens it at once; a tap opens it until Esc, a tap outside or a second tap,
  the focus a tap gives the word being that same tap on a touch screen, never a first one. An Esc
  used inside the prep never also closes it.
  It never takes the focus, and nothing moves when it opens. Numbers in what to say are bold. At
  the foot of the screen, flush with it as the prep scrolls, a row of lifelines, each labelled
  by what it gives (Give me a moment, Could you repeat that?, Don't know it, and Salary, My
  notice and Where I'm based where the notes hold them; "Moment" and "Pay" were too terse under
  pressure, the maintainer, 2026-11-12), wrapping to a second row on a phone, a label wrapping
  inside its pill, never scrolling one past the edge: a tap says one line over the row itself, labelled
  "Only for you", never above it over the answers; it fades after a while, and a tap on it or
  Esc closes it at once. A coding part with steps says first what to say, then the problem as
  they set it and its answer, then its cockpit, all in view: what to ask before typing, the
  steps as a short checklist (a step's name and its line in one run of words, the next one
  marked, ticks kept only while it is open), what to say when stuck, the edge cases to name,
  handy code with Copy, and what to say you would do with more time; its other questions come
  after. Practice opens only from Practise 3 questions: each
  answer waits behind one "Show the answer" in place of both its ways, to be said first and
  then checked (the UX review, 2026-11-10, U-4), for that opening only, so the prep read on the
  morning of the interview shows every answer. Every id in it carries the interview's, and its
  listeners are on its own root. Two of the page's rules give way here to the call-prep page:
  labels are small capitals, and an answer is drawn larger than the words around it, to be read
  at a glance mid-call. The words, the order and the timing are the engine's
  (`interview_live`). (live prep tests)
- Many of one small thing are one checklist card, a row an item: each row has its own next
  step and Done beside its trash, the trash keeping the rest (They replied, Tomorrow, Next week,
  the person's choices), and the card's own actions keep to the card's anatomy above.
  Its count is in its title ("Messages to send (7)"); its pill never says it again: only how
  many are overdue, where any are, and once one is done how far it has gone ("2 of 7 done").
  Why: "7 to send" over "Messages to send (7)" said one number twice (the screen review,
  2026-11-11). The quick answers' "1 of 4" stays: it says which question you are on.
  On a wide screen a row is one line, its name and how it stands side by side; the row spans
  the card, its trash at the card's edge (rows stopping short left the trash a column in
  mid-card, the screen review, 2026-11-11), and its buttons sit together at its end, just
  before the trash, every row's starting at one edge (the rows share the list's columns). Why:
  held a reading width from the name (the review, 2026-11-10: the button sat 650px from it),
  the buttons stood in a column halfway across the card with empty room after them and the
  trash alone at the edge, two places to look (the maintainer, 2026-11-12). A row's line of
  facts is one run of words, its dots kept wherever words stand on both sides of them, never
  a hole mid-line. On a phone the name is one line and where they work the muted line under it,
  beside the row's button. A row's button and its trash keep one line at any width, the words
  beside them giving way (at a tablet's width the trash fell under its button, 2026-11-11).
  (layout 8, one-card tests, room test, overlap test: alone)
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
  first wrote and how many messages each way, the engine's `exchange`, are on their page); in
  the corner what is next for you: "Ready to send" while a draft to them can go, whatever its
  kind, else where things stand ("Not written to", "Talking"), the same on their page (the
  screen review, 2026-11-11: Wren's said Ready to send and Ash's, as ready, Not written to); the draft with Copy
  and the pencil at the right end of its heading line ("Connection note", "Reply · LinkedIn": one line beside them on a phone, the screen review, 2026-11-11),
  the words taking the bubble's whole width, and on a phone the whole card's: only the name
  sits beside the initial (a subject's Copy an icon at its line's end, never alone on a line);
  then one row of
  pills: one filled (I sent it once copied, or the one owed step), at most two soft ones
  ("They replied"), and More. With a message on the card, "They replied" waits under More.
  Why: five buttons a card read as five jobs, and three dates a card as none. Floated into
  the bubble's corner, Copy and the pencil bent a note's first lines round them, three words a
  line on a phone, under an indent that left it two thirds of the screen (the maintainer,
  2026-11-10: "the design needs to be smart and not super padded").
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
- A draft's facts are one quiet line under it, in one tone, each in a few words from the
  engine: its count ("290/300", `count.short`), why it waits for their profile ("Waiting for
  their profile", `linkedin.reading.hold_short`, for where reading stands where the page is
  open: "Their profile is read next", "Reading their profile…" with the spinner in the app) and
  "Location not on record". What each means, in a sentence, is behind the line's one "?"
  (`linkedin.reading.hold`: "Claude reads it on your computer by itself, then rewrites this
  note", or "next time this page is open in the Claude app on your computer" on a phone or the
  web). Never a line a fact, and never an alert saying it again. A note held back on purpose
  (`hold_why`: people at the employer already wait, a hold on their record, Claude's own
  decision) keeps its reason on a line of its own, with its one way on. A first note waiting
  for its profile has no Copy; "Paste <name>'s profile" is the soft pill beside it where the
  page cannot read now, its gauge one note's rewrite (`app_alerts.paste_profile`), never a
  networking run's. Why: the line and an alert said the same twice, the paste read as "a lot of
  your allowance" (the maintainer, 2026-11-07), and five lines of different weights under one
  note did not read as one card (2026-11-09: "any better way to display"). (waiting-note and
  calm-card tests)
- Someone on hold (the engine's `on_hold`: a hold on their record, or Claude's own decision
  on the draft to them) is never in the list of people to act on. Everyone on hold is one
  group at the foot of the list, folded, titled with its count and the reason where they
  share one ("On hold: 2, waiting for a role to be posted", else "On hold: 3"), with Show.
  Inside, a card says "On hold" in its corner and why and until when in its one line, with
  no filled pill and They replied under More. A draft kept for them is folded away, with no
  Copy and no I sent it, and "Send it anyway" inside the fold is the one way on: it puts the
  card back in the list with the draft open. One who waits for a role has no draft at all:
  it is written for that role once it is posted, and they come back to the list by
  themselves, with "Draft the referral ask" as their step. Nobody on hold counts in "to
  send" or "need you", is a To do row, or is on the Brief. A search or a filter still finds
  them. Why: held notes sat among the people to act on with the draft open and a "Talking"
  state, so they read as waiting on the person (the maintainer, 2026-11-10). (on hold tests,
  `tests/test_the_on_hold_group_is_last_and_folded.py`)
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
- Putting off is not putting away: a To do card whose only choices are later (a dated
  reminder's Tomorrow or Next week, a week off) says "Later" with a clock in the trash's
  corner, the word shown; the trash stays where something goes (a person's card, with their
  choices). Why: one trash meant "later", "hide for a week" and "not this person" (the review,
  2026-11-10). (room test)
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
  never a control in a row of actions, nor a control standing on its own: a tip's Got it,
  Add all to your calendar, Add the time, the work panel's Hide, its sheet's Close and Your
  profile's Change are soft pills, on a computer a tip's drawn to its own line's height (the review, 2026-11-10). Rose is
  for links inside a sentence. (action-row test, room test)
- More holds only what is genuinely rare for that card: five at most, a short list grouped by
  kind with no long explanations. Never an action people use often, never a pencil or a way to
  edit, never a fact that belongs on the card's line of facts or its "?"; a card with nothing
  rare has no More, and anything nobody uses goes. (the maintainer, 2026-11-05: "shouldn't More
  be for genuine additional features, not just burying EVERYTHING under there"; action-row test)
- More's toggle stays in its row beside the card's other pills, open or shut, and its panel
  opens under the row, on every card. Where the row is too wide for its line, the pill before
  More goes down to the next line with it, never More alone (`moreFit`; under "Practise 3
  questions" and "Read your prep" on a phone, the screen review, 2026-11-11). Its buttons are one row of pills that wraps only at the
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
  from a hovered card. A change asked with the pencil is one soft grey block under the draft:
  "You asked" and the words, two lines with Show all, then its state with Stop Claude beside
  its words, never at the card's far edge; "New version" only once the new words are on the
  card. Words in one note's box about every note waiting for a profile, or naming the others,
  are done for them all (`tweak.about_others`: each put on the page's reading list), this note
  is left as it was, and the block says so at once (2026-11-09). Why: everything opening the Chat clogged it with tasks, and an answer
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
  with its minutes shown as Claude's ("2 min of Claude": a bare "38 min" beside Find jobs read
  as a wait, the review, 2026-11-10), and its "?" or a long press says it in one line ("About 3 minutes of
  Claude's time, from your Claude allowance"). A control that only runs code (marking sent, a
  date, the trash, a word changed in place) has none, so what is free can be seen. The minutes
  are the engine's, from this copy's own finished work of that kind and size where it has any,
  and a button that starts several says the time for all of them. A lesser choice says its
  own: "Draft the CV only" its CV-only drafts' time, else the draft's stages without the
  employer research it never runs (the screen review, 2026-11-11: it said the CV and letter's 9
  minutes). (the maintainer,
  2026-11-05: the gauge "is meant to deter someone from spending tokens unnecessarily")
- Text on a pill reads at 4.5:1 and a soft pill's edge at 3:1 against its card, in both looks;
  every control shows its focus ring. Words on the soft accent (an answer's box, your own
  message in a chat) are in the ink: the muted grey is 3.56:1 there in the dark (2026-11-11).
  Every word on every screen is checked in both looks (overlap test: faint). (colour tests, layout 14)
- On a phone everything is drawn at the page's own size with a full-size tap area (44px), and
  hover styles apply only on devices that hover, so nothing needs two taps. A phone's density
  comes from padding, never from shrinking type: a card's edge 12px, a row of pills 8px apart
  with 12px either side of a pill's words, a To do card's Later or trash in its corner, and the
  words to send in the body's size, a one-line setting a 44px row. Why: drawn at 85% a phone's body was 12.8px and its small
  words 11.2px in grey (the review, 2026-11-10); "1 job posting per screen" (the maintainer,
  2026-10-29) is answered by the padding. (room test, target probe) A switch or a checkbox is reached
  through its whole row, its label. (target probe, layout 14)
- On a computer every control is at least 24px each way where it is reached (WCAG 2.2, 2.5.8),
  at any of the page's sizes: a small one keeps its drawn look and reaches the rest through its
  `::after`; a row that is a link, and a fold's heading, are that tall; a setting's pill is its
  label's target, the whole pill. A text link inside a sentence keeps its line, as WCAG lets
  it. Why: the "?" was 20px, a tip's Got it 19px, a pencil 22px, "Show all" 13px and a
  setting's words 18px of its 36px pill (the screen review, 2026-11-11). (overlap test: small)
- Three sizes: Smaller, Standard (the default), Larger, Smaller and Larger each drawn in the
  size it sets, the control keeping its height and targets. On a phone Standard is 100%,
  Smaller the old 85% and Larger 115%. (the maintainer, 4.12; settings
  fold test)

## Colour, type and space

- A state is never its colour alone (WCAG 1.4.1): the header's dot is filled when connected
  and a ring while it waits, grey while it connects and amber while Claude is not listening;
  offline, read only and stopped are said in words on the line under the header. (room test)
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
  Sent, No answer yet, Waiting for Claude (with when it was asked), in the same chat. Work
  sent to a chat that is up says "Starting in a moment" for half a minute at most; not taken by
  then, it is "Waiting for Claude, asked at 10:42" with no clock running ("Changing it next ·
  starting in a moment · 1m 53s", the maintainer, 2026-11-09). "Claude
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
No words are drawn over other words or over a button, on any screen or view, at a phone's, a
tablet's or a laptop's width: the harness measures every line and every drawn control, and an
overlap meant to be there is named in the test with why (overlap test, on the sample and on its
extremes: two zones, long names). Why: a two-zone time ran over a row's words for a release and
only a person saw it (2026-11-11). The same run reads every screen and view, Settings with its
rows open, Claude's work, an application's page and the live prep, at 390, 768, 1280 and 1600
wide in both looks, for words crushed or broken, words cut off with nothing to say so, a dot
starting or ending a line, a control under 24px on a computer, More or a row's trash alone on
its line, words too faint, a chart's numbers piled up and a day written 2026-10-20; an
exception is named in the test with why (`DRAWN_ALLOW`).
