#!/usr/bin/env python3
"""Fetch abstracts for papers from OpenAlex, Semantic Scholar, and Europe PMC.

Usage:
    python scripts/fetch_abstracts.py results/virtual-cell/papers_cleaned.json \
        -o results/virtual-cell/papers_with_abstracts.json
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def fetch_openalex_batch(dois: list[str], email: str = "") -> dict[str, str]:
    """Fetch abstracts from OpenAlex API in batches of 50 DOIs."""
    results = {}
    batch_size = 50

    for i in range(0, len(dois), batch_size):
        batch = dois[i : i + batch_size]
        doi_filter = "|".join(f"https://doi.org/{d}" for d in batch)
        params = {
            "filter": f"doi:{doi_filter}",
            "select": "doi,abstract_inverted_index",
            "per_page": str(batch_size),
        }
        if email:
            params["mailto"] = email

        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperSift/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            for work in data.get("results", []):
                doi_raw = work.get("doi", "")
                if doi_raw:
                    doi_clean = doi_raw.replace("https://doi.org/", "").lower()
                    aii = work.get("abstract_inverted_index")
                    if aii:
                        abstract = reconstruct_abstract(aii)
                        if abstract:
                            results[doi_clean] = abstract
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  OpenAlex batch {i // batch_size + 1} error: {e}", file=sys.stderr)

        if i + batch_size < len(dois):
            time.sleep(0.2)  # polite rate limiting

    return results


def fetch_s2_batch(dois: list[str]) -> dict[str, str]:
    """Fetch abstracts from Semantic Scholar batch API (up to 500 per request)."""
    results = {}
    batch_size = 200  # conservative to avoid timeouts

    for i in range(0, len(dois), batch_size):
        batch = dois[i : i + batch_size]
        payload = json.dumps({
            "ids": [f"DOI:{d}" for d in batch],
        }).encode()

        url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=externalIds,abstract"
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "PaperSift/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())

            for j, entry in enumerate(data):
                if entry and entry.get("abstract"):
                    ext = entry.get("externalIds", {})
                    doi = ext.get("DOI", "").lower() if ext else ""
                    if not doi and j < len(batch):
                        doi = batch[j].lower()
                    if doi:
                        results[doi] = entry["abstract"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  S2 batch {i // batch_size + 1} error: {e}", file=sys.stderr)

        if i + batch_size < len(dois):
            time.sleep(1.0)  # S2 rate limit: 1 req/sec for unauthenticated

    return results


def fetch_epmc_single(doi: str) -> str | None:
    """Fetch abstract from Europe PMC for a single DOI."""
    query = urllib.parse.quote(f'DOI:"{doi}"')
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&pageSize=1&resultType=core"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PaperSift/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("resultList", {}).get("result", [])
        if results and results[0].get("abstractText"):
            import re
            abstract = re.sub(r"<[^>]+>", "", results[0]["abstractText"])
            return abstract.strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Fetch abstracts for papers")
    parser.add_argument("input", help="Input papers JSON file")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    parser.add_argument("--email", default="", help="Email for OpenAlex polite pool")
    parser.add_argument("--skip-epmc", action="store_true", help="Skip Europe PMC (slow)")
    args = parser.parse_args()

    papers = json.loads(Path(args.input).read_text())
    dois = [p["doi"] for p in papers if p.get("doi")]
    print(f"Total papers: {len(papers)}, with DOIs: {len(dois)}")

    # Phase 1: OpenAlex (fast, batch)
    print("\n[1/3] Fetching from OpenAlex...")
    oa_abstracts = fetch_openalex_batch(dois, email=args.email)
    print(f"  OpenAlex: {len(oa_abstracts)} abstracts ({len(oa_abstracts)/len(dois)*100:.1f}%)")

    # Phase 2: Semantic Scholar (batch, for remaining)
    remaining = [d for d in dois if d.lower() not in {k.lower() for k in oa_abstracts}]
    print(f"\n[2/3] Fetching from Semantic Scholar ({len(remaining)} remaining)...")
    s2_abstracts = fetch_s2_batch(remaining)
    print(f"  S2: {len(s2_abstracts)} abstracts")

    # Phase 3: Europe PMC (individual, for still-remaining)
    all_found = {k.lower() for k in oa_abstracts} | {k.lower() for k in s2_abstracts}
    still_remaining = [d for d in dois if d.lower() not in all_found]

    epmc_abstracts = {}
    if not args.skip_epmc and still_remaining:
        print(f"\n[3/3] Fetching from Europe PMC ({len(still_remaining)} remaining)...")
        for idx, doi in enumerate(still_remaining):
            abstract = fetch_epmc_single(doi)
            if abstract:
                epmc_abstracts[doi.lower()] = abstract
            if (idx + 1) % 20 == 0:
                print(f"  EPMC progress: {idx + 1}/{len(still_remaining)}")
            time.sleep(0.15)  # rate limit
        print(f"  EPMC: {len(epmc_abstracts)} abstracts")
    elif args.skip_epmc:
        print("\n[3/3] Skipping Europe PMC")

    # Merge all abstracts
    merged = {}
    for d in oa_abstracts:
        merged[d.lower()] = oa_abstracts[d]
    for d in s2_abstracts:
        if d.lower() not in merged:
            merged[d.lower()] = s2_abstracts[d]
    for d in epmc_abstracts:
        if d.lower() not in merged:
            merged[d.lower()] = epmc_abstracts[d]

    # Attach abstracts to papers
    with_abstract = 0
    for paper in papers:
        doi = paper.get("doi", "").lower()
        if doi in merged:
            paper["abstract"] = merged[doi]
            with_abstract += 1
        else:
            paper["abstract"] = ""

    # Summary
    total = len(papers)
    print(f"\n=== Summary ===")
    print(f"Total papers: {total}")
    print(f"With abstract: {with_abstract} ({with_abstract/total*100:.1f}%)")
    print(f"  OpenAlex: {len(oa_abstracts)}")
    print(f"  Semantic Scholar: {len(s2_abstracts)}")
    print(f"  Europe PMC: {len(epmc_abstracts)}")
    print(f"Without abstract: {total - with_abstract}")

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(papers, indent=2, ensure_ascii=False))
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
