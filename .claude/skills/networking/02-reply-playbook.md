# Reply playbook

`reply.classify()` picks the scenario and `reply.guidance()` returns the move.
This file is the reasoning behind each one.

## The scenarios

| Their message | The correct move | Length |
|---|---|---|
| **Asks for the resume, or gives an email** | Send it promptly, attached, with a short context paragraph. Reply once on the original channel to say it is sent. Do not wait to be asked twice. | Email: substantial. Thread reply: one line. |
| **Low effort: "sure", "absolutely", a thumbs up** | Not enthusiasm, not rejection. Move it forward with one concrete, low-friction step: offer the resume, or propose two specific times. | One or two sentences. Never a paragraph in reply to one word. |
| **Detailed and generous** | Engage with the substance. Pick the two or three most useful specifics. Ask one genuine follow-up if there is a real question. | Match theirs, roughly. |
| **Rejection, "not my market", "not hiring"** | Gracious, short close. One low-cost ask ("anyone in that space worth speaking to?") only if they engaged genuinely. | Two or three sentences. |
| **Referral offered** | Accept immediately and make it easy. Offer the resume unprompted. One clarifying question if useful. | Short and warm. |
| **Calendar link** | Book a slot, then confirm in the thread so they know it is done. | One line. |
| **Genuine mismatch** | Tell the *user* plainly, do not draft an optimistic message. A polite two-line exit preserves the relationship at zero cost. | Two lines. |
| **Discouraging market commentary** | Do not let it reshape strategy. Note whether it is generally true but not specific to this user's position, and say so. | Brief, not defensive. |
| **Quiet** | One nudge, after 5 to 7 business days, unless the person's FOLLOW_UP_DAYS and MAX_UNANSWERED (profile/networking.py) say otherwise. Never 24 to 48 hours. A genuine new development is a legitimate earlier reason and reads as initiative. | Two sentences. |
| **An automatic reply: an out-of-office, "no longer with the company"** | Not a reply, so draft nothing. Log it inbound with scenario `auto_reply`. The thread still waits on them, the employer is not a warm route, no reply is owed, and the one nudge waits until two working days after the return date it gives. "No longer with": close the contact and find who holds the role now. | None. |
| **User at fault** | Apologise once, plainly. Own it, propose a concrete alternative. Do not grovel, do not over-explain, do not stack apologies. If it has been weeks, say so rather than pretending. | Three or four sentences. |

## Precedence

An email address inside a long, substantive reply is **still `send_resume`**. The
action is the point; the substance gets engaged with in the email itself. The
classifier documents this ordering, and it is the one people get wrong by hand.

## The failure mode to watch

**Restating their points back at them.** It is the single most common tell of a
machine-written reply. `tone.restate_ratio()` measures content-word overlap and
flags it. Show you understood the shape of what they said; never summarise it
back.

## When to stop

After two explicit nos, stop. `reply.should_continue()` counts them. A third ask
after two declines costs the relationship and gains nothing.

## Time zones

Verify, always. Two zones on different daylight-saving calendars can be an hour
closer or further apart for a few weeks a year, and both sides get it wrong. Write the
zone the way `TIMEZONE_ABBR` or `TIMEZONE` in `profile/networking.py` gives it (an
abbreviation, or a name with the city in brackets). Never invent an abbreviation. On a calendar invite: set the timezone field explicitly,
give it a real title, put a short note in the description, attach the video link,
and check the date is the intended one and not today's.
