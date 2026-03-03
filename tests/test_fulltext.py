"""Unit tests for fulltext.py (PMC fulltext fetcher module)."""

import json
import pytest
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

from papersift.fulltext import (
    extract_text_recursive,
    extract_section_text,
    extract_body_text,
    parse_jats_xml,
    FulltextFetcher,
    attach_fulltext,
)


SAMPLE_JATS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <body>
    <sec sec-type="methods">
      <title>Methods</title>
      <p>We used ODE modeling to simulate cell dynamics.</p>
      <p>Parameters were estimated via maximum likelihood.</p>
    </sec>
    <sec sec-type="results">
      <title>Results</title>
      <p>The model achieved AUC=0.95 on the test set.</p>
    </sec>
    <sec sec-type="discussion">
      <title>Discussion</title>
      <p>Our approach outperforms the baseline by 2.3x.</p>
    </sec>
  </body>
</article>"""


SAMPLE_JATS_XML_TITLE_MATCH = """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <body>
    <sec>
      <title>Materials and Methods</title>
      <p>Experimental procedure described here.</p>
    </sec>
    <sec>
      <title>Results and Discussion</title>
      <p>Key findings reported here.</p>
    </sec>
  </body>
</article>"""


def test_extract_text_recursive_simple():
    """Plain text extraction from nested elements."""
    xml = "<root><p>Hello <b>world</b> test</p></root>"
    root = ET.fromstring(xml)
    text = extract_text_recursive(root)
    assert "Hello" in text
    assert "world" in text
    assert "test" in text


def test_extract_text_recursive_nested():
    """Handles deeply nested elements."""
    xml = "<root><div><span><em>deep</em> text</span></div></root>"
    root = ET.fromstring(xml)
    text = extract_text_recursive(root)
    assert "deep" in text
    assert "text" in text


def test_extract_text_recursive_empty():
    """Empty element returns empty string."""
    xml = "<root></root>"
    root = ET.fromstring(xml)
    text = extract_text_recursive(root)
    assert text == ""


def test_extract_section_text_by_sec_type():
    """Matches sections by sec-type attribute."""
    root = ET.fromstring(SAMPLE_JATS_XML)
    methods = extract_section_text(
        root,
        section_titles=["method"],
        sec_types=["methods"],
    )
    assert "ODE modeling" in methods
    assert "maximum likelihood" in methods


def test_extract_section_text_by_title():
    """Matches sections by title keyword."""
    root = ET.fromstring(SAMPLE_JATS_XML_TITLE_MATCH)
    methods = extract_section_text(
        root,
        section_titles=["method", "material"],
        sec_types=["methods"],
    )
    assert "Experimental procedure" in methods


def test_extract_section_text_no_match():
    """Returns empty string when no sections match."""
    root = ET.fromstring(SAMPLE_JATS_XML)
    text = extract_section_text(
        root,
        section_titles=["nonexistent"],
        sec_types=["nonexistent"],
    )
    assert text == ""


def test_extract_body_text():
    """Extracts all text from body element."""
    root = ET.fromstring(SAMPLE_JATS_XML)
    body_text = extract_body_text(root)
    assert "ODE modeling" in body_text
    assert "AUC=0.95" in body_text
    assert "outperforms" in body_text


def test_extract_body_text_no_body():
    """Returns empty string when no body element."""
    xml = "<article><front><title>Test</title></front></article>"
    root = ET.fromstring(xml)
    assert extract_body_text(root) == ""


def test_parse_jats_xml_extracts_sections():
    """Full XML parsing extracts all three sections."""
    result = parse_jats_xml(SAMPLE_JATS_XML)
    assert "ODE modeling" in result["methods_text"]
    assert "AUC=0.95" in result["results_text"]
    assert "outperforms" in result["discussion_text"]
    assert len(result["full_body_text"]) > 0


def test_parse_jats_xml_empty_xml():
    """Graceful handling of invalid XML."""
    result = parse_jats_xml("not valid xml <<<<")
    assert result["methods_text"] == ""
    assert result["results_text"] == ""
    assert result["discussion_text"] == ""
    assert result["full_body_text"] == ""


def test_parse_jats_xml_minimal():
    """Handles XML with no sections."""
    xml = '<?xml version="1.0"?><article><body><p>Just text.</p></body></article>'
    result = parse_jats_xml(xml)
    assert result["methods_text"] == ""
    assert result["results_text"] == ""
    assert result["discussion_text"] == ""
    assert "Just text" in result["full_body_text"]


def test_attach_fulltext_stats():
    """Coverage statistics are correct."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
        {"doi": "10.1/c", "title": "C"},
        {"title": "No DOI"},  # no doi
    ]
    fulltext_data = {
        "10.1/a": {"methods_text": "M", "results_text": "R", "discussion_text": "D"},
        "10.1/b": {"methods_text": "M2", "results_text": "", "discussion_text": ""},
    }
    papers, stats = attach_fulltext(papers, fulltext_data)
    assert stats["total"] == 4
    assert stats["with_fulltext"] == 2
    assert stats["without_fulltext"] == 1
    assert stats["without_doi"] == 1


def test_attach_fulltext_mutates_papers():
    """Papers are mutated in-place with fulltext dict."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
    ]
    fulltext_data = {
        "10.1/a": {"methods_text": "Methods here", "results_text": "Results", "discussion_text": "Disc"},
    }
    papers, _ = attach_fulltext(papers, fulltext_data)

    assert papers[0]["fulltext"]["methods_text"] == "Methods here"
    assert papers[1]["fulltext"] == {}


def test_attach_fulltext_doi_normalization():
    """DOI with https://doi.org/ prefix is normalized for matching."""
    papers = [{"doi": "https://doi.org/10.1/a", "title": "A"}]
    fulltext_data = {"10.1/a": {"methods_text": "M", "results_text": "", "discussion_text": ""}}
    papers, stats = attach_fulltext(papers, fulltext_data)
    assert stats["with_fulltext"] == 1
    assert papers[0]["fulltext"]["methods_text"] == "M"


@patch("papersift.fulltext.urllib.request.urlopen")
def test_fetch_all_with_mock(mock_urlopen):
    """Mocked HTTP calls for full pipeline."""
    # Mock PMCID lookup response
    pmcid_response = MagicMock()
    pmcid_response.__enter__ = MagicMock(return_value=pmcid_response)
    pmcid_response.__exit__ = MagicMock(return_value=False)
    pmcid_response.read.return_value = json.dumps({
        "resultList": {"result": [{"pmcid": "PMC123"}]}
    }).encode()
    pmcid_response.status = 200

    # Mock XML fetch response
    xml_response = MagicMock()
    xml_response.__enter__ = MagicMock(return_value=xml_response)
    xml_response.__exit__ = MagicMock(return_value=False)
    xml_response.read.return_value = SAMPLE_JATS_XML.encode()
    xml_response.status = 200

    # First call is PMCID lookup, second is XML fetch
    mock_urlopen.side_effect = [pmcid_response, xml_response]

    fetcher = FulltextFetcher()
    papers = [{"doi": "10.1/test", "title": "Test Paper"}]
    result = fetcher.fetch_all(papers)

    assert "10.1/test" in result
    assert "ODE modeling" in result["10.1/test"]["methods_text"]
