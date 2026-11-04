# The page's design language

For whoever changes the page (`templates/app/`): a chat or a person. Each rule says which
test holds it, so a change that breaks one fails before it ships. The person reading the
page is tired, often on a phone, and not technical: every screen answers "what do I do
next?" in its first lines, and nothing asks for a decision a default could make.

## Places

- Seven places: **Brief** (the home screen), **To do**, **Jobs** (Found, Drafts, Applied),
  **Contacts** (People, Messages), **Coming up** and **Chat** together in the side menu, and
  **Settings** alone at its foot. Five sit in the phone's tab bar (Brief, To do, Jobs,
  Contacts, Chat); To do alone carries a coloured badge, and Chat a small grey dot while an
  answer waits unseen. (layout 6, nav order test; contacts rules test)
- Each screen: its title, one plain summary line, at most three blocks before the first item.
  (layout 1 to 3)
- A long list opens on its first few and folds the rest one tap below ("Show 6 more"): To do
  five today, Drafts and Messages five, Contacts who needs you. Never a filter left on.
  (layout 2, crowd tests)
- To do's five are what is late or due today first, then the questions; setting-up cards wait
  behind the fold. (tired-person tests)
- Claude's work has one button on every screen, the pill in the header. On a wide screen it
  opens and closes the panel on the right, as the menu's "Icons only" folds, remembered on the
  device (open beside every screen but the Brief until the person chooses); narrower, it opens
  as a panel on the right, and on a phone as a sheet from the bottom. (pill tests)

## Cards and lists

- Every item is its own soft card: a 1px line, rounded corners, no shadow, 8px from the next.
  Only what floats (a sheet, a menu, a toast) has a shadow. Nothing has a line down its side.
  (design test)
- A card reads top down: its top line (a kind or a score, the title, a state pill, the bin),
  one line of facts, at most one block in a soft grey box (a question or a suggestion), then
  its actions: one filled button at most, quiet ones beside it, More for the rest. (layout 7, 8)
- A job card's line of facts says when it was posted and the pay where stated; why it scored
  what it did is the first line under More. A drafted role's card in Found opens its draft,
  where "I have applied" is; a closed one offers only setting it aside. (jobs page tests)
- A state is a small tinted pill in words a person uses, never a code word: ok green, info
  blue, warn amber, bad red, held violet, waiting grey. (status audit, colour tests)
- A To do row whose message is already drafted says "Draft ready" and its one button opens
  the draft, never drafts it again; two or more drafted are one card, "N messages ready to
  send", a row a person opening their draft and one button opening Messages. (drafted
  messages tests)
- One "?" a card at most, after the last word of its line, and no more than three on a first
  screen. (design test, budget test)

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

- A filled button is the one next step; a secondary one is a soft grey pill; a quiet one is
  underlined text. Links that act as controls have a grey underline; rose is for links inside
  a sentence. (layout 7)
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

## Words and settings

- Plain words: no git, branch, command or config, no file names, no ids.
- One date a card, said one way: a day gone by as "12 Sept", a day ahead with its weekday. A
  card about someone shows the day they wrote (or you did); its corner says only "Overdue".
  What someone asked for leads the card, and its button does it ("Make a CV for Juno").
- Where a person stands, what is owed, who the person's own rules keep back and every count
  of them are the engine's one answer (`app_model.standing`): the page renders them and never
  works them out again. A message that breaks the person's rules is never offered as ready.
- Counts agree: a tab, a summary and a badge count the same things, a checklist of people a
  thing for each person, and a button that starts several says the time for all of them.
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
