#!/usr/bin/env python3
"""e016: Extended extraction — enables/limits/open_questions for 3,070 papers.

Uses Claude Code subagent Tasks tool with haiku model.
Reuses extract.py build_batch_prompts() + parse_llm_response().

Success: enables >= 80%, limits >= 60%, open_questions >= 60%.
Kill: any field < 40%.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from papersift.extract import (
    build_batch_prompts,
    filter_extraction_quality,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell-sweep/papers_with_abstracts.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs/e016"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "results/virtual-cell-sweep/extractions_extended.json"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
BATCH_SIZE = 45


def load_papers():
    with open(DATA_PATH) as f:
        return json.load(f)


def prepare():
    """Prepare batches and prompts for subagent execution.

    Returns:
        dict with prompts, batch_dois, stats for subagent consumption.
    """
    papers = load_papers()
    print(f"Loaded {len(papers)} papers")

    # Filter to papers with abstracts (extraction quality depends on it)
    with_abstract = [p for p in papers if p.get("abstract", "").strip()]
    without_abstract = [p for p in papers if not p.get("abstract", "").strip()]
    print(f"  With abstract: {len(with_abstract)}")
    print(f"  Without abstract: {len(without_abstract)} (title-only extraction)")

    # Build prompts for ALL papers (title-only extraction still works per template)
    prompts, batch_dois = build_batch_prompts(papers, batch_size=BATCH_SIZE)
    print(f"Built {len(prompts)} batches ({BATCH_SIZE} papers/batch)")

    # Save prompts for checkpoint/resume
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    prep_data = {
        "total_papers": len(papers),
        "with_abstract": len(with_abstract),
        "without_abstract": len(without_abstract),
        "n_batches": len(prompts),
        "batch_size": BATCH_SIZE,
        "prompts": prompts,
        "batch_dois": batch_dois,
    }

    with open(OUTPUT_DIR / "prep.json", "w") as f:
        json.dump(prep_data, f, indent=2, ensure_ascii=False)

    print(f"Saved prep data to {OUTPUT_DIR / 'prep.json'}")
    return prep_data


def save_checkpoint(batch_idx: int, extractions: list[dict]):
    """Save checkpoint for a completed batch."""
    cp_path = CHECKPOINT_DIR / f"batch_{batch_idx:03d}.json"
    with open(cp_path, "w") as f:
        json.dump(extractions, f, indent=2, ensure_ascii=False)


def load_checkpoints() -> tuple[set[int], list[dict]]:
    """Load all existing checkpoints.

    Returns:
        (completed_batch_indices, all_extractions)
    """
    completed = set()
    all_extractions = []

    if not CHECKPOINT_DIR.exists():
        return completed, all_extractions

    for cp_file in sorted(CHECKPOINT_DIR.glob("batch_*.json")):
        idx = int(cp_file.stem.split("_")[1])
        with open(cp_file) as f:
            batch_ext = json.load(f)
        completed.add(idx)
        all_extractions.extend(batch_ext)

    return completed, all_extractions


def finalize(all_extractions: list[dict]) -> dict:
    """Finalize extraction results and compute statistics.

    Args:
        all_extractions: list of extraction dicts from all batches

    Returns:
        results dict with statistics and verdict
    """
    papers = load_papers()

    # Quality filter
    all_extractions = filter_extraction_quality(all_extractions)

    # Compute fill rates for extended fields
    total = len(all_extractions)
    fields = ["enables", "limits", "open_questions", "problem", "method", "finding"]
    field_stats = {}
    for field in fields:
        non_empty = sum(1 for e in all_extractions if e.get(field, "").strip())
        field_stats[field] = {
            "non_empty": non_empty,
            "rate_pct": round(non_empty / total * 100, 1) if total > 0 else 0,
        }

    # Verdict
    enables_rate = field_stats["enables"]["rate_pct"]
    limits_rate = field_stats["limits"]["rate_pct"]
    oq_rate = field_stats["open_questions"]["rate_pct"]

    if enables_rate < 40 or limits_rate < 40 or oq_rate < 40:
        verdict = f"KILL — enables {enables_rate}%, limits {limits_rate}%, open_questions {oq_rate}%"
    elif enables_rate >= 80 and limits_rate >= 60 and oq_rate >= 60:
        verdict = f"GO — enables {enables_rate}%, limits {limits_rate}%, open_questions {oq_rate}%"
    else:
        verdict = f"CONDITIONAL — enables {enables_rate}%, limits {limits_rate}%, open_questions {oq_rate}%"

    # Save extractions
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_extractions, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(all_extractions)} extractions to {OUTPUT_PATH}")

    # Save results
    results = {
        "experiment": "e016",
        "description": "Extended extraction — enables/limits/open_questions for 3,070 papers",
        "total_papers": len(papers),
        "total_extractions": total,
        "coverage_pct": round(total / len(papers) * 100, 1) if papers else 0,
        "field_fill_rates": field_stats,
        "verdict": verdict,
    }

    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved results to {OUTPUT_DIR / 'results.json'}")
    print(f"\nVerdict: {verdict}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="e016: Extended extraction")
    parser.add_argument("--prepare", action="store_true", help="Prepare batches only")
    parser.add_argument("--finalize", action="store_true", help="Finalize from checkpoints")
    args = parser.parse_args()

    if args.prepare:
        prepare()
    elif args.finalize:
        completed, all_ext = load_checkpoints()
        print(f"Loaded {len(completed)} checkpoints, {len(all_ext)} extractions")
        finalize(all_ext)
    else:
        print("Usage: --prepare or --finalize")
        print("  Subagent execution happens between prepare and finalize via Claude Code Agent tool.")
