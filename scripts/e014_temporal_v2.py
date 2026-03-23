#!/usr/bin/env python3
"""e014: T5 Temporal momentum retry on v2 dataset (3,070 papers).

v1 (354 papers, e013) → 0 significant after BH-FDR. Insufficient power.
v2 (3,070 papers) → ~8.7x data, 34 years with >=10 papers.

Success: >= 3 entities with q < 0.05 after BH-FDR.
Kill: 0 significant after FDR (same as v1).
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, ImprovedEntityExtractor

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell-sweep/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e014"


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def extract_arm_b_entities(papers, extractor):
    """Extract Arm B entities (title + abstract predefined)."""
    all_patterns = (
        [(m, pat, "METHOD") for m, pat in extractor.method_patterns]
        + [(o, pat, "ORGANISM") for o, pat in extractor.organism_patterns]
        + [(c, pat, "CONCEPT") for c, pat in extractor.concept_patterns]
        + [(d, pat, "DATASET") for d, pat in extractor.dataset_patterns]
    )

    result = {}
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
        result[p["doi"]] = entity_set

    return result


def run_temporal(papers, entity_data):
    """Per-entity temporal trend via OLS + BH-FDR correction."""
    from scipy import stats

    print("=" * 60)
    print("e014: T5 Temporal Momentum — v2 Dataset (3,070 papers)")
    print("=" * 60)

    # Build year index (optimized: pre-compute year→dois)
    paper_years = {}
    year_to_dois = defaultdict(list)
    for p in papers:
        year = p.get("year") or p.get("publication_year")
        if year and p["doi"] in entity_data:
            y = int(year)
            paper_years[p["doi"]] = y
            year_to_dois[y].append(p["doi"])

    print(f"\nPapers with year+entities: {len(paper_years)}/{len(papers)}")

    year_counts = Counter(paper_years.values())
    years_sorted = sorted(year_counts.keys())
    print(f"Year range: {years_sorted[0]}-{years_sorted[-1]} ({len(years_sorted)} unique)")

    # Filter years with >= 10 papers (stricter than v1's >=3 for stability)
    valid_years = sorted(y for y, c in year_counts.items() if c >= 10)
    print(f"Years with >= 10 papers: {len(valid_years)}")

    # Entity document frequency
    entity_doc_freq = Counter()
    for doi, ents in entity_data.items():
        if doi in paper_years:
            for e in ents:
                entity_doc_freq[e] += 1

    # Test entities with freq >= 15 (scaled from v1's >=5 proportional to dataset)
    test_entities = sorted(e for e, c in entity_doc_freq.items() if c >= 15)
    print(f"Entities to test (freq >= 15): {len(test_entities)}")

    # Pre-compute: for each valid year, which dois
    year_doi_sets = {y: set(year_to_dois[y]) for y in valid_years}
    year_sizes = {y: len(year_doi_sets[y]) for y in valid_years}

    results = []
    for entity in test_entities:
        # Yearly proportion: papers with entity / total papers in year
        x_years = []
        y_props = []
        for y in valid_years:
            dois_in_year = year_doi_sets[y]
            count = sum(1 for d in dois_in_year if entity in entity_data.get(d, set()))
            x_years.append(y)
            y_props.append(count / year_sizes[y])

        x = np.array(x_years)
        y = np.array(y_props)

        if len(x) < 5:
            continue

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        results.append({
            "entity": entity,
            "slope": round(float(slope), 6),
            "r_squared": round(float(r_value ** 2), 4),
            "p_value": float(p_value),
            "std_err": round(float(std_err), 6),
            "direction": "rising" if slope > 0 else "declining",
            "freq": entity_doc_freq[entity],
            "mean_proportion": round(float(y.mean()), 4),
            "yearly_data": {str(yr): round(prop, 4) for yr, prop in zip(x_years, y_props)},
        })

    # Benjamini-Hochberg FDR correction
    results.sort(key=lambda x: x["p_value"])
    m = len(results)
    print(f"\nTotal tests: {m}")

    for i, r in enumerate(results):
        rank = i + 1
        r["bh_threshold"] = round(0.05 * rank / m, 6) if m > 0 else 0
        r["q_value"] = round(min(r["p_value"] * m / rank, 1.0), 6) if m > 0 else 1.0

    # BH step-up: find largest k where p(k) <= 0.05 * k / m
    significant = []
    for r in results:
        if r["p_value"] <= r["bh_threshold"]:
            significant.append(r)

    print(f"Significant after BH-FDR (q < 0.05): {len(significant)}")

    if significant:
        print(f"\nSignificant entity trends:")
        for r in significant[:30]:
            print(f"  {r['entity']}: slope={r['slope']:.6f} ({r['direction']}), "
                  f"p={r['p_value']:.6f}, q={r['q_value']:.4f}, "
                  f"freq={r['freq']}, mean={r['mean_proportion']:.4f}")
    else:
        print("  No significant trends after FDR correction.")

    # Top trends regardless
    top_rising = sorted([r for r in results if r["slope"] > 0], key=lambda x: x["p_value"])[:10]
    top_declining = sorted([r for r in results if r["slope"] < 0], key=lambda x: x["p_value"])[:10]

    print(f"\nTop-10 rising (before FDR):")
    for r in top_rising:
        print(f"  {r['entity']}: slope={r['slope']:.6f}, p={r['p_value']:.6f}, freq={r['freq']}")
    print(f"\nTop-10 declining (before FDR):")
    for r in top_declining:
        print(f"  {r['entity']}: slope={r['slope']:.6f}, p={r['p_value']:.6f}, freq={r['freq']}")

    verdict = (f"GO — {len(significant)} entities significant after BH-FDR"
               if len(significant) >= 3
               else f"FAIL — only {len(significant)} significant (need >= 3)")

    print(f"\n  >>> e014 VERDICT: {verdict} <<<")

    # Comparison with v1
    print(f"\n--- v1 vs v2 comparison ---")
    print(f"  v1: 354 papers, 75 entities tested, 0 significant")
    print(f"  v2: {len(papers)} papers, {len(test_entities)} entities tested, {len(significant)} significant")

    return {
        "total_papers": len(papers),
        "papers_with_year_entities": len(paper_years),
        "valid_years": len(valid_years),
        "valid_year_range": f"{valid_years[0]}-{valid_years[-1]}" if valid_years else "N/A",
        "total_tests": m,
        "significant_count": len(significant),
        "significant": [{"entity": r["entity"], "slope": r["slope"],
                        "direction": r["direction"], "p_value": r["p_value"],
                        "q_value": r["q_value"], "freq": r["freq"],
                        "mean_proportion": r["mean_proportion"]}
                       for r in significant],
        "top_rising": [{"entity": r["entity"], "slope": r["slope"],
                       "p_value": r["p_value"], "freq": r["freq"]} for r in top_rising],
        "top_declining": [{"entity": r["entity"], "slope": r["slope"],
                          "p_value": r["p_value"], "freq": r["freq"]} for r in top_declining],
        "verdict": verdict,
        "v1_comparison": {
            "v1_papers": 354, "v1_tests": 75, "v1_significant": 0,
            "v2_papers": len(papers), "v2_tests": m, "v2_significant": len(significant),
        },
    }


def main():
    papers = load_papers()
    extractor = ImprovedEntityExtractor()
    entity_data = extract_arm_b_entities(papers, extractor)
    print(f"Loaded {len(papers)} papers, {sum(1 for v in entity_data.values() if v)} with entities")

    t5_results = run_temporal(papers, entity_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "e014",
        "description": "T5 temporal momentum retry on v2 (3,070 papers)",
        "dataset": str(DATA_PATH),
        "design": {
            "method": "Per-entity OLS on yearly proportion + BH-FDR",
            "valid_year_threshold": 10,
            "entity_freq_threshold": 15,
            "fdr_alpha": 0.05,
            "success_criteria": ">= 3 entities q < 0.05",
        },
        "t5_temporal": t5_results,
    }
    out_file = OUTPUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
