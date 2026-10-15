# /network - Discovery run

Find the right people at target companies and produce ready-to-send drafts.

Usage: `/network Acme, Initech, Globex` or `/network` to use the top
untouched employers from the latest round's shortlist.

## Run it

1. **Load state.** `state.load_contacts()`, `state.load_threads()`, the tracker,
   and `company_research/`. Anyone already contacted is out:
   `state.already_contacted(contacts, name, company, linkedin_url=...)` checks the
   profile URL first, which finds the same person under a nickname or a new employer.
   A company whose `company_research/<key>.json` `network_presence` record
   `discovery.presence_blocks(record, today)` is out until its review date.
   **Drafts queued by an earlier run come first**: contacts at `not_contacted` with a
   `documents/network/<contact_id>/draft.md`. Show them before any new search: send
   them or drop them.
   **Their own connections, if exported.** `state.first_degree()` reads
   `documents/linkedin/Connections.csv` (LinkedIn's data export). For each company,
   `state.connections_at(conns, company)` lists the people they already know there:
   the first to message, as a message, at no cost to the budget, before any search.

2. **Check the budget before searching.** `state.platform_budget(contacts, threads,
   today)` returns the connection requests and InMail credits left on the person's
   LinkedIn plan (`plan`), the personalised notes left this month on a free account,
   and the drafts already queued and unsent (`queued_unsent`), which spend the same
   budget the moment they go. There is no point producing fifteen drafts against five
   remaining slots. Size the run to the budget, net of the queue, and say what it is.
   `note` and `inmail_note` say what to do when a limit is reached: a request with no
   note and the draft sent as a message after they accept, and no InMail on a free
   account except to an Open Profile.

3. **Cheapest route first** (see `01-discovery-playbook.md`). The **alumni**
   searches name the shared history (a past employer, a school) and never the
   target, so run them **once per /network**, not once per company: triage them with
   no `target_company`, then `discovery.alumni_at(kept, targets)` sorts each hit to
   the target they work at. Then, per company: the hiring team from a live posting,
   then cold. Build queries with `discovery.queries_for()`, which uses the employer's
   everyday name (`search_name()`: no "Limited", no "(UK)") and caps the queries. Pass
   `titles=` from the posting's own role family when it differs from the person's
   usual titles, and `location=` the posting's city when it is not the home city (and
   the same city to `triage`). Run them with WebSearch, passing
   `allowed_domains=discovery.SEARCH_DOMAINS`, then put every result through
   `discovery.resolve_result(url, company)`: it drops listings, turns a post permalink
   into the author's profile plus the post's exact date (carry it as `signal_date`;
   a tier-1 signal needs one), and drops a company page's own posts. At most three
   searches for one company, the alumni pass apart.

4. **Triage with `discovery.triage()`.** It applies the disqualifiers, the
   staleness check and the tier classification. A result with no location is kept
   and marked `location_unverified`, never read as somewhere else; a hiring line with
   no date is kept as `undated_signal` but does not earn tier 1. Three verdicts:
   `has_presence`; `no_results` (nothing came back, which proves nothing: try the
   second query or a roster, record nothing); and `no_relevant_presence` (people came
   back and none fits). Only the last is recorded: merge
   `{"network_presence": discovery.presence_record(verdict, today)}` into
   `company_research/<key>.json`, which holds it for 90 days. Never into
   `job_scraper/do_not_target.json`, which also stops the employer's postings.
   If their connections were loaded, `discovery.mark_first_degree(kept, conns)` marks
   the people they already know: a message, not a connection request.

5. **Read what they have taught it**: `python3 tools/learned.py brief messages` and
   `brief people`. Every rule there outranks the defaults below.
   **Read what has worked**: `python3 tools/what_works.py brief messages --channel <connection|inmail|email> --route <the route>`.
   The messages that drew replies are the shape to match (length, opening move, the
   question asked), never the words or another person's facts, and a difference it calls
   clear (a route, a length, asking a question) is followed unless a learned rule says otherwise.
   **Compose in one batch with `compose.first_note()`.** One model call
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
   - The note fits the person's plan: `schema.LIMITS["connection_note_chars"]`, 200
     characters on a free account and 300 on Premium. `TooLong` means cut and
     recompose; a shorter `about_me` is usually the cut.
   - An InMail, where the plan has credits and the target is worth one, is
     `compose.inmail()`: a **subject** of a few words naming the common ground or the
     question (never "Quick question" or a job), the same moves as the note, and one
     paragraph of evidence. Validate with `kind="inmail"`.
   - The referral ask is a different message, `compose.referral_ask()`, sent
     only after they have engaged.

6. **Write state.** New contacts at `not_contacted`, with tier, route,
   route_detail, the quoted signal for tier 1, `linkedin_url`, the channel, and
   `linked_application` where `state.link_to_applications()` finds one. Each id from
   `state.unique_contact_id(name, company, contacts, linkedin_url=...)`. **Write each
   draft to `documents/network/<contact_id>/draft.md`** and commit it with the
   contacts: a draft that lives only in the chat is gone when the session ends, and the
   next run would skip the contact as already queued.

## Present

**People and their messages in one reply.** Finding someone and drafting the note
to them are one step: never list the people and wait to be asked for the drafts.
Ranked by tier, then by route strength (referral > alumni > cold). For each, as one
block: name, title, company, location, profile link, tier with the **quoted
signal** if tier 1, the route, the recommended channel, and **the message itself,
ready to paste**, with its character count against the plan's limit (and the
subject line for an InMail).

Then, separately and honestly: **the dead ends**, with the reason for each. A
company with no relevant presence in the target city is a real finding and saves the next
run two searches.

Say which targets justify a scarce InMail and which should take a free
connection request; on a free account there is no InMail, so say so once rather
than recommending one. If the connection cap is hit, say so and note that following
costs nothing and lets the request go out warm when the cap resets.

## Do not

- Stop after finding people to ask whether to draft their messages
- Exceed three searches for one company
- Fetch a LinkedIn profile URL, a careers page or a blog index
- Surface anyone already in `network_contacts.csv`
- Pad the list. Three good names beats twenty mediocre ones, and every message
  spends a slot and a piece of the user's reputation.
