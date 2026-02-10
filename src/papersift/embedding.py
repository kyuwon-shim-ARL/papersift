"""Embedding and sub-clustering utilities for PaperSift.

Standalone functions that convert papers into 2D embeddings via entity-presence
matrices, and support hierarchical sub-clustering of existing clusters.

Key functions:
- extract_paper_entities: Extract entity sets per paper
- build_entity_matrix: Binary entity-presence matrix
- compute_embedding: UMAP or t-SNE dimensionality reduction
- embed_papers: High-level papers-in, coordinates-out
- sub_cluster: Hierarchical sub-clustering within an existing cluster
"""

import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from papersift.entity_layer import EntityLayerBuilder


def extract_paper_entities(
    papers: List[Dict[str, Any]],
    use_topics: bool = False,
) -> Dict[str, set]:
    """Extract entity sets for each paper using a temporary EntityLayerBuilder.

    Args:
        papers: List of paper dicts with 'doi' and 'title' fields.
        use_topics: If True, also use OpenAlex topics as entities.

    Returns:
        Mapping of DOI to set of lowercase entity names.
    """
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)
    return builder.paper_entities


def build_entity_matrix(
    papers: List[Dict[str, Any]],
    paper_entities: Dict[str, set],
) -> Tuple[np.ndarray, List[str], List[str]]:
    """Build a binary entity-presence matrix.

    Rows correspond to papers (ordered by DOI appearance in *papers*),
    columns correspond to unique entities (sorted alphabetically).
    Papers with no entities receive an all-zero row.

    Args:
        papers: List of paper dicts (used for DOI ordering).
        paper_entities: Mapping of DOI to entity set (from extract_paper_entities).

    Returns:
        Tuple of (matrix, doi_list, entity_list) where matrix has shape
        (n_papers, n_entities) and dtype float32.
    """
    doi_list = [p["doi"] for p in papers]

    # Collect all unique entities across all papers
    all_entities: Set[str] = set()
    for entities in paper_entities.values():
        all_entities.update(entities)
    entity_list = sorted(all_entities)

    entity_index = {ent: i for i, ent in enumerate(entity_list)}
    n_papers = len(doi_list)
    n_entities = len(entity_list)

    matrix = np.zeros((n_papers, n_entities), dtype=np.float32)
    for row, doi in enumerate(doi_list):
        for ent in paper_entities.get(doi, set()):
            col = entity_index.get(ent)
            if col is not None:
                matrix[row, col] = 1.0

    return matrix, doi_list, entity_list


def compute_embedding(
    matrix: np.ndarray,
    method: str = "umap",
    n_components: int = 2,
    random_state: int = 42,
    **kwargs: Any,
) -> np.ndarray:
    """Reduce an entity-presence matrix to a low-dimensional embedding.

    Args:
        matrix: 2-D array of shape (n_papers, n_entities).
        method: ``"umap"`` or ``"tsne"``.
        n_components: Target dimensionality (default 2).
        random_state: Seed for reproducibility.
        **kwargs: Forwarded to the underlying reducer constructor.

    Returns:
        ndarray of shape (n_papers, n_components).

    Raises:
        ValueError: If matrix has fewer than 2 rows.
        ImportError: If method is ``"umap"`` and umap-learn is not installed.
        ValueError: If method is not ``"umap"`` or ``"tsne"``.
    """
    if matrix.shape[0] < 2:
        raise ValueError(
            f"compute_embedding requires at least 2 rows, got {matrix.shape[0]}"
        )

    if method == "umap":
        try:
            import umap  # noqa: F811
        except ImportError:
            raise ImportError(
                "UMAP is required for method='umap'. "
                "Install it with: pip install umap-learn"
            )
        reducer = umap.UMAP(
            n_components=n_components,
            random_state=random_state,
            **kwargs,
        )
        return reducer.fit_transform(matrix)

    elif method == "tsne":
        from sklearn.manifold import TSNE

        reducer = TSNE(
            n_components=n_components,
            random_state=random_state,
            **kwargs,
        )
        return reducer.fit_transform(matrix)

    else:
        raise ValueError(f"Unknown method '{method}'. Use 'umap' or 'tsne'.")


def embed_papers(
    papers: List[Dict[str, Any]],
    method: str = "umap",
    use_topics: bool = False,
    random_state: int = 42,
    **kwargs: Any,
) -> Dict[str, Tuple[float, float]]:
    """High-level: papers in, {doi: (x, y)} out.

    Internally chains extract_paper_entities -> build_entity_matrix ->
    compute_embedding, then maps coordinates back to DOIs.

    Papers whose entity set is empty are placed at the centroid of the
    embedding with small random jitter so they remain visible but do not
    distort the layout.

    Args:
        papers: List of paper dicts with 'doi' and 'title' fields.
        method: ``"umap"`` or ``"tsne"``.
        use_topics: If True, also use OpenAlex topics as entities.
        random_state: Seed for reproducibility.
        **kwargs: Forwarded to compute_embedding.

    Returns:
        Mapping of DOI to (x, y) coordinate tuple.
    """
    paper_entities = extract_paper_entities(papers, use_topics=use_topics)
    matrix, doi_list, entity_list = build_entity_matrix(papers, paper_entities)

    coords = compute_embedding(
        matrix,
        method=method,
        random_state=random_state,
        **kwargs,
    )

    # Identify papers with zero entities (all-zero rows)
    row_sums = matrix.sum(axis=1)
    zero_mask = row_sums == 0

    if zero_mask.any() and not zero_mask.all():
        # Compute centroid from non-zero papers
        centroid = coords[~zero_mask].mean(axis=0)
        rng = np.random.RandomState(random_state)
        # Small jitter: 1% of the coordinate range per axis
        for ax in range(coords.shape[1]):
            span = np.ptp(coords[~zero_mask, ax])
            jitter_scale = max(span * 0.01, 1e-6)
            jitter = rng.normal(0, jitter_scale, size=int(zero_mask.sum()))
            coords[zero_mask, ax] = centroid[ax] + jitter

    result: Dict[str, Tuple[float, float]] = {}
    for i, doi in enumerate(doi_list):
        result[doi] = (float(coords[i, 0]), float(coords[i, 1]))

    return result


def sub_cluster(
    papers: List[Dict[str, Any]],
    cluster_id: Union[int, str],
    clusters: Dict[str, Union[int, str]],
    resolution: float = 1.0,
    seed: Optional[int] = None,
    use_topics: bool = False,
) -> Dict[str, str]:
    """Hierarchical sub-clustering within an existing cluster.

    Filters papers to those belonging to *cluster_id*, builds a new entity
    graph from the subset, runs Leiden, and returns membership with
    hierarchical IDs of the form ``"{cluster_id}.{sub_id}"``.

    If only one paper belongs to the cluster, or Leiden finds only a single
    sub-cluster, the original cluster_id is returned unchanged (as a string).

    Args:
        papers: Full list of paper dicts.
        cluster_id: The cluster to sub-divide.
        clusters: Existing DOI -> cluster_id mapping.
        resolution: Leiden resolution for the sub-clustering.
        seed: Random seed for Leiden.
        use_topics: If True, also use OpenAlex topics as entities.

    Returns:
        Mapping of DOI -> hierarchical cluster ID string.

    Raises:
        ValueError: If *cluster_id* is not found in *clusters*, or if
            fewer than 2 papers belong to the cluster.
    """
    # Coerce cluster_id for comparison (clusters values may be int or str)
    member_dois = {
        doi
        for doi, cid in clusters.items()
        if str(cid) == str(cluster_id)
    }

    if not member_dois:
        raise ValueError(
            f"cluster_id '{cluster_id}' not found in clusters"
        )

    if len(member_dois) < 2:
        raise ValueError(
            f"cluster_id '{cluster_id}' has fewer than 2 papers "
            f"({len(member_dois)} found); cannot sub-cluster"
        )

    # Filter papers to those in the cluster
    subset = [p for p in papers if p["doi"] in member_dois]

    # Build a fresh entity graph and cluster the subset
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(subset)
    sub_clusters = builder.run_leiden(resolution=resolution, seed=seed)

    # Check if Leiden produced only a single sub-cluster
    unique_subs = set(sub_clusters.values())
    if len(unique_subs) <= 1:
        return {doi: str(cluster_id) for doi in member_dois}

    # Map to hierarchical IDs
    return {
        doi: f"{cluster_id}.{sub_id}"
        for doi, sub_id in sub_clusters.items()
    }
