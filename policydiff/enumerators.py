"""Shared recognition for enumerator-label styles that are ambiguous with
ordinary prose: BARE (unparenthesized) single-letter or lowercase-roman
clause markers ("A.", "a.", "i.", "iii.") and multi-letter paren-roman
markers ("(ii)", "(IV)").

Root cause this module fixes (specification gate-2 noise false positive): the
segmenter and the cosmetic normalizer already recognize arabic ("1."),
paren-arabic ("(1)"), paren-letter ("(a)"), uppercase-roman-dot ("I.")
and dotted-decimal ("4.1") clause numbers as cosmetic anchors -- stripped
before content comparison, so pure renumbering never produces a finding.
Four sibling styles were never taught to either place: bare capital-
letter-dot, bare lowercase-letter-dot, lowercase-roman-dot, and
paren-roman. A pure relabel using one of these styles (e.g. "A,B,C" ->
"B,C,D" with byte-identical bodies) therefore compared unequal and
surfaced as a spurious "[MODIFIED (direction unclear)]" finding -- noise
that also buries any REAL change riding along in the same renumbered
clause.

Why bare single-letter/lowercase-roman markers get a DIFFERENT (gated)
treatment than every other style this codebase already normalizes: they
are the only shapes that collide, at the regex level, with genuine
English abbreviations and initials ("No. 5", "U.S. law", "J. Smith") --
"J. Smith is an additional insured." is syntactically identical to "A.
Coverage A applies." at the start of a physical line. Every other marker
style this module's siblings recognize is unambiguous on its own: a
digit, a `(...)`-wrapped token, or an uppercase-roman-only character
sequence never collides with an ordinary English sentence opener.

The single structural signal that reliably tells a real bare-letter/
bare-roman enumerator apart from an abbreviation: a genuine enumerated
list always has at least one OTHER item whose label is the immediate
alphabet/roman successor or predecessor of this one ("A." sits next to
"B."/"C."); a name initial or abbreviation never does. See
confirmed_bare_alpha_line_indices() below -- a bare match is trusted only
when a sequence-adjacent sibling exists somewhere else in the same line
set (the whole document for segment.py's clause-boundary decision, or a
single clause's own body lines for normalize.py's cosmetic-marker
stripper). An isolated singleton is left exactly as it already was
before this fix -- ordinary content, not a clause anchor -- which is
never a regression: pre-fix, none of these styles were recognized at
all.
"""
from __future__ import annotations

import re

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

_ROMAN_INT_TABLE = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def _int_to_roman(n: int) -> str:
    out = []
    for v, sym in _ROMAN_INT_TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def roman_value(s: str) -> int | None:
    """Integer value of *s* if it is a well-formed roman numeral
    (case-insensitive), else None. Round-trips through _int_to_roman to
    reject a string that merely happens to be spelled only with
    roman-numeral letters but isn't a well-formed numeral (e.g. "vx",
    "iiii")."""
    s_l = s.lower()
    if not s_l or any(ch not in _ROMAN_VALUES for ch in s_l):
        return None
    total = 0
    prev = 0
    for ch in reversed(s_l):
        v = _ROMAN_VALUES[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    if total <= 0 or _int_to_roman(total) != s_l:
        return None
    return total


# A BARE (no enclosing parens/brackets) label -- 1 to 5 letters -- followed
# by a literal "." and whitespace, at the very start of a physical line:
# "A. Coverage A applies.", "a. Fire.", "i. Fire.", "iii. Theft.". This is
# intentionally as permissive at the regex level as the existing
# paren-alnum marker (see normalize.py's _LEADING_MARKER_RE) -- the real
# guard is confirmed_bare_alpha_line_indices(), not the character class.
BARE_ALPHA_DOT_RE = re.compile(r"^(?P<id>[A-Za-z]{1,5})\.\s+(?P<heading>.+)$")
BARE_ALPHA_DOT_MARKER_RE = re.compile(r"^\s*[A-Za-z]{1,5}\.\s+")

# A roman numeral written inside parens with 2+ letters -- "(ii)", "(III)",
# "(iv)". The single-letter paren case ("(i)", "(I)") is already covered
# by segment.py's existing generic single-letter lettered pattern
# (`\(?[a-zA-Z]\)`); this is only the multi-letter roman extension, and it
# is UNCONDITIONAL (not gated) -- the enclosing parens already make the
# shape unambiguous with ordinary prose, unlike the bare form above.
PAREN_ROMAN_RE = re.compile(r"^\((?P<id>[ivxlcdmIVXLCDM]{2,5})\)\s+(?P<heading>.+)$")
PAREN_ROMAN_MARKER_RE = re.compile(r"^\s*\([ivxlcdmIVXLCDM]{2,5}\)\s+")


def _is_adjacent(a: str, b: str) -> bool:
    """True if *b* is the enumerator that immediately follows *a* --
    tried as a roman-numeral successor first (so "i" -> "ii" and "iv" ->
    "v" are recognized, including when the shorter side is a single
    character that is ALSO a valid single-letter id), then as a plain
    single-letter successor ("A" -> "B", "a" -> "b") of the SAME case."""
    ra, rb = roman_value(a), roman_value(b)
    if ra is not None and rb is not None:
        return rb == ra + 1
    if (
        len(a) == 1
        and len(b) == 1
        and a.isalpha()
        and b.isalpha()
        and a.islower() == b.islower()
    ):
        return ord(b) == ord(a) + 1
    return False


def confirmed_bare_alpha_line_indices(
    lines: list[str], claimed_ids: dict[int, str] | None = None
) -> set[int]:
    """Return the subset of *lines*' indices where a BARE_ALPHA_DOT_RE
    match at that line's start should be trusted as a real clause/list
    enumerator label, per this module's docstring.

    *claimed_ids* maps line index -> enumerator id string for every line
    some OTHER, unconditional pattern (e.g. the existing uppercase-roman
    "I."/"IV." pattern, or a numeric/paren pattern) has already matched.
    Those lines are excluded from *candidacy* entirely (a bare match on
    an already-claimed line is never reinterpreted or double-matched),
    but their id IS included as a valid adjacency ANCHOR for a
    neighboring bare candidate: a real enumerated list routinely mixes
    letters that happen to also be roman-numeral characters (already
    unconditionally claimed as "roman", e.g. "C.", "I.", "V.") with ones
    that are not ("A.", "B." sitting right next to a roman-claimed "C.")
    -- a bare candidate's confirmation must not depend on which of its
    neighbors happened to fall into the always-on roman pattern instead
    of this gated one.
    """
    claimed_ids = claimed_ids or {}
    candidates: list[tuple[int, str]] = []
    for i, raw in enumerate(lines):
        if i in claimed_ids:
            continue
        stripped = raw.rstrip("\r").strip()
        m = BARE_ALPHA_DOT_RE.match(stripped)
        if m:
            candidates.append((i, m.group("id")))

    # Every candidate is a potential adjacency anchor for every OTHER
    # candidate; every already-claimed label is also an anchor (but,
    # having no candidate index of its own, can never be excluded as
    # "comparing to itself").
    anchors: list[tuple[int | None, str]] = list(candidates)
    anchors += [(None, cid_val) for cid_val in claimed_ids.values()]

    confirmed: set[int] = set()
    for i, cid in candidates:
        for anchor_idx, oid in anchors:
            if anchor_idx == i:
                continue
            if _is_adjacent(cid, oid) or _is_adjacent(oid, cid):
                confirmed.add(i)
                break
    return confirmed
