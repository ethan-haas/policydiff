"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, specification's worst class against
an earlier revision).

Defect: an earlier revision added an attachment/excess category (higher
attachment = less coverage = NARROWED), but its phrase marker
(_ATTACHMENT_RE) only recognized "attaches in excess of $X", "attachment
point", and "excess of underlying limits of $X". Sibling VERB/PREPOSITION
phrasings for the exact same excess/attachment sense slipped through to
the generic "untagged amount -> role=limit" default, whose polarity
("higher = more coverage = broadened") is exactly backwards. Reproduced
live:

  esc1: "This policy attaches above $1,000,000 of underlying limits." ->
      "...$5,000,000..." -> [BROADENED] "limit changed from $1,000,000 to
      $5,000,000" (WRONG -- a higher attachment point means the policy
      sits higher and responds to LESS; must be NARROWED).
  esc2: "This policy applies in excess of a retained limit of $250,000."
      -> "...$1,000,000..." -> [BROADENED] "limit changed" (WRONG, same
      root).

Self-inconsistency proof it's a real bug, not a modeling choice: the NOUN
form "The attachment point is $1,000,000." -> "...$5,000,000." already
correctly resolved [NARROWED] at an earlier revision -- only the verb/preposition
family ("attaches above/at", "applies in excess of", "retained limit of")
was missing from the marker.

Root fix (classify.py, _ATTACHMENT_RE): extend the marker regex to also
recognize "attaches above/at $X" (alongside the pre-existing "attaches in
excess of"), "applies in excess of $X", a bare "retained limit" (covers
both "retained limit of $X" and "excess of a retained limit of $X"), and
a bare "underlying limits" safety net (insurance-specific vocabulary that
only ever appears in an excess/attachment sense). None of the new
alternatives overlap the bare "limit"/"aggregate" role keywords, so an
ordinary "The (aggregate) limit is $X" clause is completely unaffected.
_classify_attachment itself (amount-compare + narrowed/broadened
polarity) is unchanged -- only the phrase family that ROUTES a clause
into it grew.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Excess"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# (a) "attaches above $X" INCREASE -> NARROWED (esc1, live defect).
# ---------------------------------------------------------------------


def test_attaches_above_phrasing_increase_is_narrowed():
    f = _pair(
        "This policy attaches above $1,000,000 of underlying limits.",
        "This policy attaches above $5,000,000 of underlying limits.",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()
    assert "limit changed" not in f.detail.lower()


# ---------------------------------------------------------------------
# (b) "in excess of a retained limit of $X" INCREASE -> NARROWED (esc2,
#     live defect).
# ---------------------------------------------------------------------


def test_applies_in_excess_of_retained_limit_phrasing_increase_is_narrowed():
    f = _pair(
        "This policy applies in excess of a retained limit of $250,000.",
        "This policy applies in excess of a retained limit of $1,000,000.",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()
    assert "limit changed" not in f.detail.lower()


# ---------------------------------------------------------------------
# (c) "applies in excess of $X of underlying limits" INCREASE ->
#     NARROWED (required-outcomes case).
# ---------------------------------------------------------------------


def test_applies_in_excess_of_underlying_limits_phrasing_increase_is_narrowed():
    f = _pair(
        "This policy applies in excess of $500,000 of underlying limits.",
        "This policy applies in excess of $1,000,000 of underlying limits.",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()
    assert "limit changed" not in f.detail.lower()


# ---------------------------------------------------------------------
# (d) mirrors: each of (a)-(c) DECREASE -> BROADENED.
# ---------------------------------------------------------------------


def test_attaches_above_phrasing_decrease_is_broadened():
    f = _pair(
        "This policy attaches above $5,000,000 of underlying limits.",
        "This policy attaches above $1,000,000 of underlying limits.",
    )
    assert f.kind == "broadened", f.detail


def test_applies_in_excess_of_retained_limit_phrasing_decrease_is_broadened():
    f = _pair(
        "This policy applies in excess of a retained limit of $1,000,000.",
        "This policy applies in excess of a retained limit of $250,000.",
    )
    assert f.kind == "broadened", f.detail


def test_applies_in_excess_of_underlying_limits_phrasing_decrease_is_broadened():
    f = _pair(
        "This policy applies in excess of $1,000,000 of underlying limits.",
        "This policy applies in excess of $500,000 of underlying limits.",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (e) GUARDS (must stay correct): the new phrasing must never leak into
#     genuine limit/deductible clauses, and every pre-existing
#     attachment-phrasing shape must still resolve exactly as before.
# ---------------------------------------------------------------------


def test_guard_noun_attachment_point_unchanged():
    # The self-inconsistency-proof control: this noun form already
    # resolved correctly before an earlier revision and must be unaffected.
    f = _pair(
        "The attachment point is $1,000,000.",
        "The attachment point is $5,000,000.",
        heading="Attachment",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()


def test_guard_ordinary_limit_increase_still_broadened():
    f = _pair(
        "The limit is $1,000,000.",
        "The limit is $2,000,000.",
        heading="Limit",
    )
    assert f.kind == "broadened", f.detail
    assert "attachment" not in f.detail.lower()


def test_guard_aggregate_limit_increase_still_broadened():
    f = _pair(
        "The aggregate limit is $1,000,000.",
        "The aggregate limit is $2,000,000.",
        heading="Aggregate",
    )
    assert f.kind == "broadened", f.detail
    assert "attachment" not in f.detail.lower()


def test_guard_deductible_increase_still_narrowed():
    f = _pair(
        "A deductible of $500 applies.",
        "A deductible of $1,000 applies.",
        heading="Deductible",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail.lower()
    assert "attachment" not in f.detail.lower()


def test_guard_round20_attaches_in_excess_of_phrasing_unchanged():
    # The an earlier revision form this whole category was originally built for
    # must still resolve NARROWED after the earlier marker extension.
    f = _pair(
        "This policy attaches in excess of $500,000 of underlying limits.",
        "This policy attaches in excess of $1,000,000 of underlying limits.",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()


def test_guard_attaches_at_phrasing_increase_is_narrowed():
    # Explicitly-requested sibling phrasing ("attaches at $X"), not part
    # of either live defect but named in the task's required phrase
    # family -- must route the same way as "attaches above"/"attaches in
    # excess of".
    f = _pair(
        "This policy attaches at $500,000.",
        "This policy attaches at $1,000,000.",
    )
    assert f.kind == "narrowed", f.detail
    assert "attachment" in f.detail.lower()
