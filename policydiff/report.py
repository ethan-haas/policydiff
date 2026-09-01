"""Wire segmentation -> alignment -> classification -> citation together
and produce a human-readable report plus a machine-readable diff.

Cosmetic and unchanged findings are suppressed from the human report by
default (they are still present in the JSON diff and in --verbose human
output, since a real change getting silently dropped is exactly the
failure mode this whole tool exists to prevent).

an earlier revision added a whole separate reconciliation pass (reconcile.py) to
paper over blank-line re-partitioning of unnumbered "paragraph" clauses.
an earlier fix makes that pass unnecessary: segment.py now atomizes
unnumbered prose at SENTENCE boundaries (see policydiff/sentence.py), so
a blank-line/paragraph regrouping of the exact same sentences never
changes the clause SET in the first place -- ordinary content-similarity
alignment (align.py) pairs each sentence to its identical or edited twin
directly, with no special-casing. reconcile.py has been removed; nothing
in this module calls it anymore.

an earlier revision root cause A: heading-rename SUPPRESSION used to be driven by
clause SHAPE alone (every clause a finding touched being segment.py's
"section" kind) -- but shape only tells you an atom LOOKS like a heading
line, never whether it carries real coverage content. Three rounds in a
row (r4/r5/r6) each found a new shape the previous content-in-segment.py
gate didn't anticipate, and each time real coverage changes written in
heading style ("EARTHQUAKE EXCLUDED", "Windstorm Deductible: $2,500")
were silently dropped. The fix: segment.py's "section" kind is now PURE
SHAPE again (see its module comment) and is only used here to scope
WHICH findings are heading-rename CANDIDATES; whether a candidate is
actually suppressed is decided by _is_coverage_bearing below, a CONTENT
check applied to the finding's own old/new text -- so a heading-shaped
change that turns out to carry coverage content (a $ amount, a coverage
verb/negation like "excluded"/"excludes"/"covered"/"no coverage", or a
coverage noun in assertion position, e.g. a colon-value row) is left in
its originally-computed kind and reported, never relabeled away.

Root fix: the rule above was only ever WIRED to
UNNUMBERED ("section"-kind) heading atoms -- a NUMBERED/roman/lettered
clause's own heading LINE ("4. EXCLUSIONS" -> "4. GENERAL EXCLUSIONS",
"1. LIMITS OF INSURANCE" -> "1. LIMITS OF LIABILITY") never went
through _is_coverage_bearing at all, so renaming it fabricated a
coverage finding even when the clause's coverage BODY (whether it sits
in the SAME merged "N. HEADING\nbody" clause, or flushed into its own
separate atoms when the heading line ends its own sentence) was byte-
identical. That divergence -- two different rules for what is
structurally the same kind of rename -- is exactly the trap the earlier
docstring above warns against ("do not invent a second, divergent
heading rule"). The fix routes a numbered/roman/lettered clause's own
heading PORTION through the SAME _is_coverage_bearing content-delta
predicate, scoped to just that portion (never the body) via
_numbered_heading_and_body -- see _is_numbered_heading_rename_only.
Because a numbered heading's captured text is never SHAPE-filtered at
segmentation time (unlike a bare/keyword "section" heading -- a
numbered clause's heading may legitimately be a long prose title, e.g.
"2. Coverage B -- Medical Payments"), suppression additionally requires
the heading portion to still be heading-SHAPED (segment.py's existing
_is_bare_heading_line, reused rather than re-implemented) -- this is
what keeps a genuine numbered coverage ASSERTION on the enumerator's own
line ("4. The company does not cover flood." -> "...flood or war.") out
of the suppression path even where _is_coverage_bearing's own vocabulary
happens not to key on that particular verb form: the assertion ends in
terminal sentence punctuation, so it was never heading-shaped to begin
with, exactly like the guard case segment.py's own bare-heading detector
was built to reject (see its module comment).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace

from .align import align
from .cite import Citation, cite
from .classify import Finding, classify_added, classify_pair_multi, classify_removed
from .normalize import normalize, strip_bom
from .segment import Clause, _is_bare_heading_line, segment

SUPPRESSED_KINDS = {"unchanged", "cosmetic", "heading"}

# Finding kinds that COULD represent a coverage change if both sides were
# ordinary clauses.
_COVERAGE_KINDS = {"added", "removed", "narrowed", "broadened", "modified"}

# ---------------------------------------------------------------------
# Content-delta detector (an earlier revision root cause A fix).
#
# These word forms split into two buckets:
#
#   * VERB / participle forms ("excludes", "excluded", "exclude",
#     "covered", "applies", "apply") and fixed negation phrases ("no
#     coverage", "not covered") are DECISIVE on their own -- a genuine
#     topic label is a bare noun phrase and does not normally contain a
#     conjugated verb, so a heading-shaped line that DOES contain one is
#     actually an assertion in heading clothing ("EARTHQUAKE EXCLUDED",
#     "THIS POLICY EXCLUDES FLOOD", "WAR EXCLUDED").
#   * NOUN forms ("coverage", "exclusion", "deductible", "limit",
#     "sublimit", "insur*", "pay", "payable") are AMBIGUOUS -- they show
#     up in genuine topic labels too ("EXCLUSIONS", "SCHEDULE OF LIMITS
#     OF INSURANCE"), so they only count when the line also has
#     assertion STRUCTURE: a colon-value shape ("Flood: Excluded",
#     "Windstorm Deductible: $2,500") or a copula/negation word
#     ("is"/"are"/"was"/"were"/"not"/"no").
#
# A `$`/digit amount is decisive by itself either way -- a bare topic
# label never carries one.
# ---------------------------------------------------------------------
_COVERAGE_VERB_RE = re.compile(r"\b(?:excludes?|excluded|covered|applies|apply)\b", re.IGNORECASE)
_COVERAGE_NOUN_RE = re.compile(
    r"\b(?:coverage|exclusion|deductible|limit|sublimit|insur\w*|pay|payable)\b",
    re.IGNORECASE,
)
_NEGATION_PHRASE_RE = re.compile(r"\bno\s+coverage\b|\bnot\s+covered\b", re.IGNORECASE)
_ASSERTION_CONTEXT_RE = re.compile(r":|\b(?:is|are|was|were|not|no)\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\d")


def _is_coverage_bearing(text: str) -> bool:
    """True if *text* asserts real coverage-relevant content -- see the
    block comment above. Used to decide whether a heading-shaped change
    is a pure label rename (no coverage content either side -> suppress)
    or a real coverage change written in heading style (-> report)."""
    if _AMOUNT_RE.search(text):
        return True
    if _COVERAGE_VERB_RE.search(text):
        return True
    if _NEGATION_PHRASE_RE.search(text):
        return True
    if _COVERAGE_NOUN_RE.search(text) and _ASSERTION_CONTEXT_RE.search(text):
        return True
    return False


def _is_heading_candidate(finding: Finding) -> bool:
    """True if every clause a finding touches is a bare SECTION heading
    ATOM (structural SHAPE only, see segment.py) -- i.e. this finding is
    a CANDIDATE for heading-rename suppression. Being heading-shaped
    never suppresses a finding by itself (an earlier revision fix) -- see
    _is_label_rename_only below for the actual (content-based)
    suppression decision."""
    sides = [c for c in (finding.old, finding.new) if c is not None]
    return bool(sides) and all(c.kind == "section" for c in sides)


def _is_label_rename_only(finding: Finding) -> bool:
    """True if a heading-shaped finding (see _is_heading_candidate)
    carries NO coverage-bearing content on EITHER side -- a pure
    document-structure rename/add/remove/move, not a coverage change
    written in heading style. This is the content-delta suppression
    rule itself (an earlier revision root cause A)."""
    texts = [c.text for c in (finding.old, finding.new) if c is not None]
    return not any(_is_coverage_bearing(t) for t in texts)


# Root fix: the numbered/roman/lettered equivalent of
# the two functions above, scoped to just the clause's own heading LINE
# rather than its whole text -- see the module docstring's an earlier revision note.
_NUMBERED_HEADING_KINDS = {"numeric", "lettered", "roman"}


def _numbered_heading_and_body(clause: Clause) -> tuple[str, str]:
    """Split a numbered/lettered/roman clause's `text` into its heading
    PORTION (segment.py always places the heading line first -- see
    Clause.heading and segment()'s `current["lines"] = [heading] ...`)
    and everything after it: the clause's coverage BODY, present when
    the heading and body were merged into one clause (a title-only
    heading line immediately followed by its own body sentence(s), e.g.
    "4. EXCLUSIONS\nThe company does not cover flood."), empty when the
    heading line ended its own sentence and the body flushed as separate
    standalone atoms instead (e.g. "4. EXCLUSIONS." on its own). Never
    used for "section"-kind clauses -- those already carry heading text
    as their ENTIRE `text` (no body of their own; see
    _is_heading_candidate) and are handled by _is_label_rename_only.

    an earlier revision fix: `clause.text` is now whitespace-collapsed
    (see segment.py's module docstring) so it no longer carries the
    original newline that used to mark the heading/body boundary here.
    `clause.text_raw` -- the reflow-preserving original -- is used
    instead when present (it falls back to `text` when the clause's body
    was already a single physical line, in which case there is no body
    to split off anyway)."""
    text = clause.text_raw or clause.text
    nl = text.find("\n")
    if nl == -1:
        return text, ""
    return text[:nl], text[nl + 1:].strip()


def _is_numbered_heading_rename_only(finding: Finding) -> bool:
    """True if *finding* is a rename confined to a numbered/roman/
    lettered clause's own HEADING portion: both sides are that clause
    kind, the coverage BODY portion (see _numbered_heading_and_body) is
    unchanged once cosmetic-normalized, the heading portion is still
    heading-SHAPED on both sides (segment.py's _is_bare_heading_line --
    a numbered clause's captured "heading" group is never shape-
    filtered at segmentation time the way a bare/keyword section heading
    is, so a genuine coverage assertion sitting directly on the
    enumerator's own line, e.g. "4. The company does not cover flood.",
    must be excluded here rather than reaching the content check below),
    and neither heading portion carries coverage content of its own (the
    SAME _is_coverage_bearing content-delta predicate the unnumbered/
    section path uses -- Root fix, see module docstring)."""
    if finding.old is None or finding.new is None:
        return False
    old_c, new_c = finding.old, finding.new
    if old_c.kind not in _NUMBERED_HEADING_KINDS or new_c.kind not in _NUMBERED_HEADING_KINDS:
        return False
    old_heading, old_body = _numbered_heading_and_body(old_c)
    new_heading, new_body = _numbered_heading_and_body(new_c)
    if not _is_bare_heading_line(old_heading.strip()) or not _is_bare_heading_line(new_heading.strip()):
        return False
    if normalize(old_body, suppress_cosmetic=True) != normalize(new_body, suppress_cosmetic=True):
        return False
    if _is_coverage_bearing(old_heading) or _is_coverage_bearing(new_heading):
        return False
    return True


@dataclass
class DiffResult:
    findings: list[Finding]
    citations: list[Citation]
    old_clauses: list[Clause]
    new_clauses: list[Clause]


def diff_documents(old_text: str, new_text: str, suppress_cosmetic: bool = True) -> DiffResult:
    # Root fix: strip a leading UTF-8 BOM /
    # stray zero-width BOM characters (U+FEFF) on BOTH sides before
    # anything else touches the text -- see normalize.strip_bom's
    # docstring. This runs unconditionally (not gated by
    # suppress_cosmetic): a BOM is never meaningful content on either
    # side, and segmentation itself (not just cosmetic comparison) is
    # what breaks when it's left in, so it must be gone before segment()
    # ever sees the text.
    old_text = strip_bom(old_text)
    new_text = strip_bom(new_text)
    old_clauses = segment(old_text)
    new_clauses = segment(new_text)

    alignment = align(old_clauses, new_clauses)

    findings: list[Finding] = []
    for pair in alignment.pairs:
        # A clause pair may resolve to MORE THAN ONE finding (an earlier revision
        # root fix: a clause with more than one independently-changed
        # monetary amount reports one finding per changed amount, so a
        # co-occurring narrowing is never dropped behind a broadening).
        findings.extend(classify_pair_multi(pair.old, pair.new, suppress_cosmetic=suppress_cosmetic))
    for old_c in alignment.unmatched_old:
        findings.append(classify_removed(old_c))
    for new_c in alignment.unmatched_new:
        findings.append(classify_added(new_c))

    # A bare SECTION heading is not itself coverage: an added/removed/
    # narrowed/broadened/modified finding whose clause(s) are all
    # heading-SHAPED (_is_heading_candidate) AND carry no coverage
    # content on either side (_is_label_rename_only, an earlier revision's
    # content-delta rule) gets relabeled "heading" (suppressed by
    # default, same as "unchanged"/"cosmetic") instead of read as a
    # coverage change. A heading-shaped finding that DOES carry coverage
    # content is left in its originally-computed kind -- see the module
    # docstring.
    #
    # an earlier revision's gate-5-universality fix (still applies): this relabeling
    # is itself a SUPPRESSION step, exactly like normalize.py's cosmetic
    # folding, so it must be gated on the SAME `suppress_cosmetic` toggle
    # -- with the toggle off (no-suppress-cosmetic), a heading-only
    # finding must stay in its original, visible kind, or the defect
    # hatch (gate 5) is not actually universal (see the h11
    # an earlier audit defect: the heading path silently bypassed the toggle
    # instead of honoring it).
    findings = [
        replace(f, kind="heading")
        if suppress_cosmetic
        and f.kind in _COVERAGE_KINDS
        and (
            (_is_heading_candidate(f) and _is_label_rename_only(f))
            or _is_numbered_heading_rename_only(f)
        )
        else f
        for f in findings
    ]

    # Stable, readable ordering: by the earliest clause position touched.
    def _sort_key(f: Finding):
        idx = f.old.order_index if f.old is not None else (f.new.order_index if f.new else 0)
        return idx

    findings.sort(key=_sort_key)
    citations = [cite(f) for f in findings]
    return DiffResult(findings=findings, citations=citations, old_clauses=old_clauses, new_clauses=new_clauses)


def to_json(result: DiffResult) -> dict:
    items = []
    for c in result.citations:
        items.append(
            {
                "kind": c.kind,
                "old_clause_id": c.old_clause_id,
                "new_clause_id": c.new_clause_id,
                "old_quote": c.old_quote,
                "new_quote": c.new_quote,
                "detail": c.detail,
            }
        )
    return {"findings": items}


def to_json_str(result: DiffResult) -> str:
    return json.dumps(to_json(result), indent=2, ensure_ascii=False)


def human_report(result: DiffResult, verbose: bool = False) -> str:
    lines: list[str] = []
    kind_label = {
        "added": "ADDED",
        "removed": "REMOVED",
        "narrowed": "NARROWED",
        "broadened": "BROADENED",
        "modified": "MODIFIED (direction unclear)",
        "unchanged": "unchanged",
        "cosmetic": "cosmetic",
        "heading": "heading (non-coverage)",
    }
    shown = 0
    for f, c in zip(result.findings, result.citations):
        if f.kind in SUPPRESSED_KINDS and not verbose:
            continue
        shown += 1
        lines.append(f"[{kind_label.get(f.kind, f.kind.upper())}] {f.detail}")
        if c.old_clause_id is not None:
            lines.append(f"    old {c.old_clause_id}: \"{c.old_quote}\"")
        if c.new_clause_id is not None:
            lines.append(f"    new {c.new_clause_id}: \"{c.new_quote}\"")
        lines.append("")
    if shown == 0:
        lines.append("No coverage-relevant changes found." if not verbose else "No findings.")
    return "\n".join(lines).rstrip() + "\n"
