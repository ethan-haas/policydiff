"""Explicit manifest of every change deliberately planted between
policy_old.txt and policy_new_planted.txt.

Each entry is (label, expected_kind, needle) where *needle* is a
substring expected to appear somewhere in that finding's detail/old_quote
/new_quote -- used by tests/test_planted.py to locate the one finding
that corresponds to each planted edit, independent of clause numbering
(which shifts because of the insertions/removals).

13 real coverage changes + 1 moved-but-unchanged clause = 14 entries.

The title/declarations line ("...FOR DEMONSTRATION ONLY) -- 2025
REVISION") is a genuine unnumbered-preamble edit: before the segmenter
fix it was invisible (preamble text was silently discarded), so it was
never part of this manifest. With unnumbered blocks now segmented into
their own "paragraph" clauses, this edit is correctly surfaced too --
with no recognized narrow/broaden signal, so it resolves to "modified"
(direction unclear), never a guessed direction.
"""

PLANTED = [
    ("Title/declarations line gains a revision tag (unnumbered preamble block)", "modified", "2025 revision"),
    ("Coverage B (Medical Payments) removed entirely", "removed", "Medical Payments"),
    ("Contractual Liability exclusion gains an insured-contract carve-back", "broadened", "insured contract"),
    ("Pollution exclusion gains a fungi/bacteria carve-in (new exclusionary scope)", "narrowed", "fungi or bacteria"),
    ("Cyber Incident exclusion added entirely", "added", "cyber incident"),
    ("Bail Bonds supplementary payment removed entirely", "removed", "Bail Bonds"),
    ("Each Occurrence Limit raised $1,000,000 -> $2,000,000", "broadened", "$1,000,000 to $2,000,000"),
    ("General Aggregate Limit lowered $2,000,000 -> $1,500,000", "narrowed", "$2,000,000 to $1,500,000"),
    ("Fire Legal Liability Limit lowered $300,000 -> $100,000", "narrowed", "$300,000 to $100,000"),
    ("Property Damage Deductible raised $1,000 -> $2,500", "narrowed", "$1,000 to $2,500"),
    ("\"Property damage\" definition broadened (loss of use added)", "broadened", "not physically injured"),
    ("\"Insured\" definition narrowed (volunteer worker removed)", "narrowed", "volunteer worker"),
    ("Duties in the Event of Occurrence condition added entirely", "added", "Duties in the Event of Occurrence"),
]

# The clause that MOVED (renumbered + relocated ahead of "Bodily injury" and
# "Property damage" in the Definitions section) but has byte-identical text
# on both sides -- must be reported as unchanged, never as a change.
MOVED_UNCHANGED_NEEDLE = "Occurrence\" means an accident"
