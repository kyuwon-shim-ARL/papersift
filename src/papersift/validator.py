"""
Validator module for entity-based clustering validation using citation data.

Combines CrossValidator + citation-based confidence calculation.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from collections import defaultdict
import numpy as np
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
import igraph as ig
import leidenalg


@dataclass
class ValidationReport:
    """Validation results when citation data is available."""
    ari: float                          # Adjusted Rand Index
    nmi: float                          # Normalized Mutual Information
    num_papers: int
    num_entity_clusters: int
    num_citation_clusters: int
    confidence_scores: Dict[str, float]  # doi -> confidence
    confidence_summary: Dict[str, int]   # high/medium/low counts
    interpretation: str


class ClusterValidator:
    """Validate entity clusters using citation data."""

    def __init__(
        self,
        entity_clusters: Dict[str, int],
        papers: List[Dict[str, Any]]
    ):
        """
        Args:
            entity_clusters: {doi: cluster_id} from EntityLayerBuilder
            papers: Original papers with 'doi' and optional 'referenced_works'
        """
        self.entity_clusters = entity_clusters
        self.papers = papers

        # Build citation lookup
        self.paper_dois = {p['doi'] for p in papers}
        self.citations = {}  # doi -> set(cited_dois in collection)

        for paper in papers:
            doi = paper['doi']
            refs = paper.get('referenced_works', [])
            # Only keep citations within our collection
            self.citations[doi] = {
                ref for ref in refs if ref in self.paper_dois
            }

        self._citation_clusters: Optional[Dict[str, int]] = None

    def has_citation_data(self) -> bool:
        """Check if there's enough citation data for validation."""
        total_edges = sum(len(refs) for refs in self.citations.values())
        return total_edges >= 10  # Minimum threshold

    def compute_citation_clusters(self, resolution: float = 1.0) -> Dict[str, int]:
        """
        Run Leiden on citation graph for comparison.

        Returns trivial clustering if insufficient citation data.
        """
        dois = list(self.paper_dois)
        doi_to_idx = {doi: i for i, doi in enumerate(dois)}

        # Build edges
        edges = []
        for doi, refs in self.citations.items():
            i = doi_to_idx[doi]
            for ref in refs:
                j = doi_to_idx[ref]
                edges.append((i, j))

        if not edges:
            # No edges: all papers in one cluster
            return {doi: 0 for doi in dois}

        g = ig.Graph(n=len(dois), edges=edges, directed=False)
        g.vs['doi'] = dois

        partition = leidenalg.find_partition(
            g,
            leidenalg.RBConfigurationVertexPartition,
            resolution_parameter=resolution,
            seed=0
        )

        self._citation_clusters = {
            dois[i]: partition.membership[i]
            for i in range(len(dois))
        }
        return self._citation_clusters

    def compute_ari(self) -> float:
        """Adjusted Rand Index between entity and citation clusters."""
        if self._citation_clusters is None:
            self.compute_citation_clusters()

        common = set(self.entity_clusters.keys()) & set(self._citation_clusters.keys())
        if len(common) < 2:
            return 0.0

        labels_e = [self.entity_clusters[d] for d in common]
        labels_c = [self._citation_clusters[d] for d in common]

        return adjusted_rand_score(labels_e, labels_c)

    def compute_confidence(self) -> Dict[str, float]:
        """
        Compute confidence for each paper's cluster assignment.

        Confidence = fraction of same-cluster papers that are citation-connected.

        High confidence: Paper's cluster members cite each other
        Low confidence: Paper's cluster members have no citation links
        """
        confidence = {}

        # Group papers by entity cluster
        cluster_members = defaultdict(set)
        for doi, cid in self.entity_clusters.items():
            cluster_members[cid].add(doi)

        for doi, cid in self.entity_clusters.items():
            same_cluster = cluster_members[cid] - {doi}
            if not same_cluster:
                confidence[doi] = 1.0  # Singleton
                continue

            # How many cluster members are citation-connected to this paper?
            my_citations = self.citations.get(doi, set())
            connected = 0
            for other in same_cluster:
                other_citations = self.citations.get(other, set())
                if doi in other_citations or other in my_citations:
                    connected += 1

            confidence[doi] = connected / len(same_cluster)

        return confidence

    def generate_report(self) -> ValidationReport:
        """Generate full validation report."""
        if not self.has_citation_data():
            # Return minimal report
            return ValidationReport(
                ari=0.0,
                nmi=0.0,
                num_papers=len(self.entity_clusters),
                num_entity_clusters=len(set(self.entity_clusters.values())),
                num_citation_clusters=0,
                confidence_scores={},
                confidence_summary={'insufficient_data': len(self.entity_clusters)},
                interpretation="Insufficient citation data for validation."
            )

        # Compute citation clusters
        self.compute_citation_clusters()

        # Compute metrics
        ari = self.compute_ari()

        common = set(self.entity_clusters.keys()) & set(self._citation_clusters.keys())
        labels_e = [self.entity_clusters[d] for d in common]
        labels_c = [self._citation_clusters[d] for d in common]
        nmi = normalized_mutual_info_score(labels_e, labels_c)

        # Compute confidence
        confidence = self.compute_confidence()

        # Categorize confidence
        high = sum(1 for c in confidence.values() if c >= 0.5)
        medium = sum(1 for c in confidence.values() if 0.2 <= c < 0.5)
        low = sum(1 for c in confidence.values() if c < 0.2)

        # Interpretation
        if ari > 0.5:
            interp = "Strong agreement: Entity clusters align well with citation patterns."
        elif ari > 0.2:
            interp = "Moderate agreement: Entity and citation views capture partially overlapping structure."
        else:
            interp = "Weak agreement: Entity and citation views capture different aspects of the collection."

        return ValidationReport(
            ari=ari,
            nmi=nmi,
            num_papers=len(self.entity_clusters),
            num_entity_clusters=len(set(self.entity_clusters.values())),
            num_citation_clusters=len(set(self._citation_clusters.values())),
            confidence_scores=confidence,
            confidence_summary={'high': high, 'medium': medium, 'low': low},
            interpretation=interp
        )
