"""Regression tests for an earlier fix (1 WRONG-DIRECTION
class, 5 instances, specification's worst category, reproduced live by a fresh
reviewer).

Defect A -- insured-borne floors written in PLAIN ENGLISH (no
deductible/retention/SIR keyword) were read as insurer LIMITS and
confidently inverted (the amount an insured bears / that is not covered /
below which coverage does not respond is a retention-like floor: amount
up = NARROWED, never "limit changed" / broadened):

  * "The insured shall bear the first $X of each loss." -> [BROADENED]
    "limit changed" (WRONG -- must be NARROWED).
  * "The first $X of any loss is not covered." -> same wrong
    [BROADENED] "limit changed" reading.
  * "We do not cover any claim under $X." -> same wrong [BROADENED]
    "limit changed" reading.

Root fix (classify.py): _RETENTION_FLOOR_RE gains the plain-English
insured-borne-floor family -- "insured shall bear/bears/is responsible
for (the first) $X", "the first $X ... is not covered", "we do not/will
not cover ... under $X", "no coverage for ... under $X", "claims under
$X are not covered" -- all routed through the SAME
_classify_retention_floor direction logic an earlier revision already built (higher
= narrowed, lower = broadened), never the generic numeric "limit"
default.

Defect B -- a carve-back "first-dollar" GRANT inside an exclusion
("This exclusion does not apply to the first $X of pollution loss.")
was misread as an insured retention by _RETENTION_FLOOR_RE's own
overlapping "does not apply to the first" alternative, and inverted
(higher cap = MORE carved back INTO coverage = BROADENED, but the old
code reported [NARROWED] "retention changed"):

  * "This exclusion does not apply to the first $X of pollution loss."
    -> [NARROWED] "retention changed" (WRONG -- must be BROADENED).

Root fix (classify.py): a new _CARVEBACK_GRANT_RE ("(this/the) exclusion
does not apply to the first $X", "except (for) the first $X", "we will
pay (for) the first $X", "coverage applies to the first $X") is checked
FIRST inside _classify_retention_floor -- a match makes the function bail
out (return None) immediately, before ever consulting
_RETENTION_FLOOR_RE, so the pair falls through the rest of the
_classify_signal chain to _classify_numeric. That default "limit" role
already has the CORRECT carve-back-grant polarity (higher cap =
broadened, lower = narrowed) -- see
test_guard_excess_carveback_cap_change_unaffected in
the matching regression test, which already relies on exactly this
fallthrough for the "except we will pay up to $X" marker-unchanged
shape. No new direction-computing function was needed for defect B --
only keeping the plain-English retention detector out of a carve-back
grant's way.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Retention"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# (a) Defect A -- plain-English insured-borne floor INCREASE -> NARROWED,
#     in each of the 3 phrasings the live defect reproduced, plus the
#     no-"first" and "is responsible for" generalizations.
# ---------------------------------------------------------------------


def test_insured_shall_bear_the_first_increase_is_narrowed():
    f = _pair(
        "The insured shall bear the first $10,000 of each loss.",
        "The insured shall bear the first $25,000 of each loss.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_first_dollars_is_not_covered_increase_is_narrowed():
    f = _pair(
        "The first $5,000 of any loss is not covered.",
        "The first $10,000 of any loss is not covered.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_we_do_not_cover_under_increase_is_narrowed():
    f = _pair(
        "We do not cover any claim under $500.",
        "We do not cover any claim under $1,000.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_insured_bears_no_first_generalization_increase_is_narrowed():
    # "insured bears $X" (no "the first") must also resolve.
    f = _pair(
        "The insured shall bear $10,000.",
        "The insured shall bear $25,000.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_insured_responsible_for_generalization_increase_is_narrowed():
    f = _pair(
        "The insured is responsible for the first $10,000 of each loss.",
        "The insured is responsible for the first $25,000 of each loss.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_no_coverage_for_under_generalization_increase_is_narrowed():
    f = _pair(
        "No coverage for any claim under $500.",
        "No coverage for any claim under $1,000.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_claims_under_not_covered_generalization_increase_is_narrowed():
    f = _pair(
        "Claims under $500 are not covered.",
        "Claims under $1,000 are not covered.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


# ---------------------------------------------------------------------
# (b) Defect A mirrors -- decrease -> BROADENED.
# ---------------------------------------------------------------------


def test_insured_shall_bear_the_first_decrease_is_broadened():
    f = _pair(
        "The insured shall bear the first $25,000 of each loss.",
        "The insured shall bear the first $10,000 of each loss.",
        heading="Retention",
    )
    assert f.kind == "broadened", f.detail


def test_first_dollars_is_not_covered_decrease_is_broadened():
    f = _pair(
        "The first $10,000 of any loss is not covered.",
        "The first $5,000 of any loss is not covered.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail


def test_we_do_not_cover_under_decrease_is_broadened():
    f = _pair(
        "We do not cover any claim under $1,000.",
        "We do not cover any claim under $500.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (c) Defect B -- exclusion carve-back first-dollar GRANT cap INCREASE
#     -> BROADENED, plus generalizations, plus the mirror.
# ---------------------------------------------------------------------


def test_exclusion_carveback_grant_cap_increase_is_broadened():
    f = _pair(
        "This exclusion does not apply to the first $50,000 of pollution loss.",
        "This exclusion does not apply to the first $100,000 of pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail
    assert "retention" not in f.detail.lower()


def test_exclusion_carveback_grant_cap_decrease_is_narrowed_mirror():
    f = _pair(
        "This exclusion does not apply to the first $100,000 of pollution loss.",
        "This exclusion does not apply to the first $50,000 of pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "retention" not in f.detail.lower()


def test_coverage_applies_to_the_first_grant_generalization_is_broadened():
    f = _pair(
        "Coverage applies to the first $50,000 of pollution loss.",
        "Coverage applies to the first $100,000 of pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail
    assert "retention" not in f.detail.lower()


def test_except_for_the_first_grant_generalization_is_broadened():
    f = _pair(
        "Except for the first $50,000, this exclusion applies to pollution loss.",
        "Except for the first $100,000, this exclusion applies to pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail
    assert "retention" not in f.detail.lower()


# ---------------------------------------------------------------------
# (d) GUARDS -- must stay correct: genuine insurer limit, ordinary
#     deductible, keyword retention forms (an earlier revision), and carve-back
#     add/remove (an earlier revision/19) must all be completely unaffected.
# ---------------------------------------------------------------------


def test_guard_genuine_insurer_limit_increase_still_broadened():
    f = _pair(
        "We will pay up to $1,000,000.",
        "We will pay up to $2,000,000.",
        heading="Limit",
    )
    assert f.kind == "broadened", f.detail


def test_guard_ordinary_deductible_increase_still_narrowed():
    f = _pair(
        "A deductible of $500 applies to each occurrence.",
        "A deductible of $1,000 applies to each occurrence.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail.lower()


def test_guard_round20_keyword_retention_phrasing_unchanged():
    f = _pair(
        "The insured shall retain the first $10,000 of each loss.",
        "The insured shall retain the first $25,000 of each loss.",
        heading="Retained Amount",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_guard_round20_does_not_apply_insurance_phrasing_unchanged():
    # "This INSURANCE does not apply..." (no "exclusion" governing word)
    # must still resolve as a plain-English retention -- NARROWED on
    # increase -- exactly as an earlier revision fixed it, unaffected by the new
    # carve-back-grant precedence check (which requires "exclusion", not
    # "insurance", to govern "does not apply to the first").
    f = _pair(
        "This insurance does not apply to the first $10,000 of any loss.",
        "This insurance does not apply to the first $25,000 of any loss.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_guard_round18_carveback_added_still_broadened():
    old = segment("1. Exclusion. This insurance does not apply to loss caused by mold.\n")[0]
    new = segment(
        "1. Exclusion. This insurance does not apply to loss caused by mold, "
        "except that we will pay up to $10,000 for such loss.\n"
    )[0]
    f = classify_pair(old, new, suppress_cosmetic=True)
    assert f.kind == "broadened", f.detail


def test_guard_round20_excess_carveback_cap_change_still_unaffected():
    f = _pair(
        "We do not cover theft, except we will pay up to $50,000 for "
        "employee theft.",
        "We do not cover theft, except we will pay up to $25,000 for "
        "employee theft.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "retention" not in f.detail.lower()
    assert "attachment" not in f.detail.lower()
