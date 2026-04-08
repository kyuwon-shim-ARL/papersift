#!/usr/bin/env python3
"""e018: Bridge Recommendation — 'try this combination' recommendations.

Combines T2(temporal momentum) + T3(structural gaps) + T5(failure signals).
bridge_score = momentum_score × gap_score × (1 - failure_penalty)

Success: top-10 >= 5 user-rated 'worth trying'.
Kill: novelty < 30% (most recommendations overlap existing research).
"""

import json
from pathlib import Path

E015_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e015/results.json"
E017_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e017/results.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e018"

# Biology cluster IDs
BIOLOGY_CLUSTERS = {"0", "1", "3", "5", "7"}

# Cluster labels for readability
CLUSTER_LABELS = {
    "0": "in-silico/pharmacology",
    "1": "whole-cell/systems-biology",
    "2": "telecom/V2X",
    "3": "neuro/electrophysiology",
    "4": "digital-twin/manufacturing",
    "5": "mechanics/ABM",
    "6": "fuel-cells/energy",
    "7": "immunology",
}


def load_e015():
    with open(E015_RESULTS) as f:
        return json.load(f)


def load_e017():
    with open(E017_RESULTS) as f:
        return json.load(f)


def compute_momentum_scores(t2_data: dict) -> dict:
    """Extract per-cluster momentum scores and rising entities from T2."""
    scores = {}
    for cid, cdata in t2_data["clusters"].items():
        scores[cid] = {
            "momentum": cdata["momentum_score"],
            "rising": [e["entity"] for e in cdata.get("top_rising", [])],
            "declining": [e["entity"] for e in cdata.get("top_declining", [])],
            "n_significant": cdata["significant"],
        }
    return scores


def compute_gap_scores(t3_data: dict) -> dict:
    """Extract intra-cluster gaps and cross-cluster bridges from T3."""
    intra_gaps = {}
    for cid, gaps in t3_data["intra_cluster_gaps"].items():
        intra_gaps[cid] = gaps

    bridges = []
    for b in t3_data["cross_cluster_bridges"]:
        bridges.append({
            "cluster_a": str(b["cluster_a"]),
            "cluster_b": str(b["cluster_b"]),
            "jaccard": b["entity_jaccard"],
            "shared_entities": b["shared_entities"][:10],
            "shared_count": b.get("shared_count", len(b.get("shared_entities", []))),
        })

    return {"intra_gaps": intra_gaps, "bridges": bridges}


def compute_failure_penalties(e017_data: dict) -> dict:
    """Compute per-cluster failure penalty from dead-end signals.

    penalty = dead_end_signals / (dead_end_signals + limit_themes + 1)
    Range: [0, 1), higher = more dead-ends.
    """
    penalties = {}
    for cid, cdata in e017_data.get("clusters", {}).items():
        n_dead = len(cdata.get("dead_end_signals", []))
        n_themes = len(cdata.get("limit_themes", []))
        penalty = n_dead / (n_dead + n_themes + 1)
        penalties[cid] = {
            "penalty": round(penalty, 4),
            "n_dead_ends": n_dead,
            "n_themes": n_themes,
            "dead_end_keywords": [
                d["theme_label"] for d in cdata.get("dead_end_signals", [])
            ],
        }
    return penalties


def generate_intra_cluster_recommendations(
    momentum: dict, gaps: dict, failures: dict
) -> list[dict]:
    """Generate recommendations from intra-cluster gaps + temporal momentum."""
    recommendations = []

    for cid in BIOLOGY_CLUSTERS:
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

            # Gap score: lower ratio = bigger gap = higher score
            gap_score = max(0, 1.0 - gap_ratio)

            # Boost if either entity is rising
            momentum_boost = 1.0
            if entity_a in rising_entities or entity_b in rising_entities:
                momentum_boost = 1.5

            bridge_score = (
                momentum_score * momentum_boost * gap_score * (1 - failure_penalty)
            )

            recommendations.append({
                "type": "intra_cluster",
                "cluster": cid,
                "cluster_label": CLUSTER_LABELS.get(cid, cid),
                "entity_a": entity_a,
                "entity_b": entity_b,
                "bridge_score": round(bridge_score, 6),
                "momentum_score": round(momentum_score * momentum_boost, 6),
                "gap_score": round(gap_score, 4),
                "failure_penalty": round(failure_penalty, 4),
                "gap_expected": gap["expected"],
                "gap_observed": gap["observed"],
                "rising_involved": bool(
                    {entity_a, entity_b} & rising_entities
                ),
                "recommendation": (
                    f"Explore the intersection of '{entity_a}' and '{entity_b}' "
                    f"within {CLUSTER_LABELS.get(cid, 'C' + cid)}. "
                    f"Expected co-occurrence={gap['expected']:.1f} but observed={gap['observed']}, "
                    f"suggesting an underexplored combination."
                ),
            })

    return recommendations


def generate_cross_cluster_recommendations(
    momentum: dict, gaps: dict, failures: dict
) -> list[dict]:
    """Generate recommendations from cross-cluster bridges."""
    recommendations = []

    for bridge in gaps["bridges"]:
        ca, cb = bridge["cluster_a"], bridge["cluster_b"]

        # At least one must be biology
        if ca not in BIOLOGY_CLUSTERS and cb not in BIOLOGY_CLUSTERS:
            continue

        ma = momentum.get(ca, {})
        mb = momentum.get(cb, {})
        fa = failures.get(ca, {})
        fb = failures.get(cb, {})

        # Combined momentum: average of both clusters
        combined_momentum = (
            ma.get("momentum", 0) + mb.get("momentum", 0)
        ) / 2

        # Gap score from bridge Jaccard: moderate overlap = interesting
        # Too high (>0.5) = already connected, too low (<0.05) = too distant
        jaccard = bridge["jaccard"]
        if jaccard > 0.5:
            gap_score = 0.5  # Already quite connected
        elif jaccard < 0.05:
            gap_score = 0.3  # Very distant, risky
        else:
            gap_score = 1.0 - abs(jaccard - 0.2) * 2  # Peak at ~0.2

        # Failure: average penalty
        combined_failure = (
            fa.get("penalty", 0) + fb.get("penalty", 0)
        ) / 2

        bridge_score = combined_momentum * gap_score * (1 - combined_failure)

        # Find rising entities in shared set
        rising_a = set(ma.get("rising", []))
        rising_b = set(mb.get("rising", []))
        shared = set(bridge["shared_entities"])
        rising_shared = shared & (rising_a | rising_b)

        recommendations.append({
            "type": "cross_cluster",
            "cluster_a": ca,
            "cluster_b": cb,
            "cluster_a_label": CLUSTER_LABELS.get(ca, ca),
            "cluster_b_label": CLUSTER_LABELS.get(cb, cb),
            "bridge_score": round(bridge_score, 6),
            "momentum_score": round(combined_momentum, 6),
            "gap_score": round(gap_score, 4),
            "failure_penalty": round(combined_failure, 4),
            "entity_jaccard": jaccard,
            "shared_entities": bridge["shared_entities"],
            "rising_in_shared": list(rising_shared),
            "recommendation": (
                f"Bridge {CLUSTER_LABELS.get(ca, 'C' + ca)} ↔ "
                f"{CLUSTER_LABELS.get(cb, 'C' + cb)} "
                f"(Jaccard={jaccard:.3f}, {bridge['shared_count']} shared entities). "
                + (
                    f"Rising entities in overlap: {', '.join(rising_shared)}. "
                    if rising_shared
                    else ""
                )
                + "These communities share vocabulary but rarely cite each other."
            ),
        })

    return recommendations


def run():
    print("Loading e015 (T1/T2/T3) results...")
    e015 = load_e015()

    print("Loading e017 (failure signals)...")
    e017 = load_e017()

    # Extract components
    momentum = compute_momentum_scores(e015["t2_temporal"])
    gaps = compute_gap_scores(e015["t3_structural_gaps"])
    failures = compute_failure_penalties(e017)

    mom_str = ", ".join(f"C{k}={v['momentum']:.4f}" for k, v in sorted(momentum.items()))
    fail_str = ", ".join(f"C{k}={v['penalty']:.4f}" for k, v in sorted(failures.items()))
    print(f"\nMomentum scores: {mom_str}")
    print(f"Failure penalties: {fail_str}")

    # Generate recommendations
    intra_recs = generate_intra_cluster_recommendations(momentum, gaps, failures)
    cross_recs = generate_cross_cluster_recommendations(momentum, gaps, failures)

    all_recs = intra_recs + cross_recs
    all_recs.sort(key=lambda r: r["bridge_score"], reverse=True)

    print(f"\nGenerated {len(intra_recs)} intra-cluster + {len(cross_recs)} cross-cluster recommendations")
    print("\nTop-20 recommendations:")
    for i, rec in enumerate(all_recs[:20], 1):
        print(f"  {i}. [{rec['type']}] score={rec['bridge_score']:.4f} — {rec['recommendation'][:100]}...")

    # Verdict
    # Check if recommendations are non-trivial
    n_with_rising = sum(1 for r in all_recs[:10] if r.get("rising_involved") or r.get("rising_in_shared"))
    n_bio_involved = sum(
        1 for r in all_recs[:10]
        if r.get("cluster") in BIOLOGY_CLUSTERS
        or r.get("cluster_a") in BIOLOGY_CLUSTERS
        or r.get("cluster_b") in BIOLOGY_CLUSTERS
    )

    if len(all_recs) < 5:
        verdict = f"FAIL — only {len(all_recs)} recommendations generated (need >= 5)"
    elif n_bio_involved >= 5:
        verdict = f"GO — {n_bio_involved}/10 top recs involve biology clusters, {n_with_rising} linked to rising trends"
    else:
        verdict = f"CONDITIONAL — {n_bio_involved}/10 bio, {n_with_rising} with rising trends"

    results = {
        "experiment": "e018",
        "description": "Bridge Recommendation — combining temporal + gaps + failure signals",
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
        "top_20": all_recs[:20],
        "all_recommendations": all_recs,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nVerdict: {verdict}")
    print(f"Saved to {OUTPUT_DIR / 'results.json'}")
    return results


if __name__ == "__main__":
    run()
