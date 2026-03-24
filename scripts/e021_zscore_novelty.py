#!/usr/bin/env python3
"""e021: T3 Z-Score Novelty Ranking — permutation-based null model for structural gaps.

Adds z-score based novelty ranking to intra-cluster structural gaps.
The null model permutes entity assignments across papers within each cluster
to build a distribution of expected co-occurrence counts.

Success criterion:
  GO:    additional_clusters_covered >= 2  (z < -2 finds gaps in clusters ratio < 0.2 misses)
  NO-GO: additional_clusters_covered < 2
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, ImprovedEntityExtractor

BASE = Path(__file__).resolve().parent.parent
DATA_PATH = BASE / "results/virtual-cell-sweep/papers_with_abstracts.json"
CLUSTERS_PATH = BASE / "results/virtual-cell-sweep/clusters.json"
E015_PATH = BASE / "outputs/e015/results.json"
OUTPUT_DIR = BASE / "outputs/e021"

N_PERMUTATIONS = 1000
MAX_ENTITIES = 100  # subsample to top-N by frequency if cluster has > this many


def load_data():
    with open(DATA_PATH) as f:
        papers = json.load(f)
    with open(CLUSTERS_PATH) as f:
        clusters = json.load(f)
    return papers, clusters


def extract_entities(papers):
    """Replicate e015 T0 entity extraction."""
    extractor = ImprovedEntityExtractor()
    all_patterns = (
        [(m, pat, "METHOD") for m, pat in extractor.method_patterns]
        + [(o, pat, "ORGANISM") for o, pat in extractor.organism_patterns]
        + [(c, pat, "CONCEPT") for c, pat in extractor.concept_patterns]
        + [(d, pat, "DATASET") for d, pat in extractor.dataset_patterns]
    )

    entity_data = {}
    for p in papers:
        entities = extractor.extract_entities(p["title"], p.get("category", ""))
        entity_set = {e["name"].lower() for e in entities}
        abstract = p.get("abstract", "")
        if abstract:
            for name, pattern, etype in all_patterns:
                key = name.lower()
                if key in STOPWORDS:
                    continue
                if key not in entity_set and pattern.search(abstract):
                    entity_set.add(key)
        entity_data[p["doi"]] = entity_set
    return entity_data


def build_cooccur_matrix(paper_entities, entity_index):
    """Build co-occurrence count matrix (upper triangle) as a dict of pair -> count.

    paper_entities: list of frozensets (one per paper, entity indices)
    entity_index: list of entity names
    Returns: np.ndarray shape (n_entities, n_entities), symmetric, diagonal=0
    """
    n = len(entity_index)
    mat = np.zeros((n, n), dtype=np.int32)
    for ents in paper_entities:
        lst = sorted(ents)
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                mat[lst[i], lst[j]] += 1
                mat[lst[j], lst[i]] += 1
    return mat


def permutation_null(paper_entities_idx, entity_freqs, n_entities, rng):
    """Run N_PERMUTATIONS permutations; return mean and std of co-occurrence for each pair.

    Vectorized approach: build binary paper×entity matrix X per permutation,
    then X.T @ X gives co-occurrence in one BLAS call (no Python pair loops).

    paper_entities_idx: list of arrays of entity indices (per paper)
    entity_freqs: array of entity frequencies (length n_entities)
    n_entities: total number of entities in this cluster's vocabulary

    Returns:
        null_mean: (n_entities, n_entities) mean co-occurrence under null
        null_std:  (n_entities, n_entities) std co-occurrence under null
    """
    n_papers = len(paper_entities_idx)
    paper_sizes = np.array([len(e) for e in paper_entities_idx], dtype=np.int32)

    # Flat pool: each entity token appears entity_freqs[e] times
    pool = np.repeat(np.arange(n_entities, dtype=np.int32), entity_freqs.astype(int))
    pool_size = len(pool)

    # Accumulate sum and sum-of-squares of co-occurrence matrices
    pair_sums = np.zeros((n_entities, n_entities), dtype=np.float64)
    pair_sum2 = np.zeros((n_entities, n_entities), dtype=np.float64)

    for _ in range(N_PERMUTATIONS):
        rng.shuffle(pool)

        # Build binary paper×entity matrix from shuffled pool
        X = np.zeros((n_papers, n_entities), dtype=np.float32)
        pos = 0
        for pi, sz in enumerate(paper_sizes):
            chunk = pool[pos: pos + sz]
            pos += sz
            # Use np.unique to deduplicate entity tokens within a paper
            uniq = np.unique(chunk)
            X[pi, uniq] = 1.0

        # Co-occurrence: X.T @ X  shape (n_entities, n_entities)
        # Diagonal is entity self-co-occurrence (same paper), not needed
        comat = X.T @ X  # BLAS sgemm — fast
        np.fill_diagonal(comat, 0.0)

        pair_sums += comat
        pair_sum2 += comat ** 2

    null_mean = pair_sums / N_PERMUTATIONS
    null_std = np.sqrt(np.maximum(pair_sum2 / N_PERMUTATIONS - null_mean ** 2, 0.0))
    return null_mean, null_std


def analyze_cluster(cid, dois, entity_data, rng):
    """Run permutation null model for one cluster; return z-score gaps."""
    n = len(dois)

    # Entity frequency within cluster
    entity_freq = Counter()
    for doi in dois:
        for e in entity_data.get(doi, set()):
            entity_freq[e] += 1

    # Frequent entities (freq >= 5, same threshold as e015)
    frequent_entities = [e for e, c in entity_freq.items() if c >= 5]

    # Subsample to top MAX_ENTITIES by frequency if needed
    if len(frequent_entities) > MAX_ENTITIES:
        frequent_entities = sorted(
            frequent_entities, key=lambda e: -entity_freq[e]
        )[:MAX_ENTITIES]
        print(f"  C{cid}: subsampled to top {MAX_ENTITIES} entities")

    if len(frequent_entities) < 2:
        return [], 0

    entity_index = {e: i for i, e in enumerate(frequent_entities)}
    n_entities = len(frequent_entities)

    # Build per-paper entity index lists (only frequent entities)
    paper_entities_idx = []
    for doi in dois:
        ents = entity_data.get(doi, set())
        idx_set = [entity_index[e] for e in ents if e in entity_index]
        paper_entities_idx.append(np.array(sorted(idx_set), dtype=np.int32))

    # Observed co-occurrence matrix
    obs_mat = build_cooccur_matrix(paper_entities_idx, frequent_entities)

    # Entity freq array for pool construction
    freq_arr = np.array([entity_freq[e] for e in frequent_entities], dtype=np.int32)

    # Permutation null
    null_mean, null_std = permutation_null(paper_entities_idx, freq_arr, n_entities, rng)

    # Z-scores for all pairs with expected > 5 (consistent with e015 threshold)
    gaps = []
    for i in range(n_entities):
        for j in range(i + 1, n_entities):
            expected = entity_freq[frequent_entities[i]] * entity_freq[frequent_entities[j]] / n
            if expected < 5:
                continue
            observed = int(obs_mat[i, j])
            ratio = observed / expected if expected > 0 else 0.0

            mean_null = null_mean[i, j]
            std_null = null_std[i, j]

            if std_null < 1e-9:
                # No variance in null — skip (observed = null mean always)
                continue

            z = (observed - mean_null) / std_null
            gaps.append({
                "cluster": f"C{cid}",
                "entity_a": frequent_entities[i],
                "entity_b": frequent_entities[j],
                "observed": observed,
                "expected_independence": round(float(expected), 3),
                "null_mean": round(float(mean_null), 4),
                "null_std": round(float(std_null), 4),
                "z": round(float(z), 4),
                "ratio": round(float(ratio), 4),
            })

    return gaps, n_entities


def main():
    print("=" * 60)
    print("e021: T3 Z-Score Novelty Ranking")
    print(f"N_PERMUTATIONS={N_PERMUTATIONS}, MAX_ENTITIES={MAX_ENTITIES}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    papers, clusters = load_data()
    print(f"Loaded {len(papers)} papers, {len(clusters)} cluster assignments")

    entity_data = extract_entities(papers)
    print(f"Entity extraction done: {len(entity_data)} papers")

    # Group DOIs by cluster (same logic as e015)
    cluster_dois = defaultdict(list)
    for doi, cid in clusters.items():
        if doi in entity_data:
            cluster_dois[cid].append(doi)

    # Filter clusters with >= 20 papers (same as e015)
    valid_clusters = {cid: dois for cid, dois in cluster_dois.items() if len(dois) >= 20}
    print(f"Clusters with >= 20 papers: {sorted(valid_clusters.keys())}")

    rng = np.random.default_rng(42)

    # ── Run permutation null per cluster ──────────────────────────────
    all_gaps = []  # all pairs with expected > 5 and std_null > 0
    n_clusters_analyzed = 0

    for cid in sorted(valid_clusters.keys()):
        dois = valid_clusters[cid]
        print(f"\nAnalyzing C{cid} ({len(dois)} papers)...")
        gaps, n_ent = analyze_cluster(cid, dois, entity_data, rng)
        n_clusters_analyzed += 1
        z_sig2 = [g for g in gaps if g["z"] < -2]
        z_sig3 = [g for g in gaps if g["z"] < -3]
        print(f"  C{cid}: {n_ent} entities, {len(gaps)} pairs tested, "
              f"{len(z_sig2)} z<-2 gaps, {len(z_sig3)} z<-3 gaps")
        all_gaps.extend(gaps)

    # ── Z-score gaps (z < -2 and z < -3) ─────────────────────────────
    z2_gaps = [g for g in all_gaps if g["z"] < -2]
    z3_gaps = [g for g in all_gaps if g["z"] < -3]

    clusters_with_z2 = sorted(set(g["cluster"] for g in z2_gaps))
    top10_z2 = sorted(z2_gaps, key=lambda g: g["z"])[:10]

    print(f"\nZ-score gaps summary:")
    print(f"  Total pairs tested: {len(all_gaps)}")
    print(f"  z < -2: {len(z2_gaps)} gaps in clusters {clusters_with_z2}")
    print(f"  z < -3: {len(z3_gaps)} gaps")

    # ── Ratio-based gaps (replicate e015 logic) ───────────────────────
    ratio_gaps = [g for g in all_gaps if g["ratio"] < 0.2]
    clusters_with_ratio = sorted(set(g["cluster"] for g in ratio_gaps))

    print(f"\nRatio-based gaps (ratio < 0.2):")
    print(f"  Total: {len(ratio_gaps)} gaps in clusters {clusters_with_ratio}")

    # ── Comparison ────────────────────────────────────────────────────
    z2_cluster_set = set(clusters_with_z2)
    ratio_cluster_set = set(clusters_with_ratio)
    additional_clusters = z2_cluster_set - ratio_cluster_set
    additional_clusters_covered = len(additional_clusters)

    print(f"\nAdditional clusters covered by z-score (not in ratio): "
          f"{additional_clusters_covered} → {sorted(additional_clusters)}")

    # Spearman correlation on overlapping pairs
    # Match pairs by (cluster, entity_a, entity_b)
    ratio_lookup = {(g["cluster"], g["entity_a"], g["entity_b"]): g["ratio"] for g in ratio_gaps}
    # Also include all pairs that appear in both
    paired_z = []
    paired_ratio = []
    for g in all_gaps:
        key = (g["cluster"], g["entity_a"], g["entity_b"])
        # ratio-based score: use negative ratio so correlation with z makes sense
        paired_z.append(g["z"])
        paired_ratio.append(g["ratio"])

    overlapping_pairs = len(paired_z)
    if overlapping_pairs >= 3:
        rho, pval = spearmanr(paired_z, paired_ratio)
    else:
        rho, pval = float("nan"), float("nan")

    print(f"Spearman correlation (z vs ratio, {overlapping_pairs} pairs): "
          f"rho={rho:.4f}, p={pval:.4e}")

    # ── Verdict ───────────────────────────────────────────────────────
    verdict = "GO" if additional_clusters_covered >= 2 else "NO-GO"
    print(f"\nVerdict: {verdict} "
          f"(additional_clusters_covered={additional_clusters_covered}, threshold>=2)")

    # ── Save results ──────────────────────────────────────────────────
    results = {
        "experiment": "e021",
        "title": "T3 z-score Novelty",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "null_model": {
            "n_permutations": N_PERMUTATIONS,
            "n_clusters_analyzed": n_clusters_analyzed,
            "max_entities_per_cluster": MAX_ENTITIES,
        },
        "z_score_gaps": {
            "total_pairs_tested": len(all_gaps),
            "significant_gaps_z2": len(z2_gaps),
            "significant_gaps_z3": len(z3_gaps),
            "clusters_with_z2_gaps": clusters_with_z2,
            "top_10_gaps": top10_z2,
        },
        "ratio_gaps": {
            "total": len(ratio_gaps),
            "clusters_with_gaps": clusters_with_ratio,
        },
        "comparison": {
            "additional_clusters_covered": additional_clusters_covered,
            "additional_clusters": sorted(additional_clusters),
            "overlapping_pairs": overlapping_pairs,
            "spearman_rho": round(float(rho), 6) if not (rho != rho) else None,
            "spearman_p": round(float(pval), 6) if not (pval != pval) else None,
        },
        "verdict": verdict,
    }

    out_path = OUTPUT_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
