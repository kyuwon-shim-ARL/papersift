#!/usr/bin/env python3
"""Step 4: Measure cluster stability (co-clustering preservation)."""

import json
import os

def normalize_doi(doi):
    """Normalize DOI for consistent matching."""
    if not doi:
        return ""
    doi = doi.strip().lower()
    # Remove URL prefix if present
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    elif doi.startswith("http://doi.org/"):
        doi = doi[15:]
    return doi

# Load baseline clusters (sweep)
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/clusters.json") as f:
    baseline_clusters = json.load(f)

# Load baseline papers to get normalized DOIs
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/papers_cleaned.json") as f:
    baseline_papers = json.load(f)

# Load new clusters (v3)
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/clusters.json") as f:
    new_clusters = json.load(f)

# Load new papers
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/combined_v3.json") as f:
    new_papers = json.load(f)

print("=== Stability Measurement ===\n")

# Build normalized DOI mappings
baseline_doi_map = {}
for p in baseline_papers:
    raw_doi = p.get("doi", "")
    if raw_doi:
        norm_doi = normalize_doi(raw_doi)
        baseline_doi_map[norm_doi] = raw_doi

new_doi_map = {}
for p in new_papers:
    raw_doi = p.get("doi", "")
    if raw_doi:
        norm_doi = normalize_doi(raw_doi)
        new_doi_map[norm_doi] = raw_doi

print(f"Baseline papers: {len(baseline_papers)}")
print(f"Baseline unique normalized DOIs: {len(baseline_doi_map)}")
print(f"New papers: {len(new_papers)}")
print(f"New unique normalized DOIs: {len(new_doi_map)}")

# Find papers present in both datasets
common_norm_dois = set(baseline_doi_map.keys()) & set(new_doi_map.keys())
print(f"\nCommon papers (by normalized DOI): {len(common_norm_dois)}")

if len(common_norm_dois) < 100:
    print("\n⚠️  WARNING: Very few common papers found!")
    print("    This suggests DOI normalization may still have issues.")
    print("\nSample baseline cluster keys:")
    for i, key in enumerate(list(baseline_clusters.keys())[:5]):
        print(f"  {i+1}. {key}")
    print("\nSample new cluster keys:")
    for i, key in enumerate(list(new_clusters.keys())[:5]):
        print(f"  {i+1}. {key}")

# Build reverse lookup: normalized DOI -> cluster ID
baseline_norm_to_cluster = {}
for norm_doi in common_norm_dois:
    raw_doi = baseline_doi_map[norm_doi]
    # Try to find this raw DOI in baseline_clusters
    if raw_doi in baseline_clusters:
        baseline_norm_to_cluster[norm_doi] = baseline_clusters[raw_doi]
    else:
        # Try normalized version
        norm_key = normalize_doi(raw_doi)
        for cluster_key in baseline_clusters.keys():
            if normalize_doi(cluster_key) == norm_key:
                baseline_norm_to_cluster[norm_doi] = baseline_clusters[cluster_key]
                break

new_norm_to_cluster = {}
for norm_doi in common_norm_dois:
    raw_doi = new_doi_map[norm_doi]
    if raw_doi in new_clusters:
        new_norm_to_cluster[norm_doi] = new_clusters[raw_doi]
    else:
        norm_key = normalize_doi(raw_doi)
        for cluster_key in new_clusters.keys():
            if normalize_doi(cluster_key) == norm_key:
                new_norm_to_cluster[norm_doi] = new_clusters[cluster_key]
                break

matched_papers = set(baseline_norm_to_cluster.keys()) & set(new_norm_to_cluster.keys())
print(f"Matched papers (in both cluster files): {len(matched_papers)}")

if len(matched_papers) < 100:
    print("\n⚠️  WARNING: Very few matched papers!")
    print("    Cannot compute reliable stability metric.")
    print("\nExiting early.")
    exit(1)

# Measure co-clustering preservation
# For each pair of papers that were in the same cluster in baseline,
# check if they're still in the same cluster in new

# Build baseline co-cluster pairs
baseline_pairs = set()
baseline_by_cluster = {}
for doi, cluster_id in baseline_norm_to_cluster.items():
    if doi in matched_papers:
        if cluster_id not in baseline_by_cluster:
            baseline_by_cluster[cluster_id] = []
        baseline_by_cluster[cluster_id].append(doi)

for cluster_id, dois in baseline_by_cluster.items():
    for i, doi1 in enumerate(dois):
        for doi2 in dois[i+1:]:
            baseline_pairs.add(tuple(sorted([doi1, doi2])))

print(f"\nBaseline co-cluster pairs: {len(baseline_pairs)}")

# Check preservation
preserved = 0
for doi1, doi2 in baseline_pairs:
    cluster1 = new_norm_to_cluster.get(doi1)
    cluster2 = new_norm_to_cluster.get(doi2)
    if cluster1 is not None and cluster1 == cluster2:
        preserved += 1

stability = (preserved / len(baseline_pairs) * 100) if baseline_pairs else 0

print(f"Preserved co-cluster pairs: {preserved}")
print(f"\n✓ Stability: {stability:.1f}%")

# Cluster distribution
print("\n=== Cluster Distribution ===")
print("\nBaseline:")
baseline_cluster_counts = {}
for cluster_id in baseline_norm_to_cluster.values():
    baseline_cluster_counts[cluster_id] = baseline_cluster_counts.get(cluster_id, 0) + 1
for cluster_id in sorted(baseline_cluster_counts.keys()):
    print(f"  Cluster {cluster_id}: {baseline_cluster_counts[cluster_id]} papers")

print("\nNew (v3):")
new_cluster_counts = {}
for cluster_id in new_norm_to_cluster.values():
    new_cluster_counts[cluster_id] = new_cluster_counts.get(cluster_id, 0) + 1
for cluster_id in sorted(new_cluster_counts.keys()):
    print(f"  Cluster {cluster_id}: {new_cluster_counts[cluster_id]} papers")

# Save results
results = {
    "baseline_papers": len(baseline_papers),
    "new_papers": len(new_papers),
    "common_papers": len(common_norm_dois),
    "matched_papers": len(matched_papers),
    "baseline_pairs": len(baseline_pairs),
    "preserved_pairs": preserved,
    "stability_percent": round(stability, 1),
    "baseline_clusters": len(baseline_cluster_counts),
    "new_clusters": len(new_cluster_counts)
}

os.makedirs("/home/kyuwon/projects/papersift/outputs/e004/v3", exist_ok=True)
with open("/home/kyuwon/projects/papersift/outputs/e004/v3/stability_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n✓ Results saved to outputs/e004/v3/stability_results.json")
