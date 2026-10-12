# Step 2.1 debugging log: chunking and indexing

Companion to `docs/step1_4_debugging_log.md`, same purpose: a chronological
record of what broke and how it was found, kept separate from the README
because this is a debugging narrative, not a scope decision. Issue numbers
continue from the Week 1 log (which ended at #15).

## Issue #16 — Chunks measured in words, embedding model limited by tokens

**Symptom:** none visible. Nothing errored or warned during chunking;
`sentence-transformers` truncates over-length inputs silently at embedding
time. Found only by measuring chunk lengths with the model's own tokenizer
before building the index — i.e. by checking a real constraint in its own
units instead of trusting the chunker's self-report.

**Cause:** `chunk.py` approximated tokens with whitespace-split words
(512-word chunks, 50-word overlap). BAAI/bge-small-en-v1.5 accepts at most
512 tokens including 2 special tokens. Financial text runs well above one
token per word, and tables (numbers, `$`, `%`, `|` separators) run highest
of all. A second, smaller defect rode along with it: chunks were rebuilt
with `" ".join(words)`, which flattened newlines, so table rows that were
meant to stay on separate lines ran together inside a chunk.

**Measured impact (before the fix):** 1607 sections -> 12,302 chunks;
**10,985 / 12,302 (89%) over the 512-token limit**, median 659 tokens, max
1,495. The median chunk silently lost about 22% of its text from the
search index at embedding time; the worst case (very likely a table) lost
about two-thirds. Nothing would have errored — this would have shown up
only as mysteriously weak retrieval on content near the end of chunks, and
worst of all on tables, exactly the content this corpus cares most about
getting right.

**Why the Step 2.1 tests up to this point missed it:** the chunking test
verified overlap math in words; the retrieval test verified cosine ranking
with synthetic vectors. Each component was correct in isolation — the bug
lived at the interface between them, in the mismatch between the
chunker's unit (words) and the embedding model's unit (tokens).

**Fix:** chunk with the embedding model's own tokenizer instead of a word
count. Windows of at most 500 tokens (512 minus 2 special tokens minus a
safety margin for chunks that start mid-word), 50-token overlap. Chunks
are sliced from the original text at the tokenizer's character offsets, so
each chunk is an exact substring of its section — this also fixes the
newline/table-row flattening defect as a side effect, since no
`" ".join()` reconstruction happens anymore. Added a `token_count` field
per chunk; `word_count` kept for reference.

**Result (after the fix):** 1607 sections -> 17,042 chunks (789 sections
needed splitting, up from 675 — roughly 114 sections were under the
512-word threshold but over the real 500-token one, and had previously
been kept whole and truncated silently). **0 / 17,042 chunks over 512
tokens**, median 502, max 504.

**Open note on the max:** the design target was <=502 tokens (500 content
+ 2 special), but the measured max is 504. This is a known effect of
subword tokenization, not a bug: re-tokenizing a chunk in isolation after
slicing it out by character offset doesn't always reproduce the exact
token boundaries it had inside the full document — a token can split into
more subword pieces once isolated, especially at a chunk's edges. 504 is
still well under BGE's real 512 hard limit, so nothing truncates, but the
"window size + special tokens = exact max" mental model was off by a
couple of tokens in practice. Worth remembering if the safety margin is
ever tightened.

**Regression check:** `test.py` — a token-length check run directly over
`data/processed/chunks.jsonl` (not over the original offsets, over the
actual final chunk text, which is what caught the 504 discrepancy above).
Expected output: `0/N chunks exceed 512 tokens`. Re-run this whenever the
embedding model changes (relevant for the Step 3.2 model comparison,
where a different model will have its own token limit and its own
tokenizer).

**Lesson:** when a limit is defined in one component's units, measure it
in those units, not an approximation of them. The same principle that
caught Week 1's heading-detection issues (verify against the real
artifact, not an assumption about it) applies just as much to numeric
limits as to text patterns.
