"""CLI: python -m policydiff OLD.txt NEW.txt [--out diff.json] [--verbose]

Prints a human-readable report to stdout and writes a machine-readable
diff.json alongside (or to --out).

Not insurance advice, not a coverage opinion.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from .report import diff_documents, human_report, to_json_str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="policydiff", description="Compare two versions of an insurance policy form.")
    parser.add_argument("old", type=pathlib.Path, help="path to the older policy form (plain text / markdown)")
    parser.add_argument("new", type=pathlib.Path, help="path to the newer policy form (plain text / markdown)")
    parser.add_argument("--out", type=pathlib.Path, default=None, help="path to write diff.json (default: diff.json next to cwd)")
    parser.add_argument("--verbose", action="store_true", help="include unchanged/cosmetic findings in the human report")
    parser.add_argument(
        "--no-suppress-cosmetic",
        action="store_true",
        help="disable cosmetic suppression entirely (debug / demonstration flag)",
    )
    args = parser.parse_args(argv)

    # Real policy text routinely contains characters outside cp1252 (CJK
    # names, U+2212 minus, smart punctuation the source PDF didn't
    # normalize, etc). Windows defaults stdout/stderr to the console code
    # page (cp1252), which raises UnicodeEncodeError on those characters
    # and kills the process with rc=1 -- taking the machine-readable
    # --out JSON down with it even though it was already fully computed.
    # Reconfigure both streams to UTF-8 with a safe error handler so a
    # display-encoding limitation can never crash a run on valid input.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    old_text = args.old.read_text(encoding="utf-8")
    new_text = args.new.read_text(encoding="utf-8")

    result = diff_documents(old_text, new_text, suppress_cosmetic=not args.no_suppress_cosmetic)

    # Write the machine-readable diff BEFORE printing the human report:
    # the JSON is the authoritative output and must never be lost to a
    # display/formatting failure in the human-readable path.
    out_path = args.out or pathlib.Path("diff.json")
    out_path.write_text(to_json_str(result), encoding="utf-8")

    print(human_report(result, verbose=args.verbose))
    print(f"machine-readable diff written to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
