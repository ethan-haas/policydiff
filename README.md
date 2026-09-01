# policydiff-ins

Compares two versions of an insurance policy form and reports **what
coverage actually changed** -- added, removed, narrowed, or broadened
exclusions, coverages, sublimits, deductibles, and definitions -- with
every finding citing the clause on both sides, and all cosmetic/formatting
churn suppressed.

This is not insurance advice and not a coverage opinion.

## The alignment problem, and why a text diff is the wrong tool

A line-based text diff (`diff old.txt new.txt`) compares documents by
*position*. Insurance forms get revised by inserting and deleting whole
clauses in the middle of the document, which shifts every clause number
after the edit point: clause 4.2 in the 2023 form can be clause 4.3 -- or
clause 5.1, or anything else -- in the 2025 form, with at most three words
actually changed. Fed to a positional diff, that shift alone produces
dozens of spurious hunks (every clause after the insertion point "changed"
because its line number moved), while the one clause that quietly added a
new exclusion or lowered a sublimit is buried in the noise, or worse,
paired against the wrong neighbor and silently skipped.

The fix is to stop diffing by position and start diffing by *meaning*:

1. **Segment** each version into clauses independent of surrounding
   context (`policydiff/segment.py`). Numbered/roman/lettered clauses are
   whole-blob atoms anchored by their own printed number. UNNUMBERED prose
   (a preamble, a whole unnumbered document, or the text sitting under a
   SECTION heading) is atomized at the SENTENCE, not the blank-line
   paragraph -- so a document reflowed across more or fewer blank lines
   never changes the clause set, and a real edit hiding in one sentence of
   an otherwise-untouched block never drags its unedited siblings into the
   report as phantom findings (`policydiff/sentence.py`). SECTION headers
   themselves carry no coverage and never produce an added/removed/
   narrowed/broadened finding on their own.
2. **Align** clauses across versions by content similarity (word-shingle
   Jaccard), not by clause number or document position
   (`policydiff/align.py`). A clause that moved but is otherwise
   unchanged pairs with its content-twin regardless of renumbering.
3. **Normalize away cosmetic variation** -- whitespace, line-wrapping,
   renumbering, defined-term capitalization, quote/dash style -- so that
   two clauses differing ONLY in formatting produce byte-identical
   canonical text (`policydiff/normalize.py`). This is the load-bearing
   step: skip it and every reflow/renumber/recapitalization shows up as a
   fake "change," burying the real ones exactly the way a naive text diff
   does.
4. **Classify** each aligned pair as unchanged, cosmetic, narrowed,
   broadened, or (when a real change has no clearly detectable direction)
   modified -- never silently dropped (`policydiff/classify.py`).
5. **Cite** every non-cosmetic finding with the clause id and a verbatim
   quote from both sides (`policydiff/cite.py`).

## Worked example

`tests/fixtures/policy_old.txt` / `tests/fixtures/policy_new_planted.txt`
are a synthetic (author-written, for demonstration only) commercial
general liability form and a revised version with 12 deliberately planted
coverage changes plus one clause that moved position but is otherwise
unchanged. Run it yourself:

```
python -m policydiff tests/fixtures/policy_old.txt tests/fixtures/policy_new_planted.txt
```

Sample output (abbreviated):

```
[REMOVED] clause present in old version only
    old 2: "Coverage B -- Medical Payments ..."

[BROADENED] carve-back / exception added to exclusion
    old 4: "Exclusion -- Contractual Liability ... in a contract or agreement."
    new 3: "Exclusion -- Contractual Liability ... except with respect to liability assumed under an "insured contract"."

[NARROWED] limit changed from $2,000,000 to $1,500,000
    old 9: "General Aggregate Limit ... is $2,000,000 ..."
    new 8: "General Aggregate Limit ... is $1,500,000 ..."
```

The moved-but-unchanged clause ("Occurrence" definition, relocated ahead
of "Bodily injury" and "Property damage" and renumbered from 14 to 11)
does **not** appear in this output -- it aligned to its content-twin and
was correctly classified `unchanged`.

### Real public form pair -- OWED

The sandbox this repo was built in has outbound network access (verified:
`curl` to fema.gov and google.com both returned HTTP 200), but no web
search tool -- only blind URL guesses against government/regulator
domains. A guessed FEMA Standard Flood Insurance Policy PDF URL did not
resolve, and finding a genuine same-form, two-dated-version, plain-text
(or reliably OCR-able) pair from a state SERFF filing or ISO circular by
URL-guessing alone was not a productive use of the iteration budget. Per
spec, this does not block the build: the synthetic CGL-style fixture
above is clearly labeled synthetic-for-demo everywhere it's referenced.
**Fetching and citing (source URL + retrieval date) a real public form
pair remains an OWED follow-up item**, not something this build claims to
have done.

## What each test harness proves

| Test file | Guarantee | What it proves |
|---|---|---|
| `tests/test_planted.py` | 1 | All 12 planted real changes are reported with the right kind; the 13th planted item (a moved clause) is reported as `unchanged`, not a change. |
| `tests/test_noise.py` | 2 | A formatting-only variant (reflow, +100 renumbering, defined-term recapitalization, straight->curly quotes) produces an EMPTY report. |
| `tests/test_align.py` | 3 | Clause *pairing* is correct independent of classification: the moved clause pairs to its twin; removed/added clauses land in the right unmatched buckets; renumbered-but-unchanged clauses never pair by number (ids differ by design). |
| `tests/test_suppression_toggle.py` | 5 | With cosmetic suppression disabled (`suppress_cosmetic=False`), the same noise fixture that produced zero findings now produces findings -- proving the suppressor is doing real work, not a no-op. |
| `tests/test_cite.py` | 4 | Every citation's clause id exists on the stated side and its quote is a literal substring of that clause's text; `added`/`removed` findings carry only the one side that actually has a clause. |

A sixth guarantee -- that an independent reviewer, working black-box against
the running CLI with no access to this source, finds zero defects -- is
deliberately outside this test suite. A suite cannot certify its own
blind spots, so that one is run out-of-band. It was reached after 30 such
reviews; the ones before it are what the regression tests in `tests/` encode.

## CLI

```
python -m policydiff OLD.txt NEW.txt [--out diff.json] [--verbose] [--no-suppress-cosmetic]
```

Prints a human report (cosmetic/unchanged clauses suppressed by default;
`--verbose` includes them) and writes a machine-readable `diff.json`:

```json
{
  "findings": [
    {
      "kind": "narrowed",
      "old_clause_id": "9",
      "new_clause_id": "8",
      "old_quote": "...",
      "new_quote": "...",
      "detail": "limit changed from $2,000,000 to $1,500,000"
    }
  ]
}
```

## Scope and guardrails

- Document comparison only. No pricing, rating, or underwriting decisions.
- Not insurance advice, not a coverage opinion.
- Corpus scope (per spec): public forms only, with source URL + retrieval
  date recorded per document. This build's worked example is a labeled
  synthetic fixture; see "Real public form pair -- OWED" above.
- Stdlib-only implementation (`pytest` is a dev/test-only dependency).

## Running the tests

```
python -m pytest tests/ -q
```
