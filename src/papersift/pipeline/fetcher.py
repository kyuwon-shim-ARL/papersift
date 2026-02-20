"""Multi-source paper content fetcher with graceful degradation."""

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests


@dataclass
class ContentResult:
    """Result of content fetch operation."""
    source: str  # "europe_pmc", "unpaywall", "openalex_oa", "biorxiv", "crossref"
    content_type: str  # "pmc_xml", "pdf", "abstract_only", "metadata_only"
    data: Optional[str]  # XML/text content or None for PDF
    pdf_path: Optional[str]  # Path to downloaded PDF


class RateLimiter:
    """Simple per-service rate limiter."""

    def __init__(self):
        self._last_call: dict[str, float] = {}
        self._intervals: dict[str, float] = {
            "europe_pmc": 0.2,  # 200ms
            "unpaywall": 0.1,   # 100ms
            "pdf": 2.0,         # 2000ms
            "biorxiv": 0.5,     # 500ms
            "crossref": 0.1,    # 100ms
        }

    def wait(self, service: str):
        """Wait if needed to respect rate limit."""
        now = time.time()
        last = self._last_call.get(service, 0)
        interval = self._intervals.get(service, 0.1)

        elapsed = now - last
        if elapsed < interval:
            time.sleep(interval - elapsed)

        self._last_call[service] = time.time()


class PaperFetcher:
    """Fetch paper content from multiple sources with fallback."""

    def __init__(self, email: str, ncbi_api_key: Optional[str] = None):
        """Initialize fetcher.

        Args:
            email: Contact email for API access
            ncbi_api_key: Optional NCBI API key for higher rate limits
        """
        self.email = email
        self.ncbi_api_key = ncbi_api_key or os.environ.get("NCBI_API_KEY")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"PaperPipeline/2.0 ({email})",
        })
        self.rate_limiter = RateLimiter()

    def fetch_content(
        self,
        doi: str,
        work_data: Optional[dict] = None,
        save_dir: Optional[Path] = None,
    ) -> ContentResult:
        """Fetch paper content with fallback chain.

        Fallback order:
        1. Europe PMC full-text XML
        2. OpenAlex OA URL (from work_data)
        3. Unpaywall API
        4. bioRxiv/medRxiv (if DOI starts with 10.1101/)
        5. CrossRef publisher links

        Args:
            doi: Paper DOI
            work_data: Optional OpenAlex work data with pdf_url
            save_dir: Directory to save PDF if downloaded

        Returns:
            ContentResult with source, type, and data/path
        """
        # Clean DOI
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

        # 1. Europe PMC full-text XML (best option - structured)
        pmc_xml = self.fetch_europe_pmc_fulltext(doi)
        if pmc_xml:
            return ContentResult(
                source="europe_pmc",
                content_type="pmc_xml",
                data=pmc_xml,
                pdf_path=None,
            )

        # 2. OpenAlex OA URL from work_data
        if work_data and work_data.get("pdf_url"):
            pdf_path = self._download_pdf(
                work_data["pdf_url"],
                save_dir,
                doi,
            )
            if pdf_path:
                return ContentResult(
                    source="openalex_oa",
                    content_type="pdf",
                    data=None,
                    pdf_path=pdf_path,
                )

        # 3. Unpaywall
        unpaywall_url = self.fetch_unpaywall_url(doi)
        if unpaywall_url:
            pdf_path = self._download_pdf(unpaywall_url, save_dir, doi)
            if pdf_path:
                return ContentResult(
                    source="unpaywall",
                    content_type="pdf",
                    data=None,
                    pdf_path=pdf_path,
                )

        # 4. bioRxiv/medRxiv
        if doi.startswith("10.1101/"):
            biorxiv_url = self.fetch_biorxiv_url(doi)
            if biorxiv_url:
                pdf_path = self._download_pdf(biorxiv_url, save_dir, doi)
                if pdf_path:
                    return ContentResult(
                        source="biorxiv",
                        content_type="pdf",
                        data=None,
                        pdf_path=pdf_path,
                    )

        # 5. CrossRef
        crossref_url = self.fetch_crossref_url(doi)
        if crossref_url:
            pdf_path = self._download_pdf(crossref_url, save_dir, doi)
            if pdf_path:
                return ContentResult(
                    source="crossref",
                    content_type="pdf",
                    data=None,
                    pdf_path=pdf_path,
                )

        # Fallback: abstract only (from work_data)
        if work_data and work_data.get("abstract"):
            return ContentResult(
                source="openalex",
                content_type="abstract_only",
                data=work_data["abstract"],
                pdf_path=None,
            )

        # Final fallback: metadata only
        return ContentResult(
            source="none",
            content_type="metadata_only",
            data=None,
            pdf_path=None,
        )

    def fetch_europe_pmc_fulltext(self, doi: str) -> Optional[str]:
        """Fetch full-text XML from Europe PMC.

        Args:
            doi: Paper DOI

        Returns:
            XML content string or None
        """
        self.rate_limiter.wait("europe_pmc")

        # Search for PMCID
        search_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": f'DOI:"{doi}"',
            "format": "json",
            "resultType": "core",
        }

        try:
            resp = self.session.get(search_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("resultList", {}).get("result", [])
            if not results:
                return None

            # Find PMCID
            pmcid = None
            for result in results:
                if result.get("pmcid"):
                    pmcid = result["pmcid"]
                    break

            if not pmcid:
                return None

            # Fetch full-text XML
            self.rate_limiter.wait("europe_pmc")
            xml_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

            resp = self.session.get(xml_url, timeout=60)
            resp.raise_for_status()

            # Verify it's actual XML
            content = resp.text
            if content.strip().startswith("<?xml") or content.strip().startswith("<"):
                # Check for article or DOCTYPE
                if "<!DOCTYPE" in content[:500] or "<article" in content[:500]:
                    return content

            return None

        except Exception:
            return None

    def fetch_unpaywall_url(self, doi: str) -> Optional[str]:
        """Get best OA PDF URL from Unpaywall.

        Args:
            doi: Paper DOI

        Returns:
            PDF URL or None
        """
        self.rate_limiter.wait("unpaywall")

        url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}"
        params = {"email": self.email}

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Best OA location
            best = data.get("best_oa_location")
            if best and best.get("url_for_pdf"):
                return best["url_for_pdf"]

            # Check all OA locations
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]

            return None

        except Exception:
            return None

    def fetch_biorxiv_url(self, doi: str) -> Optional[str]:
        """Get PDF URL from bioRxiv/medRxiv.

        Args:
            doi: Paper DOI (must start with 10.1101/)

        Returns:
            PDF URL or None
        """
        self.rate_limiter.wait("biorxiv")

        # Extract article ID from DOI
        article_id = doi.replace("10.1101/", "")

        # Try bioRxiv API
        api_url = f"https://api.biorxiv.org/details/biorxiv/{article_id}"

        try:
            resp = self.session.get(api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            messages = data.get("collection", [])
            if messages:
                # Get latest version
                latest = messages[-1]
                biorxiv_doi = latest.get("doi")
                if biorxiv_doi:
                    return f"https://www.biorxiv.org/content/{biorxiv_doi}.full.pdf"

            return None

        except Exception:
            # Try medRxiv
            try:
                api_url = f"https://api.biorxiv.org/details/medrxiv/{article_id}"
                resp = self.session.get(api_url, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                messages = data.get("collection", [])
                if messages:
                    latest = messages[-1]
                    medrxiv_doi = latest.get("doi")
                    if medrxiv_doi:
                        return f"https://www.medrxiv.org/content/{medrxiv_doi}.full.pdf"

                return None
            except Exception:
                return None

    def fetch_crossref_url(self, doi: str) -> Optional[str]:
        """Get PDF link from CrossRef.

        Args:
            doi: Paper DOI

        Returns:
            PDF URL or None
        """
        self.rate_limiter.wait("crossref")

        url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
        headers = {"User-Agent": f"PaperPipeline/2.0 ({self.email})"}

        try:
            resp = self.session.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            message = data.get("message", {})

            # Check links for PDF
            for link in message.get("link", []):
                if link.get("content-type") == "application/pdf":
                    return link.get("URL")
                if "pdf" in link.get("URL", "").lower():
                    return link["URL"]

            return None

        except Exception:
            return None

    def download_pdf(self, url: str, save_path: str) -> bool:
        """Download PDF to specified path.

        Args:
            url: PDF URL
            save_path: Path to save PDF

        Returns:
            True if successful
        """
        return self._download_pdf(url, Path(save_path).parent, "", Path(save_path)) is not None

    def _download_pdf(
        self,
        url: str,
        save_dir: Optional[Path],
        doi: str,
        final_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Internal PDF download with temp file.

        Args:
            url: PDF URL
            save_dir: Directory to save to
            doi: DOI for filename
            final_path: Optional specific final path

        Returns:
            Path to downloaded PDF or None
        """
        self.rate_limiter.wait("pdf")

        if save_dir is None:
            save_dir = Path(tempfile.gettempdir())

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        if final_path:
            pdf_path = final_path
        else:
            safe_doi = doi.replace("/", "_").replace(":", "_")
            pdf_path = save_dir / f"{safe_doi}.pdf"

        # Download to temp file first
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=save_dir)

        try:
            resp = self.session.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            # Verify content type
            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                # Check first bytes
                first_chunk = next(resp.iter_content(chunk_size=8), b"")
                if not first_chunk.startswith(b"%PDF"):
                    os.close(fd)
                    os.unlink(tmp_path)
                    return None

                # Write first chunk and continue
                with os.fdopen(fd, "wb") as f:
                    f.write(first_chunk)
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                with os.fdopen(fd, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

            # Verify it's a valid PDF
            with open(tmp_path, "rb") as f:
                header = f.read(8)

            if not header.startswith(b"%PDF"):
                os.unlink(tmp_path)
                return None

            # Move to final location
            os.replace(tmp_path, pdf_path)
            return str(pdf_path)

        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return None
