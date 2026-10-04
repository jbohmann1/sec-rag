"""Step 2.1 - Embed all chunks, build a flat (brute-force) cosine-similarity
index, and save it. No vector database -- at this corpus size (a few
thousand chunks) a plain numpy array is microseconds per query, and a real
vector DB would add infrastructure for no measurable benefit (see the
guide's "framework sprawl" pitfall). Revisit only if corpus size or
latency actually demands it later.

One-time install:
    pip install sentence-transformers

Run from the PROJECT ROOT with the venv active:
    python src/build_index.py
"""
import json
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
    embeddings = embed_documents(model, [c["text"] for c in chunks])

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "embeddings.npy", embeddings)
    with open(INDEX_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"Indexed {len(chunks)} chunks, embedding dim {embeddings.shape[1]}")


# --------------------------------------------------------------- search ---
def cosine_search(query_vec, embeddings, top_k=5):
    """Both query_vec and embeddings rows are assumed already L2-normalized
    (normalize_embeddings=True above), so dot product == cosine similarity.
    Returns (indices, scores) for the top_k matches, highest first.
    """
    scores = embeddings @ query_vec
    top_idx = np.argsort(-scores)[:top_k]
    return top_idx, scores[top_idx]


def search(query, top_k=5):
    """Load the saved index and return the top_k chunks for a query."""
    embeddings = np.load(INDEX_DIR / "embeddings.npy")
    with open(INDEX_DIR / "chunks.jsonl", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]

    model = SentenceTransformer(MODEL_NAME)
    query_vec = embed_query(model, query)
    idx, scores = cosine_search(query_vec, embeddings, top_k=top_k)
    return [(chunks[i], float(s)) for i, s in zip(idx, scores)]


if __name__ == "__main__":
    build()
