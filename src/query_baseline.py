"""Step 2.1 - End-to-end baseline: retrieve top-5 chunks, generate an
answer that cites chunk IDs, and verify every citation actually exists in
the retrieved set (catches fabricated citations early -- cheap to check
now, important later in Step 4.3).

One-time install:
    pip install anthropic

Requires ANTHROPIC_API_KEY in your .env (from Step 1.1).

Run from the PROJECT ROOT with the venv active.

Single question (printed, not saved):
    python src/query_baseline.py "What was Apple's revenue in FY2025?"

Batch run (one question per line; saved to experiments/baseline_2_1/):
    python src/query_baseline.py --file experiments/baseline_2_1/questions.txt
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from build_index import search, INDEX_DIR  # reuses the retrieval code from Step 2.1

load_dotenv()
client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
GENERATION_MODEL = "claude-haiku-4-5-20251001"  # cost-effective tier for baseline volume
TOP_K = 5
MAX_TOKENS = 1000

# USD per million tokens, Claude Haiku 4.5 standard (non-batch) pricing.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-10-12)
PRICE_IN_PER_MTOK = 1.00
PRICE_OUT_PER_MTOK = 5.00

RUN_DIR = Path("experiments/baseline_2_1")

PROMPT_VERSION = "v1"
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
    """Chunk IDs look like TICKER|date|item_id|n, so only bracketed text
    containing '|' counts as a citation (ignores things like [1] or
    markdown links). Splits multi-citations such as [id1, id2] or [id1; id2].
    """
    cited = set()
    for group in CITATION_RE.findall(answer_text):
        if "|" not in group:
            continue
        for part in re.split(r"[,;]", group):
            part = part.strip()
            if part:
                cited.add(part)
    return cited


def verify_citations(answer_text, retrieved_chunk_ids):
    """Returns (ok, fabricated) -- fabricated is the set of cited ids that
    do NOT appear in what was actually retrieved. A non-empty fabricated
    set means the model cited something it wasn't given, which is exactly
    the failure mode Step 4.3 asks you to catch.
    """
    cited = extract_citations(answer_text)
    fabricated = cited - set(retrieved_chunk_ids)
    return len(fabricated) == 0, fabricated


def answer(question, top_k=TOP_K):
    t0 = time.perf_counter()
    results = search(question, top_k=top_k)
    t1 = time.perf_counter()

    context = format_context(results)
    retrieved_ids = [chunk["chunk_id"] for chunk, _ in results]

    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Context:\n\n{context}\n\nQuestion: {question}",
        }],
    )
    t2 = time.perf_counter()
    answer_text = response.content[0].text

    ok, fabricated = verify_citations(answer_text, retrieved_ids)
    if fabricated:
        print(f"WARNING: model cited chunk id(s) not in the retrieved set: {fabricated}",
              file=sys.stderr)

    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    cost = in_tok / 1e6 * PRICE_IN_PER_MTOK + out_tok / 1e6 * PRICE_OUT_PER_MTOK

    return {
        "question": question,
        "answer": answer_text,
        "retrieved": [
            {
                "rank": r + 1,
                "chunk_id": chunk["chunk_id"],
                "score": round(score, 4),
                "ticker": chunk["ticker"],
                "form": chunk["form"],
                "report_date": chunk["report_date"],
                "filing_date": chunk["filing_date"],
                "item_title": chunk["item_title"],
            }
            for r, (chunk, score) in enumerate(results)
        ],
        "citations": sorted(extract_citations(answer_text)),
        "citations_valid": ok,
        "fabricated_citations": sorted(fabricated),
        "retrieval_ms": round((t1 - t0) * 1000),
        "generation_ms": round((t2 - t1) * 1000),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(cost, 6),
        "stop_reason": response.stop_reason,
    }


def print_result(res):
    print(f"\nQ: {res['question']}\n")
    print(f"A: {res['answer']}\n")
    print("Retrieved:")
    for r in res["retrieved"]:
        print(f"  {r['rank']}. {r['score']:.3f}  {r['chunk_id']}  "
              f"({r['form']}, filed {r['filing_date']})")
    print(f"Citations valid: {res['citations_valid']}")
    if res["fabricated_citations"]:
        print(f"FABRICATED: {res['fabricated_citations']}")
    print(f"Latency: retrieval {res['retrieval_ms']} ms, generation {res['generation_ms']} ms | "
          f"tokens {res['input_tokens']} in / {res['output_tokens']} out | "
          f"${res['cost_usd']:.4f}")


def run_batch(questions_path):
    questions = [q.strip() for q in Path(questions_path).read_text(encoding="utf-8").splitlines()
                 if q.strip() and not q.lstrip().startswith("#")]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUN_DIR / f"run_{stamp}.jsonl"

    index_meta_path = INDEX_DIR / "index_meta.json"
    config = {
        "run": stamp,
        "generation_model": GENERATION_MODEL,
        "top_k": TOP_K,
        "max_tokens": MAX_TOKENS,
        "prompt_version": PROMPT_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "price_per_mtok": {"input": PRICE_IN_PER_MTOK, "output": PRICE_OUT_PER_MTOK},
        "index": (json.loads(index_meta_path.read_text(encoding="utf-8"))
                  if index_meta_path.exists() else None),
        "questions_file": str(questions_path),
    }
    (RUN_DIR / f"config_{stamp}.json").write_text(json.dumps(config, indent=2),
                                                   encoding="utf-8")

    results = []
    with open(out_path, "w", encoding="utf-8") as f:
        for q in questions:
            res = answer(q)
            print_result(res)
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            results.append(res)

    # Note: the first query's retrieval time includes loading the model and
    # index once; the rest are warm. Report the warm median for latency.
    n = len(results)
    total_cost = sum(r["cost_usd"] for r in results)
    gen = sorted(r["generation_ms"] for r in results)
    ret = sorted(r["retrieval_ms"] for r in results[1:]) or [results[0]["retrieval_ms"]]
    n_fab = sum(1 for r in results if r["fabricated_citations"])
    print("\n" + "=" * 60)
    print(f"{n} questions | fabricated-citation answers: {n_fab}")
    print(f"median retrieval (warm): {ret[len(ret)//2]} ms | median generation: {gen[n//2]} ms")
    print(f"total cost ${total_cost:.4f} | per query ${total_cost / n:.4f}")
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--file":
        run_batch(args[1])
    else:
        q = " ".join(args) or "What was Apple's total revenue in its most recent fiscal year?"
        print_result(answer(q))
