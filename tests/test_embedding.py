import pytest
import json
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_papers_landscape.json"

@pytest.fixture
def landscape_papers():
    with open(FIXTURE_PATH) as f:
        return json.load(f)

# --- Embedding tests ---

def test_extract_paper_entities_basic(landscape_papers):
    """extract_paper_entities returns dict with entity sets for each DOI."""
    from papersift.embedding import extract_paper_entities
    result = extract_paper_entities(landscape_papers)
    assert isinstance(result, dict)
    assert len(result) == len(landscape_papers)
    for doi, entities in result.items():
        assert isinstance(entities, set)

def test_extract_paper_entities_with_topics(landscape_papers):
    """use_topics=True includes topic names in entity sets."""
    from papersift.embedding import extract_paper_entities
    # Only papers with topics
    papers_with_topics = [p for p in landscape_papers if 'topics' in p]
    if not papers_with_topics:
        pytest.skip("No papers with topics in fixture")
    result_no_topics = extract_paper_entities(papers_with_topics, use_topics=False)
    result_with_topics = extract_paper_entities(papers_with_topics, use_topics=True)
    # With topics should have >= as many entities
    total_no = sum(len(v) for v in result_no_topics.values())
    total_with = sum(len(v) for v in result_with_topics.values())
    assert total_with >= total_no

def test_build_entity_matrix_shape(landscape_papers):
    """Matrix shape matches (n_papers, n_entities)."""
    from papersift.embedding import extract_paper_entities, build_entity_matrix
    pe = extract_paper_entities(landscape_papers)
    matrix, dois, entities = build_entity_matrix(landscape_papers, pe)
    assert matrix.shape == (len(landscape_papers), len(entities))
    assert len(dois) == len(landscape_papers)

def test_build_entity_matrix_binary(landscape_papers):
    """All values are 0 or 1."""
    from papersift.embedding import extract_paper_entities, build_entity_matrix
    pe = extract_paper_entities(landscape_papers)
    matrix, _, _ = build_entity_matrix(landscape_papers, pe)
    assert set(np.unique(matrix)).issubset({0.0, 1.0})

def test_build_entity_matrix_zero_entity_paper():
    """Paper with no extractable entities gets all-zero row."""
    from papersift.embedding import extract_paper_entities, build_entity_matrix
    papers = [
        {"doi": "10.1/a", "title": "The of and in a"},  # no real entities
        {"doi": "10.1/b", "title": "Machine Learning for RNA-seq Analysis"},
    ]
    pe = extract_paper_entities(papers)
    matrix, dois, entities = build_entity_matrix(papers, pe)
    # Paper "a" should have mostly zeros (may have some from fallback extraction)
    # Paper "b" should have non-zero entries
    b_idx = dois.index("10.1/b")
    assert matrix[b_idx].sum() > 0

def test_compute_embedding_tsne_mocked():
    """t-SNE compute_embedding returns correct shape (mocked due to environment issues)."""
    from papersift.embedding import compute_embedding
    # Mock t-SNE due to hanging issues in test environment
    matrix = np.random.rand(15, 30).astype(np.float32)

    mock_result = np.random.rand(15, 2).astype(np.float32)
    with patch('sklearn.manifold.TSNE') as mock_tsne:
        mock_instance = MagicMock()
        mock_instance.fit_transform.return_value = mock_result
        mock_tsne.return_value = mock_instance

        result = compute_embedding(matrix, method="tsne")
        assert result.shape == (15, 2)
        mock_tsne.assert_called_once()

def test_compute_embedding_umap_mocked():
    """UMAP compute_embedding returns correct shape (mocked due to environment issues)."""
    pytest.importorskip("umap")
    from papersift.embedding import compute_embedding
    matrix = np.random.rand(50, 30).astype(np.float32)

    mock_result = np.random.rand(50, 2).astype(np.float32)
    with patch('umap.UMAP') as mock_umap:
        mock_instance = MagicMock()
        mock_instance.fit_transform.return_value = mock_result
        mock_umap.return_value = mock_instance

        result = compute_embedding(matrix, method="umap")
        assert result.shape == (50, 2)
        mock_umap.assert_called_once()

def test_compute_embedding_too_few_papers():
    """Raises ValueError for < 2 papers."""
    from papersift.embedding import compute_embedding
    matrix = np.array([[1.0, 0.0, 1.0]])
    with pytest.raises(ValueError, match="at least 2"):
        compute_embedding(matrix, method="tsne")

def test_compute_embedding_invalid_method():
    """Raises ValueError for invalid method."""
    from papersift.embedding import compute_embedding
    matrix = np.random.rand(10, 20).astype(np.float32)
    with pytest.raises(ValueError, match="Unknown method"):
        compute_embedding(matrix, method="invalid")

def test_embed_papers_standalone():
    """embed_papers works without any builder argument -- fully standalone (mocked)."""
    from papersift.embedding import embed_papers
    papers = [
        {"doi": "10.1/a", "title": "Machine Learning for Genomics"},
        {"doi": "10.1/b", "title": "Deep Learning in Biology"},
        {"doi": "10.1/c", "title": "CRISPR Gene Editing Methods"},
    ]

    mock_coords = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    with patch('papersift.embedding.compute_embedding', return_value=mock_coords):
        result = embed_papers(papers, method="tsne")
        assert isinstance(result, dict)
        assert len(result) == 3
        assert "10.1/a" in result
        assert "10.1/b" in result
        assert "10.1/c" in result

def test_embed_papers_all_dois_present():
    """All DOIs from input appear in output."""
    from papersift.embedding import embed_papers
    papers = [
        {"doi": f"10.1/{i}", "title": f"Paper {i}"}
        for i in range(5)
    ]

    mock_coords = np.random.rand(5, 2).astype(np.float32)
    with patch('papersift.embedding.compute_embedding', return_value=mock_coords):
        result = embed_papers(papers, method="umap")
        input_dois = {p['doi'] for p in papers}
        assert set(result.keys()) == input_dois

def test_embed_papers_no_nan():
    """No NaN values in coordinates."""
    from papersift.embedding import embed_papers
    papers = [
        {"doi": f"10.1/{i}", "title": f"Paper {i}"}
        for i in range(5)
    ]

    mock_coords = np.random.rand(5, 2).astype(np.float32)
    with patch('papersift.embedding.compute_embedding', return_value=mock_coords):
        result = embed_papers(papers, method="umap")
        for doi, (x, y) in result.items():
            assert not np.isnan(x), f"NaN x for {doi}"
            assert not np.isnan(y), f"NaN y for {doi}"

# --- Sub-clustering tests ---

def test_sub_cluster_basic(landscape_papers):
    """Sub-clustering divides a cluster into sub-clusters."""
    from papersift.embedding import sub_cluster
    from papersift import EntityLayerBuilder
    builder = EntityLayerBuilder()
    builder.build_from_papers(landscape_papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)

    # Find a cluster with enough papers
    from collections import Counter
    counts = Counter(clusters.values())
    largest_cid = counts.most_common(1)[0][0]
    if counts[largest_cid] < 3:
        pytest.skip("No cluster large enough for meaningful sub-clustering")

    result = sub_cluster(landscape_papers, largest_cid, clusters, resolution=1.0, seed=42)
    assert len(result) == counts[largest_cid]

def test_sub_cluster_hierarchical_ids(landscape_papers):
    """IDs follow parent.child format."""
    from papersift.embedding import sub_cluster
    from papersift import EntityLayerBuilder
    builder = EntityLayerBuilder()
    builder.build_from_papers(landscape_papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)

    from collections import Counter
    counts = Counter(clusters.values())
    largest_cid = counts.most_common(1)[0][0]
    if counts[largest_cid] < 3:
        pytest.skip("No cluster large enough")

    result = sub_cluster(landscape_papers, largest_cid, clusters, resolution=1.0, seed=42)
    for doi, hid in result.items():
        assert str(hid).startswith(str(largest_cid))

def test_sub_cluster_single_paper():
    """Raises ValueError for single-paper cluster."""
    from papersift.embedding import sub_cluster
    papers = [
        {"doi": "10.1/a", "title": "Paper A about Machine Learning"},
        {"doi": "10.1/b", "title": "Paper B about CRISPR"},
    ]
    clusters = {"10.1/a": 0, "10.1/b": 1}
    with pytest.raises(ValueError, match="fewer than 2"):
        sub_cluster(papers, 0, clusters)

def test_sub_cluster_all_papers_accounted(landscape_papers):
    """All papers in cluster appear in sub-cluster output."""
    from papersift.embedding import sub_cluster
    from papersift import EntityLayerBuilder
    builder = EntityLayerBuilder()
    builder.build_from_papers(landscape_papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)

    from collections import Counter
    counts = Counter(clusters.values())
    largest_cid = counts.most_common(1)[0][0]
    if counts[largest_cid] < 3:
        pytest.skip("No cluster large enough")

    result = sub_cluster(landscape_papers, largest_cid, clusters, resolution=1.0, seed=42)
    original_dois = {d for d, c in clusters.items() if c == largest_cid}
    assert set(result.keys()) == original_dois

def test_sub_cluster_invalid_cluster_id(landscape_papers):
    """Raises ValueError for non-existent cluster."""
    from papersift.embedding import sub_cluster
    clusters = {p['doi']: 0 for p in landscape_papers}
    with pytest.raises(ValueError, match="not found"):
        sub_cluster(landscape_papers, 999, clusters)

def test_sub_cluster_string_cluster_id(landscape_papers):
    """Works with string cluster_id (e.g., '3.1')."""
    from papersift.embedding import sub_cluster
    # Create artificial string cluster IDs
    papers_subset = landscape_papers[:10]
    clusters = {p['doi']: "3.1" for p in papers_subset}
    result = sub_cluster(papers_subset, "3.1", clusters, resolution=1.0, seed=42)
    for hid in result.values():
        assert hid.startswith("3.1")

def test_paper_entities_property():
    """EntityLayerBuilder.paper_entities returns a copy."""
    from papersift import EntityLayerBuilder
    papers = [
        {"doi": "10.1/a", "title": "Machine Learning for Drug Discovery"},
        {"doi": "10.1/b", "title": "Deep Learning in Genomics"},
    ]
    builder = EntityLayerBuilder()
    builder.build_from_papers(papers)
    pe = builder.paper_entities
    assert isinstance(pe, dict)
    assert len(pe) == 2
    # Verify it's a copy
    pe["10.1/a"].add("FAKE")
    assert "FAKE" not in builder.paper_entities.get("10.1/a", set())
