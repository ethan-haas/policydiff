"""Regression tests for an earlier fix (defect 1, a fresh
independent reviewer. -- gate 2,
"Formatting-only diff produces an empty report ... reflow ... Any finding
here is a false positive").

The defect: the unnumbered-prose sentence atomizer
(policydiff/sentence.py's _group_prose_chunks(), consulted via
group_prose_lines()/group_prose_lines_raw() from segment.py's
flush_prose()) treated a newline immediately followed by a CAPITALIZED
word as a hard sentence boundary whenever the physical line BEFORE it had
no terminal punctuation of its own. Real policy forms are hard-wrapped at
~70-80 columns and dense with capitalized defined terms ("Insured",
"Company", "Declarations", "Commercial Property Coverage Part"), so a
plain reflow of one ordinary sentence --

    OLD: "This endorsement modifies insurance provided under the Commercial
          Property Coverage Part."
    NEW: "This endorsement modifies insurance provided under the\\n
          Commercial Property Coverage Part."

(two files differ by exactly one character: a space became a newline) --
manufactured a spurious [MODIFIED]+[ADDED] pair out of pure formatting.

Root fix (policydiff/sentence.py):
  * A HEADING-SHAPED line (ALL-CAPS or short Title-Case-with-separator, no
    terminal punctuation -- the exact surface-form test segment.py already
    used for bare section headings, now shared via
    sentence.is_heading_shaped_line() so the two call sites can never
    drift) is always its own atom: it never absorbs the next line, and it
    is never absorbed by a normal prose line before it.
  * An ordinary (non-heading-shaped) prose line with no terminal
    punctuation of its own is a genuine hard-wrap continuation of the
    following line UNLESS that line itself ends in a schedule-row-style
    amount ("Each Occurrence Limit $1,000,000" -- an earlier revision's fixture
    class, a complete label+amount assertion in its own right even
    without punctuation) -- see sentence._ends_with_amount(). Only a
    line that does NOT look like a complete row, followed by a line that
    is NOT itself a distinct heading-shaped item, joins regardless of
    whether that next line starts uppercase or lowercase.

These fixtures are original (not copies of any reviewer probe/fixture file
under the audit fixtures,
task's FORBIDDEN clause) and exercise the general class, not just the one
reproduced example.
"""
import textwrap

from policydiff.report import diff_documents, human_report
from policydiff.sentence import group_prose_lines


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) minimal wrap-before-capital -- the exact live repro -- must be
# EMPTY, both at the sentence-grouping layer and through the full CLI
# pipeline.
# ---------------------------------------------------------------------


def test_minimal_wrap_before_capital_chunk_is_joined():
    chunks = group_prose_lines(
        ["This endorsement modifies insurance provided under the", "Commercial Property Coverage Part."]
    )
    assert chunks == [
        "This endorsement modifies insurance provided under the Commercial Property Coverage Part."
    ], chunks


def test_minimal_wrap_before_capital_is_empty():
    old = "This endorsement modifies insurance provided under the Commercial Property Coverage Part.\n"
    new = "This endorsement modifies insurance provided under the\nCommercial Property Coverage Part.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    # And the reverse direction.
    result_rev = diff_documents(new, old, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


# ---------------------------------------------------------------------
# (b) a full insuring-agreement sentence hard-wrapped at ~70 columns vs
# the same sentence on one physical line -- must be EMPTY.
# ---------------------------------------------------------------------

_INSURING_AGREEMENT_SENTENCE = (
    "This Commercial Property Coverage Part provides coverage for direct "
    "physical loss of or damage to Covered Property from any Covered "
    "Cause of Loss, subject to the exclusions, limitations, and "
    "conditions set forth in this Coverage Part and elsewhere in this "
    "policy, including the Declarations and any endorsements attached "
    "to and made part of this policy."
)


def test_70_column_hard_wrapped_insuring_agreement_is_empty():
    one_line = _INSURING_AGREEMENT_SENTENCE + "\n"
    wrapped = textwrap.fill(_INSURING_AGREEMENT_SENTENCE, width=70) + "\n"
    # Sanity: the wrap actually produced multiple physical lines, so this
    # is a real reflow test, not a no-op.
    assert wrapped.count("\n") >= 4

    result = diff_documents(one_line, wrapped, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    result_rev = diff_documents(wrapped, one_line, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


# ---------------------------------------------------------------------
# (c) a real change inside a hard-wrapped prose sentence -- exactly one
# finding, correct direction, not buried in phantom wrap findings.
# ---------------------------------------------------------------------


def test_real_change_inside_wrapped_sentence_is_exactly_one_finding():
    old = "This endorsement modifies insurance provided under the\nCommercial Property Coverage Part.\n"
    new = "This endorsement modifies insurance provided under the\nCommercial Auto Coverage Part.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert "Commercial Property Coverage Part" in f.old.text
    assert "Commercial Auto Coverage Part" in f.new.text


def test_dollar_amount_change_inside_wrapped_sentence_is_exactly_one_finding():
    old = "The Company will pay up to $1,000,000 for direct physical loss\nunder this Coverage Part.\n"
    new = "The Company will pay up to $500,000 for direct physical loss\nunder this Coverage Part.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert "1,000,000" in non_suppressed[0].detail and "500,000" in non_suppressed[0].detail


# ---------------------------------------------------------------------
# (d) GUARD: two distinct all-caps items on consecutive lines, one
# removed -- exactly one REMOVED, never zero, never a merged modified.
# ---------------------------------------------------------------------


def test_guard_two_allcaps_items_remove_one_is_exactly_one_removed():
    old = "FLOOD EXCLUDED\nWAR EXCLUDED\n"
    new = "FLOOD EXCLUDED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    removed = [f for f in result.findings if f.kind == "removed"]
    assert len(removed) == 1, result.findings
    assert removed[0].old.text == "WAR EXCLUDED"
    kept = [f for f in result.findings if f.kind == "unchanged"]
    assert len(kept) == 1
    assert kept[0].old.text == "FLOOD EXCLUDED"


def test_guard_two_allcaps_items_stay_separate_at_grouping_layer():
    chunks = group_prose_lines(["FLOOD EXCLUDED", "WAR EXCLUDED"])
    assert chunks == ["FLOOD EXCLUDED", "WAR EXCLUDED"], chunks


def test_guard_flood_is_covered_war_is_covered_only_one_change():
    old = "FLOOD IS COVERED\nWAR IS COVERED\n"
    new = "FLOOD IS NOT COVERED\nWAR IS COVERED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert "FLOOD" in non_suppressed[0].old.text
    kept = [f for f in result.findings if f.kind == "unchanged"]
    assert len(kept) == 1
    assert kept[0].old.text == "WAR IS COVERED"


# ---------------------------------------------------------------------
# (e) GUARD: wrapping before a LOWERCASE continuation word was already
# correct before this fix -- must stay EMPTY (non-regression of round
# 6/7/8's continuation-join logic).
# ---------------------------------------------------------------------


def test_guard_wrap_before_lowercase_still_empty():
    old = "The aggregate limit of insurance is $1,000,000 under this policy.\n"
    new = "The aggregate limit of insurance is $1,000,000\nunder this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)

    result_rev = diff_documents(new, old, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


# ---------------------------------------------------------------------
# (f) GUARD: an earlier revision's schedule-row class -- consecutive Title-Case
# "Label $Amount" rows with NO terminal punctuation anywhere must stay
# separate atoms, never fused just because the fix now joins ordinary
# unpunctuated prose forward. This is the exact non-regression the
# broadened join rule must respect (see sentence._ends_with_amount).
# ---------------------------------------------------------------------


def test_guard_schedule_rows_stay_separate_atoms():
    chunks = group_prose_lines(
        ["Each Occurrence Limit $1,000,000", "General Aggregate Limit $2,000,000"]
    )
    assert chunks == [
        "Each Occurrence Limit $1,000,000",
        "General Aggregate Limit $2,000,000",
    ], chunks


def test_guard_schedule_rows_amount_collision_still_aligns_by_label():
    old = "Each Occurrence Limit $1,000,000\nGeneral Aggregate Limit $2,000,000\n"
    new = "Each Occurrence Limit $2,000,000\nGeneral Aggregate Limit $1,500,000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in non_suppressed]
