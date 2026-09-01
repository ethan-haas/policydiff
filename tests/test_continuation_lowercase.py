"""Regression tests for an earlier fix: an earlier revision's continuation-join
restriction (physical-line continuation only triggers on a LOWERCASE-
initial next line -- see policydiff/sentence.py::_is_continuation_start)
fixed the an earlier audit "$"-standalone REORDER defect, but introduced a new
noise false positive of its own: a sentence that happens to wrap immediately
before its own trailing "$"/digit amount now splits into two atoms on
one side of a diff while an equivalent rewrap of the SAME sentence stays
one atom on the other side -- a pure line-break move (no content change
at all) manufactures a phantom [NARROWED]/[REMOVED] finding (gate 2,
"noise-only edits must never surface a finding").

Reproduced live:
    OLD: "The aggregate limit of insurance is\\n$1,000,000 under this policy."
    NEW: "The aggregate limit of insurance\\nis $1,000,000 under this policy."
(identical words, only the line-break position moved) used to produce
`[NARROWED] sublimit of $1,000,000 added` + a spurious `[REMOVED]`. Must
be EMPTY.

Root fix (policydiff/sentence.py, _is_continuation_start /
_CONTINUATION_START_RE): the join is gated on TWO conditions together,
not next-line-start alone --

    Join physical line L+1 onto L as a continuation IFF:
        (L does NOT end with terminal '.'/'?'/'!')
        AND
        (L+1 starts with a LOWERCASE letter, OR with '$'/a digit)

_is_continuation_start() (the L+1 check) is only ever consulted by
group_prose_lines() when _ends_sentence(L) is already False -- i.e. the
prev-line-incompleteness gate is structural, not an extra flag to
remember to check. That means widening the trigger back to include
"$"/digit is safe: the only place a "$"/digit-initial line is ever
ambiguous (a genuine standalone "$"-led sentence, e.g. "$1,000,000 is the
most we will pay under this policy.") always follows a line that DOES
end with terminal punctuation, so _ends_sentence(L) is True there and
_is_continuation_start() never even runs. An UPPERCASE-initial L+1 still
never joins (kept out of _CONTINUATION_START_RE entirely), which is what
keeps two distinct all-caps items ("FLOOD EXCLUDED" / "WAR EXCLUDED")
correctly separate.

These fixtures are original (not copies of any reviewer's audit-r*
fixture/probe files under the audit fixtures) and
exercise the general class, not just the one reproduced example.
"""
from policydiff.report import diff_documents, human_report, to_json


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# Case 1 -- the reproduced bug: a sentence that wraps immediately before
# its own trailing "$" amount must be a pure no-op against an equivalent
# rewrap of the SAME sentence at a different word.
# ---------------------------------------------------------------------


def test_rewrap_immediately_before_dollar_amount_is_empty():
    old = "The aggregate limit of insurance is\n$1,000,000 under this policy.\n"
    new = "The aggregate limit of insurance\nis $1,000,000 under this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
    assert [f.kind for f in result.findings] == ["unchanged"]
    assert (
        result.findings[0].old.text
        == "The aggregate limit of insurance is $1,000,000 under this policy."
    )
    assert result.findings[0].new.text == result.findings[0].old.text


def test_rewrap_immediately_before_digit_amount_is_empty():
    # Same shape, wrap falls right before a bare digit (no "$"), not just
    # a currency amount -- both trigger characters must be covered.
    old = "The waiting period is\n30 days under this policy.\n"
    new = "The waiting period\nis 30 days under this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


def test_reflow_direction_reversed_is_also_empty():
    # Symmetric check: old wraps before "is", new wraps before "$" --
    # the opposite direction of the reproduced bug -- must ALSO be empty.
    old = "The aggregate limit of insurance\nis $1,000,000 under this policy.\n"
    new = "The aggregate limit of insurance is\n$1,000,000 under this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# Case 2 -- the an earlier audit reorder fix must still hold: three complete
# sentences (one $-initial), reordered, all present verbatim both sides.
# ---------------------------------------------------------------------


def test_dollar_standalone_reorder_still_empty_no_phantom():
    old = (
        "$1,000,000 is the most we will pay under this policy.\n"
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
    )
    new = (
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
        "$1,000,000 is the most we will pay under this policy.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
    assert [f.kind for f in result.findings] == ["unchanged", "unchanged", "unchanged"]
    items = to_json(result)["findings"]
    for item in items:
        assert item["old_quote"] == item["new_quote"]
        assert item["new_quote"] is not None


def test_digit_standalone_reorder_still_empty():
    old = (
        "30 days is the waiting period under this policy.\n"
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
    )
    new = (
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
        "30 days is the waiting period under this policy.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# Case 3 -- two distinct all-caps items must never be fused just because
# neither ends with terminal punctuation; removing one must surface
# exactly ONE removed finding, not zero, not both.
# ---------------------------------------------------------------------


def test_two_allcaps_items_remove_one_is_exactly_one_removed():
    old = "FLOOD EXCLUDED\nWAR EXCLUDED\n"
    new = "FLOOD EXCLUDED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    removed = [f for f in result.findings if f.kind == "removed"]
    assert len(removed) == 1, result.findings
    assert removed[0].old.text == "WAR EXCLUDED"
    kept = [f for f in result.findings if f.kind == "unchanged"]
    assert len(kept) == 1
    assert kept[0].old.text == "FLOOD EXCLUDED"


def test_two_allcaps_items_unchanged_is_fully_empty():
    old = "FLOOD EXCLUDED\nWAR EXCLUDED\n"
    new = "FLOOD EXCLUDED\nWAR EXCLUDED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
    assert [f.kind for f in result.findings] == ["unchanged", "unchanged"]


# ---------------------------------------------------------------------
# Case 4 -- recall: a "$"-initial standalone sentence, preceded by a
# terminally-punctuated sentence, must still be caught cleanly when
# genuinely removed -- exactly ONE removed, never silently absorbed.
# ---------------------------------------------------------------------


def test_dollar_initial_standalone_removed_is_exactly_one_removed():
    old = "$1,000,000 is the most we will pay under this policy.\nFire losses are covered.\n"
    new = "Fire losses are covered.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    removed = [f for f in result.findings if f.kind == "removed"]
    assert len(removed) == 1, result.findings
    assert removed[0].old.text == "$1,000,000 is the most we will pay under this policy."
    assert _non_suppressed(result) == removed


# ---------------------------------------------------------------------
# Case 5 -- genuine lowercase-continuation wrap: a real edit on the
# wrapped 2nd line must still be exactly one [narrowed] finding, and a
# rewrap of that same sentence (no content change) must be empty.
# ---------------------------------------------------------------------


def test_genuine_wrap_lowercase_continuation_edit_is_one_narrowed():
    old = "The aggregate limit of insurance\nis $1,000,000.\n"
    new = "The aggregate limit of insurance\nis $500,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert [f.kind for f in result.findings] == ["narrowed"]
    assert result.findings[0].old.text == "The aggregate limit of insurance is $1,000,000."
    assert result.findings[0].new.text == "The aggregate limit of insurance is $500,000."


def test_rewrap_of_lowercase_continuation_sentence_is_empty():
    old = "The aggregate limit of insurance\nis $1,000,000.\n"
    new = "The aggregate limit of\ninsurance is $1,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# Case 6 -- combined regression: mix a rewrap-before-$, a genuine
# all-caps removal, and a reorder in one document, still resolves
# cleanly with no cross-contamination between the atoms.
# ---------------------------------------------------------------------


def test_combined_rewrap_and_allcaps_removal_and_reorder():
    old = (
        "$1,000,000 is the most we will pay under this policy.\n"
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
        "The aggregate sublimit for water damage is\n$250,000 under this policy.\n"
        "FLOOD EXCLUDED\n"
        "WAR EXCLUDED\n"
    )
    new = (
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
        "$1,000,000 is the most we will pay under this policy.\n"
        "The aggregate sublimit for water damage\nis $250,000 under this policy.\n"
        "FLOOD EXCLUDED\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    kinds = sorted(f.kind for f in result.findings)
    assert kinds.count("removed") == 1
    assert kinds.count("unchanged") == 5
    assert "narrowed" not in kinds and "added" not in kinds and "modified" not in kinds
    removed = [f for f in result.findings if f.kind == "removed"][0]
    assert removed.old.text == "WAR EXCLUDED"
