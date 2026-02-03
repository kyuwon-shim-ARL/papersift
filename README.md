# PaperSift: Entity-Based Paper Clustering

Cluster academic papers by shared entities (methods, organisms, concepts, datasets) extracted from paper titles using rule-based patterns and graph clustering.

## Overview

PaperSift discovers research themes and connections through entity-based analysis rather than citation data. It extracts structured information (methods, organisms, concepts, datasets) from paper titles, builds a paper-paper network based on shared entities, and applies Leiden clustering for community detection.

**Key Features:**
- Rule-based entity extraction from titles (no LLM required)
- Deterministic results with configurable random seed
- Fast clustering: 748 papers in under 30 seconds
- Optional citation-based validation
- Hub paper discovery (most connected papers)
- Entity-based paper search and filtering
- Stream traversal following entity connections

## Quick Start

Install and cluster papers in three commands:

```bash
pip install -e /path/to/papersift
papersift cluster papers.json -o results/
cat results/communities.json
```

This creates two output files:
- `clusters.json`: Paper-to-cluster mapping
- `communities.json`: Cluster summaries with top entities

## Installation

PaperSift requires Python 3.11+. Install from source:

```bash
pip install -e /path/to/.claude/skills/papersift/
```

Or with validation support:

```bash
pip install -e /path/to/.claude/skills/papersift/[validation]
```

**Dependencies:** igraph, leidenalg, numpy, scikit-learn

## CLI Reference

### cluster - Group papers by shared entities

```bash
papersift cluster INPUT -o OUTPUT [options]
```

**Arguments:**
- `INPUT`: Path to JSON file with papers list
- `-o, --output`: Output directory for results (required)

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--resolution` | float | 1.0 | Leiden resolution parameter (higher = more clusters) |
| `--seed` | int | 42 | Random seed for reproducibility |
| `--use-topics` | flag | off | Include OpenAlex topics as additional entities |
| `--validate` | flag | off | Validate clusters using citation data |

**Examples:**

```bash
# Basic clustering with title entities only
papersift cluster papers.json -o results/

# Fine-grained clustering (more clusters)
papersift cluster papers.json -o results/ --resolution 2.0

# Coarse-grained clustering (fewer clusters)
papersift cluster papers.json -o results/ --resolution 0.5

# With OpenAlex enrichment
papersift cluster enriched_papers.json -o results/ --use-topics

# With citation validation
papersift cluster papers.json -o results/ --validate

# Reproducible run with explicit seed
papersift cluster papers.json -o results/ --seed 123
```

### find - Discover hub papers and search by entity

```bash
papersift find INPUT [--hubs K | --entity NAME] [options]
```

**Arguments:**
- `INPUT`: Path to JSON file with papers list

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--hubs N` | int | Find top N most-connected papers |
| `--entity NAME` | str | Find papers containing this entity |
| `--use-topics` | flag | Include OpenAlex topics in entity search |
| `--format` | choice | Output format: `table` (default) or `json` |

**Examples:**

```bash
# Find 20 hub papers
papersift find papers.json --hubs 20

# Find papers about transformers
papersift find papers.json --entity "transformer"

# Find papers about machine learning
papersift find papers.json --entity "deep learning"

# Search with OpenAlex topics
papersift find enriched.json --entity "neural networks" --use-topics
```

**Hub Score:** Sum of shared entities with all connected papers. Higher score = central position in the research landscape.

### stream - Follow entity connections from a seed paper

```bash
papersift stream INPUT --seed DOI [options]
```

**Arguments:**
- `INPUT`: Path to JSON file with papers list
- `--seed DOI`: Starting paper DOI (required)

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--hops` | int | 5 | Maximum path length to follow |
| `--strategy` | choice | strongest | Path selection: `strongest` (most shared entities) or `diverse` (most new entities) |
| `--expand` | flag | off | Use breadth-first expansion instead of stream path |
| `--use-topics` | flag | off | Include OpenAlex topics in entity matching |

**Examples:**

```bash
# Trace strongest entity connections from a paper
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --hops 5

# Diversified path discovering new entities
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --strategy diverse --hops 10

# All reachable papers within 3 hops
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --expand --hops 3

# With topic enrichment
papersift stream enriched.json --seed "https://doi.org/10.1038/nature12373" --use-topics
```

**Strategies:**
- `strongest`: Follow the edge with highest weight (most shared entities). Finds tightly connected research areas.
- `diverse`: Follow the edge introducing the most new entities. Explores breadth of the research landscape.

## Output Files

### clusters.json
DOI-to-cluster mapping (JSON object):
```json
{
  "https://doi.org/10.1038/nature12373": 5,
  "https://doi.org/10.1038/nbt.2488": 5,
  "https://doi.org/10.1016/j.cell.2014.05.010": 3
}
```

### communities.json
Cluster summaries sorted by size (JSON array):
```json
[
  {
    "cluster_id": 5,
    "size": 107,
    "dois": [
      "https://doi.org/10.1038/nature12373",
      "https://doi.org/10.1038/nbt.2488"
    ],
    "top_entities": [
      "deep learning",
      "neural network",
      "transformer",
      "LSTM",
      "CNN"
    ]
  }
]
```

**Fields:**
- `cluster_id`: Integer cluster identifier
- `size`: Number of papers in cluster
- `dois`: List of paper DOIs
- `top_entities`: Most common entities (up to 10), sorted by frequency

### validation_report.json
(Only when `--validate` flag is used with citation data)

```json
{
  "ari": 0.42,
  "nmi": 0.58,
  "num_papers": 748,
  "num_entity_clusters": 139,
  "num_citation_clusters": 156,
  "confidence_summary": {
    "high": 412,
    "medium": 198,
    "low": 138
  },
  "interpretation": "Moderate agreement: Entity and citation views capture partially overlapping structure."
}
```

**Metrics:**
- **ARI** (Adjusted Rand Index): -1 to 1, where 1 = perfect agreement, 0 = random
- **NMI** (Normalized Mutual Information): 0 to 1, where 1 = perfect agreement, 0 = no agreement
- **Interpretation:** Human-readable summary of agreement level

### confidence.json
Per-paper confidence scores (only with `--validate` and citation data):
```json
{
  "https://doi.org/10.1038/nature12373": 0.73,
  "https://doi.org/10.1038/nbt.2488": 0.65,
  "https://doi.org/10.1016/j.cell.2014.05.010": 0.22
}
```

**Confidence Score:** For each paper, the fraction of same-cluster papers that are citation-connected. Range: [0, 1].
- 1.0 = Singleton cluster or all cluster members are cited
- 0.5 = Half of cluster members are citation-connected
- 0.0 = No citation links within cluster

## Python API

### EntityLayerBuilder

Main class for entity extraction, graph construction, and clustering.

```python
from papersift import EntityLayerBuilder

# Initialize with title-only entity extraction
builder = EntityLayerBuilder()

# Or with OpenAlex topics (requires enriched data)
builder = EntityLayerBuilder(use_topics=True)

# Build entity graph from papers
graph = builder.build_from_papers(papers)

# Run Leiden clustering
clusters = builder.run_leiden(resolution=1.0, seed=42)

# Get cluster summaries
summaries = builder.get_cluster_summary(clusters)

# Find hub papers
hubs = builder.find_hub_papers(top_k=10)

# Search for papers by entity
papers_with_transformer = builder.find_papers_by_entity("transformer")

# Expand from seed paper
reachable = builder.expand_from_seed("https://doi.org/10.1038/nature12373", hops=2)

# Stream following entity connections
path = builder.entity_stream(
    "https://doi.org/10.1038/nature12373",
    strategy="strongest",
    max_hops=10
)
```

### Key Methods

**`build_from_papers(papers: List[Dict]) -> igraph.Graph`**
- Extracts entities from each paper's title (and topics if enabled)
- Creates edges between papers sharing entities (weight = number of shared entities)
- Returns igraph.Graph with DOI vertex attributes and weight edge attributes

**`run_leiden(resolution: float = 1.0, seed: int | None = None) -> Dict[str, int]`**
- Runs Leiden modularity optimization for community detection
- Returns mapping of DOI to cluster_id
- Deterministic when seed is provided

**`get_cluster_summary(clusters: Dict[str, int]) -> List[Dict]`**
- Summarizes each cluster with size, member DOIs, and top entities
- Returns list sorted by cluster size (largest first)

**`find_hub_papers(top_k: int = 10) -> List[Dict]`**
- Returns papers with highest weighted degree (most entity connections)
- Hub score = sum of shared entities with all neighbors
- Useful for finding central papers in research area

**`find_papers_by_entity(entity_name: str) -> List[str]`**
- Case-insensitive entity search
- Returns list of DOIs containing entity

**`expand_from_seed(seed_doi: str, hops: int = 1) -> Set[str]`**
- Breadth-first expansion through entity connections
- Returns all papers reachable within N hops

**`entity_stream(start_doi: str, strategy: str = 'strongest', max_hops: int = 10) -> List[str]`**
- Traces path following entity connections
- `strongest` strategy: Follow highest-weight edges
- `diverse` strategy: Follow edges introducing most new entities
- Returns ordered list of DOIs

### ClusterValidator

Optional validation using citation data.

```python
from papersift import ClusterValidator

validator = ClusterValidator(clusters, papers)

# Check if citation data is sufficient
if validator.has_citation_data():
    # Generate full validation report
    report = validator.generate_report()
    print(f"ARI: {report.ari:.3f}")
    print(f"Confidence: {report.confidence_summary}")
    print(report.interpretation)
else:
    print("Insufficient citation data for validation")
```

### Complete Workflow Example

```python
import json
from papersift import EntityLayerBuilder, ClusterValidator

# Load papers
with open('papers.json') as f:
    data = json.load(f)
papers = data.get('papers', data)

# Build and cluster
builder = EntityLayerBuilder(use_topics=False)
builder.build_from_papers(papers)
clusters = builder.run_leiden(resolution=1.0, seed=42)

# Get results
summaries = builder.get_cluster_summary(clusters)
hubs = builder.find_hub_papers(top_k=10)

# Validate (optional)
validator = ClusterValidator(clusters, papers)
if validator.has_citation_data():
    report = validator.generate_report()
    print(f"Validation: ARI={report.ari:.3f}, NMI={report.nmi:.3f}")

# Find papers related to a topic
transformers = builder.find_papers_by_entity("transformer")
print(f"Found {len(transformers)} papers mentioning transformers")

# Trace entity path from seed paper
path = builder.entity_stream(papers[0]['doi'], strategy='strongest', max_hops=5)
print(f"Entity stream: {len(path)} papers")
```

## Input Format

Papers should be provided as JSON with the following structure:

```json
{
  "papers": [
    {
      "doi": "https://doi.org/10.1038/nature12373",
      "title": "Deep learning for protein structure prediction",
      "category": "machine_learning",
      "referenced_works": [
        "https://doi.org/10.1038/nbt.2488",
        "https://doi.org/10.1016/j.cell.2014.05.010"
      ]
    },
    {
      "doi": "https://doi.org/10.1038/nbt.2488",
      "title": "Machine learning approaches in computational biology",
      "category": "biology"
    }
  ]
}
```

Or as a plain array:
```json
[
  {
    "doi": "https://doi.org/10.1038/nature12373",
    "title": "Deep learning for protein structure prediction"
  }
]
```

**Required Fields:**
- `doi`: Unique paper identifier (URL or string)
- `title`: Paper title for entity extraction

**Optional Fields:**
- `category`: Paper category (stored but unused currently)
- `referenced_works`: List of cited paper DOIs (required for `--validate`)
- `topics`: OpenAlex topics (required for `--use-topics`)

**Topics Structure** (when using `--use-topics`):
```json
{
  "doi": "...",
  "title": "...",
  "topics": [
    {
      "display_name": "Deep Learning",
      "subfield": {
        "display_name": "Machine Learning"
      }
    }
  ]
}
```

## Entity Types

PaperSift extracts four entity categories using word-boundary matching:

### Methods
Deep learning, transformers, LSTM, CNN, RNN, machine learning, random forest, SVM, GAN, VAE, BERT, GPT, foundation models, embedding, transfer learning, fine-tuning, graph neural networks, etc.

### Organisms
Human, mouse, yeast, zebrafish, E. coli, C. elegans, Drosophila, Arabidopsis, and cell types (stem cells, T cells, neurons, cardiomyocytes, etc.)

### Concepts
Gene expression, pathway, signaling, metabolism, differentiation, drug discovery, disease, systems biology, multi-omics, virtual cell, gene regulatory network, epigenetics, etc.

### Datasets
UniProt, PDB, GenBank, KEGG, Reactome, TCGA, GTEx, Human Cell Atlas, CellxGene, GEO, STRING, DrugBank, ChEMBL, etc.

**Capitalized Terms** are also extracted from titles (e.g., "scGPT", "ScanPy"), excluding common stopwords.

## Advanced Usage

### Entity Extraction Pipeline

Understanding the entity extraction process:

1. **Rule-based matching:** Compare title against predefined entity dictionaries using word-boundary regex
2. **Capitalized terms:** Extract proper nouns and acronyms (capitalized words >= 3 chars)
3. **Stopword filtering:** Remove common words to reduce noise
4. **Lowercase normalization:** Store entities in lowercase for grouping

### Graph Construction

Paper-paper edges are weighted by shared entity count:
- Weight = number of unique entities in common
- Papers with no shared entities are disconnected
- Results in sparse network suitable for large collections

### Leiden Clustering

Uses Leiden algorithm with RBConfiguration (resolution parameter):
- `resolution=1.0`: Balanced (default)
- `resolution<1.0`: Coarser clusters, fewer communities
- `resolution>1.0`: Finer clusters, more communities

Example: 748 papers typically cluster into 80-150 communities at resolution 1.0.

### Citation Validation

Only used when `--validate` flag is provided and `referenced_works` data exists:
1. Builds citation graph from papers with external citations removed
2. Clusters citation graph independently using same Leiden parameters
3. Compares entity clusters vs citation clusters using:
   - **ARI:** Measures clustering agreement (not counting agreements on negative)
   - **NMI:** Information-theoretic measure of mutual information
4. Computes per-paper confidence as citation links within cluster

## Performance

Timing on 748 virtual cell papers:
- Entity extraction: ~1-2 seconds
- Graph construction: ~2-3 seconds
- Leiden clustering: ~3-5 seconds
- Total: <30 seconds

Memory usage: ~200-300 MB for 748 papers with ~5000 edges

## Entity Extraction Examples

| Title | Extracted Entities |
|-------|-------------------|
| "Deep learning for protein structure prediction using transformers" | deep learning, transformer, protein |
| "scGPT: A generative model for single-cell RNA-seq analysis" | scGPT, generative model, scRNA-seq, RNA-seq |
| "GROMACS: Molecular dynamics simulations" | GROMACS, molecular dynamics |
| "A survey of CRISPR gene editing in human cells" | CRISPR, gene editing, human |

## Troubleshooting

**No papers in output:**
- Check input JSON format (requires `doi` and `title` fields)
- Verify DOI format (should be "https://doi.org/..." or string)

**Too many/few clusters:**
- Adjust `--resolution`: higher for more clusters, lower for fewer
- Try `--resolution 0.5` for coarser clustering

**Validation shows weak agreement (low ARI):**
- Entity and citation views may capture different research structure
- This is expected and informative (complementary signals)
- Indicates papers may be grouped by methodological similarity (entities) vs. influence (citations)

**"Insufficient citation data":**
- Papers lack `referenced_works` field or < 10 internal citations
- Remove `--validate` flag or enrich data with citation information

## Version

PaperSift v0.1.0

Requirements: Python 3.11+, igraph 0.10+, leidenalg 0.10+, numpy, scikit-learn
