---
name: papersift
description: Entity-based academic paper clustering - cluster, enrich, find hub papers, and trace entity connections using rule-based entity extraction and Leiden graph clustering (project)
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
---

# PaperSift Skill v0.1.0
## Entity-Based Academic Paper Clustering

PaperSift discovers research themes and connections through entity-based analysis rather than citation data. It extracts structured information (methods, organisms, concepts, datasets) from paper titles, builds a paper-paper network based on shared entities, and applies Leiden clustering for community detection.

**Key capabilities for Claude:**
- Rule-based entity extraction from titles (deterministic, no LLM required)
- Fast clustering: 748 papers in under 30 seconds
- Hub paper discovery (most-connected papers)
- Entity-based paper search and filtering
- Stream traversal following entity connections
- Optional citation-based validation (ARI, NMI metrics)

---

## When to Use

Invoke this skill when you need to:

- **Cluster papers** by shared research concepts (methods, organisms, cell types, domains)
- **Find hub papers** - papers that bridge multiple research areas via shared entities
- **Discover research connections** - trace entity networks to understand topic relationships
- **Enrich papers** with OpenAlex data (referenced works, topics, abstracts) before clustering
- **Validate clusters** using citation networks (when referenced_works data available)
- **Explore entity landscapes** - stream through entity-connected paper chains

---

## Conversational Exploration

PaperSift supports interactive paper exploration workflows through entity-based filtering, cluster manipulation, and iterative refinement.

### Pattern 1: Entity-based extraction

**User prompt example:**
```
"virtual cell 관련 논문만 추출해줘"
```

**Commands:**
```bash
# First, browse to identify clusters
papersift browse papers.json --list --format json

# Filter papers containing "virtual cell" entity
papersift filter papers.json --entity "virtual cell" -o vc_papers.json
```

**Expected output:** JSON file containing only papers with "virtual cell" entity.

### Pattern 2: Cluster merge

**User prompt example:**
```
"클러스터 3과 5를 합쳐줘"
```

**Commands:**
```bash
# Merge cluster 3 and 5 into one output
papersift filter papers.json --cluster 3,5 --clusters-from results/clusters.json -o merged.json
```

**Expected output:** JSON file containing papers from both cluster 3 and 5.

### Pattern 3: Sub-cluster drill-down

**User prompt example:**
```
"가장 큰 클러스터를 세분화해줘"
```

**Commands:**
```bash
# First, identify the largest cluster
papersift browse papers.json --list --format json

# Sub-cluster the largest cluster (e.g., cluster 2)
papersift subcluster papers.json --cluster 2 --clusters-from results/clusters.json
```

**Expected output:** Sub-cluster analysis showing finer-grained communities within the selected cluster.

### Pattern 4: Topic-based re-clustering

**User prompt example:**
```
"deep learning 관련만 따로 클러스터링"
```

**Commands:**
```bash
# Filter papers by entity
papersift filter papers.json --entity "deep learning" -o dl.json

# Re-cluster the filtered papers
papersift cluster dl.json -o dl_results/
```

**Expected output:** New clustering results focused on deep learning papers only.

### Pattern 5: Multi-step refinement

**User prompt example:**
```
"transformer 관련 논문 중 큰 클러스터만 세분화하고 관련 없는 건 제외"
```

**Commands:**
```bash
# Step 1: Filter by entity
papersift filter papers.json --entity "transformer" -o tf.json

# Step 2: Cluster
papersift cluster tf.json -o tf_results/

# Step 3: Browse to identify clusters
papersift browse tf.json --list --format json

# Step 4: Sub-cluster largest cluster
papersift subcluster tf.json --cluster 0 --clusters-from tf_results/clusters.json -o tf_refined.json

# Step 5: Merge relevant sub-clusters if needed
papersift filter tf_refined.json --cluster 1,2 --clusters-from tf_refined_results/clusters.json -o final.json
```

**Expected output:** Iteratively refined paper collection through filtering, clustering, sub-clustering, and merging.

---

## Prerequisites

PaperSift must be pip-installed:

```bash
# Basic installation (title-only clustering)
pip install papersift

# With enrichment capability (recommended)
pip install papersift[enrich]
```

The `[enrich]` extra installs `pyalex` for OpenAlex integration. Requires Python 3.11+.

### First-Time Setup

After installing this plugin, you must install the Python package:

```bash
# Using pip (from GitHub)
pip install "papersift[enrich] @ git+https://github.com/kyuwon-shim-ARL/papersift.git"

# Using uv (specify target Python if needed)
uv pip install --python $(which python) "papersift[enrich] @ git+https://github.com/kyuwon-shim-ARL/papersift.git"

# Or from a local clone
pip install -e "/path/to/papersift/[enrich]"
```

Verify installation:
```bash
papersift --help
python -c "from papersift import EntityLayerBuilder; print('OK')"
```

---

## Workflow

### Step 1: Prepare Paper Collection

**Load papers from MSK2025 data directory:**

```bash
# Option A: Papers from paper-pipeline (recommended)
# Location: /home/kyuwon/projects/MSK2025/data/papers/by-collection/[COLLECTION]/collection.json

# Option B: Assemble papers manually from metadata
# Location: /home/kyuwon/projects/MSK2025/data/papers/by-doi/[DOI_ENCODED]/metadata.json
```

**Required JSON format:**
```json
[
  {
    "doi": "10.1038/nature06244",
    "title": "The Human Microbiome Project",
    "referenced_works": ["10.1101/...", "10.1038/..."],
    "topics": ["Gut microbiota", "Genomics"]
  }
]
```

### Step 2: Cluster Papers

**Run entity-based clustering with Leiden algorithm:**

```bash
papersift cluster papers.json -o results/ \
  --resolution 1.0 \
  --seed 42 \
  --use-topics
```

**Resolution tuning:**
- `0.5` = Fewer, larger clusters (broad groupings)
- `1.0` = Default, balanced community size
- `2.0` = More, smaller clusters (fine-grained)

### Step 3: Find Hub Papers

**Identify papers with highest entity connectivity (bridges research areas):**

```bash
papersift find papers.json --hubs 10
```

Output shows DOI, hub score, and top entities.

### Step 4: Search by Entity

**Locate all papers discussing a specific concept:**

```bash
papersift find papers.json --entity "transformer"
papersift find papers.json --entity "CRISPR"
```

### Step 5: Trace Entity Connections

**Follow entity-based paths from a seed paper:**

```bash
# Greedy path following strongest connections
papersift stream papers.json \
  --seed "10.1038/nature06244" \
  --strategy strongest \
  --hops 5

# Breadth-first expansion to all neighbors
papersift stream papers.json \
  --seed "10.1038/nature06244" \
  --expand \
  --hops 3
```

### Step 6: Validate Clusters (Optional)

**Compare entity clusters against citation network structure:**

```bash
papersift cluster papers.json -o results/ --validate
```

Produces ARI and NMI scores. Requires `referenced_works` field in papers.

---

## CLI Reference

### papersift cluster
Cluster papers into communities based on shared entities.

```bash
papersift cluster INPUT -o OUTPUT \
  [--resolution FLOAT]     # Leiden resolution (default: 1.0)
  [--seed INT]             # Random seed (default: 42)
  [--use-topics]           # Include OpenAlex topics
  [--validate]             # Validate with citation data
```

**Output files:**
- `clusters.json` - {doi: cluster_id}
- `communities.json` - Cluster summaries with entity listings
- `validation_report.json` - ARI/NMI scores (if --validate)

### papersift landscape
Generate UMAP/t-SNE visualization of paper landscape.

```bash
papersift landscape INPUT -o OUTPUT \
  [--method {umap,tsne}]   # Visualization method (default: tsne)
  [--use-topics]           # Include OpenAlex topics in embedding
  [--resolution FLOAT]     # Leiden resolution for cluster overlay (default: 1.0)
  [--seed INT]             # Random seed (default: 42)
  [--interactive]          # Generate interactive HTML plot
```

**Output files:**
- `landscape.png` - Static visualization
- `landscape.html` - Interactive plot (if --interactive)
- `clusters.json` - Cluster assignments used for coloring

### papersift filter
Filter papers by entity, cluster, or DOI.

```bash
papersift filter INPUT -o OUTPUT \
  [--entity NAME]              # Filter by entity (repeatable)
  [--entity-any]               # Match ANY entity (OR logic, default: AND)
  [--cluster N,M,...]          # Filter by cluster ID(s)
  [--dois file.txt]            # Filter by DOI list file
  [--exclude]                  # Invert filter (exclude matches)
  [--clusters-from FILE]       # Load clusters from file (required for --cluster)
  [--resolution FLOAT]         # Leiden resolution (default: 1.0)
  [--use-topics]               # Include OpenAlex topics in entity extraction
  [--format {json,table}]      # Output format (default: json)
```

**Input:**
- Use `-` for stdin to enable piping
- Supports both JSON array and `{"papers": [...]}` format

**Examples:**
```bash
# Filter by single entity
papersift filter papers.json --entity "transformer" -o tf_papers.json

# Filter by multiple entities (AND logic)
papersift filter papers.json --entity "CRISPR" --entity "human" -o crispr_human.json

# Filter by multiple entities (OR logic)
papersift filter papers.json --entity "CRISPR" --entity "TALEN" --entity-any -o gene_editing.json

# Filter by cluster
papersift filter papers.json --cluster 0,1,2 --clusters-from results/clusters.json -o top3.json

# Filter by DOI list
papersift filter papers.json --dois selected_dois.txt -o selected.json

# Exclude papers with entity (invert)
papersift filter papers.json --entity "review" --exclude -o no_reviews.json

# Pipe from stdin
cat papers.json | papersift filter - --entity "deep learning" -o dl.json
```

### papersift merge
Merge and deduplicate multiple paper files.

```bash
papersift merge INPUT1 INPUT2 [INPUT3 ...] -o OUTPUT
```

**Features:**
- Deduplicates by DOI (case-insensitive)
- Preserves all unique papers across input files
- Supports both JSON array and `{"papers": [...]}` format

**Example:**
```bash
papersift merge collection1.json collection2.json enriched.json -o merged.json
```

### papersift subcluster
Sub-cluster a specific cluster for finer-grained analysis.

```bash
papersift subcluster INPUT \
  --cluster N \
  --clusters-from FILE \
  [--resolution FLOAT]     # Leiden resolution (default: 1.0)
  [--use-topics]           # Include OpenAlex topics
  [--seed INT]             # Random seed (default: 42)
  [-o OUTPUT]              # Save filtered papers (optional)
  [--format {json,table}]  # Output format (default: table)
```

**Output:**
- Prints sub-cluster analysis to stdout
- Optionally saves filtered papers to file if `-o` specified

**Example:**
```bash
# Analyze sub-clusters within cluster 0
papersift subcluster papers.json --cluster 0 --clusters-from results/clusters.json

# Save sub-clustered papers to file
papersift subcluster papers.json --cluster 0 --clusters-from results/clusters.json -o cluster0_refined.json
```

### papersift browse
Browse and explore cluster assignments interactively.

```bash
papersift browse INPUT \
  [--list]                 # List all clusters with paper counts
  [--cluster N]            # Show papers in specific cluster
  [--sub-cluster]          # Show sub-cluster analysis for selected cluster
  [--clusters-from FILE]   # Load clusters from file (required)
  [--resolution FLOAT]     # Leiden resolution (default: 1.0)
  [--use-topics]           # Include OpenAlex topics
  [--format {table,json}]  # Output format (default: table)
```

**Examples:**
```bash
# List all clusters
papersift browse papers.json --list --clusters-from results/clusters.json

# List clusters in JSON format
papersift browse papers.json --list --clusters-from results/clusters.json --format json

# Show papers in cluster 2
papersift browse papers.json --cluster 2 --clusters-from results/clusters.json

# Sub-cluster analysis for cluster 2
papersift browse papers.json --cluster 2 --clusters-from results/clusters.json --sub-cluster
```

### papersift enrich
Fetch OpenAlex data to enhance papers.

```bash
papersift enrich INPUT -o OUTPUT \
  --email EMAIL \
  [--fields FIELD1,FIELD2]  # Default: referenced_works,openalex_id
```

**Supported fields:** referenced_works, openalex_id, topics, abstract

### papersift find
Discover hub papers or papers containing specific entities.

```bash
papersift find INPUT \
  [--hubs N]               # Top N hub papers
  [--entity NAME]          # Papers with this entity
  [--use-topics]           # Include OpenAlex topics
  [--format {table,json}]  # Output format (default: table)
```

### papersift stream
Follow entity connections from a seed paper.

```bash
papersift stream INPUT \
  --seed DOI \
  [--hops N]                        # Max hops (default: 5)
  [--strategy {strongest,diverse}]  # Connection strategy
  [--expand]                        # Expand to all neighbors
  [--use-topics]                    # Include OpenAlex topics
```

---

## Python API

For programmatic access in Claude scripts:

```python
from papersift import EntityLayerBuilder, ClusterValidator, OpenAlexEnricher
import json

# Load papers
with open('papers.json') as f:
    papers = json.load(f)

# Build entity graph and cluster
builder = EntityLayerBuilder(use_topics=False)  # True to use OpenAlex topics
builder.build_from_papers(papers)

# Get clusters
clusters = builder.run_leiden(resolution=1.0, seed=42)  # {doi: cluster_id}

# Get cluster summaries
summaries = builder.get_cluster_summary(clusters)

# Find hubs
hubs = builder.find_hub_papers(top_k=10)

# Find papers by entity
dois = builder.find_papers_by_entity("transformer")

# Stream from seed
path = builder.entity_stream("10.1038/nature06244", strategy="strongest", max_hops=5)
neighbors = builder.expand_from_seed("10.1038/nature06244", hops=3)

# Validate (optional)
if papers[0].get('referenced_works'):
    validator = ClusterValidator(clusters, papers)
    report = validator.generate_report()  # ARI, NMI, confidence
```

---

## Entity Extraction

PaperSift automatically extracts entities from paper titles:

**Rule-based patterns matched:**
- **Methods**: Transformers, LSTM, CNN, GNN, CRISPR, RNA-seq, scRNA-seq, XGBoost, etc.
- **Organisms**: Human, mouse, E. coli, yeast, zebrafish, etc.
- **Cell types**: Stem cell, T cell, macrophage, neuron, cardiomyocyte, etc.
- **Domains**: Machine learning, Deep learning, Reinforcement learning, Bayesian, etc.
- **Techniques**: ChIP-seq, ATAC-seq, Hi-C, FBA, UMAP, t-SNE, PCA, etc.
- **Capitalized terms**: Any multi-word capitalized phrase not in stoplist (e.g., "Virtual Cell", "Single-Cell Atlas")

**Graph construction:**
Papers are nodes; edges connect papers that share ≥1 entity. Community detection uses Leiden algorithm on entity co-occurrence graph.

---

## Input Format

Papers JSON (array or wrapped object):

```json
{
  "papers": [
    {
      "doi": "10.1038/nature12234",
      "title": "Deep Learning for Protein Structure Prediction",
      "referenced_works": ["10.1038/...", "10.1101/..."],
      "topics": ["AlphaFold", "Protein folding"]
    }
  ]
}
```

Or plain array:
```json
[
  { "doi": "...", "title": "...", ... },
  ...
]
```

**Required fields:** doi, title
**Optional fields:** referenced_works (for validation), topics (for --use-topics)

---

## Integration with Paper Pipeline

If using paper-pipeline to fetch papers:

```bash
# 1. Generate papers collection from paper-pipeline
python -m paper_pipeline cluster \
  --collection-id my-collection \
  --output data/papers/by-collection/my-collection/

# 2. Optionally enrich with OpenAlex
papersift enrich data/papers/by-collection/my-collection/papers.json \
  -o data/papers/by-collection/my-collection/enriched.json \
  --email user@example.com

# 3. Cluster with papersift
papersift cluster data/papers/by-collection/my-collection/enriched.json \
  -o data/papers/by-collection/my-collection/papersift-results/ \
  --use-topics --validate
```

---

## Output Files

### clusters.json
Entity-cluster assignment:
```json
{
  "10.1038/nature06244": 0,
  "10.1038/s41579-021-00649-x": 1,
  ...
}
```

### communities.json
Cluster summaries with entity membership:
```json
{
  "0": {
    "size": 15,
    "entities": ["Microbiome", "16S rRNA", "Genomics", ...],
    "papers": ["10.1038/nature06244", ...]
  },
  ...
}
```

### validation_report.json
(Optional, when --validate used)
```json
{
  "ari": 0.62,
  "nmi": 0.78,
  "num_papers": 150,
  "num_entity_clusters": 8,
  "num_citation_clusters": 7,
  "confidence_summary": {"high": 45, "medium": 60, "low": 45},
  "interpretation": "Strong agreement between entity and citation structure"
}
```

### confidence.json
Per-paper cluster confidence scores (0-1 scale indicating how well each paper fits its entity cluster based on citation evidence).

---

## 중요 참고사항 (Important Notes)

**MSK2025 프로젝트에서 사용할 때:**

- **데이터 위치**: `/home/kyuwon/projects/MSK2025/data/papers/by-collection/` 또는 `by-doi/`
- **기본 워크플로우**: 1) 데이터 로드 → 2) 클러스터링 → 3) 결과 분석
- **validation 옵션**: 논문이 `referenced_works`를 포함할 때만 사용 가능
- **resolution 튜닝**: 너무 많거나 적은 클러스터가 나오면 resolution 값 조정

**Claude 사용 팁:**

- 처음에는 작은 paper subset (10-20개)으로 테스트 후 확대
- `--seed` 파라미터로 결과 재현 가능
- hub papers 찾기는 논문 제도사(landscape) 이해에 매우 유용
- entity_stream으로 한 논문에서 시작하여 관련 논문들을 따라가며 탐색 가능

---

**Version**: 0.1.0
**Last Updated**: 2026-02-04
**Repository**: /home/kyuwon/projects/papersift/
