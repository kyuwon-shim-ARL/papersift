#!/usr/bin/env python3
"""
Measure cluster stability by comparing baseline vs v2 clustering.
Only measure stability for the 3,070 papers present in both datasets.
"""

import json
from pathlib import Path
from collections import Counter

# Load baseline clustering
baseline_clusters_path = Path("/home/kyuwon/projects/papersift/results/virtual-cell-sweep/clusters.json")
with open(baseline_clusters_path) as f:
    baseline_clusters = json.load(f)

# Load v2 clustering
v2_clusters_path = Path("/home/kyuwon/projects/papersift/outputs/e004/v2/clusters.json")
with open(v2_clusters_path) as f:
    v2_clusters = json.load(f)

# Get baseline DOIs (3,070 papers)
baseline_dois = set(baseline_clusters.keys())
print(f"Baseline: {len(baseline_dois)} papers, {len(set(baseline_clusters.values()))} clusters")
print(f"V2: {len(v2_clusters)} papers, {len(set(v2_clusters.values()))} clusters")

# Calculate stability: % of baseline papers that stayed in same cluster
matched = 0
for doi in baseline_dois:
    if doi in v2_clusters:
        if baseline_clusters[doi] == v2_clusters[doi]:
            matched += 1

stability = matched / len(baseline_dois) * 100
print(f"\nCluster Stability: {stability:.1f}% ({matched}/{len(baseline_dois)})")

# Analyze cluster fragmentation
baseline_cluster_counts = Counter(baseline_clusters.values())
v2_cluster_counts = Counter(v2_clusters.values())

print(f"\nCluster size distribution:")
print(f"  Baseline - largest: {max(baseline_cluster_counts.values())}, median: {sorted(baseline_cluster_counts.values())[len(baseline_cluster_counts)//2]}")
print(f"  V2 - largest: {max(v2_cluster_counts.values())}, median: {sorted(v2_cluster_counts.values())[len(v2_cluster_counts)//2]}")

# Track cluster migrations for baseline papers
baseline_to_v2_mapping = {}
for doi in baseline_dois:
    if doi in v2_clusters:
        baseline_c = baseline_clusters[doi]
        v2_c = v2_clusters[doi]
        key = (baseline_c, v2_c)
        baseline_to_v2_mapping[key] = baseline_to_v2_mapping.get(key, 0) + 1

print(f"\nTop 10 cluster migrations (baseline → v2):")
for (bc, vc), count in sorted(baseline_to_v2_mapping.items(), key=lambda x: x[1], reverse=True)[:10]:
    if bc == vc:
        print(f"  C{bc} → C{vc}: {count} papers (stable)")
    else:
        print(f"  C{bc} → C{vc}: {count} papers (migrated)")

# Save stability report
report = {
    "baseline_papers": len(baseline_dois),
    "v2_papers": len(v2_clusters),
    "new_papers": len(v2_clusters) - len(baseline_dois),
    "baseline_clusters": len(set(baseline_clusters.values())),
    "v2_clusters": len(set(v2_clusters.values())),
    "stability_pct": round(stability, 1),
    "matched_papers": matched
}

report_path = Path("/home/kyuwon/projects/papersift/outputs/e004/stability_v2.json")
with open(report_path, "w") as f:
    json.dump(report, f, indent=2)

print(f"\n✓ Saved to: {report_path}")
