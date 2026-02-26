#!/usr/bin/env python3
"""Measure cluster stability by comparing old vs new cluster assignments."""
import json
from collections import defaultdict
from itertools import combinations

# Load old cluster assignments (baseline)
# Format: {doi: cluster_id}
with open("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/clusters.json") as f:
    old_doi_to_cluster = json.load(f)

# Load new cluster assignments (hybrid)
with open("/home/kyuwon/projects/papersift/outputs/e004/clusters.json") as f:
    new_doi_to_cluster = json.load(f)

print(f"Old clusters: {len(old_doi_to_cluster)} papers")
print(f"New clusters: {len(new_doi_to_cluster)} papers")

# Normalize DOIs to lowercase
old_doi_to_cluster = {doi.strip().lower(): cid for doi, cid in old_doi_to_cluster.items()}
new_doi_to_cluster = {doi.strip().lower(): cid for doi, cid in new_doi_to_cluster.items()}

# Find common papers (papers in both datasets)
common_dois = set(old_doi_to_cluster.keys()) & set(new_doi_to_cluster.keys())
print(f"Common papers: {len(common_dois)}")

# Build old clusters (DOI sets)
old_cluster_members = defaultdict(set)
for doi in common_dois:
    old_cluster_members[old_doi_to_cluster[doi]].add(doi)

# Build new clusters (DOI sets)
new_cluster_members = defaultdict(set)
for doi in common_dois:
    new_cluster_members[new_doi_to_cluster[doi]].add(doi)

print(f"\nOld: {len(old_cluster_members)} clusters")
print(f"New: {len(new_cluster_members)} clusters")

# Measure co-clustering preservation
# Method: for each old cluster, check what % of paper pairs remain together in new clustering
results = []
for old_cid, old_members in old_cluster_members.items():
    if len(old_members) < 2:
        continue

    # Generate all paper pairs
    pairs = list(combinations(old_members, 2))
    preserved = 0
    for doi1, doi2 in pairs:
        # Check if they're still in the same cluster
        if new_doi_to_cluster[doi1] == new_doi_to_cluster[doi2]:
            preserved += 1

    preservation_rate = preserved / len(pairs) if pairs else 0
    results.append({
        "old_cluster_id": old_cid,
        "size": len(old_members),
        "pairs": len(pairs),
        "preserved_pairs": preserved,
        "preservation_rate": preservation_rate
    })

# Sort by size descending
results.sort(key=lambda x: x["size"], reverse=True)

# Overall statistics
total_pairs = sum(r["pairs"] for r in results)
total_preserved = sum(r["preserved_pairs"] for r in results)
overall_preservation = total_preserved / total_pairs if total_pairs else 0

print(f"\n{'='*60}")
print(f"CLUSTER STABILITY ANALYSIS")
print(f"{'='*60}")
print(f"Overall preservation rate: {overall_preservation*100:.1f}%")
print(f"  (fraction of paper pairs that remain co-clustered)")
print(f"Total pairs analyzed: {total_pairs}")
print(f"Preserved pairs: {total_preserved}")

# Show top 10 largest old clusters
print(f"\nTop 10 Largest Old Clusters:")
print(f"{'Old ID':<8} {'Size':<6} {'Pairs':<8} {'Preserved':<10} {'Rate':<8}")
print("-" * 60)
for r in results[:10]:
    print(f"{r['old_cluster_id']:<8} {r['size']:<6} {r['pairs']:<8} {r['preserved_pairs']:<10} {r['preservation_rate']*100:>6.1f}%")

# Show clusters with low preservation (<50%)
unstable = [r for r in results if r["preservation_rate"] < 0.5 and r["size"] >= 10]
if unstable:
    print(f"\nUnstable Clusters (preservation < 50%, size >= 10):")
    print(f"{'Old ID':<8} {'Size':<6} {'Pairs':<8} {'Preserved':<10} {'Rate':<8}")
    print("-" * 60)
    for r in unstable:
        print(f"{r['old_cluster_id']:<8} {r['size']:<6} {r['pairs']:<8} {r['preserved_pairs']:<10} {r['preservation_rate']*100:>6.1f}%")

# Save detailed results
with open("/home/kyuwon/projects/papersift/outputs/e004/stability_analysis.json", "w") as f:
    json.dump({
        "overall_preservation_rate": overall_preservation,
        "total_pairs": total_pairs,
        "preserved_pairs": total_preserved,
        "common_papers": len(common_dois),
        "old_clusters": len(old_cluster_members),
        "new_clusters": len(new_cluster_members),
        "per_cluster_results": results
    }, f, indent=2)

print(f"\nDetailed results saved to: outputs/e004/stability_analysis.json")
