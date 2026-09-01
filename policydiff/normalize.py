"""Cosmetic-variation model.

This is the core of the whole product: two clauses that differ ONLY in
formatting -- whitespace, line-wrapping, clause renumbering, defined-term
capitalization, quote/dash style, quote-mark PRESENCE around a defined
term -- must produce IDENTICAL normalized text.

The suppression is a single toggleable step (``suppress_cosmetic``) so it
can be proven to actually do work: run the noise fixture with the toggle
OFF and the noise test must go red (see tests/test_suppression_toggle.py).
When the toggle is off, this function performs no cosmetic suppression at
all (just a bare `.strip()`), so any formatting-only variant will compare
unequal and get reported as a "change" instead of being suppressed.
"""
from __future__ import annotations

import re

from .enumerators import (
    BARE_ALPHA_DOT_MARKER_RE,
    PAREN_ROMAN_MARKER_RE,
    confirmed_bare_alpha_line_indices,
)

_CURLY_QUOTES = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "«": '"',
    "»": '"',
}

_DASHES = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "−": "-",  # minus sign
}

# After unifying every dash-like character to ASCII "-", also collapse
# doubled/repeated hyphens ("--", a common markdown/typewriter em-dash
# stand-in) down to a single "-" so that "Coverage -- Section A" and
# "Coverage — Section A" normalize identically. Quote style is
# already folded above; dash style must be folded the same way or it
# leaks through as a cosmetic false positive.
_REPEATED_DASH_RE = re.compile(r"-{2,}")

# Leading list markers that can appear at the start of a *line* inside a
# clause body (renumbered sub-bullets): "1.", "(a)", "a)", "i.", "-", "*",
# and multi-level dotted numbering ("4.2 ", "5.1.3 ") -- the latter, like
# the single-level case, is a cosmetic clause-number anchor and must be
# stripped even when it has no trailing period before the whitespace
# (real-world forms write "4.2 Body...", not "4.2. Body...").
_LEADING_MARKER_RE = re.compile(
    r"^\s*(?:\(?[a-zA-Z0-9]{1,4}\)|\d+(?:\.\d+)+\.?|\d+\.|[-*•])\s+"
)

# Root fix: a monetary amount that differs
# ONLY in formatting -- thousands-separator commas present/absent, a
# trailing ".00"/".0" -- is a cosmetic-suppression axis exactly like
# whitespace/quote/dash style. "$1,000,000", "$1,000,000.00" and
# "$1000000" all name the SAME numeric value and must normalize
# identically; "$500.50" and "$500.00" name DIFFERENT values and must
# NOT be collapsed.
#
# Root fix: a currency-WORD amount ("$5
# million", "$1.5 billion", "$750 thousand") or a suffix-abbreviated one
# ("$50k", "$5M", "$1.5bn") names a real numeric value exactly like a
# fully-spelled-out one -- "$5 million" IS "$5,000,000", not "$5" with
# some decoration. Money-literal recognition and value computation are
# both defined ONCE here (MONEY_RE / money_value) and shared with
# classify.py (both classify.py's own amount-role/direction logic and
# this module's cosmetic-equality canonicalization use the SAME parse,
# so "$5 million" reads as 5,000,000 everywhere a dollar amount is
# compared -- never just where it happens to be convenient).
_MONEY_NUM_RE = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MONEY_MULT_RE = r"(?:million|billion|thousand|bn|k|m)"
MONEY_RE = re.compile(
    rf"\$(?P<num>{_MONEY_NUM_RE})(?:[ \t]*(?P<mult>{_MONEY_MULT_RE})\b)?",
    re.IGNORECASE,
)
_MULTIPLIER_VALUES = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
}


def money_value(num_str: str, mult_str: str | None) -> float:
    """Canonical numeric value of a MONEY_RE match's ``num``/``mult``
    groups -- "5", "million" -> 5,000,000.0; "1.5", "bn" -> 1.5e9; "500",
    None -> 500.0. Rounded to cents to absorb float multiplication noise
    (e.g. 1.1 * 1_000_000), never to absorb a genuine value difference."""
    value = float(num_str.replace(",", ""))
    if mult_str:
        value = round(value * _MULTIPLIER_VALUES[mult_str.lower()], 2)
    return value


def format_money(value: float) -> str:
    """Canonical human-readable form of a numeric amount: comma-grouped,
    with cents shown ONLY when the value has a genuine non-zero
    fractional part (Root fix defect 3 -- a detail
    string must never silently round $500.40 -> $500 / $500.99 -> $501,
    which describes a real change as no change; a whole-dollar amount
    must equally never grow a spurious ".00")."""
    rounded_cents = round(value * 100)
    if rounded_cents % 100 == 0:
        return f"${int(rounded_cents // 100):,}"
    return f"${rounded_cents / 100:,.2f}"


def _canonicalize_amounts(text: str) -> str:
    def _repl(m: re.Match) -> str:
        value = money_value(m.group("num"), m.group("mult"))
        return format_money(value)

    return MONEY_RE.sub(_repl, text)


# After dash CHARACTERS are unified and repeated dashes collapsed (above),
# the SPACING around a single "-" is still a free cosmetic axis: "claims
# - made" (spaces added), "claims--made"/"claims—made" (already folded to
# "claims-made" by this point) and "claims-made" itself must all compare
# identical, or a dash-spacing-only edit leaks through as a false
# "restrictive/inclusive language changed" signal (the phrase-level marker
# check in classify.py matches "claims-made" as a literal substring of the
# raw clause text, so inserting spaces around the hyphen breaks that match
# even though nothing about the term actually changed). Applied AFTER
# _strip_leading_markers/whitespace-collapse (see normalize() below) so it
# never interferes with leading "- " bullet-marker stripping, which needs
# the original per-line spacing to detect the marker in the first place.
_DASH_SPACING_RE = re.compile(r"\s*-\s*")


def _unify_quotes_and_dashes(text: str) -> str:
    for k, v in _CURLY_QUOTES.items():
        text = text.replace(k, v)
    for k, v in _DASHES.items():
        text = text.replace(k, v)
    text = _REPEATED_DASH_RE.sub("-", text)
    return text


# Root fix:
# quotation marks around a defined term are a formatting/marker
# convention -- `"insured"` vs `insured` -- dropping or adding them
# changes NO coverage. Quote STYLE (straight<->curly) is already unified
# by _unify_quotes_and_dashes above; quote PRESENCE must be folded the
# same way, or a formatting-only quotes-only edit leaks through as a
# spurious "modified (direction unclear)" finding (reproduced live:
# `The "insured" must cooperate.` -> `The insured must cooperate.`).
#
# Scoped to DOUBLE quotes only. By the time this runs, every curly
# double quote has already been unified to a single straight `"` (see
# _unify_quotes_and_dashes, which always runs first in normalize()
# below), so removing every literal `"` character folds BOTH the
# curly-quoted and straight-quoted, BOTH the quoted and unquoted, forms
# of a term to the same text. Single quotes/apostrophes are deliberately
# left untouched: an apostrophe is used constantly as a possessive/
# contraction marker WITHIN a word ("insured's obligations", "it's"),
# and there is no reliable, purely-lexical way to tell that usage apart
# from a single-quote-delimited term without risking mangling a real
# possessive or contraction -- ISO-form policies mark defined terms with
# double quotes, not single quotes, so restricting this fold to double
# quotes covers the reported cases without that risk (see the task's own
# "prefer safety" guidance). Every double-quote character is simply
# removed -- with the character gone there is nothing to "pair" or
# balance, so an odd/unbalanced literal quote elsewhere in the text
# degrades to "one fewer character" in the normalized form, never to a
# mis-paired strip that eats real words.
def _strip_quote_presence(text: str) -> str:
    return text.replace('"', "")


def _strip_leading_markers(text: str) -> str:
    # A bare (unparenthesized) single-letter or lowercase-roman marker
    # ("A.", "a.", "i.", "iii.") is only stripped on the lines where it
    # is CONFIRMED -- via a sequence-adjacent sibling elsewhere in this
    # same text -- to be a real clause-number anchor rather than a
    # sentence-internal-looking abbreviation/initial ("No. 5", "J.
    # Smith") that happens to sit at the start of a physical line. Every
    # other marker style below (paren-alnum, arabic, bullets,
    # dotted-decimal, paren-roman) is unambiguous on its own and stays
    # unconditional. See policydiff/enumerators.py's module docstring.
    lines = text.split("\n")
    confirmed = confirmed_bare_alpha_line_indices(lines)
    out_lines = []
    for i, line in enumerate(lines):
        new_line = _LEADING_MARKER_RE.sub("", line, count=1)
        if new_line == line:
            new_line = PAREN_ROMAN_MARKER_RE.sub("", line, count=1)
        if new_line == line and i in confirmed:
            new_line = BARE_ALPHA_DOT_MARKER_RE.sub("", line, count=1)
        out_lines.append(new_line)
    return "\n".join(out_lines)


def strip_bom(text: str) -> str:
    """Strip a leading UTF-8 BOM, and any stray zero-width BOM character
    (U+FEFF) anywhere else in *text*.

    Root fix: ``Path.read_text(
    encoding="utf-8")`` does NOT strip a BOM the way ``utf-8-sig`` would,
    so a source file saved WITH a leading BOM keeps a literal ``\\ufeff``
    as its first character. That character sits in front of the first
    line's enumerator ("\\ufeff1. Coverage A applies."), which stops the
    enumerator regex in segment.py from recognizing "1." as a clause
    number on that side only -- an old file without a BOM and a new file
    with one, otherwise byte-identical, then segment into DIFFERENT
    clause shapes and produce a spurious "added" finding out of pure
    formatting noise.

    This must run at the very top of diff_documents(), before
    segmentation, on BOTH old_text and new_text -- BOM removal can never
    depend on which side happens to have one, or a real, non-BOM change
    made to a BOM'd file would go uncaught on the side the strip skipped."""
    return text.replace("﻿", "")


def normalize(text: str, suppress_cosmetic: bool = True) -> str:
    """Return a canonical form of *text*.

    When ``suppress_cosmetic`` is True (the default), whitespace is
    collapsed, quotes/dashes are unified, leading list markers are
    stripped per-line, and the whole thing is case-folded so that
    defined-term recapitalization is invisible.

    When False, essentially no suppression happens -- this is the
    "disable the suppressor" path used to prove the suppression step is
    load-bearing (tests/test_suppression_toggle.py).
    """
    if not suppress_cosmetic:
        return text.strip()

    t = _unify_quotes_and_dashes(text)
    t = _strip_quote_presence(t)
    t = _strip_leading_markers(t)
    # Root fix: canonicalize monetary-amount formatting (comma
    # grouping, trailing zero decimals) before anything else touches the
    # digits -- see _canonicalize_amounts above.
    t = _canonicalize_amounts(t)
    # Collapse all whitespace (including newlines from reflow) to single
    # spaces, then case-fold. Reflow and renumbering are exactly what this
    # is meant to erase.
    t = re.sub(r"\s+", " ", t).strip()
    t = t.casefold()
    # Normalize punctuation spacing noise: "word ." -> "word.", double
    # punctuation collapses, etc.
    t = re.sub(r"\s+([.,;:!?])", r"\1", t)
    # Dash-spacing fold: "claims - made" / "claims-made" / "co - insurance"
    # all become "claims-made" / "co-insurance" -- a spaced dash is
    # indistinguishable, for comparison purposes, from an unspaced one.
    t = _DASH_SPACING_RE.sub("-", t)
    return t


def light_normalize(text: str, suppress_cosmetic: bool = True) -> str:
    """A much smaller normalization used only to detect a clause that
    moved position/number but is otherwise byte-identical.

    This intentionally does NOT case-fold or unify quotes -- it only
    strips leading/trailing whitespace per line (and, when
    ``suppress_cosmetic`` is True, also collapses runs of horizontal
    whitespace within a line), so that a clause that was reworded even
    slightly (including a pure recapitalization) does NOT get swallowed
    into "unchanged" -- that distinction belongs to cosmetic suppression
    (normalize(), above), not to this identity check.

    an earlier revision's root fix: the internal-whitespace
    collapse is itself a cosmetic-suppression step (it is precisely what
    made a pure whitespace-run/tab-vs-space edit compare "identical" and
    return "unchanged" before classify.py's caller-supplied
    ``suppress_cosmetic`` flag was ever consulted). With the flag off,
    this function now only strips each line's ends -- an internal
    whitespace-run difference is left visible, exactly like every other
    cosmetic axis the flag gates.
    """
    if suppress_cosmetic:
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    else:
        lines = [ln.strip() for ln in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
