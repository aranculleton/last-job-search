"""Morgan Ellis's grounding rules. Fictional.

The shape every profile's claims.py takes, read by tools/check_claims.py: each
rule is (severity, name, pattern, why), searched case-insensitively. A string
"@name" places one of the app's own rules; app rules not placed run after.
"""

CHECKS = [
    (
        "ERROR", "forecast-error-belongs-to-brindle",
        r"(Oakmere|Saltmarsh)[^.\n]{0,120}\b(22|14)\\?%",
        "The 22% to 14% forecast-error figure is Brindle & Hart work only.",
    ),
    (
        "WARN", "write-offs-scope",
        r"write-offs?[^.\n]{0,40}\b18\\?%(?![^.\n]{0,60}chilled)",
        "The 18% reduction was on chilled lines. Without the qualifier it reads as "
        "the whole range.",
    ),
]

FIGURE_DRIFT = [
    (r"\b(3|4|5),\d00\s*SKUs", "the SKU count is 2,400"),
]
