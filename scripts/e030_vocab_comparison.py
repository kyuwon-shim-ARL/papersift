#!/usr/bin/env python3
"""e030: generate-vocab quality comparison — rule-based vs regex vs Haiku one-shot.

T4: Haiku one-shot vocab generation
T5: 3-arm clustering comparison (A: baseline, B: regex, C: Haiku)
T6: Verdict (GO: ARI>=0.7 AND coverage >= baseline+10pp)
"""

import json
import os
import random
import re
import sys
import time
from collections import defaultdict

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from papersift.entity_layer import EntityLayerBuilder, STOPWORDS, ImprovedEntityExtractor

DATA = "results/gut-microbiome-sweep/papers.json"
DOMAIN_YAML = "domains/gut_microbiome.yaml"
OUTPUT_VOCAB = "outputs/e030/vocab_comparison.json"
OUTPUT_CLUSTER = "outputs/e030/clustering_comparison.json"

SEED = 42
SAMPLE_SIZE = 50


def load_papers():
    with open(DATA) as f:
        return json.load(f)


def generate_regex_vocab(papers, seed=SEED, sample_size=SAMPLE_SIZE):
    """Reproduce the regex generate-vocab logic from cli.py."""
    rng = random.Random(seed)
    sample = rng.sample(papers, min(sample_size, len(papers)))
    titles = [p['title'] for p in sample if p.get('title')]

    extractor = ImprovedEntityExtractor()
    existing = set()
    for attr in ('methods', 'organisms', 'concepts', 'datasets'):
        for term in getattr(extractor, attr):
            existing.add(term.lower())

    cap_pattern = re.compile(r'\b([A-Z][A-Za-z0-9-]{2,})\b')
    candidates = defaultdict(int)
    for title in titles:
        for match in cap_pattern.finditer(title):
            term = match.group(1)
            key = term.lower()
            if key not in STOPWORDS and key not in existing and not term.isdigit() and len(term) > 1:
                candidates[term] += 1

    frequent = {term: count for term, count in candidates.items() if count >= 2}
    sorted_terms = sorted(frequent.items(), key=lambda x: -x[1])

    vocab = {
        'domain': 'gut_microbiome_regex',
        'description': 'Auto-generated vocabulary (regex) for gut_microbiome domain',
        'methods': [],
        'organisms': [],
        'concepts': [term for term, _ in sorted_terms],
        'datasets': [],
    }
    return vocab


def generate_haiku_vocab(papers, seed=SEED, sample_size=SAMPLE_SIZE):
    """Generate domain vocab using Claude CLI subprocess from sample titles."""
    import subprocess

    rng = random.Random(seed)
    sample = rng.sample(papers, min(sample_size, len(papers)))
    titles = [p['title'] for p in sample if p.get('title')]

    titles_text = "\n".join(f"- {t}" for t in titles[:50])

    prompt = f"""You are a domain expert in gut microbiome research. Given these 50 paper titles, extract domain-specific entities organized into 4 categories. Focus on technical terms that distinguish research sub-communities.

Paper titles:
{titles_text}

Output ONLY a YAML document with these exact keys:
- methods: bioinformatics tools, sequencing methods, statistical methods, analysis techniques
- organisms: bacterial taxa (phyla, genera, species), host organisms
- concepts: biological concepts, diseases, metabolites, pathways, interventions
- datasets: databases, reference datasets, major projects

Rules:
- Include 15-30 terms per category
- Use exact terms as they appear in scientific literature
- Exclude generic English words
- Each term should be specific enough to cluster papers by sub-community

Output YAML only, no explanation."""

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "haiku", "--output-format", "text"],
        capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    raw = result.stdout.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:yaml)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

    parsed = yaml.safe_load(raw)

    vocab = {
        'domain': 'gut_microbiome_haiku',
        'description': 'Auto-generated vocabulary (Haiku one-shot) for gut_microbiome domain',
        'methods': parsed.get('methods', []),
        'organisms': parsed.get('organisms', []),
        'concepts': parsed.get('concepts', []),
        'datasets': parsed.get('datasets', []),
    }
    return vocab


def run_clustering(papers, use_topics=True, domain_vocab=None, seed=SEED):
    """Run EntityLayerBuilder clustering, return {doi: cluster_id} and entity stats."""
    builder = EntityLayerBuilder(
        use_topics=use_topics,
        domain_vocab=domain_vocab,
        use_abstract=False,
    )
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=1.0, seed=seed)

    # Entity coverage: papers with >= 1 entity
    total = len(papers)
    with_entities = sum(1 for doi in builder._paper_entities if len(builder._paper_entities[doi]) > 0)
    coverage = with_entities / total if total > 0 else 0

    # Average entities per paper
    all_counts = [len(ents) for ents in builder._paper_entities.values()]
    avg_entities = sum(all_counts) / len(all_counts) if all_counts else 0

    # Cluster stats
    cluster_counts = defaultdict(int)
    for cid in clusters.values():
        cluster_counts[cid] += 1
    n_clusters = len(cluster_counts)
    singletons = sum(1 for c in cluster_counts.values() if c == 1)
    singleton_pct = singletons / total * 100 if total > 0 else 0

    return {
        'clusters': clusters,
        'coverage': coverage,
        'avg_entities': avg_entities,
        'n_clusters': n_clusters,
        'singleton_pct': singleton_pct,
        'singletons': singletons,
    }


def compute_ari(clusters_a, clusters_b):
    """Compute Adjusted Rand Index between two partitions."""
    from sklearn.metrics import adjusted_rand_score

    # Align DOIs
    common_dois = sorted(set(clusters_a.keys()) & set(clusters_b.keys()))
    if len(common_dois) < 2:
        return 0.0

    labels_a = [clusters_a[d] for d in common_dois]
    labels_b = [clusters_b[d] for d in common_dois]
    return adjusted_rand_score(labels_a, labels_b)


def main():
    papers = load_papers()
    print(f"Loaded {len(papers)} papers")

    # ── T4: Generate vocabs ──────────────────────────────────────
    print("\n=== T4: Vocabulary Generation ===")

    # Load curated baseline vocab
    with open(DOMAIN_YAML) as f:
        baseline_vocab = yaml.safe_load(f)
    baseline_terms = sum(
        len(baseline_vocab.get(k, []))
        for k in ('methods', 'organisms', 'concepts', 'datasets')
    )
    print(f"Arm A (baseline): {DOMAIN_YAML} — {baseline_terms} terms")

    # Regex vocab
    regex_vocab = generate_regex_vocab(papers)
    regex_terms = len(regex_vocab['concepts'])
    print(f"Arm B (regex): {regex_terms} terms from {SAMPLE_SIZE} sample titles")

    # Haiku vocab
    print("Arm C (Haiku): calling Claude Haiku...")
    t0 = time.time()
    haiku_vocab = generate_haiku_vocab(papers)
    haiku_time = time.time() - t0
    haiku_terms = sum(
        len(haiku_vocab.get(k, []))
        for k in ('methods', 'organisms', 'concepts', 'datasets')
    )
    print(f"Arm C (Haiku): {haiku_terms} terms in {haiku_time:.1f}s")

    # Save vocab comparison
    vocab_result = {
        "experiment": "e030-T4",
        "dataset": DATA,
        "sample_size": SAMPLE_SIZE,
        "seed": SEED,
        "arms": {
            "A_baseline": {
                "source": DOMAIN_YAML,
                "total_terms": baseline_terms,
                "methods": len(baseline_vocab.get('methods', [])),
                "organisms": len(baseline_vocab.get('organisms', [])),
                "concepts": len(baseline_vocab.get('concepts', [])),
                "datasets": len(baseline_vocab.get('datasets', [])),
            },
            "B_regex": {
                "source": "regex generate-vocab",
                "total_terms": regex_terms,
                "methods": len(regex_vocab['methods']),
                "organisms": len(regex_vocab['organisms']),
                "concepts": len(regex_vocab['concepts']),
                "datasets": len(regex_vocab['datasets']),
                "terms": regex_vocab['concepts'][:30],
            },
            "C_haiku": {
                "source": "Claude Haiku one-shot",
                "total_terms": haiku_terms,
                "methods": haiku_vocab.get('methods', []),
                "organisms": haiku_vocab.get('organisms', []),
                "concepts": haiku_vocab.get('concepts', []),
                "datasets": haiku_vocab.get('datasets', []),
                "generation_time_s": round(haiku_time, 1),
            },
        },
    }
    with open(OUTPUT_VOCAB, 'w') as f:
        json.dump(vocab_result, f, indent=2, ensure_ascii=False)
    print(f"Vocab comparison saved to {OUTPUT_VOCAB}")

    # ── T5: 3-arm clustering comparison ──────────────────────────
    print("\n=== T5: Clustering Comparison ===")

    # Arm A: baseline (curated domain vocab)
    print("Running Arm A (baseline)...")
    arm_a = run_clustering(papers, use_topics=True, domain_vocab=baseline_vocab, seed=SEED)
    print(f"  coverage={arm_a['coverage']:.3f}, clusters={arm_a['n_clusters']}, "
          f"singletons={arm_a['singleton_pct']:.1f}%, entities/paper={arm_a['avg_entities']:.2f}")

    # Arm B: regex vocab
    print("Running Arm B (regex)...")
    arm_b = run_clustering(papers, use_topics=True, domain_vocab=regex_vocab, seed=SEED)
    print(f"  coverage={arm_b['coverage']:.3f}, clusters={arm_b['n_clusters']}, "
          f"singletons={arm_b['singleton_pct']:.1f}%, entities/paper={arm_b['avg_entities']:.2f}")

    # Arm C: Haiku vocab
    print("Running Arm C (Haiku)...")
    arm_c = run_clustering(papers, use_topics=True, domain_vocab=haiku_vocab, seed=SEED)
    print(f"  coverage={arm_c['coverage']:.3f}, clusters={arm_c['n_clusters']}, "
          f"singletons={arm_c['singleton_pct']:.1f}%, entities/paper={arm_c['avg_entities']:.2f}")

    # ARI comparisons
    ari_b_vs_a = compute_ari(arm_a['clusters'], arm_b['clusters'])
    ari_c_vs_a = compute_ari(arm_a['clusters'], arm_c['clusters'])
    ari_b_vs_c = compute_ari(arm_b['clusters'], arm_c['clusters'])

    print(f"\nARI(B vs A) = {ari_b_vs_a:.4f}")
    print(f"ARI(C vs A) = {ari_c_vs_a:.4f}")
    print(f"ARI(B vs C) = {ari_b_vs_c:.4f}")

    # Coverage delta
    cov_delta_b = arm_b['coverage'] - arm_a['coverage']
    cov_delta_c = arm_c['coverage'] - arm_a['coverage']

    # ── T6: Verdict ──────────────────────────────────────────────
    print("\n=== T6: Verdict ===")

    # GO conditions per arm: ARI >= 0.7 AND coverage >= baseline + 10pp
    baseline_cov = arm_a['coverage']
    threshold_cov = baseline_cov + 0.10

    b_ari_pass = ari_b_vs_a >= 0.7
    b_cov_pass = arm_b['coverage'] >= threshold_cov
    b_go = b_ari_pass and b_cov_pass

    c_ari_pass = ari_c_vs_a >= 0.7
    c_cov_pass = arm_c['coverage'] >= threshold_cov
    c_go = c_ari_pass and c_cov_pass

    if c_go and b_go:
        verdict = "GO — Both regex and Haiku meet criteria"
        best_arm = "C_haiku" if arm_c['coverage'] > arm_b['coverage'] else "B_regex"
    elif c_go:
        verdict = "CONDITIONAL — Haiku only meets criteria"
        best_arm = "C_haiku"
    elif b_go:
        verdict = "CONDITIONAL — Regex only meets criteria"
        best_arm = "B_regex"
    else:
        verdict = "NO-GO — Neither arm meets ARI>=0.7 AND coverage>=baseline+10pp"
        best_arm = "A_baseline"

    print(f"\nBaseline coverage: {baseline_cov:.3f}")
    print(f"Coverage threshold: {threshold_cov:.3f} (baseline + 10pp)")
    print(f"Arm B: ARI={ari_b_vs_a:.4f} ({'PASS' if b_ari_pass else 'FAIL'}), "
          f"coverage={arm_b['coverage']:.3f} ({'PASS' if b_cov_pass else 'FAIL'}) → {'GO' if b_go else 'NO-GO'}")
    print(f"Arm C: ARI={ari_c_vs_a:.4f} ({'PASS' if c_ari_pass else 'FAIL'}), "
          f"coverage={arm_c['coverage']:.3f} ({'PASS' if c_cov_pass else 'FAIL'}) → {'GO' if c_go else 'NO-GO'}")
    print(f"\nVERDICT: {verdict}")
    print(f"Best arm: {best_arm}")

    # Save clustering comparison
    cluster_result = {
        "experiment": "e030-T5-T6",
        "dataset": DATA,
        "n_papers": len(papers),
        "seed": SEED,
        "arms": {
            "A_baseline": {
                "vocab_source": DOMAIN_YAML,
                "coverage": round(arm_a['coverage'], 4),
                "avg_entities": round(arm_a['avg_entities'], 2),
                "n_clusters": arm_a['n_clusters'],
                "singleton_pct": round(arm_a['singleton_pct'], 2),
            },
            "B_regex": {
                "vocab_source": "regex generate-vocab",
                "coverage": round(arm_b['coverage'], 4),
                "avg_entities": round(arm_b['avg_entities'], 2),
                "n_clusters": arm_b['n_clusters'],
                "singleton_pct": round(arm_b['singleton_pct'], 2),
                "coverage_delta": round(cov_delta_b, 4),
                "ari_vs_baseline": round(ari_b_vs_a, 4),
                "ari_pass": b_ari_pass,
                "coverage_pass": b_cov_pass,
                "go": b_go,
            },
            "C_haiku": {
                "vocab_source": "Claude Haiku one-shot",
                "coverage": round(arm_c['coverage'], 4),
                "avg_entities": round(arm_c['avg_entities'], 2),
                "n_clusters": arm_c['n_clusters'],
                "singleton_pct": round(arm_c['singleton_pct'], 2),
                "coverage_delta": round(cov_delta_c, 4),
                "ari_vs_baseline": round(ari_c_vs_a, 4),
                "ari_pass": c_ari_pass,
                "coverage_pass": c_cov_pass,
                "go": c_go,
            },
        },
        "cross_ari": {
            "B_vs_A": round(ari_b_vs_a, 4),
            "C_vs_A": round(ari_c_vs_a, 4),
            "B_vs_C": round(ari_b_vs_c, 4),
        },
        "go_criteria": {
            "ari_threshold": 0.7,
            "coverage_threshold": round(threshold_cov, 4),
            "baseline_coverage": round(baseline_cov, 4),
        },
        "verdict": verdict,
        "best_arm": best_arm,
    }

    with open(OUTPUT_CLUSTER, 'w') as f:
        json.dump(cluster_result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {OUTPUT_CLUSTER}")


if __name__ == "__main__":
    main()
