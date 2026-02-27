#!/usr/bin/env python3
"""
Experiment e006: Measure actual fulltext availability across free sources.

Checks Unpaywall, Europe PMC, and OpenAlex for fulltext coverage of our
3,070 virtual cell papers. Supports checkpointing and resume.

Usage:
    python scripts/e006_fulltext_coverage.py \\
        --input results/virtual-cell-sweep/papers_enriched.json \\
        --output-dir outputs/e006 \\
        --email your.email@example.com
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote


def load_papers(input_path: str) -> List[Dict[str, Any]]:
    """Load papers from enriched JSON."""
    print(f"Loading papers from {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        papers = json.load(f)
    print(f"Loaded {len(papers)} papers")
    return papers


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """Load checkpoint if exists."""
    if os.path.exists(checkpoint_path):
        print(f"Loading checkpoint from {checkpoint_path}...")
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_checkpoint(checkpoint_path: str, data: Dict[str, Any]) -> None:
    """Save checkpoint."""
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def check_unpaywall(doi: str, email: str) -> Optional[Dict[str, Any]]:
    """
    Check Unpaywall API for OA status and PDF availability.

    Returns:
        Dict with is_oa, pdf_url, landing_url, oa_status or None if error
    """
    url = f"https://api.unpaywall.org/v2/{quote(doi)}?email={email}"

    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'PaperSift/1.0 (mailto:{})'.format(email))

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            result = {
                'is_oa': data.get('is_oa', False),
                'pdf_url': None,
                'landing_url': None,
                'oa_status': data.get('oa_status', 'closed')
            }

            # Extract best OA location
            best_oa = data.get('best_oa_location')
            if best_oa:
                result['pdf_url'] = best_oa.get('url_for_pdf')
                result['landing_url'] = best_oa.get('url_for_landing_page')

            return result

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # DOI not found in Unpaywall
            return {'is_oa': False, 'pdf_url': None, 'landing_url': None, 'oa_status': 'closed'}
        elif e.code == 429:
            # Rate limited - wait and retry once
            print(f"  Rate limited on {doi}, waiting 5s...")
            time.sleep(5)
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    result = {
                        'is_oa': data.get('is_oa', False),
                        'pdf_url': data.get('best_oa_location', {}).get('url_for_pdf'),
                        'landing_url': data.get('best_oa_location', {}).get('url_for_landing_page'),
                        'oa_status': data.get('oa_status', 'closed')
                    }
                    return result
            except Exception:
                return None
        else:
            print(f"  HTTP error {e.code} for {doi}")
            return None
    except Exception as e:
        print(f"  Error checking Unpaywall for {doi}: {e}")
        return None


def check_europe_pmc(doi: str) -> Optional[Dict[str, Any]]:
    """
    Check Europe PMC for PMCID and fulltext XML availability.

    Returns:
        Dict with found, pmcid, has_fulltext_xml or None if error
    """
    # URL encode the DOI
    query = f"DOI:{quote(doi)}"
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&resultType=core"

    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'PaperSift/1.0')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            result_list = data.get('resultList', {}).get('result', [])

            if not result_list:
                return {'found': False, 'pmcid': None, 'has_fulltext_xml': False}

            # Take first result
            result = result_list[0]
            pmcid = result.get('pmcid')

            return {
                'found': True,
                'pmcid': pmcid,
                'has_fulltext_xml': pmcid is not None
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {'found': False, 'pmcid': None, 'has_fulltext_xml': False}
        else:
            print(f"  HTTP error {e.code} for {doi}")
            return None
    except Exception as e:
        print(f"  Error checking Europe PMC for {doi}: {e}")
        return None


def batch_check_openalex(dois: List[str]) -> Dict[str, bool]:
    """
    Batch check OpenAlex for has_fulltext field.

    Returns:
        Dict mapping DOI -> has_fulltext bool
    """
    if not dois:
        return {}

    try:
        # Use pyalex for batch query
        from pyalex import Works

        # Build filter for multiple DOIs
        doi_filter = "|".join(dois)

        # IMPORTANT: Use .get() not .paginate() to avoid pagination bug
        works = Works().filter(doi=doi_filter).get(per_page=200)

        result = {}
        for work in works:
            doi = work.get('doi', '').replace('https://doi.org/', '')
            result[doi] = work.get('has_fulltext', False)

        # Fill in missing DOIs as False
        for doi in dois:
            if doi not in result:
                result[doi] = False

        return result

    except ImportError:
        print("Warning: pyalex not installed, skipping OpenAlex batch check")
        return {doi: False for doi in dois}
    except Exception as e:
        print(f"  Error batch checking OpenAlex: {e}")
        return {doi: False for doi in dois}


def check_unpaywall_batch(
    papers: List[Dict[str, Any]],
    email: str,
    checkpoint_path: str,
    checkpoint: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Check all papers against Unpaywall API."""
    print("\n=== Checking Unpaywall ===")

    results = checkpoint.get('unpaywall', {})
    total = len(papers)

    for i, paper in enumerate(papers, 1):
        doi = paper.get('doi', '')
        if not doi or doi in results:
            continue

        result = check_unpaywall(doi, email)
        if result:
            results[doi] = result

        # Rate limit: 10 req/s = 100ms between requests
        time.sleep(0.1)

        # Progress every 100 papers
        if i % 100 == 0:
            print(f"  Progress: {i}/{total} papers checked")
            # Save checkpoint
            checkpoint['unpaywall'] = results
            save_checkpoint(checkpoint_path, checkpoint)

    # Final checkpoint save
    checkpoint['unpaywall'] = results
    save_checkpoint(checkpoint_path, checkpoint)

    print(f"  Completed: {len(results)} papers checked")
    return results


def check_europe_pmc_batch(
    papers: List[Dict[str, Any]],
    checkpoint_path: str,
    checkpoint: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Check all papers against Europe PMC."""
    print("\n=== Checking Europe PMC ===")

    results = checkpoint.get('europe_pmc', {})
    total = len(papers)

    for i, paper in enumerate(papers, 1):
        doi = paper.get('doi', '')
        if not doi or doi in results:
            continue

        result = check_europe_pmc(doi)
        if result:
            results[doi] = result

        # Rate limit: 150ms between requests
        time.sleep(0.15)

        # Progress every 100 papers
        if i % 100 == 0:
            print(f"  Progress: {i}/{total} papers checked")
            # Save checkpoint
            checkpoint['europe_pmc'] = results
            save_checkpoint(checkpoint_path, checkpoint)

    # Final checkpoint save
    checkpoint['europe_pmc'] = results
    save_checkpoint(checkpoint_path, checkpoint)

    print(f"  Completed: {len(results)} papers checked")
    return results


def check_openalex_batch(
    papers: List[Dict[str, Any]],
    checkpoint_path: str,
    checkpoint: Dict[str, Any]
) -> Dict[str, bool]:
    """Check all papers for OpenAlex has_fulltext."""
    print("\n=== Checking OpenAlex ===")

    results = checkpoint.get('openalex', {})

    # First, check existing data in papers
    for paper in papers:
        doi = paper.get('doi', '')
        if not doi or doi in results:
            continue

        # Check if we already have OA info
        if paper.get('oa_url') or paper.get('primary_location', {}).get('is_oa'):
            results[doi] = True

    # Collect DOIs that need batch checking
    dois_to_check = []
    for paper in papers:
        doi = paper.get('doi', '')
        if doi and doi not in results:
            dois_to_check.append(doi)

    if dois_to_check:
        print(f"  Batch checking {len(dois_to_check)} papers...")

        # Process in batches of 200
        batch_size = 200
        for i in range(0, len(dois_to_check), batch_size):
            batch = dois_to_check[i:i + batch_size]
            batch_results = batch_check_openalex(batch)
            results.update(batch_results)

            print(f"  Progress: {min(i + batch_size, len(dois_to_check))}/{len(dois_to_check)} papers checked")

            # Save checkpoint
            checkpoint['openalex'] = results
            save_checkpoint(checkpoint_path, checkpoint)

            # Rate limit between batches
            if i + batch_size < len(dois_to_check):
                time.sleep(1)

    # Final checkpoint save
    checkpoint['openalex'] = results
    save_checkpoint(checkpoint_path, checkpoint)

    print(f"  Completed: {len(results)} papers checked")
    return results


def compute_summary(
    papers: List[Dict[str, Any]],
    unpaywall_results: Dict[str, Dict[str, Any]],
    epmc_results: Dict[str, Dict[str, Any]],
    openalex_results: Dict[str, bool]
) -> Dict[str, Any]:
    """Compute coverage summary across all sources."""

    # Unpaywall stats
    oa_count = sum(1 for r in unpaywall_results.values() if r.get('is_oa'))
    pdf_available = sum(1 for r in unpaywall_results.values() if r.get('pdf_url'))

    by_status = {}
    for r in unpaywall_results.values():
        status = r.get('oa_status', 'closed')
        by_status[status] = by_status.get(status, 0) + 1

    # Europe PMC stats
    epmc_found = sum(1 for r in epmc_results.values() if r.get('found'))
    epmc_pmcid = sum(1 for r in epmc_results.values() if r.get('pmcid'))
    epmc_fulltext = sum(1 for r in epmc_results.values() if r.get('has_fulltext_xml'))

    # OpenAlex stats
    openalex_fulltext = sum(1 for has_ft in openalex_results.values() if has_ft)

    # Combined stats - per paper
    per_paper = []
    any_fulltext_count = 0
    pdf_or_xml_count = 0

    for paper in papers:
        doi = paper.get('doi', '')
        if not doi:
            continue

        unpaywall = unpaywall_results.get(doi, {})
        epmc = epmc_results.get(doi, {})
        openalex = openalex_results.get(doi, False)

        has_pdf = bool(unpaywall.get('pdf_url'))
        has_xml = epmc.get('has_fulltext_xml', False)
        has_oa = unpaywall.get('is_oa', False) or openalex

        # Any fulltext = has PDF or XML or OpenAlex fulltext
        has_any = has_pdf or has_xml or openalex

        if has_any:
            any_fulltext_count += 1

        if has_pdf or has_xml:
            pdf_or_xml_count += 1

        per_paper.append({
            'doi': doi,
            'unpaywall_oa': unpaywall.get('is_oa', False),
            'unpaywall_pdf': unpaywall.get('pdf_url'),
            'unpaywall_status': unpaywall.get('oa_status', 'closed'),
            'epmc_pmcid': epmc.get('pmcid'),
            'openalex_fulltext': openalex
        })

    total_papers = len(papers)
    any_fulltext_pct = any_fulltext_count / total_papers if total_papers > 0 else 0

    # Go/No-Go decision: >= 60% threshold
    go_no_go = "GO" if any_fulltext_pct >= 0.60 else "NO-GO"

    return {
        'total_papers': total_papers,
        'sources': {
            'unpaywall': {
                'oa_count': oa_count,
                'pdf_available': pdf_available,
                'by_status': by_status
            },
            'europe_pmc': {
                'found': epmc_found,
                'has_pmcid': epmc_pmcid,
                'has_fulltext_xml': epmc_fulltext
            },
            'openalex': {
                'has_fulltext': openalex_fulltext
            }
        },
        'combined': {
            'any_fulltext': any_fulltext_count,
            'any_fulltext_pct': round(any_fulltext_pct, 4),
            'pdf_or_xml': pdf_or_xml_count,
            'go_no_go': go_no_go
        },
        'per_paper': per_paper
    }


def print_summary(summary: Dict[str, Any]) -> None:
    """Print human-readable summary."""
    print("\n" + "="*60)
    print("FULLTEXT COVERAGE SUMMARY")
    print("="*60)

    total = summary['total_papers']
    print(f"\nTotal papers: {total}")

    # Unpaywall
    upw = summary['sources']['unpaywall']
    print(f"\nUnpaywall:")
    print(f"  OA papers: {upw['oa_count']} ({upw['oa_count']/total*100:.1f}%)")
    print(f"  PDF available: {upw['pdf_available']} ({upw['pdf_available']/total*100:.1f}%)")
    print(f"  By status:")
    for status, count in sorted(upw['by_status'].items()):
        print(f"    {status}: {count} ({count/total*100:.1f}%)")

    # Europe PMC
    epmc = summary['sources']['europe_pmc']
    print(f"\nEurope PMC:")
    print(f"  Found: {epmc['found']} ({epmc['found']/total*100:.1f}%)")
    print(f"  Has PMCID: {epmc['has_pmcid']} ({epmc['has_pmcid']/total*100:.1f}%)")
    print(f"  Fulltext XML: {epmc['has_fulltext_xml']} ({epmc['has_fulltext_xml']/total*100:.1f}%)")

    # OpenAlex
    oalex = summary['sources']['openalex']
    print(f"\nOpenAlex:")
    print(f"  Has fulltext: {oalex['has_fulltext']} ({oalex['has_fulltext']/total*100:.1f}%)")

    # Combined
    combined = summary['combined']
    print(f"\n" + "="*60)
    print(f"COMBINED COVERAGE:")
    print(f"  Any fulltext: {combined['any_fulltext']} ({combined['any_fulltext_pct']*100:.1f}%)")
    print(f"  PDF or XML: {combined['pdf_or_xml']} ({combined['pdf_or_xml']/total*100:.1f}%)")
    print(f"\n  VERDICT: {combined['go_no_go']} (threshold: 60%)")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Measure fulltext availability across free sources'
    )
    parser.add_argument(
        '--input',
        default='results/virtual-cell-sweep/papers_enriched.json',
        help='Input papers JSON file'
    )
    parser.add_argument(
        '--output-dir',
        default='outputs/e006',
        help='Output directory for results'
    )
    parser.add_argument(
        '--email',
        default=os.environ.get('UNPAYWALL_EMAIL', 'kyuwon.shim@example.com'),
        help='Email for Unpaywall API (required)'
    )
    parser.add_argument(
        '--skip-unpaywall',
        action='store_true',
        help='Skip Unpaywall check'
    )
    parser.add_argument(
        '--skip-epmc',
        action='store_true',
        help='Skip Europe PMC check'
    )
    parser.add_argument(
        '--skip-openalex',
        action='store_true',
        help='Skip OpenAlex check'
    )

    args = parser.parse_args()

    # Validate email
    if not args.skip_unpaywall and '@' not in args.email:
        print("Error: Valid email required for Unpaywall API", file=sys.stderr)
        print("Use --email or set UNPAYWALL_EMAIL environment variable", file=sys.stderr)
        sys.exit(1)

    # Warn about example.com emails
    if not args.skip_unpaywall and 'example.com' in args.email:
        print("Warning: Unpaywall API rejects 'example.com' emails.", file=sys.stderr)
        print("Please provide a real email address via --email flag.", file=sys.stderr)
        print("Continuing anyway - Unpaywall checks will fail but other sources will work.\n", file=sys.stderr)

    # Load papers
    papers = load_papers(args.input)

    # Setup checkpoint
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = str(output_dir / 'checkpoint.json')
    checkpoint = load_checkpoint(checkpoint_path)

    # Check each source
    unpaywall_results = {}
    if not args.skip_unpaywall:
        unpaywall_results = check_unpaywall_batch(papers, args.email, checkpoint_path, checkpoint)

    epmc_results = {}
    if not args.skip_epmc:
        epmc_results = check_europe_pmc_batch(papers, checkpoint_path, checkpoint)

    openalex_results = {}
    if not args.skip_openalex:
        openalex_results = check_openalex_batch(papers, checkpoint_path, checkpoint)

    # Compute summary
    print("\n=== Computing Summary ===")
    summary = compute_summary(papers, unpaywall_results, epmc_results, openalex_results)

    # Save results
    output_path = output_dir / 'fulltext_coverage.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults saved to {output_path}")

    # Print summary
    print_summary(summary)


if __name__ == '__main__':
    main()
