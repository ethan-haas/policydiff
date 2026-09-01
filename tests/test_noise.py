"""Noise / false-positive gate (gate 2).

policy_old_noise.txt is policy_old.txt reflowed, renumbered (+100 on
every clause id), with defined terms recapitalized and quotes swapped to
curly quotes -- ZERO semantic change. The report must be EMPTY.
"""
from policydiff.report import diff_documents, human_report


def test_formatting_only_diff_is_empty(old_text, old_noise_text):
    result = diff_documents(old_text, old_noise_text, suppress_cosmetic=True)

    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed == [], (
        f"formatting-only diff produced {len(non_suppressed)} false positives: "
        f"{[(f.kind, f.detail) for f in non_suppressed]}"
    )

    report_text = human_report(result, verbose=False)
    assert "No coverage-relevant changes found." in report_text


def test_renumbering_alone_does_not_confuse_alignment(old_text, old_noise_text):
    result = diff_documents(old_text, old_noise_text, suppress_cosmetic=True)
    # 24 clauses in each document (1 unnumbered preamble/title paragraph +
    # 16 numbered + 7 section headers); every single one should align to
    # its content-twin despite the +100 shift.
    assert len(result.old_clauses) == len(result.new_clauses) == 24
    assert len(result.findings) == 24
    assert all(f.kind in ("unchanged", "cosmetic") for f in result.findings)
