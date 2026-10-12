from sentence_transformers import SentenceTransformer
import json

model = SentenceTransformer("BAAI/bge-small-en-v1.5")
tok = model.tokenizer
with open("data/processed/chunks.jsonl", encoding="utf-8") as f:
    lengths = sorted(len(tok.encode(json.loads(l)["text"])) for l in f)
over = sum(l > 512 for l in lengths)
print(f"{over}/{len(lengths)} chunks exceed 512 tokens ({over/len(lengths):.0%})")
print("median:", lengths[len(lengths)//2], " max:", lengths[-1])