"""Regression tests for an earlier fix (1 WRONG-DIRECTION
class, 3 instances against HEAD
b18140f).

More insured-borne floor / retention phrasings fell through
_RETENTION_FLOOR_RE entirely and hit the generic "untagged amount ->
role=limit" numeric default, confidently inverted (all must be NARROWED
on increase / BROADENED on decrease, never "limit changed"):

  * "We do not cover any loss of less than $X." -- the "under $X"
    spelling of this exact construction was already recognized (round
    20); "less than"/"below" are the same construction, not a new
    category.
  * "Losses of less than $X are not covered." -- the mirror ordering
    (floor phrase BEFORE the "not covered" verdict, instead of after
    it).
  * "The insured shall retain $X of each and every loss." -- a bare VERB
    "retain(s)" tied to the insured, without "the first" (already
    recognized) and without the NOUN "retention" (already routed to the
    deductible role via _ROLE_KEYWORD_RE).

Root fix Part 1 (classify.py): _RETENTION_FLOOR_RE's existing
"we (do|will) not cover ... under" alternative is widened to also accept
"less than"/"below"; its existing "claims under ... not covered"
alternative is widened to accept "loss(es)" as the noun and
"less than"/"below" as the preposition; and a new
"(the) insured (shall) retains?" / "retained by the insured" alternative
is added alongside the existing "insured shall bear/bears/is responsible
for" one.

Root fix Part 2 (classify.py, the DURABLE safety net): rather than only
ever naming one more specific phrasing (the pattern every an earlier revision/20/22/
23/24-Part-1 fix above already followed), _money_roles' blanket "no local
role keyword -> default to 'limit'" fallback is replaced with a
clause-wide check: default to "limit" only when the clause carries a
genuine insurer-limit signal (_LIMIT_SIGNAL_RE: limit/aggregate/"the most
we will pay"/"up to"/maximum/sublimit, OR a carve-back GRANT per round
23's _CARVEBACK_GRANT_RE, OR a bare un-negated "pay" verb) -- exactly the
same "limit" polarity as before for every clause that actually has one.
Otherwise: if the clause carries exclusionary/floor framing
(_EXCLUSIONARY_FRAMING_RE: do/does not cover, not covered, does not
apply, excludes/excluded, less than, under, below, retain(s)/retained,
bear(s), "the first") the amount is read as an insured-borne floor
(higher = narrowed) instead of a confident "limit" -- new "floor" role,
same polarity as "deductible". If NEITHER signal is present at all, the
amount is genuinely unclassifiable and resolves to "modified (direction
unclear)" -- a new "unclear" role -- rather than guessed. This means a
FUTURE floor phrasing not on Part 1's enumerated list degrades to, at
worst, "modified" (or, when it happens to carry recognizable
exclusionary language, the CORRECT "floor" reading directly), never a
confident wrong-direction "limit changed".

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Provision"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# (a) Part 1 -- the 3 live-reproduced defects, increase -> NARROWED.
# ---------------------------------------------------------------------


def test_do_not_cover_less_than_increase_is_narrowed():
    f = _pair(
        "We do not cover any loss of less than $500.",
        "We do not cover any loss of less than $1,000.",
        heading="Small Loss Provision",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_losses_of_less_than_not_covered_mirror_increase_is_narrowed():
    # Same construction, opposite ORDER (the floor phrase comes before
    # the "not covered" verdict rather than after a "do not cover" verb).
    f = _pair(
        "Losses of less than $500 are not covered.",
        "Losses of less than $1,000 are not covered.",
        heading="Small Loss Provision",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_insured_shall_retain_verb_increase_is_narrowed():
    f = _pair(
        "The insured shall retain $1,000 of each and every loss.",
        "The insured shall retain $5,000 of each and every loss.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


# ---------------------------------------------------------------------
# (b) Part 1 -- mirror direction, decrease -> BROADENED.
# ---------------------------------------------------------------------


def test_do_not_cover_less_than_decrease_is_broadened():
    f = _pair(
        "We do not cover any loss of less than $1,000.",
        "We do not cover any loss of less than $500.",
        heading="Small Loss Provision",
    )
    assert f.kind == "broadened", f.detail


def test_losses_of_less_than_not_covered_mirror_decrease_is_broadened():
    # This is the literal shape from the task ("Losses of less than
    # $1,000 are not covered." -> "$500").
    f = _pair(
        "Losses of less than $1,000 are not covered.",
        "Losses of less than $500 are not covered.",
        heading="Small Loss Provision",
    )
    assert f.kind == "broadened", f.detail


def test_insured_shall_retain_verb_decrease_is_broadened():
    f = _pair(
        "The insured shall retain $5,000 of each and every loss.",
        "The insured shall retain $1,000 of each and every loss.",
        heading="Retention",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (c) Part 1 -- the "under $X" spelling (an earlier revision) stays correct after
#     widening the same alternative to "less than"/"below" (never a
#     regression from adding the new spellings).
# ---------------------------------------------------------------------


def test_do_not_cover_under_spelling_still_narrowed():
    f = _pair(
        "We do not cover any claim under $500.",
        "We do not cover any claim under $1,000.",
        heading="Small Loss Provision",
    )
    assert f.kind == "narrowed", f.detail


def test_do_not_cover_below_spelling_increase_is_narrowed():
    f = _pair(
        "We will not cover losses below $500.",
        "We will not cover losses below $1,000.",
        heading="Small Loss Provision",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (d) Part 2 -- DURABLE SAFETY NET. An UNTAGGED amount (no enumerated
#     Part 1 phrasing at all) in exclusionary/floor framing with NO
#     limit word -> a confident NARROWED floor reading, never a
#     confident wrong-direction "broadened"/"limit".
# ---------------------------------------------------------------------


def test_safety_net_untagged_floor_in_exclusionary_framing_is_narrowed():
    # No "deductible"/"retention"/"SIR"/"sublimit"/"limit"/"aggregate"/
    # "pay" word anywhere, and none of Part 1's enumerated phrasings --
    # this is a hypothetical FUTURE phrasing the module has never been
    # taught by name, testing the safety net's own general rule.
    f = _pair(
        "Coverage does not apply if the loss amount is $500 or less.",
        "Coverage does not apply if the loss amount is $1,000 or less.",
        heading="Small Loss Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" not in f.detail.lower()


def test_safety_net_untagged_floor_in_exclusionary_framing_decrease_is_broadened():
    f = _pair(
        "Coverage does not apply if the loss amount is $1,000 or less.",
        "Coverage does not apply if the loss amount is $500 or less.",
        heading="Small Loss Exclusion",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (e) Part 2 -- an amount with a genuine limit word still resolves
#     confidently to the ordinary limit polarity (higher = broadened),
#     completely unaffected by the new safety net.
# ---------------------------------------------------------------------


def test_safety_net_guard_genuine_limit_word_still_broadened():
    f = _pair(
        "The maximum benefit payable is $500.",
        "The maximum benefit payable is $1,000.",
        heading="Coverage",
    )
    assert f.kind == "broadened", f.detail


def test_safety_net_guard_up_to_phrase_decrease_is_narrowed():
    f = _pair(
        "Loss is covered up to $500,000.",
        "Loss is covered up to $250,000.",
        heading="Coverage",
    )
    assert f.kind == "narrowed", f.detail


def test_safety_net_guard_bare_positive_pay_verb_still_broadened():
    # A bare, un-negated "pay" with no exclusionary language anywhere
    # counts as ordinary positive limit-shaped language (this is what
    # keeps the pre-existing an earlier revision "The Company will pay $X for each
    # claim" family, unaffected by Part 2 -- see test_round10_audit_
    # regression.py).
    f = _pair(
        "The Company will pay $1,000,000 for each claim.",
        "The Company will pay $2,000,000 for each claim.",
        heading="Coverage",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (f) Part 2 -- genuinely NO signal at all (no limit word, no
#     exclusionary/floor framing, no "pay" verb) -> "modified (direction
#     unclear)", never a guessed confident direction either way.
# ---------------------------------------------------------------------


def test_safety_net_no_signal_at_all_is_modified_not_guessed():
    f = _pair(
        "The insured must submit a proof of loss for claims totaling $500.",
        "The insured must submit a proof of loss for claims totaling $1,000.",
        heading="Notice",
    )
    assert f.kind == "modified", f.detail


# ---------------------------------------------------------------------
# (g) GUARDS -- must stay correct, completely unaffected by both Part 1
#     and Part 2: the aggregate-limit control, "we will pay up to $X",
#     "aggregate limit $X", an ordinary deductible, the pre-existing
#     NOUN "retention of $X" (never routed through the verb family),
#     "shall bear the first $X" (an earlier revision, unchanged), and the
#     carve-back first-dollar GRANT (an earlier revision defect B, unchanged).
# ---------------------------------------------------------------------


def test_guard_aggregate_limit_control_still_broadened():
    f = _pair(
        "The most we will pay in any policy year is $2,000,000.",
        "The most we will pay in any policy year is $3,000,000.",
        heading="General Aggregate",
    )
    assert f.kind == "broadened", f.detail


def test_guard_we_will_pay_up_to_still_broadened():
    f = _pair(
        "We will pay up to $1,000,000.",
        "We will pay up to $2,000,000.",
        heading="Limit",
    )
    assert f.kind == "broadened", f.detail


def test_guard_aggregate_limit_keyword_still_broadened():
    f = _pair(
        "The aggregate limit is $1,000,000.",
        "The aggregate limit is $2,000,000.",
        heading="Aggregate",
    )
    assert f.kind == "broadened", f.detail


def test_guard_ordinary_deductible_still_narrowed():
    f = _pair(
        "A deductible of $500 applies.",
        "A deductible of $1,000 applies.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail.lower()


def test_guard_noun_retention_of_amount_unaffected_by_verb_family():
    # The NOUN form "retention of $X" must keep resolving via the
    # deductible role (_ROLE_KEYWORD_RE), never the new verb-form
    # _RETENTION_FLOOR_RE alternative (which matches the VERB "retain(s)",
    # not the noun "retention").
    f = _pair(
        "A retention of $1,000 applies to each occurrence.",
        "A retention of $5,000 applies to each occurrence.",
        heading="Retention",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail.lower()


def test_guard_shall_bear_the_first_unchanged():
    f = _pair(
        "The insured shall bear the first $10,000 of each loss.",
        "The insured shall bear the first $25,000 of each loss.",
        heading="Retained Amount",
    )
    assert f.kind == "narrowed", f.detail


def test_guard_carveback_first_dollar_grant_unchanged():
    f = _pair(
        "This exclusion does not apply to the first $50,000 of pollution loss.",
        "This exclusion does not apply to the first $100,000 of pollution loss.",
        heading="Exclusion",
    )
    assert f.kind == "broadened", f.detail


def test_guard_excess_carveback_cap_change_unaffected():
    # An exclusion carve-back's own cap changing (marker present on BOTH
    # sides) must not be swept up by either the widened Part 1 marker or
    # the new Part 2 safety net.
    f = _pair(
        "We do not cover theft, except we will pay up to $50,000 for "
        "employee theft.",
        "We do not cover theft, except we will pay up to $25,000 for "
        "employee theft.",
        heading="Exclusion",
    )
    assert f.kind == "narrowed", f.detail
    assert "retention" not in f.detail.lower()
    assert "amount not covered" not in f.detail.lower()


def test_guard_sublimit_added_still_narrowed():
    old = segment("6. Coverage A. Coverage A applies to jewelry.\n")[0]
    new = segment(
        "6. Coverage A. Coverage A applies to jewelry, sublimit $5,000.\n"
    )[0]
    f = classify_pair(old, new, suppress_cosmetic=True)
    assert f.kind == "narrowed", f.detail
    assert "sublimit" in f.detail
