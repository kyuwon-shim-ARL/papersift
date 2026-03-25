"""Tests for v1.1 Knowledge Frontier Analysis sub-tab components."""

import pytest
from dash import html, dcc

from papersift.ui.components.analysis import (
    create_burst_timeline_tab,
    create_novelty_gaps_tab,
    create_themes_tab,
    create_bridge_recommendations_tab,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def burst_data():
    """Minimal e023-like burst detection data."""
    return {
        'results_by_s': {
            '2.0': {
                'n_burst_entities': 3,
                'burst_entities': [
                    {
                        'entity': 'deep learning',
                        'burst_years': [2018, 2019, 2020],
                        'burst_intervals': [{'start': 2018, 'end': 2020, 'length': 3}],
                        'peak_year': 2019,
                        'peak_count': 10,
                        'total_mentions': 25,
                    },
                    {
                        'entity': 'single-cell',
                        'burst_years': [2020, 2021],
                        'burst_intervals': [{'start': 2020, 'end': 2021, 'length': 2}],
                        'peak_year': 2021,
                        'peak_count': 8,
                        'total_mentions': 15,
                    },
                    {
                        'entity': 'digital twin',
                        'burst_years': [2022],
                        'burst_intervals': [{'start': 2022, 'end': 2022, 'length': 1}],
                        'peak_year': 2022,
                        'peak_count': 5,
                        'total_mentions': 5,
                    },
                ],
            }
        }
    }


@pytest.fixture
def zscore_data():
    """Minimal e021-like z-score novelty data."""
    return {
        'z_score_gaps': {
            'total_pairs_tested': 100,
            'significant_gaps_z2': 3,
            'top_10_gaps': [
                {
                    'cluster': 'C0',
                    'entity_a': 'disease',
                    'entity_b': 'cancer cell',
                    'observed': 1,
                    'null_mean': 8.0,
                    'null_std': 2.5,
                    'z': -2.8,
                    'ratio': 0.12,
                },
                {
                    'cluster': 'C1',
                    'entity_a': 'metabolism',
                    'entity_b': 'signaling',
                    'observed': 0,
                    'null_mean': 5.0,
                    'null_std': 1.8,
                    'z': -2.78,
                    'ratio': 0.0,
                },
            ],
        }
    }


@pytest.fixture
def themes_data():
    """Minimal e024-like semantic theme data."""
    return {
        'hdbscan': {'n_clusters': 5, 'noise_rate': 0.22},
        'themes': [
            {
                'cluster_id': 0,
                'n_items': 20,
                'keywords': ['model', 'expression', 'protein'],
                'mean_intra_sim': 0.57,
                'coherent': True,
            },
            {
                'cluster_id': 1,
                'n_items': 10,
                'keywords': ['data', 'validation'],
                'mean_intra_sim': 0.65,
                'coherent': True,
            },
        ],
    }


@pytest.fixture
def bridge_data():
    """Minimal e025-like bridge recommendation data."""
    return {
        't1_rank_norm': {
            'eval_all': {
                'dominance_ratio': 1.47,
            },
            'top_20': [
                {
                    'type': 'intra_cluster',
                    'cluster': '5',
                    'cluster_label': 'mechanics/ABM',
                    'entity_a': 'dynamics',
                    'entity_b': 'human',
                    'bridge_score': 0.875,
                    'momentum_score': 0.011,
                    'gap_score': 0.74,
                    'failure_penalty': 0.36,
                },
                {
                    'type': 'cross_cluster',
                    'cluster_a': '6',
                    'cluster_b': '7',
                    'cluster_a_label': 'fuel-cells',
                    'cluster_b_label': 'immunology',
                    'bridge_score': 0.774,
                    'momentum_score': 0.011,
                    'gap_score': 0.79,
                    'failure_penalty': 0.3,
                },
            ],
        }
    }


# ---------------------------------------------------------------------------
# Empty data tests
# ---------------------------------------------------------------------------

class TestEmptyData:
    """All v1.1 tab creators should return html.Div with no-data message for empty input."""

    def test_burst_none(self):
        result = create_burst_timeline_tab(None)
        assert isinstance(result, html.Div)

    def test_burst_empty(self):
        result = create_burst_timeline_tab({})
        assert isinstance(result, html.Div)

    def test_novelty_none(self):
        result = create_novelty_gaps_tab(None)
        assert isinstance(result, html.Div)

    def test_novelty_empty(self):
        result = create_novelty_gaps_tab({})
        assert isinstance(result, html.Div)

    def test_themes_none(self):
        result = create_themes_tab(None)
        assert isinstance(result, html.Div)

    def test_themes_empty(self):
        result = create_themes_tab({})
        assert isinstance(result, html.Div)

    def test_bridge_none(self):
        result = create_bridge_recommendations_tab(None)
        assert isinstance(result, html.Div)

    def test_bridge_empty(self):
        result = create_bridge_recommendations_tab({})
        assert isinstance(result, html.Div)


# ---------------------------------------------------------------------------
# Normal data tests
# ---------------------------------------------------------------------------

class TestNormalData:
    """v1.1 tab creators should produce correct component types for valid data."""

    def test_burst_has_graph(self, burst_data):
        result = create_burst_timeline_tab(burst_data)
        assert isinstance(result, html.Div)
        # Should contain a dcc.Graph
        graphs = _find_components(result, dcc.Graph)
        assert len(graphs) >= 1
        assert graphs[0].id == 'analysis-v11-burst-chart'

    def test_novelty_has_graph(self, zscore_data):
        result = create_novelty_gaps_tab(zscore_data)
        assert isinstance(result, html.Div)
        graphs = _find_components(result, dcc.Graph)
        assert len(graphs) >= 1
        assert graphs[0].id == 'analysis-v11-novelty-chart'

    def test_themes_has_grid(self, themes_data):
        result = create_themes_tab(themes_data)
        assert isinstance(result, html.Div)
        import dash_ag_grid as dag
        grids = _find_components(result, dag.AgGrid)
        assert len(grids) >= 1
        assert grids[0].id == 'analysis-v11-themes-grid'
        assert len(grids[0].rowData) == 2

    def test_bridge_has_grid(self, bridge_data):
        result = create_bridge_recommendations_tab(bridge_data)
        assert isinstance(result, html.Div)
        import dash_ag_grid as dag
        grids = _find_components(result, dag.AgGrid)
        assert len(grids) >= 1
        assert grids[0].id == 'analysis-v11-bridge-grid'
        assert len(grids[0].rowData) == 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_components(component, target_type, found=None):
    """Recursively find all components of a given type."""
    if found is None:
        found = []
    if isinstance(component, target_type):
        found.append(component)
    if hasattr(component, 'children'):
        children = component.children
        if isinstance(children, (list, tuple)):
            for child in children:
                _find_components(child, target_type, found)
        elif children is not None:
            _find_components(children, target_type, found)
    return found
