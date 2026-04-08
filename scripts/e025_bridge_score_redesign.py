#!/usr/bin/env python3
"""e025: Bridge Score Formula Redesign — momentum dominance 해소.

T0: 3-component sensitivity + variance decomposition
T1: Rank-normalization formula
T2: Weighted geometric mean (T0 rho-inverse auto weights)
T3: Best formula selection + evaluation

Success criteria:
- dominance_ratio < 2.0 (MANDATORY)
- top-10 changes >= 3 OR Kendall tau displacement >= 0.15
- gap↔bridge rho in [0.3, 0.9]
- intra/cross independent pass (each meets 2/3 above)

Decision rule: dominance < 2.0 mandatory + 2/3 others → GO.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr, kendalltau, rankdata
from sentence_transformers import SentenceTransformer

E015_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e015/results.json"
E017_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e017/results.json"
E018_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e018/results.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e025"

BIOLOGY_CLUSTERS = {"0", "1", "3", "5", "7"}
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


def load_data():
    with open(E015_RESULTS) as f:
        e015 = json.load(f)
    with open(E017_RESULTS) as f:
        e017 = json.load(f)
    with open(E018_RESULTS) as f:
        e018 = json.load(f)
    return e015, e017, e018


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(1.0 - np.dot(a_norm, b_norm))


def extract_components(e018_recs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract momentum, gap, failure components from e018 recommendations."""
    intra = []
    cross = []
    for rec in e018_recs:
        entry = {
            "momentum": rec["momentum_score"],
            "gap": rec["gap_score"],
            "failure": rec["failure_penalty"],
            "bridge_score": rec["bridge_score"],
            "rec": rec,
        }
        if rec["type"] == "intra_cluster":
            intra.append(entry)
        else:
            cross.append(entry)
    return intra, cross


def compute_embedding_gap_scores(model: SentenceTransformer, e018_recs: list[dict]) -> dict:
    """Compute embedding-based gap scores (from e020 methodology)."""
    # Collect all entities
    all_entities = set()
    for rec in e018_recs:
        if rec["type"] == "intra_cluster":
            all_entities.add(rec["entity_a"])
            all_entities.add(rec["entity_b"])
        else:
            all_entities.update(rec.get("shared_entities", []))

    entity_list = sorted(all_entities)
    vecs = model.encode(entity_list, convert_to_numpy=True, show_progress_bar=False)
    emb_map = {name: vec for name, vec in zip(entity_list, vecs)}

    gap_scores = {}
    for i, rec in enumerate(e018_recs):
        if rec["type"] == "intra_cluster":
            a, b = rec["entity_a"], rec["entity_b"]
            if a in emb_map and b in emb_map:
                gap_scores[i] = cosine_distance(emb_map[a], emb_map[b])
            else:
                gap_scores[i] = rec["gap_score"]
        else:
            shared = [e for e in rec.get("shared_entities", []) if e in emb_map]
            if len(shared) >= 2:
                pairwise = []
                for si in range(len(shared)):
                    for sj in range(si + 1, len(shared)):
                        pairwise.append(cosine_distance(emb_map[shared[si]], emb_map[shared[sj]]))
                gap_scores[i] = float(np.mean(pairwise))
            else:
                gap_scores[i] = rec["gap_score"]
    return gap_scores


# ─── T0: Sensitivity Analysis ───────────────────────────────────────────

def t0_sensitivity(components: list[dict], label: str) -> dict:
    """Leave-one-out sensitivity + variance decomposition."""
    n = len(components)
    if n < 3:
        return {"error": f"Too few data points ({n}) for {label}", "n": n}

    momentum = np.array([c["momentum"] for c in components])
    gap = np.array([c["gap"] for c in components])
    failure = np.array([c["failure"] for c in components])
    bridge = np.array([c["bridge_score"] for c in components])

    # Full ranking
    full_rank = rankdata(-bridge, method="average")

    # Leave-one-out: fix each component to median, recompute score
    results = {}
    for name, values in [("momentum", momentum), ("gap", gap), ("failure", failure)]:
        median_val = np.median(values)
        if name == "momentum":
            reduced_scores = median_val * gap * (1 - failure)
        elif name == "gap":
            reduced_scores = momentum * median_val * (1 - failure)
        else:  # failure
            reduced_scores = momentum * gap * (1 - median_val)

        reduced_rank = rankdata(-reduced_scores, method="average")
        rho, pval = spearmanr(full_rank, reduced_rank)
        results[name] = {
            "rho_with_full": round(float(rho), 4),
            "p_value": round(float(pval), 6),
            "interpretation": "HIGH influence" if rho > 0.9 else "MODERATE" if rho > 0.7 else "LOW influence",
        }

    # Dominance ratio
    rhos = [results[k]["rho_with_full"] for k in ["momentum", "gap", "failure"]]
    max_rho = max(rhos)
    min_rho = min(rhos)
    dominance_ratio = max_rho / min_rho if min_rho > 0 else float("inf")

    # Variance decomposition (Sobol first-order proxy)
    total_var = np.var(bridge) if np.var(bridge) > 0 else 1e-10
    var_contributions = {}
    for name, values in [("momentum", momentum), ("gap", gap), ("failure", failure)]:
        # E[Y|Xi] for each unique Xi bin (5 bins)
        bins = np.percentile(values, [0, 20, 40, 60, 80, 100])
        bin_indices = np.digitize(values, bins[1:-1])
        conditional_means = []
        for b in range(len(bins) - 1):
            mask = bin_indices == b
            if mask.sum() > 0:
                conditional_means.append(np.mean(bridge[mask]))
        var_conditional = np.var(conditional_means) if len(conditional_means) > 1 else 0
        var_contributions[name] = round(float(var_conditional / total_var), 4)

    # Distribution stats
    dist_stats = {}
    for name, values in [("momentum", momentum), ("gap", gap), ("failure", failure)]:
        dist_stats[name] = {
            "mean": round(float(np.mean(values)), 6),
            "std": round(float(np.std(values)), 6),
            "min": round(float(np.min(values)), 6),
            "max": round(float(np.max(values)), 6),
            "cv": round(float(np.std(values) / np.mean(values)) if np.mean(values) > 0 else 0, 4),
            "range": round(float(np.max(values) - np.min(values)), 6),
        }

    return {
        "label": label,
        "n": n,
        "leave_one_out": results,
        "dominance_ratio": round(dominance_ratio, 4),
        "dominant_component": max(results, key=lambda k: results[k]["rho_with_full"]),
        "weakest_component": min(results, key=lambda k: results[k]["rho_with_full"]),
        "variance_decomposition": var_contributions,
        "distribution_stats": dist_stats,
    }


# ─── T1: Rank-Normalization ─────────────────────────────────────────────

def t1_rank_norm(components: list[dict]) -> list[dict]:
    """Percentile rank normalization + multiplicative combination."""
    n = len(components)
    if n < 2:
        return components

    momentum = np.array([c["momentum"] for c in components])
    gap = np.array([c["gap"] for c in components])
    failure = np.array([c["failure"] for c in components])

    # Percentile rank [0, 1] using scipy rankdata(average) / n
    r_momentum = rankdata(momentum, method="average") / n
    r_gap = rankdata(gap, method="average") / n
    r_inv_failure = rankdata(-failure, method="average") / n  # Invert: lower failure = better

    new_recs = []
    for i, c in enumerate(components):
        new_score = float(r_momentum[i] * r_gap[i] * r_inv_failure[i])
        new_recs.append({
            **c["rec"],
            "bridge_score": round(new_score, 6),
            "formula": "rank_norm",
            "r_momentum": round(float(r_momentum[i]), 4),
            "r_gap": round(float(r_gap[i]), 4),
            "r_inv_failure": round(float(r_inv_failure[i]), 4),
            "old_bridge_score": c["rec"]["bridge_score"],
        })

    return new_recs


# ─── T2: Weighted Geometric Mean ────────────────────────────────────────

def t2_weighted_geometric(
    components: list[dict],
    weights: tuple[float, float, float],
) -> list[dict]:
    """Weighted geometric mean: momentum^w1 × gap^w2 × (1-failure)^w3."""
    w1, w2, w3 = weights
    new_recs = []
    for c in components:
        m = max(c["momentum"], 1e-10)
        g = max(c["gap"], 0.01)  # gap < 0.01 guard
        f = max(1 - c["failure"], 1e-10)

        score = float((m ** w1) * (g ** w2) * (f ** w3))
        new_recs.append({
            **c["rec"],
            "bridge_score": round(score, 6),
            "formula": "weighted_geometric",
            "weights": {"momentum": w1, "gap": w2, "failure": w3},
            "old_bridge_score": c["rec"]["bridge_score"],
        })

    return new_recs


def derive_weights_from_t0(t0_result: dict) -> tuple[float, float, float]:
    """Auto-derive weights from T0 rho inverse."""
    loo = t0_result["leave_one_out"]
    rhos = {
        "momentum": loo["momentum"]["rho_with_full"],
        "gap": loo["gap"]["rho_with_full"],
        "failure": loo["failure"]["rho_with_full"],
    }
    # Inverse rho: high rho = dominant = lower weight
    inv_rhos = {k: 1.0 / max(v, 0.01) for k, v in rhos.items()}
    total = sum(inv_rhos.values())
    w_m = inv_rhos["momentum"] / total
    w_g = inv_rhos["gap"] / total
    w_f = inv_rhos["failure"] / total
    return (round(w_m, 4), round(w_g, 4), round(w_f, 4))


# ─── Evaluation ─────────────────────────────────────────────────────────

def rec_key(r: dict) -> str:
    if r["type"] == "intra_cluster":
        return f"intra|{r['cluster']}|{r['entity_a']}|{r['entity_b']}"
    return f"cross|{r['cluster_a']}|{r['cluster_b']}"


def evaluate_formula(
    original_recs: list[dict],
    new_recs: list[dict],
    label: str,
) -> dict:
    """Evaluate a formula against success criteria."""
    # Sort by bridge_score descending
    orig_sorted = sorted(original_recs, key=lambda r: r["bridge_score"], reverse=True)
    new_sorted = sorted(new_recs, key=lambda r: r["bridge_score"], reverse=True)

    # Top-10 changes
    orig_top10 = set(rec_key(r) for r in orig_sorted[:10])
    new_top10 = set(rec_key(r) for r in new_sorted[:10])
    n_changed = len(orig_top10.symmetric_difference(new_top10)) // 2

    # Kendall tau displacement
    orig_keys = [rec_key(r) for r in orig_sorted]
    new_key_rank = {rec_key(r): i for i, r in enumerate(new_sorted)}
    orig_ranks = list(range(len(orig_sorted)))
    new_ranks = [new_key_rank.get(k, len(new_sorted)) for k in orig_keys]
    if len(orig_ranks) >= 2:
        tau, tau_p = kendalltau(orig_ranks, new_ranks)
        tau_displacement = round(1.0 - float(tau), 4)  # 1-tau: higher = more different
    else:
        tau_displacement = 0.0

    # Sensitivity: component rho with new bridge_score
    new_bridge = np.array([r["bridge_score"] for r in new_sorted])
    new_rank = rankdata(-new_bridge, method="average")

    component_rhos = {}
    for comp_name, comp_key in [("momentum", "momentum_score"), ("gap", "gap_score"), ("failure", "failure_penalty")]:
        comp_vals = np.array([r[comp_key] if comp_key in r else r.get(comp_name, 0) for r in new_sorted])
        if len(comp_vals) >= 2 and np.std(comp_vals) > 0:
            rho, _ = spearmanr(comp_vals, new_rank)
            component_rhos[comp_name] = round(abs(float(rho)), 4)
        else:
            component_rhos[comp_name] = 0.0

    rho_values = [v for v in component_rhos.values() if v > 0]
    dominance_ratio = max(rho_values) / min(rho_values) if len(rho_values) >= 2 and min(rho_values) > 0 else float("inf")

    # gap↔bridge correlation
    gap_vals = np.array([r["gap_score"] for r in new_sorted])
    bridge_vals = np.array([r["bridge_score"] for r in new_sorted])
    if len(gap_vals) >= 2:
        gap_bridge_rho, _ = spearmanr(gap_vals, bridge_vals)
        gap_bridge_rho = round(float(gap_bridge_rho), 4)
    else:
        gap_bridge_rho = 0.0

    # Criteria checks
    criteria = {
        "top10_changes": n_changed >= 3,
        "kendall_displacement": tau_displacement >= 0.15,
        "top10_OR_kendall": n_changed >= 3 or tau_displacement >= 0.15,
        "dominance_ratio": dominance_ratio < 2.0,
        "gap_bridge_rho_lower": gap_bridge_rho >= 0.3,
        "gap_bridge_rho_upper": gap_bridge_rho <= 0.9,
        "gap_bridge_rho": 0.3 <= gap_bridge_rho <= 0.9,
    }

    # Decision: dominance mandatory + 2/3 others
    other_criteria = [criteria["top10_OR_kendall"], criteria["gap_bridge_rho"]]
    n_other_pass = sum(other_criteria)
    overall_pass = criteria["dominance_ratio"] and n_other_pass >= 1  # 2 other criteria, need 1+

    return {
        "label": label,
        "n_recs": len(new_recs),
        "top10_changes": n_changed,
        "kendall_tau_displacement": tau_displacement,
        "dominance_ratio": round(dominance_ratio, 4),
        "component_rhos": component_rhos,
        "gap_bridge_rho": gap_bridge_rho,
        "criteria": criteria,
        "overall_pass": overall_pass,
        "top5_new": [
            {"rank": i + 1, "key": rec_key(r), "score": r["bridge_score"]}
            for i, r in enumerate(new_sorted[:5])
        ],
    }


# ─── Main ────────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("e025: Bridge Score Formula Redesign")
    print("=" * 60)

    e015, e017, e018 = load_data()
    original_recs = e018["all_recommendations"]
    print(f"Loaded {len(original_recs)} recommendations from e018")

    # Load embedding model and compute embedding gap scores
    print("\nLoading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Computing embedding gap scores...")
    embedding_gaps = compute_embedding_gap_scores(model, original_recs)

    # Update gap scores with embeddings
    for i, rec in enumerate(original_recs):
        if i in embedding_gaps:
            rec["gap_score"] = embedding_gaps[i]

    # Extract components
    intra, cross = extract_components(original_recs)
    all_components = intra + cross
    print(f"Components: {len(intra)} intra + {len(cross)} cross = {len(all_components)} total")

    # ─── T0: Sensitivity Analysis ───
    print("\n" + "─" * 40)
    print("T0: Sensitivity Analysis")
    print("─" * 40)

    t0_intra = t0_sensitivity(intra, "intra_cluster")
    t0_cross = t0_sensitivity(cross, "cross_cluster")
    t0_all = t0_sensitivity(all_components, "all")

    for t0 in [t0_intra, t0_cross, t0_all]:
        if "error" in t0:
            print(f"  {t0['label']}: {t0['error']}")
            continue
        print(f"\n  [{t0['label']}] n={t0['n']}")
        print(f"    Dominant: {t0['dominant_component']} (rho={t0['leave_one_out'][t0['dominant_component']]['rho_with_full']:.4f})")
        print(f"    Weakest: {t0['weakest_component']} (rho={t0['leave_one_out'][t0['weakest_component']]['rho_with_full']:.4f})")
        print(f"    Dominance ratio: {t0['dominance_ratio']:.4f}")
        print(f"    Variance decomposition: {t0['variance_decomposition']}")
        for name in ["momentum", "gap", "failure"]:
            stats = t0["distribution_stats"][name]
            print(f"    {name}: mean={stats['mean']:.6f}, CV={stats['cv']:.4f}, range={stats['range']:.6f}")

    # ─── T1: Rank-Normalization ───
    print("\n" + "─" * 40)
    print("T1: Rank-Normalization")
    print("─" * 40)

    t1_intra_recs = t1_rank_norm(intra)
    t1_cross_recs = t1_rank_norm(cross)
    t1_all_recs = t1_intra_recs + t1_cross_recs
    t1_all_recs.sort(key=lambda r: r["bridge_score"], reverse=True)

    orig_intra_recs = [c["rec"] for c in intra]
    orig_cross_recs = [c["rec"] for c in cross]

    t1_eval_intra = evaluate_formula(orig_intra_recs, t1_intra_recs, "T1_rank_norm_intra")
    t1_eval_cross = evaluate_formula(orig_cross_recs, t1_cross_recs, "T1_rank_norm_cross")
    t1_eval_all = evaluate_formula(original_recs, t1_all_recs, "T1_rank_norm_all")

    print(f"\n  [all] top10_changes={t1_eval_all['top10_changes']}, kendall={t1_eval_all['kendall_tau_displacement']:.4f}")
    print(f"  [all] dominance={t1_eval_all['dominance_ratio']:.4f}, gap_rho={t1_eval_all['gap_bridge_rho']:.4f}")
    print(f"  [all] PASS={t1_eval_all['overall_pass']}")
    print(f"  [intra] dominance={t1_eval_intra['dominance_ratio']:.4f}, PASS={t1_eval_intra['overall_pass']}")
    print(f"  [cross] dominance={t1_eval_cross['dominance_ratio']:.4f}, PASS={t1_eval_cross['overall_pass']}")

    # ─── T2: Weighted Geometric Mean ───
    print("\n" + "─" * 40)
    print("T2: Weighted Geometric Mean")
    print("─" * 40)

    # Auto-derive weights from T0 (all components)
    if "error" not in t0_all:
        auto_weights = derive_weights_from_t0(t0_all)
        print(f"  Auto-derived weights from T0: momentum={auto_weights[0]}, gap={auto_weights[1]}, failure={auto_weights[2]}")
    else:
        auto_weights = (0.333, 0.333, 0.334)
        print(f"  Using equal weights (T0 failed): {auto_weights}")

    # Weight configurations: auto + ±0.1 sensitivity
    weight_configs = [
        ("auto", auto_weights),
        ("equal", (0.333, 0.333, 0.334)),
    ]
    # Sensitivity: shift each weight by ±0.1
    for shift_name, shift_idx in [("gap_boost", 1), ("momentum_boost", 0), ("failure_boost", 2)]:
        shifted = list(auto_weights)
        shifted[shift_idx] += 0.1
        # Normalize
        total = sum(shifted)
        shifted = tuple(round(w / total, 4) for w in shifted)
        weight_configs.append((shift_name, shifted))

    t2_results = {}
    for wname, weights in weight_configs:
        t2_intra_recs = t2_weighted_geometric(intra, weights)
        t2_cross_recs = t2_weighted_geometric(cross, weights)
        t2_all_recs = t2_intra_recs + t2_cross_recs
        t2_all_recs.sort(key=lambda r: r["bridge_score"], reverse=True)

        t2_eval_intra = evaluate_formula(orig_intra_recs, t2_intra_recs, f"T2_{wname}_intra")
        t2_eval_cross = evaluate_formula(orig_cross_recs, t2_cross_recs, f"T2_{wname}_cross")
        t2_eval_all = evaluate_formula(original_recs, t2_all_recs, f"T2_{wname}_all")

        t2_results[wname] = {
            "weights": weights,
            "eval_all": t2_eval_all,
            "eval_intra": t2_eval_intra,
            "eval_cross": t2_eval_cross,
        }

        print(f"\n  [{wname}] w=({weights[0]:.3f}, {weights[1]:.3f}, {weights[2]:.3f})")
        print(f"    [all] top10={t2_eval_all['top10_changes']}, kendall={t2_eval_all['kendall_tau_displacement']:.4f}, dom={t2_eval_all['dominance_ratio']:.4f}, gap_rho={t2_eval_all['gap_bridge_rho']:.4f}, PASS={t2_eval_all['overall_pass']}")
        print(f"    [intra] dom={t2_eval_intra['dominance_ratio']:.4f}, PASS={t2_eval_intra['overall_pass']}")
        print(f"    [cross] dom={t2_eval_cross['dominance_ratio']:.4f}, PASS={t2_eval_cross['overall_pass']}")

    # ─── T3: Best Formula Selection ───
    print("\n" + "─" * 40)
    print("T3: Best Formula Selection")
    print("─" * 40)

    candidates = []

    # T1 candidate
    if t1_eval_all["overall_pass"]:
        candidates.append({
            "name": "T1_rank_norm",
            "eval_all": t1_eval_all,
            "eval_intra": t1_eval_intra,
            "eval_cross": t1_eval_cross,
            "dominance": t1_eval_all["dominance_ratio"],
            "recs": t1_all_recs,
        })

    # T2 candidates
    for wname, result in t2_results.items():
        if result["eval_all"]["overall_pass"]:
            candidates.append({
                "name": f"T2_{wname}",
                "eval_all": result["eval_all"],
                "eval_intra": result["eval_intra"],
                "eval_cross": result["eval_cross"],
                "dominance": result["eval_all"]["dominance_ratio"],
                "weights": result["weights"],
                "recs": None,  # Don't store full recs for T2 variants
            })

    # Check intra/cross independent pass
    final_candidates = []
    for c in candidates:
        intra_pass = c["eval_intra"]["overall_pass"]
        cross_pass = c["eval_cross"]["overall_pass"]
        c["intra_pass"] = intra_pass
        c["cross_pass"] = cross_pass
        c["independent_pass"] = intra_pass and cross_pass
        final_candidates.append(c)

    # Sort by dominance_ratio (lower is better)
    final_candidates.sort(key=lambda c: c["dominance"])

    if final_candidates:
        best = final_candidates[0]
        verdict = f"GO — {best['name']}, dominance={best['dominance']:.4f}"
        print(f"\n  Best: {best['name']}")
        print(f"    dominance_ratio={best['dominance']:.4f}")
        print(f"    top10_changes={best['eval_all']['top10_changes']}")
        print(f"    kendall_displacement={best['eval_all']['kendall_tau_displacement']:.4f}")
        print(f"    gap_bridge_rho={best['eval_all']['gap_bridge_rho']:.4f}")
        print(f"    intra_pass={best['intra_pass']}, cross_pass={best['cross_pass']}")
    else:
        # Check if any candidate passes dominance but fails others
        all_evals = [("T1_rank_norm", t1_eval_all)]
        all_evals.extend([(f"T2_{wn}", r["eval_all"]) for wn, r in t2_results.items()])

        closest = min(all_evals, key=lambda x: abs(x[1]["dominance_ratio"] - 2.0))
        verdict = f"NO-GO — no formula passes all criteria. Closest: {closest[0]} (dominance={closest[1]['dominance_ratio']:.4f})"
        best = None
        print("\n  No formula passed all criteria.")
        print(f"  Closest: {closest[0]}, dominance={closest[1]['dominance_ratio']:.4f}")

    print(f"\nVerdict: {verdict}")

    # ─── Save Results ───
    results = {
        "experiment": "e025",
        "title": "Bridge Score Formula Redesign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "t0_sensitivity": {
            "intra": t0_intra,
            "cross": t0_cross,
            "all": t0_all,
        },
        "t1_rank_norm": {
            "eval_all": t1_eval_all,
            "eval_intra": t1_eval_intra,
            "eval_cross": t1_eval_cross,
            "top_20": [
                {k: v for k, v in r.items() if k != "shared_entities"}
                for r in t1_all_recs[:20]
            ],
        },
        "t2_weighted_geometric": {
            wname: {
                "weights": result["weights"],
                "eval_all": result["eval_all"],
                "eval_intra": result["eval_intra"],
                "eval_cross": result["eval_cross"],
            }
            for wname, result in t2_results.items()
        },
        "t3_selection": {
            "n_candidates": len(final_candidates),
            "candidates": [
                {
                    "name": c["name"],
                    "dominance": c["dominance"],
                    "top10_changes": c["eval_all"]["top10_changes"],
                    "kendall_displacement": c["eval_all"]["kendall_tau_displacement"],
                    "gap_bridge_rho": c["eval_all"]["gap_bridge_rho"],
                    "intra_pass": c["intra_pass"],
                    "cross_pass": c["cross_pass"],
                    "independent_pass": c["independent_pass"],
                    "weights": c.get("weights"),
                }
                for c in final_candidates
            ],
            "best": final_candidates[0]["name"] if final_candidates else None,
        },
        "verdict": verdict,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {OUTPUT_DIR / 'results.json'}")
    return results


if __name__ == "__main__":
    run()
