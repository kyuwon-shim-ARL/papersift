"""Abstract fetcher module using 3-API cascade.

This module fetches abstracts for academic papers using a cascading strategy:
1. OpenAlex (batch of 50, 200ms delay) - primary source, free, fast
2. Semantic Scholar (batch of 200, 1s delay) - fills gaps from step 1
3. Europe PMC (individual, 150ms delay) - final fallback for remaining papers

All APIs use stdlib urllib (no external dependencies).
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable


class AbstractFetcher:
    """Fetch abstracts from OpenAlex, Semantic Scholar, and Europe PMC."""

    def __init__(
        self,
        email: str = "",
        skip_epmc: bool = False,
        on_progress: Callable[[str, int, int], None] | None = None,
    ):
        """Initialize the abstract fetcher.

        Args:
            email: Email for OpenAlex polite pool (recommended for faster access)
            skip_epmc: Skip Europe PMC individual queries (faster but lower coverage)
            on_progress: Callback(source_name, found_count, total_count) for progress reporting
        """
        self.email = email
        self.skip_epmc = skip_epmc
        self.on_progress = on_progress

    def fetch_all(self, papers: list[dict]) -> dict[str, str]:
        """Fetch abstracts for all papers using 3-API cascade.

        Args:
            papers: List of paper dicts, each must have 'doi' field

        Returns:
            Dict mapping lowercase DOI to abstract text
        """
        # Extract DOIs
        dois = []
        for paper in papers:
            doi = paper.get("doi", "")
            if doi:
                # Normalize DOI: strip https://doi.org/ prefix and lowercase
                doi_clean = doi.replace("https://doi.org/", "").lower()
                dois.append(doi_clean)

        if not dois:
            return {}

        total = len(dois)
        results = {}

        # Stage 1: OpenAlex batch
        print(f"Fetching abstracts from OpenAlex (batch of 50)...", file=sys.stderr)
        openalex_results = self._fetch_openalex_batch(dois)
        results.update(openalex_results)
        if self.on_progress:
            self.on_progress("openalex", len(openalex_results), total)
        print(
            f"  OpenAlex: {len(openalex_results)}/{total} abstracts found",
            file=sys.stderr,
        )

        # Stage 2: Semantic Scholar batch (remaining)
        remaining = [d for d in dois if d not in results]
        if remaining:
            print(
                f"Fetching remaining from Semantic Scholar (batch of 200)...",
                file=sys.stderr,
            )
            s2_results = self._fetch_s2_batch(remaining)
            results.update(s2_results)
            if self.on_progress:
                self.on_progress("s2", len(s2_results), len(remaining))
            print(
                f"  Semantic Scholar: {len(s2_results)}/{len(remaining)} abstracts found",
                file=sys.stderr,
            )

        # Stage 3: Europe PMC individual (still remaining)
        if not self.skip_epmc:
            remaining = [d for d in dois if d not in results]
            if remaining:
                print(
                    f"Fetching remaining from Europe PMC (individual queries)...",
                    file=sys.stderr,
                )
                epmc_count = 0
                for i, doi in enumerate(remaining):
                    abstract = self._fetch_epmc_single(doi)
                    if abstract:
                        results[doi] = abstract
                        epmc_count += 1
                    if (i + 1) % 10 == 0:
                        print(
                            f"  Progress: {i + 1}/{len(remaining)} queried, {epmc_count} found",
                            file=sys.stderr,
                        )
                    if i < len(remaining) - 1:
                        time.sleep(0.15)
                if self.on_progress:
                    self.on_progress("epmc", epmc_count, len(remaining))
                print(
                    f"  Europe PMC: {epmc_count}/{len(remaining)} abstracts found",
                    file=sys.stderr,
                )

        print(f"Total: {len(results)}/{total} abstracts fetched", file=sys.stderr)
        return results

    def _fetch_openalex_batch(self, dois: list[str]) -> dict[str, str]:
        """Fetch abstracts from OpenAlex in batches of 50.

        Args:
            dois: List of lowercase DOIs

        Returns:
            Dict mapping lowercase DOI to abstract text
        """
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
            if self.email:
                params["mailto"] = self.email

            url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"

            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "PaperSift/1.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())

                for work in data.get("results", []):
                    doi_raw = work.get("doi", "")
                    if doi_raw:
                        doi_clean = doi_raw.replace("https://doi.org/", "").lower()
                        aii = work.get("abstract_inverted_index")
                        if aii:
                            abstract = self._reconstruct_abstract(aii)
                            if abstract:
                                results[doi_clean] = abstract

            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
            ) as e:
                print(
                    f"  OpenAlex batch {i // batch_size + 1} error: {e}",
                    file=sys.stderr,
                )

            # Delay between batches
            if i + batch_size < len(dois):
                time.sleep(0.2)

        return results

    def _fetch_s2_batch(self, dois: list[str]) -> dict[str, str]:
        """Fetch abstracts from Semantic Scholar in batches of 200.

        Args:
            dois: List of lowercase DOIs

        Returns:
            Dict mapping lowercase DOI to abstract text
        """
        results = {}
        batch_size = 200

        for i in range(0, len(dois), batch_size):
            batch = dois[i : i + batch_size]
            payload = json.dumps({"ids": [f"DOI:{d}" for d in batch]}).encode()
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

                # S2 returns list with null entries for DOIs it can't find
                for j, entry in enumerate(data):
                    if entry is not None and entry.get("abstract"):
                        ext = entry.get("externalIds", {})
                        doi = ext.get("DOI", "").lower() if ext else ""
                        # Fallback to batch DOI if externalIds.DOI is missing
                        if not doi and j < len(batch):
                            doi = batch[j].lower()
                        if doi:
                            results[doi] = entry["abstract"]

            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
            ) as e:
                print(
                    f"  S2 batch {i // batch_size + 1} error: {e}", file=sys.stderr
                )

            # Delay between batches
            if i + batch_size < len(dois):
                time.sleep(1.0)

        return results

    def _fetch_epmc_single(self, doi: str) -> str | None:
        """Fetch abstract from Europe PMC for a single DOI.

        Args:
            doi: Lowercase DOI

        Returns:
            Abstract text or None if not found
        """
        query = urllib.parse.quote(f'DOI:"{doi}"')
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&pageSize=1&resultType=core"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperSift/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            results = data.get("resultList", {}).get("result", [])
            if results and results[0].get("abstractText"):
                # Strip HTML tags
                abstract = re.sub(r"<[^>]+>", "", results[0]["abstractText"])
                return abstract.strip()

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass

        return None

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        """Reconstruct abstract text from OpenAlex inverted index.

        Args:
            inverted_index: Dict mapping word to list of positions

        Returns:
            Reconstructed abstract text
        """
        if not inverted_index:
            return ""

        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        word_positions.sort()
        return " ".join(w for _, w in word_positions)


def attach_abstracts(
    papers: list[dict], abstracts: dict[str, str]
) -> tuple[list[dict], dict]:
    """Attach abstracts to papers and return statistics.

    Mutates papers in-place by setting paper["abstract"].

    Args:
        papers: List of paper dicts
        abstracts: Dict mapping lowercase DOI to abstract text

    Returns:
        Tuple of (papers, stats_dict) where stats_dict contains:
        - total: Total number of papers
        - with_abstract: Papers that got an abstract
        - without_abstract: Papers without abstract
        - without_doi: Papers missing DOI field
        - sources: Empty dict (source tracking not implemented per-DOI)
    """
    total = len(papers)
    without_doi = 0
    with_abstract = 0
    without_abstract = 0

    for paper in papers:
        doi = paper.get("doi", "")
        if not doi:
            without_doi += 1
            paper["abstract"] = ""
            continue

        # Normalize DOI
        doi_clean = doi.replace("https://doi.org/", "").lower()
        abstract = abstracts.get(doi_clean, "")

        paper["abstract"] = abstract
        if abstract:
            with_abstract += 1
        else:
            without_abstract += 1

    stats = {
        "total": total,
        "with_abstract": with_abstract,
        "without_abstract": without_abstract,
        "without_doi": without_doi,
        "sources": {},  # Aggregate source tracking not implemented
    }

    return papers, stats
