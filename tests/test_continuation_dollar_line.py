"""Regression tests for an earlier audit's two defect families (fresh independent
independent reviewer, 2 defect classes.

Defect 1 (SEVERE -- gate-4 hard fail + gate-2): an earlier revision's continuation-join
(sentence.py) treated a physical line beginning with "$" or a digit as a
mid-sentence continuation of whatever preceded it. A policy line routinely
OPENS a complete, standalone sentence with a dollar amount ("$1,000,000 is
the most we will pay under this policy."), and an earlier revision's regex could not
tell that shape apart from a genuine wrap ("...is\\n$1,000,000."). Two
distinct bugs conspired here:

  * sentence.py's sentence-BOUNDARY regex (_BOUNDARY_RE) never treated
    "$" as a character that can start a new sentence, so "...covered.
    $1,000,000 is the most..." (both halves already terminally
    punctuated, on separate physical lines that got joined into one
    chunk) never split at all -- the two sentences stayed fused into one
    atom forever.
  * sentence.py's continuation-trigger (_is_continuation_start) treated
    a $/digit-initial NEXT line as proof the current, unpunctuated line
    continues into it -- forcing group_prose_lines to keep buffering
    instead of hard-flushing a genuine two-atom boundary.

On a PURE REORDER of such sentences, the corrupted atom set made the tool
manufacture phantom findings, including a fabricated/wrong-side [REMOVED]
citation (new_quote: null) for a clause that in fact appears verbatim on
the new side (gate 4 hard fail) plus a noise-rate violation (gate 2).

Root fix (policydiff/sentence.py):
  * _BOUNDARY_RE's lookahead class now includes "$", so a period/bang/
    question-mark followed by whitespace followed by a dollar amount is
    always a valid sentence boundary.
  * _CONTINUATION_START_RE is restricted to a bare lowercase letter --
    "$"/digit-initial (or uppercase-initial) lines never trigger the
    continuation-join path; only a line that unambiguously continues an
    in-progress sentence (starts lowercase) still joins.

Defect 2 (lower -- gate 5, "a suppression step never exercised is
not a feature"): under --no-suppress-cosmetic, quote/dash/heading-rename
pairs correctly surfaced findings, but whitespace-run, line-join/rewrap,
and enumerator/renumber differences did not -- because those particular
normalizations ran UNCONDITIONALLY, upstream of the suppress_cosmetic
toggle entirely:
  * a numbered clause's enumerator ("4." vs "7.") is parsed OUT of
    Clause.text at segmentation time and never re-enters any text
    comparison, regardless of the flag.
  * unnumbered-prose sentence atomization (sentence.py) always collapses
    a physical line break to a single space before classify.py ever
    runs, destroying the one piece of information a rewrap-only edit
    needs to be visible.
  * classify.py's fast-path identity check (light_normalize) ALWAYS
    collapsed internal whitespace runs, independent of suppress_cosmetic,
    so a pure whitespace-run/tab edit returned "unchanged" before the
    caller-supplied flag was ever consulted.

Root fix:
  * Clause gained a `text_raw` field (segment.py) that preserves a
    "paragraph" (unnumbered-sentence) clause's original line-break
    position; every other clause kind already keeps its own line breaks
    in `text` itself. classify.py compares `text_raw` (falling back to
    `text`) instead of `text` when suppress_cosmetic is False.
  * classify.py separately compares old.id / new.id for clause kinds
    with a real printed enumerator (numeric/lettered/roman) when
    suppress_cosmetic is False, since the id never enters `text` at all.
  * normalize.py's light_normalize() takes a suppress_cosmetic flag and
    only collapses internal whitespace runs when it's True.

These fixtures are original (not copies of the reviewer's an earlier audit
fixture/probe files under the audit fixtures)
and exercise the general class.
"""
from policydiff.report import diff_documents, human_report, to_json


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# Defect 1 -- $/digit-initial standalone sentences must never be glued
# to the sentence before them.
# ---------------------------------------------------------------------


def test_three_standalone_sentences_one_dollar_initial_reorder_is_empty():
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
    # No phantom MODIFIED/ADDED/REMOVED at all -- every sentence is a
    # clean "unchanged" match regardless of position.
    assert [f.kind for f in result.findings] == ["unchanged", "unchanged", "unchanged"]


def test_three_standalone_sentences_reorder_no_fabricated_citation():
    # The reviewer's exact failure mode: a fabricated [REMOVED] with
    # new_quote:null for a clause that IS present verbatim on the new
    # side. Assert directly against the JSON citations, not just the
    # finding kinds, so a regression here can never hide behind a
    # differently-labeled but still-wrong finding.
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
    items = to_json(result)["findings"]
    assert all(item["kind"] != "removed" for item in items), items
    assert all(item["kind"] != "added" for item in items), items
    for item in items:
        assert item["old_quote"] == item["new_quote"]
        assert item["new_quote"] is not None


def test_digit_initial_standalone_sentence_reorder_is_empty():
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


def test_control_letter_initial_standalone_sentence_reorder_is_empty():
    # Sanity control (matches the reviewer's own reorder_cap_letter probe):
    # the same reorder, with the third sentence starting with a plain
    # letter instead of "$", must ALSO be empty -- proves the fix isn't
    # accidentally keyed on "any capital-letter-led sentence".
    old = (
        "The most we will pay under this policy is one million dollars.\n"
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
    )
    new = (
        "Fire losses are covered.\n"
        "Theft losses are covered.\n"
        "The most we will pay under this policy is one million dollars.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


def test_dollar_initial_standalone_sentence_removed_is_exactly_one_removed():
    # Recall check: a genuine removal of a $-initial standalone sentence
    # must still be caught cleanly -- exactly one REMOVED, not silently
    # absorbed into a neighboring atom.
    old = "$1,000,000 is the most we will pay under this policy.\nFire losses are covered.\n"
    new = "Fire losses are covered.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    removed = [f for f in result.findings if f.kind == "removed"]
    assert len(removed) == 1, result.findings
    assert removed[0].old.text == "$1,000,000 is the most we will pay under this policy."
    assert _non_suppressed(result) == removed


def test_genuinely_wrapped_sentence_lowercase_continuation_still_joins_and_edit_is_one_finding():
    # A real edit on the wrapped (lowercase-continuation) second physical
    # line must still be caught as ONE narrowed finding on the whole
    # (re-joined) sentence -- not split into two atoms.
    old = "The aggregate limit of insurance\nis $1,000,000.\n"
    new = "The aggregate limit of insurance\nis $500,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert [f.kind for f in result.findings] == ["narrowed"]
    assert result.findings[0].old.text == "The aggregate limit of insurance is $1,000,000."
    assert result.findings[0].new.text == "The aggregate limit of insurance is $500,000."


def test_rewrap_of_genuinely_wrapped_sentence_is_empty():
    # The SAME sentence, wrapped at a different word -- must be a pure
    # no-op (this is an earlier fix; verifying it survives an earlier revision's
    # narrower continuation trigger).
    old = "The aggregate limit of insurance\nis $1,000,000.\n"
    new = "The aggregate limit of\ninsurance is $1,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


def test_two_distinct_dollar_initial_items_still_separate():
    # Two genuinely distinct $-initial standalone statements must never
    # be fused into one atom just because both start with "$".
    old = "$500 deductible applies to fire claims.\n$1,000 deductible applies to theft claims.\n"
    new = "$500 deductible applies to fire claims.\n$2,000 deductible applies to theft claims.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, result.findings
    assert non_suppressed[0].old.text == "$1,000 deductible applies to theft claims."
    assert non_suppressed[0].new.text == "$2,000 deductible applies to theft claims."


# ---------------------------------------------------------------------
# Defect 2 -- every cosmetic axis must be gated by suppress_cosmetic,
# not just heading-rename/dash/quote.
#
# For each axis: default (suppress_cosmetic=True) -> fully suppressed
# (unchanged/cosmetic/heading only); --no-suppress-cosmetic (False) ->
# at least one non-suppressed finding.
# ---------------------------------------------------------------------


def _assert_gate5_axis(old: str, new: str):
    default_result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(default_result) == [], (
        "default (suppression ON) must be fully suppressed:\n" + human_report(default_result, verbose=True)
    )
    off_result = diff_documents(old, new, suppress_cosmetic=False)
    non_suppressed = _non_suppressed(off_result)
    assert non_suppressed != [], (
        "--no-suppress-cosmetic must surface this cosmetic-only pair as a "
        "real finding, not silently stay empty -- SPEC gate 5"
    )
    # Sanity: still a full, non-crashing finding set.
    assert len(off_result.findings) >= len(non_suppressed) > 0


def test_gate5_whitespace_axis():
    _assert_gate5_axis(
        "1. The  limit is $1,000,000.\n",
        "1. The limit is  $1,000,000.\n",
    )


def test_gate5_rewrap_axis():
    # Deliberately wraps at an ordinary word (lowercase continuation),
    # not immediately before a "$" amount, so defect 1's fix does not
    # itself introduce a real atom-count difference here.
    _assert_gate5_axis(
        "The aggregate limit of insurance\nis $1,000,000.\n",
        "The aggregate limit of\ninsurance is $1,000,000.\n",
    )


def test_gate5_single_level_renumber_axis():
    _assert_gate5_axis(
        "4. The limit is $1,000,000.\n",
        "7. The limit is $1,000,000.\n",
    )


def test_gate5_multi_level_renumber_axis():
    _assert_gate5_axis(
        "4.2 The limit is $1,000,000.\n",
        "4.3 The limit is $1,000,000.\n",
    )


def test_gate5_dash_axis():
    _assert_gate5_axis(
        "Coverage A - liability applies.\n",
        "Coverage A — liability applies.\n",
    )


def test_gate5_quote_axis():
    _assert_gate5_axis(
        'The "insured" is covered.\n',
        "The “insured” is covered.\n",
    )


def test_gate5_defined_term_recap_axis():
    _assert_gate5_axis(
        'The "Insured" is covered under this policy.\n',
        'The "insured" is covered under this policy.\n',
    )


def test_gate5_heading_rename_axis():
    _assert_gate5_axis(
        "SECTION I -- DEFINITIONS\n1. Fire is covered.\n",
        "SECTION I -- DEFS\n1. Fire is covered.\n",
    )


def test_gate5_default_mode_all_axes_still_empty_together():
    # A single combined document exercising every axis at once, still
    # fully suppressed by default -- guards against a fix that only
    # works axis-by-axis in isolation.
    old = (
        "SECTION I -- DEFINITIONS\n"
        "1. The  limit is $1,000,000.\n"
        "4.2 Coverage A - liability applies.\n"
        'The "Insured" is covered.\n'
        "The aggregate limit of insurance\nis $500,000.\n"
    )
    new = (
        "SECTION I -- DEFS\n"
        "1. The limit is  $1,000,000.\n"
        "4.3 Coverage A — liability applies.\n"
        'The "insured" is covered.\n'
        "The aggregate limit of\ninsurance is $500,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


def test_gate5_no_suppress_does_not_fabricate_a_real_edit_when_none_exists():
    # Turning the toggle off must never invent a numeric/direction change
    # that isn't there -- a pure renumber's finding must still describe
    # the renumber, not a bogus "limit changed" detail.
    result = diff_documents(
        "4. The limit is $1,000,000.\n",
        "7. The limit is $1,000,000.\n",
        suppress_cosmetic=False,
    )
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == "modified"
    assert "renumber" in finding.detail.lower()
