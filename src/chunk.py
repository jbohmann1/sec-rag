"""Step 2.1 - Fixed-size chunking with overlap, measured in real tokens.

Reads data/processed/records.jsonl (Step 1.4's section-level output) and
splits each section's text into chunks of at most MAX_TOKENS tokens with
OVERLAP tokens shared between consecutive chunks, writing one row per chunk
to data/processed/chunks.jsonl.

Token counting uses the embedding model's own tokenizer (BAAI/bge-small-en-v1.5),
so "500 tokens" here means exactly what the model will see. The model's hard
input limit is 512 tokens including 2 special tokens ([CLS], [SEP]); anything
longer is silently truncated at embedding time.

History (issue #16): the first version counted words instead of tokens.
On this corpus that produced 12,302 chunks of which 10,985 (89%) exceeded
512 tokens (median 659, max 1495), so most chunks lost their tail at
embedding time -- worst for tables, where numbers split into many tokens.

Chunks are cut from the ORIGINAL text at token character offsets, so each
chunk is an exact substring of the section (whitespace, newlines and table
row breaks preserved), not a re-joined approximation.

Run from the PROJECT ROOT with the venv active:
    python src/chunk.py
"""
import json
from pathlib import Path

from transformers import AutoTokenizer

IN_PATH = Path("data/processed/records.jsonl")
OUT_PATH = Path("data/processed/chunks.jsonl")

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MAX_TOKENS = 500   # 512 limit - 2 special tokens - safety margin (a chunk can
                   # start mid-word, so re-tokenizing it can add a token or two)
OVERLAP = 50       # tokens shared between consecutive chunks

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
# We tokenize whole sections here only to find cut points; nothing this long
# is ever fed to the model. Raising the limit silences the misleading
# "sequence length is longer than the maximum" warning.
tokenizer.model_max_length = 10**9


def chunk_text(text, max_tokens=MAX_TOKENS, overlap=OVERLAP):
    """Split text into overlapping token windows.

    Returns a list of (chunk_text, token_count) tuples. A section that fits
    in one window is returned whole, unsplit.
    """
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    offsets = enc["offset_mapping"]   # (start_char, end_char) per token
    n = len(offsets)
    if n <= max_tokens:
        return [(text, n)]

    chunks = []
    step = max_tokens - overlap
    for start in range(0, n, step):
        end = min(start + max_tokens, n)
        piece = text[offsets[start][0] : offsets[end - 1][1]]
        chunks.append((piece, end - start))
        if end == n:
            break
    return chunks


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    out_records = []
    n_split = 0
    for rec in records:
        pieces = chunk_text(rec["text"])
        if len(pieces) > 1:
            n_split += 1
        for i, (text, token_count) in enumerate(pieces):
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
                "token_count": token_count,
                "word_count": len(text.split()),
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ids = [r["chunk_id"] for r in out_records]
    print(f"{len(records)} sections -> {len(out_records)} chunks")
    print(f"{n_split} section(s) required splitting into multiple chunks")
    print(f"max token_count: {max(r['token_count'] for r in out_records)} (limit {MAX_TOKENS})")
    if len(set(ids)) != len(ids):
        print(f"WARNING: {len(ids) - len(set(ids))} duplicate chunk_id(s)")


if __name__ == "__main__":
    main()
