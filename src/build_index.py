"""Step 2.1 - Embed all chunks, build a flat (brute-force) cosine-similarity
index, and save it. No vector database -- at this corpus size (~17k chunks)
a plain numpy array is milliseconds per query, and a real vector DB would
add infrastructure for no measurable benefit (see the guide's "framework
sprawl" pitfall). Revisit only if corpus size or latency actually demands it.

One-time install:
    pip install sentence-transformers

Run from the PROJECT ROOT with the venv active:
    python src/build_index.py
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

CHUNKS_PATH = Path("data/processed/chunks.jsonl")
INDEX_DIR = Path("data/index")
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# bge models are trained to expect this exact prefix on retrieval queries
# (not on the documents being indexed) -- omitting it measurably hurts
# retrieval quality for this model family.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def load_chunks():
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def embed_documents(model, texts, batch_size=32):
    return model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                        show_progress_bar=True)


def embed_query(model, query):
    vec = model.encode([QUERY_PREFIX + query], normalize_embeddings=True)
    return vec[0]


def build():
    chunks = load_chunks()
    model = SentenceTransformer(MODEL_NAME)

    # Safety net for issue #16: refuse to build if any chunk would be
    # silently truncated by the model.
    tok = model.tokenizer
    too_long = [c["chunk_id"] for c in chunks
                if len(tok.encode(c["text"])) > model.max_seq_length]
    if too_long:
        raise SystemExit(f"{len(too_long)} chunk(s) exceed {model.max_seq_length} "
                         f"tokens, e.g. {too_long[:3]}. Re-run chunk.py.")

    t0 = time.perf_counter()
    embeddings = embed_documents(model, [c["text"] for c in chunks])
    elapsed = time.perf_counter() - t0

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "embeddings.npy", embeddings)
    with open(INDEX_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Record what this index was built from, so every experiment can be
    # traced back to the exact chunking + model it used.
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL_NAME,
        "query_prefix": QUERY_PREFIX,
        "normalized": True,
        "n_chunks": len(chunks),
        "dim": int(embeddings.shape[1]),
        "max_seq_length": model.max_seq_length,
        "chunking": "token-based, max 500 tokens, 50-token overlap (chunk.py)",
        "embed_seconds": round(elapsed, 1),
    }
    with open(INDEX_DIR / "index_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Indexed {len(chunks)} chunks, embedding dim {embeddings.shape[1]}, "
          f"{elapsed / 60:.1f} min ({len(chunks) / elapsed:.0f} chunks/s)")


# --------------------------------------------------------------- search ---
def cosine_search(query_vec, embeddings, top_k=5):
    """Both query_vec and embeddings rows are assumed already L2-normalized
    (normalize_embeddings=True above), so dot product == cosine similarity.
    Returns (indices, scores) for the top_k matches, highest first.
    """
    scores = embeddings @ query_vec
    top_idx = np.argsort(-scores)[:top_k]
    return top_idx, scores[top_idx]


# Loaded once per process and reused, so a batch of queries doesn't reload
# the model and the 17k-row index for every question (and so per-query
# latency measures search, not disk/model loading).
_cache = {}


def _load():
    if not _cache:
        _cache["embeddings"] = np.load(INDEX_DIR / "embeddings.npy")
        with open(INDEX_DIR / "chunks.jsonl", encoding="utf-8") as f:
            _cache["chunks"] = [json.loads(line) for line in f]
        _cache["model"] = SentenceTransformer(MODEL_NAME)
    return _cache


def search(query, top_k=5):
    """Return the top_k (chunk, score) pairs for a query, highest first."""
    c = _load()
    query_vec = embed_query(c["model"], query)
    idx, scores = cosine_search(query_vec, c["embeddings"], top_k=top_k)
    return [(c["chunks"][i], float(s)) for i, s in zip(idx, scores)]


if __name__ == "__main__":
    build()
