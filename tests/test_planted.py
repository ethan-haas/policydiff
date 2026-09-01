"""Planted-change harness (gate 1).

policy_new_planted.txt injects 13 real coverage changes spanning: added
exclusion, removed coverage, narrowed sublimit, changed deductible,
altered definition (both directions), an unnumbered-preamble edit with
no resolvable direction, plus a moved-but-unchanged clause. Every one of
the 13 must be reported, and the moved clause must NOT be.
"""
from policydiff.report import diff_documents

from tests.fixtures.manifest import PLANTED, MOVED_UNCHANGED_NEEDLE


def _haystack(citation) -> str:
    parts = [citation.detail, citation.old_quote or "", citation.new_quote or ""]
    return " ".join(parts).lower()


def test_all_twelve_planted_changes_are_reported(old_text, new_planted_text):
    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)

    non_suppressed = [
        (f, c)
        for f, c in zip(result.findings, result.citations)
        if f.kind not in ("unchanged", "cosmetic")
    ]

    # Gate: exactly the 13 planted real changes, nothing more, nothing less.
    assert len(non_suppressed) == len(PLANTED) == 13, (
        f"expected {len(PLANTED)} reported changes, got {len(non_suppressed)}: "
        f"{[(f.kind, c.detail) for f, c in non_suppressed]}"
    )

    for label, expected_kind, needle in PLANTED:
        matches = [(f, c) for f, c in non_suppressed if needle.lower() in _haystack(c)]
        assert matches, f"planted change not found: {label!r} (needle={needle!r})"
        assert len(matches) == 1, f"planted change matched more than one finding: {label!r}"
        f, c = matches[0]
        assert f.kind == expected_kind, (
            f"planted change {label!r}: expected kind={expected_kind!r}, got {f.kind!r} ({c.detail})"
        )


def test_moved_clause_is_not_reported_as_a_change(old_text, new_planted_text):
    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)

    moved = [
        (f, c)
        for f, c in zip(result.findings, result.citations)
        if MOVED_UNCHANGED_NEEDLE.lower() in _haystack(c)
    ]
    assert moved, "expected to find the moved 'Occurrence' definition clause in the diff output"
    for f, c in moved:
        assert f.kind == "unchanged", (
            f"moved-but-unchanged clause was misclassified as {f.kind!r} ({c.detail})"
        )

    # And it must not appear in the (default, suppressed) human report.
    from policydiff.report import human_report

    report_text = human_report(result, verbose=False)
    assert "occurrence" not in report_text.lower() or "means an accident" not in report_text.lower()
