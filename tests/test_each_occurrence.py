"""Regression tests for an earlier fix (defect: 1 root-cause
defect, 3 manifestations) against HEAD
95d23a5 -- a wrong-direction defects (the specification's worst category).

The defect: the phrase "each occurrence" (and "per occurrence"/"each
accident"/"each claim") was a candidate role-keyword in the "limit" group
of _ROLE_KEYWORD_RE. A frequency qualifier like "each occurrence" is NOT a
role word on its own -- it only means "this cap resets per event" -- but
"deductible of $10,000 each occurrence" had TWO role-keyword candidates in
the same segment ("deductible" and "each occurrence"), and _amount_role's
nearest-to-the-amount tiebreak almost always picked "each occurrence"
(it sits immediately after the amount, closer than "deductible" which
comes before it). That silently RE-ASSIGNED the amount's role from
deductible to limit, and inverted the reported direction: a deductible
INCREASE (which narrows coverage -- the insured now pays more out of
pocket before the policy responds) was reported as
"[BROADENED] limit changed from $10,000 to $20,000" -- wrong role AND
wrong direction.

Root fix (see policydiff/classify.py's _ROLE_KEYWORD_RE an earlier revision comment):
frequency phrases ("each occurrence", "per occurrence", "each accident",
"each claim") are removed entirely from role-keyword candidacy. Role =
limit is now triggered ONLY by an actual limit word ("limit", "aggregate",
"most we will pay") being present in the amount's own segment -- never by
a bare frequency qualifier. An explicit, specific role word (deductible /
retention / SIR / sublimit) therefore always wins for an amount that has
no competing limit word in its segment, even when a frequency phrase sits
right next to the amount.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures (that
directory is -- they are
original clauses built from the same scenarios described in the task.
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, suppress_cosmetic: bool = True):
    old = segment(f"9. {old_text}\n")[0]
    new = segment(f"9. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=suppress_cosmetic)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a)/(b) -- deductible "each occurrence": role must stay "deductible",
# direction must follow deductible polarity (higher = narrowed), not
# limit polarity (higher = broadened).
# ---------------------------------------------------------------------


def test_deductible_each_occurrence_increase_is_narrowed():
    f = _pair(
        "The insured pays a deductible of $10,000 each occurrence.",
        "The insured pays a deductible of $20,000 each occurrence.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "10,000" in f.detail and "20,000" in f.detail


def test_deductible_each_occurrence_decrease_is_broadened():
    f = _pair(
        "The insured pays a deductible of $20,000 each occurrence.",
        "The insured pays a deductible of $10,000 each occurrence.",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "20,000" in f.detail and "10,000" in f.detail


# ---------------------------------------------------------------------
# (c) -- self-insured retention "each occurrence" must be treated exactly
# like a deductible (the "retention" role word wins over the frequency
# phrase).
# ---------------------------------------------------------------------


def test_self_insured_retention_each_occurrence_increase_is_narrowed():
    f = _pair(
        "A self-insured retention of $10,000 each occurrence applies.",
        "A self-insured retention of $20,000 each occurrence applies.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail  # SIR/retention shares the deductible role label
    assert "limit" not in f.detail
    assert "10,000" in f.detail and "20,000" in f.detail


# ---------------------------------------------------------------------
# (d) GUARD -- a genuine "each occurrence limit" must be unaffected: the
# word "limit" is actually present, so role = limit is still correct, and
# a higher limit is still a broadening.
# ---------------------------------------------------------------------


def test_genuine_each_occurrence_limit_increase_is_still_broadened():
    f = _pair(
        "The each occurrence limit is $1,000,000.",
        "The each occurrence limit is $2,000,000.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


# ---------------------------------------------------------------------
# (e) GUARD -- the pre-existing "per claim" deductible control must stay
# unbroken (it never went through the buggy "each occurrence" path, but
# must keep passing after the precedence fix).
# ---------------------------------------------------------------------


def test_per_claim_deductible_increase_still_narrowed():
    f = _pair(
        "The insured pays a deductible of $10,000 per claim.",
        "The insured pays a deductible of $20,000 per claim.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "10,000" in f.detail and "20,000" in f.detail


# ---------------------------------------------------------------------
# (f) -- "aggregate limit ... each occurrence"-style phrasing (a limit
# word AND a frequency phrase together) must still classify as limit,
# because "limit"/"aggregate" is present -- the frequency phrase is just
# along for the ride and never competes for role.
# ---------------------------------------------------------------------


def test_aggregate_limit_each_occurrence_phrasing_still_limit():
    f = _pair(
        "The aggregate limit each occurrence is $1,000,000.",
        "The aggregate limit each occurrence is $2,000,000.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


def test_per_occurrence_deductible_phrasing_also_fixed():
    # Same defect class, "per occurrence" spelling instead of "each
    # occurrence" -- both are frequency qualifiers per the module
    # docstring / _FREQUENCY_RE, neither is a role word.
    f = _pair(
        "The insured pays a deductible of $10,000 per occurrence.",
        "The insured pays a deductible of $20,000 per occurrence.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


def test_full_document_diff_reports_narrowed_deductible_not_broadened_limit():
    # End-to-end through diff_documents (not just classify_pair) for the
    # exact live-reproduced scenario, to match how the CLI actually
    # surfaces findings.
    result = diff_documents(
        "9. The insured pays a deductible of $10,000 each occurrence.\n",
        "9. The insured pays a deductible of $20,000 each occurrence.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed"
    assert "deductible" in f.detail
    assert "limit" not in f.detail
