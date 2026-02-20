"""PyAlex-based paper discovery module."""

from typing import Optional
import pyalex
from pyalex import Works
from tqdm import tqdm

from papersift.doi import normalize_doi


class PaperDiscovery:
    """PyAlex wrapper for paper search with abstract restoration."""

    def __init__(self, email: str):
        """Initialize with email for polite pool access.

        Args:
            email: Contact email for OpenAlex polite pool (faster rate limits)
        """
        pyalex.config.email = email
        pyalex.config.max_retries = 3
        pyalex.config.retry_backoff_factor = 0.1
        pyalex.config.retry_http_codes = [429, 500, 503]

    def search(
        self,
        query: str,
        max_results: int = 50,
        filters: Optional[dict] = None,
        show_progress: bool = True,
    ) -> list[dict]:
        """Search papers by query with optional filters.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            filters: Optional filters dict, e.g. {"publication_year": ">2020", "is_oa": True}
            show_progress: Show tqdm progress bar

        Returns:
            List of normalized paper dicts with restored abstracts
        """
        q = Works().search(query)

        if filters:
            q = q.filter(**filters)

        q = q.sort(cited_by_count="desc")

        results = []
        iterator = q.paginate(per_page=min(200, max_results), n_max=max_results)

        if show_progress:
            iterator = tqdm(iterator, desc="Searching papers", unit="page")

        for page in iterator:
            for work in page:
                results.append(self._normalize_work(work))
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        return results[:max_results]

    def search_by_topic(
        self,
        topic_id: str,
        max_results: int = 50,
        **filters,
    ) -> list[dict]:
        """Search papers by OpenAlex topic ID.

        Args:
            topic_id: OpenAlex topic ID (e.g., "T10000")
            max_results: Maximum results
            **filters: Additional filters

        Returns:
            List of normalized paper dicts
        """
        q = Works().filter(topics={"id": topic_id})

        if filters:
            q = q.filter(**filters)

        q = q.sort(cited_by_count="desc")

        results = []
        for page in q.paginate(per_page=min(200, max_results), n_max=max_results):
            for work in page:
                results.append(self._normalize_work(work))

        return results[:max_results]

    def search_by_dois(self, dois: list[str], show_progress: bool = True) -> list[dict]:
        """Fetch papers by DOI list with batch splitting.

        Args:
            dois: List of DOIs to fetch
            show_progress: Show progress bar

        Returns:
            List of normalized paper dicts
        """
        results = []
        batch_size = 30  # URL length limit

        batches = [dois[i:i + batch_size] for i in range(0, len(dois), batch_size)]

        iterator = batches
        if show_progress:
            iterator = tqdm(batches, desc="Fetching DOIs", unit="batch")

        for batch in iterator:
            # Build OR filter for DOIs
            doi_filter = "|".join(batch)
            try:
                works = Works().filter(doi=doi_filter).get()
                for work in works:
                    results.append(self._normalize_work(work))
            except Exception:
                # Fallback: fetch individually
                for doi in batch:
                    try:
                        work = Works().filter(doi=doi).get()
                        if work:
                            results.append(self._normalize_work(work[0]))
                    except Exception:
                        continue

        return results

    def get_oa_pdf_url(self, work: dict) -> Optional[str]:
        """Extract best OA PDF URL from work object.

        Priority: primary_location.pdf_url > oa_url > locations[].pdf_url

        Args:
            work: Raw PyAlex work object

        Returns:
            PDF URL or None if not available
        """
        # 1. Primary location PDF
        primary = work.get("primary_location") or {}
        if primary.get("pdf_url"):
            return primary["pdf_url"]

        # 2. Open access URL
        oa = work.get("open_access") or {}
        if oa.get("oa_url"):
            url = oa["oa_url"]
            if url.endswith(".pdf"):
                return url

        # 3. Search all locations
        for loc in work.get("locations") or []:
            if loc.get("pdf_url"):
                return loc["pdf_url"]

        # 4. Return OA URL even if not PDF (might redirect)
        if oa.get("oa_url"):
            return oa["oa_url"]

        return None

    def _normalize_work(self, work: dict) -> dict:
        """Convert PyAlex work to internal schema.

        Args:
            work: Raw PyAlex work object

        Returns:
            Normalized paper dict with all fields
        """
        doi = normalize_doi(work.get("doi") or "")

        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        oa = work.get("open_access") or {}

        return {
            "doi": doi,
            "openalex_id": work.get("id", ""),
            "title": work.get("title", ""),
            "abstract": work.get("abstract"),  # PyAlex auto-restores
            "publication_year": work.get("publication_year"),
            "publication_date": work.get("publication_date"),
            "journal": source.get("display_name"),
            "cited_by_count": work.get("cited_by_count", 0),
            "is_oa": oa.get("is_oa", False),
            "oa_status": oa.get("oa_status"),
            "oa_url": oa.get("oa_url"),
            "pdf_url": self.get_oa_pdf_url(work),
            "authorships": work.get("authorships", []),
            "topics": [
                {
                    "display_name": t.get("display_name", ""),
                    "score": t.get("score", 0),
                    "subfield": {
                        "display_name": (t.get("subfield") or {}).get("display_name", ""),
                    },
                    "field": {
                        "display_name": (t.get("field") or {}).get("display_name", ""),
                    },
                    "domain": {
                        "display_name": (t.get("domain") or {}).get("display_name", ""),
                    },
                }
                for t in (work.get("topics") or [])[:5]
            ],
            "type": work.get("type"),
        }
