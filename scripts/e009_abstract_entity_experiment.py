#!/usr/bin/env python3
"""e009: Abstract predefined-entity enrichment — additive 2-arm experiment.

Arm A: title predefined + title heuristic (baseline, current code)
Arm B: Arm A ∪ {abstract predefined matches, STOPWORDS filtered}

GO criteria:
  - predefined entity mean >= 30% increase
  - low-entity (<=1) paper count decreases
  - cluster preservation >= 80%
  - ARI 0.5-0.9
  - cluster count change <= 30%
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, EntityLayerBuilder, ImprovedEntityExtractor

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e009"

RESOLUTION = 1.0
SEED = 42


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def extract_arm_a(papers, extractor):
    """Arm A: current baseline (title predefined + title heuristic)."""
    result = {}
    for p in papers:
        entities = extractor.extract_entities(p["title"], p.get("category", ""))
        entity_set = {e["name"].lower() for e in entities}
        entity_types = {e["name"].lower(): e["type"] for e in entities}
        result[p["doi"]] = {"entities": entity_set, "types": entity_types}
    return result


def extract_arm_b(papers, extractor, arm_a_result):
    """Arm B: Arm A ∪ {abstract predefined matches, STOPWORDS filtered}.

    Additive only — no entity is removed from Arm A.
    Only predefined patterns matched on abstract; no heuristic on abstract.
    STOPWORDS applied to filter generic terms from abstract matches.
    """
    all_patterns = (
        [(m, p, "METHOD") for m, p in extractor.method_patterns]
        + [(o, p, "ORGANISM") for o, p in extractor.organism_patterns]
        + [(c, p, "CONCEPT") for c, p in extractor.concept_patterns]
        + [(d, p, "DATASET") for d, p in extractor.dataset_patterns]
    )

    result = {}
    abstract_additions = {}

    for p in papers:
        doi = p["doi"]
        base = arm_a_result[doi]
        entity_set = set(base["entities"])
        entity_types = dict(base["types"])
        added = set()

        abstract = p.get("abstract", "")
        if abstract:
            for name, pattern, etype in all_patterns:
                key = name.lower()
                if key in STOPWORDS:
                    continue  # STOPWORDS filter on abstract matches
                if key not in entity_set and pattern.search(abstract):
                    entity_set.add(key)
                    entity_types[key] = etype
                    added.add(key)

        result[doi] = {"entities": entity_set, "types": entity_types}
        abstract_additions[doi] = added

    return result, abstract_additions


def build_graph_and_cluster(papers, entity_data):
    """Build graph from entity data and run Leiden clustering."""
    builder = EntityLayerBuilder()
    builder._dois = [p["doi"] for p in papers]
    builder._paper_entities = {doi: data["entities"] for doi, data in entity_data.items()}

    # Build edges
    n = len(builder._dois)
    edges = []
    weights = []
    for i in range(n):
        doi1 = builder._dois[i]
        ents1 = builder._paper_entities[doi1]
        for j in range(i + 1, n):
            doi2 = builder._dois[j]
            ents2 = builder._paper_entities[doi2]
            shared = len(ents1 & ents2)
            if shared > 0:
                edges.append((i, j))
                weights.append(shared)

    import igraph as ig
    builder.graph = ig.Graph(n=n, edges=edges, directed=False)
    builder.graph.vs["doi"] = builder._dois
    builder.graph.es["weight"] = weights

    clusters = builder.run_leiden(resolution=RESOLUTION, seed=SEED)
    return builder, clusters, edges, weights


def compute_entity_stats(entity_data, papers):
    """Compute entity-level statistics."""
    all_counts = []
    predefined_counts = []
    heuristic_counts = []
    type_counter = Counter()
    entity_doc_freq = Counter()
    low_entity = 0

    for p in papers:
        doi = p["doi"]
        data = entity_data[doi]
        ents = data["entities"]
        types = data["types"]

        all_counts.append(len(ents))
        pred = sum(1 for e in ents if types.get(e, "METHOD") in ("METHOD", "ORGANISM", "CONCEPT", "DATASET")
                   and e in {name.lower() for name, _ in ImprovedEntityExtractor().method_patterns}
                   or e in {name.lower() for name, _ in ImprovedEntityExtractor().organism_patterns}
                   or e in {name.lower() for name, _ in ImprovedEntityExtractor().concept_patterns}
                   or e in {name.lower() for name, _ in ImprovedEntityExtractor().dataset_patterns})

        # Simpler: count by whether entity is in predefined lists
        predefined_set = _get_predefined_set()
        n_pred = sum(1 for e in ents if e in predefined_set)
        n_heur = len(ents) - n_pred

        predefined_counts.append(n_pred)
        heuristic_counts.append(n_heur)

        for e in ents:
            t = types.get(e, "UNKNOWN")
            type_counter[t] += 1
            entity_doc_freq[e] += 1

        if len(ents) <= 1:
            low_entity += 1

    return {
        "total_mean": float(np.mean(all_counts)),
        "total_median": float(np.median(all_counts)),
        "predefined_mean": float(np.mean(predefined_counts)),
        "predefined_median": float(np.median(predefined_counts)),
        "heuristic_mean": float(np.mean(heuristic_counts)),
        "low_entity_count": low_entity,
        "low_entity_pct": round(low_entity / len(papers) * 100, 1),
        "type_breakdown": dict(type_counter.most_common()),
        "top_universal_connectors": [
            {"entity": e, "doc_freq": c, "pct": round(c / len(papers) * 100, 1)}
            for e, c in entity_doc_freq.most_common(20)
            if c / len(papers) > 0.1
        ],
    }


_predefined_cache = None

def _get_predefined_set():
    global _predefined_cache
    if _predefined_cache is None:
        ext = ImprovedEntityExtractor()
        s = set()
        for name, _ in ext.method_patterns:
            s.add(name.lower())
        for name, _ in ext.organism_patterns:
            s.add(name.lower())
        for name, _ in ext.concept_patterns:
            s.add(name.lower())
        for name, _ in ext.dataset_patterns:
            s.add(name.lower())
        _predefined_cache = s
    return _predefined_cache


def compute_cluster_stats(clusters, edges, weights):
    """Compute cluster-level statistics."""
    cluster_ids = list(set(clusters.values()))
    cluster_sizes = Counter(clusters.values())
    size_dist = sorted(cluster_sizes.values(), reverse=True)

    n_papers = len(clusters)
    n_edges = len(edges)
    max_edges = n_papers * (n_papers - 1) / 2
    density = n_edges / max_edges if max_edges > 0 else 0

    weight_counter = Counter(weights)
    w1_pct = round(weight_counter.get(1, 0) / len(weights) * 100, 1) if weights else 0

    return {
        "cluster_count": len(cluster_ids),
        "size_distribution": size_dist,
        "edge_count": n_edges,
        "density": round(density, 4),
        "weight_1_pct": w1_pct,
        "weight_mean": round(float(np.mean(weights)), 2) if weights else 0,
    }


def compute_ari_nmi(clusters_a, clusters_b, papers):
    """Compute ARI and NMI between two clusterings."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    dois = [p["doi"] for p in papers]
    labels_a = [clusters_a[d] for d in dois]
    labels_b = [clusters_b[d] for d in dois]

    return {
        "ari": round(adjusted_rand_score(labels_a, labels_b), 4),
        "nmi": round(normalized_mutual_info_score(labels_a, labels_b), 4),
    }


def compute_cluster_preservation(clusters_a, clusters_b, papers):
    """Compute what fraction of major Arm A clusters are preserved in Arm B."""
    cluster_a_members = defaultdict(set)
    for p in papers:
        cluster_a_members[clusters_a[p["doi"]]].add(p["doi"])

    # Major clusters: size >= 5
    major_clusters = {cid: members for cid, members in cluster_a_members.items() if len(members) >= 5}

    if not major_clusters:
        return {"preservation_rate": 1.0, "major_cluster_count": 0, "details": []}

    preserved = 0
    details = []
    for cid, members in sorted(major_clusters.items(), key=lambda x: -len(x[1])):
        # Find best-matching Arm B cluster (max Jaccard)
        b_clusters_for_members = Counter(clusters_b[d] for d in members)
        best_b_cid, best_count = b_clusters_for_members.most_common(1)[0]

        # Jaccard: intersection / union
        b_members = {d for d in clusters_b if clusters_b[d] == best_b_cid}
        intersection = len(members & b_members)
        union = len(members | b_members)
        jaccard = intersection / union if union > 0 else 0

        # Preservation: >= 60% of A-cluster members in same B-cluster
        overlap_pct = best_count / len(members)
        is_preserved = overlap_pct >= 0.6
        if is_preserved:
            preserved += 1

        details.append({
            "arm_a_cluster": cid,
            "size": len(members),
            "best_arm_b_cluster": best_b_cid,
            "overlap_pct": round(overlap_pct, 3),
            "jaccard": round(jaccard, 3),
            "preserved": is_preserved,
        })

    return {
        "preservation_rate": round(preserved / len(major_clusters), 3),
        "major_cluster_count": len(major_clusters),
        "preserved_count": preserved,
        "details": details,
    }


def compute_edge_decomposition(papers, entity_data_a, entity_data_b, edges_b):
    """Decompose Arm B edges into title-origin vs abstract-origin contribution."""
    dois = [p["doi"] for p in papers]
    title_only_edges = 0
    abstract_contributed_edges = 0
    mixed_edges = 0

    for i, j in edges_b:
        doi1 = dois[i]
        doi2 = dois[j]

        ents_a1 = entity_data_a[doi1]["entities"]
        ents_a2 = entity_data_a[doi2]["entities"]
        ents_b1 = entity_data_b[doi1]["entities"]
        ents_b2 = entity_data_b[doi2]["entities"]

        shared_b = ents_b1 & ents_b2
        shared_a = ents_a1 & ents_a2

        if shared_b == shared_a:
            title_only_edges += 1
        elif not shared_a:
            abstract_contributed_edges += 1
        else:
            mixed_edges += 1

    total = len(edges_b)
    return {
        "title_only_edges": title_only_edges,
        "abstract_new_edges": abstract_contributed_edges,
        "mixed_edges": mixed_edges,
        "total_edges": total,
        "abstract_new_pct": round(abstract_contributed_edges / total * 100, 1) if total else 0,
    }


def compute_abstract_bias(papers, entity_data_a, entity_data_b):
    """Quantify abstract availability bias."""
    has_abstract = [p for p in papers if p.get("abstract")]
    no_abstract = [p for p in papers if not p.get("abstract")]

    def mean_entities(paper_list, data):
        return float(np.mean([len(data[p["doi"]]["entities"]) for p in paper_list])) if paper_list else 0

    delta_has = mean_entities(has_abstract, entity_data_b) - mean_entities(has_abstract, entity_data_a)
    delta_no = mean_entities(no_abstract, entity_data_b) - mean_entities(no_abstract, entity_data_a)

    # Abstract length correlation with new entities
    lengths = []
    new_ent_counts = []
    for p in has_abstract:
        doi = p["doi"]
        abstract_len = len(p.get("abstract", ""))
        new_ents = len(entity_data_b[doi]["entities"]) - len(entity_data_a[doi]["entities"])
        lengths.append(abstract_len)
        new_ent_counts.append(new_ents)

    corr = float(np.corrcoef(lengths, new_ent_counts)[0, 1]) if len(lengths) > 2 else 0

    return {
        "has_abstract_count": len(has_abstract),
        "no_abstract_count": len(no_abstract),
        "has_abstract_mean_delta": round(delta_has, 2),
        "no_abstract_mean_delta": round(delta_no, 2),
        "abstract_length_correlation": round(corr, 3),
        "has_abstract_arm_a_mean": round(mean_entities(has_abstract, entity_data_a), 2),
        "has_abstract_arm_b_mean": round(mean_entities(has_abstract, entity_data_b), 2),
        "no_abstract_arm_a_mean": round(mean_entities(no_abstract, entity_data_a), 2),
        "no_abstract_arm_b_mean": round(mean_entities(no_abstract, entity_data_b), 2),
    }


def go_nogo_判定(stats_a, stats_b, comparison, preservation):
    """Evaluate GO/NO-GO criteria."""
    criteria = {}

    # C1: predefined entity mean >= 30% increase
    pred_increase = (stats_b["predefined_mean"] - stats_a["predefined_mean"]) / stats_a["predefined_mean"] * 100 if stats_a["predefined_mean"] > 0 else 0
    criteria["C1_predefined_increase"] = {
        "value": round(pred_increase, 1),
        "threshold": 30,
        "pass": pred_increase >= 30,
    }

    # C2: low-entity count decreases
    criteria["C2_low_entity_reduction"] = {
        "arm_a": stats_a["low_entity_count"],
        "arm_b": stats_b["low_entity_count"],
        "pass": stats_b["low_entity_count"] < stats_a["low_entity_count"],
    }

    # C3: cluster preservation >= 80%
    criteria["C3_preservation"] = {
        "value": preservation["preservation_rate"],
        "threshold": 0.80,
        "pass": preservation["preservation_rate"] >= 0.80,
    }

    # C4: ARI 0.5-0.9
    ari = comparison["ari"]
    criteria["C4_ari_range"] = {
        "value": ari,
        "range": [0.5, 0.9],
        "pass": 0.5 <= ari <= 0.9,
    }

    # C5: cluster count change <= 30%
    count_a = stats_a["cluster_count"] if "cluster_count" in stats_a else 0
    count_b = stats_b["cluster_count"] if "cluster_count" in stats_b else 0
    if count_a > 0:
        change_pct = abs(count_b - count_a) / count_a * 100
    else:
        change_pct = 0
    criteria["C5_cluster_count_stability"] = {
        "arm_a": count_a,
        "arm_b": count_b,
        "change_pct": round(change_pct, 1),
        "threshold": 30,
        "pass": change_pct <= 30,
    }

    all_pass = all(c["pass"] for c in criteria.values())
    verdict = "GO" if all_pass else "NO-GO"

    # Conditional GO check
    if not all_pass and criteria["C3_preservation"]["pass"] and criteria["C4_ari_range"]["pass"]:
        verdict = "CONDITIONAL GO"

    return {"verdict": verdict, "criteria": criteria}


def main():
    print("=" * 60)
    print("e009: Abstract Predefined-Entity Enrichment Experiment")
    print("=" * 60)

    # Load data
    papers = load_papers()
    print(f"\nLoaded {len(papers)} papers ({sum(1 for p in papers if p.get('abstract'))} with abstracts)")

    extractor = ImprovedEntityExtractor()

    # === T1: Arm A baseline ===
    print("\n--- T1: Arm A (baseline) ---")
    arm_a = extract_arm_a(papers, extractor)
    builder_a, clusters_a, edges_a, weights_a = build_graph_and_cluster(papers, arm_a)
    stats_a_entity = compute_entity_stats(arm_a, papers)
    stats_a_cluster = compute_cluster_stats(clusters_a, edges_a, weights_a)
    print(f"  Entities: mean={stats_a_entity['total_mean']:.1f}, predefined_mean={stats_a_entity['predefined_mean']:.1f}")
    print(f"  Low-entity (<=1): {stats_a_entity['low_entity_count']} ({stats_a_entity['low_entity_pct']}%)")
    print(f"  Clusters: {stats_a_cluster['cluster_count']}, edges: {stats_a_cluster['edge_count']}, density: {stats_a_cluster['density']}")

    # === T2: Arm B ===
    print("\n--- T2: Arm B (+ abstract predefined, STOPWORDS filtered) ---")
    arm_b, abstract_adds = extract_arm_b(papers, extractor, arm_a)
    builder_b, clusters_b, edges_b, weights_b = build_graph_and_cluster(papers, arm_b)
    stats_b_entity = compute_entity_stats(arm_b, papers)
    stats_b_cluster = compute_cluster_stats(clusters_b, edges_b, weights_b)
    print(f"  Entities: mean={stats_b_entity['total_mean']:.1f}, predefined_mean={stats_b_entity['predefined_mean']:.1f}")
    print(f"  Low-entity (<=1): {stats_b_entity['low_entity_count']} ({stats_b_entity['low_entity_pct']}%)")
    print(f"  Clusters: {stats_b_cluster['cluster_count']}, edges: {stats_b_cluster['edge_count']}, density: {stats_b_cluster['density']}")

    # Abstract addition stats
    total_added = sum(len(v) for v in abstract_adds.values())
    papers_enriched = sum(1 for v in abstract_adds.values() if v)
    print(f"  Abstract additions: {total_added} entities across {papers_enriched} papers")

    # === T3: Entity diagnostics ===
    print("\n--- T3: Entity Diagnostics ---")
    pred_increase = (stats_b_entity["predefined_mean"] - stats_a_entity["predefined_mean"]) / stats_a_entity["predefined_mean"] * 100 if stats_a_entity["predefined_mean"] > 0 else 0
    print(f"  Predefined mean: {stats_a_entity['predefined_mean']:.2f} → {stats_b_entity['predefined_mean']:.2f} ({pred_increase:+.1f}%)")
    print(f"  Heuristic mean: {stats_a_entity['heuristic_mean']:.2f} → {stats_b_entity['heuristic_mean']:.2f} (unchanged, additive)")
    print(f"  Universal connectors (>10% papers):")
    for uc in stats_b_entity["top_universal_connectors"][:10]:
        print(f"    {uc['entity']}: {uc['doc_freq']} papers ({uc['pct']}%)")

    # === T4: Cluster comparison ===
    print("\n--- T4: Cluster Comparison ---")
    comparison = compute_ari_nmi(clusters_a, clusters_b, papers)
    preservation = compute_cluster_preservation(clusters_a, clusters_b, papers)
    edge_decomp = compute_edge_decomposition(papers, arm_a, arm_b, edges_b)

    print(f"  ARI: {comparison['ari']}, NMI: {comparison['nmi']}")
    print(f"  Cluster preservation: {preservation['preservation_rate']:.1%} ({preservation['preserved_count']}/{preservation['major_cluster_count']} major clusters)")
    for d in preservation["details"]:
        status = "✓" if d["preserved"] else "✗"
        print(f"    {status} A-C{d['arm_a_cluster']} (n={d['size']}) → B-C{d['best_arm_b_cluster']} overlap={d['overlap_pct']:.1%} jaccard={d['jaccard']:.3f}")
    print(f"  Edge decomposition: title-only={edge_decomp['title_only_edges']}, abstract-new={edge_decomp['abstract_new_edges']} ({edge_decomp['abstract_new_pct']}%), mixed={edge_decomp['mixed_edges']}")

    # === T5: Abstract bias ===
    print("\n--- T5: Abstract Availability Bias ---")
    bias = compute_abstract_bias(papers, arm_a, arm_b)
    print(f"  Has abstract ({bias['has_abstract_count']}): {bias['has_abstract_arm_a_mean']} → {bias['has_abstract_arm_b_mean']} (Δ={bias['has_abstract_mean_delta']})")
    print(f"  No abstract ({bias['no_abstract_count']}): {bias['no_abstract_arm_a_mean']} → {bias['no_abstract_arm_b_mean']} (Δ={bias['no_abstract_mean_delta']})")
    print(f"  Abstract length ↔ new entities correlation: r={bias['abstract_length_correlation']}")

    # === T6: GO/NO-GO ===
    print("\n--- T6: GO/NO-GO Judgment ---")
    # Merge cluster stats into entity stats for judgment
    stats_a_entity["cluster_count"] = stats_a_cluster["cluster_count"]
    stats_b_entity["cluster_count"] = stats_b_cluster["cluster_count"]
    judgment = go_nogo_判定(stats_a_entity, stats_b_entity, comparison, preservation)

    for name, c in judgment["criteria"].items():
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  {name}: {status} — {c}")

    print(f"\n  >>> VERDICT: {judgment['verdict']} <<<")

    # === Save results ===
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e009",
        "description": "Abstract predefined-entity enrichment — additive 2-arm",
        "dataset": str(DATA_PATH),
        "controls": {"resolution": RESOLUTION, "seed": SEED, "use_topics": False},
        "arm_a": {
            "entity_stats": stats_a_entity,
            "cluster_stats": stats_a_cluster,
        },
        "arm_b": {
            "entity_stats": stats_b_entity,
            "cluster_stats": stats_b_cluster,
            "abstract_additions": {
                "total_entities_added": total_added,
                "papers_enriched": papers_enriched,
            },
        },
        "comparison": {
            **comparison,
            "preservation": preservation,
            "edge_decomposition": edge_decomp,
        },
        "abstract_bias": bias,
        "judgment": judgment,
    }

    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
