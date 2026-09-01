"""Segment a plain-text/markdown policy form into an ordered list of clauses.

A clause is anything that starts at the beginning of a physical line and
matches one of a handful of common policy-form numbering conventions:

    1.  Numbered / dotted numbering       "4.2 Contractual Liability"
    2.  Roman numerals                    "IV. Exclusions"
    3.  Lettered sub-items                "(a) ..."
    4.  Section headers                   "SECTION I -- EXCLUSIONS"

NUMBERED / ROMAN / LETTERED clauses gather their OWN BODY TEXT across
physical lines UNCONDITIONALLY: once such a clause opens, every physical
line (blank or not) up to the next enumerator/heading line or EOF
belongs to it, full stop -- there is no per-physical-line "does this
line's own sentence look complete yet" gate deciding whether to keep
absorbing (Root fix: an earlier revision put exactly that gate
in, keyed on whether the clause's own last physical line already ended
with terminal '.'/'?'/'!' -- but that made the clause's ATOM SET a
function of where the physical line break happened to fall. "4. Coverage
A applies to bodily injury. It also applies to property damage." on ONE
physical line stayed a single atom; the SAME two sentences rewrapped
across TWO physical lines closed clause 4 after the first sentence and
spun the second off as an unrelated standalone atom -- so a pure reflow
(no content change at all) manufactured a phantom [ADDED] finding, and
worse, on a real edit inside that second sentence, the phantom
add/remove could invert the reported direction entirely (a coverage cut
read as a broadening -- see an earlier audit's wrapreal repro). A line-break
heuristic cannot distinguish "Y is a wrapped continuation of X" from "Y
is a genuinely separate provision that happens to follow X" -- "1.
X.\nY." is the identical shape either way -- so it has been removed as
the deciding axis entirely.)

The clause's own `text` is built by joining every absorbed physical line
(including the heading text on the enumerator's own line, if any) and
collapsing ALL internal whitespace -- including the newlines between
physical lines and any blank lines -- down to single spaces, exactly
like `normalize()` does for cosmetic comparison. This is what makes the
atom's CONTENT (and therefore the atom SET produced by two versions of
the same document) independent of exactly where line breaks happen to
fall: "X.\nY." and "X. Y." join to byte-identical `text`. The clause's
original physical-line layout is preserved separately in `text_raw` (see
the Clause docstring below) so a caller that disables cosmetic
suppression can still see a pure-reflow edit as a change.

Recall for a clause whose SWALLOWED body turns out to hold more than one
real sentence -- whether that's two sentences on one original physical
line, or several original standalone sentences that used to spin off as
separate atoms under the old line-break gate -- is no longer segment.py's
job at all: classify.py's per-sentence classification (see
classify_pair_multi's docstring) reports every independently-changed
sentence inside an aligned clause pair as its own Finding, with its own
precise citation, once the pair itself doesn't match verbatim. A line
that carries its OWN enumerator ("(a)", "2.", "ii.") is still always its
own clause, matched before any of this ever runs. Nested numbering like
"2." followed by "2.1" still simply produces two sibling-ish clauses in
document order. The clause NUMBER remains a real, spec-assigned stable
anchor.

SECTION headers are different: they are pure organizational headings
("SECTION I -- EXCLUSIONS") that carry NO coverage content of their own.
Emit them as their own zero-body "section" clause and do NOT let them
swallow the prose underneath them the way a numbered clause swallows its
body -- that prose is UNNUMBERED content (see below).

Any text that isn't under an open numbered/roman/lettered clause -- a
title/declarations block before the first header, the entire body of a
document that uses no enumerators at all, or the prose sitting under a
SECTION header before its next sibling header -- is UNNUMBERED PROSE.
It is never discarded, and (this is an earlier fix) it is segmented at
SENTENCE boundaries, not blank-line/paragraph boundaries: a blank-line
regrouping of the exact same sentences must never change the clause SET,
or alignment sees a different document shape and manufactures phantom
findings out of pure re-partitioning (see policydiff/sentence.py and
policydiff/reconcile.py's retirement note). Each sentence gets a
synthesized id ("¶N").

Each clause records:
    id               -- the clause number/letter/roman AS PRINTED, or a
                         synthesized "¶N" id for an unnumbered sentence
    kind             -- "section" | "numeric" | "lettered" | "roman" | "paragraph"
    heading           -- the text on the header line itself (may be empty);
                         for a "paragraph" (sentence) clause, this carries
                         the enclosing SECTION header's heading text, or
                         "" if there wasn't one -- informational scope for
                         a human reader, not load-bearing for alignment
                         (alignment is purely content-based, see align.py)
    text              -- full clause text (heading + body for numbered/
                         roman/lettered/section; the sentence text itself
                         for a paragraph clause)
    order_index       -- 0-based position in the source document
    content_hash      -- sha256 of the normalized (cosmetic-suppressed) text

content_hash is a convenience for exact-duplicate detection; classify.py
does its own (toggle-aware) normalization rather than trusting this hash
blindly, so segmentation stays independent of the suppression toggle.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .enumerators import (
    BARE_ALPHA_DOT_RE,
    PAREN_ROMAN_RE,
    confirmed_bare_alpha_line_indices,
    roman_value,
)
from .sentence import (
    group_prose_lines,
    group_prose_lines_raw,
    is_heading_shaped_line,
    split_sentences,
    split_sentences_raw,
)


@dataclass
class Clause:
    id: str
    kind: str          # "section" | "numeric" | "lettered" | "roman" | "paragraph"
    heading: str
    text: str
    order_index: int
    content_hash: str = field(default="")
    # an earlier revision's root fix: a "paragraph" (unnumbered
    # sentence) clause's `text` has already had its physical line breaks
    # collapsed to single spaces by sentence.py, unconditionally, before
    # the suppress_cosmetic toggle is ever in scope -- so a pure rewrap of
    # such a clause is unrecoverable from `text` alone. `text_raw`
    # preserves the original newline positions for exactly that clause
    # kind (see segment()'s flush_prose()).
    #
    # an earlier revision's root fix: a numbered/roman/lettered clause's
    # `text` is now ALSO whitespace-collapsed (see segment()'s
    # flush_current() and the module docstring above) so that its atom
    # SET no longer depends on where a physical line break falls within
    # its body. `text_raw` carries the same original-newline-preserving
    # role for these clause kinds that it already carried for "paragraph"
    # clauses. Only "section" clauses (heading-only, no body) still leave
    # `text_raw` as "" -- their `text` is just the heading line itself,
    # never multi-line -- and callers fall back to `text` via `text_raw or
    # text` uniformly regardless of kind.
    text_raw: str = field(default="")

    def short_id(self) -> str:
        return self.id


_PATTERNS = [
    (
        "numeric",
        # an earlier revision's root fix: multi-level/dotted
        # numbering ("4.2 ...", "5.1.3 ...", "10.2 ...", "4.2(a) ...")
        # -- real-world forms write these WITHOUT a trailing period
        # before the heading text once a second level is present ("4.2
        # Body...", not "4.2. Body..."). The enumerator here is the
        # clause NUMBER, a cosmetic anchor normalized away by alignment
        # (content-based, see align.py) -- not prose -- at ANY depth.
        # Tried before the single-level pattern below since it's the
        # more specific shape (requires 2+ segments).
        re.compile(r"^(?P<id>\d+(?:\.\d+)+(?:\([a-zA-Z]\))?)\s+(?P<heading>.+)$"),
    ),
    (
        "numeric",
        # Single-level numbering ("1. Coverage A"), or multi-level
        # numbering that IS explicitly dotted before the heading ("4.2.
        # Coverage") -- the original an earlier revision pattern, unchanged, so
        # every existing single-level fixture keeps parsing exactly as
        # before.
        re.compile(r"^(?P<id>\d+(?:\.\d+)*)\.\s+(?P<heading>.+)$"),
    ),
    (
        "numeric",
        # Letter-dot-number numbering ("A.1 ...", "A.1.2 ...").
        re.compile(r"^(?P<id>[A-Za-z]\.\d+(?:\.\d+)*)\s+(?P<heading>.+)$"),
    ),
    (
        "lettered",
        re.compile(r"^\((?P<id>[a-zA-Z])\)\s+(?P<heading>.+)$"),
    ),
    (
        "lettered",
        # Chained parenthetical numbering ("(4)(a) ...").
        re.compile(r"^(?P<id>\(\d+\)\([a-zA-Z]\))\s+(?P<heading>.+)$"),
    ),
    (
        "roman",
        re.compile(r"^(?P<id>[IVXLCDM]+)\.\s+(?P<heading>.+)$"),
    ),
    (
        "roman",
        # Multi-letter paren-roman numbering ("(ii)", "(III)", "(iv)") --
        # see policydiff/enumerators.py's module docstring. Unconditional
        # (not gated by adjacency) since the enclosing parens already make
        # the shape unambiguous with ordinary prose -- unlike the BARE
        # letter/lowercase-roman forms handled separately in segment()
        # below, which lack that structural disambiguator.
        PAREN_ROMAN_RE,
    ),
]

# an earlier revision's root fix: heading detection must run BEFORE sentence
# atomization and must be ROBUST + SYMMETRIC, so a heading line is
# ALWAYS recognized as its own zero-body atom (never glued onto the
# following prose sentence by sentence.py) and parsed identically
# regardless of which side of a diff it's on.
#
# Two heading shapes are recognized, both emitted as kind "section":
#
#   1. Keyword-cued: "SECTION <id>" / "ARTICLE <id>", optionally
#      followed by a separator ("--", em/en-dash, ":", "-") and a
#      short title, e.g. "SECTION A -- DEFINITIONS", "SECTION 4 --
#      EXCLUSIONS", "SECTION 1", "SECTION 1 (renamed)", "ARTICLE III
#      -- CONDITIONS". <id> may be a roman numeral, a plain number, or
#      a single letter -- the OLD pattern only accepted roman/digit,
#      which silently failed to recognize "SECTION A" at all and let
#      it glue onto the next sentence as ordinary prose.
#   2. Bare title line: a SHORT (<=8 words) line with no terminal
#      sentence punctuation that is either ALL-CAPS ("DEFINITIONS") or
#      Title-Case with a heading-style separator ("Coverage A --
#      Bodily Injury"). This is intentionally conservative -- a real
#      coverage sentence almost always ends in '.', '?' or '!' and/or
#      is not uniformly capitalized, so it is never misclassified as a
#      heading and dropped (see the guard regression test for "No
#      coverage for flood." / "Deductible $500.").
_SECTION_KEYWORD_RE = re.compile(
    r"^(?:SECTION|ARTICLE)\s+(?P<id>[A-Za-z0-9]+)(?:\s+(?P<rest>.+))?$",
    re.IGNORECASE,
)
_HEADING_SEP_RE = re.compile(r"^[\-–—:]+\s*(.*)$")
_MAX_KEYWORD_REST_WORDS = 10

# an earlier revision tried to make bare-ALL-CAPS heading SHAPE detection also do
# CONTENT filtering (a coverage-word + copula/negation check) so that a
# real coverage determination written in short, unpunctuated, all-caps
# style ("MOLD DAMAGE IS COVERED") would not be swallowed into a
# zero-body "section" clause and silently discarded by report.py's
# heading suppression.
#
# an earlier revision root cause A: that content check was itself the fragile
# mechanism -- three rounds in a row (r4 glued headings, r5 keyed on
# caps+no-period, r6 on the exact boundary: "EARTHQUAKE EXCLUDED" has no
# copula, "THIS POLICY EXCLUDES FLOOD" has a verb but no copula,
# "Windstorm Deductible: $2,500" is Title-Case-with-colon and never even
# reached the coverage check, "Flood: Excluded" likewise) kept finding a
# new surface shape the surface-form gate didn't anticipate.
#
# Per "delete-the-mechanism-after-two-high-defects": segmentation here
# goes back to being PURE SURFACE FORM (is this line short/unpunctuated/
# uniformly-capitalized enough to be heading-SHAPED?) and carries no
# opinion about content at all. Content is what determines whether a
# heading-shaped CHANGE gets suppressed or reported -- that decision now
# lives in report.py's content-delta check (_is_coverage_bearing),
# applied to the actual Finding text on either side, regardless of which
# surface shape produced the atom. See report.py's module docstring.


def _clean_heading_text(rest: str | None) -> str:
    """Strip a leading run of separator characters ("--", an em/en-dash,
    ":", "-") plus surrounding whitespace from a keyword-header's raw
    trailing text -- symmetric and total, unlike the old single-char
    separator-class regex, which left a second literal "-" glued onto
    the heading for a "--" (double-dash) separator (the cite-fragment
    bug, e.g. "- EXCLUSIONS" instead of "EXCLUSIONS")."""
    if not rest:
        return ""
    rest = rest.strip()
    m = _HEADING_SEP_RE.match(rest)
    if m:
        return m.group(1).strip()
    return rest


def _is_heading_shaped_rest(rest: str | None) -> bool:
    """True if a keyword header's trailing text still LOOKS like a
    heading title -- no terminal sentence punctuation, and short --
    rather than the start of an ordinary sentence that merely happens
    to begin with the word "Section"/"Article" (e.g. "Section 3
    imposes additional duties on the insured.")."""
    if rest is None:
        return True
    rest = rest.strip()
    if not rest:
        return True
    if rest[-1] in ".?!":
        return False
    if len(rest.split()) > _MAX_KEYWORD_REST_WORDS:
        return False
    return True


def _is_bare_heading_line(stripped: str) -> bool:
    """True for a short, unpunctuated, uniformly-capitalized line that
    looks like a heading on its own (no SECTION/ARTICLE keyword) --
    e.g. "DEFINITIONS" or "Coverage A -- Bodily Injury".

    an earlier revision's root fix: this is now a thin wrapper around
    sentence.is_heading_shaped_line(), the SAME surface-form test
    sentence.py's unnumbered-prose grouper uses to decide whether an
    unfinished physical line is a distinct heading-shaped item or an
    ordinary hard-wrap continuation (see that module's docstring) --
    sharing one implementation instead of two independently-maintained
    copies is what keeps segmentation's heading detection and prose
    line-grouping's continuation-boundary detection from ever drifting
    apart on the same input."""
    return is_heading_shaped_line(stripped)


def _match_section(line: str, heading_counter: list[int]):
    """Return (id, heading_text) if *line* is a recognized heading of
    either shape, else None. *heading_counter* is a 1-element mutable
    list used to synthesize a stable id for bare (no explicit id)
    headings."""
    stripped = line.strip()
    if not stripped:
        return None
    m = _SECTION_KEYWORD_RE.match(stripped)
    if m:
        rest = m.group("rest")
        if _is_heading_shaped_rest(rest):
            return m.group("id"), _clean_heading_text(rest)
        return None
    if _is_bare_heading_line(stripped):
        heading_counter[0] += 1
        return f"§{heading_counter[0]}", stripped
    return None


def _match_header(line: str):
    stripped = line.strip()
    if not stripped:
        return None
    for kind, pat in _PATTERNS:
        m = pat.match(stripped)
        if m:
            return kind, m
    return None


def _content_hash(text: str) -> str:
    # Local import to avoid a hard cycle at module load time; normalize.py
    # does not import segment.py, so this is safe, but keep it lazy anyway.
    from .normalize import normalize

    return hashlib.sha256(normalize(text, suppress_cosmetic=True).encode("utf-8")).hexdigest()[:16]


def segment(text: str) -> list[Clause]:
    """Parse *text* into an ordered list of :class:`Clause`."""
    lines = text.split("\n")
    clauses: list[Clause] = []
    current: dict | None = None          # open numeric/lettered/roman clause
    order_index = 0
    unnumbered_counter = 0
    prose_buffer: list[str] = []
    scope_heading = ""                   # nearest preceding SECTION heading

    def flush_current():
        nonlocal current, order_index
        if current is None:
            return
        body_lines = current["lines"]
        while body_lines and body_lines[0] == "":
            body_lines.pop(0)
        while body_lines and body_lines[-1] == "":
            body_lines.pop()
        raw_text = "\n".join(body_lines).strip()
        # Root fix: collapse ALL internal whitespace
        # (physical line breaks, blank lines, runs of spaces) to single
        # spaces for the canonical `text` -- see the module docstring.
        # This is what makes the clause's atom content independent of
        # exactly where a physical line break falls within its body.
        # `text_raw` keeps the original layout for a caller comparing
        # with cosmetic suppression disabled (see Clause's docstring).
        collapsed_text = re.sub(r"\s+", " ", raw_text).strip()
        clause = Clause(
            id=current["id"],
            kind=current["kind"],
            heading=current["heading"],
            text=collapsed_text,
            order_index=order_index,
            text_raw=raw_text if raw_text != collapsed_text else "",
        )
        clause.content_hash = _content_hash(clause.text)
        clauses.append(clause)
        order_index += 1
        current = None

    def flush_prose():
        # UNNUMBERED prose (preamble, whole unnumbered document, or the
        # body sitting under a SECTION header) becomes one clause PER
        # SENTENCE, never per blank-line block -- so a pure blank-line
        # re-partition of the exact same sentences can never change the
        # clause set (see policydiff/sentence.py).
        nonlocal order_index, unnumbered_counter, prose_buffer
        if not prose_buffer:
            return
        raw_lines = prose_buffer
        prose_buffer = []
        collapsed_chunks = group_prose_lines(raw_lines)
        raw_chunks = group_prose_lines_raw(raw_lines)
        for collapsed_chunk, raw_chunk in zip(collapsed_chunks, raw_chunks):
            sentences = split_sentences(collapsed_chunk)
            raw_sentences = split_sentences_raw(raw_chunk)
            if len(raw_sentences) != len(sentences):
                # Should not happen (both splitters walk the same boundary
                # sequence over the same word content, differing only in
                # which whitespace character separates two sentences) --
                # fail safe rather than mis-pair a raw sentence to the
                # wrong collapsed one.
                raw_sentences = sentences
            for sentence, raw_sentence in zip(sentences, raw_sentences):
                unnumbered_counter += 1
                clause = Clause(
                    id=f"¶{unnumbered_counter}",
                    kind="paragraph",
                    heading=scope_heading,
                    text=sentence,
                    order_index=order_index,
                    text_raw=raw_sentence,
                )
                clause.content_hash = _content_hash(clause.text)
                clauses.append(clause)
                order_index += 1

    # Pre-scan for BARE (unparenthesized) single-letter/lowercase-roman
    # enumerator candidates ("A.", "a.", "i.", "iii.") -- see
    # policydiff/enumerators.py's module docstring for why these need a
    # sequence-adjacency confirmation pass that every OTHER marker style
    # (arabic, paren-alnum, paren-roman, uppercase-roman) does not: they
    # are the only shapes that collide with a genuine English
    # abbreviation/initial ("No. 5", "J. Smith") at the start of a
    # physical line. `claimed_ids` excludes every line an existing,
    # unconditional pattern already recognizes (numeric/paren-lettered/
    # uppercase-roman/paren-roman) from re-candidacy, while still letting
    # its id anchor an adjacency decision for a neighboring bare
    # candidate (e.g. bare "B." sitting next to an already-claimed
    # roman "C.").
    clean_lines = [ln.rstrip("\r") for ln in lines]
    claimed_ids: dict[int, str] = {}
    for i, ln in enumerate(clean_lines):
        m = _match_header(ln)
        if m is not None:
            claimed_ids[i] = m[1].group("id")
    confirmed_bare = confirmed_bare_alpha_line_indices(clean_lines, claimed_ids)

    heading_counter = [0]
    for line_idx, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r")
        # NUMBERED / ROMAN / LETTERED headers are checked first -- they
        # are unambiguous (a leading "N.", roman numeral + ".", or
        # "(a)") and their own heading text is free-form prose (e.g.
        # "2. Coverage B -- Medical Payments"), so a numbered item's
        # heading line must never be reinterpreted as a bare SECTION
        # heading just because it happens to be short and Title-Case.
        matched = _match_header(line)
        if matched is None and line_idx in confirmed_bare:
            # A bare letter/lowercase-roman candidate whose sequence
            # adjacency to some OTHER bare candidate elsewhere in the
            # document confirms it as a real enumerator label, not an
            # abbreviation/initial -- see confirmed_bare_alpha_line_indices.
            bare_m = BARE_ALPHA_DOT_RE.match(line.strip())
            if bare_m is not None:
                bare_id = bare_m.group("id")
                bare_kind = "roman" if roman_value(bare_id) is not None else "lettered"
                matched = (bare_kind, bare_m)
        if matched:
            kind, m = matched
            cid = m.group("id")
            heading = (m.groupdict().get("heading") or "").strip()
            flush_prose()
            flush_current()
            current = {
                "id": cid,
                "kind": kind,
                "heading": heading,
                "lines": [heading] if heading else [],
            }
            continue

        section_match = _match_section(line, heading_counter)
        if section_match is not None:
            # A heading line -- keyword-cued ("SECTION A -- DEFINITIONS")
            # or bare ("DEFINITIONS") -- carries no coverage content of
            # its own: close out whatever numbered clause and/or
            # unnumbered prose run preceded it, emit the header as its
            # own zero-body clause BEFORE any sentence atomization runs
            # (so it is never glued onto the following coverage
            # sentence -- see policydiff/sentence.py), and let
            # everything after it (until the next header of any kind)
            # accumulate as unnumbered prose scoped to this heading.
            cid, heading = section_match
            flush_current()
            flush_prose()
            clause = Clause(
                id=cid,
                kind="section",
                heading=heading,
                text=heading,
                order_index=order_index,
            )
            clause.content_hash = _content_hash(clause.text)
            clauses.append(clause)
            order_index += 1
            scope_heading = heading
            continue

        if current is not None:
            # Root fix: a physical line inside an
            # open numbered/roman/lettered clause is ALWAYS absorbed into
            # its body, unconditionally, whether or not the clause's own
            # last line already looks like a complete sentence -- there is
            # no per-line "is this still in progress" gate any more (see
            # the module docstring for why that gate broke reflow
            # invariance). The clause keeps absorbing lines until the next
            # enumerator/heading line (matched above, before this branch
            # is ever reached) or EOF. A blank line is absorbed the same
            # way -- it collapses away in flush_current()'s whitespace
            # normalization regardless.
            stripped_line = line.strip()
            current["lines"].append(stripped_line)
        else:
            prose_buffer.append(line)
    flush_current()
    flush_prose()
    return clauses
