"""Step 1.4 - Split filings into sections, strip boilerplate, hash, dedup.

Reads data/manifest.csv, processes every filing, writes one JSON record per
Item/section to data/processed/records.jsonl.

One-time install (only needed for this step):
    pip install datasketch

Run from the PROJECT ROOT with the venv active:
    python src/clean_process.py
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from datasketch import MinHash, MinHashLSH

MANIFEST = Path("data/manifest.csv")
OUT_PATH = Path("data/processed/records.jsonl")
SENTINEL = "\x00SECTION\x00"

# ------------------------------------------------------ section detection ---
# Real EDGAR HTML almost never uses semantic <b>/<strong> tags for headings --
# it uses inline CSS (style="font-weight:bold") on a <span>, which is why
# html2text and plain BeautifulSoup both missed headings in Step 1.3.
ITEM_RE = re.compile(r"^\s*Item\s+(\d+[A-Za-z]?)[.\u2014\u2013:]\s*(.*)$", re.IGNORECASE)
# Some filers (oil & gas especially) combine two items into one heading, e.g.
# "Items 1 and 2. Business and Properties" -- ITEM_RE alone can't match this
# (plural "Items", two numbers) so it silently fails to detect the very first
# heading in the document, collapsing the whole filing into one FRONT blob.
COMBINED_ITEM_RE = re.compile(
    r"^\s*Items\s+(\d+[A-Za-z]?)\s+and\s+(\d+[A-Za-z]?)[.\u2014\u2013:]?\s*(.*)$", re.IGNORECASE
)


INLINE_WRAPPER_TAGS = {"span", "font", "a", "em", "i", "b", "strong", "u", "sub", "sup"}


def is_standalone(tag):
    """A real Item heading has no meaningful text BEFORE it within its
    immediate inline context -- it may be legitimately FOLLOWED by more text
    (e.g. a separate sibling span holding the title, as DVN does), so we
    only check what precedes it. An inline cross-reference -- e.g. "As
    discussed in Item 1A. Risk Factors above" -- has substantial prose text
    before it. Checking only the tag's own immediate siblings isn't always
    enough: if the heading text is wrapped in an extra inline <span> (common
    when a filer layers multiple style rules), the lead-in text sits as a
    sibling of that OUTER wrapper, one level up. So we climb through inline
    wrapper tags only, checking preceding siblings at each level -- and stop
    the instant the parent is NOT a pure inline wrapper (div/p/td/etc),
    WITHOUT checking that container's siblings at all. This matters because
    real EDGAR HTML often uses sibling <div>s as paragraphs rather than <p>
    tags, so climbing to "the nearest div" would expose the entire preceding
    document as false "preceding text" -- which is exactly what broke AAPL
    when this first tried climbing to any block-level tag.
    """
    node = tag
    while True:
        preceding_text = "".join(
            (s.get_text(" ", strip=True) if hasattr(s, "get_text") else str(s))
            for s in node.previous_siblings
        ).strip()
        if len(preceding_text) >= 10:
            return False
        parent = node.parent
        if parent is None or parent.name not in INLINE_WRAPPER_TAGS:
            break
        node = parent
    return True


def is_bold(tag):
    style = (tag.get("style") or "").lower()
    m = re.search(r"font-weight\s*:\s*(\w+)", style)
    if m:
        val = m.group(1)
        if val == "bold" or (val.isdigit() and int(val) >= 600):
            return True
    if tag.name in ("b", "strong"):
        return True
    # Not every filer uses bold for headings. JPM, for example, uses no
    # font-weight distinction at all: its 10-Ks mark headings with a larger,
    # distinct font-size (12pt vs ~10pt body text) in a custom font-family,
    # and its 10-Qs use underline instead. This is safe to add broadly:
    # this function only gates whether we ATTEMPT an ITEM_RE match on this
    # leaf's text, so it can't create a spurious section unless unrelated
    # text elsewhere also happens to literally read like an Item heading.
    if "underline" in style:
        return True
    size_m = re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)pt", style)
    if size_m and float(size_m.group(1)) >= 12:
        return True
    return False


def mark_sections(soup):
    """Insert a SENTINEL string before every heading-like element found.
    Only matches leaf elements (no nested tags) so a bold wrapper around
    several headings doesn't get double-counted.
    """
    # A table containing MULTIPLE bold "Item N." matches is almost certainly
    # a Table-of-Contents row layout (item number | title | page number as
    # separate cells) -- skip Item detection only inside those. A table
    # wrapping just ONE such heading is more likely a real heading laid out
    # in a single-cell table for styling, so that case is left alone.
    toc_tables = set()
    for table in soup.find_all("table"):
        hits = 0
        for leaf in table.find_all(True):
            if leaf.find(True) is not None:
                continue
            if leaf.find_parent("a", href=True) is not None:
                continue  # a hyperlink, not the real heading (see below)
            if not is_standalone(leaf):
                continue  # embedded in a larger sentence, not a real heading
            if is_bold(leaf) and (ITEM_RE.match(leaf.get_text(" ", strip=True))
                                   or COMBINED_ITEM_RE.match(leaf.get_text(" ", strip=True))):
                hits += 1
        if hits >= 2:
            toc_tables.add(id(table))

    for tag in soup.find_all(True):
        if tag.find(True) is not None:  # has nested tags, not a leaf
            continue
        if not is_bold(tag):
            continue
        if tag.find_parent("a", href=True) is not None:
            # A real Item heading is a link DESTINATION, never a link SOURCE.
            # Cross-reference sentences elsewhere in the document ("see Item
            # 1A. Risk Factors") are often rendered as underlined hyperlinks
            # quoting the heading's exact text -- without this, broadening
            # is_bold() to catch underline (needed for JPM) also catches
            # every one of these scattered cross-references as a duplicate
            # heading.
            continue
        if not is_standalone(tag):
            continue  # embedded in a larger sentence (a cross-reference), not a real heading
        text = tag.get_text(" ", strip=True)
        parent_table = tag.find_parent("table")
        if parent_table is not None and id(parent_table) in toc_tables:
            continue  # inside a genuine multi-row TOC table, not a real heading

        m = ITEM_RE.match(text)
        if m:
            raw_id = m.group(1).upper()
            marker = f"{SENTINEL}{raw_id}{SENTINEL}{m.group(2).strip()}{SENTINEL}"
            tag.replace_with(NavigableString(marker))
            continue

        cm = COMBINED_ITEM_RE.match(text)
        if cm:
            raw_id = f"{cm.group(1).upper()}-{cm.group(2).upper()}"
            marker = f"{SENTINEL}{raw_id}{SENTINEL}{cm.group(3).strip()}{SENTINEL}"
            tag.replace_with(NavigableString(marker))


# ---------------------------------------------------------------- Parts ---
# Which Part each Item belongs to is fixed by SEC convention -- it doesn't
# depend on how any given filer's HTML happens to style a "PART I" heading,
# which we found varies (not bold at all, or not even a <table>-based TOC)
# across filers in ways that made HTML-based Part detection unreliable.
TENK_PART_MAP = {
    "1": "I", "1A": "I", "1B": "I", "1C": "I", "2": "I", "3": "I", "4": "I",
    "1-2": "I",  # combined "Items 1 and 2" heading (e.g. DVN's Business and Properties)
    "5": "II", "6": "II", "7": "II", "7A": "II", "8": "II", "9": "II",
    "9A": "II", "9B": "II", "9C": "II",
    "10": "III", "11": "III", "12": "III", "13": "III", "14": "III",
    "15": "IV", "16": "IV",
}


def assign_parts(sections, form):
    """Prefix each item_id with its Part (I/II/III/IV).
    10-Ks: item number alone determines the Part (never reused across Parts).
    10-Qs: Part I and Part II both number their items from 1 -- Part I's
    items (1-4) always come first in the document, so the SECOND time
    "Item 1" appears marks the start of Part II.
    """
    if form == "10-K":
        return [
            (item_id if item_id == "FRONT" else f"{TENK_PART_MAP.get(item_id, '?')}-{item_id}", title, text)
            for item_id, title, text in sections
        ]
    if form == "10-Q":
        result = []
        seen_item_1 = 0
        current_part = "I"
        for item_id, title, text in sections:
            if item_id == "FRONT":
                result.append((item_id, title, text))
                continue
            if item_id == "1":
                seen_item_1 += 1
                if seen_item_1 == 2:
                    current_part = "II"
            result.append((f"{current_part}-{item_id}", title, text))
        return result
    return sections  # unknown form type: leave item_id as-is


def extract_text_with_tables(soup):
    """Same table handling as Step 1.3's bs4_structured -- rows become
    tab-separated lines inside [TABLE]...[/TABLE] markers.
    """
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Inline-XBRL filings wrap every tagged fact in <ix:header><ix:hidden>...
    # per the ix spec, these facts are tagged for machines but never meant
    # to be rendered. BeautifulSoup's get_text() ignores CSS/rendering rules,
    # so without this it dumps the entire raw XBRL fact block as plain text.
    for tag in soup.find_all(["ix:header", "ix:hidden"]):
        tag.decompose()
    for table in soup.find_all("table"):
        lines = []
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if any(cells):
                lines.append("\t".join(cells))
        table.replace_with("\n[TABLE]\n" + "\n".join(lines) + "\n[/TABLE]\n")
    return soup.get_text(separator="\n")


TOC_LINE_RE = re.compile(r"\t[^\t\n]*\t\d{1,4}(-\d{1,4})?\s*$")


def looks_like_toc(text, threshold=0.5, min_lines=3):
    """A Table of Contents entry -- even a long one, e.g. a filer that lists
    sub-headings under each Item with page numbers -- is structurally
    distinct from real prose: most of its lines are literally
    'title[TAB]page_number'. Real body text never looks like this, even
    when it's short, so this catches duplicates that a length check alone
    (JPM, WMT) doesn't.
    """
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < min_lines:
        return False
    hits = sum(1 for l in lines if TOC_LINE_RE.search(l))
    return (hits / len(lines)) >= threshold


def dedupe_short_duplicates(sections, min_len=150):
    """When the same raw item_id appears more than once within one document,
    it's almost always a TOC row or a stray duplicate heading match, not a
    second real section -- a real section is followed by substantial body
    text, while a TOC/stray entry either has very little text before the
    next heading, or (JPM, WMT) is a dense outline of sub-heading/page-number
    lines. Drop occurrences that are short OR TOC-shaped, as long as at
    least one occurrence survives. Legitimate 10-Q Part I/Part II reuse (two
    substantial, prose-shaped "Item 1" sections) survives both checks; a
    single genuinely short section (e.g. "Item 9. None.") survives because
    it has no competing duplicate.
    """
    groups = defaultdict(list)
    for i, sec in enumerate(sections):
        groups[sec[0]].append(i)

    keep = set()
    for item_id, indices in groups.items():
        if len(indices) == 1:
            keep.add(indices[0])
            continue
        good = [i for i in indices
                if len(sections[i][2]) >= min_len and not looks_like_toc(sections[i][2])]
        for i in (good or indices):  # keep at least one if all look bad
            keep.add(i)

    return [sec for i, sec in enumerate(sections) if i in keep]


def split_into_sections(html):
    """Returns a list of (item_id, item_title, text) tuples. Text before the
    first detected heading (cover page, TOC) is returned as item_id "FRONT".
    """
    soup = BeautifulSoup(html, "lxml")
    mark_sections(soup)
    text = extract_text_with_tables(soup)

    parts = text.split(SENTINEL)
    sections = [("FRONT", "", parts[0])]
    # after split: [front, id1, title1, body1, id2, title2, body2, ...]
    for i in range(1, len(parts) - 2, 3):
        sections.append((parts[i], parts[i + 1], parts[i + 2]))
    return sections


# ---------------------------------------------------------- boilerplate ---
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")
FORM_HEADER_RE = re.compile(r"\bForm\s+10-[KQ]\b", re.IGNORECASE)  # no longer used as an unconditional strip (see strip_boilerplate) -- it also matched one-off legitimate sentences like exhibit descriptions; genuine footers are still caught because they repeat
TOC_RE = re.compile(r"^\s*table of contents\s*$", re.IGNORECASE)


def strip_boilerplate(text, min_repeats=2):
    """Removes lines matching known boilerplate shapes, plus any short line
    that repeats often enough to be a running header/footer regardless of
    its exact wording -- this is what avoids needing one regex per filer.
    """
    lines = text.split("\n")
    counts = Counter(line.strip() for line in lines if line.strip())

    def is_boilerplate(line):
        s = line.strip()
        if not s:
            return False
        if s in ("[TABLE]", "[/TABLE]"):
            return False  # our own structural markers, not document content --
            # sections with multiple embedded tables repeat these often enough
            # to otherwise trip the generic frequency rule below, silently
            # destroying table-boundary information needed for chunking
        if PAGE_NUMBER_RE.match(s):
            return True
        if TOC_RE.match(s):
            return True
        if len(s) < 100 and counts[s] >= min_repeats:
            return True  # generic: short line repeated within this section
        return False

    kept = [line for line in lines if not is_boilerplate(line)]
    cleaned = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


# -------------------------------------------------------------- hashing ---
def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_minhash(text, num_perm=128, shingle_size=3):
    """5-word shingles -> MinHash signature, for near-duplicate detection."""
    words = text.split()
    mh = MinHash(num_perm=num_perm)
    if len(words) < shingle_size:
        mh.update(text.encode("utf-8"))
        return mh
    for i in range(len(words) - shingle_size + 1):
        shingle = " ".join(words[i:i + shingle_size])
        mh.update(shingle.encode("utf-8"))
    return mh


def find_near_duplicates(records, threshold=0.7, num_perm=128):
    """Returns a list of (key_a, key_b, est_similarity) pairs above threshold."""
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    minhashes = {}
    key_counts = Counter()
    for r in records:
        if len(r["text"]) < 200:  # too short for a meaningful shingle set
            continue
        base_key = f"{r['ticker']}|{r['report_date']}|{r['item_id']}"
        key_counts[base_key] += 1
        # Disambiguate instead of crashing if the same ticker/report_date/item_id
        # appears more than once (e.g. a heading matched twice in one filing) --
        # this used to raise "ValueError: The given key already exists".
        key = base_key if key_counts[base_key] == 1 else f"{base_key}#{key_counts[base_key]}"
        mh = make_minhash(r["text"], num_perm=num_perm)
        minhashes[key] = mh
        lsh.insert(key, mh)

    repeated = {k: c for k, c in key_counts.items() if c > 1}
    if repeated:
        print(f"  WARNING: {len(repeated)} (ticker, report_date, item_id) combos appeared "
              f"more than once -- likely a falsely-triggered heading match:")
        for k, c in list(repeated.items())[:10]:
            print(f"    {k}  (x{c})")

    seen_pairs = set()
    duplicates = []
    for key, mh in minhashes.items():
        for match in lsh.query(mh):
            if match == key:
                continue
            pair = tuple(sorted((key, match)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            duplicates.append((pair[0], pair[1], mh.jaccard(minhashes[pair[1]])))
    return duplicates


# ---------------------------------------------------------------- main ---
def main():
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    records = []
    for row in rows:
        path = Path(row["local_path"])
        if not path.exists():
            print(f"  MISSING FILE: {path} ({row['ticker']})")
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        sections = split_into_sections(html)
        sections = dedupe_short_duplicates(sections)
        sections = assign_parts(sections, row["form"])

        for item_id, item_title, raw_text in sections:
            cleaned = strip_boilerplate(raw_text)
            if len(cleaned) < 50:
                continue  # empty/near-empty section, not worth keeping
            records.append({
                "ticker": row["ticker"],
                "cik": row["cik"],
                "company": row["company"],
                "form": row["form"],
                "filing_date": row["filing_date"],
                "report_date": row["report_date"],
                "accession": row["accession"],
                "item_id": item_id,
                "item_title": item_title,
                "text": cleaned,
                "char_count": len(cleaned),
                "content_hash": content_hash(cleaned),
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} section records from {len(rows)} filings to {OUT_PATH}")

    item_counts = Counter(r["item_id"] for r in records)
    print(f"Sections found: {dict(item_counts.most_common(10))} ...")

    print("\nSearching for near-duplicate sections (this can take a minute)...")
    dupes = find_near_duplicates(records)
    print(f"Found {len(dupes)} near-duplicate section pairs (similarity >= 0.7):")
    for a, b, sim in sorted(dupes, key=lambda d: -d[2])[:10]:
        print(f"  {sim:.2f}  {a}  <->  {b}")


if __name__ == "__main__":
    main()
