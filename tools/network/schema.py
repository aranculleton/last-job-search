"""The contract every networking module shares.

Design note on integration. The brief asks for networking to extend the
application system rather than sit beside it, and the join already exists:
`tools/company_key.py` turns a bank's legal name, its initials and its capital
markets division into one key. Contacts carry that key, applications carry that key,
so a thread and an application at the same employer find each other without a
second identity scheme. Company-level findings live in the existing
`company_research/` cache, which already has a `network_contacts_note` field
nobody was writing to.

Two files hold networking state, both CSV like the tracker so they open in a
spreadsheet and diff in git:

  network_contacts.csv   one row per person
  network_threads.csv    one row per message sent or received

A person is not a thread. Someone can be contacted on LinkedIn, then email,
then a call; the contact row holds who they are, the thread rows hold what
happened. Deriving status from messages rather than storing it means the
status can never drift from the evidence.
"""

import os
import sys

CONTACT_COLUMNS = [
    "contact_id",        # stable slug: company_key + surname, e.g. "acme_halloway"
    "name",
    "title",
    "company",           # as written
    "company_key",       # company_key.key(company) - the join to the tracker
    "location",
    "linkedin_url",
    "email",
    "tier",              # 1 live hiring intent | 2 hiring authority | 3 senior IC | 4 adjacent
    "route",             # cold | connection | alumni_employer | alumni_school | referral | mutual | hiring_team
    "route_detail",      # "Acme alumni", "referred by Jane Smith", "named on the posting"
    "found_via",         # the source kind that surfaced them (tools/network/sources.py KINDS)
    "referred_by",       # contact_id of the referrer, for the referral graph
    "signal",            # the quoted hiring signal, for tier 1
    "signal_date",
    "first_contacted",
    "channel",           # connection | inmail | email | intro
    "status",            # see THREAD_STATUSES
    "next_action",
    "next_action_due",
    "outcome",
    "linked_application",  # cv_file of the related application row, if any
    "notes",
]

THREAD_COLUMNS = [
    "contact_id",
    "date",
    "direction",         # out | in
    "channel",
    "scenario",          # reply_engine classification, for inbound
    "summary",           # one line, what was said
    "full_text",         # the message, for reply context
    "subject",           # an InMail's or an email's subject line, as sent
]

# Ordered by how far the thread has progressed. A status later in this list
# never reverts to an earlier one without an explicit outcome.
THREAD_STATUSES = [
    "not_contacted",
    "awaiting_reply",        # we sent, they have not answered
    # Accepted the connection request and said nothing. A different state from
    # awaiting_reply, and a better one: a 1st-degree connection is a free and
    # permanent DM channel, and clicking accept is a small signal of interest
    # that not replying does not cancel. Kept apart because, as one bucket, the
    # state hid every accepted-but-silent contact inside "sent and ignored"
    # when the two need opposite follow-ups.
    "connected_no_reply",
    "replied_needs_response",  # they answered, we owe a reply
    "in_conversation",       # back and forth, nothing owed right now
    "call_booked",
    "referral_in_progress",
    "converted_to_application",
    "gone_cold",             # no reply after a nudge
    "closed",                # explicit no, or we walked away
    # Set aside before anything was sent: a queued note the person chose not to send,
    # for now. Never a dead end, so `state.py reopen` brings it back; a closed row is
    # a real one (they left, they said no, nobody can reach them). Thirty-one rows in
    # one contact book were closed for "queue dropped; never sent", and a run told
    # the person their best employers were "already covered" with nobody written to.
    "dropped",
]

OWED_BY_US = {"replied_needs_response"}
TERMINAL = {"gone_cold", "closed", "converted_to_application", "dropped"}
# Nothing has gone to them: no message, no request. Who `state.py reopen` may bring back.
NEVER_SENT = {"not_contacted", "dropped"}

# Platform limits the output has to fit inside. LinkedIn caps connection
# requests weekly and InMail credits monthly; sending more than the user can
# actually send produces a list they cannot action.
#
# Which limits apply depends on the person's LinkedIn account, and they were
# Premium's for everyone: a 300-character note, InMail credits, no monthly cap on
# personalised notes. A free account gets a shorter note (reported as 200
# characters), a handful of personalised notes a month and no InMail except to an
# Open Profile, so its drafts could not be sent. The plan is the person's
# (profile/networking.py LINKEDIN_PLAN), and with none recorded the free limits
# apply: a note short enough for free is short enough for Premium, never the
# other way round. LINKEDIN_LIMITS there overrides any number (a Business or
# Sales Navigator plan carries more InMail credits).
PLANS = {
    "free": {"connection_note_chars": 200, "personal_notes_per_month": 5,
             "inmail_credits_per_month": 0},
    "premium": {"connection_note_chars": 300, "personal_notes_per_month": None,
                "inmail_credits_per_month": 5},
}


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import person  # noqa: E402

# Written as a plain binding so tools/profile_names.py sees the names read here.
_NETWORKING = person.module("networking") if person.exists("networking.py") else None
PLAN = str(getattr(_NETWORKING, "LINKEDIN_PLAN", "") or "free").strip().lower()
if PLAN not in PLANS:
    PLAN = "free"

def plan(fresh: bool = False) -> str:
    """The person's LinkedIn plan, "free" or "premium": the one reader of LINKEDIN_PLAN.
    `fresh` reads the file as it is now (a change on the page shows in the same run);
    otherwise the plan this module read at import, which LIMITS were set from."""
    got = str(getattr(_NETWORKING, "LINKEDIN_PLAN", "") or "")
    if fresh:
        try:
            import profile_set
            v = profile_set.get("networking.py", "LINKEDIN_PLAN")
            got = "" if v in (profile_set.MISSING, None) else str(v)
        except Exception:  # noqa: BLE001  no profile, or no networking settings: free
            got = ""
    got = got.strip().lower() or "free"
    return got if got in PLANS else "free"


LIMITS = {
    # No cap on connection requests of the app's own (2026-10-22): it once held a week to 50
    # and a day to 25, a planning number a tool printed as "requests left" as if it were
    # LinkedIn's. LinkedIn publishes no number and says itself when its weekly limit is
    # reached; that is the only limit.
    **PLANS[PLAN],
    # A message to someone already connected (a first-degree connection): no subject, no
    # credit and no weekly cap, and LinkedIn's message box takes about 8,000 characters.
    # A first message there is still held to CONNECTED_CHARS by the composer.
    "message_chars": 8000,
    # A ceiling, not a target: an InMail is the first note with room for one
    # paragraph of evidence, and padding it to a word count is the failure.
    "inmail_words": (None, 200),
    # LinkedIn's subject field takes about 200 characters; a subject is a label,
    # so the composer holds it to a few words well inside that.
    "inmail_subject_chars": 200,
    "inmail_subject_words": 8,
    # A nudge is capped BELOW the note it is chasing, which is the whole point.
    # Someone who ignored a 300 character message is not going to respond to an
    # even longer one, especially a senior reader. A first message is an
    # introduction and earns its 300 characters. A nudge has already been
    # declined once, so every extra word is spent arguing with someone who has
    # not engaged. It gets less room, not more.
    # `gone_quiet` in reply.py has always said two sentences; this makes it
    # a number the composer can refuse to exceed.
    "nudge_chars": 280,
}

# What LIMITS holds before any plan or setting of the person's: the base `limits_now` starts from.
_FIXED = {k: v for k, v in LIMITS.items() if k not in PLANS["premium"]}

# The person's own limits for their plan (more InMail credits than Premium's, say). A
# connection cap written there is ignored: the app sets none, and one written to escape the
# old cap would only print a number LinkedIn never gave.
# Keys of LINKEDIN_LIMITS the app reads nothing from (`ignored_limits` names them).
IGNORED_LIMITS = ("connections_per_week", "connections_per_day")
LIMITS.update({k: v for k, v in dict(getattr(_NETWORKING, "LINKEDIN_LIMITS", {}) or {}).items()
               if k not in IGNORED_LIMITS})


def ignored_limits(limits=None) -> list:
    """The keys of the person's LINKEDIN_LIMITS (or `limits`) the app drops, sorted: written
    there, they read as a cap the app keeps and it keeps none (the audit, 2026-11-10)."""
    if limits is None:
        limits = getattr(_NETWORKING, "LINKEDIN_LIMITS", {}) or {}
    return sorted(k for k in dict(limits or {}) if k in IGNORED_LIMITS)

# Below the note it chases, whatever the plan allows the note.
LIMITS["nudge_chars"] = min(LIMITS["nudge_chars"], LIMITS["connection_note_chars"] - 20)
_READ_AT: list = [None]


def _settings_mark():
    """(path, time, size) of the person's networking settings, or None: what LIMITS was read
    from, so a change shows."""
    try:
        path = person.path("networking.py")
        st = os.stat(path)
        return (path, st.st_mtime_ns, st.st_size)
    except Exception:  # noqa: BLE001  no profile, or no networking settings
        return None


_READ_AT[0] = _settings_mark()


def limits_now() -> dict:
    """LIMITS as the person's settings say now: the plan (`plan(fresh=True)`) and their own
    LINKEDIN_LIMITS read again whenever profile/networking.py has changed since LIMITS was
    last read, and updated in place, so every module holding LIMITS sees it. A process that
    ran on kept the old plan's limits after the person changed theirs on the page (the
    audit, 2026-11-10). Returns LIMITS; compose brings its copies (KIND_LIMITS) in line from
    it at every check."""
    global FOLLOW_UP_DAYS, MAX_UNANSWERED, CONTACT_NUDGES, MAX_NUDGES, GONE_COLD_DAYS
    mark = _settings_mark()
    if mark == _READ_AT[0]:
        return LIMITS
    _READ_AT[0] = mark
    theirs: dict = {}
    try:
        import profile_set
        got = profile_set.get("networking.py", "LINKEDIN_LIMITS")
        theirs = got if isinstance(got, dict) else {}
    except Exception:  # noqa: BLE001  no settings: the plan's own
        profile_set = None
        theirs = {}

    def days(name):
        try:
            v = profile_set.get("networking.py", name) if profile_set else 0
            v = 0 if v is getattr(profile_set, "MISSING", object()) else v
            return max(int(v or 0), 0)
        except Exception:  # noqa: BLE001  unset or not a number: the app's own
            return 0
    # The person's follow-up rule too, read again with the plan: their limit of unanswered
    # messages stayed as first read after they changed it (the review, 2026-11-11).
    FOLLOW_UP_DAYS = days("FOLLOW_UP_DAYS")
    MAX_UNANSWERED = days("MAX_UNANSWERED") or 2
    CONTACT_NUDGES = max(MAX_UNANSWERED - 1, 0)
    MAX_NUDGES = CONTACT_NUDGES
    GONE_COLD_DAYS = days("GONE_COLD_DAYS") or 90
    new = {**_FIXED, **PLANS[plan(fresh=True)],
           **{k: v for k, v in theirs.items() if k not in IGNORED_LIMITS}}
    new["nudge_chars"] = min(new["nudge_chars"], new["connection_note_chars"] - 20)
    LIMITS.clear()
    LIMITS.update(new)
    return LIMITS

# Follow-up cadence, in business days. The brief is explicit that 24-48 hours
# reads as impatient and 5-7 business days is the correct window.
FOLLOWUP_BUSINESS_DAYS = 6
# The person's own rule outranks the app's (profile/networking.py, 2026-10-23):
# FOLLOW_UP_DAYS calendar days of silence before a follow-up, counted from our last
# message or from the day they accepted, and MAX_UNANSWERED messages in a row with no
# reply before the app suggests no more. Unset, the app's six business days and one
# nudge (two messages unanswered) stand. Other tools put the same two numbers in the
# person's hands: a "stay in touch" interval in days, and a cap on follow-ups.
def _days_setting(name: str) -> int:
    # A whole number from profile/networking.py, or 0 (the app's own) when it is unset or
    # not a number: a typo there never stops every networking tool.
    value = getattr(_NETWORKING, name, 0)
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


FOLLOW_UP_DAYS = _days_setting("FOLLOW_UP_DAYS")
# Unset, two messages in a row with no reply: the first, and one nudge.
MAX_UNANSWERED = _days_setting("MAX_UNANSWERED") or 2
# Follow-ups to a contact after the first message: a name of its own, apart from an
# application's (followups.APPLICATION_NUDGES). MAX_NUDGES is the name callers already read.
CONTACT_NUDGES = max(MAX_UNANSWERED - 1, 0)
MAX_NUDGES = CONTACT_NUDGES
# Days with no answer before a conversation is closed as gone cold (state.close_gone_cold).
GONE_COLD_DAYS = _days_setting("GONE_COLD_DAYS") or 90
# Days after any message of ours before the same person is offered another (surface.held):
# the person's own "nobody written to in the last N days" rule, which lived in a script of
# their own that bypassed the one check (the audit's NW-16, 2026-11-10). 0, unset: none.
QUIET_AFTER_SEND_DAYS = _days_setting("QUIET_AFTER_SEND_DAYS")


def follow_up_rule() -> str:
    """The rule in force, in words: "14 days, at most 2 with no reply"."""
    wait = (f"{FOLLOW_UP_DAYS} days" if FOLLOW_UP_DAYS
            else f"{FOLLOWUP_BUSINESS_DAYS} business days")
    return f"{wait}, at most {MAX_UNANSWERED} with no reply"
