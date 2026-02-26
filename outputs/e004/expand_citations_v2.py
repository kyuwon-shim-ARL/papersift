#!/usr/bin/env python3
"""
Expand citations from domain-appropriate seeds.
Uses paper-pipeline to fetch citing papers (forward citations).
"""

import sys
import json
import time
from pathlib import Path

# Add paper-pipeline to path
sys.path.insert(0, "/home/kyuwon/projects/tools/paper-pipeline/src")

from paper_pipeline.discovery import PaperDiscovery

# Load enriched seeds (with OpenAlex IDs)
seeds_path = Path("/home/kyuwon/projects/papersift/outputs/e004/seeds_v2_enriched.json")
with open(seeds_path) as f:
    seeds = json.load(f)

print(f"Loaded {len(seeds)} seed papers")
for i, seed in enumerate(seeds, 1):
    print(f"  {i}. {seed['title'][:60]}... (citations={seed['cited_by_count']})")
print()

# Initialize discovery
discovery = PaperDiscovery(email="kyuwon.shim@ip-korea.org")

# Expand citations (100 per seed, no strict filters)
print("Expanding citations (max 100 per seed, year_min=2015)...")
start = time.time()

results = discovery.expand_citations(
    seeds,
    max_per_seed=100,
    year_min=2015
)

elapsed = time.time() - start

# Save results
output_path = Path("/home/kyuwon/projects/papersift/outputs/e004/sota_expand_v2.json")
with open(output_path, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n✓ Collected {len(results)} citing papers in {elapsed:.1f}s")
print(f"  Saved to: {output_path}")

# Show per-seed breakdown
seed_dois = {s['doi'].lower() for s in seeds}
citing_counts = {}
for paper in results:
    refs = paper.get('referenced_works', [])
    for ref in refs:
        ref_doi = ref.lower().replace('https://doi.org/', '')
        if ref_doi in seed_dois:
            citing_counts[ref_doi] = citing_counts.get(ref_doi, 0) + 1

print(f"\nCitations per seed:")
for seed in seeds:
    doi = seed['doi'].lower()
    count = citing_counts.get(doi, 0)
    print(f"  {doi}: {count} citing papers")
