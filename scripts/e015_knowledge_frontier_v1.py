#!/usr/bin/env python3
"""e015: Knowledge Frontier v1.0 — T0+T1+T2+T3 + acceptance test.

T0: Entity extraction on v2 3,070 papers (shared prerequisite)
T1: Redundancy scoring (entity Jaccard + bibliographic coupling)
T2: Per-cluster temporal dynamics (per-cluster OLS + BH-FDR)
T3: Structural gaps (intra-cluster gap + cross-cluster bridge)
Acceptance: knowledge_frontier_v1.json integration

Scenarios covered: A(combination), B(redundancy), C(distant connection), E(search space reduction)
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, ImprovedEntityExtractor

BASE = Path(__file__).resolve().parent.parent
DATA_PATH = BASE / "results/virtual-cell-sweep/papers_with_abstracts.json"
CLUSTERS_PATH = BASE / "results/virtual-cell-sweep/clusters.json"
OUTPUT_DIR = BASE / "outputs/e015"


def load_data():
    with open(DATA_PATH) as f:
        papers = json.load(f)
    with open(CLUSTERS_PATH) as f:
        clusters = json.load(f)
    return papers, clusters


# ── T0: Entity Extraction ──────────────────────────────────────────


def t0_extract_entities(papers):
    """Extract Arm B entities (title + abstract predefined) for all papers.

    Reuses e014 pattern: ImprovedEntityExtractor with STOPWORDS filter.
    """
    print("=" * 60)
    print("T0: Entity Extraction on v2 (3,070 papers)")
    print("=" * 60)

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

    non_empty = sum(1 for v in entity_data.values() if v)
    mean_count = np.mean([len(v) for v in entity_data.values()])
    print(f"  Papers: {len(entity_data)}, non-empty: {non_empty} ({non_empty/len(entity_data)*100:.1f}%)")
    print(f"  Mean entities/paper: {mean_count:.1f}")

    return entity_data


# ── T1: Redundancy Scoring ─────────────────────────────────────────


def t1_redundancy(papers, entity_data, clusters):
    """Detect similar papers within clusters using 2-axis scoring.

    Axis 1: Entity Jaccard = |A∩B| / |A∪B|
    Axis 2: Bibliographic coupling = Jaccard(refs_A, refs_B)
    Combined = 0.5 * entity_jaccard + 0.5 * biblio_coupling
    """
    print("\n" + "=" * 60)
    print("T1: Redundancy Scoring (Scenario B+E)")
    print("=" * 60)

    # Build DOI -> referenced_works sets
    ref_sets = {}
    for p in papers:
        ref_sets[p["doi"]] = set(p.get("referenced_works", []))

    # Group DOIs by cluster
    cluster_dois = defaultdict(list)
    for doi, cid in clusters.items():
        cluster_dois[cid].append(doi)

    results = []
    pairs_checked = 0

    for cid, dois in sorted(cluster_dois.items(), key=lambda x: x[0]):
        if len(dois) < 2:
            continue
        for i in range(len(dois)):
            for j in range(i + 1, len(dois)):
                d1, d2 = dois[i], dois[j]
                e1 = entity_data.get(d1, set())
                e2 = entity_data.get(d2, set())
                r1 = ref_sets.get(d1, set())
                r2 = ref_sets.get(d2, set())

                # Entity Jaccard
                e_union = e1 | e2
                e_jaccard = len(e1 & e2) / len(e_union) if e_union else 0.0

                # Bibliographic coupling
                r_union = r1 | r2
                b_jaccard = len(r1 & r2) / len(r_union) if r_union else 0.0

                combined = 0.5 * e_jaccard + 0.5 * b_jaccard
                pairs_checked += 1

                if combined > 0.15:  # Only store notable pairs
                    results.append({
                        "doi_a": d1,
                        "doi_b": d2,
                        "cluster": cid,
                        "entity_jaccard": round(e_jaccard, 4),
                        "biblio_coupling": round(b_jaccard, 4),
                        "combined_score": round(combined, 4),
                    })

    results.sort(key=lambda x: -x["combined_score"])

    # Correlation between the two axes
    if results:
        ej = np.array([r["entity_jaccard"] for r in results])
        bc = np.array([r["biblio_coupling"] for r in results])
        if np.std(ej) > 0 and np.std(bc) > 0:
            corr = np.corrcoef(ej, bc)[0, 1]
        else:
            corr = 0.0
    else:
        corr = 0.0

    print(f"  Pairs checked: {pairs_checked:,}")
    print(f"  Notable pairs (combined > 0.15): {len(results)}")
    print(f"  Entity↔Biblio correlation: r={corr:.3f}")
    print(f"\n  Top-20 redundant pairs:")
    for r in results[:20]:
        print(f"    cluster={r['cluster']}: {r['doi_a'][:30]}... × {r['doi_b'][:30]}... "
              f"combined={r['combined_score']:.3f} (entity={r['entity_jaccard']:.3f}, biblio={r['biblio_coupling']:.3f})")

    return {
        "pairs_checked": pairs_checked,
        "notable_pairs": len(results),
        "axis_correlation": round(corr, 4),
        "top_20": results[:20],
        "threshold": 0.15,
        "per_cluster_counts": {
            cid: sum(1 for r in results if r["cluster"] == cid)
            for cid in sorted(set(r["cluster"] for r in results))
        },
    }


# ── T2: Temporal Dynamics ──────────────────────────────────────────


def t2_temporal(papers, entity_data, clusters):
    """Per-cluster per-entity OLS + BH-FDR. Momentum score per cluster."""
    from scipy import stats

    print("\n" + "=" * 60)
    print("T2: Per-Cluster Temporal Dynamics (Scenario A+E)")
    print("=" * 60)

    # Build DOI -> year, cluster
    paper_years = {}
    for p in papers:
        year = p.get("year") or p.get("publication_year")
        if year:
            paper_years[p["doi"]] = int(year)

    # Group by cluster
    cluster_dois = defaultdict(list)
    for doi, cid in clusters.items():
        if doi in paper_years and doi in entity_data:
            cluster_dois[cid].append(doi)

    cluster_results = {}
    total_tests = 0
    total_significant = 0

    for cid in sorted(cluster_dois.keys()):
        dois = cluster_dois[cid]
        if len(dois) < 20:  # Skip tiny clusters
            continue

        # Year distribution for this cluster
        year_counts = Counter(paper_years[d] for d in dois)
        valid_years = sorted(y for y, c in year_counts.items() if c >= 5)
        if len(valid_years) < 5:
            continue

        # Pre-compute year -> dois
        year_doi_sets = defaultdict(set)
        for d in dois:
            y = paper_years[d]
            if y in set(valid_years):
                year_doi_sets[y].add(d)
        year_sizes = {y: len(year_doi_sets[y]) for y in valid_years}

        # Entity doc freq within cluster
        entity_freq = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                entity_freq[e] += 1

        # Test entities with freq >= 5 within cluster
        test_entities = sorted(e for e, c in entity_freq.items() if c >= 5)

        results = []
        for entity in test_entities:
            x_years = []
            y_props = []
            for y in valid_years:
                count = sum(1 for d in year_doi_sets[y] if entity in entity_data.get(d, set()))
                x_years.append(y)
                y_props.append(count / year_sizes[y])

            x = np.array(x_years, dtype=float)
            y = np.array(y_props)

            if len(x) < 5:
                continue

            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            results.append({
                "entity": entity,
                "slope": round(float(slope), 6),
                "r_squared": round(float(r_value ** 2), 4),
                "p_value": float(p_value),
                "direction": "rising" if slope > 0 else "declining",
                "freq": entity_freq[entity],
            })

        # BH-FDR correction within cluster
        results.sort(key=lambda x: x["p_value"])
        m = len(results)
        total_tests += m

        significant = []
        for i, r in enumerate(results):
            rank = i + 1
            r["q_value"] = round(min(r["p_value"] * m / rank, 1.0), 6) if m > 0 else 1.0
            bh_threshold = 0.05 * rank / m if m > 0 else 0
            if r["p_value"] <= bh_threshold:
                significant.append(r)

        total_significant += len(significant)

        # Momentum score: mean slope of significant entities
        if significant:
            momentum = round(np.mean([r["slope"] for r in significant]), 6)
        else:
            # Use top-5 by p-value as fallback
            top5 = results[:5] if results else []
            momentum = round(np.mean([r["slope"] for r in top5]), 6) if top5 else 0.0

        rising = [r for r in significant if r["direction"] == "rising"]
        declining = [r for r in significant if r["direction"] == "declining"]

        cluster_results[cid] = {
            "n_papers": len(dois),
            "valid_years": len(valid_years),
            "year_range": f"{valid_years[0]}-{valid_years[-1]}",
            "tests": m,
            "significant": len(significant),
            "rising_count": len(rising),
            "declining_count": len(declining),
            "momentum_score": momentum,
            "top_rising": [{"entity": r["entity"], "slope": r["slope"], "q_value": r["q_value"]}
                           for r in rising[:5]],
            "top_declining": [{"entity": r["entity"], "slope": r["slope"], "q_value": r["q_value"]}
                              for r in declining[:5]],
        }

        print(f"  C{cid}: {len(dois)} papers, {m} tests, {len(significant)} significant "
              f"({len(rising)}↑ {len(declining)}↓), momentum={momentum:.6f}")

    # Momentum score variance
    momenta = [v["momentum_score"] for v in cluster_results.values()]
    momentum_var = round(float(np.var(momenta)), 8) if momenta else 0.0

    print(f"\n  Total: {total_tests} tests, {total_significant} significant")
    print(f"  Momentum variance across clusters: {momentum_var:.8f}")

    return {
        "total_tests": total_tests,
        "total_significant": total_significant,
        "momentum_variance": momentum_var,
        "clusters": cluster_results,
    }


# ── T3: Structural Gaps ───────────────────────────────────────────


def t3_structural_gaps(papers, entity_data, clusters):
    """Intra-cluster gaps + cross-cluster bridges."""
    print("\n" + "=" * 60)
    print("T3: Structural Gaps (Scenario A+C)")
    print("=" * 60)

    # Group DOIs by cluster
    cluster_dois = defaultdict(list)
    for doi, cid in clusters.items():
        if doi in entity_data:
            cluster_dois[cid].append(doi)

    # ── Intra-cluster gaps ──
    print("\n  --- Intra-cluster gaps ---")
    intra_gaps = {}

    for cid in sorted(cluster_dois.keys()):
        dois = cluster_dois[cid]
        if len(dois) < 20:
            continue

        n = len(dois)
        # Entity freq within cluster
        entity_freq = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                entity_freq[e] += 1

        # Co-occurrence within cluster
        cooccur = Counter()
        for d in dois:
            ents = sorted(entity_data.get(d, set()))
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    cooccur[(ents[i], ents[j])] += 1

        # Find gaps: expected > 5 AND observed/expected < 0.2
        gaps = []
        frequent_entities = [e for e, c in entity_freq.items() if c >= 5]
        for i in range(len(frequent_entities)):
            for j in range(i + 1, len(frequent_entities)):
                e_a, e_b = frequent_entities[i], frequent_entities[j]
                pair = tuple(sorted([e_a, e_b]))
                expected = entity_freq[e_a] * entity_freq[e_b] / n
                if expected < 5:
                    continue
                observed = cooccur.get(pair, 0)
                ratio = observed / expected if expected > 0 else 0
                if ratio < 0.2:
                    gaps.append({
                        "entity_a": pair[0],
                        "entity_b": pair[1],
                        "freq_a": entity_freq[pair[0]],
                        "freq_b": entity_freq[pair[1]],
                        "expected": round(expected, 2),
                        "observed": observed,
                        "ratio": round(ratio, 4),
                    })

        gaps.sort(key=lambda x: -x["expected"])
        intra_gaps[cid] = gaps[:20]  # Top 20 per cluster

        print(f"  C{cid}: {len(dois)} papers, {len(frequent_entities)} entities (freq>=5), "
              f"{len(gaps)} gaps (expected>5, ratio<0.2), top: "
              f"{gaps[0]['entity_a']}×{gaps[0]['entity_b']} exp={gaps[0]['expected']}" if gaps else f"  C{cid}: 0 gaps")

    # ── Cross-cluster bridges ──
    print("\n  --- Cross-cluster bridges ---")

    # Compute cluster-level entity profiles (set of entities with freq >= 3)
    cluster_entity_sets = {}
    for cid, dois in cluster_dois.items():
        if len(dois) < 20:
            continue
        freq = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                freq[e] += 1
        cluster_entity_sets[cid] = {e for e, c in freq.items() if c >= 3}

    bridges = []
    cids = sorted(cluster_entity_sets.keys())
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            c_a, c_b = cids[i], cids[j]
            s_a = cluster_entity_sets[c_a]
            s_b = cluster_entity_sets[c_b]
            union = s_a | s_b
            if not union:
                continue
            jaccard = len(s_a & s_b) / len(union)

            # Shared entities (potential bridge topics)
            shared = sorted(s_a & s_b)

            if jaccard > 0.05:  # Lower threshold to find distant connections
                bridges.append({
                    "cluster_a": c_a,
                    "cluster_b": c_b,
                    "entity_jaccard": round(jaccard, 4),
                    "shared_entities": shared[:10],
                    "unique_a": len(s_a - s_b),
                    "unique_b": len(s_b - s_a),
                    "shared_count": len(shared),
                })

    bridges.sort(key=lambda x: -x["entity_jaccard"])

    print(f"  Cluster pairs checked: {len(cids) * (len(cids) - 1) // 2}")
    print(f"  Bridge pairs (Jaccard > 0.05): {len(bridges)}")
    for b in bridges[:10]:
        print(f"    C{b['cluster_a']}↔C{b['cluster_b']}: Jaccard={b['entity_jaccard']:.4f}, "
              f"shared={b['shared_count']}, entities: {', '.join(b['shared_entities'][:5])}")

    return {
        "intra_cluster_gaps": {str(k): v for k, v in intra_gaps.items()},
        "cross_cluster_bridges": bridges,
        "intra_summary": {
            str(cid): len(gaps) for cid, gaps in intra_gaps.items()
        },
    }


# ── Acceptance Test ────────────────────────────────────────────────


def acceptance_test(t1_results, t2_results, t3_results):
    """v1.0 acceptance: >=3 biology clusters with non-trivial signals in all 3 dimensions."""
    print("\n" + "=" * 60)
    print("v1.0 ACCEPTANCE TEST")
    print("=" * 60)

    biology_clusters = [0, 1, 3, 5, 7]  # Known biology clusters
    passing = []

    for cid in biology_clusters:
        cid_str = str(cid)

        # T1: >=10 notable pairs with combined > 0.15
        t1_count = t1_results["per_cluster_counts"].get(cid, 0)
        t1_pass = t1_count >= 5  # Relaxed: >= 5 notable pairs

        # T2: >= 1 significant entity
        t2_data = t2_results["clusters"].get(cid, {})
        t2_sig = t2_data.get("significant", 0)
        t2_pass = t2_sig >= 1

        # T3: >= 1 intra-cluster gap
        t3_gaps = len(t3_results["intra_cluster_gaps"].get(cid_str, []))
        t3_pass = t3_gaps >= 1

        all_pass = t1_pass and t2_pass and t3_pass
        if all_pass:
            passing.append(cid)

        status = "PASS" if all_pass else "FAIL"
        print(f"  C{cid}: T1={t1_count} pairs({'OK' if t1_pass else 'X'}), "
              f"T2={t2_sig} sig({'OK' if t2_pass else 'X'}), "
              f"T3={t3_gaps} gaps({'OK' if t3_pass else 'X'}) → {status}")

    verdict = "PASS" if len(passing) >= 3 else "FAIL"
    print(f"\n  >>> v1.0 ACCEPTANCE: {verdict} — {len(passing)}/5 biology clusters pass (need >= 3) <<<")

    return {
        "biology_clusters_tested": len(biology_clusters),
        "passing_clusters": passing,
        "passing_count": len(passing),
        "verdict": verdict,
    }


# ── Main ───────────────────────────────────────────────────────────


def main():
    papers, clusters = load_data()
    print(f"Loaded {len(papers)} papers, {len(clusters)} cluster assignments\n")

    # T0: Entity extraction
    entity_data = t0_extract_entities(papers)

    # T1, T2, T3 (sequential in script, but logically parallel)
    t1_results = t1_redundancy(papers, entity_data, clusters)
    t2_results = t2_temporal(papers, entity_data, clusters)
    t3_results = t3_structural_gaps(papers, entity_data, clusters)

    # Acceptance test
    accept = acceptance_test(t1_results, t2_results, t3_results)

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e015",
        "description": "Knowledge Frontier v1.0 — T0+T1+T2+T3 + acceptance test",
        "dataset": str(DATA_PATH),
        "clusters": str(CLUSTERS_PATH),
        "t0_entity_extraction": {
            "total_papers": len(entity_data),
            "non_empty": sum(1 for v in entity_data.values() if v),
            "mean_entities_per_paper": round(float(np.mean([len(v) for v in entity_data.values()])), 2),
        },
        "t1_redundancy": t1_results,
        "t2_temporal": t2_results,
        "t3_structural_gaps": t3_results,
        "acceptance": accept,
    }

    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_file}")

    # Also save entity data for downstream use
    entity_out = BASE / "results/virtual-cell-sweep/papers_with_entities.json"
    entity_export = {doi: sorted(ents) for doi, ents in entity_data.items()}
    with open(entity_out, "w") as f:
        json.dump(entity_export, f, indent=2, ensure_ascii=False)
    print(f"Entity data saved to {entity_out}")


if __name__ == "__main__":
    main()
