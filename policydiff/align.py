"""Align clauses across two document versions by CONTENT similarity, not by
clause number or position.

Produces:
    pairs         -- list[(old_clause, new_clause, score)]
    unmatched_old -- list[old_clause]   (candidate "removed")
    unmatched_new -- list[new_clause]   (candidate "added")

Similarity is word-shingle Jaccard over a lowercased, whitespace-collapsed
token stream (deliberately independent of the cosmetic-suppression toggle
in normalize.py -- alignment must keep working even when the toggle used
for *classification* is flipped off).

Matching is greedy-best-first: score every old/new pair, sort descending,
and take pairs above ``threshold`` in that order as long as both sides are
still free. This is not a Hungarian assignment (no global-optimum
guarantee) but it is deterministic and, for the sparse near-1-to-1 case
that policy-form revisions actually produce, converges to the same result
as an exact assignment in every case exercised by the test suite.

3-word shingles are precise for ordinary-length clauses, but on a SHORT
clause a single edited word can flip most of its shingles at once (a
6-word clause only has 4 shingles total), so a genuinely-paired edit can
fall below ``threshold`` and get reported as an unrelated remove+add
instead of a modified pair -- losing direction and both-side citation.
A second pass re-scores whatever is left unmatched after the primary
pass using plain unigram (whole-word-set) Jaccard, which is far more
forgiving of a short edit proportionally, at a stricter threshold so it
only mops up genuine near-twins rather than pairing unrelated leftover
clauses to each other.

Root fix: a monetary AMOUNT is exactly the
thing a revision is expected to CHANGE -- it is never the stable
identity of a clause -- while the row LABEL (the words around it) is.
Feeding raw numeric tokens ("1", "000", "000" out of "$1,000,000") into
the SAME token stream used for content-similarity scoring lets a
coincidentally-shared amount outscore a genuinely-shared label: two
DIFFERENT schedule rows that happen to land on the same dollar figure
after a revision (e.g. Each Occurrence raised from $1,000,000 to
$2,000,000 while General Aggregate is cut from $2,000,000 to $1,500,000
-- the raised EachOcc and the old GenAgg now literally share "$2,000,000")
scored higher against EACH OTHER than either did against its own actual
twin, producing a bogus cross-pair plus a decoupled remove+add that
disguised a real coverage cut as a brand-new "added" clause. Every
similarity function below (`_shingles`, `_word_set`) therefore strips
purely-numeric tokens out of the token stream before scoring -- a
clause's identity is judged on its non-numeric (label) content only.
This does not affect what direction is *reported* for a changed amount
(classify.py works from the untouched clause text of an already-aligned
pair); it only stops a shared number from winning or losing an alignment
pairing that the shared label should have decided.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .segment import Clause

_WORD_RE = re.compile(r"[a-z0-9]+")

# Second-pass (leftover-only) unigram similarity threshold. Comfortably
# above the word-overlap any two unrelated clauses share by coincidence
# (boilerplate phrasing like "we will pay"/"this insurance"), comfortably
# below the overlap a genuinely edited short clause keeps with its own
# twin -- see tests/test_align_short_clauses.py for the margin.
_SECOND_PASS_THRESHOLD = 0.40

# Third pass (leftover-only, terse-row) word-count ceiling. On a clause
# this short (e.g. "Deductible $500.") a single numeric edit can change
# EVERY shingle (3-word) and drag unigram Jaccard below _SECOND_PASS_
# THRESHOLD too (numbers tokenize as their own words: "500" and "1" "000"
# share nothing), so neither Jaccard pass can pair it to its own twin --
# it falls out as an unrelated remove+add, losing direction and both-side
# citation on exactly the terse deductible/sublimit rows where direction
# matters most to an underwriter. Below this many words, pair leftover
# rows structurally instead: by a shared leading LABEL token (the first
# non-numeric word -- "Deductible", "Sublimit", "Pay" -- deliberately
# NOT by proximity/score, so two different-label rows never cross-pair).
_SHORT_ROW_WORD_LIMIT = 6


def _content_words(text: str) -> list[str]:
    """Tokens used for CONTENT-similarity scoring (shingles / word-set
    Jaccard): every lowercased [a-z0-9]+ token EXCEPT purely-numeric ones
    (Root fix -- see module docstring). A monetary amount ("$1
    ,000,000" -> "1"/"000"/"000") or any other bare numeral is exactly
    the part of a schedule row expected to change between versions, so it
    must never be allowed to outweigh the row's stable LABEL words in an
    alignment-similarity score. `_word_count`/`_leading_label` (used only
    by the third, label-based pass) deliberately keep using the raw
    (numbers-included) token stream -- they already treat numeric tokens
    specially on their own terms."""
    return [w for w in _WORD_RE.findall(text.lower()) if not w.isdigit()]


def _word_set(text: str) -> set[str]:
    return set(_content_words(text))


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text.lower()))


def _leading_label(text: str) -> str | None:
    """First alphabetic (non-purely-numeric) token, case-folded -- the
    "Deductible"/"Sublimit"/"Pay" in a terse label+amount row. Used only
    to pair leftover short rows structurally when Jaccard similarity
    can't (see _SHORT_ROW_WORD_LIMIT above)."""
    for w in _WORD_RE.findall(text.lower()):
        if not w.isdigit():
            return w
    return None


def _shingles(text: str, n: int = 3) -> set[str]:
    words = _content_words(text)
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass
class AlignedPair:
    old: Clause
    new: Clause
    score: float


@dataclass
class AlignmentResult:
    pairs: list[AlignedPair]
    unmatched_old: list[Clause]
    unmatched_new: list[Clause]


def align(
    old_clauses: list[Clause],
    new_clauses: list[Clause],
    threshold: float = 0.30,
) -> AlignmentResult:
    old_shingles = [_shingles(c.text) for c in old_clauses]
    new_shingles = [_shingles(c.text) for c in new_clauses]

    candidates: list[tuple[float, int, int]] = []
    for i, os_ in enumerate(old_shingles):
        for j, ns_ in enumerate(new_shingles):
            score = jaccard(os_, ns_)
            if score >= threshold:
                candidates.append((score, i, j))

    # Deterministic ordering: score desc, then original document order so
    # ties resolve predictably instead of by dict/set iteration order.
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[AlignedPair] = []
    for score, i, j in candidates:
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        pairs.append(AlignedPair(old=old_clauses[i], new=new_clauses[j], score=score))

    unmatched_old_idx = [i for i in range(len(old_clauses)) if i not in used_old]
    unmatched_new_idx = [j for j in range(len(new_clauses)) if j not in used_new]

    # Second pass: leftover-only, unigram Jaccard, stricter threshold.
    if unmatched_old_idx and unmatched_new_idx:
        leftover_old_words = {i: _word_set(old_clauses[i].text) for i in unmatched_old_idx}
        leftover_new_words = {j: _word_set(new_clauses[j].text) for j in unmatched_new_idx}
        second_candidates: list[tuple[float, int, int]] = []
        for i in unmatched_old_idx:
            for j in unmatched_new_idx:
                score = jaccard(leftover_old_words[i], leftover_new_words[j])
                if score >= _SECOND_PASS_THRESHOLD:
                    second_candidates.append((score, i, j))
        second_candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
        for score, i, j in second_candidates:
            if i in used_old or j in used_new:
                continue
            used_old.add(i)
            used_new.add(j)
            pairs.append(AlignedPair(old=old_clauses[i], new=new_clauses[j], score=score))

    # Third pass: leftover-only, terse-row LABEL pairing. Neither Jaccard
    # pass can resolve a short label+amount row against its own twin (see
    # _SHORT_ROW_WORD_LIMIT), so group whatever's still unmatched -- and
    # short enough -- by leading label token, and pair same-label rows
    # positionally within that label group (document order on each side).
    # A label with candidates on only one side is left unmatched (nothing
    # to pair it to); a label with N candidates on each side pairs them
    # 1st-to-1st, 2nd-to-2nd, etc, deterministically.
    unmatched_old_idx = [i for i in range(len(old_clauses)) if i not in used_old]
    unmatched_new_idx = [j for j in range(len(new_clauses)) if j not in used_new]
    if unmatched_old_idx and unmatched_new_idx:
        old_by_label: dict[str, list[int]] = {}
        for i in unmatched_old_idx:
            text = old_clauses[i].text
            if _word_count(text) > _SHORT_ROW_WORD_LIMIT:
                continue
            label = _leading_label(text)
            if label is None:
                continue
            old_by_label.setdefault(label, []).append(i)

        new_by_label: dict[str, list[int]] = {}
        for j in unmatched_new_idx:
            text = new_clauses[j].text
            if _word_count(text) > _SHORT_ROW_WORD_LIMIT:
                continue
            label = _leading_label(text)
            if label is None:
                continue
            new_by_label.setdefault(label, []).append(j)

        for label, old_idxs in old_by_label.items():
            new_idxs = new_by_label.get(label)
            if not new_idxs:
                continue
            old_idxs_sorted = sorted(old_idxs, key=lambda i: old_clauses[i].order_index)
            new_idxs_sorted = sorted(new_idxs, key=lambda j: new_clauses[j].order_index)
            for i, j in zip(old_idxs_sorted, new_idxs_sorted):
                if i in used_old or j in used_new:
                    continue
                used_old.add(i)
                used_new.add(j)
                pairs.append(AlignedPair(old=old_clauses[i], new=new_clauses[j], score=0.0))

    pairs.sort(key=lambda p: p.old.order_index)
    unmatched_old = [c for i, c in enumerate(old_clauses) if i not in used_old]
    unmatched_new = [c for j, c in enumerate(new_clauses) if j not in used_new]
    return AlignmentResult(pairs=pairs, unmatched_old=unmatched_old, unmatched_new=unmatched_new)
