#!/usr/bin/env python3
"""e017: Failure Signal Aggregation — dead-end detection from limits + open_questions.

Aggregates T4 extended extractions per cluster. Identifies recurring limitation
themes and dead-end signals using text similarity clustering.

Success: >= 2 recurring limitation themes per cluster + >= 5 actionable directions.
Kill: generic limitations ('more data needed') >= 80%.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

EXTRACTIONS_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell-sweep/extractions_extended.json"
CLUSTERS_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell-sweep/clusters.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e017"

# Generic limitation patterns that don't carry signal
GENERIC_PATTERNS = [
    r"more data",
    r"more research",
    r"further (study|studies|research|investigation|work)",
    r"larger (dataset|sample|cohort)",
    r"additional (data|experiments|validation)",
    r"limited (data|sample size)",
    r"computational(ly)? (expensive|costly|intensive)",
    r"not (yet |fully )?(validated|verified|tested)",
]

GENERIC_RE = re.compile("|".join(GENERIC_PATTERNS), re.IGNORECASE)


def load_data():
    with open(EXTRACTIONS_PATH) as f:
        extractions = json.load(f)
    with open(CLUSTERS_PATH) as f:
        clusters = json.load(f)
    return extractions, clusters


def is_generic(text: str) -> bool:
    """Check if a limitation text is generic/uninformative."""
    if not text or len(text.strip()) < 10:
        return True
    return bool(GENERIC_RE.search(text))


def extract_key_phrases(text: str) -> list[str]:
    """Extract key noun phrases from limitation/question text.

    Simple approach: split on common delimiters, clean, lowercase.
    """
    if not text:
        return []
    # Split on semicolons, commas in lists, "and" conjunctions
    parts = re.split(r"[;]|,\s+(?:and|or)\s+|,\s+(?=[a-z])", text.lower())
    phrases = []
    for part in parts:
        part = part.strip().rstrip(".")
        # Remove leading articles/prepositions
        part = re.sub(r"^(the|a|an|this|that|whether|if|how|what)\s+", "", part)
        if len(part) > 5 and len(part) < 200:
            phrases.append(part)
    return phrases if phrases else [text.lower().strip().rstrip(".")]


def cluster_limitations_by_keywords(limitations: list[dict]) -> list[dict]:
    """Group limitations by keyword overlap.

    Returns theme clusters with representative text and frequency.
    """
    if not limitations:
        return []

    # Extract keyword sets for each limitation
    keyword_sets = []
    for lim in limitations:
        words = set(re.findall(r"\b[a-z]{4,}\b", lim["text"].lower()))
        # Remove very common words
        stop = {"this", "that", "with", "from", "have", "been", "which", "their",
                "these", "those", "also", "into", "only", "such", "does", "would",
                "could", "should", "more", "most", "some", "other", "than", "very",
                "will", "each", "both", "well", "still", "however", "while", "when",
                "where", "about", "between", "through", "during", "after", "before",
                "being", "over", "under", "same", "different", "specific", "particular",
                "model", "models", "approach", "method", "methods", "study", "work",
                "based", "using", "used", "results", "limited", "limitations"}
        words -= stop
        keyword_sets.append(words)

    # Greedy clustering by keyword overlap
    assigned = [False] * len(limitations)
    themes = []

    for i in range(len(limitations)):
        if assigned[i]:
            continue
        cluster_members = [i]
        assigned[i] = True
        cluster_words = keyword_sets[i].copy()

        for j in range(i + 1, len(limitations)):
            if assigned[j]:
                continue
            overlap = cluster_words & keyword_sets[j]
            union = cluster_words | keyword_sets[j]
            if union and len(overlap) / len(union) > 0.15:
                cluster_members.append(j)
                assigned[j] = True
                cluster_words |= keyword_sets[j]

        if len(cluster_members) >= 2:
            # Find most common keywords as theme label
            all_words = Counter()
            for idx in cluster_members:
                all_words.update(keyword_sets[idx])
            top_words = [w for w, _ in all_words.most_common(4)]

            themes.append({
                "theme_keywords": top_words,
                "theme_label": " + ".join(top_words[:3]),
                "count": len(cluster_members),
                "dois": [limitations[idx]["doi"] for idx in cluster_members],
                "representative": limitations[cluster_members[0]]["text"],
                "samples": [limitations[idx]["text"] for idx in cluster_members[:3]],
            })

    # Sort by frequency
    themes.sort(key=lambda t: t["count"], reverse=True)
    return themes


def analyze_cluster(cluster_id: str, cluster_extractions: list[dict]) -> dict:
    """Analyze limitations and open questions for a single cluster."""

    # Collect non-empty limits and open_questions
    limits = []
    open_qs = []
    generic_count = 0
    total_with_limits = 0

    for ext in cluster_extractions:
        lim_text = ext.get("limits", "").strip()
        oq_text = ext.get("open_questions", "").strip()

        if lim_text:
            total_with_limits += 1
            if is_generic(lim_text):
                generic_count += 1
            else:
                limits.append({"doi": ext["doi"], "text": lim_text})

        if oq_text and not is_generic(oq_text):
            open_qs.append({"doi": ext["doi"], "text": oq_text})

    # Cluster limitations into themes
    limit_themes = cluster_limitations_by_keywords(limits)

    # Cluster open questions into themes
    oq_themes = cluster_limitations_by_keywords(open_qs)

    generic_rate = generic_count / total_with_limits if total_with_limits > 0 else 0

    return {
        "cluster_id": cluster_id,
        "n_papers": len(cluster_extractions),
        "n_with_limits": total_with_limits,
        "n_specific_limits": len(limits),
        "n_generic_limits": generic_count,
        "generic_rate": round(generic_rate, 3),
        "n_open_questions": len(open_qs),
        "limit_themes": limit_themes[:10],
        "oq_themes": oq_themes[:10],
        "dead_end_signals": [t for t in limit_themes if t["count"] >= 3],
    }


def run():
    extractions, clusters = load_data()

    # Build DOI→extraction lookup
    ext_by_doi = {e["doi"].lower(): e for e in extractions if e.get("doi")}

    # Group by cluster
    cluster_exts = defaultdict(list)
    for doi, cid in clusters.items():
        cid_str = str(cid)
        ext = ext_by_doi.get(doi.lower())
        if ext:
            cluster_exts[cid_str].append(ext)

    # Analyze each cluster
    cluster_results = {}
    total_dead_ends = 0
    total_themes = 0
    total_actionable = 0

    for cid in sorted(cluster_exts.keys(), key=lambda x: int(x)):
        result = analyze_cluster(cid, cluster_exts[cid])
        cluster_results[cid] = result
        total_dead_ends += len(result["dead_end_signals"])
        total_themes += len(result["limit_themes"])
        total_actionable += len(result["oq_themes"])

        print(f"C{cid}: {result['n_papers']} papers, "
              f"{len(result['limit_themes'])} limit themes, "
              f"{len(result['oq_themes'])} OQ themes, "
              f"{len(result['dead_end_signals'])} dead-ends, "
              f"generic={result['generic_rate']:.1%}")

    # Overall statistics
    all_generic_rates = [r["generic_rate"] for r in cluster_results.values()]
    overall_generic = sum(all_generic_rates) / len(all_generic_rates) if all_generic_rates else 0

    # Verdict
    biology_clusters = ["0", "1", "3", "5", "7"]
    bio_with_themes = sum(
        1 for cid in biology_clusters
        if cid in cluster_results and len(cluster_results[cid]["limit_themes"]) >= 2
    )

    if overall_generic >= 0.8:
        verdict = f"KILL — generic rate {overall_generic:.1%} >= 80%"
    elif bio_with_themes >= 3 and total_actionable >= 5:
        verdict = f"GO — {bio_with_themes}/5 bio clusters with themes, {total_actionable} actionable OQ themes"
    else:
        verdict = f"CONDITIONAL — {bio_with_themes}/5 bio clusters, {total_actionable} actionable"

    results = {
        "experiment": "e017",
        "description": "Failure Signal Aggregation — dead-end detection",
        "total_extractions_used": sum(r["n_papers"] for r in cluster_results.values()),
        "total_limit_themes": total_themes,
        "total_dead_end_signals": total_dead_ends,
        "total_oq_themes": total_actionable,
        "overall_generic_rate": round(overall_generic, 3),
        "bio_clusters_with_themes": bio_with_themes,
        "verdict": verdict,
        "clusters": cluster_results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nVerdict: {verdict}")
    print(f"Saved to {OUTPUT_DIR / 'results.json'}")
    return results


if __name__ == "__main__":
    run()
