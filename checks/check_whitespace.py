import json, re
from collections import Counter

pat = re.compile(r"[a-z],[a-z]|[a-z]\.[A-Z][a-z]")   # "business,which" / "end.The"
hits = Counter(); total = Counter()
for line in open("data/processed/chunks.jsonl", encoding="utf-8"):
    c = json.loads(line)
    total[c["ticker"]] += 1
    if pat.search(c["text"]):
        hits[c["ticker"]] += 1
print(f"{sum(hits.values())}/{sum(total.values())} chunks affected")
for t, n in hits.most_common(10):
    print(f"  {t}: {n}/{total[t]}")