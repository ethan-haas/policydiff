"""Regression tests for an earlier audit's two defect families (fresh independent
independent reviewer, 7 defects, this is the
THIRD consecutive round the heading/coverage classifier misfired: r4
glued headings, r5 keyed on caps+no-period, r6 found the exact boundary
that surface-form gate missed).

Root cause A (5 defects, esc1/esc1b/esc2/esc3/esc4/esc5): heading-rename
SUPPRESSION was still driven by a SURFACE-FORM content gate living in
segment.py (caps + coverage-word + copula/negation). That gate silently
dropped:
  * "EARTHQUAKE EXCLUDED" -- "excluded" is a predicate/participle with
    no separate copula word, so the old gate's "coverage word AND
    is/are/not/no" test failed even though the line is a plain
    assertion.
  * "THIS POLICY EXCLUDES FLOOD" -- same story, verb form "excludes".
  * "Windstorm Deductible: $2,500" / "Flood: Excluded" -- Title-Case
    colon-value rows never even reached the coverage check (it only
    ran in the ALL-CAPS branch of segment.py's old heading matcher).
  * two distinct all-caps items ("FLOOD EXCLUDED" / "WAR EXCLUDED"),
    removing one -- both sides misread as headings, the real removal
    vanished entirely instead of reporting exactly one REMOVED.

an earlier fix, per "delete-the-mechanism-after-two-high-defects":
segment.py's heading detection goes back to pure SURFACE SHAPE (no
content opinion at all -- see its module comment). Suppression is now a
CONTENT-DELTA decision in report.py (_is_coverage_bearing /
_is_label_rename_only): a heading-shaped change is suppressed only if
NEITHER side carries coverage-bearing content (a $/digit amount, a
coverage verb/negation phrase, or a coverage noun in assertion
position). A false positive (reporting a genuine bare-title rename) is
never possible to fully rule out from vocabulary alone, but the design
explicitly prefers over-reporting to a silent drop.

Root cause B (esc6): group_prose_lines() flushed every physical line
with no trailing sentence punctuation as its own atom, so a wrapped
sentence re-flowed at a different word ("The aggregate limit of
insurance\\nis $1,000,000." -> "The aggregate limit of\\ninsurance is
$1,000,000.") changed the atom SET and produced two phantom [MODIFIED]
findings out of pure reflow. an earlier fix: an unpunctuated line only
flushes if the NEXT physical line does NOT look like a continuation
(does not start with a lowercase letter or digit/$) -- see
sentence.py's _is_continuation_start.

These fixtures are original (not copies of the reviewer's an earlier audit
fixture/probe files under the audit fixtures)
and exercise the general class.
"""
from policydiff.report import diff_documents, human_report


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) all-caps coverage line removed/added -- reported, not swallowed
#     into a suppressed heading, even with no copula word.
# ---------------------------------------------------------------------


def test_all_caps_coverage_line_removed_is_reported():
    old = "Coverage A applies to bodily injury and property damage.\nEARTHQUAKE EXCLUDED\n"
    new = "Coverage A applies to bodily injury and property damage.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "removed", f.detail
    assert f.new is None
    assert "EARTHQUAKE EXCLUDED" in f.old.text


def test_all_caps_coverage_line_added_is_reported():
    old = "Coverage A applies to bodily injury and property damage.\n"
    new = "Coverage A applies to bodily injury and property damage.\nEARTHQUAKE EXCLUDED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "added", f.detail
    assert f.old is None
    assert "EARTHQUAKE EXCLUDED" in f.new.text


# ---------------------------------------------------------------------
# (b) verb-form assertion with no copula ("EXCLUDES") -- REMOVED.
# ---------------------------------------------------------------------


def test_verb_assertion_exclusion_removed_is_reported():
    old = "Coverage A applies to bodily injury and property damage.\nTHIS POLICY EXCLUDES FLOOD\n"
    new = "Coverage A applies to bodily injury and property damage.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "removed", f.detail
    assert "EXCLUDES" in f.old.text


# ---------------------------------------------------------------------
# (c) Title-Case colon-value rows -- removed / $ change reported.
# ---------------------------------------------------------------------


def test_colon_row_exclusion_removed_is_reported():
    old = "Coverage A applies to bodily injury and property damage.\nFlood: Excluded\n"
    new = "Coverage A applies to bodily injury and property damage.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "removed"
    assert "Excluded" in non_suppressed[0].old.text


def test_colon_row_deductible_dollar_change_is_narrowed():
    old = "Coverage A applies to bodily injury and property damage.\nWindstorm Deductible: $2,500\n"
    new = "Coverage A applies to bodily injury and property damage.\nWindstorm Deductible: $5,000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "2,500" in f.detail and "5,000" in f.detail


# ---------------------------------------------------------------------
# (d) two distinct all-caps coverage items -- remove one -> exactly one
#     REMOVED (not zero, not both).
# ---------------------------------------------------------------------


def test_two_distinct_all_caps_items_remove_one_is_exactly_one_removed():
    old = "FLOOD EXCLUDED\nWAR EXCLUDED\n"
    new = "FLOOD EXCLUDED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "removed", f.detail
    assert "WAR EXCLUDED" in f.old.text


# ---------------------------------------------------------------------
# (e) GUARD: genuine bare-title renames with unchanged body stay EMPTY,
#     even though this class of line is now segmented purely by shape.
# ---------------------------------------------------------------------


def test_guard_definitions_bare_title_rename_stays_empty():
    old = "DEFINITIONS\nThe insured means the named entity.\n"
    new = "TERMS\nThe insured means the named entity.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_guard_schedule_of_limits_bare_title_rename_stays_empty():
    # The r5 boundary case explicitly called out by the fix spec: this
    # title contains the word "limit"/"insurance" but is a bare noun
    # phrase (no verb/amount/colon-value), so it must stay suppressed.
    old = "SCHEDULE OF LIMITS\nEach occurrence limit is $1,000,000.\n"
    new = "SCHEDULE OF LIMITS OF INSURANCE\nEach occurrence limit is $1,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_guard_heading_moved_unchanged_body_stays_empty():
    old = "EXCLUSIONS\nCoverage A applies to bodily injury and property damage.\n"
    new = "Coverage A applies to bodily injury and property damage.\nEXCLUSIONS\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []


def test_guard_limit_of_insurance_colon_dollar_change_is_narrowed():
    # The companion case: the SAME "limit of insurance" vocabulary, but
    # with an actual $ assertion -- must be reported, not suppressed.
    old = "LIMIT OF INSURANCE: $1,000,000\n"
    new = "LIMIT OF INSURANCE: $500,000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "1,000,000" in f.detail and "500,000" in f.detail


# ---------------------------------------------------------------------
# (f) Root cause B: a rewrapped sentence (line break moved, same words)
#     must be EMPTY, in both directions.
# ---------------------------------------------------------------------


def test_rewrapped_sentence_break_moved_is_empty():
    old = "The aggregate limit of insurance\nis $1,000,000.\n"
    new = "The aggregate limit of\ninsurance is $1,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    # And the reverse direction.
    result_rev = diff_documents(new, old, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


def test_two_distinct_unpunctuated_items_still_separate_after_rewrap_fix():
    # GUARD: the continuation-join must not fuse two genuinely distinct
    # unpunctuated items just because neither ends in terminal
    # punctuation -- the second line here starts uppercase, not a
    # continuation, so it must stay its own atom (same as (d) above,
    # exercised through the sentence-grouping layer directly).
    from policydiff.sentence import group_prose_lines

    chunks = group_prose_lines(["FLOOD EXCLUDED", "WAR EXCLUDED"])
    assert chunks == ["FLOOD EXCLUDED", "WAR EXCLUDED"], chunks


def test_rewrap_continuation_join_produces_identical_chunk_both_ways():
    from policydiff.sentence import group_prose_lines

    old_chunks = group_prose_lines(["The aggregate limit of insurance", "is $1,000,000."])
    new_chunks = group_prose_lines(["The aggregate limit of", "insurance is $1,000,000."])
    assert old_chunks == new_chunks == ["The aggregate limit of insurance is $1,000,000."]
