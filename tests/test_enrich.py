"""Tests for OpenAlex enrichment module (mocked, no network required)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Skip entire module if pyalex not installed
pyalex = pytest.importorskip("pyalex")

from papersift.enrich import OpenAlexEnricher

FIXTURES = Path(__file__).parent / "fixtures"


def _make_work(doi, referenced_works=None, topics=None, abstract_inverted_index=None):
    """Create a mock OpenAlex work dict."""
    work = {
        "id": f"https://openalex.org/W{abs(hash(doi)) % 10**10}",
        "doi": f"https://doi.org/{doi}",
        "referenced_works": referenced_works or [],
        "topics": topics or [],
    }
    if abstract_inverted_index is not None:
        work["abstract_inverted_index"] = abstract_inverted_index
    return work


def _make_resolved_work(openalex_id, doi):
    """Create a mock resolved work from batch ID lookup."""
    return {"id": openalex_id, "doi": f"https://doi.org/{doi}"}


class TestOpenAlexEnricher:

    def test_enrich_adds_referenced_works(self):
        """Enriched papers should have referenced_works as DOI list."""
        papers = [
            {"doi": "10.1234/a", "title": "Paper A"},
            {"doi": "10.1234/b", "title": "Paper B"},
        ]

        mock_work_a = _make_work(
            "10.1234/a",
            referenced_works=[
                "https://openalex.org/W111",
                "https://openalex.org/W222",
            ],
        )
        mock_work_b = _make_work("10.1234/b", referenced_works=[])

        # Mock Works()[doi_url] calls
        with patch("papersift.enrich.Works") as MockWorks:
            mock_instance = MagicMock()
            MockWorks.return_value = mock_instance

            def getitem(self_or_key, key=None):
                # Handle both bound/unbound calls
                actual_key = key if key is not None else self_or_key
                if "10.1234/a" in actual_key:
                    return mock_work_a
                return mock_work_b

            mock_instance.__getitem__ = MagicMock(side_effect=lambda k: getitem(k))

            # Mock batch resolution for _resolve_openalex_ids_to_dois
            mock_filter = MagicMock()
            mock_instance.filter.return_value = mock_filter
            mock_filter.get.return_value = [
                _make_resolved_work("https://openalex.org/W111", "10.5678/x"),
                _make_resolved_work("https://openalex.org/W222", "10.5678/y"),
            ]

            enricher = OpenAlexEnricher(email="test@example.com")
            enricher.DELAY = 0  # No delay in tests
            result = enricher.enrich_papers(papers, fields=["referenced_works"], progress=False)

        assert result[0]["referenced_works"] == ["10.5678/x", "10.5678/y"]
        assert result[1]["referenced_works"] == []

    def test_enrich_resolves_openalex_ids(self):
        """OpenAlex IDs should be resolved to DOIs via batch API."""
        with patch("papersift.enrich.Works") as MockWorks:
            mock_instance = MagicMock()
            MockWorks.return_value = mock_instance

            mock_filter = MagicMock()
            mock_instance.filter.return_value = mock_filter
            mock_filter.get.return_value = [
                _make_resolved_work("https://openalex.org/W111", "10.1000/alpha"),
                _make_resolved_work("https://openalex.org/W222", "10.1000/beta"),
            ]

            enricher = OpenAlexEnricher(email="test@example.com")
            enricher.DELAY = 0

            ids = ["https://openalex.org/W111", "https://openalex.org/W222"]
            dois = enricher._resolve_openalex_ids_to_dois(ids)

        assert dois == ["10.1000/alpha", "10.1000/beta"]

    def test_enrich_skips_missing_doi(self):
        """Papers without DOIs should be skipped gracefully."""
        papers = [
            {"title": "No DOI paper"},
            {"doi": "10.1234/c", "title": "Has DOI"},
        ]

        mock_work = _make_work("10.1234/c", referenced_works=[])

        with patch("papersift.enrich.Works") as MockWorks:
            mock_instance = MagicMock()
            MockWorks.return_value = mock_instance
            mock_instance.__getitem__ = lambda self, x: mock_work

            enricher = OpenAlexEnricher(email="test@example.com")
            enricher.DELAY = 0
            result = enricher.enrich_papers(papers, fields=["referenced_works"], progress=False)

        # First paper should not have referenced_works
        assert "referenced_works" not in result[0]
        # Second paper should
        assert result[1]["referenced_works"] == []

    def test_enrich_adds_openalex_id(self):
        """openalex_id field should be populated."""
        papers = [{"doi": "10.1234/d", "title": "Paper D"}]

        mock_work = _make_work("10.1234/d")

        with patch("papersift.enrich.Works") as MockWorks:
            mock_instance = MagicMock()
            MockWorks.return_value = mock_instance
            mock_instance.__getitem__ = lambda self, x: mock_work

            enricher = OpenAlexEnricher(email="test@example.com")
            enricher.DELAY = 0
            result = enricher.enrich_papers(papers, fields=["openalex_id"], progress=False)

        assert result[0]["openalex_id"].startswith("https://openalex.org/W")

    def test_reconstruct_abstract(self):
        """Abstract should be reconstructed from inverted index."""
        inv_index = {
            "Machine": [0],
            "learning": [1],
            "is": [2],
            "powerful": [3],
        }
        abstract = OpenAlexEnricher._reconstruct_abstract(
            {"abstract_inverted_index": inv_index}
        )
        assert abstract == "Machine learning is powerful"

    def test_enriched_papers_enable_validation(self):
        """Papers enriched with referenced_works should allow citation validation."""
        from papersift import EntityLayerBuilder, ClusterValidator

        # Use fixture with refs
        with open(FIXTURES / "sample_papers_with_refs.json") as f:
            data = json.load(f)
        papers = data.get("papers", data)

        builder = EntityLayerBuilder()
        builder.build_from_papers(papers)
        clusters = builder.run_leiden()
        validator = ClusterValidator(clusters, papers)

        assert validator.has_citation_data()
        report = validator.generate_report()
        assert "insufficient_data" not in report.confidence_summary
