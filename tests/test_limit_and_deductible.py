"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, specification's worst category, a REGRESSION from an earlier revision's own
floor-over-limit precedence fix
).

The defect: a clause naming BOTH a limit and a deductible, with no
','/';' separating the two amount-bearing phrases at all --

    "The Limit of Insurance is $2,000,000 subject to a deductible of
    $10,000."

-- puts both amounts in a single _segment_spans segment (no comma or
semicolon separates "...Insurance is $2,000,000" from "...deductible of
$10,000"). an earlier revision's floor-over-limit precedence discarded every
"limit"/"aggregate" candidate for the WHOLE segment whenever a
deductible/retention/SIR keyword appeared anywhere in it -- so when only
the Limit changed ($2,000,000 -> $1,000,000, a narrowing), the tool
still reported "[BROADENED] deductible changed from $2,000,000 to
$1,000,000": wrong direction (broadened instead of narrowed) AND a
mislabeled field (the $2,000,000/$1,000,000 figures were never the
deductible; the deductible is the unchanged $10,000).

Root cause: an earlier revision's precedence was applied segment-wide, not
per-amount-local.

Root fix (classify.py, _amount_role): when a segment holds more than one
amount, candidacy for a given amount is first narrowed to the role
keyword(s) LOCAL to it -- a keyword is local to an amount when that
amount is the nearest of the segment's amounts to it. Only among an
amount's own local keywords does an earlier revision's floor-over-limit precedence
get consulted. For every an earlier revision fixture (single amount per segment)
this is a no-op: the one amount is trivially the nearest amount to every
keyword in the segment, so floor-over-limit still applies exactly as
an earlier revision left it. A single role keyword anywhere in the segment still
governs every amount in it regardless of amount count (an earlier revision's
propagation contract, unaffected).

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
the task's FORBIDDEN clause) -- they are original clauses authored from
the task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair, classify_pair_multi
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Provision"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


def _pair_multi(old_text: str, new_text: str, heading: str = "Provision"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair_multi(old, new, suppress_cosmetic=True)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) The live-reproduced defect: limit decreases, deductible unchanged.
#     Must report NARROWED "limit changed", deductible silent.
# ---------------------------------------------------------------------


def test_limit_decrease_with_unchanged_deductible_in_same_clause_is_narrowed_limit():
    f = _pair(
        "The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.",
        "The Limit of Insurance is $1,000,000 subject to a deductible of $10,000.",
        heading="Limits",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "2,000,000" in f.detail and "1,000,000" in f.detail


# ---------------------------------------------------------------------
# (b) Mirror -- limit increase, deductible unchanged -> BROADENED limit.
# ---------------------------------------------------------------------


def test_limit_increase_with_unchanged_deductible_in_same_clause_is_broadened_limit():
    f = _pair(
        "The Limit of Insurance is $1,000,000 subject to a deductible of $10,000.",
        "The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.",
        heading="Limits",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


# ---------------------------------------------------------------------
# (c) Same clause, deductible-only change: limit unchanged -> NARROWED
#     deductible, limit silent (this direction already worked, but must
#     keep working under the per-amount-local fix).
# ---------------------------------------------------------------------


def test_deductible_increase_with_unchanged_limit_in_same_clause_is_narrowed_deductible():
    f = _pair(
        "The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.",
        "The Limit of Insurance is $2,000,000 subject to a deductible of $25,000.",
        heading="Limits",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "10,000" in f.detail and "25,000" in f.detail


def test_deductible_decrease_with_unchanged_limit_in_same_clause_is_broadened_deductible():
    f = _pair(
        "The Limit of Insurance is $2,000,000 subject to a deductible of $25,000.",
        "The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.",
        heading="Limits",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


# ---------------------------------------------------------------------
# (d) Both change in the same clause -> TWO findings, each directioned
#     by its own role (an earlier revision multi-amount contract, restored here).
# ---------------------------------------------------------------------


def test_both_limit_and_deductible_change_in_same_clause_produce_two_findings():
    findings = _pair_multi(
        "The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.",
        "The Limit of Insurance is $1,000,000 subject to a deductible of $25,000.",
        heading="Limits",
    )
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["narrowed", "narrowed"], [(f.kind, f.detail) for f in findings]
    limit_finding = [f for f in findings if "limit" in f.detail][0]
    deductible_finding = [f for f in findings if "deductible" in f.detail][0]
    assert limit_finding.kind == "narrowed"
    assert "2,000,000" in limit_finding.detail and "1,000,000" in limit_finding.detail
    assert deductible_finding.kind == "narrowed"
    assert "10,000" in deductible_finding.detail and "25,000" in deductible_finding.detail


def test_limit_down_deductible_down_produces_narrowed_and_broadened():
    findings = _pair_multi(
        "The Limit of Insurance is $2,000,000 subject to a deductible of $25,000.",
        "The Limit of Insurance is $1,000,000 subject to a deductible of $10,000.",
        heading="Limits",
    )
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in findings]
    limit_finding = [f for f in findings if "limit" in f.detail][0]
    deductible_finding = [f for f in findings if "deductible" in f.detail][0]
    assert limit_finding.kind == "narrowed"
    assert deductible_finding.kind == "broadened"


# ---------------------------------------------------------------------
# (e) Other declarations-page phrasings naming both a limit word and a
#     deductible in one un-punctuated clause -- must direction the limit
#     correctly.
# ---------------------------------------------------------------------


def test_general_aggregate_limit_with_deductible_clause_directions_limit():
    f = _pair(
        "General Aggregate Limit $1,000,000 subject to a deductible of $5,000.",
        "General Aggregate Limit $2,000,000 subject to a deductible of $5,000.",
        heading="General Aggregate",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


def test_each_occurrence_limit_with_deductible_clause_directions_limit():
    f = _pair(
        "Each Occurrence Limit $500,000 subject to a deductible of $1,000.",
        "Each Occurrence Limit $250,000 subject to a deductible of $1,000.",
        heading="Each Occurrence",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


# ---------------------------------------------------------------------
# (f) GUARDS -- an earlier revision's own single-amount compound-noun fixtures must
#     stay exactly as an earlier revision left them: floor-over-limit precedence
#     is a no-op change here since each segment holds only ONE amount.
# ---------------------------------------------------------------------


def test_guard_self_insured_retention_limit_single_amount_still_narrowed():
    f = _pair(
        "The self-insured retention limit borne by the insured is $50,000 per claim.",
        "The self-insured retention limit borne by the insured is $100,000 per claim.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


def test_guard_aggregate_deductible_limit_single_amount_still_narrowed():
    f = _pair(
        "An aggregate deductible limit of $25,000 applies before coverage responds.",
        "An aggregate deductible limit of $60,000 applies before coverage responds.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


def test_guard_per_occurrence_deductible_limit_single_amount_still_narrowed():
    f = _pair(
        "A per-occurrence deductible limit of $10,000 applies to each covered loss.",
        "A per-occurrence deductible limit of $30,000 applies to each covered loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


# ---------------------------------------------------------------------
# (g) GUARDS -- plain single-amount clauses, no co-occurring floor/limit
#     keyword pair at all, are completely unaffected.
# ---------------------------------------------------------------------


def test_guard_plain_general_aggregate_limit_no_deductible_still_broadened():
    f = _pair(
        "General Aggregate Limit $1,000,000.",
        "General Aggregate Limit $2,000,000.",
        heading="General Aggregate",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail


def test_guard_plain_deductible_no_limit_still_narrowed():
    f = _pair(
        "Deductible is $500.",
        "Deductible is $1,000.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail


# ---------------------------------------------------------------------
# (h) GUARD -- an earlier revision's single-keyword-governs-multiple-amounts
#     propagation within one segment (no role choice to make at all)
#     must be completely unaffected by the per-amount-local narrowing.
# ---------------------------------------------------------------------


def test_guard_single_deductible_keyword_still_governs_both_amounts_in_segment():
    f = _pair(
        "The deductible is $500 for property and $800 for liability.",
        "The deductible is $500 for property and $1,000 for liability.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail


# ---------------------------------------------------------------------
# (i) End-to-end through diff_documents, matching how the CLI actually
#     surfaces findings for the literal live-reproduced scenario.
# ---------------------------------------------------------------------


def test_full_document_diff_limit_subject_to_deductible_reports_narrowed_limit_not_broadened_deductible():
    result = diff_documents(
        "6. The Limit of Insurance is $2,000,000 subject to a deductible of $10,000.\n",
        "6. The Limit of Insurance is $1,000,000 subject to a deductible of $10,000.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed"
    assert "limit" in f.detail
    assert "deductible" not in f.detail
