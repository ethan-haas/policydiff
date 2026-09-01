"""Split a block of UNNUMBERED prose into sentence-level atoms.

This is an earlier revision's root fix: an earlier revision made unnumbered content diffable by
segmenting it into "paragraph" clauses at BLANK-LINE boundaries
(segment.py); an earlier revision patched the fallout (blank-line re-partitioning
changing the clause SET) with a whole separate reconciliation pass
(reconcile.py) that operated on "paragraph runs". That reconciliation
pass was itself only a partial fix -- it only recognized a narrow set of
shapes (identical-run cosmetic collapse, and a single old paragraph
splitting 1:many with a positional line match) and broke on anything
else: a merge that drops a whole sentence, a sentence that moves across
a structural boundary (e.g. a section header), a split where the pieces
don't line up 1:1 with the old clause's own physical lines, etc.

The actual invariant a re-partition-proof design needs is: the ATOM used
for alignment and classification must be stable under "how many blank
lines / newlines separate two sentences" -- i.e. the atom must be the
SENTENCE, not the blank-line-delimited block. Once sentences are the
atom, blank-line/paragraph regrouping never changes the atom SET at all
(splitting or merging blank-line blocks is purely a boundary op on
whitespace BETWEEN sentences, never on the sentences themselves), so the
existing content-similarity alignment (align.py) and classification
(classify.py) handle every re-partition shape uniformly, with no special
"paragraph run" machinery required.

The splitter is deliberately simple and conservative: it only splits on
'.', '!', '?' immediately followed by whitespace and then an uppercase
letter, digit, or opening quote -- and even then, not if the token
immediately before the punctuation is a known abbreviation, or is a
single letter (an initial, e.g. "J. Smith"). Critically, requiring
whitespace *immediately* after the punctuation means a decimal number
like "$1,000.00" (no space before the trailing "00") is never a split
candidate at all -- only an actual sentence boundary (period, then a
space, then the next sentence) is.
"""
from __future__ import annotations

import re

# Common abbreviations whose trailing "." must never be treated as a
# sentence boundary, even when followed by whitespace + a capitalized
# word (e.g. "U.S. Government agencies ..." or "See Endorsement No. 5").
# Keys are lowercased with internal periods preserved (so "U.S" and
# "e.g" match the token exactly as extracted below).
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "inc", "co", "corp", "ltd", "llc", "no", "vol", "fig", "dept",
    "assn", "approx", "gen", "rev", "art", "sec", "para", "pp",
    "e.g", "i.e", "u.s", "u.k", "a.m", "p.m",
}

# A candidate sentence boundary: sentence-ending punctuation, an optional
# closing quote/paren, one-or-more whitespace, then something that can
# start a new sentence (uppercase letter, digit, opening quote/paren, or a
# "$" amount -- an earlier revision's root fix: a dollar-amount sentence routinely
# opens a policy statement outright ("...are covered. $1,000,000 is the
# most we will pay..."), and without "$" in this class the boundary regex
# never even considered a split there, silently fusing a genuinely
# standalone "$"-led sentence onto whatever preceded it regardless of the
# terminal punctuation already present -- see group_prose_lines() below
# for the sibling fix on the no-terminal-punctuation continuation path).
_BOUNDARY_RE = re.compile(r'([.!?])(["\')\]]*)(\s+)(?=[A-Z0-9$"\'(“‘])')

_TRAILING_WORD_RE = re.compile(r"(\S+)$")


def _is_guarded(text: str, period_index: int) -> bool:
    """True if the '.'/'.!?' at *period_index* must NOT be treated as a
    sentence boundary -- either because the token right before it is a
    known abbreviation, or because it's a single-letter initial."""
    before = text[:period_index]
    m = _TRAILING_WORD_RE.search(before)
    if not m:
        return False
    token = m.group(1).strip("\"'([{")
    token_l = token.lower()
    if token_l in _ABBREVIATIONS:
        return True
    # A lone letter immediately before the period ("J. Smith", "A. Co.")
    # is almost always an initial, not a sentence end.
    if len(token) == 1 and token.isalpha():
        return True
    return False


_SENTENCE_END_CHARS = ".!?\"'”’)"


def _ends_sentence(line: str) -> bool:
    line = line.rstrip()
    return bool(line) and line[-1] in _SENTENCE_END_CHARS


_CONTINUATION_START_RE = re.compile(r"^[a-z$0-9]")


def _is_continuation_start(line: str) -> bool:
    """True if *line* looks like it continues the sentence begun on the
    physical line before it -- starts with a LOWERCASE LETTER, a `$`, or a
    digit (clearly an ordinary word/amount continuing mid-sentence, e.g.
    "is $1,000,000.", "of insurance ...", "insurance is\\n$1,000,000 under
    this policy."), as opposed to an UPPERCASE-initial NEW item (a fresh
    ALL-CAPS statement like "WAR EXCLUDED", or an ordinary Title-Case
    sentence start), which must never be silently fused onto the line
    before it -- see group_prose_lines() below.

    an earlier revision restricted this trigger to a bare lowercase letter, reasoning
    that `$`/digit-initial lines are ambiguous between "mid-sentence
    continuation" and "standalone sentence that happens to open with an
    amount" (e.g. "$1,000,000 is the most we will pay under this
    policy."). That restriction over-corrected: this function is only
    ever consulted from group_prose_lines() when the CURRENT (preceding)
    physical line does NOT already end with terminal punctuation ('.',
    '!', '?') -- see _ends_sentence() -- so the ambiguous case (a
    genuinely standalone "$"/digit-led sentence following one that
    already ends in '.') never reaches this function at all: it always
    flushes as its own atom regardless of what the next line starts with.
    A $/digit-initial NEXT line therefore only ever gets consulted here
    when the PREVIOUS line is provably incomplete, in which case it is
    always a genuine continuation, never a new sentence -- so it is safe,
    and in fact necessary, to treat it as one. Without it, a sentence that
    happens to wrap immediately before its own trailing "$" amount ("The
    aggregate limit of insurance is\\n$1,000,000 under this policy.")
    split into two atoms on one side of a diff while an equivalent rewrap
    ("The aggregate limit of insurance\\nis $1,000,000 under this
    policy.") stayed one atom on the other -- a pure line-break move
    manufacturing a phantom finding. The uppercase-
    initial guard (never matched by this regex) is what still keeps the
    genuine reorder/two-distinct-items cases correct: those sentences all
    end with terminal punctuation on their own line, so _ends_sentence()
    is already True and this continuation check never even runs for
    them."""
    line = line.lstrip()
    return bool(line) and bool(_CONTINUATION_START_RE.match(line))


# an earlier revision's root fix: a hard line-wrap
# of ordinary UNNUMBERED PROSE was still splitting one real sentence into
# multiple atoms whenever the wrap happened to land immediately before a
# capitalized word -- extremely common in real policy forms, which are
# hard-wrapped at ~70-80 columns and dense with capitalized defined terms
# ("Insured", "Company", "Declarations", "Commercial Property Coverage
# Part"). _is_continuation_start()'s lowercase/$/digit-only trigger (round
# 7/8, see above) was deliberately narrow so that two genuinely distinct
# ALL-CAPS items on consecutive lines ("FLOOD EXCLUDED" / "WAR EXCLUDED")
# never fused -- but that same narrowness meant an ordinary, unfinished
# mixed-case sentence ("This endorsement modifies insurance provided
# under the") followed by its own capitalized continuation ("Commercial
# Property Coverage Part.") was ALSO treated as two distinct items and
# hard-flushed apart, producing a phantom [MODIFIED]+[ADDED] pair out of
# a pure line-wrap (see repro in the module docstring's cross-reference
# below and the matching regression test).
#
# The actual invariant, matching numbered-clause bodies since an earlier revision:
# a hard wrap must never change the sentence atom set. The join decision
# cannot key off what the NEXT line starts with (that conflated "a
# proper noun/defined term continues the sentence" with "a fresh
# standalone item begins") -- it must key off what the CURRENT
# (unfinished) line, and the NEXT line, each individually LOOK LIKE:
#
#   * A line that is HEADING-SHAPED -- short, unpunctuated, and either
#     ALL-CAPS or Title-Case-with-separator (the exact surface-form test
#     segment.py already uses to recognize a bare section heading, see
#     is_heading_shaped_line() below, shared rather than duplicated so
#     the two call sites can never drift) -- is always its OWN atom. It
#     never absorbs the following line as a continuation (it is a
#     complete, self-contained item even without terminal punctuation),
#     and it is never absorbed BY a normal prose line before it either
#     (see the loop in _group_prose_chunks): joining an unfinished
#     ordinary sentence onto what is structurally a distinct heading-
#     shaped item would be exactly the wrong call.
#   * Any other unfinished line is ordinary prose -- a genuine hard-wrap
#     continuation of the same sentence -- and joins the line that
#     follows UNCONDITIONALLY, regardless of whether that next line
#     starts uppercase or lowercase, because a capitalized defined term
#     or proper noun routinely opens the continuation.
#
# This supersedes _is_continuation_start() as the join gate in
# _group_prose_chunks (kept above, still exported, since an earlier revision/8's
# narrower lowercase/$/digit semantics remain independently documented
# and exercised at the unit level by test_round6/7/8_regression.py) --
# the new gate is a strict widening for a normal current line (it now
# joins on an uppercase-but-not-heading-shaped next line too) while
# staying exactly as narrow as before for a heading-shaped current OR
# next line, which is what keeps every existing all-caps guard passing
# unchanged.
_MAX_HEADING_WORDS = 8
_HEADING_TITLE_SEP_CHARS = ("–", "—", ":")


def is_heading_shaped_line(line: str) -> bool:
    """True for a short, unpunctuated line that LOOKS like a heading/
    distinct-item on its own -- e.g. "DEFINITIONS", "FLOOD EXCLUDED", or
    "Coverage A -- Bodily Injury". Pure surface form, no content opinion
    (an earlier revision's "delete-the-mechanism-after-two-high-defects" lesson
    applies here just as it did to segment.py's own bare-heading
    detector, which this mirrors byte-for-byte -- see segment.py's
    _is_bare_heading_line, which now delegates here so the two never
    drift apart)."""
    stripped = line.strip()
    if not stripped or stripped[-1] in ".?!":
        return False
    words = stripped.split()
    if not words or len(words) > _MAX_HEADING_WORDS:
        return False
    letters = [ch for ch in stripped if ch.isalpha()]
    if not letters:
        return False
    if all(ch.isupper() for ch in letters):
        return True
    if any(sep in stripped for sep in _HEADING_TITLE_SEP_CHARS):
        if all(w[0].isupper() for w in words if w[0].isalpha()):
            return True
    return False


# A schedule/declarations-page row ("Each Occurrence Limit $1,000,000",
# "General Aggregate Limit: $2,000,000") is a complete, if elliptical,
# label+amount ASSERTION on its own -- it never needs a following
# physical line to complete it, even though it carries no terminal
# sentence punctuation (an earlier revision's fixture class). Such a row's own last
# token is the amount itself; that is what tells it apart from an
# ordinary prose line that merely happens to break, unfinished, before a
# capitalized word (an earlier revision's repro: "...under the" / "Commercial
# Property Coverage Part."). Anchored so a trailing "." (already
# excluded by the _ends_sentence() check upstream) or "%" doesn't defeat
# the match, and requires the token to be genuinely numeric (at least
# one digit) so an ordinary word is never mistaken for an amount.
_AMOUNT_TAIL_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?$")


def _ends_with_amount(line: str) -> bool:
    """True if the LAST whitespace-delimited token of *line* looks like a
    dollar amount, bare number, or percentage -- see _AMOUNT_TAIL_RE."""
    stripped = line.strip()
    if not stripped:
        return False
    last_token = stripped.rsplit(None, 1)[-1]
    return bool(_AMOUNT_TAIL_RE.fullmatch(last_token))


def group_prose_lines(raw_lines: list[str]) -> list[str]:
    """Group physical *raw_lines* of unnumbered prose (blank lines
    included) into logical chunks to hand to :func:`split_sentences`.

    an earlier revision's root fix: a real insurance
    form sometimes states coverage in short, standalone lines with NO
    terminal punctuation at all ("MOLD DAMAGE IS COVERED", "DEDUCTIBLE
    IS $500", one statement per physical line). Simply joining the whole
    unnumbered-prose run with a single space (as an earlier revision originally did)
    and handing it to the punctuation-only splitter glues every such
    line into ONE giant "sentence" when none of them end in '.'/'!'/'?'
    -- corrupting alignment (a single-line removal reads as a
    substitution of the whole block) and classification (multiple
    unrelated $ amounts and keywords collide in one Finding).

    Consecutive lines that DO end in sentence-final punctuation are
    still joined into one run and handed to split_sentences() together,
    UNCHANGED from an earlier revision's behavior -- physical line/blank-line
    boundaries between already-punctuated sentences carry no meaning
    (this is what keeps blank-line reflow a no-op on the atom set, and
    keeps the abbreviation guard in split_sentences -- "Acme Corp." not
    splitting mid-name -- working identically regardless of which
    physical line the following sentence happens to start on).

    an earlier revision root cause B fix: a line with NO trailing sentence
    punctuation of its own does NOT automatically force a hard flush
    right after it anymore. A genuinely wrapped sentence ("The aggregate
    limit of insurance\\nis $1,000,000.") re-wrapped at a different word
    ("The aggregate limit of\\ninsurance is $1,000,000.") is the SAME
    sentence with the line break moved -- flushing on physical-line shape
    made the atom SET depend on exactly where the wrap fell, producing
    two phantom [MODIFIED] findings out of a pure reflow. The fix: only
    flush an unpunctuated line if the NEXT physical line does NOT look
    like a continuation of it (does not start with a lowercase letter or
    a digit/`$` -- see _is_continuation_start). Two genuinely distinct
    unpunctuated items ("FLOOD EXCLUDED" / "WAR EXCLUDED") still each
    flush as their own atom, because the second line starts with an
    uppercase letter, not a continuation.
    """
    return [" ".join(chunk) for chunk in _group_prose_chunks(raw_lines)]


def group_prose_lines_raw(raw_lines: list[str]) -> list[str]:
    """Same chunk boundaries as :func:`group_prose_lines`, but joined with
    the original newline between physical lines instead of collapsing to
    a single space.

    an earlier revision's root fix: normal sentence-atomization
    (this module) runs unconditionally at segmentation time, before the
    ``suppress_cosmetic`` toggle is even in scope -- so a pure line-wrap
    reflow of unnumbered prose was UNRECOVERABLY collapsed into identical
    text on both sides before classify.py ever got a chance to honor
    ``--no-suppress-cosmetic``. This raw-joined variant preserves exactly
    which physical line each word fell on, so segment.py can hand
    classify.py a text that still differs across a pure rewrap when the
    caller has asked to see cosmetic-only deltas, while the ordinary
    (space-joined) ``text`` used for every other purpose -- default
    comparison, citation quoting, alignment -- is completely unaffected."""
    return ["\n".join(chunk) for chunk in _group_prose_chunks(raw_lines)]


def _group_prose_chunks(raw_lines: list[str]) -> list[list[str]]:
    lines = [raw.strip() for raw in raw_lines if raw.strip()]
    chunks: list[list[str]] = []
    buf: list[str] = []

    def _flush():
        if buf:
            chunks.append(list(buf))
            buf.clear()

    for i, line in enumerate(lines):
        buf.append(line)
        if _ends_sentence(line):
            continue
        if is_heading_shaped_line(line):
            # an earlier revision's root fix: a heading-shaped line ("FLOOD
            # EXCLUDED", "DEFINITIONS") is always its own complete atom,
            # even though it has no terminal punctuation -- it never
            # absorbs the following line as a continuation.
            _flush()
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is not None and _is_continuation_start(nxt):
            # an earlier revision/8's original trigger, unchanged: L+1 starts with a
            # lowercase letter, "$", or a digit -- an unambiguous
            # mid-sentence continuation (see _is_continuation_start).
            continue
        if (
            nxt is not None
            and not _ends_with_amount(line)
            and not is_heading_shaped_line(nxt)
        ):
            # an earlier revision's root fix: L
            # (ordinary, unfinished prose) has no terminal punctuation of
            # its own, does NOT end in a schedule-row-style amount (the
            # ONE shape a bare, unpunctuated line is still allowed to be
            # a COMPLETE assertion on its own -- see _ends_with_amount
            # and an earlier revision's fixture class), and L+1 is not a distinct
            # heading-shaped item either -- so L+1 must be a hard-wrap
            # continuation of the SAME sentence, regardless of whether it
            # happens to start uppercase (a capitalized defined term /
            # proper noun, e.g. "...under the" / "Commercial Property
            # Coverage Part.") or lowercase. Keep buffering so a
            # formatting-only rewrap of the SAME sentence always joins
            # back to identical text, wherever the physical line break
            # falls. A line that DOES end in an amount ("Each Occurrence
            # Limit $1,000,000") is left to the ordinary flush path below
            # -- it is a complete row in its own right, and two such rows
            # sitting on consecutive physical lines with no punctuation
            # anywhere (a declarations/schedule listing) must never be
            # fused just because the next row also starts uppercase.
            continue
        _flush()
    _flush()
    return chunks


def ends_sentence(line: str) -> bool:
    """Public wrapper around :func:`_ends_sentence` -- an earlier revision's root
    fix: segment.py needs the EXACT SAME
    "does this physical line already terminate a sentence" test it uses
    for unnumbered prose to also gate whether a physical line FOLLOWING
    a numbered/roman/lettered clause header is a genuine wrapped
    continuation of that clause's body, or a fresh standalone sentence
    that must be atomized on its own (see segment.py's segment(),
    _last_nonblank / the "current is not None" branch). Exposed here
    rather than duplicated so the two call sites can never drift.

    Unlike unnumbered prose's continuation join, segment.py deliberately
    does NOT also require the next line to look like a lowercase/$/digit
    continuation (:func:`_is_continuation_start`) before absorbing it
    into an open numbered/roman/lettered clause: a real multi-line
    clause body legitimately resumes mid-sentence with any character at
    all (an opening quote mark on a quoted defined term is common --
    see tests/fixtures/policy_old_noise.txt), and the explicit clause
    NUMBER already establishes that the lines belong together while the
    clause's own sentence is still incomplete. The symmetric other half
    of the fix -- once a line DOES end with terminal punctuation, the
    very next physical line is always evaluated fresh and breaks out on
    its own if it doesn't extend that sentence -- is what actually fixes
    the defect (see the module docstring)."""
    return _ends_sentence(line)


def sentence_boundary_starts(text: str) -> list[int]:
    """Character offsets into *text* AS GIVEN (no whitespace-collapsing,
    so offsets line up with the caller's own string) marking where a NEW
    sentence starts, per the exact same boundary regex + abbreviation/
    initial guard as :func:`split_sentences_raw`.

    Root fix: classify.py's monetary-amount
    ROLE propagation (see _money_roles' docstring there) must reset at a
    genuine sentence boundary, not just at ';' -- but a numbered/lettered
    CLAUSE's body text can legitimately hold more than one sentence
    ("A deductible of $500 applies. The Company will pay $1,000,000..."),
    so that reset can't be detected at the document-segmentation level
    (this module otherwise only atomizes UNNUMBERED prose into separate
    clauses in the first place). Exposing the same boundary detector used
    there lets classify.py find sentence starts WITHIN one clause's text
    without duplicating (and risking drifting from) the abbreviation/
    decimal/initial guard logic that already makes it safe -- a decimal
    point ("$500.40") never matches (no whitespace follows it), and
    neither does an abbreviation ("No.", "U.S.") or a single-letter
    initial ("J. Smith"), for exactly the reasons documented above.
    """
    positions: list[int] = []
    for m in _BOUNDARY_RE.finditer(text):
        period_index = m.start(1)
        if _is_guarded(text, period_index):
            continue
        positions.append(m.end(3))
    return positions


def split_sentences(text: str) -> list[str]:
    """Split *text* (already whitespace-collapsed or not -- both are
    handled) into a list of trimmed, non-empty sentence strings.

    Internal newlines/runs of whitespace are collapsed to a single space
    first, since sentence boundaries are a punctuation property, not a
    layout property (reflow/line-wrap must never change the sentence
    set)."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return []

    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(collapsed):
        period_index = m.start(1)
        if _is_guarded(collapsed, period_index):
            continue
        end = m.start(3)  # start of the whitespace run == end of sentence
        sentence = collapsed[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = m.end(3)
    tail = collapsed[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def split_sentences_raw(text: str) -> list[str]:
    """Same sentence-boundary algorithm as :func:`split_sentences`, but
    WITHOUT the leading whitespace-collapse -- internal newlines/runs of
    whitespace inside *text* are left exactly as found.

    Used only to build each sentence clause's ``text_raw`` (see
    segment.py / classify.py) so that a pure line-wrap reflow of the same
    sentence set is still visible as a text difference when the caller
    has disabled cosmetic suppression (``--no-suppress-cosmetic``); the
    ordinary whitespace-collapsed ``text`` field used everywhere else is
    unaffected. The boundary regex and the abbreviation/initial guard
    both only look at the punctuation mark and the token immediately
    before/after it, so they behave identically whether the whitespace
    between sentences is a single space or an embedded newline -- the
    same sequence of sentences (same words, same count) comes out of
    both functions for the same underlying content."""
    text = text.strip()
    if not text:
        return []

    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(text):
        period_index = m.start(1)
        if _is_guarded(text, period_index):
            continue
        end = m.start(3)
        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = m.end(3)
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences
