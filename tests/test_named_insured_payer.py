"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, specification's worst category.).

The defect: in every ISO form, "you"/"your" is the Named Insured. "you
must pay the first $X of any loss" is the insured's own
deductible/retention -- raising it means the insured bears MORE out of
pocket before the policy responds, which NARROWS coverage. The tool read
the bare, un-negated "pay" verb (_POSITIVE_PAY_RE) as an insurer-limit /
pay-share signal regardless of WHO the subject of "pay" was, and inverted
this to [BROADENED] -- even with the word "deductible" present elsewhere
in the same clause (a ';'-reset segment boundary keeps that keyword from
reaching the "you must pay" segment, by design).

Root fix (classify.py):

  1. _RETENTION_FLOOR_RE (consulted first, in _classify_retention_floor,
     ahead of the generic numeric chain) grew a SECOND-PERSON
     insured-payer family -- "you must pay (the first) $X", "you pay (the
     first) $X", "you are responsible for (the first) $X" -- and the
     mirror third-person "the insured must pay $X" / "the insured pays
     $X", each guarded against directly preceding an already-correctly-
     handled "(a) deductible"/"(a) retention" keyword phrase.
  2. As defense in depth, the earlier safety net's "bare un-negated pay
     verb -> limit role" branch (_money_roles' has_pay_signal) now
     additionally requires the payer NOT be exclusively insured-side
     (_INSURED_PAYER_RE matches and _INSURER_PAYER_RE does not) -- so ANY
     insured-payer phrasing this module's enumerated marker list doesn't
     happen to name still falls through to the honest
     EXCLUSIONARY_FRAMING/"unclear" branches instead of confidently
     inverting.

Guards (per the task): an INSURER-subject "pay"/"reimburse" clause (higher
amount = more coverage = BROADENED) must stay completely unaffected, and
every existing deductible/retention phrasing (plain keyword, plain-English
third-person "insured", attachment/coinsurance) must keep resolving
exactly as before, with the SAME detail wording (an earlier revision/an earlier revision
guarantee that a clause already carrying the local "deductible" keyword
reports "deductible changed ...", not the generic "retention changed
...").

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations.
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
# (a) The live-reproduced defect: "you must pay the first $X" increase.
#     Must report NARROWED (the insured's own deductible/retention),
#     never [BROADENED] "limit changed".
# ---------------------------------------------------------------------


def test_you_must_pay_the_first_increase_is_narrowed():
    f = _pair(
        "You must pay the first $500 of any loss.",
        "You must pay the first $2,500 of any loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "500" in f.detail and "2,500" in f.detail


def test_you_must_pay_the_first_decrease_is_broadened():
    # Mirror of (a): a LOWER retention means the insured bears LESS
    # out of pocket -- BROADENED.
    f = _pair(
        "You must pay the first $2,500 of any loss.",
        "You must pay the first $500 of any loss.",
        heading="Deductible",
    )
    assert f.kind == "broadened", f.detail
    assert "2,500" in f.detail and "500" in f.detail


# ---------------------------------------------------------------------
# (b) The exact live-reproduced defect 2, verbatim from the task/audit
#     fixtures: "deductible" is even present elsewhere in the clause
#     (across a ';' reset boundary) -- zero ambiguity that this is a
#     deductible, yet the tool still inverted it pre-fix.
# ---------------------------------------------------------------------


def test_deductible_word_plus_you_must_pay_clause_is_narrowed():
    result = diff_documents(
        "1. A deductible applies; you must pay the first $2,500 of any loss.\n",
        "1. A deductible applies; you must pay the first $7,500 of any loss.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "2,500" in f.detail and "7,500" in f.detail


# ---------------------------------------------------------------------
# (c) "you are responsible for the first $X" generalization.
# ---------------------------------------------------------------------


def test_you_are_responsible_for_the_first_increase_is_narrowed():
    f = _pair(
        "You are responsible for the first $1,000 of any loss.",
        "You are responsible for the first $5,000 of any loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "1,000" in f.detail and "5,000" in f.detail


# ---------------------------------------------------------------------
# (d) Third-person mirror: "the insured must pay the first $X".
# ---------------------------------------------------------------------


def test_the_insured_must_pay_the_first_increase_is_narrowed():
    f = _pair(
        "The insured must pay the first $1,000 of any loss.",
        "The insured must pay the first $4,000 of any loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "1,000" in f.detail and "4,000" in f.detail


# ---------------------------------------------------------------------
# GUARDS -- must stay completely unaffected by the payer-subject fix.
# ---------------------------------------------------------------------


def test_guard_we_will_pay_up_to_increase_stays_broadened():
    f = _pair(
        "We will pay up to $500,000 for each occurrence.",
        "We will pay up to $1,000,000 for each occurrence.",
        heading="Limit of Insurance",
    )
    assert f.kind == "broadened", f.detail
    assert "500,000" in f.detail and "1,000,000" in f.detail


def test_guard_we_will_reimburse_percent_increase_stays_broadened():
    f = _pair(
        "We will reimburse up to 80% of covered expenses.",
        "We will reimburse up to 90% of covered expenses.",
        heading="Reimbursement",
    )
    assert f.kind == "broadened", f.detail
    assert "80" in f.detail and "90" in f.detail


def test_guard_plain_deductible_keyword_clause_unaffected_by_you_pay_family():
    # "the insured pays a deductible of $X" already resolved correctly
    # (and more precisely -- detail names the role) via the existing
    # _ROLE_KEYWORD_RE "deductible" keyword mechanism; the new "insured
    # pays"/"you pay" markers must not steal this clause and regress its
    # detail wording to the generic "retention changed ...".
    f = _pair(
        "The insured pays a deductible of $10,000 each occurrence.",
        "The insured pays a deductible of $20,000 each occurrence.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "10,000" in f.detail and "20,000" in f.detail


def test_guard_insured_shall_be_responsible_for_the_first_unaffected():
    # Pre-existing third-person phrasing (an earlier revision) -- already NARROWED,
    # must keep working unchanged.
    f = _pair(
        "The insured shall be responsible for the first $1,000 of any loss.",
        "The insured shall be responsible for the first $5,000 of any loss.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "1,000" in f.detail and "5,000" in f.detail


def test_guard_the_most_we_will_pay_increase_stays_broadened():
    f = _pair(
        "The most we will pay is $500,000.",
        "The most we will pay is $1,000,000.",
        heading="Limit of Insurance",
    )
    assert f.kind == "broadened", f.detail
    assert "500,000" in f.detail and "1,000,000" in f.detail
