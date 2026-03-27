"""PaperSift HTML view generators — sub-package."""

import json
import os
import shutil
from collections import defaultdict
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import generate_labels
from .views_cluster import generate_overview, generate_drilldown
from .views_bridge import generate_bridges, generate_ranking
from .views_temporal import generate_timeline
from .views_summary import generate_decision_summary, generate_detail

__all__ = [
    'generate_labels', 'generate_overview', 'generate_drilldown',
    'generate_bridges', 'generate_ranking', 'generate_timeline',
    'generate_detail', 'generate_decision_summary', 'generate_all_views',
]


def generate_all_views(results_dir: str, output_dir: Optional[str] = None) -> List[str]:
    """Read all JSON files from results_dir and generate all HTML views.

    Args:
        results_dir: path to directory containing clusters.json, papers.json,
                     gaps.json, temporal.json
        output_dir: destination directory (default: {results_dir}/views/)

    Returns:
        list of absolute paths to generated HTML files
    """
    results_path = Path(results_dir)
    out_path = Path(output_dir) if output_dir else results_path / 'views'
    out_path.mkdir(parents=True, exist_ok=True)

    # Load data files
    clusters_file = results_path / 'clusters.json'
    papers_file = results_path / 'papers.json'
    if not papers_file.exists():
        papers_file = results_path / 'papers_cleaned.json'
    gaps_file = results_path / 'gaps.json'
    temporal_file = results_path / 'temporal.json'

    clusters: Dict[str, int] = {}
    papers: List[Dict[str, Any]] = []
    gaps: Dict[str, Any] = {}
    temporal: Dict[str, Any] = {}

    if clusters_file.exists():
        with open(clusters_file, 'r', encoding='utf-8') as f:
            clusters = json.load(f)

    if papers_file.exists():
        with open(papers_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)

    if gaps_file.exists():
        with open(gaps_file, 'r', encoding='utf-8') as f:
            gaps = json.load(f)

    if temporal_file.exists():
        with open(temporal_file, 'r', encoding='utf-8') as f:
            temporal = json.load(f)

    labels = generate_labels(clusters, papers)

    generated: List[str] = []

    # Overview (V2)
    ov_path = out_path / 'overview.html'
    generate_overview(clusters, papers, labels, str(ov_path))
    generated.append(str(ov_path))

    # Bridges (V3) — always generate; empty-data handler shows guidance
    br_path = out_path / 'bridges.html'
    generate_bridges(gaps, labels, str(br_path))
    generated.append(str(br_path))

    # Ranking (T1) — always generate; empty-data handler shows guidance
    rk_path = out_path / 'ranking.html'
    generate_ranking(gaps, labels, str(rk_path))
    generated.append(str(rk_path))

    # Drill-down per cluster (V5)
    doi_to_paper: Dict[str, Dict[str, Any]] = {p.get('doi', ''): p for p in papers if p.get('doi')}
    cluster_to_papers: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for doi, cid in clusters.items():
        paper = doi_to_paper.get(doi)
        if paper:
            cluster_to_papers[cid].append(paper)

    for cid, cluster_papers in cluster_to_papers.items():
        dd_path = out_path / f'cluster_{cid}.html'
        generate_drilldown(cid, cluster_papers, labels, str(dd_path))
        generated.append(str(dd_path))

    # Timeline (V6)
    if temporal:
        tl_path = out_path / 'timeline.html'
        generate_timeline(temporal, labels, str(tl_path))
        generated.append(str(tl_path))

    # Detail (V7)
    if papers:
        dt_path = out_path / 'detail.html'
        generate_detail(papers, clusters, labels, str(dt_path))
        generated.append(str(dt_path))

    # Decision Summary (T6)
    ds_path = out_path / 'decision.html'
    generate_decision_summary(clusters, gaps, labels, str(ds_path))
    generated.append(str(ds_path))

    # Copy plotly.min.js for offline use
    try:
        static_js = pkg_files('papersift').joinpath('static/plotly.min.js')
        shutil.copy(str(static_js), str(out_path / 'plotly.min.js'))
    except Exception:
        pass  # CDN fallback in HTML covers this case

    return generated
