#!/usr/bin/env python3
"""
Merge sweep + sota_expand_v2, then cluster.
"""

import json
from pathlib import Path

# Load datasets
sweep_path = Path("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json")
sota_path = Path("/home/kyuwon/projects/papersift/outputs/e004/sota_expand_v2.json")

with open(sweep_path) as f:
    sweep_papers = json.load(f)

with open(sota_path) as f:
    sota_papers = json.load(f)

print(f"Sweep: {len(sweep_papers)} papers")
print(f"SOTA expand: {len(sota_papers)} papers")

# Merge by DOI
doi_to_paper = {}
for paper in sweep_papers:
    doi = paper.get('doi', '').strip().lower()
    if doi:
        doi_to_paper[doi] = paper

added = 0
for paper in sota_papers:
    doi = paper.get('doi', '').strip().lower()
    if doi and doi not in doi_to_paper:
        doi_to_paper[doi] = paper
        added += 1

combined = list(doi_to_paper.values())
print(f"\nCombined: {len(combined)} papers ({added} new from SOTA)")

# Save
output_path = Path("/home/kyuwon/projects/papersift/outputs/e004/combined_v2.json")
with open(output_path, "w") as f:
    json.dump(combined, f, indent=2, ensure_ascii=False)

print(f"✓ Saved to: {output_path}")
