"""Tests for topics format compatibility."""
from papersift import EntityLayerBuilder


def test_string_topics():
    """Flat string topics should work with use_topics=True."""
    papers = [
        {"doi": "10.test/001", "title": "Paper A", "topics": ["Genomics", "Machine Learning"]},
        {"doi": "10.test/002", "title": "Paper B", "topics": ["Genomics", "Proteomics"]},
    ]
    builder = EntityLayerBuilder(use_topics=True)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)
    assert len(clusters) == 2


def test_dict_topics():
    """Rich dict topics should work with use_topics=True."""
    papers = [
        {"doi": "10.test/001", "title": "Paper A", "topics": [
            {"display_name": "Genomics", "subfield": {"display_name": "Molecular Biology"}},
        ]},
        {"doi": "10.test/002", "title": "Paper B", "topics": [
            {"display_name": "Genomics", "subfield": {"display_name": "Bioinformatics"}},
        ]},
    ]
    builder = EntityLayerBuilder(use_topics=True)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)
    assert len(clusters) == 2


def test_mixed_topics():
    """Mixed string and dict topics in same paper list should work."""
    papers = [
        {"doi": "10.test/001", "title": "Paper A", "topics": ["Genomics"]},
        {"doi": "10.test/002", "title": "Paper B", "topics": [
            {"display_name": "Genomics", "subfield": {"display_name": "Molecular Biology"}},
        ]},
    ]
    builder = EntityLayerBuilder(use_topics=True)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)
    assert len(clusters) == 2
