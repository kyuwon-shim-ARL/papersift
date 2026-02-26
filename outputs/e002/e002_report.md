# E002: OpenAlex Fulltext Coverage & Filter Pattern Analysis

**Date**: 2026-02-26
**Dataset**: Virtual Cell Sweep (3,070 papers)
**Objective**: Measure OpenAlex fulltext indexing coverage and SOTA text filtering pattern effectiveness

---

## Executive Summary

### Key Findings

1. **Fulltext Coverage: 48.6% (GO)**
   - 751 out of 1,545 checked papers have fulltext indexed
   - 95% CI: [46.1%, 51.1%]
   - **Decision: GO** (threshold: 30%)

2. **Best Filter Pattern: "improvement" (29.7%)**
   - Outperforms all other patterns tested
   - 3.8x more effective than SOTA-narrow patterns

3. **Method Proposal vs SOTA**
   - Method proposal: 26.8% avg hit rate
   - SOTA narrow: 7.8% avg hit rate
   - SOTA broad: 7.3% avg hit rate
   - **Method proposal is 3.4x more prevalent**

---

## Detailed Results

### 1. Fulltext Indexing Coverage

| Metric | Value |
|--------|-------|
| Total papers in dataset | 3,070 |
| Papers checked via API | 1,545 (50.3%) |
| Fulltext available | 751 |
| **Coverage rate** | **48.6%** |
| 95% Confidence Interval | [46.1%, 51.1%] |

**Go/No-Go**: GO ✓

### 2. Filter Pattern Performance

Ranked by average hit rate across 10 seed papers (total 1.27M citing papers):

| Rank | Pattern | Avg Hit Rate | Total Hits | Effect Size |
|------|---------|--------------|------------|-------------|
| 1 | Improvement | 29.7% | 378,136 | 3.8x SOTA-narrow |
| 2 | Method Proposal | 26.8% | 333,247 | 3.4x SOTA-narrow |
| 3 | Combined | 9.8% | 118,466 | — |
| 4 | Sota Narrow | 7.8% | 109,659 | — |
| 5 | Sota Broad | 7.3% | 84,825 | — |

### 3. Seed Papers (Top 10 by Citations)

| Paper | Citations | Best Pattern | Hit Rate |
|-------|-----------|--------------|----------|
| Deep Residual Learning for Image Recognition | 214,678 | improvement | 43.9% |
| Generalized Gradient Approximation Made Simple | 203,551 | improvement | 16.4% |
| Analysis of Relative Gene Expression Data Using Re... | 172,801 | improvement | 27.2% |
| Random Forests | 118,517 | improvement | 38.5% |
| Controlling the False Discovery Rate: A Practical ... | 104,957 | method proposal | 40.9% |
| Density-functional thermochemistry. III. The role ... | 101,039 | method proposal | 10.0% |
| Moderated estimation of fold change and dispersion... | 90,173 | method proposal | 32.8% |
| Long Short-Term Memory | 93,552 | improvement | 40.4% |
| Basic local alignment search tool | 91,720 | method proposal | 25.1% |
| Global cancer statistics 2018: GLOBOCAN estimates ... | 82,194 | improvement | 38.4% |

---

## Visualizations

### Figure 1: Coverage and Pattern Effectiveness
![E002 Summary](e002_summary.png)

**Panel A**: Fulltext coverage breakdown showing 48.6% of accessible papers have indexed fulltext.

**Panel B**: Filter pattern comparison ranked by effectiveness. "Improvement" and "method proposal" patterns significantly outperform SOTA-focused patterns.

### Figure 2: Pattern Performance by Seed Paper
![E002 Detailed Patterns](e002_detailed_patterns.png)

Pattern hit rates vary significantly across seed papers, with ML/CV papers (ResNet, LSTM, Random Forest) showing highest SOTA-narrow rates (13-25%) while methodology papers show lower rates (1-4%).

---

## Key Insights

### Finding 1: Fulltext Coverage is Adequate for Tier-1 Strategy
- **Evidence**: 48.6% coverage (95% CI: [46.1%, 51.1%])
- **Interpretation**: Nearly half of papers have searchable fulltext, sufficient for filtering strategies
- **Caveat**: API returned only 50.3% of dataset; missing papers may have different coverage rates

### Finding 2: Method Proposal Patterns Outperform SOTA Patterns
- **Evidence**: 26.8% vs 7.8% avg hit rate (3.4x difference)
- **Interpretation**: Papers more commonly describe new methods than claim SOTA performance
- **Implication**: Use method-focused filters for broader recall; SOTA filters for high-precision

### Finding 3: "Improvement" Pattern Shows Highest Recall
- **Evidence**: 29.7% avg hit rate across all seed papers
- **Interpretation**: "improves/extends/enhances/advances" captures incremental contributions
- **Recommendation**: Consider "improvement" as primary filter for broad method discovery

### Finding 4: Combined Patterns Underperform
- **Evidence**: Combined pattern (9.8%) < method_proposal (26.8%)
- **Interpretation**: Likely due to OpenAlex OR query semantics in fulltext search
- **Limitation**: May require investigation of query processing behavior

### Finding 5: Domain-Specific Variation
- **Evidence**: ML/CV papers show 13-25% SOTA-narrow rate vs 1-4% in methodology papers
- **Interpretation**: SOTA claims are field-dependent; ML/DL papers emphasize benchmarking
- **Implication**: Pattern selection should consider target domain characteristics

---

## Limitations

1. **API Coverage Gap**: Only 50.3% of papers returned by API; missing papers may bias coverage estimates
2. **Seed Paper Bias**: Top 10 cited papers may not represent typical papers in dataset
3. **Pattern Specificity**: Tested patterns are English-centric and may miss non-English fulltext
4. **Citation Context**: Hit rates based on total citing papers; does not assess relevance quality
5. **Query Semantics**: OpenAlex fulltext search behavior for OR queries requires further investigation

---

## Recommendations for Tier-1 Strategy

### Go Decision: Proceed with Fulltext Filtering
Coverage of 48.6% exceeds 30% threshold. Fulltext search is viable for Tier-1.

### Recommended Filter Patterns (Ranked):
1. **"improvement" pattern** (29.7% recall) — Broadest coverage of methodological advances
2. **"method_proposal" pattern** (26.8% recall) — Strong for novel method discovery
3. **"sota_narrow" pattern** (7.8% recall) — High precision for benchmark papers (ML/DL domains)
4. **Avoid "combined" pattern** — Underperforms individual patterns due to query semantics

### Implementation Strategy:
- **Phase 1**: Use "improvement" OR "method_proposal" for high recall
- **Phase 2**: Apply "sota_narrow" as secondary filter for benchmark-focused papers
- **Domain-aware**: Adjust pattern weights based on field (higher SOTA weight for ML/CV)

---

## Data Availability

- **Coverage Results**: `outputs/e002/fulltext_coverage.json`
- **Pattern Analysis**: `outputs/e002/filter_patterns.json`
- **Execution Log**: `outputs/e002/execution.log`
- **Visualizations**: `outputs/e002/e002_summary.png`, `outputs/e002/e002_detailed_patterns.png`

---

**Report Generated**: {output_dir / 'e002_report.md'}
