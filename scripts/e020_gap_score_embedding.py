#!/usr/bin/env python3
"""e020: Gap Score Embedding — replace ratio-based gap_score with cosine distance.

Replaces:
- Intra-cluster: gap_score = max(0, 1.0 - ratio) → cosine_distance(embed(a), embed(b))
- Cross-cluster: entity_jaccard → mean_cosine_distance of all entity pairs

Pilot gate: CV >= 15% on 50-pair sample before proceeding.
Success: rho >= 0.3 AND CV >= 15% AND top-10 changes >= 3.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sentence_transformers import SentenceTransformer

E015_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e015/results.json"
E018_RESULTS = Path(__file__).resolve().parent.parent / "outputs/e018/results.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e020"
BRIDGE_RECOMMEND_PY = Path(__file__).resolve().parent.parent / "src/papersift/bridge_recommend.py"

BIOLOGY_CLUSTERS = {"0", "1", "3", "5", "7"}


def load_data():
    with open(E015_RESULTS) as f:
        e015 = json.load(f)
    with open(E018_RESULTS) as f:
        e018 = json.load(f)
    return e015, e018


def embed_entities(model: SentenceTransformer, entities: list[str]) -> np.ndarray:
    return model.encode(entities, convert_to_numpy=True, show_progress_bar=False)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """1 - cosine_similarity for unit vectors."""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(1.0 - np.dot(a_norm, b_norm))


def collect_intra_pairs(e015: dict) -> list[dict]:
    """Collect all intra-cluster entity pairs from e015 T3 gaps."""
    pairs = []
    t3 = e015["t3_structural_gaps"]
    for cid, gaps in t3["intra_cluster_gaps"].items():
        for gap in gaps:
            pairs.append({
                "cluster": cid,
                "entity_a": gap["entity_a"],
                "entity_b": gap["entity_b"],
                "ratio": gap["ratio"],
                "expected": gap["expected"],
                "observed": gap["observed"],
                "old_gap_score": max(0, 1.0 - gap["ratio"]),
            })
    return pairs


def run_pilot(model: SentenceTransformer, pairs: list[dict]) -> dict:
    """T0: Pilot gate — CV test on first 50 pairs."""
    print("T0: Running pilot gate (50-pair cosine distance CV test)...")
    pilot_pairs = pairs[:50]
    n = len(pilot_pairs)
    print(f"  Using {n} pairs")

    entities_a = [p["entity_a"] for p in pilot_pairs]
    entities_b = [p["entity_b"] for p in pilot_pairs]

    all_entities = list(set(entities_a + entities_b))
    print(f"  Embedding {len(all_entities)} unique entities...")
    embeddings = {e: embed_entities(model, [e])[0] for e in all_entities}

    distances = []
    for p in pilot_pairs:
        d = cosine_distance(embeddings[p["entity_a"]], embeddings[p["entity_b"]])
        distances.append(d)

    distances = np.array(distances)
    mean_d = float(np.mean(distances))
    std_d = float(np.std(distances))
    cv = std_d / mean_d if mean_d > 0 else 0.0

    gate = "PASS" if cv >= 0.15 else "FAIL"
    print(f"  mean={mean_d:.4f}, std={std_d:.4f}, CV={cv:.4f} -> {gate}")

    return {
        "n_pairs": n,
        "cv": round(cv, 4),
        "mean_distance": round(mean_d, 4),
        "std_distance": round(std_d, 4),
        "gate": gate,
    }


def compute_new_intra_scores(
    model: SentenceTransformer,
    pairs: list[dict],
    e018_recs: list[dict],
) -> tuple[list[dict], dict]:
    """Replace gap_score with cosine distance for all intra-cluster pairs."""
    print(f"\nIntra-cluster: embedding {len(pairs)} gap pairs...")

    all_entity_names = list({p["entity_a"] for p in pairs} | {p["entity_b"] for p in pairs})
    print(f"  Embedding {len(all_entity_names)} unique entities...")
    emb_map = {}
    vecs = embed_entities(model, all_entity_names)
    for name, vec in zip(all_entity_names, vecs):
        emb_map[name] = vec

    # Compute new gap scores
    for p in pairs:
        p["new_gap_score"] = cosine_distance(emb_map[p["entity_a"]], emb_map[p["entity_b"]])

    old_scores = np.array([p["old_gap_score"] for p in pairs])
    new_scores = np.array([p["new_gap_score"] for p in pairs])

    old_cv = float(np.std(old_scores) / np.mean(old_scores)) if np.mean(old_scores) > 0 else 0.0
    new_cv = float(np.std(new_scores) / np.mean(new_scores)) if np.mean(new_scores) > 0 else 0.0

    # Build lookup for e018 intra recs: (cluster, entity_a, entity_b) -> new gap score
    pair_lookup = {
        (p["cluster"], p["entity_a"], p["entity_b"]): p["new_gap_score"]
        for p in pairs
    }

    # Recalculate bridge_score for intra-cluster e018 recs
    new_intra_recs = []
    for rec in e018_recs:
        if rec["type"] != "intra_cluster":
            continue
        key = (rec["cluster"], rec["entity_a"], rec["entity_b"])
        new_gap = pair_lookup.get(key, rec["gap_score"])  # fallback to old if not found
        old_momentum_boost_ratio = rec["momentum_score"] / (rec["momentum_score"] / rec["gap_score"]) if rec["gap_score"] > 0 else rec["momentum_score"]
        # Reconstruct: bridge_score = momentum_score * new_gap * (1 - failure_penalty)
        # momentum_score in rec already includes boost factor
        new_bridge = rec["momentum_score"] * new_gap * (1.0 - rec["failure_penalty"])
        new_intra_recs.append({
            **rec,
            "gap_score": round(new_gap, 4),
            "bridge_score": round(new_bridge, 6),
            "old_gap_score": rec["gap_score"],
            "old_bridge_score": rec["bridge_score"],
        })

    # Spearman rho between new_gap_score and bridge_score
    gap_arr = np.array([r["gap_score"] for r in new_intra_recs])
    bridge_arr = np.array([r["bridge_score"] for r in new_intra_recs])
    if len(gap_arr) >= 2:
        rho, pval = spearmanr(gap_arr, bridge_arr)
    else:
        rho, pval = 0.0, 1.0

    stats = {
        "old_cv": round(old_cv, 4),
        "new_cv": round(new_cv, 4),
        "spearman_rho": round(float(rho), 4),
        "spearman_p": round(float(pval), 6),
        "n_gaps": len(pairs),
    }
    print(f"  old_cv={old_cv:.4f}, new_cv={new_cv:.4f}, rho={rho:.4f} (p={pval:.4f})")

    return new_intra_recs, stats


def compute_new_cross_scores(
    model: SentenceTransformer,
    e018_recs: list[dict],
    t3_bridges: list[dict],
) -> tuple[list[dict], dict]:
    """Replace entity_jaccard with mean_cosine_distance for cross-cluster bridges."""
    print(f"\nCross-cluster: computing mean cosine distance for {len(t3_bridges)} bridges...")

    # Build entity sets per cluster from t3 data
    cluster_entities: dict[str, set] = {}
    for bridge in t3_bridges:
        ca = str(bridge["cluster_a"])
        cb = str(bridge["cluster_b"])
        # Shared entities as proxy; real per-cluster sets not stored in bridge data
        # Use shared_entities for mean pairwise distance
        shared = bridge.get("shared_entities", [])
        for cid in [ca, cb]:
            if cid not in cluster_entities:
                cluster_entities[cid] = set()
        cluster_entities[ca].update(shared)
        cluster_entities[cb].update(shared)

    # Collect all unique entities across cross-cluster recs
    all_entities = set()
    for rec in e018_recs:
        if rec["type"] == "cross_cluster":
            all_entities.update(rec.get("shared_entities", []))

    if not all_entities:
        print("  No entities found in cross-cluster recs — skipping embedding")
        return [], {"old_method": "entity_jaccard", "new_method": "mean_cosine_distance", "n_bridges": 0}

    all_entity_list = list(all_entities)
    print(f"  Embedding {len(all_entity_list)} unique cross-cluster entities...")
    vecs = embed_entities(model, all_entity_list)
    emb_map = {name: vec for name, vec in zip(all_entity_list, vecs)}

    new_cross_recs = []
    for rec in e018_recs:
        if rec["type"] != "cross_cluster":
            continue

        shared = rec.get("shared_entities", [])
        if len(shared) < 2:
            # Not enough entities for pairwise distance — use old jaccard-based score
            new_cross_recs.append({
                **rec,
                "old_gap_score": rec["gap_score"],
                "old_bridge_score": rec["bridge_score"],
                "mean_cosine_distance": None,
            })
            continue

        # Compute mean pairwise cosine distance within shared entity set
        embedded = [emb_map[e] for e in shared if e in emb_map]
        if len(embedded) < 2:
            new_cross_recs.append({
                **rec,
                "old_gap_score": rec["gap_score"],
                "old_bridge_score": rec["bridge_score"],
                "mean_cosine_distance": None,
            })
            continue

        pairwise = []
        for i in range(len(embedded)):
            for j in range(i + 1, len(embedded)):
                pairwise.append(cosine_distance(embedded[i], embedded[j]))
        mean_dist = float(np.mean(pairwise))

        # New gap_score = mean_cosine_distance (high distance = semantically diverse = interesting bridge)
        new_gap = mean_dist
        new_bridge = rec["momentum_score"] * new_gap * (1.0 - rec["failure_penalty"])

        new_cross_recs.append({
            **rec,
            "gap_score": round(new_gap, 4),
            "bridge_score": round(new_bridge, 6),
            "old_gap_score": rec["gap_score"],
            "old_bridge_score": rec["bridge_score"],
            "mean_cosine_distance": round(mean_dist, 4),
        })

    stats = {
        "old_method": "entity_jaccard",
        "new_method": "mean_cosine_distance",
        "n_bridges": len(new_cross_recs),
    }
    print(f"  Processed {len(new_cross_recs)} cross-cluster recs")

    return new_cross_recs, stats


def compute_top10_changes(
    original_recs: list[dict],
    new_recs: list[dict],
) -> dict:
    """Compare top-10 original vs new recommendations."""
    def rec_key(r: dict) -> str:
        if r["type"] == "intra_cluster":
            return f"intra|{r['cluster']}|{r['entity_a']}|{r['entity_b']}"
        return f"cross|{r['cluster_a']}|{r['cluster_b']}"

    orig_top10_keys = [rec_key(r) for r in original_recs[:10]]
    new_top10_keys = [rec_key(r) for r in new_recs[:10]]

    orig_set = set(orig_top10_keys)
    new_set = set(new_top10_keys)
    n_changed = len(orig_set.symmetric_difference(new_set)) // 2  # entries that differ

    return {
        "original_top10": [r.get("recommendation", rec_key(r))[:80] for r in original_recs[:10]],
        "new_top10": [r.get("recommendation", rec_key(r))[:80] for r in new_recs[:10]],
        "n_changed": n_changed,
    }


def scan_downstream_sync() -> dict:
    """Read bridge_recommend.py and identify gap_score / jaccard usage lines."""
    with open(BRIDGE_RECOMMEND_PY) as f:
        lines = f.readlines()

    gap_score_lines = []
    jaccard_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "gap_score" in stripped and not stripped.startswith("#"):
            gap_score_lines.append(i)
        if "jaccard" in stripped.lower() and not stripped.startswith("#"):
            jaccard_lines.append(i)

    return {
        "bridge_recommend_py": {
            "gap_score_lines": gap_score_lines,
            "jaccard_lines": jaccard_lines,
            "needs_update": bool(gap_score_lines or jaccard_lines),
        }
    }


def run():
    print("=" * 60)
    print("e020: Gap Score Embedding")
    print("=" * 60)

    e015, e018 = load_data()
    original_recs = e018["all_recommendations"]

    # Collect intra pairs from e015
    intra_pairs = collect_intra_pairs(e015)
    t3_bridges = e015["t3_structural_gaps"]["cross_cluster_bridges"]
    print(f"Loaded {len(intra_pairs)} intra-cluster gap pairs from e015")
    print(f"Loaded {len(t3_bridges)} cross-cluster bridges from e015")
    print(f"Loaded {len(original_recs)} recommendations from e018")

    # Load model
    print("\nLoading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Model loaded.")

    # T0: Pilot gate
    pilot = run_pilot(model, intra_pairs)

    if pilot["gate"] == "FAIL":
        print(f"\nPilot FAILED: CV={pilot['cv']:.4f} < 0.15 — cosine distances lack spread.")
        print("Verdict: KILL")
        results = {
            "experiment": "e020",
            "title": "T6 Gap Score Embedding",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pilot": pilot,
            "intra_cluster": None,
            "cross_cluster": None,
            "top10_changes": None,
            "downstream_sync": scan_downstream_sync(),
            "verdict": "KILL",
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / "results.json", "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Saved to {OUTPUT_DIR / 'results.json'}")
        return results

    print(f"\nPilot PASSED: CV={pilot['cv']:.4f} >= 0.15 — proceeding with main experiment.")

    # Main experiment
    new_intra_recs, intra_stats = compute_new_intra_scores(model, intra_pairs, original_recs)
    new_cross_recs, cross_stats = compute_new_cross_scores(model, original_recs, t3_bridges)

    # Merge and sort new recs
    all_new_recs = new_intra_recs + new_cross_recs
    all_new_recs.sort(key=lambda r: r["bridge_score"], reverse=True)

    # Top-10 changes
    top10 = compute_top10_changes(original_recs, all_new_recs)

    # Downstream sync check
    downstream = scan_downstream_sync()

    # Determine verdict
    rho = intra_stats["spearman_rho"]
    new_cv = intra_stats["new_cv"]
    n_changed = top10["n_changed"]

    print(f"\nEvaluation:")
    print(f"  Spearman rho = {rho:.4f} (target >= 0.3)")
    print(f"  New CV = {new_cv:.4f} (target >= 0.15)")
    print(f"  Top-10 changes = {n_changed} (target >= 3)")

    if rho >= 0.3 and new_cv >= 0.15 and n_changed >= 3:
        verdict = "GO"
    else:
        reasons = []
        if rho < 0.3:
            reasons.append(f"rho={rho:.3f}<0.3")
        if new_cv < 0.15:
            reasons.append(f"cv={new_cv:.3f}<0.15")
        if n_changed < 3:
            reasons.append(f"top10_changes={n_changed}<3")
        verdict = f"NO-GO ({'; '.join(reasons)})"

    print(f"\nVerdict: {verdict}")

    results = {
        "experiment": "e020",
        "title": "T6 Gap Score Embedding",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pilot": pilot,
        "intra_cluster": intra_stats,
        "cross_cluster": cross_stats,
        "top10_changes": top10,
        "downstream_sync": downstream,
        "verdict": verdict,
        "top_20_new": all_new_recs[:20],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUTPUT_DIR / 'results.json'}")

    return results


if __name__ == "__main__":
    run()
