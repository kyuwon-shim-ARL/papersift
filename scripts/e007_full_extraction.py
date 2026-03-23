#!/usr/bin/env python3
"""
Experiment e007: Full 3,070-paper LLM extraction with checkpoint/resume.

Reuses e006 pmc_fulltext.json (664 papers with sections) to avoid re-fetching.
Papers already have abstracts and cluster_ids from papers_enriched.json.

Usage:
    # Full run (prepare + extract + finalize)
    python scripts/e007_full_extraction.py

    # Resume from checkpoint (skips completed batches)
    python scripts/e007_full_extraction.py --resume

    # Prepare prompts only (no extraction)
    python scripts/e007_full_extraction.py --prepare-only

    # Finalize from saved extractions (skip extraction)
    python scripts/e007_full_extraction.py --finalize-only

    # Validate success criteria
    python scripts/e007_full_extraction.py --validate
"""

import argparse
import concurrent.futures
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PAPERS = PROJECT_ROOT / "results" / "virtual-cell-sweep" / "papers_enriched.json"
PMC_FULLTEXT = PROJECT_ROOT / "outputs" / "e006" / "pmc_fulltext.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "e007"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

# Extraction parameters (critique-adjusted)
ABSTRACT_BATCH_SIZE = 45
FULLTEXT_BATCH_SIZE = 10
MAX_PARALLEL = 5
CLAUDE_TIMEOUT = 300  # seconds per batch


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def convert_fulltext_list_to_dict(fulltext_list: list) -> dict:
    """Convert e006 pmc_fulltext.json list format to attach_fulltext dict format.

    e006 format: [{doi, pmcid, methods_text, results_text, discussion_text, full_body_text}]
    attach format: {doi_lower: {methods_text, results_text, discussion_text, full_body_text}}
    """
    result = {}
    for item in fulltext_list:
        doi = item.get("doi", "").lower()
        if not doi:
            continue
        # Only include if has usable sections
        methods = item.get("methods_text", "")
        results = item.get("results_text", "")
        discussion = item.get("discussion_text", "")
        full_body = item.get("full_body_text", "")
        if methods or results or discussion:
            result[doi] = {
                "methods_text": methods,
                "results_text": results,
                "discussion_text": discussion,
                "full_body_text": full_body,
            }
    return result


def attach_fulltext_from_cache(papers: list, fulltext_dict: dict) -> tuple[list, dict]:
    """Attach pre-loaded fulltext to papers (avoids network calls)."""
    total = len(papers)
    with_ft = 0
    without_ft = 0
    without_doi = 0

    for paper in papers:
        doi = paper.get("doi", "")
        if not doi:
            without_doi += 1
            paper["fulltext"] = {}
            continue

        doi_clean = doi.replace("https://doi.org/", "").lower()
        ft = fulltext_dict.get(doi_clean, {})
        paper["fulltext"] = ft
        if ft:
            with_ft += 1
        else:
            without_ft += 1

    stats = {
        "total": total,
        "with_fulltext": with_ft,
        "without_fulltext": without_ft,
        "without_doi": without_doi,
    }
    return papers, stats


def build_prompts(papers: list) -> tuple[list, list, dict]:
    """Build extraction prompts, splitting fulltext vs abstract-only.

    Returns: (prompts, batch_doi_lists, split_stats)
    """
    from papersift.extract import (
        build_batch_prompts,
        build_fulltext_batch_prompts,
    )

    papers_with_ft = [p for p in papers if p.get("fulltext")]
    papers_without_ft = [p for p in papers if not p.get("fulltext")]

    prompts = []
    batch_doi_lists = []

    if papers_with_ft:
        ft_prompts, ft_dois = build_fulltext_batch_prompts(
            papers_with_ft, batch_size=FULLTEXT_BATCH_SIZE
        )
        prompts.extend(ft_prompts)
        batch_doi_lists.extend(ft_dois)

    if papers_without_ft:
        abs_prompts, abs_dois = build_batch_prompts(
            papers_without_ft, batch_size=ABSTRACT_BATCH_SIZE
        )
        prompts.extend(abs_prompts)
        batch_doi_lists.extend(abs_dois)

    split_stats = {
        "fulltext_papers": len(papers_with_ft),
        "abstract_papers": len(papers_without_ft),
        "fulltext_batches": len([p for p in papers_with_ft]) // FULLTEXT_BATCH_SIZE + (1 if len(papers_with_ft) % FULLTEXT_BATCH_SIZE else 0) if papers_with_ft else 0,
        "abstract_batches": len([p for p in papers_without_ft]) // ABSTRACT_BATCH_SIZE + (1 if len(papers_without_ft) % ABSTRACT_BATCH_SIZE else 0) if papers_without_ft else 0,
        "total_prompts": len(prompts),
    }

    return prompts, batch_doi_lists, split_stats


def extract_batch(idx: int, prompt: str) -> tuple[int, list]:
    """Extract one batch via claude CLI."""
    import os

    from papersift.extract import parse_llm_response

    # Strip CLAUDECODE env var to allow nested subprocess
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", "claude-haiku-4-5-20251001"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            env=clean_env,
        )
        if result.returncode != 0:
            stderr_msg = result.stderr[:200] if result.stderr else "(no stderr)"
            print(f"  Warning: Batch {idx+1} claude CLI returned code {result.returncode}: {stderr_msg}", file=sys.stderr)
            return idx, []
        response = json.loads(result.stdout)
        text = response.get("result", "")
        return idx, parse_llm_response(text)
    except subprocess.TimeoutExpired:
        print(f"  Warning: Batch {idx+1} timed out after {CLAUDE_TIMEOUT}s", file=sys.stderr)
        return idx, []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Warning: Batch {idx+1} parse error: {e}", file=sys.stderr)
        return idx, []


def run_extraction_with_checkpoint(
    prompts: list, batch_doi_lists: list, resume: bool = False, max_parallel: int = MAX_PARALLEL
) -> list:
    """Run LLM extraction with per-batch checkpoint/resume.

    Each batch result is saved immediately to checkpoints/batch_NNN.json.
    On resume, completed batches are skipped.
    """
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    results = [None] * len(prompts)
    pending_indices = []

    # Check existing checkpoints
    for i in range(len(prompts)):
        cp_path = CHECKPOINT_DIR / f"batch_{i:04d}.json"
        if resume and cp_path.exists():
            data = load_json(cp_path)
            results[i] = data.get("extractions", [])
            print(f"  Batch {i+1}/{len(prompts)}: restored from checkpoint ({len(results[i])} extractions)", file=sys.stderr)
        else:
            pending_indices.append(i)

    if not pending_indices:
        print("All batches already completed.", file=sys.stderr)
        return results

    print(f"\nExtracting {len(pending_indices)}/{len(prompts)} pending batches (max_parallel={max_parallel})...\n", file=sys.stderr)

    completed = len(prompts) - len(pending_indices)
    failed = 0
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {
            pool.submit(extract_batch, i, prompts[i]): i
            for i in pending_indices
        }

        for future in concurrent.futures.as_completed(futures):
            idx, parsed = future.result()
            results[idx] = parsed
            completed += 1

            if not parsed:
                failed += 1
            else:
                # Only save checkpoint on success (allows retry on resume)
                cp_data = {
                    "batch_index": idx,
                    "dois": batch_doi_lists[idx],
                    "extractions": parsed,
                    "timestamp": datetime.now().isoformat(),
                    "extraction_count": len(parsed),
                }
                save_json(cp_data, CHECKPOINT_DIR / f"batch_{idx:04d}.json")

            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (len(prompts) - completed) / rate if rate > 0 else 0
            print(
                f"  Batch {idx+1:>4}/{len(prompts)}: {len(parsed):>3} extractions | "
                f"Progress: {completed}/{len(prompts)} | "
                f"ETA: {eta/60:.1f}min",
                file=sys.stderr,
            )

    total_extractions = sum(len(r) for r in results if r)
    print(
        f"\nExtraction complete: {total_extractions} total extractions, "
        f"{failed} failed batches",
        file=sys.stderr,
    )

    return [r if r is not None else [] for r in results]


def merge_and_export(papers: list, all_extractions: list, clusters: dict, output_dir: Path):
    """Merge extractions into papers and export."""
    from papersift.extract import merge_extractions

    # Flatten extraction results
    flat_extractions = []
    for batch in all_extractions:
        flat_extractions.extend(batch)

    print(f"\nMerging {len(flat_extractions)} extractions into {len(papers)} papers...", file=sys.stderr)
    merge_extractions(papers, flat_extractions)

    # Build enriched output
    enriched_papers = []
    for paper in papers:
        doi = paper.get("doi", "")
        enriched = {
            "doi": doi,
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "cluster_id": str(paper.get("cluster_id")) if paper.get("cluster_id") is not None else None,
            "abstract": paper.get("abstract", ""),
            "problem": paper.get("problem", ""),
            "method": paper.get("method", ""),
            "finding": paper.get("finding", ""),
            "dataset": paper.get("dataset", ""),
            "metric": paper.get("metric", ""),
            "baseline": paper.get("baseline", ""),
            "result": paper.get("result", ""),
            "has_fulltext": bool(paper.get("fulltext")),
        }
        enriched_papers.append(enriched)

    # Stats
    total = len(enriched_papers)
    with_problem = sum(1 for p in enriched_papers if p["problem"])
    with_method = sum(1 for p in enriched_papers if p["method"])
    with_finding = sum(1 for p in enriched_papers if p["finding"])
    with_dataset = sum(1 for p in enriched_papers if p["dataset"])
    with_metric = sum(1 for p in enriched_papers if p["metric"])
    with_baseline = sum(1 for p in enriched_papers if p["baseline"])
    with_result = sum(1 for p in enriched_papers if p["result"])
    with_ft = sum(1 for p in enriched_papers if p["has_fulltext"])

    stats = {
        "total_papers": total,
        "with_fulltext": with_ft,
        "coverage": {
            "problem": round(100 * with_problem / total, 1),
            "method": round(100 * with_method / total, 1),
            "finding": round(100 * with_finding / total, 1),
            "dataset": round(100 * with_dataset / total, 1),
            "metric": round(100 * with_metric / total, 1),
            "baseline": round(100 * with_baseline / total, 1),
            "result": round(100 * with_result / total, 1),
        },
        "timestamp": datetime.now().isoformat(),
    }

    # Export
    output_dir.mkdir(parents=True, exist_ok=True)

    save_json(enriched_papers, output_dir / "enriched_papers.json")
    save_json(clusters, output_dir / "clusters.json")
    save_json(stats, output_dir / "extraction_stats.json")

    # Also save flat extractions for reproducibility
    save_json(flat_extractions, output_dir / "raw_extractions.json")

    print(f"\n=== Export Summary ===", file=sys.stderr)
    print(f"Total papers: {total}", file=sys.stderr)
    print(f"With fulltext: {with_ft} ({100*with_ft/total:.1f}%)", file=sys.stderr)
    print(f"Coverage:", file=sys.stderr)
    for field, pct in stats["coverage"].items():
        print(f"  {field}: {pct}%", file=sys.stderr)
    print(f"\nOutput: {output_dir}/", file=sys.stderr)

    return stats


def validate_success(output_dir: Path) -> bool:
    """Validate e007 success criteria: coverage ≥90% non-empty problem+method."""
    stats_path = output_dir / "extraction_stats.json"
    if not stats_path.exists():
        print("ERROR: extraction_stats.json not found", file=sys.stderr)
        return False

    stats = load_json(stats_path)
    coverage = stats["coverage"]

    problem_pct = coverage["problem"]
    method_pct = coverage["method"]

    print(f"\n=== e007 Success Criteria Validation ===\n", file=sys.stderr)
    print(f"problem coverage: {problem_pct}% (threshold: ≥90%)", file=sys.stderr)
    print(f"method coverage:  {method_pct}% (threshold: ≥90%)", file=sys.stderr)

    problem_pass = problem_pct >= 90.0
    method_pass = method_pct >= 90.0

    print(f"\nproblem ≥90%: {'PASS' if problem_pass else 'FAIL'}", file=sys.stderr)
    print(f"method ≥90%:  {'PASS' if method_pass else 'FAIL'}", file=sys.stderr)

    both_pass = problem_pass and method_pass
    if both_pass:
        print(f"\n** GO — success criteria met **", file=sys.stderr)
    elif problem_pct >= 70 and method_pct >= 70:
        print(f"\n** PARTIAL GO — 70-90% range, acceptable with caveats **", file=sys.stderr)
    else:
        print(f"\n** NO-GO — coverage below threshold **", file=sys.stderr)

    # Also show all fields
    print(f"\nAll field coverage:", file=sys.stderr)
    for field, pct in coverage.items():
        marker = "OK" if pct >= 90 else "LOW" if pct >= 70 else "FAIL"
        print(f"  {field}: {pct}% [{marker}]", file=sys.stderr)

    return both_pass


def main():
    parser = argparse.ArgumentParser(
        description="e007: Full 3,070-paper LLM extraction with checkpoint/resume"
    )
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare prompts only (no extraction)")
    parser.add_argument("--finalize-only", action="store_true", help="Finalize from saved checkpoints")
    parser.add_argument("--validate", action="store_true", help="Validate success criteria only")
    parser.add_argument("--max-parallel", type=int, default=MAX_PARALLEL, help=f"Max parallel extractions (default: {MAX_PARALLEL})")

    args = parser.parse_args()

    if args.validate:
        success = validate_success(OUTPUT_DIR)
        return 0 if success else 1

    if args.max_parallel != MAX_PARALLEL:
        # Override module-level constant via function parameter passing
        pass
    max_parallel = args.max_parallel

    # === Phase 1: Load and Prepare ===
    print("=== e007: Full Extraction Pipeline ===\n", file=sys.stderr)

    print("Step 1: Loading papers...", file=sys.stderr)
    papers = load_json(INPUT_PAPERS)
    print(f"  Loaded {len(papers)} papers", file=sys.stderr)
    with_abs = sum(1 for p in papers if p.get("abstract"))
    print(f"  With abstracts: {with_abs}/{len(papers)} ({100*with_abs/len(papers):.1f}%)", file=sys.stderr)

    # Extract existing clusters
    clusters = {}
    for p in papers:
        doi = p.get("doi", "")
        cid = p.get("cluster_id")
        if doi and cid is not None:
            clusters[doi] = cid

    print(f"  Clusters: {len(set(clusters.values()))} unique", file=sys.stderr)

    print("\nStep 2: Loading e006 fulltext cache...", file=sys.stderr)
    ft_list = load_json(PMC_FULLTEXT)
    ft_dict = convert_fulltext_list_to_dict(ft_list)
    print(f"  Converted {len(ft_list)} records → {len(ft_dict)} with usable sections", file=sys.stderr)

    papers, ft_stats = attach_fulltext_from_cache(papers, ft_dict)
    print(f"  Attached: {ft_stats['with_fulltext']}/{ft_stats['total']} papers with fulltext", file=sys.stderr)

    print("\nStep 3: Building extraction prompts...", file=sys.stderr)
    prompts, batch_doi_lists, split_stats = build_prompts(papers)
    print(f"  Fulltext: {split_stats['fulltext_papers']} papers → {split_stats['fulltext_batches']} batches (batch_size={FULLTEXT_BATCH_SIZE})", file=sys.stderr)
    print(f"  Abstract: {split_stats['abstract_papers']} papers → {split_stats['abstract_batches']} batches (batch_size={ABSTRACT_BATCH_SIZE})", file=sys.stderr)
    print(f"  Total: {split_stats['total_prompts']} prompts", file=sys.stderr)

    # Save prompts for reproducibility
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(
        {
            "prompts": prompts,
            "batch_dois": batch_doi_lists,
            "split_stats": split_stats,
            "params": {
                "abstract_batch_size": ABSTRACT_BATCH_SIZE,
                "fulltext_batch_size": FULLTEXT_BATCH_SIZE,
                "max_parallel": MAX_PARALLEL,
                "input": str(INPUT_PAPERS),
                "fulltext_cache": str(PMC_FULLTEXT),
            },
            "timestamp": datetime.now().isoformat(),
        },
        OUTPUT_DIR / "extraction_prompts.json",
    )
    print(f"  Saved prompts to {OUTPUT_DIR / 'extraction_prompts.json'}", file=sys.stderr)

    if args.prepare_only:
        print("\n--prepare-only: stopping before extraction.", file=sys.stderr)
        return 0

    # === Phase 2: LLM Extraction ===
    if args.finalize_only:
        print("\n--finalize-only: loading from checkpoints...", file=sys.stderr)
        all_results = run_extraction_with_checkpoint(
            prompts, batch_doi_lists, resume=True, max_parallel=max_parallel
        )
    else:
        print(f"\n=== Phase 2: LLM Extraction ({len(prompts)} batches) ===\n", file=sys.stderr)
        all_results = run_extraction_with_checkpoint(
            prompts, batch_doi_lists, resume=args.resume, max_parallel=max_parallel
        )

    # === Phase 3: Finalize ===
    print(f"\n=== Phase 3: Merge & Export ===\n", file=sys.stderr)
    stats = merge_and_export(papers, all_results, clusters, OUTPUT_DIR)

    # === Phase 4: Validate ===
    print("", file=sys.stderr)
    validate_success(OUTPUT_DIR)

    return 0


if __name__ == "__main__":
    sys.exit(main())
