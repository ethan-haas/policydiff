"""Regression tests for an earlier fix (2 WRONG-DIRECTION
defects + 1 noise false positive against HEAD
c285eae).

  * Defect 1 (primary, wrong-direction): the exclusion-context router
    (classify._is_exclusion) recognized only "exclusion"/"does not
    apply"/"we will not pay" -- so a carve-back/restriction added to an
    exclusion phrased with "does not cover", bare "excludes"/"excluded",
    or "no coverage for" never reached the exclusion scope-signal logic
    at all; it fell through to the GENERIC restrictive-marker path, which
    reads an added "except" as plain restriction and reports "narrowed"
    -- backwards, since restricting an exclusion's own trigger BROADENS
    coverage (an earlier revision's own scope-signal logic, unreachable for these
    verbs). Root fix: _is_exclusion now recognizes the full phrasing
    family and routes ALL of them through _classify_exclusion.

  * Defect 2 (secondary, wrong-direction): a pure REWORD of a defined
    noun phrase ("the named insured" -> "the person or organization
    named") was misread as a restrictive-qualifier NARROWING, because the
    inserted span "person or organization" happens to sit right after
    the determiner "the" -- the same shape a genuine restrictive
    premodifier insertion has ("any land motor vehicle" -> "any PRIVATE
    PASSENGER land motor vehicle"). The difference: the reword ALSO
    deletes the old noun phrase it replaces ("named insured"), so the
    word-level diff is a SUBSTITUTION, not a clean insertion with the
    rest of the definition intact. Root fix: the bare determiner-
    adjacency signal (classify._definition_span_signal's last branch) is
    suppressed when the clause's word diff shows both an insert-side and
    a delete-side span (classify._classify_definition's is_substitution
    gate) -- an explicit keyword/coordinating-word signal still fires
    regardless.

  * Defect 3 (noise): an old file without a UTF-8 BOM compared against an
    otherwise-identical new file WITH a leading BOM (\\ufeff) produced a
    spurious "added" finding, because the un-stripped BOM sat in front of
    "1." on the new side only, stopping the enumerator regex from
    recognizing it there. Root fix: report.diff_documents now strips a
    leading/stray BOM (normalize.strip_bom) from BOTH sides before
    segmentation ever runs.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses exercising the same
scenario classes described in the task.
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str):
    old = segment(f"1. Clause. {old_text}\n")[0]
    new = segment(f"1. Clause. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


# ---------------------------------------------------------------------
# Defect 1: the exclusion-verb family. All four carve-back phrasings
# (required outcome list) -> BROADENED.
# ---------------------------------------------------------------------


def test_escape1_does_not_cover_carveback_is_broadened():
    f = _pair(
        "This insurance does not cover damage arising out of pollution.",
        "This insurance does not cover damage arising out of pollution, except damage from a hostile fire.",
    )
    assert f.kind == "broadened", f.detail


def test_escape1_control_does_not_apply_to_carveback_still_broadened():
    f = _pair(
        "This policy does not apply to bodily injury.",
        "This policy does not apply to bodily injury, except bodily injury arising from a covered occurrence.",
    )
    assert f.kind == "broadened", f.detail


def test_escape1_bare_excludes_carveback_is_broadened():
    f = _pair(
        "This policy excludes bodily injury to any employee.",
        'This policy excludes bodily injury to any employee, except bodily injury for which the insured has assumed liability under an "insured contract".',
    )
    assert f.kind == "broadened", f.detail


def test_escape1_no_coverage_for_carveback_is_broadened():
    f = _pair(
        "There is no coverage for loss to the dwelling.",
        "There is no coverage for loss to the dwelling, except loss caused by fire or lightning.",
    )
    assert f.kind == "broadened", f.detail


def test_escape1_not_covered_phrasing_carveback_is_broadened():
    f = _pair(
        "Loss caused by wear and tear is not covered.",
        "Loss caused by wear and tear is not covered, unless the wear and tear results from a covered peril.",
    )
    assert f.kind == "broadened", f.detail


def test_escape1_will_not_pay_phrasing_carveback_is_broadened():
    f = _pair(
        "We will not pay for loss caused by mold.",
        "We will not pay for loss caused by mold, except mold resulting from a covered water damage claim.",
    )
    assert f.kind == "broadened", f.detail


def test_escape1_new_peril_still_narrows_for_does_not_cover_phrasing():
    # GUARD: the new phrasing family must not swallow the genuine
    # new-excluded-peril case -- a coordinating-word span extending WHAT
    # is excluded still narrows coverage.
    f = _pair(
        "This insurance does not cover flood.",
        "This insurance does not cover flood or war.",
    )
    assert f.kind == "narrowed", f.detail


def test_escape1_new_peril_still_narrows_for_bare_excludes_phrasing():
    f = _pair(
        "This policy excludes theft.",
        "This policy excludes theft or vandalism.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# Defect 2: definition pure-reword -> modified (direction unclear); the
# genuine restrictive/expansive definition changes are unaffected.
# ---------------------------------------------------------------------


def test_escape2_definition_pure_reword_is_modified_unclear():
    f = _pair(
        '"Insured" means the named insured shown in the Declarations.',
        '"Insured" means the person or organization named in the Declarations.',
    )
    assert f.kind == "modified", f.detail


def test_escape2_guard_restrictive_premodifier_insertion_still_narrowed():
    # Pure insertion (no co-occurring delete) after a determiner -- still
    # a real restrictive premodifier, must stay narrowed.
    f = _pair(
        '"Auto" means any land motor vehicle.',
        '"Auto" means any private passenger land motor vehicle.',
    )
    assert f.kind == "narrowed", f.detail


def test_escape2_guard_expansive_addition_still_broadened():
    f = _pair(
        '"Auto" means any car.',
        '"Auto" means any car or trailer.',
    )
    assert f.kind == "broadened", f.detail


def test_escape2_guard_restrictive_qualifier_removal_still_broadened():
    # Pure deletion (no co-occurring insert) -- still a real qualifier
    # removed, must stay broadened.
    f = _pair(
        '"Auto" means any commercial motor vehicle.',
        '"Auto" means any motor vehicle.',
    )
    assert f.kind == "broadened", f.detail


def test_escape2_another_reword_shape_is_modified_unclear():
    # A second, differently-shaped substitution (a single-word swap via a
    # real "replace" opcode) -- must also resolve to modified, not a
    # guessed direction.
    f = _pair(
        '"Contractor" means a person hired to perform work.',
        '"Contractor" means a person engaged to perform work.',
    )
    assert f.kind == "modified", f.detail


# ---------------------------------------------------------------------
# Defect 3: BOM-only difference -> EMPTY (no findings beyond
# unchanged/cosmetic); a real change in a BOM'd file is still caught.
# ---------------------------------------------------------------------


def test_escape3_bom_only_difference_is_empty():
    old_text = "1. Coverage A applies.\n"
    new_text = "﻿1. Coverage A applies.\n"
    result = diff_documents(old_text, new_text, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]


def test_escape3_real_change_in_bommed_file_still_caught():
    old_text = "﻿1. This insurance does not cover flood.\n"
    new_text = "﻿1. This insurance does not cover flood or war.\n"
    result = diff_documents(old_text, new_text, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "narrowed", non_suppressed[0].detail


def test_escape3_stray_bom_mid_document_stripped_on_both_sides():
    old_text = "1. Coverage A applies.\n2. Coverage B applies.\n"
    new_text = "1. Coverage A applies.\n2. ﻿Coverage B applies.\n"
    result = diff_documents(old_text, new_text, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
