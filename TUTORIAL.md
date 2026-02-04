# PaperSift Tutorial

End-to-end guide: from installation to validated paper clustering.

## Prerequisites

- Python 3.11+
- pip

## 1. Installation

```bash
# Clone the repository
git clone https://github.com/kyuwon-shim-ARL/papersift.git
cd papersift

# Install core package
pip install -e .

# Install with enrichment support (OpenAlex API)
pip install -e ".[enrich]"
```

Verify the installation:

```bash
papersift --help
```

## 2. Quick Start: Cluster in Three Commands

PaperSift includes sample data for testing. Run your first clustering:

```bash
# Cluster 20 sample papers
papersift cluster tests/fixtures/sample_papers.json -o /tmp/papersift-quickstart/

# View cluster summaries
python -m json.tool /tmp/papersift-quickstart/communities.json
```

Expected output:

```
Loaded 20 papers
Building entity graph (Title-only)...
  Graph: 20 nodes, XX edges
Running Leiden clustering (resolution=1.0, seed=42)...
  Found N clusters
Saved: /tmp/papersift-quickstart/clusters.json
Saved: /tmp/papersift-quickstart/communities.json
```

## 3. Preparing Input Data

PaperSift accepts JSON files with paper metadata. Minimum required fields: `doi` and `title`.

### Minimal format

```json
[
  {
    "doi": "10.1038/s41586-023-06291-2",
    "title": "Deep learning for protein structure prediction"
  },
  {
    "doi": "10.1038/nbt.2488",
    "title": "Machine learning in computational biology"
  }
]
```

### Full format with optional fields

```json
{
  "papers": [
    {
      "doi": "10.1038/s41586-023-06291-2",
      "title": "Deep learning for protein structure prediction",
      "category": "machine_learning",
      "referenced_works": ["10.1038/nbt.2488"],
      "topics": [
        {
          "display_name": "Protein Structure",
          "subfield": {"display_name": "Structural Biology"}
        }
      ]
    }
  ]
}
```

Both array `[...]` and object `{"papers": [...]}` formats are supported.

## 4. Enriching Papers with OpenAlex

If your papers have DOIs but lack citation or topic data, use the `enrich` command to fetch this from OpenAlex.

```bash
papersift enrich your_papers.json -o enriched_papers.json --email your@email.com
```

The `--email` flag registers you with OpenAlex's polite pool for faster rate limits.

### Available fields

```bash
# Default: referenced_works + openalex_id
papersift enrich papers.json -o enriched.json --email you@example.com

# Fetch all available fields
papersift enrich papers.json -o enriched.json --email you@example.com \
  --fields referenced_works,openalex_id,topics,abstract
```

| Field | Description |
|-------|-------------|
| `referenced_works` | Cited papers as DOI list (for `--validate`) |
| `openalex_id` | OpenAlex work identifier |
| `topics` | OpenAlex topic taxonomy (for `--use-topics`) |
| `abstract` | Paper abstract text |

### What happens during enrichment

1. For each paper with a DOI, PaperSift queries the OpenAlex API
2. `referenced_works` are returned as OpenAlex IDs, which are batch-resolved to DOIs
3. Abstracts are reconstructed from OpenAlex's inverted index format
4. Papers without DOIs are skipped with a warning

## 5. Clustering Papers

### Basic clustering

```bash
papersift cluster enriched_papers.json -o results/
```

### Tuning resolution

The `--resolution` parameter controls cluster granularity:

```bash
# Coarse clusters (fewer, larger groups)
papersift cluster papers.json -o results-coarse/ --resolution 0.5

# Default balance
papersift cluster papers.json -o results/ --resolution 1.0

# Fine clusters (more, smaller groups)
papersift cluster papers.json -o results-fine/ --resolution 2.0
```

### Using OpenAlex topics

If your papers have topic data (from enrichment), use `--use-topics` for richer entity coverage:

```bash
papersift cluster enriched_papers.json -o results/ --use-topics
```

This adds topic names and subfield names as additional entities, typically increasing entities per paper from ~3.5 to ~8.5.

### Interpreting cluster output

`communities.json` contains cluster summaries sorted by size:

```json
[
  {
    "cluster_id": 0,
    "size": 45,
    "dois": ["10.1038/...", "10.1016/..."],
    "top_entities": ["deep learning", "neural network", "protein", "transformer", "CNN"]
  }
]
```

The `top_entities` field tells you what the cluster is about. Papers in the same cluster share many of these entities.

## 6. Validating with Citations

Citation validation compares entity-based clusters against citation-based clusters. This requires `referenced_works` data.

```bash
# Enrich first (if not already done)
papersift enrich papers.json -o enriched.json --email you@example.com

# Cluster with validation
papersift cluster enriched.json -o validated/ --validate
```

Expected output:

```
Validating with citation data...
  ARI: 0.XXX
  NMI: 0.XXX
  Confidence: {'high': N, 'medium': N, 'low': N}
  Moderate agreement: Entity and citation views capture partially overlapping structure.
```

### Interpreting validation metrics

| Metric | Range | Meaning |
|--------|-------|---------|
| ARI | -1 to 1 | Agreement between entity and citation clusters. >0.5 = strong, 0.2-0.5 = moderate, <0.2 = weak |
| NMI | 0 to 1 | Mutual information between clusterings. >0.5 = strong, 0.2-0.5 = moderate |

**Weak agreement is normal.** Entity clustering groups papers by methodological similarity, while citations reflect influence. These are complementary views -- low ARI means they capture different structure, not that clustering is wrong.

### Confidence scores

`confidence.json` contains per-paper scores (0 to 1):
- **High (>0.5):** Paper's cluster members frequently cite each other
- **Medium (0.2-0.5):** Some citation links within cluster
- **Low (<0.2):** Few citation links within cluster

## 7. Finding Hub Papers

Hub papers are the most connected in the entity graph -- they share entities with many other papers:

```bash
papersift find papers.json --hubs 10
```

Output:

```
Top 10 Entity Hub Papers:
------------------------------------------------------------
 1. [ 847] Deep learning for single-cell multi-omics int...
    Entities: deep learning, single-cell, multi-omics, integration, neural network
 2. [ 623] Machine learning approaches in computational ...
    Entities: machine learning, computational biology, gene expression
```

The number in brackets is the hub score (sum of shared entities with all neighbors).

## 8. Searching by Entity

Find all papers that mention a specific entity:

```bash
papersift find papers.json --entity "CRISPR"
papersift find papers.json --entity "deep learning"
papersift find papers.json --entity "E. coli"
```

Entity search is case-insensitive. It matches against the extracted entity list, not the raw title text.

## 9. Exploring with Stream

Stream mode traces a path through the entity graph starting from a seed paper:

```bash
# Follow strongest entity connections
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --hops 5

# Discover diverse topics
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --strategy diverse --hops 10

# Get all papers within 3 hops
papersift stream papers.json --seed "https://doi.org/10.1038/nature12373" --expand --hops 3
```

**Strategies:**
- `strongest`: Each hop follows the neighbor sharing the most entities. Stays within a tightly related area.
- `diverse`: Each hop follows the neighbor introducing the most new entities. Explores across research areas.

## 10. Interpreting Results

### communities.json

Each entry represents a research theme discovered from shared entities:
- **size**: Number of papers in the cluster
- **top_entities**: The defining entities for this theme
- **dois**: Member papers

### clusters.json

A flat DOI-to-cluster-ID mapping for programmatic use:

```python
import json

with open('results/clusters.json') as f:
    clusters = json.load(f)

# Find papers in cluster 5
cluster_5 = [doi for doi, cid in clusters.items() if cid == 5]
```

### validation_report.json

Summary of how well entity clusters align with citation patterns:

```python
import json

with open('results/validation_report.json') as f:
    report = json.load(f)

print(f"Agreement: ARI={report['ari']:.3f}, NMI={report['nmi']:.3f}")
print(f"Entity clusters: {report['num_entity_clusters']}")
print(f"Citation clusters: {report['num_citation_clusters']}")
```

## 11. FAQ / Troubleshooting

**Q: How many papers can PaperSift handle?**
A: Tested with 748 papers in under 30 seconds. The main bottleneck is graph construction (O(n^2) comparisons). For 1000+ papers, expect a few minutes.

**Q: Why do some papers have no entities?**
A: Very short or generic titles may not match any predefined patterns. Use `--use-topics` with enriched data for better coverage.

**Q: Why does validation show "Insufficient citation data"?**
A: Papers need `referenced_works` field with DOIs that reference other papers in the same collection. Use `papersift enrich` to fetch this data from OpenAlex.

**Q: Can I use PaperSift without DOIs?**
A: Currently DOIs are required as paper identifiers. All papers must have a `doi` field.

**Q: What's the difference between hub score and citation count?**
A: Hub score measures entity connectivity (shared methods, organisms, concepts with other papers). Citation count measures how often a paper is referenced. These are complementary -- a paper can be a hub without many citations and vice versa.

**Q: How do I choose the right resolution?**
A: Start with the default (1.0). If clusters are too large and mix unrelated topics, increase resolution. If clusters are too small and split related work, decrease resolution. Compare `communities.json` at different resolutions to find the right granularity for your needs.
