#!/usr/bin/env python3
"""Select top 5 seed papers by citation count from existing sweep results."""
import json

# Load existing sweep results
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    papers = json.load(f)

# Filter candidates: must have DOI, year <= 2022, 50 <= cited_by < 10000
# Upper bound avoids mega-cited papers that are too general
candidates = [
    p for p in papers
    if p.get("doi")
    and p.get("year", 9999) <= 2022
    and 50 <= p.get("cited_by_count", 0) < 10000
]

# Sort by citation count descending
candidates.sort(key=lambda p: p.get("cited_by_count", 0), reverse=True)

# Take top 5
seeds = candidates[:5]

# Extract relevant fields
seed_data = [
    {
        "doi": s.get("doi"),
        "title": s.get("title"),
        "cited_by_count": s.get("cited_by_count"),
        "year": s.get("year")
    }
    for s in seeds
]

# Save
with open("/home/kyuwon/projects/papersift/outputs/e004/seeds.json", "w") as f:
    json.dump(seed_data, f, indent=2, ensure_ascii=False)

print(f"Selected {len(seed_data)} seed papers from {len(candidates)} candidates")
for i, s in enumerate(seed_data, 1):
    print(f"{i}. [{s['year']}] {s['title'][:80]}... ({s['cited_by_count']} citations)")
