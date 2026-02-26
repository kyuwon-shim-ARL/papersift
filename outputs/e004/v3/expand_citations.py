#!/usr/bin/env python3
"""Step 2: Expand citations with domain text filter.

IMPORTANT: Run with system python3, NOT venv:
  python3 /home/kyuwon/projects/papersift/outputs/e004/v3/expand_citations.py
"""
"""Step 2: Expand citations with domain text filter."""

import sys
import json
import time
import os

# Add paper-pipeline to path
sys.path.insert(0, "/home/kyuwon/projects/tools/paper-pipeline/src")
from paper_pipeline.discovery import PaperDiscovery

# Load seeds
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/seeds_v3.json") as f:
    seeds = json.load(f)

print(f"Loaded {len(seeds)} seeds")
for i, s in enumerate(seeds, 1):
    print(f"{i}. [{s.get('year')}] {s.get('title', '')[:70]}")

# Initialize discovery
discovery = PaperDiscovery(email="kyuwon.shim@ip-korea.org")

# Domain text filter: virtual cell related terms
domain_filter = "cell model OR cell simulation OR whole-cell OR in silico OR computational biology OR systems biology"

print(f"\nDomain filter: {domain_filter}")
print(f"Expanding citations (max 200 per seed, year >= 2010)...\n")

start = time.time()

# Expand with domain filter
results = discovery.expand_citations(
    seeds,
    max_per_seed=200,
    text_filter=domain_filter,
    year_min=2010
)

elapsed = time.time() - start

# Save results
os.makedirs("/home/kyuwon/projects/papersift/outputs/e004/v3", exist_ok=True)
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/sota_expand_v3.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n✓ Domain-filtered results: {len(results)} papers in {elapsed:.1f}s")
print(f"✓ Saved to outputs/e004/v3/sota_expand_v3.json")
