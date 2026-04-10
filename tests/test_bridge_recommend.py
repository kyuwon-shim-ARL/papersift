"""Tests for bridge_recommend module — rank-norm integration (e025)."""

import pytest

from papersift.bridge_recommend import (
    _rank_normalize,
    generate_recommendations,
)


# --- Fixtures ---

def _make_frontier_results(n_clusters=3, n_gaps_per_cluster=3, n_bridges=5):
    """Build minimal frontier_results for testing."""
    clusters = {}
    for i in range(n_clusters):
        cid = str(i)
        clusters[cid] = {
            "momentum_score": 0.005 + i * 0.003,
            "significant": 5 + i,
            "top_rising": [{"entity": f"entity_r_{cid}", "slope": 0.01, "q_value": 0.01}],
            "top_declining": [],
        }

    intra_gaps = {}
    for i in range(n_clusters):
        cid = str(i)
        gaps = []
        for j in range(n_gaps_per_cluster):
            gaps.append({
                "entity_a": f"entity_a_{cid}_{j}",
                "entity_b": f"entity_b_{cid}_{j}",
                "freq_a": 20,
                "freq_b": 15,
                "expected": 10.0 + j,
                "observed": j,
                "ratio": round(j / (10.0 + j), 4),
            })
        intra_gaps[cid] = gaps

    bridges = []
    cids = [str(i) for i in range(n_clusters)]
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            if len(bridges) >= n_bridges:
                break
            bridges.append({
                "cluster_a": cids[i],
                "cluster_b": cids[j],
                "entity_jaccard": 0.1 + 0.05 * len(bridges),
                "shared_entities": [f"shared_{len(bridges)}"],
                "shared_count": 1,
                "unique_a": 10,
                "unique_b": 8,
            })

    return {
        "t2_temporal": {"clusters": clusters},
        "t3_structural_gaps": {
            "intra_cluster_gaps": intra_gaps,
            "cross_cluster_bridges": bridges,
        },
    }


def _make_failure_results(n_clusters=3):
    """Build minimal failure_results for testing."""
    clusters = {}
    for i in range(n_clusters):
        cid = str(i)
        clusters[cid] = {
            "dead_end_signals": [{"theme_label": f"dead_{j}"} for j in range(i + 1)],
            "limit_themes": [{"theme": f"limit_{j}"} for j in range(3)],
        }
    return {"clusters": clusters}


# --- Tests ---

class TestRankNormalize:
    def test_basic_ranking(self):
        result = _rank_normalize([10, 20, 30])
        assert result == [pytest.approx(1 / 3, abs=0.01),
                          pytest.approx(2 / 3, abs=0.01),
                          pytest.approx(1.0, abs=0.01)]

    def test_single_element(self):
        result = _rank_normalize([42])
        assert result == [1.0]

    def test_empty(self):
        result = _rank_normalize([])
        assert result == []

    def test_ties(self):
        result = _rank_normalize([5, 5, 10])
        # Tied values get average rank: (1+2)/2 = 1.5, so 1.5/3 = 0.5
        assert result[0] == result[1]
        assert result[2] > result[0]

    def test_all_values_in_unit_interval(self):
        result = _rank_normalize([100, 1, 50, 75, 25])
        for v in result:
            assert 0 < v <= 1.0


class TestGenerateRecommendations:
    def test_basic_output_structure(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
            top_n=10,
        )

        assert "n_intra_recommendations" in result
        assert "n_cross_recommendations" in result
        assert "all_recommendations" in result
        assert "formula" in result
        assert result["formula"] == "rank_norm (e025)"

    def test_rank_norm_fields_present(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
        )

        for rec in result["all_recommendations"]:
            assert "r_momentum" in rec
            assert "r_gap" in rec
            assert "r_inv_failure" in rec

    def test_bridge_scores_in_unit_interval(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
        )

        for rec in result["all_recommendations"]:
            assert 0 <= rec["bridge_score"] <= 1.0, (
                f"bridge_score {rec['bridge_score']} outside [0,1]"
            )

    def test_rank_components_in_unit_interval(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
        )

        for rec in result["all_recommendations"]:
            assert 0 < rec["r_momentum"] <= 1.0
            assert 0 < rec["r_gap"] <= 1.0
            assert 0 < rec["r_inv_failure"] <= 1.0

    def test_sorted_by_bridge_score_descending(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
        )

        scores = [r["bridge_score"] for r in result["all_recommendations"]]
        assert scores == sorted(scores, reverse=True)

    def test_intra_cross_types_present(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2"],
        )

        types = {r["type"] for r in result["all_recommendations"]}
        assert "intra_cluster" in types
        assert "cross_cluster" in types

    def test_no_single_component_dominance(self):
        """Verify rank-norm prevents extreme dominance (e025 criterion)."""
        frontier = _make_frontier_results(n_clusters=5, n_gaps_per_cluster=5, n_bridges=10)
        failure = _make_failure_results(n_clusters=5)
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=["0", "1", "2", "3", "4"],
        )

        # For cross pool (larger n), check that scores are not all identical
        cross_recs = [r for r in result["all_recommendations"] if r["type"] == "cross_cluster"]
        if len(cross_recs) >= 3:
            scores = [r["bridge_score"] for r in cross_recs]
            assert max(scores) > min(scores), "All cross scores identical — rank-norm not effective"

    def test_empty_biology_clusters(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        result = generate_recommendations(
            frontier, failure,
            biology_clusters=[],
        )
        assert result["n_total"] == 0

    def test_default_biology_clusters(self):
        frontier = _make_frontier_results()
        failure = _make_failure_results()
        # Should not raise with defaults
        result = generate_recommendations(frontier, failure)
        assert isinstance(result, dict)


# ── e032: OTR background_terms tests ─────────────────────────────────────────

class TestComputeOtrBackgroundTerms:
    def test_background_terms_reduces_otr(self):
        """When bg has 0 of the top-5 entities, OTR should be 0."""
        from papersift.bridge_recommend import _compute_otr
        entities = ["simulation", "human", "cell", "model", "growth"]
        bg = {"simulation", "human"}
        otr = _compute_otr(entities, background_terms=bg)
        assert otr == 0.4  # 2/5 are in bg

    def test_background_terms_empty_set_gives_zero(self):
        """Empty background_terms set: no entity is background → OTR=0."""
        from papersift.bridge_recommend import _compute_otr
        entities = ["simulation", "human", "cell"]
        otr = _compute_otr(entities, background_terms=set())
        assert otr == 0.0

    def test_compute_otr_type_safety_list_input(self):
        """bg=list is converted to set internally without error."""
        from papersift.bridge_recommend import _compute_otr
        entities = ["simulation", "apoptosis", "signaling"]
        bg_list = ["simulation"]
        otr = _compute_otr(entities, background_terms=bg_list)
        assert otr == pytest.approx(1 / 3, rel=1e-3)

    def test_fallback_when_no_background_terms(self):
        """Without background_terms, falls back to single-token proxy."""
        from papersift.bridge_recommend import _compute_otr
        entities = ["cell cycle", "apoptosis", "p53"]  # "cell cycle"=multi, "apoptosis"/"p53"=single
        otr = _compute_otr(entities)  # no background_terms
        assert otr == pytest.approx(2 / 3, rel=1e-3)

    def test_empty_entities_returns_zero(self):
        from papersift.bridge_recommend import _compute_otr
        assert _compute_otr([], background_terms={"x"}) == 0.0
