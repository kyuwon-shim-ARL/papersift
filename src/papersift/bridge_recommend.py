"""Bridge recommendation: combine temporal + structural gaps + failure signals.

Uses rank-normalization (e025) to prevent single-component dominance.
Each component (momentum, gap, failure) is converted to percentile rank [0,1]
before multiplicative combination: bridge_score = r_momentum * r_gap * r_inv_failure.

Intra-cluster and cross-cluster pools are ranked independently.

Limitations (from e025 validation on virtual-cell-sweep 3,070 papers):
  1. Small intra pool (n~8) has limited rank granularity (dominance 2.65 vs target <2.0).
     Cross pool (n~25) passes (dominance 1.19).
  2. Validated on a single dataset only; generalization unverified.
  3. Rank transformation makes raw scores non-interpretable; use rank position instead.
  4. Intra/cross pools are ranked independently, so bridge_score values are not
     directly comparable across pool types.

Refactored from scripts/e018_bridge_recommendation.py, updated with e025 rank-norm.
"""

from scipy.stats import rankdata

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


def _top_id(cid: str) -> str:
    """Return top-level cluster ID from hierarchical ID like '3.1' → '3'."""
    return str(cid).split(".")[0]


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


def _rank_normalize(values: list[float]) -> list[float]:
    """Convert raw values to percentile ranks in [0, 1].

    Uses scipy.stats.rankdata with 'average' method, then divides by n.
    """
    n = len(values)
    if n < 2:
        return [1.0] * n
    ranks = rankdata(values, method="average")
    return [round(float(r / n), 4) for r in ranks]


def _compute_otr(entities: list[str], otr_threshold: float = 0.10) -> float:
    """OTR = fraction of top-5 entities that are single short tokens (proxy for over-general).

    A proper OTR uses corpus prevalence >= threshold. Without that index,
    we proxy: entities with no hyphen, no slash, and exactly one token are
    likely domain-general.
    """
    top5 = entities[:5]
    if not top5:
        return 0.0
    overused = sum(
        1 for e in top5
        if len(e.split()) == 1 and "-" not in e and "/" not in e
    )
    return round(overused / len(top5), 3)


def _compute_ccr(entities: list[str]) -> float:
    """CCR = fraction of entities with hyphen, slash, or 2+ tokens (compound concepts)."""
    if not entities:
        return 0.0
    compound = sum(
        1 for e in entities
        if "-" in e or "/" in e or len(e.split()) >= 2
    )
    return round(compound / len(entities), 3)


def _evaluability(otr: float, ccr: float) -> str:
    """Combined PASS rule: otr <= 0.40 AND ccr >= 0.30."""
    if otr <= 0.40 and ccr >= 0.30:
        return "PASS"
    elif otr <= 0.60:
        return "CONDITIONAL"
    return "FAIL"


def _generate_intra_cluster_recommendations(
    momentum: dict,
    gaps: dict,
    failures: dict,
    biology_clusters: set,
    cluster_labels: dict,
) -> list[dict]:
    # Phase 1: collect raw components for all intra recommendations
    raw_entries = []

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
            boosted_momentum = momentum_score * momentum_boost

            raw_entries.append({
                "cid": cid,
                "entity_a": entity_a,
                "entity_b": entity_b,
                "momentum_raw": boosted_momentum,
                "gap_raw": gap_score,
                "failure_raw": failure_penalty,
                "gap": gap,
                "rising_involved": bool({entity_a, entity_b} & rising_entities),
                "cluster_label": cluster_labels.get(cid, cid),
            })

    if not raw_entries:
        return []

    # Phase 2: rank-normalize each component independently
    r_momentum = _rank_normalize([e["momentum_raw"] for e in raw_entries])
    r_gap = _rank_normalize([e["gap_raw"] for e in raw_entries])
    # Invert failure: lower penalty = better rank
    r_inv_failure = _rank_normalize([-e["failure_raw"] for e in raw_entries])

    # Phase 3: compute bridge_score and build output
    recommendations = []
    for i, entry in enumerate(raw_entries):
        bridge_score = r_momentum[i] * r_gap[i] * r_inv_failure[i]
        gap = entry["gap"]

        recommendations.append({
            "type": "intra_cluster",
            "cluster": entry["cid"],
            "cluster_label": entry["cluster_label"],
            "entity_a": entry["entity_a"],
            "entity_b": entry["entity_b"],
            "bridge_score": round(bridge_score, 6),
            "momentum_score": round(entry["momentum_raw"], 6),
            "gap_score": round(entry["gap_raw"], 4),
            "failure_penalty": round(entry["failure_raw"], 4),
            "r_momentum": r_momentum[i],
            "r_gap": r_gap[i],
            "r_inv_failure": r_inv_failure[i],
            "gap_expected": gap["expected"],
            "gap_observed": gap["observed"],
            "rising_involved": entry["rising_involved"],
            "recommendation": (
                f"Explore the intersection of '{entry['entity_a']}' and '{entry['entity_b']}' "
                f"within {entry['cluster_label']}. "
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
    # Phase 1: collect raw components for all cross recommendations
    raw_entries = []

    for bridge in gaps["bridges"]:
        ca, cb = bridge["cluster_a"], bridge["cluster_b"]

        if _top_id(ca) not in biology_clusters and _top_id(cb) not in biology_clusters:
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

        rising_a = set(ma.get("rising", []))
        rising_b = set(mb.get("rising", []))
        shared = set(bridge["shared_entities"])
        rising_shared = shared & (rising_a | rising_b)

        raw_entries.append({
            "ca": ca,
            "cb": cb,
            "momentum_raw": combined_momentum,
            "gap_raw": gap_score,
            "failure_raw": combined_failure,
            "jaccard": jaccard,
            "bridge": bridge,
            "rising_shared": rising_shared,
        })

    if not raw_entries:
        return []

    # Phase 2: rank-normalize each component independently
    r_momentum = _rank_normalize([e["momentum_raw"] for e in raw_entries])
    r_gap = _rank_normalize([e["gap_raw"] for e in raw_entries])
    r_inv_failure = _rank_normalize([-e["failure_raw"] for e in raw_entries])

    # Phase 3: compute bridge_score and build output
    recommendations = []
    for i, entry in enumerate(raw_entries):
        bridge_score = r_momentum[i] * r_gap[i] * r_inv_failure[i]
        bridge = entry["bridge"]

        recommendations.append({
            "type": "cross_cluster",
            "cluster_a": entry["ca"],
            "cluster_b": entry["cb"],
            "cluster_a_label": cluster_labels.get(entry["ca"], entry["ca"]),
            "cluster_b_label": cluster_labels.get(entry["cb"], entry["cb"]),
            "bridge_score": round(bridge_score, 6),
            "momentum_score": round(entry["momentum_raw"], 6),
            "gap_score": round(entry["gap_raw"], 4),
            "failure_penalty": round(entry["failure_raw"], 4),
            "r_momentum": r_momentum[i],
            "r_gap": r_gap[i],
            "r_inv_failure": r_inv_failure[i],
            "entity_jaccard": entry["jaccard"],
            "shared_entities": bridge["shared_entities"],
            "rising_in_shared": list(entry["rising_shared"]),
            "otr": _compute_otr(bridge["shared_entities"]),
            "ccr": _compute_ccr(bridge["shared_entities"]),
            "evaluability": _evaluability(
                _compute_otr(bridge["shared_entities"]),
                _compute_ccr(bridge["shared_entities"]),
            ),
            "recommendation": (
                f"Bridge {cluster_labels.get(entry['ca'], 'C' + entry['ca'])} <-> "
                f"{cluster_labels.get(entry['cb'], 'C' + entry['cb'])} "
                f"(Jaccard={entry['jaccard']:.3f}, {bridge['shared_count']} shared entities). "
                + (f"Rising entities in overlap: {', '.join(entry['rising_shared'])}. " if entry["rising_shared"] else "")
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
    tier: str = "top",  # "top" | "leaf"
    leaf_filter: str = "cross_parent",  # "all" | "cross_parent" | "same_parent"
) -> dict:
    """Generate bridge recommendations combining T2+T3 (frontier) and failure signals.

    Uses rank-normalization (e025) to prevent momentum dominance in the
    multiplicative bridge_score formula. Each component is converted to
    percentile rank before combination.

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

    # Leaf-tier: filter bridge list to cross-parent pairs only
    if tier == "leaf" and leaf_filter == "cross_parent":
        import copy
        t3 = frontier_results["t3_structural_gaps"]
        filtered_bridges = [
            b for b in t3["cross_cluster_bridges"]
            if _top_id(str(b["cluster_a"])) != _top_id(str(b["cluster_b"]))
        ]
        frontier_results = copy.deepcopy(frontier_results)
        frontier_results["t3_structural_gaps"]["cross_cluster_bridges"] = filtered_bridges

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
        if _top_id(r.get("cluster", "")) in bio_set
        or _top_id(r.get("cluster_a", "")) in bio_set
        or _top_id(r.get("cluster_b", "")) in bio_set
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
        "formula": "rank_norm (e025)",
        "momentum_summary": {
            cid: {"momentum": v["momentum"], "rising": v["rising"]}
            for cid, v in momentum.items()
        },
        "failure_summary": failures,
        f"top_{top_n}": all_recs[:top_n],
        "all_recommendations": all_recs,
        "cross_cluster_bridges": all_recs[:top_n],  # legacy flat list (kept for backward compat)
        "hierarchical_bridges": [],  # populated when tier="leaf" is called separately
    }
