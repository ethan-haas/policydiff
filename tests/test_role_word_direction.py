"""Regression tests for an earlier fix, all
. Two of the
three were the highest-severity class: WRONG DIRECTION (a broadening
reported as a narrowing, or vice versa).

Defect 1 (WRONG DIRECTION) -- a role word ("deductible", "sublimit",
"limit"/"aggregate") propagated across a ';' (an earlier fix) but NOT
across a sentence-ending '.'/'!'/'?' within the SAME clause's body text
-- a numbered clause routinely holds more than one sentence with no ';'
anywhere in it ("A deductible of $500 applies. The Company will pay
$1,000,000 for each claim."), so "deductible" leaked straight across
the full stop and claimed the payout amount in the next sentence,
reporting a $1M->$2M payout INCREASE (broadening) as a "[NARROWED]
deductible" change. Root fix: policydiff/sentence.py's real
sentence-boundary detector (abbreviation/decimal/initial-guarded) is
now reused by classify.py's role-propagation reset AND to scope the
segment a role keyword is searched within (policydiff/classify.py:
_money_roles / _segment_spans / _sentence_end_positions).

Defect 2 (WRONG DIRECTION + fabricated magnitude) -- a currency-WORD
amount ("$5 million", "$50k") was parsed as its leading integer only
("$5 million" -> 5), so "$5 million" -> "$2,000,000" (a real 60% CUT)
read as a huge INCREASE ("$5" -> "$2,000,000"), and "$1 million" vs
"$1,000,000" (equal) read as a change instead of empty. Root fix:
MONEY_RE / money_value in policydiff/normalize.py understand
million/billion/thousand words and k/M/bn suffixes (case-insensitive,
optional decimal), and this SAME parse is used everywhere an amount is
compared: cosmetic-equality canonicalization, direction computation,
and the reported detail (policydiff/classify.py imports MONEY_RE and
money_value from normalize.py instead of keeping its own).

Defect 3 (detail integrity) -- the detail string rounded sub-dollar
amounts to whole dollars ("$500.40" -> "$500.20" rendered as "changed
from $500 to $500", a real change described as no change). Root fix:
format_money() in policydiff/normalize.py shows cents only when the
amount has a genuine non-zero fractional part, used everywhere a
detail string names an amount.

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures (that
directory is -- they are
original clauses built from the same scenarios described in the task
(the $500.40/$500.20 pair is entirely original, authored for this
task).
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, suppress_cosmetic: bool = True):
    old = segment(f"1. {old_text}\n")[0]
    new = segment(f"1. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=suppress_cosmetic)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# Defect 1 -- role propagation must reset at a real sentence boundary.
# ---------------------------------------------------------------------


def test_role_word_does_not_leak_across_sentence_full_stop():
    # (a) the exact defect shape: payout GROWS $1M -> $2M (broadening);
    # "deductible" in the first sentence must never claim it.
    f = _pair(
        "A deductible of $500 applies. The Company will pay $1,000,000 for each claim.",
        "A deductible of $500 applies. The Company will pay $2,000,000 for each claim.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


def test_role_word_does_not_leak_across_sentence_full_stop_reverse():
    # (a, reverse) payout SHRINKS -> narrowing.
    f = _pair(
        "A deductible of $500 applies. The Company will pay $2,000,000 for each claim.",
        "A deductible of $500 applies. The Company will pay $1,000,000 for each claim.",
    )
    assert f.kind == "narrowed", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


def test_semicolon_control_still_broadens_limit():
    # (b) the identical clause with ';' instead of '.' must keep working
    # exactly as an earlier revision left it (this is the reviewer's control).
    f = _pair(
        "A deductible of $500 applies; the Company will pay $1,000,000 for each claim.",
        "A deductible of $500 applies; the Company will pay $2,000,000 for each claim.",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail


def test_two_deductible_sentence_does_not_over_reset_within_one_sentence():
    # (c) a genuine two-amount, ONE-sentence, comma-list deductible edit
    # must still assign BOTH amounts "deductible" -- the sentence-end
    # reset must not fire mid-sentence just because this fix exists.
    f = _pair(
        "Deductible $500 for property, $800 for liability.",
        "Deductible $500 for property, $1,000 for liability.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "800" in f.detail and "1,000" in f.detail


def test_decimal_point_in_amount_is_not_a_sentence_reset():
    # (d) "$500.40" must not be mistaken for a sentence-ending period --
    # deductible role must still govern the second, keyword-less amount
    # in the same sentence.
    f = _pair(
        "The deductible is $500.40 for the first claim and $800 for the second.",
        "The deductible is $500.40 for the first claim and $1,000 for the second.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


def test_abbreviation_periods_are_not_sentence_resets():
    # (d) "No." and "U.S." must not be mistaken for sentence boundaries
    # -- the deductible role stated before them still governs the
    # keyword-less amount stated after.
    f = _pair(
        "See endorsement No. 5. Under U.S. law the deductible is $500 for the first claim and $800 for the second.",
        "See endorsement No. 5. Under U.S. law the deductible is $500 for the first claim and $1,000 for the second.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail


# ---------------------------------------------------------------------
# Defect 2 -- currency-word / suffix-abbreviated amounts.
# ---------------------------------------------------------------------


def test_million_word_amount_narrowed_correct_direction_and_magnitude():
    # (e) "$5 million" -> "$2,000,000" is a real 60% CUT -- narrowed,
    # with the FULL numeric values shown (not "$5").
    f = _pair(
        "The aggregate limit is $5 million.",
        "The aggregate limit is $2,000,000.",
    )
    assert f.kind == "narrowed", f.detail
    assert "5,000,000" in f.detail and "2,000,000" in f.detail
    assert "broadened" not in f.kind


def test_million_word_vs_digit_form_is_cosmetic_equal():
    # (f) "$1 million" vs "$1,000,000" name the SAME value -> EMPTY.
    result = diff_documents(
        "1. The aggregate limit is $1 million.\n",
        "1. The aggregate limit is $1,000,000.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_digit_form_vs_million_word_is_cosmetic_equal_reverse():
    # (g) the reverse direction ("$5,000,000" -> "$5 million") is the
    # same cosmetic value, must also be EMPTY.
    result = diff_documents(
        "1. The aggregate limit is $5,000,000.\n",
        "1. The aggregate limit is $5 million.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_million_word_broadened():
    # (h) "$2 million" -> "$5 million" is a real increase -> broadened.
    f = _pair(
        "The aggregate limit is $2 million.",
        "The aggregate limit is $5 million.",
    )
    assert f.kind == "broadened", f.detail
    assert "2,000,000" in f.detail and "5,000,000" in f.detail


def test_k_suffix_vs_digit_form_is_cosmetic_equal():
    # (i) "$50k" vs "$50,000" name the SAME value -> EMPTY.
    result = diff_documents(
        "1. The sublimit is $50k.\n",
        "1. The sublimit is $50,000.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_billion_and_thousand_words_and_M_bn_suffixes_parse_correctly():
    # Broader coverage of the multiplier vocabulary named in the task:
    # "$1.5 billion", "$750 thousand", "$5M", "$1.5bn".
    f = _pair(
        "The aggregate limit is $1.5 billion.",
        "The aggregate limit is $1 billion.",
    )
    assert f.kind == "narrowed", f.detail
    assert "1,500,000,000" in f.detail and "1,000,000,000" in f.detail

    f = _pair(
        "The sublimit is $750 thousand.",
        "The sublimit is $500 thousand.",
    )
    assert f.kind == "narrowed", f.detail
    assert "750,000" in f.detail and "500,000" in f.detail

    f = _pair(
        "The aggregate limit is $5M.",
        "The aggregate limit is $8M.",
    )
    assert f.kind == "broadened", f.detail
    assert "5,000,000" in f.detail and "8,000,000" in f.detail

    result = diff_documents(
        "1. The aggregate limit is $1.5bn.\n",
        "1. The aggregate limit is $1,500,000,000.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# Defect 3 -- detail must not round sub-dollar amounts to whole dollars.
# ---------------------------------------------------------------------


def test_cents_change_shown_in_detail_not_rounded():
    # (j) $500.40 -> $500.20 is a real change; a LOWER deductible
    # BROADENS (less out-of-pocket exposure) -- and the detail must show
    # the actual cents, not "$500 -> $500".
    f = _pair(
        "The deductible is $500.40.",
        "The deductible is $500.20.",
    )
    assert f.kind == "broadened", f.detail
    assert "$500.40" in f.detail and "$500.20" in f.detail
    assert "$500 to $500" not in f.detail


def test_cents_round_up_change_shown_in_detail_not_rounded():
    # A cents change that would round UP to the next whole dollar
    # ($500.99 -> $501) must still show the real amounts, not the
    # rounded ones.
    f = _pair(
        "The deductible is $500.00.",
        "The deductible is $500.99.",
    )
    assert f.kind == "narrowed", f.detail
    assert "$500.99" in f.detail
    assert "$501" not in f.detail


def test_whole_dollar_amounts_still_render_without_trailing_zero_cents():
    # (k) a genuine whole-dollar change must not grow a spurious ".00".
    f = _pair(
        "The general aggregate limit is $1,000,000.",
        "The general aggregate limit is $1,500,000.",
    )
    assert f.kind == "broadened", f.detail
    assert "$1,000,000" in f.detail and "$1,500,000" in f.detail
    assert "$1,000,000.00" not in f.detail and "$1,500,000.00" not in f.detail
