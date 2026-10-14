"""Morgan Ellis's answers to the portal form fields that gate a submission. Fictional.

The shape every profile's screening.py takes, read by
tools/screening_answers.py. Each entry is (question as portals ask it, answer,
note). Placeholders the tool fills from facts it parses out of the profile:
{sponsor_answer}, {notice}, {floor}, {low}, {high}.
"""

QUESTIONS = [
    ("Do you have the right to work in the UK?",
     "Yes",
     "Settled status. This is a different question from sponsorship below."),

    ("Will you now or in the future require visa sponsorship?",
     "{sponsor_answer}",
     "A plain answer, with no caveat."),

    ("Do you hold, or are you eligible for, security clearance (SC or DV)?",
     "No current clearance",
     "Roles that require clearance to be held already are cut by the eligibility "
     "gate before they reach a shortlist."),

    ("What is your notice period?",
     "{notice}",
     "Parsed from the profile."),

    ("What are your salary expectations?",
     "GBP {low:,} to {high:,}",
     "The target band. The walk-away floor is {floor:,}. Give a band, never a "
     "single number."),

    ("Where are you based?",
     "Manchester",
     "Hybrid in Greater Manchester and the North West; remote anywhere in the UK."),

    ("How did you hear about this role?",
     "[check the tracker row]",
     "The portal the posting came from, or the person who mentioned it."),
]

NEEDS_A_PERSON = ("What are your salary expectations?",
                  "How did you hear about this role?")
