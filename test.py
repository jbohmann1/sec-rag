import json
for line in open("data/index/chunks.jsonl", encoding="utf-8"):
    c = json.loads(line)
    if c["chunk_id"] == "BAC|2025-12-31|10-K:II-7|53":
        print(c["text"])
        break