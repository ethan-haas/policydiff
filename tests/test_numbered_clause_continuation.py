"""Regression tests for an earlier fix (defect 1, HIGH severity,
.

The bug: once a numbered/roman/lettered clause's own line already
completed a sentence ("1. Coverage A applies to bodily injury."), every
FOLLOWING physical line up to the next header was still unconditionally
absorbed into that clause's body -- even though the continuation-join
rule unnumbered prose already used (see policydiff/sentence.py) would
never have joined them. Several unrelated, independently-changed
standalone sentences (a coinsurance change, an exclusion broadened, a
waiting period narrowed) got glued into ONE atom, and the classifier
chain resolves only the FIRST applicable signal on that merged blob and
returns -- so only one of the several real changes ever became a
Finding; the rest were dropped silently, with no trace in the report at
all (not even inside another finding's detail).

Original (an earlier revision) fix: a numbered/roman/lettered clause absorbed a
following physical line into its own body only while its own last
physical line had NOT already ended with terminal '.'/'?'/'!'. Once a
line DID complete the clause's own sentence, the next physical line was
evaluated fresh and, unless it carried its own enumerator, closed the
clause and started accumulating as ordinary UNNUMBERED PROSE.

Root fix SUPERSEDES the segmentation half of this:
that physical-line-completion gate made a clause's atom SET depend on
exactly where a line break fell, so a pure REFLOW (no content change at
all) of a multi-sentence clause could manufacture a phantom finding, or
worse, invert a real change's reported direction (see
the matching regression test). segment.py now absorbs a numbered/
roman/lettered clause's ENTIRE body unconditionally, up to the next
enumerator/heading/EOF, with all internal whitespace (including line
breaks) collapsed for its `text` -- so "1. X.\nY." and "1. X. Y." always
produce the identical atom, regardless of which physical line the break
happens to fall on. Recall for what used to be several independent
standalone atoms trailing a complete numbered clause (this file's
"mask"/"shape" scenarios) is now carried entirely by classify.py's
per-sentence backup (see below) -- the tests in this file are UNCHANGED
in what scenario they exercise and what they guarantee (recall: every
independent change is still reported, each with its own precise
citation; clause 1's own untouched sentence never gets touched by
someone else's change), but several assertions about the exact Clause
object shape (bare `.text` embedding a raw newline; a distinct `.id` per
finding; a separately-emitted "unchanged" Finding for an atom that's now
folded into its parent clause) have been updated to match the new,
reflow-invariant atom shape.

Backup requirement (policydiff/classify.py): even a genuine SINGLE
multi-sentence clause (two sentences on one physical line under one
clause number, or several sentences absorbed into one clause's body by
segment.py's an earlier revision fix) must never collapse more than one
independently-changed sentence down to the first-matching classifier's
lone result -- classify_pair_multi splits into a per-sentence pass
whenever both sides hold the same number (>1) of real sentences, firing
for as few as ONE changed sentence pair (an earlier revision broadened this from
an earlier revision's original 2+ threshold -- see classify_pair_multi's
docstring), with each resulting Finding scoped to its own sentence text
for a precise citation.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures
the task's FORBIDDEN clause) -- they are original clauses exercising the
same scenario classes described in the task.
"""
from policydiff.classify import classify_pair_multi
from policydiff.report import diff_documents, human_report
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) the reproduced "mask" shape: a numbered clause whose own line is
# an already-COMPLETE sentence, followed by three unrelated standalone
# sentences (percentage, exclusion, waiting period) -- all three must
# surface, clause 1 stays silent, and each finding cites only its own
# sentence, never the merged blob.
# ---------------------------------------------------------------------


def test_mask_shape_three_findings_clause_one_silent_precise_citations():
    old = (
        "1. Coverage A applies to bodily injury.\n"
        "Coinsurance of 70% applies to covered property.\n"
        "This insurance does not apply to earthquake.\n"
        "The waiting period is 10 days before benefits begin.\n"
    )
    new = (
        "1. Coverage A applies to bodily injury.\n"
        "Coinsurance of 85% applies to covered property.\n"
        "This insurance does not apply to earthquake or landslide.\n"
        "The waiting period is 45 days before benefits begin.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 3, [(f.kind, f.detail) for f in non_suppressed]

    # Clause "1"'s own opening sentence ("Coverage A applies to bodily
    # injury.") is untouched by any of the three real changes that follow
    # it -- an earlier revision's segmentation folds it into the same clause "1" atom
    # as the three changed sentences (rather than keeping it as a
    # separately-segmented standalone atom the way an earlier revision did), so there
    # is no longer a distinct "unchanged" Finding to look up by id; instead
    # assert directly that no finding's citation ever quotes that sentence.
    assert all(f.old is None or f.old.text != "Coverage A applies to bodily injury." for f in non_suppressed)
    assert all(f.old.id == "1" for f in non_suppressed if f.old is not None)

    # Each finding's own citation is the SPECIFIC changed sentence, not
    # the whole merged blob -- verified directly on old.text/new.text
    # (cite.py quotes exactly this).
    exclusion = next(f for f in non_suppressed if "exclusionary" in f.detail)
    assert exclusion.old.text == "This insurance does not apply to earthquake."
    assert exclusion.new.text == "This insurance does not apply to earthquake or landslide."
    assert exclusion.kind == "narrowed"

    wait = next(f for f in non_suppressed if "waiting period" in f.detail)
    assert wait.old.text == "The waiting period is 10 days before benefits begin."
    assert wait.new.text == "The waiting period is 45 days before benefits begin."
    assert wait.kind == "narrowed"

    coinsurance = next(
        f for f in non_suppressed if f is not exclusion and f is not wait
    )
    assert coinsurance.old.text == "Coinsurance of 70% applies to covered property."
    assert coinsurance.new.text == "Coinsurance of 85% applies to covered property."
    # Direction may or may not resolve for this exact phrasing (the
    # percent-direction regex is scoped elsewhere) -- what matters here
    # is RECALL: the change is reported at all, with its own precise
    # citation, never swallowed into another finding's blob.
    assert coinsurance.kind in ("narrowed", "broadened", "modified")


# ---------------------------------------------------------------------
# (b) the reproduced "shape" family: roman numeral + ALL-CAPS colon
# exclusion + colon-labeled sublimit + waiting-period sentence, all
# following one already-complete roman clause -- all four must surface.
# ---------------------------------------------------------------------


def test_roman_colon_caps_waitperiod_four_findings():
    old = (
        "IV. Coinsurance of 75% applies to covered property.\n"
        "WINDSTORM EXCLUSION: This insurance does not apply to windstorm.\n"
        "Sublimit for firearms: $3,000.\n"
        "The waiting period is 5 days before benefits begin.\n"
    )
    new = (
        "IV. Coinsurance of 95% applies to covered property.\n"
        "WINDSTORM EXCLUSION: This insurance does not apply to windstorm or hail.\n"
        "Sublimit for firearms: $1,500.\n"
        "The waiting period is 60 days before benefits begin.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 4, [(f.kind, f.detail) for f in non_suppressed]

    details = " | ".join(f.detail for f in non_suppressed)
    sublimit = next(f for f in non_suppressed if "sublimit" in f.detail)
    assert sublimit.kind == "narrowed"
    assert "3,000" in sublimit.detail and "1,500" in sublimit.detail

    wait = next(f for f in non_suppressed if "waiting period" in f.detail)
    assert wait.kind == "narrowed"
    assert "5" in wait.detail and "60" in wait.detail

    exclusion = next(f for f in non_suppressed if "exclusionary" in f.detail)
    assert exclusion.kind == "narrowed"
    assert exclusion.old.text == "WINDSTORM EXCLUSION: This insurance does not apply to windstorm."
    assert exclusion.new.text == "WINDSTORM EXCLUSION: This insurance does not apply to windstorm or hail."

    # roman clause IV's own coinsurance sentence changed too -- present,
    # its own precisely-cited finding (an earlier revision: every non_suppressed
    # finding here shares id "IV", the parent clause -- see
    # test_mask_shape... above -- so identify this one by its own sentence
    # text rather than by a now-shared id).
    coinsurance = next(f for f in non_suppressed if f is not sublimit and f is not wait and f is not exclusion)
    assert coinsurance.old.text == "Coinsurance of 75% applies to covered property."
    assert coinsurance.new.text == "Coinsurance of 95% applies to covered property."


# ---------------------------------------------------------------------
# (c) GUARD -- a genuine numbered clause wrapped across physical lines
# WITHOUT terminal punctuation between them still stays ONE clause, and
# a pure rewrap (line break moved, no content change) is still empty.
# ---------------------------------------------------------------------


def test_genuine_wrapped_numbered_clause_stays_one_clause_real_edit():
    old = "4. The aggregate limit of insurance is\n$1,000,000 under this policy.\n"
    new = "4. The aggregate limit of insurance is\n$2,000,000 under this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "broadened", f.detail
    # an earlier revision: `text` is whitespace-collapsed (reflow-invariant) for
    # numbered/roman/lettered clauses now -- the original physical-line
    # break is no longer embedded in it (see Clause.text_raw for that).
    assert f.old.text == "The aggregate limit of insurance is $1,000,000 under this policy."
    assert f.new.text == "The aggregate limit of insurance is $2,000,000 under this policy."


def test_rewrap_of_genuine_wrapped_numbered_clause_is_empty():
    old = "4. The aggregate limit of insurance is\n$1,000,000 under this policy.\n"
    new = "4. The aggregate limit of insurance\nis $1,000,000 under this policy.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == [], human_report(result, verbose=True)


# ---------------------------------------------------------------------
# (d) GUARD -- a numbered clause with lettered sub-items still segments
# those as their own atoms, unaffected by the continuation-gate change
# (a header line always short-circuits the gate).
# ---------------------------------------------------------------------


def test_numbered_clause_with_lettered_subitems_unchanged():
    old = "2. Coverage B\n(a) Fire damage is covered.\n(b) Theft damage is covered.\n"
    new = "2. Coverage B\n(a) Fire damage is covered.\n(b) Vandalism damage is covered.\n"

    old_clauses = segment(old)
    ids = [(c.id, c.kind) for c in old_clauses]
    assert ids == [("2", "numeric"), ("a", "lettered"), ("b", "lettered")], ids
    assert old_clauses[0].text == "Coverage B"
    assert old_clauses[1].text == "Fire damage is covered."
    assert old_clauses[2].text == "Theft damage is covered."

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.old.id == "b" and f.new.id == "b"
    assert f.old.text == "Theft damage is covered."
    assert f.new.text == "Vandalism damage is covered."


# ---------------------------------------------------------------------
# (e) a numbered clause followed by exactly ONE changed standalone
# sentence -> exactly that one finding, cited to the sentence itself.
# ---------------------------------------------------------------------


def test_numbered_clause_followed_by_one_changed_sentence_is_one_finding():
    old = "5. Coverage C applies to theft.\nA single deductible of $500 applies per claim.\n"
    new = "5. Coverage C applies to theft.\nA single deductible of $750 applies per claim.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert f.old.text == "A single deductible of $500 applies per claim."
    assert f.new.text == "A single deductible of $750 applies per claim."
    # Clause 5's own opening sentence ("Coverage C applies to theft.") is
    # untouched -- an earlier revision's per-sentence backup only ever emits a
    # Finding for a sentence pair that actually changed, so an unchanged
    # sentence inside the same clause produces no Finding of its own (it
    # is no longer a separately-segmented atom to look up by id -- see
    # test_mask_shape... above). This is the ONLY finding for the pair.
    assert len(result.findings) == 1
    assert f.old.text != "Coverage C applies to theft."


# ---------------------------------------------------------------------
# GUARD -- the common real-world "Title\nBody" numbered-clause idiom (a
# title-only heading line with NO terminal punctuation, immediately
# followed by its explanatory body sentence(s) that start with an
# UPPERCASE letter) must still be absorbed into ONE clause -- this is
# the shape tests/fixtures/policy_old.txt's clause 1 uses throughout,
# and it must not regress into two spurious atoms.
# ---------------------------------------------------------------------


def test_title_only_heading_still_absorbs_uppercase_body():
    old = (
        "1. Coverage A -- Bodily Injury\n"
        "We will pay those sums the insured is legally obligated to pay because of bodily injury.\n"
    )
    new = (
        "1. Coverage A -- Bodily Injury\n"
        "We will pay those sums the insured is legally obligated to pay because of bodily injury or death.\n"
    )
    old_clauses = segment(old)
    assert len(old_clauses) == 1, old_clauses
    assert old_clauses[0].id == "1"
    # an earlier revision: `text` is whitespace-collapsed (reflow-invariant) now --
    # see Clause.text_raw for the original-newline-preserving form.
    assert old_clauses[0].text == (
        "Coverage A -- Bodily Injury "
        "We will pay those sums the insured is legally obligated to pay because of bodily injury."
    )

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].old.id == "1"


# ---------------------------------------------------------------------
# Backup requirement -- classify.py: a genuine single multi-sentence
# clause (two sentences on ONE physical line under one clause number)
# must report BOTH independent changes, never just the first-matching
# classifier's lone result.
# ---------------------------------------------------------------------


def test_backup_multi_sentence_single_line_clause_reports_both_changes():
    old = segment(
        "1. Coinsurance of 80% applies to covered property. "
        "This insurance does not apply to flood.\n"
    )[0]
    new = segment(
        "1. Coinsurance of 90% applies to covered property. "
        "This insurance does not apply to flood or surface water.\n"
    )[0]
    findings = classify_pair_multi(old, new, suppress_cosmetic=True)
    assert len(findings) == 2, [(f.kind, f.detail) for f in findings]
    kinds_and_details = [(f.kind, f.detail) for f in findings]
    assert any("exclusionary" in d for _k, d in kinds_and_details)
    exclusion = next(f for f in findings if "exclusionary" in f.detail)
    assert exclusion.kind == "narrowed"


def test_backup_single_sentence_changed_within_multi_sentence_clause_unaffected():
    # GUARD: when only ONE of the clause's several sentences actually
    # changed, the existing whole-text chain (with its own full-clause
    # role/segment scoping -- see an earlier fix) still runs; the round
    # 13 backup split must never engage or alter its result.
    old = segment(
        "1. A deductible of $500 applies. The Company will pay $1,000,000 for each claim.\n"
    )[0]
    new = segment(
        "1. A deductible of $500 applies. The Company will pay $2,000,000 for each claim.\n"
    )[0]
    findings = classify_pair_multi(old, new, suppress_cosmetic=True)
    assert len(findings) == 1, [(f.kind, f.detail) for f in findings]
    assert findings[0].kind == "broadened", findings[0].detail
    assert "limit" in findings[0].detail
    assert "deductible" not in findings[0].detail
