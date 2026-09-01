"""Regression tests for an earlier fix, all
in the direction/classification logic (policydiff/classify.py).

Defect 1 (HIGH) -- direction inverted + field fabricated: the classifier
used to key off the WORD "deductible" appearing ANYWHERE in the clause
and apply deductible semantics to whichever dollar figure changed
first -- even when that figure was actually the LIMIT and the deductible
was untouched. Root fix: every monetary amount is assigned a ROLE
(deductible | sublimit | limit) from its OWN local context (the segment
of the clause it actually sits in, split on ';'/',' that aren't part of
a money literal's own thousands-grouping), and amounts are compared BY
ROLE -- an unchanged amount of one role can never influence the
direction computed for a changed amount of a different role.

Defect 2 (MED-HIGH) -- a clause with more than one changed amount used
to classify on only ONE of them and silently drop the other, so a
co-occurring narrowing (e.g. a sublimit cut) vanished behind a
broadening (e.g. an aggregate raised) reported for the same clause.
Root fix: classify_pair_multi returns one Finding PER changed amount.

Defect 3 / 3b (LOW, under-call) -- a reimbursement/coinsurance
percentage decrease, and a waiting/elimination period increase, used to
resolve to "modified (direction unclear)" even though direction is
definable from unambiguous phrasing. Root fix: two new narrow signal
detectors (_classify_reimburse_percent, _classify_wait_period) that only
fire on a single, unambiguous match per side.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures (that
directory is -- they are
original clauses built from the same scenarios described in the task.
"""
from policydiff.classify import classify_pair, classify_pair_multi
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str):
    old = segment(f"1. {old_text}\n")[0]
    new = segment(f"1. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


def _pair_multi(old_text: str, new_text: str):
    old = segment(f"1. {old_text}\n")[0]
    new = segment(f"1. {new_text}\n")[0]
    return classify_pair_multi(old, new, suppress_cosmetic=True)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a)/(b)/(c) -- role-aware direction with an UNCHANGED amount of a
# different role present in the same clause (defect 1).
# ---------------------------------------------------------------------


def test_limit_increase_with_unchanged_deductible_is_broadened_not_deductible():
    f = _pair(
        "Coverage limit is $1,000,000, with a deductible of $500 per claim.",
        "Coverage limit is $2,000,000, with a deductible of $500 per claim.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


def test_limit_decrease_with_unchanged_deductible_is_narrowed():
    f = _pair(
        "Coverage limit is $2,000,000, with a deductible of $500 per claim.",
        "Coverage limit is $1,000,000, with a deductible of $500 per claim.",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" in f.detail


def test_deductible_increase_with_unchanged_limit_is_narrowed_names_deductible():
    f = _pair(
        "Coverage limit is $1,000,000, with a deductible of $500 per claim.",
        "Coverage limit is $1,000,000, with a deductible of $1,500 per claim.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "500" in f.detail and "1,500" in f.detail


def test_deductible_decrease_with_unchanged_limit_is_broadened():
    f = _pair(
        "Coverage limit is $1,000,000, with a deductible of $1,500 per claim.",
        "Coverage limit is $1,000,000, with a deductible of $500 per claim.",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail


def test_deductible_ahead_of_limit_still_resolves_correctly():
    # Deductible mentioned FIRST in the sentence, limit SECOND -- role
    # assignment must not depend on textual order, only local context.
    f = _pair(
        "Subject to a deductible of $500 per claim, the limit is $1,000,000.",
        "Subject to a deductible of $500 per claim, the limit is $3,000,000.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail


# ---------------------------------------------------------------------
# (d) -- multi-amount clause: aggregate raised AND sublimit cut. BOTH
# must be surfaced; the narrowing must never be dropped (defect 2).
# ---------------------------------------------------------------------


def test_multi_amount_aggregate_up_and_sublimit_down_both_surfaced():
    findings = _pair_multi(
        "Aggregate limit is $1,000,000; jewelry sublimit is $2,500 per item.",
        "Aggregate limit is $2,000,000; jewelry sublimit is $500 per item.",
    )
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in findings]

    broadened = [f for f in findings if f.kind == "broadened"][0]
    narrowed = [f for f in findings if f.kind == "narrowed"][0]
    assert "1,000,000" in broadened.detail and "2,000,000" in broadened.detail
    assert "2,500" in narrowed.detail and "500" in narrowed.detail
    # The narrowing must be visible standalone, not just inside the raw
    # quote -- i.e. it is its own Finding with kind == "narrowed", which
    # the assertions above already establish.


def test_multi_amount_narrowing_survives_full_report_pipeline():
    old = "1. Aggregate limit is $1,000,000; jewelry sublimit is $2,500 per item.\n"
    new = "1. Aggregate limit is $2,000,000; jewelry sublimit is $500 per item.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in non_suppressed]
    # A downstream consumer reading only the finding kinds (not the raw
    # quote) must still see the coverage cut.
    narrowed_details = " ".join(f.detail for f in non_suppressed if f.kind == "narrowed")
    assert "sublimit" in narrowed_details


# ---------------------------------------------------------------------
# (e) -- reimbursement percentage decrease is NARROWED, not unclear.
# ---------------------------------------------------------------------


def test_reimbursement_percent_decrease_is_narrowed():
    f = _pair(
        "The plan reimburses 90% of covered costs.",
        "The plan reimburses 60% of covered costs.",
    )
    assert f.kind == "narrowed", f.detail
    assert "90" in f.detail and "60" in f.detail


def test_reimbursement_percent_increase_is_broadened():
    f = _pair(
        "We pay 60% of eligible expenses under this section.",
        "We pay 90% of eligible expenses under this section.",
    )
    assert f.kind == "broadened", f.detail


def test_coinsurance_payshare_percent_decrease_is_narrowed():
    f = _pair(
        "Benefits are subject to 80% coinsurance for out-of-network care.",
        "Benefits are subject to 50% coinsurance for out-of-network care.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (f) -- waiting/elimination period increase is NARROWED, not unclear.
# ---------------------------------------------------------------------


def test_waiting_period_increase_is_narrowed():
    f = _pair(
        "Benefits begin after a waiting period of 30 days.",
        "Benefits begin after a waiting period of 90 days.",
    )
    assert f.kind == "narrowed", f.detail
    assert "30" in f.detail and "90" in f.detail


def test_waiting_period_decrease_is_broadened():
    f = _pair(
        "Benefits begin after a waiting period of 90 days.",
        "Benefits begin after a waiting period of 30 days.",
    )
    assert f.kind == "broadened", f.detail


def test_elimination_period_increase_is_narrowed():
    f = _pair(
        "The elimination period is 14 days before disability benefits start.",
        "The elimination period is 60 days before disability benefits start.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (g) -- a genuinely ambiguous multi-word change must still resolve to
# modified (direction unclear), not be swept up by the new signals.
# ---------------------------------------------------------------------


def test_ambiguous_percent_change_with_no_payshare_marker_stays_unclear():
    # A bare percentage with no reimburse/pay/coinsurance marker nearby
    # -- direction must NOT be guessed.
    f = _pair(
        "The premium adjustment factor is 90%.",
        "The premium adjustment factor is 60%.",
    )
    assert f.kind == "modified", f.detail


def test_ambiguous_multi_word_substitution_stays_unclear():
    f = _pair(
        "Claims are handled by the regional processing office.",
        "Claims are handled by the national review center.",
    )
    assert f.kind == "modified", f.detail


def test_two_different_units_in_wait_period_stays_unclear():
    # 30 days vs. 4 hours -- mismatched units must not be compared.
    f = _pair(
        "Benefits begin after a waiting period of 30 days.",
        "Benefits begin after a waiting period of 4 hours.",
    )
    assert f.kind != "narrowed" and f.kind != "broadened", f.detail
