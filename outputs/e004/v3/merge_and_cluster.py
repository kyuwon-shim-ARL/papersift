#!/usr/bin/env python3
"""Step 3: Merge sweep + v3 results and cluster."""

import json
import os

# Load existing sweep
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    sweep = json.load(f)

# Load v3 results
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/sota_expand_v3.json") as f:
    sota = json.load(f)

print(f"Sweep: {len(sweep)} papers")
print(f"SOTA v3: {len(sota)} papers")

# Normalize DOIs for comparison
def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip().lower()
    # Remove URL prefix if present
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    elif doi.startswith("http://doi.org/"):
        doi = doi[15:]
    return doi

# Build sweep DOI set
sweep_dois = {normalize_doi(p.get("doi", "")) for p in sweep if p.get("doi")}
sweep_dois.discard("")

print(f"Sweep unique DOIs: {len(sweep_dois)}")

# Find new papers
new_papers = []
for p in sota:
    doi = normalize_doi(p.get("doi", ""))
    if doi and doi not in sweep_dois:
        new_papers.append(p)

print(f"New papers from v3: {len(new_papers)}")

# Merge
combined = sweep + new_papers

print(f"Combined: {len(combined)} papers")

# Save combined
os.makedirs("/home/kyuwon/projects/papersift/outputs/e004/v3", exist_ok=True)
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/combined_v3.json", "w") as f:
    json.dump(combined, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved to outputs/e004/v3/combined_v3.json")
print(f"\nNext: Run clustering with:")
print(f"  cd /home/kyuwon/projects/papersift")
print(f"  .venv/bin/python -m papersift cluster outputs/e004/v3/combined_v3.json -o outputs/e004/v3/")
