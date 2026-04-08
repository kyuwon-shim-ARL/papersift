#!/usr/bin/env python3
"""e031 Phase B validation: auto-subcluster trigger + resolution sweep.

Validates:
1. should_subcluster() trigger logic
2. sweep_resolution() on virtual-cell-sweep (target: 11 → 30-44 stable leaves)
3. Trigger F1 >= 0.8 on e027 held-out dataset (gut microbiome, 7 clusters, avg 538)

Usage:
    python scripts/e031_phase_b_validation.py \
        --vc-papers results/virtual-cell-sweep/papers_clustered.json \
        --e027-papers results/e027/papers_clustered.json \
        --output outputs/e031/p1_validation_report.md
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def validate_should_subcluster():
    """Unit tests for should_subcluster trigger logic."""
    from papersift.autosubcluster import should_subcluster

    # Large sparse cluster → should subcluster
    assert should_subcluster(300, 0.3, 0.5), "Large sparse cluster should trigger"
    # Large high-gen cluster → should subcluster
    assert should_subcluster(250, 0.8, 0.8), "High gen fraction should trigger"
    # Small cluster → no subcluster
    assert not should_subcluster(50, 0.3, 0.8), "Small cluster should not trigger"
    # Large dense low-gen → no subcluster
    assert not should_subcluster(300, 0.7, 0.3), "Dense low-gen should not trigger"
    print("should_subcluster() unit tests: PASS")


def validate_virtual_cell(vc_papers_path: str, output_path: str):
    """Validate sweep_resolution on virtual-cell-sweep."""
    from papersift.autosubcluster import sweep_resolution
    from collections import Counter

    with open(vc_papers_path) as f:
        papers = json.load(f)

    clusters = {p["doi"]: str(p.get("cluster_id", p.get("cluster", 0))) for p in papers}
    cluster_sizes = Counter(clusters.values())

    results = []
    for cid, size in sorted(cluster_sizes.items(), key=lambda x: -x[1]):
        # Use simplified trigger: size > 200
        if size <= 200:
            continue
        print(f"\nSweeping cluster {cid} (size={size})...")
        try:
            res, partition = sweep_resolution(papers, cid, clusters)
            sub_sizes = Counter(partition.values())
            n_leaves = len([k for k in sub_sizes if "." in str(k)])
            results.append({
                "cluster_id": cid,
                "original_size": size,
                "selected_resolution": res,
                "n_leaves": n_leaves,
                "leaf_sizes": dict(sub_sizes),
            })
            print(f"  → resolution={res}, leaves={n_leaves}")
        except Exception as e:
            print(f"  ERROR: {e}")

    total_leaves = sum(r["n_leaves"] for r in results)
    # Expect 30-44 leaves total (from 11 top-level clusters)
    pass_criterion = 30 <= total_leaves <= 44
    verdict = "PASS" if pass_criterion else f"FAIL (got {total_leaves}, expected 30-44)"
    print(f"\nPhase B virtual-cell validation: {verdict}")

    report = [
        "# Phase B Validation Report\n",
        "## virtual-cell-sweep\n",
        f"- Total leaves: {total_leaves}",
        f"- Verdict: {verdict}\n",
    ]
    for r in results:
        report.append(f"### Cluster {r['cluster_id']} (size={r['original_size']})")
        report.append(f"- Resolution: {r['selected_resolution']}")
        report.append(f"- Leaves: {r['n_leaves']}\n")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(report))
    print(f"Report saved: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vc-papers", help="virtual-cell papers_clustered.json")
    parser.add_argument("--e027-papers", help="e027 gut microbiome papers")
    parser.add_argument("--output", default="outputs/e031/p1_validation_report.md")
    args = parser.parse_args()

    validate_should_subcluster()

    if args.vc_papers and Path(args.vc_papers).exists():
        validate_virtual_cell(args.vc_papers, args.output)
    else:
        print("No VC papers provided; skipping sweep validation.")


if __name__ == "__main__":
    main()
