"""Citations: every non-cosmetic, non-unchanged finding must carry the
clause id + a short verbatim quote from BOTH sides where applicable.

    added   -> new-side quote only (old_clause_id / old_quote are None)
    removed -> old-side quote only (new_clause_id / new_quote are None)
    everything else (narrowed/broadened/modified/unchanged/cosmetic)
            -> both sides

A quote is always a literal substring of the clause's own text -- never a
paraphrase -- so "does the cited text exist on the stated side" is a
mechanical, testable property (tests/test_cite.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from .classify import Finding
from .segment import Clause

_QUOTE_MAX_LEN = 400


def _quote(clause: Clause | None) -> str | None:
    if clause is None:
        return None
    text = " ".join(clause.text.split())
    if len(text) <= _QUOTE_MAX_LEN:
        return text
    return text[:_QUOTE_MAX_LEN].rstrip() + "..."


@dataclass
class Citation:
    kind: str
    old_clause_id: str | None
    new_clause_id: str | None
    old_quote: str | None
    new_quote: str | None
    detail: str


def cite(finding: Finding) -> Citation:
    old_id = finding.old.id if finding.old is not None else None
    new_id = finding.new.id if finding.new is not None else None
    old_q = _quote(finding.old) if finding.old is not None else None
    new_q = _quote(finding.new) if finding.new is not None else None

    if finding.kind == "added" and old_q is not None:
        raise AssertionError("added finding must not carry an old-side quote")
    if finding.kind == "removed" and new_q is not None:
        raise AssertionError("removed finding must not carry a new-side quote")

    return Citation(
        kind=finding.kind,
        old_clause_id=old_id,
        new_clause_id=new_id,
        old_quote=old_q,
        new_quote=new_q,
        detail=finding.detail,
    )


def quote_is_substring(quote: str | None, clause_text: str) -> bool:
    """True iff *quote* (possibly truncated with a trailing "...") is a
    verbatim substring of clause_text's whitespace-collapsed form."""
    if quote is None:
        return True
    collapsed = " ".join(clause_text.split())
    if quote.endswith("..."):
        quote = quote[:-3]
    return quote in collapsed
