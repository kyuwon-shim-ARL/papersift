"""Bridge recommendation: combine temporal + structural gaps + failure signals.

Refactored from scripts/e018_bridge_recommendation.py for use as CLI subcommand.
"""

# Default cluster labels; callers may override via cluster_labels parameter
DEFAULT_CLUSTER_LABELS = {
    "0": "in-silico/pharmacology",
    "1": "whole-cell/systems-biology",
    "2": "telecom/V2X",
    "3": "neuro/electrophysiology",
    "4": "digital-twin/manufacturing",
    "5": "mechanics/ABM",
    "6": "fuel-cells/energy",
    "7": "immunology",
}

DEFAULT_BIOLOGY_CLUSTERS = {"0", "1", "3", "5", "7"}


def _compute_momentum_scores(t2_data: dict) -> dict:
    scores = {}
    for cid, cdata in t2_data["clusters"].items():
        scores[cid] = {
            "momentum": cdata["momentum_score"],
            "rising": [e["entity"] for e in cdata.get("top_rising", [])],
            "declining": [e["entity"] for e in cdata.get("top_declining", [])],
            "n_significant": cdata["significant"],
        }
    return scores


def _compute_gap_scores(t3_data: dict) -> dict:
    intra_gaps = {cid: gaps for cid, gaps in t3_data["intra_cluster_gaps"].items()}
    bridges = [
        {
            "cluster_a": str(b["cluster_a"]),
            "cluster_b": str(b["cluster_b"]),
            "jaccard": b["entity_jaccard"],
            "shared_entities": b["shared_entities"][:10],
            "shared_count": b.get("shared_count", len(b.get("shared_entities", []))),
        }
        for b in t3_data["cross_cluster_bridges"]
    ]
    return {"intra_gaps": intra_gaps, "bridges": bridges}


def _compute_failure_penalties(e017_data: dict) -> dict:
    penalties = {}
    for cid, cdata in e017_data.get("clusters", {}).items():
        n_dead = len(cdata.get("dead_end_signals", []))
        n_themes = len(cdata.get("limit_themes", []))
        penalty = n_dead / (n_dead + n_themes + 1)
        penalties[cid] = {
            "penalty": round(penalty, 4),
            "n_dead_ends": n_dead,
            "n_themes": n_themes,
            "dead_end_keywords": [d["theme_label"] for d in cdata.get("dead_end_signals", [])],
        }
    return penalties


def _generate_intra_cluster_recommendations(
    momentum: dict,
    gaps: dict,
    failures: dict,
    biology_clusters: set,
    cluster_labels: dict,
) -> list[dict]:
    recommendations = []

    for cid in biology_clusters:
        if cid not in gaps["intra_gaps"]:
            continue

        m = momentum.get(cid, {})
        f = failures.get(cid, {})
        cluster_gaps = gaps["intra_gaps"][cid]

        momentum_score = m.get("momentum", 0)
        failure_penalty = f.get("penalty", 0)
        rising_entities = set(m.get("rising", []))

        for gap in cluster_gaps:
            entity_a = gap["entity_a"]
            entity_b = gap["entity_b"]
            gap_ratio = gap["ratio"]

            gap_score = max(0, 1.0 - gap_ratio)

            momentum_boost = 1.5 if (entity_a in rising_entities or entity_b in rising_entities) else 1.0

            bridge_score = momentum_score * momentum_boost * gap_score * (1 - failure_penalty)

            recommendations.append({
                "type": "intra_cluster",
                "cluster": cid,
                "cluster_label": cluster_labels.get(cid, cid),
                "entity_a": entity_a,
                "entity_b": entity_b,
                "bridge_score": round(bridge_score, 6),
                "momentum_score": round(momentum_score * momentum_boost, 6),
                "gap_score": round(gap_score, 4),
                "failure_penalty": round(failure_penalty, 4),
                "gap_expected": gap["expected"],
                "gap_observed": gap["observed"],
                "rising_involved": bool({entity_a, entity_b} & rising_entities),
                "recommendation": (
                    f"Explore the intersection of '{entity_a}' and '{entity_b}' "
                    f"within {cluster_labels.get(cid, 'C' + cid)}. "
                    f"Expected co-occurrence={gap['expected']:.1f} but observed={gap['observed']}, "
                    f"suggesting an underexplored combination."
                ),
            })

    return recommendations


def _generate_cross_cluster_recommendations(
    momentum: dict,
    gaps: dict,
    failures: dict,
    biology_clusters: set,
    cluster_labels: dict,
) -> list[dict]:
    recommendations = []

    for bridge in gaps["bridges"]:
        ca, cb = bridge["cluster_a"], bridge["cluster_b"]

        if ca not in biology_clusters and cb not in biology_clusters:
            continue

        ma = momentum.get(ca, {})
        mb = momentum.get(cb, {})
        fa = failures.get(ca, {})
        fb = failures.get(cb, {})

        combined_momentum = (ma.get("momentum", 0) + mb.get("momentum", 0)) / 2

        jaccard = bridge["jaccard"]
        if jaccard > 0.5:
            gap_score = 0.5
        elif jaccard < 0.05:
            gap_score = 0.3
        else:
            gap_score = 1.0 - abs(jaccard - 0.2) * 2

        combined_failure = (fa.get("penalty", 0) + fb.get("penalty", 0)) / 2

        bridge_score = combined_momentum * gap_score * (1 - combined_failure)

        rising_a = set(ma.get("rising", []))
        rising_b = set(mb.get("rising", []))
        shared = set(bridge["shared_entities"])
        rising_shared = shared & (rising_a | rising_b)

        recommendations.append({
            "type": "cross_cluster",
            "cluster_a": ca,
            "cluster_b": cb,
            "cluster_a_label": cluster_labels.get(ca, ca),
            "cluster_b_label": cluster_labels.get(cb, cb),
            "bridge_score": round(bridge_score, 6),
            "momentum_score": round(combined_momentum, 6),
            "gap_score": round(gap_score, 4),
            "failure_penalty": round(combined_failure, 4),
            "entity_jaccard": jaccard,
            "shared_entities": bridge["shared_entities"],
            "rising_in_shared": list(rising_shared),
            "recommendation": (
                f"Bridge {cluster_labels.get(ca, 'C' + ca)} <-> "
                f"{cluster_labels.get(cb, 'C' + cb)} "
                f"(Jaccard={jaccard:.3f}, {bridge['shared_count']} shared entities). "
                + (f"Rising entities in overlap: {', '.join(rising_shared)}. " if rising_shared else "")
                + "These communities share vocabulary but rarely cite each other."
            ),
        })

    return recommendations


def generate_recommendations(
    frontier_results: dict,
    failure_results: dict,
    biology_clusters: list[str] | None = None,
    cluster_labels: dict | None = None,
    top_n: int = 20,
) -> dict:
    """Generate bridge recommendations combining T2+T3 (frontier) and failure signals.

    Args:
        frontier_results: Output from e015 pipeline containing 't2_temporal' and
            't3_structural_gaps' keys.
        failure_results: Output from analyze_failures() / e017 pipeline.
        biology_clusters: Cluster IDs to treat as biology. Defaults to
            DEFAULT_BIOLOGY_CLUSTERS.
        cluster_labels: Dict mapping cluster_id -> human label. Defaults to
            DEFAULT_CLUSTER_LABELS.
        top_n: Number of top recommendations to include in output.

    Returns:
        Result dict with all_recommendations (sorted by bridge_score) and summary stats.
    """
    if biology_clusters is None:
        bio_set = DEFAULT_BIOLOGY_CLUSTERS
    else:
        bio_set = set(str(c) for c in biology_clusters)

    if cluster_labels is None:
        cluster_labels = DEFAULT_CLUSTER_LABELS

    momentum = _compute_momentum_scores(frontier_results["t2_temporal"])
    gaps = _compute_gap_scores(frontier_results["t3_structural_gaps"])
    failures = _compute_failure_penalties(failure_results)

    mom_str = ", ".join(f"C{k}={v['momentum']:.4f}" for k, v in sorted(momentum.items()))
    fail_str = ", ".join(f"C{k}={v['penalty']:.4f}" for k, v in sorted(failures.items()))
    print(f"Momentum scores: {mom_str}")
    print(f"Failure penalties: {fail_str}")

    intra_recs = _generate_intra_cluster_recommendations(
        momentum, gaps, failures, bio_set, cluster_labels
    )
    cross_recs = _generate_cross_cluster_recommendations(
        momentum, gaps, failures, bio_set, cluster_labels
    )

    all_recs = intra_recs + cross_recs
    all_recs.sort(key=lambda r: r["bridge_score"], reverse=True)

    print(f"\nGenerated {len(intra_recs)} intra-cluster + {len(cross_recs)} cross-cluster recommendations")

    n_with_rising = sum(
        1 for r in all_recs[:10] if r.get("rising_involved") or r.get("rising_in_shared")
    )
    n_bio_involved = sum(
        1 for r in all_recs[:10]
        if r.get("cluster") in bio_set
        or r.get("cluster_a") in bio_set
        or r.get("cluster_b") in bio_set
    )

    if len(all_recs) < 5:
        verdict = f"FAIL — only {len(all_recs)} recommendations generated (need >= 5)"
    elif n_bio_involved >= 5:
        verdict = (f"GO — {n_bio_involved}/10 top recs involve biology clusters, "
                   f"{n_with_rising} linked to rising trends")
    else:
        verdict = f"CONDITIONAL — {n_bio_involved}/10 bio, {n_with_rising} with rising trends"

    return {
        "n_intra_recommendations": len(intra_recs),
        "n_cross_recommendations": len(cross_recs),
        "n_total": len(all_recs),
        "top_10_bio_involved": n_bio_involved,
        "top_10_with_rising": n_with_rising,
        "verdict": verdict,
        "momentum_summary": {
            cid: {"momentum": v["momentum"], "rising": v["rising"]}
            for cid, v in momentum.items()
        },
        "failure_summary": failures,
        f"top_{top_n}": all_recs[:top_n],
        "all_recommendations": all_recs,
    }
