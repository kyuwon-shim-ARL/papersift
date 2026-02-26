#!/usr/bin/env python3
"""Step 1: Select virtual cell seeds from existing sweep data."""

import json
import os
import sys

# Add paper-pipeline to path
sys.path.insert(0, "/home/kyuwon/projects/tools/paper-pipeline/src")
from paper_pipeline.discovery import PaperDiscovery

# Load existing sweep data
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    papers = json.load(f)

# Virtual cell core keywords (including hyphenated variations)
keywords = [
    "virtual cell", "whole-cell", "whole cell model",
    "in silico cell", "cell simulation", "computational cell",
    "digital cell", "virtual organ"
]

# Find candidates
candidates = []
for p in papers:
    title = (p.get("title") or "").lower()
    if any(kw in title for kw in keywords):
        oa_id = p.get("openalex_id", "")
        doi = p.get("doi", "")
        citations = p.get("cited_by_count", 0)
        year = p.get("year") or p.get("publication_year") or 0

        if doi and citations >= 20 and year >= 2010:
            candidates.append({
                "paper": p,
                "citations": citations,
                "year": year
            })

# Sort by citations, select diverse seeds
candidates.sort(key=lambda x: x["citations"], reverse=True)

print(f"Found {len(candidates)} candidates with virtual cell keywords")
print("\nTop 20 candidates:")
for i, c in enumerate(candidates[:20], 1):
    p = c["paper"]
    print(f"{i:2d}. [{c['year']}] {p.get('title', '')[:80]}")
    print(f"    DOI: {p.get('doi')} | Citations: {c['citations']}")

# Select top 5 seeds (diverse years if possible)
if len(candidates) >= 5:
    seeds = [c["paper"] for c in candidates[:5]]
else:
    # Fallback: broaden keywords
    print("\n⚠️  Less than 5 candidates, broadening search...")
    broader_keywords = ["cell model", "systems biology model", "cellular simulation"]

    for p in papers:
        title = (p.get("title") or "").lower()
        if any(kw in title for kw in broader_keywords):
            oa_id = p.get("openalex_id", "")
            doi = p.get("doi", "")
            citations = p.get("cited_by_count", 0)
            year = p.get("year") or p.get("publication_year") or 0

            if doi and citations >= 50 and year >= 2010:
                # Check not already in candidates
                if not any(c["paper"].get("doi") == doi for c in candidates):
                    candidates.append({
                        "paper": p,
                        "citations": citations,
                        "year": year
                    })

    candidates.sort(key=lambda x: x["citations"], reverse=True)
    seeds = [c["paper"] for c in candidates[:5]]

# Enrich seeds with OpenAlex IDs if missing
print("\n📡 Enriching seeds with OpenAlex IDs...")
discovery = PaperDiscovery(email="kyuwon.shim@ip-korea.org")

for s in seeds:
    if not s.get("openalex_id"):
        doi = s.get("doi", "")
        if doi:
            # Lookup OpenAlex ID by DOI
            try:
                result = discovery.search_by_doi(doi)
                if result:
                    oa_id = result.get("openalex_id", "")
                    if oa_id:
                        s["openalex_id"] = oa_id
                        print(f"  ✓ {doi[:30]} -> {oa_id}")
                    else:
                        print(f"  ✗ {doi[:30]} -> No OpenAlex ID in result")
                else:
                    print(f"  ✗ {doi[:30]} -> Not found in OpenAlex")
            except Exception as e:
                print(f"  ✗ {doi[:30]} -> Error: {e}")

# Save seeds
os.makedirs("/home/kyuwon/projects/papersift/outputs/e004/v3", exist_ok=True)
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/seeds_v3.json", "w") as f:
    json.dump(seeds, f, indent=2, ensure_ascii=False)

print(f"\n✓ Selected {len(seeds)} seeds:")
for i, s in enumerate(seeds, 1):
    year = s.get("year") or s.get("publication_year")
    oa_id = s.get("openalex_id", "MISSING")
    print(f"{i}. [{year}] {s.get('title', '')[:70]}")
    print(f"   Citations: {s.get('cited_by_count', 0)} | DOI: {s.get('doi')}")
    print(f"   OpenAlex: {oa_id}")

print(f"\n✓ Seeds saved to outputs/e004/v3/seeds_v3.json")
