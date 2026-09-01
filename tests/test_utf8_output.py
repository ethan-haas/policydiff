"""Regression test for defect 3: a finding whose quote contains
a character outside cp1252 (e.g. CJK, U+2212 minus) used to crash
`print(human_report(...))` on Windows (default console code page is
cp1252), rc=1, and the --out JSON was NEVER written because it was
generated AFTER the crashing print. This exercises the CLI as a real
subprocess (not the in-process API) so it actually goes through stdout,
the same path that broke.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_cli(old_path: Path, new_path: Path, out_path: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "policydiff", str(old_path), str(new_path), "--out", str(out_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
    )


def test_cli_survives_non_cp1252_characters_and_writes_json(tmp_path):
    old_path = tmp_path / "old.txt"
    new_path = tmp_path / "new.txt"
    out_path = tmp_path / "out.json"

    old_path.write_text(
        '1. Definitions. "Insured" means the named company.\n', encoding="utf-8"
    )
    # CJK text + a genuine Unicode minus sign (U+2212), both outside
    # cp1252 -- a real-world case (translated endorsement, engineering
    # unit convention) not an artificial edge case.
    new_path.write_text(
        '1. Definitions. "Insured" means the named company and its '
        "subsidiary 保险 unit, adjusted by −$500.\n",
        encoding="utf-8",
    )

    import os

    env = dict(os.environ)
    # Force the narrowest possible console encoding so the test actually
    # exercises the failure mode even on a UTF-8-default CI runner.
    env["PYTHONIOENCODING"] = "cp1252"

    proc = _run_cli(old_path, new_path, out_path, env)

    assert proc.returncode == 0, (
        f"CLI crashed on valid UTF-8 input: rc={proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert out_path.exists(), "the --out JSON must always be written for valid input"

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["findings"], "expected at least one finding"
    joined = json.dumps(data, ensure_ascii=False)
    assert "保险" in joined  # the CJK text round-tripped, not mangled/dropped


def test_cli_empty_report_case_also_survives_non_cp1252_env(tmp_path):
    # Even when there's nothing to report, the human-report print path
    # (and the earlier-written JSON) must not choke on the environment.
    old_path = tmp_path / "old2.txt"
    new_path = tmp_path / "new2.txt"
    out_path = tmp_path / "out2.json"
    text = '1. Notice. Notices go to the 保险 office.\n'
    old_path.write_text(text, encoding="utf-8")
    new_path.write_text(text, encoding="utf-8")

    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"

    proc = _run_cli(old_path, new_path, out_path, env)
    assert proc.returncode == 0
    assert out_path.exists()
