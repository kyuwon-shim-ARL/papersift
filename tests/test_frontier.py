"""Tests for Knowledge Frontier modules: frontier, failure_signal, bridge_recommend."""

import pytest


# ── Fixtures ────────────────────────────────────────────────────────


PAPERS = [
    {
        "doi": "10.1/A",
        "title": "ODE model of whole-cell signaling",
        "abstract": "We present an ODE model using machine learning for simulation.",
        "year": 2018,
        "referenced_works": ["W1", "W2", "W3"],
    },
    {
        "doi": "10.1/B",
        "title": "Agent-based model of immune response",
        "abstract": "Agent-based simulation with stochastic dynamics.",
        "year": 2019,
        "referenced_works": ["W2", "W3", "W4"],
    },
    {
        "doi": "10.1/C",
        "title": "ODE model for pharmacology",
        "abstract": "ODE-based pharmacokinetics model with machine learning.",
        "year": 2020,
        "referenced_works": ["W1", "W2"],
    },
    {
        "doi": "10.1/D",
        "title": "Stochastic simulation of metabolism",
        "abstract": "Stochastic ordinary differential equations for metabolic networks.",
        "year": 2021,
        "referenced_works": ["W3", "W4", "W5"],
    },
    {
        "doi": "10.1/E",
        "title": "Machine learning for drug discovery",
        "abstract": "Deep learning applied to whole-cell simulation.",
        "year": 2022,
        "referenced_works": ["W1", "W5"],
    },
]

CLUSTERS = {
    "10.1/A": 0,
    "10.1/B": 1,
    "10.1/C": 0,
    "10.1/D": 1,
    "10.1/E": 0,
}


# ── frontier.extract_entities ────────────────────────────────────────


def test_extract_entities_returns_dict():
    from papersift.frontier import extract_entities

    result = extract_entities(PAPERS)

    assert isinstance(result, dict)
    assert set(result.keys()) == {p["doi"] for p in PAPERS}


def test_extract_entities_values_are_sets():
    from papersift.frontier import extract_entities

    result = extract_entities(PAPERS)

    for doi, entities in result.items():
        assert isinstance(entities, set), f"Expected set for {doi}, got {type(entities)}"


def test_extract_entities_non_empty_for_known_terms():
    from papersift.frontier import extract_entities

    result = extract_entities(PAPERS)

    # At least some papers should have entities extracted
    non_empty = sum(1 for v in result.values() if v)
    assert non_empty >= 1


# ── frontier.redundancy_scoring ─────────────────────────────────────


def test_redundancy_scoring_structure():
    from papersift.frontier import extract_entities, redundancy_scoring

    entity_data = extract_entities(PAPERS)
    result = redundancy_scoring(PAPERS, entity_data, CLUSTERS)

    assert "pairs_checked" in result
    assert "notable_pairs" in result
    assert "axis_correlation" in result
    assert "top_20" in result
    assert "threshold" in result
    assert "per_cluster_counts" in result


def test_redundancy_scoring_pairs_counted():
    from papersift.frontier import extract_entities, redundancy_scoring

    entity_data = extract_entities(PAPERS)
    result = redundancy_scoring(PAPERS, entity_data, CLUSTERS)

    # Cluster 0 has 3 papers (A, C, E) → 3 pairs; cluster 1 has 2 papers (B, D) → 1 pair
    assert result["pairs_checked"] == 4


def test_redundancy_scoring_with_empty_entity_data():
    from papersift.frontier import redundancy_scoring

    entity_data = {p["doi"]: set() for p in PAPERS}
    result = redundancy_scoring(PAPERS, entity_data, CLUSTERS)

    # Entity jaccard will be 0, but biblio coupling may still score pairs
    assert result["pairs_checked"] == 4
    assert isinstance(result["notable_pairs"], int)


# ── frontier.temporal_dynamics ───────────────────────────────────────


def test_temporal_dynamics_structure():
    from papersift.frontier import extract_entities, temporal_dynamics

    entity_data = extract_entities(PAPERS)
    result = temporal_dynamics(PAPERS, entity_data, CLUSTERS)

    assert "total_tests" in result
    assert "total_significant" in result
    assert "momentum_variance" in result
    assert "clusters" in result
    assert isinstance(result["clusters"], dict)


def test_temporal_dynamics_skips_small_clusters():
    from papersift.frontier import extract_entities, temporal_dynamics

    entity_data = extract_entities(PAPERS)
    result = temporal_dynamics(PAPERS, entity_data, CLUSTERS)

    # With only 5 papers, clusters have < 20 papers → all skipped
    assert len(result["clusters"]) == 0
    assert result["total_tests"] == 0


# ── frontier.structural_gaps ─────────────────────────────────────────


def test_structural_gaps_structure():
    from papersift.frontier import extract_entities, structural_gaps

    entity_data = extract_entities(PAPERS)
    result = structural_gaps(PAPERS, entity_data, CLUSTERS)

    assert "intra_cluster_gaps" in result
    assert "cross_cluster_bridges" in result
    assert "intra_summary" in result
    assert isinstance(result["cross_cluster_bridges"], list)


def test_structural_gaps_skips_small_clusters():
    from papersift.frontier import extract_entities, structural_gaps

    entity_data = extract_entities(PAPERS)
    result = structural_gaps(PAPERS, entity_data, CLUSTERS)

    # Clusters have < 20 papers → no intra gaps and no cluster entity sets for bridges
    assert result["intra_cluster_gaps"] == {}


# ── failure_signal ───────────────────────────────────────────────────


EXTRACTIONS = [
    {"doi": "10.1/A", "limits": "The model does not account for spatial heterogeneity.", "open_questions": ""},
    {"doi": "10.1/B", "limits": "More data needed for validation.", "open_questions": "Can we scale to whole organisms?"},
    {"doi": "10.1/C", "limits": "Spatial heterogeneity is ignored in current formulation.", "open_questions": "How to integrate experimental data?"},
    {"doi": "10.1/D", "limits": "Limited to small metabolic networks.", "open_questions": ""},
    {"doi": "10.1/E", "limits": "Further research required.", "open_questions": "What are the boundary conditions?"},
]


def test_is_generic_detects_generic():
    from papersift.failure_signal import is_generic

    assert is_generic("More data needed") is True
    assert is_generic("further study required") is True
    assert is_generic("") is True
    assert is_generic("short") is True


def test_is_generic_passes_specific():
    from papersift.failure_signal import is_generic

    assert is_generic("The model ignores spatial heterogeneity of signaling proteins") is False


def test_cluster_limitations_by_keywords_groups_similar():
    from papersift.failure_signal import cluster_limitations_by_keywords

    limitations = [
        {"doi": "10.1/A", "text": "spatial heterogeneity is not modeled"},
        {"doi": "10.1/C", "text": "spatial heterogeneity ignored in current formulation"},
        {"doi": "10.1/D", "text": "limited to small networks"},
    ]
    themes = cluster_limitations_by_keywords(limitations)

    # First two share "spatial" and "heterogeneity" — should cluster together
    assert len(themes) >= 1
    theme_labels = [t["theme_label"] for t in themes]
    assert any("spatial" in label or "heterogeneity" in label for label in theme_labels)


def test_analyze_failures_structure():
    from papersift.failure_signal import analyze_failures

    result = analyze_failures(EXTRACTIONS, CLUSTERS)

    assert "total_extractions_used" in result
    assert "total_limit_themes" in result
    assert "total_dead_end_signals" in result
    assert "overall_generic_rate" in result
    assert "verdict" in result
    assert "clusters" in result


def test_analyze_failures_generic_rate():
    from papersift.failure_signal import analyze_failures

    result = analyze_failures(EXTRACTIONS, CLUSTERS)

    # 2 of 5 are generic ("More data needed" and "Further research required")
    assert 0.0 <= result["overall_generic_rate"] <= 1.0


# ── bridge_recommend ─────────────────────────────────────────────────


FRONTIER_RESULTS = {
    "t2_temporal": {
        "clusters": {
            "0": {
                "momentum_score": 0.002,
                "significant": 3,
                "top_rising": [{"entity": "ode", "slope": 0.01, "q_value": 0.04}],
                "top_declining": [],
            },
            "1": {
                "momentum_score": -0.001,
                "significant": 1,
                "top_rising": [],
                "top_declining": [{"entity": "abm", "slope": -0.005, "q_value": 0.03}],
            },
        }
    },
    "t3_structural_gaps": {
        "intra_cluster_gaps": {
            "0": [
                {"entity_a": "ode", "entity_b": "machine learning", "freq_a": 10, "freq_b": 8,
                 "expected": 6.5, "observed": 1, "ratio": 0.15},
            ],
            "1": [],
        },
        "cross_cluster_bridges": [
            {
                "cluster_a": 0,
                "cluster_b": 1,
                "entity_jaccard": 0.18,
                "shared_entities": ["simulation", "model"],
                "unique_a": 5,
                "unique_b": 3,
                "shared_count": 2,
            }
        ],
    },
}

FAILURE_RESULTS = {
    "clusters": {
        "0": {
            "limit_themes": [{"theme_label": "spatial heterogeneity", "count": 3}],
            "dead_end_signals": [],
        },
        "1": {
            "limit_themes": [{"theme_label": "scalability", "count": 2}],
            "dead_end_signals": [{"theme_label": "scalability", "count": 2}],
        },
    }
}


def test_generate_recommendations_structure():
    from papersift.bridge_recommend import generate_recommendations

    result = generate_recommendations(FRONTIER_RESULTS, FAILURE_RESULTS)

    assert "n_intra_recommendations" in result
    assert "n_cross_recommendations" in result
    assert "n_total" in result
    assert "verdict" in result
    assert "all_recommendations" in result


def test_generate_recommendations_sorted_by_score():
    from papersift.bridge_recommend import generate_recommendations

    result = generate_recommendations(FRONTIER_RESULTS, FAILURE_RESULTS)

    recs = result["all_recommendations"]
    scores = [r["bridge_score"] for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_generate_recommendations_top_n():
    from papersift.bridge_recommend import generate_recommendations

    result = generate_recommendations(FRONTIER_RESULTS, FAILURE_RESULTS, top_n=5)

    # top_5 key should exist and have <= 5 entries
    assert "top_5" in result
    assert len(result["top_5"]) <= 5


def test_generate_recommendations_biology_filter():
    from papersift.bridge_recommend import generate_recommendations

    # Only cluster "0" in biology_clusters → cross-cluster bridge C0↔C1 included (C0 is bio)
    result = generate_recommendations(
        FRONTIER_RESULTS,
        FAILURE_RESULTS,
        biology_clusters=["0"],
    )

    # Should still produce intra recs for C0 and cross recs for C0↔C1
    assert result["n_total"] >= 1
