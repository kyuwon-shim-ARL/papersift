# E004: Hybrid Workflow Smoke Test Report

**Date**: 2026-02-26
**Test**: Combine sweep results with SOTA citation expansion and verify PaperSift pipeline

## Executive Summary

❌ **FAILED** - Cluster stability (48.3%) below 80% threshold

## Test Results

### Step 1: Seed Selection ✅
- **Seeds selected**: 5 papers
- **Citation range**: 8,974 - 9,887 citations
- **Year range**: 2004 - 2020
- **Criteria met**: All seeds have DOI, year ≤ 2022, 50 ≤ citations < 10,000

**Selected Seeds**:
1. [2013] Signatures of mutational processes in human cancer (9,887 cites)
2. [2004] Glide: A New Approach for Rapid, Accurate Docking and Scoring (9,624 cites)
3. [2009] Comprehensive Mapping of Long-Range Interactions (9,301 cites)
4. [2013] The Cancer Genome Atlas Pan-Cancer analysis project (9,047 cites)
5. [2020] Structure, Function, and Antigenicity of SARS-CoV-2 Spike Glycoprotein (8,974 cites)

### Step 2: Citation Expansion ✅
- **Pattern 1 (improvement)**: 996 papers
- **Pattern 2 (method_proposal)**: 981 papers
- **Pattern 3 (no filter)**: 990 papers
- **Total unique**: 2,577 papers
- **Execution time**: 81.8s (1.4 min)
- **API calls**: 3 patterns × 5 seeds = 15 queries

### Step 3: Merge with Sweep ✅
- **Existing sweep**: 3,070 papers
- **SOTA-expand**: 2,577 papers
- **New papers**: 2,566 (99.6% novelty rate)
- **Combined dataset**: 5,636 papers

### Step 4: PaperSift Clustering ✅
- **Input**: 5,636 papers
- **Graph**: 682,569 edges
- **Clusters found**: 535 clusters
- **Algorithm**: Leiden (resolution=1.0, seed=42)
- **Execution**: Success (no errors)

### Step 5: Cluster Stability Analysis ❌
- **Overall preservation rate**: 48.3% (FAIL - threshold: ≥80%)
- **Common papers**: 3,070 (100% of baseline)
- **Baseline clusters**: 11
- **New clusters**: 322 (29× increase)
- **Total paper pairs**: 669,832
- **Preserved pairs**: 323,432

**Per-Cluster Breakdown**:
| Old Cluster | Size | Pairs | Preserved | Preservation Rate |
|-------------|------|-------|-----------|-------------------|
| C0          | 595  | 176,715 | 68,728  | 38.9% |
| C1          | 571  | 162,735 | 78,080  | 48.0% |
| C2          | 453  | 102,378 | 67,459  | 65.9% |
| C4          | 362  | 65,341  | 43,548  | 66.6% |
| C3          | 362  | 65,341  | 22,094  | 33.8% |
| C5          | 336  | 56,280  | 26,146  | 46.5% |
| C6          | 254  | 32,131  | 13,735  | 42.7% |
| C7          | 134  | 8,911   | 3,642   | 40.9% |

**Unstable Clusters** (preservation < 50%):
- 6 out of 8 large clusters (≥10 papers) are unstable
- Largest cluster (C0, 595 papers) fragmented to 38.9% preservation
- Worst performer: C3 (33.8% preservation)

## Go/No-Go Assessment

| Criterion | Threshold | Result | Status |
|-----------|-----------|--------|--------|
| Pipeline completion | No errors | Success | ✅ PASS |
| Cluster stability | ≥ 80% | 48.3% | ❌ FAIL |
| Additional papers | ≥ 50 | 2,566 | ✅ PASS |
| Execution time | ≤ 30 min | ~3 min | ✅ PASS |

**Overall**: ❌ **NO-GO**

## Root Cause Analysis

### Cluster Fragmentation
The dramatic increase from 11 → 535 clusters (and 11 → 322 for common papers) suggests over-fragmentation caused by:

1. **Heterogeneous citation patterns**: SOTA-expand papers (citing the 5 seeds) have different entity overlap patterns than sweep papers (title-based discovery)
2. **Domain mismatch**: Seeds cover cancer genomics, docking, genomics, COVID-19 — these are outside the "virtual cell" domain, introducing noise
3. **Citation network structure**: Papers that cite highly-cited method papers (ResNet, Glide) span many domains, diluting entity coherence

### Why 99.6% Novelty?
The 5 seeds themselves were not in the original sweep (they're mega-citations from general methods/tools), so their citing papers are also outside the sweep's topical scope.

## Recommendations

### Immediate Actions
1. **Re-run with domain-filtered seeds**: Select 5 seeds from the original sweep that are:
   - Central to the "virtual cell" domain (C0, C1, or C3 from baseline)
   - Have moderate citations (200-2,000 range)
   - Published 2018-2021 (balance between citability and recency)

2. **Validate seed quality**: Before running expand_citations, manually verify that seeds are topically coherent with the target domain

3. **Reduce expansion volume**: Lower max_per_seed from 200 to 50-100 to maintain topical focus

### Alternative Approaches
1. **Two-stage filtering**:
   - Run expand_citations with current seeds
   - Filter SOTA-expand results by entity overlap with sweep corpus (≥1 shared entity)
   - Re-cluster filtered subset

2. **Citation chaining instead of citation expansion**:
   - Use expand_references() (backward citations) instead of expand_citations() (forward)
   - Backward citations have higher topical coherence (authors cite relevant background)

3. **Hybrid with text filter**:
   - Add domain-specific text filter: `"virtual cell" OR "whole-cell model" OR "in silico cell"`
   - This constrains SOTA-expand to stay on-topic

## Files Generated
```
outputs/e004/
├── seeds.json                    # 5 selected seed papers
├── sota_expand_results.json      # 2,577 citing papers (raw)
├── combined.json                 # 5,636 papers (sweep + new)
├── clusters.json                 # Cluster assignments
├── communities.json              # Cluster metadata
├── stability_analysis.json       # Detailed preservation metrics
└── smoke_test_report.md          # This report
```

## Next Steps

**Option A (Quick Fix)**: Re-run E004 with domain-appropriate seeds
- Estimated time: 5 minutes
- Expected stability: 70-80%

**Option B (Deep Dive)**: Investigate why mega-cited seeds were selected
- Check citation distribution in sweep corpus
- Identify "noise" papers that inflated citation counts
- Re-design seed selection criteria

**Option C (Pivot)**: Use expand_references() instead of expand_citations()
- Run E005 with backward citation chaining
- Compare stability and novelty
