#!/usr/bin/env python3
"""e029 T1: 3-way comparison (topics-only / abstract-only / topics+abstract) on gut-microbiome."""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from collections import defaultdict
from itertools import combinations
from papersift.entity_layer import EntityLayerBuilder

DATA = "results/gut-microbiome-sweep/papers.json"
OUTPUT = "outputs/e029/t1_3way_comparison.json"
SEEDS = [42, 43, 44, 45, 46]
RESOLUTION = 1.0


def load_papers():
    with open(DATA) as f:
        return json.load(f)


def run_arm(papers, use_topics, use_abstract, seed):
    builder = EntityLayerBuilder(use_topics=use_topics, use_abstract=use_abstract)
    graph = builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=RESOLUTION, seed=seed)

    # Metrics
    total = len(clusters)
    cluster_sizes = defaultdict(int)
    for cid in clusters.values():
        cluster_sizes[cid] += 1

    singletons = sum(1 for s in cluster_sizes.values() if s == 1)
    singleton_pct = singletons / total * 100 if total > 0 else 0
    n_clusters = len(cluster_sizes)
    major_clusters = sum(1 for s in cluster_sizes.values() if s >= 10)

    # Entities per paper
    pe = builder.paper_entities
    entities_per_paper = [len(pe.get(doi, set())) for doi in clusters]
    avg_entities = sum(entities_per_paper) / len(entities_per_paper) if entities_per_paper else 0

    # Modularity
    modularity = graph.modularity(
        [clusters[graph.vs[i]['doi']] for i in range(len(graph.vs))],
        weights='weight'
    )

    return {
        "total_papers": total,
        "n_clusters": n_clusters,
        "major_clusters": major_clusters,
        "singletons": singletons,
        "singleton_pct": round(singleton_pct, 2),
        "avg_entities_per_paper": round(avg_entities, 2),
        "modularity": round(modularity, 4),
        "cluster_sizes": dict(sorted(
            {str(k): v for k, v in cluster_sizes.items()}.items(),
            key=lambda x: -x[1]
        )),
        "clusters": clusters,
    }


def co_clustering_preservation(clusters_a, clusters_b):
    """Fraction of paper-pairs that remain co-clustered."""
    dois = sorted(set(clusters_a.keys()) & set(clusters_b.keys()))
    if len(dois) < 2:
        return 1.0

    # Sample pairs for large datasets (cap at 50k pairs)
    import random
    rng = random.Random(99)
    all_pairs = list(combinations(range(len(dois)), 2))
    if len(all_pairs) > 50000:
        all_pairs = rng.sample(all_pairs, 50000)

    same = 0
    total = 0
    for i, j in all_pairs:
        d1, d2 = dois[i], dois[j]
        a_same = clusters_a[d1] == clusters_a[d2]
        b_same = clusters_b[d1] == clusters_b[d2]
        if a_same:
            total += 1
            if b_same:
                same += 1

    return same / total if total > 0 else 1.0


def main():
    papers = load_papers()
    print(f"Loaded {len(papers)} papers")

    arms = {
        "A_topics_only": {"use_topics": True, "use_abstract": False},
        "B_abstract_only": {"use_topics": False, "use_abstract": True},
        "C_topics_abstract": {"use_topics": True, "use_abstract": True},
    }

    results = {}
    for arm_name, params in arms.items():
        print(f"\n=== {arm_name} ===")
        arm_results = []
        for seed in SEEDS:
            r = run_arm(papers, **params, seed=seed)
            clusters = r.pop("clusters")
            r["seed"] = seed
            arm_results.append({"metrics": r, "clusters": clusters})
            print(f"  seed={seed}: singletons={r['singleton_pct']}%, entities/paper={r['avg_entities_per_paper']}, clusters={r['n_clusters']}, modularity={r['modularity']}")

        # Stability: co-clustering preservation across seed pairs
        preservations = []
        for i in range(len(SEEDS)):
            for j in range(i + 1, len(SEEDS)):
                p = co_clustering_preservation(
                    arm_results[i]["clusters"],
                    arm_results[j]["clusters"]
                )
                preservations.append(round(p * 100, 2))

        avg_pres = round(sum(preservations) / len(preservations), 2) if preservations else 0
        min_pres = min(preservations) if preservations else 0

        # Average metrics across seeds
        avg_metrics = {}
        for key in arm_results[0]["metrics"]:
            if key in ("seed", "cluster_sizes"):
                continue
            vals = [r["metrics"][key] for r in arm_results]
            avg_metrics[key] = round(sum(vals) / len(vals), 2)

        results[arm_name] = {
            "params": params,
            "avg_metrics": avg_metrics,
            "stability": {
                "preservations": preservations,
                "avg_preservation": avg_pres,
                "min_preservation": min_pres,
                "pass_avg": avg_pres >= 80,
                "pass_min": min_pres >= 70,
            },
            "per_seed": [{
                "seed": r["metrics"]["seed"],
                "singleton_pct": r["metrics"]["singleton_pct"],
                "avg_entities_per_paper": r["metrics"]["avg_entities_per_paper"],
                "n_clusters": r["metrics"]["n_clusters"],
                "modularity": r["metrics"]["modularity"],
            } for r in arm_results],
        }

    # --- GO/NO-GO judgment ---
    baseline = results["A_topics_only"]["avg_metrics"]

    judgments = {}
    for arm_name in ["B_abstract_only", "C_topics_abstract"]:
        arm = results[arm_name]["avg_metrics"]
        singleton_delta = baseline["singleton_pct"] - arm["singleton_pct"]
        entity_delta_pct = ((arm["avg_entities_per_paper"] - baseline["avg_entities_per_paper"])
                            / baseline["avg_entities_per_paper"] * 100
                            if baseline["avg_entities_per_paper"] > 0 else 0)
        modularity_delta = arm["modularity"] - baseline["modularity"]

        and_pass = singleton_delta >= 5 and entity_delta_pct >= 20
        or_pass = singleton_delta >= 5 or entity_delta_pct >= 20
        stability = results[arm_name]["stability"]

        judgments[arm_name] = {
            "singleton_delta_pp": round(singleton_delta, 2),
            "entity_increase_pct": round(entity_delta_pct, 2),
            "modularity_delta": round(modularity_delta, 4),
            "modularity_warning": abs(modularity_delta) >= 0.05,
            "and_pass": and_pass,
            "or_pass": or_pass,
            "stability_pass": stability["pass_avg"] and stability["pass_min"],
        }

    # Best arm selection
    best_arm = "A_topics_only"
    for arm_name in ["C_topics_abstract", "B_abstract_only"]:
        j = judgments[arm_name]
        if j["and_pass"] and j["stability_pass"]:
            best_arm = arm_name
            break
        elif j["or_pass"] and j["stability_pass"] and best_arm == "A_topics_only":
            best_arm = arm_name

    # Overall verdict
    best_j = judgments.get(best_arm)
    if best_arm == "A_topics_only":
        verdict = "NO-GO"
        verdict_detail = "No arm improved over baseline"
    elif best_j and best_j["and_pass"] and best_j["stability_pass"]:
        verdict = "GO"
        verdict_detail = f"{best_arm} passes AND condition + stability"
    elif best_j and best_j["or_pass"] and best_j["stability_pass"]:
        verdict = "CONDITIONAL"
        verdict_detail = f"{best_arm} passes OR condition only + stability"
    else:
        verdict = "NO-GO"
        verdict_detail = "No stable improvement found"

    output = {
        "experiment": "e029-T1",
        "dataset": DATA,
        "n_papers": len(papers),
        "resolution": RESOLUTION,
        "seeds": SEEDS,
        "arms": results,
        "judgments": judgments,
        "best_arm": best_arm,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
    }

    # Remove per-seed cluster assignments (too large for JSON)
    for arm in output["arms"].values():
        if "per_seed_clusters" in arm:
            del arm["per_seed_clusters"]

    with open(OUTPUT, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict} — {verdict_detail}")
    print(f"Best arm: {best_arm}")
    for arm_name, j in judgments.items():
        print(f"  {arm_name}: singleton Δ={j['singleton_delta_pp']}pp, entity +{j['entity_increase_pct']}%, AND={j['and_pass']}, OR={j['or_pass']}, stable={j['stability_pass']}")
    print(f"Results saved to {OUTPUT}")


if __name__ == "__main__":
    main()
