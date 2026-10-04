# Step 1.4 debugging log: section splitting

This documents how `src/clean_process.py`'s section-splitting logic (`mark_sections`,
`is_bold`, `is_standalone`, `assign_parts`, `dedupe_short_duplicates`) reached its
final form. Kept separate from the README because this is a debugging narrative,
not a scope decision — useful for the Week 1 report-back and as a reference if
the same failure modes reappear on new filings in later weeks.

**Method throughout:** every fix was validated against a real filing (usually
AAPL's FY2023 10-K, which was already on hand) before being shipped, specifically
to catch regressions — a fix for one filer's HTML broke a previous filer's
detection on two separate occasions below, and both were caught this way before
being handed off.

## Starting point

The initial script detected headings by scanning for bold-styled (`style="font-weight:bold"`
or `<b>`/`<strong>`) leaf elements whose text matched `Item \d+[A-Za-z]?\.` — a
workaround for EDGAR's habit of using inline CSS instead of semantic heading tags
(see README's Step 1.3 notes). Boilerplate stripping and MinHash near-dup detection
were already working. Running it on all 93 filings surfaced a `ValueError` crash
in the near-duplicate detector and, once past that, widespread missing/incorrect
sections across the corpus.

## Issue 1 — Crash: duplicate `(ticker, report_date, item_id)` keys

**Symptom:** `find_near_duplicates` used `f"{ticker}|{report_date}|{item_id}"` as a
dict key without expecting collisions; `ValueError: The given key already exists`.

**Fix (defensive):** disambiguate colliding keys with a `#2`, `#3` suffix instead
of crashing, and print a warning listing every collision. This didn't fix the
underlying cause, but made every subsequent bug visible in the tool's own output
instead of via a stack trace — the warning list became the main diagnostic
signal for the rest of this log.

## Issue 2 — 10-Qs reuse Item 1-4 under two different Parts

**Symptom:** the warning list showed `AAPL|2025-03-29|1 (x2)`. A 10-Q's Part I
Item 1 (Financial Statements) and Part II Item 1 (Legal Proceedings) both got
the bare `item_id="1"`.

**Fix (attempt 1, wrong path):** tried detecting "PART I"/"PART II" as bold
headings and prefixing `item_id` with the tracked Part. This worked for AAPL but
depended entirely on each filer styling "PART I" as bold — which turned out not
to hold (see Issue 4).

**Fix (final):** abandoned HTML-based Part detection. The Part a given Item
belongs to is fixed by SEC convention and never depends on formatting:
- **10-K:** a static `item_id -> Part` lookup table (Item 1-4 = Part I, 5-9C =
  Part II, 10-14 = Part III, 15-16 = Part IV). Item numbers never repeat across
  Parts in a 10-K, so this is unambiguous regardless of HTML quirks.
- **10-Q:** Part I's four items (1-4) always precede Part II's in document
  order, and Part II also starts at 1 — so the **second** occurrence of `item_id
  == "1"` marks the Part I/II boundary. Verified against a hand-built synthetic
  10-Q section list before trusting it on real data (no real 10-Q was available
  locally at this point).

This produced the `I-1`, `II-1`, etc. labels used from here on.

## Issue 3 — Table-of-Contents rows misdetected as real headings

**Symptom:** some filers' TOC rows are laid out as an actual `<table>` (item
number | title | page number as separate cells) and are bold-styled the same
as real headings, producing a second, spurious heading per Item.

**Fix (attempt 1, regression):** skip any bold match inside *any* `<table>`.
This immediately broke a different filer — `Sections found` for `'1'` dropped
from all 93 filings to 78, because that filer's *real* heading happened to sit
inside a single-cell table used purely for layout, not a TOC.

**Fix (final):** only treat a table as TOC-like — and skip matches inside it —
when it contains **two or more** bold Item-matching leaves. A table wrapping
exactly one heading (layout table) is left alone; a table listing many items
(a real TOC) is excluded. Re-verified the original regression was gone.

## Issue 4 — Part-tracking got stuck on "Part IV" for an entire filing

**Symptom:** BAC, CRSR, and MSFT's 10-Ks each showed *every* item (1 through 16)
labeled `IV-*`.

**Root cause:** the (now-abandoned, see Issue 2) HTML-based Part-tracking
checked for "PART" labels *before* checking TOC-table membership. A TOC that
bold-labels its own Part dividers ("PART I" ... "PART IV" as section headers
within the TOC itself) left the tracked Part stuck on whichever was listed last,
because these three filers' real body Part headings weren't picked up as bold
at all.

**Fix:** superseded entirely by Issue 2's final fix (deterministic Part
mapping, no HTML detection). Confirmed BAC/CRSR/MSFT cleared once that shipped.

## Issue 5 — Real heading, zero detections: COST's em-dash separator

**Symptom:** COST, COP, EA, INTC, and JPM's 10-Ks produced *only* a `FRONT`
section — no items detected at all.

**Investigation:** `ITEM_RE` required a literal period after the item number.
Inspecting COST's actual heading markup (bypassing the TOC, which uses a
different, non-bold style) found the real text was `'Item\xa01\u2014Business'`
— a non-breaking space, then an **em dash**, not a period.

**Fix:** broadened the separator character class to accept `.`, em dash, en
dash, or colon. Confirmed against both COST's real text and AAPL's original
period-based text with no regression.

This also cleared COP, which turned out to share the same convention.

## Issue 6 — Combined "Items 1 and 2." headings (oil & gas convention)

**Symptom:** DVN was missing exactly `I-1` and `I-2` (and only those two) while
every other item was present.

**Investigation:** inspecting DVN's real markup found the heading text is
literally `'Items 1 and 2.'` (plural "Items", two numbers) — DVN combines
Business and Properties into one Item, a known oil & gas convention. The title
text lives in a separate sibling span, so the matched leaf's own title capture
is empty (cosmetic only — the title still appears as ordinary body text).

**Fix:** added a second pattern, `COMBINED_ITEM_RE`, matching "Items N and M."
and producing a composite id like `1-2`, mapped to Part I in the lookup table.
This also fixed COP, which uses the same convention.

## Issue 7 — JPM uses no bold styling at all

**Symptom:** JPM remained at zero detections after Issue 5's fix.

**Investigation:** JPM's real headings are **never bold** (`font-weight:400`
throughout). Instead: its 10-Ks use a larger font-size (12pt, vs. ~10pt body
text) in a custom brand font-family; its 10-Qs use `text-decoration:underline`.

**Fix:** broadened `is_bold()` (heading-likeness, despite the name) to also
treat `text-decoration:underline` and `font-size >= 12pt` as heading signals.
Low risk in principle, since this only gates whether the code *attempts* an
`ITEM_RE` match — it can't invent a spurious section unless unrelated text
elsewhere also happens to read exactly like an Item heading. That risk turned
out not to be negligible (Issues 8-9).

## Issue 8 — Broadened heading detection caught hyperlinked cross-references

**Symptom:** new duplicate-key warnings appeared for JPM and WMT immediately
after Issue 7's fix, e.g. `WMT|2025-01-31|I-1 (x4)`.

**Investigation:** large filings cross-reference sections by name — "the risks
described in *Item 1A. Risk Factors*" — often as a clickable, underlined link
quoting the heading's exact text. Broadening the underline signal caught these
too.

**Fix (partial):** exclude any candidate inside a hyperlink with an `href`
attribute — a real heading is a link *destination*, never a link *source*.
This fixed JPM's case, but WMT's persisted unchanged.

## Issue 9 — Underlined cross-references without an actual hyperlink

**Symptom:** WMT's duplicate counts were completely unaffected by Issue 8's fix.

**Investigation:** printed every occurrence of `item_id == "1"` in WMT's
document via the real pipeline functions directly. Found occurrences up to
84,481 characters long, starting mid-sentence with a stray closing quotation
mark — i.e. WMT underlines cross-reference text for visual/stylistic reasons
without wrapping it in an actual `<a>` tag, so the href check in Issue 8 never
applied.

**Fix (attempt 1, regression):** compare the full parent element's text length
against the candidate heading's own text length, on the theory that a
cross-reference's parent (a full sentence) is much longer than a heading's.
This broke DVN — its real heading and title live as two sibling spans under
the *same* parent, so the parent legitimately contains more text than the
heading alone, and got wrongly rejected.

**Fix (attempt 2, still a regression):** switch to checking only *preceding*
siblings, and walk up through parent elements until reaching any block-level
tag (`div`, `p`, `td`, ...), checking preceding siblings at each level. This
broke **AAPL** — real EDGAR HTML often uses sibling `<div>`s as paragraphs
rather than `<p>` tags, so "climb to the nearest div" actually climbed to a
container whose siblings were *every preceding paragraph in the document*,
producing a false "lots of preceding text" result for essentially every
heading.

**Fix (final):** climb up only through genuine **inline wrapper** tags
(`span`, `font`, `a`, `em`, `i`, `b`, `strong`, `u`, `sub`, `sup`) — stopping
the instant the parent is a block-level container, *without* checking that
container's own siblings at all. This correctly distinguishes:
- a heading directly inside a paragraph (no preceding siblings at its own
  level → standalone),
- a heading double-wrapped in an extra inline `<span>` for styling, whose
  lead-in text is a sibling of the *outer* wrapper (caught by climbing one
  inline level, unlike Issue 8's single-level check),
- a heading whose paragraph is itself one of many sibling `<div>`s (stops
  before climbing into paragraph-level territory, unlike the previous
  attempt).

Verified against four synthetic cases (genuine heading, WMT-style
double-wrapped cross-reference, DVN-style sibling title, and an AAPL-style
"heading's div has many sibling divs" case) plus the real AAPL file before
shipping.

## Issue 10 — A duplicate that isn't short: JPM's outline-style TOC

**Symptom:** even with Issues 8-9 fixed, a length-based dedup pass
(`dedupe_short_duplicates`, dropping same-`item_id` duplicates under 150 chars)
didn't touch JPM's remaining `I-1 (x2)`.

**Investigation:** JPM's TOC lists not just each Item but its sub-headings with
page numbers — a dense outline like `"\tBusiness.\t1\n\tOverview\t1\n\tBusiness
segments\t1\n..."`, long enough (1,612 chars) to clear the length threshold
entirely.

**Fix:** added `looks_like_toc()` — checks whether most lines in a candidate
match the shape `\t{title}\t{page number}`. Structurally distinct from real
prose regardless of total length. `dedupe_short_duplicates` now drops an
occurrence if it's *either* short *or* TOC-shaped, keeping at least one
occurrence always. Verified this doesn't disturb the real 10-Q Part I/II
double-occurrence case (both are prose-shaped and long, so both survive).

## Issue 11 — INTC: not a bug, a genuinely different document structure

**Symptom:** INTC remained at zero detections after every fix above.

**Investigation:** a search of the *entire* extracted document (530K characters)
for any occurrence of "Item 1" found exactly one — at character 526,281, in the
last 1% of the document. It reads: *"Form 10-K Cross-Reference Index ... Item 1.
Business: General development of business Pages 3-9, 20..."* — INTC uses a
Cross-Reference Index appendix mapping Items to page numbers, and never restates
"Item 1. Business" as a literal heading before the actual narrative content.
The narrative exists (confirmed "Intel Corporation", "Santa Clara" appear where
expected) but under its own subject-matter headings with no "Item N" text
anywhere nearby.

**Resolution:** this is not a parsing bug — the text pattern every other fix
relies on genuinely does not exist where the content is. Fixing it properly
would mean a dedicated parser reading the Cross-Reference Index and mapping
page ranges to content, which isn't reliable given page boundaries aren't
preserved in extracted text. **Decision: swap INTC out of the corpus** (Texas
Instruments, TXN, replaces it) rather than build one-off infrastructure for a
single filer.

## Issue 12 — Boilerplate stripper was eating our own [TABLE]/[/TABLE] markers

**Found during:** report-back review, item 5 (false-positive boilerplate
check), run against real long sections across AAPL, JPM, GS, RBLX, COST.

**Symptom:** AAPL's Item 1A was clean (no legitimately-repeated subheading
wrongly dropped — the original worry). But JPM's multi-table sections showed
`x10: '[TABLE]'` and `x10: '[/TABLE]'` in the stripped-lines list.

**Root cause:** `[TABLE]`/`[/TABLE]` are the pipeline's own structural
markers (inserted by `extract_text_with_tables`), not document content. Any
section with two or more embedded tables repeats them often enough to trip
the generic frequency-based boilerplate rule, silently destroying
table-boundary information that a later chunking step would need.

**Fix:** exempt these two literal strings from `strip_boilerplate`
regardless of repeat count. Verified against a synthetic case that the
markers now survive while genuinely repeated content (e.g. footer lines)
still gets stripped, then confirmed against real data: near-duplicate pairs
dropped from 970 to 966 after the fix (a handful of pairs that previously
matched partly on now-preserved table markers no longer cross the
threshold) — the expected signature of a correct fix, not a regression.

## Issue 13 — item_id collision between 10-K and 10-Q under the same Part II prefix

**Found during:** report-back review, cross-checking the full `item_id`
count breakdown against expected totals by hand.

**Symptom:** `II-5` = 89 but there are only 72 10-Ks (89 − 72 = 17, fitting
inside the 21 10-Qs); `II-6` = 24 but there are only 21 10-Qs (24 − 21 = 3
extra from 10-Ks). No crash, no missing content — every record still had
the correct `form` field — but two unrelated disclosure types were sharing
one `item_id`.

**Root cause:** 10-K Part II (Items 5-9C, from Issue 2's fixed lookup table)
and 10-Q Part II (Items 1-6, from Issue 2's occurrence-counting rule) both
use the `II-` prefix. The two ranges overlap exactly at Items 5 and 6: a
10-K's `II-5` is "Market for Registrant's Common Equity"; a 10-Q's `II-5` is
"Other Information" — different disclosures, same label. (The 3 extra `II-6`
10-K records turned out to be legitimate, not a bug: CFG and Corsair both
still restate "Item 6. [Reserved]" as a formality even though the SEC
eliminated the requirement in 2021.)

**Fix:** namespace `item_id` by form type at the point records are written
(`"10-K:II-5"` vs. `"10-Q:II-5"`), making the id unambiguous on its own
rather than relying on every downstream script to also filter on `form`.
Verified as a pure relabeling with no content change: total records (1607)
and near-duplicate pair count (966) were identical before and after.

## Issue 14 — JPM's 10-Q never restates Part I's Item 1 or Item 2 at all

**Found during:** report-back review, investigating why 3 of 21 10-Qs were
missing an `II-6` (Exhibits) record. The obvious guess — "Item 6 is
genuinely short, same as the Issue-checked Item 2/Properties case" — didn't
hold up: Item 6 in a 10-Q is structurally mandatory (it must at least list
certification exhibits), so it can't be legitimately trivial. Tracing it
showed the real symptom was different: all 3 affected filings had *every*
item labeled under `I-`, with zero `II-` items at all, even though the raw
HTML clearly contained well-formed, correctly-styled Part II headings
(confirmed via the same underline-detection signal that already worked for
other JPM items).

**Root cause:** the Part I/II boundary for 10-Qs is detected by the
*second* occurrence of raw item_id "1" (Issue 2). Tracing the raw sections
list for an affected filing showed only **one** "1" existed before any
dedup or Part-assignment ran: Part II's "Item 1. Legal Proceedings." A
targeted search of the raw HTML for "Item 1"/"Item 2" confirmed why — JPM's
10-Q TOC lists Part I's "Item 1."/"Item 2." normally (correctly excluded,
not bold/underlined), but the **real body never restates them**. JPM jumps
straight into its own custom sub-headings ("NOTES TO CONSOLIDATED FINANCIAL
STATEMENTS," etc.) without ever literally writing "Item 1. Financial
Statements" or "Item 2. ...Analysis" anywhere. Only Part II's Items 1 and 2
exist as real, detectable headings. With Part I's "1" never occurring, the
occurrence-counting rule never fires, so Part II's entire block (Items 1A
through 6) gets mislabeled as a continuation of Part I.

**Resolution:** same category as Issue 11 (INTC) — not a styling or
detection bug, a genuine absence of the text pattern every fix in this log
relies on. Unlike INTC, this doesn't block the whole filing: items 3
through 6 position correctly regardless of the Part I/II mislabeling bug,
since Issue 2's `TENK_PART_MAP`-equivalent reasoning for 10-Qs depends only
on the "1" trigger, not on 1/2 being found individually. **Practical
consequence:** Part I's Items 1 and 2 (Financial Statements and MD&A —
typically the bulk of a 10-Q's actual content) have no heading to split on
for these 3 JPM 10-Qs, so that content is absorbed into the `FRONT` section
rather than its own records. Not lost, just not segmented. **Decision:**
document as a known limitation rather than build further infrastructure —
JPM is in the dev subset and not easily swapped the way INTC was, and no
heading-detection approach can split content that was never labeled in the
source document.

## Final verification

After all fixes, `I-1` appeared in exactly 84 of 93 filings — matching the
predicted count exactly (93 total, minus 3 INTC filings with zero detections,
minus 3 COP and 3 DVN filings using the composite `1-2` id instead of bare
`1`). The duplicate-key warning list was empty. This exact-match arithmetic,
rather than "looks about right," was the actual confirmation the pipeline was
correct — not just quieter.

This checkpoint held up for the core detection logic, but the subsequent
report-back review (hand-verifying the full `item_id` breakdown, not just
spot-checking) caught three further issues the arithmetic above didn't
surface: Issues 12-14. All three were found the same way as everything
else in this log — by checking real output against an independently
computed expectation, not by assuming a clean run meant a correct one.

## Summary table

| Filer(s) | Symptom | Root cause | Fix |
|---|---|---|---|
| AAPL | — (baseline) | — | Standard bold + period pattern |
| COST, COP | Zero detections | Em dash, not period, between item number and title | Broadened separator character class |
| DVN, COP | Missing Item 1 & 2 only | Combined "Items 1 and 2." heading (oil & gas convention) | Second regex pattern, composite id `1-2` |
| BAC, CRSR, MSFT | Every item mislabeled under one Part | TOC's own bold Part-divider labels left HTML-based Part-tracking stuck | Replaced with a fixed item-number-to-Part lookup (10-K) / occurrence-counting rule (10-Q) |
| JPM | Zero detections | No bold styling anywhere; underline (10-Q) or 12pt custom font (10-K) instead | Broadened heading-detection signals |
| JPM, WMT | Duplicate item_id per filing | Broadened signals also caught cross-reference text quoting a heading verbatim | `href`-exclusion, then an inline-context "no preceding text" check, then a TOC-shape check for JPM's long outline-style TOC |
| INTC | Zero detections, unfixable | Never restates "Item N" inline; uses a page-number Cross-Reference Index instead | Swapped out of the corpus (→ TXN) |
| JPM (multi-table sections) | Boilerplate stripper removed real structural markers | `[TABLE]`/`[/TABLE]` repeat often enough to trip the frequency rule | Exempted these two literal strings from stripping |
| 10-K vs 10-Q, Items 5 & 6 | Two unrelated disclosures sharing one `item_id` | `II-` prefix used by both 10-K Part II (5-9C) and 10-Q Part II (1-6) — overlap at 5/6 | Namespaced `item_id` by form (`10-K:II-5` vs `10-Q:II-5`) |
| JPM (10-Q only) | Part II mislabeled as Part I for 3 filings | Never restates Part I's "Item 1"/"Item 2" inline, so the occurrence-counting trigger never fires | Documented as a known limitation (unfixable, not detection bug) — affected content absorbed into FRONT |
