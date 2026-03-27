"""Unit tests for papersift.views — HTML view generators."""

import json
import pytest
from papersift.views import (
    generate_labels, generate_overview, generate_bridges, generate_ranking,
    generate_drilldown, generate_timeline, generate_detail,
    generate_decision_summary, generate_all_views,
)


@pytest.fixture
def sample_clusters():
    return {
        '10.1000/a': 0, '10.1000/b': 0, '10.1000/c': 0,
        '10.1000/d': 1, '10.1000/e': 1,
        '10.1000/f': 2,
    }


@pytest.fixture
def sample_papers():
    return [
        {'doi': '10.1000/a', 'title': 'Machine Learning Drug Discovery', 'year': 2023, 'cited_by_count': 50, 'topics': ['AI']},
        {'doi': '10.1000/b', 'title': 'Deep Learning Drug Screening', 'year': 2022, 'cited_by_count': 30, 'topics': []},
        {'doi': '10.1000/c', 'title': 'Neural Network Drug Design', 'year': 2024, 'cited_by_count': 10, 'topics': [{'display_name': 'ML'}]},
        {'doi': '10.1000/d', 'title': 'Molecular Dynamics Simulation Methods', 'year': 2023, 'cited_by_count': 45, 'topics': ['Chemistry']},
        {'doi': '10.1000/e', 'title': 'Molecular Modeling Protein Folding', 'year': 2021, 'cited_by_count': 100, 'topics': []},
        {'doi': '10.1000/f', 'title': 'Genomics Cancer Biomarker Identification', 'year': 2023, 'cited_by_count': 25, 'topics': ['Biology']},
    ]


@pytest.fixture
def sample_gaps():
    return {
        'cross_cluster_bridges': [
            {'cluster_a': 0, 'cluster_b': 1, 'entity_jaccard': 0.15, 'shared_entities': ['drug', 'molecular']},
            {'cluster_a': 1, 'cluster_b': 2, 'entity_jaccard': 0.08, 'shared_entities': ['protein']},
        ]
    }


@pytest.fixture
def sample_temporal():
    return {
        'clusters': {
            '0': {
                'entities': [
                    {'entity': 'machine_learning', 'slope': 0.5, 'q_value': 0.01, 'yearly_counts': {'2020': 1, '2021': 2, '2022': 3}},
                ],
                'year_range': '2020-2022',
                'n_papers': 30,
            },
            '1': {
                'top_rising': [
                    {'entity': 'molecular_dynamics', 'slope': 0.3, 'q_value': 0.05, 'yearly_counts': {'2020': 2, '2021': 2, '2022': 3}},
                ],
                'year_range': '2020-2022',
                'n_papers': 20,
            },
        }
    }


@pytest.fixture
def sample_labels(sample_clusters, sample_papers):
    return generate_labels(sample_clusters, sample_papers)


# ---------------------------------------------------------------------------
# generate_labels
# ---------------------------------------------------------------------------

def test_generate_labels(sample_clusters, sample_papers):
    labels = generate_labels(sample_clusters, sample_papers)
    # Should have labels for all 3 cluster IDs
    assert set(labels.keys()) == {0, 1, 2}
    # Labels should contain capitalized words joined by " + "
    for cid, label in labels.items():
        assert isinstance(label, str)
        assert len(label) > 0
        # Each word part should be capitalized (Title case)
        parts = label.split(' + ')
        for part in parts:
            assert part[0].isupper(), f"Expected capitalized word, got '{part}'"


def test_generate_labels_empty():
    labels = generate_labels({}, [])
    assert labels == {}


# ---------------------------------------------------------------------------
# generate_overview
# ---------------------------------------------------------------------------

def test_generate_overview(tmp_path, sample_clusters, sample_papers, sample_labels):
    out = tmp_path / 'overview.html'
    result = generate_overview(sample_clusters, sample_papers, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Cluster Overview' in html
    assert 'treemap' in html.lower() or 'Treemap' in html or 'treemapData' in html.lower()
    assert 'papersift_cluster_validation' in html
    assert 'papersift_my_position' in html


# ---------------------------------------------------------------------------
# generate_bridges
# ---------------------------------------------------------------------------

def test_generate_bridges(tmp_path, sample_gaps, sample_labels):
    out = tmp_path / 'bridges.html'
    result = generate_bridges(sample_gaps, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Cluster Bridges' in html
    assert 'sankey' in html.lower() or 'Sankey' in html
    assert 'papersift_bridge_eval' in html


def test_generate_bridges_empty(tmp_path, sample_labels):
    out = tmp_path / 'bridges.html'
    result = generate_bridges({}, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'No bridge data' in html


# ---------------------------------------------------------------------------
# generate_ranking
# ---------------------------------------------------------------------------

def test_generate_ranking(tmp_path, sample_gaps, sample_labels):
    out = tmp_path / 'ranking.html'
    result = generate_ranking(sample_gaps, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Bridge Ranking' in html or 'rank-table' in html
    assert 'rank-table' in html
    assert 'score-bar' in html


def test_generate_ranking_empty(tmp_path, sample_labels):
    out = tmp_path / 'ranking.html'
    result = generate_ranking({}, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'No bridge data' in html


# ---------------------------------------------------------------------------
# generate_drilldown
# ---------------------------------------------------------------------------

def test_generate_drilldown(tmp_path, sample_papers, sample_labels):
    cluster_papers = [p for p in sample_papers if p['doi'] in ('10.1000/a', '10.1000/b', '10.1000/c')]
    out = tmp_path / 'cluster_0.html'
    result = generate_drilldown(0, cluster_papers, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    # Should contain cluster label
    label = sample_labels[0]
    assert label in html
    # Should contain paper titles
    assert 'Machine Learning Drug Discovery' in html
    assert 'Deep Learning Drug Screening' in html
    # Should have sortable table structure
    assert '<table' in html or 'data-search' in html


# ---------------------------------------------------------------------------
# generate_timeline
# ---------------------------------------------------------------------------

def test_generate_timeline(tmp_path, sample_temporal, sample_labels):
    out = tmp_path / 'timeline.html'
    result = generate_timeline(sample_temporal, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    # Should contain entity names
    assert 'machine_learning' in html
    # Should use plotly
    assert 'plotly' in html.lower() or 'Plotly' in html


def test_generate_timeline_top_rising(tmp_path, sample_labels):
    """Temporal data with top_rising key (AMR format) should work."""
    temporal = {
        'clusters': {
            '0': {
                'top_rising': [
                    {'entity': 'deep_learning', 'slope': 0.8, 'q_value': 0.001, 'yearly_counts': {'2021': 5, '2022': 10}},
                ],
                'top_declining': [
                    {'entity': 'rule_based', 'slope': -0.3, 'q_value': 0.02, 'yearly_counts': {'2021': 8, '2022': 5}},
                ],
                'year_range': '2021-2022',
                'n_papers': 15,
            },
        }
    }
    out = tmp_path / 'timeline.html'
    result = generate_timeline(temporal, sample_labels, str(out))
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'deep_learning' in html
    assert 'plotly' in html.lower() or 'Plotly' in html


# ---------------------------------------------------------------------------
# generate_detail
# ---------------------------------------------------------------------------

def test_generate_detail(tmp_path, sample_papers, sample_clusters, sample_labels):
    out = tmp_path / 'detail.html'
    result = generate_detail(sample_papers, sample_clusters, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Paper Directory' in html
    assert 'pagination' in html
    assert 'search' in html.lower()


# ---------------------------------------------------------------------------
# generate_decision_summary
# ---------------------------------------------------------------------------

def test_generate_decision_summary(tmp_path, sample_clusters, sample_gaps, sample_labels):
    out = tmp_path / 'decision.html'
    result = generate_decision_summary(sample_clusters, sample_gaps, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Decision Summary' in html
    # Should reference all 3 localStorage keys
    assert 'papersift_cluster_validation' in html
    assert 'papersift_my_position' in html
    assert 'papersift_bridge_eval' in html


def test_generate_decision_summary_no_gaps(tmp_path, sample_clusters, sample_labels):
    out = tmp_path / 'decision.html'
    result = generate_decision_summary(sample_clusters, {}, sample_labels, str(out))
    assert result == str(out)
    assert out.exists()
    html = out.read_text(encoding='utf-8')
    assert 'Decision Summary' in html


# ---------------------------------------------------------------------------
# generate_all_views
# ---------------------------------------------------------------------------

def test_generate_all_views(tmp_path, sample_clusters, sample_papers, sample_gaps, sample_temporal):
    # Write input JSON files
    (tmp_path / 'clusters.json').write_text(json.dumps(sample_clusters), encoding='utf-8')
    (tmp_path / 'papers.json').write_text(json.dumps(sample_papers), encoding='utf-8')
    (tmp_path / 'gaps.json').write_text(json.dumps(sample_gaps), encoding='utf-8')
    (tmp_path / 'temporal.json').write_text(json.dumps(sample_temporal), encoding='utf-8')

    out_dir = tmp_path / 'views'
    generated = generate_all_views(str(tmp_path), str(out_dir))

    assert len(generated) > 0
    # Check expected files exist
    expected_names = [
        'overview.html', 'bridges.html', 'ranking.html',
        'cluster_0.html', 'cluster_1.html', 'cluster_2.html',
        'timeline.html', 'detail.html', 'decision.html',
    ]
    existing_names = [f.name for f in out_dir.iterdir()]
    for name in expected_names:
        assert name in existing_names, f"Expected {name} in generated views"


def test_generate_all_views_minimal(tmp_path):
    """Only clusters.json provided — all nav pages should exist; bridges/ranking with empty-data content."""
    clusters = {'10.1000/x': 0, '10.1000/y': 1}
    (tmp_path / 'clusters.json').write_text(json.dumps(clusters), encoding='utf-8')

    out_dir = tmp_path / 'views'
    generated = generate_all_views(str(tmp_path), str(out_dir))

    existing_names = [f.name for f in out_dir.iterdir()]
    assert 'overview.html' in existing_names
    assert 'decision.html' in existing_names
    # Bridges/ranking always generated (empty-data placeholder); no temporal → no timeline
    assert 'bridges.html' in existing_names
    assert 'ranking.html' in existing_names
    assert 'timeline.html' not in existing_names
    # Bridges should show empty-data message
    bridges_html = (out_dir / 'bridges.html').read_text(encoding='utf-8')
    assert 'No bridge data' in bridges_html


# ---------------------------------------------------------------------------
# T6: New edge-case tests
# ---------------------------------------------------------------------------

def test_generate_all_views_copies_plotly_js(tmp_path, sample_clusters):
    """After generate_all_views(), plotly.min.js should exist in output dir (T2)."""
    import importlib.resources
    try:
        pkg_files = importlib.resources.files('papersift')
        static_js = pkg_files.joinpath('static/plotly.min.js')
        import pathlib
        if not pathlib.Path(str(static_js)).exists():
            pytest.skip("plotly.min.js not bundled yet — pending T2 implementation")
    except Exception:
        pytest.skip("static resource not available — pending T2 implementation")

    (tmp_path / 'clusters.json').write_text(json.dumps(sample_clusters), encoding='utf-8')
    out_dir = tmp_path / 'views'
    generate_all_views(str(tmp_path), str(out_dir))
    assert (out_dir / 'plotly.min.js').exists(), "plotly.min.js must be copied to output dir"


def test_generate_all_views_fallback_filenames(tmp_path, sample_clusters, sample_papers):
    """generate_all_views() should find papers_cleaned.json when papers.json absent."""
    (tmp_path / 'clusters.json').write_text(json.dumps(sample_clusters), encoding='utf-8')
    (tmp_path / 'papers_cleaned.json').write_text(json.dumps(sample_papers), encoding='utf-8')

    out_dir = tmp_path / 'views'
    generated = generate_all_views(str(tmp_path), str(out_dir))

    existing_names = [f.name for f in out_dir.iterdir()]
    assert 'overview.html' in existing_names
    assert 'detail.html' in existing_names  # papers loaded from fallback filename


def test_generate_overview_top20_boundary(tmp_path):
    """25 clusters → overview should contain 'Others' bucket."""
    clusters = {f'10.1000/p{i}': i for i in range(25)}
    papers = [
        {'doi': f'10.1000/p{i}', 'title': f'Paper {i}', 'year': 2023,
         'cited_by_count': i, 'topics': []}
        for i in range(25)
    ]
    labels = generate_labels(clusters, papers)
    out = tmp_path / 'overview.html'
    generate_overview(clusters, papers, labels, str(out))
    html = out.read_text(encoding='utf-8')
    assert 'Others' in html, "Overview with 25 clusters must collapse extras into 'Others'"


def test_generate_overview_has_highlight_js(tmp_path, sample_clusters, sample_papers, sample_labels):
    """Generated overview HTML must contain highlightCluster JS function."""
    out = tmp_path / 'overview.html'
    generate_overview(sample_clusters, sample_papers, sample_labels, str(out))
    html = out.read_text(encoding='utf-8')
    assert 'highlightCluster' in html, "overview.html must define highlightCluster JS function"


# ---------------------------------------------------------------------------
# Autoplan: new tests for bug fixes
# ---------------------------------------------------------------------------

def test_generate_all_views_ignores_trend_analysis(tmp_path, sample_clusters):
    """trend_analysis.json should NOT be used as temporal data — different schema."""
    (tmp_path / 'clusters.json').write_text(json.dumps(sample_clusters), encoding='utf-8')
    # Only trend_analysis.json, no temporal.json
    (tmp_path / 'trend_analysis.json').write_text(json.dumps({
        'task2_temporal_evolution': {},
        'task3_emerging_declining_methods': {},
    }), encoding='utf-8')

    out_dir = tmp_path / 'views'
    generated = generate_all_views(str(tmp_path), str(out_dir))
    existing_names = [f.name for f in out_dir.iterdir()]
    # Timeline should NOT be generated (no valid temporal.json)
    assert 'timeline.html' not in existing_names


def test_generate_all_views_no_gaps_generates_all_nav_pages(tmp_path, sample_clusters, sample_papers):
    """Without gaps.json, bridges.html and ranking.html should still be generated."""
    (tmp_path / 'clusters.json').write_text(json.dumps(sample_clusters), encoding='utf-8')
    (tmp_path / 'papers.json').write_text(json.dumps(sample_papers), encoding='utf-8')

    out_dir = tmp_path / 'views'
    generated = generate_all_views(str(tmp_path), str(out_dir))
    existing_names = [f.name for f in out_dir.iterdir()]
    assert 'bridges.html' in existing_names, "bridges.html must exist even without gaps.json"
    assert 'ranking.html' in existing_names, "ranking.html must exist even without gaps.json"
    # Content should show empty-data message
    bridges_html = (out_dir / 'bridges.html').read_text(encoding='utf-8')
    assert 'No bridge data' in bridges_html
    ranking_html = (out_dir / 'ranking.html').read_text(encoding='utf-8')
    assert 'No bridge data' in ranking_html


def test_generate_detail_has_cluster_filter(tmp_path, sample_papers, sample_clusters, sample_labels):
    """Detail page should have a cluster filter dropdown."""
    out = tmp_path / 'detail.html'
    generate_detail(sample_papers, sample_clusters, sample_labels, str(out))
    html = out.read_text(encoding='utf-8')
    assert 'clusterFilter' in html, "Detail page must have cluster filter dropdown"
    assert 'All Clusters' in html


def test_generate_timeline_empty_dict(tmp_path, sample_labels):
    """Empty temporal dict should produce 'No temporal data' page."""
    out = tmp_path / 'timeline.html'
    generate_timeline({}, sample_labels, str(out))
    html = out.read_text(encoding='utf-8')
    assert 'No temporal data' in html
