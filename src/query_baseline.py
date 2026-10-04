"""Step 2.1 - End-to-end baseline: retrieve top-5 chunks, generate an
answer that cites chunk IDs, and verify every citation actually exists in
the retrieved set (catches fabricated citations early -- cheap to check
now, important later in Step 4.3).

One-time install:
    pip install anthropic

Requires ANTHROPIC_API_KEY in your .env (from Step 1.1).

Run from the PROJECT ROOT with the venv active:
    python src/query_baseline.py "What was Apple's revenue in FY2025?"
"""
import os
import re
import sys

from dotenv import load_dotenv
from anthropic import Anthropic

from build_index import search  # reuses the retrieval code from Step 2.1

load_dotenv()
client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
GENERATION_MODEL = "claude-haiku-4-5-20251001"  # cost-effective tier for baseline volume

SYSTEM_PROMPT = """You answer questions about SEC filings using only the \
provided context chunks. Rules:
1. Answer ONLY using information in the provided chunks. Do not use outside knowledge.
2. Every factual claim must end with a citation in the form [chunk_id].
3. If the chunks don't contain enough information to answer, say so explicitly \
rather than guessing. Do not fill gaps with plausible-sounding numbers.
4. Be concise. Do not restate the question."""


def format_context(results):
    """results: list of (chunk_dict, score) from build_index.search()."""
    blocks = []
    for chunk, score in results:
        blocks.append(
            f"[{chunk['chunk_id']}] {chunk['company']} ({chunk['ticker']}), "
            f"{chunk['form']} for period {chunk['report_date']}, "
            f"{chunk['item_title']}:\n{chunk['text']}"
        )
    return "\n\n---\n\n".join(blocks)


CITATION_RE = re.compile(r"\[([^\[\]]+)\]")


def extract_citations(answer_text):
    return set(CITATION_RE.findall(answer_text))


def verify_citations(answer_text, retrieved_chunk_ids):
    """Returns (ok, fabricated) -- fabricated is the set of cited ids that
    do NOT appear in what was actually retrieved. A non-empty fabricated
    set means the model cited something it wasn't given, which is exactly
    the failure mode Step 4.3 asks you to catch.
    """
    cited = extract_citations(answer_text)
    fabricated = cited - set(retrieved_chunk_ids)
    return len(fabricated) == 0, fabricated


def answer(question, top_k=5):
    results = search(question, top_k=top_k)
    context = format_context(results)
    retrieved_ids = [chunk["chunk_id"] for chunk, _ in results]

    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Context:\n\n{context}\n\nQuestion: {question}",
        }],
    )
    answer_text = response.content[0].text

    ok, fabricated = verify_citations(answer_text, retrieved_ids)
    if not fabricated:
        pass
    else:
        print(f"WARNING: model cited chunk id(s) not in the retrieved set: {fabricated}",
              file=sys.stderr)

    return {
        "question": question,
        "answer": answer_text,
        "retrieved_chunk_ids": retrieved_ids,
        "citations_valid": ok,
        "fabricated_citations": list(fabricated),
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What was Apple's total revenue in its most recent fiscal year?"
    result = answer(q)
    print(f"\nQ: {result['question']}\n")
    print(f"A: {result['answer']}\n")
    print(f"Retrieved: {result['retrieved_chunk_ids']}")
    print(f"Citations valid: {result['citations_valid']}")
    if result["fabricated_citations"]:
        print(f"FABRICATED: {result['fabricated_citations']}")
