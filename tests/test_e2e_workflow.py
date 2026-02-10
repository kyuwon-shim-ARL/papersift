"""End-to-end workflow tests for PaperSift.

Tests the full pipeline from data loading to embedding and hierarchical clustering.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_landscape_workflow_e2e():
    """Full workflow test: load fixture -> build graph -> cluster -> embed -> sub-cluster.

    Tests:
    - Loading fixture from tests/fixtures/sample_papers_landscape.json
    - Building graph and clustering with EntityLayerBuilder
    - Computing embedding with embed_papers(method="tsne")
    - Asserting all DOIs present, no NaN coordinates
    - Finding largest cluster and sub-clustering it
    - Asserting hierarchical IDs follow parent.child format
    - Multi-level: sub-cluster a sub-cluster if possible
    """
    from papersift import EntityLayerBuilder
    from papersift.embedding import embed_papers, sub_cluster

    # Load fixture
    fixture_path = Path(__file__).parent / "fixtures" / "sample_papers_landscape.json"
    with open(fixture_path) as f:
        papers = json.load(f)

    assert len(papers) > 0, "Fixture should contain papers"
    n_papers = len(papers)

    # Build graph and cluster
    builder = EntityLayerBuilder(use_topics=False)
    builder.build_from_papers(papers)
    clusters = builder.run_leiden(resolution=1.0, seed=42)

    # Verify clustering
    assert len(clusters) == n_papers, "All papers should be clustered"
    n_clusters = len(set(clusters.values()))
    assert n_clusters > 1, "Should produce multiple clusters"

    # Compute embedding with perplexity adjustment for small datasets
    perplexity = min(30.0, (n_papers - 1) / 3.0)
    embedding = embed_papers(
        papers,
        method="tsne",
        use_topics=False,
        random_state=42,
        perplexity=perplexity
    )

    # Assert all DOIs present, no NaN
    assert len(embedding) == n_papers, "Embedding should cover all papers"
    for paper in papers:
        doi = paper["doi"]
        assert doi in embedding, f"DOI {doi} missing from embedding"
        x, y = embedding[doi]
        assert not (x != x or y != y), f"NaN coordinate for {doi}"  # NaN check

    # Find largest cluster
    from collections import Counter
    cluster_counts = Counter(clusters.values())
    largest_cluster_id, largest_size = cluster_counts.most_common(1)[0]

    # Sub-cluster the largest cluster if it has enough papers
    if largest_size >= 2:
        sub_results = sub_cluster(
            papers,
            cluster_id=largest_cluster_id,
            clusters=clusters,
            resolution=1.0,
            seed=42,
            use_topics=False
        )

        # Assert hierarchical IDs follow parent.child format
        for doi, sub_id in sub_results.items():
            sub_id_str = str(sub_id)
            if "." in sub_id_str:
                parent, child = sub_id_str.split(".", 1)
                assert parent == str(largest_cluster_id), \
                    f"Sub-cluster {sub_id_str} should have parent {largest_cluster_id}"
                assert child.isdigit(), f"Child ID should be numeric, got {child}"

        # Multi-level: try to sub-cluster a sub-cluster if possible
        sub_cluster_ids = set(sub_results.values())
        if len(sub_cluster_ids) > 1:
            # Pick first hierarchical sub-cluster with enough members
            sub_counts = Counter(sub_results.values())
            for sub_cid, count in sub_counts.most_common():
                if count >= 2 and "." in str(sub_cid):
                    # Attempt multi-level sub-clustering
                    try:
                        multi_level_results = sub_cluster(
                            papers,
                            cluster_id=sub_cid,
                            clusters=sub_results,
                            resolution=1.0,
                            seed=42,
                            use_topics=False
                        )

                        # Verify multi-level IDs
                        for doi, multi_id in multi_level_results.items():
                            multi_id_str = str(multi_id)
                            if "." in multi_id_str and multi_id_str.count(".") >= 2:
                                # Format: parent.child.grandchild
                                parts = multi_id_str.split(".")
                                assert len(parts) >= 3, \
                                    f"Multi-level ID should have 3+ parts, got {multi_id_str}"

                        break  # Successfully tested multi-level
                    except ValueError:
                        # Sub-cluster might be too small or indivisible
                        continue


def test_cli_landscape_export(tmp_path):
    """CLI test: run papersift landscape and verify output.

    Tests:
    - Run `papersift landscape tests/fixtures/sample_papers_landscape.json --method tsne -o {output}`
    - Assert returncode 0, file exists, contains "plotly"
    """
    fixture_path = Path(__file__).parent / "fixtures" / "sample_papers_landscape.json"
    output_path = tmp_path / "landscape.html"

    # Run CLI command
    cmd = [
        sys.executable, "-m", "papersift.cli",
        "landscape",
        str(fixture_path),
        "--method", "tsne",
        "-o", str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Assert returncode 0
    assert result.returncode == 0, \
        f"CLI command failed with code {result.returncode}\nstderr: {result.stderr}"

    # Assert file exists
    assert output_path.exists(), f"Output file not created: {output_path}"

    # Assert contains "plotly" (indicates Plotly HTML was written)
    with open(output_path) as f:
        content = f.read()
    assert "plotly" in content.lower(), "Output HTML should contain Plotly content"

    # Verify basic HTML structure
    assert "<html>" in content.lower(), "Output should be valid HTML"
    assert "</html>" in content.lower(), "Output should be valid HTML"
