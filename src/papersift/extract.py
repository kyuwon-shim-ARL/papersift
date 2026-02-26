"""LLM extraction prompt builder and response parser.

This module bridges Python and LLM subagents. It builds prompts and parses responses,
but NEVER calls LLMs itself. NO rule-based extraction.
"""

import json
import re
import sys
from pathlib import Path


EXTRACTION_PROMPT_TEMPLATE = """You are a scientific paper analyst. For each paper below, extract:
- problem: The research problem or question addressed (1-2 sentences)
- method: The computational/experimental methods used (1-2 sentences)
- finding: The key results or conclusions (1-2 sentences)
- dataset: The dataset(s) or biological system(s) studied (short phrase, e.g., "E. coli K-12", "MNIST", "patient cohort N=500")
- metric: The evaluation metric(s) used (short phrase, e.g., "AUC-ROC", "RMSE", "fold change", "p-value")
- baseline: The comparison baseline or prior method (short phrase, e.g., "random forest", "previous SOTA", "null model")
- result: The quantitative result or performance claim (short phrase, e.g., "AUC=0.95", "2.3x speedup", "p<0.001")

If information is not available for a field, use empty string.

If the abstract is empty or missing, extract what you can from the title alone.

Return a JSON array with one object per paper:
[
  {{
    "doi": "10.xxxx/...",
    "problem": "...",
    "method": "...",
    "finding": "...",
    "dataset": "...",
    "metric": "...",
    "baseline": "...",
    "result": "..."
  }},
  ...
]

Papers to analyze:
{papers_block}"""


def build_batch_prompts(papers: list[dict], batch_size: int = 45) -> tuple[list[str], list[list[str]]]:
    """
    Groups papers into batches and builds extraction prompts.

    Each paper in the papers_block looks like:
    ---
    DOI: 10.xxxx/...
    Title: Paper Title Here
    Year: 2024
    Abstract: Full abstract text or "(no abstract available)"
    ---

    Args:
        papers: list of paper dicts with doi, title, year, abstract fields
        batch_size: papers per batch (default 45, optimized for Haiku context window)

    Returns:
        (prompts, batch_doi_lists) where:
        - prompts[i] is the full prompt string for batch i
        - batch_doi_lists[i] is the list of DOIs in batch i
    """
    prompts = []
    batch_doi_lists = []

    # Filter out papers without DOI
    valid_papers = [p for p in papers if p.get("doi")]

    # Split into batches
    for i in range(0, len(valid_papers), batch_size):
        batch = valid_papers[i:i + batch_size]

        # Build papers_block
        paper_entries = []
        batch_dois = []

        for paper in batch:
            doi = paper["doi"]
            title = paper.get("title", "(no title)")
            year = paper.get("year", "unknown")
            abstract = paper.get("abstract", "").strip()

            if not abstract:
                abstract = "(no abstract available)"

            entry = f"""---
DOI: {doi}
Title: {title}
Year: {year}
Abstract: {abstract}
---"""
            paper_entries.append(entry)
            batch_dois.append(doi)

        papers_block = "\n\n".join(paper_entries)
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(papers_block=papers_block)

        prompts.append(prompt)
        batch_doi_lists.append(batch_dois)

    return prompts, batch_doi_lists


def parse_llm_response(response: str) -> list[dict]:
    """
    Parse a single LLM subagent response (expected JSON array).

    Handles common LLM output quirks:
    - JSON wrapped in markdown code blocks (```json ... ```)
    - Extra text before/after the JSON array
    - Missing trailing bracket

    Returns list of {doi, problem, method, finding} dicts.
    On parse failure, returns empty list and prints warning to stderr.
    """
    # Strip markdown code blocks
    response = response.strip()

    # Remove ```json and ``` markers
    response = re.sub(r'^```json\s*', '', response, flags=re.MULTILINE)
    response = re.sub(r'^```\s*$', '', response, flags=re.MULTILINE)
    response = response.strip()

    # Try to find JSON array in response
    # Look for outermost [...] structure
    match = re.search(r'\[.*\]', response, re.DOTALL)
    if match:
        json_str = match.group(0)
    else:
        # No array found, try the whole response
        json_str = response

    try:
        data = json.loads(json_str)

        # Ensure it's a list
        if not isinstance(data, list):
            print(f"Warning: Expected JSON array, got {type(data).__name__}", file=sys.stderr)
            return []

        # Validate each entry has required fields
        valid_extractions = []
        for item in data:
            if isinstance(item, dict) and "doi" in item:
                # Ensure required fields exist (use empty string as default)
                extraction = {
                    "doi": item["doi"],
                    "problem": item.get("problem", ""),
                    "method": item.get("method", ""),
                    "finding": item.get("finding", ""),
                    "dataset": item.get("dataset", ""),
                    "metric": item.get("metric", ""),
                    "baseline": item.get("baseline", ""),
                    "result": item.get("result", ""),
                }
                valid_extractions.append(extraction)

        return valid_extractions

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse LLM response as JSON: {e}", file=sys.stderr)
        print(f"Response snippet: {json_str[:200]}...", file=sys.stderr)
        return []


def filter_extraction_quality(extractions: list[dict], max_field_length: int = 200) -> list[dict]:
    """
    Filter and clean extraction fields for quality.

    - Truncates fields longer than max_field_length characters
    - Flags fields that appear to be raw abstract text (contain 3+ sentences)
    """
    for ext in extractions:
        for field in ["problem", "method", "finding", "dataset", "metric", "baseline", "result"]:
            value = ext.get(field, "")
            if len(value) > max_field_length:
                # Truncate and mark
                ext[field] = value[:max_field_length].rsplit(" ", 1)[0] + "..."
                ext.setdefault("_quality_flags", []).append(f"{field}_truncated")
    return extractions


def merge_extractions(papers: list[dict], extractions: list[dict]) -> list[dict]:
    """
    Merge extraction results back into paper dicts.

    Builds {doi_lower: {problem, method, finding, dataset, metric, baseline, result}} lookup from extractions.
    For each paper: if extraction exists, attach fields; otherwise set empty strings.
    Returns the mutated papers list (same objects, new fields added).
    DOI matching is case-insensitive.
    """
    # Build lookup dict with lowercase DOIs
    extraction_lookup = {}
    for ext in extractions:
        doi = ext.get("doi", "").lower()
        if doi:
            extraction_lookup[doi] = {
                "problem": ext.get("problem", ""),
                "method": ext.get("method", ""),
                "finding": ext.get("finding", ""),
                "dataset": ext.get("dataset", ""),
                "metric": ext.get("metric", ""),
                "baseline": ext.get("baseline", ""),
                "result": ext.get("result", ""),
            }

    # Merge into papers
    for paper in papers:
        doi = paper.get("doi", "").lower()

        if doi in extraction_lookup:
            ext = extraction_lookup[doi]
            paper["problem"] = ext["problem"]
            paper["method"] = ext["method"]
            paper["finding"] = ext["finding"]
            paper["dataset"] = ext["dataset"]
            paper["metric"] = ext["metric"]
            paper["baseline"] = ext["baseline"]
            paper["result"] = ext["result"]
        else:
            # Set empty strings for missing extractions
            paper["problem"] = ""
            paper["method"] = ""
            paper["finding"] = ""
            paper["dataset"] = ""
            paper["metric"] = ""
            paper["baseline"] = ""
            paper["result"] = ""

    return papers


def load_extractions(path: Path) -> list[dict]:
    """
    Load pre-computed extractions from JSON file.

    Supports two formats:
    - List format: [{doi, problem, method, finding}, ...]
    - Dict format: {doi: {problem, method, finding}, ...} (converts to list)

    Returns flat list of extraction dicts.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Convert dict format to list format
        extractions = []
        for doi, fields in data.items():
            extraction = {"doi": doi}
            extraction.update(fields)
            extractions.append(extraction)
        return extractions
    else:
        print(f"Warning: Unexpected format in {path}, expected list or dict", file=sys.stderr)
        return []


def save_prompts(prompts: list[str], batch_doi_lists: list[list[str]], path: Path) -> None:
    """
    Save prompts to JSON file for external consumption.

    Format: {
        "prompts": [...],
        "batch_dois": [[...], ...],
        "batch_size": N,
        "total_papers": N
    }
    """
    batch_size = len(batch_doi_lists[0]) if batch_doi_lists else 0
    total_papers = sum(len(dois) for dois in batch_doi_lists)

    data = {
        "prompts": prompts,
        "batch_dois": batch_doi_lists,
        "batch_size": batch_size,
        "total_papers": total_papers
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
