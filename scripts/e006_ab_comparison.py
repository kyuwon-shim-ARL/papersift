#!/usr/bin/env python3
"""
Experiment e006: A/B comparison of abstract-only vs fulltext LLM extraction quality.

This script prepares prompts for comparing extraction quality between:
- Condition A: Abstract-only (current baseline)
- Condition B: Fulltext (Methods + Results + Discussion from PMC XML)

Usage:
    # Prepare prompt sets
    python scripts/e006_ab_comparison.py \
        --papers results/virtual-cell-sweep/papers_with_abstracts.json \
        --fulltext outputs/e006/pmc_fulltext.json \
        --output-dir outputs/e006 \
        --sample-size 50

    # Evaluate completed extractions
    python scripts/e006_ab_comparison.py \
        --evaluate \
        --output-dir outputs/e006
"""

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple


# Extraction prompt template (from extract.py)
EXTRACTION_PROMPT_TEMPLATE = """Extract the following structured information from each paper in JSON format.

For each paper, extract:
- problem: The research problem or question (1-2 sentences)
- method: The computational/experimental method used (1-2 sentences)
- finding: The key finding or conclusion (1-2 sentences)
- dataset: The dataset used, if any (name and brief description)
- metric: The evaluation metric(s) used, if any
- baseline: The baseline methods compared against, if any
- result: The quantitative result, if any (numbers, percentages, improvements)

Return a JSON array with one object per paper. Each object should have a "doi" field and the extracted fields above. Use empty string "" for fields that are not found or not applicable.

Papers:
{papers_text}

Return ONLY the JSON array, no additional text."""


def load_json(filepath: Path) -> Any:
    """Load JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Any, filepath: Path) -> None:
    """Save JSON file with pretty printing."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_papers_with_both(papers: List[Dict], fulltext_data: List[Dict]) -> List[Dict]:
    """
    Find papers that have both abstract and PMC fulltext.

    Args:
        papers: List of paper dicts with doi, abstract, etc.
        fulltext_data: List of {doi, pmcid, methods_text, results_text, ...}

    Returns:
        List of paper dicts enriched with fulltext fields
    """
    fulltext_by_doi = {ft['doi']: ft for ft in fulltext_data}

    papers_with_both = []
    for paper in papers:
        doi = paper.get('doi')
        if not doi or not paper.get('abstract'):
            continue

        if doi in fulltext_by_doi:
            # Enrich paper with fulltext
            enriched = paper.copy()
            enriched['fulltext'] = fulltext_by_doi[doi]
            papers_with_both.append(enriched)

    return papers_with_both


def select_sample(papers: List[Dict], sample_size: int, seed: int = 42) -> Tuple[List[Dict], List[str]]:
    """
    Randomly select sample papers.

    Args:
        papers: List of candidate papers
        sample_size: Number of papers to sample
        seed: Random seed for reproducibility

    Returns:
        (sampled_papers, sample_dois)
    """
    random.seed(seed)

    if len(papers) <= sample_size:
        sampled = papers
    else:
        sampled = random.sample(papers, sample_size)

    sample_dois = [p['doi'] for p in sampled]
    return sampled, sample_dois


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max characters."""
    if not text:
        return ""
    return text[:max_chars] if len(text) > max_chars else text


def build_abstract_batch_prompts(papers: List[Dict], batch_size: int = 45) -> Tuple[List[str], List[List[str]]]:
    """
    Build abstract-only prompts (condition A).

    Args:
        papers: List of paper dicts with doi, title, abstract, year
        batch_size: Papers per prompt batch

    Returns:
        (prompts, batch_dois) where batch_dois[i] corresponds to prompts[i]
    """
    prompts = []
    batch_dois = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]

        # Build papers text block
        papers_text_parts = []
        for paper in batch:
            paper_text = f"""---
DOI: {paper['doi']}
Title: {paper.get('title', 'N/A')}
Year: {paper.get('year', 'N/A')}
Abstract: {paper.get('abstract', 'N/A')}
---"""
            papers_text_parts.append(paper_text)

        papers_text = "\n\n".join(papers_text_parts)
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(papers_text=papers_text)

        prompts.append(prompt)
        batch_dois.append([p['doi'] for p in batch])

    return prompts, batch_dois


def build_fulltext_batch_prompts(papers: List[Dict], batch_size: int = 45) -> Tuple[List[str], List[List[str]]]:
    """
    Build fulltext prompts (condition B) with Methods/Results/Discussion sections.

    Args:
        papers: List of paper dicts with doi, title, abstract, year, and fulltext field
        batch_size: Papers per prompt batch

    Returns:
        (prompts, batch_dois) where batch_dois[i] corresponds to prompts[i]
    """
    prompts = []
    batch_dois = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]

        # Build papers text block with fulltext sections
        papers_text_parts = []
        for paper in batch:
            ft = paper['fulltext']

            # Truncate sections to manage token usage
            methods = truncate_text(ft.get('methods_text', ''), 5000)
            results = truncate_text(ft.get('results_text', ''), 5000)
            discussion = truncate_text(ft.get('discussion_text', ''), 2000)

            paper_text = f"""---
DOI: {paper['doi']}
Title: {paper.get('title', 'N/A')}
Year: {paper.get('year', 'N/A')}
Abstract: {paper.get('abstract', 'N/A')}
Methods: {methods if methods else 'N/A'}
Results: {results if results else 'N/A'}
Discussion: {discussion if discussion else 'N/A'}
---"""
            papers_text_parts.append(paper_text)

        papers_text = "\n\n".join(papers_text_parts)
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(papers_text=papers_text)

        prompts.append(prompt)
        batch_dois.append([p['doi'] for p in batch])

    return prompts, batch_dois


def compute_completeness_rate(extractions: List[Dict], field: str) -> float:
    """
    Compute completeness rate for a field (non-empty values).

    Args:
        extractions: List of extraction dicts
        field: Field name to check

    Returns:
        Completeness rate as percentage (0-100)
    """
    if not extractions:
        return 0.0

    non_empty = sum(1 for ex in extractions if ex.get(field, "").strip())
    return (non_empty / len(extractions)) * 100


def compute_avg_length(extractions: List[Dict], field: str) -> float:
    """
    Compute average character length for a field (excluding empty values).

    Args:
        extractions: List of extraction dicts
        field: Field name to check

    Returns:
        Average character length
    """
    lengths = [len(ex.get(field, "")) for ex in extractions if ex.get(field, "").strip()]
    return sum(lengths) / len(lengths) if lengths else 0.0


def detect_quantitative_signals(extractions: List[Dict], field: str) -> float:
    """
    Detect quantitative signals (numbers) in a field.

    Args:
        extractions: List of extraction dicts
        field: Field name to check

    Returns:
        Detection rate as percentage (0-100)
    """
    if not extractions:
        return 0.0

    # Regex for numbers (integers, decimals, percentages)
    number_pattern = re.compile(r'\d+\.?\d*%?')

    with_numbers = sum(1 for ex in extractions
                       if number_pattern.search(ex.get(field, "")))

    return (with_numbers / len(extractions)) * 100


def detect_sota_signals(extractions: List[Dict], field: str) -> float:
    """
    Detect SOTA/comparison signals in a field.

    Args:
        extractions: List of extraction dicts
        field: Field name to check

    Returns:
        Detection rate as percentage (0-100)
    """
    if not extractions:
        return 0.0

    # SOTA/comparison keywords
    sota_keywords = [
        'outperform', 'state-of-the-art', 'sota', 'better than',
        'improve', 'improvement', 'compared to', 'superior',
        'exceeds', 'surpass', 'best', 'competitive'
    ]

    pattern = re.compile('|'.join(re.escape(kw) for kw in sota_keywords), re.IGNORECASE)

    with_sota = sum(1 for ex in extractions
                    if pattern.search(ex.get(field, "")))

    return (with_sota / len(extractions)) * 100


def evaluate_extractions(abstract_path: Path, fulltext_path: Path, output_dir: Path) -> None:
    """
    Evaluate and compare abstract vs fulltext extractions.

    Args:
        abstract_path: Path to abstract-only extractions JSON
        fulltext_path: Path to fulltext extractions JSON
        output_dir: Output directory for results
    """
    print("\n=== e006 A/B Evaluation: Abstract vs Fulltext ===\n")

    # Load extractions
    abstract_extractions = load_json(abstract_path)
    fulltext_extractions = load_json(fulltext_path)

    if len(abstract_extractions) != len(fulltext_extractions):
        print(f"WARNING: Extraction count mismatch (abstract: {len(abstract_extractions)}, fulltext: {len(fulltext_extractions)})")

    # Extraction fields
    fields = ['problem', 'method', 'finding', 'dataset', 'metric', 'baseline', 'result']

    # Compute metrics
    metrics = {
        'sample_size': len(abstract_extractions),
        'completeness': {},
        'avg_length': {},
        'quantitative_signals': {},
        'sota_signals': {},
        'verdict': {}
    }

    print("## Completeness Rate (non-empty %)")
    print(f"{'Field':<12} {'Abstract':<12} {'Fulltext':<12} {'Δ':<12}")
    print("-" * 50)
    for field in fields:
        abstract_rate = compute_completeness_rate(abstract_extractions, field)
        fulltext_rate = compute_completeness_rate(fulltext_extractions, field)
        delta = fulltext_rate - abstract_rate

        metrics['completeness'][field] = {
            'abstract': round(abstract_rate, 1),
            'fulltext': round(fulltext_rate, 1),
            'delta': round(delta, 1)
        }

        print(f"{field:<12} {abstract_rate:>10.1f}% {fulltext_rate:>10.1f}% {delta:>+10.1f}%")

    print("\n## Average Character Length (non-empty only)")
    print(f"{'Field':<12} {'Abstract':<12} {'Fulltext':<12} {'Δ':<12}")
    print("-" * 50)
    for field in fields:
        abstract_len = compute_avg_length(abstract_extractions, field)
        fulltext_len = compute_avg_length(fulltext_extractions, field)
        delta = fulltext_len - abstract_len

        metrics['avg_length'][field] = {
            'abstract': round(abstract_len, 1),
            'fulltext': round(fulltext_len, 1),
            'delta': round(delta, 1)
        }

        print(f"{field:<12} {abstract_len:>10.1f} {fulltext_len:>10.1f} {delta:>+10.1f}")

    print("\n## Quantitative Signal Detection (contains numbers %)")
    print(f"{'Field':<12} {'Abstract':<12} {'Fulltext':<12} {'Δ':<12}")
    print("-" * 50)
    for field in fields:
        abstract_quant = detect_quantitative_signals(abstract_extractions, field)
        fulltext_quant = detect_quantitative_signals(fulltext_extractions, field)
        delta = fulltext_quant - abstract_quant

        metrics['quantitative_signals'][field] = {
            'abstract': round(abstract_quant, 1),
            'fulltext': round(fulltext_quant, 1),
            'delta': round(delta, 1)
        }

        print(f"{field:<12} {abstract_quant:>10.1f}% {fulltext_quant:>10.1f}% {delta:>+10.1f}%")

    print("\n## SOTA/Comparison Signal Detection (keywords %)")
    print(f"{'Field':<12} {'Abstract':<12} {'Fulltext':<12} {'Δ':<12}")
    print("-" * 50)
    for field in fields:
        abstract_sota = detect_sota_signals(abstract_extractions, field)
        fulltext_sota = detect_sota_signals(fulltext_extractions, field)
        delta = fulltext_sota - abstract_sota

        metrics['sota_signals'][field] = {
            'abstract': round(abstract_sota, 1),
            'fulltext': round(fulltext_sota, 1),
            'delta': round(delta, 1)
        }

        print(f"{field:<12} {abstract_sota:>10.1f}% {fulltext_sota:>10.1f}% {delta:>+10.1f}%")

    # Compute verdict
    print("\n## Verdict")

    # Aggregate improvements
    total_completeness_delta = sum(m['delta'] for m in metrics['completeness'].values())
    total_quant_delta = sum(m['delta'] for m in metrics['quantitative_signals'].values())
    total_sota_delta = sum(m['delta'] for m in metrics['sota_signals'].values())

    avg_completeness_delta = total_completeness_delta / len(fields)
    avg_quant_delta = total_quant_delta / len(fields)
    avg_sota_delta = total_sota_delta / len(fields)

    print(f"Average completeness improvement: {avg_completeness_delta:+.1f}%")
    print(f"Average quantitative signal improvement: {avg_quant_delta:+.1f}%")
    print(f"Average SOTA signal improvement: {avg_sota_delta:+.1f}%")

    # Go/No-Go criteria
    # GO if: avg completeness delta >= +5% AND (quant delta >= +3% OR sota delta >= +3%)
    completeness_pass = avg_completeness_delta >= 5.0
    signal_pass = avg_quant_delta >= 3.0 or avg_sota_delta >= 3.0

    go_no_go = "GO" if (completeness_pass and signal_pass) else "NO-GO"

    print(f"\nCompleteness improvement >= +5%: {'PASS' if completeness_pass else 'FAIL'}")
    print(f"Signal improvement >= +3%: {'PASS' if signal_pass else 'FAIL'}")
    print(f"\n**Overall: {go_no_go}**")

    metrics['verdict'] = {
        'avg_completeness_delta': round(avg_completeness_delta, 1),
        'avg_quant_delta': round(avg_quant_delta, 1),
        'avg_sota_delta': round(avg_sota_delta, 1),
        'completeness_pass': completeness_pass,
        'signal_pass': signal_pass,
        'go_no_go': go_no_go
    }

    # Save metrics
    metrics_path = output_dir / 'ab_comparison_metrics.json'
    save_json(metrics, metrics_path)
    print(f"\nMetrics saved to: {metrics_path}")


def main():
    parser = argparse.ArgumentParser(
        description='e006: A/B comparison of abstract-only vs fulltext extraction quality'
    )

    # Preparation mode args
    parser.add_argument(
        '--papers',
        type=Path,
        help='Path to papers_with_abstracts.json'
    )
    parser.add_argument(
        '--fulltext',
        type=Path,
        help='Path to pmc_fulltext.json'
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=50,
        help='Number of papers to sample (default: 50)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for sampling (default: 42)'
    )

    # Evaluation mode arg
    parser.add_argument(
        '--evaluate',
        action='store_true',
        help='Evaluation mode: compare completed extractions'
    )

    # Common args
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help='Output directory for results'
    )

    args = parser.parse_args()

    if args.evaluate:
        # Evaluation mode
        abstract_path = args.output_dir / 'ab_abstract_extractions.json'
        fulltext_path = args.output_dir / 'ab_fulltext_extractions.json'

        if not abstract_path.exists() or not fulltext_path.exists():
            print(f"ERROR: Missing extraction files in {args.output_dir}")
            print(f"Expected: ab_abstract_extractions.json, ab_fulltext_extractions.json")
            return 1

        evaluate_extractions(abstract_path, fulltext_path, args.output_dir)

    else:
        # Preparation mode
        if not args.papers or not args.fulltext:
            print("ERROR: --papers and --fulltext required for preparation mode")
            return 1

        if not args.papers.exists() or not args.fulltext.exists():
            print(f"ERROR: Input files not found")
            return 1

        print(f"\n=== e006 A/B Preparation: Sample Selection ===\n")

        # Load data
        print(f"Loading papers from: {args.papers}")
        papers = load_json(args.papers)
        print(f"Loaded {len(papers)} papers with abstracts")

        print(f"Loading fulltext from: {args.fulltext}")
        fulltext_data = load_json(args.fulltext)
        print(f"Loaded {len(fulltext_data)} fulltext records")

        # Find papers with both
        papers_with_both = find_papers_with_both(papers, fulltext_data)
        print(f"Found {len(papers_with_both)} papers with both abstract and fulltext")

        if len(papers_with_both) < args.sample_size:
            print(f"WARNING: Only {len(papers_with_both)} papers available, adjusting sample size")
            args.sample_size = len(papers_with_both)

        # Select sample
        sampled_papers, sample_dois = select_sample(papers_with_both, args.sample_size, args.seed)
        print(f"Selected {len(sampled_papers)} papers (seed={args.seed})")

        # Build abstract-only prompts
        print("\nBuilding abstract-only prompts (condition A)...")
        abstract_prompts, abstract_batch_dois = build_abstract_batch_prompts(sampled_papers)
        print(f"Generated {len(abstract_prompts)} abstract-only prompt batches")

        abstract_prompts_data = {
            'prompts': abstract_prompts,
            'batch_dois': abstract_batch_dois,
            'sample_dois': sample_dois,
            'condition': 'abstract_only'
        }
        abstract_prompts_path = args.output_dir / 'ab_prompts_abstract.json'
        save_json(abstract_prompts_data, abstract_prompts_path)
        print(f"Saved to: {abstract_prompts_path}")

        # Build fulltext prompts
        print("\nBuilding fulltext prompts (condition B)...")
        fulltext_prompts, fulltext_batch_dois = build_fulltext_batch_prompts(sampled_papers)
        print(f"Generated {len(fulltext_prompts)} fulltext prompt batches")

        fulltext_prompts_data = {
            'prompts': fulltext_prompts,
            'batch_dois': fulltext_batch_dois,
            'sample_dois': sample_dois,
            'condition': 'fulltext'
        }
        fulltext_prompts_path = args.output_dir / 'ab_prompts_fulltext.json'
        save_json(fulltext_prompts_data, fulltext_prompts_path)
        print(f"Saved to: {fulltext_prompts_path}")

        # Create comparison template
        print("\nCreating comparison template...")
        template = {
            'sample_size': len(sampled_papers),
            'sample_dois': sample_dois,
            'abstract_extractions': [],  # To be filled after LLM runs
            'fulltext_extractions': [],  # To be filled after LLM runs
            'metrics': {}  # To be computed
        }
        template_path = args.output_dir / 'ab_comparison_template.json'
        save_json(template, template_path)
        print(f"Saved to: {template_path}")

        print("\n=== Preparation complete ===")
        print(f"\nNext steps:")
        print(f"1. Run LLM extraction on abstract-only prompts")
        print(f"2. Run LLM extraction on fulltext prompts")
        print(f"3. Save results as ab_abstract_extractions.json and ab_fulltext_extractions.json")
        print(f"4. Run: python scripts/e006_ab_comparison.py --evaluate --output-dir {args.output_dir}")

    return 0


if __name__ == '__main__':
    exit(main())
