"""Regression tests for an earlier fix (3 WRONG-DIRECTION
defects sharing one root, specification's worst class, reproduced live by a fresh
reviewer).

Defect (wrong-direction, one shared root): an amount that is a FLOOR the
INSURED bears/retains before coverage applies -- a first-dollar
retention, an excess-of-loss attachment point, or a coinsurance
insurance-to-value REQUIREMENT -- was not recognized by any role keyword
_ROLE_KEYWORD_RE looks for (that regex only matches the bare words
"deductible"/"retention"/"SIR"/"limit"/"aggregate"/"sublimit"), so the
amount fell through to _money_roles' unresolved-amount default of
"limit", whose polarity ("higher = more coverage = broadened") is exactly
backwards for these three framings. Reproduced live:

  r1: "This insurance does not apply to the first $10,000 of any loss."
      -> "...$25,000..." -> [BROADENED] "limit changed from $10,000 to
      $25,000" (WRONG -- the insured now bears MORE before coverage
      responds; must be NARROWED).
  r2: "The insured shall retain the first $10,000 of each loss." ->
      "...$25,000..." -> same wrong [BROADENED] "limit changed" reading.
  r3: "We will not pay for the portion of any loss below $10,000." ->
      "...$25,000..." -> same wrong [BROADENED] "limit changed" reading.
  att: "This policy attaches in excess of $500,000 of underlying
      limits." -> "...$1,000,000..." -> [BROADENED] "limit changed"
      (WRONG -- a higher attachment point means the policy sits higher
      and responds to LESS; must be NARROWED).
  co: "An 80% coinsurance clause applies to this coverage." -> "A 90%
      coinsurance clause applies..." -> [BROADENED] "reimbursement
      percentage changed from 80% to 90%" (WRONG TWICE -- a higher
      required coinsurance percentage is a STRICTER insurance-to-value
      condition on the insured, must be NARROWED; and it is mislabeled
      "reimbursement", a pay-share concept this clause has nothing to do
      with).

Root fix (classify.py): three new phrase-triggered classifiers --
_classify_retention_floor, _classify_attachment, _classify_coinsurance --
each engage ONLY when their own phrase marker is present (so an unrelated
clause is completely unaffected), and run in _classify_signal AFTER the
existing exclusion carve-back-marker-added/removed check (an earlier revision, which
must keep first refusal on any marker-added/removed shape) but BEFORE
_classify_numeric / _classify_reimburse_percent -- so the amount inside
one of these three framings never reaches the generic "untagged amount ->
role=limit" default. The pre-existing bare-keyword "retention"/"SIR" ->
deductible-role path (an earlier revision) is left completely untouched (these new
phrasings -- "retain THE FIRST $X", "does not apply to THE FIRST $X",
"retained amount", "will not pay for the portion ... below $X" -- are all
patterns _ROLE_KEYWORD_RE never matched in the first place). A bare "N%
coinsurance" WITHOUT "clause"/"requirement" attached is deliberately left
to the ORIGINAL pay-share reading (an earlier revision's health-insurance-style
"subject to N% coinsurance for X care" -- see the coinsurance-domain-
ambiguity guard tests below) -- only "coinsurance clause"/"coinsurance
requirement" phrasing is treated as the insurance-to-value requirement
with the inverted (higher = narrowed) polarity.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures (off-limits
per the task's FORBIDDEN clause) -- they are original clauses authored
from the task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Retention"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# (a) first-dollar retention floor INCREASE -> NARROWED, in each of the
#     3 phrasings the live defect reproduced.
# ---------------------------------------------------------------------


def test_retention_floor_does_not_apply_phrasing_increase_is_narrowed():
    f = _pair(
        "This insurance does not apply to the first $10,000 of any loss.",
        "This insurance does not apply to the first $25,000 of any loss.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_retention_floor_shall_retain_phrasing_increase_is_narrowed():
    f = _pair(
        "The insured shall retain the first $10,000 of each loss.",
        "The insured shall retain the first $25,000 of each loss.",
        heading="Retained Amount",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_retention_floor_will_not_pay_portion_phrasing_increase_is_narrowed():
    f = _pair(
        "We will not pay for the portion of any loss below $10,000.",
        "We will not pay for the portion of any loss below $25,000.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


# ---------------------------------------------------------------------
# (b) excess attachment point INCREASE -> NARROWED.
# ---------------------------------------------------------------------


def test_attachment_point_increase_is_narrowed():
    f = _pair(
        "This policy attaches in excess of $500,000 of underlying limits.",
        "This policy attaches in excess of $1,000,000 of underlying limits.",
        heading="Excess",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()
    assert "limit changed" not in f.detail.lower()


# ---------------------------------------------------------------------
# (c) coinsurance REQUIREMENT percentage INCREASE -> NARROWED, and the
#     detail must NOT say "reimbursement" (mislabel from the defect).
# ---------------------------------------------------------------------


def test_coinsurance_requirement_increase_is_narrowed():
    f = _pair(
        "An 80% coinsurance clause applies to this coverage.",
        "A 90% coinsurance clause applies to this coverage.",
        heading="Coinsurance",
    )
    assert f.kind == "narrowed", f.detail
    assert "reimbursement" not in f.detail.lower()
    assert "coinsurance" in f.detail.lower()


# ---------------------------------------------------------------------
# (d) mirrors: retention/attachment/coinsurance DECREASE -> BROADENED.
# ---------------------------------------------------------------------


def test_retention_floor_decrease_is_broadened():
    f = _pair(
        "This insurance does not apply to the first $25,000 of any loss.",
        "This insurance does not apply to the first $10,000 of any loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail


def test_retained_amount_decrease_is_broadened():
    f = _pair(
        "The insured shall retain the first $25,000 of each loss.",
        "The insured shall retain the first $10,000 of each loss.",
        heading="Retained Amount",
    )
    assert f.kind == "broadened", f.detail


def test_attachment_point_decrease_is_broadened():
    f = _pair(
        "This policy attaches in excess of $1,000,000 of underlying limits.",
        "This policy attaches in excess of $500,000 of underlying limits.",
        heading="Excess",
    )
    assert f.kind == "broadened", f.detail


def test_coinsurance_requirement_decrease_is_broadened():
    f = _pair(
        "A 90% coinsurance clause applies to this coverage.",
        "An 80% coinsurance clause applies to this coverage.",
        heading="Coinsurance",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (e) GUARDS (must stay correct): the new categories must never leak into
#     genuine limit/deductible/pay-share clauses, and the pre-existing
#     bare-"retention"-keyword path (an earlier revision) must be untouched.
# ---------------------------------------------------------------------


def test_guard_genuine_limit_increase_still_broadened():
    f = _pair(
        "The aggregate limit is $1,000,000.",
        "The aggregate limit is $2,000,000.",
        heading="Aggregate",
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


def test_guard_sublimit_added_still_narrowed():
    old = segment("6. Coverage A. Coverage A applies to jewelry.\n")[0]
    new = segment(
        "6. Coverage A. Coverage A applies to jewelry, sublimit $5,000.\n"
    )[0]
    f = classify_pair(old, new, suppress_cosmetic=True)
    assert f.kind == "narrowed", f.detail
    assert "sublimit" in f.detail


def test_guard_payshare_reimburse_increase_still_broadened():
    f = _pair(
        "We will reimburse up to 80% of covered repair costs.",
        "We will reimburse up to 90% of covered repair costs.",
        heading="Reimbursement",
    )
    assert f.kind == "broadened", f.detail
    assert "reimbursement" in f.detail.lower()


def test_guard_bare_self_insured_retention_still_uses_deductible_role():
    # an earlier fix: bare "self-insured retention" keyword text must
    # keep resolving via the deductible role (not the new retention-floor
    # detail wording) -- see the matching regression test's own
    # assertion on this exact phrasing.
    f = _pair(
        "A self-insured retention of $10,000 applies.",
        "A self-insured retention of $25,000 applies.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail.lower()


def test_guard_health_style_bare_coinsurance_percentage_stays_payshare():
    # an earlier fix: a BARE "N% coinsurance" with no "clause"/
    # "requirement" word attached is health-insurance pay-share framing,
    # NOT an insurance-to-value requirement -- opposite polarity from the
    # new coinsurance-requirement category, and must be unaffected by it.
    f = _pair(
        "Benefits are subject to 80% coinsurance for out-of-network care.",
        "Benefits are subject to 50% coinsurance for out-of-network care.",
        heading="Coinsurance",
    )
    assert f.kind == "narrowed", f.detail


def test_guard_excess_carveback_cap_change_unaffected():
    # An exclusion carve-back's own cap changing (marker present on BOTH
    # sides, e.g. "except we will pay up to $X") is a DIFFERENT category
    # (an earlier revision) and must not be swept up by the new retention-floor
    # phrase match -- "will pay up to" is not "will not pay for the
    # portion", so _classify_retention_floor never engages here.
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


def test_guard_ambiguous_bare_percentage_with_no_marker_stays_unclear():
    f = _pair(
        "The premium adjustment factor is 90%.",
        "The premium adjustment factor is 60%.",
        heading="Premium",
    )
    assert f.kind == "modified", f.detail
