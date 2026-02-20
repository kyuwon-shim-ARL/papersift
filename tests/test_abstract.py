import json
from unittest.mock import MagicMock, patch
import pytest
from papersift.abstract import AbstractFetcher, attach_abstracts


def test_reconstruct_abstract():
    """OpenAlex inverted index reconstruction."""
    idx = {"Hello": [0], "world": [1], "of": [2], "science": [3]}
    result = AbstractFetcher._reconstruct_abstract(idx)
    assert result == "Hello world of science"

    # Empty input
    assert AbstractFetcher._reconstruct_abstract({}) == ""
    assert AbstractFetcher._reconstruct_abstract(None) == ""


def test_attach_abstracts():
    """Abstract attachment to paper dicts."""
    papers = [
        {"doi": "10.1234/a", "title": "Paper A"},
        {"doi": "10.1234/b", "title": "Paper B"},
    ]
    abstracts = {"10.1234/a": "Abstract for A"}

    result, stats = attach_abstracts(papers, abstracts)
    assert result[0]["abstract"] == "Abstract for A"
    assert result[1]["abstract"] == ""
    assert stats["with_abstract"] == 1
    assert stats["without_abstract"] == 1


def test_attach_abstracts_stats_include_without_doi():
    """Verify without_doi field in stats."""
    papers = [
        {"doi": "10.1234/a", "title": "Paper A"},
        {"title": "Paper B no DOI"},  # no doi field
        {"doi": "", "title": "Paper C empty DOI"},  # empty doi
    ]
    abstracts = {"10.1234/a": "Abstract A"}

    _, stats = attach_abstracts(papers, abstracts)
    assert stats["without_doi"] == 2  # both empty and missing
    assert stats["total"] == 3
    assert stats["with_abstract"] == 1


def test_stats_calculation():
    """Coverage stats accuracy."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
        {"doi": "10.1/c", "title": "C"},
    ]
    abstracts = {"10.1/a": "abs A", "10.1/b": "abs B"}

    _, stats = attach_abstracts(papers, abstracts)
    assert stats["total"] == 3
    assert stats["with_abstract"] == 2
    assert stats["without_abstract"] == 1
    assert stats["without_doi"] == 0
    assert stats["sources"] == {}  # not implemented per-DOI


def test_empty_papers_list():
    """Edge case: empty input."""
    papers = []
    abstracts = {}
    result, stats = attach_abstracts(papers, abstracts)
    assert result == []
    assert stats["total"] == 0


def test_papers_without_dois():
    """Edge case: papers missing DOI field."""
    papers = [
        {"title": "No DOI paper 1"},
        {"title": "No DOI paper 2"},
    ]
    abstracts = {"10.1/something": "abstract"}

    result, stats = attach_abstracts(papers, abstracts)
    assert all(p["abstract"] == "" for p in result)
    assert stats["without_doi"] == 2


def test_s2_null_entry_handling():
    """S2 batch returns null for unfound DOIs — mock test."""
    fetcher = AbstractFetcher()

    # Mock the S2 API response with null entries
    mock_response_data = [
        None,  # DOI not found
        {"abstract": "Found abstract", "externalIds": {"DOI": "10.1/b"}},
        None,  # DOI not found
    ]

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = fetcher._fetch_s2_batch(["10.1/a", "10.1/b", "10.1/c"])

    assert "10.1/b" in result
    assert result["10.1/b"] == "Found abstract"
    assert "10.1/a" not in result
    assert "10.1/c" not in result
