import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from papersift.research import ResearchPipeline, PreparedData, ResearchOutput


# Helper: create minimal paper list
def _make_papers(n=5):
    return [
        {
            "doi": f"10.1234/paper{i}",
            "title": f"Virtual Cell Modeling Study {i} with ODE simulation",
            "year": 2020 + i,
        }
        for i in range(n)
    ]


def _make_prepared(papers=None):
    """Create a minimal PreparedData for testing finalize."""
    if papers is None:
        papers = _make_papers(3)
    return PreparedData(
        papers=papers,
        clusters={p["doi"]: i % 2 for i, p in enumerate(papers)},
        cluster_summaries=[
            {"cluster_id": 0, "size": 2, "top_entities": ["ode", "simulation", "virtual cell", "modeling", "biology"], "dois": [p["doi"] for p in papers if papers.index(p) % 2 == 0]},
            {"cluster_id": 1, "size": 1, "top_entities": ["ode", "cell cycle", "agent-based", "dynamics", "disease"], "dois": [p["doi"] for p in papers if papers.index(p) % 2 == 1]},
        ],
        paper_entities={p["doi"]: ["ode", "simulation"] for p in papers},
        prompts=["prompt1"],
        batch_doi_lists=[[p["doi"] for p in papers]],
        stats={"total": len(papers), "with_abstract": 0, "without_abstract": len(papers), "without_doi": 0, "sources": {}},
        metadata={"resolution": 1.0, "seed": 42, "use_topics": False},
    )


@patch("papersift.research.AbstractFetcher")
def test_prepare_produces_prompts(mock_fetcher_cls):
    """PreparedData contains non-empty prompts list."""
    # Mock AbstractFetcher to not make network calls
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_all.return_value = {}
    mock_fetcher_cls.return_value = mock_fetcher

    papers = _make_papers(5)
    pipeline = ResearchPipeline()
    prepared = pipeline.prepare(papers)

    assert len(prepared.prompts) > 0
    assert len(prepared.batch_doi_lists) > 0
    assert len(prepared.clusters) == 5
    assert len(prepared.paper_entities) > 0


@patch("papersift.research.AbstractFetcher")
def test_prepare_with_clusters_from(mock_fetcher_cls, tmp_path):
    """Pipeline loads pre-computed clusters."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_all.return_value = {}
    mock_fetcher_cls.return_value = mock_fetcher

    papers = _make_papers(3)
    # Pre-compute clusters file
    clusters = {p["doi"]: i for i, p in enumerate(papers)}
    clusters_file = tmp_path / "clusters.json"
    clusters_file.write_text(json.dumps(clusters))

    pipeline = ResearchPipeline()
    prepared = pipeline.prepare(papers, clusters_from=clusters_file)

    # Should use the provided clusters
    assert prepared.clusters == {p["doi"]: i for i, p in enumerate(papers)}


def test_finalize_with_llm_results():
    """Merges programmatic LLM results correctly."""
    papers = _make_papers(3)
    prepared = _make_prepared(papers)

    llm_results = [
        [
            {"doi": papers[0]["doi"], "problem": "P0", "method": "M0", "finding": "F0"},
            {"doi": papers[1]["doi"], "problem": "P1", "method": "M1", "finding": "F1"},
            {"doi": papers[2]["doi"], "problem": "P2", "method": "M2", "finding": "F2"},
        ]
    ]

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared, llm_results=llm_results)

    assert len(output.papers) == 3
    assert output.papers[0]["problem"] == "P0"
    assert output.papers[1]["method"] == "M1"
    assert output.papers[2]["finding"] == "F2"


def test_finalize_with_extractions_from(tmp_path):
    """Loads and merges from file."""
    papers = _make_papers(2)
    prepared = _make_prepared(papers)

    extractions = [
        {"doi": papers[0]["doi"], "problem": "P0", "method": "M0", "finding": "F0"},
        {"doi": papers[1]["doi"], "problem": "P1", "method": "M1", "finding": "F1"},
    ]
    ext_file = tmp_path / "extractions.json"
    ext_file.write_text(json.dumps(extractions))

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared, extractions_from=ext_file)

    assert output.papers[0]["problem"] == "P0"
    assert output.papers[1]["finding"] == "F1"


def test_finalize_without_extractions():
    """Produces valid output with empty extraction fields."""
    papers = _make_papers(2)
    prepared = _make_prepared(papers)

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared)  # no llm_results, no extractions_from

    assert len(output.papers) == 2
    # Fields should be empty strings
    for p in output.papers:
        assert p["problem"] == ""
        assert p["method"] == ""
        assert p["finding"] == ""


def test_research_output_schema():
    """Validate enriched paper dict structure."""
    papers = _make_papers(2)
    prepared = _make_prepared(papers)

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared)

    required_keys = {"doi", "title", "year", "cluster_id", "cluster_label", "abstract", "problem", "method", "finding", "entities"}
    for paper in output.papers:
        assert required_keys.issubset(paper.keys()), f"Missing keys: {required_keys - paper.keys()}"
        assert isinstance(paper["cluster_id"], str) or paper["cluster_id"] is None
        assert isinstance(paper["entities"], list)


def test_for_research_md_self_contained_sections(tmp_path):
    """Each cluster section is independently parseable."""
    papers = _make_papers(4)
    prepared = _make_prepared(papers)

    llm_results = [[
        {"doi": p["doi"], "problem": f"Problem {i}", "method": f"Method {i}", "finding": f"Finding {i}"}
        for i, p in enumerate(papers)
    ]]

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared, llm_results=llm_results)
    pipeline.export(output, tmp_path, prepared=prepared)

    md_path = tmp_path / "for_research.md"
    assert md_path.exists()

    content = md_path.read_text()
    # Should have cluster sections
    assert "## Cluster" in content
    # Should have summary sections with papers
    assert "### Summary" in content
    assert "### Papers" in content or "Papers Without Abstracts" in content


def test_pipeline_end_to_end_mock(tmp_path):
    """Full prepare+finalize with mocked abstracts and fake LLM results."""
    papers = _make_papers(3)

    with patch("papersift.research.AbstractFetcher") as mock_cls:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_all.return_value = {
            papers[0]["doi"]: "Abstract for paper 0",
        }
        mock_cls.return_value = mock_fetcher

        pipeline = ResearchPipeline()
        prepared = pipeline.prepare(papers)

    # Fake LLM results
    llm_results = [[
        {"doi": p["doi"], "problem": f"P{i}", "method": f"M{i}", "finding": f"F{i}"}
        for i, p in enumerate(papers)
    ]]

    output = pipeline.finalize(prepared, llm_results=llm_results)
    assert output.stats["paper_count"] == 3
    assert output.stats["extraction_coverage"] > 0


def test_export_creates_files(tmp_path):
    """Output directory contains expected files."""
    papers = _make_papers(2)
    prepared = _make_prepared(papers)

    pipeline = ResearchPipeline()
    output = pipeline.finalize(prepared)

    out_dir = tmp_path / "output"
    pipeline.export(output, out_dir, prepared=prepared)

    assert (out_dir / "enriched_papers.json").exists()
    assert (out_dir / "for_research.md").exists()
    assert (out_dir / "extraction_prompts.json").exists()

    # Verify enriched_papers.json structure
    with open(out_dir / "enriched_papers.json") as f:
        data = json.load(f)
    assert "papers" in data
    assert "stats" in data
    assert "metadata" in data
