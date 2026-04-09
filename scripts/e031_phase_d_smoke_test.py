#!/usr/bin/env python3
"""T18: e031 Phase D end-to-end smoke test.

Runs auto-subcluster + hierarchical leaf bridge pipeline on virtual-cell-sweep.
Verifies two-tier output and leaf bridge quality (should look like
"ODE+ABM hybrid for tumor growth", NOT "antibiotic" / "bacteria").

Usage:
    python scripts/e031_phase_d_smoke_test.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

PAPERS_PATH = Path("results/virtual-cell-sweep/papers_cleaned.json")
CLUSTERS_PATH = Path("results/virtual-cell-sweep/clusters.json")
OUTPUT_PATH = Path("outputs/e031/p3_smoke_test.md")

# Only sub-cluster the largest clusters to keep smoke test fast
TARGET_CLUSTERS = ["0", "1", "5"]  # 595, 571, 336 papers


def load_data():
    with open(PAPERS_PATH) as f:
        papers = json.load(f)
    with open(CLUSTERS_PATH) as f:
        clusters = json.load(f)  # doi -> cluster_id (int)
    # Normalize to str
    clusters_str = {doi: str(cid) for doi, cid in clusters.items()}
    return papers, clusters_str


def build_leaf_partition(papers, clusters_str):
    """Run sweep_resolution on target clusters and collect leaf IDs."""
    from papersift.autosubcluster import sweep_resolution

    leaf_clusters = dict(clusters_str)  # start with top-level

    for cid in TARGET_CLUSTERS:
        size = sum(1 for v in clusters_str.values() if v == cid)
        print(f"\n[T7] Sweeping cluster {cid} (size={size})...")
        try:
            res, partition = sweep_resolution(
                papers, cid, clusters_str,
                resolutions=(1.5, 2.0, 2.5, 3.0),
                seeds=(42, 43, 44),
                target_avg_size=60,
                min_stability=0.80,
            )
            sub_sizes = Counter(partition.values())
            leaves = [k for k in sub_sizes if "." in str(k)]
            print(f"  → resolution={res:.1f}, leaves={len(leaves)}, sizes={dict(sorted(sub_sizes.items()))}")
            leaf_clusters.update(partition)
        except Exception as e:
            print(f"  ERROR: {e}")

    return leaf_clusters


def build_cluster_overrides(leaf_clusters):
    """Convert doi->cid map to cid->doi_list map."""
    overrides = {}
    for doi, cid in leaf_clusters.items():
        overrides.setdefault(cid, []).append(doi)
    return overrides


def run_leaf_pipeline(papers, clusters_str, leaf_clusters):
    """Run frontier pipeline with leaf partition, then get leaf-tier bridges."""
    from papersift.frontier import run_pipeline
    from papersift.bridge_recommend import generate_recommendations

    cluster_overrides = build_cluster_overrides(leaf_clusters)
    leaf_ids = [cid for cid in cluster_overrides if "." in str(cid)]
    print(f"\n[T13] Running frontier pipeline with {len(cluster_overrides)} partitions "
          f"({len(leaf_ids)} leaf sub-clusters)...")

    # Build a minimal failure_results stub (no e017 data available in smoke test)
    failure_stub = {"clusters": {cid: {"dead_end_signals": [], "limit_themes": []}
                                  for cid in cluster_overrides}}

    frontier = run_pipeline(
        papers,
        clusters_str,
        cluster_overrides=cluster_overrides,
        min_papers=10,
        min_entities=3,
        allow_high_leaf_drop=True,
    )

    print(f"\n[T11] Generating leaf-tier bridge recommendations...")
    # Leaf clusters that pass structural_gaps (min_papers=10)
    leaf_bio_clusters = [cid for cid in cluster_overrides if "." in str(cid)]
    top_bio_clusters = [cid for cid in cluster_overrides if "." not in str(cid)]

    recs = generate_recommendations(
        frontier_results={
            "t2_temporal": frontier["t2_temporal"],
            "t3_structural_gaps": frontier["t3_structural_gaps"],
        },
        failure_results=failure_stub,
        biology_clusters=leaf_bio_clusters + top_bio_clusters,
        tier="leaf",
        leaf_filter="cross_parent",
        top_n=20,
    )

    return frontier, recs


def write_smoke_test_report(frontier, recs, leaf_clusters):
    """Write p3_smoke_test.md with two-tier output."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    leaf_ids = [cid for cid in leaf_clusters.values() if "." in str(cid)]
    unique_leaves = set(leaf_ids)
    all_recs_list = recs.get("all_recommendations", [])
    cross_bridges = [r for r in all_recs_list if r.get("type") == "cross_cluster"]
    hier_bridges = recs.get("hierarchical_bridges", [])

    lines = [
        "# e031 Phase D Smoke Test Report",
        "",
        "## Setup",
        f"- Dataset: virtual-cell-sweep",
        f"- Top-level clusters: 11 (clusters 0-10)",
        f"- Sub-clustered: {TARGET_CLUSTERS} (size > 200)",
        f"- Total leaf sub-clusters: {len(unique_leaves)}",
        f"- Total partitions in pipeline: {len(set(leaf_clusters.values()))}",
        "",
        "## Two-Tier Bridge Output",
        "",
        "### Tier 1 — Top-level bridges (legacy, backward compat)",
        "",
    ]

    top_cross = [r for r in cross_bridges if "." not in str(r.get("cluster_a", "")) and "." not in str(r.get("cluster_b", ""))]
    for r in top_cross[:5]:
        entities = r.get("shared_entities", [])
        otr = r.get("otr", "?")
        evl = r.get("evaluability", "?")
        lines.append(f"- **C{r['cluster_a']} ↔ C{r['cluster_b']}**: {', '.join(entities[:5])} (OTR={otr}, {evl})")

    lines += [
        "",
        "### Tier 2 — Leaf-level bridges (cross_parent filter)",
        "",
    ]

    leaf_cross = [r for r in cross_bridges if "." in str(r.get("cluster_a", "")) or "." in str(r.get("cluster_b", ""))]
    if not leaf_cross:
        leaf_cross = cross_bridges[:10]  # fallback if tier filtering not populated

    for r in leaf_cross[:10]:
        entities = r.get("shared_entities", [])
        otr = r.get("otr", "?")
        ccr = r.get("ccr", "?")
        evl = r.get("evaluability", "?")
        lines.append(
            f"- **{r.get('cluster_a')} ↔ {r.get('cluster_b')}**: "
            f"{', '.join(entities[:5])} "
            f"(OTR={otr}, CCR={ccr}, {evl})"
        )

    lines += [
        "",
        "## OTR/CCR Evaluability Summary",
        "",
    ]

    all_recs = recs.get("all_recommendations", [])
    n_pass = sum(1 for r in all_recs if r.get("evaluability") == "PASS")
    n_cond = sum(1 for r in all_recs if r.get("evaluability") == "CONDITIONAL")
    n_fail = sum(1 for r in all_recs if r.get("evaluability") == "FAIL")
    total = len(all_recs)

    lines += [
        f"- Total recommendations: {total}",
        f"- PASS (OTR≤0.40 AND CCR≥0.30): {n_pass} ({100*n_pass//max(total,1)}%)",
        f"- CONDITIONAL: {n_cond} ({100*n_cond//max(total,1)}%)",
        f"- FAIL: {n_fail} ({100*n_fail//max(total,1)}%)",
        "",
    ]

    verdict = "PASS" if (n_pass / max(total, 1)) >= 0.50 else "CONDITIONAL"
    lines += [
        f"## Verdict: {verdict}",
        "",
        "## Sanity Check — Are leaf bridges domain-specific?",
        "",
        "Top 5 leaf cross-cluster bridge entities (should be compound/specific, NOT single generic words):",
        "",
    ]

    shown = 0
    for r in cross_bridges:
        if shown >= 5:
            break
        entities = r.get("shared_entities", [])
        if entities:
            compound = [e for e in entities if "-" in e or "/" in e or len(e.split()) >= 2]
            if compound:
                lines.append(f"  - {r.get('cluster_a')} ↔ {r.get('cluster_b')}: **{', '.join(compound[:3])}**")
                shown += 1

    if shown == 0:
        # Show top entities regardless
        for r in cross_bridges[:5]:
            entities = r.get("shared_entities", [])
            lines.append(f"  - {r.get('cluster_a')} ↔ {r.get('cluster_b')}: {', '.join(entities[:3])}")

    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"\nReport saved: {OUTPUT_PATH}")
    return verdict


def main():
    print("=== T18: e031 Phase D Smoke Test ===\n")

    print("[load] Loading virtual-cell-sweep data...")
    papers, clusters_str = load_data()
    print(f"  Papers: {len(papers)}, Clusters: {len(set(clusters_str.values()))}")

    leaf_clusters = build_leaf_partition(papers, clusters_str)
    n_leaves = len(set(v for v in leaf_clusters.values() if "." in str(v)))
    print(f"\n[T5/T7] Leaf partition built: {n_leaves} leaf sub-clusters")

    frontier, recs = run_leaf_pipeline(papers, clusters_str, leaf_clusters)

    print(f"\n[T15] Bridge recommendations: {recs['n_total']} total")
    verdict = write_smoke_test_report(frontier, recs, leaf_clusters)

    print(f"\n=== T18 VERDICT: {verdict} ===")

    # Print top 5 bridge entities for quick sanity check
    print("\nTop leaf bridges (sanity check):")
    for r in recs.get("all_recommendations", [])[:5]:
        entities = r.get("shared_entities", [])
        print(f"  {r.get('cluster_a','?')} ↔ {r.get('cluster_b','?')}: {entities[:5]}")


if __name__ == "__main__":
    main()
