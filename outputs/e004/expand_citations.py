#!/usr/bin/env python3
"""Run expand_citations with multiple text filters and deduplicate results.
Note: Run this script from the papersift directory with: python3 outputs/e004/expand_citations.py
"""
"""Run expand_citations with multiple text filters and deduplicate results."""
import sys
sys.path.insert(0, "/home/kyuwon/projects/tools/paper-pipeline/src")

from paper_pipeline.discovery import PaperDiscovery
import json
import time

# Load seeds
with open("/home/kyuwon/projects/papersift/outputs/e004/seeds.json") as f:
    seeds = json.load(f)

print(f"Loaded {len(seeds)} seed papers")

# Convert DOIs to OpenAlex Work IDs using pyalex
import pyalex
pyalex.config.email = "kyuwon.shim@ip-korea.org"

seed_works = []
for seed in seeds:
    doi = seed["doi"]
    # Query OpenAlex for Work ID
    works = pyalex.Works().filter(doi=doi).get()
    if works and len(works) > 0:
        work = works[0]
        seed_works.append({
            "openalex_id": work["id"],  # expand_citations expects 'openalex_id' field
            "doi": doi,
            "title": seed["title"]
        })
        print(f"  ✓ {doi[:30]}... → {work['id']}")
    else:
        print(f"  ✗ {doi[:30]}... → NOT FOUND")

print(f"\nConverted {len(seed_works)} seeds to OpenAlex Work IDs")

# Initialize discovery
discovery = PaperDiscovery(email="kyuwon.shim@ip-korea.org")

start = time.time()

# Pattern 1: improvement (e002 showed 29.7% recall)
print("\n[1/3] Expanding with 'improvement' pattern...")
results_1 = discovery.expand_citations(
    seed_works, max_per_seed=200,
    text_filter="improves upon OR extends OR enhances OR advances",
    year_min=2015
)
print(f"  → {len(results_1)} papers")

# Pattern 2: method_proposal (e002 showed 26.8% recall)
print("\n[2/3] Expanding with 'method_proposal' pattern...")
results_2 = discovery.expand_citations(
    seed_works, max_per_seed=200,
    text_filter="we propose OR novel method OR new framework OR new approach",
    year_min=2015
)
print(f"  → {len(results_2)} papers")

# Pattern 3: no filter (baseline)
print("\n[3/3] Expanding with no filter...")
results_no_filter = discovery.expand_citations(
    seed_works, max_per_seed=100,
    year_min=2015
)
print(f"  → {len(results_no_filter)} papers")

elapsed = time.time() - start

# Deduplicate across patterns by DOI
seen_dois = set()
all_results = []
for r in results_1 + results_2 + results_no_filter:
    doi = r.get("doi", "").strip().lower()
    if doi and doi not in seen_dois:
        seen_dois.add(doi)
        all_results.append(r)

# Export
with open("/home/kyuwon/projects/papersift/outputs/e004/sota_expand_results.json", "w") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"\n{'='*60}")
print(f"Results: {len(results_1)} + {len(results_2)} + {len(results_no_filter)} = {len(all_results)} unique")
print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
print(f"Saved to: outputs/e004/sota_expand_results.json")
