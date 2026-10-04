"""Step 2.1 - Fixed-size chunking with overlap.

Reads data/processed/records.jsonl (Step 1.4's section-level output) and
splits each section's text into ~512-token chunks with ~50-token overlap,
writing one row per chunk to data/processed/chunks.jsonl.

NOTE on token counting: this uses a word-count approximation (splitting on
whitespace) rather than a real tokenizer, since a real tokenizer needs a
model-specific download. Once you've installed sentence-transformers for
Step 2.1's embedding model, swap CHUNK_SIZE/OVERLAP to use that model's
actual tokenizer (AutoTokenizer.from_pretrained(...).tokenize()) for an
accurate token count -- word count typically undercounts tokens by ~25-30%
for English prose, so real chunks will run a bit smaller than this estimates.

Run from the PROJECT ROOT with the venv active:
    python src/chunk.py
"""
import json
from pathlib import Path

IN_PATH = Path("data/processed/records.jsonl")
OUT_PATH = Path("data/processed/chunks.jsonl")

CHUNK_SIZE = 512   # words (approximating tokens -- see note above)
OVERLAP = 50       # words of overlap between consecutive chunks


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """Split text into overlapping word-count windows. Returns a list of
    (chunk_text, start_word_idx, end_word_idx) tuples. A section shorter
    than one chunk is returned as a single chunk, unsplit.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [(text, 0, len(words))]

    chunks = []
    start = 0
    step = chunk_size - overlap
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append((" ".join(words[start:end]), start, end))
        if end == len(words):
            break
        start += step
    return chunks


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    out_records = []
    for rec in records:
        pieces = chunk_text(rec["text"])
        for i, (text, start, end) in enumerate(pieces):
            chunk_id = f"{rec['ticker']}|{rec['report_date']}|{rec['item_id']}|{i}"
            out_records.append({
                "chunk_id": chunk_id,
                "ticker": rec["ticker"],
                "company": rec["company"],
                "form": rec["form"],
                "filing_date": rec["filing_date"],
                "report_date": rec["report_date"],
                "accession": rec["accession"],
                "item_id": rec["item_id"],
                "item_title": rec["item_title"],
                "text": text,
                "chunk_index": i,
                "n_chunks_in_section": len(pieces),
                "word_count": end - start,
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{len(records)} sections -> {len(out_records)} chunks")
    multi = [r for r in records if len(chunk_text(r["text"])) > 1]
    print(f"{len(multi)} section(s) required splitting into multiple chunks")


if __name__ == "__main__":
    main()
