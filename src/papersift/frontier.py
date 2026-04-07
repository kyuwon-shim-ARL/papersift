"""Knowledge Frontier analysis: redundancy scoring, temporal dynamics, structural gaps.

Refactored from scripts/e015_knowledge_frontier_v1.py for use as CLI subcommands.
"""

from collections import Counter, defaultdict

import numpy as np

from papersift.entity_layer import EntityLayerBuilder


def extract_entities(papers: list[dict], domain_vocab=None) -> dict[str, set]:
    """T0: Extract entities (title + abstract) for all papers.

    Uses EntityLayerBuilder with use_abstract=True for unified extraction.

    Args:
        papers: List of paper dicts with 'doi', 'title', optional 'abstract'.
        domain_vocab: Optional domain-specific vocabulary dict.

    Returns:
        Dict mapping doi -> set of entity strings.
    """
    builder = EntityLayerBuilder(use_abstract=True, domain_vocab=domain_vocab)
    builder.build_from_papers(papers)
    entity_data = dict(builder.paper_entities)

    non_empty = sum(1 for v in entity_data.values() if v)
    if entity_data:
        mean_count = float(np.mean([len(v) for v in entity_data.values()]))
    else:
        mean_count = 0.0
    print(f"  Papers: {len(entity_data)}, non-empty: {non_empty} "
          f"({non_empty / len(entity_data) * 100:.1f}%)" if entity_data else "  Papers: 0")
    print(f"  Mean entities/paper: {mean_count:.1f}")

    return entity_data


def redundancy_scoring(
    papers: list[dict],
    entity_data: dict[str, set],
    clusters: dict[str, int],
) -> dict:
    """T1: Detect similar papers within clusters using 2-axis scoring.

    Axis 1: Entity Jaccard = |A∩B| / |A∪B|
    Axis 2: Bibliographic coupling = Jaccard(refs_A, refs_B)
    Combined = 0.5 * entity_jaccard + 0.5 * biblio_coupling

    Args:
        papers: List of paper dicts.
        entity_data: DOI -> set of entities (from extract_entities).
        clusters: DOI -> cluster_id mapping.

    Returns:
        Result dict with pairs_checked, notable_pairs, top_20, per_cluster_counts.
    """
    ref_sets: dict[str, set] = {}
    for p in papers:
        ref_sets[p["doi"]] = set(p.get("referenced_works", []))

    cluster_dois: dict = defaultdict(list)
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

                e_union = e1 | e2
                e_jaccard = len(e1 & e2) / len(e_union) if e_union else 0.0

                r_union = r1 | r2
                b_jaccard = len(r1 & r2) / len(r_union) if r_union else 0.0

                combined = 0.5 * e_jaccard + 0.5 * b_jaccard
                pairs_checked += 1

                if combined > 0.15:
                    results.append({
                        "doi_a": d1,
                        "doi_b": d2,
                        "cluster": cid,
                        "entity_jaccard": round(e_jaccard, 4),
                        "biblio_coupling": round(b_jaccard, 4),
                        "combined_score": round(combined, 4),
                    })

    results.sort(key=lambda x: -x["combined_score"])

    if results:
        ej = np.array([r["entity_jaccard"] for r in results])
        bc = np.array([r["biblio_coupling"] for r in results])
        corr = float(np.corrcoef(ej, bc)[0, 1]) if np.std(ej) > 0 and np.std(bc) > 0 else 0.0
    else:
        corr = 0.0

    print(f"  Pairs checked: {pairs_checked:,}")
    print(f"  Notable pairs (combined > 0.15): {len(results)}")
    print(f"  Entity<->Biblio correlation: r={corr:.3f}")

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


def temporal_dynamics(
    papers: list[dict],
    entity_data: dict[str, set],
    clusters: dict[str, int],
) -> dict:
    """T2: Per-cluster per-entity OLS + BH-FDR. Momentum score per cluster.

    Args:
        papers: List of paper dicts with 'doi', 'year' or 'publication_year'.
        entity_data: DOI -> set of entities.
        clusters: DOI -> cluster_id mapping.

    Returns:
        Result dict with total_tests, total_significant, momentum_variance, clusters.
    """
    from scipy import stats

    paper_years: dict[str, int] = {}
    for p in papers:
        year = p.get("year") or p.get("publication_year")
        if year:
            paper_years[p["doi"]] = int(year)

    cluster_dois: dict = defaultdict(list)
    for doi, cid in clusters.items():
        if doi in paper_years and doi in entity_data:
            cluster_dois[cid].append(doi)

    cluster_results: dict = {}
    total_tests = 0
    total_significant = 0

    for cid in sorted(cluster_dois.keys()):
        dois = cluster_dois[cid]
        if len(dois) < 20:
            continue

        year_counts = Counter(paper_years[d] for d in dois)
        valid_years = sorted(y for y, c in year_counts.items() if c >= 5)
        if len(valid_years) < 5:
            continue

        year_doi_sets: dict = defaultdict(set)
        for d in dois:
            y = paper_years[d]
            if y in set(valid_years):
                year_doi_sets[y].add(d)
        year_sizes = {y: len(year_doi_sets[y]) for y in valid_years}

        entity_freq: Counter = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                entity_freq[e] += 1

        test_entities = sorted(e for e, c in entity_freq.items() if c >= 5)

        ols_results = []
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

            slope, _intercept, r_value, p_value, _std_err = stats.linregress(x, y)
            ols_results.append({
                "entity": entity,
                "slope": round(float(slope), 6),
                "r_squared": round(float(r_value ** 2), 4),
                "p_value": float(p_value),
                "direction": "rising" if slope > 0 else "declining",
                "freq": entity_freq[entity],
            })

        ols_results.sort(key=lambda x: x["p_value"])
        m = len(ols_results)
        total_tests += m

        significant = []
        for i, r in enumerate(ols_results):
            rank = i + 1
            r["q_value"] = round(min(r["p_value"] * m / rank, 1.0), 6) if m > 0 else 1.0
            bh_threshold = 0.05 * rank / m if m > 0 else 0
            if r["p_value"] <= bh_threshold:
                significant.append(r)

        total_significant += len(significant)

        if significant:
            momentum = round(float(np.mean([r["slope"] for r in significant])), 6)
        else:
            top5 = ols_results[:5] if ols_results else []
            momentum = round(float(np.mean([r["slope"] for r in top5])), 6) if top5 else 0.0

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
              f"({len(rising)} rising {len(declining)} declining), momentum={momentum:.6f}")

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


def structural_gaps(
    papers: list[dict],
    entity_data: dict[str, set],
    clusters: dict[str, int],
    *,
    background_cluster_fraction: float = 0.80,
    background_terms_extra: set | None = None,
) -> dict:
    """T3: Intra-cluster gaps + cross-cluster bridges.

    Args:
        papers: List of paper dicts (unused directly, for API consistency).
        entity_data: DOI -> set of entities.
        clusters: DOI -> cluster_id mapping.
        background_cluster_fraction: e031 stoplist — entities appearing in at
            least this fraction of valid clusters (size>=20) are considered
            domain-general background and removed from bridge ranking. Default
            0.80 means terms appearing in >=80% of clusters are filtered. Set
            to 1.01 to disable. AMR corpora have ~30 such terms (bacteria,
            antibiotics, treatment, clinical, mechanisms) that overwhelm both
            alphabetical and b-potential ranking. Cluster-level prevalence is
            the correct signal: a term in ALL clusters cannot discriminate
            between them and is, by definition, not a bridge.
        background_terms_extra: Optional explicit stoplist to merge with
            data-driven filter.

    Returns:
        Result dict with intra_cluster_gaps, cross_cluster_bridges, intra_summary,
        and background_terms (the auto-detected stoplist for diagnostics).
    """
    cluster_dois: dict = defaultdict(list)
    for doi, cid in clusters.items():
        if doi in entity_data:
            cluster_dois[cid].append(doi)

    # e031 stoplist: data-driven cluster-level background filter
    # An entity appearing in (almost) every valid cluster cannot discriminate
    # between clusters and is, by definition, not a bridge. Compute per-entity
    # cluster_df (# of valid clusters containing it with freq>=3).
    valid_clusters = [cid for cid, dois in cluster_dois.items() if len(dois) >= 20]
    n_valid_clusters = len(valid_clusters) or 1
    cluster_appearance: Counter = Counter()
    for cid in valid_clusters:
        seen_in_cluster: set = set()
        cluster_freq: Counter = Counter()
        for d in cluster_dois[cid]:
            for e in entity_data.get(d, set()):
                cluster_freq[e] += 1
        for e, c in cluster_freq.items():
            if c >= 3 and e not in seen_in_cluster:
                seen_in_cluster.add(e)
                cluster_appearance[e] += 1
    background_terms = {
        e for e, df in cluster_appearance.items()
        if (df / n_valid_clusters) >= background_cluster_fraction
    }
    if background_terms_extra:
        background_terms |= set(background_terms_extra)

    intra_gaps: dict = {}

    for cid in sorted(cluster_dois.keys()):
        dois = cluster_dois[cid]
        if len(dois) < 20:
            continue

        n = len(dois)
        entity_freq: Counter = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                entity_freq[e] += 1

        cooccur: Counter = Counter()
        for d in dois:
            ents = sorted(entity_data.get(d, set()))
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    cooccur[(ents[i], ents[j])] += 1

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
        intra_gaps[cid] = gaps[:20]

        if gaps:
            print(f"  C{cid}: {len(dois)} papers, {len(frequent_entities)} entities (freq>=5), "
                  f"{len(gaps)} gaps, top: {gaps[0]['entity_a']}x{gaps[0]['entity_b']} "
                  f"exp={gaps[0]['expected']}")
        else:
            print(f"  C{cid}: 0 gaps")

    # cluster_entity_data[cid] = (entity_set, freq_Counter, total_entity_occurrences)
    # Counter retained (not just set) to enable b-potential bridge ranking below.
    cluster_entity_data: dict = {}
    for cid, dois in cluster_dois.items():
        if len(dois) < 20:
            continue
        freq: Counter = Counter()
        for d in dois:
            for e in entity_data.get(d, set()):
                if e in background_terms:
                    continue  # e031: skip domain-general background terms
                freq[e] += 1
        # Filter low-frequency noise (freq>=3) but preserve counts for retained entities.
        retained = Counter({e: c for e, c in freq.items() if c >= 3})
        if retained:
            cluster_entity_data[cid] = (set(retained), retained, sum(retained.values()))

    # Bridge ranking via b-potential (Hristovski D, Kastrin A, 2010)
    # "Identification of concepts bridging diverse biomedical domains"
    # BMC Bioinformatics 11(S5):P4. doi:10.1186/1471-2105-11-S5-P4
    # bridge_score(t, A, B) = ctfidf_a(t) * ctfidf_b(t)
    # where ctfidf_c(t) = (count(t,c)/total_c) * log(1 + N_clusters / df_c(t))
    # Replaces alphabetical sorted(s_a & s_b)[:10] which collapsed to general
    # low-letter terms (antibiotic, bacteria, clinical) regardless of specificity.
    n_clusters = len(cluster_entity_data)
    # df_c(t): number of clusters in which entity t appears (after freq>=3 filter)
    cluster_df: Counter = Counter()
    for cid, (ent_set, _, _) in cluster_entity_data.items():
        for e in ent_set:
            cluster_df[e] += 1

    bridges = []
    cids = sorted(cluster_entity_data.keys())
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            c_a, c_b = cids[i], cids[j]
            s_a, freq_a, tot_a = cluster_entity_data[c_a]
            s_b, freq_b, tot_b = cluster_entity_data[c_b]
            union = s_a | s_b
            if not union:
                continue
            inter = s_a & s_b
            jaccard = len(inter) / len(union)

            if jaccard > 0.05:
                # Score each shared entity by b-potential (product of c-TF-IDF in both clusters)
                scored = []
                for t in inter:
                    df_t = cluster_df[t]
                    if df_t == 0 or tot_a == 0 or tot_b == 0:
                        continue
                    idf = np.log(1.0 + n_clusters / df_t)
                    tf_a = freq_a[t] / tot_a
                    tf_b = freq_b[t] / tot_b
                    score = tf_a * idf * tf_b * idf
                    scored.append((t, score))
                scored.sort(key=lambda x: -x[1])
                shared_top = [t for t, _ in scored[:10]]

                bridges.append({
                    "cluster_a": c_a,
                    "cluster_b": c_b,
                    "entity_jaccard": round(jaccard, 4),
                    "shared_entities": shared_top,
                    "unique_a": len(s_a - s_b),
                    "unique_b": len(s_b - s_a),
                    "shared_count": len(inter),
                })

    bridges.sort(key=lambda x: -x["entity_jaccard"])

    print(f"  Cluster pairs checked: {len(cids) * (len(cids) - 1) // 2}")
    print(f"  Bridge pairs (Jaccard > 0.05): {len(bridges)}")

    return {
        "intra_cluster_gaps": {str(k): v for k, v in intra_gaps.items()},
        "cross_cluster_bridges": bridges,
        "intra_summary": {str(cid): len(gaps) for cid, gaps in intra_gaps.items()},
        "background_terms": sorted(background_terms),  # e031 diagnostic
    }
