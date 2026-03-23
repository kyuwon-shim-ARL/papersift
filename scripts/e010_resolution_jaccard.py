#!/usr/bin/env python3
"""e010: Resolution sweep (T0) + Jaccard weighting A/B (T1).

T0: Sweep resolution 1.0/1.2/1.4/1.6/2.0 on e009 Arm B data.
    Lexicographic selection: (1) abstract-length r < 0.50,
    (2) major cluster preservation >= 90%, (3) cluster count closest to baseline(13).

T1: At selected resolution, compare raw count vs Jaccard edge weighting.
    Success: preservation overlap>=0.6 AND Jaccard>=0.3, ARI>=0.7.
    Kill: preservation<80% OR ARI<0.5 OR abstract-length r increases.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, EntityLayerBuilder, ImprovedEntityExtractor

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e010"
SEED = 42
BASELINE_CLUSTER_COUNT = 13  # Arm A at resolution 1.0


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def extract_arm_a(papers, extractor):
    result = {}
    for p in papers:
        entities = extractor.extract_entities(p["title"], p.get("category", ""))
        entity_set = {e["name"].lower() for e in entities}
        result[p["doi"]] = {"entities": entity_set}
    return result


def extract_arm_b(papers, extractor, arm_a_result):
    all_patterns = (
        [(m, p, "METHOD") for m, p in extractor.method_patterns]
        + [(o, p, "ORGANISM") for o, p in extractor.organism_patterns]
        + [(c, p, "CONCEPT") for c, p in extractor.concept_patterns]
        + [(d, p, "DATASET") for d, p in extractor.dataset_patterns]
    )
    result = {}
    for p in papers:
        doi = p["doi"]
        entity_set = set(arm_a_result[doi]["entities"])
        abstract = p.get("abstract", "")
        if abstract:
            for name, pattern, etype in all_patterns:
                key = name.lower()
                if key in STOPWORDS:
                    continue
                if key not in entity_set and pattern.search(abstract):
                    entity_set.add(key)
        result[doi] = {"entities": entity_set}
    return result


def build_graph_and_cluster(papers, entity_data, resolution, seed=SEED, weight_mode="raw"):
    """Build graph and cluster. weight_mode: 'raw' or 'jaccard'."""
    import igraph as ig

    dois = [p["doi"] for p in papers]
    n = len(dois)
    edges = []
    weights = []

    for i in range(n):
        ents1 = entity_data[dois[i]]["entities"]
        for j in range(i + 1, n):
            ents2 = entity_data[dois[j]]["entities"]
            shared = len(ents1 & ents2)
            if shared > 0:
                if weight_mode == "jaccard":
                    union = len(ents1 | ents2)
                    w = shared / union if union > 0 else 0
                else:
                    w = shared
                edges.append((i, j))
                weights.append(w)

    g = ig.Graph(n=n, edges=edges, directed=False)
    g.vs["doi"] = dois
    g.es["weight"] = weights

    import leidenalg
    partition = leidenalg.find_partition(
        g, leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution, weights="weight", seed=seed,
    )
    clusters = {dois[i]: partition.membership[i] for i in range(n)}
    return clusters, edges, weights


def compute_cluster_metrics(clusters):
    sizes = Counter(clusters.values())
    major = {cid: sz for cid, sz in sizes.items() if sz >= 5}
    singletons = sum(1 for sz in sizes.values() if sz == 1)
    return {
        "cluster_count": len(sizes),
        "major_count": len(major),
        "major_sizes": sorted(major.values(), reverse=True),
        "singleton_count": singletons,
    }


def compute_abstract_length_r(papers, entity_data_a, entity_data_b):
    """Correlation between abstract length and new entity count."""
    lengths, deltas = [], []
    for p in papers:
        abstract = p.get("abstract", "")
        if not abstract:
            continue
        doi = p["doi"]
        new_count = len(entity_data_b[doi]["entities"]) - len(entity_data_a[doi]["entities"])
        lengths.append(len(abstract))
        deltas.append(new_count)
    if len(lengths) < 3:
        return 0.0
    return float(np.corrcoef(lengths, deltas)[0, 1])


def compute_preservation(clusters_base, clusters_test, papers):
    """Dual preservation: overlap >= 0.6 AND Jaccard >= 0.3."""
    base_members = defaultdict(set)
    for p in papers:
        base_members[clusters_base[p["doi"]]].add(p["doi"])

    major = {cid: m for cid, m in base_members.items() if len(m) >= 5}
    if not major:
        return {"rate": 1.0, "count": 0, "preserved": 0, "details": []}

    preserved = 0
    details = []
    for cid, members in sorted(major.items(), key=lambda x: -len(x[1])):
        b_counts = Counter(clusters_test[d] for d in members)
        best_cid, best_n = b_counts.most_common(1)[0]
        b_members = {d for d, c in clusters_test.items() if c == best_cid}
        overlap = best_n / len(members)
        intersection = len(members & b_members)
        union = len(members | b_members)
        jaccard = intersection / union if union > 0 else 0
        is_preserved = overlap >= 0.6 and jaccard >= 0.3
        if is_preserved:
            preserved += 1
        details.append({
            "base_cluster": cid, "size": len(members),
            "best_match": best_cid, "overlap": round(overlap, 3),
            "jaccard": round(jaccard, 3), "preserved": is_preserved,
        })

    return {
        "rate": round(preserved / len(major), 3),
        "count": len(major), "preserved": preserved, "details": details,
    }


def compute_abstract_partition(papers, entity_data, clusters):
    """Report cluster distribution for abstract有 vs 無 papers."""
    has_abs = [p for p in papers if p.get("abstract")]
    no_abs = [p for p in papers if not p.get("abstract")]

    def dist(paper_list):
        c = Counter(clusters[p["doi"]] for p in paper_list)
        sizes = Counter(c.values())
        return {
            "paper_count": len(paper_list),
            "mean_entities": round(float(np.mean([len(entity_data[p["doi"]]["entities"]) for p in paper_list])), 2) if paper_list else 0,
            "cluster_spread": len(c),
            "singleton_pct": round(sum(1 for p in paper_list if Counter(clusters[pp["doi"]] for pp in paper_list)[clusters[p["doi"]]] == 1) / len(paper_list) * 100, 1) if paper_list else 0,
        }

    return {"has_abstract": dist(has_abs), "no_abstract": dist(no_abs)}


def run_t0(papers, entity_data_a, entity_data_b):
    """T0: Resolution sweep on Arm B."""
    print("=" * 60)
    print("T0: Resolution Sweep (e009 Arm B)")
    print("=" * 60)

    resolutions = [1.0, 1.2, 1.4, 1.6, 2.0]
    r_value = compute_abstract_length_r(papers, entity_data_a, entity_data_b)
    print(f"\nAbstract-length bias r = {r_value:.3f} (constant across resolutions)")

    # Baseline: Arm A at resolution 1.0
    clusters_baseline, _, _ = build_graph_and_cluster(papers, entity_data_a, 1.0)
    baseline_metrics = compute_cluster_metrics(clusters_baseline)
    print(f"Baseline (Arm A, res=1.0): {baseline_metrics['cluster_count']} clusters, "
          f"{baseline_metrics['major_count']} major(>=5), {baseline_metrics['singleton_count']} singletons")

    sweep_results = []
    for res in resolutions:
        clusters, edges, weights = build_graph_and_cluster(papers, entity_data_b, res)
        metrics = compute_cluster_metrics(clusters)
        preservation = compute_preservation(clusters_baseline, clusters, papers)

        result = {
            "resolution": res,
            "cluster_count": metrics["cluster_count"],
            "major_count": metrics["major_count"],
            "major_sizes": metrics["major_sizes"],
            "singleton_count": metrics["singleton_count"],
            "abstract_length_r": round(r_value, 3),
            "preservation": preservation,
        }
        sweep_results.append(result)

        print(f"\n  res={res}: clusters={metrics['cluster_count']}, "
              f"major={metrics['major_count']}, singletons={metrics['singleton_count']}, "
              f"preservation={preservation['rate']:.1%} ({preservation['preserved']}/{preservation['count']})")

    # Lexicographic selection
    print("\n--- Lexicographic Selection ---")
    print("  Priority: (1) r < 0.50, (2) major preservation >= 90%, (3) cluster count closest to baseline")

    candidates = sweep_results  # r is constant, so all pass criterion 1 if r < 0.50
    r_pass = r_value < 0.50
    print(f"  (1) r = {r_value:.3f} {'< 0.50 PASS' if r_pass else '>= 0.50 FAIL'}")

    # Filter by preservation >= 90%
    candidates = [r for r in candidates if r["preservation"]["rate"] >= 0.90]
    print(f"  (2) Preservation >= 90%: {len(candidates)}/{len(sweep_results)} pass")

    if candidates:
        # Select closest to baseline cluster count
        candidates.sort(key=lambda r: (abs(r["cluster_count"] - BASELINE_CLUSTER_COUNT), r["resolution"]))
        selected = candidates[0]
    else:
        # Fallback: best preservation, lowest resolution
        sweep_results.sort(key=lambda r: (-r["preservation"]["rate"], r["resolution"]))
        selected = sweep_results[0]
        print("  WARNING: No resolution meets preservation >= 90%, using best available")

    print(f"  (3) Selected: resolution={selected['resolution']} "
          f"(clusters={selected['cluster_count']}, Δ={abs(selected['cluster_count'] - BASELINE_CLUSTER_COUNT)} from baseline)")

    return sweep_results, selected


def run_t1(papers, entity_data_a, entity_data_b, selected_resolution):
    """T1: Jaccard vs raw count A/B at selected resolution."""
    print("\n" + "=" * 60)
    print(f"T1: Jaccard A/B (resolution={selected_resolution})")
    print("=" * 60)

    from sklearn.metrics import adjusted_rand_score

    # Arm A: raw count (baseline for this comparison)
    clusters_raw, edges_raw, weights_raw = build_graph_and_cluster(
        papers, entity_data_b, selected_resolution, weight_mode="raw")
    metrics_raw = compute_cluster_metrics(clusters_raw)

    # Arm B: Jaccard weighting
    clusters_jac, edges_jac, weights_jac = build_graph_and_cluster(
        papers, entity_data_b, selected_resolution, weight_mode="jaccard")
    metrics_jac = compute_cluster_metrics(clusters_jac)

    # ARI
    dois = [p["doi"] for p in papers]
    labels_raw = [clusters_raw[d] for d in dois]
    labels_jac = [clusters_jac[d] for d in dois]
    ari = adjusted_rand_score(labels_raw, labels_jac)

    # Preservation (raw as base, jaccard as test)
    preservation = compute_preservation(clusters_raw, clusters_jac, papers)

    # Abstract-length bias for both
    r_raw = compute_abstract_length_r(papers, entity_data_a, entity_data_b)

    # Weight distribution
    w_raw_1pct = round(Counter(weights_raw).get(1, 0) / len(weights_raw) * 100, 1) if weights_raw else 0
    w_jac_dist = np.array(weights_jac) if weights_jac else np.array([0])

    # Abstract partition stability
    partition_raw = compute_abstract_partition(papers, entity_data_b, clusters_raw)
    partition_jac = compute_abstract_partition(papers, entity_data_b, clusters_jac)

    print(f"\n  Raw count: {metrics_raw['cluster_count']} clusters, "
          f"{metrics_raw['major_count']} major, weight_1_pct={w_raw_1pct}%")
    print(f"  Jaccard:   {metrics_jac['cluster_count']} clusters, "
          f"{metrics_jac['major_count']} major, weight_mean={w_jac_dist.mean():.3f}")
    print(f"  ARI: {ari:.4f}")
    print(f"  Preservation: {preservation['rate']:.1%} ({preservation['preserved']}/{preservation['count']})")
    for d in preservation["details"]:
        status = "Y" if d["preserved"] else "N"
        print(f"    [{status}] C{d['base_cluster']}(n={d['size']}) → C{d['best_match']} "
              f"overlap={d['overlap']:.3f} jaccard={d['jaccard']:.3f}")

    # GO/NO-GO
    pres_pass = preservation["rate"] >= 0.80
    ari_pass = ari >= 0.50
    kill = not pres_pass or not ari_pass

    if kill:
        verdict = "KILL — Jaccard폐기, raw count 유지"
    elif ari >= 0.7 and preservation["rate"] >= 0.80:
        verdict = "GO — Jaccard 채택"
    else:
        verdict = "CONDITIONAL — Jaccard marginal"

    print(f"\n  >>> T1 VERDICT: {verdict} <<<")
    print(f"      preservation={preservation['rate']:.1%} (threshold 80%), "
          f"ARI={ari:.4f} (threshold 0.5/0.7)")

    return {
        "resolution": selected_resolution,
        "raw": {"metrics": metrics_raw, "weight_1_pct": w_raw_1pct, "partition": partition_raw},
        "jaccard": {
            "metrics": metrics_jac,
            "weight_mean": round(float(w_jac_dist.mean()), 4),
            "weight_median": round(float(np.median(w_jac_dist)), 4),
            "partition": partition_jac,
        },
        "ari": round(ari, 4),
        "preservation": preservation,
        "abstract_length_r": round(r_raw, 3),
        "verdict": verdict,
    }


def main():
    papers = load_papers()
    print(f"Loaded {len(papers)} papers ({sum(1 for p in papers if p.get('abstract'))} with abstracts)")

    extractor = ImprovedEntityExtractor()
    arm_a = extract_arm_a(papers, extractor)
    arm_b = extract_arm_b(papers, extractor, arm_a)

    # T0: Resolution sweep
    sweep_results, selected = run_t0(papers, arm_a, arm_b)

    # T1: Jaccard A/B at selected resolution
    t1_results = run_t1(papers, arm_a, arm_b, selected["resolution"])

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e010",
        "description": "T0 resolution sweep + T1 Jaccard A/B",
        "dataset": str(DATA_PATH),
        "seed": SEED,
        "baseline_cluster_count": BASELINE_CLUSTER_COUNT,
        "t0_sweep": sweep_results,
        "t0_selected": selected,
        "t1_jaccard_ab": t1_results,
    }
    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
