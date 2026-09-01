"""Regression tests for an earlier fix (3 WRONG-DIRECTION
defects, Family 4 -- the specification's worst class, reproduced live by a fresh
reviewer).

The bug: definition/exclusion direction was decided by whether text was
ADDED or REMOVED (or, structurally, by pure-insertion/pure-deletion
containment -- itself just a length/count check wearing a "structural"
label), never by what the added/removed text actually SAID about the
covered/defined SET.

  * A restrictive qualifier ADDS words while NARROWING scope --
    `"Auto" means any land motor vehicle.` -> `...any PRIVATE PASSENGER
    land motor vehicle.` shrinks the defined set, but the old
    "content added = broadened" one-sided fallback called it broadened.
  * The mirror: removing that qualifier GROWS the set but the same
    fallback called it narrowed.
  * An exclusion's TRIGGER being restricted ("...bodily injury." ->
    "...bodily injury ARISING FROM ASSAULT.") means LESS is excluded --
    coverage BROADENS -- but the old pure-insertion-always-narrows
    fallback called it narrowed.

Root fix (policydiff/classify.py): definition/exclusion direction is now
decided by a per-span structural signal -- what KIND of word span
(computed by a real word-level diff, never a length/count summary) was
inserted or removed: for definitions, EXPANSIVE (new parallel member) vs
RESTRICTIVE (a qualifier, including a marker-less premodifier
immediately after a determiner); for exclusions, a NEW PERIL vs a
TRIGGER-RESTRICTION. No signal resolves it -> "modified (direction
unclear)", never a guess.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures
the task's FORBIDDEN clause) -- they are original clauses exercising the
same scenario classes described in the task and its Procedure section
((a) through (g)).
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str):
    old = segment(f"1. Clause. {old_text}\n")[0]
    new = segment(f"1. Clause. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# The 3 live defects, reproduced with original (non-reviewer) text.
# ---------------------------------------------------------------------


def test_escape1_definition_narrowed_by_restrictive_premodifier_not_broadened():
    # "private passenger" inserted directly after the determiner "any",
    # qualifying (shrinking) the noun it precedes -- no marker keyword
    # anywhere, but it can only be restricting the defined set.
    f = _pair(
        '"Auto" means any land motor vehicle.',
        '"Auto" means any private passenger land motor vehicle.',
    )
    assert f.kind == "narrowed", f.detail


def test_escape1_mirror_definition_broadened_when_qualifier_removed():
    f = _pair(
        '"Auto" means any private passenger land motor vehicle.',
        '"Auto" means any land motor vehicle.',
    )
    assert f.kind == "broadened", f.detail


def test_escape1_definition_narrowed_by_designed_for_phrase():
    f = _pair(
        '"Auto" means any land motor vehicle.',
        '"Auto" means any land motor vehicle designed for use on public roads.',
    )
    assert f.kind == "narrowed", f.detail


def test_escape1_definition_narrowed_by_ownership_qualifier():
    f = _pair(
        '"Covered property" means property.',
        '"Covered property" means property you own.',
    )
    assert f.kind == "narrowed", f.detail


def test_escape2_exclusion_trigger_restriction_broadens_coverage_not_narrows():
    f = _pair(
        "Coverage does not apply to bodily injury.",
        "Coverage does not apply to bodily injury arising from assault.",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# GUARD: the CORRECT control that must stay correct -- a genuinely new
# excluded peril added still narrows coverage.
# ---------------------------------------------------------------------


def test_guard_new_excluded_peril_still_narrows_coverage():
    f = _pair(
        "This insurance does not apply to flood.",
        "This insurance does not apply to flood or war.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# Procedure (a)-(g): the required regression coverage.
# ---------------------------------------------------------------------


def test_a1_definition_restrictive_qualifier_add_premodifier_is_narrowed():
    f = _pair(
        '"Auto" means any motor vehicle.',
        '"Auto" means any commercial motor vehicle.',
    )
    assert f.kind == "narrowed", f.detail


def test_a2_definition_restrictive_qualifier_add_designed_for_is_narrowed():
    f = _pair(
        '"Structure" means any building.',
        '"Structure" means any building designed for use as a dwelling.',
    )
    assert f.kind == "narrowed", f.detail


def test_a3_definition_restrictive_qualifier_add_ownership_is_narrowed():
    f = _pair(
        '"Covered item" means personal property.',
        '"Covered item" means personal property you own.',
    )
    assert f.kind == "narrowed", f.detail


def test_b_definition_qualifier_remove_is_broadened():
    f = _pair(
        '"Auto" means any commercial motor vehicle.',
        '"Auto" means any motor vehicle.',
    )
    assert f.kind == "broadened", f.detail


def test_c1_definition_expansive_add_or_trailer_is_broadened():
    f = _pair(
        '"Auto" means any car.',
        '"Auto" means any car or trailer.',
    )
    assert f.kind == "broadened", f.detail


def test_c2_definition_expansive_add_including_is_broadened():
    f = _pair(
        '"Property" means buildings.',
        '"Property" means buildings, including fences.',
    )
    assert f.kind == "broadened", f.detail


def test_d1_exclusion_trigger_restriction_arising_from_is_broadened():
    f = _pair(
        "This insurance does not apply to bodily injury.",
        "This insurance does not apply to bodily injury arising from assault.",
    )
    assert f.kind == "broadened", f.detail


def test_d2_exclusion_trigger_restriction_only_if_is_broadened():
    f = _pair(
        "This insurance does not apply to theft.",
        "This insurance does not apply to theft only if the vehicle is unattended.",
    )
    assert f.kind == "broadened", f.detail


def test_d3_exclusion_trigger_restriction_when_is_broadened():
    f = _pair(
        "This insurance does not apply to water damage.",
        "This insurance does not apply to water damage when caused by flood.",
    )
    assert f.kind == "broadened", f.detail


def test_e_exclusion_new_peril_add_is_narrowed_coverage():
    f = _pair(
        "This insurance does not apply to flood.",
        "This insurance does not apply to flood or earthquake.",
    )
    assert f.kind == "narrowed", f.detail


def test_f_exclusion_peril_remove_is_broadened_coverage():
    f = _pair(
        "This insurance does not apply to flood or earthquake.",
        "This insurance does not apply to flood.",
    )
    assert f.kind == "broadened", f.detail


def test_g1_definition_ambiguous_reword_is_modified_not_a_guess():
    f = _pair(
        '"Contractor" means a person hired to perform work.',
        '"Contractor" means a person engaged to perform work.',
    )
    assert f.kind == "modified", f.detail


def test_g2_exclusion_ambiguous_reword_is_modified_not_a_guess():
    f = _pair(
        "This insurance does not apply to loss caused by fire.",
        "This insurance does not apply to loss caused by kitchen fire.",
    )
    assert f.kind == "modified", f.detail


# ---------------------------------------------------------------------
# End-to-end sanity via the CLI-facing diff_documents() entry point, so
# the fix is proven through the same path production traffic uses, not
# just the classify_pair() unit.
# ---------------------------------------------------------------------


def test_end_to_end_definition_narrowed_via_diff_documents():
    old = '1. "Auto" means any land motor vehicle.\n'
    new = '1. "Auto" means any private passenger land motor vehicle.\n'
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "narrowed", non_suppressed[0].detail


def test_end_to_end_exclusion_broadened_via_diff_documents():
    old = "1. Coverage does not apply to bodily injury.\n"
    new = "1. Coverage does not apply to bodily injury arising from assault.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "broadened", non_suppressed[0].detail
