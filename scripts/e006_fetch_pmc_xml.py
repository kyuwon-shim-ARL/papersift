#!/usr/bin/env python3
"""
Fetch PMC JATS XML fulltext for papers with PMCIDs.

Reads fulltext_coverage.json, fetches XML from Europe PMC OA API,
extracts Methods/Results/Discussion sections, saves as JSON.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from xml.etree import ElementTree as ET

import requests


def extract_text_recursive(element: ET.Element) -> str:
    """
    Recursively extract all text content from an XML element.
    Strips all tags and returns plain text.
    """
    text_parts = []

    # Get element's own text
    if element.text:
        text_parts.append(element.text.strip())

    # Recursively get text from children
    for child in element:
        text_parts.append(extract_text_recursive(child))
        # Get tail text after child element
        if child.tail:
            text_parts.append(child.tail.strip())

    return " ".join(filter(None, text_parts))


def extract_section_text(root: ET.Element, section_titles: List[str], sec_types: List[str]) -> str:
    """
    Extract text from <sec> elements matching given titles or sec-type attributes.

    Args:
        root: XML root element
        section_titles: List of title keywords to match (case-insensitive)
        sec_types: List of sec-type attribute values to match

    Returns:
        Concatenated plain text from all matching sections
    """
    sections = []

    # Find all <sec> elements
    for sec in root.iter("sec"):
        # Check sec-type attribute
        sec_type = sec.get("sec-type", "").lower()
        if any(st in sec_type for st in sec_types):
            sections.append(extract_text_recursive(sec))
            continue

        # Check title element
        title_elem = sec.find("title")
        if title_elem is not None:
            title_text = (title_elem.text or "").lower()
            if any(keyword in title_text for keyword in section_titles):
                sections.append(extract_text_recursive(sec))

    return "\n\n".join(sections)


def extract_body_text(root: ET.Element) -> str:
    """Extract all text from the <body> element."""
    body = root.find(".//body")
    if body is not None:
        return extract_text_recursive(body)
    return ""


def parse_jats_xml(xml_content: str) -> Dict[str, str]:
    """
    Parse JATS XML and extract Methods, Results, Discussion, and full body text.

    Returns:
        Dict with keys: methods_text, results_text, discussion_text, full_body_text
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"Warning: XML parse error: {e}", file=sys.stderr)
        return {
            "methods_text": "",
            "results_text": "",
            "discussion_text": "",
            "full_body_text": ""
        }

    # Extract sections
    methods_text = extract_section_text(
        root,
        section_titles=["method", "material", "experiment", "procedure"],
        sec_types=["methods", "materials", "materials|methods", "materials-methods"]
    )

    results_text = extract_section_text(
        root,
        section_titles=["result", "finding"],
        sec_types=["results", "results|discussion"]
    )

    discussion_text = extract_section_text(
        root,
        section_titles=["discussion", "conclusion"],
        sec_types=["discussion", "conclusions"]
    )

    full_body_text = extract_body_text(root)

    return {
        "methods_text": methods_text,
        "results_text": results_text,
        "discussion_text": discussion_text,
        "full_body_text": full_body_text
    }


def fetch_pmc_xml(pmcid: str, max_retries: int = 3) -> Optional[str]:
    """
    Fetch JATS XML from Europe PMC OA API.

    Args:
        pmcid: PMC ID (e.g., "PMC12148494")
        max_retries: Number of retries for 5xx errors

    Returns:
        XML content as string, or None if fetch failed
    """
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                print(f"Warning: {pmcid} not found (404)", file=sys.stderr)
                return None
            elif response.status_code >= 500:
                # Retry on 5xx errors
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"Warning: {pmcid} returned {response.status_code}, "
                      f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                      file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"Warning: {pmcid} returned {response.status_code}", file=sys.stderr)
                return None

        except requests.RequestException as e:
            print(f"Warning: {pmcid} request failed: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None

    return None


def load_checkpoint(checkpoint_path: Path) -> Set[str]:
    """Load already-fetched PMCIDs from checkpoint file."""
    if not checkpoint_path.exists():
        return set()

    try:
        with open(checkpoint_path) as f:
            data = json.load(f)
            return set(item["pmcid"] for item in data)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to load checkpoint: {e}", file=sys.stderr)
        return set()


def save_checkpoint(checkpoint_path: Path, results: List[Dict]) -> None:
    """Save current progress to checkpoint file."""
    with open(checkpoint_path, "w") as f:
        json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PMC JATS XML fulltext and extract Methods/Results/Discussion sections"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/home/kyuwon/projects/papersift/outputs/e006/fulltext_coverage.json"),
        help="Input fulltext_coverage.json file"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/home/kyuwon/projects/papersift/outputs/e006"),
        help="Output directory for results and checkpoint"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of papers to process (for testing)"
    )
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output_dir / "pmc_fulltext.json"
    checkpoint_path = args.output_dir / "pmc_checkpoint.json"

    # Load input
    print(f"Loading {args.input}...")
    with open(args.input) as f:
        coverage_data = json.load(f)

    # Filter papers with PMCIDs
    papers_with_pmcid = [
        p for p in coverage_data.get("per_paper", [])
        if p.get("epmc_pmcid")
    ]

    if args.limit:
        papers_with_pmcid = papers_with_pmcid[:args.limit]

    print(f"Found {len(papers_with_pmcid)} papers with PMCIDs")

    # Load checkpoint (already-fetched PMCIDs)
    fetched_pmcids = load_checkpoint(checkpoint_path)
    print(f"Checkpoint: {len(fetched_pmcids)} papers already fetched")

    # Load existing results if checkpoint exists
    results = []
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            results = json.load(f)

    # Process papers
    skipped = 0
    fetched = 0
    failed = 0

    for i, paper in enumerate(papers_with_pmcid, start=1):
        doi = paper.get("doi", "")
        pmcid = paper["epmc_pmcid"]

        # Skip if already fetched
        if pmcid in fetched_pmcids:
            skipped += 1
            continue

        # Rate limiting: 10 requests/second = 100ms delay
        time.sleep(0.1)

        # Fetch XML
        xml_content = fetch_pmc_xml(pmcid)

        if xml_content is None:
            failed += 1
            continue

        # Parse and extract sections
        sections = parse_jats_xml(xml_content)

        # Create result entry
        result = {
            "doi": doi,
            "pmcid": pmcid,
            **sections
        }

        results.append(result)
        fetched_pmcids.add(pmcid)
        fetched += 1

        # Save checkpoint every 50 papers
        if i % 50 == 0:
            save_checkpoint(checkpoint_path, results)
            print(f"Progress: {i}/{len(papers_with_pmcid)} papers processed "
                  f"({fetched} fetched, {skipped} skipped, {failed} failed)")

    # Final save
    save_checkpoint(checkpoint_path, results)

    # Save final output
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nComplete!")
    print(f"  Total papers with PMCIDs: {len(papers_with_pmcid)}")
    print(f"  Successfully fetched: {fetched}")
    print(f"  Skipped (already fetched): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
