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
```

**Section detection.** Headings are found by scanning for text matching `Item
\d+[A-Za-z]?[.\u2014\u2013:]` inside elements styled as headings — the
workaround for EDGAR's lack of semantic heading tags noted in Step 1.3. A
second pattern also catches combined "Items N and M." headings (an oil & gas
convention — see below). "Heading-styled" turned out to mean different things
for different filers (bold, underline, or a larger custom font-size), and a
handful of filer-specific quirks required real debugging to get right; see
[`docs/step1_4_debugging_log.md`](docs/step1_4_debugging_log.md) for the full
chronological account. Summary:

| Filer(s) | Quirk | Fix |
|---|---|---|
| COST, COP | Real heading uses an em dash, not a period, between item number and title (`Item 1\u2014Business`) | Broadened the separator pattern to accept a period, em dash, en dash, or colon |
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
Confirmed working correctly on real data: it correctly identifies a 10-Q's
Part II "Legal Proceedings" section as near-identical to the same fiscal
year's 10-K Part I "Legal Proceedings" section (both are the same real-world
disclosure, filed under different Item numbers by convention), and separately
flags AAPL's cover page and "Properties" disclosure as reused nearly verbatim
year over year — both legitimate, not detector errors.

## Status
Week 1, Step 1.4 - cleaning, metadata extraction and near-duplicate detection complete
