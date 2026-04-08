"""Automatic sub-clustering trigger and resolution sweep for PaperSift.

Phase B of e031: determine when a cluster should be sub-divided and find
the optimal Leiden resolution via sweep.
"""
from __future__ import annotations

import warnings
from typing import Optional


def should_subcluster(
    cluster_size: int,
    entity_density: float,
    max_bridge_gen_fraction: float,
) -> bool:
    """Return True if a cluster warrants automatic sub-clustering.

    Trigger conditions (any):
      - cluster_size > 200 AND entity_density < 0.5 (sparse entity coverage)
      - cluster_size > 200 AND max_bridge_gen_fraction > 0.7 (dominated by
        domain-general bridge terms)

    Args:
        cluster_size: Number of papers in the cluster.
        entity_density: Mean fraction of entities per paper (0-1).
        max_bridge_gen_fraction: Fraction of top-5 bridge entities that are
            domain-general (OTR from bridge_recommend output).

    Returns:
        True if the cluster should be sub-divided.
    """
    if cluster_size <= 200:
        return False
    return entity_density < 0.5 or max_bridge_gen_fraction > 0.7


def sweep_resolution(
    papers: list[dict],
    cluster_id,
    clusters: dict,
    resolutions: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0),
    seeds: tuple[int, ...] = (42, 43, 44),
    target_avg_size: int = 60,
    min_stability: float = 0.80,
    use_topics: bool = False,
    domain_vocab: Optional[dict] = None,
) -> tuple[float, dict[str, str]]:
    """Find optimal Leiden resolution for sub-clustering a cluster.

    Sweeps resolutions x seeds (default 4x3=12 Leiden runs). Selects the
    smallest resolution where avg_major_size <= target_avg_size AND
    5-seed pairwise ARI mean >= min_stability.

    Partition type: RBConfigurationVertexPartition (matches entity_layer.py).
    See entity_layer.py:383-391.

    If no resolution achieves the target, extends sweep to {3.5, 4.0}. If
    still failing, logs a warning and returns the highest-resolution result.

    Args:
        papers: Full list of paper dicts.
        cluster_id: The cluster to sub-divide.
        clusters: Existing DOI -> cluster_id mapping.
        resolutions: Resolution values to sweep.
        seeds: Seeds for stability measurement.
        target_avg_size: Maximum acceptable average sub-cluster size.
        min_stability: Minimum mean pairwise ARI across seeds.
        use_topics: Passed to sub_cluster().
        domain_vocab: Passed to sub_cluster().

    Returns:
        Tuple of (selected_resolution, best_partition) where best_partition
        maps DOI -> hierarchical cluster ID string.

    Raises:
        ValueError: If cluster_id is not found or has < 2 papers.
    """
    from papersift.embedding import sub_cluster

    def _pairwise_ari(partitions: list[dict[str, str]]) -> float:
        """Mean pairwise ARI across all partition pairs."""
        try:
            from sklearn.metrics import adjusted_rand_score
        except ImportError:
            return 1.0  # cannot compute, assume stable

        if len(partitions) < 2:
            return 1.0

        dois = sorted(partitions[0].keys())
        aris = []
        for i in range(len(partitions)):
            for j in range(i + 1, len(partitions)):
                labels_i = [partitions[i].get(d, "") for d in dois]
                labels_j = [partitions[j].get(d, "") for d in dois]
                aris.append(adjusted_rand_score(labels_i, labels_j))
        return float(sum(aris) / len(aris)) if aris else 1.0

    def _try_resolutions(res_list):
        for res in res_list:
            partitions = []
            for seed in seeds:
                part = sub_cluster(
                    papers, cluster_id, clusters,
                    resolution=res, seed=seed,
                    singleton_warn=False,
                    use_topics=use_topics,
                    domain_vocab=domain_vocab,
                )
                partitions.append(part)

            # Compute avg major sub-cluster size
            best_part = partitions[0]
            from collections import Counter
            sub_sizes = Counter(best_part.values())
            unique_subs = [k for k in sub_sizes if "." in str(k)]
            if not unique_subs:
                # Singleton fallback — skip this resolution
                continue
            avg_size = sum(sub_sizes[k] for k in unique_subs) / len(unique_subs)

            # Compute stability across seeds
            stability = _pairwise_ari(partitions)

            if avg_size <= target_avg_size and stability >= min_stability:
                return res, best_part

        return None, None

    # Primary sweep
    best_res, best_part = _try_resolutions(resolutions)
    if best_res is not None:
        return best_res, best_part

    # Fallback sweep
    fallback = (3.5, 4.0)
    best_res, best_part = _try_resolutions(fallback)
    if best_res is not None:
        return best_res, best_part

    # Last resort: highest resolution
    warnings.warn(
        f"sweep_resolution: no resolution achieved target for cluster {cluster_id}. "
        "Using highest resolution result."
    )
    final_res = max(resolutions + fallback)
    final_part = sub_cluster(
        papers, cluster_id, clusters,
        resolution=final_res, seed=seeds[0],
        singleton_warn=False,
        use_topics=use_topics,
        domain_vocab=domain_vocab,
    )
    return final_res, final_part


def check_resolution_plateau(
    graph,
    selected_resolution: float,
    resolution_range: tuple[float, float] = (0.5, 4.0),
) -> dict:
    """Check if selected_resolution falls inside a plateau in the resolution profile.

    Runs leidenalg.Optimiser.resolution_profile() and detects flat regions
    (consecutive resolution steps with same community count).

    Args:
        graph: igraph.Graph object (from EntityLayerBuilder.graph).
        selected_resolution: The resolution chosen by sweep_resolution().
        resolution_range: Range for resolution_profile sweep.

    Returns:
        Dict with keys: 'in_plateau' (bool), 'plateau_range' (tuple|None),
        'community_profile' (list of (resolution, n_communities)).
    """
    try:
        import leidenalg
    except ImportError:
        return {"in_plateau": False, "plateau_range": None, "community_profile": []}

    try:
        optimiser = leidenalg.Optimiser()
        profile = optimiser.resolution_profile(
            graph,
            leidenalg.RBConfigurationVertexPartition,
            resolution_range=resolution_range,
        )
    except Exception as e:
        warnings.warn(f"check_resolution_plateau failed: {e}")
        return {"in_plateau": False, "plateau_range": None, "community_profile": []}

    community_profile = [(p.resolution_parameter, len(p)) for p in profile]

    # Detect plateaus: consecutive steps with same community count
    in_plateau = False
    plateau_range = None
    for i in range(len(community_profile) - 1):
        res_i, n_i = community_profile[i]
        res_next, n_next = community_profile[i + 1]
        if n_i == n_next:
            if selected_resolution >= res_i and selected_resolution <= res_next:
                in_plateau = True
                plateau_range = (res_i, res_next)
                break

    if in_plateau:
        import logging
        logging.getLogger(__name__).info(
            f"Resolution {selected_resolution} is inside plateau "
            f"{plateau_range} (community count stable) — HIGH confidence"
        )
    else:
        warnings.warn(
            f"Resolution {selected_resolution} is outside detected plateaus — "
            "result may be less stable"
        )

    return {
        "in_plateau": in_plateau,
        "plateau_range": plateau_range,
        "community_profile": community_profile,
    }
