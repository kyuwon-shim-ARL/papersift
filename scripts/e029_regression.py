#!/usr/bin/env python3
"""e029 T3: virtual-cell regression test — verify Phase 0-4 changes don't break existing clustering."""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from collections import defaultdict
from papersift.entity_layer import EntityLayerBuilder

DATA = "results/virtual-cell/papers_with_abstracts.json"
BASELINE_CLUSTERS = "results/virtual-cell/clusters.json"
OUTPUT = "outputs/e029/t3_regression_snapshot.json"
SEED = 42
RESOLUTION = 1.0
BASELINE_N_CLUSTERS = 7
ALLOWED_DELTA = 2  # ±2
MAX_REASSIGNMENT_PCT = 15.0
MIN_MAJOR_CLUSTERS = 5  # size >= 10


def main():
    # Load papers
    with open(DATA) as f:
        papers = json.load(f)
    print(f"Loaded {len(papers)} papers")

    # Load baseline clusters for reassignment comparison
    baseline_clusters = None
    if os.path.exists(BASELINE_CLUSTERS):
        with open(BASELINE_CLUSTERS) as f:
            baseline_data = json.load(f)
        if isinstance(baseline_data, dict) and "clusters" in baseline_data:
            baseline_clusters = baseline_data["clusters"]
        elif isinstance(baseline_data, list):
            # List of cluster summaries
            baseline_clusters = {}
            for cluster in baseline_data:
                cid = cluster.get("cluster_id", cluster.get("id"))
                for doi in cluster.get("dois", cluster.get("papers", [])):
                    baseline_clusters[doi] = cid

    # Run clustering with current code (Phase 0-4 applied)
    builder = EntityLayerBuilder(use_topics=True)
    builder.build_from_papers(papers)
    new_clusters = builder.run_leiden(resolution=RESOLUTION, seed=SEED)

    # Metrics
    cluster_sizes = defaultdict(int)
    for cid in new_clusters.values():
        cluster_sizes[cid] += 1

    n_clusters = len(cluster_sizes)
    singletons = sum(1 for s in cluster_sizes.values() if s == 1)
    major_clusters = sum(1 for s in cluster_sizes.values() if s >= 10)

    # Cluster count check
    cluster_count_pass = abs(n_clusters - BASELINE_N_CLUSTERS) <= ALLOWED_DELTA
    cluster_range = f"{BASELINE_N_CLUSTERS - ALLOWED_DELTA}-{BASELINE_N_CLUSTERS + ALLOWED_DELTA}"

    # Major cluster check
    major_pass = major_clusters >= MIN_MAJOR_CLUSTERS

    # Paper reassignment check
    reassignment_pct = 0.0
    reassigned_count = 0
    if baseline_clusters:
        common_dois = set(new_clusters.keys()) & set(baseline_clusters.keys())
        if common_dois:
            # Map baseline cluster IDs to new cluster IDs by majority vote
            from collections import Counter
            baseline_to_new = defaultdict(list)
            for doi in common_dois:
                baseline_to_new[baseline_clusters[doi]].append(new_clusters[doi])

            # Best mapping: for each baseline cluster, the most common new cluster
            mapping = {}
            for b_cid, new_cids in baseline_to_new.items():
                most_common = Counter(new_cids).most_common(1)[0][0]
                mapping[b_cid] = most_common

            # Count reassignments
            for doi in common_dois:
                expected = mapping.get(baseline_clusters[doi])
                if new_clusters[doi] != expected:
                    reassigned_count += 1

            reassignment_pct = reassigned_count / len(common_dois) * 100
    reassignment_pass = reassignment_pct <= MAX_REASSIGNMENT_PCT

    # Overall verdict
    all_pass = cluster_count_pass and major_pass and reassignment_pass
    verdict = "PASS" if all_pass else "FAIL"

    results = {
        "experiment": "e029-T3",
        "dataset": DATA,
        "n_papers": len(papers),
        "seed": SEED,
        "resolution": RESOLUTION,
        "baseline_n_clusters": BASELINE_N_CLUSTERS,
        "new_n_clusters": n_clusters,
        "cluster_count_check": {
            "expected_range": cluster_range,
            "actual": n_clusters,
            "pass": cluster_count_pass,
        },
        "major_clusters_check": {
            "required": MIN_MAJOR_CLUSTERS,
            "actual": major_clusters,
            "pass": major_pass,
        },
        "reassignment_check": {
            "max_allowed_pct": MAX_REASSIGNMENT_PCT,
            "actual_pct": round(reassignment_pct, 2),
            "reassigned_papers": reassigned_count,
            "pass": reassignment_pass,
        },
        "singletons": singletons,
        "cluster_sizes": dict(sorted(
            {str(k): v for k, v in cluster_sizes.items()}.items(),
            key=lambda x: -x[1]
        )),
        "verdict": verdict,
    }

    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nVERDICT: {verdict}")
    print(f"  Clusters: {n_clusters} (baseline {BASELINE_N_CLUSTERS}, range {cluster_range}) — {'PASS' if cluster_count_pass else 'FAIL'}")
    print(f"  Major clusters (>=10): {major_clusters} (need >={MIN_MAJOR_CLUSTERS}) — {'PASS' if major_pass else 'FAIL'}")
    print(f"  Reassignment: {reassignment_pct:.1f}% (max {MAX_REASSIGNMENT_PCT}%) — {'PASS' if reassignment_pass else 'FAIL'}")
    print(f"  Singletons: {singletons}")
    print(f"Results saved to {OUTPUT}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
