#!/usr/bin/env python3
"""e012: Schema extension pilot — stratified 50-paper sample.

Stratified sampling: major cluster(>=5) min 6/each, minor(2-4) min 2/each,
singleton min 3, no-abstract min 5. Total 50.

Success: enables >= 60% non-empty, limits >= 40% non-empty.
Kill: enables < 40% or spot-check < 5/10.
"""

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.entity_layer import STOPWORDS, EntityLayerBuilder, ImprovedEntityExtractor
from papersift.extract import build_batch_prompts

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e012"
SEED = 42
RESOLUTION = 1.6


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def cluster_papers(papers):
    """Cluster using Arm B entities at resolution 1.6."""
    extractor = ImprovedEntityExtractor()
    all_patterns = (
        [(m, p, "METHOD") for m, p in extractor.method_patterns]
        + [(o, p, "ORGANISM") for o, p in extractor.organism_patterns]
        + [(c, p, "CONCEPT") for c, p in extractor.concept_patterns]
        + [(d, p, "DATASET") for d, p in extractor.dataset_patterns]
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

    builder = EntityLayerBuilder()
    builder._dois = [p["doi"] for p in papers]
    builder._paper_entities = entity_data

    import igraph as ig
    n = len(builder._dois)
    edges, weights = [], []
    for i in range(n):
        ents1 = entity_data[builder._dois[i]]
        for j in range(i + 1, n):
            ents2 = entity_data[builder._dois[j]]
            shared = ents1 & ents2
            if shared:
                union = ents1 | ents2
                edges.append((i, j))
                weights.append(len(shared) / len(union))

    builder.graph = ig.Graph(n=n, edges=edges, directed=False)
    builder.graph.vs["doi"] = builder._dois
    builder.graph.es["weight"] = weights

    return builder.run_leiden(resolution=RESOLUTION, seed=SEED)


def stratified_sample(papers, clusters, target=50):
    """Stratified sample: major 6/each, minor 2/each, singleton 3, no-abstract 5."""
    random.seed(SEED)

    cluster_members = defaultdict(list)
    for p in papers:
        cluster_members[clusters[p["doi"]]].append(p)

    sizes = {c: len(m) for c, m in cluster_members.items()}
    major = {c: m for c, m in cluster_members.items() if len(m) >= 5}
    minor = {c: m for c, m in cluster_members.items() if 2 <= len(m) < 5}
    singletons = [m[0] for c, m in cluster_members.items() if len(m) == 1]

    no_abstract = [p for p in papers if not p.get("abstract")]
    sampled_dois = set()
    sampled = []

    def add(paper_list, n, label=""):
        added = 0
        candidates = [p for p in paper_list if p["doi"] not in sampled_dois]
        for p in random.sample(candidates, min(n, len(candidates))):
            sampled.append(p)
            sampled_dois.add(p["doi"])
            added += 1
        return added

    # Major clusters: 6 each
    for cid in sorted(major.keys()):
        add(major[cid], 6, f"major-C{cid}")

    # Minor clusters: 2 each
    for cid in sorted(minor.keys()):
        add(minor[cid], 2, f"minor-C{cid}")

    # Singletons: 3
    add(singletons, 3, "singleton")

    # No-abstract: ensure at least 5
    no_abs_sampled = sum(1 for p in sampled if not p.get("abstract"))
    if no_abs_sampled < 5:
        add(no_abstract, 5 - no_abs_sampled, "no-abstract")

    # Fill remaining to reach target
    remaining = target - len(sampled)
    if remaining > 0:
        pool = [p for p in papers if p["doi"] not in sampled_dois]
        add(pool, remaining, "fill")

    print(f"Sampled {len(sampled)} papers:")
    print(f"  From major clusters: {sum(1 for p in sampled if sizes[clusters[p['doi']]] >= 5)}")
    print(f"  From minor clusters: {sum(1 for p in sampled if 2 <= sizes[clusters[p['doi']]] < 5)}")
    print(f"  Singletons: {sum(1 for p in sampled if sizes[clusters[p['doi']]] == 1)}")
    print(f"  No abstract: {sum(1 for p in sampled if not p.get('abstract'))}")

    return sampled


def evaluate_extractions(extractions):
    """Evaluate fill rates for new schema fields."""
    total = len(extractions)
    if total == 0:
        return {"error": "no extractions"}

    fields = ["enables", "limits", "open_questions"]
    stats = {}
    for field in fields:
        non_empty = sum(1 for e in extractions if e.get(field, "").strip())
        stats[field] = {
            "non_empty": non_empty,
            "fill_rate": round(non_empty / total * 100, 1),
        }

    # Also check existing fields for comparison
    for field in ["problem", "method", "finding"]:
        non_empty = sum(1 for e in extractions if e.get(field, "").strip())
        stats[field] = {
            "non_empty": non_empty,
            "fill_rate": round(non_empty / total * 100, 1),
        }

    # GO/NO-GO
    enables_rate = stats["enables"]["fill_rate"]
    limits_rate = stats["limits"]["fill_rate"]

    if enables_rate < 40:
        verdict = f"KILL — enables {enables_rate}% < 40%"
    elif enables_rate < 60:
        verdict = f"CONDITIONAL — enables {enables_rate}% (threshold 60%)"
    else:
        verdict = f"GO — enables {enables_rate}%, limits {limits_rate}%"

    return {"field_stats": stats, "verdict": verdict}


def save_prompts_and_sample(sampled, prompts, batch_dois):
    """Save for external execution if needed."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "sampled_papers.json", "w") as f:
        json.dump(sampled, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_DIR / "prompts.json", "w") as f:
        json.dump({"prompts": prompts, "batch_dois": batch_dois}, f, indent=2, ensure_ascii=False)


def main():
    papers = load_papers()
    print(f"Loaded {len(papers)} papers")

    # Cluster
    clusters = cluster_papers(papers)
    sizes = Counter(clusters.values())
    print(f"Clusters: {len(sizes)} (major={sum(1 for s in sizes.values() if s >= 5)})")

    # Sample
    sampled = stratified_sample(papers, clusters)

    # Build prompts with new schema
    prompts, batch_dois = build_batch_prompts(sampled, batch_size=25)
    print(f"\nBuilt {len(prompts)} prompts ({len(sampled)} papers, batch_size=25)")

    # Save
    save_prompts_and_sample(sampled, prompts, batch_dois)
    print(f"Saved to {OUTPUT_DIR}")

    return prompts, batch_dois


if __name__ == "__main__":
    main()
