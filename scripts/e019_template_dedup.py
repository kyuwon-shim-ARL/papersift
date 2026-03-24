#!/usr/bin/env python3
"""e019: Template Deduplication — clean limitation/open-question texts.

Tests three dedup methods against raw LLM-extracted limitations and open_questions:
  T0: Baseline (exact string uniqueness)
  M1: regex_expanded  — broader boilerplate regex removal
  M2: semantic_embedding — cosine similarity >= 0.85 dedup
  M3: hybrid — regex_expanded then semantic_embedding

Success criteria:
  GO:           unique_lim >= 80% AND unique_OQ >= 50%
  CONDITIONAL:  unique_lim >= 60% AND unique_OQ >= 30%
  KILL:         unique_lim < 50%
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

EXTRACTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "results/virtual-cell-sweep/extractions_extended.json"
)
E017_PATH = Path(__file__).resolve().parent.parent / "outputs/e017/results.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e019"

# ── Original GENERIC_PATTERNS from e017 ──────────────────────────────────────
GENERIC_PATTERNS_BASE = [
    r"more data",
    r"more research",
    r"further (study|studies|research|investigation|work)",
    r"larger (dataset|sample|cohort)",
    r"additional (data|experiments|validation)",
    r"limited (data|sample size)",
    r"computational(ly)? (expensive|costly|intensive)",
    r"not (yet |fully )?(validated|verified|tested)",
]

# ── Expanded boilerplate patterns for e019 ───────────────────────────────────
GENERIC_PATTERNS_EXPANDED = GENERIC_PATTERNS_BASE + [
    r"further research is needed",
    r"more studies are (required|needed|necessary)",
    r"limitations? (include|of (this|the) (study|work|approach|model))",
    r"future work should",
    r"future (studies|research|work) (should|could|may|might|will)",
    r"this (study|work|paper|model) (is |has )?(limited|constrained)",
    r"(remains?|remain) (to be|an) (open|challenging|difficult|unsolved|unclear)",
    r"(needs?|requires?) (further|additional|more) (investigation|validation|testing|study)",
    r"(broader|wider) (applicability|generalization|validation)",
    r"long[- ]term (impact|effect|consequence|outcome)",
    r"(more|additional) (experimental|empirical) (validation|evidence|data)",
    r"(lack|absence) of (sufficient|enough|adequate) (data|evidence)",
    r"(scalability|generalizability) (remains?|is) (a|an) (challenge|concern|issue|limitation)",
    r"(real[- ]world|in vivo|clinical) (validation|testing|application)",
    r"(further|additional) (work|effort|investigation) (is|are) (needed|required|necessary)",
    r"investigation needed",
    r"(unclear|unknown) (whether|how|if|what)",
    r"(need|require)s? validation",
    r"(applied|tested) (only |primarily )?(in|to|on) (a |the )?(limited|small|single)",
]

GENERIC_RE_EXPANDED = re.compile(
    "|".join(GENERIC_PATTERNS_EXPANDED), re.IGNORECASE
)


def is_generic_expanded(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return True
    return bool(GENERIC_RE_EXPANDED.search(text))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
    with open(EXTRACTIONS_PATH) as f:
        extractions = json.load(f)
    with open(E017_PATH) as f:
        e017 = json.load(f)
    return extractions, e017


# ── Baseline: exact-string uniqueness ────────────────────────────────────────

def baseline_stats(extractions: list[dict]) -> dict:
    limitations = [
        e["limits"].strip()
        for e in extractions
        if e.get("limits", "").strip()
    ]
    open_questions = [
        e["open_questions"].strip()
        for e in extractions
        if e.get("open_questions", "").strip()
    ]

    unique_lim = len(set(limitations))
    unique_oq = len(set(open_questions))

    return {
        "total_lim": len(limitations),
        "unique_lim": unique_lim,
        "unique_lim_rate": round(unique_lim / len(limitations), 4) if limitations else 0.0,
        "total_oq": len(open_questions),
        "unique_oq": unique_oq,
        "unique_oq_rate": round(unique_oq / len(open_questions), 4) if open_questions else 0.0,
        "all_limitations": limitations,
        "all_open_questions": open_questions,
    }


# ── Method 1: regex_expanded ─────────────────────────────────────────────────

def apply_regex_expanded(limitations: list[str], open_questions: list[str]) -> dict:
    kept_lim = [t for t in limitations if not is_generic_expanded(t)]
    kept_oq = [t for t in open_questions if not is_generic_expanded(t)]

    unique_lim = len(set(kept_lim))
    unique_oq = len(set(kept_oq))

    return {
        "kept_lim": kept_lim,
        "kept_oq": kept_oq,
        "unique_lim_rate": round(unique_lim / len(kept_lim), 4) if kept_lim else 0.0,
        "unique_oq_rate": round(unique_oq / len(kept_oq), 4) if kept_oq else 0.0,
        "removed_lim": len(limitations) - len(kept_lim),
        "removed_oq": len(open_questions) - len(kept_oq),
    }


# ── Method 2: semantic_embedding ─────────────────────────────────────────────

def apply_semantic_dedup(
    texts: list[str], threshold: float = 0.85, batch_size: int = 512
) -> list[str]:
    """Return deduplicated texts using cosine similarity >= threshold."""
    if not texts:
        return []

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Embed in batches
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embs = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        all_embeddings.append(embs)
    embeddings = np.vstack(all_embeddings)

    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    # Greedy dedup: mark duplicates
    n = len(texts)
    kept_mask = np.ones(n, dtype=bool)

    for i in range(n):
        if not kept_mask[i]:
            continue
        # Compute cosine similarity of i with all j > i that are still kept
        sims = embeddings[i + 1 :] @ embeddings[i]
        dups = np.where(sims >= threshold)[0] + i + 1
        for d in dups:
            if kept_mask[d]:
                kept_mask[d] = False

    return [texts[i] for i in range(n) if kept_mask[i]]


def apply_semantic_embedding(limitations: list[str], open_questions: list[str]) -> dict:
    threshold = 0.85

    print(f"  Embedding {len(limitations)} limitations...", flush=True)
    kept_lim = apply_semantic_dedup(limitations, threshold)

    print(f"  Embedding {len(open_questions)} open questions...", flush=True)
    kept_oq = apply_semantic_dedup(open_questions, threshold)

    unique_lim = len(set(kept_lim))
    unique_oq = len(set(kept_oq))

    return {
        "kept_lim": kept_lim,
        "kept_oq": kept_oq,
        "unique_lim_rate": round(unique_lim / len(kept_lim), 4) if kept_lim else 0.0,
        "unique_oq_rate": round(unique_oq / len(kept_oq), 4) if kept_oq else 0.0,
        "removed_lim": len(limitations) - len(kept_lim),
        "removed_oq": len(open_questions) - len(kept_oq),
        "threshold": threshold,
    }


# ── Method 3: hybrid ─────────────────────────────────────────────────────────

def apply_hybrid(limitations: list[str], open_questions: list[str]) -> dict:
    # Step 1: regex
    regex_result = apply_regex_expanded(limitations, open_questions)
    after_regex_lim = regex_result["kept_lim"]
    after_regex_oq = regex_result["kept_oq"]

    # Step 2: semantic on remainder
    print(f"  Hybrid: after regex {len(after_regex_lim)} lim, {len(after_regex_oq)} oq", flush=True)
    threshold = 0.85

    print(f"  Embedding {len(after_regex_lim)} limitations (hybrid)...", flush=True)
    kept_lim = apply_semantic_dedup(after_regex_lim, threshold)

    print(f"  Embedding {len(after_regex_oq)} open questions (hybrid)...", flush=True)
    kept_oq = apply_semantic_dedup(after_regex_oq, threshold)

    unique_lim = len(set(kept_lim))
    unique_oq = len(set(kept_oq))

    return {
        "kept_lim": kept_lim,
        "kept_oq": kept_oq,
        "unique_lim_rate": round(unique_lim / len(kept_lim), 4) if kept_lim else 0.0,
        "unique_oq_rate": round(unique_oq / len(kept_oq), 4) if kept_oq else 0.0,
        "removed_lim": len(limitations) - len(kept_lim),
        "removed_oq": len(open_questions) - len(kept_oq),
    }


# ── Verdict ───────────────────────────────────────────────────────────────────

def determine_verdict(unique_lim_rate: float, unique_oq_rate: float) -> str:
    if unique_lim_rate >= 0.80 and unique_oq_rate >= 0.50:
        return "GO"
    elif unique_lim_rate >= 0.60 and unique_oq_rate >= 0.30:
        return "CONDITIONAL"
    else:
        return "KILL"


def pick_best_method(methods: dict) -> str:
    """Pick best method by combined unique rate score."""
    scores = {}
    for name, m in methods.items():
        # Weighted: lim 60%, oq 40%
        scores[name] = 0.6 * m["unique_lim_rate"] + 0.4 * m["unique_oq_rate"]
    return max(scores, key=scores.__getitem__)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("Loading data...", flush=True)
    extractions, e017 = load_data()

    # T0: Baseline
    print("\n[T0] Baseline measurement", flush=True)
    base = baseline_stats(extractions)
    print(f"  Total limitations: {base['total_lim']}, unique: {base['unique_lim']} "
          f"({base['unique_lim_rate']:.1%})")
    print(f"  Total open_questions: {base['total_oq']}, unique: {base['unique_oq']} "
          f"({base['unique_oq_rate']:.1%})")

    all_lim = base["all_limitations"]
    all_oq = base["all_open_questions"]

    # M1: regex_expanded
    print("\n[M1] regex_expanded", flush=True)
    m1 = apply_regex_expanded(all_lim, all_oq)
    print(f"  Removed lim: {m1['removed_lim']}, oq: {m1['removed_oq']}")
    print(f"  unique_lim_rate: {m1['unique_lim_rate']:.1%}, unique_oq_rate: {m1['unique_oq_rate']:.1%}")

    # M2: semantic_embedding
    print("\n[M2] semantic_embedding", flush=True)
    m2 = apply_semantic_embedding(all_lim, all_oq)
    print(f"  Removed lim: {m2['removed_lim']}, oq: {m2['removed_oq']}")
    print(f"  unique_lim_rate: {m2['unique_lim_rate']:.1%}, unique_oq_rate: {m2['unique_oq_rate']:.1%}")

    # M3: hybrid
    print("\n[M3] hybrid (regex then semantic)", flush=True)
    m3 = apply_hybrid(all_lim, all_oq)
    print(f"  Removed lim: {m3['removed_lim']}, oq: {m3['removed_oq']}")
    print(f"  unique_lim_rate: {m3['unique_lim_rate']:.1%}, unique_oq_rate: {m3['unique_oq_rate']:.1%}")

    # Determine best method and verdict
    methods_summary = {
        "regex_expanded": {
            "unique_lim_rate": m1["unique_lim_rate"],
            "unique_oq_rate": m1["unique_oq_rate"],
            "removed_lim": m1["removed_lim"],
            "removed_oq": m1["removed_oq"],
        },
        "semantic_embedding": {
            "unique_lim_rate": m2["unique_lim_rate"],
            "unique_oq_rate": m2["unique_oq_rate"],
            "removed_lim": m2["removed_lim"],
            "removed_oq": m2["removed_oq"],
            "threshold": m2["threshold"],
        },
        "hybrid": {
            "unique_lim_rate": m3["unique_lim_rate"],
            "unique_oq_rate": m3["unique_oq_rate"],
            "removed_lim": m3["removed_lim"],
            "removed_oq": m3["removed_oq"],
        },
    }

    best_method = pick_best_method(methods_summary)
    best = {"regex_expanded": m1, "semantic_embedding": m2, "hybrid": m3}[best_method]
    verdict = determine_verdict(best["unique_lim_rate"], best["unique_oq_rate"])

    results = {
        "experiment": "e019",
        "title": "T5 Template Dedup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "total_lim": base["total_lim"],
            "unique_lim": base["unique_lim"],
            "unique_lim_rate": base["unique_lim_rate"],
            "total_oq": base["total_oq"],
            "unique_oq": base["unique_oq"],
            "unique_oq_rate": base["unique_oq_rate"],
        },
        "methods": methods_summary,
        "best_method": best_method,
        "verdict": verdict,
        "deduped_limitations": best["kept_lim"],
        "deduped_open_questions": best["kept_oq"],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Best method : {best_method}")
    print(f"  unique_lim_rate : {best['unique_lim_rate']:.1%}")
    print(f"  unique_oq_rate  : {best['unique_oq_rate']:.1%}")
    print(f"Verdict     : {verdict}")
    print(f"Saved to    : {out_path}")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    run()
