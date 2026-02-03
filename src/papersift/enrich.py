"""
OpenAlex enrichment module for PaperSift.

Fetches referenced_works (as DOIs), topics, and abstracts from OpenAlex API.
Requires optional dependency: pip install papersift[enrich]
"""

import json
import sys
import time
from typing import Dict, List, Optional, Any

try:
    from pyalex import Works
    import pyalex
except ImportError:
    raise ImportError(
        "pyalex is required for enrichment. Install with: pip install papersift[enrich]"
    )


class OpenAlexEnricher:
    """Fetch and resolve OpenAlex data for papers."""

    BATCH_SIZE = 50  # OpenAlex filter limit per request
    DELAY = 0.1      # 100ms between requests (polite pool)

    def __init__(self, email: str):
        """
        Args:
            email: Contact email for OpenAlex polite pool (faster rate limits).
        """
        pyalex.config.email = email
        self.email = email

    def enrich_papers(
        self,
        papers: List[Dict[str, Any]],
        fields: Optional[List[str]] = None,
        progress: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Enrich papers with OpenAlex data.

        Args:
            papers: List of paper dicts with 'doi' key.
            fields: Fields to fetch. Default: ['referenced_works', 'openalex_id'].
                    Supported: 'referenced_works', 'openalex_id', 'topics', 'abstract'.
            progress: Show progress output.

        Returns:
            Papers list with requested fields added.
        """
        if fields is None:
            fields = ['referenced_works', 'openalex_id']

        papers_with_doi = [(i, p) for i, p in enumerate(papers) if p.get('doi')]
        total = len(papers_with_doi)

        if progress:
            print(f"Enriching {total} papers (of {len(papers)} total)...")

        enriched_count = 0
        for idx, (i, paper) in enumerate(papers_with_doi):
            doi = paper['doi']

            try:
                work = self._fetch_work(doi)
                if work is None:
                    continue

                if 'openalex_id' in fields:
                    papers[i]['openalex_id'] = work.get('id', '')

                if 'referenced_works' in fields:
                    ref_ids = work.get('referenced_works', [])
                    if ref_ids:
                        ref_dois = self._resolve_openalex_ids_to_dois(ref_ids)
                        papers[i]['referenced_works'] = ref_dois
                    else:
                        papers[i]['referenced_works'] = []

                if 'topics' in fields:
                    topics = work.get('topics', [])
                    papers[i]['topics'] = topics

                if 'abstract' in fields:
                    abstract = self._reconstruct_abstract(work)
                    if abstract:
                        papers[i]['abstract'] = abstract

                enriched_count += 1

            except Exception as e:
                if progress:
                    print(f"  Warning: Failed to enrich {doi}: {e}", file=sys.stderr)

            if progress and (idx + 1) % 10 == 0:
                print(f"  [{idx + 1}/{total}] enriched {enriched_count} papers")

            time.sleep(self.DELAY)

        if progress:
            print(f"Done: enriched {enriched_count}/{total} papers")

        return papers

    def _fetch_work(self, doi: str) -> Optional[Dict]:
        """Fetch a single work from OpenAlex by DOI."""
        try:
            # Normalize DOI to URL format for OpenAlex
            if not doi.startswith('http'):
                doi_url = f"https://doi.org/{doi}"
            else:
                doi_url = doi

            work = Works()[doi_url]
            return work
        except Exception:
            return None

    def _resolve_openalex_ids_to_dois(self, openalex_ids: List[str]) -> List[str]:
        """
        Batch-resolve OpenAlex work IDs to DOIs.

        Args:
            openalex_ids: List of OpenAlex URLs like 'https://openalex.org/W1234567'.

        Returns:
            List of DOIs (strings). IDs that can't be resolved are omitted.
        """
        dois = []

        # Process in batches
        for batch_start in range(0, len(openalex_ids), self.BATCH_SIZE):
            batch = openalex_ids[batch_start:batch_start + self.BATCH_SIZE]

            # Build pipe-separated filter
            id_filter = "|".join(batch)

            try:
                results = Works().filter(openalex_id=id_filter).get()
                for work in results:
                    doi = work.get('doi')
                    if doi:
                        # OpenAlex returns DOIs as URLs, strip prefix
                        if doi.startswith('https://doi.org/'):
                            doi = doi[len('https://doi.org/'):]
                        dois.append(doi)

                time.sleep(self.DELAY)

            except Exception:
                # Skip batch on error
                continue

        return dois

    @staticmethod
    def _reconstruct_abstract(work: Dict) -> Optional[str]:
        """Reconstruct abstract from OpenAlex inverted index format."""
        inv_index = work.get('abstract_inverted_index')
        if not inv_index:
            return None

        # Inverted index: {word: [positions]}
        word_positions = []
        for word, positions in inv_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        word_positions.sort(key=lambda x: x[0])
        return " ".join(word for _, word in word_positions)
