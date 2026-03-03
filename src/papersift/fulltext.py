"""PMC fulltext fetcher module.

Fetches JATS XML fulltext from Europe PMC for papers with open-access content.
Uses DOI→PMCID lookup via Europe PMC search API, then fetches fulltext XML.

All APIs use stdlib urllib (no external dependencies), matching abstract.py pattern.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable
from xml.etree import ElementTree as ET


def extract_text_recursive(element: ET.Element) -> str:
    """Recursively extract all text content from an XML element.

    Strips all tags and returns plain text.
    """
    text_parts = []

    if element.text:
        text_parts.append(element.text.strip())

    for child in element:
        text_parts.append(extract_text_recursive(child))
        if child.tail:
            text_parts.append(child.tail.strip())

    return " ".join(filter(None, text_parts))


def extract_section_text(
    root: ET.Element, section_titles: list[str], sec_types: list[str]
) -> str:
    """Extract text from <sec> elements matching given titles or sec-type attributes.

    Args:
        root: XML root element
        section_titles: List of title keywords to match (case-insensitive)
        sec_types: List of sec-type attribute values to match

    Returns:
        Concatenated plain text from all matching sections
    """
    sections = []

    for sec in root.iter("sec"):
        sec_type = sec.get("sec-type", "").lower()
        if any(st in sec_type for st in sec_types):
            sections.append(extract_text_recursive(sec))
            continue

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


def parse_jats_xml(xml_content: str) -> dict[str, str]:
    """Parse JATS XML and extract Methods, Results, Discussion, and full body text.

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
            "full_body_text": "",
        }

    methods_text = extract_section_text(
        root,
        section_titles=["method", "material", "experiment", "procedure"],
        sec_types=["methods", "materials", "materials|methods", "materials-methods"],
    )

    results_text = extract_section_text(
        root,
        section_titles=["result", "finding"],
        sec_types=["results", "results|discussion"],
    )

    discussion_text = extract_section_text(
        root,
        section_titles=["discussion", "conclusion"],
        sec_types=["discussion", "conclusions"],
    )

    full_body_text = extract_body_text(root)

    return {
        "methods_text": methods_text,
        "results_text": results_text,
        "discussion_text": discussion_text,
        "full_body_text": full_body_text,
    }


class FulltextFetcher:
    """Fetch PMC fulltext via Europe PMC APIs.

    Uses DOI→PMCID lookup, then fetches JATS XML for open-access papers.
    """

    def __init__(
        self,
        on_progress: Callable[[str, int, int], None] | None = None,
    ):
        """Initialize the fulltext fetcher.

        Args:
            on_progress: Callback(stage_name, found_count, total_count)
        """
        self.on_progress = on_progress

    def fetch_all(self, papers: list[dict]) -> dict[str, dict]:
        """Fetch fulltext for all papers with available PMC XML.

        Args:
            papers: List of paper dicts, each must have 'doi' field

        Returns:
            Dict mapping lowercase DOI to fulltext dict with keys:
            methods_text, results_text, discussion_text, full_body_text
        """
        # Extract DOIs
        dois = []
        for paper in papers:
            doi = paper.get("doi", "")
            if doi:
                doi_clean = doi.replace("https://doi.org/", "").lower()
                dois.append(doi_clean)

        if not dois:
            return {}

        total = len(dois)

        # Step 1: DOI → PMCID lookup
        print(f"Looking up PMCIDs for {total} DOIs...", file=sys.stderr)
        doi_to_pmcid = self._fetch_pmcids(dois)
        print(
            f"  Found {len(doi_to_pmcid)}/{total} PMCIDs",
            file=sys.stderr,
        )
        if self.on_progress:
            self.on_progress("pmcid_lookup", len(doi_to_pmcid), total)

        if not doi_to_pmcid:
            return {}

        # Step 2: Fetch XML for each PMCID
        print(
            f"Fetching PMC XML for {len(doi_to_pmcid)} papers...",
            file=sys.stderr,
        )
        results = {}
        fetched = 0
        failed = 0

        for i, (doi, pmcid) in enumerate(doi_to_pmcid.items()):
            # Rate limiting: 10 req/s = 100ms delay
            if i > 0:
                time.sleep(0.1)

            xml_content = self._fetch_pmc_xml(pmcid)
            if xml_content is None:
                failed += 1
                continue

            sections = parse_jats_xml(xml_content)

            # Only include if we got meaningful content
            if sections["methods_text"] or sections["results_text"] or sections["discussion_text"]:
                results[doi] = sections
                fetched += 1
            else:
                failed += 1

            if (i + 1) % 50 == 0:
                print(
                    f"  Progress: {i + 1}/{len(doi_to_pmcid)} ({fetched} with sections, {failed} failed)",
                    file=sys.stderr,
                )

        if self.on_progress:
            self.on_progress("xml_fetch", fetched, len(doi_to_pmcid))

        print(
            f"  Fulltext fetched: {fetched}/{len(doi_to_pmcid)} papers with sections",
            file=sys.stderr,
        )
        return results

    def _fetch_pmcids(self, dois: list[str]) -> dict[str, str]:
        """Batch lookup DOI→PMCID via Europe PMC search API.

        Args:
            dois: List of lowercase DOIs

        Returns:
            Dict mapping lowercase DOI to PMCID (e.g., "PMC12345")
        """
        results = {}

        for i, doi in enumerate(dois):
            query = urllib.parse.quote(f'DOI:"{doi}"')
            url = (
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                f"?query={query}&format=json&pageSize=1"
            )

            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "PaperSift/1.0"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())

                result_list = data.get("resultList", {}).get("result", [])
                if result_list:
                    pmcid = result_list[0].get("pmcid", "")
                    if pmcid:
                        results[doi] = pmcid

            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                pass

            # Rate limit: ~10 req/s
            if i < len(dois) - 1:
                time.sleep(0.1)

            if (i + 1) % 100 == 0:
                print(
                    f"  PMCID lookup: {i + 1}/{len(dois)} ({len(results)} found)",
                    file=sys.stderr,
                )

        return results

    def _fetch_pmc_xml(self, pmcid: str, max_retries: int = 3) -> str | None:
        """Fetch JATS XML from Europe PMC OA API.

        Args:
            pmcid: PMC ID (e.g., "PMC12148494")
            max_retries: Number of retries for 5xx errors

        Returns:
            XML content as string, or None if fetch failed
        """
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "PaperSift/1.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        return resp.read().decode()

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                elif e.code >= 500:
                    wait_time = 2**attempt
                    print(
                        f"Warning: {pmcid} returned {e.code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                        file=sys.stderr,
                    )
                    time.sleep(wait_time)
                else:
                    return None

            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                else:
                    return None

        return None


def attach_fulltext(
    papers: list[dict], fulltext_data: dict[str, dict]
) -> tuple[list[dict], dict]:
    """Attach fulltext sections to papers and return statistics.

    Mutates papers in-place by setting paper["fulltext"] dict.

    Args:
        papers: List of paper dicts
        fulltext_data: Dict mapping lowercase DOI to fulltext sections dict

    Returns:
        Tuple of (papers, stats_dict) where stats_dict contains:
        - total: Total number of papers
        - with_fulltext: Papers that got fulltext
        - without_fulltext: Papers without fulltext
        - without_doi: Papers missing DOI field
    """
    total = len(papers)
    without_doi = 0
    with_fulltext = 0
    without_fulltext = 0

    for paper in papers:
        doi = paper.get("doi", "")
        if not doi:
            without_doi += 1
            paper["fulltext"] = {}
            continue

        doi_clean = doi.replace("https://doi.org/", "").lower()
        ft = fulltext_data.get(doi_clean, {})

        paper["fulltext"] = ft
        if ft:
            with_fulltext += 1
        else:
            without_fulltext += 1

    stats = {
        "total": total,
        "with_fulltext": with_fulltext,
        "without_fulltext": without_fulltext,
        "without_doi": without_doi,
    }

    return papers, stats
