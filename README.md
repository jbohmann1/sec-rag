# RAG over SEC Filings
Measured investigation into what makes retrieval work on messy financial documents.

## Scope
- **Companies:** 20 across 4 sectors (see table below)
- **Fiscal years:** FY2023, FY2024, FY2025
- **Form types:**
  - 10-K (annual report): all 20 companies x 3 fiscal years = 60 filings
  - 10-Q (quarterly report): the three FY2025 10-Qs for the dev subset only = 15 filings
- **Total corpus:** ~75 filings
- **Dev subset:** AAPL, JPM, WMT, XOM, DG (5 companies, one per sector, used for fast iteration)

| Sector  | Companies |
|---------|-----------|
| Tech    | Apple (AAPL), Microsoft (MSFT), Salesforce (CRM), Intel (INTC), Workday (WDAY) |
| Banking | JPMorgan (JPM), Bank of America (BAC), Goldman Sachs (GS), Citizens Financial (CFG), Regions Financial (RF) |
| Retail  | Walmart (WMT), Target (TGT), Costco (COST), Dollar General (DG), Ross Stores (ROST) |
| Energy  | ExxonMobil (XOM), Chevron (CVX), ConocoPhillips (COP), Devon Energy (DVN), Marathon Petroleum (MPC) |

## Scoping rationale
- **Size:** ~75 filings is a scope that can be finished. A polished small project beats a half-finished large one; scale up only if ahead of schedule.
- **Years:** As of September 2026, the last three complete fiscal years are FY2023-FY2025. FY2026 10-Ks are mostly not filed yet.
- **Fiscal year-end differences:** Fiscal years do not match calendar years. Apple's FY ends in late September, Microsoft's on June 30, and Walmart's and Workday's on January 31, so "FY2024" covers very different date ranges depending on the company. Wrong-year retrieval is a major error source, so metadata records the **fiscal year end date**, not just a year label.
- **Famous vs. less-famous names:** LLMs have memorized facts about famous companies (e.g. Apple's FY2023 revenue), which can make retrieval metrics meaningless for those questions. Mid-caps like Workday, Citizens Financial, Regions, Dollar General, Ross Stores and Devon Energy force the system to actually retrieve.
- **Sectors:** Tech, banking, retail and energy give varied document structure, terminology and fiscal calendars.
- **Dev subset choice:** One company per sector, a mix of famous (AAPL, JPM, WMT, XOM) and less-famous (DG) names, with different fiscal year-ends.

## Status
Week 1, Step 1.1 - setup complete; corpus scope defined
