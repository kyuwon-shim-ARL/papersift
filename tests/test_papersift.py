"""Tests for PaperSift plugin."""

import json
import pytest
import time
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Load papers from a fixture JSON file."""
    with open(FIXTURES_DIR / name) as f:
        data = json.load(f)
        return data['papers']


def test_entity_extraction():
    """Verify ImprovedEntityExtractor works with typical paper titles."""
    from papersift.entity_layer import ImprovedEntityExtractor

    extractor = ImprovedEntityExtractor()
    entities = extractor.extract_entities(
        "Deep learning for protein structure prediction using transformers",
        "machine_learning"
    )

    names = [e['name'].lower() for e in entities]
    assert 'deep learning' in names or 'transformer' in names or 'transformers' in names


def test_build_graph():
    """Verify graph building with fixture papers."""
    from papersift import EntityLayerBuilder

    papers = load_fixture("sample_papers.json")

    builder = EntityLayerBuilder()
    graph = builder.build_from_papers(papers)

    assert graph.vcount() == 20
    assert graph.ecount() > 0
    assert all(doi.startswith('https://doi.org/') for doi in graph.vs['doi'])


def test_leiden_deterministic():
    """Verify same seed produces same results (reproducibility)."""
    from papersift import EntityLayerBuilder

    papers = load_fixture("sample_papers.json")

    builder1 = EntityLayerBuilder()
    builder1.build_from_papers(papers)
    clusters1 = builder1.run_leiden(seed=42)

    builder2 = EntityLayerBuilder()
    builder2.build_from_papers(papers)
    clusters2 = builder2.run_leiden(seed=42)

    assert clusters1 == clusters2


def test_full_dataset():
    """Test clustering on full fixture dataset (20 papers)."""
    from papersift import EntityLayerBuilder

    papers = load_fixture("sample_papers.json")
    assert len(papers) == 20

    builder = EntityLayerBuilder()
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(seed=42)

    assert len(clusters) == 20
    num_clusters = len(set(clusters.values()))
    assert 2 <= num_clusters <= 20


def test_performance():
    """Verify clustering completes in under 5 seconds for fixture papers."""
    from papersift import EntityLayerBuilder

    papers = load_fixture("sample_papers.json")

    start = time.time()
    builder = EntityLayerBuilder()
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(seed=0)
    elapsed = time.time() - start

    assert elapsed < 5, f"Too slow: {elapsed:.1f}s"


def test_validator_no_citations():
    """Verify validator handles papers without citation data gracefully."""
    from papersift import EntityLayerBuilder, ClusterValidator

    # Papers without referenced_works field
    papers = [
        {'doi': 'https://doi.org/10.1/a', 'title': 'Deep learning methods'},
        {'doi': 'https://doi.org/10.1/b', 'title': 'Machine learning tools'},
    ]

    builder = EntityLayerBuilder()
    builder.build_from_papers(papers)
    clusters = builder.run_leiden()

    validator = ClusterValidator(clusters, papers)
    assert not validator.has_citation_data()

    report = validator.generate_report()
    assert 'insufficient_data' in report.confidence_summary


def test_validator_with_citations():
    """Verify validator works correctly with citation data."""
    from papersift import EntityLayerBuilder, ClusterValidator

    papers = load_fixture("sample_papers_with_refs.json")

    builder = EntityLayerBuilder()
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(seed=42)

    validator = ClusterValidator(clusters, papers)
    assert validator.has_citation_data()

    report = validator.generate_report()
    assert report.num_papers == 10
    assert report.num_entity_clusters >= 1
    assert report.num_citation_clusters >= 1
    assert -1.0 <= report.ari <= 1.0
    assert 0.0 <= report.nmi <= 1.0
    assert len(report.confidence_scores) == 10
    assert 'high' in report.confidence_summary


def test_use_topics():
    """Verify topics mode works with enriched data."""
    from papersift import EntityLayerBuilder

    papers = load_fixture("sample_papers_with_topics.json")

    # Build with use_topics=False
    builder_no_topics = EntityLayerBuilder(use_topics=False)
    builder_no_topics.build_from_papers(papers)
    clusters_no_topics = builder_no_topics.run_leiden(seed=42)

    # Build with use_topics=True
    builder_with_topics = EntityLayerBuilder(use_topics=True)
    builder_with_topics.build_from_papers(papers)
    clusters_with_topics = builder_with_topics.run_leiden(seed=42)

    # With topics should produce more edges (richer graph)
    assert builder_with_topics.graph.ecount() >= builder_no_topics.graph.ecount()

    # Both should cluster all papers
    assert len(clusters_no_topics) == 10
    assert len(clusters_with_topics) == 10
