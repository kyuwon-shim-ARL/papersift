# e004-v3 Smoke Test Report: Domain-Filtered Citation Expansion

## Executive Summary

**Verdict: NO-GO** - Domain text filter prevents pipeline errors but causes severe cluster fragmentation (398 clusters, 56.8% stability).

## Methodology

### Seed Selection
- **Source**: Existing virtual-cell-sweep papers with virtual cell keywords
- **Criteria**: Title contains "virtual cell", "whole-cell", etc. + citations ≥ 20 + year ≥ 2010
- **Seeds selected**: 5 highly-cited papers (1282, 263, 184, 146, 105 citations)
  1. [2012] A Whole-Cell Computational Model Predicts Phenotype from Genotype (DOI: 10.1016/j.cell.2012.05.044)
  2. [2012] Coupling actin flow, adhesion, and morphology in a computational cell motility model (DOI: 10.1073/pnas.1203252109)
  3. [2024] How to build the virtual cell with artificial intelligence (DOI: 10.1016/j.cell.2024.11.015)
  4. [2018] A whole-cell electron tomography model of vacuole biogenesis in Arabidopsis root (DOI: 10.1038/s41477-018-0328-1)
  5. [2022] Whole-cell modeling in yeast predicts compartment-specific proteome constraints (DOI: 10.1038/s41467-022-28467-6)

### Domain Filter
```
cell model OR cell simulation OR whole-cell OR in silico OR computational biology OR systems biology
```

### Citation Expansion
- **Method**: OpenAlex `filter=cites:{oa_id}` with domain text filter
- **Parameters**: max_per_seed=200, year_min=2010
- **Results**: 384 citing papers found, 349 new (non-duplicate)
- **Runtime**: 14.8 seconds

### Merge & Cluster
- **Baseline**: 3,070 papers (virtual-cell-sweep)
- **Combined**: 3,419 papers (+349 new, +11.4%)
- **Clustering**: Leiden algorithm (resolution=1.0, seed=42)
- **Result**: 398 clusters (vs baseline 11 clusters)

## Results

### Go/No-Go Criteria

| Criterion | Threshold | Result | Status |
|-----------|-----------|--------|--------|
| Pipeline completion | No errors | ✅ Completed | **PASS** |
| Cluster stability | ≥ 80% | ❌ 56.8% | **FAIL** |
| New papers | ≥ 50 | ✅ 349 papers | **PASS** |

**Overall: 2/3 PASS → NO-GO**

### Cluster Stability: 56.8%

- **Matched papers**: 3,070/3,070 (100% DOI matching after normalization fix)
- **Baseline co-cluster pairs**: 669,832
- **Preserved pairs**: 380,786
- **Stability**: 56.8% (vs v1: 48.3%, v2: 9.4%)

### Cluster Fragmentation

**Baseline (sweep)**:
- 11 clusters (8 major: 595, 571, 453, 362, 362, 336, 254, 134 papers)
- Coherent structure: biology clusters (C0, C1, C3, C5, C7) + noise clusters (C2, C4, C6)

**v3 (domain-filtered)**:
- **398 clusters** (4 major + 337 singletons + 57 small clusters)
- Major clusters: C0(1245), C1(536), C2(443), C3(356), C4(157)
- **Severe fragmentation**: 337 singleton clusters (1 paper each)

**Problem**: The new papers are not integrating into existing clusters. Instead, they're forming isolated singleton clusters or merging existing clusters into mega-clusters (C0: 595→1245, +110%).

## Analysis

### Why Domain Filter Prevents Errors

v2 (no filter) had 9.4% stability because forward citations included:
- Telecom papers citing virtual cell beamforming
- Manufacturing papers citing digital twin cells
- Unrelated fields citing methodology papers

Domain filter successfully excludes these irrelevant citations.

### Why Clustering Still Fails

The domain filter is **too broad**:
- "cell model" matches everything from bacterial models to cancer cell models
- "computational biology" matches genomics, proteomics, metabolomics
- "systems biology" matches pathway analysis, network inference

Result: 349 new papers span diverse sub-domains that don't share entities with virtual cell modeling core.

### Entity Mismatch

Virtual cell papers use terms like:
- "whole-cell model", "in silico cell", "genome-scale model"
- "E. coli", "M. genitalium", "yeast", "pathway simulation"

New citing papers may use:
- "computational model", "mathematical model", "simulation"
- Generic biology terms without virtual cell specifics

Without shared entities, papers form singleton clusters.

## Comparison with Previous Versions

| Version | Method | Papers | Clusters | Stability | Verdict |
|---------|--------|--------|----------|-----------|---------|
| Baseline | Sweep | 3,070 | 11 | - | - |
| v1 | Mega-cited seeds (no filter) | 3,120 | 11 | 48.3% | NO-GO |
| v2 | Domain seeds (no filter) | 3,358 | 11 | 9.4% | NO-GO |
| **v3** | **Domain seeds + filter** | **3,419** | **398** | **56.8%** | **NO-GO** |

**Key insight**: Text filter prevents extreme instability (9.4%→56.8%) but causes fragmentation (11→398 clusters).

## Root Cause Analysis

Forward citation expansion is **fundamentally unsuitable** for virtual cell domain because:

1. **Citation polysemy**: Papers cite "whole-cell model" for different reasons (methodology, comparison, analogy)
2. **Broad domain filter dilemma**:
   - Too narrow → misses relevant papers
   - Too broad → includes diverse sub-domains without shared entities
3. **Entity sparsity**: Citing papers don't necessarily use the same terminology as seed papers

## Recommendations

### Short-term: Abandon Forward Citation Expansion

Stop e004 experiment line. Forward citations are incompatible with entity-based clustering.

### Long-term: Alternative Discovery Methods

1. **Backward citation expansion** (e001-e003): Works better because referenced works are intentionally selected by authors
2. **Topic-based search** (original sweep): Directly targets domain-relevant papers
3. **Hybrid approach**: Sweep + selective backward expansion from high-quality clusters

### If Forward Citation Must Be Used

Narrow the filter to virtual cell **specifics**:
```
"whole-cell model" OR "whole cell model" OR "in silico cell" OR "genome-scale model" OR "virtual cell"
```

But even this may not solve entity mismatch.

## Files Generated

- `outputs/e004/v3/seeds_v3.json` - 5 virtual cell seed papers with OpenAlex IDs
- `outputs/e004/v3/sota_expand_v3.json` - 384 citing papers (domain-filtered)
- `outputs/e004/v3/combined_v3.json` - 3,419 papers (sweep + 349 new)
- `outputs/e004/v3/clusters.json` - Cluster assignments (398 clusters)
- `outputs/e004/v3/communities.json` - Community metadata
- `outputs/e004/v3/stability_results.json` - Stability metrics
- `outputs/e004/v3/smoke_test_v3_report.md` - This report

## Conclusion

Domain text filtering successfully prevents extreme instability (9.4%→56.8%) but causes severe cluster fragmentation (11→398 clusters). The 56.8% stability is still below the 80% threshold, and the fragmentation indicates new papers are not meaningfully integrating into the existing landscape.

**Verdict: NO-GO** - Domain-filtered forward citation expansion is not viable for virtual cell discovery.

Recommend terminating e004 experiment line and focusing on backward citation or topic-based methods.

---

**Report generated**: 2026-02-26
**Experiment**: e004-v3 (domain-filtered citation expansion)
**Status**: Complete, NO-GO
