"""Entity-based paper clustering layer for PaperSift.

This module provides entity extraction and graph-based clustering without citation data.
It extracts entities from paper titles using rule-based patterns and builds a paper-paper
graph based on shared entities.

Key components:
- STOPWORDS: Set of common words to filter from capitalized term extraction
- ImprovedEntityExtractor: Rule-based entity extraction with word-boundary matching
- EntityLayerBuilder: Builds paper graphs and runs Leiden clustering
"""

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

import igraph as ig
import leidenalg


# Stopwords to filter from capitalized word extraction
STOPWORDS = {
    'the', 'a', 'an', 'of', 'in', 'for', 'to', 'and', 'with', 'on',
    'using', 'towards', 'building', 'based', 'new', 'novel', 'large',
    'comprehensive', 'survey', 'review', 'challenges', 'future',
    'applications', 'current', 'scale', 'from', 'single', 'multi',
    'via', 'through', 'across', 'beyond', 'into', 'between', 'among',
    'how', 'what', 'why', 'when', 'where', 'which', 'who',
    'can', 'may', 'could', 'would', 'should', 'will', 'shall',
    'are', 'is', 'was', 'were', 'been', 'being', 'have', 'has', 'had',
    'its', 'their', 'our', 'your', 'his', 'her',
    'this', 'that', 'these', 'those', 'all', 'any', 'some', 'each',
    'both', 'few', 'more', 'most', 'other', 'such',
    'only', 'just', 'also', 'very', 'quite', 'rather', 'too',
    'not', 'but', 'yet', 'however', 'although', 'though', 'while',
    'model', 'models', 'modeling', 'modelling', 'analysis', 'approach',
    'method', 'methods', 'study', 'studies', 'data', 'learning',
    'cell', 'cells', 'cellular', 'biology', 'biological',
    'protein', 'proteins', 'gene', 'genes', 'genomic', 'molecular',
    'network', 'networks', 'system', 'systems', 'computational',
    'development', 'prediction', 'predictions', 'predictive',
    'inference', 'identification', 'detection', 'classification',
    'generation', 'synthesis', 'integration', 'exploration',
    'understanding', 'insights', 'perspective', 'perspectives',
    'framework', 'platform', 'pipeline', 'tool', 'tools', 'software',
    'enables', 'enabling', 'enabled', 'reveals', 'revealing', 'revealed',
    'improved', 'improving', 'improvement', 'enhanced', 'enhancing',
    'scalable', 'efficient', 'effective', 'robust', 'accurate',
    'high', 'low', 'deep', 'wide', 'long', 'short',
    'resolution', 'level', 'levels', 'type', 'types',
    'based', 'driven', 'guided', 'informed', 'aware',
    # Common title words that get capitalized at start
    'towards', 'beyond', 'within', 'without',
}


class ImprovedEntityExtractor:
    """Rule-based entity extraction with word-boundary matching."""

    def __init__(self):
        # Methods - use word boundaries
        self.methods = [
            'scGPT', 'transformer', 'transformers', 'LSTM', 'CNN', 'RNN', 'GRU',
            'neural network', 'deep learning', 'machine learning', 'ML', 'DL', 'AI',
            'random forest', 'support vector', 'SVM', 'clustering', 'k-means',
            'classification', 'regression', 'ensemble', 'boosting', 'XGBoost',
            'reinforcement learning', 'RL',
            'GAN', 'VAE', 'autoencoder', 'diffusion model',
            'attention mechanism', 'self-attention', 'BERT', 'GPT', 'LLM',
            'foundation model', 'language model', 'embedding', 'representation learning',
            'transfer learning', 'fine-tuning', 'pre-training', 'pretraining',
            'zero-shot', 'few-shot', 'contrastive learning',
            'graph neural network', 'GNN', 'graph convolutional', 'GCN',
            'message passing', 'node embedding',
            'simulation', 'optimization', 'algorithm',
            'RNA-seq', 'scRNA-seq', 'spatial transcriptomics', 'ATAC-seq',
            'ChIP-seq', 'Hi-C', 'CITE-seq', 'multiome',
            'mass spectrometry', 'proteomics', 'metabolomics', 'genomics',
            'CRISPR', 'gene editing', 'perturbation', 'screening', 'Perturb-seq',
            'FBA', 'flux balance analysis', 'constraint-based',
            'ODE', 'differential equation', 'stochastic simulation',
            'Monte Carlo', 'MCMC', 'Bayesian', 'variational inference',
            'dimensionality reduction', 'PCA', 'UMAP', 't-SNE',
            'batch correction', 'data integration', 'imputation',
        ]

        # Organisms - IMPORTANT: use word boundaries to avoid substring matches
        self.organisms = [
            'human', 'mouse', 'yeast', 'zebrafish', 'fruit fly',
            'E. coli', 'Escherichia coli', 'S. cerevisiae', 'Saccharomyces cerevisiae',
            'C. elegans', 'Caenorhabditis elegans',
            'Drosophila', 'Arabidopsis', 'Mycoplasma',
            'bacteria', 'bacterial', 'microbial', 'microbiome',
            'mammalian', 'vertebrate', 'eukaryote', 'eukaryotic', 'prokaryote',
            # Cell types
            'stem cell', 'iPSC', 'ESC', 'T cell', 'B cell', 'NK cell',
            'neuron', 'neuronal', 'immune cell', 'macrophage', 'dendritic cell',
            'cancer cell', 'tumor cell', 'epithelial', 'endothelial',
            'cardiomyocyte', 'hepatocyte', 'fibroblast', 'keratinocyte',
            'organoid', 'spheroid', 'tissue', 'organ',
            # NOTE: removed 'rat' - will add with word boundary only
        ]

        # Concepts
        self.concepts = [
            'gene expression', 'transcription', 'translation', 'regulation',
            'pathway', 'signaling', 'metabolism', 'homeostasis', 'metabolic',
            'differentiation', 'development', 'proliferation', 'apoptosis', 'cell cycle',
            'drug discovery', 'drug design', 'therapeutic', 'biomarker',
            'diagnosis', 'prognosis', 'precision medicine', 'personalized medicine',
            'systems biology', 'computational biology', 'bioinformatics',
            'multi-omics', 'multiomics', 'heterogeneity', 'variability',
            'dynamics', 'evolution', 'adaptation', 'response', 'perturbation response',
            'disease', 'cancer', 'diabetes', 'Alzheimer', 'COVID', 'COVID-19',
            'virtual cell', 'whole-cell', 'in silico', 'digital twin',
            'cell state', 'cell fate', 'cell identity', 'cell atlas',
            'gene regulatory network', 'GRN', 'protein-protein interaction', 'PPI',
            'chromatin accessibility', 'epigenetics', 'epigenome', 'methylation',
        ]

        # Datasets/databases
        self.datasets = [
            'UniProt', 'PDB', 'Protein Data Bank', 'GenBank', 'RefSeq', 'Ensembl',
            'KEGG', 'Reactome', 'Gene Ontology', 'GO',
            'TCGA', 'GTEx', 'UK Biobank', 'GnomAD', 'ClinVar',
            'Human Cell Atlas', 'HCA', 'Allen Brain Atlas', 'ENCODE', 'FANTOM',
            'CellxGene', 'CELLxGENE', 'Single Cell Portal', 'GEO', 'ArrayExpress',
            'Tabula Muris', 'Tabula Sapiens', 'HuBMAP', 'BioGRID',
            'STRING', 'DrugBank', 'ChEMBL', 'PubChem',
            'scRNA-seq atlas', 'cell atlas', 'expression atlas',
        ]

        # Build compiled patterns for word-boundary matching
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for efficient matching."""
        self.method_patterns = []
        for method in self.methods:
            # Escape special chars and add word boundaries
            pattern = re.compile(r'\b' + re.escape(method.lower()) + r'\b', re.IGNORECASE)
            self.method_patterns.append((method, pattern))

        self.organism_patterns = []
        for organism in self.organisms:
            pattern = re.compile(r'\b' + re.escape(organism.lower()) + r'\b', re.IGNORECASE)
            self.organism_patterns.append((organism, pattern))

        # Add 'rat' separately with strict word boundary (not in 'generative', etc.)
        # \brat\b will only match standalone "rat"
        self.organism_patterns.append(('rat', re.compile(r'\brat\b', re.IGNORECASE)))

        self.concept_patterns = []
        for concept in self.concepts:
            pattern = re.compile(r'\b' + re.escape(concept.lower()) + r'\b', re.IGNORECASE)
            self.concept_patterns.append((concept, pattern))

        self.dataset_patterns = []
        for dataset in self.datasets:
            pattern = re.compile(r'\b' + re.escape(dataset.lower()) + r'\b', re.IGNORECASE)
            self.dataset_patterns.append((dataset, pattern))

    def extract_entities(self, title: str, category: str) -> List[Dict[str, str]]:
        """
        Extract entities from title using word-boundary regex matching.

        Args:
            title: Paper title to extract entities from
            category: Paper category (currently unused, for future expansion)

        Returns:
            List of {"name": str, "type": str} dicts
        """
        entities = []
        seen = set()

        # Extract methods
        for method, pattern in self.method_patterns:
            if pattern.search(title):
                key = method.lower()
                if key not in seen:
                    entities.append({"name": method, "type": "METHOD"})
                    seen.add(key)

        # Extract organisms
        for organism, pattern in self.organism_patterns:
            if pattern.search(title):
                key = organism.lower()
                if key not in seen:
                    entities.append({"name": organism, "type": "ORGANISM"})
                    seen.add(key)

        # Extract concepts
        for concept, pattern in self.concept_patterns:
            if pattern.search(title):
                key = concept.lower()
                if key not in seen:
                    entities.append({"name": concept, "type": "CONCEPT"})
                    seen.add(key)

        # Extract datasets
        for dataset, pattern in self.dataset_patterns:
            if pattern.search(title):
                key = dataset.lower()
                if key not in seen:
                    entities.append({"name": dataset, "type": "DATASET"})
                    seen.add(key)

        # Extract capitalized terms (acronyms/proper nouns) with stopword filtering
        words = re.findall(r'\b[A-Z][A-Za-z0-9-]*\b', title)
        for word in words:
            word_lower = word.lower()
            # Filter: length >= 3, not a stopword, not already seen
            if len(word) >= 3 and word_lower not in seen and word_lower not in STOPWORDS:
                # Guess type based on context
                if any(kw in word_lower for kw in ['seq', 'omics', 'data', 'atlas', 'bank']):
                    entities.append({"name": word, "type": "DATASET"})
                elif word.isupper() and len(word) <= 6:
                    # Short all-caps likely method/tool acronym
                    entities.append({"name": word, "type": "METHOD"})
                else:
                    entities.append({"name": word, "type": "METHOD"})
                seen.add(word_lower)

        return entities


class EntityLayerBuilder:
    """Build entity-based paper clustering.

    Supports two modes:
    - Title-only (default): Extract entities from paper titles using rule-based patterns
    - Title + Topics (--use-topics): Also include OpenAlex topics as entities for richer clustering
    """

    def __init__(self, use_topics: bool = False):
        """
        Initialize the entity layer builder.

        Args:
            use_topics: If True, also use OpenAlex topics from paper['topics'] as entities.
                       Requires enriched paper data with 'topics' field.
        """
        self.extractor = ImprovedEntityExtractor()
        self.use_topics = use_topics
        self.graph: Optional[ig.Graph] = None
        self._paper_entities: Dict[str, set] = {}  # doi -> set(entity_names)
        self._dois: List[str] = []

    def _extract_entities_for_paper(self, paper: Dict[str, Any]) -> Set[str]:
        """
        Extract entities from a paper, optionally including topics.

        Args:
            paper: Paper dict with 'title', optional 'category', optional 'topics'

        Returns:
            Set of lowercase entity names
        """
        # Rule-based entities from title
        entities = self.extractor.extract_entities(
            paper['title'],
            paper.get('category', '')
        )
        entity_set = {e['name'].lower() for e in entities}

        # Add OpenAlex topics if enabled
        if self.use_topics:
            for topic in paper.get('topics', []):
                # Add topic display name
                display_name = topic.get('display_name', '')
                if display_name:
                    entity_set.add(display_name.lower())
                # Add subfield for broader coverage
                subfield = topic.get('subfield', {}).get('display_name', '')
                if subfield:
                    entity_set.add(subfield.lower())

        return entity_set

    def build_from_papers(self, papers: List[Dict[str, Any]]) -> ig.Graph:
        """
        Build paper-paper graph via shared entities.

        Algorithm:
        1. Extract entities from each paper (title + optional topics)
        2. For each paper pair: edge weight = |shared entities|
        3. Create igraph with DOIs as node attributes

        Args:
            papers: List of paper dicts with 'doi' and 'title' fields

        Returns:
            igraph.Graph with DOI vertex attributes and weight edge attributes
        """
        # Step 1: Extract entities
        self._dois = []
        self._paper_entities = {}

        for paper in papers:
            doi = paper['doi']
            self._dois.append(doi)
            self._paper_entities[doi] = self._extract_entities_for_paper(paper)

        # Step 2: Compute edges
        n = len(self._dois)
        edges = []
        weights = []

        for i in range(n):
            doi1 = self._dois[i]
            ents1 = self._paper_entities[doi1]
            for j in range(i + 1, n):
                doi2 = self._dois[j]
                ents2 = self._paper_entities[doi2]
                shared = len(ents1 & ents2)
                if shared > 0:
                    edges.append((i, j))
                    weights.append(shared)

        # Step 3: Create igraph
        self.graph = ig.Graph(n=n, edges=edges, directed=False)
        self.graph.vs['doi'] = self._dois
        self.graph.es['weight'] = weights

        return self.graph

    def run_leiden(
        self,
        resolution: float = 1.0,
        seed: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Run Leiden clustering with deterministic seed.

        Args:
            resolution: Higher = more clusters
            seed: Random seed for reproducibility

        Returns:
            {doi: cluster_id}
        """
        if self.graph is None:
            raise ValueError("Call build_from_papers() first")

        partition = leidenalg.find_partition(
            self.graph,
            leidenalg.RBConfigurationVertexPartition,
            resolution_parameter=resolution,
            weights='weight',
            seed=seed
        )

        return {
            self.graph.vs[i]['doi']: partition.membership[i]
            for i in range(len(self.graph.vs))
        }

    def get_cluster_summary(self, clusters: Dict[str, int]) -> List[Dict]:
        """
        Generate summary for each cluster.

        Args:
            clusters: Mapping of DOI to cluster_id from run_leiden()

        Returns:
            List of cluster summaries, sorted by size (largest first):
            {
                "cluster_id": int,
                "size": int,
                "dois": List[str],
                "top_entities": List[str]  # Most common entities (top 10)
            }
        """
        # Group by cluster
        cluster_members = defaultdict(list)
        for doi, cid in clusters.items():
            cluster_members[cid].append(doi)

        summaries = []
        for cid, dois in sorted(cluster_members.items()):
            # Count entities in this cluster
            entity_counts = defaultdict(int)
            for doi in dois:
                for ent in self._paper_entities.get(doi, []):
                    entity_counts[ent] += 1

            top_entities = [
                ent for ent, _ in sorted(
                    entity_counts.items(),
                    key=lambda x: -x[1]
                )[:10]
            ]

            summaries.append({
                "cluster_id": cid,
                "size": len(dois),
                "dois": dois,
                "top_entities": top_entities
            })

        return sorted(summaries, key=lambda x: -x['size'])

    # ===== Citation-alternative functions =====

    def find_hub_papers(self, top_k: int = 10) -> List[Dict]:
        """
        Find Entity Hub Papers (Citation Major Paper alternative).

        Hub Score = weighted degree = sum of shared entities with all neighbors
        High hub score = paper shares many entities with many other papers

        Args:
            top_k: Number of top hub papers to return

        Returns:
            List of hub paper dicts (sorted by hub_score descending):
            {
                "doi": str,
                "hub_score": int,
                "entities": List[str] (top 10 entities)
            }
        """
        if self.graph is None:
            raise ValueError("Call build_from_papers() first")

        # Weighted degree = sum of edge weights
        scores = self.graph.strength(weights='weight')

        ranked = sorted(
            zip(self._dois, scores),
            key=lambda x: -x[1]
        )[:top_k]

        return [
            {
                'doi': doi,
                'hub_score': int(score),
                'entities': list(self._paper_entities.get(doi, []))[:10]
            }
            for doi, score in ranked
        ]

    def find_papers_by_entity(self, entity_name: str) -> List[str]:
        """
        Find papers containing a specific entity (Seed Paper alternative).

        Args:
            entity_name: Entity to search for (case-insensitive)

        Returns:
            List of DOIs containing this entity
        """
        entity_lower = entity_name.lower()
        return [
            doi for doi, entities in self._paper_entities.items()
            if entity_lower in entities
        ]

    def expand_from_seed(self, seed_doi: str, hops: int = 1) -> Set[str]:
        """
        Expand from seed paper via shared entities (Citation stream alternative).

        Like citation forward/backward traversal, but using entity connections.

        Args:
            seed_doi: Starting paper DOI
            hops: Number of expansion hops (1 = direct neighbors only)

        Returns:
            Set of DOIs reachable within hops (including seed)
        """
        if self.graph is None:
            raise ValueError("Call build_from_papers() first")

        if seed_doi not in self._dois:
            raise ValueError(f"Seed DOI not in graph: {seed_doi}")

        visited = {seed_doi}
        current = {seed_doi}

        for _ in range(hops):
            next_layer = set()
            for doi in current:
                idx = self._dois.index(doi)
                neighbors = self.graph.neighbors(idx)
                for n_idx in neighbors:
                    n_doi = self.graph.vs[n_idx]['doi']
                    if n_doi not in visited:
                        next_layer.add(n_doi)
                        visited.add(n_doi)
            current = next_layer
            if not current:
                break

        return visited

    def entity_stream(
        self,
        start_doi: str,
        strategy: str = 'strongest',
        max_hops: int = 10
    ) -> List[str]:
        """
        Follow entity connections like citation stream traversal.

        Strategies:
        - 'strongest': Follow edge with highest weight (most shared entities)
        - 'diverse': Follow edge introducing most new entities

        Args:
            start_doi: Starting paper DOI
            strategy: 'strongest' or 'diverse'
            max_hops: Maximum path length

        Returns:
            Ordered path of DOIs from start
        """
        if self.graph is None:
            raise ValueError("Call build_from_papers() first")

        path = [start_doi]
        visited = {start_doi}
        current = start_doi

        for _ in range(max_hops):
            idx = self._dois.index(current)
            neighbors = self.graph.neighbors(idx)

            if not neighbors:
                break

            candidates = []
            for n_idx in neighbors:
                n_doi = self.graph.vs[n_idx]['doi']
                if n_doi in visited:
                    continue

                if strategy == 'strongest':
                    eid = self.graph.get_eid(idx, n_idx)
                    score = self.graph.es[eid]['weight']
                elif strategy == 'diverse':
                    my_ents = self._paper_entities[current]
                    their_ents = self._paper_entities[n_doi]
                    score = len(their_ents - my_ents)
                else:
                    score = 1

                candidates.append((n_doi, score))

            if not candidates:
                break

            next_doi = max(candidates, key=lambda x: x[1])[0]
            path.append(next_doi)
            visited.add(next_doi)
            current = next_doi

        return path
