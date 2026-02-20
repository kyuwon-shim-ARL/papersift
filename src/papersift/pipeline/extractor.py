"""Text extraction from PDF/XML with GROBID and pymupdf4llm fallback."""

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


@dataclass
class ExtractionResult:
    """Result of text extraction."""
    sections: dict[str, str] = field(default_factory=dict)
    abstract: Optional[str] = None
    full_text: str = ""
    tables: list[str] = field(default_factory=list)
    figure_captions: list[str] = field(default_factory=list)
    extraction_method: str = ""


class PaperExtractor:
    """Extract structured text from papers using GROBID or pymupdf4llm."""

    # Europe PMC section type mappings
    PMC_SECTION_TYPES = {
        "intro": "Introduction",
        "introduction": "Introduction",
        "background": "Background",
        "methods": "Methods",
        "materials": "Methods",
        "materials|methods": "Methods",
        "results": "Results",
        "discussion": "Discussion",
        "conclusions": "Conclusions",
        "conclusion": "Conclusions",
        "supplementary-material": "Supplementary",
        "acknowledgments": "Acknowledgments",
        "references": "References",
    }

    def __init__(self, grobid_url: str = "http://localhost:8070"):
        """Initialize extractor.

        Args:
            grobid_url: GROBID service URL
        """
        self.grobid_url = grobid_url
        self.grobid_available = self._check_grobid()

    def _check_grobid(self) -> bool:
        """Check if GROBID service is available.

        Returns:
            True if GROBID is running
        """
        try:
            resp = requests.get(f"{self.grobid_url}/api/isalive", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def extract(
        self,
        content_type: str,
        data: Optional[str] = None,
        pdf_path: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract text based on content type.

        Args:
            content_type: "pmc_xml", "pdf", etc.
            data: XML/text content (for pmc_xml)
            pdf_path: Path to PDF file

        Returns:
            ExtractionResult with sections and full text
        """
        if content_type == "pmc_xml" and data:
            return self.extract_from_europe_pmc_xml(data)

        if content_type == "pdf" and pdf_path:
            if self.grobid_available:
                result = self.extract_from_pdf_grobid(pdf_path)
                if result.sections:  # GROBID succeeded
                    return result
            # Fallback to pymupdf4llm
            return self.extract_from_pdf_pymupdf(pdf_path)

        # Empty result
        return ExtractionResult(extraction_method="none")

    def extract_from_europe_pmc_xml(self, xml_content: str) -> ExtractionResult:
        """Extract text from Europe PMC JATS XML.

        Args:
            xml_content: Full XML content string

        Returns:
            ExtractionResult with sections
        """
        result = ExtractionResult(extraction_method="europe_pmc_xml")

        try:
            # Parse XML
            root = ET.fromstring(xml_content)

            # Handle namespaces - find the actual root
            # PMC XML might have different structures
            article = root
            if root.tag != "article":
                article = root.find(".//article")
                if article is None:
                    article = root

            # Extract abstract
            abstract_elem = article.find(".//abstract")
            if abstract_elem is not None:
                result.abstract = self._get_element_text(abstract_elem)

            # Extract body sections
            body = article.find(".//body")
            if body is not None:
                for sec in body.findall(".//sec"):
                    sec_type = sec.get("sec-type", "").lower()

                    # Get section title
                    title_elem = sec.find("title")
                    if title_elem is not None and title_elem.text:
                        section_name = title_elem.text.strip()
                    elif sec_type in self.PMC_SECTION_TYPES:
                        section_name = self.PMC_SECTION_TYPES[sec_type]
                    else:
                        section_name = "Section"

                    # Get section content
                    content = self._get_section_content(sec)
                    if content:
                        # Merge if same section exists
                        if section_name in result.sections:
                            result.sections[section_name] += "\n\n" + content
                        else:
                            result.sections[section_name] = content

            # Extract tables
            for table in article.findall(".//table-wrap"):
                caption = table.find(".//caption")
                if caption is not None:
                    result.tables.append(self._get_element_text(caption))

            # Extract figure captions
            for fig in article.findall(".//fig"):
                caption = fig.find(".//caption")
                if caption is not None:
                    result.figure_captions.append(self._get_element_text(caption))

            # Build full text
            parts = []
            if result.abstract:
                parts.append(f"## Abstract\n\n{result.abstract}")
            for name, content in result.sections.items():
                parts.append(f"## {name}\n\n{content}")

            result.full_text = "\n\n".join(parts)

        except Exception as e:
            result.extraction_method = f"europe_pmc_xml_error: {str(e)}"

        return result

    def _get_element_text(self, elem: ET.Element) -> str:
        """Get all text content from an element recursively."""
        return "".join(elem.itertext()).strip()

    def _get_section_content(self, sec: ET.Element) -> str:
        """Get content from section, excluding nested sections."""
        paragraphs = []

        for p in sec.findall("p"):
            text = self._get_element_text(p)
            if text:
                paragraphs.append(text)

        return "\n\n".join(paragraphs)

    def extract_from_pdf_grobid(self, pdf_path: str) -> ExtractionResult:
        """Extract text from PDF using GROBID.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ExtractionResult with sections from TEI XML
        """
        result = ExtractionResult(extraction_method="grobid")

        try:
            # Call GROBID
            url = f"{self.grobid_url}/api/processFulltextDocument"

            with open(pdf_path, "rb") as f:
                files = {"input": f}
                data = {"consolidateHeader": "1", "consolidateCitations": "0"}
                resp = requests.post(url, files=files, data=data, timeout=300)

            if resp.status_code != 200:
                return result

            tei_xml = resp.text

            # Save TEI XML for reference
            tei_path = Path(pdf_path).with_suffix(".tei.xml")
            with open(tei_path, "w", encoding="utf-8") as f:
                f.write(tei_xml)

            # Parse TEI XML
            result.sections = self._parse_tei_xml(tei_xml)

            # Extract abstract
            root = ET.fromstring(tei_xml)
            ns = {"tei": "http://www.tei-c.org/ns/1.0"}

            abstract_elem = root.find(".//tei:abstract", ns)
            if abstract_elem is not None:
                result.abstract = self._get_element_text(abstract_elem)

            # Build full text
            parts = []
            if result.abstract:
                parts.append(f"## Abstract\n\n{result.abstract}")
            for name, content in result.sections.items():
                parts.append(f"## {name}\n\n{content}")

            result.full_text = "\n\n".join(parts)

        except Exception as e:
            result.extraction_method = f"grobid_error: {str(e)}"

        return result

    def _parse_tei_xml(self, tei_xml: str) -> dict[str, str]:
        """Parse GROBID TEI XML to extract sections.

        Uses ElementTree directly (grobidmonkey fallback removed for reliability).

        Args:
            tei_xml: TEI XML content string

        Returns:
            Dict mapping section names to content
        """
        sections = {}

        try:
            root = ET.fromstring(tei_xml)
            ns = {"tei": "http://www.tei-c.org/ns/1.0"}

            # Find body
            body = root.find(".//tei:body", ns)
            if body is None:
                return sections

            # Process divisions
            for div in body.findall("tei:div", ns):
                # Get section head
                head = div.find("tei:head", ns)
                if head is not None and head.text:
                    section_name = head.text.strip()
                    # Clean up numbered sections (e.g., "1. Introduction" -> "Introduction")
                    section_name = re.sub(r"^\d+\.\s*", "", section_name)
                else:
                    # Try to identify by content
                    section_name = "Section"

                # Get paragraphs
                paragraphs = []
                for p in div.findall("tei:p", ns):
                    text = self._get_element_text(p)
                    if text:
                        paragraphs.append(text)

                if paragraphs:
                    content = "\n\n".join(paragraphs)
                    if section_name in sections:
                        sections[section_name] += "\n\n" + content
                    else:
                        sections[section_name] = content

        except Exception:
            pass

        return sections

    def extract_from_pdf_pymupdf(self, pdf_path: str) -> ExtractionResult:
        """Extract text from PDF using pymupdf4llm (fallback).

        Args:
            pdf_path: Path to PDF file

        Returns:
            ExtractionResult with markdown text
        """
        result = ExtractionResult(extraction_method="pymupdf4llm")

        try:
            import pymupdf4llm

            # Convert PDF to markdown
            md_text = pymupdf4llm.to_markdown(pdf_path)
            result.full_text = md_text

            # Try to segment by common section headers
            result.sections = self._regex_segment(md_text)

            # Extract abstract if found in sections
            for key in ["Abstract", "ABSTRACT", "Summary", "SUMMARY"]:
                if key in result.sections:
                    result.abstract = result.sections[key]
                    break

        except ImportError:
            # pymupdf4llm not installed, try basic PyMuPDF
            try:
                import fitz  # PyMuPDF

                doc = fitz.open(pdf_path)
                text_parts = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()

                result.full_text = "\n".join(text_parts)
                result.sections = self._regex_segment(result.full_text)
                result.extraction_method = "pymupdf_basic"

            except Exception as e:
                result.extraction_method = f"pymupdf_error: {str(e)}"

        except Exception as e:
            result.extraction_method = f"pymupdf4llm_error: {str(e)}"

        return result

    def _regex_segment(self, text: str) -> dict[str, str]:
        """Segment text by common section headers using regex.

        Args:
            text: Full text content

        Returns:
            Dict of section names to content
        """
        sections = {}

        # Common section headers pattern
        header_pattern = r"(?:^|\n)#+\s*(\d*\.?\s*(?:Abstract|Introduction|Background|Methods|Materials|Results|Discussion|Conclusions?|Acknowledgments?|References))\s*\n"

        # Find all headers
        matches = list(re.finditer(header_pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            section_name = match.group(1).strip()
            # Clean up numbering
            section_name = re.sub(r"^\d+\.\s*", "", section_name)
            section_name = section_name.title()

            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            content = text[start:end].strip()
            if content:
                sections[section_name] = content

        # If no sections found, create a single "Content" section
        if not sections and text.strip():
            sections["Content"] = text.strip()

        return sections
