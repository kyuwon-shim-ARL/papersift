#!/usr/bin/env python3
"""Merge sweep results with sota-expand results."""
import json

# Load existing sweep results
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    sweep = json.load(f)

# Load sota-expand results
with open("/home/kyuwon/projects/papersift/outputs/e004/sota_expand_results.json") as f:
    sota = json.load(f)

print(f"Sweep: {len(sweep)} papers")
print(f"SOTA-expand: {len(sota)} papers")

# Build DOI set from sweep (normalize to lowercase)
sweep_dois = {p.get("doi", "").strip().lower() for p in sweep if p.get("doi")}
print(f"Sweep DOIs: {len(sweep_dois)}")

# Filter new papers from sota-expand
new_papers = []
for p in sota:
    doi = p.get("doi", "").strip().lower()
    if doi and doi not in sweep_dois:
        new_papers.append(p)

print(f"New papers from SOTA-expand: {len(new_papers)}")

# Combine
combined = sweep + new_papers

# Save
with open("/home/kyuwon/projects/papersift/outputs/e004/combined.json", "w") as f:
    json.dump(combined, f, indent=2, ensure_ascii=False)

print(f"\nCombined: {len(combined)} papers")
print(f"New paper rate: {len(new_papers)/len(sota)*100:.1f}% of sota-expand results are new")
print(f"Saved to: outputs/e004/combined.json")
