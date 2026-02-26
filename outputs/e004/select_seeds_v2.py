#!/usr/bin/env python3
"""
Select domain-appropriate seeds from existing virtual-cell-sweep clusters.
Target: 5 biology clusters (0,1,3,5,7), 1 seed per cluster.
Criteria: 50-2000 citations, 2015-2022 (openalex_id not required - can lookup by DOI).
"""

import json

# Load data
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    papers = json.load(f)

with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/clusters.json") as f:
    doi_to_cluster = json.load(f)

# Target biology clusters
target_clusters = [0, 1, 3, 5, 7]
cluster_names = {
    0: "in-silico cell modeling",
    1: "whole-cell models",
    3: "neuronal systems",
    5: "cellular mechanics",
    7: "immunology"
}

# Build cluster → papers mapping
cluster_papers = {c: [] for c in target_clusters}
for paper in papers:
    doi = paper.get("doi", "").strip().lower()
    cluster_id = doi_to_cluster.get(doi)
    if cluster_id in target_clusters:
        year = paper.get("year") or paper.get("publication_year") or 0
        citations = paper.get("cited_by_count", 0)

        # Relaxed filters: just citations and year (DOI can be used to lookup openalex_id)
        if 50 <= citations <= 2000 and 2015 <= year <= 2022:
            cluster_papers[cluster_id].append(paper)

# Select top-cited from each cluster
seeds = []
for cluster_id in target_clusters:
    candidates = cluster_papers[cluster_id]
    if not candidates:
        print(f"⚠️  Cluster {cluster_id} ({cluster_names[cluster_id]}): No candidates found")
        continue

    # Sort by citations descending
    candidates.sort(key=lambda x: x.get("cited_by_count", 0), reverse=True)
    seed = candidates[0]
    seeds.append(seed)

    print(f"✓ Cluster {cluster_id} ({cluster_names[cluster_id]}):")
    print(f"  {seed['title'][:80]}...")
    print(f"  Year={seed.get('year', seed.get('publication_year'))}, Citations={seed.get('cited_by_count', 0)}")
    print(f"  DOI={seed['doi']}")
    print()

# Save seeds
output_path = "/home/kyuwon/projects/papersift/outputs/e004/seeds_v2.json"
with open(output_path, "w") as f:
    json.dump(seeds, f, indent=2, ensure_ascii=False)

print(f"Selected {len(seeds)}/5 seeds → {output_path}")
