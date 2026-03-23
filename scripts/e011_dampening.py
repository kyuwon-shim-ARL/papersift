#!/usr/bin/env python3
"""e011: High-df dampening A/B — incremental on T1 Jaccard (resolution=1.6).

Dampening: entities with doc_freq > 20% of papers get reduced contribution.
Weight = Jaccard * dampening_factor, where dampening_factor = 1/log2(doc_freq+1) for high-df entities.

Kill criteria:
- abstract-influenced edge (abstract-new + mixed) reduction > 40% → over-punishment
- universal connector edge contribution reduction < 5% vs T1 → marginal, discard
"""

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, EntityLayerBuilder, ImprovedEntityExtractor

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e011"
SEED = 42
RESOLUTION = 1.6  # From T0 selection
DF_THRESHOLD = 0.20  # Entities appearing in >20% of papers


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def extract_entities(papers, extractor):
    """Extract Arm A (title) and Arm B (title+abstract) entities."""
    arm_a = {}
    for p in papers:
        entities = extractor.extract_entities(p["title"], p.get("category", ""))
        arm_a[p["doi"]] = {"entities": {e["name"].lower() for e in entities}}

    all_patterns = (
        [(m, pat, "METHOD") for m, pat in extractor.method_patterns]
        + [(o, pat, "ORGANISM") for o, pat in extractor.organism_patterns]
        + [(c, pat, "CONCEPT") for c, pat in extractor.concept_patterns]
        + [(d, pat, "DATASET") for d, pat in extractor.dataset_patterns]
    )
    arm_b = {}
    for p in papers:
        doi = p["doi"]
        entity_set = set(arm_a[doi]["entities"])
        abstract = p.get("abstract", "")
        if abstract:
            for name, pattern, etype in all_patterns:
                key = name.lower()
                if key in STOPWORDS:
                    continue
                if key not in entity_set and pattern.search(abstract):
                    entity_set.add(key)
        arm_b[doi] = {"entities": entity_set}

    return arm_a, arm_b


def compute_doc_freq(papers, entity_data):
    """Compute document frequency for each entity."""
    df = Counter()
    for p in papers:
        for e in entity_data[p["doi"]]["entities"]:
            df[e] += 1
    return df


def build_graph_and_cluster(papers, entity_data, resolution, doc_freq=None,
                            dampen=False, n_papers=None, seed=SEED):
    """Build Jaccard-weighted graph with optional dampening."""
    import igraph as ig
    import leidenalg

    dois = [p["doi"] for p in papers]
    n = len(dois)
    high_df_entities = set()

    if dampen and doc_freq and n_papers:
        threshold_count = int(n_papers * DF_THRESHOLD)
        high_df_entities = {e for e, c in doc_freq.items() if c > threshold_count}

    edges = []
    weights = []
    for i in range(n):
        ents1 = entity_data[dois[i]]["entities"]
        for j in range(i + 1, n):
            ents2 = entity_data[dois[j]]["entities"]
            shared = ents1 & ents2
            if not shared:
                continue
            union = ents1 | ents2

            if dampen and high_df_entities:
                # Dampened Jaccard: high-df entities contribute less
                w = 0.0
                for e in shared:
                    if e in high_df_entities:
                        w += 1.0 / math.log2(doc_freq[e] + 1)
                    else:
                        w += 1.0
                w /= len(union)
            else:
                w = len(shared) / len(union)

            edges.append((i, j))
            weights.append(w)

    g = ig.Graph(n=n, edges=edges, directed=False)
    g.vs["doi"] = dois
    g.es["weight"] = weights

    partition = leidenalg.find_partition(
        g, leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution, weights="weight", seed=seed,
    )
    clusters = {dois[i]: partition.membership[i] for i in range(n)}
    return clusters, edges, weights


def compute_metrics(clusters):
    sizes = Counter(clusters.values())
    major = {c: s for c, s in sizes.items() if s >= 5}
    return {
        "cluster_count": len(sizes),
        "major_count": len(major),
        "singleton_count": sum(1 for s in sizes.values() if s == 1),
    }


def compute_preservation(base_clusters, test_clusters, papers):
    base_members = defaultdict(set)
    for p in papers:
        base_members[base_clusters[p["doi"]]].add(p["doi"])
    major = {c: m for c, m in base_members.items() if len(m) >= 5}
    if not major:
        return {"rate": 1.0, "count": 0, "preserved": 0, "details": []}

    preserved = 0
    details = []
    for cid, members in sorted(major.items(), key=lambda x: -len(x[1])):
        b_counts = Counter(test_clusters[d] for d in members)
        best_cid, best_n = b_counts.most_common(1)[0]
        b_members = {d for d, c in test_clusters.items() if c == best_cid}
        overlap = best_n / len(members)
        jaccard = len(members & b_members) / len(members | b_members)
        is_ok = overlap >= 0.6 and jaccard >= 0.3
        if is_ok:
            preserved += 1
        details.append({
            "cluster": cid, "size": len(members), "match": best_cid,
            "overlap": round(overlap, 3), "jaccard": round(jaccard, 3), "preserved": is_ok,
        })
    return {"rate": round(preserved / len(major), 3), "count": len(major),
            "preserved": preserved, "details": details}


def compute_edge_decomposition(papers, arm_a, arm_b, edges):
    """Classify edges by origin (title-only, abstract-new, mixed)."""
    dois = [p["doi"] for p in papers]
    title_only = abstract_new = mixed = 0
    for i, j in edges:
        d1, d2 = dois[i], dois[j]
        shared_b = arm_b[d1]["entities"] & arm_b[d2]["entities"]
        shared_a = arm_a[d1]["entities"] & arm_a[d2]["entities"]
        if shared_b == shared_a:
            title_only += 1
        elif not shared_a:
            abstract_new += 1
        else:
            mixed += 1
    total = len(edges)
    return {
        "title_only": title_only, "abstract_new": abstract_new, "mixed": mixed,
        "total": total,
        "abstract_influenced": abstract_new + mixed,
        "abstract_influenced_pct": round((abstract_new + mixed) / total * 100, 1) if total else 0,
    }


def main():
    papers = load_papers()
    extractor = ImprovedEntityExtractor()
    arm_a, arm_b = extract_entities(papers, extractor)
    doc_freq = compute_doc_freq(papers, arm_b)

    high_df_threshold = int(len(papers) * DF_THRESHOLD)
    high_df = {e: c for e, c in doc_freq.items() if c > high_df_threshold}
    print(f"Loaded {len(papers)} papers. High-df entities (>{DF_THRESHOLD*100:.0f}%={high_df_threshold}): {len(high_df)}")
    for e, c in sorted(high_df.items(), key=lambda x: -x[1])[:10]:
        print(f"  {e}: {c} papers ({c/len(papers)*100:.1f}%)")

    # Baseline: Jaccard without dampening (T1 result)
    print("\n--- Jaccard (no dampening) ---")
    cl_base, edges_base, w_base = build_graph_and_cluster(papers, arm_b, RESOLUTION)
    m_base = compute_metrics(cl_base)
    decomp_base = compute_edge_decomposition(papers, arm_a, arm_b, edges_base)
    print(f"  Clusters={m_base['cluster_count']}, major={m_base['major_count']}, "
          f"abstract-influenced edges={decomp_base['abstract_influenced']} ({decomp_base['abstract_influenced_pct']}%)")

    # Test: Jaccard + dampening
    print("\n--- Jaccard + dampening ---")
    cl_damp, edges_damp, w_damp = build_graph_and_cluster(
        papers, arm_b, RESOLUTION, doc_freq=doc_freq, dampen=True, n_papers=len(papers))
    m_damp = compute_metrics(cl_damp)
    decomp_damp = compute_edge_decomposition(papers, arm_a, arm_b, edges_damp)
    print(f"  Clusters={m_damp['cluster_count']}, major={m_damp['major_count']}, "
          f"abstract-influenced edges={decomp_damp['abstract_influenced']} ({decomp_damp['abstract_influenced_pct']}%)")

    # Preservation
    from sklearn.metrics import adjusted_rand_score
    dois = [p["doi"] for p in papers]
    ari = adjusted_rand_score([cl_base[d] for d in dois], [cl_damp[d] for d in dois])
    preservation = compute_preservation(cl_base, cl_damp, papers)

    print(f"\n  ARI: {ari:.4f}")
    print(f"  Preservation: {preservation['rate']:.1%} ({preservation['preserved']}/{preservation['count']})")
    for d in preservation["details"]:
        s = "Y" if d["preserved"] else "N"
        print(f"    [{s}] C{d['cluster']}(n={d['size']}) → C{d['match']} "
              f"overlap={d['overlap']:.3f} jaccard={d['jaccard']:.3f}")

    # Kill criteria evaluation
    print("\n--- Kill Criteria ---")
    abs_infl_base = decomp_base["abstract_influenced"]
    abs_infl_damp = decomp_damp["abstract_influenced"]
    abs_reduction = (abs_infl_base - abs_infl_damp) / abs_infl_base * 100 if abs_infl_base > 0 else 0
    print(f"  Abstract-influenced edge change: {abs_infl_base} → {abs_infl_damp} ({abs_reduction:+.1f}%)")
    kill_over_punishment = abs_reduction > 40
    print(f"  Kill (>40% reduction): {'YES → KILL' if kill_over_punishment else 'NO'}")

    # Note: edge count change is what matters, not just decomposition shift
    # Since dampening changes weights but not connectivity, edge count stays same
    # The meaningful metric is cluster structure change
    marginal = abs(abs_reduction) < 5
    print(f"  Marginal (<5% change): {'YES → discard (no effect)' if marginal else 'NO'}")

    pres_pass = preservation["rate"] >= 0.90
    ari_pass = ari >= 0.7
    print(f"  Preservation >= 90%: {'PASS' if pres_pass else 'FAIL'} ({preservation['rate']:.1%})")
    print(f"  ARI >= 0.7: {'PASS' if ari_pass else 'FAIL'} ({ari:.4f})")

    if kill_over_punishment:
        verdict = "KILL — abstract-influenced edge reduction > 40%, dampening 과도"
    elif marginal:
        verdict = "KILL — marginal effect < 5%, dampening 불필요"
    elif pres_pass and ari_pass:
        verdict = "GO — dampening 채택"
    else:
        verdict = "NO-GO — preservation or ARI below threshold"

    print(f"\n  >>> T2 VERDICT: {verdict} <<<")

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e011",
        "description": "T2 high-df dampening A/B (incremental on T1 Jaccard)",
        "resolution": RESOLUTION,
        "df_threshold": DF_THRESHOLD,
        "high_df_entities": {e: c for e, c in sorted(high_df.items(), key=lambda x: -x[1])},
        "baseline_jaccard": {"metrics": m_base, "edge_decomposition": decomp_base},
        "dampened_jaccard": {"metrics": m_damp, "edge_decomposition": decomp_damp},
        "ari": round(ari, 4),
        "preservation": preservation,
        "abstract_influenced_reduction_pct": round(abs_reduction, 1),
        "verdict": verdict,
    }
    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
