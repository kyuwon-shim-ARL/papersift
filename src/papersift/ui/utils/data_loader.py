"""Load papers and prepare data for UI components."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from papersift import EntityLayerBuilder


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if needed."""
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len] + '...'


def slim_papers(papers: List[Dict[str, Any]], keep_topics: bool = False) -> List[Dict[str, Any]]:
    """
    Create a lighter version of papers for Store (reduces payload size).

    Args:
        papers: full paper list
        keep_topics: if True, preserve 'topics' field for re-clustering with use_topics
    """
    result = []
    for p in papers:
        slim = {
            'doi': p['doi'],
            'title': p.get('title', ''),
            'year': p.get('year', ''),
        }
        if keep_topics and 'topics' in p:
            slim['topics'] = p['topics']
        result.append(slim)
    return result


def load_papers(path: str) -> List[Dict[str, Any]]:
    """Load papers from JSON file with validation."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Papers file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in papers file: {e}")

    raw_papers = data.get('papers', data)

    # Validate required fields
    papers = []
    skipped = 0
    for p in raw_papers:
        if not p.get('doi'):
            skipped += 1
            continue
        papers.append(p)

    if skipped > 0:
        print(f"Warning: Skipped {skipped} papers without DOI")

    if not papers:
        raise ValueError("No valid papers found (all missing DOI)")

    return papers


def cluster_papers(
    papers: List[Dict[str, Any]],
    resolution: float = 1.0,
    seed: int = 42,
    use_topics: bool = False,
) -> Tuple[Dict[str, int], EntityLayerBuilder]:
    """Run Leiden clustering on papers with optional topic-enhanced entities."""
    builder = EntityLayerBuilder(use_topics=use_topics)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=resolution, seed=seed)
    return clusters, builder


def generate_cluster_colors(cluster_ids) -> Dict[Any, str]:
    """
    Generate distinct colors for clusters.

    Uses a categorical color palette that's colorblind-friendly.
    Accepts any hashable cluster IDs (int, str, or mixed).

    Args:
        cluster_ids: set of unique cluster IDs (e.g., {0, 1, 2} or {"3.1", "3.2"})
                     Also accepts int for backward compatibility.
    """
    # Backward compatibility: if int passed, treat as range(n)
    if isinstance(cluster_ids, int):
        cluster_ids = set(range(cluster_ids))

    palette = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
        '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5'
    ]
    colors = {}
    for i, cid in enumerate(sorted(cluster_ids, key=str)):
        colors[cid] = palette[i % len(palette)]
    return colors


def papers_to_cytoscape_elements(
    papers: List[Dict[str, Any]],
    clusters: Dict[str, int],
    builder: EntityLayerBuilder
) -> List[Dict[str, Any]]:
    """
    Convert papers and clusters to Cytoscape elements.

    Returns:
        List of node and edge elements for dash-cytoscape
    """
    colors = generate_cluster_colors(set(clusters.values()))

    elements = []

    # Create nodes
    doi_to_paper = {p['doi']: p for p in papers}
    for doi, cluster_id in clusters.items():
        paper = doi_to_paper.get(doi, {})
        elements.append({
            'data': {
                'id': doi,
                'label': paper.get('title', doi)[:50] + '...',
                'title': paper.get('title', ''),
                'cluster': cluster_id,
                'color': colors[cluster_id],
                'year': paper.get('year', ''),
                'abstract': _truncate(paper.get('abstract', ''), 200)
            }
        })

    # Create edges from entity graph
    graph = builder.graph
    for edge in graph.es:
        source_doi = graph.vs[edge.source]['doi']
        target_doi = graph.vs[edge.target]['doi']
        weight = edge['weight']
        # Only include edges with weight >= 2 to reduce visual clutter
        if weight >= 2:
            elements.append({
                'data': {
                    'source': source_doi,
                    'target': target_doi,
                    'weight': weight
                }
            })

    return elements


def papers_to_table_data(
    papers: List[Dict[str, Any]],
    clusters: Dict[str, int]
) -> List[Dict[str, Any]]:
    """
    Convert papers to AG Grid row data.

    Returns:
        List of row dictionaries for dash-ag-grid
    """
    colors = generate_cluster_colors(set(clusters.values()))

    rows = []
    for paper in papers:
        doi = paper['doi']
        cluster_id = clusters.get(doi, -1)
        rows.append({
            'doi': doi,
            'title': paper.get('title', ''),
            'year': paper.get('year', ''),
            'cluster': cluster_id,
            'cluster_color': colors.get(cluster_id, '#cccccc'),
            'abstract': _truncate(paper.get('abstract', ''), 100)
        })

    return rows


def compute_paper_embedding(
    papers: list,
    method: str = "tsne",
    use_topics: bool = False,
) -> Dict[str, list]:
    """
    Compute embedding standalone, return JSON-serializable {doi: [x, y]}.
    """
    from papersift.embedding import embed_papers
    result = embed_papers(papers, method=method, use_topics=use_topics)
    return {doi: list(coords) for doi, coords in result.items()}
