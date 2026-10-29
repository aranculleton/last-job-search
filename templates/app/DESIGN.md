# The page's design language

For whoever changes the page (`templates/app/`): a chat or a person. Each rule says which
test holds it, so a change that breaks one fails before it ships. The person reading the
page is tired, often on a phone, and not technical: every screen answers "what do I do
next?" in its first lines, and nothing asks for a decision a default could make.

## Places

- Seven places: **Brief** (the home screen), **To do**, **Jobs** (Found, Drafts, Applied),
  **Contacts** (People, Messages), **Chat**, then **Interviews** and **Settings**. Five sit in
  the phone's tab bar; To do alone carries a coloured badge. (layout 6)
- Each screen: its title, one plain summary line, at most three blocks before the first item.
  (layout 1 to 3)
- A long list opens on its first few and folds the rest one tap below ("Show 6 more"): To do
  five today, Drafts and Messages five, Contacts who needs you. Never a filter left on.
  (layout 2, crowd tests)

## Cards and lists

- Every item is its own soft card: a 1px line, rounded corners, no shadow, 8px from the next.
  Only what floats (a sheet, a menu, a toast) has a shadow. Nothing has a line down its side.
  (design test)
- A card reads top down: its top line (a kind or a score, the title, a state pill, the bin),
  one line of facts, at most one block in a soft grey box (a question or a suggestion), then
  its actions: one filled button at most, quiet ones beside it, More for the rest. (layout 7, 8)
- A state is a small tinted pill in words a person uses, never a code word: ok green, info
  blue, warn amber, bad red, held violet, waiting grey. (status audit, colour tests)
- One "?" a card at most, after the last word of its line, and no more than three on a first
  screen. (design test, budget test)

## The bin

- One icon puts anything away: the bin, top right of every live card. Never an x.
- One possible answer: done at once, with Undo. Several: a short sheet, each choice doing
  exactly what it says, and Undo putting every part back. (bin tests, design test)
- The choices: a job (not this role, the pay, the place, my field, no more from the employer,
  already applied, closed); a draft (won't apply, already applied, closed); a message (set it
  aside, or the person's choices); a person (don't contact, not that employer any more, in
  touch another way); an interview or an application (they said no, I withdrew, stopped
  waiting); a reminder in To do (hide it for a week).

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
- Work says where it stands in words: running, Next, In line, in the same chat. The top pill
  names the one thing running.

## Words and settings

- Plain words: no git, branch, command or config, no file names, no ids.
- Nothing asks what a default answers. A choice becomes a setting only where people really
  differ, and work goes where it can run without anyone choosing (one chat answers the page;
  only the brief needs the cloud). (place and routing tests)
- Each setting has one home in Settings. Where a setting also has a control elsewhere (the
  Brief's bell, a break from To do), both open the same sheet and can never disagree.
- Every control does something visible (the sweep test taps all of them) and every action
  reaches the engine and is applied (the round-trip tests).

## Before a change ships

Run the browser tests, then look at the screen you changed on a phone and on a laptop, in
light and dark. A rule here that a change needs to break is changed here first, with its test.
