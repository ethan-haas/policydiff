"""Regression tests for defect 2: narrowed/broadened direction
must NEVER be inferred from net text length -- that heuristic inverts
constantly (adding a restriction is longer text but narrows; removing one
is shorter text but broadens). Direction must come from a real semantic
signal, or the finding must honestly resolve to "modified (direction
unclear)" rather than guess.

All fixtures here are original, non-exclusion clauses (coverage grants /
conditions) -- the exact clause class the defect called out -- and are
NOT copies of the reviewer's probe/fixture files.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str):
    old = segment(f"1. Clause. {old_text}\n")[0]
    new = segment(f"1. Clause. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


def test_limit_increase_is_broadened():
    f = _pair(
        "The aggregate limit is $1,000,000.",
        "The aggregate limit is $2,000,000.",
    )
    assert f.kind == "broadened", f.detail


def test_limit_decrease_is_narrowed():
    f = _pair(
        "The aggregate limit is $2,000,000.",
        "The aggregate limit is $1,000,000.",
    )
    assert f.kind == "narrowed", f.detail


def test_deductible_increase_is_narrowed():
    f = _pair(
        "A deductible of $500 applies per claim.",
        "A deductible of $2,500 applies per claim.",
    )
    assert f.kind == "narrowed", f.detail


def test_deductible_decrease_is_broadened():
    f = _pair(
        "A deductible of $2,500 applies per claim.",
        "A deductible of $500 applies per claim.",
    )
    assert f.kind == "broadened", f.detail


def test_sublimit_added_is_narrowed():
    f = _pair(
        "The company will pay all covered defense costs.",
        "The company will pay all covered defense costs, subject to a cap of $50,000.",
    )
    assert f.kind == "narrowed", f.detail


def test_sublimit_removed_is_broadened():
    f = _pair(
        "The company will pay all covered defense costs, subject to a cap of $50,000.",
        "The company will pay all covered defense costs.",
    )
    assert f.kind == "broadened", f.detail


def test_restriction_added_to_coverage_grant_is_narrowed_not_broadened():
    # This is the exact inversion class from the defect: the edited text
    # is LONGER (net length went UP) but the change is a NARROWING
    # (adding "only"/"solely" restricts when/how coverage applies). The
    # old net-length heuristic reported this as [BROADENED].
    f = _pair(
        "The company will indemnify the insured for covered loss.",
        "The company will indemnify the insured for covered loss, but only "
        "if notice is given within 30 days and solely for claims made during "
        "the policy period.",
    )
    assert f.kind == "narrowed", f.detail
    assert f.detail != "text net expanded"


def test_restriction_removed_from_coverage_grant_is_broadened_not_narrowed():
    # Mirror image: text got SHORTER (net length DOWN) but removing a
    # restriction broadens coverage. The old heuristic reported narrowed.
    f = _pair(
        "The company will indemnify the insured for covered loss, but only "
        "if notice is given within 30 days and solely for claims made during "
        "the policy period.",
        "The company will indemnify the insured for covered loss.",
    )
    assert f.kind == "broadened", f.detail


def test_unresolvable_direction_reports_modified_not_a_guess():
    # A genuine substitution with no numeric/restrictive/inclusive signal
    # either way -- must not guess a direction from which side is longer.
    f = _pair(
        "Claims are handled by the regional office.",
        "Claims are handled by the national processing center.",
    )
    assert f.kind == "modified", f.detail
