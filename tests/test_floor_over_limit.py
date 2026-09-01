"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, 3 phrasings, specification's worst category, reproduced live by a fresh
reviewer).

The defect: a floor/retention clause that ALSO contains the bare word
"limit" was misread as an insurer limit and inverted. All three live
reproductions report [BROADENED] "limit changed" on an amount increase,
when every one of them must be NARROWED (the insured bears more):

  * "The self-insured retention limit borne by the insured is $50,000
    per claim." -> $100,000
  * "An aggregate deductible limit of $25,000 applies before coverage
    responds." -> $60,000
  * "A per-occurrence deductible limit of $10,000 applies to each
    covered loss." -> $30,000

Root cause: _amount_role's nearest-distance tiebreak, run whenever a
segment has MORE THAN ONE role-keyword candidate, doesn't distinguish a
floor-role keyword (deductible/retention/SIR) from a co-occurring
generic "limit"/"aggregate" keyword -- it just picks whichever candidate
sits textually closer to the dollar figure. In every one of these
phrasings, "limit"/"aggregate" sits immediately next to (or right
before) the amount, while the floor word (retention/deductible) comes
earlier in the same compound noun phrase -- so "limit" always won the
tiebreak, even though it is merely naming the floor amount's MAGNITUDE
("the retention's limit is $X"), not making the amount an insurer limit.

Root fix (classify.py, _amount_role): a floor-role keyword
(deductible/retention/SIR) found in a segment now takes PRECEDENCE over
any co-occurring generic "limit"/"aggregate" candidate for every amount
in that segment -- checked, and resolved, BEFORE the nearest-distance
tiebreak ever runs. A parallel fix (_FLOOR_ROLE_CLAUSE_RE) extends the
same precedence to the earlier safety net's clause-WIDE fallback, for
the three floor-role PHRASES ("borne by the insured", "retained by the
insured", "applies before coverage responds") that carry no
_ROLE_KEYWORD_RE recognition of their own.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
the task's FORBIDDEN clause) -- they are original clauses authored from
the task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Provision"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) The 3 live-reproduced defects, increase -> NARROWED, detail names
#     the floor role (deductible/retention), never "limit".
# ---------------------------------------------------------------------


def test_self_insured_retention_limit_borne_by_insured_increase_is_narrowed():
    f = _pair(
        "The self-insured retention limit borne by the insured is $50,000 per claim.",
        "The self-insured retention limit borne by the insured is $100,000 per claim.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "50,000" in f.detail and "100,000" in f.detail


def test_aggregate_deductible_limit_increase_is_narrowed():
    f = _pair(
        "An aggregate deductible limit of $25,000 applies before coverage responds.",
        "An aggregate deductible limit of $60,000 applies before coverage responds.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "25,000" in f.detail and "60,000" in f.detail


def test_per_occurrence_deductible_limit_increase_is_narrowed():
    f = _pair(
        "A per-occurrence deductible limit of $10,000 applies to each covered loss.",
        "A per-occurrence deductible limit of $30,000 applies to each covered loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "10,000" in f.detail and "30,000" in f.detail


# ---------------------------------------------------------------------
# (b) Mirrors -- amount decrease -> BROADENED for all three.
# ---------------------------------------------------------------------


def test_self_insured_retention_limit_borne_by_insured_decrease_is_broadened():
    f = _pair(
        "The self-insured retention limit borne by the insured is $100,000 per claim.",
        "The self-insured retention limit borne by the insured is $50,000 per claim.",
        heading="Retention",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail


def test_aggregate_deductible_limit_decrease_is_broadened():
    f = _pair(
        "An aggregate deductible limit of $60,000 applies before coverage responds.",
        "An aggregate deductible limit of $25,000 applies before coverage responds.",
        heading="Deductible",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail


def test_per_occurrence_deductible_limit_decrease_is_broadened():
    f = _pair(
        "A per-occurrence deductible limit of $30,000 applies to each covered loss.",
        "A per-occurrence deductible limit of $10,000 applies to each covered loss.",
        heading="Deductible",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail


# ---------------------------------------------------------------------
# (c) A bare "borne by the insured" amount (no deductible/retention/SIR
#     keyword at all) increase -> NARROWED via the clause-wide safety net.
# ---------------------------------------------------------------------


def test_borne_by_the_insured_no_keyword_increase_is_narrowed():
    # The amount's OWN sentence has no local role keyword at all (the
    # "limit" word sits in a SEPARATE sentence, past a real
    # sentence-boundary reset) -- this exercises the earlier/25
    # clause-wide safety net directly: _FLOOR_ROLE_CLAUSE_RE's "borne by
    # the insured" phrase must suppress the clause-wide _LIMIT_SIGNAL_RE
    # branch so the untagged amount reads as a floor, not a limit.
    f = _pair(
        "The amount borne by the insured is $500. Coverage otherwise applies up to the maximum benefit.",
        "The amount borne by the insured is $1,000. Coverage otherwise applies up to the maximum benefit.",
        heading="Cost Sharing",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_borne_by_the_insured_no_keyword_decrease_is_broadened():
    f = _pair(
        "The amount borne by the insured is $1,000. Coverage otherwise applies up to the maximum benefit.",
        "The amount borne by the insured is $500. Coverage otherwise applies up to the maximum benefit.",
        heading="Cost Sharing",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (d) GUARDS -- ordinary insurer-limit clauses (no floor-role keyword at
#     all) must stay confidently BROADENED on increase, completely
#     unaffected by the earlier precedence change.
# ---------------------------------------------------------------------


def test_guard_general_aggregate_limit_no_floor_word_still_broadened():
    f = _pair(
        "General Aggregate Limit $1,000,000.",
        "General Aggregate Limit $2,000,000.",
        heading="General Aggregate",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


def test_guard_we_will_pay_up_to_still_broadened():
    f = _pair(
        "We will pay up to $1,000,000.",
        "We will pay up to $2,000,000.",
        heading="Limit",
    )
    assert f.kind == "broadened", f.detail


def test_guard_the_most_we_will_pay_still_broadened():
    f = _pair(
        "The most we will pay is $2,000,000.",
        "The most we will pay is $3,000,000.",
        heading="Aggregate",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (e) GUARDS -- plain deductible/retention/SIR/attachment (rounds 11/20)
#     and retention floors (rounds 23/24) unchanged.
# ---------------------------------------------------------------------


def test_guard_plain_deductible_each_occurrence_unaffected():
    f = _pair(
        "The insured pays a deductible of $10,000 each occurrence.",
        "The insured pays a deductible of $20,000 each occurrence.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


def test_guard_attachment_point_unaffected():
    f = _pair(
        "The policy attaches in excess of $1,000,000.",
        "The policy attaches in excess of $2,000,000.",
        heading="Attachment",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail


def test_guard_shall_bear_the_first_unaffected():
    f = _pair(
        "The insured shall bear the first $10,000 of each loss.",
        "The insured shall bear the first $25,000 of each loss.",
        heading="Retained Amount",
    )
    assert f.kind == "narrowed", f.detail


def test_guard_carveback_grant_unaffected():
    f = _pair(
        "This exclusion does not apply to the first $50,000 of pollution loss.",
        "This exclusion does not apply to the first $100,000 of pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (f) GUARD -- a deductible word in one semicolon-separated segment must
#     never leak its floor role across the reset boundary into an
#     unrelated pay/limit amount in the same clause (an earlier revision's own
#     control, re-asserted here against the earlier clause-wide
#     _FLOOR_ROLE_CLAUSE_RE change specifically).
# ---------------------------------------------------------------------


def test_guard_deductible_does_not_leak_across_semicolon_to_pay_amount():
    f = _pair(
        "A deductible of $500 applies; the Company will pay $1,000,000 for each claim.",
        "A deductible of $500 applies; the Company will pay $2,000,000 for each claim.",
        heading="Coverage",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


# ---------------------------------------------------------------------
# (g) End-to-end through diff_documents, matching how the CLI actually
#     surfaces findings for the literal live-reproduced srl scenario.
# ---------------------------------------------------------------------


def test_full_document_diff_srl_reports_narrowed_deductible_not_broadened_limit():
    result = diff_documents(
        "6. The self-insured retention limit borne by the insured is $50,000 per claim.\n",
        "6. The self-insured retention limit borne by the insured is $100,000 per claim.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed"
    assert "deductible" in f.detail
    assert "limit" not in f.detail
