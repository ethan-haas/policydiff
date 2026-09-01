"""Classify each aligned clause pair as one of:

    unchanged | cosmetic | narrowed | broadened | modified

("added"/"removed" are assigned directly to unmatched clauses by the
caller -- report.py / __main__.py -- not by this module.)

Direction detection ("narrowed" vs "broadened") is signal-based, NEVER a
net-text-length / word-count-ratio guess -- that heuristic inverts
constantly (a narrowing edit that happens to add more words than it
removes reads as "broadened", and vice versa). Every classifier below
either resolves direction from a real semantic signal, or gives up
honestly with "modified (direction unclear)". A real change is always
reported either way -- recall never depends on direction being resolved.

Signals, in priority order, applied across ALL clause kinds (not just
exclusions):

  * exclusion carve-back marker added/removed (Root fix,
    an earlier audit) -- checked FIRST, but ONLY inside an exclusion clause: a
    carve-back/exception ("except", "however", "but this exclusion does
    not apply", "does not apply to the first $X", "we will pay up to
    $X") newly ADDED grants coverage that did not exist -- BROADENED --
    WHETHER OR NOT it carries a "$" cap; the same marker REMOVED takes
    that coverage away -- NARROWED. This runs ahead of the numeric rule
    below on purpose: a $-denominated carve-back's cap is the LIMIT of
    NEWLY-GRANTED coverage, not a reduction of existing coverage, so the
    numeric rule's "a dollar figure of this role appeared/disappeared
    outright -> added narrows, removed broadens" reading is exactly
    backwards for it. A carve-back present on BOTH sides whose CAP merely
    changes is NOT intercepted here -- it falls through to the numeric
    rule below, which already resolves it correctly (equal count, one
    amount each side, role defaults to "limit" -> higher cap = broadened,
    lower = narrowed).
  * numeric limits / deductibles / sublimits -- extract dollar amounts,
    each assigned a ROLE (deductible | sublimit | limit) from its OWN
    LOCAL context (the words immediately around THAT amount, scoped to
    its own comma/semicolon-delimited segment of the clause) -- never
    from whichever coverage word happens to appear anywhere else in the
    clause (A defect: a clause mentioning "deductible" anywhere
    used to have deductible semantics applied to whichever dollar figure
    happened to change first, even when that figure was actually the
    LIMIT and the deductible was untouched). Amounts are then compared
    BY ROLE across old/new, so an unchanged deductible never influences
    the direction computed for a changed limit in the same clause, and
    vice versa. Equal count for a role: the changed value(s) resolve
    directly (deductible: higher = narrowed; sublimit/limit: higher =
    broadened). Unequal count for a role: a dollar figure of that role
    was added or removed outright (e.g. a brand-new sublimit, or a cap
    that used to exist and no longer does) -- ADDED narrows (something
    that was previously unlimited/uncapped now is), REMOVED broadens.
    A clause with more than one changed amount reports ONE finding PER
    changed amount (A defect) -- a co-occurring narrowing (e.g.
    a sublimit cut) is never dropped behind a broadening (e.g. an
    aggregate raised) reported for the same clause pair.
  * reimbursement/coinsurance percentage and waiting/elimination periods
    -- resolved only for unambiguous, single-match phrasing ("reimburses
    N%", "we pay N%", "N% coinsurance" in the pay-share sense: higher %
    = broadened; "waiting/elimination period of N days/hours": higher N
    = narrowed). Anything else (count != 1 on a side, no recognized
    marker) is left unresolved -- a wrong direction is worse than
    "modified (direction unclear)".
  * exclusion clauses -- direction is decided by SCOPE semantics, NEVER
    by which side is textually longer (Root fix: the
    previous fallback here was a pure-insertion/pure-deletion
    CONTAINMENT check -- "did new strictly contain old" -- which is
    exactly the length/containment heuristic the module docstring's
    opening paragraph already forbids everywhere else; it silently
    inverted every case where the ADDED text was a RESTRICTION on the
    exclusion's own trigger rather than a new excluded peril, e.g.
    "does not apply to bodily injury" -> "...bodily injury arising from
    assault" is a pure insertion, so the old fallback called it
    "narrowed"; restricting WHEN an exclusion fires means LESS is
    excluded, i.e. coverage BROADENS). Every inserted/removed WORD SPAN
    (computed by a word-level diff, never a net length/count) between
    old and new is classified on its own:
      - a span that is a NEW EXCLUDED PERIL/ITEM -- a parallel member
        extending WHAT is excluded, signalled by the span itself
        STARTING with a coordinating conjunction ("or <peril>", "and
        <peril>") -- makes the exclusion BROADER, so coverage NARROWS.
        Added -> narrowed; the same span removed -> broadened.
      - a span that RESTRICTS the exclusion's TRIGGER/SCOPE -- limiting
        WHEN or HOW it applies, signalled by phrases like "arising
        from"/"arising out of"/"resulting from"/"caused by"/"only
        if"/"solely when"/"when"/"provided that"/"except"/"unless"/"to
        the extent" appearing IN THAT SPAN (not merely anywhere in the
        clause, which would let an unrelated pre-existing "caused by"
        wrongly license a change to a totally different word) -- makes
        the exclusion NARROWER, so coverage BROADENS. Added ->
        broadened; the same span removed -> narrowed.
      - every span's vote is collected; if they disagree (or none
        resolve), the whole pair is "modified (direction unclear)" --
        never guessed from whichever span happens to be longer.
    Root fix: when
    the SAME carve-back marker is present on BOTH sides (an existing
    exception, as opposed to an earlier revision's marker-added/removed case), the
    clause has TWO regions with OPPOSITE polarity -- the BASE exclusion
    (before the marker) and the EXCEPTION/carve-back itself (at/after
    the marker). The peril/trigger-restriction rule above is exactly
    right for a span in the BASE, but backwards for a span in the
    EXCEPTION: growing the exception carves MORE loss back INTO
    coverage (broadens), shrinking it carves LESS back (narrows) --
    the opposite of growing/shrinking the base exclusion itself. Every
    span is scoped to its region (_carveback_boundary_index /
    _carveback_region) and a span confined to the EXCEPTION has its
    vote inverted before joining the same agree/disagree tally as
    every other span; a span that straddles the boundary, or a clause
    with disagreeing votes from the two regions, still resolves to
    "modified (direction unclear)".
  * definition clauses ("X" means ...) -- likewise SCOPE-based, never
    length-based (Root fix: the previous fallback -- content
    added with nothing removed = broadened, content removed with
    nothing added = narrowed -- is precisely a one-sided length/count
    guess, and inverts whenever the ADDED content is a RESTRICTIVE
    QUALIFIER rather than a new alternative member, e.g. "means any
    land motor vehicle" -> "...any PRIVATE PASSENGER land motor
    vehicle" adds words while SHRINKING the defined set). A marker-word
    pass runs first (added inclusive marker word e.g. "also"/
    "including"/"additionally"/"plus" = broadened; added restrictive
    marker word e.g. "except"/"only"/"solely"/"must"/"excluding" =
    narrowed; the same words removed = the opposite), then, if that
    doesn't resolve it, each inserted/removed WORD SPAN from a
    word-level diff is classified on its own:
      - EXPANSIVE (a new alternative/parallel member): the span itself
        STARTS with a coordinating/list word ("or", "and", "plus",
        "including", "also", "additionally") followed by actual content
        (a lone conjunction with nothing after it is not a signal on
        its own). Added -> broadened; removed -> narrowed.
      - RESTRICTIVE (a qualifier that shrinks the defined set): the
        span contains a restrictive-qualifier phrase ("only", "solely",
        "must", "except", "excluding", "designed for", "used for",
        "that is", "provided that", an ownership limiter "you own"/
        "owned by"), OR the span is inserted/removed immediately after
        a bare determiner ("a"/"an"/"any"/"the") -- i.e. it is a
        premodifier of the defined noun itself ("any PRIVATE PASSENGER
        land motor vehicle"), which is a restrictive signal even with
        no keyword match, since a determiner-adjacent insertion can
        only be qualifying the noun it precedes, never coordinating a
        new list member. Added -> narrowed; removed -> broadened.
      - every span's vote is collected; if they disagree (or none
        resolve), "modified (direction unclear)".
  * anything else (coverage grants, conditions, and any clause that
    isn't an exclusion or a definition) -- the SAME kind of restrictive/
    inclusive marker signal as definitions (added sublimit language,
    "claims-made"/"claims first made", "only", "solely", "provided
    that", a bare "not" = narrows; the same language removed =
    broadens; "also"/"including"/"any"/etc added = broadens). No
    length-based fallback here: if no marker resolves it, "modified".
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, replace

from .normalize import MONEY_RE as _MONEY_RE
from .normalize import format_money, light_normalize, money_value, normalize
from .segment import Clause, _is_bare_heading_line
from .sentence import sentence_boundary_starts

# Money-literal recognition (comma-grouping in groups-of-3, with a
# fallback for amounts that have no comma grouping at all ("$1000"), plus
# an optional currency-word/suffix multiplier -- "$5 million", "$50k")
# and its numeric-value computation both live in normalize.py (MONEY_RE /
# money_value), shared with this module's cosmetic-equality
# canonicalization -- see normalize.py's Root fix docstring
#.
_WORD_RE = re.compile(r"[a-z']+")

# Root fix (defect 1/2): ROLE of a monetary amount, resolved from
# LOCAL context only (see _amount_role / _money_roles below) -- never
# from a keyword anywhere else in the clause.
#
# Root fix: "each
# occurrence" / "per occurrence" / "each accident" / "each claim" are
# FREQUENCY qualifiers ("this cap resets/applies per event"), NOT role
# words on their own. "each occurrence limit is $1,000,000" IS a limit --
# but only because the word "limit" is right there; the frequency phrase
# itself carries no role information. Treating "each occurrence" as a
# limit-role keyword meant "a deductible of $10,000 each occurrence" had
# TWO candidate role keywords in the same segment ("deductible" and "each
# occurrence"), and the nearest-to-the-amount tiebreak in _amount_role
# picked whichever one sat textually closer to the "$10,000" -- which is
# "each occurrence" almost every time, since it's the words immediately
# after the amount. That silently re-assigned a deductible amount's role
# to "limit" and inverted its direction (a deductible INCREASE reported
# as "[BROADENED] limit ... "). Fix: frequency phrases are recognized
# separately (see _FREQUENCY_RE below) and are NEVER a role-keyword
# candidate. Role = limit now requires an actual limit word ("limit",
# "aggregate", "most we will pay") in the segment; role = deductible
# requires "deductible"/"retention"/"SIR"(uppercase-only, avoids matching
# the pronoun "sir")/"self-insured retention" (via "retention"). A
# specific role word (deductible/retention/SIR/sublimit) and a limit word
# ("limit"/"aggregate") can still both be present in one segment (e.g.
# "the deductible limit") -- that residual ambiguity is resolved the same
# nearest-candidate way as before; only the frequency phrase is removed
# from candidacy, which is what gives the specific role word precedence
# over a bare frequency qualifier for the SAME amount.
_ROLE_KEYWORD_RE = re.compile(
    r"(?P<deductible>\b(?:deductible|retention)\b|(?-i:\bSIR\b))"
    r"|(?P<sublimit>\bsub[\s-]?limit\b|\bper\s+item\b|\bany\s+one\s+item\b)"
    r"|(?P<limit>\blimit\b|\baggregate\b|\bmost\s+we\s+will\s+pay\b)",
    re.IGNORECASE,
)
_ROLE_LABELS = {
    "deductible": "deductible",
    "sublimit": "sublimit",
    "limit": "limit",
    "floor": "amount not covered",
    "unclear": "amount",
}

# Root fix: every prior
# round (11, 20, 22, 23, 24's own Part 1 above) fixed this module's
# insured-borne-floor blind spot by naming ONE MORE specific phrasing --
# but a phrasing not yet on that list still falls through to
# _money_roles' old blanket "no local keyword -> role='limit'" default,
# whose polarity ("higher = more coverage = broadened") is BACKWARDS for
# any floor/retention framing, confidently. That is a whack-a-mole
# pattern, not a root fix: the module docstring's own promise -- "a
# GUESSED-WRONG direction is worse than modified (direction unclear)" --
# was being broken by the ONE case (the blanket default) that runs when
# NOTHING else recognized the clause at all.
#
# Root fix: an amount with no LOCAL role keyword (_ROLE_KEYWORD_RE) and no
# propagated role from an earlier segment no longer defaults straight to
# "limit". It first checks whether the clause carries a genuine INSURER-
# LIMIT signal ANYWHERE (_LIMIT_SIGNAL_RE below) -- if so, "limit" is
# still the right default, unchanged from every prior round (this is what
# keeps "We will pay up to $X" / "The Company will pay up to $X" / "the
# maximum (we will pay) is $X" resolving exactly as before with no local
# "limit"/"aggregate" keyword at all). Only when NO limit signal is
# present does the clause's own EXCLUSIONARY/floor framing
# (_EXCLUSIONARY_FRAMING_RE) get consulted: present -> "floor" role
# (same narrows-on-increase polarity as "deductible", see
# _role_changed_direction, with its own detail wording so the finding
# never claims "limit" for money that was never a limit); absent
# altogether -> "unclear" role, which _classify_numeric resolves to
# "modified (direction unclear)" for an EQUAL-count (existing amount's
# value merely changed) comparison rather than guessing either direction.
#
# This deliberately does NOT change the UNEQUAL-count (amount added/
# removed outright) branch of _classify_numeric -- that branch's rule
# ("a dollar figure of this role appeared -> narrows; disappeared ->
# broadens") is ALREADY role-agnostic-correct: a brand-new cap of any
# kind (limit, sublimit, or floor) restricts something that was
# previously uncapped/unexcluded (narrows), and removing any existing cap
# of any kind un-restricts it (broadens) -- see
# test_direction_signals.test_sublimit_added_is_narrowed, which relies on
# exactly this role-agnostic behavior for an amount with no role keyword
# and no limit signal at all. Only the EQUAL-count branch's polarity
# actually depends on which of "limit" vs "floor" the amount is, so only
# that branch needs the "unclear" degrade-to-modified treatment.
_LIMIT_SIGNAL_RE = re.compile(
    r"\blimit\b"
    r"|\baggregate\b"
    r"|\bmost\s+we\s+will\s+pay\b"
    r"|\bup\s+to\b"
    r"|\bmaximum\b"
    r"|\bsub[\s-]?limit\b",
    re.IGNORECASE,
)
_EXCLUSIONARY_FRAMING_RE = re.compile(
    r"\bdo(?:es)?\s+not\s+cover\b"
    r"|\bnot\s+covered\b"
    r"|\bdoes\s+not\s+apply\b"
    r"|\bexcludes?\b"
    r"|\bexcluded\b"
    r"|\bless\s+than\b"
    r"|\bunder\b"
    r"|\bbelow\b"
    r"|\bretains?\b"
    r"|\bretained\b"
    r"|\bbears?\b"
    r"|\bthe\s+first\b",
    re.IGNORECASE,
)

# Root fix (an earlier audit, Part 2 -- clause-wide safety-net
# precedence): the same floor-over-limit precedence _amount_role now
# applies locally (see its an earlier revision docstring) must ALSO apply to the
# an earlier revision safety net's clause-wide fallback (_money_roles' fallback_role
# below), so a floor-role PHRASE that _ROLE_KEYWORD_RE itself never
# recognizes at all -- "borne by the insured" / "retained by the
# insured" / "applies before coverage responds" (named alongside the
# keyword-recognized deductible/retention/SIR in the task's root-fix
# description) -- can still suppress the "limit signal -> limit role"
# branch for an amount that has no local role keyword in its own
# segment. Deliberately does NOT repeat the bare "deductible"/
# "retention"/"SIR" words here: those are already _ROLE_KEYWORD_RE
# candidates, resolved correctly by _amount_role locally (an earlier revision's own
# fix, above) or carried forward by the existing propagation mechanism
# (_role_reset_boundaries) when they apply to THIS amount; re-adding them
# to a clause-WIDE (not segment-scoped) check here would let a deductible
# word describing a completely different, reset-boundary-separated
# amount in the same clause wrongly reclassify an unrelated limit/pay
# amount as a floor (e.g. "A deductible of $500 applies; the Company
# will pay $1,000,000 for each claim." -- the pay-verb amount after the
# ';' reset must stay "limit", never inherit "deductible"'s floor
# polarity across a boundary that already, correctly, blocks ordinary
# propagation). Only the three PHRASES that carry no local-role-keyword
# recognition path of their own are added, so this can never re-open
# that hole. A carve-back GRANT (_CARVEBACK_GRANT_RE) is still checked
# first and still wins, unchanged from an earlier revision -- see
# _classify_retention_floor / _CARVEBACK_GRANT_RE's own precedence
# docstring for why a carve-back's cap must never be read as a floor.
_FLOOR_ROLE_CLAUSE_RE = re.compile(
    r"\bborne\s+by\s+the\s+insured\b"
    r"|\bretained\s+by\s+the\s+insured\b"
    r"|\bapplies\s+before\s+coverage\s+responds\b",
    re.IGNORECASE,
)

# A bare, UN-NEGATED "pay" verb ("The Company will pay $X for each claim.",
# "Pay $200.") is, on its own, ordinary positive insurer-payment language
# -- the plainest possible phrasing of a coverage amount -- and belongs on
# the "limit" side of the safety net's fallback exactly like the
# enumerated keyword phrases above (see the block comment above
# _LIMIT_SIGNAL_RE): a clause that does nothing but say what the insurer
# WILL pay, with no exclusionary framing anywhere, is a limit-shaped
# amount even with no "limit"/"aggregate"/"up to" keyword at all. A
# NEGATED "pay" ("will not pay", "does not pay", "shall not pay") is the
# opposite -- that phrasing already carries its own dedicated recognizer
# (_RETENTION_FLOOR_RE's "will not pay for the portion" alternative, and
# _EXCLUSIONARY_FRAMING_RE's own "not covered"/"does not cover"/"under"/
# "less than"/"below" alternatives elsewhere in the same clause) -- so a
# negated "pay" must never itself count as a positive limit signal here,
# or it would silently re-invert a floor phrased with "pay" that Part 1's
# enumerated list doesn't happen to name.
#
# Root fix: the above is only true when the payer is
# the INSURER. A bare un-negated "pay" is only "ordinary positive
# insurer-payment language" when the entity doing the paying is the
# insurer (we/the Company/the insurer/the underwriter) -- see the module
# docstring's payer-subject rule. When the SUBJECT governing "pay" is the
# INSURED instead ("you must pay the first $X", "you pay $X", "the
# insured pays $X") the amount is the insured's own deductible/retention
# -- an insured-borne FLOOR, the opposite polarity -- and must never count
# as a positive "limit" signal here. This is a defense-in-depth safety
# net only: the primary fix for this exact phrasing is
# _RETENTION_FLOOR_RE's new "you must pay"/"insured pays" alternatives
# above (checked earlier, in _classify_retention_floor, before this
# fallback ever runs) -- this qualification exists so that ANY OTHER
# insured-payer phrasing this module's enumerated marker lists don't
# happen to name still falls through to the honest EXCLUSIONARY_FRAMING/
# "unclear" branches below instead of confidently inverting, matching the
# module docstring's "a wrong direction is worse than modified (direction
# unclear)" discipline. _INSURED_PAYER_RE is scoped to a "pay" verb
# governed by an insured-side subject within the same clause (no '.'/';'
# between them, mirroring every other subject-scoped check in this
# module); when the SAME text ALSO carries an insurer-side "pay" (e.g. a
# clause naming both "we will pay" and, separately, "you must pay"),
# _INSURER_PAYER_RE wins and the ordinary positive-limit reading is kept
# -- only a clause whose ONLY "pay" usage is insured-borne is
# reclassified.
_POSITIVE_PAY_RE = re.compile(r"\bpay\b", re.IGNORECASE)
_NEGATED_PAY_RE = re.compile(
    r"\b(?:not|never)\b[^.]{0,20}?\bpay\b", re.IGNORECASE
)
_INSURER_PAYER_RE = re.compile(
    r"\b(?:we|it|the\s+company|the\s+insurer|the\s+underwriter)\b"
    r"[^.;]{0,20}?\bpays?\b",
    re.IGNORECASE,
)
_INSURED_PAYER_RE = re.compile(
    r"\b(?:you|your|the\s+insured|named\s+insured|the\s+policyholder)\b"
    r"[^.;]{0,20}?\bpays?\b",
    re.IGNORECASE,
)

# Frequency qualifiers -- recognized only so future signals (none today)
# could use them, and to document explicitly that they are NOT part of
# _ROLE_KEYWORD_RE. Kept even though currently unused by any classifier,
# as a single named place documenting the full frequency-phrase set the
# module docstring and this comment block both refer to.
_FREQUENCY_RE = re.compile(
    r"\b(?:each|per)\s+(?:occurrence|accident|claim)\b", re.IGNORECASE
)

# Segment boundary characters (';'/',') used to scope role-keyword lookup
# to the PART of the clause that actually contains a given amount -- a
# keyword on the far side of a semicolon/comma-separated item must never
# claim an amount that belongs to a different item (an earlier revision defect 1's
# "Limit is $2,000,000; deductible $500" case: "deductible" is textually
# CLOSER to the limit amount across the semicolon than "Limit" is, so a
# pure nearest-character-distance rule without segment scoping would
# misassign it).
_SPLIT_CHARS_RE = re.compile(r"[;,]")

# Root fix: a role word GOVERNS subsequent
# comma-separated amounts in the same list until a new role word, a ';',
# or a sentence end resets it -- "Deductible $500 for property, $800 for
# liability" must assign BOTH amounts the "deductible" role, not fall
# back to "limit" for the second (keyword-less) comma item. A ';' or a
# sentence-ending '.'/'!'/'?' is a STRONGER boundary than ',' and resets
# the propagated role back to none (so "Limit $2M; deductible $500"
# still assigns each its own role, and a role word never leaks into an
# unrelated later sentence).
#
# Root fix: an earlier revision's reset fired on ';'
# but NOT on a sentence-ending '.'/'!'/'?' -- a numbered clause's body
# routinely holds MORE THAN ONE sentence ("A deductible of $500 applies.
# The Company will pay $1,000,000...") with no ';' anywhere in it, so a
# role word in the first sentence leaked straight across the full stop
# and claimed an amount in a completely unrelated second sentence. The
# real sentence-boundary detector (with its abbreviation/decimal/initial
# guard -- "$500.40" and "No."/"U.S." never count) already exists in
# sentence.py for document segmentation; reuse it here (via
# _sentence_end_positions, below) rather than re-guessing sentence
# boundaries with a bare "[.!?]+" regex, which cannot tell a real
# sentence end from either of those.


def _sentence_end_positions(text: str, money_spans: list[tuple[int, int]]) -> set[int]:
    """Character offsets right after each real sentence boundary in
    *text* (see sentence.sentence_boundary_starts), excluding any that
    would fall inside a money literal's own span -- defensive only: the
    boundary detector already requires whitespace after the punctuation,
    which a decimal point ("$500.40") and a directly-attached multiplier
    suffix ("$50k") never have, so this exclusion should never actually
    trigger, but it keeps this function's contract identical to every
    other money-span-aware boundary check in this module."""
    return {
        pos
        for pos in sentence_boundary_starts(text)
        if not any(s <= pos <= e for s, e in money_spans)
    }

# Pay-share reimbursement/coinsurance percentage: "reimburses N%", "we
# pay N%", "pays N%", or a BARE "N% coinsurance" with no "clause"/
# "requirement" word attached. Higher % = broadened (an earlier revision defect 3).
#
# Root fix: "N% coinsurance" is genuinely ambiguous
# across insurance domains -- health-style usage ("benefits are subject
# to 80% coinsurance for out-of-network care", an earlier revision's
# test_coinsurance_payshare_percent_decrease_is_narrowed) names the
# PAY-SHARE percentage itself (the plan/insurer's portion), same polarity
# as an ordinary reimbursement rate: higher = broadened. Property-style
# usage names a distinct INSURANCE-TO-VALUE REQUIREMENT clause ("an 80%
# coinsurance CLAUSE applies to this coverage") with the OPPOSITE
# polarity (higher required % = stricter on the insured = narrowed --
# see _classify_coinsurance below). The two are told apart by whether
# "clause"/"requirement" sits next to "coinsurance": _classify_coinsurance
# (which runs first in _classify_signal) claims only the "clause"/
# "requirement" phrasing; this regex's own coinsurance alternative
# explicitly excludes that phrasing (negative lookahead) so the two can
# never both claim the same match, and a bare "N% coinsurance" with
# neither word nearby still falls through to this pay-share reading,
# exactly as it always has.
_REIMBURSE_PCT_RE = re.compile(
    r"\b(?:reimburses?|we\s+(?:will\s+)?pay|pays?)\b[^.%]{0,30}?(\d+(?:\.\d+)?)\s*%"
    r"|(\d+(?:\.\d+)?)\s*%\s*coinsurance\b(?!\s+(?:clause|requirement))",
    re.IGNORECASE,
)

# Waiting/elimination period in days/hours: higher N = narrowed (less
# coverage available sooner) (an earlier revision defect 3b).
_WAIT_PERIOD_RE = re.compile(
    r"\b(?:waiting|elimination)\s+period\b[^.]{0,30}?(\d+(?:\.\d+)?)\s*(day|days|hour|hours)\b",
    re.IGNORECASE,
)

# Root fix (an earlier audit, 3 wrong-direction defects sharing one
# root, reproduced live at an earlier revision): an amount that is a FLOOR the
# INSURED bears/retains before coverage applies -- a first-dollar
# retention, an excess-of-loss attachment point, or a coinsurance
# insurance-to-value REQUIREMENT -- was falling through to the generic
# "untagged amount -> role=limit" default (_amount_role returns None for
# any segment with no _ROLE_KEYWORD_RE hit, and _money_roles then defaults
# an unresolved amount to "limit"), whose polarity is "higher = more
# coverage = broadened". For every one of these three framings that
# polarity is EXACTLY BACKWARDS: a higher first-dollar retention/
# attachment/coinsurance requirement is WORSE for the insured (NARROWED).
#
#   * "does not apply to the first $X (of any/each loss)" / "retain(s)
#     the first $X" / "retained amount" / "will not pay for the portion
#     ... below $X" -- the INSURANCE (not an exclusion's own carve-back --
#     see the distinction below) does not respond to the first $X; the
#     insured bears it. Deliberately NOT reusing the bare "retention"/
#     "SIR" keyword _ROLE_KEYWORD_RE already recognizes correctly via the
#     "deductible" role (see the matching regression test's self-
#     insured-retention-each-occurrence case, whose detail text asserts
#     the word "deductible") -- these are NEW phrasings that keyword
#     never matched (a bare verb "retain"/"retained", not the noun
#     "retention"), so this only ever fires where the existing mechanism
#     was previously silent, never overriding it.
#
#     This deliberately overlaps textually with _CARVEBACK_MARKER_RE's
#     own "does not apply to the first" alternative -- that is fine and
#     by design: _classify_exclusion_carveback only intercepts when the
#     marker's PRESENCE differs between old/new (added/removed); when the
#     phrase is present on BOTH sides (only the amount inside changed,
#     exactly this defect's shape) that check returns None and this one
#     runs instead. The two only conflict if a fixture needed BOTH "this
#     retention-floor phrase was added" AND "the retention floor's OWN
#     cap differs" in the same pair -- not a shape any current fixture or
#     regression test exercises; if it ever is, marker-added/removed
#     already correctly wins (checked first in _classify_signal) and this
#     amount-only comparison is scoped to marker-present-on-both-sides by
#     construction (see _classify_retention_floor's docstring).
#
#   * "attaches in excess of $X (of underlying limits)" / "attachment
#     point (of) $X" / "excess of underlying limits of $X" -- the
#     underlying-loss amount BELOW which this (typically excess) policy
#     does not respond at all. A HIGHER attachment point means the policy
#     sits higher and responds to less -- NARROWED.
#
#     Root fix (an earlier audit, 1 wrong-direction defect, reproduced
#     live at an earlier revision): the earlier marker regex only recognized the
#     "attaches in excess of" / "attachment point" / "excess of underlying
#     limits of" spellings, so sibling VERB/PREPOSITION phrasings for the
#     exact same excess/attachment sense -- "attaches ABOVE $X", "attaches
#     AT $X", "APPLIES in excess of $X", and the bare "RETAINED LIMIT of
#     $X" / "excess of A RETAINED LIMIT of $X" construction -- fell
#     through this marker entirely and hit the generic "limit" role
#     keyword instead (every one of those phrasings contains the bare word
#     "limit" or "excess of", neither of which _ROLE_KEYWORD_RE or this
#     regex, pre-fix, recognized as attachment-shaped), landing on the
#     numeric default's exactly-backwards "higher = broadened" polarity.
#     Self-inconsistency proof it was a real bug, not a modeling choice:
#     the NOUN form "The attachment point is $X" already correctly
#     resolved NARROWED via the "attachment point" alternative below --
#     only the verb/preposition family was missing. Fix: add
#     "attaches?\s+(?:above|at|in\s+excess\s+of)", "applies\s+in\s+excess\s+of",
#     "retained\s+limit", and a bare "underlying\s+limits?" safety-net
#     alternative (insurance-specific vocabulary that only ever appears in
#     an excess/attachment sense, never an ordinary first-dollar limit
#     clause) to the marker below. None of these overlap "limit"/
#     "aggregate" alone, so an ordinary "The (aggregate) limit is $X"
#     clause is completely unaffected (see the earlier guard test, still
#     green, and the new an earlier revision ordinary-limit guard below).
#
#   * an amount/percentage tied to the word "coinsurance" (a "coinsurance
#     clause"/"coinsurance requirement"/"N% coinsurance") is an
#     insurance-to-value REQUIREMENT on the insured (carry at least N% of
#     value or face a penalty at claim time), NOT a pay-share/
#     reimbursement percentage -- a HIGHER required percentage is a
#     STRICTER condition on the insured -- NARROWED. This is the OPPOSITE
#     polarity from an ordinary "we pay N%"/"reimburses N%" pay-share
#     (an earlier revision defect 3, _classify_reimburse_percent, unchanged: higher =
#     broadened), so _REIMBURSE_PCT_RE's own former "N% coinsurance"
#     alternative is removed below -- a coinsurance-tagged percentage is
#     now recognized and resolved ONLY by _classify_coinsurance, ahead of
#     _classify_reimburse_percent in _classify_signal, so the two can
#     never compete for the same match.
#
# All three run in _classify_signal AFTER the exclusion carve-back check
# (which must keep first refusal on any marker-added/removed shape) but
# BEFORE _classify_numeric / _classify_reimburse_percent, exactly the same
# precedence pattern an earlier revision established for carve-backs -- see that
# round's docstring. Each function engages ONLY when its own phrase
# marker is present (on the old text, the new text, or both) AND at least
# one dollar amount / percentage is present on either side; with no
# marker present at all it returns None immediately, so an unrelated
# clause is completely unaffected. Per the task's own instruction --
# "a GUESSED-WRONG direction is worse than modified (direction
# unclear)" -- an ambiguous shape (more than one amount changed, or the
# marker present but the single-amount comparison finds nothing to
# compare) resolves to "modified (direction unclear)" rather than falling
# through to the numeric default's limit-shaped guess.
#
# Root fix (an earlier audit, defect A -- 5 wrong-direction defects
# sharing one root, specification's worst category, reproduced live at HEAD
# 87de5b8): an insured-borne floor written in PLAIN ENGLISH -- with no
# "deductible"/"retention"/"SIR" keyword and no "does not apply to the
# first"/"retains the first"/"retained amount"/"will not pay for the
# portion" marker _RETENTION_FLOOR_RE already recognized -- fell through
# the same "untagged amount -> role=limit" default an earlier revision fixed for the
# keyword-shaped forms, and inverted:
#
#   * "the insured shall bear the first $X" / "the insured bears the
#     first $X" / "the insured shall bear $X" (no "first" needed) / "the
#     insured is responsible for the first $X" -- the insured, by name,
#     carries the amount; a bare "insured" + "bear(s)"/"is responsible
#     for" verb is added to the marker (no "first"/"$" requirement on the
#     verb phrase itself -- the function's own amount-presence gate below
#     already requires at least one $ figure on either side).
#   * "the first $X of (any/each) loss is not covered" / "the first $X
#     ... is not covered" -- coverage does not respond below $X, i.e. the
#     insured bears it, phrased as a bare "is not covered" verdict on
#     "the first $X" rather than a "does not apply"/"retain" verb.
#   * "we do not cover (any claim/loss) under $X" / "we will not cover
#     ... under $X" / "no coverage for (any claim/loss) under $X" /
#     "claims under $X are not covered" -- a claim/loss BELOW $X gets no
#     coverage at all, same insured-borne-floor sense as "will not pay
#     for the portion ... below $X" already covered, just phrased with
#     "under" instead of "below" and without the word "portion".
#
# Every one of these is scoped to the INSURED-BORNE sense (insured
# bears/is responsible for it, or coverage does not respond below/under
# it) -- never a bare "is not covered"/"not cover" alone, which would
# swallow ordinary exclusion clauses with no floor-amount semantics at
# all (the function's own dollar-amount gate below already limits this to
# clauses that actually carry a $ figure, and the exclusion-verb phrases
# here additionally require "under"/"the first ... is not covered" so an
# ordinary "flood is not covered" clause with an unrelated dollar amount
# elsewhere never matches).
#
# Precedence (defect B): a "the first $X" grant CARVED BACK OUT OF an
# EXCLUSION ("this exclusion does not apply to the first $X", "except
# (for) the first $X", "we will pay (for) the first $X", "coverage
# applies to the first $X") is the OPPOSITE construction -- the exclusion
# is WAIVED for the first $X, so the first $X of loss IS covered, and
# raising the cap BROADENS coverage, not narrows it. This overlaps
# textually with "does not apply to the first" above (a carve-back is
# always phrased "the EXCLUSION does not apply to the first $X", not "the
# INSURANCE does not apply"), so _classify_retention_floor below checks
# _CARVEBACK_GRANT_RE FIRST and bails out (returns None) whenever it
# matches, letting the pair fall through the rest of the chain to
# _classify_numeric, whose default "limit" role already has the CORRECT
# carve-back-grant polarity (higher cap = broadened, lower = narrowed --
# see test_guard_excess_carveback_cap_change_unaffected in
# the matching regression test, which already relies on exactly this
# fallthrough for the "except we will pay up to $X" marker-unchanged
# shape). No new direction-computing function is needed for defect B --
# only keeping the plain-English retention detector OUT of a carve-back
# grant's way.
_CARVEBACK_GRANT_RE = re.compile(
    r"\b(?:this|the)\s+exclusion\s+does\s+not\s+apply\s+to\s+the\s+first\b"
    r"|\bexcept\s+(?:for\s+)?the\s+first\b"
    r"|\bwe\s+will\s+pay\s+(?:for\s+)?the\s+first\b"
    r"|\bcoverage\s+applies\s+to\s+the\s+first\b",
    re.IGNORECASE,
)

# Root fix (an earlier audit, 1 wrong-direction class / 3 instances,
# reproduced live at an earlier revision): two more insured-borne-floor framings
# fell through this marker entirely and hit the generic "untagged amount
# -> role=limit" default, exactly the same failure shape an earlier revision and 23
# already fixed for other phrasings of the identical underlying floor
# concept:
#
#   * "we do not cover ... less than $X" / "... under $X" / "... below
#     $X" -- an earlier revision already recognized the "under" spelling of this
#     exact construction (_RETENTION_FLOOR_RE's own
#     "we (do|will) not cover ... under" alternative); "less than"/
#     "below" are the SAME construction with a different preposition, not
#     a new category, so they are added to the SAME alternative rather
#     than given a new one. The mirror phrasing "losses/claims of less
#     than/under/below $X ... are not covered" (marker BEFORE the "not
#     covered" verdict instead of after it) is likewise the same
#     construction read the other way round -- the "claims under $X ...
#     not covered" alternative already handled one ordering for "claims";
#     it is widened to also accept "loss"/"losses" as the noun and
#     "less than"/"below" as the preposition, covering both this round's
#     literal defect and its mirror.
#   * a bare VERB "retain(s)"/"retained by" tied to the insured -- as
#     opposed to the NOUN "retention" (already correctly routed to the
#     deductible role via _ROLE_KEYWORD_RE) or the "retains the first"
#     phrasing already recognized above -- is the same first-dollar-floor
#     sense without the word "first" ("the insured shall retain $X of
#     each and every loss"). Scoped to the insured as subject (mirroring
#     the existing "insured shall bear"/"insured bears" alternative
#     immediately below) so a wholly unrelated use of the verb "retain"
#     elsewhere in a clause is never swept in.
#
# Root fix (an earlier audit, 1 wrong-direction defect, specification's worst
# class, reproduced live at an earlier revision): "you must pay the first $X (of
# any loss)" -- the plainest, most common ISO-form phrasing of the
# insured's own deductible/retention ("you"/"your" is always the Named
# Insured in an ISO form, never the insurer) -- was NOT one of the marker
# phrases above (those all name the THIRD-PERSON "the insured", never the
# SECOND-PERSON "you" an actual policy form uses when addressing its own
# insured directly), so it fell through this marker entirely and hit the
# an earlier revision safety net's "bare un-negated pay verb -> limit" branch
# instead (see _POSITIVE_PAY_RE below), inverting: a raised deductible
# ("you must pay the first $500" -> "$2,500", i.e. the insured now bears
# MORE out of pocket before the policy responds -- NARROWED) read as
# "[BROADENED] limit changed", backwards, even with the word "deductible"
# present elsewhere in the same clause (a ';'-reset segment boundary keeps
# that keyword from reaching the "you must pay" segment -- by design, see
# the earlier/an earlier revision segment-scoping comments above -- so the keyword
# alone was never going to save this phrasing). Fix: add the SECOND-PERSON
# insured-payer family -- "you must pay (the first) $X", "you pay (the
# first) $X", "you are responsible for (the first) $X" -- alongside the
# existing third-person "insured ... is responsible for" alternative, and
# the mirror third-person phrasings "the insured must pay $X" / "the
# insured pays $X" (the same verb, spelled in the third person some forms
# use instead of "you"). All resolve via the SAME insured-borne-floor
# polarity every other alternative in this regex already uses (higher
# amount = insured bears more = NARROWED) -- see _classify_retention_floor.
# This is deliberately scoped to the SUBJECT pronoun/noun immediately
# governing "pay" ("you"/"your"/"the insured"/"named insured"/"the
# policyholder"), never a bare "pay" alone, so an INSURER-subject "we will
# pay"/"the company will pay" clause is completely untouched -- see the
# _POSITIVE_PAY_RE/_INSURED_PAYER_RE block comment below for the mirror
# fix applied to the safety net itself.
#
# Each of the five new alternatives also carries a negative lookahead
# excluding a directly-following "(a) deductible"/"(a) retention" --
# "the insured pays a deductible of $10,000" already resolves correctly
# and more precisely (detail names the role, "deductible changed from...")
# via _ROLE_KEYWORD_RE's own local "deductible" keyword match in
# _classify_numeric (an earlier revision's original mechanism, unchanged); this regex
# must not steal that clause into the generic "retention changed"
# wording, which would report the same (correct) NARROWED direction but
# regress the detail text every an earlier revision/an earlier revision guard test asserts
# names the role explicitly. Not needed for "you"/"insured" + a first-
# dollar amount with NO deductible/retention keyword right after "pay" --
# that shape has no local role keyword at all and would otherwise fall
# through to the (backwards, for an insured payer) numeric default this
# whole round exists to fix.
_RETENTION_FLOOR_RE = re.compile(
    r"\bdoes\s+not\s+apply\s+to\s+the\s+first\b"
    r"|\bretains?\s+the\s+first\b"
    r"|\bretained\s+amount\b"
    r"|\bwill\s+not\s+pay\s+for\s+the\s+portion\b"
    r"|\binsured\s+(?:shall\s+bear|bears?|is\s+responsible\s+for)\b"
    r"|\b(?:the\s+)?insured\s+(?:shall\s+)?retains?\b"
    r"|\bretained\s+by\s+the\s+insured\b"
    r"|\bthe\s+first\b[^.]{0,40}?\bis\s+not\s+covered\b"
    r"|\bwe\s+(?:do|will)\s+not\s+cover\b[^.]{0,40}?\b(?:under|less\s+than|below)\b"
    r"|\bno\s+coverage\s+for\b[^.]{0,40}?\b(?:under|less\s+than|below)\b"
    r"|\b(?:claims?|loss(?:es)?)\b[^.]{0,10}?\b(?:under|less\s+than|below)\b[^.]{0,40}?\bnot\s+covered\b"
    r"|\byou(?:r)?\s+must\s+pay\b(?!\s+(?:a\s+)?(?:deductible|retention)\b)"
    r"|\byou\s+pay\b(?!\s+(?:a\s+)?(?:deductible|retention)\b)"
    r"|\byou\s+are\s+responsible\s+for\b(?!\s+(?:a\s+)?(?:deductible|retention)\b)"
    r"|\b(?:the\s+)?insured\s+must\s+pay\b(?!\s+(?:a\s+)?(?:deductible|retention)\b)"
    r"|\b(?:the\s+)?insured\s+pays\b(?!\s+(?:a\s+)?(?:deductible|retention)\b)",
    re.IGNORECASE,
)

_ATTACHMENT_RE = re.compile(
    r"\battaches?\s+(?:above|at|in\s+excess\s+of)\b"
    r"|\battachment\s+point\b"
    r"|\bapplies\s+in\s+excess\s+of\b"
    r"|\bretained\s+limit\b"
    r"|\bexcess\s+of\s+underlying\s+limits\s+of\b"
    r"|\bunderlying\s+limits?\b",
    re.IGNORECASE,
)

# "N% coinsurance clause"/"N% coinsurance requirement" or "coinsurance
# clause/requirement (of) N%" -- the INSURANCE-TO-VALUE requirement
# reading, distinguished from the pay-share reading (_REIMBURSE_PCT_RE's
# own bare "N% coinsurance" alternative) by the presence of "clause" or
# "requirement" immediately after "coinsurance" -- see the block comment
# above _REIMBURSE_PCT_RE for the full disambiguation rationale.
_COINSURANCE_PCT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*coinsurance\s+(?:clause|requirement)\b"
    r"|\bcoinsurance\s+(?:clause|requirement)\b[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


def _classify_retention_floor(old_text: str, new_text: str) -> tuple[str, str] | None:
    """"narrowed"/"broadened"/"modified" (with detail) when *old_text* or
    *new_text* carries first-dollar-retention framing (_RETENTION_FLOOR_RE)
    -- see the block comment above. Returns None when neither side shows
    the framing at all (the ordinary numeric/generic chain runs
    unaffected).

    Root fix: bails out FIRST,
    before even checking _RETENTION_FLOOR_RE, when either side carries
    exclusion-carve-back-GRANT framing (_CARVEBACK_GRANT_RE) -- "this
    exclusion does not apply to the first $X" is a carve-back cap, not an
    insured-borne retention, even though it textually overlaps
    _RETENTION_FLOOR_RE's own "does not apply to the first" alternative.
    See the block comment above _CARVEBACK_GRANT_RE."""
    if _CARVEBACK_GRANT_RE.search(old_text) or _CARVEBACK_GRANT_RE.search(new_text):
        return None
    if not (_RETENTION_FLOOR_RE.search(old_text) or _RETENTION_FLOOR_RE.search(new_text)):
        return None
    old_amt = list(_MONEY_RE.finditer(old_text))
    new_amt = list(_MONEY_RE.finditer(new_text))
    if not old_amt and not new_amt:
        return None
    if len(old_amt) == 1 and len(new_amt) == 1:
        o = money_value(old_amt[0].group("num"), old_amt[0].group("mult"))
        n = money_value(new_amt[0].group("num"), new_amt[0].group("mult"))
        if o == n:
            return None
        kind = "narrowed" if n > o else "broadened"
        detail = f"retention changed from {format_money(o)} to {format_money(n)}"
        return kind, detail
    if len(old_amt) != len(new_amt):
        if len(new_amt) > len(old_amt):
            return "narrowed", "retention amount added"
        return "broadened", "retention amount removed"
    return "modified", "retention/floor wording changed, direction unclear"


def _classify_attachment(old_text: str, new_text: str) -> tuple[str, str] | None:
    """"narrowed"/"broadened"/"modified" (with detail) when *old_text* or
    *new_text* carries excess-attachment framing (_ATTACHMENT_RE) -- see
    the block comment above. Returns None when neither side shows the
    framing at all."""
    if not (_ATTACHMENT_RE.search(old_text) or _ATTACHMENT_RE.search(new_text)):
        return None
    old_amt = list(_MONEY_RE.finditer(old_text))
    new_amt = list(_MONEY_RE.finditer(new_text))
    if not old_amt and not new_amt:
        return None
    if len(old_amt) == 1 and len(new_amt) == 1:
        o = money_value(old_amt[0].group("num"), old_amt[0].group("mult"))
        n = money_value(new_amt[0].group("num"), new_amt[0].group("mult"))
        if o == n:
            return None
        kind = "narrowed" if n > o else "broadened"
        detail = f"attachment point changed from {format_money(o)} to {format_money(n)}"
        return kind, detail
    if len(old_amt) != len(new_amt):
        if len(new_amt) > len(old_amt):
            return "narrowed", "attachment point added"
        return "broadened", "attachment point removed"
    return "modified", "attachment wording changed, direction unclear"


def _classify_coinsurance(old_text: str, new_text: str) -> tuple[str, str] | None:
    """"narrowed"/"broadened" (with detail) for an unambiguous single
    coinsurance-requirement percentage change on each side (an earlier revision root
    fix) -- see the block comment above. A HIGHER required coinsurance
    percentage is NARROWED (opposite polarity from an ordinary pay-share
    percentage, _classify_reimburse_percent). Resolved only for exactly
    one match per side, same discipline as _classify_reimburse_percent /
    _classify_wait_period -- anything else is left unresolved rather than
    guessed."""
    old_m = list(_COINSURANCE_PCT_RE.finditer(old_text))
    new_m = list(_COINSURANCE_PCT_RE.finditer(new_text))
    if len(old_m) != 1 or len(new_m) != 1:
        return None
    o = float(old_m[0].group(1) or old_m[0].group(2))
    n = float(new_m[0].group(1) or new_m[0].group(2))
    if o == n:
        return None
    kind = "narrowed" if n > o else "broadened"
    detail = f"coinsurance requirement changed from {o:g}% to {n:g}%"
    return kind, detail


_INCLUSIVE_MARKERS = {"also", "including", "includes", "additionally", "any", "plus", "addition"}
_RESTRICTIVE_MARKERS = {"except", "unless", "only", "solely", "must", "excluding"}

# Broader restriction vocabulary for clauses that are NOT a formal
# "definition" -- coverage grants, conditions, insuring agreements, etc.
# still gain restriction language (new sublimit wording, "provided that",
# a bare "not") that must be recognized without inferring it from length.
_GENERIC_RESTRICTIVE_MARKERS = _RESTRICTIVE_MARKERS | {"sublimit", "provided", "not"}
_GENERIC_INCLUSIVE_MARKERS = _INCLUSIVE_MARKERS

# Multi-word restriction phrases that a unigram token-set diff can't see
# reliably (e.g. "claims-made" tokenizes to "claims"/"made", both of
# which are common enough elsewhere to be unsafe as bare markers).
_RESTRICTIVE_PHRASES = ("claims-made", "claims made", "claims first made", "condition precedent")

# Root fix: definition-clause structural signal,
# used only AFTER the marker-word pass below fails to resolve direction.
# See the module docstring's definition paragraph for the full rationale
# -- a span STARTING with a coordinating/list word (+ real content after
# it) is an EXPANSIVE new member; a span containing a restrictive-
# qualifier phrase, OR sitting immediately after a bare determiner (a
# premodifier of the defined noun itself), is RESTRICTIVE, even with no
# keyword match at all -- "any PRIVATE PASSENGER land motor vehicle" has
# no marker word anywhere, but "private passenger" can only be
# qualifying "land motor vehicle", never coordinating a new list member.
_DEF_EXPANSIVE_START_RE = re.compile(
    r"^(?:or|and|plus|including|include|includes|also|additionally)\b", re.IGNORECASE
)
_DEF_RESTRICTIVE_PHRASE_RE = re.compile(
    r"\b(?:only|solely|must|except|excluding|designed\s+for|used\s+for|"
    r"that\s+is|provided\s+that|you\s+own|owned\s+by)\b",
    re.IGNORECASE,
)
_DETERMINERS = {"a", "an", "any", "the"}


def _definition_span_signal(
    words: list[str], preceding_word: str | None, allow_bare_determiner_signal: bool = True
) -> str | None:
    """"expansive" | "restrictive" | None for one inserted/removed word
    span in a definition clause -- see the block comment above.

    Root fix:
    *allow_bare_determiner_signal* gates ONLY the no-keyword,
    determiner-adjacency fallback (the last branch below) -- never the
    two explicit-signal branches above it (an actual coordinating-word
    span, or an actual restrictive-phrase keyword match, are real signals
    regardless of what else changed in the clause). The caller
    (_classify_definition) sets this False when the clause's word-level
    diff is a SUBSTITUTION (both an insert-side and a delete-side span
    present -- i.e. a rephrase where words were swapped, not a clean
    insertion or a clean removal with the rest of the definition intact).
    Without this gate, a pure REWORD of the defined noun phrase --
    "the named insured" -> "the person or organization named" -- was
    misread as a restrictive-qualifier NARROWING: the inserted span
    "person or organization" happens to sit right after the determiner
    "the", which is exactly what a genuine restrictive premodifier
    insertion looks like ("any land motor vehicle" -> "any PRIVATE
    PASSENGER land motor vehicle"), but here the OLD noun phrase itself
    was also deleted ("named insured" -> gone) -- so this is a
    substitution of the whole referent-naming phrase, not a qualifier
    added on top of an otherwise-intact definition. A determiner sitting
    in front of an inserted span can never, on its own, tell a
    same-referent reword apart from a real narrowing premodifier; only
    the presence (or absence) of a co-occurring deletion of the noun
    phrase it replaces can. See the module docstring's definition
    paragraph and _classify_definition below."""
    span = " ".join(words)
    if len(words) >= 2 and _DEF_EXPANSIVE_START_RE.match(span):
        return "expansive"
    if _DEF_RESTRICTIVE_PHRASE_RE.search(span):
        return "restrictive"
    if allow_bare_determiner_signal and preceding_word in _DETERMINERS:
        return "restrictive"
    return None

# Clause kinds whose `id` is a real, PRINTED enumerator in the source
# document (a clause number, letter, or roman numeral) -- as opposed to
# "paragraph" (a synthesized "¶N" position id) or "section" (often a
# synthesized "§N" bare-heading id), neither of which the document itself
# ever shows a reader. an earlier revision's root fix: renumbering
# one of these (e.g. "4." -> "7." with the body text otherwise identical)
# is a cosmetic-suppression axis exactly like whitespace/dash/quote, but
# the id is stripped out of `text` at segmentation time and never enters
# any of the text comparisons below -- so it must be compared separately,
# gated the same way, or the toggle can never surface a pure renumber.
_ID_COMPARABLE_KINDS = {"numeric", "lettered", "roman"}


@dataclass
class Finding:
    kind: str  # unchanged | cosmetic | narrowed | broadened | modified | added | removed
    old: Clause | None
    new: Clause | None
    detail: str
    score: float | None = None


def _money_values(text: str) -> list[float]:
    return [money_value(m.group("num"), m.group("mult")) for m in _MONEY_RE.finditer(text)]


def _segment_spans(text: str, money_spans: list[tuple[int, int]], resets: set[int]) -> list[tuple[int, int]]:
    """Split *text* into segments at ';'/',' separators AND real sentence
    boundaries (Root fix defect 1 -- see
    _sentence_end_positions), EXCLUDING any ';'/',' that falls inside a
    money literal's own span (it can't be a real segment separator there
    -- see MONEY_RE, which itself never swallows a genuine sentence-
    comma, so any comma still landing inside a money span is a
    thousands-grouping comma the literal legitimately owns). A segment
    must never span a sentence boundary -- otherwise a role keyword in
    one sentence's segment would still be "the only candidate" for an
    amount that actually belongs to the NEXT sentence (see _amount_role's
    single-candidate shortcut)."""
    bounds = {0, len(text)}
    for m in _SPLIT_CHARS_RE.finditer(text):
        pos = m.start()
        if any(s <= pos < e for s, e in money_spans):
            continue
        bounds.add(m.end())
    bounds.update(resets)
    ordered = sorted(bounds)
    return [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)]


def _amount_role(
    text: str,
    seg: tuple[int, int],
    amt_start: int,
    amt_end: int,
    seg_money_spans: list[tuple[int, int]] | None = None,
) -> str | None:
    """Role of the amount at [amt_start, amt_end) in *text*, resolved
    from role-keyword(s) found ONLY within its own segment (see
    _segment_spans) -- never from a keyword elsewhere in the clause.
    Returns None when the segment has no role keyword of its own --
    the caller (_money_roles) then falls back to a role PROPAGATED from
    an earlier segment in the same sentence/list, or "limit" if there is
    none (Root fix). More than one keyword in the segment -> the
    nearest one (by character distance) to this specific amount wins.

    Root fix (wrong-direction defect, 3 phrasings,
    reproduced live at an earlier revision): "self-insured retention limit",
    "aggregate deductible limit", "per-occurrence deductible limit" are
    all a SINGLE floor/retention amount whose compound name happens to
    ALSO contain the bare word "limit" -- "limit" there merely names the
    amount's MAGNITUDE ("the retention's limit is $X"), it does not make
    the amount an insurer limit. But a floor-role keyword (deductible/
    retention/SIR) and a generic "limit"/"aggregate" keyword landing in
    the SAME segment used to go straight to the nearest-distance tiebreak
    above, and "limit"/"aggregate" sits immediately next to the dollar
    figure in every one of these phrasings ("... limit ... is $X",
    "aggregate deductible limit of $X") -- textually nearer than the
    deductible/retention word, which comes earlier in the compound noun
    phrase -- so the tiebreak picked "limit" every time and inverted the
    direction (a floor INCREASE, which narrows coverage, was reported as
    "[BROADENED] limit changed"). Fix (superseded in scope by an earlier revision,
    see below): when a floor-role keyword (deductible/retention/SIR) is
    among a segment's candidates, it takes PRECEDENCE over any
    co-occurring generic "limit"/"aggregate" candidate -- checked, and
    resolved, BEFORE the nearest-distance tiebreak ever runs.

    Root fix (wrong-direction REGRESSION from round
    25, reproduced live at an earlier revision): an earlier revision's floor-over-limit
    precedence was applied to every candidate found ANYWHERE in the
    segment, but a segment can hold MORE THAN ONE amount when no ','/';'
    separates the amount-bearing clauses at all -- "The Limit of
    Insurance is $2,000,000 subject to a deductible of $10,000." has no
    comma/semicolon between "...Insurance is $2,000,000" and "...
    deductible of $10,000" (see _segment_spans, which splits on ';'/','
    and sentence boundaries only), so both amounts land in ONE segment
    with candidates ["Limit", "deductible"]. an earlier revision's precedence then
    threw away the "Limit" candidate for EVERY amount in the segment,
    including the $2,000,000 whose own nearest, and only relevant, role
    word is "Limit" -- misreporting a limit cut as
    "[BROADENED] deductible changed".
    Root fix: the floor-over-limit precedence must be PER-AMOUNT-LOCAL,
    not segment-wide. When the segment holds more than one amount
    (*seg_money_spans* has more than one entry), candidacy for THIS
    amount is first narrowed to the keyword(s) LOCAL to it -- a keyword
    is local to an amount when that amount is the nearest of the
    segment's amounts to it (an earlier revision's original per-amount-local
    contract). Only among an amount's own local keywords does the
    an earlier revision floor-over-limit precedence get consulted. This is exactly
    a no-op for every an earlier revision fixture: each of those phrasings has a
    SINGLE amount in its segment, so every keyword in the segment is
    trivially local to that one amount (there is nothing else for it to
    be local to), and the floor-over-limit precedence still applies
    across the whole segment, unchanged. If no keyword is local to this
    amount at all (every candidate is nearer to a different amount in
    the segment), this amount has no role keyword of its own here --
    same "return None" contract as an empty segment, so the caller falls
    back to a propagated/clause-wide role exactly as it always has for
    an amount with no local keyword."""
    seg_start, seg_end = seg
    candidates = list(_ROLE_KEYWORD_RE.finditer(text, seg_start, seg_end))
    if not candidates:
        return None

    def _dist(m: re.Match, span: tuple[int, int]) -> int:
        s, e = span
        return min(
            abs(m.start() - s),
            abs(m.start() - e),
            abs(m.end() - s),
            abs(m.end() - e),
        )

    # A single role keyword anywhere in the segment governs every amount
    # in it, same as always (an earlier revision's "role word governs subsequent
    # amounts until reset" contract) -- the per-amount-local narrowing
    # below only matters when there is a genuine CHOICE to make between
    # two or more competing keywords, so it must never run ahead of this
    # single-candidate shortcut (an earlier revision's "Deductible $500 for property
    # and $800 for liability" -- one keyword, two amounts, both
    # deductible -- would otherwise see "deductible" as non-local to the
    # second, keyword-less amount and wrongly return None).
    if len(candidates) == 1:
        return candidates[0].lastgroup

    if seg_money_spans and len(seg_money_spans) > 1:
        this_amt = (amt_start, amt_end)

        def _nearest_amt(m: re.Match) -> tuple[int, int]:
            return min(seg_money_spans, key=lambda span: _dist(m, span))

        local = [c for c in candidates if _nearest_amt(c) == this_amt]
        if not local:
            return None
        candidates = local

    floor_candidates = [c for c in candidates if c.lastgroup == "deductible"]
    if floor_candidates:
        candidates = floor_candidates
    if len(candidates) == 1:
        return candidates[0].lastgroup

    return min(candidates, key=lambda m: _dist(m, (amt_start, amt_end))).lastgroup


def _role_reset_boundaries(text: str, money_spans: list[tuple[int, int]]) -> set[int]:
    """Character positions (a boundary's end) after which a propagated
    role must NOT carry forward: a ';' or a real sentence boundary
    (never a plain ',', which is exactly what lets an earlier role word
    govern a later, keyword-less amount in the same comma list -- round
    9 root fix). A ';' inside a money literal's own span is ignored,
    same as _segment_spans; sentence-boundary detection already excludes
    decimals/abbreviations/initials on its own (Root fix,
    an earlier audit defect 1 -- see _sentence_end_positions)."""
    positions: set[int] = set()
    for m in _SPLIT_CHARS_RE.finditer(text):
        if m.group() != ";":
            continue
        if any(s <= m.start() < e for s, e in money_spans):
            continue
        positions.add(m.end())
    positions |= _sentence_end_positions(text, money_spans)
    return positions


def _money_roles(text: str) -> list[tuple[float, str]]:
    """Every monetary amount in *text*, each paired with its ROLE
    (deductible | sublimit | limit | floor | unclear) resolved from its
    own local context (Root fix), with an unresolved
    (keyword-less) comma item inheriting the most recently seen role
    word from earlier in the same sentence/';'-clause (Root fix
    -- see the module docstring and _role_reset_boundaries). A role word
    NEVER leaks across a real sentence boundary, even within a single
    clause's body text that holds more than one sentence (an earlier revision root
    fix defect 1).

    Root fix (Part 2 -- see the block comment above
    _LIMIT_SIGNAL_RE): an amount with no local keyword AND no propagated
    role no longer defaults blindly to "limit". It defaults to "limit"
    only when the WHOLE clause carries a genuine insurer-limit signal
    (_LIMIT_SIGNAL_RE) somewhere, OR carries exclusion-carve-back-GRANT
    framing (_CARVEBACK_GRANT_RE -- "this exclusion does not apply to
    the first $X", "except (for) the first $X", "we will pay (for) the
    first $X", "coverage applies to the first $X"): an earlier revision already
    established that a carve-back grant's own cap is the LIMIT of
    newly-granted coverage, not an insured-borne floor, even though it
    textually overlaps floor phrasing like "does not apply"/"the first"
    -- see _CARVEBACK_GRANT_RE's docstring; that precedent must hold
    here too, or this safety net would re-invert exactly the case round
    23 fixed. A bare un-negated "pay" verb (_POSITIVE_PAY_RE, guarded
    against a negated "will not pay"/"does not pay" by _NEGATED_PAY_RE --
    see the block comment above those two) counts the same as an
    enumerated limit keyword, for the same reason. Otherwise defaults to
    "floor" when the clause carries exclusionary/floor framing
    (_EXCLUSIONARY_FRAMING_RE), or to "unclear" when it carries neither
    -- computed once per call (the clause-level signal
    _classify_numeric's docstring refers to), not re-scanned per
    segment, since the safety net is deliberately a clause-wide fallback
    of last resort, not a new local-context role source (that role
    remains exclusively _ROLE_KEYWORD_RE's job).

    Root fix (Part 2 -- see the block comment above
    _FLOOR_ROLE_CLAUSE_RE): a carve-back GRANT still wins outright
    (unchanged from an earlier revision/23). Otherwise, a floor-role phrase
    (_FLOOR_ROLE_CLAUSE_RE) now suppresses the "limit signal -> limit
    role" branch -- checked, and resolved, BEFORE _LIMIT_SIGNAL_RE/
    has_pay_signal are even consulted, so a clause that carries both
    (e.g. a floor phrase elsewhere and a bare "limit"/"aggregate"/"up
    to" word) reads as the insured-borne floor it actually is, not a
    confident (and backwards) insurer limit.

    Root fix (Part 2 -- see the block comment above
    _POSITIVE_PAY_RE/_INSURED_PAYER_RE): has_pay_signal now additionally
    requires that the bare "pay" verb NOT be exclusively insured-side --
    a clause whose only "pay" usage is governed by an insured-side
    subject ("you must pay", "the insured pays") and carries no
    insurer-side "pay" anywhere else no longer counts as a positive
    limit signal here (it falls through to the EXCLUSIONARY_FRAMING/
    "unclear" branches below instead, never a confident but backwards
    limit reading)."""
    money = list(_MONEY_RE.finditer(text))
    if not money:
        return []
    money_spans = [(m.start(), m.end()) for m in money]
    resets = _role_reset_boundaries(text, money_spans)
    segments = _segment_spans(text, money_spans, resets)
    has_pay_signal = (
        bool(_POSITIVE_PAY_RE.search(text))
        and not _NEGATED_PAY_RE.search(text)
        and not (_INSURED_PAYER_RE.search(text) and not _INSURER_PAYER_RE.search(text))
    )
    if _CARVEBACK_GRANT_RE.search(text):
        fallback_role = "limit"
    elif _FLOOR_ROLE_CLAUSE_RE.search(text):
        fallback_role = "floor"
    elif _LIMIT_SIGNAL_RE.search(text) or has_pay_signal:
        fallback_role = "limit"
    elif _EXCLUSIONARY_FRAMING_RE.search(text):
        fallback_role = "floor"
    else:
        fallback_role = "unclear"

    roles: list[tuple[float, str]] = []
    propagated_role: str | None = None
    prev_seg_end = 0
    for seg_start, seg_end in segments:
        if any(prev_seg_end <= pos <= seg_start for pos in resets):
            propagated_role = None
        seg_candidates = list(_ROLE_KEYWORD_RE.finditer(text, seg_start, seg_end))
        seg_money_spans = [(s, e) for s, e in money_spans if seg_start <= s < seg_end]
        for m in money:
            if not (seg_start <= m.start() < seg_end):
                continue
            role = _amount_role(text, (seg_start, seg_end), m.start(), m.end(), seg_money_spans)
            if role is None:
                role = propagated_role or fallback_role
            value = money_value(m.group("num"), m.group("mult"))
            roles.append((value, role))
        if seg_candidates:
            propagated_role = seg_candidates[-1].lastgroup
        prev_seg_end = seg_end
    return roles


def _role_changed_direction(role: str, o: float, n: float) -> str:
    if role in ("deductible", "floor"):
        # Higher out-of-pocket exposure = narrowed. "floor" (an earlier revision
        # Part 2 safety net) is the same insured-borne-exposure polarity
        # as "deductible" -- see the block comment above _LIMIT_SIGNAL_RE.
        return "narrowed" if n > o else "broadened"
    # sublimit and limit/aggregate share the same polarity: a higher cap
    # is more coverage available (broadened); a lower one is less
    # (narrowed).
    return "broadened" if n > o else "narrowed"


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(normalize(text, suppress_cosmetic=True)))


# Root fix: the
# exclusion-context router used to recognize only "does not apply",
# "exclusion", and "we will not pay" -- so a carve-back/restriction span
# added to an exclusion phrased with any of the other, equally common
# exclusion verbs ("does not cover", bare "excludes"/"excluded", "no
# coverage for", "not covered") never reached _classify_exclusion at all;
# it fell through to _classify_generic instead, whose GENERIC restrictive-
# marker vocabulary (see _GENERIC_RESTRICTIVE_MARKERS) treats an added
# "except"/"unless" as plain restrictive language and reports "narrowed"
# -- backwards for a carve-back that RESTRICTS the exclusion's own
# trigger (restricting WHEN an exclusion fires means LESS is excluded,
# i.e. coverage BROADENS -- see _classify_exclusion's docstring). Every
# phrasing below routes the pair through the SAME scope-signal logic,
# regardless of which exclusion verb the drafter used.
_EXCLUSION_PHRASES = (
    "exclusion",
    "excludes",
    "excluded",
    "does not apply",
    "does not cover",
    "will not cover",
    "will not pay",
    "no coverage for",
    "not covered",
    "this insurance does not",
)


def _is_exclusion(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _EXCLUSION_PHRASES)


# Root fix: a DOLLAR-
# denominated exception carved back OUT OF an exclusion ("except that we
# will pay up to $10,000 for such loss", "however, we will pay up to
# $50,000 for...", "does not apply to the first $25,000 of such loss")
# GRANTS coverage that did not exist -- BROADENING -- but used to lose to
# _classify_numeric's generic "a dollar figure of this role appeared/
# disappeared outright" rule (see _classify_numeric below), which fires
# whenever the $ amount COUNT differs between old and new and reads any
# newly-appeared amount as a narrowing cap, regardless of what kind of
# clause it sits in. That rule is correct for an ordinary coverage grant
# gaining a sublimit (nothing carved back, no prior exception existed --
# the new $ figure really is a fresh restriction on otherwise-uncapped
# coverage) but backwards for a carve-back: the $ amount there is the
# LIMIT of NEWLY-GRANTED coverage inside an exclusion that previously paid
# nothing at all for that loss, not a reduction of existing coverage.
#
# Root fix: inside an exclusion clause, detect whether a carve-back/
# exception marker itself (not just a dollar figure) was added or removed
# -- BEFORE _classify_numeric ever runs -- and let that carry the
# direction (added -> broadened, removed -> narrowed) whether or not the
# carve-back happens to carry a "$" cap. A carve-back present on BOTH
# sides whose cap merely changed value is deliberately NOT special-cased
# here: with the marker unchanged, _classify_numeric's role-count stays
# EQUAL (one amount old, one amount new, no role keyword present so both
# default to "limit"), which already resolves via the ordinary
# higher-limit-is-broader / lower-limit-is-narrower polarity -- exactly
# the semantics a carve-back's OWN cap needs (higher cap = more
# newly-granted coverage = broadened), so no extra logic is needed for
# that case; only the ADDED/REMOVED (unequal-count) shape needs
# reordering ahead of the numeric rule.
_CARVEBACK_MARKER_RE = re.compile(
    r"\bexcept\b"
    r"|\bunless\b"
    r"|\bhowever\b"
    r"|\bbut\s+this\s+exclusion\s+does\s+not\s+apply\b"
    r"|\bdoes\s+not\s+apply\s+to\s+the\s+first\b"
    r"|\bwe\s+will\s+pay\s+up\s+to\b"
    # an earlier revision addition: sibling carve-back-grant
    # verb phrasings for the SAME first-dollar-grant sense -- "we will
    # pay (for) the first $X" (as opposed to "up to $X") and "coverage
    # applies to the first $X" -- so a marker ADDED/REMOVED in either of
    # these spellings gets the same broadened/narrowed precedence
    # treatment as the existing spellings above, instead of falling
    # through to the generic numeric/retention-floor chain.
    r"|\bwe\s+will\s+pay\s+(?:for\s+)?the\s+first\b"
    r"|\bcoverage\s+applies\s+to\s+the\s+first\b",
    re.IGNORECASE,
)


# Root fix (an earlier audit, 1 wrong-direction defect, 2 mirror
# reproductions): a carve-back/exception clause has TWO regions with
# OPPOSITE coverage polarity -- the BASE exclusion (before the marker)
# and the EXCEPTION/carve-back itself (at/after the marker). Growing the
# BASE (a new excluded peril, e.g. "pollution" -> "pollution or
# contamination") narrows coverage exactly like an ordinary exclusion.
# Growing the EXCEPTION (a new carved-back peril, e.g. "except loss
# caused by a hostile fire" -> "...fire or by equipment used to heat the
# insured premises") does the OPPOSITE -- it carves MORE loss back INTO
# coverage, so it BROADENS. _classify_exclusion used to run the same
# "peril span -> narrows" / "trigger-restriction span -> broadens" rule
# everywhere in the clause regardless of which region the changed span
# fell in -- correct for the base, backwards for the exception (see the
# esc_*/tr2_* defects: an "or <peril>" span added INSIDE the exception
# was read as a new excluded peril and reported [NARROWED]; the same
# span removed was read as an excluded peril removed and reported
# [BROADENED] -- both exactly inverted).
#
# Root fix: when the SAME carve-back marker is present on BOTH old and
# new text (an earlier revision's ADD/REMOVED-marker case is unaffected -- that is
# handled entirely by _classify_exclusion_carveback above, before this
# function ever runs), locate the marker's WORD position on each side
# (via _carveback_boundary_index, using the identical word tokenization
# _word_diff_ops already produced) and scope every inserted/removed word
# span to BASE (before the marker) or EXCEPTION (at/after it). A span
# entirely inside the exception gets its polarity INVERTED relative to
# the base-exclusion reading; a span entirely inside the base keeps the
# base reading; a span that itself straddles the boundary is
# unresolvable on its own and casts a synthetic "can't tell" vote so the
# clause falls through to "modified (direction unclear)" rather than
# guessing. This naturally also covers the "edits in both regions with
# conflicting polarity" case: each region's votes are collected exactly
# like every other multi-span exclusion edit, so agreeing votes still
# resolve and disagreeing votes still fall to "modified".
def _carveback_boundary_index(words: list[str]) -> int | None:
    """Word-index split point between the BASE and EXCEPTION regions of
    an exclusion clause already tokenized as *words* (in the SAME order
    _word_diff_ops used) -- the count of words strictly before the first
    carve-back marker, or None if no marker is present in *words* at
    all. Matching is done against " ".join(words) (not the raw source
    text) so the boundary lines up exactly with the word-diff opcode
    indices that reference this same list -- a raw-text character offset
    could straddle a word differently once punctuation/whitespace is
    normalized away."""
    joined = " ".join(words)
    m = _CARVEBACK_MARKER_RE.search(joined)
    if m is None:
        return None
    prefix = joined[: m.start()]
    return len(prefix.split()) if prefix else 0


def _carveback_region(start: int, end: int, boundary: int | None) -> str:
    """"base" | "exception" | "spans_both" for the word span [start:end)
    relative to *boundary* (see _carveback_boundary_index). No boundary
    (marker absent, or not present on both sides) means the clause isn't
    being scoped at all -- everything is "base", preserving the plain
    (non-carve-back) exclusion reading exactly as before an earlier revision."""
    if boundary is None:
        return "base"
    if end <= boundary:
        return "base"
    if start >= boundary:
        return "exception"
    return "spans_both"


def _classify_exclusion_carveback(old_text: str, new_text: str) -> tuple[str, str] | None:
    """"broadened"/"narrowed" (with detail) when a carve-back/exception
    marker was ADDED or REMOVED between *old_text* and *new_text* -- see
    the block comment above. Returns None when the marker's presence is
    UNCHANGED (absent on both sides, or present on both sides -- the
    latter meaning only the carve-back's own cap may have changed, which
    is left to the caller's normal numeric/exclusion chain to resolve)."""
    old_has = bool(_CARVEBACK_MARKER_RE.search(old_text))
    new_has = bool(_CARVEBACK_MARKER_RE.search(new_text))
    if old_has == new_has:
        return None
    if new_has and not old_has:
        return "broadened", "exclusion carve-back added, coverage broadened"
    return "narrowed", "exclusion carve-back removed, coverage narrowed"


def _is_definition(text: str) -> bool:
    return bool(re.match(r'^"[^"]+"\s+means\b', text.strip(), re.IGNORECASE))


def _phrase_signal(old_text: str, new_text: str, phrases=_RESTRICTIVE_PHRASES) -> tuple[bool, bool]:
    """Whole-phrase (not token-set) added/removed check, for restriction
    language that a unigram diff can't see reliably (e.g. "claims-made")."""
    old_l, new_l = old_text.lower(), new_text.lower()
    added = any(p in new_l and p not in old_l for p in phrases)
    removed = any(p in old_l and p not in new_l for p in phrases)
    return added, removed


def _ordered_words(text: str) -> list[str]:
    """Normalized words of *text*, in ORIGINAL ORDER (unlike _tokenize's
    set) -- the input to the word-level diff below."""
    return _WORD_RE.findall(normalize(text, suppress_cosmetic=True))


def _word_diff_ops(old_text: str, new_text: str):
    """Word-level diff between *old_text* and *new_text*: returns
    ``(old_words, new_words, ops)`` where *ops* is every non-"equal"
    opcode `(tag, i1, i2, j1, j2)` from `difflib.SequenceMatcher` run on
    the normalized word sequences -- i.e. exactly the spans of words that
    were actually inserted/deleted/replaced, in document order, never a
    net length/count summary of the whole clause (Root fix,
    an earlier audit -- see the module docstring's exclusion/definition
    paragraphs). ``tag`` is "insert", "delete", or "replace"; "replace"
    carries BOTH an old-side span (i1:i2) and a new-side span (j1:j2) --
    a real substitution, not a pure add or pure remove."""
    old_words = _ordered_words(old_text)
    new_words = _ordered_words(new_text)
    sm = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    return old_words, new_words, ops


# Root fix:
# exclusion direction is decided by what KIND of span was inserted/
# removed, checked ONLY within that span's own text -- never from a
# keyword anywhere else in the clause (a pre-existing, unchanged "caused
# by" elsewhere in the sentence must never license an unrelated word
# swap), and never from pure insertion/deletion LENGTH (the bug: a pure
# insertion used to mean "narrowed" outright, regardless of what the
# inserted text actually said).
#
#   * a NEW EXCLUDED PERIL/ITEM -- a parallel member extending WHAT is
#     excluded -- is signalled by the span STARTING with a coordinating
#     conjunction ("or <peril>", "and <peril>") followed by real content
#     (a bare "and"/"or" with nothing after it is glue, not a new item --
#     see the length>=2 guard below, needed because a real substitution
#     can produce a lone-conjunction insert/delete pair that carries no
#     signal of its own, e.g. inserting "and" to fix list grammar while a
#     LATER span removes an unrelated whole clause).
#   * a RESTRICTION on the exclusion's TRIGGER/SCOPE -- limiting WHEN or
#     HOW it applies -- is signalled by the span containing one of the
#     trigger-restriction phrases.
_EXCL_PERIL_START_RE = re.compile(r"^(?:or|and)\b", re.IGNORECASE)
_EXCL_TRIGGER_RESTRICTION_RE = re.compile(
    r"\b(?:arising\s+from|arising\s+out\s+of|resulting\s+from|caused\s+by|"
    r"only\s+if|solely\s+when|when|provided\s+that|except|unless|"
    r"to\s+the\s+extent)\b",
    re.IGNORECASE,
)


def _exclusion_span_signal(words: list[str]) -> str | None:
    """"peril" | "trigger_restriction" | None for one inserted/removed
    word span in an exclusion clause -- see the block comment above."""
    span = " ".join(words)
    if len(words) >= 2 and _EXCL_PERIL_START_RE.match(span):
        return "peril"
    if _EXCL_TRIGGER_RESTRICTION_RE.search(span):
        return "trigger_restriction"
    return None


def _classify_numeric(old_text: str, new_text: str) -> list[tuple[str, str]] | None:
    """Role-aware amount classification (Root fix). Returns a
    list of (kind, detail) -- one entry PER changed amount, or None if
    no money is present at all or no amount actually changed. See the
    module docstring's numeric-signal paragraph."""
    old_roles = _money_roles(old_text)
    new_roles = _money_roles(new_text)
    if not old_roles and not new_roles:
        return None

    old_by_role: dict[str, list[float]] = {}
    new_by_role: dict[str, list[float]] = {}
    order: list[str] = []
    for _value, role in old_roles + new_roles:
        if role not in old_by_role:
            old_by_role[role] = []
            new_by_role[role] = []
            order.append(role)
    for value, role in old_roles:
        old_by_role[role].append(value)
    for value, role in new_roles:
        new_by_role[role].append(value)

    results: list[tuple[str, str]] = []
    for role in order:
        label = _ROLE_LABELS[role]
        ov, nv = old_by_role[role], new_by_role[role]
        if len(ov) == len(nv):
            # Equal count for this role: pair positionally and report
            # only the value(s) that actually changed -- an UNCHANGED
            # amount of this role must never produce a finding, and must
            # never influence a different role's direction (an earlier revision
            # defect 1).
            for o, n in zip(ov, nv):
                if o == n:
                    continue
                # Root fix: show the ACTUAL
                # amounts, including cents when present, via format_money
                # -- never round to whole dollars ($500.40 -> $500 loses
                # the real change; a whole-dollar amount never grows a
                # spurious ".00").
                if role == "unclear":
                    # an earlier revision Part 2 safety net: this specific amount's
                    # value changed but the clause carries neither a
                    # local role keyword, a propagated one, nor ANY
                    # clause-wide limit or exclusionary/floor signal at
                    # all -- genuinely no basis to pick a direction, so
                    # report it honestly instead of guessing (never
                    # narrowed/broadened on a coin flip).
                    kind = "modified"
                    detail = (
                        f"amount changed from {format_money(o)} to {format_money(n)}, "
                        "direction unclear"
                    )
                else:
                    kind = _role_changed_direction(role, o, n)
                    detail = f"{label} changed from {format_money(o)} to {format_money(n)}"
                results.append((kind, detail))
        elif len(nv) > len(ov):
            # A new amount of this role appeared outright -- something
            # previously unlimited/uncapped/uncharged now is: narrows,
            # regardless of role.
            for val in nv[len(ov):]:
                results.append(("narrowed", f"{label} of {format_money(val)} added"))
        else:
            # An amount of this role that used to exist no longer does:
            # broadens, regardless of role.
            for val in ov[len(nv):]:
                results.append(("broadened", f"{label} of {format_money(val)} removed"))

    if not results:
        return None
    return results


def _classify_reimburse_percent(old_text: str, new_text: str) -> tuple[str, str] | None:
    """Pay-share reimbursement percentage direction (an earlier revision defect 3;
    narrowed to exclude coinsurance framing at an earlier revision -- see
    _REIMBURSE_PCT_RE's and _classify_coinsurance's docstrings). Resolved
    ONLY for an unambiguous single match on each side -- anything else (no
    marker, or more than one candidate on either side) is left unresolved
    rather than guessed."""
    old_m = list(_REIMBURSE_PCT_RE.finditer(old_text))
    new_m = list(_REIMBURSE_PCT_RE.finditer(new_text))
    if len(old_m) != 1 or len(new_m) != 1:
        return None
    o = float(old_m[0].group(1) or old_m[0].group(2))
    n = float(new_m[0].group(1) or new_m[0].group(2))
    if o == n:
        return None
    kind = "broadened" if n > o else "narrowed"
    detail = f"reimbursement percentage changed from {o:g}% to {n:g}%"
    return kind, detail


def _classify_wait_period(old_text: str, new_text: str) -> tuple[str, str] | None:
    """Waiting/elimination period direction (an earlier revision defect 3b): a
    longer period before benefits begin is less coverage (narrowed); a
    shorter one is broadened. Resolved only for an unambiguous single
    match on each side with matching units."""
    old_m = list(_WAIT_PERIOD_RE.finditer(old_text))
    new_m = list(_WAIT_PERIOD_RE.finditer(new_text))
    if len(old_m) != 1 or len(new_m) != 1:
        return None
    o_unit = old_m[0].group(2).lower().rstrip("s")
    n_unit = new_m[0].group(2).lower().rstrip("s")
    if o_unit != n_unit:
        return None
    o, n = float(old_m[0].group(1)), float(new_m[0].group(1))
    if o == n:
        return None
    kind = "narrowed" if n > o else "broadened"
    detail = f"waiting period changed from {o:g} to {n:g} {n_unit}s"
    return kind, detail


def _classify_exclusion(old_text: str, new_text: str):
    """Root fix: direction comes ONLY from what KIND
    of word span was inserted/removed (new peril vs. trigger-restriction
    -- see _exclusion_span_signal and the module docstring), never from
    pure-insertion/pure-deletion LENGTH. Every non-equal opcode from a
    word-level diff casts its own vote; if the votes disagree (or none
    resolve), the pair is reported "modified (direction unclear)" rather
    than guessed.

    Root fix: when the same carve-back marker is
    present on BOTH sides, each span's vote is additionally scoped to
    the BASE or EXCEPTION region (see _carveback_boundary_index /
    _carveback_region above) and a span landing in the EXCEPTION gets
    its polarity inverted relative to the base-exclusion reading. A
    marker absent on either side (or absent altogether) leaves every
    span scoped to "base" -- byte-for-byte the pre-an earlier revision behavior."""
    old_words, new_words, ops = _word_diff_ops(old_text, new_text)

    old_boundary = new_boundary = None
    if _CARVEBACK_MARKER_RE.search(old_text) and _CARVEBACK_MARKER_RE.search(new_text):
        old_boundary = _carveback_boundary_index(old_words)
        new_boundary = _carveback_boundary_index(new_words)

    results: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("insert", "replace") and j2 > j1:
            signal = _exclusion_span_signal(new_words[j1:j2])
            if signal is not None:
                region = _carveback_region(j1, j2, new_boundary)
                if region == "spans_both":
                    results.append(("__unclear__", "change spans both the base exclusion and the exception/carve-back"))
                elif signal == "peril":
                    kind = "narrowed" if region == "base" else "broadened"
                    detail = (
                        "additional exclusionary language added"
                        if region == "base"
                        else "exception/carve-back enlarged, coverage broadened"
                    )
                    results.append((kind, detail))
                elif signal == "trigger_restriction":
                    kind = "broadened" if region == "base" else "narrowed"
                    detail = (
                        "exclusion trigger restricted (exclusion applies more narrowly, coverage broadened)"
                        if region == "base"
                        else "exception/carve-back's own trigger restricted, coverage narrowed"
                    )
                    results.append((kind, detail))
        if tag in ("delete", "replace") and i2 > i1:
            signal = _exclusion_span_signal(old_words[i1:i2])
            if signal is not None:
                region = _carveback_region(i1, i2, old_boundary)
                if region == "spans_both":
                    results.append(("__unclear__", "change spans both the base exclusion and the exception/carve-back"))
                elif signal == "peril":
                    kind = "broadened" if region == "base" else "narrowed"
                    detail = (
                        "excluded peril removed"
                        if region == "base"
                        else "exception/carve-back narrowed, coverage narrowed"
                    )
                    results.append((kind, detail))
                elif signal == "trigger_restriction":
                    kind = "narrowed" if region == "base" else "broadened"
                    detail = (
                        "exclusion trigger restriction removed (exclusion applies more broadly, coverage narrowed)"
                        if region == "base"
                        else "exception/carve-back's own trigger restriction removed, coverage broadened"
                    )
                    results.append((kind, detail))
    kinds = {kind for kind, _detail in results}
    if len(kinds) == 1 and "__unclear__" not in kinds:
        return results[0]
    return "modified", "exclusion wording changed, direction unclear"


def _direction_from_markers(
    old_text: str,
    new_text: str,
    restrictive_markers: set[str],
    inclusive_markers: set[str],
    use_phrases: bool = False,
):
    old_words, new_words = _tokenize(old_text), _tokenize(new_text)
    added, removed = new_words - old_words, old_words - new_words
    added_restrictive = bool(added & restrictive_markers)
    added_inclusive = bool(added & inclusive_markers)
    removed_restrictive = bool(removed & restrictive_markers)
    removed_inclusive = bool(removed & inclusive_markers)
    if use_phrases:
        phrase_added, phrase_removed = _phrase_signal(old_text, new_text)
        added_restrictive = added_restrictive or phrase_added
        removed_restrictive = removed_restrictive or phrase_removed
    if added_restrictive and not added_inclusive:
        return "narrowed", added, removed
    if added_inclusive and not added_restrictive:
        return "broadened", added, removed
    if removed_inclusive and not removed_restrictive:
        return "narrowed", added, removed
    if removed_restrictive and not removed_inclusive:
        return "broadened", added, removed
    return None, added, removed


def _classify_definition(old_text: str, new_text: str):
    """Root fix: the marker-word pass (unigram
    added/removed word SET, unordered) runs first and still resolves the
    common case. When it doesn't, fall to the structural per-span signal
    (_definition_span_signal) -- NEVER to a one-sided add/remove word-set
    guess (that was the bug: "content added" was reported "broadened"
    even when the added content was a RESTRICTIVE qualifier, not a new
    list member -- see the module docstring). Every non-equal opcode
    from a word-level diff casts its own vote; if the votes disagree (or
    none resolve), "modified (direction unclear)"."""
    direction, added, removed = _direction_from_markers(
        old_text, new_text, _RESTRICTIVE_MARKERS, _INCLUSIVE_MARKERS
    )
    if direction == "narrowed":
        return "narrowed", "restrictive language added to definition"
    if direction == "broadened":
        return "broadened", "inclusive language added to definition"

    old_words, new_words, ops = _word_diff_ops(old_text, new_text)

    # Root fix: a SUBSTITUTION -- both an
    # insert-side span and a delete-side span present in the same
    # clause's word diff (whether as one "replace" opcode or as separate
    # "insert"/"delete" opcodes around a matched anchor word, e.g. "named
    # insured" -> "person or organization named", where SequenceMatcher
    # aligns "named" and leaves an insert + a delete either side of it) --
    # is a REWORD of the definiendum, not a clean restrictive insertion
    # ("with the rest of the definition intact") or a clean expansive/
    # restrictive removal. The bare determiner-adjacency fallback in
    # _definition_span_signal must not fire in that shape (see its
    # docstring); an explicit keyword/coordinating-word signal still can,
    # since that's real evidence regardless of a co-occurring delete
    # elsewhere in the same clause.
    is_substitution = any(tag in ("insert", "replace") and j2 > j1 for tag, i1, i2, j1, j2 in ops) and any(
        tag in ("delete", "replace") and i2 > i1 for tag, i1, i2, j1, j2 in ops
    )

    results: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("insert", "replace") and j2 > j1:
            preceding = new_words[j1 - 1] if j1 > 0 else None
            signal = _definition_span_signal(
                new_words[j1:j2], preceding, allow_bare_determiner_signal=not is_substitution
            )
            if signal == "expansive":
                results.append(("broadened", "content added to definition's inclusive list"))
            elif signal == "restrictive":
                results.append(("narrowed", "restrictive qualifier added to definition"))
        if tag in ("delete", "replace") and i2 > i1:
            preceding = old_words[i1 - 1] if i1 > 0 else None
            signal = _definition_span_signal(
                old_words[i1:i2], preceding, allow_bare_determiner_signal=not is_substitution
            )
            if signal == "expansive":
                results.append(("narrowed", "content removed from definition's inclusive list"))
            elif signal == "restrictive":
                results.append(("broadened", "restrictive qualifier removed from definition"))
    kinds = {kind for kind, _detail in results}
    if len(kinds) == 1:
        return results[0]
    return "modified", "definition wording changed, direction unclear"


def _classify_generic(old_text: str, new_text: str):
    direction, _added, _removed = _direction_from_markers(
        old_text,
        new_text,
        _GENERIC_RESTRICTIVE_MARKERS,
        _GENERIC_INCLUSIVE_MARKERS,
        use_phrases=True,
    )
    if direction == "narrowed":
        return "narrowed", "restrictive language added"
    if direction == "broadened":
        return "broadened", "inclusive language added"
    # No length-based fallback here: an unresolved generic edit is
    # reported honestly rather than guessed from which side is longer.
    return "modified", "wording changed, direction unclear"


def _classify_signal(old_text: str, new_text: str, context: str = "") -> list[tuple[str, str]]:
    """The shared single-fragment classifier chain (numeric -> pct ->
    wait period -> exclusion -> definition -> generic), factored out of
    classify_pair_multi's tail so BOTH the whole-clause path and the
    per-sentence backup path below call the exact same logic on
    whatever text fragment they hand it -- never a hand-duplicated copy
    that could drift. Always returns at least one (kind, detail) pair
    (the generic fallback never returns None).

    *context* (an earlier revision addition): extra text -- the clause's
    own HEADING when called from the per-sentence backup on a BODY
    sentence -- consulted ONLY for the _is_exclusion routing check below,
    never as part of the actual old_text/new_text comparison. A numbered
    clause's heading routinely names what its body sentences are doing
    ("4. EXCLUSIONS\nThe company does not cover flood.") without the
    body sentence itself repeating the word "exclusion" anywhere -- the
    whole-clause path already saw this correctly because old_text/
    new_text used to BE "EXCLUSIONS The company does not cover flood."
    (heading and body glued together); the per-sentence path scopes each
    Finding's own comparison text down to just its own sentence for a
    precise citation (see classify_pair_multi), which would otherwise
    blind this same routing check to the heading's own wording.

    Root fix: when the clause is an exclusion, the
    carve-back-marker-added/removed check (_classify_exclusion_carveback)
    runs BEFORE _classify_numeric -- see that function's docstring. This
    must be checked first in the chain: _classify_numeric would otherwise
    intercept any pair where a "$" amount's COUNT differs (exactly what a
    newly-added/removed carve-back does) and misread it as an ordinary
    sublimit added/removed, before the exclusion-scope logic ever runs.

    Root fix: retention-floor / attachment-point /
    coinsurance-requirement framing (_classify_retention_floor /
    _classify_attachment / _classify_coinsurance) run next, AFTER the
    carve-back check but still BEFORE _classify_numeric and
    _classify_reimburse_percent -- see the block comment above those
    three functions. Each is a no-op (returns None) unless its own
    phrase marker is present, so this never changes behavior for a
    clause that isn't one of these three framings.

    Root fix: _classify_retention_floor's own first
    check is now _CARVEBACK_GRANT_RE (an exclusion carve-back's
    first-dollar GRANT, e.g. "this exclusion does not apply to the first
    $X") -- when that matches, the function bails out immediately so the
    pair falls through to _classify_numeric's correctly-polarized "limit"
    default, giving the carve-back-grant check first refusal over the
    plain-English insured-borne-retention family _RETENTION_FLOOR_RE also
    grew this round, even though the two overlap textually on "does not
    apply to the first". See the block comment above _CARVEBACK_GRANT_RE
    and _RETENTION_FLOOR_RE."""
    is_exclusion_ctx = _is_exclusion(old_text) or _is_exclusion(new_text) or _is_exclusion(context)
    if is_exclusion_ctx:
        carveback = _classify_exclusion_carveback(old_text, new_text)
        if carveback is not None:
            return [carveback]
    retention = _classify_retention_floor(old_text, new_text)
    if retention is not None:
        return [retention]
    attachment = _classify_attachment(old_text, new_text)
    if attachment is not None:
        return [attachment]
    coinsurance = _classify_coinsurance(old_text, new_text)
    if coinsurance is not None:
        return [coinsurance]
    numeric = _classify_numeric(old_text, new_text)
    if numeric is not None:
        return numeric
    pct = _classify_reimburse_percent(old_text, new_text)
    if pct is not None:
        return [pct]
    wait = _classify_wait_period(old_text, new_text)
    if wait is not None:
        return [wait]
    if is_exclusion_ctx:
        return [_classify_exclusion(old_text, new_text)]
    if _is_definition(old_text) or _is_definition(new_text):
        return [_classify_definition(old_text, new_text)]
    return [_classify_generic(old_text, new_text)]


def _split_clause_sentences(text: str) -> list[str]:
    """Split *text* at real sentence boundaries (the same
    abbreviation/decimal/initial-guarded detector classify.py already
    uses for money-role resets, see sentence_boundary_starts), returning
    the non-empty sentence fragments in order. A clause with no internal
    sentence boundary at all returns a single-element list (the whole
    text) -- callers gate on len() > 1 before treating this as a genuine
    multi-sentence clause."""
    positions = sentence_boundary_starts(text)
    if not positions:
        stripped = text.strip()
        return [stripped] if stripped else []
    bounds = [0] + positions + [len(text)]
    return [
        text[bounds[i]:bounds[i + 1]].strip()
        for i in range(len(bounds) - 1)
        if text[bounds[i]:bounds[i + 1]].strip()
    ]


def _split_clause_sentences_with_heading(text: str, heading: str) -> list[str]:
    """Like :func:`_split_clause_sentences`, but keeps a numbered/roman/
    lettered clause's own HEADING (segment.py always places it as the
    first thing in `text` -- see Clause.heading and segment()'s
    `current["lines"] = [heading] ...`) as its OWN leading unit, never
    merged into the clause's first real body sentence.

    A heading routinely has no terminal '.'/'?'/'!' of its own
    ("EXCLUSIONS", "LIMITS OF INSURANCE") -- plain sentence-boundary
    splitting would glue it onto whatever body sentence follows ("LIMITS
    OF INSURANCE The aggregate limit is $1,000,000." reads as a SINGLE
    sentence to the boundary detector). That would make a pure
    heading-only rename (an earlier revision's an earlier audit fix) indistinguishable
    from a change to the first body sentence once classify_pair_multi's
    per-sentence backup (an earlier revision) is in play -- report.py's numbered-
    heading-rename content-delta suppression needs the heading isolated
    on its own to evaluate it independently of the body. When *heading*
    is empty (or *text* doesn't actually start with it -- e.g. a
    "paragraph" clause's own scope-heading field, which was never part
    of its `text` to begin with), this is exactly
    :func:`_split_clause_sentences`."""
    heading = heading.strip()
    # Only pull the heading out as its own leading unit when:
    #   (1) the clause actually holds MORE than just that heading line
    #       (i.e. continuation lines were absorbed into its body -- see
    #       segment.py's Root fix). When `text` IS the heading
    #       verbatim (a single physical line under the enumerator, with
    #       everything -- possibly several sentences -- squeezed onto
    #       that one line, e.g. an earlier audit's wrap06/wrapreal repro), there
    #       is no separate body to split off: fall straight through to
    #       the plain splitter, which still isolates each real sentence
    #       on that line correctly by its own terminal punctuation; AND
    #   (2) the heading text is actually heading-SHAPED (segment.py's own
    #       `_is_bare_heading_line` -- short, no terminal '.'/'?'/'!',
    #       ALL-CAPS or Title-Case-with-separator). Otherwise this
    #       "heading" is really just the wrapped FIRST physical line of a
    #       single ongoing sentence with no punctuation of its own yet
    #       ("4. The aggregate limit of insurance is\n$1,000,000 under
    #       this policy." -- heading = "The aggregate limit of insurance
    #       is") -- splitting it off here would incorrectly chop ONE
    #       sentence into two.
    if (
        heading
        and text.startswith(heading)
        and len(text) > len(heading)
        and _is_bare_heading_line(heading)
    ):
        body = text[len(heading):].strip()
        body_sentences = _split_clause_sentences(body) if body else []
        return [heading] + body_sentences
    return _split_clause_sentences(text)


def classify_pair_multi(old: Clause, new: Clause, suppress_cosmetic: bool = True) -> list[Finding]:
    """Classify a clause pair into ONE OR MORE findings. Almost always a
    single finding; a clause with more than one independently-changed
    monetary amount (A defect, e.g. an aggregate raised AND a
    sublimit cut in the same sentence) produces one Finding PER changed
    amount, so a narrowing is never dropped behind a co-occurring
    broadening. See classify_pair for the common single-finding case.

    Per-sentence classification (an earlier revision's original backup requirement,
    broadened by an earlier revision): a clause pair that holds more
    than one real sentence on BOTH sides is classified SENTENCE BY
    SENTENCE rather than as one blob, so:

      * every independently-changed sentence gets its own Finding --
        never just the FIRST applicable classifier signal on the whole
        clause's merged text, which would silently drop every change
        after the first;
      * this now fires for as few as ONE changed sentence (an earlier revision --
        previously required 2+, deferring a single-sentence change to
        the whole-text chain below). Since segment.py (an earlier revision root
        fix) now swallows a numbered/roman/lettered clause's ENTIRE body
        -- including what used to be separate standalone-sentence atoms
        under the old line-break-gated segmentation, and regardless of
        exactly where a physical line break falls within it -- recall
        for "a clause followed by other, unrelated standalone sentences"
 now depends entirely
        on this per-sentence split running for a single changed sentence
        too, not just two or more;
      * each per-sentence Finding is given its OWN precise citation --
        `old`/`new` are shallow copies of the clause with `text`
        replaced by just that one sentence -- so a citation quotes the
        specific changed sentence, never the whole multi-sentence blob
        (this is what keeps a real change from ever looking like it also
        touched -- or fabricated a finding out of -- an unrelated
        sibling sentence in the same clause)."""
    # an earlier revision's root fix: with suppression OFF, compare
    # the raw (line-break-preserving) text for a "paragraph" clause instead
    # of its whitespace-collapsed `text` -- see Clause.text_raw's docstring
    # in segment.py. Every other clause kind already keeps its own
    # original line breaks in `text`, so this is a no-op for them
    # (text_raw falls back to text). With suppression ON this is entirely
    # unused -- default-mode comparisons are byte-for-byte unchanged.
    cmp_old = old.text if suppress_cosmetic else (old.text_raw or old.text)
    cmp_new = new.text if suppress_cosmetic else (new.text_raw or new.text)

    # A printed enumerator (clause number/letter/roman numeral) changing
    # is likewise a cosmetic-suppression axis, but the id never enters
    # `text`/`text_raw` at all -- compare it directly, gated the same way.
    id_changed = (
        not suppress_cosmetic
        and old.kind in _ID_COMPARABLE_KINDS
        and new.kind in _ID_COMPARABLE_KINDS
        and old.id != new.id
    )

    light_old = light_normalize(cmp_old, suppress_cosmetic)
    light_new = light_normalize(cmp_new, suppress_cosmetic)
    if light_old == light_new and not id_changed:
        return [Finding(kind="unchanged", old=old, new=new, detail="no textual change (may have moved/renumbered)")]

    norm_old = normalize(cmp_old, suppress_cosmetic)
    norm_new = normalize(cmp_new, suppress_cosmetic)
    if norm_old == norm_new:
        if suppress_cosmetic:
            return [Finding(kind="cosmetic", old=old, new=new, detail="formatting-only change (suppressed)")]
        # suppress_cosmetic is off: the SAME comparison, run with
        # suppression on, would have collapsed to a no-op (identical
        # content once the enumerator/whitespace/reflow is set aside) --
        # surface that honestly instead of falling through into the
        # semantic classifiers below, which have nothing left to compare
        # once old.text == new.text.
        if id_changed:
            detail = f"clause renumbered from {old.id!r} to {new.id!r} (formatting-only otherwise; suppressed by default)"
        else:
            detail = "formatting-only change (whitespace/reflow) -- suppressed by default"
        return [Finding(kind="modified", old=old, new=new, detail=detail)]

    # Root fix:
    # engage the per-sentence split whenever the clause genuinely holds 2+
    # real sentences on BOTH sides (equal count -- a mismatched count means
    # a sentence was itself added/removed, a structural change the
    # whole-text chain below is already built to handle via
    # _classify_numeric's added/removed-amount path and the
    # exclusion/definition containment signals; guessing a
    # sentence-for-sentence pairing there would risk a wrong pairing) AND
    # at least ONE of those sentence pairs independently shows a real,
    # non-cosmetic change (an earlier revision required 2+ here; an earlier revision lowers this
    # to 1+ -- see the module docstring above for why: recall for a single
    # changed sentence trailing an otherwise-unchanged clause now depends
    # on this path, since segment.py no longer ever spins that sentence off
    # as its own separate atom). Each surfaced Finding is scoped to its OWN
    # sentence text (not the whole clause) for a precise, unambiguous
    # citation -- see cite.py, which quotes straight from `Finding.old`/
    # `Finding.new`.
    old_sentences = _split_clause_sentences_with_heading(old.text, old.heading)
    new_sentences = _split_clause_sentences_with_heading(new.text, new.heading)
    if len(old_sentences) > 1 and len(old_sentences) == len(new_sentences):
        per_sentence: list[Finding] = []
        for o_sent, n_sent in zip(old_sentences, new_sentences):
            if normalize(o_sent, suppress_cosmetic) == normalize(n_sent, suppress_cosmetic):
                continue
            sent_old = replace(old, text=o_sent, text_raw="")
            sent_new = replace(new, text=n_sent, text_raw="")
            # Give the exclusion/definition ROUTING check (not the actual
            # comparison) visibility into the clause's own heading -- see
            # _classify_signal's *context* param docstring above.
            context = old.heading if o_sent != old.heading else ""
            for kind, detail in _classify_signal(o_sent, n_sent, context=context):
                per_sentence.append(Finding(kind=kind, old=sent_old, new=sent_new, detail=detail))
        if len(per_sentence) >= 1:
            # A genuine multi-sentence clause holding one or more
            # independent changes -- never collapse to the first
            # matching classifier's single result on the merged blob and
            # drop the rest (the same "a real change is never silently
            # dropped" invariant the earlier segmentation fix enforced
            # across physical lines, now enforced within one clause and
            # independent of exactly where those physical lines fall --
            # see segment.py's Root fix).
            return per_sentence

    return [Finding(kind=kind, old=old, new=new, detail=detail) for kind, detail in _classify_signal(old.text, new.text)]


def classify_pair(old: Clause, new: Clause, suppress_cosmetic: bool = True) -> Finding:
    """Single-finding convenience wrapper around classify_pair_multi, for
    the common case (at most one independently-classified change per
    clause pair). Callers that must see every change in a clause with
    more than one changed amount should use classify_pair_multi
    directly -- see its docstring."""
    return classify_pair_multi(old, new, suppress_cosmetic)[0]


def classify_removed(old: Clause) -> Finding:
    return Finding(kind="removed", old=old, new=None, detail="clause present in old version only")


def classify_added(new: Clause) -> Finding:
    return Finding(kind="added", old=None, new=new, detail="clause present in new version only")
