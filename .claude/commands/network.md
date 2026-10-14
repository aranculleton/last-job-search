# /network - Discovery run

Find the right people at target companies and produce ready-to-send drafts.

Usage: `/network Acme, Initech, Globex` or `/network` to use the top
untouched employers from the latest round's shortlist.

## Run it

1. **Load state.** `state.load_contacts()`, `state.load_threads()`, the tracker,
   and `company_research/`. Anyone already contacted is out. Any company already
   recorded as having no relevant presence is out.

2. **Check the budget before searching.** `state.platform_budget()` returns the
   connection requests and InMail credits left. There is no point producing
   fifteen drafts against five remaining slots. Size the run to the budget and
   say what the budget is.

3. **Per company, cheapest route first** (see `01-discovery-playbook.md`):
   alumni, then hiring team from a live posting, then school, then cold. Build
   queries with `discovery.queries_for()`, which caps at three and enforces the
   profile-path pattern. Run them with WebSearch, passing
   `allowed_domains=discovery.SEARCH_DOMAINS`, then drop every result that
   fails `discovery.is_person_url()` (about two in ten are job-board pages).

4. **Triage with `discovery.triage()`.** It applies the disqualifiers, the
   staleness check and the tier classification. When everything drops, the
   verdict is `no_relevant_presence`: write that to `company_research/<key>.json`
   so the company is not re-targeted.

5. **Compose in one batch with `compose.first_note()`.** One model call
   producing every draft, not one per person, then `compose.validate(kind=
   "connection")` on each. A draft that fails is rewritten, never shown with a
   warning attached. The rules are in "Composition" in `networking/SKILL.md`;
   the short version:

   - The note asks for a conversation, never the job. No role the candidate wants, no
     "are you hiring", no "is it on your team", no work authorization (unless
     the person is a recruiter). `AsksForTheJob` refuses all of them.
   - Per person, write two things: the **common ground** (shared employer,
     school or move first; otherwise the one specific thing about their work)
     and a **question** about them, answerable in a line. The opener, the
     one-line "about me" and the 15-minute ask default to the candidate's own
     words in `profile/networking.py`.
   - The referral ask is a different message, `compose.referral_ask()`, sent
     only after they have engaged.

6. **Write state.** New contacts at `not_contacted`, with tier, route,
   route_detail, the quoted signal for tier 1, and `linked_application` where
   `state.link_to_applications()` finds one.

## Present

Ranked by tier, then by route strength (referral > alumni > cold). For each:
name, title, company, location, tier with the **quoted signal** if tier 1, the
route, the recommended channel, and the draft.

Then, separately and honestly: **the dead ends**, with the reason for each. A
company with no relevant presence in the target city is a real finding and saves the next
run two searches.

Say which targets justify a scarce InMail and which should take a free
connection request. If the connection cap is hit, say so and note that following
costs nothing and lets the request go out warm when the cap resets.

## Do not

- Exceed three searches for one company
- Fetch a LinkedIn profile URL, a careers page or a blog index
- Surface anyone already in `network_contacts.csv`
- Pad the list. Three good names beats twenty mediocre ones, and every message
  spends a slot and a piece of the user's reputation.
