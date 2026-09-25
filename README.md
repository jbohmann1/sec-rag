# RAG over SEC Filings
Measured investigation into what makes retrieval work on messy financial documents.

## Scope
- **Companies:** 24 across 6 sectors (see table below)
- **Period selection rule:** for each company, take the three most recent 10-Ks whose fiscal period ends on or before 2025-12-31. The rule is based on the period-end date, not a fiscal-year label, because companies label years differently (see rationale below).
- **Form types:**
  - 10-K (annual report): 24 companies x 3 filings = 72 filings
  - 10-Q (quarterly report): the three most recent 10-Qs for the dev subset only = 21 filings
- **Total corpus:** ~93 filings
- **Dev subset:** AAPL, JPM, WMT, XOM, DG, EA, ACM (7 companies: one per sector, plus a second retailer (DG) for a less-famous name; used for fast iteration)

| Sector       | Companies |
|--------------|-----------|
| Tech         | Apple (AAPL), Microsoft (MSFT), Intel (INTC), Workday (WDAY) |
| Banking      | JPMorgan (JPM), Bank of America (BAC), Goldman Sachs (GS), Citizens Financial (CFG) |
| Retail       | Walmart (WMT), Costco (COST), Dollar General (DG), Ross Stores (ROST) |
| Energy       | ExxonMobil (XOM), ConocoPhillips (COP), Devon Energy (DVN), Marathon Petroleum (MPC) |
| Gaming       | Electronic Arts (EA), Roblox (RBLX), Unity Software (U), Corsair Gaming (CRSR) |
| Architecture & Engineering | AECOM (ACM), Fluor (FLR), Tetra Tech (TTEK), Sterling Infrastructure (STRL) |

**Note on excluded companies:** Tencent (and its subsidiary Riot Games) file with the Hong Kong Stock Exchange, not the SEC, so no 10-K exists for either. Activision Blizzard's last 10-K covered FY2022 (filed Feb 2023); Microsoft completed its acquisition in October 2023, so no later 10-K exists and its filings wouldn't line up in time with the rest of the corpus. Neither is included. There is no major public *pure* architecture firm — Gensler, HOK, SOM and similar are private partnerships that file nothing with the SEC — so "Architecture & Engineering" uses the closest public equivalent: architecture-and-engineering and engineering-and-construction firms.

**Note on a mid-project substitution:** NV5 Global (NVEE) was originally selected for this sector but was dropped after NV5 agreed to be acquired by Acuren Corporation (announced May 2025, shareholder approval July 2025); the ticker has since been delisted, and NV5's fiscal-year timing means it would only have one usable 10-K in the 2025-12-31 window — the same problem that excluded Activision Blizzard. Sterling Infrastructure (STRL) replaces it. Two companies still in the corpus were also affected by 2026 corporate events but remain usable: Exxon (XOM) redomiciled from New Jersey to Texas on 2026-07-01, so its ticker now maps to a new successor entity's CIK with no 10-K history — its FY2023-2025 10-Ks are pulled from its original CIK instead. Electronic Arts (EA) went private on 2026-08-04 and was delisted; all three of its needed 10-Ks were filed while it was still public, so its data is unaffected, but its ticker no longer resolves via SEC's standard ticker lookup and its original CIK is used directly.

## Scoping rationale
- **Size:** ~93 filings, covering six sectors at four companies each. Trimmed from an initial 30 to 24 companies (one dropped per sector) to protect eval-set and error-analysis time later in the schedule, per the guide's scope-creep warning. Each drop favored the more structurally redundant company — e.g., CRM and WDAY were both January-fiscal-year SaaS firms, so CRM was cut and WDAY (the less-famous name) kept.
- **Period-end rule instead of fiscal-year labels:** Fiscal years do not match calendar years, and companies label them inconsistently. Apple's fiscal year ends in late September, Microsoft's on June 30, and Walmart's, Workday's and other retailers' in late January or early February. Dollar General calls the year ending January 2025 "fiscal 2024", while Walmart calls the same period "fiscal 2025". Selecting filings by period-end date (on or before 2025-12-31) gives consistent time coverage across companies. Some FY2026 filings already exist (e.g. January year-ends and Microsoft's June 2026 year), but the cutoff deliberately excludes them.
- **Metadata:** Each filing records its fiscal period end date, not just a year label, since wrong-year retrieval is a major error source.
- **Famous vs. less-famous names:** LLMs have memorized facts about famous companies (e.g. Apple's revenue), which can make retrieval metrics meaningless for those questions. Mid-caps like Workday, Citizens Financial, Dollar General, Ross Stores, Devon Energy, Corsair Gaming and Sterling Infrastructure force the system to actually retrieve.
- **Sectors (business reasons):** Tech, banking, retail, energy, gaming and architecture & engineering give varied terminology and fiscal calendars. Gaming and architecture & engineering were added for personal interest and domain familiarity (gaming) and current work experience (architecture/engineering process management).
- **Sectors (technical reasons):** Each sector has a different document structure that stresses the parser and retriever differently:
  - Energy: climate-risk disclosures change year to year, giving rich material for multi-hop and year-over-year questions.
  - Banking: regulatory-capital tables.
  - Retail: seasonality and segment reporting.
  - Gaming: bookings vs. GAAP revenue reconciliations (notably Roblox), live-service/microtransaction revenue recognition.
  - Architecture & Engineering: project-based (percentage-of-completion) revenue recognition, backlog disclosures.
- **Dev subset choice:** One company per sector, plus a second retailer (DG) for a less-famous name. It mixes famous (AAPL, JPM, WMT, XOM, EA, ACM) and less-famous names with different fiscal year-ends.

## Status
Week 1, Step 1.1 - setup complete; corpus scope defined
