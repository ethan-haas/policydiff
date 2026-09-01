"""Regression tests for an earlier fix (HIGH severity including
a wrong-direction defects against HEAD
fa8a6d6).

The bug: a numbered clause's own physical-line-completion continuation
gate (an earlier fix, see the matching regression test) made a
clause's ATOM SET depend on exactly where a line break happened to fall
within it. "4. X. Y." on ONE physical line stayed a single atom; the
SAME two sentences rewrapped across TWO physical lines closed the clause
after the first sentence and spun the second sentence off as an
unrelated standalone atom -- so a pure REFLOW of a multi-sentence
numbered clause (no content change at all) manufactured a phantom
[ADDED] finding with a fabricated citation, and on a real edit inside
that second sentence, the same phantom add/remove could invert the
reported direction entirely (a coverage CUT read as a BROADENING).

"1. X.\nY." is the identical shape whether Y is a genuinely separate
provision that happens to follow X (an earlier revision's "mask" scenario) or a
wrapped continuation of X (an earlier revision's "wrap" scenario) -- a line-break
heuristic cannot tell them apart on its own.

Root fix (policydiff/segment.py): a numbered/roman/lettered clause now
absorbs its ENTIRE body -- every physical line up to the next
enumerator/heading/EOF -- unconditionally, with all internal whitespace
(line breaks, blank lines) collapsed to single spaces for its `text`.
"X.\nY." and "X. Y." always produce the byte-identical atom, so the atom
SET a document produces no longer depends on where a physical line
break falls. `text_raw` preserves the original layout for
--no-suppress-cosmetic.

Recall is preserved by policydiff/classify.py's per-sentence
classification (an earlier revision's original backup mechanism, broadened by round
15 to fire for as few as ONE changed sentence rather than requiring 2+),
which reports every independently-changed sentence inside an aligned
clause pair as its own precisely-cited Finding.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures
the task's FORBIDDEN clause) -- they are original clauses exercising the
same scenario classes described in the task.
"""
from policydiff.report import diff_documents, human_report
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) reflow at a sentence boundary ('.' then a line break) -> EMPTY.
# ---------------------------------------------------------------------


def test_reflow_at_sentence_boundary_is_empty():
    old = (
        "6. Coverage D applies to theft of scheduled property. "
        "It also applies to vandalism of scheduled property.\n"
    )
    new = (
        "6. Coverage D applies to theft of scheduled property.\n"
        "It also applies to vandalism of scheduled property.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# (b) reflow after a closing quote (no sentence-ending punctuation at the
# break) -> EMPTY.
# ---------------------------------------------------------------------


def test_reflow_after_closing_quote_is_empty():
    old = '7. This exclusion applies only to "hired autos" scheduled on the declarations page.\n'
    new = (
        '7. This exclusion applies only to "hired autos"\n'
        "scheduled on the declarations page.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# (c) reflow of a multi-sentence clause PLUS one real change inside the
# second sentence -> exactly that one finding, correct direction, no
# phantom added/removed.
# ---------------------------------------------------------------------


def test_reflow_plus_one_real_change_is_one_finding_correct_direction():
    old = (
        "8. Coverage E applies to bodily injury arising from products sold by the insured. "
        "It also applies to property damage arising from those products.\n"
    )
    new = (
        "8. Coverage E applies to bodily injury arising from products sold by the insured.\n"
        "It does not apply to property damage arising from those products.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    # A pure removal of "also applies to X" -> "does not apply to X" is a
    # coverage cut, never a broadening; no phantom [ADDED]/[REMOVED] pair.
    assert f.kind in ("narrowed", "modified"), f.detail
    assert f.kind != "broadened", f.detail
    assert f.old.text == "It also applies to property damage arising from those products."
    assert f.new.text == "It does not apply to property damage arising from those products."


# ---------------------------------------------------------------------
# (d) the reproduced "wrapreal" shape: a numbered clause's second
# sentence carries a monetary limit that is CUT (narrowed) while being
# rewrapped onto its own physical line -- must report NARROWED only, no
# phantom [BROADENED]/[ADDED], no wrong direction.
# ---------------------------------------------------------------------


def test_wrap_plus_limit_cut_reports_narrowed_only_no_phantom():
    old = (
        "9. Coverage F applies to bodily injury during the policy period. "
        "The General Aggregate Limit is $4,000,000.\n"
    )
    new = (
        "9. Coverage F applies to bodily injury during the policy period.\n"
        "The General Aggregate Limit is $2,000,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "4,000,000" in f.detail and "2,000,000" in f.detail
    assert f.old.text == "The General Aggregate Limit is $4,000,000."
    assert f.new.text == "The General Aggregate Limit is $2,000,000."
    # No phantom added/removed finding anywhere in the result.
    assert not any(finding.kind in ("added", "removed") for finding in result.findings)


# ---------------------------------------------------------------------
# (e) GUARD -- an earlier revision's mask shape must still report all three trailing
# changes, clause 1's own sentence untouched, each precisely cited.
# ---------------------------------------------------------------------


def test_mask_shape_still_three_findings():
    old = (
        "10. Coverage G applies to business personal property.\n"
        "Coinsurance of 80% applies to covered property.\n"
        "This insurance does not apply to flood.\n"
        "The waiting period is 14 days before benefits begin.\n"
    )
    new = (
        "10. Coverage G applies to business personal property.\n"
        "Coinsurance of 90% applies to covered property.\n"
        "This insurance does not apply to flood or mudslide.\n"
        "The waiting period is 30 days before benefits begin.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 3, [(f.kind, f.detail) for f in non_suppressed]
    assert all(
        f.old is None or f.old.text != "Coverage G applies to business personal property."
        for f in non_suppressed
    )


# ---------------------------------------------------------------------
# (f) GUARD -- a genuinely separate trailing provision's own real change
# is still caught (not accidentally suppressed by the reflow-invariance
# fix -- the fix must never trade recall away).
# ---------------------------------------------------------------------


def test_genuinely_separate_trailing_provision_change_still_caught():
    old = (
        "11. Coverage H applies to fire damage.\n"
        "A separate hurricane deductible of 2% applies to wind claims.\n"
    )
    new = (
        "11. Coverage H applies to fire damage.\n"
        "A separate hurricane deductible of 5% applies to wind claims.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.old.text == "A separate hurricane deductible of 2% applies to wind claims."
    assert f.new.text == "A separate hurricane deductible of 5% applies to wind claims."
    assert f.old.text != "Coverage H applies to fire damage."


# ---------------------------------------------------------------------
# GUARD -- control: reflow that lands mid-phrase (no sentence-ending
# punctuation at the break at all) never triggers per-sentence splitting
# and stays a single-sentence clause, EMPTY on a pure rewrap.
# ---------------------------------------------------------------------


def test_control_midphrase_wrap_stays_single_sentence_clause():
    old = "12. Exclusion applies to loss arising out of nuclear reaction or radiation.\n"
    new = "12. Exclusion applies to loss arising out of nuclear reaction\nor radiation.\n"
    old_clauses = segment(old)
    assert len(old_clauses) == 1, old_clauses
    assert old_clauses[0].text == "Exclusion applies to loss arising out of nuclear reaction or radiation."
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)
