#!/usr/bin/env python3
"""e024: Semantic Theme Clustering — HDBSCAN on semantic embeddings of deduped limitations.

Depends on e019: outputs/e019/results.json (deduped_limitations)
Reference: e017 keyword-based greedy clustering for comparison.

Success criteria:
  - cluster_specific_rate >= 80% (mean intra-cluster cosine sim >= 0.5)
  - cross_cluster_duplicate_rate <= 10%
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import umap
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

E019_PATH = Path(__file__).resolve().parent.parent / "outputs/e019/results.json"
E017_PATH = Path(__file__).resolve().parent.parent / "outputs/e017/results.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e024"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
HDBSCAN_MIN_CLUSTER_SIZE = 5
INTRA_SIM_THRESHOLD = 0.5   # coherent if mean cosine sim >= this
CROSS_SIM_THRESHOLD = 0.85  # duplicate if cosine sim to another cluster centroid >= this


def load_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer
        print(f"Loading {EMBEDDING_MODEL}...")
        return SentenceTransformer(EMBEDDING_MODEL)
    except ImportError:
        print("sentence-transformers not available, installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "sentence-transformers", "-q"])
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(model, texts: list[str]) -> np.ndarray:
    print(f"Embedding {len(texts)} texts...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    return embeddings


def extract_theme_keywords(texts: list[str], n: int = 3) -> list[str]:
    """Extract top N keywords from a list of texts using TF-IDF."""
    if not texts:
        return []
    stop_words = (
        "english"  # sklearn built-in
    )
    try:
        vec = TfidfVectorizer(
            stop_words=stop_words,
            max_features=200,
            ngram_range=(1, 2),
            min_df=1,
        )
        X = vec.fit_transform(texts)
        scores = np.asarray(X.sum(axis=0)).ravel()
        top_idx = scores.argsort()[::-1][:n]
        feature_names = vec.get_feature_names_out()
        return [feature_names[i] for i in top_idx]
    except Exception:
        # Fallback: simple word frequency
        words = re.findall(r"\b[a-z]{4,}\b", " ".join(texts).lower())
        stop = {"this", "that", "with", "from", "have", "been", "which", "their",
                "these", "those", "also", "into", "only", "such", "does", "would",
                "could", "should", "more", "most", "some", "other", "than", "very",
                "will", "each", "both", "well", "still", "however", "while", "when",
                "model", "models", "approach", "method", "methods", "study", "work"}
        counts = Counter(w for w in words if w not in stop)
        return [w for w, _ in counts.most_common(n)]


def build_hdbscan_themes(texts: list[str], embeddings: np.ndarray) -> tuple[list[dict], np.ndarray]:
    """Run UMAP + HDBSCAN and build theme dicts. Returns (themes, labels, centroids)."""
    # Reduce dimensionality with UMAP before HDBSCAN — standard practice for
    # high-dim sentence embeddings (384-dim → 15-dim).
    print("Running UMAP dimensionality reduction (384 → 15 dims)...")
    reducer = umap.UMAP(
        n_components=15,
        n_neighbors=15,
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )
    reduced = reducer.fit_transform(embeddings)

    clusterer = HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=3,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(reduced)

    cluster_ids = sorted(set(labels))
    n_clusters = sum(1 for c in cluster_ids if c >= 0)
    n_noise = int((labels == -1).sum())
    print(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points")

    themes = []
    centroids = {}
    for cid in cluster_ids:
        if cid < 0:
            continue
        mask = labels == cid
        cluster_texts = [texts[i] for i in range(len(texts)) if mask[i]]
        cluster_embs = embeddings[mask]

        centroid = cluster_embs.mean(axis=0)
        centroids[cid] = centroid

        # Intra-cluster cosine similarity
        sims = cosine_similarity(cluster_embs, centroid.reshape(1, -1)).ravel()
        mean_intra_sim = float(sims.mean())

        keywords = extract_theme_keywords(cluster_texts, n=3)

        themes.append({
            "cluster_id": int(cid),
            "n_items": int(mask.sum()),
            "keywords": keywords,
            "mean_intra_sim": round(mean_intra_sim, 4),
            "coherent": mean_intra_sim >= INTRA_SIM_THRESHOLD,
            "samples": cluster_texts[:3],
        })

    themes.sort(key=lambda t: t["n_items"], reverse=True)
    return themes, labels, centroids


def evaluate_clustering(
    texts: list[str],
    embeddings: np.ndarray,
    labels: np.ndarray,
    themes: list[dict],
    centroids: dict,
) -> dict:
    """Compute cluster_specific_rate and cross_cluster_duplicate_rate."""
    coherent = sum(1 for t in themes if t["coherent"])
    total = len(themes)
    cluster_specific_rate = coherent / total if total > 0 else 0.0

    # Cross-cluster duplicate rate: fraction of items (excl. noise) whose
    # embedding has cosine sim >= CROSS_SIM_THRESHOLD to a DIFFERENT cluster centroid
    non_noise_mask = labels >= 0
    non_noise_indices = np.where(non_noise_mask)[0]
    if len(non_noise_indices) == 0:
        cross_dup_rate = 0.0
    else:
        non_noise_embs = embeddings[non_noise_mask]
        non_noise_labels = labels[non_noise_mask]
        centroid_ids = sorted(centroids.keys())
        centroid_matrix = np.stack([centroids[c] for c in centroid_ids])  # (K, D)

        sims = cosine_similarity(non_noise_embs, centroid_matrix)  # (N, K)
        duplicates = 0
        for i, own_label in enumerate(non_noise_labels):
            own_col = centroid_ids.index(own_label)
            for j, other_label in enumerate(centroid_ids):
                if other_label == own_label:
                    continue
                if sims[i, j] >= CROSS_SIM_THRESHOLD:
                    duplicates += 1
                    break
        cross_dup_rate = duplicates / len(non_noise_indices)

    return {
        "cluster_specific_rate": round(cluster_specific_rate, 4),
        "cross_cluster_duplicate_rate": round(cross_dup_rate, 4),
        "coherent_clusters": coherent,
        "total_clusters": total,
    }


def compare_with_e017(themes: list[dict]) -> dict:
    """Compare HDBSCAN cluster keywords with e017 greedy themes."""
    try:
        with open(E017_PATH) as f:
            e017 = json.load(f)
    except FileNotFoundError:
        return {"error": "e017 results not found"}

    # Collect all e017 theme labels
    e017_theme_labels = []
    for cluster_data in e017.get("clusters", {}).values():
        for t in cluster_data.get("limit_themes", []):
            e017_theme_labels.append(t.get("theme_label", ""))

    n_e017 = len(e017_theme_labels)
    n_hdbscan = len(themes)

    # One-to-one mapping: for each HDBSCAN cluster, check if any e017 theme
    # shares >= 1 keyword with the HDBSCAN cluster keywords
    matched = 0
    for theme in themes:
        hdbscan_kws = set(w for kw in theme["keywords"] for w in kw.lower().split())
        for label in e017_theme_labels:
            e017_kws = set(label.lower().replace("+", " ").split())
            if hdbscan_kws & e017_kws:
                matched += 1
                break

    one_to_one_rate = matched / n_hdbscan if n_hdbscan > 0 else 0.0

    return {
        "e017_themes": n_e017,
        "hdbscan_clusters": n_hdbscan,
        "one_to_one_mapping_rate": round(one_to_one_rate, 4),
    }


def run():
    # Load e019 deduped limitations
    with open(E019_PATH) as f:
        e019 = json.load(f)

    texts = e019["deduped_limitations"]
    n_input = len(texts)
    print(f"Loaded {n_input} deduped limitations from e019")

    # Embed
    model = load_sentence_transformer()
    embeddings = embed_texts(model, texts)

    # HDBSCAN clustering
    themes, labels, centroids = build_hdbscan_themes(texts, embeddings)
    n_clusters = len(themes)
    n_noise = int((labels == -1).sum())
    noise_rate = round(n_noise / n_input, 4)

    # Evaluation
    evaluation = evaluate_clustering(texts, embeddings, labels, themes, centroids)

    # e017 comparison
    e017_comparison = compare_with_e017(themes)

    # Verdict
    csr = evaluation["cluster_specific_rate"]
    ccdr = evaluation["cross_cluster_duplicate_rate"]
    if csr >= 0.80 and ccdr <= 0.10:
        verdict = "GO"
    else:
        parts = []
        if csr < 0.80:
            parts.append(f"cluster_specific_rate {csr:.1%} < 80%")
        if ccdr > 0.10:
            parts.append(f"cross_cluster_dup {ccdr:.1%} > 10%")
        verdict = "NO-GO — " + "; ".join(parts)

    # Print summary
    print(f"\n=== e024 Results ===")
    print(f"Clusters: {n_clusters}, Noise: {n_noise} ({noise_rate:.1%})")
    print(f"Cluster-specific rate: {csr:.1%} (coherent clusters: {evaluation['coherent_clusters']}/{evaluation['total_clusters']})")
    print(f"Cross-cluster dup rate: {ccdr:.1%}")
    print(f"e017 comparison: {e017_comparison}")
    print(f"Verdict: {verdict}")
    print("\nTop themes:")
    for t in themes[:10]:
        print(f"  C{t['cluster_id']}: {t['n_items']} items, kws={t['keywords']}, "
              f"intra_sim={t['mean_intra_sim']:.3f}, coherent={t['coherent']}")

    # Strip samples from output themes (keep first 3 samples per theme but not in main list)
    themes_out = []
    for t in themes:
        themes_out.append({
            "cluster_id": t["cluster_id"],
            "n_items": t["n_items"],
            "keywords": t["keywords"],
            "mean_intra_sim": t["mean_intra_sim"],
            "coherent": t["coherent"],
        })

    results = {
        "experiment": "e024",
        "title": "T5 Semantic Theme Clustering",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": {
            "n_deduped_limitations": n_input,
            "embedding_model": EMBEDDING_MODEL,
        },
        "hdbscan": {
            "min_cluster_size": HDBSCAN_MIN_CLUSTER_SIZE,
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "noise_rate": noise_rate,
        },
        "themes": themes_out,
        "evaluation": evaluation,
        "e017_comparison": e017_comparison,
        "verdict": verdict if verdict == "GO" else verdict.split(" — ")[0],
        "verdict_detail": f"cluster_specific >= 80% AND cross_cluster_dup <= 10% | actual: csr={csr:.3f}, ccdr={ccdr:.3f}",
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_path}")
    return results


if __name__ == "__main__":
    run()
