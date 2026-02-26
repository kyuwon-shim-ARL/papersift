#!/usr/bin/env python3
"""
Look up OpenAlex IDs for seed papers using their DOIs.
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, "/home/kyuwon/projects/tools/paper-pipeline/src")
import pyalex
from pyalex import Works

# Configure PyAlex
pyalex.config.email = "kyuwon.shim@ip-korea.org"

# Load seeds
seeds_path = Path("/home/kyuwon/projects/papersift/outputs/e004/seeds_v2.json")
with open(seeds_path) as f:
    seeds = json.load(f)

print(f"Looking up OpenAlex IDs for {len(seeds)} seeds...")

enriched_seeds = []
for i, seed in enumerate(seeds, 1):
    doi = seed['doi']
    print(f"{i}. {doi[:30]}...", end=" ")

    try:
        # Query OpenAlex by DOI
        results = Works().filter(doi=doi).get()

        if results and len(results) > 0:
            work = results[0]
            seed['openalex_id'] = work['id']
            # Also update other fields if available
            if 'cited_by_count' in work:
                seed['cited_by_count'] = work['cited_by_count']
            print(f"✓ {work['id']}")
            enriched_seeds.append(seed)
        else:
            print(f"✗ Not found in OpenAlex")
            enriched_seeds.append(seed)  # Keep anyway

        time.sleep(0.1)  # Rate limiting

    except Exception as e:
        print(f"✗ Error: {e}")
        enriched_seeds.append(seed)  # Keep anyway

# Save enriched seeds
output_path = Path("/home/kyuwon/projects/papersift/outputs/e004/seeds_v2_enriched.json")
with open(output_path, "w") as f:
    json.dump(enriched_seeds, f, indent=2, ensure_ascii=False)

found = sum(1 for s in enriched_seeds if s.get('openalex_id'))
print(f"\n✓ Found OpenAlex IDs for {found}/{len(seeds)} seeds")
print(f"  Saved to: {output_path}")
