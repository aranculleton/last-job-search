"""Morgan Ellis's roles, education and certifications. Fictional.

The shape every profile's roles.py takes: ROLES most recent first, which is the
CV's order. See profile/roles.py in a real profile for what each key does;
tools/allocate.py, render_application.py and verify_batch.sh read them.
"""

ROLES = [
    dict(employer="Brindle & Hart Logistics", title="Senior Operations Analyst",
         dates="Mar 2023 - Present", loc="Manchester, UK", short="BH",
         tenure_months=31, floor=2, cap=4),
    # known_as: the name people use for the employer, when it is not the one
    # above. A letter says "at Oakmere", and the letter audit and the outreach
    # note accept it as naming this employer. A string or a list.
    dict(employer="Oakmere Foods", title="Supply Chain Data Analyst",
         dates="Sep 2020 - Feb 2023", loc="Leeds, UK", short="OF",
         tenure_months=29, floor=2, cap=4, verify_min=2, known_as="Oakmere"),
    dict(employer="Saltmarsh Analytics", title="Graduate Analyst",
         dates="Sep 2019 - Aug 2020", loc="Manchester, UK", short="SA", ns=4,
         tenure_months=12, floor=1, cap=2,
         # A one-year graduate scheme: one line unless the posting is about
         # consulting or client work.
         cap_unless=dict(cap=1, at_least=0.5, themes=("consulting", "delivery")),
         always_show="SALT_FORECAST", skills_context=False),
]

EDUCATION = r"\textbf{BSc Mathematics}, University of Leeds, UK (2016-2019)."
EDUCATION_DEFAULT = "EDU_STD"
EDUCATION_DETAILS = {
    "EDU_STD": "Statistics, operational research and numerical methods.",
    "EDU_OR": "Operational research and optimisation; final-year project on warehouse slotting.",
}

CERTIFICATIONS = r"Microsoft Certified: Power BI Data Analyst Associate (2024)"
