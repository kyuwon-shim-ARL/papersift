#!/usr/bin/env python3
"""e013: T4 Composability + T5 Temporal momentum.

T4: Co-occurrence expected/observed ratio for entity pairs.
    Top-10 underexplored pairs (ratio < 1, both entities freq >= 5).
    Success: >= 6/10 meaningful (user evaluation).
    Kill: < 3 meaningful.

T5: Per-entity temporal trend via OLS on yearly proportion.
    Benjamini-Hochberg FDR correction.
    Success: >= 3 entities with q < 0.05.
    Kill: 0 significant after FDR.
"""

import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, ImprovedEntityExtractor

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e013"


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def extract_arm_b_entities(papers, extractor):
    """Extract Arm B entities (title + abstract predefined)."""
    arm_a = {}
    for p in papers:
        entities = extractor.extract_entities(p["title"], p.get("category", ""))
        arm_a[p["doi"]] = {e["name"].lower() for e in entities}

    all_patterns = (
        [(m, pat, "METHOD") for m, pat in extractor.method_patterns]
        + [(o, pat, "ORGANISM") for o, pat in extractor.organism_patterns]
        + [(c, pat, "CONCEPT") for c, pat in extractor.concept_patterns]
        + [(d, pat, "DATASET") for d, pat in extractor.dataset_patterns]
    )

    result = {}
    for p in papers:
        doi = p["doi"]
        entity_set = set(arm_a[doi])
        abstract = p.get("abstract", "")
        if abstract:
            for name, pattern, etype in all_patterns:
                key = name.lower()
                if key in STOPWORDS:
                    continue
                if key not in entity_set and pattern.search(abstract):
                    entity_set.add(key)
        result[doi] = entity_set

    return result


# ===== T4: Composability =====

def run_t4(papers, entity_data):
    """Compute underexplored entity pairs via expected/observed ratio."""
    print("=" * 60)
    print("T4: Composability — Underexplored Entity Pairs")
    print("=" * 60)

    n_papers = len(papers)

    # Entity document frequency
    doc_freq = Counter()
    for doi, ents in entity_data.items():
        for e in ents:
            doc_freq[e] += 1

    # Filter: entities appearing in >= 5 papers
    freq_entities = {e for e, c in doc_freq.items() if c >= 5}
    print(f"\nEntities with freq >= 5: {len(freq_entities)}")

    # Co-occurrence count
    cooccur = Counter()
    for doi, ents in entity_data.items():
        filtered = ents & freq_entities
        for a, b in combinations(sorted(filtered), 2):
            cooccur[(a, b)] += 1

    # Expected/observed ratio
    gaps = []
    for (a, b), observed in cooccur.items():
        expected = (doc_freq[a] * doc_freq[b]) / n_papers
        if expected > 0:
            ratio = observed / expected
            gaps.append({
                "entity_a": a, "entity_b": b,
                "freq_a": doc_freq[a], "freq_b": doc_freq[b],
                "observed": observed, "expected": round(expected, 2),
                "ratio": round(ratio, 4),
            })

    # Also find pairs that NEVER co-occur but both are frequent
    all_freq_pairs = set(combinations(sorted(freq_entities), 2))
    never_cooccur = all_freq_pairs - set(cooccur.keys())
    for a, b in never_cooccur:
        expected = (doc_freq[a] * doc_freq[b]) / n_papers
        if expected >= 1.0:  # Only report if expected >= 1
            gaps.append({
                "entity_a": a, "entity_b": b,
                "freq_a": doc_freq[a], "freq_b": doc_freq[b],
                "observed": 0, "expected": round(expected, 2),
                "ratio": 0.0,
            })

    # Sort by ratio (ascending) — most underexplored first
    gaps.sort(key=lambda x: (x["ratio"], -x["expected"]))

    print(f"Total entity pairs analyzed: {len(gaps)}")
    print("\nTop-10 underexplored pairs (lowest observed/expected ratio):")
    top10 = gaps[:10]
    for i, g in enumerate(top10, 1):
        print(f"  {i}. {g['entity_a']} × {g['entity_b']}: "
              f"observed={g['observed']}, expected={g['expected']}, "
              f"ratio={g['ratio']:.4f} (freq: {g['freq_a']}, {g['freq_b']})")

    # Also show top overexplored for context
    overexplored = sorted(gaps, key=lambda x: -x["ratio"])[:5]
    print("\nTop-5 overexplored pairs (highest ratio, for context):")
    for g in overexplored:
        print(f"  {g['entity_a']} × {g['entity_b']}: ratio={g['ratio']:.2f} "
              f"(obs={g['observed']}, exp={g['expected']})")

    print("\n  >>> T4: Top-10 underexplored pairs generated. User evaluation required. <<<")
    return {"top_underexplored": top10, "top_overexplored": overexplored[:5],
            "total_pairs": len(gaps), "freq_entity_count": len(freq_entities)}


# ===== T5: Temporal Momentum =====

def run_t5(papers, entity_data):
    """Per-entity temporal trend via OLS + FDR correction."""
    print("\n" + "=" * 60)
    print("T5: Temporal Momentum — Entity Trend Detection")
    print("=" * 60)

    from scipy import stats

    # Get year for each paper
    paper_years = {}
    for p in papers:
        year = p.get("year") or p.get("publication_year")
        if year:
            paper_years[p["doi"]] = int(year)

    papers_with_year = {d: y for d, y in paper_years.items() if d in entity_data}
    print(f"\nPapers with year data: {len(papers_with_year)}/{len(papers)}")

    if len(papers_with_year) < 10:
        print("  Insufficient temporal data. SKIP.")
        return {"verdict": "SKIP — insufficient year data", "significant": []}

    # Year range
    years = sorted(set(papers_with_year.values()))
    year_counts = Counter(papers_with_year.values())
    print(f"Year range: {min(years)}-{max(years)} ({len(years)} unique years)")

    # Filter years with >= 3 papers for stable proportions
    valid_years = {y for y, c in year_counts.items() if c >= 3}
    print(f"Years with >= 3 papers: {len(valid_years)}")

    if len(valid_years) < 5:
        print("  Fewer than 5 valid years. SKIP.")
        return {"verdict": "SKIP — fewer than 5 valid years", "significant": []}

    # Per-entity yearly proportion
    entity_doc_freq = Counter()
    for doi, ents in entity_data.items():
        if doi in papers_with_year:
            for e in ents:
                entity_doc_freq[e] += 1

    # Only test entities with freq >= 5
    test_entities = {e for e, c in entity_doc_freq.items() if c >= 5}
    print(f"Entities to test (freq >= 5): {len(test_entities)}")

    results = []
    for entity in sorted(test_entities):
        # Compute yearly proportion: (count in year) / (total papers in year)
        year_props = {}
        for y in sorted(valid_years):
            papers_in_year = [d for d, yr in papers_with_year.items() if yr == y]
            count = sum(1 for d in papers_in_year if entity in entity_data.get(d, set()))
            year_props[y] = count / len(papers_in_year) if papers_in_year else 0

        x = np.array(sorted(year_props.keys()))
        y = np.array([year_props[yr] for yr in x])

        if len(x) < 5:
            continue

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        results.append({
            "entity": entity,
            "slope": round(float(slope), 6),
            "r_squared": round(float(r_value ** 2), 4),
            "p_value": float(p_value),
            "direction": "rising" if slope > 0 else "declining",
            "freq": entity_doc_freq[entity],
            "yearly_data": {str(yr): round(prop, 4) for yr, prop in sorted(year_props.items())},
        })

    # Benjamini-Hochberg FDR correction
    results.sort(key=lambda x: x["p_value"])
    m = len(results)
    for i, r in enumerate(results):
        rank = i + 1
        r["bh_threshold"] = round(0.05 * rank / m, 6) if m > 0 else 0
        r["q_value"] = round(min(r["p_value"] * m / rank, 1.0), 6) if m > 0 else 1.0

    # Apply BH: find largest k where p(k) <= 0.05 * k / m
    significant = []
    for i, r in enumerate(results):
        if r["p_value"] <= r["bh_threshold"]:
            significant.append(r)

    print(f"\nTotal tests: {m}")
    print(f"Significant after FDR (q < 0.05): {len(significant)}")

    if significant:
        print("\nSignificant entity trends:")
        for r in significant[:20]:
            print(f"  {r['entity']}: slope={r['slope']:.6f} ({r['direction']}), "
                  f"p={r['p_value']:.4f}, q={r['q_value']:.4f}, freq={r['freq']}")
    else:
        print("  No significant trends after FDR correction.")

    # Top trends regardless of significance (for context)
    top_rising = sorted([r for r in results if r["slope"] > 0], key=lambda x: x["p_value"])[:5]
    top_declining = sorted([r for r in results if r["slope"] < 0], key=lambda x: x["p_value"])[:5]

    print("\nTop-5 rising (before FDR):")
    for r in top_rising:
        print(f"  {r['entity']}: slope={r['slope']:.6f}, p={r['p_value']:.4f}, freq={r['freq']}")
    print("Top-5 declining (before FDR):")
    for r in top_declining:
        print(f"  {r['entity']}: slope={r['slope']:.6f}, p={r['p_value']:.4f}, freq={r['freq']}")

    verdict = (f"GO — {len(significant)} entities significant"
               if len(significant) >= 3
               else f"FAIL — only {len(significant)} significant (need >= 3)")

    print(f"\n  >>> T5 VERDICT: {verdict} <<<")

    return {
        "total_tests": m,
        "significant_count": len(significant),
        "significant": [{"entity": r["entity"], "slope": r["slope"],
                        "direction": r["direction"], "p_value": r["p_value"],
                        "q_value": r["q_value"], "freq": r["freq"]}
                       for r in significant],
        "top_rising": [{"entity": r["entity"], "slope": r["slope"],
                       "p_value": r["p_value"], "freq": r["freq"]} for r in top_rising],
        "top_declining": [{"entity": r["entity"], "slope": r["slope"],
                          "p_value": r["p_value"], "freq": r["freq"]} for r in top_declining],
        "verdict": verdict,
    }


def main():
    papers = load_papers()
    extractor = ImprovedEntityExtractor()
    entity_data = extract_arm_b_entities(papers, extractor)
    print(f"Loaded {len(papers)} papers, {len(entity_data)} with entities")

    t4_results = run_t4(papers, entity_data)
    t5_results = run_t5(papers, entity_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e013",
        "description": "T4 composability + T5 temporal momentum",
        "dataset": str(DATA_PATH),
        "t4_composability": t4_results,
        "t5_temporal": t5_results,
    }
    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
