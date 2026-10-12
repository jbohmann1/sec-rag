# RAG over SEC Filings
Measured investigation into what makes retrieval work on messy financial documents.

## Scope
- **Companies:** 24 across 6 sectors (see table below)
- **Period selection rule:** for each company, take the three most recent 10-Ks whose fiscal period ends on or before 2025-12-31. The rule is based on the period-end date, not a fiscal-year label, because companies label years differently (see rationale below).
- **10-K/A check:** 10-K/A amendments were deliberately excluded from the download (Step 1.2). Checked whether any exist whose period overlaps a selected 10-K, across the dev subset (AAPL, JPM, WMT, XOM, DG, EA, ACM): none do — every 10-K/A found for these companies predates FY2023 (as far back as the 1990s), except EA's FY2026 10-K/A (filed due to its going-private deal), which falls outside the selected FY2023-2025 window anyway. No special handling needed.
- **Form types:**
  - 10-K (annual report): 24 companies x 3 filings = 72 filings
  - 10-Q (quarterly report): the three most recent 10-Qs for the dev subset only = 21 filings
- **Total corpus:** 93 filings
- **Dev subset:** AAPL, JPM, WMT, XOM, DG, EA, ACM (7 companies: one per sector, plus a second retailer (DG) for a less-famous name; used for fast iteration)

| Sector       | Companies |
|--------------|-----------|
| Tech         | Apple (AAPL), Microsoft (MSFT), Texas Instruments (TXN), Workday (WDAY) |
| Banking      | JPMorgan (JPM), Bank of America (BAC), Goldman Sachs (GS), Citizens Financial (CFG) |
| Retail       | Walmart (WMT), Costco (COST), Dollar General (DG), Ross Stores (ROST) |
| Energy       | ExxonMobil (XOM), ConocoPhillips (COP), Devon Energy (DVN), Marathon Petroleum (MPC) |
| Gaming       | Electronic Arts (EA), Roblox (RBLX), Unity Software (U), Corsair Gaming (CRSR) |
| Architecture & Engineering | AECOM (ACM), Fluor (FLR), Tetra Tech (TTEK), Sterling Infrastructure (STRL) |

**Note on excluded companies:** Tencent (and its subsidiary Riot Games) file with the Hong Kong Stock Exchange, not the SEC, so no 10-K exists for either. Activision Blizzard's last 10-K covered FY2022; Microsoft completed its acquisition in October 2023, so no later 10-K exists. Neither is included. There is no major public *pure* architecture firm — Gensler, HOK, SOM and similar are private partnerships that file nothing with the SEC — so "Architecture & Engineering" uses the closest public equivalent: architecture-and-engineering and engineering-and-construction firms.

**Note on the original 30-company draft:** the sector list originally included CRM, RF, TGT, CVX, TTWO, J, and NVEE — trimmed to protect eval-set and error-analysis time later in the schedule (six companies dropped as the more structurally redundant one in each sector's pair, e.g. CRM and WDAY were both January-fiscal-year enterprise SaaS firms, so CRM was cut and WDAY, the less-famous name, kept). Separately, **NVEE (NV5 Global) was swapped for STRL (Sterling Infrastructure)**: NV5 Global was acquired by Acuren Corporation and delisted from Nasdaq in August 2025, so its ticker no longer resolves via SEC's current ticker-to-CIK lookup even though its filing history remains on EDGAR.

**Note on INTC → TXN:** Intel was dropped during Step 1.4 parsing. Unlike every other filer in the corpus, Intel's 10-K never restates "Item 1. Business" (or any Item number) as a literal heading before its narrative content — the only occurrence of "Item 1" anywhere in the document is in a "Form 10-K Cross-Reference Index" appendix near the end, mapping Items to page numbers. Every section-splitting heuristic in this pipeline depends on that text pattern existing near the actual content, so this isn't fixable without building a dedicated page-number-based parser just for this one filer. Texas Instruments (TXN) replaces it — same sector role, standard Item-heading formatting.

## Scoping rationale
- **Size:** trimmed from an initial 30-company draft to 24 (one company dropped per sector), per the guide's scope-creep warning — a polished 24-company project beats a half-finished 30-company one, and the time saved protects Week 2's eval-set work and Week 4's error analysis.
- **Period-end rule instead of fiscal-year labels:** Fiscal years do not match calendar years, and companies label them inconsistently. Dollar General calls the year ending January 2025 "fiscal 2024", while Walmart calls the same period "fiscal 2025". Selecting filings by period-end date (on or before 2025-12-31) gives consistent time coverage across companies.
- **Fiscal-calendar conventions differ even within one cluster:** WMT and DG both have January fiscal year-ends, but they don't follow the same convention. DG's is a floating 52/53-week calendar ("the Friday closest to January 31") — its three selected period-end dates are 2023-02-03, 2024-02-02, and 2025-01-31, all Fridays. WMT's is a fixed calendar date — its three dates are all exactly 2023/2024/2025-01-31 regardless of weekday. A date-matching rule tuned on one company's pattern would silently mishandle the other, which is why metadata records the exact period-end date rather than inferring it from a rule.
- **Famous vs. less-famous names:** LLMs have memorized facts about famous companies (e.g. Apple's revenue), which can make retrieval metrics meaningless for those questions. Mid-caps like Workday, Citizens Financial, Dollar General, Ross Stores, Devon Energy, Corsair Gaming and Sterling Infrastructure force the system to actually retrieve.
- **Sectors (business reasons):** Tech, banking, retail, energy, gaming and architecture & engineering give varied terminology and fiscal calendars. Gaming and architecture & engineering were added for personal interest and domain familiarity (gaming) and current work experience (architecture/engineering process management).
- **Sectors (technical reasons):** Each sector has a different document structure that stresses the parser and retriever differently:
  - Energy: climate-risk disclosures change year to year, giving rich material for multi-hop and year-over-year questions.
  - Banking: regulatory-capital tables; Goldman Sachs in particular stacks multiple small tables with identical row labels back to back (a ratio table immediately followed by a dollar-value table), which is a real risk of cross-table contamination if chunk boundaries don't respect table edges.
  - Retail: seasonality and segment reporting; Costco runs a 52/53-week fiscal year of "thirteen four-week periods" (FY2023 was an explicit 53-week year), so any chunk or metadata field assuming calendar quarters will misalign with its actual reporting periods.
  - Gaming: bookings vs. GAAP revenue reconciliations. Roblox reports "Bookings" as its core non-GAAP metric inside a "Key Metrics" section nested one level deeper than Item-level headings (Key Metrics → DAUs / Hours Engaged / Bookings / ABPDAU) — a chunker that only splits on "Item N" headings will lump this whole subsection together.
  - Architecture & Engineering: project-based (percentage-of-completion) revenue recognition, backlog disclosures.
- **Dev subset choice:** One company per sector, plus a second retailer (DG) for a less-famous name.

## Parsing (Step 1.3)
Three approaches were compared on a 10-filing sample (AAPL, JPM, WMT, XOM, DG, EA, ACM, GS, RBLX, COST): plain BeautifulSoup text extraction, BeautifulSoup with table-aware extraction, and html2text. **Chosen: BeautifulSoup with table-aware extraction.** Plain text extraction destroys table row/column association entirely (a multi-year, multi-segment table collapses into a flat list of numbers with no attached labels). html2text's markdown tables are readable but add pipe-syntax noise that would need to be stripped anyway, and — contrary to expectation — it does **not** preserve headings on real EDGAR HTML: SEC filings mark headings with inline CSS (`style="font-weight:bold"`) rather than semantic `<b>`/`<strong>` tags, so none of the three approaches distinguish a heading from body text without an explicit style-based heuristic (see Metadata below). Since boilerplate and page headers/footers also leak through identically in all three and need a separate cleanup pass regardless, table fidelity was the deciding factor.

## Metadata, Cleaning & Dedup (Step 1.4)
Each filing is split into one record per Item/section. Record schema:

```
ticker, cik, company, form, filing_date, report_date, accession,
item_id, item_title, text, char_count, content_hash

# item_id is namespaced by form, e.g. "10-K:I-1A", "10-Q:II-1" (see below)
```

**Section detection.** Headings are found by scanning for text matching `Item
\d+[A-Za-z]?[.—–:]` inside elements styled as headings — the
workaround for EDGAR's lack of semantic heading tags noted in Step 1.3. A
second pattern also catches combined "Items N and M." headings (an oil & gas
convention — see below). "Heading-styled" turned out to mean different things
for different filers (bold, underline, or a larger custom font-size), and a
handful of filer-specific quirks required real debugging to get right; see
[`docs/step1_4_debugging_log.md`](docs/step1_4_debugging_log.md) for the full
chronological account. Summary:

| Filer(s) | Quirk | Fix |
|---|---|---|
| COST, COP | Real heading uses an em dash, not a period, between item number and title (`Item 1—Business`) | Broadened the separator pattern to accept a period, em dash, en dash, or colon |
| DVN, COP | Combine Business and Properties into one heading, `"Items 1 and 2."` | A second regex producing a composite id, `1-2` |
| BAC, CRSR, MSFT | Table of Contents bold-labels its own "PART I/II/III/IV" dividers, leaving naive Part-tracking stuck on whichever Part was listed last | Replaced HTML-based Part detection entirely with a fixed item-number-to-Part lookup for 10-Ks, and an occurrence-counting rule for 10-Qs (Part II starts the second time "Item 1" appears, since Part I and Part II both number their items from 1) |
| JPM | Uses no bold styling anywhere — 10-Ks use a larger custom font-size instead, 10-Qs use underline | Broadened heading detection to also treat underline and font-size ≥ 12pt as heading-like |
| JPM, WMT | Broadened detection above also caught inline cross-references quoting a heading's exact text (e.g. "as discussed in *Item 1A. Risk Factors* above") | Excluded hyperlinked text, then added a check for whether meaningful text precedes the candidate within its inline context, then a shape-based check for JPM's outline-style Table of Contents |
| INTC | Never restates "Item N" as a literal heading at all — uses a page-number Cross-Reference Index instead | Not fixable by heading-detection heuristics; swapped out of the corpus (→ TXN) |

**Boilerplate.** Page numbers, "Table of Contents" running headers, and
"Form 10-K" footer lines are stripped via a mix of targeted patterns and a
generic rule — any short line repeating often enough within a section is
treated as boilerplate regardless of its exact wording. Chosen deliberately
over per-filer regexes, since footer formats vary by filer (AAPL: single-line
"Company | Year Form 10-K | page#"; Goldman Sachs: two-line "Goldman Sachs
Year Form 10-K" + page number; Costco: a repeating "Table of Contents" header)
and a per-filer approach wouldn't generalize to companies not yet inspected.

**Near-duplicates.** Flagged via MinHash over 3-word shingles at a 0.7
similarity threshold, tuned against a synthetic test case after an initial
5-word/0.8 configuration failed to catch a realistic near-duplicate pair.
The final run over the full 93-filing corpus found **966 near-duplicate
section pairs** (970 before the `[TABLE]`/`[/TABLE]` boilerplate fix below —
a handful of pairs that partly matched on now-preserved table markers no
longer cross the threshold, as expected). Spot-checked and confirmed working
correctly on real data:
it correctly identifies a 10-Q's Part II "Legal Proceedings" section as
near-identical to the same fiscal year's 10-K Part I "Legal Proceedings"
section (both are the same real-world disclosure, filed under different
Item numbers by convention), and separately flags AAPL's cover page and
"Properties" disclosure as reused nearly verbatim year over year — both
legitimate, not detector errors.

**Report-back results (final run, 93 filings, 1607 records).** Full `item_id`
breakdown confirms the pipeline is internally consistent: `I-3` (Legal
Proceedings) = 93/93, since every filing has one regardless of form type or
combined-item filers; `I-1` = 87/93 exactly matches 93 minus COP's and DVN's
6 combined-item filings. `I-2` (Properties) was initially 82/93 — the
remaining 5-filing gap traced to ACM (both years) and EA (all three years)
consistently, not randomly, pointing to the same `len(cleaned) < 50`
short-section-drop behavior already documented for AAPL's Item 9: both are
asset-light businesses whose Properties disclosure is apparently minimal
enough to fall under the keep threshold every year. A sample record (BAC,
Item III-13, 225 chars — short because it's legitimately incorporated by
reference to the Proxy Statement) confirmed correct schema and metadata.

**`item_id` namespacing fix.** Found a real schema ambiguity: 10-K Part II
(Items 5-9C) and 10-Q Part II (Items 1-6, since Part II renumbers from 1 per
the Issue 2 rule in the debugging log) both use the `II-` prefix, colliding
at `II-5` and `II-6` specifically — two unrelated disclosure types sharing
one id. Confirmed on real data: `II-5` = 89 (72 from 10-Ks' "Market for
Registrant's Common Equity" + 17 from 10-Qs' "Other Information"); `II-6` =
24 (18 from 10-Qs' "Exhibits" + 6 from 10-Ks' "[Reserved]" — some filers
like CFG and Corsair still restate this item as a formality even though SEC
eliminated the requirement in 2021, which is legitimate content, not a bug).
**Fixed by namespacing `item_id` with form type** (`10-K:II-5` vs.
`10-Q:II-5`), making the id unambiguous on its own rather than relying on
every downstream script to also filter on `form`. This is a schema change —
**re-run `clean_process.py` on top of this version if you have older
`records.jsonl` output**, since old and new item_id formats aren't
compatible.

**INTC follow-up:** confirmed directly against Intel's real FY2023 10-K
(fetched from SEC.gov) that the SEC-standard phrase "General development of
business" appears exactly once in the entire document, inside the Cross-
Reference Index appendix itself. Intel's own Table of Contents lists its
real page-3 section as **"Introduction to Our Business"** — different
wording entirely — confirming this isn't a missing-heading parsing artifact
but a deliberate choice: Intel's narrative never restates SEC Item language
inline, and only the end-of-document index translates between the two
vocabularies.

**Boilerplate stripper false-positive check:** tested against real long
sections (AAPL, JPM, GS, RBLX, COST). AAPL's Item 1A was clean across all
three years — no legitimately-repeated subheading was wrongly dropped.
However, JPM's multi-table sections revealed a real bug: the pipeline's own
`[TABLE]`/`[/TABLE]` structural markers were being stripped as boilerplate,
since sections with several embedded tables repeat them often enough to
trip the generic frequency rule — silently destroying table-boundary
information needed for chunking. **Fixed:** these two literal markers are
now exempted from boilerplate stripping regardless of repeat count. Verified
the fix preserves the markers while still correctly stripping genuinely
repeated content (e.g. footer lines) — and confirmed against the real corpus:
re-running the false-positive check shows JPM's `[TABLE]`/`[/TABLE]` entries
gone from the stripped-lines list, leaving only the lower-stakes items (a
`'Part I'` running header, stray bullet/dash glyphs from list markers) that
don't need further action.

**Known limitation: JPM's 10-Q never restates Part I's Item 1 or Item 2.**
Investigating why 3 of 21 10-Qs were missing an `II-6` (Exhibits) record —
checked rather than assumed, since Item 6 is structurally mandatory and
can't legitimately be trivial, unlike the I-2/Properties case above — found
a different and genuinely unfixable gap: JPM's 10-Q lists "Item 1."/"Item
2." in its Table of Contents as expected, but the real body never restates
them before diving into its own custom sub-headings ("NOTES TO CONSOLIDATED
FINANCIAL STATEMENTS," etc.). Only Part II's Items 1 and 2 exist as real,
detectable headings, so the occurrence-counting rule that detects the Part
I/II boundary (two occurrences of raw item "1") never fires, and the entire
Part II block ends up mislabeled under the `I-` prefix for these 3 filings.
Same category as the INTC exclusion — not a detection bug, a genuine
absence of the text pattern this pipeline relies on. Unlike INTC, this
doesn't block the whole filing (Items 3-6 still position correctly); the
practical consequence is that Part I's Items 1 and 2 (Financial Statements
and MD&A — typically the bulk of a 10-Q) have no heading to split on for
these 3 filings, so that content is absorbed into `FRONT` rather than its
own records. **Documented rather than fixed**, since JPM is in the dev
subset and not easily swapped the way INTC was, and no heading-detection
approach can split content that source document never labeled.

**Dedup logic fix, verified to have zero net effect on this corpus (by
design, not by luck).** Investigating a 4th 10-Q missing `II-5` (beyond
JPM's 3, explained by the limitation above) surfaced a genuine bug in the
Issue-10 dedup logic: it assumed a shorter occurrence of the same raw
`item_id` must be a fake duplicate, which is false for 10-Q Part I/Part II
reuse specifically — Part II's versions of Items 3/4 ("Defaults Upon Senior
Securities", "Mine Safety Disclosures") are almost always genuine one-line
disclosures ("None.", "Not applicable."), not fakes. Fixed by removing the
length-based component, keeping only TOC-shape detection (confirmed every
previously-fixed case still holds without it). Re-ran the full corpus:
total records (1607) and every affected count were **identical** before and
after. Traced this precisely rather than assuming it meant nothing changed:
the fix does work exactly as intended (`II-3`/`II-4` now correctly survive
dedup and Part-assignment), but `main()`'s own separate, already-documented
minimum-content filter independently catches the same trivial one-liners
anyway, so the final output is unchanged for this specific corpus. The fix
was still necessary — it corrects a logically broken assumption that would
silently drop real content in any filing where Part II's one-liner happens
to be longer than 50 characters but shorter than the old 150-character
threshold, which just doesn't occur among this corpus's 93 filings.

## Chunking (Step 2.1)
Each of the 1607 Step 1.4 section records is split into fixed-size chunks
for embedding. Chunking is **token-based, using the embedding model's own
tokenizer** (BAAI/bge-small-en-v1.5), not a word-count approximation:
windows of at most 500 tokens (512 minus 2 special tokens minus a safety
margin), 50-token overlap, sliced from the original text at the
tokenizer's character offsets so each chunk is an exact substring of its
section — newlines and table rows are preserved rather than flattened.

The first version chunked by word count (512 words, 50-word overlap)
instead, on the assumption that words were a reasonable proxy for tokens.
They aren't, for this corpus: financial text runs well above one token per
word, and tables (numbers, `$`, `%`, `|` separators) run highest of all.
Measuring the actual token length of the resulting chunks found **89% of
them (10,985 of 12,302) exceeded BGE's 512-token limit** — silently
truncated by `sentence-transformers` at embedding time with no error, no
warning, median chunk losing ~22% of its text from the search index, worst
case (a table) losing about two-thirds. Fixed by chunking with the
embedding model's real tokenizer: 1607 sections now produce **17,042
chunks** (789 sections split, up from 675 under the word-based version),
**0 of 17,042 exceeding the token limit** (median 502, max 504). The
2-token gap above the 502-token design target is a known effect of subword
tokenization — re-tokenizing a chunk in isolation after slicing it out by
character offset doesn't always reproduce the exact token boundaries it had
inside the full document — not a bug; 504 is still comfortably under BGE's
real 512 hard limit. Full account, including why the earlier synthetic
tests didn't catch this (each component — chunking overlap, retrieval
ranking — was correct in isolation; the bug was in the unit mismatch
between them):
[`docs/step2_1_debugging_log.md`](docs/step2_1_debugging_log.md).

**Note for Step 3.2:** this token limit and tokenizer are specific to
BGE-small. Any embedding model comparison needs its own token-length
regression check (`checks/check_token_length.py`) re-run per model, not an
assumption that whatever passed for BGE still holds.

## Baseline Retrieval and Generation (Step 2.1)
`build_index.py` embeds all 17,042 chunks with BAAI/bge-small-en-v1.5
(guards against over-length chunks before embedding, times the run, and
writes `data/index/index_meta.json` recording the config); `query_baseline.py`
retrieves top-5 by cosine similarity and generates an answer with
`claude-haiku-4-5-20251001`, citing chunk IDs and verifying every citation
actually exists in the retrieved set. A `--file` batch mode logs each
run's config, retrieved chunk IDs/scores, and full answers to
`experiments/baseline_2_1/`.

**Performance.** Indexing: 17,042 chunks in 26.0 minutes on CPU (~11
chunks/sec) — this sets the real cost of re-embedding for every Week 3
chunking experiment, which is why those will run on the 7-company dev
subset (~5 min each) rather than the full corpus, per the guide's
suggested workflow. Retrieval: 19ms once warm (the first query's 3.3s was
model load). Generation: 2.05s median — the LLM call is effectively all of
the end-to-end latency. Cost: $0.0042/query, so a 200-question eval set
costs under $1 per configuration — most of the $50 budget will go toward
Step 2.4's judge calibration, not bulk generation.

**Spot-check (8 questions, qualitative — not a metrics run; that's Step
2.4).** 0 fabricated citations across all 8. 2 correct abstentions
(a company genuinely not in the corpus; a fiscal year not yet filed). 1
false abstention (Apple: right filing retrieved, not the chunk with the
actual total — an honest "I don't know" with a real retrieval miss behind
it, not a hallucination). 1 wrong answer with fully valid citations
(Walmart) — the standout finding of this run.

**The Walmart case.** The answer stated "fiscal 2025 ending January 31,
2025" and cited figures that are actually Walmart's fiscal 2024 numbers
from a chunk whose real period end is 2024-01-31. The citation check
passed — the cited chunk genuinely was retrieved — but the generated
*claim* doesn't match what that chunk actually says. **This is the
concrete demonstration of why citation validity and faithfulness are
different checks**: a valid citation only proves the chunk existed in the
retrieved set, not that the answer is actually grounded in it. This is
exactly the gap Step 2.4's faithfulness judge exists to catch, and now
there's a real, hand-verified example of the failure mode it needs to
detect, ahead of building that judge.

**BofA CET1 ratio — verified, not just plausible.** The model selected
the FY2025 chunk over a higher-ranked FY2024 chunk and reported 11.4%.
Manually traced through the table's regulatory-minimum footnotes (10.0%
minimum = 4.5% + 3.0% + 2.5% buffer, matching the buffer disclosed for
December 31, 2025) to confirm the figure, ratio, year, and approach
(Standardized, BofA's binding ratio) are all correct. **Open question this
exposed:** the table's year/column labels weren't visible within the
retrieved chunk itself — they may sit in an adjacent chunk (chunk 52). If
so, the model got the right answer without having direct access to the
label that justifies it, which would mean this answer is correct by
inference or luck rather than by grounded evidence. Added as a distinct
failure hypothesis from Apple's "table embeds poorly" case: this one is
about a retrieved chunk not being self-contained, not about retrieval
missing it entirely.

**Failure hypotheses carried into Week 3-4 (evidenced, not speculative —
each has a real example from this run):**
- **Wrong period retrieved** (Walmart; BofA's top-ranked chunk was also
  the wrong year) — embeddings have no explicit sense of "most recent."
  Target: Step 4.1 metadata filtering.
- **10-Qs crowding out 10-Ks on annual questions** (ExxonMobil: 4 of 5
  retrieved chunks were quarterly; Apple: 2 of 5) — quarterly
  "compared with the prior-year period" phrasing apparently matches
  year-over-year query language better than a 10-K's annual framing does.
- **Cross-filing near-duplicate chunks crowding out diversity** (EA: 3 of
  5 slots held the same risk-factor language from 3 different 10-Qs, all
  scoring 0.749) — Week 1's MinHash dedup only caught duplicates *within*
  a filing, not the same boilerplate reused verbatim *across* separate
  quarterly filings. Candidate for retrieval-time suppression in Step 3.1.
- **Wrong company on generic topics** (Dollar General: 3 of 5 retrieved
  chunks were Costco's and Corsair's — generic supply-chain risk language
  reads nearly identically across unrelated retailers/manufacturers).
- **Financial-statement totals not retrieved** (Apple's false abstention)
  — hypothesis: headline numbers in dense tables may embed poorly as
  dense vectors; candidate test in Step 3.3 (BM25/hybrid).
  - **Related, more specific finding (BofA):** even when the right table
    *is* retrieved, its year/column labels may not be in the same chunk —
    a chunking-boundary problem distinct from the embedding-quality
    hypothesis above.
- **Compressed BGE similarity scores** — an irrelevant chunk (Nvidia
  question) scored 0.737, nearly identical to a correct hit's score. A
  known characteristic of BGE-family models. **Consequence: no raw
  cosine-similarity threshold can be used for abstention decisions** —
  that judgment has to come from the LLM itself (or, later, a reranker),
  not the retrieval score.

## Known limitation: word-joining in parsed text (Issue #17)
128 / 17,042 chunks (0.75%) contain two words run together with no space
(e.g. `"delayof"`, `"business,which"`), traced to `bs4_structured`
producing no separator between two adjacent inline HTML elements that had
no text node between them in the source. By rate, Unity (2.65%) and Ross
Stores (2.10%) are the most affected filers, not the largest filer by raw
count (JPM, 1.08%) — that distinction matters for where to look if this is
ever revisited. Deliberately deferred rather than fixed in Step 2.1 — low
prevalence corpus-wide, and a proper fix touches Step 1.4's HTML
extraction, which has already been hardened against 15 filer-specific
issues. Revisit if Week 4's error analysis shows it actually degrading
results, particularly for Step 3.3's BM25 exact-term matching, which is
more sensitive to this than dense embeddings are. Full account, including
the per-ticker breakdown:
[`docs/step2_1_debugging_log.md`](docs/step2_1_debugging_log.md).

## Status
Week 2, Step 2.1 complete. Chunking is token-based and verified (17,042
chunks, 0 over the embedding model's limit — Issue #16). Baseline index
and query pipeline run end to end with real data: 0 fabricated citations,
real failure patterns captured and evidenced (not hypothetical) ahead of
Week 4's formal error analysis. One known, deferred data-quality
limitation (Issue #17, word-joining, 0.75% of chunks corpus-wide). Full
debugging narratives: `docs/step1_4_debugging_log.md` (Week 1, 15 issues),
`docs/step2_1_debugging_log.md` (Step 2.1, issues #16-17).

Next: Step 2.2, designing the gold eval set. One decision already made
ahead of that step: gold sources will point to sections (ticker, period,
item_id), not chunk IDs, so the eval set survives Week 3's chunking
experiments without needing to be rebuilt each time chunk boundaries change.
